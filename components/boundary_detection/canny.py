"""Show Canny contours in cyan over the original image."""

from numbers import Integral

import cv2
import numpy as np

from .scale import image_short_side, percent_to_length


def detect_edges(image, low=50, high=150, blur_size=5):
    if not 0 <= low < high:
        raise ValueError("Thresholds must satisfy 0 <= low < high")
    if blur_size < 1 or blur_size % 2 == 0:
        raise ValueError("blur-size must be a positive odd number")
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (blur_size, blur_size), 0)
    return cv2.Canny(blurred, low, high, L2gradient=True)


def detect_lines(edges, min_length_pct=0, max_gap_pct=3.90625, threshold=80):
    """Fit Hough lines with length/gap percentages of the edge image's short side."""
    if isinstance(threshold, bool) or not isinstance(threshold, Integral) or threshold < 1:
        raise ValueError("Hough vote threshold must be a positive integer")
    reference = image_short_side(edges.shape)
    min_length = percent_to_length(min_length_pct, reference, name="Hough minimum length", allow_zero=True)
    max_gap = percent_to_length(max_gap_pct, reference, name="Hough maximum gap", allow_zero=True)
    lines = cv2.HoughLinesP(
        edges, rho=1, theta=np.pi / 180, threshold=threshold,
        minLineLength=min_length, maxLineGap=max_gap,
    )
    return np.empty((0, 4), dtype=np.int32) if lines is None else lines.reshape(-1, 4)


def draw_contours(image, edges):
    """Colour the original Canny pixels without adding corners or line fitting."""
    overlay = (cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2 else image.copy())
    overlay[edges != 0] = (255, 255, 0)  # Cyan in OpenCV BGR order.
    return overlay


def make_comparison(image, edges, contour_overlay, line_overlay=None):
    width = min(650, image.shape[1])
    height = round(image.shape[0] * width / image.shape[1])
    panels = []
    contents = [
        ("Original", image),
        ("Canny edges", cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)),
        ("Canny contours", contour_overlay),
    ]
    if line_overlay is not None:
        contents.append(("Hough line candidates", line_overlay))
    for title, content in contents:
        header = np.full((36, width, 3), 245, dtype=np.uint8)
        cv2.putText(header, title, (12, 25), cv2.FONT_HERSHEY_SIMPLEX,
                    0.65, (30, 30, 30), 1, cv2.LINE_AA)
        panels.append(np.vstack([header, cv2.resize(content, (width, height))]))
    return np.hstack(panels)
