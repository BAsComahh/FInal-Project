"""Write one paused match observation for offline diagnosis."""

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
import json
from math import isfinite
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import numpy as np

from components.image_io import save_image


def _json_value(value):
    if is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (np.ndarray, np.generic)):
        return _json_value(value.tolist())
    if isinstance(value, float) and not isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    return value


def save_debug_capture(state, source, output):
    current = state.current
    prediction = current.prediction or {}
    object_ids = prediction.get("object_ids", ())
    masks = prediction.get("masks", ())
    if len(object_ids) != len(masks) or any(
            current.prediction_frame is None or mask.shape != current.prediction_frame.shape[:2] for mask in masks):
        raise ValueError("Debug mask dimensions do not match the observation frame.")

    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".pending_", dir=output) as temporary:
        draft = Path(temporary)
        images = {}
        for name, frame in (("frame", current.frame), ("source", state.source_image),
                            ("mask_frame", current.prediction_frame), ("geometry_frame", current.geometry_frame)):
            if frame is not None:
                images[name] = f"{name}.png"
                save_image(draft / images[name], frame)
        mask_files = {}
        for obj, mask in zip(object_ids, masks):
            filename = f"masks/object_{int(obj):03d}.png"
            save_image(draft / filename, np.where(mask, np.uint8(255), np.uint8(0)))
            mask_files[obj] = filename
        metadata = {
            "format": "match-debug-v1",
            "source": source,
            "display_ref": state.source_ref,
            "mask_ref": state.observation_ref,
            "mask_metadata": current.prediction_metadata,
            "geometry_metadata": prediction.get("geometry_metadata"),
            "images": images,
            "mask_files": mask_files,
            "prediction": {key: value for key, value in prediction.items() if key != "masks"},
            "board": state.board,
            "units": state.units,
            "tracking": state.tracking,
            "rules": state.rules,
            "tracker": state.tracker_name,
            "inference_fps": state.inference_fps,
            "tray_status": state.tray_status,
            "registration": state.reference_folder,
            "note": state.note,
        }
        (draft / "snapshot.json").write_text(json.dumps(_json_value(metadata), ensure_ascii=False, indent=2, allow_nan=False),
                                            encoding="utf-8")
        target = output / f"frame_{state.source_ref.frame_index}_{uuid4().hex[:8]}"
        draft.rename(target)
    return target
