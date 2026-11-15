"""Internal missing episodes and post-search human requests, independent of the visible tool."""
from copy import deepcopy
import json
from pathlib import Path
from threading import Event

from . import config


class AutomaticRecovery:
    def __init__(self, session):
        self._session = session
        self.records = {}
        self.batch = None

    @property
    def enabled(self):
        return config.AUTO_RECOVERY_ENABLED and self._session.worker.tracker_name == "edgetam"

    def _phase(self, uid, phase, note):
        state = self._session.data.tracking.get(uid)
        if state is not None:
            changed = (state.recovery_phase, state.recovery_note) != (phase, note)
            state.recovery_phase, state.recovery_note = phase, note
            if changed and self._session.data.reference_folder is not None:
                entry = {"unit_id": uid, "phase": phase, "reason": note,
                         "source": self._session.source.metadata(), "generation": self._session.generation,
                         "observation": self._session.data.current.prediction_metadata,
                         "diagnostics": self.records.get(uid, {}).get("diagnostics")}
                try:
                    path = Path(self._session.data.reference_folder) / "automatic_recovery.jsonl"
                    with path.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
                except OSError as error:
                    print(f"Automatic recovery log could not be written: {error}", flush=True)
        self._session.mark_changed()

    def observe(self):
        data = self._session.data
        failed = {uid for uid, state in data.tracking.items() if state.active and state.status == "failed"}
        for uid in list(self.records):
            if uid not in failed:
                if self.batch is not None and uid in {target["unit_id"] for target in self.batch["targets"]}:
                    self.invalidate("Missing set changed during search")
                record = self.records.pop(uid)
                if record.get("candidate") is not None:
                    record["candidate"].cancel()
                self._phase(uid, None, None)
        for uid, record in self.records.items():
            if record.get("candidate") is not None and record["candidate"].cancelled.is_set():
                record["candidate"] = record["preview"] = None
                self._phase(uid, "manual", "Candidate was invalidated; manual input required")
        if not self.enabled or not self._session.registration_locked:
            return
        for uid in failed - self.records.keys():
            self.records[uid] = {}
            self._phase(uid, "queued", "Waiting for one automatic search")

    def take_request(self):
        session, data = self._session, self._session.data
        if not self.enabled or self.batch is not None or not session.worker.tracker_initialized or session.model_failed:
            return None
        ids = [uid for uid in self.records if data.tracking[uid].recovery_phase == "queued"]
        if not ids or data.current.prediction is None or data.current.prediction_metadata is None:
            return None
        # All currently missing references guard identity conflicts; only queued IDs get a new attempt.
        targets = [{"unit_id": uid, "object_id": obj} for obj, uid in data.units.bindings.items()
                   if uid in self.records and data.tracking[uid].active and data.tracking[uid].status == "failed"]
        normal = [obj for obj, uid in data.units.bindings.items()
                  if data.tracking.get(uid) is not None and data.tracking[uid].active and data.tracking[uid].status == "tracking"]
        self.batch = {"cancelled": Event(), "unit_ids": ids, "targets": targets,
                      "reference_folder": str(data.reference_folder), "normal_ids": normal,
                      "similarity": config.AUTO_RECOVERY_SIMILARITY, "margin": config.AUTO_RECOVERY_MARGIN,
                      "prompt": config.AUTO_RECOVERY_PROMPT, "detection_threshold": config.AUTO_RECOVERY_DETECTION_THRESHOLD}
        for uid in ids:
            self._phase(uid, "searching", "Automatic search in progress")
        return "automatic_recovery", {"frame": data.current.prediction_frame,
                                     "metadata": deepcopy(data.current.prediction_metadata),
                                     "raw_frame": session.prediction_raw_frame, "generation": session.generation,
                                     "prediction": data.current.prediction, "automatic_request": self.batch}

    def valid(self, request):
        return (request.get("automatic_request") is self.batch and self.batch is not None
                and not self.batch["cancelled"].is_set()
                and request["metadata"].get("calibration_version") == self._session.data.board.calibration_version)

    def accept(self, request, error=None):
        if not self.valid(request):
            for row in request.get("automatic_rows", []):
                if row.get("candidate") is not None:
                    row["candidate"].cancel()
            return
        batch, self.batch = self.batch, None
        rows = {row["unit_id"]: row for row in request.get("automatic_rows", [])}
        for uid in batch["unit_ids"]:
            state = self._session.data.tracking.get(uid)
            if uid not in self.records or state is None or not state.active or state.status != "failed":
                continue
            row = rows.get(uid, {})
            candidate = row.get("candidate")
            self.records[uid] = {"candidate": candidate,
                                 "preview": {"prediction": candidate.prediction, "metadata": deepcopy(request["metadata"])}
                                 if candidate is not None else None,
                                 "diagnostics": {key: row.get(key) for key in ("scores", "top_two_margin", "reason",
                                                                             "candidate_id", "candidate_ids")}}
            self._phase(uid, "review" if candidate is not None else "manual",
                        str(error) if error is not None else row.get("reason", "Automatic search could not recover this unit"))

    def candidates(self):
        return list({id(record["candidate"]): record["candidate"] for record in self.records.values()
                     if record.get("candidate") is not None and not record["candidate"].cancelled.is_set()}.values())

    def accept_propagation(self, request):
        for candidate, prediction, error in request.get("automatic_updates", []):
            for uid, record in self.records.items():
                if record.get("candidate") is not candidate:
                    continue
                if error is not None or prediction is None or not prediction["masks"][0].any():
                    candidate.cancel()
                    record["candidate"] = record["preview"] = None
                    self._phase(uid, "manual", f"Candidate unavailable: {error or 'No mask'}")
                else:
                    record["preview"] = {"prediction": prediction, "metadata": deepcopy(request["metadata"])}

    def take_candidate(self, uid):
        record = self.records.get(uid, {})
        candidate, preview = record.get("candidate"), record.get("preview")
        if candidate is None or candidate.cancelled.is_set() or preview is None:
            return None
        # A competing candidate can be reviewed for one ID at a time, never cloned into two identities.
        for other, row in self.records.items():
            if row.get("candidate") is candidate:
                row["candidate"] = row["preview"] = None
                self._phase(other, "manual", "Candidate transferred to manual review")
        return candidate, preview, record.get("diagnostics", {})

    def retry(self, uid):
        state = self._session.data.tracking.get(uid)
        if uid not in self.records or state is None or not state.active or state.status != "failed":
            return
        record = self.records[uid]
        if record.get("candidate") is not None:
            record["candidate"].cancel()
        self.records[uid] = {}
        self._phase(uid, "queued", "User requested one new automatic search")

    def invalidate(self, reason, *, reset=False):
        if self.batch is not None:
            self.batch["cancelled"].set()
            self.batch = None
        for uid, record in self.records.items():
            if record.get("candidate") is not None:
                record["candidate"].cancel()
            record["candidate"] = record["preview"] = None
            self._phase(uid, None if reset else "manual", reason)
        if reset:
            self.records.clear()
