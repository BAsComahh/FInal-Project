"""Show Canny contours, with optional Hough comparison."""

import argparse
from pathlib import Path
import sys

import cv2
import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from components.boundary_detection.canny import detect_edges, detect_lines, draw_contours, make_comparison
from components.boundary_detection.config import PROJECT_ROOT
from components.image_io import load_image, save_image


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("image", nargs="?", type=Path, default=PROJECT_ROOT / "inputs" / "test2.png")
    parser.add_argument("--low", type=float, default=50, help="Canny low gradient threshold")
    parser.add_argument("--high", type=float, default=150, help="Canny high gradient threshold")
    parser.add_argument("--blur-size", type=int, default=5, help="Gaussian kernel size, odd (default: 5)")
    parser.add_argument("--hough", action=argparse.BooleanOptionalAction, default=False, help="Also export an optional Hough comparison (off by default)")
    parser.add_argument("--min-line-length-pct", "--hough-min-length-pct", dest="hough_min_length_pct", type=float, default=0, help="Minimum Hough length as a percentage of the image short side; 0 disables the length limit")
    parser.add_argument("--hough-threshold", type=int, default=80, help="Minimum Hough votes")
    parser.add_argument("--max-line-gap-pct", type=float, default=3.90625, help="Allowed Hough gap as a percentage of the image short side (default: 3.90625)")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "canny")
    parser.add_argument("--show", action="store_true", help="Also open a preview window")
    args = parser.parse_args()

    try:
        image = load_image(args.image)
        edges = detect_edges(image, args.low, args.high, args.blur_size)
        lines = (detect_lines(edges, min_length_pct=args.hough_min_length_pct,
                              max_gap_pct=args.max_line_gap_pct, threshold=args.hough_threshold)
                 if args.hough else np.empty((0, 4), dtype=np.int32))
        contours = draw_contours(image, edges)
        overlay = image.copy() if args.hough else None
        for line in lines:
            cv2.line(overlay, tuple(map(int, line[:2])), tuple(map(int, line[2:])),
                     (255, 150, 0), 2, cv2.LINE_AA)
        comparison = make_comparison(image, edges, contours, overlay)
        results = [("edges", edges), ("contours", contours), ("edge_comparison", comparison)]
        if args.hough:
            results.append(("lines", overlay))
        for suffix, result in results:
            output = args.output_dir / f"{args.image.stem}_{suffix}.png"
            save_image(output, result)
            print(f"Saved: {output.resolve()}")
    except (OSError, ValueError, cv2.error) as error:
        parser.error(str(error))

    print(f"Edge pixels: {np.count_nonzero(edges)}; Hough line candidates: {len(lines)}")
    if args.show:
        import matplotlib.pyplot as plt

        plt.figure(figsize=(14, 9))
        plt.imshow(cv2.cvtColor(contours, cv2.COLOR_BGR2RGB))
        plt.title(f"Canny contours {args.low:g}/{args.high:g}")
        plt.axis("off")
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    main()
