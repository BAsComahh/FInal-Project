"""Causal EdgeTAM tracking through Transformers' supported streaming API.

The Transformers conversion is ``yonigozlan/EdgeTAM-hf`` (Apache-2.0).
Only local checkpoints are loaded; the project cache and the existing default
Hugging Face cache are both supported. Initial SAM3 masks are mask prompts,
without generating another set of click prompts or editing tracking history.
"""

from numbers import Integral
from pathlib import Path
import sys
import types

import numpy as np


_MODEL_ID = "yonigozlan/EdgeTAM-hf"
_REVISION = "c266ce53b3fc00f0f495b583f6a116c4e57f53bb"
_DOCUMENTATION = "https://huggingface.co/docs/transformers/model_doc/edgetam_video"

# Controlled CUDA/HIP acceleration toggles for Transformers 5.18.0 EdgeTAM:
# - _ENABLE_CUDA_FAST_ATTENTION: local FP16 autocast + SDPA backend selection on
#   memory_attention & spatial_perceiver (zero Conv2d layers) plus per-_infer()
#   Layer-0 self-attention caching across objects on the same frame.
# - _ENABLE_CUDA_GPU_STATE: keep prune-bounded session memory on the active GPU
#   instead of synchronous CPU<->GPU transfers on every frame.
_ENABLE_CUDA_FAST_ATTENTION = True
_ENABLE_CUDA_GPU_STATE = True


def _resolve_device(device):
    import torch

    target = torch.device("cpu" if device is None else device)
    if target.type == "cuda" and target.index is None and torch.cuda.is_available():
        target = torch.device("cuda", torch.cuda.current_device())
    return target


def bind_cuda_device(device):
    """Ensure the calling worker thread's active HIP/CUDA device matches the selected GPU."""
    import torch

    if device is not None and torch.cuda.is_available():
        target = torch.device(device)
        if target.type == "cuda":
            torch.cuda.set_device(target)


