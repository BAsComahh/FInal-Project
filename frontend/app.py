"""Assemble workflow controllers and coordinate stage/input/resource boundaries."""
from enum import Enum
import cv2
import numpy as np
from application.app import MatchApplication
from .registration.view import RegistrationView
from .presentation import RegistrationSelection, GeometrySelection
from .calibration.view import CalibrationView
from .live.view import LiveView
from .replay.view import ReplayView
from .recovery.view import RecoveryView
from .geometry_tools.view import GeometryView
from .scene_editing.controller import SceneEditor
from .scene_editing.view import SceneEditingView
from .shared.layers import PresentationLayers, overlay_masks
from .shared.viewport import Viewport
from .shared.drawing import draw_text

class Stage(Enum):
    TABLE = "table"
    REGISTER = "register"
    PLAYBACK = "playback"
    RECALIBRATE = "recalibrate"

class VideoApplication:
    def __init__(self, video, *, preview_width=960, units=None, calibration=None, board_size_in=None, **options):
        self.viewport = Viewport(preview_width)
        self.match = MatchApplication(video, units=units, calibration=calibration, board_size_in=board_size_in, **options)
        self.registration = RegistrationSelection(self.match)
        self.recovery = self.match.recovery
        self.replay = self.match.replay
        self.replay_view = ReplayView(self.replay)
        self.calibration = self.match.calibration
        self.geometry = GeometrySelection(self.match)
        self.editor = SceneEditor(self.match, self.geometry)
        self.scene_view = SceneEditingView(self.editor)
        self.geometry_view = GeometryView(self.geometry, self.match.geometry, self.editor, self.scene_view)
        self.display = PresentationLayers()
        self.recovery_view = RecoveryView(self.recovery, self.match, self.display)
        self.registration_view = RegistrationView(self.registration, self.match, self.geometry_view, self.display, self.viewport)
        self.live_view = LiveView(self.match, self.geometry_view, self.display)
        self.table_setup = CalibrationView(self.state.current.frame, board_size_in=np.asarray(self.state.board.board_size_mm) / 25.4)
        self.dirty = True
        self.match.tick()

    @property
    def state(self):
        return self.match.snapshot()

    @property
    def stage(self):
        return Stage(self.state.stage)

    @property
    def preview_size(self):
        frame = self.table_setup.frame if self.stage is Stage.RECALIBRATE else self.state.current.frame
        return self.viewport.size(frame)

    def _reset_tools(self):
        self.recovery.cancel()
        self.geometry.clear()
        self.editor.clear()

    def render(self):
        if self.replay.active:
            image = self.replay_view.render(self.preview_size)
        elif self.stage in (Stage.TABLE, Stage.RECALIBRATE):
            image = self.table_setup.render_status(self.preview_size, self.state, self.calibration.status)
        elif self.stage is Stage.PLAYBACK:
            if self.recovery.active:
                self.match.present(self.state.source_ref)
                image = self.recovery_view.render(self.preview_size)
            else:
                image = self.live_view.render(self.preview_size)
        else:
            image = self.registration_view.render(self.preview_size)
        if self.state.history_warning:
            width = image.shape[1]
            banner = np.full((48, width, 3), (35, 35, 100), dtype=np.uint8)
            limit = max(20, width // 7)
            warning = self.state.history_warning
            for row in range(2):
                draw_text(banner, warning[row * limit:(row + 1) * limit], (10, 18 + row * 20), size=12)
            image = np.vstack((image, banner))
        self.dirty = False
        return image

    def _activate_table_view(self):
        if not self.table_setup.confirmed or self.stage not in (Stage.TABLE, Stage.RECALIBRATE):
            return
        try:
            if self.stage is Stage.RECALIBRATE:
                boundary = self.table_setup.snapshot()
                self.table_setup.confirmed = False
                receipt = self.calibration.apply_recalibration(self.table_setup.corners, boundary,
                                                  board_size_in=self.table_setup.board_size_in)
            else:
                receipt = self.calibration.confirm_table(self.table_setup.corners, self.table_setup.snapshot(),
                                            board_size_in=self.table_setup.board_size_in)
            if receipt.status == "rejected":
                self.table_setup.confirmed = False
                self.table_setup.note = receipt.reason
        except (ValueError, cv2.error) as error:
            self.table_setup.confirmed = False
            self.table_setup.note = f"Cannot map these corners: {error}. Please correct them."
        self.dirty = True

    def _begin_recalibration(self):
        try:
            receipt = self.calibration.begin_recalibration()
            if receipt.status == "rejected":
                self.match.set_note(receipt.reason)
                return
            frame = receipt.value
        except (ValueError, OSError, cv2.error) as error:
            self.match.set_note(str(error))
        else:
            self._reset_tools()
            self.geometry.note = "Select a rule tool, then click one or two units."
            self.table_setup.close()
            self.table_setup = CalibrationView(frame, board_size_in=np.asarray(self.state.board.board_size_mm) / 25.4)
        self.dirty = True

    def _cancel_recalibration(self):
        try:
            self.calibration.cancel_recalibration()
        except ValueError as error:
            self.table_setup.note = str(error)
        self.dirty = True

    def _overlay(self):
        return overlay_masks(self.state.current.prediction_frame, self.state.current.prediction,
                             labels=self.state.units.bindings if self.state.units else None) if self.state.current.prediction is not None else None

    def _toggle_play(self):
        if self.editor.input_mode is not None and self.stage is not Stage.PLAYBACK:
            self.geometry.note = "Finish the rule input first, or press F / G again to cancel it."
            self.dirty = True
            return
        if self.stage is Stage.PLAYBACK:
            self._clear_query()
        elif self.state.source_ref.frame_index >= self.state.end_index:
            self.match.set_note("End of video interval. R restarts.")
        else:
            self._reset_tools()
            try:
                receipt = self.match.start(self._overlay())
                if receipt.status == "rejected":
                    self.match.set_note(receipt.reason)
                    self.dirty = True
                    return
            except (OSError, ValueError, cv2.error) as error:
                self.match.set_note(str(error))
                self.dirty = True
                return
            self.registration_view.drag_type = self.registration_view.drag_position = None
        self.dirty = True

    def _clear_query(self):
        self._reset_tools()
        self.dirty = True

    def _open_recovery(self, unit_id=None):
        try:
            self._reset_tools()
            self.recovery_view.drag_id = self.recovery_view.drag_position = None
            receipt = self.recovery.open(unit_id)
            if receipt.status == "rejected":
                self.match.set_note(f"Manual recovery: {receipt.reason}")
        except ValueError as error:
            self.match.set_note(f"Manual recovery: {error}")
        self.dirty = True

    def _replay_action(self, action):
        if action in ("open", "live"):
            self._reset_tools()
            self.dirty = True
            self.display.layer_buttons = []
            self.geometry_view.buttons = []
            self.live_view.view_buttons = []
            self.replay_view.buttons = []
            self.replay.open() if action == "open" else self.replay.clear()
        elif action == "refresh":
            self.replay.refresh()
        elif action in ("previous", "next"):
            self.replay.navigate(-1 if action == "previous" else 1)
        self.dirty = True

    def _unit_action(self, action, unit_id=None):
        try:
            if action in ("load", "import_A", "import_B", "calibration"):
                kind = "calibration" if action == "calibration" else "B" if action == "import_B" else "A"
                self._load_catalog_dialog(kind)
            elif action == "dimensions":
                if not self.match.registration.can_import_list():
                    return
                from .registration.dimensions import edit_type_dimensions

                dimensions = edit_type_dimensions(self.state.units)
                if dimensions is not None and self.match.registration.update_dimensions(dimensions).status == "accepted":
                    self._reset_tools()
            else:
                if action == "mode":
                    self._reset_tools()
                self.registration.unit_action(action, unit_id)
                if action in ("bind", "unbind", "select", "undo"):
                    self.geometry.invalidate()
        except (ImportError, OSError, ValueError, RuntimeError) as error:
            self.match.set_note(str(error))
        self.dirty = True

    def _load_catalog_dialog(self, kind):
        allowed = self.match.registration.can_edit_points() if kind == "calibration" else self.match.registration.can_import_list()
        if not allowed:
            return
        path = self.registration_view.choose_catalog(kind)
        if path:
            if kind == "calibration":
                receipt = self.calibration.load_calibration(path)
                if receipt.status == "rejected":
                    self.match.set_note(receipt.reason)
                self.geometry.invalidate()
            else:
                receipt = self.match.registration.import_unit_list(path, kind)
                if receipt.status == "rejected":
                    self.match.set_note(receipt.reason)
                    return
                self.registration.selected_type = next(key for key, row in self.state.units.types.items() if row.get("list_id") == kind)
                self.registration_view.unit_panel.offset[kind] = 0
                self._reset_tools()
                self.registration_view.drag_type = self.registration_view.drag_position = None

    def on_mouse(self, event, x, y, flags, _=None):
        try:
            self._on_mouse(event, x, y, flags)
        finally:
            self.match.tick()
            self.dirty = True

    def _on_mouse(self, event, x, y, flags):
        if self.state.closed:
            return
        if self.replay.active:
            if event == cv2.EVENT_LBUTTONDOWN:
                for rect, action in self.replay_view.buttons:
                    if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                        self._replay_action(action)
                        break
            return
        if self.stage in (Stage.TABLE, Stage.RECALIBRATE):
            if self.stage is Stage.RECALIBRATE:
                rect = self.table_setup.recalibration_cancel_button
                if event == cv2.EVENT_LBUTTONDOWN and rect and rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                    self._cancel_recalibration()
                    return
                if self.calibration.status["draft"] is not None or self.calibration.status["pending"] is not None:
                    return
            self.table_setup.on_mouse(event, x, y, self.preview_size)
            self._activate_table_view()
            self.dirty = True
            return
        if self.recovery.active:
            try:
                self.recovery_view.on_mouse(event, x, y, flags)
            except (ValueError, RuntimeError, cv2.error) as error:
                self.recovery.note = str(error)
            self.dirty = True
            return
        if event == cv2.EVENT_LBUTTONDOWN:
            for rect, key in self.display.layer_buttons:
                if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                    self.on_key(ord(key))
                    return
            for rect, action in self.geometry_view.buttons:
                if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                    self._rule_action(action)
                    return
            for rect, action in self.live_view.view_buttons:
                if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                    if action == "recalibrate":
                        self._begin_recalibration()
                    elif action == "clear":
                        self._clear_query()
                    elif action == "replay":
                        self._replay_action("open")
                    elif action == "recover":
                        self._open_recovery()
                    else:
                        self._toggle_play()
                    return
        width, height = self.preview_size
        if 0 <= x < width and 0 <= y < height:
            if self.editor.input_mode is not None:
                try:
                    if event == cv2.EVENT_RBUTTONDOWN and self.editor.input_mode == "terrain":
                        self._rule_action("undo_terrain")
                    elif event == cv2.EVENT_LBUTTONDOWN:
                        image_size = np.asarray(self.state.current.frame.shape[1::-1])
                        self.editor.note = self.geometry.note
                        self.editor.click_input(self.viewport.image_point((x, y), image_size, self.preview_size), np.asarray(self.preview_size) / image_size)
                        self.geometry.note = self.editor.note
                except (ValueError, cv2.error) as error:
                    self.geometry.note = str(error)
                self.dirty = True
                return
            if self.geometry.mode is not None:
                if event == cv2.EVENT_LBUTTONDOWN:
                    object_id = self.viewport.mask_at(x, y, self.state, self.preview_size)
                    if object_id is not None:
                        self.geometry.select(object_id)
                        self.dirty = True
                return
        if self.stage is Stage.PLAYBACK:
            if x >= width and event == cv2.EVENT_LBUTTONDOWN:
                uid = self.live_view.missing_panel.unit_at(x - width, y)
                if uid is not None and uid in self.live_view.missing_panel.failed_units(self.state):
                    self._open_recovery(uid)
                    return
            if x >= width and event == cv2.EVENT_MOUSEWHEEL:
                self.live_view.missing_panel.scroll(x - width, -3 if (flags >> 16) > 0 else 3)
                self.dirty = True
            return
        self.registration_view.on_mouse(event, x, y, flags, self.preview_size, self._unit_action, self._reset_tools, self._toggle_play)

    def on_key(self, key):
        try:
            self._on_key(key)
        finally:
            self.match.tick()
            self.dirty = True

    def _on_key(self, key):
        if self.state.closed:
            return
        if self.recovery.active and key in (27, ord("q"), 32):
            if not self.recovery.committing:
                self._clear_query()
            return
        if self.replay.active:
            if key == 27:
                self._replay_action("live")
            elif key in (ord("r"), ord("R")):
                self.reset()
            elif key in (0x250000, ord("a"), ord("A")):
                self._replay_action("previous")
            elif key in (0x270000, ord("d"), ord("D")):
                self._replay_action("next")
            return
        if self.stage in (Stage.TABLE, Stage.RECALIBRATE):
            if key == 27:
                self._cancel_recalibration() if self.stage is Stage.RECALIBRATE else self.close()
            elif self.stage is Stage.RECALIBRATE and (self.calibration.status["draft"] is not None or
                                                       self.calibration.status["pending"] is not None):
                return
            else:
                self.table_setup.on_key(key)
                self._activate_table_view()
            self.dirty = True
            return
        if key in (ord("k"), ord("K")) and self.stage is Stage.PLAYBACK:
            self._begin_recalibration()
            return
        if self.editor.input_mode == "terrain" and key in (26, ord("u"), ord("z")):
            self._rule_action("undo_terrain")
            return
        if self.editor.input_mode == "front" and key in (26, ord("u"), ord("z")):
            self.editor.input_mode = None
            self.geometry.note = "Front input cancelled; SAM point prompts are unchanged."
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
        if self.stage is Stage.PLAYBACK and key not in (ord("m"), ord("t"), 32, ord("r"), 27):
            return
        if key == 9:
            self._reset_tools()
            self._unit_action("mode")
        elif key in (ord("m"), ord("t")):
            if key == ord("m"):
                self.display.show_masks = not self.display.show_masks
            else:
                self.display.show_rectangles = not self.display.show_rectangles
        elif key == 32:
            self._toggle_play()
        elif key == ord("n"):
            self._reset_tools()
            self.registration.new_object()
        elif key in (26, ord("u"), ord("z")):
            self.registration.undo_point()
        elif ord("1") <= key <= ord("9"):
            self.registration.select_mask(key - ord("0"))
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
            self.registration.cycle_mask(-1 if key == ord("[") else 1)
        elif key == ord("r"):
            self.reset()
        elif key == ord("s"):
            try:
                receipt = self.match.registration.finish_registration(self._overlay())
                if receipt.status == "rejected":
                    self.match.set_note(receipt.reason)
            except (OSError, ValueError, cv2.error) as error:
                self.match.set_note(str(error))
        elif key == 27:
            self.close()
        self.dirty = True

    def advance(self):
        previous = self.state.revision
        self.match.tick()
        self.dirty |= self.state.revision != previous
        if self.editor.poll():
            self.geometry.note = self.editor.note
            self.dirty = True
        if self.replay.active:
            return
        if self.stage is Stage.RECALIBRATE:
            self.table_setup.frame = self.state.source_image
        if self.table_setup.poll():
            self.dirty = True
        self._activate_table_view()

    def _rule_action(self, action):
        self.recovery.cancel()
        try:
            if action in ("distance", "los", "double", "move"):
                self.geometry.query(action)
                self.editor.clear()
            else:
                self.editor.note = self.geometry.note
                self.editor.action(action, self.registration.active_id)
                self.geometry.note = self.editor.note
        except (ValueError, cv2.error) as error:
            self.geometry.note = str(error)
        self.dirty = True

    def reset(self):
        self.replay.clear()
        self.replay_view.buttons = []
        self._reset_tools()
        self.registration_view.drag_type = self.registration_view.drag_position = None
        self.display.layer_buttons = []
        self.live_view.view_buttons = []
        self.registration_view.render_times.clear()
        self.dirty = True
        self.match.reset()
        self.registration.reset()

    def close(self):
        self.recovery.cancel()
        self.editor.clear()
        self.dirty = True
        self.match.close()
        self.table_setup.close()

    def input_delay(self):
        return self.match.input_delay()
