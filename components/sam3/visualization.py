"""Simple segmentation preview; numbering is local to this image."""

import cv2
import numpy as np


def draw_segmentation(result):
    canvas = result["image"].copy()
    rng = np.random.default_rng(42)
    for index, (mask, box, score) in enumerate(zip(result["masks"], result["boxes"], result["scores"])):
        color = tuple(int(value) for value in rng.integers(60, 255, size=3))
        canvas[mask] = (canvas[mask] * 0.5 + np.asarray(color) * 0.5).astype(np.uint8)
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(canvas, contours, -1, color, 1)
        x1, y1, x2, y2 = np.rint(box).astype(int)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 1)
        cv2.putText(canvas, f"{index}: {score:.2f}", (x1, max(15, y1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    if len(result["masks"]) == 0:
        cv2.putText(canvas, "No matches", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    return canvas
