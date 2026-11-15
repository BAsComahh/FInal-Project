"""Playback layout, presentation controls and read-only failure lists."""
import cv2
import numpy as np
from ..shared.drawing import draw_text, draw_loading_progress
from .missing_panel import MissingUnitPanel

class LiveView:
    def __init__(self, match, geometry_view, display):
        self.match, self.geometry_view, self.display = match, geometry_view, display
        self.missing_panel = MissingUnitPanel()
        self.view_buttons = []

    def tray_caption(self):
        return self.match.snapshot().tray_status if self.display.show_rectangles else "OFF"

    def render(self, preview_size):
        session = self.match.snapshot()
        view = self.match.snapshot()
        self.preview_size = preview_size
        preview = self.display.render(view, preview_size)
        self.geometry_view.draw(preview, view)
        if session.load_progress is not None:
            draw_loading_progress(preview, session.load_progress)
        width, height = self.preview_size
        missing = self.missing_panel.failed_units(view)
        recovery_note = session.note.startswith(("Manual recovery", "Recovery:"))
        facing_error = session.facing_error
        faces = (view.current.prediction or {}).get("facing_results", {})
        facing_note = ""
        for phase in ("failed", "pending"):
            ids = [obj for obj, row in faces.items() if row.get("recovery_phase") == phase]
            if ids:
                labels = [(view.units.bindings.get(obj, f"Mask {obj}") if view.units else f"Mask {obj}") for obj in ids]
                estimated = sum(obj in view.rules.fronts for obj in ids)
                facing_note = f"Facing recovery {phase}: {', '.join(labels)}. Estimated {estimated}; unknown {len(ids)-estimated}."
                break
        show_status = session.model_failed or session.pending_play or bool(missing) or recovery_note or bool(facing_error) or bool(facing_note)
        button_columns = 3 if width >= 640 else 2
        extra_height = 36
        panel_height = max(332 if missing else 0, height + (272 if show_status else 232) + extra_height)
        panel_width = width + (self.missing_panel.WIDTH if missing else 0)
        panel = np.full((panel_height, panel_width, 3), 30, dtype=np.uint8)
        panel[:height, :width] = preview
        if missing:
            panel[:, width:] = self.missing_panel.render(panel_height, view)
        self.display.controls(panel, height + 8, preview_size, self.tray_caption())
        self.view_buttons = []
        labels = (("clear", "Clear query [Q]"), ("recalibrate", "Recalibrate [K]"), ("replay", "Replay"),
                  ("recover", "Recover units"))
        for i, (action, label) in enumerate(labels):
            button_width = min(190, (width - 10 * (button_columns + 1)) // button_columns)
            x, y = 10 + (i % button_columns) * (button_width + 10), height + 42 + (i // button_columns) * 36
            rect = (x, y, x + button_width, y + 28)
            cv2.rectangle(panel, rect[:2], rect[2:], (65, 65, 65), -1)
            draw_text(panel, label, (x + 6, y + 20), size=max(10, min(13, button_width // 14)))
            self.view_buttons.append((rect, action))
        state = "LIVE"
        stamp = (view.current.prediction_metadata or {}).get("timestamp_seconds")
        observed = "none" if stamp is None else f"{stamp:.2f}s"
        geometry_stamp = (view.current.prediction or {}).get("geometry_metadata", {}).get("timestamp_seconds")
        geometry_time = "none" if geometry_stamp is None else f"{geometry_stamp:.2f}s"
        unavailable = set((view.current.prediction or {}).get("unavailable_ids", ())) | set((view.current.prediction or {}).get("inactive_ids", ()))
        eligible = set(faces) - unavailable
        facing_caption = f" | facing {len(eligible & view.rules.fronts.keys())}/{len(eligible)}" if faces else ""
        live_time = session.source_ref.frame_index / session.fps
        version = session.board.calibration_version
        caption = (f"{session.tracker_name} | View {state} | live {live_time:.2f}s | masks {observed} | geometry {geometry_time} | calibration v{version}{facing_caption}"
                   if width >= 640 else f"LIVE {live_time:.1f}s | seen {observed} | v{version}{facing_caption}")
        draw_text(panel, caption, (10, height + 84 + extra_height), size=12)
        self.geometry_view.controls(panel, preview_size, height + 92 + extra_height, view, self.match.snapshot())
        if show_status:
            status = (session.note if session.model_failed or session.pending_play or recovery_note else
                      "Facing unavailable: " + facing_error if facing_error else
                      facing_note if facing_note else
                      "Candidates ready for review: " + ", ".join(missing) + ".")
            limit = max(24, width // 7)
            for row in range(2):
                draw_text(panel, status[row * limit:(row + 1) * limit], (10, height + 238 + extra_height + row * 18),
                          (100, 170, 245) if session.model_failed else (220, 220, 220), size=12)
        return panel
