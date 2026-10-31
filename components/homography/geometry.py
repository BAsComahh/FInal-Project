"""Homography calibration and coordinate transformations."""

import cv2
import numpy as np


CORNER_NAMES = ("TL", "TR", "BR", "BL")


def order_corners(points):
    """Label four unordered points by image orientation, without quadrant gates."""
    points = np.asarray(points, dtype=np.float64)
    if points.shape != (4, 2) or not np.isfinite(points).all():
        raise ValueError("Select four finite corner points")
    contour = points.astype(np.float32)
    if not np.isfinite(contour).all():
        raise ValueError("Corner coordinates exceed the supported range")
    indices = cv2.convexHull(contour, returnPoints=False).ravel()
    if len(indices) != 4 or abs(cv2.contourArea(contour[indices])) <= 1e-6:
        raise ValueError("Four distinct corners must form a convex quadrilateral")
    # Keep original precision when ordering the float32 convex-hull indices.
    hull = points[indices]
    if cv2.contourArea(hull.astype(np.float32), oriented=True) < 0:
        hull = hull[::-1]
    target = np.array([[0, 0], [1, 0], [1, 1], [0, 1]])
    normalized = (hull - hull.min(axis=0)) / np.ptp(hull, axis=0)
    shift = min(range(4), key=lambda i: (
        float(np.square(np.roll(normalized, -i, axis=0) - target).sum()),
        hull[i, 1], hull[i, 0]))
    ordered = _corners_array(np.roll(hull, -shift, axis=0))
    return {name: point.tolist() for name, point in zip(CORNER_NAMES, ordered)}


def _corners_array(corners):
    if isinstance(corners, dict):
        if not all(name in corners for name in CORNER_NAMES):
            raise ValueError("corners must contain TL, TR, BR and BL")
        corners = [corners[name] for name in CORNER_NAMES]
    points = np.asarray(corners, dtype=np.float64)
    if points.shape != (4, 2) or not np.all(np.isfinite(points)):
        raise ValueError("corners must be four finite [x, y] points in TL, TR, BR, BL order")
    contour = points.astype(np.float32)
    if (not np.all(np.isfinite(contour)) or not cv2.isContourConvex(contour)
            or abs(cv2.contourArea(contour)) <= 1e-6):
        raise ValueError("corners must form a convex, non-degenerate quadrilateral")
    return points


def _size_pair(value, name, *, pixels=False):
    size = np.asarray(value, dtype=np.float64)
    if size.shape != (2,) or not np.all(np.isfinite(size)) or np.any(size <= 0):
        raise ValueError(f"{name} must be a positive finite (width, height) pair")
    if pixels:
        if np.any(size < 2) or np.any(size != np.floor(size)):
            raise ValueError("output_size must contain integer pixel dimensions of at least 2")
        return tuple(map(int, size))
    return tuple(map(float, size))


def compute_homography(corners, output_size=None, *, board_size=None):
    """Return forward/inverse matrices for TL/TR/BR/BL to a rectangle.

    output_size is (width, height) in pixels. Without it, opposite edge lengths
    estimate the raster size. If board_size=(physical_width, physical_height)
    is supplied, automatic raster sizing follows that aspect ratio, and the
    result also includes image_to_board / board_to_image matrices. Physical
    units are defined by the caller; no real-world dimensions are assumed.
    """
    source = _corners_array(corners)
    board = _size_pair(board_size, "board_size") if board_size is not None else None
    estimated_size = output_size is None
    if estimated_size:
        top, right, bottom, left = np.linalg.norm(np.roll(source, -1, axis=0) - source, axis=1)
        width_span, height_span = max(top, bottom), max(left, right)
        if board is not None:
            scale = max(width_span / board[0], height_span / board[1])
            width_span, height_span = board[0] * scale, board[1] * scale
        output_size = (max(2, int(round(width_span)) + 1), max(2, int(round(height_span)) + 1))
    width, height = _size_pair(output_size, "output_size", pixels=True)
    target = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
                      dtype=np.float64)
    matrix = cv2.getPerspectiveTransform(source.astype(np.float32), target.astype(np.float32))
    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError as error:
        raise ValueError("corners do not define an invertible homography") from error
    if not np.all(np.isfinite(matrix)) or not np.all(np.isfinite(inverse)):
        raise ValueError("homography contains non-finite values")
    image_to_board = board_to_image = None
    if board is not None:
        scale = np.diag([board[0] / (width - 1), board[1] / (height - 1), 1.0])
        image_to_board = scale @ matrix
        board_to_image = inverse @ np.diag([(width - 1) / board[0], (height - 1) / board[1], 1.0])
    return {
        "matrix": matrix, "inverse_matrix": inverse,
        "source_corners": source, "target_corners": target,
        "output_size": (width, height), "output_size_estimated": estimated_size,
        "board_size": board, "image_to_board": image_to_board, "board_to_image": board_to_image,
    }


def transform_points(points, matrix):
    """Map an (N, 2) point array, or one [x, y] point, without clipping."""
    points = np.asarray(points, dtype=np.float64)
    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise ValueError("matrix must be a finite 3x3 homography")
    if points.size == 0:
        return np.empty((0, 2), dtype=np.float64)
    single = points.shape == (2,)
    if single:
        points = points.reshape(1, 2)
    if points.ndim != 2 or points.shape[1] != 2 or not np.all(np.isfinite(points)):
        raise ValueError("points must be finite [x, y] pairs")
    projected = np.column_stack([points, np.ones(len(points))]) @ matrix.T
    if np.any(projected[:, 2] == 0):
        raise ValueError("a point maps to infinity under this homography")
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        result = projected[:, :2] / projected[:, 2:]
    if not np.all(np.isfinite(result)):
        raise ValueError("point transformation produced non-finite coordinates")
    return result[0] if single else result
