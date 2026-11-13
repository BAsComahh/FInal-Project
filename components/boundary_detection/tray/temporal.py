"""Cheap mask-change checks against the last actual, accepted rectangle fit."""
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class TrayStability:
    centroid_pct: float = 2.0
    max_area_change: float = 0.10
    min_shape_iou: float = 0.90
    max_axis_deg: float = 3.0

    def __post_init__(self):
        values = (self.centroid_pct, self.max_area_change, self.min_shape_iou, self.max_axis_deg)
        if (not np.isfinite(values).all() or not 0 < self.centroid_pct <= 100 or
                not 0 <= self.max_area_change < 1 or not 0 < self.min_shape_iou <= 1 or
                not 0 < self.max_axis_deg < 90):
            raise ValueError("Invalid tray stability thresholds")

    def compare(self, baseline, current, short_side):
        shift = float(np.linalg.norm(np.asarray(current["centroid"]) - baseline["centroid"]))
        area_change = abs(current["area"] / baseline["area"] - 1)
        old = np.unpackbits(np.frombuffer(bytes.fromhex(baseline["shape_bits"]), np.uint8)).astype(bool)
        new = np.unpackbits(np.frombuffer(bytes.fromhex(current["shape_bits"]), np.uint8)).astype(bool)
        union = int(np.count_nonzero(old | new))
        iou = float(np.count_nonzero(old & new) / union) if union else 0.0
        # A near-square mask has no reliable principal-axis angle.
        axis_checked = min(baseline["anisotropy"], current["anisotropy"]) >= 0.10
        angle = abs((current["axis_deg"] - baseline["axis_deg"] + 90) % 180 - 90) if axis_checked else None
        limit = float(short_side * self.centroid_pct / 100)
        stable = (shift <= limit and area_change <= self.max_area_change and iou >= self.min_shape_iou
                  and (angle is None or angle <= self.max_axis_deg))
        return stable, dict(centroid_shift_px=shift, centroid_limit_px=limit, mask_area_change=area_change,
                            shape_iou=iou, axis_change_deg=angle)


def describe_mask(mask):
    mask = np.asarray(mask)
    if mask.ndim != 2 or not np.isfinite(mask).all():
        raise ValueError("Tray stability requires a finite two-dimensional mask")
    binary = (mask != 0).astype(np.uint8)
    moments = cv2.moments(binary, binaryImage=True)
    area = moments["m00"]
    if area <= 0:
        raise ValueError("Tray stability requires a non-empty mask")
    x, y, width, height = cv2.boundingRect(binary)
    thumbnail = cv2.resize(binary[y:y + height, x:x + width], (32, 32), interpolation=cv2.INTER_NEAREST)
    a, b, c = (moments[key] / area for key in ("mu20", "mu11", "mu02"))
    anisotropy = float(np.hypot(a - c, 2 * b) / (a + c)) if a + c > 0 else 0.0
    return dict(area=area, centroid=[moments["m10"] / area, moments["m01"] / area],
                axis_deg=float(np.degrees(.5 * np.arctan2(2 * b, a - c))), anisotropy=anisotropy,
                shape_bits=np.packbits(thumbnail.ravel()).tobytes().hex())
