"""Owner-thread recovery drafts; inference stays on the shared serial worker."""
from copy import deepcopy

from components.tracking.recovery import RecoveryCandidate
from components.homography import transform_points


class RecoveryController:
    def __init__(self, session):
        self.session = session
        self.active = self.picking_error = self.committing = False
        self.candidate = self.preview = self.pending_prompt = self.pending_binding = None
        self.reported = set()
        self.review_unit_id = None
        self.note = "Add positive / negative points, then drag an existing ID onto the candidate."
        session.recovery = self

    @property
    def busy(self):
        request = self.session.worker.request
        return (self.pending_prompt is not None or self.committing
                or (request is not None and request.get("recovery_candidate") is self.candidate
                    and request["kind"] in ("recovery_seed", "recovery_point")))

    def open(self, unit_id=None):
        if (not self.session.registration_locked or not self.session.worker.tracker_initialized
                or self.session.worker.tracker_name != "edgetam" or self.session.model_failed):
            raise ValueError("Manual recovery requires a registered, running EdgeTAM session.")
        if self.committing:
            raise ValueError("Wait for the confirmed recovery to finish.")
        self.cancel()
        self.session.presented_frame = None
        self.active = True
        self.note = "Left: positive | Right: negative | Drag an existing ID to confirm."
        offers = self.session.automatic_recovery.records
        selected = unit_id or next((uid for uid in offers if offers[uid].get("candidate") is not None), None)
        if selected is not None:
            if not self.select_unit(selected):
                state = self.session.data.tracking.get(selected)
                if state is not None and state.recovery_note:
                    self.note = f"{selected}: {state.recovery_note}. Add points to create a manual candidate."
        self.session.mark_changed()

    def clear_candidate(self):
        if self.committing:
            return
        if self.candidate is not None:
            self.candidate.cancel()
        self.candidate = self.preview = self.pending_prompt = None
        self.review_unit_id = None
        self.picking_error = False
        self.note = "Candidate cleared. Add a positive point to retry."
        self.session.mark_changed()

    def cancel(self, *, force=False):
        self.active = self.picking_error = False
        self.review_unit_id = None
        self.reported.clear()
        if self.candidate is not None:
            self.candidate.cancel()
        if self.pending_binding is not None:
            self.pending_binding = None
            self.committing = False
        if force:
            self.committing = False
        if not self.committing:
            self.candidate = self.preview = self.pending_prompt = None

    def labels(self):
        data = self.session.data
        return [unit_id for unit_id, state in data.tracking.items()
                if state.active and ((state.status == "failed" and state.recovery_phase not in ("queued", "searching"))
                                     or unit_id in self.reported)]

    def select_unit(self, unit_id):
        if self.busy or unit_id not in self.labels():
            return False
        offered = self.session.automatic_recovery.take_candidate(unit_id)
        if offered is None:
            return False
        self.clear_candidate()
        self.candidate, self.preview, diagnostics = offered
        self.review_unit_id = unit_id
        scores = diagnostics.get("scores") or []
        score = f"{scores[0]:.3f}" if scores else "unknown"
        self.note = f"Proposed {unit_id} | seed cosine {score}. Correct confirms; No starts one new search."
        return True

    def reject(self):
        if self.busy or self.review_unit_id is None:
            return
        uid = self.review_unit_id
        self.cancel()
        self.session.automatic_recovery.retry(uid)
        self.session.mark_changed()

    def report_error(self, object_id):
        data = self.session.data
        unit_id = data.units.bindings.get(object_id)
        state = data.tracking.get(unit_id)
        if unit_id is None or state is None or not state.active:
            raise ValueError("Pick a currently registered, active unit mask.")
        if unit_id in self.session.automatic_recovery.records:
            self.session.automatic_recovery.invalidate("Operator requested manual correction")
        self.reported.add(unit_id)
        self.picking_error = False
        self.note = f"Draft correction for {unit_id}. Original tracking continues until confirmation."
        self.session.mark_changed()

    def point(self, point, positive):
        snapshot = self.session.presented_frame
        if self.busy:
            self.note = "Wait for the candidate update; playback continues."
            return
        if not self.active or snapshot is None:
            return
        if self.candidate is None:
            if not positive:
                self.note = "Start a candidate with a positive point."
                return
            self.candidate = RecoveryCandidate()
            kind = "recovery_seed"
        else:
            if self.preview is None:
                self.note = "Clear / Retry to create a new candidate."
                return
            kind = "recovery_point"
        self.pending_prompt = {"kind": kind, "snapshot": snapshot,
                               "point": list(map(float, point)), "positive": bool(positive),
                               "point_source": transform_points(point, self.session.data.board.homography["inverse_matrix"]).tolist()}
        self.note = "Updating candidate; source playback continues."
        self.session.mark_changed()

    def bind(self, unit_id):
        if self.busy or unit_id not in self.labels() or self.preview is None:
            raise ValueError("Wait for a current candidate and drag an available existing ID.")
        if not self.preview["prediction"]["masks"][0].any():
            raise ValueError("Candidate is missing. Add points or Clear / Retry.")
        object_id = next(obj for obj, unit in self.session.data.units.bindings.items() if unit == unit_id)
        self.pending_binding = object_id
        self.committing = True
        self.picking_error = False
        self.note = f"Applying recovery for {unit_id}; playback continues."
        self.session.mark_changed()

    def take_request(self):
        if self.pending_prompt is not None:
            pending, self.pending_prompt = self.pending_prompt, None
            snapshot = pending["snapshot"]
            return pending["kind"], {**snapshot, "recovery_candidate": self.candidate,
                                     "prompt": {"point": pending["point"], "positive": pending["positive"],
                                                "point_source": pending["point_source"]}}
        if self.pending_binding is not None:
            data = self.session.data
            observed = data.current.prediction_metadata
            if observed is None:
                return None
            if observed["frame_index"] < self.candidate.backend.source_frame:
                snapshot = self.session.presented_frame
                if snapshot is None or snapshot["metadata"]["frame_index"] <= self.session.worker.tracker.source_frame:
                    return None
                # Align normal masks too, including when confirming at the end of the video.
                return "propagate", {**snapshot, "recovery_candidate": self.candidate,
                                     "automatic_candidates": self.session.automatic_recovery.candidates()}
            snapshot = {"frame": data.current.prediction_frame, "metadata": deepcopy(observed),
                        "raw_frame": self.session.prediction_raw_frame, "generation": self.session.generation}
            object_id, self.pending_binding = self.pending_binding, None
            normal = [obj for obj, uid in self.session.data.units.bindings.items()
                      if obj != object_id and self.session.data.tracking.get(uid) is not None
                      and self.session.data.tracking[uid].active and self.session.data.tracking[uid].status == "tracking"]
            return "recovery_commit", {**snapshot, "recovery_candidate": self.candidate, "recovery_object_id": object_id,
                                       "prediction": self.session.data.current.prediction,
                                       "prompt": {"method": "reviewed" if self.review_unit_id is not None else "manual",
                                                  "normal_ids": normal}}
        return None

    def for_propagation(self):
        return self.candidate if self.active and self.preview is not None and not self.busy else None

    def accept(self, request, prediction, error=None):
        candidate = request.get("recovery_candidate")
        if candidate is not self.candidate:
            return
        if request["kind"] == "recovery_commit":
            self.committing = False
            if error is None and request.get("recovery_applied"):
                self.cancel()
                self.session.note = "Unit recovered with its original ID. Facing is unknown."
            elif not candidate.cancelled.is_set():
                self.preview = None
                self.note = f"Recovery not applied: {error}. Clear / Retry."
            else:
                self.cancel()
        elif self.active and not candidate.cancelled.is_set():
            if error is not None:
                self.preview = None
                self.note = f"Candidate error: {error}. Clear / Retry."
            elif prediction is not None:
                self.preview = {"prediction": prediction, "metadata": deepcopy(request["metadata"])}
                self.note = ((f"Review {self.review_unit_id}: Correct confirms; No starts one new search."
                              if self.review_unit_id is not None else "Drag an existing ID onto the candidate to confirm.")
                             if prediction["masks"][0].any() else "Candidate missing. Add points or Clear / Retry.")
        self.session.mark_changed()
