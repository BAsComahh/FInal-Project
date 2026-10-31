"""Manual polygon masks, independent of SAM inference."""

import cv2
import numpy as np


def polygon_selection(image_shape, vertices):
    """Rasterize a simple polygon, allowing concave shapes in click order."""
    height, width = image_shape[:2]
    points = np.asarray(vertices, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3 or not np.isfinite(points).all():
        raise ValueError("A polygon needs at least three finite vertices")
    if np.any(points < 0) or np.any(points[:, 0] >= width) or np.any(points[:, 1] >= height):
        raise ValueError("Polygon vertices must lie inside the image")
    if len(np.unique(points, axis=0)) != len(points):
        raise ValueError("Polygon vertices must be distinct")
    contour = points.astype(np.float32)
    if abs(cv2.contourArea(contour)) <= 1e-6:
        raise ValueError("Polygon area must be greater than zero")
    # Adjacent edges share a vertex; all other edge intersections are invalid.
    def cross(a, b, c):
        ab, ac = b - a, c - a
        return ab[0] * ac[1] - ab[1] * ac[0]

    def intersects(a, b, c, d):
        if np.any(np.maximum(np.minimum(a, b), np.minimum(c, d)) >
                  np.minimum(np.maximum(a, b), np.maximum(c, d)) + 1e-9):
            return False
        return cross(a, b, c) * cross(a, b, d) <= 0 and cross(c, d, a) * cross(c, d, b) <= 0

    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            if j == i + 1 or (i == 0 and j == len(points) - 1):
                continue
            if intersects(points[i], points[(i + 1) % len(points)], points[j], points[(j + 1) % len(points)]):
                raise ValueError("Polygon edges must not cross; undo a vertex and try again")
    pixel_points = np.rint(points).astype(np.int32)
    pixel_points[:, 0] = np.clip(pixel_points[:, 0], 0, width - 1)
    pixel_points[:, 1] = np.clip(pixel_points[:, 1], 0, height - 1)
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [pixel_points], 1)
    ys, xs = np.nonzero(mask)
    return {"mask": mask.astype(bool),
            "box": [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1],
            "vertices": points.tolist(), "origin": "manual_polygon",
            "score": None, "score_type": None, "points": [], "labels": []}
