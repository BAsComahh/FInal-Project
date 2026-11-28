"""Rectangle geometry and local metric/pixel working views."""

import cv2
import numpy as np

from components.homography.geometry import transform_points


def make_work_view(image, mask, size, image_to_plane, max_size, margin):
    ys, xs = np.nonzero(mask)
    bbox = np.array([[xs.min(), ys.min()], [xs.max(), ys.min()],
                     [xs.max(), ys.max()], [xs.min(), ys.max()]], dtype=float)
    mapping = np.eye(3) if image_to_plane is None else np.asarray(image_to_plane, dtype=float)
    if mapping.shape != (3, 3) or not np.isfinite(mapping).all() or np.linalg.slogdet(mapping)[0] == 0:
        raise ValueError("image_to_plane must be a finite invertible 3x3 matrix")
    divisors = bbox @ mapping[2, :2] + mapping[2, 2]
    if not ((divisors > 0).all() or (divisors < 0).all()):
        raise ValueError("Mask bounding box crosses the calibration horizon")
    plane_bbox = transform_points(bbox, mapping)
    center = transform_points([xs.mean(), ys.mean()], mapping)
    span = np.maximum(np.ptp(plane_bbox, axis=0), 1e-6)
    padding = margin * span.max()
    radius = np.linalg.norm(size) * (0.5 + margin)
    low = np.minimum(plane_bbox.min(axis=0) - padding, center - radius)
    high = np.maximum(plane_bbox.max(axis=0) + padding, center + radius)
    if image_to_plane is None:
        # Keep the full work margin at the frame edge for partially visible trays.
        native_scale = 1.0
    else:
        native_scale = np.sqrt(((np.ptp(xs) + 1) * (np.ptp(ys) + 1)) / np.prod(span))
    scale = min(native_scale, (max_size - 1) / max(high - low))
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("Invalid working scale; check calibration and dimensions")
    plane_to_work = np.array([[scale, 0, -low[0] * scale], [0, scale, -low[1] * scale], [0, 0, 1]])
    image_to_work = plane_to_work @ mapping
    work_size = tuple(np.clip(np.ceil((high - low) * scale).astype(int) + 1, 2, max_size))
    work_image = cv2.warpPerspective(image, image_to_work, work_size, flags=cv2.INTER_LINEAR)
    work_mask = cv2.warpPerspective(mask.astype(np.uint8), image_to_work, work_size,
                                    flags=cv2.INTER_NEAREST).astype(bool)
    if not work_mask.any():
        raise ValueError("The mask vanished in the calibrated working view")
    visible = cv2.warpPerspective(np.ones(mask.shape, np.uint8), image_to_work, work_size,
                                  flags=cv2.INTER_NEAREST)
    valid = cv2.erode(visible, np.ones((3, 3), np.uint8))
    return {"image": work_image, "mask": work_mask, "valid": valid, "visible": visible.astype(bool), "scale": scale,
            "size": np.asarray(size) * scale, "image_to_work": image_to_work,
            "work_to_image": np.linalg.inv(image_to_work), "work_to_plane": np.linalg.inv(plane_to_work)}
