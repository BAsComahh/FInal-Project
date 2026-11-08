"""Shared data for one match; model sessions and UI controls live elsewhere."""

from copy import deepcopy
from dataclasses import dataclass, field
from math import floor
from pathlib import Path

import numpy as np
from components.homography import transform_points

from components.history import HistoryStore
from components.motion_history import MotionRecorder, SOURCE_COORDINATE_BASIS
from components.registration.units import UnitRoster
from components.registration.rule_state import RuleState
from components.tracking.status import update_tracking


def _history_source(metadata):
    return {key: deepcopy(value) for key, value in metadata.items() if key in (
        "type", "video", "frame_index", "timestamp_seconds", "fps", "source_timestamp_seconds",
        "source_url", "calibration_version", "coordinate_space", "image_size", "source_image_size")}


@dataclass
class BoardData:
    calibration_version: int = 0
    source_size: tuple | None = None
    board_size_mm: tuple | None = None
    source_to_plane: object = None
    image_to_plane: object = None
    homography: dict | None = None
    table_boundary: dict | None = None


@dataclass
class CurrentData:
    frame: object = None
    prediction: dict | None = None
    prediction_frame: object = None
    prediction_metadata: dict | None = None
    view_revision: int = 0


@dataclass
class GameData:
    board: BoardData = field(default_factory=BoardData)
    units: UnitRoster | None = None
    rules: RuleState = field(default_factory=RuleState)
    current: CurrentData = field(default_factory=CurrentData)
    history: list = field(default_factory=list)
    calibrations: list = field(default_factory=list)
    tracking: dict = field(default_factory=dict)
    reference_folder: Path | None = None
    history_store: HistoryStore | None = field(default=None, repr=False)
    global_history: dict = field(default_factory=dict)
    motion_recorder: MotionRecorder | None = field(default=None, repr=False)
    _history_sequence: int = 0
    _history_latest_time: float = 0.0

    def accept_observation(self, prediction, frame, metadata, *, disappearance_seconds=None):
        """Accept a completed result with its matching image and source time."""
        if disappearance_seconds is not None:
            previous = self.current.prediction_metadata
            if previous is not None and (metadata["frame_index"] < previous["frame_index"]
                                         or metadata.get("calibration_version", 0) < previous.get("calibration_version", 0)):
                return False
        if self.board.source_to_plane is not None:
            inverse = np.linalg.inv(self.board.source_to_plane)
            trays = {}
            for object_id, tray in prediction.get("trays", {}).items():
                corners = np.asarray(tray["corners_plane"], dtype=float)
                trays[object_id] = {**tray, "corners_source": transform_points(corners, inverse).tolist(),
                                    "center_source": transform_points(corners.mean(axis=0), inverse).tolist()}
            prediction = {**prediction, "trays": trays}
        if disappearance_seconds is not None:
            prediction = update_tracking(self.tracking, self.units, prediction, metadata, disappearance_seconds)
        self.current.prediction = prediction
        self.current.prediction_frame = frame
        self.current.prediction_metadata = metadata
        self.rules.observe(prediction, metadata["frame_index"], source_to_plane=self.board.source_to_plane)
        return True

    def snapshot(self):
        """Freeze one observation without copying the growing match history."""
        current = self.current
        frame = current.prediction_frame if current.prediction is not None else current.frame
        frame = None if frame is None else frame.copy()
        return GameData(
            board=deepcopy(self.board), units=deepcopy(self.units), rules=deepcopy(self.rules),
            tracking=deepcopy(self.tracking),
            current=CurrentData(frame=frame, prediction=deepcopy(current.prediction),
                                prediction_frame=frame if current.prediction is not None else None,
                                prediction_metadata=deepcopy(current.prediction_metadata),
                                view_revision=current.view_revision),
            reference_folder=self.reference_folder,
        )

    def start_history(self, folder, source):
        """Start one persistent registration; analysis snapshots never own a writer."""
        if self.history_store is not None:
            raise RuntimeError("Close the previous history before starting another registration")
        if self.motion_recorder is None:
            self.motion_recorder = MotionRecorder()
        self.history_store = HistoryStore(Path(folder) / "history.sqlite3", {
            "source": _history_source(source), "reference_folder": str(folder),
            "units": self.units.snapshot() if self.units is not None else None,
            "rules": self.rules.snapshot(),
            "time_basis": "acceptance/edit clip_source_seconds; geometry retains its own observation source time",
            "spatial_coordinate_basis": SOURCE_COORDINATE_BASIS,
            "motion_parameters": {"position_tolerance_mm": self.motion_recorder.position_tolerance_mm,
                                  "rotation_tolerance_deg": self.motion_recorder.rotation_tolerance_deg,
                                  "settle_seconds": self.motion_recorder.settle_seconds},
        })
        self._history_sequence = 0
        self._history_latest_time = 0.0
        self.global_history.clear()
        self.motion_recorder.reset()

    def _calibration_records(self):
        records = []
        for item in self.calibrations:
            board = item["board"]
            records.append({"version": item["version"], "source": _history_source(item["source"]),
                            "reference_folder": item["reference_folder"],
                            "board": {key: deepcopy(getattr(board, key)) for key in (
                                "source_size", "board_size_mm", "source_to_plane", "image_to_plane", "homography")}})
        return records

    def poll_history(self):
        if self.history_store is None:
            return
        self.history_store.poll()
        cutoff = floor((self._history_latest_time - 300.0) / 30.0) * 30.0
        self.history[:] = [entry for entry in self.history
                           if entry["timestamp_seconds"] >= cutoff
                           or entry["sequence"] > self.history_store.saved_sequence]
        self.global_history = {key: event for key, event in self.global_history.items()
                               if event["status"] == "ongoing" or event["recorded_source"]["timestamp_seconds"] >= cutoff
                               or event["updated_sequence"] > self.history_store.saved_sequence}

    def finish_motion(self, reason, source):
        if self.motion_recorder is not None and self.motion_recorder.has_active:
            self.record_history(kind="interruption", source=source, interruption=reason)

    def record_history(self, *, kind="observation", source=None, interruption=None):
        """Record geometry/states; the writer separately retains active step images."""
        current = self.current
        if self.units is None or current.prediction is None or current.prediction_metadata is None:
            return False
        units = {}
        unavailable = set(current.prediction.get("unavailable_ids", [])) | set(current.prediction.get("inactive_ids", []))
        for object_id, unit_id in self.units.bindings.items():
            unit = self.units.units[unit_id]
            profile = {**self.units.types[unit["type_id"]].get("attributes", {}), **unit["attributes"]}
            tray = current.prediction.get("trays", {}).get(object_id) if object_id not in unavailable else None
            tracking = self.tracking.get(unit_id)
            units[unit_id] = {
                "type_id": unit["type_id"], "attributes": deepcopy(profile),
                "corners_mm": deepcopy(tray["corners_plane"]) if tray is not None else None,
                "corners_source": deepcopy(tray.get("corners_source")) if tray is not None else None,
                "center_source": deepcopy(tray.get("center_source")) if tray is not None else None,
                "position_status": "available" if tray is not None else "unavailable",
                "tracking_status": tracking.status if tracking else None,
                "visibility": tracking.visibility if tracking else None,
                "disappeared_time": tracking.disappeared_time if tracking else None,
                "active": tracking.active if tracking else not (profile.get("routed") or profile.get("removed")),
                "state": {"engaged": deepcopy(profile.get("engaged")),
                          "wavering": deepcopy(profile.get("wavering")),
                          "facing": deepcopy(self.rules.fronts.get(object_id))},
            }
        observation = current.prediction_metadata
        source = observation if source is None else source
        entry = {"calibration_version": self.board.calibration_version, "kind": kind,
                 "source": _history_source(source), "observation_source": _history_source(observation),
                 "rules": self.rules.snapshot(),
                 "observation_frame_index": observation["frame_index"],
                 "observation_timestamp_seconds": observation.get("timestamp_seconds"),
                 "frame_index": source["frame_index"],
                 "timestamp_seconds": source.get("timestamp_seconds"), "units": units}
        if self.history and {key: value for key, value in self.history[-1].items()
                            if key not in ("sequence", "motion_events", "motion_event_ids")} == entry:
            return False
        self._history_sequence += 1
        entry["sequence"] = self._history_sequence
        if self.motion_recorder is not None:
            events = (self.motion_recorder.interrupt_all(entry, interruption) if interruption is not None
                      else self.motion_recorder.observe(entry, source_to_plane=self.board.source_to_plane))
            entry["motion_events"] = events
            entry["motion_event_ids"] = [event["event_id"] for event in events]
            self.global_history.update({event["event_id"]: event for event in events})
        self.history.append(entry)
        if self.history_store is not None:
            self.history_store.append(entry, self._calibration_records(), frame=current.prediction_frame)
            self._history_latest_time = max(self._history_latest_time, entry["timestamp_seconds"])
            self.poll_history()
        return True

    def record_calibration(self, metadata):
        self.calibrations.append({"version": self.board.calibration_version,
                                  "source": deepcopy(metadata), "board": deepcopy(self.board),
                                  "reference_folder": self.reference_folder})
