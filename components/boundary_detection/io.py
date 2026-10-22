"""Unicode-safe image I/O and pipeline exports."""

import json
from pathlib import Path

import cv2
import numpy as np

from .visualization import draw_border_lines, draw_merge_round


def load_image(path):
    """Read a BGR image, including files with non-ASCII Windows paths."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Image not found: {path}")
    data = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    if image is None:
        raise ValueError(f"Cannot decode image: {path}")
    return image


def save_image(path, image):
    path = Path(path)
    success, encoded = cv2.imencode(path.suffix or ".png", image)
    if not success:
        raise ValueError(f"Cannot encode output image: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded.tofile(path)


def save_report(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_result(args, stages, report):
    save_image(args.output_dir / f"{args.image.stem}_boundary.png", stages["refined"]["image"])
    return save_report(args.output_dir / f"{args.image.stem}_stages.json", report)


def export_stages(args, stages, report):
    for number, key in enumerate(stages):
        save_image(args.output_dir / f"{args.image.stem}_stage_{number:02d}_{key}.png", stages[key]["image"])
    for merge_round in report["merge_diagnostics"].get("rounds", []):
        overlay = draw_merge_round(stages["input"]["image"], np.asarray(report["raw_lines"]).reshape(-1, 4), merge_round)
        save_image(args.output_dir / f"{args.image.stem}_merge_round_{merge_round['round']:02d}.png", overlay)
    for number, step in enumerate(report["border_search"]["trace"]):
        overlay = draw_border_lines(stages["input"]["image"], step["selected"])
        save_image(args.output_dir / f"{args.image.stem}_border_search_{number:03d}.png", overlay)
    return export_result(args, stages, report)
