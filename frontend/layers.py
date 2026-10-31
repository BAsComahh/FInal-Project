"""Cached display layers built only when an algorithm result changes."""

import cv2
import numpy as np

from .annotation_panel import draw_text


def _cache(rgba):
    pixels = rgba[:, :, 3] != 0
    alpha = rgba[:, :, 3][pixels, None].astype(np.float32) / 255
    colors = rgba[:, :, :3][pixels].astype(np.float32) * alpha
    return pixels, alpha, colors


class VideoLayers:
    def __init__(self, size):
        self.size = size
        self.update(None, size)

    def update(self, prediction, source_size, labels=None, *, active_id=None):
        mask_layer = np.zeros((*self.size[::-1], 4), np.uint8)
        rectangle_layer = mask_layer.copy()
        labels = labels or {}
        scale = np.asarray(self.size) / np.asarray(source_size)
        if prediction is not None:
            for object_id, mask in zip(prediction["object_ids"], prediction["masks"]):
                color = tuple(int(v) for v in np.random.default_rng(object_id).integers(60, 255, 3))
                label = labels.get(object_id, f"Mask {object_id}")
                small = cv2.resize(mask.astype(np.uint8), self.size, interpolation=cv2.INTER_NEAREST)
                mask_layer[small != 0] = (*color, 110)
                contours, _ = cv2.findContours(small, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if object_id == active_id:
                    cv2.drawContours(mask_layer, contours, -1, (255, 255, 255, 255), 3)
                cv2.drawContours(mask_layer, contours, -1, (*color, 220), 1)
                ys, xs = np.nonzero(small)
                if len(xs):
                    draw_text(mask_layer, label, (int(xs.min()), max(17, int(ys.min()) - 3)), (*color, 255), size=16)
                tray = prediction.get("trays", {}).get(object_id)
                if tray is not None:
                    points = np.asarray(tray["corners_image"]) * scale
                    polygon = np.clip(np.rint(points), -1_000_000_000, 1_000_000_000).astype(np.int32)
                    cv2.polylines(rectangle_layer, [polygon], True, (*color, 255), 2, cv2.LINE_AA)
                    if len(xs):
                        draw_text(rectangle_layer, label, (int(xs.min()), max(17, int(ys.min()) - 3)), (*color, 255), size=16)
        self.masks, self.rectangles = _cache(mask_layer), _cache(rectangle_layer)

    def render(self, frame, *, show_masks=True, show_rectangles=True):
        canvas = cv2.resize(frame, self.size, interpolation=cv2.INTER_AREA)
        for enabled, layer in ((show_masks, self.masks), (show_rectangles, self.rectangles)):
            if enabled:
                pixels, alpha, colors = layer
                canvas[pixels] = (canvas[pixels] * (1 - alpha) + colors).astype(np.uint8)
        return canvas


def overlay_masks(frame, prediction, *, labels=None):
    canvas = frame.copy()
    if prediction is None:
        return canvas
    for object_id, mask in zip(prediction["object_ids"], prediction["masks"]):
        color = tuple(int(v) for v in np.random.default_rng(object_id).integers(60, 255, 3))
        canvas[mask] = (canvas[mask] * 0.5 + np.asarray(color) * 0.5).astype(np.uint8)
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(canvas, contours, -1, color, 1)
        ys, xs = np.nonzero(mask)
        if len(xs):
            label = (labels or {}).get(object_id, f"Mask {object_id}")
            draw_text(canvas, label, (int(xs.min()), max(18, int(ys.min()) - 4)), color, size=18)
    return canvas