def _install_cuda_attention_accel(model):
    """Wrap Transformers 5.18.0 memory_attention & spatial_perceiver for CUDA/HIP."""
    if not _ENABLE_CUDA_FAST_ATTENTION or getattr(model, "_edgetam_cuda_accel_installed", False):
        return False
    ma = getattr(model, "memory_attention", None)
    sp = getattr(model, "spatial_perceiver", None)
    layers = getattr(ma, "layers", None) if ma is not None else None
    if ma is None or sp is None or not layers:
        return False
    layer0 = layers[0]
    required_ma = ("rotary_emb", "position_ids", "position_ids_k", "layer_norm")
    required_l0 = ("layer_norm1", "self_attn", "dropout1", "layer_norm2", "cross_attn_image",
                   "dropout2", "layer_norm3", "mlp", "dropout3")
    if not (all(hasattr(ma, attr) for attr in required_ma) and all(hasattr(layer0, attr) for attr in required_l0)):
        return False

    import torch
    from torch.nn.attention import SDPBackend, sdpa_kernel

    orig_ma_forward = ma.forward
    orig_sp_forward = sp.forward
    fast_backends = [SDPBackend.EFFICIENT_ATTENTION, SDPBackend.FLASH_ATTENTION, SDPBackend.MATH]
    model._edgetam_layer0_cache = None

    def fast_ma_forward(
        current_vision_features,
        memory,
        current_vision_position_embeddings=None,
        memory_posision_embeddings=None,
        num_object_pointer_tokens=0,
        num_spatial_memory_tokens=-1,
    ):
        if not current_vision_features.is_cuda:
            return orig_ma_forward(
                current_vision_features=current_vision_features,
                memory=memory,
                current_vision_position_embeddings=current_vision_position_embeddings,
                memory_posision_embeddings=memory_posision_embeddings,
                num_object_pointer_tokens=num_object_pointer_tokens,
                num_spatial_memory_tokens=num_spatial_memory_tokens,
            )
        with torch.autocast("cuda", dtype=torch.float16), sdpa_kernel(fast_backends):
            cache = getattr(model, "_edgetam_layer0_cache", None)
            if (
                cache is None
                or current_vision_features.ndim != 3
                or current_vision_features.shape[1] != 1
            ):
                return orig_ma_forward(
                    current_vision_features=current_vision_features,
                    memory=memory,
                    current_vision_position_embeddings=current_vision_position_embeddings,
                    memory_posision_embeddings=memory_posision_embeddings,
                    num_object_pointer_tokens=num_object_pointer_tokens,
                    num_spatial_memory_tokens=num_spatial_memory_tokens,
                ).float()

            key = (
                id(current_vision_features),
                current_vision_features.data_ptr(),
                tuple(current_vision_features.shape),
                id(current_vision_position_embeddings),
                current_vision_position_embeddings.data_ptr()
                if current_vision_position_embeddings is not None
                else 0,
            )
            cached = cache.get(key)
            if cached is None:
                cache.clear()
                out0 = current_vision_features
                if current_vision_position_embeddings is not None:
                    out0 = out0 + 0.1 * current_vision_position_embeddings
                out0 = out0.transpose(0, 1)
                rope_pe = ma.rotary_emb(out0, ma.position_ids)
                rope_pe_k = ma.rotary_emb(out0, ma.position_ids_k)
                q0 = out0.unsqueeze(1) if out0.ndim == 3 else out0
                first_layer = ma.layers[0]
                q_norm = first_layer.layer_norm1(q0)
                q_sa, _ = first_layer.self_attn(
                    query=q_norm, key=q_norm, value=q_norm, position_embeddings=rope_pe,
                )
                q_after_sa = q0 + first_layer.dropout1(q_sa)
                q_ln2 = first_layer.layer_norm2(q_after_sa)
                cached = (q_after_sa, q_ln2, rope_pe, rope_pe_k)
                cache[key] = cached
            q_after_sa, q_ln2, rope_pe, rope_pe_k = cached
            mem = memory.transpose(0, 1).unsqueeze(1)
            mem_pe = (
                memory_posision_embeddings.transpose(0, 1).unsqueeze(1)
                if memory_posision_embeddings is not None
                else None
            )
            first_layer = ma.layers[0]
            q_ca, _ = first_layer.cross_attn_image(
                query=q_ln2,
                key=mem if mem_pe is None else mem + mem_pe,
                value=mem,
                position_embeddings=rope_pe,
                position_embeddings_k=rope_pe_k,
                num_k_exclude_rope=num_object_pointer_tokens,
                rope_k_repeat=num_spatial_memory_tokens,
            )
            queries = q_after_sa + first_layer.dropout2(q_ca)
            output = queries + first_layer.dropout3(first_layer.mlp(first_layer.layer_norm3(queries)))
            for layer in ma.layers[1:]:
                output = layer(
                    queries=output,
                    keys=mem,
                    key_point_embedding=mem_pe,
                    rope_position_embeddings=rope_pe,
                    rope_position_embeddings_k=rope_pe_k,
                    num_k_exclude_rope=num_object_pointer_tokens,
                    rope_k_repeat=num_spatial_memory_tokens,
                )
            return ma.layer_norm(output).transpose(0, 1).float()

    def fast_sp_forward(hidden_states, positional_encoding=None):
        if not hidden_states.is_cuda:
            return orig_sp_forward(hidden_states, positional_encoding)
        with torch.autocast("cuda", dtype=torch.float16), sdpa_kernel(fast_backends):
            latents, pos = orig_sp_forward(hidden_states, positional_encoding)
            return latents.float(), (pos.float() if pos is not None else None)

    ma.forward = fast_ma_forward
    sp.forward = fast_sp_forward
    model._edgetam_cuda_accel_installed = True
    return True


def _store_output_pageable(
    self,
    obj_idx,
    frame_idx,
    output_key=None,
    output_value=None,
    is_conditioning_frame=True,
):
    import torch

    storage_key = "cond_frame_outputs" if is_conditioning_frame else "non_cond_frame_outputs"
    if output_key is None and isinstance(output_value, dict):
        self.output_dict_per_obj[obj_idx][storage_key][frame_idx] = {}
        for key, value in output_value.items():
            self.store_output(obj_idx, frame_idx, key, value, is_conditioning_frame)
        return
    if output_key in ("object_pointer", "object_score_logits"):
        self.output_dict_per_obj[obj_idx][storage_key][frame_idx][output_key] = output_value
    elif isinstance(output_value, torch.Tensor):
        self.output_dict_per_obj[obj_idx][storage_key][frame_idx][output_key] = output_value.detach().to(
            self.inference_state_device, non_blocking=False
        )
    else:
        self.output_dict_per_obj[obj_idx][storage_key][frame_idx][output_key] = output_value


def _cache_vision_features_pageable(self, frame_idx, features):
    import torch

    if len(self._vision_features) >= self.max_vision_features_cache_size:
        self._vision_features.pop(min(self._vision_features.keys()))
    cached = {}
    for key, value in features.items():
        if isinstance(value, torch.Tensor):
            cached[key] = value.detach().to(self.inference_state_device, non_blocking=False)
        elif isinstance(value, (list, tuple)) and value and isinstance(value[0], torch.Tensor):
            cached[key] = [v.detach().to(self.inference_state_device, non_blocking=False) for v in value]
        else:
            cached[key] = value
    self._vision_features[frame_idx] = cached


