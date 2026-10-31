"""Diagnostic overlays for one tray search; drawing never changes coordinates."""

import cv2
import numpy as np

from ..visualization import draw_lines


def _polygon(canvas, points, color, label=None, thickness=2):
    points = np.rint(points).astype(np.int32)
    cv2.polylines(canvas, [points], True, color, thickness, cv2.LINE_AA)
    if label:
        x, y = points.min(axis=0)
        cv2.putText(canvas, label, (max(2, int(x)), max(17, int(y) - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)


def diagnostic_images(image, mask, result):
    matrix = np.asarray(result["image_to_work"])
    size = tuple(result["work_size"])
    roi = cv2.warpPerspective(image, matrix, size)
    local_mask = cv2.warpPerspective((mask != 0).astype(np.uint8), matrix, size,
                                    flags=cv2.INTER_NEAREST).astype(bool)
    mask_view = roi.copy()
    mask_view[local_mask] = (0.5 * mask_view[local_mask] + 0.5 * np.array([70, 220, 70])).astype(np.uint8)
    lines = draw_lines(roi, result["raw_lines_work"], (255, 220, 0), 1)
    corners = lines.copy()
    for index, item in enumerate(result["corner_candidates_work"]):
        point = tuple(np.rint(item["point"]).astype(int))
        cv2.circle(corners, point, 3, (0, 70, 255), -1)
        cv2.putText(corners, str(index), point, cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 70, 255), 1)
    images = {"roi": roi, "mask": mask_view, "lsd": lines, "corners": corners}
    colors = [(0, 255, 0), (0, 180, 255), (255, 100, 100), (220, 180, 30), (180, 80, 200)]
    for stage in result["stages"]:
        canvas = np.full((mask_view.shape[0] + 22 + 20 * len(stage["top"]), mask_view.shape[1], 3), 30, np.uint8)
        canvas[:mask_view.shape[0]] = mask_view
        for index in range(len(stage["top"]) - 1, -1, -1):
            item = stage["top"][index]
            color = colors[index % len(colors)]
            _polygon(canvas, item["corners_work"], color)
            label = f"#{index + 1} score={item['score']:.2f} mask={item['mask_coverage']:.2f} edge={item['edge_support']:.2f}"
            cv2.putText(canvas, label, (5, mask_view.shape[0] + 18 + 20 * index),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)
        images[f"candidates_{stage['method']}"] = canvas
    overlay = image.copy()
    best = result["best"]
    if best is not None:
        _polygon(overlay, best["corners_image"], (0, 255, 0) if result["success"] else (0, 150, 255),
                 f"{best['method']} mask={best['mask_coverage']:.2f} edge={best['edge_support']:.2f}")
    images["overlay"] = overlay
    # Compact stage sheet; the individual files retain their native resolution.
    tiles = []
    for name, canvas in images.items():
        factor = min(400 / canvas.shape[1], 300 / canvas.shape[0])
        scaled = cv2.resize(canvas, (max(1, round(canvas.shape[1] * factor)), max(1, round(canvas.shape[0] * factor))))
        tile = np.full((330, 420, 3), 30, np.uint8)
        tile[28:28 + scaled.shape[0], 10:10 + scaled.shape[1]] = scaled
        cv2.putText(tile, name, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (240, 240, 240), 1)
        tiles.append(tile)
    while len(tiles) % 3:
        tiles.append(np.full((330, 420, 3), 30, np.uint8))
    images["stages"] = np.vstack([np.hstack(tiles[i:i + 3]) for i in range(0, len(tiles), 3)])
    return images
