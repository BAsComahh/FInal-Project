"""Registration layout, type-list selection/dragging and prompt pointer input."""
from collections import deque
from time import perf_counter
import cv2
import numpy as np
from application.config import PROJECT_ROOT
from ..shared.drawing import draw_text, draw_loading_progress
from .unit_panel import UnitPanel

class RegistrationView:
    def __init__(self, registration, match, geometry_view, display, viewport):
        self.registration, self.match = registration, match
        self.geometry_view, self.display, self.viewport = geometry_view, display, viewport
        self.unit_panel = UnitPanel()
        self._panel_key = self._panel_image = self._selected_row = None
        self.drag_type = self.drag_position = None
        self.render_times = deque(maxlen=120)
        self.last_rendered_frame = -1

    def render(self, preview_size):
        session = self.match.snapshot()
        self.drawn = session
        self.match.present(session.source_ref)
        self.preview_size = preview_size
        selection = (id(session.units), self.registration.selected_type)
        if selection != self._selected_row:
            self.unit_panel.reveal(session.units, self.registration.selected_type)
            self._selected_row = selection
        preview = self.display.render(self.match.snapshot(), preview_size, self.registration.active_id)
        self.geometry_view.draw(preview, self.match.snapshot())
        if session.load_progress is not None:
            draw_loading_progress(preview, session.load_progress)
        height, width = session.current.frame.shape[:2]
        for click in session.registration_prompts:
            if click["object_id"] == self.registration.active_id and click["video_frame"] == session.source_ref.frame_index:
                x, y = click["point"]
                point = (round(x * self.preview_size[0] / width), round(y * self.preview_size[1] / height))
                cv2.drawMarker(preview, point, (0, 255, 0) if click["positive"] else (0, 0, 255),
                               cv2.MARKER_CROSS if click["positive"] else cv2.MARKER_TILTED_CROSS, 12, 2)
        if session.playing and session.source_ref.frame_index != self.last_rendered_frame:
            self.render_times.append(perf_counter())
        self.last_rendered_frame = session.source_ref.frame_index
        fps = ((len(self.render_times) - 1) / (self.render_times[-1] - self.render_times[0])
               if len(self.render_times) > 1 and self.render_times[-1] > self.render_times[0] else 0)
        lag = ("none" if session.current.prediction_metadata is None else
               f"{max(0, session.source_ref.frame_index - session.current.prediction_metadata['frame_index']) / session.fps:.2f}s")
        panel_height = max(500, self.preview_size[1] + 290)
        panel = np.full((panel_height, self.preview_size[0] + self.unit_panel.WIDTH, 3), 30, dtype=np.uint8)
        panel[:self.preview_size[1], :self.preview_size[0]] = preview
        known_ids = self.match.registration.known_ids()
        key = (panel_height, id(session.units), tuple(session.units.bindings.items()) if session.units else (),
               tuple(session.units.counters.items()) if session.units else (),
               self.registration.selected_type, self.registration.active_id, tuple(known_ids), tuple(self.unit_panel.offset.items()), session.registration_locked, self.registration.interaction_mode)
        if key != self._panel_key:
            self._panel_image = self.unit_panel.render(panel_height, session.units, self.registration.selected_type,
                                                       self.registration.active_id, known_ids, locked=session.registration_locked, mode=self.registration.interaction_mode)
            self._panel_key = key
        panel[:, self.preview_size[0]:] = self._panel_image
        y = self.preview_size[1]
        play_label = "Play / Pause" if session.registration_locked else "Finish + play"
        for x, label in ((10, play_label), (190, "New object (N)")):
            cv2.rectangle(panel, (x, y + 8), (x + 165, y + 39), (80, 80, 80), -1)
            cv2.putText(panel, label, (x + 8, y + 29), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        self.display.controls(panel, y + 48, preview_size, self.match.snapshot().tray_status if self.display.show_rectangles else "OFF")
        model_status = "ready" if session.startup_ready else ("preparing" if session.model_loaded else "loading")
        if session.model_failed:
            model_status = "error"
        rate = f"max {session.inference_fps:g} Hz" if session.inference_fps is not None else "uncapped"
        clock = (f"Clip {session.source_ref.frame_index/session.fps:.2f}s | model {model_status} | display {fps:.1f}/{session.fps:g} fps"
                 f" | Tracking {rate} | mask age {lag} | object {self.registration.active_id}")
        cv2.putText(panel, clock, (10, y + 96), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (230, 230, 230), 1)
        limit = max(20, self.preview_size[0] // 8)
        for row, text in enumerate((session.note[:limit], session.note[limit:limit * 2])):
            cv2.putText(panel, text, (10, y + 118 + row * 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 230, 230), 1)
        self.geometry_view.controls(panel, preview_size, y + 158, self.match.snapshot(), self.match.snapshot())
        if self.drag_type is not None and self.drag_position is not None:
            x, y = self.drag_position
            cv2.rectangle(panel, (x + 8, y + 8), (x + 155, y + 38), (90, 65, 40), -1)
            draw_text(panel, self.drag_type, (x + 15, y + 30), size=16)
        return panel

    def on_mouse(self, event, x, y, flags, preview_size, unit_action, reset_tools, toggle_play):
        session = self.match.snapshot()
        self.preview_size = preview_size
        if self.drag_type is not None:
            if event == cv2.EVENT_MOUSEMOVE:
                self.drag_position = (x, y)
            elif event == cv2.EVENT_LBUTTONUP:
                type_id = self.drag_type
                self.drag_type = self.drag_position = None
                object_id = self.viewport.mask_at(x, y, self.match.snapshot(), preview_size)
                if object_id is not None:
                    self.registration.select_mask(object_id)
                    unit_action("select", type_id)
                elif self.unit_panel.hit(x - self.preview_size[0], y) == ("select", type_id):
                    unit_action("select", type_id)
                else:
                    self.match.set_note("Drop the type onto a segmented mask. Binding unchanged.")
            return
        if x >= self.preview_size[0]:
            if event == cv2.EVENT_MOUSEWHEEL:
                self.unit_panel.scroll(x - self.preview_size[0], -3 if (flags >> 16) > 0 else 3)
            elif event == cv2.EVENT_LBUTTONDOWN:
                action, type_id = self.unit_panel.hit(x - self.preview_size[0], y)
                if action == "select" and self.match.registration.can_edit_points():
                    reset_tools()
                    self.drag_type, self.drag_position = type_id, (x, y)
                else:
                    unit_action(action, type_id)
            return
        if event not in (cv2.EVENT_LBUTTONDOWN, cv2.EVENT_RBUTTONDOWN):
            return
        preview_width, preview_height = self.preview_size
        if 0 <= x < preview_width and 0 <= y < preview_height:
            if self.registration.interaction_mode == "label":
                object_id = self.viewport.mask_at(x, y, self.match.snapshot(), preview_size)
                if object_id is not None:
                    self.registration.select_mask(object_id)
                else:
                    self.match.set_note("No mask here. Tab switches back to segment mode.")
                return
            point = self.viewport.image_point((x, y), session.current.frame.shape[1::-1], preview_size)
            source = self.drawn.board.homography["inverse_matrix"]
            from components.homography import transform_points
            receipt = self.match.registration.point(self.registration.active_id, transform_points(point, source), self.drawn.source_ref,
                                          positive=event == cv2.EVENT_LBUTTONDOWN)
            if receipt.status == "rejected":
                self.match.set_note(receipt.reason)
        elif event == cv2.EVENT_LBUTTONDOWN and preview_height + 8 <= y <= preview_height + 39:
            if 10 <= x <= 175:
                toggle_play()
            elif 190 <= x <= 355:
                reset_tools()
                self.registration.new_object()

    def choose_catalog(self, kind):
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            title = "Load tray calibration (mm)" if kind == "calibration" else f"Import list {kind}"
            filetypes = [("JSON", "*.json")] if kind == "calibration" else [("Army list PDF", "*.pdf"), ("Type catalog JSON", "*.json")]
            path = filedialog.askopenfilename(parent=root, title=title, filetypes=filetypes,
                                              initialdir=str(PROJECT_ROOT / "inputs/army_lists"))
            return path or None
        finally:
            root.destroy()
