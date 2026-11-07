"""Read-only, discrete replay of one registration's recorded board scenes.

Capture inputs on the history owner's thread, then build/read the index and
recorded step images on a background reader using the captured boundary.
"""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
import json
from math import isfinite
from pathlib import Path
import re
import sqlite3

import cv2

from components.image_io import load_image
from components.replay_frames import replay_frame_path


class ReplayError(ValueError):
    """The captured registration cannot be replayed completely or consistently."""


@dataclass(frozen=True)
class ReplayInputs:
    path: Path | None
    cutoff_sequence: int
    history: tuple = ()
    events: tuple = ()
    metadata: dict = field(default_factory=dict)
    calibrations: tuple = ()
    frames: dict = field(default_factory=dict)


class ReplayIndex:
    """Detached navigation boundary; only endpoint memory records are retained.

    Public mappings are returned as copies. SQLite observation rows are immutable
    by sequence, so later endpoint reads retain this index's captured boundary.
    """

    def __init__(self, path, cutoff_sequence, schema_version, steps, memory, metadata, calibrations, frames=None):
        self.path = path
        self.cutoff_sequence = cutoff_sequence
        self.schema_version = schema_version
        self._steps = tuple(deepcopy(steps))
        self._memory = deepcopy(memory)
        self._metadata = deepcopy(metadata)
        self._calibrations = deepcopy(calibrations)
        self._frames = dict(frames or {})

    @property
    def steps(self):
        return deepcopy(self._steps)

    @property
    def metadata(self):
        return deepcopy(self._metadata)

    def __len__(self):
        return len(self._steps)


def capture_replay_inputs(data):
    """Owner-thread capture of the current registration, without flushing writes.

    Only the writer's public path/metadata are read. History and global event
    caches include the owner's unsaved records; missing older records must be
    recovered from disk rather than silently dropping the start of the match.
    """
    store = data.history_store
    if store is None:
        raise ReplayError("Complete registration before opening replay")
    return ReplayInputs(
        path=Path(store.path).resolve(), cutoff_sequence=data._history_sequence,
        history=tuple(deepcopy(data.history)), events=tuple(deepcopy(list(data.global_history.values()))),
        metadata=deepcopy(store.metadata), calibrations=tuple(deepcopy(data._calibration_records())),
        frames=store.capture_replay_frames(),
    )


def _integer(value, name, minimum=1):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ReplayError(f"{name} must be an integer >= {minimum}")
    return value


def _seconds(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ReplayError(f"{name} must be finite non-negative source seconds")
    return value


def _mapping(payload, name):
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ReplayError(f"Invalid {name}: expected a JSON object")
    return value


@contextmanager
def _database(path):
    connection = None
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.2)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (1, 2):
            raise ReplayError(f"Unsupported or uninitialized replay history schema: {version}")
        yield connection, version
    finally:
        if connection is not None:
            connection.close()


def _disk_record(connection, sequence, unit_ids=None):
    row = connection.execute(
        "SELECT payload, calibration_version FROM observations WHERE sequence=?", (sequence,)).fetchone()
    if row is None:
        raise ReplayError(f"Replay observation {sequence} is missing from disk and captured memory")
    entry = _mapping(row[0], "observation")
    if entry.get("sequence") != sequence or entry.get("calibration_version") != row[1]:
        raise ReplayError(f"Replay observation {sequence} has inconsistent sequence/calibration")
    if unit_ids is None:
        rows = connection.execute(
            "SELECT unit_id, payload FROM unit_history WHERE sequence=? ORDER BY unit_id", (sequence,))
    else:
        # Registration fixes the roster; use its IDs to seek the existing PK.
        rows = ((unit_id, row[0]) for unit_id in unit_ids for row in connection.execute(
            "SELECT payload FROM unit_history WHERE unit_id=? AND sequence=?", (unit_id, sequence)))
    entry["units"] = {unit_id: _mapping(payload, "unit history") for unit_id, payload in rows}
    return entry


def _merge_event(events, event, cutoff):
    if not isinstance(event, dict):
        raise ReplayError("Invalid motion event")
    updated = _integer(event.get("updated_sequence"), "Event update sequence")
    if updated > cutoff:
        return
    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        raise ReplayError("Motion event ID is missing")
    previous = events.get(event_id)
    if previous is None or updated >= previous["updated_sequence"]:
        events[event_id] = deepcopy(event)


