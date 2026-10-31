"""Point-prompted SAM3 segmentation, with cached image embeddings."""

import cv2
import numpy as np
from PIL import Image
import sys

from .segmenter import _load_image, _pick_device


def check_point_dependencies(tool="tools.sam3_click_segmenter"):
    """Fail before opening a viewer if its interpreter lacks SAM3 support."""
    try:
        import torch
        from transformers import Sam3TrackerModel, Sam3TrackerProcessor
    except ImportError as error:
        raise RuntimeError(
            f"SAM3 dependencies are unavailable in {sys.executable}. "
            "Run: conda run --no-capture-output -n sam3-demo python "
            f"-m {tool} inputs/test.png"
        ) from error
    return torch, Sam3TrackerModel, Sam3TrackerProcessor


class Sam3PointSegmenter:
    """Left/right click coordinates become positive/negative point prompts.

    The tracker model supplies point prompts for a still image; no tracking is
    performed. Weights and preprocessing come from the cached SAM3 checkpoint.
    """

    def __init__(self, model_id="facebook/sam3", device=None):
        self.model_id, self.device = str(model_id), device
        self.model = self.processor = None
        self.image = self._pil_image = self._embeddings = None

    def set_image(self, image):
        """Set an image path or OpenCV array; discard the previous image cache."""
        self.image = _load_image(image).copy()
        self._pil_image = Image.fromarray(cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB))
        self._embeddings = None

    def _load_model(self):
        if self.model is not None:
            return
        torch, Sam3TrackerModel, Sam3TrackerProcessor = check_point_dependencies()

        processor = Sam3TrackerProcessor.from_pretrained(self.model_id, local_files_only=True)
        model, info = Sam3TrackerModel.from_pretrained(
            self.model_id, local_files_only=True, output_loading_info=True)
        if info.get("missing_keys") or info.get("mismatched_keys"):
            raise ValueError("Checkpoint does not contain all required SAM3 point-prompt weights")
        model = model.to(device=self.device or _pick_device(), dtype=torch.float32).eval()
        self.processor, self.model = processor, model
        self.device = str(model.device)

    def segment(self, points, labels=None):
        """Segment one target from (N,2) original-pixel points, labels 1/0.

        Returns the highest predicted-IoU candidate, a full-size boolean mask,
        and its xyxy pixel box (exclusive upper bound), or None for an empty mask.
        """
        if self.image is None:
            raise ValueError("Call set_image before segment")
        points = np.asarray(points, dtype=np.float32)
        if points.ndim != 2 or points.shape[1] != 2 or len(points) == 0 or not np.isfinite(points).all():
            raise ValueError("points must be a non-empty finite (N,2) array")
        height, width = self.image.shape[:2]
        if np.any(points < 0) or np.any(points[:, 0] >= width) or np.any(points[:, 1] >= height):
            raise ValueError("points must be inside the image")
        labels = np.ones(len(points), dtype=np.int64) if labels is None else np.asarray(labels)
        if labels.shape != (len(points),) or not np.isin(labels, [0, 1]).all() or not np.any(labels == 1):
            raise ValueError("labels must contain one 0/1 value per point and at least one positive point")
        self._load_model()
        import torch

        inputs = self.processor(images=self._pil_image, input_points=[[points.tolist()]],
                                input_labels=[[labels.tolist()]], return_tensors="pt").to(self.model.device)
        if self._embeddings is not None:
            inputs.pop("pixel_values")
            inputs["image_embeddings"] = self._embeddings
        with torch.inference_mode():
            outputs = self.model(**inputs, multimask_output=True)
            self._embeddings = outputs.image_embeddings
            scores = outputs.iou_scores[0, 0]
            best = int(scores.argmax().item())
            selected = outputs.pred_masks[:, :, best:best + 1]
            mask = self.processor.post_process_masks(selected, inputs["original_sizes"])[0][0, 0]
        mask = mask.detach().cpu().numpy().astype(bool)
        ys, xs = np.nonzero(mask)
        box = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1] if len(xs) else None
        return {"mask": mask, "box": box, "score": float(scores[best].item()),
                "points": points.tolist(), "labels": labels.astype(int).tolist()}
