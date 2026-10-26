"""Rectify a table image and export reusable homography calibration.

Requires an image and --corners X1 Y1 X2 Y2 X3 Y3 X4 Y4 (TL, TR, BR, BL).
The calculation API is provided by components.homography and re-exported here.
"""

import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from components.homography import compute_homography, transform_points, warp_table
from components.homography.geometry import CORNER_NAMES


__all__ = ["compute_homography", "transform_points", "warp_table", "main"]
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--corners", nargs=8, type=float, required=True, metavar="COORD",
                        help="Four pixel coordinates: TL_x TL_y TR_x TR_y BR_x BR_y BL_x BL_y")
    parser.add_argument("--size", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"), help="Rectified output size in pixels")
    parser.add_argument("--board-size", nargs=2, type=float, metavar=("WIDTH", "HEIGHT"), help="Actual table width and height in a consistent unit")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "homography")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        corners = np.asarray(args.corners).reshape(4, 2)
        result = warp_table(args.image, corners, args.size, board_size=args.board_size)
        image_path = args.output_dir / f"{args.image.stem}_rectified.png"
        success, encoded = cv2.imencode(".png", result["image"])
        if not success:
            raise ValueError(f"Cannot encode output image: {image_path}")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        encoded.tofile(image_path)
        metadata = {key: value.tolist() if isinstance(value, np.ndarray) else value
                    for key, value in result.items() if key != "image"}
        metadata.update(image=str(args.image.resolve()), corner_order=list(CORNER_NAMES))
        report_path = args.output_dir / f"{args.image.stem}_homography.json"
        report_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved: {image_path.resolve()}")
        print(f"Saved: {report_path.resolve()}")
        return 0
    except (OSError, ValueError, cv2.error) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
