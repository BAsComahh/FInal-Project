"""Table calibration and the isolated B08 replacement transaction."""
from copy import deepcopy
import json
from pathlib import Path
from time import perf_counter
import numpy as np
from components.homography import warp_table
from components.recalibration import prepare_recalibration
from ..config import DEFAULT_BOARD_SIZE_IN

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


def configure_board(data, calibration=None, board_size_in=None):
    if calibration is not None and board_size_in is not None:
        raise ValueError("Use either --calibration or --board-size-in, not both.")
    if calibration is not None:
        data.board.source_to_plane, data.board.board_size_mm = _read_tray_calibration(calibration)
    else:
        size = np.asarray(board_size_in if board_size_in is not None else DEFAULT_BOARD_SIZE_IN, dtype=float)
        if size.shape != (2,) or not np.isfinite(size).all() or np.any(size <= 0):
            raise ValueError("Board width and depth must be positive inch dimensions.")
        data.board.board_size_mm = tuple(size * 25.4)
    data.board.image_to_plane = data.board.source_to_plane

class CalibrationController:
    def __init__(self, session, live):
        self.session = session
        self.data = session.data
        self.live = live
        self.context = None

    def confirm_table(self, corners, boundary, *, board_size_in=None):
        size_mm = np.asarray(self.data.board.board_size_mm, dtype=float)
        if board_size_in is not None:
            size_mm = np.asarray(board_size_in, dtype=float) * 25.4
        if size_mm.shape != (2,) or not np.isfinite(size_mm).all() or np.any(size_mm <= 0):
            raise ValueError("Board length and width must be positive inch dimensions.")
        result = warp_table(self.session.initial_frame, corners, board_size=size_mm)
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
        if self.data.board.source_to_plane is not None:
            self.data.board.image_to_plane = self.data.board.source_to_plane @ self.data.board.homography["inverse_matrix"]
        self.data.record_calibration(self.session.frame_metadata())
        self.session.configure_trays()
        self.session.mark_changed()
        self.session.note = "Table focused. Preparing SAM3 features for the rectified first frame."

    def begin_recalibration(self):
        if not self.session.registration_locked or self.session.pending_play:
            raise ValueError("Start playback before recalibrating the table.")
        if self.session.model_failed:
            raise ValueError("Resolve the tracking error before recalibrating.")
        raw = self.session.source.read_frame(self.session.source.frame_index)
        self.context = {"frame": raw, "frame_index": self.session.source.frame_index,
                              "resume_playing": self.session.playing, "held_view": self.live.snapshot, "draft": None}
        self.session.playing = False
        self.session.note = "Video paused. Confirm the table on this source frame; Esc cancels."
        self.session.dirty = True
        return raw

    def cancel_recalibration(self):
        if self.context is None:
            return
        if self.context["draft"] is not None:
            raise ValueError("Wait for tracking initialization before cancelling.")
        context, self.context = self.context, None
        self.live.snapshot = context["held_view"]
        if context["resume_playing"] and self.session.source.frame_index < self.session.end_index:
            self.session.start_stream()
        self.session.note = "Recalibration cancelled; previous calibration and tracking retained."
        self.session.dirty = True

    def apply_recalibration(self, corners, boundary, *, board_size_in):
        context = self.context
        if context is None or context["draft"] is not None:
            return
        if self.session.model_failed:
            raise ValueError("Tracking failed on the paused frame; cancel recalibration.")
        metadata = self.data.current.prediction_metadata
        if self.session.worker.busy or metadata is None or metadata["frame_index"] != context["frame_index"]:
            raise ValueError("Preparing masks for the paused frame. Wait, then press Continue again.")
        size = np.asarray(board_size_in, dtype=float) * 25.4
        draft = prepare_recalibration(self.data, context["frame"], corners, boundary, size)
        sizes = {obj: self.data.units.types[self.data.units.units[unit]["type_id"]].get("dimension", {})
                 for obj, unit in self.data.units.bindings.items()}
        tray_context = {"image_to_plane": draft["board"].image_to_plane,
                        "sizes": {obj: (size["width_mm"], size["depth_mm"]) for obj, size in sizes.items()
                                  if "width_mm" in size and "depth_mm" in size}}
        self.session.generation += 1
        self.session.worker.submit("recalibrate", frame=draft["frame"], prediction=draft["prediction"],
                           metadata=self.session.frame_metadata(board=draft["board"], frame=draft["frame"]),
                           generation=self.session.generation, tray_context=tray_context)
        context["draft"] = draft
        self.session.note = "Preparing tracking in the new calibration. Unit identities remain locked."
        self.session.dirty = True

    def commit_recalibration(self, request):
        context = self.context
        draft = context["draft"]
        if self.session.worker.tracker is None:
            self.session.worker.predictor = request["new_backend"]
        else:
            self.session.worker.tracker = request["new_backend"]
        self.session.worker.tracker_initialized = True
        self.session.worker.tray_context = request["tray_context"]
        self.data.board, self.data.rules = draft["board"], draft["rules"]
        self.data.current.frame = draft["frame"]
        self.session.initial_frame = context["frame"]
        self.session.registration_start_frame = context["frame_index"]
        self.data.record_calibration(request["metadata"])
        self.data.calibrations[-1]["unseeded_units"] = draft["unseeded_units"]
        self.session.last_submitted_frame = context["frame_index"]
        self.session.next_inference_time = perf_counter() + 1 / self.session.inference_fps
        self.session.pending_trays = False
        self.live.snapshot = None
        self.context = None
        if context["resume_playing"] and self.session.source.frame_index < self.session.end_index:
            self.session.start_stream()

    def load_calibration(self, path):
        self.data.board.source_to_plane, self.data.board.board_size_mm = _read_tray_calibration(path)
        self.data.rules.fronts.clear()
        self.data.board.image_to_plane = (self.data.board.source_to_plane @ self.data.board.homography["inverse_matrix"]
                               if self.data.board.homography is not None else self.data.board.source_to_plane)
        self.data.board.calibration_version += 1
        if self.data.current.prediction is not None:
            self.data.current.prediction_metadata = self.session.frame_metadata()
        self.data.record_calibration(self.session.frame_metadata())
        self.session.configure_trays()
        self.session.mark_changed()
        self.session.note = "Tray calibration loaded. Trays will be refitted; facing marks were cleared."
