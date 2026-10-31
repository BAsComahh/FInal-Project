"""Click multiple targets, then press S to segment, preview and save them."""

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from components.sam3 import Sam3PointSegmenter
from components.sam3.point_segmenter import check_point_dependencies
from frontend.image.point_viewer import PointSegmentationViewer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
__all__ = ["Sam3PointSegmenter", "main"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--device", help="Torch device; automatically prefer the largest GPU")
    parser.add_argument("--model", default="facebook/sam3", help="Cached model ID or local model directory")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "sam3_click")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        check_point_dependencies()
        segmenter = Sam3PointSegmenter(model_id=args.model, device=args.device)
        segmenter.set_image(args.image)
        PointSegmentationViewer(segmenter, args.output_dir, source=str(args.image.resolve())).show()
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
