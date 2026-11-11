"""Query controls, selected trays and cached measurement/range overlays."""
import cv2
import numpy as np
from components.homography import transform_points
from ..shared.drawing import draw_text

class GeometryView:
    def __init__(self, geometry, queries, editor, scene_view):
        self.geometry, self.editor, self.scene_view = geometry, editor, scene_view
        self.buttons = []
        self.queries = queries
        self.overlay = self.overlay_key = None

    def controls(self, panel, preview_size, y, presentation, source):
        width = preview_size[0]
        self.buttons = []
        moves = self.geometry.mode.replace("_", " ").title() if self.geometry.mode in self.geometry.ORDERS else "Move"
        items = [("distance", "Distance [D]"), ("los", "LOS [L]"), ("move", f"{moves} [V]"), ("double", "Double [J]"),
                 ("front", "Set front [F]"), ("profile", "Unit rules [E]"), ("terrain", "Terrain [G]"), ("undo_terrain", "Undo terrain")]
        button_width = (width - 50) // 4
        for i, (action, label) in enumerate(items):
            x, top = 10 + (i % 4) * (button_width + 10), y + (i // 4) * 34
            rect = (x, top, x + button_width, top + 28)
            active = self.geometry.mode == action or (action == "move" and self.geometry.mode in self.geometry.ORDERS) or self.editor.input_mode == action
            cv2.rectangle(panel, rect[:2], rect[2:], (90, 100, 45) if active else (55, 55, 55), -1)
            draw_text(panel, label, (x + 6, top + 19), size=max(9, min(13, button_width // 13)))
            self.buttons.append((rect, action))
        text = self.geometry.note
        if self.queries.result is not None:
            status = self.queries.result.get("status", "unknown")
            if self.geometry.mode == "distance" and "distance_in" in self.queries.result:
                text = f"Distance: {self.queries.result['distance_in']:.2f} in / {self.queries.result['distance_mm']:.1f} mm"
            else:
                text = f"{self.geometry.mode}: {status}. {self.queries.result.get('reason', '')}"
            if self.queries.result_request is not None:
                observed = self.queries.result_request["metadata"]["timestamp_seconds"]
                age = max(0, source.source_ref.frame_index - self.queries.result_request["metadata"]["frame_index"]) / source.fps
                text = f"Observed {observed:.2f}s / age {age:.2f}s | " + text
                if not self.queries.result_current(presentation):
                    text = "Updating | " + text
            if self.queries.result.get("warnings"):
                text += " | " + "; ".join(self.queries.result["warnings"][:1])
        roster = presentation.units
        selected = ", ".join(roster.bindings.get(i, f"Mask {i}") for i in self.geometry.selected) if roster else ""
        draw_text(panel, f"KoW4 mini | Selected: {selected or 'none'} | estimates | Q clears query", (10, y + 86), size=12)
        limit = max(24, width // 7)
        for row in range(2):
            draw_text(panel, text[row * limit:(row + 1) * limit], (10, y + 106 + row * 18), size=12)

    def draw(self, preview, view):
        scale = np.asarray(preview.shape[1::-1]) / np.asarray(view.current.frame.shape[1::-1])
        self.scene_view.draw_terrain(preview, view)
        if view.current.prediction is not None:
            for object_id in self.geometry.selected:
                tray = view.current.prediction.get("trays", {}).get(object_id)
                if tray is not None:
                    points = np.rint(np.asarray(tray["corners_image"]) * scale).astype(np.int32)
                    cv2.polylines(preview, [points], True, (245, 245, 245), 2, cv2.LINE_AA)
        self.scene_view.draw_inputs(preview, view)
        if self.queries.result is None or self.queries.result_request is None or self.geometry.mode is None:
            return
        if not self.queries.result_current(view):
            return
        key = (self.queries.result_request["epoch"], self.queries.result_request["view_revision"], preview.shape)
        if key != self.overlay_key:
            self.overlay_key = key
            self.overlay = np.zeros_like(preview)
            inverse = np.linalg.inv(self.queries.result_request["image_to_plane"])
            line = self.queries.result.get("line_mm")
            if self.geometry.mode == "distance" and "point_a_mm" in self.queries.result:
                line = [self.queries.result["point_a_mm"], self.queries.result["point_b_mm"]]
            if line is not None:
                points = np.rint(transform_points(line, inverse) * scale).astype(int)
                color = (100, 240, 160) if self.queries.result.get("status") in ("ok", "clear") else (0, 190, 240)
                cv2.line(self.overlay, tuple(points[0]), tuple(points[1]), color, 2, cv2.LINE_AA)
            centers = [pose["center_mm"] for pose in self.queries.result.get("poses", [])]
            if centers:
                for point in np.rint(transform_points(centers, inverse) * scale).astype(int):
                    cv2.circle(self.overlay, tuple(point), 2, (230, 160, 60), -1)
        mask = self.overlay.any(axis=2)
        preview[mask] = (preview[mask] * .4 + self.overlay[mask] * .6).astype(np.uint8)
