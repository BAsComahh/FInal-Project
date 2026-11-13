"""Cached display layers built only when an algorithm result changes."""

import cv2
import numpy as np

from .drawing import draw_text
from components.homography import transform_points


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


class QueryLayers:
    """Screen overlays cached only for the matching accepted geometry observation."""
    def __init__(self):
        self._key = self._overlay = None

    def draw(self, preview, queries, view):
        if queries.result is None or queries.result_request is None or not queries.result_current(view):
            return
        request, result = queries.result_request, queries.result
        key = (request["epoch"], request["view_revision"], preview.shape)
        if key != self._key:
            self._key = key
            self._overlay = np.zeros_like(preview)
            scale = np.asarray(preview.shape[1::-1]) / np.asarray(view.current.frame.shape[1::-1])
            inverse = np.linalg.inv(request["image_to_plane"])
            project = lambda points: np.rint(transform_points(points, inverse) * scale).astype(np.int32)
            line = result.get("line_mm")
            if "point_a_mm" in result:
                line = [result["point_a_mm"], result["point_b_mm"]]
            if line is not None:
                points = project(line)
                color = (100, 240, 160) if result.get("status") in ("ok", "clear") else (0, 190, 240)
                cv2.line(self._overlay, tuple(points[0]), tuple(points[1]), color, 2, cv2.LINE_AA)
                for point in points:
                    cv2.circle(self._overlay, tuple(point), 4, color, -1, cv2.LINE_AA)
            poses = result.get("poses", ())
            if poses:
                for point in project([pose["center_mm"] for pose in poses]):
                    cv2.circle(self._overlay, tuple(point), 2, (230, 160, 60), -1)
                for index in np.linspace(0, len(poses) - 1, min(12, len(poses)), dtype=int):
                    cv2.polylines(self._overlay, [project(poses[index]["corners_mm"])], True, (230, 160, 60), 1, cv2.LINE_AA)
        pixels = self._overlay.any(axis=2)
        preview[pixels] = (preview[pixels] * .4 + self._overlay[pixels] * .6).astype(np.uint8)


class PresentationLayers:
    """Current view's cached pixels and independent mask/tray display switches."""
    def __init__(self):
        self.layers = None
        self.key = None
        self.show_masks = self.show_rectangles = True
        self.layer_buttons = []

    def render(self, presentation, preview_size, active_id=None):
        key = (id(presentation), presentation.current.view_revision, preview_size)
        if key != self.key:
            if self.layers is None or self.layers.size != preview_size:
                self.layers = VideoLayers(preview_size)
            labels = dict(presentation.units.bindings) if presentation.units else {}
            for object_id in (presentation.current.prediction or {}).get("estimated_ids", []):
                labels[object_id] = labels.get(object_id, f"Mask {object_id}") + " [Estimated]"
            self.layers.update(presentation.current.prediction, presentation.current.frame.shape[1::-1], labels, active_id=active_id)
            self.key = key
        return self.layers.render(presentation.current.frame, show_masks=self.show_masks, show_rectangles=self.show_rectangles)

    def controls(self, panel, y, preview_size, tray_caption):
        button_width = min(165, (preview_size[0] - 30) // 2)
        self.layer_buttons = []
        for x, name, key, enabled, status in (
            (10, "MASK", "m", self.show_masks, "ON" if self.show_masks else "OFF"),
            (20 + button_width, "TRAY", "t", self.show_rectangles, tray_caption),
        ):
            rect = (x, y, x + button_width, y + 28)
            color = (90, 65, 40) if enabled else (55, 55, 55)
            if name == "TRAY" and enabled and not status.startswith("ON"):
                color = (45, 85, 120)
            cv2.rectangle(panel, rect[:2], rect[2:], color, -1)
            draw_text(panel, f"{name} [{key.upper()}]: {status}", (x + 8, y + 20), size=13)
            self.layer_buttons.append((rect, key))
