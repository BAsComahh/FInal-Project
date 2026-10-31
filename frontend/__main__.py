"""Register objects in video using click prompts and export reference masks/cutouts."""

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.window import VideoWindow
from frontend.workflow import DEFAULT_UNITS


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
    parser.add_argument("--inference-fps", type=float, default=2, help="Maximum SAM3 updates per second; video plays at source rate")
    parser.add_argument("--stride", type=int, help="Set model frequency to source fps / N; playback stays at source rate")
    parser.add_argument("--preview-width", type=int, default=960, help="Preview width; prompts and masks use full rectified-frame coordinates")
    parser.add_argument("--device", help="Torch device; automatically choose the GPU with the most memory")
    parser.add_argument("--model", default="facebook/sam3")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "outputs/sam3_registration")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        viewer = VideoWindow(args.video, units=args.units, calibration=args.calibration, board_size_in=args.board_size_in,
                                   model_id=args.model, device=args.device, start=args.start,
                                   seconds=args.seconds, stride=args.stride, inference_fps=args.inference_fps,
                                   preview_width=args.preview_width, output_dir=args.output_dir)
        viewer.show()
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
