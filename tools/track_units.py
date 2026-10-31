"""Run the independent CPU unit-tracking experiment from an initialized geometry JSON."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter

import cv2
import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from components.homography.geometry import transform_points
from components.unit_tracking import LKConfig, UnitTracker
from components.video_io import VideoSource


def _draw(frame, observations):
    canvas = frame.copy()
    for row in observations:
        color = (30, 220, 30) if row["status"] != "uncertain" else (0, 165, 255)
        points = np.rint(row["corners_image"]).astype(np.int32)
        cv2.polylines(canvas, [points], True, color, 2, cv2.LINE_AA)
        label = f"{row['unit_id']} {row['status']} pose@{row['pose_frame_index']}"
        x, y = points.min(axis=0)
        cv2.putText(canvas, label, (max(0, x), max(16, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    return canvas


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("video", type=Path)
    parser.add_argument("--initialization", type=Path, required=True, help="Geometry JSON with units, optional homography and clip_timestamp_seconds")
    parser.add_argument("--start", type=float, help="Override initialization's local clip time")
    parser.add_argument("--seconds", type=float, default=15)
    parser.add_argument("--tracking-fps", type=float, default=15, help="Sampling rate, recorded separately from CPU processing throughput")
    parser.add_argument("--max-width", type=int, default=960, help="Working raster width cap; all initialization corners scale with the image")
    parser.add_argument("--output-dir", type=Path, help="Fresh output directory (must not already exist)")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    source = writer = None
    try:
        if not np.isfinite([args.seconds, args.tracking_fps]).all() or min(args.seconds, args.tracking_fps) <= 0 or args.max_width < 64:
            raise ValueError("seconds/fps must be positive and finite; max-width must be >= 64")
        payload = json.loads(args.initialization.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("Initialization must be a JSON object")
        with args.video.open("rb") as stream:
            video_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        if payload.get("source_video_sha256", video_hash) != video_hash:
            raise ValueError("Initialization belongs to a different source video")
        start = args.start if args.start is not None else payload.get("clip_timestamp_seconds", 0)
        if "clip_timestamp_seconds" in payload and not np.isclose(start, payload["clip_timestamp_seconds"]):
            raise ValueError("Initialization belongs to a different start time; supply geometry for the requested frame")
        units = payload.get("units")
        if not isinstance(units, list) or not units:
            raise ValueError("Initialization needs units: [{unit_id, corners_image}, ...]")
        if any(not isinstance(row, dict) for row in units):
            raise ValueError("Each unit must be a geometry record")
        source = VideoSource(args.video)
        first = source.read_at(start)
        homography = payload.get("homography")
        matrix = np.eye(3)
        size = first.shape[1::-1]
        if homography is not None:
            matrix = np.asarray(homography["matrix"], dtype=float)
            raw_size = np.asarray(homography["output_size"], dtype=float)
            if (matrix.shape != (3, 3) or not np.isfinite(matrix).all() or np.linalg.matrix_rank(matrix) != 3
                    or raw_size.shape != (2,) or not np.isfinite(raw_size).all() or (raw_size < 2).any()
                    or (raw_size != np.floor(raw_size)).any()):
                raise ValueError("Homography needs a finite invertible matrix and positive integer output_size")
            size = tuple(raw_size.astype(int))
        factor = min(1, args.max_width / size[0])
        matrix = np.diag([factor, factor, 1]) @ matrix
        size = tuple(max(2, round(value * factor)) for value in size)
        units = [{**row, "corners_image": transform_points(row["corners_image"], matrix).tolist()} for row in units]
        frame = cv2.warpPerspective(first, matrix, size)
        config = LKConfig()
        tracker = UnitTracker(config)
        initialize_started = perf_counter()
        observations = tracker.initialize(frame, units, source_frame_index=source.frame_index)
        initialize_seconds = perf_counter() - initialize_started
        output = args.output_dir or Path("outputs/tracking_comparison") / datetime.now(timezone.utc).strftime("lk_%Y%m%d_%H%M%S_%f")
        output.mkdir(parents=True, exist_ok=False)
        step = max(1, round(source.fps / args.tracking_fps))
        sampled_fps = source.fps / step
        writer = cv2.VideoWriter(str(output / "overlay.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), sampled_fps, size)
        if not writer.isOpened():
            raise ValueError("Cannot open output MP4 writer")
        repo = Path(__file__).resolve().parents[1]
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True)
        hashes = {str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for root in (repo / "components/unit_tracking", repo / "components/video_io")
                  for path in root.glob("*.py")}
        hashes[str(Path(__file__).resolve().relative_to(repo))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        geometry_path = repo / "components/homography/geometry.py"
        hashes[str(geometry_path.relative_to(repo))] = hashlib.sha256(geometry_path.read_bytes()).hexdigest()
        versions = {name: importlib.metadata.version(name) for name in ("numpy", "opencv-python", "torch", "transformers")}
        run = {"backend": "cpu_lk_ransac", "commit": commit.stdout.strip(), "source_hashes": hashes,
               "python": platform.python_version(), "versions": versions, "device": "CPU",
               "video": str(args.video.resolve()), "video_sha256": video_hash,
               "initialization": str(args.initialization.resolve()),
               "initialization_sha256": hashlib.sha256(args.initialization.read_bytes()).hexdigest(),
               "initialization_metadata": payload, "config": asdict(config), "start_seconds": start,
               "requested_seconds": args.seconds, "input_fps": source.fps, "sampling_step": step,
               "sampling_fps": sampled_fps, "input_size": list(first.shape[1::-1]), "working_size": size,
               "image_to_work": matrix.tolist(), "object_count": len(units),
               "initialization_seconds": initialize_seconds,
               "limitations": ["No automatic recovery after uncertainty", "No identity/visibility guarantee",
                               "Initial geometry is supplied, not detected", "No model-speed comparison or physical accuracy measurement"]}
        (output / "run.json").write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
        durations, counts, by_active_count = [], {}, {}
        begin, end = source.frame_index, min(source.frame_count - 1, int((start + args.seconds) * source.fps) - 1)
        with (output / "timings.csv").open("w", newline="", encoding="utf-8") as timing_file, (output / "observations.jsonl").open("w", encoding="utf-8") as observation_file:
            columns = ["source_frame_index", "timestamp_seconds", "active_track_count", "decode_warp_seconds", "tracking_seconds", "overlay_write_seconds"]
            csv_writer = csv.DictWriter(timing_file, fieldnames=columns)
            csv_writer.writeheader()
            for index in range(begin, end + 1, step):
                started = perf_counter()
                if index != begin:
                    frame = cv2.warpPerspective(source.read_frame(index), matrix, size)
                decoded = perf_counter()
                if index != begin:
                    observations = tracker.update(frame, source_frame_index=index)
                tracked = perf_counter()
                active = sum(row["status"] != "uncertain" for row in observations)
                for row in observations:
                    observation_file.write(json.dumps({**row, "timestamp_seconds": index / source.fps,
                        "pose_timestamp_seconds": row["pose_frame_index"] / source.fps}) + "\n")
                    counts[row["status"]] = counts.get(row["status"], 0) + 1
                canvas = _draw(frame, observations)
                cv2.putText(canvas, f"CPU LK experiment | video {index / source.fps:.2f}s | uncertain = last accepted pose", (10, 24),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
                writer.write(canvas)
                finished = perf_counter()
                csv_writer.writerow(dict(zip(columns, [index, index / source.fps, active, decoded - started, tracked - decoded, finished - tracked])))
                if index != begin:
                    durations.append(tracked - decoded)
                    by_active_count.setdefault(active, []).append(tracked - decoded)
                if args.show:
                    cv2.imshow("CPU unit tracking experiment - Esc closes", canvas)
                    if cv2.waitKey(1) & 0xFF == 27:
                        break
        run["result"] = {"tracking_median_seconds": float(np.median(durations)) if durations else None,
                         "tracking_p95_seconds": float(np.percentile(durations, 95)) if durations else None,
                         "status_observation_counts": counts, "last_source_frame_index": source.frame_index,
                         "timing_by_active_track_count": {key: {"frames": len(values), "median_seconds": float(np.median(values)),
                                                                "p95_seconds": float(np.percentile(values, 95))}
                                                         for key, values in by_active_count.items()},
                         "accuracy_evaluated": False}
        (output / "run.json").write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved: {output.resolve()}")
        print(json.dumps(run["result"]))
        return 0
    except (OSError, ValueError, KeyError, TypeError, cv2.error) as error:
        parser.error(str(error))
    finally:
        if source is not None:
            source.close()
        if writer is not None:
            writer.release()
        if args.show:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    raise SystemExit(main())
