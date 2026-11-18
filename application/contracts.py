"""Published match data: detached metadata, shared read-only image storage."""
from dataclasses import dataclass
from functools import wraps
from types import MappingProxyType
from collections.abc import Mapping

import numpy as np


def freeze(value):
    if isinstance(value, np.ndarray):
        result = value.view()
        result.flags.writeable = False
        return result
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(value)
    return value


@dataclass(frozen=True)
class FrameRef:
    generation: int
    frame_index: int
    timestamp_seconds: float
    source_size: tuple
    calibration_version: int


@dataclass(frozen=True)
class CommandReceipt:
    status: str
    reason: str = ""
    request_id: int | None = None
    value: object = None


def command(method):
    """Normalize external command failures; internal contract errors still surface."""
    @wraps(method)
    def invoke(*args, **kwargs):
        try:
            result = method(*args, **kwargs)
        except (ValueError, OSError) as error:
            return CommandReceipt("rejected", str(error))
        return result if isinstance(result, CommandReceipt) else CommandReceipt("accepted", value=result)
    return invoke


@dataclass(frozen=True)
class BoardSnapshot:
    calibration_version: int
    source_size: tuple
    board_size_mm: tuple
    source_to_plane: object
    image_to_plane: object
    homography: object
    table_boundary: object


@dataclass(frozen=True)
class CurrentSnapshot:
    frame: object
    prediction: object
    prediction_frame: object
    prediction_metadata: object
    view_revision: int
    geometry_frame: object = None
    geometry_revision: int = 0


@dataclass(frozen=True)
class RosterSnapshot:
    types: object
    units: object
    bindings: object
    counters: object
    payload: object
    source: object
    next_ids: object

    def next_unit_id(self, type_id):
        return self.next_ids[type_id]


@dataclass(frozen=True)
class RulesSnapshot:
    fronts: object
    terrain: object
    track_facing: bool = True


@dataclass(frozen=True)
class TrackingSnapshot:
    status: str
    visibility: bool | None
    disappeared_time: float | None
    frame_index: int
    timestamp_seconds: float | None
    calibration_version: int
    active: bool
    last_accepted_position: object
    recovery_phase: str | None
    recovery_note: str | None
    recovery_update_error: str | None = None


@dataclass(frozen=True)
class MatchSnapshot:
    revision: int
    stage: str
    mode: str
    source_ref: FrameRef
    source_image: object
    observation_ref: FrameRef | None
    board: BoardSnapshot
    current: CurrentSnapshot
    units: RosterSnapshot
    rules: RulesSnapshot
    tracking: object
    reference_folder: object
    fps: float
    end_index: int
    playing: bool
    pending_play: bool
    closed: bool
    registration_locked: bool
    startup_ready: bool
    model_failed: bool
    model_loaded: bool
    tracker_name: str
    tracker_initialized: bool
    facing_error: str | None
    load_progress: object
    inference_fps: float | None
    history_warning: str | None
    tray_status: str
    note: str
    registration_prompts: object
    recovery: object
    registration_unconfirmed: tuple[int, ...] = ()
