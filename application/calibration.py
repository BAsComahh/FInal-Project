"""Table calibration and the isolated B08 replacement transaction."""
from copy import deepcopy
import json
from pathlib import Path
from time import perf_counter
import numpy as np
import cv2
from components.homography import warp_table
from components.recalibration import prepare_recalibration
from .contracts import command, CommandReceipt, freeze
from .config import DEFAULT_BOARD_SIZE_IN

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

class Calibration:
    def __init__(self, session):
        self._session = session
        self._data = session.data
        self._context = None

    @property
    def status(self):
        context = self._context
        return None if context is None else freeze({"draft": True if context["draft"] is not None else None,
            "pending": True if context["pending"] is not None else None, "error": context["error"],
            "request_id": id(context["token"])})

    @command
    def confirm_table(self, corners, boundary, *, board_size_in=None):
        if self._session.closed or self._session.registration_locked:
            raise ValueError("Use B08 to recalibrate after registration.")
        size_mm = np.asarray(self._data.board.board_size_mm, dtype=float)
        if board_size_in is not None:
            size_mm = np.asarray(board_size_in, dtype=float) * 25.4
        if size_mm.shape != (2,) or not np.isfinite(size_mm).all() or np.any(size_mm <= 0):
            raise ValueError("Board length and width must be positive inch dimensions.")
        result = warp_table(self._session.initial_frame, corners, board_size=size_mm)
        if self._data.board.source_to_plane is not None:
            scale = np.diag([*(size_mm / self._data.board.board_size_mm), 1.0])
            self._data.board.source_to_plane = scale @ self._data.board.source_to_plane
        else:
            self._data.board.source_to_plane = result["image_to_board"]
        self._data.board.board_size_mm = tuple(size_mm)
        self._data.board.homography = {key: value for key, value in result.items() if key != "image"}
        self._data.current.frame = result["image"]
        self._data.board.table_boundary = deepcopy(boundary)
        self._data.board.calibration_version += 1
        if self._data.board.source_to_plane is not None:
            self._data.board.image_to_plane = self._data.board.source_to_plane @ self._data.board.homography["inverse_matrix"]
        self._data.record_calibration(self._session.frame_metadata())
        self._session.configure_trays()
        self._session.mark_changed()
        self._session.note = "Table focused. Preparing SAM3 features for the rectified first frame."
        return CommandReceipt("accepted")

    @command
    def begin_recalibration(self):
        if self._session.closed or not self._session.playback_started or self._session.pending_play:
            raise ValueError("Start playback before recalibrating the table.")
        if self._session.model_failed:
            raise ValueError("Resolve the tracking error before recalibrating.")
        self._session.recovery.cancel()
        raw = self._session.source.frame
        self._session.automatic_recovery.invalidate("Recalibration invalidated the recovery candidate")
        self._context = {"frame_index": self._session.source.frame_index,
                        "token": object(), "draft": None, "pending": None, "error": None}
        self._session.note = "Live recalibration. Select the table corners. Esc cancels."
        return CommandReceipt("accepted", request_id=id(self._context["token"]), value=freeze(raw))

    @command
    def cancel_recalibration(self):
        if self._context is None:
            return CommandReceipt("accepted", self._session.note)
        self._context = None
        self._session.note = "Recalibration cancelled; previous calibration and tracking retained."
        return CommandReceipt("accepted")

    @command
    def apply_recalibration(self, corners, boundary, *, board_size_in):
        context = self._context
        if context is None or context["draft"] is not None or context["pending"] is not None:
            return CommandReceipt("rejected", self._session.note)
        if self._session.model_failed:
            raise ValueError("Resolve the tracking error before applying recalibration.")
        context["pending"] = (deepcopy(corners), deepcopy(boundary), np.asarray(board_size_in, dtype=float) * 25.4)
        context["error"] = None
        self._session.note = "Waiting for a matching observation; source playback continues."
        return CommandReceipt("pending", request_id=id(context["token"]))

    def submit_pending(self):
        context = self._context
        if context is None or context["pending"] is None or context["draft"] is not None or self._session.model_failed:
            return False
        metadata = self._data.current.prediction_metadata
        raw = self._session.prediction_raw_frame
        if metadata is None or raw is None or metadata["frame_index"] < context["frame_index"]:
            if self._session.source.frame_index > self._session.last_submitted_frame:
                self._session.worker.submit("propagate", frame=self._data.current.frame,
                                           metadata=self._session.frame_metadata(), generation=self._session.generation,
                                           raw_frame=self._session.source.frame)
                self._session.last_submitted_frame = self._session.source.frame_index
                self._session.next_inference_time = perf_counter() + self._session.inference_interval
                return True
            return False
        corners, boundary, size = context["pending"]
        try:
            draft = prepare_recalibration(self._data, raw, corners, boundary, size)
        except (ValueError, cv2.error) as error:
            context["pending"] = None
            self._session.note = f"Recalibration not applied: {error}"
            context["error"] = self._session.note
            return False
        sizes = {obj: self._data.units.types[self._data.units.units[unit]["type_id"]].get("dimension", {})
                 for obj, unit in self._data.units.bindings.items()}
        tray_context = {"image_to_plane": draft["board"].image_to_plane,
                        "sizes": {obj: (size["width_mm"], size["depth_mm"]) for obj, size in sizes.items()
                                  if "width_mm" in size and "depth_mm" in size}}
        source_metadata = self._session.frame_metadata(board=draft["board"], frame=draft["frame"])
        for key in ("frame_index", "timestamp_seconds", "source_timestamp_seconds"):
            if key in metadata:
                source_metadata[key] = metadata[key]
        self._session.worker.submit("recalibrate", frame=draft["frame"], prediction=draft["prediction"],
                           metadata=source_metadata, raw_frame=raw, calibration_token=context["token"],
                           generation=self._session.generation, tray_context=tray_context)
        context["draft"] = draft
        context["pending"] = None
        self._session.note = "Preparing tracking in the new calibration. Unit identities remain locked."
        return True

    def accept_result(self, request, prediction, error):
        context = self._context
        if context is None or request.get("calibration_token") is not context["token"]:
            return False
        if error is not None or prediction is None or not any(mask.any() for mask in prediction["masks"]):
            context["draft"] = None
            self._session.note = f"Recalibration failed: {error or 'No usable initialized masks'}. Old tracking retained."
            context["error"] = self._session.note
            return False
        self.commit_recalibration(request)
        return True

    def commit_recalibration(self, request):
        context = self._context
        draft = context["draft"]
        if self._session.worker.tracker is None:
            self._session.worker.predictor = request["new_backend"]
        else:
            self._session.worker.tracker = request["new_backend"]
        self._session.worker.tracker_initialized = True
        self._session.worker.tray_context = request["tray_context"]
        self._data.board, self._data.rules = draft["board"], draft["rules"]
        self._data.current.frame = self._session._warp_frame(self._session.source.frame)
        self._session.initial_frame = request["raw_frame"]
        self._session.registration_start_frame = request["metadata"]["frame_index"]
        self._data.record_calibration(request["metadata"])
        self._data.calibrations[-1]["unseeded_units"] = draft["unseeded_units"]
        self._session.last_submitted_frame = request["metadata"]["frame_index"]
        self._session.next_inference_time = perf_counter() + self._session.inference_interval
        self._session.pending_trays = False
        self._session.generation += 1
        self._context = None

    @command
    def load_calibration(self, path):
        if self._session.closed or self._session.registration_locked:
            raise ValueError("Calibration import is locked after registration; use B08.")
        self._data.board.source_to_plane, self._data.board.board_size_mm = _read_tray_calibration(path)
        self._data.rules.fronts.clear()
        self._data.board.image_to_plane = (self._data.board.source_to_plane @ self._data.board.homography["inverse_matrix"]
                               if self._data.board.homography is not None else self._data.board.source_to_plane)
        self._data.board.calibration_version += 1
        if self._data.current.prediction is not None:
            self._data.current.prediction_metadata = self._session.frame_metadata()
        self._data.record_calibration(self._session.frame_metadata())
        self._session.configure_trays()
        self._session.mark_changed()
        self._session.note = "Tray calibration loaded. Trays will be refitted; facing marks were cleared."
        return CommandReceipt("accepted")
