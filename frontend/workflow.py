"""Application workflow: registration drafts, rectification and video tasks."""

from collections import deque
from copy import deepcopy
from enum import Enum
import json
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from components.homography import warp_table
from components.video_io import VideoSource
from components.registration import UnitRoster, extract_references, save_registration, read_unit_list_pdf
from components.game_data import GameData
from components.recalibration import prepare_recalibration
from .task_worker import TaskWorker


DEFAULT_UNITS = Path(__file__).resolve().parents[1] / "inputs/units.video_estimate.json"
DEFAULT_BOARD_SIZE_IN = (72, 48)


class Stage(Enum):
    TABLE = "table"
    REGISTER = "register"
    PLAYBACK = "playback"
    RECALIBRATE = "recalibrate"


def _read_tray_calibration(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Calibration must be a homography JSON object")
    matrix = np.asarray(data.get("image_to_board"), dtype=float)
    board_size = np.asarray(data.get("board_size"), dtype=float)
    if (matrix.shape != (3, 3) or not np.isfinite(matrix).all()
            or np.linalg.matrix_rank(matrix) != 3 or board_size.shape != (2,)
            or not np.isfinite(board_size).all() or np.any(board_size <= 0)):
        raise ValueError("Tray calibration needs image_to_board and positive board_size, both using mm")
    return matrix, tuple(board_size)


class RegistrationWorkflow:
    def __init__(self, video, *, model_id="facebook/sam3", device=None, start=0, seconds=10,
                 inference_fps=2, stride=None, output_dir=None, units=None, calibration=None, board_size_in=None,
                 profile=False, tray_search="full", tracker="sam3", tracker_model=None, tracker_cache=None):
        if seconds <= 0 or not np.isfinite(seconds):
            raise ValueError("seconds must be positive")
        if inference_fps <= 0 or not np.isfinite(inference_fps):
            raise ValueError("inference-fps must be positive")
        if stride is not None and stride < 1:
            raise ValueError("stride must be positive")
        if calibration is not None and board_size_in is not None:
            raise ValueError("Use either --calibration or --board-size-in, not both.")
        self.data = GameData()
        if calibration is not None:
            self.data.board.source_to_plane, self.data.board.board_size_mm = _read_tray_calibration(calibration)
        else:
            size = np.asarray(board_size_in if board_size_in is not None else DEFAULT_BOARD_SIZE_IN, dtype=float)
            if size.shape != (2,) or not np.isfinite(size).all() or np.any(size <= 0):
                raise ValueError("Board width and depth must be positive inch dimensions.")
            self.data.board.board_size_mm = tuple(size * 25.4)
        self.data.board.image_to_plane = self.data.board.source_to_plane
        self.data.units = UnitRoster.load(units if units is not None else DEFAULT_UNITS)
        if units is None or Path(units).resolve() == DEFAULT_UNITS:
            self.data.units = self.data.units.with_list("A", self.data.units.payload, source=str(DEFAULT_UNITS))
        self.selected_type = next(iter(self.data.units.types)) if self.data.units else None
        self.worker = TaskWorker(model_id, device, profile=profile, tray_search=tray_search,
                                 tracker=tracker, tracker_model=tracker_model, tracker_cache=tracker_cache)
        self.worker.submit("load", generation=0)
        self.source = None
        try:
            self.source = VideoSource(video)
            self.data.current.frame = self.source.read_at(start)
        except Exception:
            if self.source is not None:
                self.source.close()
            self.worker.close()
            raise
        self.initial_frame = self.data.current.frame
        self.registration_start_frame = self.source.frame_index
        self.data.board.source_size = self.data.current.frame.shape[1::-1]
        self.stage = Stage.TABLE
        self.start = start
        self.end_index = min(self.source.frame_count - 1, int((start + seconds) * self.source.fps) - 1)
        self.inference_fps = self.source.fps / stride if stride is not None else inference_fps
        self.output_dir = (Path(output_dir) if output_dir is not None else
                           Path(__file__).resolve().parents[1] / "outputs/sam3_registration")
        self.load_progress = None
        self.pending_trays = False
        self.interaction_mode = "segment"
        self.active_id = 1
        self.clicks = []
        self.pending_clicks = deque()
        self.next_click_id = 0
        self.pending_update = None
        self.updating_points = False
        self.generation = 0
        self.needs_reset = False
        self.needs_load = False
        self.needs_prepare = True
        self.startup_ready = False
        self.model_failed = self.closed = self.playing = False
        self.display_snapshot = None
        self.pending_play = False
        self.recalibration = None
        self.next_inference_time = 0.0
        self.last_submitted_frame = -1
        self.dirty = True
        self._configure_trays()
        self.note = "Loading SAM3 and preparing the first frame. Confirm the table boundary first."
        self._schedule(perf_counter())

    @property
    def registration_locked(self):
        return self.data.reference_folder is not None

    def known_ids(self):
        ids = {click["object_id"] for click in self.clicks}
        if self.data.current.prediction is not None:
            ids.update(self.data.current.prediction["object_ids"])
        return sorted(ids)

    def confirm_table(self, corners, boundary, *, board_size_in=None):
        if self.stage is not Stage.TABLE:
            return
        size_mm = np.asarray(self.data.board.board_size_mm, dtype=float)
        if board_size_in is not None:
            size_mm = np.asarray(board_size_in, dtype=float) * 25.4
        if size_mm.shape != (2,) or not np.isfinite(size_mm).all() or np.any(size_mm <= 0):
            raise ValueError("Board length and width must be positive inch dimensions.")
        result = warp_table(self.initial_frame, corners, board_size=size_mm)
        if self.data.board.source_to_plane is not None:
            scale = np.diag([*(size_mm / self.data.board.board_size_mm), 1.0])
            self.data.board.source_to_plane = scale @ self.data.board.source_to_plane
        else:
            self.data.board.source_to_plane = result["image_to_board"]
        self.data.board.board_size_mm = tuple(size_mm)
        self.data.board.homography = {key: value for key, value in result.items() if key != "image"}
        self.data.current.frame = result["image"]
        self.data.board.table_boundary = deepcopy(boundary)
        self.data.board.calibration_version += 1
        self.stage = Stage.REGISTER
        if self.data.board.source_to_plane is not None:
            self.data.board.image_to_plane = self.data.board.source_to_plane @ self.data.board.homography["inverse_matrix"]
        self.data.record_calibration(self._frame_metadata())
        self._configure_trays()
        self._prediction_changed()
        self.note = "Table focused. Preparing SAM3 features for the rectified first frame."

    def _warp_frame(self, frame):
        if self.data.board.homography is None:
            return frame
        return cv2.warpPerspective(frame, self.data.board.homography["matrix"], self.data.board.homography["output_size"])

    def _frame_metadata(self, *, board=None, frame=None):
        board = self.data.board if board is None else board
        frame = self.data.current.frame if frame is None else frame
        metadata = self.source.metadata()
        if board.homography is not None:
            metadata.update(
                coordinate_space="rectified_table_pixels", image_size=list(frame.shape[1::-1]),
                source_image_size=list(board.source_size), calibration_version=board.calibration_version,
                homography={key: value.tolist() if isinstance(value, np.ndarray) else value
                            for key, value in board.homography.items()},
            )
            if board.image_to_plane is not None:
                metadata.update(image_to_plane=board.image_to_plane.tolist(), board_size_mm=list(board.board_size_mm))
        return metadata

    def begin_recalibration(self):
        if self.stage is not Stage.PLAYBACK or self.pending_play:
            raise ValueError("Start playback before recalibrating the table.")
        if self.model_failed:
            raise ValueError("Resolve the tracking error before recalibrating.")
        raw = self.source.read_frame(self.source.frame_index)
        self.recalibration = {"frame": raw, "frame_index": self.source.frame_index,
                              "resume_playing": self.playing, "held_view": self.display_snapshot, "draft": None}
        self.playing = False
        self.stage = Stage.RECALIBRATE
        self.note = "Video paused. Confirm the table on this source frame; Esc cancels."
        self._schedule(perf_counter())
        self.dirty = True
        return raw

    def cancel_recalibration(self):
        if self.recalibration is None:
            return
        if self.recalibration["draft"] is not None:
            raise ValueError("Wait for tracking initialization before cancelling.")
        context, self.recalibration = self.recalibration, None
        self.stage = Stage.PLAYBACK
        self.display_snapshot = context["held_view"]
        if context["resume_playing"] and self.source.frame_index < self.end_index:
            self._start_stream()
        self.note = "Recalibration cancelled; previous calibration and tracking retained."
        self.dirty = True

    def apply_recalibration(self, corners, boundary, *, board_size_in):
        context = self.recalibration
        if context is None or context["draft"] is not None:
            return
        if self.model_failed:
            raise ValueError("Tracking failed on the paused frame; cancel recalibration.")
        metadata = self.data.current.prediction_metadata
        if self.worker.busy or metadata is None or metadata["frame_index"] != context["frame_index"]:
            raise ValueError("Preparing masks for the paused frame. Wait, then press Continue again.")
        size = np.asarray(board_size_in, dtype=float) * 25.4
        draft = prepare_recalibration(self.data, context["frame"], corners, boundary, size)
        sizes = {obj: self.data.units.types[self.data.units.units[unit]["type_id"]].get("dimension", {})
                 for obj, unit in self.data.units.bindings.items()}
        tray_context = {"image_to_plane": draft["board"].image_to_plane,
                        "sizes": {obj: (size["width_mm"], size["depth_mm"]) for obj, size in sizes.items()
                                  if "width_mm" in size and "depth_mm" in size}}
        self.generation += 1
        self.worker.submit("recalibrate", frame=draft["frame"], prediction=draft["prediction"],
                           metadata=self._frame_metadata(board=draft["board"], frame=draft["frame"]),
                           generation=self.generation, tray_context=tray_context)
        context["draft"] = draft
        self.note = "Preparing tracking in the new calibration. Unit identities remain locked."
        self.dirty = True

    def _commit_recalibration(self, request):
        context = self.recalibration
        draft = context["draft"]
        if self.worker.tracker is None:
            self.worker.predictor = request["new_backend"]
        else:
            self.worker.tracker = request["new_backend"]
        self.worker.tracker_initialized = True
        self.worker.tray_context = request["tray_context"]
        self.data.board, self.data.rules = draft["board"], draft["rules"]
        self.data.current.frame = draft["frame"]
        self.initial_frame = context["frame"]
        self.registration_start_frame = context["frame_index"]
        self.data.record_calibration(request["metadata"])
        self.data.calibrations[-1]["unseeded_units"] = draft["unseeded_units"]
        self.last_submitted_frame = context["frame_index"]
        self.next_inference_time = perf_counter() + 1 / self.inference_fps
        self.pending_trays = False
        self.display_snapshot = None
        self.stage = Stage.PLAYBACK
        self.recalibration = None
        if context["resume_playing"] and self.source.frame_index < self.end_index:
            self._start_stream()

    def can_edit_points(self):
        if self.stage is Stage.TABLE:
            self.note = "Confirm the table corners and dimensions before registering units."
            self.dirty = True
            return False
        if self.registration_locked:
            self.note = "Registration is complete. R starts a new registration."
            self.dirty = True
            return False
        if not self.startup_ready:
            self.note = ("SAM3 preparation failed. R retries." if self.model_failed else
                         "Preparing SAM3 and first-frame features. Please wait before adding unit prompts.")
            self.dirty = True
            return False
        return True

    def load_units(self, path):
        if not self.can_edit_points():
            return
        roster = UnitRoster.load(path)
        if self.data.units is not None:
            roster.retain_bindings(self.data.units)
        self.data.units = roster
        self.selected_type = next(iter(roster.types))
        self._configure_trays()
        self._prediction_changed()
        self.note = f"Loaded {len(roster.types)} types. Select a mask and click a type, or drag a type onto a mask."

    def can_import_list(self):
        if self.stage is Stage.TABLE or self.registration_locked:
            self.note = ("Confirm the table corners and dimensions before importing army lists."
                         if self.stage is Stage.TABLE else "Registration is complete. R starts a new registration.")
            self.dirty = True
            return False
        return True

    def import_unit_list(self, path, list_id):
        if not self.can_import_list():
            return False
        self.pause()
        path = Path(path).resolve()
        if path.suffix.lower() == ".pdf":
            payload = read_unit_list_pdf(path, side=list_id)
        elif path.suffix.lower() == ".json":
            payload = UnitRoster.load(path).payload
        else:
            raise ValueError("Choose an army-list PDF or a type-catalog JSON.")
        roster = self.data.units.with_list(list_id, payload, source=str(path))
        cleared = set(self.data.units.bindings) - set(roster.bindings)
        for object_id in cleared:
            self.data.rules.fronts.pop(object_id, None)
        self.data.units = roster
        self.selected_type = next(key for key, row in roster.types.items() if row.get("list_id") == list_id)
        self._configure_trays()
        self._prediction_changed()
        count = sum(row.get("list_id") == list_id for row in roster.types.values())
        self.note = f"Imported list {list_id}: {count} types."
        if cleared:
            self.note += f" Reassign {len(cleared)} masks from the replaced list."
        return True

    def load_calibration(self, path):
        if not self.can_edit_points():
            return
        self.data.board.source_to_plane, self.data.board.board_size_mm = _read_tray_calibration(path)
        self.data.rules.fronts.clear()
        self.data.board.image_to_plane = (self.data.board.source_to_plane @ self.data.board.homography["inverse_matrix"]
                               if self.data.board.homography is not None else self.data.board.source_to_plane)
        self.data.board.calibration_version += 1
        if self.data.current.prediction is not None:
            self.data.current.prediction_metadata = self._frame_metadata()
        self.data.record_calibration(self._frame_metadata())
        self._configure_trays()
        self._prediction_changed()
        self.note = "Tray calibration loaded. Trays will be refitted; facing marks were cleared."

    def bind_active(self):
        if not self.can_edit_points():
            return
        self.pause()
        if self.data.units is None or self.selected_type is None:
            raise ValueError("Load a type catalog and select a type first")
        if self.active_id not in self.known_ids():
            raise ValueError("Click a target before binding its unit")
        previous = self.data.units.bindings.get(self.active_id)
        unit_id = self.data.units.bind(self.active_id, self.selected_type)
        if unit_id != previous:
            self.data.rules.fronts.pop(self.active_id, None)
            self._configure_trays()
        self._prediction_changed()
        self.note = f"Mask {self.active_id} -> {unit_id}. Click another type to rebind; N adds another mask."

    def unbind_active(self):
        if not self.can_edit_points():
            return
        self.pause()
        if self.data.units is not None:
            self.data.units.unbind(self.active_id)
            self.data.rules.fronts.pop(self.active_id, None)
            self._configure_trays()
            self._prediction_changed()
        self.note = f"Mask {self.active_id} is unlabelled. Click a type to bind it."

    def select_mask(self, object_id):
        self.pause()
        self.active_id = object_id
        if self.data.units and object_id in self.data.units.bindings:
            unit_id = self.data.units.bindings[object_id]
            self.selected_type = self.data.units.units[unit_id]["type_id"]
        self.note = (f"Registered mask {object_id}. Registration is complete; R starts again."
                     if self.registration_locked else
                     f"Selected mask {object_id}. Click a type to bind; Tab switches point editing / labelling.")
        self._prediction_changed()

    def cycle_mask(self, direction):
        ids = self.known_ids()
        if not ids:
            return
        index = ids.index(self.active_id) if self.active_id in ids else -1
        self.select_mask(ids[(index + direction) % len(ids)])

    def unit_action(self, action, unit_id=None):
        try:
            if action == "bind":
                self.bind_active()
            elif action == "unbind":
                self.unbind_active()
            elif action == "undo":
                self.undo_point()
            elif action == "mode":
                if self.can_edit_points():
                    self.interaction_mode = "label" if self.interaction_mode == "segment" else "segment"
                    self.note = ("Label mode: click a mask, then a type; or drag a type onto a mask."
                                 if self.interaction_mode == "label" else
                                 "Segment mode: clicks edit prompts. N adds a mask; Tab switches to labelling.")
            elif action == "select":
                if not self.can_edit_points():
                    return
                self.selected_type = unit_id
                self.interaction_mode = "label"
                if self.active_id in self.known_ids():
                    self.bind_active()
                else:
                    self.note = "Select a segmented mask, then click the type; or drag the type onto a mask."
        except (OSError, ValueError, RuntimeError) as error:
            self.note = str(error)
        self.dirty = True

    def _configure_trays(self):
        sizes = {}
        if self.data.units:
            for object_id, unit_id in self.data.units.bindings.items():
                type_id = self.data.units.units[unit_id]["type_id"]
                dimension = self.data.units.types[type_id].get("dimension", {})
                if "width_mm" in dimension and "depth_mm" in dimension:
                    sizes[object_id] = (dimension["width_mm"], dimension["depth_mm"])
        self.worker.tray_context = ({"image_to_plane": self.data.board.image_to_plane, "sizes": sizes}
                                    if self.data.board.image_to_plane is not None else None)
        request = self.worker.request if self.worker.busy else None
        # A queued result may still carry tray sizes from the replaced list.
        self.pending_trays = self.data.current.prediction is not None or (
            request is not None and request["kind"] in ("click", "replace", "propagate", "trays"))
        if self.data.current.prediction is not None:
            self.data.current.prediction = {**self.data.current.prediction, "trays": {}, "tray_errors": {}}

    def _prediction_changed(self):
        self.data.current.view_revision += 1
        self.dirty = True

    def tray_status(self):
        if self.data.board.image_to_plane is None:
            return "NO CALIB"
        if not self.worker.tray_context["sizes"]:
            return "NO SIZES"
        if self.data.current.prediction is None:
            return "WAIT MASK"
        trays = self.data.current.prediction.get("trays", {})
        if trays:
            return f"ON ({len(trays)})"
        if self.data.current.prediction.get("tray_errors"):
            return "CHECK FIT"
        if self.pending_trays or self.worker.busy:
            return "FITTING"
        return "NO FIT"

    def pause(self):
        if self.stage is Stage.PLAYBACK:
            if self.display_snapshot is None:
                self.display_snapshot = self.data.snapshot()
        else:
            self.playing = False
        self.dirty = True

    @property
    def presentation(self):
        return self.display_snapshot if self.display_snapshot is not None else self.data

    def resume_live(self):
        self.display_snapshot = None
        self.dirty = True

    def refresh_analysis_inputs(self):
        if self.display_snapshot is not None:
            self.display_snapshot.units = deepcopy(self.data.units)
            self.display_snapshot.rules.terrain = deepcopy(self.data.rules.terrain)
        if self.registration_locked:
            self.data.record_history()

    def toggle_play(self, overlay=None):
        if self.stage is Stage.PLAYBACK:
            if self.display_snapshot is None:
                self.pause()
            else:
                self.resume_live()
        elif self.source.frame_index >= self.end_index:
            self.note = "End of video interval. R restarts."
        else:
            if not self.registration_locked:
                try:
                    self.finish_registration(overlay)
                except (OSError, ValueError, cv2.error) as error:
                    self.note = str(error)
                    self.dirty = True
                    return
            self.stage = Stage.PLAYBACK
            if not self.worker.tracker_initialized:
                self.pending_play = True
                self.note = f"Initializing {self.worker.tracker_name} from registered masks before starting the video."
                self._schedule(perf_counter())
            else:
                self._start_stream()
            self._prediction_changed()
        self.dirty = True

    def _start_stream(self):
        self.play_start = perf_counter()
        self.play_start_frame = self.source.frame_index
        self.playing = True
        self.pending_play = False

    def new_object(self):
        if not self.can_edit_points():
            return
        self.pause()
        self.interaction_mode = "segment"
        self.active_id = max(self.known_ids(), default=0) + 1
        self._prediction_changed()
        self.note = f"Left click new mask {self.active_id}. Types can be assigned after all masks are segmented."

    def click(self, x, y, *, positive=True):
        if self.closed:
            return
        if not self.can_edit_points():
            return
        height, width = self.data.current.frame.shape[:2]
        if not (0 <= x < width and 0 <= y < height):
            return
        self.pause()
        ids = {click["object_id"] for click in self.clicks if click["positive"]}
        if not positive and self.active_id not in ids:
            self.note = "Start this object with a positive click."
            return
        click = {"object_id": self.active_id, "point": [float(x), float(y)],
                 "positive": positive, "video_frame": self.source.frame_index, "session_frame": None,
                 "click_id": self.next_click_id}
        self.next_click_id += 1
        self.clicks.append(click)
        self.pending_clicks.append((self.data.current.frame.copy(), self._frame_metadata(), click))
        self.model_failed = False
        self.note = "Click queued. SAM3 runs in the background; playback remains available."
        self._schedule(perf_counter())

    def undo_point(self):
        """Undo the most recent positive/negative click across all objects."""
        if not self.can_edit_points():
            return
        self.pause()
        if not self.clicks:
            self.note = "No point to undo."
            return
        removed = self.clicks.pop()
        self.active_id = removed["object_id"]
        if self.data.units and not any(click["object_id"] == self.active_id for click in self.clicks):
            unit_id = self.data.units.bindings.get(self.active_id)
            if unit_id is not None:
                self.selected_type = self.data.units.units[unit_id]["type_id"]
            self.data.units.unbind(self.active_id)
            self.data.rules.fronts.pop(self.active_id, None)
            self._configure_trays()
        queued = any(prompt["click_id"] == removed["click_id"] for _, _, prompt in self.pending_clicks)
        if queued and not self.updating_points:
            self.pending_clicks = deque(item for item in self.pending_clicks
                                        if item[2]["click_id"] != removed["click_id"])
            self.note = "Undid the queued point."
            return
        # Serialize prompt replacement behind any in-flight inference and
        # discard its stale UI result using the generation counter.
        self.generation += 1
        self.pending_clicks.clear()
        self.pending_update = {"frame": self.data.current.frame.copy(), "metadata": self._frame_metadata(),
                                "clicks": [dict(click) for click in self.clicks]}
        self.updating_points = True
        self.data.current.prediction = self.data.current.prediction_frame = self.data.current.prediction_metadata = None
        self.model_failed = False
        self._prediction_changed()
        self._schedule(perf_counter())
        self.note = "Point undone. Updating initial-frame prompts; please wait before saving."

    def _schedule(self, now):
        if self.worker.busy or self.closed:
            return
        if self.stage is Stage.RECALIBRATE:
            context = self.recalibration
            metadata = self.data.current.prediction_metadata
            if (context["draft"] is None and not self.model_failed and metadata is not None
                    and metadata["frame_index"] < context["frame_index"]):
                self.worker.submit("propagate", frame=self._warp_frame(context["frame"]),
                                   metadata=self._frame_metadata(), generation=self.generation)
                self.last_submitted_frame = context["frame_index"]
                self.next_inference_time = now + 1 / self.inference_fps
            return
        if self.needs_reset:
            self.needs_reset = False
            self.worker.submit("reset", generation=self.generation)
        elif self.needs_load:
            self.needs_load = False
            self.worker.submit("load", generation=self.generation)
        elif self.needs_prepare and self.data.board.homography is not None and not self.model_failed:
            self.needs_prepare = False
            self.worker.submit("prepare", frame=self.data.current.frame, metadata=self._frame_metadata(), generation=self.generation)
        elif self.pending_update is not None:
            request, self.pending_update = self.pending_update, None
            self.worker.submit("replace", **request, generation=self.generation)
        elif self.pending_clicks:
            frame, metadata, prompt = self.pending_clicks.popleft()
            self.worker.submit("click", frame=frame, metadata=metadata, prompt=prompt, generation=self.generation)
        elif self.pending_trays and self.data.current.prediction is not None:
            self.pending_trays = False
            self.worker.submit("trays", frame=self.data.current.prediction_frame, metadata=self.data.current.prediction_metadata,
                               prediction=self.data.current.prediction, generation=self.generation)
        elif self.pending_play and not self.worker.tracker_initialized and not self.model_failed:
            self.worker.submit("start_tracker", frame=self.data.current.prediction_frame, metadata=self.data.current.prediction_metadata,
                               prediction=self.data.current.prediction, generation=self.generation)
        elif (self.playing and self.data.current.prediction is not None and not self.model_failed and not self.updating_points
              and now >= self.next_inference_time and self.source.frame_index > self.last_submitted_frame):
            self.worker.submit("propagate", frame=self.data.current.frame, metadata=self._frame_metadata(), generation=self.generation)
            self.last_submitted_frame = self.source.frame_index
            self.next_inference_time = now + 1 / self.inference_fps

    def advance(self):
        if self.closed:
            return
        now = perf_counter()
        completed = self.worker.poll()
        if completed is not None:
            request, prediction, error = completed
            if request["generation"] == self.generation:
                if request["kind"] == "replace":
                    self.updating_points = False
                if error is not None and request["kind"] == "recalibrate":
                    self.recalibration["draft"] = None
                    self.note = f"Recalibration failed: {error}. Retry or Esc to cancel."
                elif error is not None:
                    self.model_failed = True
                    self.note = f"Model/tracking error: {error}. R resets the session."
                elif prediction is not None:
                    if request["kind"] == "recalibrate":
                        self._commit_recalibration(request)
                    prediction["accepted_at"] = perf_counter()
                    if self.pending_trays:
                        prediction = {**prediction, "trays": {}, "tray_errors": {}}
                    self.data.accept_observation(prediction, request["frame"], request["metadata"])
                    if self.registration_locked and request["kind"] in ("propagate", "recalibrate"):
                        self.data.record_history()
                    if request["kind"] == "click":
                        request["prompt"]["session_frame"] = prediction["frame_idx"]
                        self.last_submitted_frame = max(self.last_submitted_frame, request["metadata"]["frame_index"])
                        self.next_inference_time = now + 1 / self.inference_fps
                    elif request["kind"] == "replace":
                        by_id = {click["click_id"]: click for click in request["clicks"]}
                        for click in self.clicks:
                            if click["click_id"] in by_id:
                                click["session_frame"] = by_id[click["click_id"]]["session_frame"]
                        self.last_submitted_frame = request["metadata"]["frame_index"]
                        self.next_inference_time = now + 1 / self.inference_fps
                    elif request["kind"] == "start_tracker":
                        self._start_stream()
                    self._prediction_changed()
                    times = prediction.get("timings_seconds", {})
                    self.note = (f"Update {prediction['inference_seconds']:.2f}s | "
                                 f"{prediction.get('tracking_backend', 'model')} operation {times.get('worker_operation', 0):.2f}s | "
                                 f"tray {times.get('tray_fit', 0):.2f}s. Latest result held between updates.")
                elif request["kind"] == "replace":
                    self.last_submitted_frame = -1
                    self.note = "Point undone. No objects remain; click to register again."
                elif request["kind"] == "load":
                    self.note = ("Weights loaded. Preparing rectified first-frame features." if self.data.board.homography is not None else
                                 "Weights loaded. Confirm the table corners to focus the battlefield.")
                elif request["kind"] == "prepare":
                    self.startup_ready = True
                    self.note = f"SAM3 and first-frame features ready on {self.worker.predictor.device}. Segment targets; Tab labels."
                self.dirty = True
        if self.playing:
            target = min(self.end_index, self.play_start_frame + int((now - self.play_start) * self.source.fps))
            if target > self.source.frame_index:
                try:
                    self.data.current.frame = self._warp_frame(self.source.read_frame(target))
                    self.dirty = True
                except (OSError, ValueError, cv2.error) as error:
                    self.playing = False
                    self.note = str(error)
            if target >= self.end_index:
                self.playing = False
                self.note = "Video interval complete. Final registration references are already saved."
        self._schedule(now)

        progress = self.worker.load_progress
        if progress != self.load_progress or progress is not None:
            self.load_progress = progress
            self.dirty = True

    def extract_references(self):
        """Return masks and cutouts from the latest completed inference snapshot."""
        if self.updating_points:
            raise ValueError("Wait for the point update to finish before saving")
        if self.data.current.prediction is None:
            raise ValueError("No completed SAM3 result to extract")
        if self.pending_clicks or (self.worker.busy and self.worker.request["kind"] == "click"):
            raise ValueError("Wait for the queued click prompts to finish before extracting")
        return extract_references(self.data.current.prediction_frame, self.data.current.prediction, source=self.data.current.prediction_metadata,
                                  roster=self.data.units)

    def finish_registration(self, overlay):
        """Commit final references once; drafts remain editable after save errors."""
        if self.stage is Stage.TABLE:
            raise ValueError("Confirm the table boundary before completing registration")
        if self.data.reference_folder is not None:
            self.note = f"Registration already saved: {self.data.reference_folder}"
            self.dirty = True
            return self.data.reference_folder
        if self.worker.busy or self.pending_clicks or self.pending_trays or self.updating_points or self.needs_reset or self.needs_load or self.needs_prepare:
            raise ValueError("Wait for the point prompts to finish before completing registration")
        if self.model_failed:
            raise ValueError("Resolve the SAM3 error before completing registration; R resets")
        references = self.extract_references()
        self.pause()
        metadata = {**self.data.current.prediction_metadata, "object_ids": self.data.current.prediction["object_ids"],
                    "clicks": self.clicks, "inference_fps_limit": self.inference_fps,
                    "display_video_frame": self.source.frame_index, "model": self.worker.predictor.model_id,
                    "tracking_backend": self.worker.tracker_name,
                    "tracker_model": self.worker.tracker.model_id if self.worker.tracker is not None else self.worker.predictor.model_id,
                    "session_frame": self.data.current.prediction["frame_idx"], "registration_complete": True,
                    "table_boundary": self.data.board.table_boundary, "rule_inputs": self.data.rules.snapshot()}
        if self.data.board.image_to_plane is not None and self.data.units is not None:
            metadata["rule_scene"] = self.data.rules.scene(self.data.units, self.data.current.prediction, self.data.board.image_to_plane,
                                                          self.data.board.board_size_mm, self.data.current.prediction_metadata)
        folder = save_registration(self.data.current.prediction_frame, overlay, references, metadata,
                                   self.output_dir, roster=self.data.units)
        self.data.reference_folder = folder
        self.data.record_history()
        print(f"Saved: {folder.resolve()}", flush=True)
        self.note = f"Registration complete; final references saved. Space plays. {folder}"
        self.dirty = True
        return folder

    def reset(self):
        self.playing = False
        self.display_snapshot = None
        self.pending_play = False
        self.recalibration = None
        self.stage = Stage.REGISTER
        self.data.reference_folder = None
        self.data.history.clear()
        self.data.rules.fronts.clear()
        self.interaction_mode = "segment"
        self.generation += 1
        self.needs_reset = True
        self.needs_load = not self.worker.models_loaded
        self.needs_prepare = True
        self.startup_ready = False
        self.pending_clicks.clear()
        self.pending_update = None
        self.updating_points = False
        self.data.current.frame = self._warp_frame(self.source.read_frame(self.registration_start_frame))
        self.data.current.prediction = self.data.current.prediction_frame = self.data.current.prediction_metadata = None
        self.active_id = 1
        if self.data.units:
            self.data.units.reset_bindings()
            self.selected_type = next(iter(self.data.units.types))
        self._configure_trays()
        self.clicks.clear()
        self.last_submitted_frame = -1
        self.next_inference_time = 0
        self.model_failed = False
        self._prediction_changed()
        self._schedule(perf_counter())
        self.note = "Reset. Old in-flight results will be discarded."

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.playing = False
        self.display_snapshot = None
        self.source.close()
        self.worker.close()
