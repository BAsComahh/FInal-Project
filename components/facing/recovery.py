"""Propose facing state updates; the owner commits them only with accepted observations."""

from copy import deepcopy

import numpy as np

from .appearance import tray_patch, patch_similarity, patch_change, predicted_edge


class FacingRecovery:
    def __init__(self, *, min_similarity=.35, alternative_margin=.15, consecutive=2,
                 retry_change=.12, retry_seconds=2., min_coverage=.25):
        if (not -1 <= min_similarity <= 1 or not 0 <= alternative_margin <= 2
                or type(consecutive) is not int or consecutive < 1 or not 0 < min_coverage <= 1
                or not 0 <= retry_change <= 1 or not np.isfinite(retry_seconds) or retry_seconds < 0):
            raise ValueError("Invalid facing recovery parameters")
        self.min_similarity, self.alternative_margin, self.consecutive = min_similarity, alternative_margin, consecutive
        self.retry_change, self.retry_seconds, self.min_coverage = retry_change, retry_seconds, min_coverage

    def evaluate(self, estimator, prediction, raw_frame, metadata, context, references, fronts, states,
                 excluded=(), targets=None, force=(), cancelled=None):
        rows, updates = {}, {}
        masks = dict(zip(prediction["object_ids"], prediction["masks"]))
        for obj, reference in references.items():
            if cancelled is not None and cancelled.is_set():
                break
            if targets is not None and obj not in targets:
                continue
            front = None if obj in force else fronts.get(obj)
            patch = None
            state = deepcopy(states.get(obj, {}))
            if state.get("reference_id") != reference["reference_id"]:
                state = {"reference_id": reference["reference_id"], "baseline": reference.get("detector_template"),
                         "phase": "tracking", "suspect_count": 0, "last_frame": -1,
                         "verified_frame": reference["frame_index"], "verified_by": "initial_manual"}
            row = {"status": "unknown", "unit_id": reference["unit_id"], "reference_id": reference["reference_id"],
                   "frame_index": metadata["frame_index"], "calibration_version": metadata.get("calibration_version"),
                   "recovery_phase": state["phase"], "model_called": False}
            try:
                tray = prediction.get("trays", {}).get(obj)
                if obj in excluded or obj not in masks or not masks[obj].any() or tray is None:
                    state.update(phase="waiting", suspect_count=0)
                    row.update(reason="Facing waits for accepted tracking and tray geometry", recovery_phase="waiting")
                else:
                    mapping = np.asarray(context["image_to_plane"]) @ np.asarray(metadata["homography"]["matrix"])
                    anchor = front or {"source_ray": reference["source_ray"]}
                    edge, candidates = predicted_edge(anchor, tray, mapping, reference["front_width_mm"])
                    patch = tray_patch(raw_frame, masks[obj], metadata, tray, edge)
                    row.update(edge=edge, status="estimated" if front else "unknown")
                    fresh = metadata["frame_index"] > state["last_frame"]
                    retry = state["phase"] == "failed"
                    if retry:
                        change = patch_change(state["attempt_patch"], patch, min_coverage=self.min_coverage)
                        elapsed = metadata["timestamp_seconds"] - state["attempt_seconds"]
                        row.update(appearance_change=change, reason=state["failure_reason"])
                        attempt = (fresh and change is not None and change >= self.retry_change and elapsed >= self.retry_seconds)
                    else:
                        scores = {candidate: patch_similarity(state["baseline"],
                                  patch if candidate == edge else tray_patch(raw_frame, masks[obj], metadata, tray, candidate),
                                  min_coverage=self.min_coverage) for candidate in candidates} if state["baseline"] is not None else {}
                        current = scores.get(edge)
                        alternatives = [score for candidate, score in scores.items() if candidate != edge and score is not None]
                        best = max(alternatives, default=-1.)
                        suspect = ((current is None and bool(alternatives) and best >= self.min_similarity) or
                                   (current is not None and (current < self.min_similarity or best-current >= self.alternative_margin)))
                        if fresh:
                            state["suspect_count"] = state["suspect_count"] + 1 if suspect else 0
                        row.update(appearance_scores=scores, reason="Rectangle continuity; no facing recovery required")
                        if current is None and best < self.min_similarity:
                            row["reason"] = "Insufficient comparable foreground/texture; retaining rectangle continuity"
                        attempt = (obj in force or front is None or
                                   (fresh and state["suspect_count"] >= self.consecutive))
                        state["phase"] = "pending" if suspect else "tracking"
                        if suspect:
                            row["reason"] = "Facing appearance is suspicious; retaining Estimated front"
                    if obj in force:
                        attempt = True  # New, accepted ID/mask association; no old facing fallback.
                    if attempt:
                        row["model_called"] = True
                        result = estimator.estimate(prediction, raw_frame, metadata, context, references,
                                                    excluded, targets=(obj,))[obj]
                        row["model_result"] = result
                        if result["status"] == "selected":
                            row.update(result)
                            state.update(phase="tracking", suspect_count=0,
                                         baseline=tray_patch(raw_frame, masks[obj], metadata, tray, result["edge"]),
                                         verified_frame=metadata["frame_index"], verified_by="dvmnet")
                            row["reason"] = "DVMNet recovered the front edge"
                        else:
                            reason = "Facing recovery failed: " + result.get("reason", "ambiguous front")
                            state.update(phase="failed", attempt_patch=patch, attempt_seconds=metadata["timestamp_seconds"],
                                         failure_reason=reason)
                            row.update(status="estimated" if front else "unknown", reason=reason)
                    row["recovery_phase"] = state["phase"]
            except Exception as error:
                # A facing-only error must not remove an otherwise usable old front.
                row.update(status="estimated" if front and "edge" in row else "unknown",
                           reason="Facing recovery failed: " + str(error), recovery_phase="failed")
                if patch is not None and row.get("edge") is not None:
                    state.update(phase="failed", attempt_patch=patch, attempt_seconds=metadata["timestamp_seconds"],
                                 failure_reason=row["reason"])
            state["last_frame"] = max(state["last_frame"], metadata["frame_index"])
            row.update(last_verified_frame_index=state["verified_frame"], last_verified_by=state["verified_by"])
            rows[obj], updates[obj] = row, state
        return rows, updates
