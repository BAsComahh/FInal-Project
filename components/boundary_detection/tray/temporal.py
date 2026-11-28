"""Mask motion and exact image-space IoU against the last fitting attempt."""
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class TrayStability:
    centroid_pct: float = 5.0
    min_mask_iou: float = 0.90
    failed_retry_seconds: float = 5.0

    def __post_init__(self):
        if (not np.isfinite((self.centroid_pct, self.min_mask_iou, self.failed_retry_seconds)).all() or
                not 0 < self.centroid_pct <= 100 or not 0 < self.min_mask_iou <= 1 or self.failed_retry_seconds <= 0):
            raise ValueError("Invalid tray stability thresholds")

    def compare(self, baseline, current, short_side):
        shift = float(np.linalg.norm(np.asarray(current["centroid"]) - baseline["centroid"]))
        old, new = (mask_pixels(sample) for sample in (baseline, current))
        ax, ay, aw, ah = baseline["bbox"]
        bx, by, bw, bh = current["bbox"]
        x0, y0, x1, y1 = max(ax, bx), max(ay, by), min(ax + aw, bx + bw), min(ay + ah, by + bh)
        intersection = (int(np.count_nonzero(old[y0-ay:y1-ay, x0-ax:x1-ax] & new[y0-by:y1-by, x0-bx:x1-bx]))
                        if x1 > x0 and y1 > y0 else 0)
        iou = intersection / (baseline["area"] + current["area"] - intersection)
        limit = float(short_side * self.centroid_pct / 100)
        return shift <= limit and iou >= self.min_mask_iou, dict(
            centroid_shift_px=shift, centroid_limit_px=limit, mask_iou=iou)


def mask_pixels(sample):
    width, height = sample["bbox"][2:]
    return np.unpackbits(np.frombuffer(bytes.fromhex(sample["mask_bits"]), np.uint8),
                         count=width * height).reshape(height, width).astype(bool)


def describe_mask(mask):
    mask = np.asarray(mask)
    if mask.ndim != 2 or (mask.dtype.kind not in "bui" and not np.isfinite(mask).all()):
        raise ValueError("Tray stability requires a finite two-dimensional mask")
    if mask.dtype == np.bool_:
        binary = mask.view(np.uint8)
    elif mask.dtype == np.uint8:
        binary = mask
    else:
        binary = (mask != 0).astype(np.uint8)
    x, y, width, height = cv2.boundingRect(binary)
    if not width or not height:
        raise ValueError("Tray stability requires a non-empty mask")
    crop = binary[y:y + height, x:x + width]
    moments = cv2.moments(crop, binaryImage=True)
    area = moments["m00"]
    centroid = [(moments["m10"] + x * area) / area, (moments["m01"] + y * area) / area]
    return dict(area=area, centroid=centroid, bbox=[x, y, width, height],
                mask_bits=np.packbits(crop).tobytes().hex())