def _event_key(event, cutoff):
    endpoint = event.get("end")
    if not isinstance(endpoint, dict):
        raise ReplayError(f"Completed event {event['event_id']} has no endpoint")
    sequence = _integer(endpoint.get("sequence"), "Event endpoint sequence")
    if sequence > cutoff:
        raise ReplayError(f"Completed event {event['event_id']} ends beyond the captured history")
    stamp = _seconds(endpoint.get("timestamp_seconds"), "Event endpoint time")
    if event.get("confirmed_sequence", event["updated_sequence"]) > cutoff:
        raise ReplayError(f"Completed event {event['event_id']} was confirmed beyond the captured history")
    if sequence > event["updated_sequence"]:
        raise ReplayError(f"Completed event {event['event_id']} predates its endpoint record")
    _integer(event.get("calibration_version"), "Event calibration version", 0)
    if not isinstance(event.get("unit_id"), str) or not event["unit_id"]:
        raise ReplayError(f"Completed event {event['event_id']} has no unit ID")
    number = re.fullmatch(r"E(\d+)", event["event_id"])
    if number is None:
        raise ReplayError(f"Invalid motion event ID: {event['event_id']}")
    return stamp, 0 if event["kind"] == "translation" else 1, sequence, int(number[1]), event["event_id"]


def _calibration_map(records):
    result = {}
    for item in records:
        if not isinstance(item, dict):
            raise ReplayError("Invalid replay calibration record")
        version = _integer(item.get("version"), "Calibration version", 0)
        result[version] = deepcopy(item)
    return result


def _scene(index, step, observation):
    sequence = step["end_sequence"]
    if observation.get("sequence") != sequence or sequence > index.cutoff_sequence:
        raise ReplayError(f"Replay observation {sequence} does not match the selected endpoint")
    version = _integer(observation.get("calibration_version"), "Observation calibration version", 0)
    event = step["event"]
    if event is not None and (event["calibration_version"] != version
                             or event["end"].get("calibration_version", version) != version):
        raise ReplayError(f"Event {event['event_id']} and endpoint calibration disagree")
    calibration = index._calibrations.get(version)
    if calibration is None:
        raise ReplayError(f"Calibration v{version} required by replay observation {sequence} is missing")
    board = calibration.get("board")
    if not isinstance(board, dict):
        raise ReplayError(f"Calibration v{version} has no board mapping")
    dimensions = board.get("board_size_mm")
    if dimensions is None or len(dimensions) != 2 or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0
            for value in dimensions):
        raise ReplayError(f"Calibration v{version} has invalid board dimensions")
    if not isinstance(observation.get("units"), dict):
        raise ReplayError(f"Replay observation {sequence} has no unit mapping")
    # Keep original payloads, including unavailable/removed IDs and empty geometry.
    # Renderers must honour position_status/active rather than reuse older corners.
    return deepcopy({"step": step, "observation": observation, "calibration": calibration,
                     "board_size_mm": list(dimensions), "units": observation["units"],
                     "metadata": index._metadata})


def read_replay_index(inputs):
    """Background read of completed events at a fixed owner-thread high water mark.

    Step 0 is observation 1 (initial registration). Each later step references
    its event's whole-board end.sequence, never its confirmation record. Ordering
    is geometry end time, Move before Rotate, end sequence, numeric event ID.
    Ongoing/interrupted events are excluded. Equal endpoints remain distinct.
    """
    try:
        return _read_index(inputs)
    except ReplayError:
        raise
    except (OSError, sqlite3.Error, TypeError, KeyError, ValueError, OverflowError) as error:
        raise ReplayError(f"Cannot read replay history: {error}") from error


