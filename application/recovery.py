"""Owner-thread recovery drafts; inference stays on the shared serial worker."""
from copy import deepcopy

import cv2
import numpy as np

from components.tracking.recovery import RecoveryCandidate
from components.homography import transform_points
from components.homography.geometry import order_corners
from .contracts import command, CommandReceipt, freeze


class Recovery:
    def __init__(self, session):
        self._session = session
        self.sample = None
        self.candidate_generation = 0
        self.active = self.committing = False
        self._candidate = self._preview = self.pending_prompt = self.pending_binding = None
        self.manual_target = None
        self.review_unit_id = None
        self.note = "Use Points, Rectangle, or Four corners to mark the unit, then click or drag its ID to confirm."
        session.recovery = self

    @property
    def preview(self):
        return freeze(self._preview)

    @property
    def busy(self):
        request = self._session.worker.request
        return (self.pending_prompt is not None or self.committing
                or (request is not None and request.get("recovery_candidate") is self._candidate
                    and request["kind"] in ("recovery_seed", "recovery_seed_mask", "recovery_point")))

    @command
    def open(self, unit_id=None, *, manual=False):
        if (self._session.closed or not self._session.registration_locked or not self._session.worker.tracker_initialized
                or self._session.worker.tracker_name != "edgetam" or self._session.model_failed):
            raise ValueError("Manual recovery requires a registered, running EdgeTAM session.")
        if self.committing:
            raise ValueError("Wait for the confirmed recovery to finish.")
        automatic = self._session.automatic_recovery
        if manual:
            self._take_over_manually(unit_id)
        self.cancel()
        self._session.presented_frame = None
        self.active = True
        if manual:
            return self._report_manual_target(unit_id)
        self.note = "Use Points, Rectangle, or Four corners, then click or drag an existing ID to confirm."
        offers = automatic.records
        selected = unit_id or next((uid for uid in offers if offers[uid].get("candidate") is not None), None)
        if selected is not None:
            if self.select_unit(selected).status != "accepted":
                state = self._session.data.tracking.get(selected)
                if state is not None and (reason := state.recovery_update_error or state.recovery_note):
                    self.note = f"{selected}: {reason}. Use Points, Rectangle, or Four corners to draw a candidate."
        self._session.mark_changed()
        return CommandReceipt("accepted")

    @command
    def clear_candidate(self):
        if self.committing:
            return CommandReceipt("rejected", self.note)
        if self._candidate is not None:
            self._candidate.cancel()
        self._candidate = self._preview = self.pending_prompt = None
        self.candidate_generation += 1
        self.review_unit_id = None
        self.note = "Candidate cleared. Add a positive point to retry."
        self._session.mark_changed()
        return CommandReceipt("accepted")

    @command
    def cancel(self, *, force=False):
        self.candidate_generation += 1
        self.active = False
        self.review_unit_id = None
        self.manual_target = None
        if self._candidate is not None:
            self._candidate.cancel()
        if self.pending_binding is not None:
            self.pending_binding = None
            self.committing = False
        if force:
            self.committing = False
        if not self.committing:
            self._candidate = self._preview = self.pending_prompt = None
        return CommandReceipt("accepted")

    def labels(self):
        data = self._session.data
        return [unit_id for unit_id, state in data.tracking.items()
                if state.active and ((state.status == "failed" and state.recovery_phase not in ("queued", "searching"))
                                     or unit_id == self.manual_target)]

    @command
    def select_unit(self, unit_id):
        if self.busy or unit_id not in self.labels():
            return CommandReceipt("rejected", self.note)
        switched_manual = self.manual_target not in (None, unit_id)
        if switched_manual:
            self.manual_target = None
        offered = self._session.automatic_recovery.take_candidate(unit_id)
        if offered is None:
            if switched_manual or self.review_unit_id not in (None, unit_id):
                return self.clear_candidate()
            return CommandReceipt("rejected", self.note)
        self.clear_candidate()
        self._candidate, self._preview, diagnostics = offered
        self.review_unit_id = unit_id
        scores = diagnostics.get("scores") or []
        score = f"{scores[0]:.3f}" if scores else "unknown"
        self.note = f"Proposed {unit_id} | seed cosine {score}. Correct confirms; No starts one new search."
        return CommandReceipt("accepted", value=True)

    @command
    def reject(self):
        if self.busy or self.review_unit_id is None:
            return CommandReceipt("rejected", self.note)
        uid = self.review_unit_id
        self.cancel()
        self._session.automatic_recovery.retry(uid)
        self._session.mark_changed()
        return CommandReceipt("accepted")

    def _take_over_manually(self, unit_id):
        state = self._session.data.tracking.get(unit_id)
        if self._session.closed or state is None or not state.active:
            raise ValueError("Pick a currently registered, active unit mask.")
        if not self._session.automatic_recovery.take_over_manually(unit_id):
            raise ValueError("Wait for automatic recovery to finish applying this unit's mask.")

    def _report_manual_target(self, unit_id):
        self.manual_target = unit_id
        self.note = f"Draft correction for {unit_id}. Original tracking continues until confirmation."
        self._session.mark_changed()
        return CommandReceipt("accepted")

    @command
    def report_error(self, unit_id):
        if self.committing:
            return CommandReceipt("rejected", self.note)
        self._take_over_manually(unit_id)
        if self.review_unit_id == unit_id:
            self.clear_candidate()
        return self._report_manual_target(unit_id)

    @command
    def point(self, source_point, positive, reference):
        snapshot = self.sample(reference)
        point = transform_points(source_point, self._session.data.board.homography["matrix"])
        if self.busy:
            self.note = "Wait for the candidate update; playback continues."
            return CommandReceipt("rejected", self.note)
        if not self.active or snapshot is None:
            return CommandReceipt("rejected", self.note)
        if self._candidate is None:
            if not positive:
                self.note = "Start a candidate with a positive point."
                return CommandReceipt("rejected", self.note)
            self._candidate = RecoveryCandidate()
            kind = "recovery_seed"
        else:
            if self._preview is None:
                self.note = "Clear / Retry to create a new candidate."
                return CommandReceipt("rejected", self.note)
            kind = "recovery_point"
        self.pending_prompt = {"kind": kind, "snapshot": snapshot,
                               "point": list(map(float, point)), "positive": bool(positive),
                               "point_source": transform_points(point, self._session.data.board.homography["inverse_matrix"]).tolist()}
        self.note = "Updating candidate; source playback continues."
        self._session.mark_changed()
        return CommandReceipt("pending", request_id=self.candidate_generation)

    @command
    def manual_mask(self, corners, reference):
        if not self.active:
            return CommandReceipt("rejected", self.note)
        if self.busy:
            self.note = "Wait for the candidate update; playback continues."
            return CommandReceipt("rejected", self.note)
        snapshot = self.sample(reference)
        if snapshot is None:
            return CommandReceipt("rejected", self.note)
        height, width = snapshot["frame"].shape[:2]
        quad = np.asarray(list(order_corners(corners).values()))
        if np.any(quad < 0) or np.any(quad >= [width, height]):
            raise ValueError("Draw the mask inside the video frame.")
        pixels = np.floor(quad).astype(np.int32)
        if not cv2.isContourConvex(pixels) or cv2.contourArea(pixels) <= 0:
            raise ValueError("The manual mask is too small.")
        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.fillConvexPoly(mask, pixels, 1)
        mask = mask.astype(bool)
        if not mask.any():
            raise ValueError("The manual mask is too small.")
        if self._candidate is not None:
            self._candidate.cancel()
        self.candidate_generation += 1
        self.review_unit_id = None
        self._preview = None
        self._candidate = RecoveryCandidate()
        self.pending_prompt = {"kind": "recovery_seed_mask", "snapshot": snapshot, "mask": mask}
        self.note = "Building candidate from manual shape; playback continues."
        self._session.mark_changed()
        return CommandReceipt("pending", request_id=self.candidate_generation)

    @command
    def bind(self, unit_id, candidate_generation):
        if candidate_generation != self.candidate_generation or not self.active:
            raise ValueError("Recovery candidate changed; review the current candidate before confirming.")
        if self.busy or unit_id not in self.labels() or self._preview is None:
            raise ValueError("Wait for a current candidate and choose an available existing ID.")
        if not self._preview["prediction"]["masks"][0].any():
            raise ValueError("Candidate is missing. Redraw, add points, or Clear / Retry.")
        object_id = next(obj for obj, unit in self._session.data.units.bindings.items() if unit == unit_id)
        self.pending_binding = object_id
        self.committing = True
        self.note = f"Applying recovery for {unit_id}; playback continues."
        self._session.mark_changed()
        return CommandReceipt("pending", request_id=self.candidate_generation)

    def _reject_pending_binding(self, reason):
        self.pending_binding, self.committing = None, False
        self.clear_candidate()
        self.note = f"Recovery failed because {reason}. Draw a new candidate or cancel."

    def take_request(self):
        if self.pending_prompt is not None:
            pending, self.pending_prompt = self.pending_prompt, None
            snapshot = pending["snapshot"]
            prompt = ({"mask": pending["mask"]} if pending["kind"] == "recovery_seed_mask"
                      else {"point": pending["point"], "positive": pending["positive"],
                            "point_source": pending["point_source"]})
            return pending["kind"], {**snapshot, "recovery_candidate": self._candidate, "prompt": prompt}
        if self.pending_binding is not None:
            session = self._session
            data = session.data
            observed = data.current.prediction_metadata
            tracked_frame = session.worker.tracker.source_frame
            candidate_frame = self._candidate.backend.source_frame
            if observed is None or observed["frame_index"] != tracked_frame or tracked_frame < candidate_frame:
                source_frame = session.source.frame_index
                if source_frame > tracked_frame:
                    # A decoded frame can still be tracked after playback reaches the end.
                    return "propagate", {**session.source_sample(), "recovery_candidate": self._candidate,
                                         "automatic_candidates": session.automatic_recovery.candidates()}
                if not session.playing or source_frame >= session.end_index:
                    self._reject_pending_binding("playback cannot supply a matching tracking frame")
                return None
            snapshot = {"frame": data.current.prediction_frame, "metadata": deepcopy(observed),
                        "raw_frame": session.prediction_raw_frame, "generation": session.generation}
            object_id, self.pending_binding = self.pending_binding, None
            normal = [obj for obj, uid in self._session.data.units.bindings.items()
                      if obj != object_id and self._session.data.tracking.get(uid) is not None
                      and self._session.data.tracking[uid].active and self._session.data.tracking[uid].status == "tracking"]
            normal_labels = {obj: self._session.data.units.bindings[obj] for obj in normal}
            return "recovery_commit", {**snapshot, "recovery_candidate": self._candidate, "recovery_object_id": object_id,
                                       "prediction": self._session.data.current.prediction,
                                       "prompt": {"method": "reviewed" if self.review_unit_id is not None else "manual",
                                                  "normal_ids": normal, "normal_labels": normal_labels}}
        return None

    def for_propagation(self):
        return self._candidate if self.active and self._preview is not None and not self.busy else None

    def accept(self, request, prediction, error=None):
        candidate = request.get("recovery_candidate")
        if candidate is not self._candidate:
            return
        if request["kind"] == "recovery_commit":
            self.committing = False
            if error is None and request.get("recovery_applied"):
                self.cancel()
                self._session.note = "Unit recovered with its original ID. Facing is unknown."
            elif not candidate.cancelled.is_set():
                if request.get("recovery_consumed"):
                    self._preview = None
                    self.note = f"Recovery not applied: {error}. Clear / Retry."
                elif (candidate.backend is not None and candidate.backend.session is not None
                      and candidate.backend.source_frame == request["metadata"]["frame_index"]
                      and candidate.prediction is not None and candidate.prediction["masks"][0].any()):
                    self._preview = {"prediction": candidate.prediction, "metadata": deepcopy(request["metadata"])}
                    self.note = f"Recovery not applied: {error}"
                else:
                    self._reject_pending_binding(f"the candidate is no longer usable ({error})")
                    return
            else:
                self.cancel()
        elif self.pending_binding is not None and error is not None:
            self._reject_pending_binding(f"candidate could not reach the matching frame ({error})")
            return
        elif self.active and not candidate.cancelled.is_set():
            if error is not None:
                self._preview = None
                self.note = f"Candidate error: {error}. Clear / Retry."
            elif prediction is not None:
                self._preview = {"prediction": prediction, "metadata": deepcopy(request["metadata"])}
                self.note = ((f"Review {self.review_unit_id}: Correct confirms; No starts one new search."
                              if self.review_unit_id is not None else "Click or drag an existing ID from the right panel to confirm.")
                             if prediction["masks"][0].any() else "Candidate missing. Redraw, add points, or Clear / Retry.")
        self._session.mark_changed()
