"""SAM3 image inference through the locally installed Transformers API."""

import cv2
import numpy as np
from PIL import Image

from components.image_io import load_image as _load_image

def _pick_device():
    import torch

    if not torch.cuda.is_available():
        return "cpu"
    index = max(range(torch.cuda.device_count()),
                key=lambda i: torch.cuda.get_device_properties(i).total_memory)
    return f"cuda:{index}"


def share_sam3_vision_weights(predictor, segmenter):
    """Share only verified ViT parameter storage in the serialized inference worker."""
    import torch
    import transformers

    checkpoint = "facebook/sam3"
    if transformers.__version__ != "5.18.0" or predictor.model_id != checkpoint or segmenter.model_id != checkpoint:
        return 0
    from transformers import Sam3Model, Sam3TrackerVideoModel, Sam3ViTModel

    video, text = predictor.model, segmenter.model
    if type(video) is not Sam3TrackerVideoModel or type(text) is not Sam3Model:
        return 0
    if video.training or text.training or video.name_or_path != checkpoint or text.name_or_path != checkpoint:
        return 0
    source = getattr(video.vision_encoder, "backbone", None)
    target = getattr(text.vision_encoder, "backbone", None)
    if type(source) is not Sam3ViTModel or type(target) is not Sam3ViTModel:
        return 0
    # The parent configs may declare different dtypes; validate the loaded tensors below.
    source_config, target_config = source.config.to_dict(), target.config.to_dict()
    source_config.pop("dtype", None)
    target_config.pop("dtype", None)
    if source_config != target_config:
        return 0

    left, right = dict(source.named_parameters()), dict(target.named_parameters())
    if len(left) != 516 or left.keys() != right.keys():
        return 0
    replacements = []
    shared_bytes = 0
    for name, original in left.items():
        duplicate = right[name]
        if (original.device.type != "cuda" or original.device != duplicate.device
                or original.dtype != torch.float32 or duplicate.dtype != torch.float32
                or original.shape != duplicate.shape or not original.is_contiguous() or not duplicate.is_contiguous()):
            return 0
        shared_bytes += original.numel() * original.element_size()
        if original.data_ptr() == duplicate.data_ptr():
            continue
        # Compare FP32 bits, including signed zero, before changing any parameter.
        try:
            identical = torch.equal(original.view(torch.int32), duplicate.view(torch.int32))
        except RuntimeError:
            return 0
        if not identical:
            return 0
        parent, attribute = name.rsplit(".", 1)
        alias = torch.nn.Parameter(original.detach(), requires_grad=duplicate.requires_grad)
        replacements.append((target.get_submodule(parent), attribute, alias))
    for module, name, alias in replacements:
        setattr(module, name, alias)
    return shared_bytes


class Sam3Segmenter:
    """Load SAM3 on first use and reuse it across images.

    Uses cached weights only. Automatic device selection prefers the GPU with
    the most memory, including AMD GPUs exposed via torch.cuda. FP32 matches
    the existing sam3-demo environment's working ROCm configuration.
    """

    def __init__(self, model_id="facebook/sam3", device=None):
        self.model_id = str(model_id)
        self.device = device
        self.model = None
        self.processor = None

    def _load_model(self):
        if self.model is not None:
            return
        import torch
        from transformers import Sam3Model, Sam3Processor
        from components.tracking.edgetam import bind_cuda_device

        device = self.device or _pick_device()
        bind_cuda_device(device)
        processor = Sam3Processor.from_pretrained(self.model_id, local_files_only=True)
        model, info = Sam3Model.from_pretrained(
            self.model_id, local_files_only=True, output_loading_info=True)
        if info.get("missing_keys") or info.get("mismatched_keys"):
            raise ValueError("Checkpoint does not contain all required SAM3 detection weights")
        model = model.to(device=device, dtype=torch.float32).eval()
        self.processor, self.model = processor, model
        self.device = str(model.device)

    def segment(self, image, prompt="miniature", *, threshold=0.5):
        """Return original-size boolean masks, xyxy pixel boxes, and scores.

        Input arrays use OpenCV BGR order. The returned image is BGR too.
        No files are saved and no detection or homography tools are called.
        """
        image = _load_image(image)
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        threshold = float(threshold)
        if not np.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        self._load_model()
        import torch

        if torch.cuda.is_available() and self.model.device.type == "cuda":
            torch.cuda.set_device(self.model.device)
        pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        inputs = self.processor(images=pil_image, text=prompt, return_tensors="pt").to(self.model.device)
        with torch.inference_mode():
            outputs = self.model(**inputs)
            result = self.processor.post_process_instance_segmentation(
                outputs, threshold=threshold, mask_threshold=0.5,
                target_sizes=inputs["original_sizes"].tolist(),
            )[0]
        height, width = image.shape[:2]
        masks = result["masks"].detach().cpu().numpy().astype(bool).reshape(-1, height, width)
        return {
            "image": image, "prompt": prompt, "threshold": threshold,
            "width": width, "height": height,
            "masks": masks,
            "boxes": result["boxes"].detach().cpu().numpy().astype(np.float32).reshape(-1, 4),
            "scores": result["scores"].detach().cpu().numpy().astype(np.float32).reshape(-1),
        }
