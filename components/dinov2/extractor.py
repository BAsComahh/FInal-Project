"""Image embeddings using the official Transformers DINOv2 backbone interface."""

from math import ceil
from pathlib import Path
from importlib.metadata import version

import numpy as np
from PIL import Image


def normalize_rows(features):
    features = np.asarray(features, dtype=np.float32)
    if features.ndim != 2 or features.shape[1] < 1:
        raise ValueError("Features must be a two-dimensional array with a positive embedding dimension")
    norms = np.linalg.norm(features, axis=1, keepdims=True)
    if not np.isfinite(features).all() or (norms <= 1e-12).any():
        raise ValueError("Feature vectors must be finite and nonzero")
    return features / norms


class DinoV2Extractor:
    def __init__(self, model_id="facebook/dinov2-small", device=None, *, allow_download=False):
        self.model_id, self.device = str(model_id), device
        self.allow_download = allow_download
        self.processor = self.model = None
        self.model_commit = None

    def load(self):
        if self.model is not None:
            return
        import torch
        from transformers import AutoImageProcessor, AutoModel

        if self.device is None:
            self.device = (f"cuda:{max(range(torch.cuda.device_count()), key=lambda i: torch.cuda.get_device_properties(i).total_memory)}"
                           if torch.cuda.is_available() else "cpu")
        from components.tracking.edgetam import bind_cuda_device

        bind_cuda_device(self.device)
        self.processor = AutoImageProcessor.from_pretrained(
            self.model_id, local_files_only=not self.allow_download)
        model = AutoModel.from_pretrained(self.model_id, local_files_only=not self.allow_download)
        if model.config.model_type not in ("dinov2", "dinov2_with_registers"):
            raise ValueError("Choose a DINOv2 backbone checkpoint")
        self.model = model.to(device=self.device, dtype=torch.float32).eval().requires_grad_(False)
        self.model_commit = getattr(model.config, "_commit_hash", None)
        if self.model_commit is None and not Path(self.model_id).is_dir():
            from huggingface_hub import try_to_load_from_cache

            config = try_to_load_from_cache(self.model_id, "config.json")
            if isinstance(config, str) and Path(config).parent.parent.name == "snapshots":
                self.model_commit = Path(config).parent.name

    def prepare_image(self, image):
        """Composite the alpha mask, then pad to preserve the whole object.

        This object-specific preparation is our policy. The pretrained official
        processor still performs resizing, center crop and normalization.
        """
        self.load()
        rgba = image.convert("RGBA")
        if rgba.getchannel("A").getbbox() is None:
            raise ValueError("Cannot embed an empty alpha mask")
        color = tuple(round(value * 255) for value in self.processor.image_mean)
        canvas = Image.new("RGBA", rgba.size, (*color, 255))
        canvas.alpha_composite(rgba)
        rgb = canvas.convert("RGB")
        ratio = 1.0
        if self.processor.do_center_crop:
            crop = self.processor.crop_size
            edge = self.processor.size.get("shortest_edge")
            if edge is None or crop["height"] != crop["width"]:
                raise ValueError("Expected the DINOv2 square center-crop processor configuration")
            ratio = max(1.0, edge / crop["height"])
        side = max(1, ceil(max(rgb.size) * ratio))
        square = Image.new("RGB", (side, side), color)
        square.paste(rgb, ((side - rgb.width) // 2, (side - rgb.height) // 2))
        return square

    def encode(self, images, *, batch_size=8):
        """Return float32 L2-normalized CLS vectors; accepts PIL RGB/RGBA images."""
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.load()
        import torch

        from components.tracking.edgetam import bind_cuda_device

        bind_cuda_device(self.device)

        batches = []
        for start in range(0, len(images), batch_size):
            prepared = [self.prepare_image(image) for image in images[start:start + batch_size]]
            inputs = self.processor(images=prepared, return_tensors="pt").to(self.device)
            with torch.inference_mode():
                # Official documentation: token zero is the whole-image CLS embedding.
                features = self.model(**inputs).last_hidden_state[:, 0, :]
            batches.append(features.float().cpu().numpy())
        if not batches:
            return np.empty((0, self.model.config.hidden_size), dtype=np.float32)
        return normalize_rows(np.concatenate(batches))

    def metadata(self):
        self.load()
        return {"model": self.model_id, "model_commit": self.model_commit,
                "transformers_version": version("transformers"),
                "embedding": "cls", "dimension": self.model.config.hidden_size,
                "normalization": "l2", "dtype": "float32",
                "input_policy": "alpha_over_image_mean_then_square_pad_for_official_center_crop",
                "processor": self.processor.to_dict()}
