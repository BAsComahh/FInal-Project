"""Fit one known-size rectangular tray using local LSD and mask-guided fallback."""

import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from components.image_io import load_image, save_image
from components.boundary_detection.io import save_report
from components.boundary_detection.scale import image_short_side, percent_to_length
from components.boundary_detection.tray import TrayConfig, fit_tray
from components.boundary_detection.tray.visualization import diagnostic_images


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("image", type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--mask", type=Path, help="Full-resolution binary mask aligned with the image")
    source.add_argument("--point", nargs=2, type=float, metavar=("X", "Y"), help="Original image pixel coordinates for the existing SAM3 point component")
    parser.add_argument("--size-pct", nargs=2, type=float, metavar=("WIDTH", "DEPTH"),
                        help="Width/depth as percentages of the full input image short side; pixel-only experiment")
    parser.add_argument("--units", type=Path, help="Type catalog containing dimension.width_mm/depth_mm")
    parser.add_argument("--type", dest="type_id", help="Type whose physical dimensions should be used")
    parser.add_argument("--calibration", type=Path, help="Homography JSON with image_to_board and board_size expressed in mm")
    parser.add_argument("--mode", choices=("auto", "corner", "edge", "mask"), default="auto")
    parser.add_argument("--no-merge", action="store_true")
    parser.add_argument("--max-work-size", type=int, default=512)
    percent_options = {
        "roi_margin_pct": "ROI padding/radius margin percentage (existing work-view semantics)",
        "min_line_length_pct": "Minimum line length as a percentage of the working tray short side",
        "endpoint_gap_pct": "Corner endpoint gap as a percentage of the working tray short side",
        "edge_tolerance_pct": "Edge support distance as a percentage of the working tray short side",
        "merge_distance_pct": "Merge distance as a percentage of the working tray short side",
        "merge_gap_pct": "Merge gap as a percentage of the working tray short side",
        "corner_dedup_pct": "Corner deduplication distance as a percentage of the working tray short side",
        "corner_nudge_pct": "Corner translation/strength regularizer as a percentage of the working tray short side",
        "candidate_dedup_pct": "Candidate deduplication distance as a percentage of the working tray short side",
        "search_pct": "Mask fallback seed offset along each tray width/depth axis, including diagonals",
    }
    defaults = TrayConfig()
    for name, help_text in percent_options.items():
        parser.add_argument(f"--{name.replace('_', '-')}", type=float, default=getattr(defaults, name), help=help_text)
    parser.add_argument("--angle-tolerance", type=float, default=12)
    parser.add_argument("--angle-step", type=float, default=5)
    parser.add_argument("--refine-rounds", type=int, default=defaults.refine_rounds,
                        help="Maximum Beam rounds per seed set; 0 scores the seeds only")
    parser.add_argument("--min-mask-coverage", type=float, default=defaults.min_mask_coverage)
    parser.add_argument("--device", help="SAM3 device if --point is used")
    parser.add_argument("--model", default="facebook/sam3")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "outputs/tray_detection")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        mapping, unit = None, "pixels"
        image = load_image(args.image)
        if args.size_pct is not None:
            if args.units or args.type_id or args.calibration:
                raise ValueError("--size-pct is separate from physical dimensions/calibration")
            reference = image_short_side(image.shape)
            size = [percent_to_length(value, reference, name=f"size-{name}-pct")
                    for name, value in zip(("width", "depth"), args.size_pct)]
        else:
            if not (args.units and args.type_id and args.calibration):
                raise ValueError("Provide --size-pct, or --units + --type + --calibration for physical dimensions")
            from components.registration.units import UnitRoster

            roster = UnitRoster.load(args.units)
            if args.type_id not in roster.types:
                raise ValueError(f"Unknown type: {args.type_id}")
            dimension = roster.types[args.type_id].get("dimension", {})
            if not all(key in dimension for key in ("width_mm", "depth_mm")):
                raise ValueError("Type needs dimension.width_mm and dimension.depth_mm")
            size = [dimension["width_mm"], dimension["depth_mm"]]
            calibration = json.loads(args.calibration.read_text(encoding="utf-8-sig"))
            if calibration.get("image_to_board") is None or calibration.get("board_size") is None:
                raise ValueError("Calibration must include image_to_board and a board_size entered in mm")
            mapping, unit = np.asarray(calibration["image_to_board"], dtype=float), "mm"
        config = TrayConfig(mode=args.mode, merge=not args.no_merge, max_work_size=args.max_work_size,
                            angle_tolerance_deg=args.angle_tolerance, angle_step_deg=args.angle_step,
                            refine_rounds=args.refine_rounds,
                            min_mask_coverage=args.min_mask_coverage,
                            **{name: getattr(args, name) for name in percent_options})
        config.validate()
        if not np.isfinite(size).all() or min(size) <= 0:
            raise ValueError("Dimensions must be finite and positive")
        if args.mask:
            mask = load_image(args.mask, mode="gray")
        else:
            from components.sam3 import Sam3PointSegmenter

            segmenter = Sam3PointSegmenter(model_id=args.model, device=args.device)
            segmenter.set_image(image)
            print("Generating ROI mask with SAM3...", flush=True)
            mask = segmenter.segment([args.point])["mask"]
        result = fit_tray(image, mask, size, image_to_plane=mapping, config=config)
        result.update(image=str(args.image.resolve()), mask_source=str(args.mask.resolve()) if args.mask else {"point": args.point},
                      length_unit=unit, type_id=args.type_id,
                      calibration=str(args.calibration.resolve()) if args.calibration else None)
        if args.size_pct is not None:
            result.update(requested_size_pct=args.size_pct,
                          size_percentage_basis={"reference": "full_input_image_short_side", "reference_px": reference})
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name, canvas in diagnostic_images(image, mask, result).items():
            save_image(args.output_dir / f"{args.image.stem}_{name}.png", canvas)
        save_image(args.output_dir / f"{args.image.stem}_input_mask.png", (np.asarray(mask) != 0).astype(np.uint8) * 255)
        report = args.output_dir / f"{args.image.stem}_tray.json"
        save_report(report, result)
        best = result["best"]
        print(f"Saved: {report.resolve()}")
        print(f"Candidate accepted: {result['success']}; visual review required")
        if best:
            print(f"Method: {best['method']}; mask coverage: {best['mask_coverage']:.3f}; edge support: {best['edge_support']:.3f}")
        if args.show:
            sheet = diagnostic_images(image, mask, result)["stages"]
            factor = min(1, 1280 / sheet.shape[1], 850 / sheet.shape[0])
            cv2.imshow("Tray detection stages", cv2.resize(sheet, None, fx=factor, fy=factor))
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        return 0
    except (ImportError, OSError, ValueError, RuntimeError, KeyError, cv2.error) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
