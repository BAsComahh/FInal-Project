"""Directional distance fields for fixed-size rectangle fitting."""

import cv2
import numpy as np

from ..geometry import rectangle_corners


_FRACTIONS = np.linspace(0.03, 0.97, 24)[None, :, None]
_SIDE_ANGLES = np.array([0, np.pi / 2, 0, np.pi / 2])
_DIRECTION_COUNT = 36


class DirectionalChamfer:
    """Lazily constructed for a fitting ROI, shared by its search stages."""

    def __init__(self, view, lines, tolerance, angle_tolerance):
        self.size = view["size"]
        self.height, self.width = view["mask"].shape
        self.visible = view["visible"]
        self.tolerance = tolerance
        self.angular_weight = tolerance / angle_tolerance

        delta = lines[:, 2:] - lines[:, :2]
        angle_step = np.pi / _DIRECTION_COUNT
        bins = np.rint(np.arctan2(delta[:, 1], delta[:, 0]) / angle_step).astype(int) % _DIRECTION_COUNT
        occupied = np.unique(bins)
        self.orientations = occupied * angle_step
        self.fields = np.empty((len(occupied), self.height, self.width), dtype=np.float32)
        for index, direction in enumerate(occupied):
            raster = np.ones((self.height, self.width), dtype=np.uint8)
            for ax, ay, bx, by in np.rint(lines[bins == direction] * 16).astype(int):
                cv2.line(raster, (ax, ay), (bx, by), 0, 1, shift=4)
            cv2.distanceTransform(raster, cv2.DIST_L2, cv2.DIST_MASK_5, self.fields[index])

    def distances(self, centers, angle):
        polygon = rectangle_corners(np.zeros(2), angle, self.size)
        sides = np.roll(polygon, -1, axis=0) - polygon
        samples = polygon[:, None, :] + _FRACTIONS * sides[:, None, :]
        lower = -polygon.min(axis=0)
        upper = np.array([self.width - 1, self.height - 1]) - polygon.max(axis=0)
        valid = ((centers >= lower) & (centers <= upper)).all(axis=1)
        pixels = np.rint(centers[:, None, None, :] + samples).astype(int)
        x = np.clip(pixels[..., 0], 0, self.width - 1)
        y = np.clip(pixels[..., 1], 0, self.height - 1)
        difference = np.abs(self.orientations[:, None] - (angle + _SIDE_ANGLES) % np.pi)
        angular_cost = np.minimum(difference, np.pi - difference) * self.angular_weight
        distance = self.fields[:, y, x]
        distance += angular_cost[:, None, :, None].astype(np.float32)
        cost = np.minimum(distance.min(axis=0), 3 * self.tolerance)
        return np.where(valid[:, None, None] & self.visible[y, x], cost, np.inf)
