"""Assemble workflow controllers and coordinate stage/input/resource boundaries."""
from enum import Enum
from pathlib import Path
from time import perf_counter
import cv2
import numpy as np
from components.game_data import GameData
from components.registration import UnitRoster
from .config import DEFAULT_UNITS
from .runtime.session import MatchSession
from .registration.controller import RegistrationController
from .registration.view import RegistrationView
from .calibration.controller import CalibrationController, configure_board
from .calibration.view import CalibrationView
from .live.controller import LiveController
from .live.view import LiveView
from .replay.controller import ReplayController
from .replay.view import ReplayView
from .geometry_tools.controller import GeometryController
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
        data = GameData()
        configure_board(data, calibration, board_size_in)
        data.units = UnitRoster.load(units if units is not None else DEFAULT_UNITS)
        if units is None or Path(units).resolve() == DEFAULT_UNITS:
            data.units = data.units.with_list("A", data.units.payload, source=str(DEFAULT_UNITS))
        self.session = MatchSession(video, data, **options)
        self.registration = RegistrationController(self.session)
        self.live = LiveController(self.session)
        self.replay = ReplayController(self.session)
        self.replay_view = ReplayView(self.replay)
        self.calibration = CalibrationController(self.session, self.live)
        self.geometry = GeometryController()
        self.editor = SceneEditor(self.session, self.live, self.geometry)
        self.scene_view = SceneEditingView(self.editor)
        self.geometry_view = GeometryView(self.geometry, self.editor, self.scene_view)
        self.display = PresentationLayers()
        self.registration_view = RegistrationView(self.registration, self.session, self.live, self.geometry_view, self.display, self.viewport)
        self.live_view = LiveView(self.session, self.live, self.geometry_view, self.display)
        self.table_setup = CalibrationView(self.session.initial_frame, board_size_in=np.asarray(data.board.board_size_mm) / 25.4)
        self.stage = Stage.TABLE
        self.dirty = True
        self.session.schedule(self.registration, self.calibration)

    @property
    def preview_size(self):
        frame = self.table_setup.frame if self.stage is Stage.RECALIBRATE else self.session.data.current.frame
        return self.viewport.size(frame)

    def _reset_tools(self):
        self.geometry.clear()
        self.editor.clear()

    def _pause(self):
        if self.stage is Stage.REGISTER:
            self.session.pause_source()

    def render(self):
        if self.replay.active:
            image = self.replay_view.render(self.preview_size)
        elif self.stage in (Stage.TABLE, Stage.RECALIBRATE):
            image = self.table_setup.render_status(self.preview_size, self.session, self.calibration.context)
        elif self.stage is Stage.PLAYBACK:
            image = self.live_view.render(self.preview_size)
        else:
            image = self.registration_view.render(self.preview_size)
        if self.session.history_warning:
            width = image.shape[1]
            banner = np.full((48, width, 3), (35, 35, 100), dtype=np.uint8)
            limit = max(20, width // 7)
            warning = self.session.history_warning
            for row in range(2):
                draw_text(banner, warning[row * limit:(row + 1) * limit], (10, 18 + row * 20), size=12)
            image = np.vstack((image, banner))
        self.dirty = self.session.dirty = False
        return image

    def _activate_table_view(self):
        if not self.table_setup.confirmed or self.stage not in (Stage.TABLE, Stage.RECALIBRATE):
            return
        try:
            if self.stage is Stage.RECALIBRATE:
                boundary = self.table_setup.snapshot()
                self.table_setup.confirmed = False
                self.calibration.apply_recalibration(self.table_setup.corners, boundary,
                                                  board_size_in=self.table_setup.board_size_in)
            else:
                self.calibration.confirm_table(self.table_setup.corners, self.table_setup.snapshot(),
                                            board_size_in=self.table_setup.board_size_in)
                self.stage = Stage.REGISTER
        except (ValueError, cv2.error) as error:
            self.table_setup.confirmed = False
            self.table_setup.note = f"Cannot map these corners: {error}. Please correct them."
        self.dirty = True

    def _begin_recalibration(self):
        try:
            frame = self.calibration.begin_recalibration()
        except (ValueError, OSError, cv2.error) as error:
            self.session.note = str(error)
        else:
            self.stage = Stage.RECALIBRATE
            self._reset_tools()
            self.geometry.note = "Select a rule tool, then click one or two units."
            self.table_setup.close()
            self.table_setup = CalibrationView(frame, board_size_in=np.asarray(self.session.data.board.board_size_mm) / 25.4)
        self.dirty = True

    def _cancel_recalibration(self):
        try:
            self.calibration.cancel_recalibration()
            self.stage = Stage.PLAYBACK
        except ValueError as error:
            self.table_setup.note = str(error)
        self.dirty = True

    def _overlay(self):
        return overlay_masks(self.session.data.current.prediction_frame, self.session.data.current.prediction,
                             labels=self.session.data.units.bindings if self.session.data.units else None) if self.session.data.current.prediction is not None else None

    def _toggle_play(self):
        if self.editor.input_mode is not None and self.stage is not Stage.PLAYBACK:
            self.geometry.note = "Finish the rule input first, or press F / G again to cancel it."
            self.dirty = True
            return
        if self.stage is Stage.PLAYBACK:
            self._clear_query()
        elif self.session.source.frame_index >= self.session.end_index:
            self.session.note = "End of video interval. R restarts."
        else:
            self._reset_tools()
            if not self.registration.registration_locked:
                try:
                    self.registration.finish_registration(self._overlay())
                except (OSError, ValueError, cv2.error) as error:
                    self.session.note = str(error)
                    self.dirty = True
                    return
            self.stage = Stage.PLAYBACK
            if not self.session.worker.tracker_initialized:
                self.session.pending_play = True
                self.session.note = f"Initializing {self.session.worker.tracker_name} from registered masks before starting the video."
                self.session.schedule(self.registration, self.calibration)
            else:
                self.session.start_stream()
            self.session.mark_changed()
            self.registration_view.drag_type = self.registration_view.drag_position = None
        self.session.dirty = True

    def _clear_query(self):
        self._reset_tools()
        self.live.return_live()
        self.dirty = True

    def _replay_action(self, action):
        if action in ("open", "live"):
            self._reset_tools()
            self.live.return_live()
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
                if not self.registration.can_import_list():
                    return
                from .registration.dimensions import edit_type_dimensions

                dimensions = edit_type_dimensions(self.session.data.units)
                if dimensions is not None and self.registration.update_dimensions(dimensions):
                    self._reset_tools()
            else:
                if action == "mode":
                    self._reset_tools()
                self.registration.unit_action(action, unit_id)
                if action in ("bind", "unbind", "select", "undo"):
                    self.geometry.invalidate()
        except (ImportError, OSError, ValueError, RuntimeError) as error:
            self.session.note = str(error)
        self.dirty = True

    def _load_catalog_dialog(self, kind):
        allowed = self.registration.can_edit_points() if kind == "calibration" else self.registration.can_import_list()
        if not allowed:
            return
        self._pause()
        path = self.registration_view.choose_catalog(kind)
        if path:
            if kind == "calibration":
                self.calibration.load_calibration(path)
                self.geometry.invalidate()
            elif self.registration.import_unit_list(path, kind):
                self.registration_view.unit_panel.offset[kind] = 0
                self._reset_tools()
                self.registration_view.drag_type = self.registration_view.drag_position = None

    def on_mouse(self, event, x, y, flags, _=None):
        try:
            self._on_mouse(event, x, y, flags)
        finally:
            self.session.schedule(self.registration, self.calibration)

    def _on_mouse(self, event, x, y, flags):
        if self.session.closed:
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
                if self.calibration.context["draft"] is not None or self.calibration.context["pending"] is not None:
                    return
            self.table_setup.on_mouse(event, x, y, self.preview_size)
            self._activate_table_view()
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
                        image_size = np.asarray(self.session.data.current.frame.shape[1::-1])
                        self.editor.note = self.geometry.note
                        self.editor.click_input(self.viewport.image_point((x, y), image_size, self.preview_size), np.asarray(self.preview_size) / image_size)
                        self.geometry.note = self.editor.note
                except (ValueError, cv2.error) as error:
                    self.geometry.note = str(error)
                self.dirty = True
                return
            if self.geometry.mode is not None:
                if event == cv2.EVENT_LBUTTONDOWN:
                    object_id = self.viewport.mask_at(x, y, self.live.presentation, self.preview_size)
                    if object_id is not None:
                        self.geometry.select(object_id)
                        self._pause()
                        self.dirty = True
                return
        if self.stage is Stage.PLAYBACK:
            if x >= width and event == cv2.EVENT_MOUSEWHEEL:
                self.live_view.missing_panel.scroll(x - width, -3 if (flags >> 16) > 0 else 3)
                self.dirty = True
            return
        self.registration_view.on_mouse(event, x, y, flags, self.preview_size, self._unit_action, self._reset_tools, self._toggle_play)

    def on_key(self, key):
        try:
            self._on_key(key)
        finally:
            self.session.schedule(self.registration, self.calibration)

    def _on_key(self, key):
        if self.session.closed:
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
            elif self.stage is Stage.RECALIBRATE and (self.calibration.context["draft"] is not None or
                                                       self.calibration.context["pending"] is not None):
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
                self.registration.finish_registration(self._overlay())
            except (OSError, ValueError, cv2.error) as error:
                self.session.note = str(error)
        elif key == 27:
            self.close()
        self.dirty = True

    def advance(self):
        self.session.advance(self.registration, self.calibration)
        if self.editor.poll():
            self.geometry.note = self.editor.note
            self.dirty = True
        if self.replay.poll():
            self.dirty = True
        if self.replay.active:
            return
        if self.stage is Stage.RECALIBRATE and self.calibration.context is None:
            self.stage = Stage.PLAYBACK
        if self.stage is Stage.RECALIBRATE:
            self.table_setup.frame = self.session.source.frame
        if self.table_setup.poll():
            self.dirty = True
        self._activate_table_view()
        if self.geometry.tick(self.live.presentation, self.session):
            self.dirty = True

    def _rule_action(self, action):
        try:
            if action in ("distance", "los", "double", "move"):
                self.geometry.query(action)
                if self.geometry.mode is not None:
                    self._pause()
                else:
                    self.live.return_live()
                self.editor.clear()
            else:
                self.editor.note = self.geometry.note
                self.editor.action(action, self.registration.active_id, self._pause)
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
        self.live.return_live()
        self.calibration.context = None
        self.stage = Stage.REGISTER
        self.session.reset()
        self.registration.reset()
        self.session.configure_trays()
        self.session.schedule(self.registration, self.calibration)

    def close(self):
        self.replay.close()
        self.editor.clear()
        self.live.return_live()
        self.session.close()
        self.table_setup.close()
        self.geometry.close()

    def input_delay(self):
        if self.session.playing:
            next_time = self.session.play_start + (self.session.source.frame_index + 1 - self.session.play_start_frame) / self.session.source.fps
            return max(1, min(15, int((next_time - perf_counter()) * 1000)))
        return 15
