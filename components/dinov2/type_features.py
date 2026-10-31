"""Replace type features from one completed registration without stale samples."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
from PIL import Image

from .extractor import DinoV2Extractor, normalize_rows


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _inside(root, relative):
    if not isinstance(relative, str) or not relative:
        raise ValueError("Reference file paths must be non-empty strings")
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Reference file is outside its registration folder: {relative}")
    return path


def _references(reference_dir):
    root = Path(reference_dir).resolve()
    registration = _read_json(root / "prompts.json")
    if registration.get("registration_complete") is not True:
        raise ValueError("Finish registration with S or Finish + play before updating type features")
    entries = _read_json(root / "instances.json").get("instances")
    if not isinstance(entries, list):
        raise ValueError("instances.json must contain an instances list")
    images, samples, skipped, seen = [], [], [], set()
    for entry in entries:
        if entry.get("empty"):
            skipped.append({"object_id": entry.get("object_id"), "unit_id": entry.get("unit_id"),
                            "type_id": entry.get("type_id"), "reason": "empty_mask"})
            continue
        selection = _inside(root, entry.get("selection"))
        info = _read_json(selection)
        unit_id, type_id = info.get("unit_id"), info.get("type_id")
        if not all(isinstance(value, str) and value.strip() for value in (unit_id, type_id)):
            raise ValueError(f"Reference is missing unit/type labels: {selection}")
        if unit_id in seen:
            raise ValueError(f"Duplicate unit_id in registration: {unit_id}")
        seen.add(unit_id)
        if entry.get("unit_id") != unit_id or entry.get("type_id") != type_id:
            raise ValueError(f"Reference labels disagree with instances.json: {selection}")
        if not isinstance(info.get("cutout"), str) or not info["cutout"]:
            raise ValueError(f"Non-empty reference has no cutout: {selection}")
        cutout = _inside(root, str(selection.parent.relative_to(root) / info["cutout"]))
        with Image.open(cutout) as image:
            if "A" not in image.getbands():
                raise ValueError(f"Reference cutout has no alpha mask: {cutout}")
            rgba = image.convert("RGBA")
        if rgba.getchannel("A").getbbox() is None:
            skipped.append({"unit_id": unit_id, "reason": "empty_alpha"})
            continue
        images.append(rgba)
        samples.append({"row": len(samples), "unit_id": unit_id, "type_id": type_id,
                        "object_id": info.get("object_id"), "source": info.get("source"),
                        "selection": str(selection.relative_to(root)), "cutout": str(cutout.relative_to(root)),
                        "cutout_sha256": hashlib.sha256(cutout.read_bytes()).hexdigest(),
                        "unit": info.get("unit", {}), "unit_type": info.get("unit_type", {})})
    if not samples:
        raise ValueError("No labelled, non-empty references; existing feature file was not changed")
    return root, images, samples, skipped


def update_type_features(reference_dir, output=None, *, extractor=None, batch_size=8):
    """Recompute samples/type prototypes and atomically replace a single NPZ file.

    The supplied completed registration is authoritative. This does not append
    previous views, retain removed types or modify the DINOv2 model weights.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    root, images, samples, skipped = _references(reference_dir)
    output = Path(output).resolve() if output is not None else root / "type_features.npz"
    if output.suffix.lower() != ".npz":
        raise ValueError("Feature output must have an .npz extension")
    extractor = extractor or DinoV2Extractor()
    sample_features = normalize_rows(extractor.encode(images, batch_size=batch_size))
    if len(sample_features) != len(samples):
        raise ValueError("The number of feature vectors must match the reference samples")
    type_ids = sorted({sample["type_id"] for sample in samples})
    groups = [[sample["row"] for sample in samples if sample["type_id"] == type_id] for type_id in type_ids]
    type_features = normalize_rows(np.stack([sample_features[rows].mean(axis=0) for rows in groups]))
    metadata = {"format_version": 1, "updated_at": datetime.now(timezone.utc).isoformat(),
                "update_mode": "replace", "reference_dir": str(root), **extractor.metadata(),
                "samples": samples, "skipped": skipped,
                "types": [{"type_id": key, "row": index, "sample_rows": rows, "sample_count": len(rows)}
                          for index, (key, rows) in enumerate(zip(type_ids, groups))],
                "type_aggregation": "l2_normalized_mean_of_normalized_sample_cls"}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=output.parent, prefix=".features_", suffix=".npz", delete=False) as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, sample_features=sample_features, type_features=type_features,
                                sample_unit_ids=np.asarray([s["unit_id"] for s in samples]),
                                sample_type_ids=np.asarray([s["type_id"] for s in samples]),
                                type_ids=np.asarray(type_ids), metadata=np.asarray(json.dumps(metadata, ensure_ascii=False)))
        temporary.replace(output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output


def load_type_features(path):
    """Load vectors and embedded JSON metadata without pickle."""
    with np.load(path, allow_pickle=False) as archive:
        result = {key: archive[key].copy() for key in
                  ("sample_features", "type_features", "sample_unit_ids", "sample_type_ids", "type_ids")}
        result["metadata"] = json.loads(str(archive["metadata"].item()))
    return result
