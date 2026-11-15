"""Query controls, selected trays and cached measurement/range overlays."""
import cv2
import numpy as np
from ..shared.drawing import draw_text
from ..shared.layers import QueryLayers

class GeometryView:
    def __init__(self, geometry, queries, editor, scene_view):
        self.geometry, self.editor, self.scene_view = geometry, editor, scene_view
        self.buttons = []
        self.queries = queries
        self.query_layers = QueryLayers()

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
                label = "Snapshot" if self.queries.result_request.get("fixed") else "Observed"
                text = f"{label} {observed:.2f}s / age {age:.2f}s | " + text
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
        if self.geometry.mode is not None:
            self.query_layers.draw(preview, self.queries, view)
