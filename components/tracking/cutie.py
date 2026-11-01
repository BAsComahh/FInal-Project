"""Causal mask propagation with the official hkchengrex/Cutie inference core.

Install the official source in ``vendor/cutie`` or the active environment.
The released ``cutie-base-mega.pth`` goes in its ``weights`` directory, or
``cache_dir`` alongside the two ResNet checkpoints requested by Cutie's model.
No optional dependency or checkpoint is downloaded by this adapter.
"""

from numbers import Integral
from pathlib import Path
import sys

import numpy as np


_REPOSITORY = "https://github.com/hkchengrex/Cutie"
_CHECKPOINT = "cutie-base-mega.pth"
_BACKBONES = (
    "resnet18-5c106cde.pth",
    "resnet50-19c8e357.pth",
)


class CutieTracker:
    def __init__(self, model_id=None, device=None, cache_dir=None):
        self.model_id = str(model_id) if model_id is not None else _CHECKPOINT
        self.device = device
        self.cache_dir = Path(cache_dir).expanduser().resolve() if cache_dir else None
        self.load_progress = None
        self.model = self.processor = None
        self._core_type = None
        self.reset()

    def load(self):
        """Load local official weights; keep optional imports out of app startup."""
        if self.model is not None:
            return
        self.load_progress = ("Loading Cutie dependencies", None, None)
        try:
            project = Path(__file__).resolve().parents[2]
            dependencies = project / "outputs" / "tracking_dependencies"
            if dependencies.is_dir() and str(dependencies) not in sys.path:
                sys.path.insert(0, str(dependencies))
            repository = project / "vendor" / "cutie"
            if (repository / "cutie" / "inference" / "inference_core.py").is_file():
                if str(repository) not in sys.path:
                    sys.path.insert(0, str(repository))
            try:
                import torch
                import cutie
                from hydra import compose, initialize_config_dir
                from omegaconf import open_dict
                from cutie.inference.inference_core import InferenceCore
                from cutie.inference.utils.args_utils import get_dataset_cfg
                from cutie.model.cutie import CUTIE
            except ImportError as error:
                raise RuntimeError(
                    f"Cutie dependencies are unavailable ({error}). Clone {_REPOSITORY} "
                    "into vendor/cutie (or install its official package), and install "
                    "hydra-core>=1.3.2 in this Python environment with compatible "
                    "torch and numpy. "
                    f"Official setup: {_REPOSITORY}#installation"
                ) from error

            package = Path(next(iter(cutie.__path__))).resolve()
            if self.model_id in ("cutie-base-mega", _CHECKPOINT):
                candidates = ([self.cache_dir / _CHECKPOINT] if self.cache_dir else [])
                candidates.append(package.parent / "weights" / _CHECKPOINT)
                checkpoint = next((path for path in candidates if path.is_file()), candidates[0])
            else:
                checkpoint = Path(self.model_id).expanduser().resolve()
            if not checkpoint.is_file():
                raise FileNotFoundError(
                    f"Cutie checkpoint is missing: {checkpoint}. Download "
                    f"{_REPOSITORY}/releases/download/v1.0/{_CHECKPOINT} and place it "
                    "there, or pass its local path as model_id."
                )

            # Cutie's supported resnet_model_path avoids its constructor downloading backbones.
            backbone_dir = self.cache_dir or Path(torch.hub.get_dir()) / "checkpoints"
            missing = [name for name in _BACKBONES if not (backbone_dir / name).is_file()]
            if missing:
                links = ", ".join(f"https://download.pytorch.org/models/{name}" for name in missing)
                raise FileNotFoundError(
                    f"Cutie's pretrained ResNet initialization needs {', '.join(missing)} "
                    f"in {backbone_dir}. Download from {links}. "
                    "These are required by the official CUTIE constructor before it loads "
                    "the released tracking checkpoint."
                )
            if self.device is None:
                self.device = (
                    f"cuda:{max(range(torch.cuda.device_count()), key=lambda i: torch.cuda.get_device_properties(i).total_memory)}"
                    if torch.cuda.is_available() else "cpu"
                )
            self.load_progress = ("Preparing Cutie configuration", None, None)
            with initialize_config_dir(version_base="1.3.2", config_dir=str(package / "config")):
                cfg = compose(config_name="eval_config", overrides=["dataset=generic"])
            get_dataset_cfg(cfg)
            cfg.weights = str(checkpoint)
            cfg.max_internal_size = 480
            with open_dict(cfg.model):
                cfg.model.resnet_model_path = str(backbone_dir)
            self.load_progress = ("Loading Cutie weights", None, None)
            model = CUTIE(cfg)
            weights = torch.load(checkpoint, map_location="cpu", weights_only=True)
            model.load_weights(weights)
            self.load_progress = (f"Moving Cutie to {self.device}", None, None)
            model = model.to(device=self.device, dtype=torch.float32).eval().requires_grad_(False)
            self.model, self._core_type = model, InferenceCore
        finally:
            self.load_progress = None

    def reset(self):
        """Discard every per-video memory store while retaining the loaded model."""
        self.processor = None
        self.object_ids = []
        self.index = -1
        self.source_frame = None
        self._image_shape = None

    @staticmethod
    def _validate_frame(frame):
        if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
                or frame.ndim != 3 or frame.shape[2] != 3 or min(frame.shape[:2]) < 1):
            raise ValueError("Cutie expects a nonempty uint8 BGR frame with shape (H, W, 3)")

    @staticmethod
    def _source_index(value, default):
        value = default if value is None else value
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or value < 0:
            raise ValueError("source_frame must be a nonnegative integer")
        return int(value)

    def _frame_tensor(self, frame):
        import torch

        rgb = np.ascontiguousarray(frame[..., ::-1].transpose(2, 0, 1))
        return torch.from_numpy(rgb).to(device=self.device, dtype=torch.float32).div_(255)

    def _prediction(self, output_prob, processor, object_ids, index, shape):
        labels = processor.output_prob_to_mask(output_prob).detach().cpu().numpy()
        if labels.shape != shape:
            raise RuntimeError(f"Cutie returned mask shape {labels.shape}; expected {shape}")
        masks = np.stack([labels == label for label in range(1, len(object_ids) + 1)])
        return {"object_ids": list(object_ids), "masks": masks, "frame_idx": index}

    def initialize(self, frame, object_ids, masks, *, source_frame=None):
        """Memorize initial instances, mapping external IDs to consecutive labels."""
        self._validate_frame(frame)
        object_ids = list(object_ids)
        if (not object_ids or any(isinstance(value, (bool, np.bool_))
                                 or not isinstance(value, Integral) or value <= 0
                                 for value in object_ids)
                or len(set(object_ids)) != len(object_ids)):
            raise ValueError("Cutie object IDs must be distinct positive integers")
        object_ids = [int(value) for value in object_ids]
        shape = frame.shape[:2]
        if (not isinstance(masks, np.ndarray) or masks.dtype != np.bool_
                or masks.shape != (len(object_ids), *shape)):
            raise ValueError("Initial masks must be bool with shape (len(object_ids), H, W)")
        source_frame = self._source_index(source_frame, 0)
        labels = np.zeros(shape, dtype=np.int64)
        # Match the app's drawing order: the last registered mask owns overlapping pixels.
        for label, mask in enumerate(masks, start=1):
            labels[mask] = label
        self.load()
        import torch

        processor = self._core_type(self.model, cfg=self.model.cfg)
        with torch.inference_mode():
            output_prob = processor.step(
                self._frame_tensor(frame), torch.from_numpy(labels).to(self.device),
                objects=list(range(1, len(object_ids) + 1)), idx_mask=True,
            )
            prediction = self._prediction(output_prob, processor, object_ids, 0, shape)
        self.processor, self.object_ids = processor, object_ids
        self.index, self.source_frame, self._image_shape = 0, source_frame, shape
        return prediction

    def propagate(self, frame, *, source_frame=None):
        """Consume one later frame without replay, lookahead, or prompt edits."""
        if self.processor is None:
            raise ValueError("Initialize Cutie with the registered masks before propagation")
        self._validate_frame(frame)
        if frame.shape[:2] != self._image_shape:
            raise ValueError("Frame size changed; reset and register the new video first")
        source_frame = self._source_index(source_frame, self.source_frame + 1)
        if source_frame <= self.source_frame:
            raise ValueError("Cutie propagation requires a strictly later source frame")
        import torch

        try:
            with torch.inference_mode():
                output_prob = self.processor.step(self._frame_tensor(frame))
                prediction = self._prediction(
                    output_prob, self.processor, self.object_ids, self.index + 1, self._image_shape,
                )
        except Exception:
            # A failed official step can leave partially updated memory; do not reuse it.
            self.reset()
            raise
        self.index += 1
        self.source_frame = source_frame
        return prediction