def _read_index(inputs):
    cutoff = _integer(inputs.cutoff_sequence, "Replay cutoff sequence")
    path = Path(inputs.path).resolve() if inputs.path is not None else None
    memory = {}
    for entry in inputs.history:
        if not isinstance(entry, dict):
            raise ReplayError("Invalid replay history record")
        sequence = _integer(entry.get("sequence"), "History sequence")
        if sequence <= cutoff:
            memory[sequence] = deepcopy(entry)
    events, metadata, calibrations = {}, {}, {}
    schema_version = 2
    initial = memory.get(1)
    if path is not None:
        try:
            with _database(path) as (connection, schema_version):
                metadata = {key: json.loads(payload) for key, payload in connection.execute("SELECT key, payload FROM metadata")}
                calibrations = _calibration_map(_mapping(payload, "calibration") for (payload,) in connection.execute(
                    "SELECT payload FROM calibrations ORDER BY version"))
                disk_count = connection.execute(
                    "SELECT COUNT(*) FROM observations WHERE sequence BETWEEN 1 AND ?", (cutoff,)).fetchone()[0]
                # Count the union without loading every raw observation or sequence.
                memory_only = set(memory)
                keys = list(memory)
                for start in range(0, len(keys), 500):
                    batch = keys[start:start + 500]
                    memory_only.difference_update(row[0] for row in connection.execute(
                        "SELECT sequence FROM observations WHERE sequence IN (" + ",".join("?" for _ in batch) + ")", batch))
                if disk_count + len(memory_only) != cutoff:
                    raise ReplayError("Replay history has gaps before the captured cutoff; cannot truncate old history")
                if initial is None:
                    initial = _disk_record(connection, 1)
                if schema_version >= 2:
                    for event_id, updated, payload in connection.execute(
                            "SELECT event_id, updated_sequence, payload FROM motion_events WHERE updated_sequence<=?", (cutoff,)):
                        event = _mapping(payload, "motion event")
                        if event.get("event_id") != event_id or event.get("updated_sequence") != updated:
                            raise ReplayError(f"Motion event {event_id} has inconsistent identity/update sequence")
                        _merge_event(events, event, cutoff)
        except (ReplayError, OSError, sqlite3.Error, TypeError, KeyError, ValueError):
            if len(memory) != cutoff:
                raise
            # A first write may have created the file before its schema/commit.
            # Complete captured history is sufficient without any disk content.
            metadata, calibrations, events = {}, {}, {}
            schema_version = 2
            initial = memory[1]
    elif len(memory) != cutoff:
        raise ReplayError("Replay database is unavailable and captured memory does not contain complete history 1..cutoff")
    metadata.update(deepcopy(inputs.metadata))
    calibrations.update(_calibration_map(inputs.calibrations))
    for entry in sorted(memory.values(), key=lambda row: row["sequence"]):
        for event in entry.get("motion_events", []):
            _merge_event(events, event, cutoff)
    for event in inputs.events:
        _merge_event(events, event, cutoff)
    completed = [event for event in events.values()
                 if event.get("status") == "completed" and event.get("kind") in ("translation", "rotation")]
    completed.sort(key=lambda event: _event_key(event, cutoff))
    stamp = initial.get("observation_timestamp_seconds", initial.get("timestamp_seconds"))
    steps = [{"index": 0, "event_id": None, "unit_id": None, "kind": "registration", "label": "Initial registration",
              "end_timestamp_seconds": _seconds(stamp, "Initial registration time"), "end_sequence": 1, "event": None}]
    for event in completed:
        steps.append({"index": len(steps), "event_id": event["event_id"], "unit_id": event["unit_id"],
                      "kind": event["kind"], "label": "Move" if event["kind"] == "translation" else "Rotate",
                      "end_timestamp_seconds": event["end"]["timestamp_seconds"],
                      "end_sequence": event["end"]["sequence"], "event": event})
    endpoints = {step["end_sequence"] for step in steps}
    retained = {sequence: entry for sequence, entry in memory.items() if sequence in endpoints}
    retained[1] = initial
    frame_keys = {(step["event"]["calibration_version"], step["end_sequence"])
                  for step in steps if step["event"] is not None}
    frame_keys.add((initial["calibration_version"], 1))
    frames = {key: image for key, image in inputs.frames.items() if key in frame_keys}
    index = ReplayIndex(path, cutoff, schema_version, steps, retained, metadata, calibrations, frames)
    _scene(index, steps[0], initial)
    return index


def read_replay_scene(index, step_index):
    """Lazily load one endpoint; return detached H02 data and its exact calibration.

    The original observation distinguishes acceptance/manual time from geometric
    observation time. Unit IDs, attributes, statuses and corners are preserved;
    no interpolation or geometry synthesis is performed.
    """
    try:
        _integer(step_index, "Replay step index", 0)
        if step_index >= len(index):
            raise ReplayError(f"Replay step {step_index} is outside 0..{len(index) - 1}")
        step = index._steps[step_index]
        sequence = step["end_sequence"]
        if sequence in index._memory:
            observation = index._memory[sequence]
        else:
            if index.path is None:
                raise ReplayError(f"No disk history for replay observation {sequence}")
            with _database(index.path) as (connection, _):
                observation = _disk_record(connection, sequence, index._memory[1]["units"])
        scene = _scene(index, step, observation)
        key = observation["calibration_version"], sequence
        scene["background"] = index._frames.get(key)
        if scene["background"] is None:
            try:
                scene["background"] = load_image(replay_frame_path(index.path, key)) if index.path is not None else None
            except (OSError, ValueError, cv2.error):
                scene["background"] = None
        if scene["background"] is None:
            scene["background_note"] = "Step image unavailable."
        return scene
    except ReplayError:
        raise
    except (OSError, sqlite3.Error, TypeError, KeyError, ValueError, OverflowError) as error:
        raise ReplayError(f"Cannot read replay scene: {error}") from error