def configure_video_session(session, device):
    """Avoid hipHostMalloc pinned-memory accumulation and redundant 1-frame feature transfers."""
    if session is None:
        return None
    if hasattr(session, "cache") and session.cache is not None:
        session.cache.inference_state_device = device
        session.cache.cache_vision_features = types.MethodType(_cache_vision_features_pageable, session.cache)
    session.store_output = types.MethodType(_store_output_pageable, session)
    return session


def prune_video_session(session, model, current_idx):
    """Bound streaming session state to the exact windows read by Transformers 5.18.0."""
    import torch

    if session is None or model is None or current_idx is None:
        return
    if session.processed_frames:
        for k in [k for k in session.processed_frames if k < current_idx]:
            session.processed_frames.pop(k, None)
    mem_window = max(0, int(getattr(model, "num_maskmem", getattr(model.config, "num_maskmem", 7))) - 1)
    ptr_window = max(0, int(getattr(model.config, "max_object_pointers_in_encoder", 16)) - 1)
    max_window = max(mem_window, ptr_window)
    min_mem_idx = current_idx - mem_window
    min_ptr_idx = current_idx - max_window
    pending_objs = set(getattr(session, "obj_with_new_inputs", ()))
    state_device = _resolve_device(getattr(session, "inference_state_device", "cpu"))

    for obj_idx, obj_id in list(getattr(session, "_obj_idx_to_id", {}).items()):
        if obj_id not in pending_objs:
            mask_inputs = session.mask_inputs_per_obj.get(obj_idx)
            if mask_inputs:
                for k in [k for k in mask_inputs if k <= current_idx]:
                    mask_inputs.pop(k, None)
            point_inputs = session.point_inputs_per_obj.get(obj_idx)
            if point_inputs:
                for k in [k for k in point_inputs if k < current_idx]:
                    point_inputs.pop(k, None)
        od = session.output_dict_per_obj.get(obj_idx)
        if not od:
            continue
        for k, entry in list(od.get("cond_frame_outputs", {}).items()):
            entry.pop("high_res_masks", None)
            if k < current_idx:
                entry.pop("pred_masks", None)
            for tk, tv in list(entry.items()):
                if isinstance(tv, torch.Tensor):
                    if tk in ("maskmem_features", "maskmem_pos_enc") and _resolve_device(tv.device) != state_device:
                        entry[tk] = tv.detach().to(state_device, non_blocking=False).clone()
                    elif not tv.is_cuda and tv.is_pinned():
                        entry[tk] = tv.detach().clone()
        non_cond = od.get("non_cond_frame_outputs", {})
        for k in list(non_cond):
            if k < min_ptr_idx:
                non_cond.pop(k, None)
                continue
            entry = non_cond[k]
            entry.pop("high_res_masks", None)
            if k < current_idx:
                entry.pop("pred_masks", None)
            if k < min_mem_idx:
                entry.pop("maskmem_features", None)
                entry.pop("maskmem_pos_enc", None)
            for tk, tv in list(entry.items()):
                if isinstance(tv, torch.Tensor):
                    if tk in ("maskmem_features", "maskmem_pos_enc") and _resolve_device(tv.device) != state_device:
                        entry[tk] = tv.detach().to(state_device, non_blocking=False).clone()
                    elif not tv.is_cuda and tv.is_pinned():
                        entry[tk] = tv.detach().clone()
        tracked = session.frames_tracked_per_obj.get(obj_idx)
        if tracked and len(tracked) > max_window + 1:
            for k in [k for k in tracked if k < min_ptr_idx]:
                tracked.pop(k, None)


