"""Durable match observations and indexed per-unit reads; no model or UI imports."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
import json
from math import isfinite
from pathlib import Path
import sqlite3
from time import monotonic

from components.replay_frames import save_replay_frame


SCHEMA_VERSION = 2


def _step_frame_keys(entry):
    keys = {(entry["calibration_version"], entry["sequence"])} if entry.get("kind") == "registration" else set()
    keys.update((event["calibration_version"], event["end"]["sequence"])
                for event in entry.get("motion_events", []) if event["status"] == "completed")
    return keys


def _json(value):
    def convert(item):
        if isinstance(item, Path):
            return str(item)
        if hasattr(item, "tolist"):
            return item.tolist()
        raise TypeError(f"Unsupported history value: {type(item).__name__}")
    return json.dumps(value, ensure_ascii=False, allow_nan=False, default=convert)


class HistoryStore:
    """The owner thread appends/polls; one separate worker performs all writes.

    Pending entries are removed only after a successful transaction. They are
    retained across failures, including entries submitted during an active write.
    """

    def __init__(self, path, metadata, *, retry_seconds=5.0):
        if not isfinite(retry_seconds) or retry_seconds <= 0:
            raise ValueError("History retry interval must be finite and positive")
        self.path = Path(path)
        self.metadata = deepcopy(metadata)
        self.retry_seconds = retry_seconds
        self.saved_sequence = 0
        self.error = None
        self._pending = []
        self._frames = {}
        self._active_frames = {}
        self._calibrations = {}
        self._future = None
        self._batch_size = 0
        self._next_retry = 0.0
        self._closed = False
        self._writer = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="match-history")

    @property
    def pending_count(self):
        return len(self._pending)

    def append(self, entry, calibrations, *, frame=None):
        if self._closed:
            raise RuntimeError("History store is closed")
        self._pending.append(deepcopy(entry))
        self._calibrations.update({item["version"]: deepcopy(item) for item in calibrations})
        self._capture_frames(entry, frame)
        self.poll()

    def _capture_frames(self, entry, frame):
        capture = _step_frame_keys(entry) if entry.get("kind") == "registration" else set()
        for event in entry.get("motion_events", []):
            key = event["calibration_version"], event["end"]["sequence"]
            if event["status"] == "ongoing":
                self._active_frames[event["event_id"]] = key
            else:
                self._active_frames.pop(event["event_id"], None)
            if event["status"] in ("ongoing", "completed") and key[1] == entry["sequence"]:
                capture.add(key)
        if frame is not None:
            for key in capture - self._frames.keys():
                image = frame.copy()
                image.setflags(write=False)
                self._frames[key] = image
        self._prune_frames()

    def _prune_frames(self):
        needed = set(self._active_frames.values())
        for entry in self._pending:
            needed.update(_step_frame_keys(entry))
        self._frames = {key: image for key, image in self._frames.items() if key in needed}

    def capture_replay_frames(self):
        """Owner-thread capture; pixels are immutable copies of accepted inputs."""
        needed = set()
        for entry in self._pending:
            needed.update(_step_frame_keys(entry))
        return {key: image for key, image in self._frames.items() if key in needed}

    def _submit(self, count):
        self._batch_size = count
        entries = self._pending[:count]
        needed = set().union(*(_step_frame_keys(entry) for entry in entries))
        frames = {key: image for key, image in self._frames.items() if key in needed}
        self._future = self._executor.submit(self._write, entries, dict(self._calibrations), frames)

    def _complete(self, now):
        try:
            self._future.result()
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"
            self._next_retry = now + self.retry_seconds
        else:
            self.saved_sequence = self._pending[self._batch_size - 1]["sequence"]
            del self._pending[:self._batch_size]
            self.error = None
            self._prune_frames()
        self._future = None

    def poll(self, now=None):
        if self._closed:
            return
        now = monotonic() if now is None else now
        if self._future is not None and self._future.done():
            self._complete(now)
        if self._future is None and self._pending and now >= self._next_retry:
            self._submit(min(len(self._pending), 128))

    def close(self):
        """Drain one final batch; report failure without discarding pending memory."""
        if not self._closed:
            if self._future is not None:
                self._complete(monotonic())
            if self._pending:
                self._submit(len(self._pending))
                self._complete(monotonic())
            try:
                self._executor.submit(self._close_writer).result()
            finally:
                self._executor.shutdown(wait=True)
                self._closed = True
        return not self._pending

    def _open_writer(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=0.2)
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, SCHEMA_VERSION):
                raise ValueError(f"Unsupported history schema version: {version}")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS calibrations (version INTEGER PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS observations (
                    sequence INTEGER PRIMARY KEY, timestamp_seconds REAL NOT NULL,
                    calibration_version INTEGER NOT NULL REFERENCES calibrations(version),
                    payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS unit_history (
                    unit_id TEXT NOT NULL, sequence INTEGER NOT NULL REFERENCES observations(sequence),
                    timestamp_seconds REAL NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (unit_id, sequence));
                CREATE INDEX IF NOT EXISTS unit_time ON unit_history(unit_id, timestamp_seconds, sequence);
                CREATE TABLE IF NOT EXISTS motion_events (
                    event_id TEXT PRIMARY KEY, unit_id TEXT NOT NULL, kind TEXT NOT NULL,
                    start_seconds REAL NOT NULL, end_seconds REAL NOT NULL,
                    updated_sequence INTEGER NOT NULL REFERENCES observations(sequence), payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS motion_unit_time ON motion_events(unit_id, start_seconds, end_seconds);
            """)
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        except Exception:
            connection.close()
            raise
        return connection

    def _close_writer(self):
        # SQLite connections are opened and closed on the writer thread.
        writer, self._writer = self._writer, None
        if writer is not None:
            writer.close()

    def _write(self, entries, calibrations, frames):
        if self._writer is None:
            self._writer = self._open_writer()
        connection = self._writer
        try:
            with connection:
                connection.executemany("INSERT INTO metadata VALUES (?, ?) ON CONFLICT(key) DO NOTHING",
                                       [(key, _json(value)) for key, value in self.metadata.items()])
                connection.executemany("INSERT INTO calibrations VALUES (?, ?) ON CONFLICT(version) DO NOTHING",
                                       [(version, _json(value)) for version, value in calibrations.items()])
                for entry in entries:
                    header = {key: value for key, value in entry.items() if key not in ("units", "motion_events")}
                    connection.execute("INSERT INTO observations VALUES (?, ?, ?, ?) ON CONFLICT(sequence) DO NOTHING",
                                       (entry["sequence"], entry["timestamp_seconds"], entry["calibration_version"], _json(header)))
                    connection.executemany("INSERT INTO unit_history VALUES (?, ?, ?, ?) ON CONFLICT(unit_id, sequence) DO NOTHING",
                        [(unit_id, entry["sequence"], entry["timestamp_seconds"], _json(unit))
                         for unit_id, unit in entry["units"].items()])
                    connection.executemany("""INSERT INTO motion_events VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(event_id) DO UPDATE SET end_seconds=excluded.end_seconds,
                            updated_sequence=excluded.updated_sequence, payload=excluded.payload
                        WHERE excluded.updated_sequence >= motion_events.updated_sequence""",
                        [(event["event_id"], event["unit_id"], event["kind"], event["start"]["timestamp_seconds"],
                          event["end"]["timestamp_seconds"], event["updated_sequence"], _json(event))
                         for event in entry.get("motion_events", [])])
        except sqlite3.Error:
            self._close_writer()
            raise
        for key, frame in frames.items():
            save_replay_frame(self.path, key, frame)


