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
from components.tracking.status import UnitTracking, update_tracking


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
    geometry_frame: object = None
    geometry_revision: int = 0


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

    def _source_geometry(self, prediction):
        if self.board.source_to_plane is None:
            return prediction
        inverse = np.linalg.inv(self.board.source_to_plane)
        trays = {}
        for obj, tray in prediction.get("trays", {}).items():
            corners = np.asarray(tray["corners_plane"], dtype=float)
            trays[obj] = {**tray, "corners_source": transform_points(corners, inverse).tolist(),
                          "center_source": transform_points(corners.mean(axis=0), inverse).tolist()}
        return {**prediction, "trays": trays}

    def accept_observation(self, prediction, frame, metadata, *, disappearance_seconds=None, resume_visible_masks=False):
        """Accept a completed result with its matching image and source time."""
        if disappearance_seconds is not None:
            previous = self.current.prediction_metadata
            if previous is not None and (metadata["frame_index"] < previous["frame_index"]
                                         or metadata.get("calibration_version", 0) < previous.get("calibration_version", 0)):
                return False
        pending = prediction.get("geometry_pending", False)
        if not pending:
            prediction = self._source_geometry(prediction)
        if disappearance_seconds is not None:
            prediction = update_tracking(self.tracking, self.units, prediction, metadata, disappearance_seconds,
                                         resume_visible_masks=resume_visible_masks)
        if pending:
            previous = self.current.prediction or {}
            prediction = {**prediction, **{key: previous[key] for key in
                ("trays", "tray_errors", "facing_results", "geometry_metadata", "tray_fit_stats") if key in previous}}
            prev_tray_fit = (previous.get("timings_seconds") or {}).get("tray_fit")
            timings = dict(prediction.get("timings_seconds") or {})
            if prev_tray_fit is not None and "tray_fit" not in timings:
                timings["tray_fit"] = prev_tray_fit
            if timings:
                prediction["timings_seconds"] = timings
            unavailable = set(prediction.get("unavailable_ids", ())) | set(prediction.get("inactive_ids", ()))
            prediction["trays"] = {obj: tray for obj, tray in prediction.get("trays", {}).items() if obj not in unavailable}
            for obj in unavailable:
                self.rules.fronts.pop(obj, None)
        else:
            prediction = {**prediction, "geometry_metadata": deepcopy(metadata)}
            self.current.geometry_frame = frame
            self.current.geometry_revision += 1
        self.current.prediction = prediction
        self.current.prediction_frame = frame
        self.current.prediction_metadata = metadata
        if not pending:
            self.rules.observe(prediction, metadata["frame_index"], source_to_plane=self.board.source_to_plane,
                               calibration_version=metadata.get("calibration_version"),
                               bindings=self.units.bindings if self.units is not None else None)
        return True

    def accept_geometry(self, prediction, frame, metadata):
        """Attach one frame-aligned batch without rewinding the latest masks."""
        prediction = self._source_geometry(prediction)
        trays = {}
        for obj, tray in prediction.get("trays", {}).items():
            if obj in prediction.get("unavailable_ids", ()) or obj in prediction.get("inactive_ids", ()):
                continue
            trays[obj] = tray
            state = self.tracking.get(self.units.bindings.get(obj))
            if state is not None:
                state.last_accepted_position = dict(corners_mm=deepcopy(tray["corners_plane"]),
                    corners_source=tray.get("corners_source"), center_source=tray.get("center_source"),
                    frame_index=metadata["frame_index"], timestamp_seconds=metadata["timestamp_seconds"],
                    calibration_version=metadata.get("calibration_version"))
        prediction = {**prediction, "trays": trays, "geometry_metadata": deepcopy(metadata), "geometry_pending": False}
        self.rules.observe(prediction, metadata["frame_index"], source_to_plane=self.board.source_to_plane,
                           calibration_version=metadata.get("calibration_version"), bindings=self.units.bindings)
        current = self.current
        timings = {**(current.prediction.get("timings_seconds") or {}), **(prediction.get("timings_seconds") or {})}
        current.prediction = {**current.prediction, **{key: prediction[key] for key in
            ("trays", "tray_errors", "facing_results", "geometry_metadata", "tray_fit_stats") if key in prediction},
            **({"timings_seconds": timings} if timings else {})}
        current.geometry_frame = frame
        current.geometry_revision += 1
        return prediction

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
                                view_revision=current.view_revision, geometry_frame=current.geometry_frame,
                                geometry_revision=current.geometry_revision),
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

    def accept_manual_recovery(self, prediction, frame, metadata, object_id, *, source, disappearance_seconds):
        return self.accept_recovery(prediction, frame, metadata, object_id, source=source,
                                    disappearance_seconds=disappearance_seconds, method="manual")

    def accept_recovery(self, prediction, frame, metadata, object_id, *, source, disappearance_seconds, method="manual"):
        """Accept one confirmed existing ID; drafts never reach this method."""
        if method not in ("manual", "reviewed", "automatic"):
            raise ValueError("Unknown recovery method")
        if self.units is None or object_id not in self.units.bindings:
            raise ValueError("Recovery target is no longer registered")
        unit_id = self.units.bindings[object_id]
        state = self.tracking.get(unit_id)
        unit = self.units.units[unit_id]
        profile = {**self.units.types[unit["type_id"]].get("attributes", {}), **unit["attributes"]}
        if (state is None or not state.active or profile.get("removed") is True or profile.get("routed") is True
                or metadata.get("calibration_version") != self.board.calibration_version):
            raise ValueError("Recovery target or calibration is no longer current")
        if (self.current.prediction_metadata is not None
                and metadata["frame_index"] < self.current.prediction_metadata["frame_index"]):
            raise ValueError("Recovery observation is older than accepted tracking")
        masks = dict(zip(prediction["object_ids"], prediction["masks"]))
        if object_id not in masks or not masks[object_id].any():
            raise ValueError("Confirmed recovery has no current mask")
        state.status, state.visibility, state.disappeared_time = "tracking", True, None
        state.recovery_update_error = None
        state.recovery_phase = state.recovery_note = None
        state.frame_index = -1  # Same-frame/EOF recovery must refresh this ID too.
        self.rules.fronts.pop(object_id, None)
        self.accept_observation(prediction, frame, metadata, disappearance_seconds=disappearance_seconds)
        self.record_history(kind=f"{method}_recovery", source=source,
                            recovery={"unit_id": unit_id, "object_id": object_id, "method": method})

    def fail_manual_recovery(self, object_id, source):
        return self.fail_recovery(object_id, source, method="manual")

    def fail_recovery(self, object_id, source, *, method="manual", error=None):
        """A consumed but unsuccessful update invalidates only its target."""
        unit_id = self.units.bindings.get(object_id) if self.units is not None else None
        if unit_id is None:
            return
        state = self.tracking.setdefault(unit_id, UnitTracking())
        state.status = "failed"
        state.recovery_update_error = str(error or "") or "The updated mask could not be accepted."
        state.recovery_phase = "manual"
        self.rules.fronts.pop(object_id, None)
        if self.current.prediction is not None:
            prediction = self.current.prediction
            prediction["unavailable_ids"] = sorted(set(prediction.get("unavailable_ids", [])) | {object_id})
        self.record_history(kind=f"{method}_recovery_failed", source=source,
                            recovery={"unit_id": unit_id, "object_id": object_id, "method": method})

    def record_history(self, *, kind="observation", source=None, interruption=None, recovery=None,
                       observation=None, tracking=None, interruptions=()):
        """Record geometry/states; the writer separately retains active step images."""
        current = self.current
        prediction, frame, metadata = (observation if observation is not None else
            (current.prediction, current.geometry_frame if current.geometry_frame is not None else current.prediction_frame,
             (current.prediction or {}).get("geometry_metadata", current.prediction_metadata)))
        if self.units is None or current.prediction is None or current.prediction_metadata is None:
            return False
        units = {}
        unavailable = set(prediction.get("unavailable_ids", [])) | set(prediction.get("inactive_ids", []))
        for object_id, unit_id in self.units.bindings.items():
            unit = self.units.units[unit_id]
            profile = {**self.units.types[unit["type_id"]].get("attributes", {}), **unit["attributes"]}
            tray = prediction.get("trays", {}).get(object_id) if object_id not in unavailable else None
            state = (self.tracking if tracking is None else tracking).get(unit_id)
            units[unit_id] = {
                "type_id": unit["type_id"], "attributes": deepcopy(profile),
                "corners_mm": deepcopy(tray["corners_plane"]) if tray is not None else None,
                "corners_source": deepcopy(tray.get("corners_source")) if tray is not None else None,
                "center_source": deepcopy(tray.get("center_source")) if tray is not None else None,
                "position_status": "available" if tray is not None else "unavailable",
                "tracking_status": state.status if state else None,
                "visibility": state.visibility if state else None,
                "disappeared_time": state.disappeared_time if state else None,
                "recovery_phase": state.recovery_phase if state else None,
                "recovery_note": state.recovery_note if state else None,
                "recovery_update_error": state.recovery_update_error if state else None,
                "active": state.active if state else not (profile.get("routed") or profile.get("removed")),
                "state": {"engaged": deepcopy(profile.get("engaged")),
                          "wavering": deepcopy(profile.get("wavering")),
                          "facing": deepcopy(self.rules.fronts.get(object_id))},
            }
        source = metadata if source is None else source
        entry = {"calibration_version": self.board.calibration_version, "kind": kind,
                 "source": _history_source(source), "observation_source": _history_source(metadata),
                 "mask_source": _history_source(metadata if observation is not None else current.prediction_metadata),
                 "rules": self.rules.snapshot(),
                 "observation_frame_index": metadata["frame_index"],
                 "observation_timestamp_seconds": metadata.get("timestamp_seconds"),
                 "frame_index": source["frame_index"],
                 "timestamp_seconds": source.get("timestamp_seconds"), "units": units}
        if recovery is not None:
            entry["recovery"] = deepcopy(recovery)
        if interruptions:
            entry["tracking_interruptions"] = list(interruptions)
        if self.history and {key: value for key, value in self.history[-1].items()
                            if key not in ("sequence", "motion_events", "motion_event_ids")} == entry:
            return False
        self._history_sequence += 1
        entry["sequence"] = self._history_sequence
        if self.motion_recorder is not None:
            events = []
            for unit_id in interruptions:
                events.extend(self.motion_recorder.interrupt_unit(unit_id, entry, "mask_missing"))
            if recovery is not None:
                events.extend(self.motion_recorder.interrupt_unit(recovery["unit_id"], entry, kind))
            events.extend(self.motion_recorder.interrupt_all(entry, interruption) if interruption is not None
                          else self.motion_recorder.observe(entry, source_to_plane=self.board.source_to_plane))
            entry["motion_events"] = events
            entry["motion_event_ids"] = [event["event_id"] for event in events]
            self.global_history.update({event["event_id"]: event for event in events})
        self.history.append(entry)
        if self.history_store is not None:
            self.history_store.append(entry, self._calibration_records(), frame=frame)
            self._history_latest_time = max(self._history_latest_time, entry["timestamp_seconds"])
            self.poll_history()
        return True

    def record_calibration(self, metadata):
        self.calibrations.append({"version": self.board.calibration_version,
                                  "source": deepcopy(metadata), "board": deepcopy(self.board),
                                  "reference_folder": self.reference_folder})