def video_session_diagnostics(session):
    """Return lightweight counts and byte totals for a Transformers video inference session."""
    import torch

    if session is None:
        return {"active": False, "processed_frames": 0, "cond_frames": 0, "non_cond_frames": 0,
                "cpu_mib": 0.0, "gpu_mib": 0.0, "pinned_mib": 0.0}
    cpu_bytes = gpu_bytes = pinned_bytes = 0

    def _account(tensor):
        nonlocal cpu_bytes, gpu_bytes, pinned_bytes
        if not isinstance(tensor, torch.Tensor):
            return
        nbytes = tensor.numel() * tensor.element_size()
        if tensor.is_cuda:
            gpu_bytes += nbytes
        else:
            cpu_bytes += nbytes
            if tensor.is_pinned():
                pinned_bytes += nbytes

    processed = session.processed_frames or {}
    for tensor in processed.values():
        _account(tensor)
    cache_entries = getattr(getattr(session, "cache", None), "_vision_features", {}) or {}
    for vf in cache_entries.values():
        for val in vf.values():
            for tensor in (val if isinstance(val, (list, tuple)) else (val,)):
                _account(tensor)
    cond_frames = set()
    non_cond_frames = set()
    for od in (session.output_dict_per_obj or {}).values():
        for k, entry in od.get("cond_frame_outputs", {}).items():
            cond_frames.add(k)
            for tensor in entry.values():
                _account(tensor)
        for k, entry in od.get("non_cond_frame_outputs", {}).items():
            non_cond_frames.add(k)
            for tensor in entry.values():
                _account(tensor)
    for md in (session.mask_inputs_per_obj or {}).values():
        for tensor in md.values():
            _account(tensor)
    return {
        "active": True,
        "objects": len(getattr(session, "obj_ids", ())),
        "processed_frames": len(processed),
        "cond_frames": len(cond_frames),
        "non_cond_frames": len(non_cond_frames),
        "cpu_mib": round(cpu_bytes / (1024 ** 2), 2),
        "gpu_mib": round(gpu_bytes / (1024 ** 2), 2),
        "pinned_mib": round(pinned_bytes / (1024 ** 2), 2),
    }


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
                bind_cuda_device(self.device)
                model = model.to(device=self.device, dtype=torch.float32).eval().requires_grad_(False)
                if _ENABLE_CUDA_FAST_ATTENTION and _resolve_device(self.device).type == "cuda":
                    _install_cuda_attention_accel(model)
            except RuntimeError as error:
                raise RuntimeError(
                    f"EdgeTAM could not use device {self.device}: {error}. Use a "
                    "compatible PyTorch/device environment or select device='cpu'."
                ) from error
            self.model, self.processor = model, processor
        finally:
            self.load_progress = None

    def runtime_config(self):
        """Describe effective precision and session state placement for profile logs."""
        import torch

        if self.device is not None:
            target = _resolve_device(self.device)
        elif torch.cuda.is_available():
            best = max(range(torch.cuda.device_count()), key=lambda i: torch.cuda.get_device_properties(i).total_memory)
            target = torch.device(f"cuda:{best}")
        else:
            target = torch.device("cpu")
        is_cuda = target.type == "cuda"
        return {
            "model_precision": (
                "float32+fp16_memory_attention_perceiver"
                if is_cuda and _ENABLE_CUDA_FAST_ATTENTION else "float32"
            ),
            "inference_state_device": str(target) if is_cuda and _ENABLE_CUDA_GPU_STATE else "cpu",
        }

    def reset(self):
        """Discard the official per-video session while retaining loaded weights."""
        if self.session is not None:
            if self.session.processed_frames is not None:
                self.session.processed_frames.clear()
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
        from contextlib import nullcontext
        import torch
        from torch.nn.attention import SDPBackend, sdpa_kernel
        from PIL import Image

        bind_cuda_device(self.device)
        inputs = self.processor(
            images=Image.fromarray(np.ascontiguousarray(frame[..., ::-1])), return_tensors="pt",
        )
        attn_ctx = (
            sdpa_kernel([SDPBackend.MATH])
            if self.device is not None and torch.cuda.is_available() and torch.device(self.device).type == "cuda"
            else nullcontext()
        )
        # Scope Layer-0 self-attention cache strictly to one _infer() invocation to prevent
        # cross-frame data_ptr() reuse and cross-session RecoveryCandidate interference.
        layer0_cache = {} if getattr(self.model, "_edgetam_cuda_accel_installed", False) else None
        if layer0_cache is not None:
            self.model._edgetam_layer0_cache = layer0_cache
        try:
            with torch.inference_mode(), attn_ctx:
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
                    apply_non_overlapping_constraints=True,
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
                prune_video_session(session, self.model, index)
            return prediction
        finally:
            if layer0_cache is not None:
                layer0_cache.clear()
                self.model._edgetam_layer0_cache = None

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
        bind_cuda_device(self.device)
        state_device = (
            _resolve_device(self.device)
            if _ENABLE_CUDA_GPU_STATE and _resolve_device(self.device).type == "cuda"
            else "cpu"
        )
        session = configure_video_session(
            self.processor.init_video_session(
                inference_device=self.device, inference_state_device=state_device,
                video_storage_device="cpu", processing_device="cpu", dtype=torch.float32,
            ),
            self.device,
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
            obj_idx = self.session.obj_id_to_idx(object_id)
            self.session.frames_tracked_per_obj.get(obj_idx, {}).pop(index, None)
            self.session.output_dict_per_obj.get(obj_idx, {}).get("non_cond_frame_outputs", {}).pop(index, None)
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
