"""Register objects in video using click prompts and export reference masks/cutouts."""

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.window import VideoWindow
from frontend.config import DEFAULT_UNITS, PROJECT_ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--units", type=Path, default=DEFAULT_UNITS,
                        help="JSON unit-type catalog (default: ABC test catalog, inputs/units.video_estimate.json)")
    parser.add_argument("--calibration", type=Path, help="Optional table homography with image_to_board and board_size in mm for tray rectangles")
    parser.add_argument("--board-size-in", nargs=2, type=float, metavar=("WIDTH", "DEPTH"),
                        help="Prefill table length/width in inches (default: 72 48); confirm them after the corners")
    parser.add_argument("--start", type=float, default=0, help="Local clip start in seconds")
    parser.add_argument("--seconds", type=float, default=10, help="Playback interval (default: 10s)")
    parser.add_argument("--inference-fps", type=float, default=2, help="Maximum tracking updates per second; source video keeps its own clock")
    parser.add_argument("--stride", type=int, help="Set model frequency to source fps / N; playback stays at source rate")
    parser.add_argument("--preview-width", type=int, default=960, help="Preview width; prompts and masks use full rectified-frame coordinates")
    parser.add_argument("--device", help="Torch device; automatically choose the GPU with the most memory")
    parser.add_argument("--model", default="facebook/sam3")
    parser.add_argument("--tracker", choices=("sam3", "cutie", "edgetam"), default="sam3",
                        help="Video propagation backend; first-frame registration always uses SAM3")
    parser.add_argument("--tracker-model", help="Optional local checkpoint or HF model ID for the selected candidate")
    parser.add_argument("--tracker-cache", type=Path, help="Candidate model cache root (default: outputs/model_cache)")
    parser.add_argument("--profile", action="store_true", help="Synchronize GPU phase timing; may add profiling overhead")
    parser.add_argument("--tray-search", choices=("full", "local"), default="full",
                        help="Experimental local tray update with full-search fallback; full is the baseline")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs/sam3_registration")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        viewer = VideoWindow(args.video, units=args.units, calibration=args.calibration, board_size_in=args.board_size_in,
                                   model_id=args.model, device=args.device, start=args.start,
                                   seconds=args.seconds, stride=args.stride, inference_fps=args.inference_fps,
                                   preview_width=args.preview_width, output_dir=args.output_dir,
                                   profile=args.profile, tray_search=args.tray_search, tracker=args.tracker,
                                   tracker_model=args.tracker_model, tracker_cache=args.tracker_cache)
        viewer.show()
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
