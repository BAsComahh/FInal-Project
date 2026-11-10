"""Offline SAM text candidates and missing-instance DINO retrieval; never accepts IDs."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
from tempfile import mkdtemp
from time import perf_counter

import cv2
import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(PROJECT_ROOT))

from components.dinov2 import DinoV2Extractor, rank_candidates
from components.dinov2.type_features import _references
from components.homography import transform_points as map_points
from components.image_io import load_image, save_image
from components.registration.references import extract_references
from components.sam3 import Sam3Segmenter
from components.sam3.visualization import draw_segmentation


def mask_geometry(mask, to_source, source_to_mm=None):
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise ValueError("Cannot locate an empty candidate mask")
    center = [float(xs.mean()), float(ys.mean())]
    box = [[xs.min(), ys.min()], [xs.max() + 1, ys.min()],
           [xs.max() + 1, ys.max() + 1], [xs.min(), ys.max() + 1]]
    source_center = map_points([center], to_source)[0]
    return {"center_working": center, "center_source": source_center.tolist(),
            "box_corners_source": map_points(box, to_source).tolist(),
            "center_mm": None if source_to_mm is None else map_points([source_center], source_to_mm)[0].tolist(),
            "center_definition": "mapped_mask_centroid", "mask_area_working_pixels": int(len(xs))}


def _json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def _hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _timed(device, operation):
    import torch

    if device.startswith("cuda"):
        torch.cuda.synchronize(device)
    started = perf_counter()
    value = operation()
    if device.startswith("cuda"):
        torch.cuda.synchronize(device)
    return value, perf_counter() - started


def _mappings(metadata, raw_size):
    declared = metadata.get("source_image_size")
    if declared is not None and list(declared) != list(raw_size):
        raise ValueError("Video canvas differs from registration source_image_size")
    homography = metadata.get("homography")
    if homography is None:
        if metadata.get("coordinate_space") == "rectified_table_pixels":
            raise ValueError("Rectified registration has no homography")
        return np.eye(3), np.eye(3), None, tuple(raw_size)
    matrix = np.asarray(homography["matrix"], dtype=np.float64)
    inverse = np.asarray(homography["inverse_matrix"], dtype=np.float64)
    # Validate both mappings rather than silently pairing incompatible references.
    sample = np.array([[0, 0], [raw_size[0] / 2, raw_size[1] / 2], [*raw_size]])
    if not np.allclose(map_points(map_points(sample, matrix), inverse), sample, atol=1e-4):
        raise ValueError("Registration homography and inverse disagree")
    size = tuple(int(value) for value in homography["output_size"])
    if len(size) != 2 or min(size) < 1:
        raise ValueError("Invalid registration working image size")
    if metadata.get("image_size") is not None and list(size) != metadata["image_size"]:
        raise ValueError("Registration image_size differs from its homography output")
    metric = homography.get("image_to_board")
    if metric is not None:
        metric = np.asarray(metric, dtype=np.float64)
        map_points(sample, metric)
    return matrix, inverse, metric, size


def _tile(image, title, subtitle="", size=(250, 210)):
    if isinstance(image, Image.Image):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (235, 235, 235, 255))
        background.alpha_composite(rgba)
        image = cv2.cvtColor(np.asarray(background.convert("RGB")), cv2.COLOR_RGB2BGR)
    elif image is not None and image.shape[2] == 4:
        alpha = image[:, :, 3:4] / 255.0
        image = (image[:, :, :3] * alpha + 235 * (1 - alpha)).astype(np.uint8)
    canvas = np.full((size[1], size[0], 3), 245, np.uint8)
    if image is not None:
        scale = min((size[0] - 12) / image.shape[1], (size[1] - 56) / image.shape[0])
        scaled = cv2.resize(image, (max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale))))
        x = (size[0] - scaled.shape[1]) // 2
        canvas[50:50 + scaled.shape[0], x:x + scaled.shape[1]] = scaled
    cv2.putText(canvas, title, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, .45, (20, 20, 20), 1, cv2.LINE_AA)
    cv2.putText(canvas, subtitle, (6, 38), cv2.FONT_HERSHEY_SIMPLEX, .4, (65, 65, 65), 1, cv2.LINE_AA)
    return canvas


def _comparison(path, ranking, references, candidates):
    rows = []
    for row in ranking["rankings"]:
        tiles = [_tile(references[row["unit_id"]], row["unit_id"], "Reference; identity unreviewed")]
        for rank, (index, score) in enumerate(zip(row["candidate_ids"][:3], row["scores"][:3]), 1):
            tiles.append(_tile(candidates[index]["cutout"], f"#{rank} candidate {index}", f"cosine {score:.4f}; not accepted"))
        tiles.extend(_tile(None, "No candidate") for _ in range(4 - len(tiles)))
        rows.append(np.hstack(tiles))
    save_image(path, np.vstack(rows))


def evaluate(reference_dir, *, times=None, missing_groups=None, prompt="miniature", device=None,
             threshold=.3, output_dir=None):
    """Write a fresh diagnostic run; all source registrations remain read-only."""
    root, reference_images, samples, skipped = _references(reference_dir)
    metadata = json.loads((root / "prompts.json").read_text(encoding="utf-8-sig"))
    available = {sample["unit_id"]: (sample, image) for sample, image in zip(samples, reference_images)}
    groups = missing_groups or [list(available)]
    for group in groups:
        if not group or len(group) != len(set(group)) or set(group) - available.keys():
            raise ValueError("Each missing group must contain unique, non-empty registered instance IDs")
    ids = list(dict.fromkeys(unit_id for group in groups for unit_id in group))
    samples = [available[unit_id][0] for unit_id in ids]
    images = [available[unit_id][1] for unit_id in ids]
    if not isinstance(prompt, str) or not prompt.strip() or not np.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Use a non-empty text prompt and a detection threshold between zero and one")
    if times is not None and (not times or not all(np.isfinite(t) and t >= 0 for t in times)):
        raise ValueError("Sample times must be finite, nonnegative video seconds")
    video = Path(metadata["video"])
    if not video.is_file():
        video = PROJECT_ROOT / "inputs" / video.name
    if not video.is_file():
        raise ValueError("Registration video is unavailable")
    output_base = Path(output_dir or PROJECT_ROOT / "outputs/recovery_evaluation").resolve()
    if (not output_base.is_relative_to((PROJECT_ROOT / "outputs").resolve())
            or output_base.is_relative_to(root) or root.is_relative_to(output_base)):
        raise ValueError("Use a separate output directory beneath project outputs/")
    inputs = {str(path.relative_to(root)): _hash(path) for path in sorted(root.rglob("*")) if path.is_file()}
    cap = cv2.VideoCapture(str(video))
    try:
        if not cap.isOpened():
            raise ValueError("Cannot open registration video")
        fps, count = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if not np.isfinite(fps) or fps <= 0 or count <= 0:
            raise ValueError("Video has no valid frame count or FPS")
        raw_size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        matrix, inverse, metric, working_size = _mappings(metadata, raw_size)
        frames = (sorted({int(round(t * fps)) for t in times}) if times is not None
                  else sorted(set(np.linspace(int(metadata["frame_index"]), count - 1, 11).round().astype(int).tolist())))
        if min(frames) < int(metadata["frame_index"]) or max(frames) >= count:
            raise ValueError("Samples must be at or after registration and within the video")
        # HF caches optional-package availability at import time, as in create_tracker.
        dependencies = PROJECT_ROOT / "outputs/tracking_dependencies"
        if dependencies.is_dir() and str(dependencies) not in sys.path:
            sys.path.insert(0, str(dependencies))
        import torch
        from importlib.metadata import version

        extractor = DinoV2Extractor(device=device)
        started = perf_counter()
        extractor.load()
        device = str(extractor.device)
        if device.startswith("cuda"):
            torch.cuda.synchronize(device)
        dino_load_seconds = perf_counter() - started
        segmenter = Sam3Segmenter(device=device)
        _, sam_load_seconds = _timed(device, segmenter._load_model)
        physical_device = torch.cuda.get_device_name(device) if device.startswith("cuda") else "CPU (deliberate CPU run)"
        print(f"Device: {physical_device} ({device}); {len(frames)} frames; {len(groups)} missing groups", flush=True)
        if device.startswith("cuda"):
            torch.cuda.reset_peak_memory_stats(device)
        features, reference_seconds = _timed(device, lambda: extractor.encode(images))
        reference_locations = {}
        for unit_id, sample in zip(ids, samples):
            info = json.loads((root / sample["selection"]).read_text(encoding="utf-8-sig"))
            mask_path = (root / sample["selection"]).parent / info["mask"]
            if not mask_path.resolve().is_relative_to(root):
                raise ValueError("Reference mask is outside registration")
            mask = load_image(mask_path, mode="gray")
            if mask.shape != working_size[::-1]:
                raise ValueError("Reference mask and video coordinate canvas differ")
            reference_locations[unit_id] = {**mask_geometry(mask != 0, inverse, metric),
                                            "frame_index": int(metadata["frame_index"]),
                                            "timestamp_seconds": int(metadata["frame_index"]) / fps,
                                            "basis": "registration_frame_not_live_last_observation"}
        output_base.mkdir(parents=True, exist_ok=True)
        output = Path(mkdtemp(prefix="run_", dir=output_base))
        _json(output / "input_fingerprints.json", {"reference_files": inputs, "video_sha256": _hash(video)})
        np.savez_compressed(output / "reference_features.npz", unit_ids=np.asarray(ids), features=features,
                            metadata=np.asarray(json.dumps(extractor.metadata(), ensure_ascii=False)))
        result = {"schema_version": 1, "complete": False, "reference_dir": str(root), "video": str(video.resolve()),
                  "device": device, "physical_device": physical_device, "torch_version": torch.__version__,
                  "transformers_version": version("transformers"), "dtype": "float32",
                  "sam_model": segmenter.model_id, "dino": extractor.metadata(),
                  "sam_detection_threshold": threshold, "sam_mask_threshold": .5, "prompt": prompt,
                  "source_image_size": list(raw_size), "working_image_size": list(working_size),
                  "calibration_version": metadata.get("calibration_version"), "homography": metadata.get("homography"),
                  "coordinate_basis": "source_image_pixels",
                  "calibration_provenance": {"registration_metadata_sha256": inputs["prompts.json"],
                                             "legacy_version_missing": metadata.get("calibration_version") is None},
                  "source_url": metadata.get("source_url"), "source_timestamp_seconds": metadata.get("source_timestamp_seconds"),
                  "last_known": reference_locations, "samples": samples, "skipped_references": skipped,
                  "missing_groups": groups, "frames": [],
                  "timings_seconds": {"sam_load": sam_load_seconds, "dino_load": dino_load_seconds,
                                      "reference_encoding": reference_seconds},
                  "limitations": ["No automatic ID acceptance or confidence threshold",
                                  "Normal assigned objects are not filtered in this offline baseline",
                                  "Existing example type labels are not verified game-unit classes",
                                  "Mask-centroid distance is not tray movement distance",
                                  "No propagation outputs used as identity ground truth"]}
        reviews, overview = [], []
        for frame_index in frames:
            frame_started = perf_counter()
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, raw = cap.read()
            if not ok:
                raise ValueError(f"Cannot decode frame {frame_index}")
            actual_index = int(round(cap.get(cv2.CAP_PROP_POS_FRAMES))) - 1
            if actual_index != frame_index or raw.shape[1::-1] != raw_size:
                raise ValueError(f"Decoded frame/canvas differs at {frame_index}")
            image = cv2.warpPerspective(raw, matrix, working_size) if metadata.get("homography") else raw
            decode_seconds = perf_counter() - frame_started
            detection, sam_seconds = _timed(device, lambda: segmenter.segment(image, prompt, threshold=threshold))
            prediction = {"object_ids": list(range(len(detection["masks"]))), "masks": detection["masks"]}
            candidates = extract_references(image, prediction)
            # An instance may pass its score threshold with no surviving foreground.
            keep = [index for index, item in enumerate(candidates) if item["cutout"] is not None]
            empty_ids = sorted(set(range(len(candidates))) - set(keep))
            candidates = [candidates[index] for index in keep]
            detection = {**detection, "masks": detection["masks"][keep],
                         "boxes": detection["boxes"][keep], "scores": detection["scores"][keep]}
            candidate_features, dino_seconds = _timed(device, lambda: extractor.encode(
                [Image.fromarray(cv2.cvtColor(item["cutout"], cv2.COLOR_BGRA2RGBA)) for item in candidates]))
            folder = output / f"frame_{frame_index:06d}"
            folder.mkdir()
            save_image(folder / "source.png", raw)
            save_image(folder / "working.png", image)
            overlay = draw_segmentation(detection)
            save_image(folder / "candidates.png", overlay)
            overview.append(_tile(overlay, f"Frame {frame_index}: {frame_index / fps:.2f}s",
                                  f"{len(candidates)} candidates; identities unreviewed", size=(480, 355)))
            candidate_records = []
            for index, (item, score) in enumerate(zip(candidates, detection["scores"])):
                save_image(folder / f"mask_{index:03d}.png", item["mask"].astype(np.uint8) * 255)
                save_image(folder / f"cutout_{index:03d}.png", item["cutout"])
                candidate_records.append({"candidate_id": index, "sam_score": float(score),
                                          "sam_original_index": keep[index],
                                          **mask_geometry(item["mask"], inverse, metric)})
            match_started = perf_counter()
            cases, table = [], []
            for case_index, group in enumerate(groups, 1):
                ranked = rank_candidates(group, features[[ids.index(unit_id) for unit_id in group]], candidate_features)
                ranked["case_id"] = case_index
                for ranking in ranked["rankings"]:
                    location = reference_locations[ranking["unit_id"]]
                    distances = []
                    for rank, (index, score) in enumerate(zip(ranking["candidate_ids"], ranking["scores"]), 1):
                        candidate = candidate_records[index]
                        pixels = float(np.linalg.norm(np.subtract(candidate["center_source"], location["center_source"])))
                        mm = (None if metric is None else
                              float(np.linalg.norm(np.subtract(candidate["center_mm"], location["center_mm"]))))
                        distances.append({"candidate_id": index, "distance_source_pixels": pixels, "distance_mm": mm})
                        table.append([case_index, ranking["unit_id"], index, rank, score, ranking["top_two_margin"],
                                      pixels, mm, frame_index / fps - location["timestamp_seconds"], "unknown"])
                    ranking["distances_from_last_known"] = distances
                    reviews.append({"frame_index": frame_index, "unit_id": ranking["unit_id"],
                                    "candidate_id": None, "visibility": "unknown", "identity": "unknown", "note": ""})
                cases.append(ranked)
            matching_seconds = perf_counter() - match_started
            for case in cases:
                _comparison(folder / f"case_{case['case_id']:02d}.png", case,
                            {unit_id: image for unit_id, (_, image) in available.items()}, candidates)
            with (folder / "scores.csv").open("w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.writer(stream)
                writer.writerow(["case_id", "unit_id", "candidate_id", "rank", "cosine", "top_two_margin",
                                 "distance_source_pixels", "distance_mm", "seconds_since_last_known", "identity"])
                writer.writerows(table)
            entry = {"frame_index": frame_index, "timestamp_seconds": frame_index / fps,
                     "source_timestamp_seconds": (None if metadata.get("source_timestamp_seconds") is None else
                                                  metadata["source_timestamp_seconds"] + frame_index / fps
                                                  - metadata.get("timestamp_seconds", 0)),
                     "calibration_version": metadata.get("calibration_version"),
                     "candidates": candidate_records, "discarded_empty_sam_indices": empty_ids, "cases": cases,
                     "timings_seconds": {"decode_and_warp": decode_seconds, "sam_search": sam_seconds,
                                         "dino_encoding": dino_seconds, "matching": matching_seconds},
                     "artifact_dir": folder.name}
            np.savez_compressed(folder / "candidate_features.npz", features=candidate_features)
            _json(folder / "results.json", entry)
            result["frames"].append(entry)
            _json(output / "results.json", result)
            print(f"Frame {frame_index}: {len(candidates)} candidates; SAM {sam_seconds:.3f}s; "
                  f"DINO {dino_seconds:.3f}s; matching {matching_seconds:.4f}s", flush=True)
        blank = np.full_like(overview[0], 245)
        overview.extend(blank.copy() for _ in range((-len(overview)) % 3))
        save_image(output / "overview.png", np.vstack([np.hstack(overview[i:i + 3]) for i in range(0, len(overview), 3)]))
        # One review per physical ID/frame, even when it appears in several scenarios.
        reviews = list({(item["frame_index"], item["unit_id"]): item for item in reviews}.values())
        _json(output / "review.json", {"instruction": "Visual review only. Unknown is not incorrect or correct. "
                                     "Use identity=verified only when the physical association is visible; "
                                     "leave ambiguous identities unknown. Do not use tracker output as truth.",
                                     "observations": reviews})
        result["input_references_unchanged"] = all((root / path).is_file() and _hash(root / path) == digest
                                                    for path, digest in inputs.items())
        if device.startswith("cuda"):
            result["peak_gpu_allocated_bytes"] = torch.cuda.max_memory_allocated(device)
            result["peak_gpu_reserved_bytes"] = torch.cuda.max_memory_reserved(device)
        _json(output / "results.json", result)
        if not result["input_references_unchanged"]:
            raise ValueError("An input reference changed during the experiment")
        result["complete"] = True
        _json(output / "results.json", result)
        print(f"Saved: {output}", flush=True)
        return output
    finally:
        cap.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_dir", type=Path, help="Completed registration directory")
    parser.add_argument("--times", nargs="+", type=float, help="Video seconds; default eleven evenly spaced frames")
    parser.add_argument("--missing", action="append", nargs="+", help="Simulated missing IDs; repeat for independent cases")
    parser.add_argument("--prompt", default="miniature")
    parser.add_argument("--threshold", type=float, default=.3, help="SAM detection score cutoff, not identity confidence")
    parser.add_argument("--device", help="Torch device; explicitly select the physical GPU for experiments")
    parser.add_argument("--output-dir", type=Path, help="Separate directory under outputs/; each run creates a new child")
    args = parser.parse_args()
    try:
        evaluate(args.reference_dir, times=args.times, missing_groups=args.missing, prompt=args.prompt,
                 threshold=args.threshold, device=args.device, output_dir=args.output_dir)
    except (OSError, ValueError, KeyError, RuntimeError, cv2.error) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
