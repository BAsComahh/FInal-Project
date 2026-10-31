"""Geometry shared by table frames and local rectangular boundaries."""

import numpy as np


def line_intersection(a, b, *, relative=False, tolerance=1e-8):
    """Intersect infinite supporting lines, returning None for degenerate pairs.

    With relative=True the determinant is normalized by segment lengths, as
    used by table quadrilateral completion. Endpoints need not touch.
    """
    a = np.asarray(a, dtype=float).reshape(2, 2)
    b = np.asarray(b, dtype=float).reshape(2, 2)
    da, db = a[1] - a[0], b[1] - b[0]
    matrix = np.column_stack((da, -db))
    lengths = np.linalg.norm(da) * np.linalg.norm(db)
    limit = tolerance * lengths if relative else tolerance
    if lengths < 1e-12 or abs(np.linalg.det(matrix)) < limit:
        return None
    t = np.linalg.solve(matrix, b[0] - a[0])[0]
    point = a[0] + t * da
    return point if np.isfinite(point).all() else None


def rectangle_corners(center, angle, size):
    """Cyclic corners of a width/depth rectangle; angle is in radians."""
    width, depth = size
    offsets = np.array([[-width, -depth], [width, -depth], [width, depth], [-width, depth]]) / 2
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    return offsets @ rotation.T + center