def _reader(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=0.2)
    if connection.execute("PRAGMA user_version").fetchone()[0] not in (1, SCHEMA_VERSION):
        connection.close()
        raise ValueError("Unsupported or uninitialized history database")
    return connection


def read_unit_history(path, unit_id, *, start=None, end=None):
    """Read this instance by inclusive acceptance/edit clip-source seconds.

    Each result contains the observation header and just this unit's payload.
    Entries at equal times retain sequence order, including manual state edits.
    Geometry's observation_timestamp_seconds can be earlier than the record time.
    Reads see committed records only and never create a missing database.
    """
    if not isinstance(unit_id, str) or not unit_id.strip():
        raise ValueError("unit_id must be a non-empty string")
    for value in (start, end):
        if value is not None and (isinstance(value, bool) or not isfinite(value) or value < 0):
            raise ValueError("History time bounds must be finite non-negative seconds")
    if start is not None and end is not None and start > end:
        raise ValueError("History start must not exceed end")
    clauses, values = ["u.unit_id = ?"], [unit_id]
    for bound, operator in ((start, ">="), (end, "<=")):
        if bound is not None:
            clauses.append(f"u.timestamp_seconds {operator} ?")
            values.append(bound)
    with closing(_reader(path)) as connection:
        rows = connection.execute(
            "SELECT o.payload, u.payload FROM unit_history u JOIN observations o USING (sequence) WHERE "
            + " AND ".join(clauses) + " ORDER BY u.timestamp_seconds, u.sequence", values)
        return [{**json.loads(header), "units": {unit_id: json.loads(unit)}} for header, unit in rows]


