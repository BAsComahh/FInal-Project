"""Causal EdgeTAM tracking through Transformers' supported streaming API.

The Transformers conversion is ``yonigozlan/EdgeTAM-hf`` (Apache-2.0).
Only local checkpoints are loaded; the project cache and the existing default
Hugging Face cache are both supported. Initial SAM3 masks are mask prompts,
without generating another set of click prompts or editing tracking history.
"""

from numbers import Integral
from pathlib import Path
import sys

import numpy as np


_MODEL_ID = "yonigozlan/EdgeTAM-hf"
_REVISION = "c266ce53b3fc00f0f495b583f6a116c4e57f53bb"
_DOCUMENTATION = "https://huggingface.co/docs/transformers/model_doc/edgetam_video"


class EdgeTamTracker:
    def __init__(self, model_id=None, device=None, cache_dir=None):
        self.model_id = str(model_id) if model_id is not None else _MODEL_ID
        self.device = device
        self.cache_dir = (
            Path(cache_dir).expanduser().resolve() if cache_dir is not None
            else Path(__file__).resolve().parents[2] / "outputs" / "model_cache"
        )
        self.load_progress = None
        self.model = self.processor = self.session = None
        self.reset()

    def _from_pretrained(self, factory, *, raw_config=False, **kwargs):
        # Existing user caches remain readable when the project cache is empty.
        if self.model_id == _MODEL_ID:
            kwargs.setdefault("revision", _REVISION)
        error = None
        for cache_dir in (str(self.cache_dir), None):
            try:
                load = factory.get_config_dict if raw_config else factory.from_pretrained
                return load(
                    self.model_id, cache_dir=cache_dir, local_files_only=True, **kwargs,
                )
            except OSError as caught:
                error = caught
        raise RuntimeError(
            f"EdgeTAM checkpoint '{self.model_id}' is unavailable locally. Download the "
            "Transformers checkpoint with huggingface_hub.snapshot_download "
            f"(repo_id='{self.model_id}', cache_dir=r'{self.cache_dir}'"
            f"{', revision=' + repr(_REVISION) if self.model_id == _MODEL_ID else ''}), or pass its "
            "local snapshot directory as model_id. The original Meta edgetam.pt file "
            f"is a different format. Model: https://huggingface.co/{self.model_id}; "
            f"backend documentation: {_DOCUMENTATION}. Original error: {error}"
        ) from error

    def load(self):
        """Load local weights once, keeping optional dependencies lazy."""
        if self.model is not None:
            return
        self.load_progress = ("Loading EdgeTAM dependencies", None, None)
        try:
            dependencies = Path(__file__).resolve().parents[2] / "outputs" / "tracking_dependencies"
            if dependencies.is_dir() and str(dependencies) not in sys.path:
                sys.path.insert(0, str(dependencies))
            try:
                import torch
                from transformers import EdgeTamVideoConfig, Sam2VideoProcessor
                from components.sam3.video.loading import weight_loading_progress
                from .edgetam_compat import video_model_class
            except ImportError as error:
                raise RuntimeError(
                    f"EdgeTAM dependencies are unavailable ({error}). Use the project's "
                    "sam3-demo environment with compatible torch/torchvision and "
                    "Transformers 5.18.0, whose EdgeTamVideoModel and mask-prompt "
                    f"Sam2VideoProcessor APIs this adapter uses. See {_DOCUMENTATION}."
                ) from error

            if self.device is None:
                self.device = (
                    f"cuda:{max(range(torch.cuda.device_count()), key=lambda i: torch.cuda.get_device_properties(i).total_memory)}"
                    if torch.cuda.is_available() else "cpu"
                )
            self.load_progress = ("Loading EdgeTAM processor", None, None)
            processor = self._from_pretrained(Sam2VideoProcessor)
            config_data, _ = self._from_pretrained(EdgeTamVideoConfig, raw_config=True)
            # HF 5.18 creates default vision configs while formatting repr(), causing
            # an unwanted Hub lookup. The checkpoint supplies its complete config.
            config_data["has_no_defaults_at_init"] = True
            config_data["vision_config"]["has_no_defaults_at_init"] = True
            config = EdgeTamVideoConfig.from_dict(config_data)

            def report(progress):
                self.load_progress = progress

            self.load_progress = ("Loading EdgeTAM weights", None, None)
            try:
                with weight_loading_progress(report):
                    model, info = self._from_pretrained(video_model_class(), config=config, output_loading_info=True)
            except ImportError as error:
                raise RuntimeError(
                    f"EdgeTAM's backbone dependency is unavailable ({error}). Install "
                    "timm with RepViT support in this Python environment, alongside "
                    f"compatible torch/torchvision. See {_DOCUMENTATION}."
                ) from error
            if info.get("missing_keys") or info.get("mismatched_keys"):
                raise ValueError("The checkpoint is missing compatible EdgeTAM video weights")
            self.load_progress = (f"Moving EdgeTAM to {self.device}", None, None)
            try:
                model = model.to(device=self.device, dtype=torch.float32).eval().requires_grad_(False)
            except RuntimeError as error:
                raise RuntimeError(
                    f"EdgeTAM could not use device {self.device}: {error}. Use a "
                    "compatible PyTorch/device environment or select device='cpu'."
                ) from error
            self.model, self.processor = model, processor
        finally:
            self.load_progress = None

    def reset(self):
        """Discard the official per-video session while retaining loaded weights."""
        if self.session is not None:
            self.session.reset_inference_session()
        self.session = None
        self.object_ids = []
        self.index = -1
        self.source_frame = None
        self._image_shape = None
        self._last_frame = None

    @staticmethod
    def _validate_frame(frame):
        if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
                or frame.ndim != 3 or frame.shape[2] != 3 or min(frame.shape[:2]) < 1):
            raise ValueError("EdgeTAM expects a nonempty uint8 BGR frame with shape (H, W, 3)")

    @staticmethod
    def _source_index(value, default):
        value = default if value is None else value
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or value < 0:
            raise ValueError("source_frame must be a nonnegative integer")
        return int(value)

    def _infer(self, frame, session, object_ids, index, source_frame):
        import torch
        from PIL import Image

        inputs = self.processor(
            images=Image.fromarray(np.ascontiguousarray(frame[..., ::-1])), return_tensors="pt",
        )
        with torch.inference_mode():
            outputs = self.model(
                inference_session=session, frame_idx=index, frame=inputs.pixel_values[0],
            )
            output_ids = list(outputs.object_ids)
            if (len(output_ids) != len(object_ids) or set(output_ids) != set(object_ids)
                    or outputs.frame_idx != index):
                raise RuntimeError("EdgeTAM returned inconsistent object IDs or frame index")
            order = [output_ids.index(obj_id) for obj_id in object_ids]
            masks = self.processor.post_process_masks(
                [outputs.pred_masks], original_sizes=inputs.original_sizes, binarize=True,
            )[0]
            if tuple(masks.shape) != (len(object_ids), 1, *frame.shape[:2]):
                raise RuntimeError(f"EdgeTAM returned unexpected mask shape {tuple(masks.shape)}")
            prediction = {
                "object_ids": list(object_ids),
                "masks": masks[:, 0][order].detach().cpu().numpy().astype(bool, copy=False),
                "frame_idx": index,
                "source_frame_index": source_frame,
            }
            if outputs.object_score_logits is not None:
                logits = outputs.object_score_logits.reshape(-1)
                if logits.numel() != len(object_ids):
                    raise RuntimeError("EdgeTAM returned inconsistent object presence scores")
                prediction["object_score_logits"] = logits[order].detach().float().cpu().tolist()
        return prediction

    def initialize(self, frame, object_ids, masks, *, source_frame=None):
        """Memorize the registered masks on the first processed frame."""
        self._validate_frame(frame)
        object_ids = list(object_ids)
        if (not object_ids or any(isinstance(value, (bool, np.bool_))
                                 or not isinstance(value, Integral) or value <= 0
                                 for value in object_ids)
                or len(set(object_ids)) != len(object_ids)):
            raise ValueError("EdgeTAM object IDs must be distinct positive integers")
        object_ids = [int(value) for value in object_ids]
        if (not isinstance(masks, np.ndarray) or masks.dtype != np.bool_
                or masks.shape != (len(object_ids), *frame.shape[:2])):
            raise ValueError("Initial masks must be bool with shape (len(object_ids), H, W)")
        source_frame = self._source_index(source_frame, 0)
        self.load()
        import torch

        self.reset()
        session = self.processor.init_video_session(
            inference_device=self.device, inference_state_device="cpu",
            video_storage_device="cpu", processing_device="cpu", dtype=torch.float32,
        )
        with torch.inference_mode():
            self.processor.add_inputs_to_inference_session(
                # The official session consumes this list as prompts are processed.
                inference_session=session, frame_idx=0, obj_ids=list(object_ids),
                input_masks=list(masks), original_size=frame.shape[:2],
            )
            prediction = self._infer(frame, session, object_ids, 0, source_frame)
        self.session, self.object_ids = session, object_ids
        self.index, self.source_frame, self._image_shape = 0, source_frame, frame.shape[:2]
        self._last_frame = frame.copy()
        return prediction

    def _edit_frame(self, frame, source_frame):
        if self.session is None:
            raise ValueError("Initialize EdgeTAM before editing a tracked object")
        self._validate_frame(frame)
        if frame.shape[:2] != self._image_shape:
            raise ValueError("Recovery frame size does not match its tracking session")
        source_frame = self._source_index(source_frame, self.source_frame)
        if source_frame < self.source_frame:
            raise ValueError("Recovery cannot apply prompts to an older source frame")
        if source_frame == self.source_frame and not np.array_equal(frame, self._last_frame):
            raise ValueError("A source frame number cannot refer to a different image")
        return source_frame, self.index + int(source_frame > self.source_frame)

    def correct_points(self, frame, points, labels, *, source_frame=None):
        """Refine one disposable candidate using frame-bound official prompts."""
        source_frame, _ = self._edit_frame(frame, source_frame)
        points, labels = np.asarray(points, dtype=float), list(labels)
        if (len(self.object_ids) != 1 or points.ndim != 2 or points.shape[1] != 2
                or not len(points) or len(points) != len(labels) or not np.isfinite(points).all()
                or any(label not in (0, 1) for label in labels)
                or (points < 0).any() or (points >= np.asarray(frame.shape[1::-1])).any()):
            raise ValueError("Candidate prompts require valid points and positive/negative labels")
        if source_frame > self.source_frame:
            self.propagate(frame, source_frame=source_frame)
        self.processor.add_inputs_to_inference_session(
            inference_session=self.session, frame_idx=self.index, obj_ids=self.object_ids[0],
            input_points=[[points.tolist()]], input_labels=[[labels]],
            original_size=frame.shape[:2], clear_old_inputs=False,
        )
        return self._infer(frame, self.session, self.object_ids, self.index, source_frame)

    def update_mask(self, frame, object_id, mask, *, source_frame=None):
        """Update an existing object without resetting other objects' memory."""
        source_frame, index = self._edit_frame(frame, source_frame)
        if (isinstance(object_id, (bool, np.bool_)) or not isinstance(object_id, Integral)
                or object_id not in self.object_ids or not isinstance(mask, np.ndarray)
                or mask.dtype != np.bool_ or mask.shape != frame.shape[:2] or not mask.any()):
            raise ValueError("Recovery requires a nonempty mask for an existing object")
        try:
            self.processor.add_inputs_to_inference_session(
                inference_session=self.session, frame_idx=index, obj_ids=[object_id],
                input_masks=[mask], original_size=frame.shape[:2],
            )
            return self._infer(frame, self.session, self.object_ids, index, source_frame)
        finally:
            # A failed forward may already have consumed this frame/cache index.
            # Reserve it; never reset unrelated objects or reuse it for a new image.
            self.index, self.source_frame = index, source_frame
            self._last_frame = frame.copy()

    def propagate(self, frame, *, source_frame=None):
        """Consume one later frame with persistent memory and no lookahead."""
        if self.session is None:
            raise ValueError("Initialize EdgeTAM with registered masks before propagation")
        self._validate_frame(frame)
        if frame.shape[:2] != self._image_shape:
            raise ValueError("Frame size changed; reset and register the new video first")
        source_frame = self._source_index(source_frame, self.source_frame + 1)
        if source_frame <= self.source_frame:
            raise ValueError("EdgeTAM propagation requires a strictly later source frame")
        try:
            # Dense indices describe processed frames, including when sampling a video.
            prediction = self._infer(frame, self.session, self.object_ids, self.index + 1, source_frame)
        except Exception:
            # An interrupted official forward may have partially updated the session.
            self.reset()
            raise
        self.index += 1
        self.source_frame = source_frame
        self._last_frame = frame.copy()
        return prediction
