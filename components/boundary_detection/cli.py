"""Explore battlefield boundaries with LSD."""

import argparse
import inspect
from pathlib import Path
from time import perf_counter

import cv2

from .io import export_result, export_stages, load_image, save_image, save_report
from .merge import merge_collinear_segments
from .pipeline import STAGES, compute_stages, detect_segments, preprocess_image
from .visualization import draw_lines
from .config import DEFAULT_CONFIG, PROJECT_ROOT, add_switch_arguments, initial_switches


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    merge_defaults = inspect.signature(merge_collinear_segments).parameters
    parser.add_argument("image", nargs="?", type=Path, default=PROJECT_ROOT / "inputs" / "table.png")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="TOML pipeline switches (default: components/boundary_detection/config.toml)")
    parser.add_argument("--raw", "--no-filter", action="store_true", help="Output raw LSD segments; skip merging and side selection")
    parser.add_argument("--interactive", action="store_true", help="Interactive stage viewer with pipeline/merge-condition checkboxes")
    parser.add_argument("--export-stages", action="store_true", help="Export each pipeline stage and effective settings without opening a window")
    parser.add_argument("--stage", choices=[key for key, _ in STAGES], default="merged", help="Initial stage in interactive mode")
    add_switch_arguments(parser)
    parser.add_argument("--border-region-ratio", type=float, default=None, help="Per-side region as an image fraction, (0, 0.5]; default from config")
    parser.add_argument("--min-line-length", type=int, default=200, help="Long-line length threshold in original image pixels")
    parser.add_argument("--blur-size", type=int, default=5, help="Shared Gaussian kernel, odd; 1 disables blur")
    parser.add_argument("--refine", choices=["none", "std", "adv"], default="std", help="LSD refinement mode")
    parser.add_argument("--angle-tolerance", type=float, default=15, help="Allowed tilt from horizontal/vertical, in degrees")
    parser.add_argument("--merge-min-length", type=float, default=merge_defaults["min_segment_length"].default, help="Minimum source segment length for merging (px)")
    parser.add_argument("--merge-angle", type=float, default=merge_defaults["angle_tolerance"].default, help="Maximum direction difference for merging (degrees)")
    parser.add_argument("--merge-distance", type=float, default=merge_defaults["distance_tolerance"].default, help="Maximum endpoint deviation from fitted line (px)")
    parser.add_argument("--merge-gap", type=float, default=merge_defaults["max_gap"].default, help="Maximum uncovered gap along a merged line (px)")
    parser.add_argument("--merge-min-coverage", type=float, default=merge_defaults["min_coverage"].default, help="Minimum observed coverage of fitted span (0, 1]")
    parser.add_argument("--connection-distance", type=float, default=20, help="Allowed endpoint/intersection gap in pixels")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "boundary_detection")
    parser.add_argument("--show", action="store_true", help="Open the stage viewer (raw mode: original/raw comparison)")
    return parser


def run_raw_mode(args, switches):
    """Standalone raw output: skip merging, filtering and frame search."""
    image = load_image(args.image)
    start = perf_counter()
    gray = preprocess_image(image, args, switches)
    lines, note = detect_segments(gray, args, switches)
    elapsed_ms = (perf_counter() - start) * 1000
    overlay = draw_lines(image, lines, (0, 150, 255), thickness=1)
    output = args.output_dir / f"{args.image.stem}_lsd_raw.png"
    save_image(output, overlay)
    report_path = args.output_dir / f"{args.image.stem}_lsd_raw_report.json"
    report = {
        "mode": "raw", "image": str(args.image.resolve()),
        "image_size": {"width": image.shape[1], "height": image.shape[0]},
        "detector": "lsd", "switches": dict(switches),
        "parameters": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "postprocessing": "none", "opencv_version": cv2.__version__,
        "raw_count": len(lines), "raw_lines": lines.tolist(),
        "note": note, "single_run_ms": {"preprocessing_and_detection": elapsed_ms},
    }
    save_report(report_path, report)
    print(f"LSD raw: {len(lines)} segments; {note}")
    print(f"Saved: {output.resolve()}")
    print(f"Saved: {report_path.resolve()}")
    if args.show:
        import matplotlib.pyplot as plt

        panels = [(image, "Original")]
        panels.append((overlay, f"All LSD segments: {len(lines)}"))
        figure, axes = plt.subplots(1, len(panels), figsize=(16, 8))
        for axis, (content, title) in zip(axes, panels):
            axis.imshow(cv2.cvtColor(content, cv2.COLOR_BGR2RGB))
            axis.set_title(title)
            axis.axis("off")
        figure.tight_layout()
        plt.show()


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        switches = initial_switches(args)
        if args.raw:
            if args.interactive or args.export_stages:
                raise ValueError("Use --stage raw for stage inspection; --raw is a standalone mode")
            run_raw_mode(args, switches)
            return

        image = load_image(args.image)
        stages, report = compute_stages(image, args, switches)
        if args.export_stages or args.interactive or args.show:
            path = export_stages(args, stages, report)
        else:
            path = export_result(args, stages, report)
        for key, label in STAGES:
            stage = stages[key]
            print(f"{label}: {stage['count']}; {stage['note']}")
        print(f"Saved result and report: {path.resolve()}")
        if args.interactive or args.show:
            import matplotlib.pyplot as plt
            from .viewer import StepViewer

            viewer = StepViewer(image, args, switches, (stages, report))
            viewer.figure.savefig(args.output_dir / f"{args.image.stem}_stage_controls.png", dpi=110)
            plt.show()
    except (OSError, ValueError, cv2.error) as error:
        parser.error(str(error))
