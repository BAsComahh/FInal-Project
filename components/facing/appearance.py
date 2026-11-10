"""Small, pose-aligned source patches for cheap facing checks; no neural model."""

import cv2
import numpy as np

from components.homography import transform_points


def tray_patch(raw_frame, mask, metadata, tray, edge, *, size=48):
    """Normalize a tray so its proposed front is the patch's top edge."""
    if raw_frame is None or raw_frame.shape[1::-1] != tuple(metadata["source_image_size"]):
        raise ValueError("Facing check requires the matching source frame")
    if mask.shape != tuple(metadata["image_size"])[::-1]:
        raise ValueError("Facing check mask dimensions disagree with the observation")
    corners = tray.get("corners_image")
    if corners is None:
        if tray.get("corners_source") is not None:
            corners = transform_points(tray["corners_source"], metadata["homography"]["matrix"])
        else:
            corners = transform_points(tray["corners_plane"], np.linalg.inv(metadata["image_to_plane"]))
    corners = np.asarray(corners, dtype=np.float32)
    target = np.float32([[0, 0], [size-1, 0], [size-1, size-1], [0, size-1]])
    warp = cv2.getPerspectiveTransform(np.roll(corners, -edge, axis=0), target)
    source_warp = warp @ np.asarray(metadata["homography"]["matrix"], dtype=float)
    pixels = cv2.warpPerspective(raw_frame, source_warp, (size, size))[:, :, ::-1].astype(np.float32) / 255
    selected = cv2.warpPerspective(mask.astype(np.uint8), warp, (size, size), flags=cv2.INTER_NEAREST).astype(bool)
    # Background never contributes to the comparison or bleeds into foreground.
    pixels[~selected] = 0
    return {"pixels": pixels, "mask": selected}


def patch_similarity(first, second, *, min_coverage=.25):
    common = first["mask"] & second["mask"]
    if common.mean() < min_coverage:
        return None
    a, b = first["pixels"][common].astype(float), second["pixels"][common].astype(float)
    a, b = a - a.mean(axis=0), b - b.mean(axis=0)
    scale = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.clip(np.sum(a * b) / scale, -1, 1)) if scale > 1e-8 else None


def patch_change(first, second, *, min_coverage=.25):
    common = first["mask"] & second["mask"]
    if common.mean() < min_coverage:
        if min(first["mask"].mean(), second["mask"].mean()) >= min_coverage:
            return float(1 - common.sum() / (first["mask"] | second["mask"]).sum())
        return None
    return float(np.abs(first["pixels"][common] - second["pixels"][common]).mean())


def predicted_edge(front, tray, source_to_plane, front_width):
    corners = np.asarray(tray["corners_plane"], dtype=float)
    directions = (corners + np.roll(corners, -1, axis=0)) / 2 - corners.mean(axis=0)
    headings = np.degrees(np.arctan2(directions[:, 1], directions[:, 0]))
    if front.get("source_ray") is not None:
        ray = transform_points(front["source_ray"], source_to_plane)
        angle = np.degrees(np.arctan2(*(ray[1] - ray[0])[::-1]))
    else:
        angle = front["angle_deg"]
    lengths = np.linalg.norm(np.roll(corners, -1, axis=0) - corners, axis=1)
    pairs = [lengths[[0, 2]].mean(), lengths[[1, 3]].mean()]
    if np.isclose(*pairs, rtol=.01):
        candidates = list(range(4))
    else:
        parity = int(np.argmin(np.abs(np.asarray(pairs) - front_width)))
        candidates = [parity, parity + 2]
    edge = min(candidates, key=lambda i: abs((headings[i] - angle + 180) % 360 - 180))
    return edge, candidates
