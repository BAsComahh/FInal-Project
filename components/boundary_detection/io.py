"""Unicode-safe image I/O and pipeline exports."""

import json
from pathlib import Path

import numpy as np

from components.image_io import load_image, save_image
from .visualization import draw_merge_round


def save_report(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_result(args, image, report):
    save_image(args.output_dir / f"{args.image.stem}_boundary.png", image)
    return save_report(args.output_dir / f"{args.image.stem}_stages.json", report)


def export_stages(args, stages, report):
    for number, key in enumerate(stages):
        save_image(args.output_dir / f"{args.image.stem}_stage_{number:02d}_{key}.png", stages[key]["image"])
    for merge_round in report["merge_diagnostics"].get("rounds", []):
        overlay = draw_merge_round(stages["input"]["image"], np.asarray(report["raw_lines"]).reshape(-1, 4), merge_round)
        save_image(args.output_dir / f"{args.image.stem}_merge_round_{merge_round['round']:02d}.png", overlay)
    final_stage = "closure" if report["final_frame"]["valid"] else "completed"
    return export_result(args, stages[final_stage]["image"], report)
