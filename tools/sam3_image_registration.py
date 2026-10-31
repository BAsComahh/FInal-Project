"""Detect miniatures, then review, add and remove registered targets in a UI."""

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from components.sam3 import Sam3PointSegmenter, Sam3Segmenter
from components.sam3.point_segmenter import check_point_dependencies
from frontend.image.registration_viewer import RegistrationViewer


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--prompt", default="miniature")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--device", help="Torch device; automatically prefer the largest GPU")
    parser.add_argument("--model", default="facebook/sam3", help="Cached model ID or local model directory")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "sam3_registration")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        torch, _, _ = check_point_dependencies("tools.sam3_image_registration")
        detector = Sam3Segmenter(model_id=args.model, device=args.device)
        print(f"Detecting targets with prompt: {args.prompt}", flush=True)
        detection = detector.segment(args.image, args.prompt, threshold=args.threshold)
        device = detector.device
        print(f"Found {len(detection['masks'])} targets. Opening registration review.", flush=True)
        # The automatic model is no longer needed during manual point prompts.
        del detector
        if device.startswith("cuda"):
            with torch.cuda.device(device):
                torch.cuda.empty_cache()
        segmenter = Sam3PointSegmenter(model_id=args.model, device=device)
        segmenter.set_image(detection["image"])
        RegistrationViewer(segmenter, detection, args.output_dir, source=str(args.image.resolve())).show()
        return 0
    except (ImportError, OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
