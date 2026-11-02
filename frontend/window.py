"""OpenCV desktop window reading shared match data from its workflow."""

from collections import deque
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from .annotation_panel import UnitPanel, draw_text
from .layers import VideoLayers, overlay_masks
from .table_setup import TableSetup
from .workflow import RegistrationWorkflow, Stage
from .rules_panel import RulesPanel


class VideoWindow:
    WINDOW = "Battlefield - video registration"

    def __init__(self, video, *, preview_width=960, **options):
        if preview_width < 320:
            raise ValueError("preview-width must be at least 320")
        self.workflow = RegistrationWorkflow(video, **options)
        self.preview_width_limit = preview_width
        self.unit_panel = UnitPanel()
        self.table_setup = TableSetup(self.workflow.initial_frame,
                                      board_size_in=np.asarray(self.workflow.data.board.board_size_mm) / 25.4)
        self.rules = RulesPanel()
        self.layers = VideoLayers(self.preview_size)
        self._layer_key = self._panel_key = self._panel_image = self._selected_row = None
        self.drag_type = self.drag_position = None
        self.show_masks = self.show_rectangles = True
        self.layer_buttons = []
        self.view_buttons = []
        self.recalibration_cancel_button = None
        self.render_times = deque(maxlen=120)
        self.last_rendered_frame = -1
        self.dirty = True

    @property
    def preview_size(self):
        frame = (self.table_setup.frame if self.workflow.stage is Stage.RECALIBRATE
                 else self.workflow.data.current.frame)
        height, width = frame.shape[:2]
        preview_width = min(self.preview_width_limit, width)
        return preview_width, max(1, round(height * preview_width / width))

    def _activate_table_view(self):
        if not self.table_setup.confirmed or self.workflow.stage not in (Stage.TABLE, Stage.RECALIBRATE):
            return
        try:
            if self.workflow.stage is Stage.RECALIBRATE:
                boundary = self.table_setup.snapshot()
                self.table_setup.confirmed = False
                self.workflow.apply_recalibration(self.table_setup.corners, boundary,
                                                  board_size_in=self.table_setup.board_size_in)
            else:
                self.workflow.confirm_table(self.table_setup.corners, self.table_setup.snapshot(),
                                            board_size_in=self.table_setup.board_size_in)
        except (ValueError, cv2.error) as error:
            self.table_setup.confirmed = False
            self.table_setup.note = f"Cannot map these corners: {error}. Please correct them."
        self.dirty = True

    def _begin_recalibration(self):
        if self.rules.input_mode is not None:
            self.rules.note = "Finish or cancel the rule input before recalibrating."
            self.dirty = True
            return
        try:
            frame = self.workflow.begin_recalibration()
        except (ValueError, OSError, cv2.error) as error:
            self.workflow.note = str(error)
        else:
            self.rules.reset()
            self.rules.note = "Select a rule tool, then click one or two units."
            self.table_setup.close()
            self.table_setup = TableSetup(frame, board_size_in=np.asarray(self.workflow.data.board.board_size_mm) / 25.4)
        self.dirty = True

    def _cancel_recalibration(self):
        try:
            self.workflow.cancel_recalibration()
        except ValueError as error:
            self.table_setup.note = str(error)
        self.dirty = True

    def _update_layers(self):
        flow = self.workflow
        view = flow.presentation
        key = (id(view), view.current.view_revision, self.preview_size)
        if key != self._layer_key:
            if self.layers.size != self.preview_size:
                self.layers = VideoLayers(self.preview_size)
            self.layers.update(view.current.prediction, view.current.frame.shape[1::-1],
                               view.units.bindings if view.units else None,
                               active_id=None if flow.stage is Stage.PLAYBACK else flow.active_id)
            self._layer_key = key
        selection = (id(flow.data.units), flow.selected_type)
        if selection != self._selected_row:
            self.unit_panel.reveal(flow.data.units, flow.selected_type)
            self._selected_row = selection

    def render(self):
        self._update_layers()
        panel = self._render()
        self.dirty = self.workflow.dirty = False
        return panel

    def _tray_caption(self):
        view = self.workflow.presentation
        if view is not self.workflow.data and self.show_rectangles:
            count = len((view.current.prediction or {}).get("trays", {}))
            return f"ON ({count})" if count else "NO FIT"
        return self.workflow.tray_status() if self.show_rectangles else "OFF"

    def _overlay(self):
        flow = self.workflow
        return overlay_masks(flow.data.current.prediction_frame, flow.data.current.prediction,
                             labels=flow.data.units.bindings if flow.data.units else None) if flow.data.current.prediction is not None else None

    def _toggle_play(self):
        flow = self.workflow
        if self.rules.input_mode is not None:
            self.rules.note = "Finish the rule input first, or press F / G again to cancel it."
            self.dirty = True
            return
        if flow.stage is Stage.PLAYBACK and flow.display_snapshot is not None:
            self._clear_query()
            return
        if flow.stage is not Stage.PLAYBACK:
            self.rules.reset()
        flow.toggle_play(self._overlay() if not flow.registration_locked else None)
        if flow.stage is Stage.PLAYBACK:
            self.drag_type = self.drag_position = None

    def _clear_query(self):
        self.rules.reset()
        self.workflow.resume_live()
        self.dirty = True

    def _unit_action(self, action, unit_id=None):
        try:
            if action in ("load", "import_A", "import_B", "calibration"):
                kind = "calibration" if action == "calibration" else "B" if action == "import_B" else "A"
                self._load_catalog_dialog(kind)
            else:
                if action == "mode":
                    self.rules.reset()
                self.workflow.unit_action(action, unit_id)
                if action in ("bind", "unbind", "select", "undo"):
                    self.rules.invalidate()
        except (ImportError, OSError, ValueError, RuntimeError) as error:
            self.workflow.note = str(error)
        self.dirty = True

    def _load_catalog_dialog(self, kind):
        flow = self.workflow
        allowed = flow.can_edit_points() if kind == "calibration" else flow.can_import_list()
        if not allowed:
            return
        flow.pause()
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            title = "Load tray calibration (mm)" if kind == "calibration" else f"Import list {kind}"
            filetypes = [("JSON", "*.json")] if kind == "calibration" else [("Army list PDF", "*.pdf"), ("Type catalog JSON", "*.json")]
            path = filedialog.askopenfilename(parent=root, title=title, filetypes=filetypes,
                                              initialdir=str(Path(__file__).resolve().parents[1] / "inputs/army_lists"))
            if path:
                if kind == "calibration":
                    flow.load_calibration(path)
                    self.rules.invalidate()
                elif flow.import_unit_list(path, kind):
                    self.unit_panel.offset[kind] = 0
                    self.rules.reset()
                    self.drag_type = self.drag_position = None
        finally:
            root.destroy()

    def _draw_layer_controls(self, panel, y):
        button_width = min(165, (self.preview_size[0] - 30) // 2)
        self.layer_buttons = []
        for x, name, key, enabled, status in (
            (10, "MASK", "m", self.show_masks, "ON" if self.show_masks else "OFF"),
            (20 + button_width, "TRAY", "t", self.show_rectangles, self._tray_caption()),
        ):
            rect = (x, y, x + button_width, y + 28)
            color = (90, 65, 40) if enabled else (55, 55, 55)
            if name == "TRAY" and enabled and not status.startswith("ON"):
                color = (45, 85, 120)
            cv2.rectangle(panel, rect[:2], rect[2:], color, -1)
            draw_text(panel, f"{name} [{key.upper()}]: {status}", (x + 8, y + 20), size=13)
            self.layer_buttons.append((rect, key))

    def _render(self):
        flow = self.workflow
        if flow.stage in (Stage.TABLE, Stage.RECALIBRATE):
            panel = self.table_setup.render(self.preview_size)
            if flow.load_progress is not None:
                self._draw_loading_progress(panel)
            elif flow.stage is Stage.TABLE:
                status = flow.note if flow.model_failed else (
                    "Weights ready. Confirm the table setup to continue." if flow.worker.predictor.model is not None
                    else "Loading SAM3...")
                draw_text(panel, status[:max(28, self.preview_size[0] // 8)],
                          (16, panel.shape[0] - 35), size=14)
            if flow.stage is Stage.RECALIBRATE:
                panel = cv2.copyMakeBorder(panel, 0, 48, 0, 0, cv2.BORDER_CONSTANT, value=(31, 29, 27))
                y = panel.shape[0] - 40
                rect = (10, y, 195, y + 30)
                cv2.rectangle(panel, rect[:2], rect[2:], (65, 61, 56), -1)
                draw_text(panel, "Cancel / Return [Esc]", (18, y + 21), size=13)
                self.recalibration_cancel_button = rect
                draw_text(panel, flow.note[:max(12, (panel.shape[1] - 220) // 7)], (210, y + 21), size=12)
            return panel
        view = flow.presentation
        preview = self.layers.render(view.current.frame, show_masks=self.show_masks, show_rectangles=self.show_rectangles)
        self.rules.draw(preview, flow)
        if flow.load_progress is not None:
            self._draw_loading_progress(preview)
        if flow.stage is Stage.PLAYBACK:
            width, height = self.preview_size
            tracked = (flow.data.current.prediction or {}).get("object_ids", [])
            missing = [unit for obj, unit in flow.data.units.bindings.items() if obj not in tracked]
            show_status = flow.model_failed or flow.pending_play or bool(missing)
            panel = np.full((height + (272 if show_status else 232), width, 3), 30, dtype=np.uint8)
            panel[:height] = preview
            self._draw_layer_controls(panel, height + 8)
            self.view_buttons = []
            labels = (("view", "Return live [Space]" if flow.display_snapshot is not None else "Hold view [Space]"),
                      ("clear", "Clear query [Q]"), ("recalibrate", "Recalibrate [K]"))
            for i, (action, label) in enumerate(labels):
                button_width = min(190, (width - 40) // 3)
                x, y = 10 + i * (button_width + 10), height + 42
                rect = (x, y, x + button_width, y + 28)
                cv2.rectangle(panel, rect[:2], rect[2:], (65, 65, 65), -1)
                draw_text(panel, label, (x + 6, y + 20), size=max(10, min(13, button_width // 14)))
                self.view_buttons.append((rect, action))
            state = "HELD" if flow.display_snapshot is not None else "LIVE"
            stamp = (view.current.prediction_metadata or {}).get("timestamp_seconds")
            observed = "none" if stamp is None else f"{stamp:.2f}s"
            draw_text(panel, f"{flow.worker.tracker_name} | View {state} | live {flow.source.frame_index / flow.source.fps:.2f}s | masks {observed} | calibration v{flow.data.board.calibration_version}",
                      (10, height + 84), size=12)
            self.rules.controls(panel, self.preview_size, height + 92, flow)
            if show_status:
                status = (flow.note if flow.model_failed or flow.pending_play else
                          "No tracking masks: " + ", ".join(missing) + ". Unit identities retained.")
                limit = max(24, width // 7)
                for row in range(2):
                    draw_text(panel, status[row * limit:(row + 1) * limit], (10, height + 238 + row * 18),
                              (100, 170, 245) if flow.model_failed else (220, 220, 220), size=12)
            return panel
        height, width = flow.data.current.frame.shape[:2]
        for click in flow.clicks:
            if click["object_id"] == flow.active_id and click["video_frame"] == flow.source.frame_index:
                x, y = click["point"]
                point = (round(x * self.preview_size[0] / width), round(y * self.preview_size[1] / height))
                cv2.drawMarker(preview, point, (0, 255, 0) if click["positive"] else (0, 0, 255),
                               cv2.MARKER_CROSS if click["positive"] else cv2.MARKER_TILTED_CROSS, 12, 2)
        if flow.playing and flow.source.frame_index != self.last_rendered_frame:
            self.render_times.append(perf_counter())
        self.last_rendered_frame = flow.source.frame_index
        fps = ((len(self.render_times) - 1) / (self.render_times[-1] - self.render_times[0])
               if len(self.render_times) > 1 and self.render_times[-1] > self.render_times[0] else 0)
        lag = ("none" if flow.data.current.prediction_metadata is None else
               f"{max(0, flow.source.frame_index - flow.data.current.prediction_metadata['frame_index']) / flow.source.fps:.2f}s")
        panel_height = max(500, self.preview_size[1] + 290)
        panel = np.full((panel_height, self.preview_size[0] + self.unit_panel.WIDTH, 3), 30, dtype=np.uint8)
        panel[:self.preview_size[1], :self.preview_size[0]] = preview
        known_ids = flow.known_ids()
        key = (panel_height, id(flow.data.units), tuple(flow.data.units.bindings.items()) if flow.data.units else (),
               tuple(flow.data.units.counters.items()) if flow.data.units else (),
               flow.selected_type, flow.active_id, tuple(known_ids), tuple(self.unit_panel.offset.items()), flow.registration_locked, flow.interaction_mode)
        if key != self._panel_key:
            self._panel_image = self.unit_panel.render(panel_height, flow.data.units, flow.selected_type,
                                                       flow.active_id, known_ids, locked=flow.registration_locked, mode=flow.interaction_mode)
            self._panel_key = key
        panel[:, self.preview_size[0]:] = self._panel_image
        y = self.preview_size[1]
        play_label = "Play / Pause" if flow.registration_locked else "Finish + play"
        for x, label in ((10, play_label), (190, "New object (N)")):
            cv2.rectangle(panel, (x, y + 8), (x + 165, y + 39), (80, 80, 80), -1)
            cv2.putText(panel, label, (x + 8, y + 29), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        self._draw_layer_controls(panel, y + 48)
        model_status = "ready" if flow.startup_ready else ("preparing" if flow.worker.predictor.model is not None else "loading")
        if flow.model_failed:
            model_status = "error"
        clock = (f"Clip {flow.source.frame_index/flow.source.fps:.2f}s | model {model_status} | display {fps:.1f}/{flow.source.fps:g} fps"
                 f" | SAM max {flow.inference_fps:g} Hz | mask age {lag} | object {flow.active_id}")
        cv2.putText(panel, clock, (10, y + 96), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (230, 230, 230), 1)
        limit = max(20, self.preview_size[0] // 8)
        for row, text in enumerate((flow.note[:limit], flow.note[limit:limit * 2])):
            cv2.putText(panel, text, (10, y + 118 + row * 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 230, 230), 1)
        self.rules.controls(panel, self.preview_size, y + 158, flow)
        if self.drag_type is not None and self.drag_position is not None:
            x, y = self.drag_position
            cv2.rectangle(panel, (x + 8, y + 8), (x + 155, y + 38), (90, 65, 40), -1)
            draw_text(panel, self.drag_type, (x + 15, y + 30), size=16)
        return panel

    def _draw_loading_progress(self, canvas):
        flow = self.workflow
        stage, completed, total = flow.load_progress
        height, width = canvas.shape[:2]
        left, right = 16, width - 16
        top, bottom = max(0, height - 76), height - 12
        cv2.rectangle(canvas, (left - 6, top), (right + 6, bottom), (25, 25, 25), -1)
        bar_top, bar_bottom = bottom - 18, bottom - 7
        cv2.rectangle(canvas, (left, bar_top), (right, bar_bottom), (65, 65, 65), -1)
        if total is not None and total > 0 and completed is not None:
            ratio = min(1.0, max(0.0, completed / total))
            label = f"{stage}: {ratio:.0%} ({completed}/{total})"
            end = left + round((right - left) * ratio)
            if end > left:
                cv2.rectangle(canvas, (left, bar_top), (end, bar_bottom), (210, 160, 80), -1)
        else:
            label = stage + "..."
            span = max(1, (right - left) // 4)
            start = left + int((perf_counter() % 1.5) / 1.5 * (right - left - span))
            cv2.rectangle(canvas, (start, bar_top), (start + span, bar_bottom), (210, 160, 80), -1)
        draw_text(canvas, label, (left + 2, top + 22), size=14)

    def _mask_at(self, x, y):
        view = self.workflow.presentation
        width, height = self.preview_size
        if view.current.prediction is None or not (0 <= x < width and 0 <= y < height):
            return None
        source_height, source_width = view.current.frame.shape[:2]
        px, py = min(source_width - 1, int(x * source_width / width)), min(source_height - 1, int(y * source_height / height))
        # The last mask is drawn on top when masks overlap.
        for object_id, mask in reversed(list(zip(view.current.prediction["object_ids"], view.current.prediction["masks"]))):
            if mask[py, px]:
                return object_id
        return None

    def on_mouse(self, event, x, y, flags, _):
        flow = self.workflow
        if flow.closed:
            return
        if flow.stage in (Stage.TABLE, Stage.RECALIBRATE):
            if flow.stage is Stage.RECALIBRATE:
                rect = self.recalibration_cancel_button
                if event == cv2.EVENT_LBUTTONDOWN and rect and rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                    self._cancel_recalibration()
                    return
                if flow.recalibration["draft"] is not None:
                    return
            self.table_setup.on_mouse(event, x, y, self.preview_size)
            self._activate_table_view()
            self.dirty = True
            return
        if event == cv2.EVENT_LBUTTONDOWN:
            for rect, key in self.layer_buttons:
                if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                    self.on_key(ord(key))
                    return
            for rect, action in self.rules.buttons:
                if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                    self._rule_action(action)
                    return
            for rect, action in self.view_buttons:
                if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                    if action == "recalibrate":
                        self._begin_recalibration()
                    elif action == "clear":
                        self._clear_query()
                    else:
                        self._toggle_play()
                    return
        width, height = self.preview_size
        if 0 <= x < width and 0 <= y < height:
            if self.rules.input_mode is not None:
                try:
                    if event == cv2.EVENT_RBUTTONDOWN and self.rules.input_mode == "terrain":
                        self._rule_action("undo_terrain")
                    elif event == cv2.EVENT_LBUTTONDOWN:
                        image_size = np.asarray(flow.data.current.frame.shape[1::-1])
                        self.rules.click_input(np.asarray([x, y]) * image_size / self.preview_size,
                                               flow, np.asarray(self.preview_size) / image_size)
                except (ValueError, cv2.error) as error:
                    self.rules.note = str(error)
                self.dirty = True
                return
            if self.rules.mode is not None:
                if event == cv2.EVENT_LBUTTONDOWN:
                    object_id = self._mask_at(x, y)
                    if object_id is not None:
                        self.rules.select(object_id)
                        flow.pause()
                        self.dirty = True
                return
        if flow.stage is Stage.PLAYBACK:
            return
        if self.drag_type is not None:
            if event == cv2.EVENT_MOUSEMOVE:
                self.drag_position = (x, y)
                self.dirty = True
            elif event == cv2.EVENT_LBUTTONUP:
                type_id = self.drag_type
                self.drag_type = self.drag_position = None
                object_id = self._mask_at(x, y)
                if object_id is not None:
                    flow.select_mask(object_id)
                    self._unit_action("select", type_id)
                elif self.unit_panel.hit(x - self.preview_size[0], y) == ("select", type_id):
                    self._unit_action("select", type_id)
                else:
                    flow.note = "Drop the type onto a segmented mask. Binding unchanged."
                self.dirty = True
            return
        if x >= self.preview_size[0]:
            if event == cv2.EVENT_MOUSEWHEEL:
                self.unit_panel.scroll(x - self.preview_size[0], -3 if (flags >> 16) > 0 else 3)
                self.dirty = True
            elif event == cv2.EVENT_LBUTTONDOWN:
                action, type_id = self.unit_panel.hit(x - self.preview_size[0], y)
                if action == "select" and flow.can_edit_points():
                    self.rules.reset()
                    self.drag_type, self.drag_position = type_id, (x, y)
                    self.dirty = True
                else:
                    self._unit_action(action, type_id)
            return
        if event not in (cv2.EVENT_LBUTTONDOWN, cv2.EVENT_RBUTTONDOWN):
            return
        preview_width, preview_height = self.preview_size
        if 0 <= x < preview_width and 0 <= y < preview_height:
            if flow.interaction_mode == "label":
                object_id = self._mask_at(x, y)
                if object_id is not None:
                    flow.select_mask(object_id)
                else:
                    flow.note = "No mask here. Tab switches back to segment mode."
                    self.dirty = True
                return
            height, width = flow.data.current.frame.shape[:2]
            flow.click(x * width / preview_width, y * height / preview_height,
                       positive=event == cv2.EVENT_LBUTTONDOWN)
        elif event == cv2.EVENT_LBUTTONDOWN and preview_height + 8 <= y <= preview_height + 39:
            if 10 <= x <= 175:
                self._toggle_play()
            elif 190 <= x <= 355:
                self.rules.reset()
                flow.new_object()

    def on_key(self, key):
        flow = self.workflow
        if flow.closed:
            return
        if flow.stage in (Stage.TABLE, Stage.RECALIBRATE):
            if key == 27:
                self._cancel_recalibration() if flow.stage is Stage.RECALIBRATE else self.close()
            elif flow.stage is Stage.RECALIBRATE and flow.recalibration["draft"] is not None:
                return
            else:
                self.table_setup.on_key(key)
                self._activate_table_view()
            self.dirty = True
            return
        if key == ord("k") and flow.stage is Stage.PLAYBACK:
            self._begin_recalibration()
            return
        if self.rules.input_mode == "terrain" and key in (26, ord("u"), ord("z")):
            self._rule_action("undo_terrain")
            return
        if self.rules.input_mode == "front" and key in (26, ord("u"), ord("z")):
            self.rules.input_mode = None
            self.rules.note = "Front input cancelled; SAM point prompts are unchanged."
            self.dirty = True
            return
        rule_keys = {ord("d"): "distance", ord("l"): "los", ord("v"): "move", ord("j"): "double",
                     ord("f"): "front", ord("e"): "profile", ord("g"): "terrain"}
        if key in rule_keys:
            self._rule_action(rule_keys[key])
            return
        if key == ord("q"):
            self._clear_query()
            return
        if flow.stage is Stage.PLAYBACK and key not in (ord("m"), ord("t"), 32, ord("r"), 27):
            return
        if key == 9:
            self.rules.reset()
            self._unit_action("mode")
        elif key in (ord("m"), ord("t")):
            attribute = "show_masks" if key == ord("m") else "show_rectangles"
            setattr(self, attribute, not getattr(self, attribute))
        elif key == 32:
            self._toggle_play()
        elif key == ord("n"):
            self.rules.reset()
            flow.new_object()
        elif key in (26, ord("u"), ord("z")):
            flow.undo_point()
        elif ord("1") <= key <= ord("9"):
            flow.select_mask(key - ord("0"))
        elif key == ord("b"):
            self._unit_action("bind")
        elif key == ord("o"):
            self._unit_action("import_A")
        elif key == ord("p"):
            self._unit_action("import_B")
        elif key == ord("c"):
            self._unit_action("calibration")
        elif key in (8, 127):
            self._unit_action("unbind")
        elif key in (ord("["), ord("]")):
            flow.cycle_mask(-1 if key == ord("[") else 1)
        elif key == ord("r"):
            self.rules.reset()
            self.drag_type = self.drag_position = None
            self.layer_buttons = []
            self.view_buttons = []
            self.render_times.clear()
            flow.reset()
        elif key == ord("s"):
            try:
                flow.finish_registration(self._overlay())
            except (OSError, ValueError, cv2.error) as error:
                flow.note = str(error)
        elif key == 27:
            self.close()
        self.dirty = True

    def advance(self):
        self.workflow.advance()
        if self.table_setup.poll():
            self.dirty = True
        self._activate_table_view()
        if self.rules.tick(self.workflow):
            self.dirty = True

    def _rule_action(self, action):
        try:
            self.rules.action(action, self.workflow)
        except (ValueError, cv2.error) as error:
            self.rules.note = str(error)
        self.dirty = True

    def close(self):
        self.workflow.close()
        self.table_setup.close()
        self.rules.close()

    def show(self):
        flow = self.workflow
        cv2.namedWindow(self.WINDOW, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(self.WINDOW, self.on_mouse)
        try:
            while not flow.closed:
                self.advance()
                if self.dirty or flow.dirty:
                    cv2.imshow(self.WINDOW, self.render())
                delay = 15
                if flow.playing:
                    next_time = flow.play_start + (flow.source.frame_index + 1 - flow.play_start_frame) / flow.source.fps
                    delay = max(1, min(15, int((next_time - perf_counter()) * 1000)))
                key = cv2.waitKey(delay)
                if key >= 0:
                    self.on_key(key & 0xff)
                if cv2.getWindowProperty(self.WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    break
        finally:
            self.close()
            cv2.destroyWindow(self.WINDOW)
