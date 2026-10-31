"""Project identified tray corners and draw them on a rectified battlefield."""

from zlib import crc32

import cv2
import numpy as np

from .geometry import transform_points


def _unit_color(unit_id):
    return tuple(int(v) for v in np.random.default_rng(
        crc32(unit_id.encode("utf-8"))).integers(100, 256, 3))


def _binary_mask(mask, shape):
    mask = np.asarray(mask)
    if (mask.shape != tuple(shape) or mask.dtype.kind not in "buif"
            or not np.all((mask == 0) | (mask == 1) | (mask == 255))):
        raise ValueError(f"Mask must be a binary array matching image shape {tuple(shape)}; not logits or a crop")
    return mask != 0


def project_units(units, matrix):
    """Map cyclic original-image corners, preserving IDs and input metadata.

    Each record needs unit_id and corners_image (four cyclic [x, y] points).
    Coordinates stay floating point and are never clipped or refitted.
    """
    matrix = np.asarray(matrix, dtype=np.float64)
    # Reuse the point API's validation even for an empty unit list.
    transform_points([], matrix)
    if np.linalg.matrix_rank(matrix) != 3:
        raise ValueError("matrix must be an invertible homography")
    result, seen = [], set()
    for unit in units:
        if not isinstance(unit, dict):
            raise ValueError("Each unit must be a record with unit_id and corners_image")
        unit_id = unit.get("unit_id")
        if not isinstance(unit_id, str) or not unit_id.strip():
            raise ValueError("Each unit needs a non-empty string unit_id")
        if unit_id in seen:
            raise ValueError(f"Duplicate unit_id: {unit_id}")
        seen.add(unit_id)
        corners = np.asarray(unit.get("corners_image"), dtype=np.float64)
        if corners.shape != (4, 2) or not np.all(np.isfinite(corners)):
            raise ValueError(f"{unit_id}: corners_image must contain four finite [x, y] points")
        contour = corners.astype(np.float32)
        if (not np.all(np.isfinite(contour)) or not cv2.isContourConvex(contour)
                or abs(cv2.contourArea(contour)) <= 1e-6):
            raise ValueError(f"{unit_id}: corners_image must be cyclic, convex and non-degenerate")
        denominators = np.column_stack([corners, np.ones(4)]) @ matrix[2]
        if not (np.all(denominators > 0) or np.all(denominators < 0)):
            raise ValueError(f"{unit_id}: tray crosses the homography horizon")
        mapped = transform_points(corners, matrix)
        result.append({**unit, "corners_image": corners.tolist(),
                       "corners_rectified": mapped.tolist()})
    return result


