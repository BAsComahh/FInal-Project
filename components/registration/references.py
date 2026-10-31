"""Extract per-object reference material from a matching frame and prediction."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import cv2
import numpy as np

from components.image_io import save_image as _save_png

def extract_references(frame, prediction, *, source=None, roster=None):
    """Return independent full-size masks, BGR crops and BGRA cutouts in memory.

    frame must be the original BGR frame used for prediction, not a newer display
    frame. Empty masks are retained with box/crop/cutout set to None.
    """
    height, width = frame.shape[:2]
    ids = prediction["object_ids"]
    masks = np.asarray(prediction["masks"], dtype=bool)
    if masks.shape != (len(ids), height, width):
        raise ValueError("Prediction masks must match the original frame dimensions and object count")
    references = []
    for object_id, mask in zip(ids, masks):
        mask = mask.copy()
        ys, xs = np.nonzero(mask)
        box = crop = cutout = None
        if len(xs):
            box = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
            x1, y1, x2, y2 = box
            crop = frame[y1:y2, x1:x2].copy()
            cutout = cv2.cvtColor(crop, cv2.COLOR_BGR2BGRA)
            cutout[:, :, 3] = mask[y1:y2, x1:x2].astype(np.uint8) * 255
        reference = {"object_id": int(object_id), "mask": mask, "box": box,
                           "crop": crop, "cutout": cutout, "width": width, "height": height,
                           "origin": "video_click", "source": deepcopy(source)}
        if roster is not None:
            reference.update(roster.annotation(int(object_id)))
        references.append(reference)
    return references


def save_references(references, output_dir):
    """Write a gallery-material manifest and one folder per object.

    Call with a fresh output directory to retain multiple views of the same
    object across snapshots. This exports samples; it does not run DINO or
    decide which samples a gallery should retain.
    """
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    instances = []
    for index, reference in enumerate(references, start=1):
        object_id = reference["object_id"]
        name = f"object_{object_id:03d}"
        folder = output / name
        folder.mkdir(parents=True, exist_ok=True)
        _save_png(folder / "mask.png", reference["mask"].astype(np.uint8) * 255)
        empty = reference["box"] is None
        if not empty:
            _save_png(folder / "crop.png", reference["crop"])
            _save_png(folder / "target.png", reference["cutout"])
        metadata = {key: value for key, value in reference.items() if key not in ("mask", "crop", "cutout")}
        metadata.update(box_format="xyxy_exclusive", mask="mask.png",
                        crop=None if empty else "crop.png", cutout=None if empty else "target.png")
        (folder / "selection.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        instance = {"index": index, "object_id": object_id, "empty": empty,
                    "selection": f"{name}/selection.json"}
        if "unit_id" in reference:
            instance.update(unit_id=reference["unit_id"], type_id=reference["type_id"])
        instances.append(instance)
    (output / "instances.json").write_text(
        json.dumps({"instances": instances}, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def save_registration(frame, overlay, references, metadata, output_dir, *, roster=None):
    """Publish a complete snapshot, retaining no partial reference directories."""
    if overlay is None or overlay.shape != frame.shape:
        raise ValueError("Registration overlay must match its prediction frame")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".pending_", dir=output) as temporary:
        draft = Path(temporary)
        _save_png(draft / "frame.png", frame)
        _save_png(draft / "overlay.png", overlay)
        save_references(references, draft)
        if roster is not None:
            (draft / "units.json").write_text(
                json.dumps(roster.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
        (draft / "prompts.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        if metadata.get("rule_scene") is not None:
            (draft / "scene.json").write_text(
                json.dumps(metadata["rule_scene"], ensure_ascii=False, indent=2), encoding="utf-8")
        folder = output / f"frame_{uuid4().hex[:12]}"
        draft.rename(folder)
    return folder
