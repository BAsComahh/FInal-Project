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

        device = self.device or _pick_device()
        if torch.cuda.is_available() and torch.device(device).type == "cuda":
            torch.cuda.set_device(torch.device(device))
        processor = Sam3Processor.from_pretrained(self.model_id, local_files_only=True)
        model = Sam3Model.from_pretrained(self.model_id, local_files_only=True)
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
