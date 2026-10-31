"""Read and save one image, optionally converting its channel layout."""

import argparse
from pathlib import Path
import sys

import cv2

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from components.image_io import load_image, save_image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--mode", choices=("color", "gray", "unchanged"), default="unchanged",
                        help="Default: preserve grayscale/BGR/BGRA channels; output format follows extension")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        image = load_image(args.input, mode=args.mode)
        save_image(args.output, image)
        print(f"Saved: {args.output.resolve()} | shape: {image.shape} | mode: {args.mode}")
        return 0
    except (OSError, ValueError, cv2.error) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
