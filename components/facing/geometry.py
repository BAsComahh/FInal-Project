"""Source-frame crops and conservative selection among current tray edges."""

from uuid import uuid4

import cv2
import numpy as np

MEAN_RGB = (124, 116, 104)


def masked_source_crop(raw_frame, mask, metadata):
    """Mask both reference/query backgrounds before the model's normalization."""
    if raw_frame is None or raw_frame.ndim != 3 or raw_frame.shape[2] != 3:
        raise ValueError("Facing requires a matching original BGR source frame")
    source_size = tuple(metadata["source_image_size"])
    if raw_frame.shape[1::-1] != source_size or mask.shape != tuple(metadata["image_size"])[::-1]:
        raise ValueError("Facing frame/mask dimensions do not match their provenance")
    inverse = np.asarray(metadata["homography"]["inverse_matrix"], dtype=float)
    source_mask = cv2.warpPerspective(np.asarray(mask, dtype=np.uint8), inverse, source_size,
                                      flags=cv2.INTER_NEAREST).astype(bool)
    ys, xs = np.nonzero(source_mask)
    if not len(xs):
        raise ValueError("Facing target has no source-frame mask")
    lo, hi = np.array([xs.min(), ys.min()]), np.array([xs.max() + 1, ys.max() + 1])
    side = max(1, int(round(float((hi - lo).max()) * 1.15)))
    x, y = np.rint((lo + hi) / 2 - side / 2).astype(int)
    crop = np.full((side, side, 3), MEAN_RGB, dtype=np.uint8)
    x0, y0, x1, y1 = max(0, x), max(0, y), min(source_size[0], x + side), min(source_size[1], y + side)
    rgb = cv2.cvtColor(raw_frame[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)
    selected = source_mask[y0:y1, x0:x1]
    target = crop[y0-y:y1-y, x0-x:x1-x]
    target[selected] = rgb[selected]
    return crop


def make_reference(raw_frame, mask, metadata, front, tray, unit_id):
    ray = np.asarray(front.get("source_ray"), dtype=float)
    if front.get("source") != "manual" or ray.shape != (2, 2) or not np.isfinite(ray).all():
        raise ValueError("Facing reference requires an initial manual source-facing ray")
    direction = ray[1] - ray[0]
    if np.linalg.norm(direction) < 1e-8:
        raise ValueError("Facing reference ray is degenerate")
    corners = np.asarray(tray["corners_plane"], dtype=float)
    directions = (corners + np.roll(corners, -1, axis=0)) / 2 - corners.mean(axis=0)
    headings = np.degrees(np.arctan2(directions[:, 1], directions[:, 0]))
    edge = int(np.argmin(np.abs((headings - front["angle_deg"] + 180) % 360 - 180)))
    crop = masked_source_crop(raw_frame, mask, metadata)
    crop.setflags(write=False)
    from .appearance import tray_patch
    template = tray_patch(raw_frame, mask, metadata, tray, edge)
    for value in template.values():
        value.setflags(write=False)
    return {"reference_id": uuid4().hex, "unit_id": unit_id, "crop_rgb": crop,
            "detector_template": template,
            "source_ray": ray.tolist(), "front_width_mm": float(np.linalg.norm(corners[(edge+1) % 4] - corners[edge])),
            "source_size": list(raw_frame.shape[1::-1]), "frame_index": metadata["frame_index"],
            "calibration_version": metadata.get("calibration_version")}


def select_front_edge(rotation, reference_ray, corners_source, corners_mm, front_width_mm, *, margin_deg=20.0):
    rotation, ray = np.asarray(rotation, dtype=float), np.asarray(reference_ray, dtype=float)
    source, metric = np.asarray(corners_source, dtype=float), np.asarray(corners_mm, dtype=float)
    if (rotation.shape != (3, 3) or ray.shape != (2, 2) or source.shape != (4, 2) or metric.shape != (4, 2)
            or not all(np.isfinite(x).all() for x in (rotation, ray, source, metric))
            or not np.isfinite(front_width_mm) or front_width_mm <= 0
            or not np.isfinite(margin_deg) or not 0 <= margin_deg < 90):
        raise ValueError("Invalid facing geometry or candidate margin")
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-3) or not np.isclose(np.linalg.det(rotation), 1, atol=1e-3):
        raise ValueError("Facing estimate is not a proper rotation")
    # shortcut: image-plane projection, until calibrated camera geometry is available.
    reference_direction = ray[1] - ray[0]
    direction = rotation[:2, :2] @ reference_direction
    if np.linalg.norm(reference_direction) < 1e-8 or np.linalg.norm(direction) < 1e-6 * np.linalg.norm(reference_direction):
        return {"status": "unknown", "reason": "Facing projection is degenerate"}
    directions = (source + np.roll(source, -1, axis=0)) / 2 - source.mean(axis=0)
    norms = np.linalg.norm(directions, axis=1)
    if np.any(norms < 1e-8):
        return {"status": "unknown", "reason": "Tray edge direction is degenerate"}
    lengths = np.linalg.norm(np.roll(metric, -1, axis=0) - metric, axis=1)
    pairs = np.array([lengths[[0, 2]].mean(), lengths[[1, 3]].mean()])
    if np.isclose(*pairs, rtol=.01):
        candidates = [0, 1, 2, 3]
    else:
        parity = int(np.argmin(np.abs(pairs - front_width_mm)))
        candidates = [parity, parity + 2]
    errors = np.degrees(np.arccos(np.clip(directions @ direction / (norms * np.linalg.norm(direction)), -1, 1)))
    ranked = sorted(candidates, key=lambda edge: errors[edge])
    margin = float(errors[ranked[1]] - errors[ranked[0]])
    result = {"status": "unknown", "reason": "Facing edge candidates are ambiguous", "candidates": candidates,
              "edge_errors_deg": errors.tolist(), "edge_margin_deg": margin,
              "coarse_source_direction": (direction / np.linalg.norm(direction)).tolist(),
              "coordinate_assumption": "source_image_plane_projection"}
    if margin > margin_deg:
        result.update(status="selected", edge=int(ranked[0]), reason="Appearance selected a current tray edge")
    return result