def read_history_context(path):
    """Read the initial catalog/source and effective calibrations, without scans of other units."""
    with closing(_reader(path)) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        metadata = {key: json.loads(payload) for key, payload in connection.execute("SELECT key, payload FROM metadata")}
        calibrations = [json.loads(payload) for (payload,) in connection.execute("SELECT payload FROM calibrations ORDER BY version")]
    return {"schema_version": version, "metadata": metadata, "calibrations": calibrations}


def read_motion_events(path, unit_id, *, start=None, end=None):
    """Read events overlapping an inclusive geometry-source time range.

    Unlike local-record query times, these bounds refer to actual observed
    poses, not acceptance/edit times. Ongoing and interrupted records are
    returned with explicit status; they are not completed moves. v1 has none.
    """
    if not isinstance(unit_id, str) or not unit_id.strip():
        raise ValueError("unit_id must be a non-empty string")
    for value in (start, end):
        if value is not None and (isinstance(value, bool) or not isfinite(value) or value < 0):
            raise ValueError("History time bounds must be finite non-negative seconds")
    if start is not None and end is not None and start > end:
        raise ValueError("History start must not exceed end")
    clauses, values = ["unit_id = ?"], [unit_id]
    for bound, column, operator in ((start, "end_seconds", ">="), (end, "start_seconds", "<=")):
        if bound is not None:
            clauses.append(f"{column} {operator} ?")
            values.append(bound)
    with closing(_reader(path)) as connection:
        if connection.execute("PRAGMA user_version").fetchone()[0] == 1:
            return []
        rows = connection.execute("SELECT payload FROM motion_events WHERE " + " AND ".join(clauses)
                                  + " ORDER BY start_seconds, updated_sequence, event_id", values)
        return [json.loads(payload) for (payload,) in rows]


def read_event_history(path, event_id):
    """Read one event and its local evidence through the latest update/confirmation.

    Samples are referenced by sequence, so delayed geometry, manual edits and
    parallel event ranges retain their original records without duplicating data.
    The final sample may be an interruption rather than valid motion evidence.
    Source-based events may span calibrations; legacy events retain their
    original single-calibration evidence boundary.
    """
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("event_id must be a non-empty string")
    with closing(_reader(path)) as connection:
        if connection.execute("PRAGMA user_version").fetchone()[0] == 1:
            raise KeyError(f"Event not found: {event_id}")
        row = connection.execute("SELECT payload FROM motion_events WHERE event_id=?", (event_id,)).fetchone()
        if row is None:
            raise KeyError(f"Event not found: {event_id}")
        event = json.loads(row[0])
        unit_id = event["unit_id"]
        values = [unit_id, event["start"]["sequence"], event["updated_sequence"]]
        version_filter = ""
        if event.get("coordinate_basis") != "source_image_pixels":
            version_filter = " AND o.calibration_version=?"
            values.append(event["calibration_version"])
        rows = connection.execute("""SELECT o.payload, u.payload FROM unit_history u
            JOIN observations o USING (sequence) WHERE u.unit_id=? AND u.sequence BETWEEN ? AND ?"""
            + version_filter + " ORDER BY u.sequence", values)
        records = [{**json.loads(header), "units": {unit_id: json.loads(unit)}} for header, unit in rows]
    return {"event": event, "records": records}
