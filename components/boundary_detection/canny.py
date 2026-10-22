"""Explore Canny edges and long line candidates on a board-game image."""

import argparse
from pathlib import Path

import cv2
import numpy as np

from .io import load_image, save_image
from .config import PROJECT_ROOT


def detect_edges(image, low=50, high=150, blur_size=5):
    if not 0 <= low < high:
        raise ValueError("Thresholds must satisfy 0 <= low < high")
    if blur_size < 1 or blur_size % 2 == 0:
        raise ValueError("blur-size must be a positive odd number")
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (blur_size, blur_size), 0)
    return cv2.Canny(blurred, low, high, L2gradient=True)


def detect_lines(edges, min_length=0, max_gap=20, threshold=80):
    if min_length < 0 or max_gap < 0 or threshold < 1:
        raise ValueError("Hough length/gap must be non-negative; vote threshold must be positive")
    lines = cv2.HoughLinesP(
        edges, rho=1, theta=np.pi / 180, threshold=threshold,
        minLineLength=min_length, maxLineGap=max_gap,
    )
    return np.empty((0, 4), dtype=np.int32) if lines is None else lines.reshape(-1, 4)


def make_comparison(image, edges, line_overlay):
    width = min(650, image.shape[1])
    height = round(image.shape[0] * width / image.shape[1])
    panels = []
    for title, content in [
        ("Original", image),
        ("Canny edges", cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)),
        ("Hough line candidates", line_overlay),
    ]:
        header = np.full((36, width, 3), 245, dtype=np.uint8)
        cv2.putText(header, title, (12, 25), cv2.FONT_HERSHEY_SIMPLEX,
                    0.65, (30, 30, 30), 1, cv2.LINE_AA)
        panels.append(np.vstack([header, cv2.resize(content, (width, height))]))
    return np.hstack(panels)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", type=Path, default=PROJECT_ROOT / "inputs" / "test2.png")
    parser.add_argument("--low", type=float, default=50, help="Canny low gradient threshold")
    parser.add_argument("--high", type=float, default=150, help="Canny high gradient threshold")
    parser.add_argument("--blur-size", type=int, default=5, help="Gaussian kernel size, odd (default: 5)")
    parser.add_argument("--hough", action=argparse.BooleanOptionalAction, default=True, help="Optional Hough comparison; --no-hough keeps only Canny edges")
    parser.add_argument("--min-line-length", "--hough-min-length", dest="hough_min_length", type=int, default=0, help="Minimum Hough length; 0 disables the length limit")
    parser.add_argument("--hough-threshold", type=int, default=80, help="Minimum Hough votes")
    parser.add_argument("--max-line-gap", type=int, default=20, help="Allowed Hough gap in pixels")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "canny")
    parser.add_argument("--show", action="store_true", help="Also open a preview window")
    args = parser.parse_args()

    try:
        image = load_image(args.image)
        edges = detect_edges(image, args.low, args.high, args.blur_size)
        min_length = args.hough_min_length
        lines = (detect_lines(edges, min_length, args.max_line_gap, args.hough_threshold)
                 if args.hough else np.empty((0, 4), dtype=np.int32))
        overlay = image.copy()
        for line in lines:
            cv2.line(overlay, tuple(map(int, line[:2])), tuple(map(int, line[2:])),
                     (255, 150, 0), 2, cv2.LINE_AA)
        comparison = make_comparison(image, edges, overlay)
        for suffix, result in [("edges", edges), ("lines", overlay), ("edge_comparison", comparison)]:
            output = args.output_dir / f"{args.image.stem}_{suffix}.png"
            save_image(output, result)
            print(f"Saved: {output.resolve()}")
    except (OSError, ValueError, cv2.error) as error:
        parser.error(str(error))

    print(f"Edge pixels: {np.count_nonzero(edges)}; Hough line candidates: {len(lines)}")
    if args.show:
        import matplotlib.pyplot as plt

        plt.figure(figsize=(17, 6))
        plt.imshow(cv2.cvtColor(comparison, cv2.COLOR_BGR2RGB))
        plt.title(f"Canny {args.low:g}/{args.high:g}, Hough min length {min_length}px")
        plt.axis("off")
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    main()