def draw_units(rectified, units):
    """Draw projected tray outlines and IDs on a copy; no mask overlay.

    units must be records returned by project_units. Rasterization rounds
    corners only while drawing; the records retain their original precision.
    """
    if (not isinstance(rectified, np.ndarray) or rectified.dtype != np.uint8
            or rectified.ndim != 3 or rectified.shape[2] != 3 or not rectified.size):
        raise ValueError("rectified must be a non-empty uint8 BGR image")
    canvas = rectified.copy()
    height, width = canvas.shape[:2]
    for unit in units:
        points = np.asarray(unit["corners_rectified"], dtype=np.float64)
        if points.shape != (4, 2) or not np.isfinite(points).all():
            raise ValueError("corners_rectified must contain four finite [x, y] points")
        # int32 raster coordinates cannot represent arbitrary near-horizon values.
        if np.max(np.abs(points)) > np.iinfo(np.int32).max - 1:
            raise ValueError(f"{unit['unit_id']}: projected corners exceed drawing range")
        polygon = np.rint(points).astype(np.int32)
        color = _unit_color(unit["unit_id"])
        cv2.polylines(canvas, [polygon], True, color, 2, cv2.LINE_AA)
        # An entirely off-screen unit should not leave a misleading border label.
        if (points[:, 0].max() < 0 or points[:, 1].max() < 0
                or points[:, 0].min() >= width or points[:, 1].min() >= height):
            continue
        label = unit["unit_id"]
        (text_width, text_height), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        x = int(np.clip(points[:, 0].min(), 0, max(0, width - text_width - 6)))
        y = int(np.clip(points[:, 1].min() - 6, text_height + 4, max(text_height + 4, height - baseline - 2)))
        cv2.rectangle(canvas, (x, y - text_height - 3), (x + text_width + 5, y + baseline + 2), (25, 25, 25), -1)
        cv2.putText(canvas, label, (x + 2, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1, cv2.LINE_AA)
    return canvas


def render_unit_layers(rectified, units, *, masks=None, show_rectangles=True,
                       show_masks=False, mask_alpha=0.4):
    """Compose independent mask and rectangle layers over a rectified image.

    masks maps unit_id to a *rectified* binary mask. Rectangles (including
    their ID labels) are drawn last. Toggling flags performs no projection,
    fitting or inference. Missing masks are permitted for individual units.
    """
    if (not isinstance(rectified, np.ndarray) or rectified.dtype != np.uint8
            or rectified.ndim != 3 or rectified.shape[2] != 3 or not rectified.size):
        raise ValueError("rectified must be a non-empty uint8 BGR image")
    if not np.isfinite(mask_alpha) or not 0 <= mask_alpha <= 1:
        raise ValueError("mask_alpha must be between 0 and 1")
    masks = {} if masks is None else masks
    if not isinstance(masks, dict):
        raise ValueError("masks must map unit_id to a binary array")
    known_ids = {unit["unit_id"] for unit in units}
    if masks.keys() - known_ids:
        raise ValueError("Every mask must correspond to an existing unit_id")
    if show_masks and not masks and units:
        raise ValueError("Mask layer requested but no masks supplied; add mask_path to the unit geometry")
    canvas = rectified.copy()
    if show_masks:
        for unit in units:
            unit_id = unit["unit_id"]
            if unit_id not in masks:
                continue
            mask = _binary_mask(masks[unit_id], rectified.shape[:2])
            color = np.asarray(_unit_color(unit_id))
            canvas[mask] = ((1 - mask_alpha) * canvas[mask] + mask_alpha * color).astype(np.uint8)
    return draw_units(canvas, units) if show_rectangles else canvas


def rectify_units(image, units, calibration, *, masks=None, show_rectangles=True,
                  show_masks=False, mask_alpha=0.4):
    """Return background, tray overlay and mapped records using one calibration.

    image is the original uint8 BGR frame. calibration is the result of
    compute_homography or a JSON export from tools.homography. No model is
    loaded, no files are written, and no input is modified. Optional masks
    maps unit_id to an original-frame binary mask; the result's masks key
    holds nearest-neighbor-warped masks, reusable for layer toggles.
    """
    if (not isinstance(image, np.ndarray) or image.dtype != np.uint8
            or image.ndim != 3 or image.shape[2] != 3 or not image.size):
        raise ValueError("image must be a non-empty uint8 BGR image")
    if not isinstance(calibration, dict) or not all(key in calibration for key in ("matrix", "output_size")):
        raise ValueError("calibration needs matrix and output_size")
    size = np.asarray(calibration["output_size"], dtype=np.float64)
    if (size.shape != (2,) or not np.isfinite(size).all() or np.any(size < 2)
            or np.any(size != np.floor(size))):
        raise ValueError("output_size must be integer (width, height), each at least 2")
    matrix = np.asarray(calibration["matrix"], dtype=np.float64)
    projected = project_units(units, matrix)
    output_size = tuple(map(int, size))
    background = cv2.warpPerspective(image, matrix, output_size)
    masks = {} if masks is None else masks
    if not isinstance(masks, dict):
        raise ValueError("masks must map unit_id to a binary array")
    if masks.keys() - {unit["unit_id"] for unit in projected}:
        raise ValueError("Every mask must correspond to an existing unit_id")
    projected_masks = {}
    for unit_id, mask in masks.items():
        binary = _binary_mask(mask, image.shape[:2])
        projected_masks[unit_id] = cv2.warpPerspective(
            binary.astype(np.uint8), matrix, output_size, flags=cv2.INTER_NEAREST).astype(bool)
    overlay = render_unit_layers(background, projected, masks=projected_masks,
                                 show_rectangles=show_rectangles, show_masks=show_masks,
                                 mask_alpha=mask_alpha)
    return {"rectified": background, "overlay": overlay,
            "units": projected, "masks": projected_masks}
