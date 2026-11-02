"""Shared data for one match; model sessions and UI controls live elsewhere."""

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from components.registration.units import UnitRoster
from components.registration.rule_state import RuleState


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
    reference_folder: Path | None = None

    def accept_observation(self, prediction, frame, metadata):
        """Accept a completed result with its matching image and source time."""
        self.current.prediction = prediction
        self.current.prediction_frame = frame
        self.current.prediction_metadata = metadata
        self.rules.observe(prediction, metadata["frame_index"])

    def snapshot(self):
        """Freeze one observation without copying the growing match history."""
        current = self.current
        frame = current.prediction_frame if current.prediction is not None else current.frame
        frame = None if frame is None else frame.copy()
        return GameData(
            board=deepcopy(self.board), units=deepcopy(self.units), rules=deepcopy(self.rules),
            current=CurrentData(frame=frame, prediction=deepcopy(current.prediction),
                                prediction_frame=frame if current.prediction is not None else None,
                                prediction_metadata=deepcopy(current.prediction_metadata),
                                view_revision=current.view_revision),
            reference_folder=self.reference_folder,
        )

    def record_history(self):
        """Copy rectangle positions and current states; never retain frame/mask arrays."""
        current = self.current
        if self.units is None or current.prediction is None or current.prediction_metadata is None:
            return False
        units = {}
        for object_id, unit_id in self.units.bindings.items():
            unit = self.units.units[unit_id]
            profile = {**self.units.types[unit["type_id"]].get("attributes", {}), **unit["attributes"]}
            tray = current.prediction.get("trays", {}).get(object_id)
            units[unit_id] = {
                "corners_mm": deepcopy(tray["corners_plane"]) if tray is not None else None,
                "position_status": "available" if tray is not None else "unavailable",
                "state": {"engaged": deepcopy(profile.get("engaged")),
                          "wavering": deepcopy(profile.get("wavering")),
                          "facing": deepcopy(self.rules.fronts.get(object_id))},
            }
        entry = {"calibration_version": self.board.calibration_version,
                 "frame_index": current.prediction_metadata["frame_index"],
                 "timestamp_seconds": current.prediction_metadata.get("timestamp_seconds"), "units": units}
        if self.history and self.history[-1] == entry:
            return False
        self.history.append(entry)
        return True

    def record_calibration(self, metadata):
        self.calibrations.append({"version": self.board.calibration_version,
                                  "source": deepcopy(metadata), "board": deepcopy(self.board),
                                  "reference_folder": self.reference_folder})
