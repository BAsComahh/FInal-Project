"""Serialize model operations outside the playback/UI thread."""

from concurrent.futures import ThreadPoolExecutor
from copy import copy, deepcopy
import importlib.metadata
import hashlib
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import numpy as np

from ..config import DEFAULT_TRACKER, PROJECT_ROOT, AUTO_RECOVERY_ENABLED
from .. import config
from components.sam3.video import VideoPredictor
from components.tracking import create_tracker


def _point_ids(clicks):
    groups = {}
    for click in clicks:
        groups.setdefault(click["object_id"], []).append(click["click_id"])
    return groups


class TaskWorker:
    """One in-flight request; playback never waits for its result."""

    def __init__(self, model_id="facebook/sam3", device=None, *, profile=False, tray_search="full",
                 tracker=DEFAULT_TRACKER, tracker_model=None, tracker_cache=None):
        if tray_search not in ("full", "local"):
            raise ValueError("tray_search must be full or local")
        self.predictor = VideoPredictor(model_id, device, profile=profile)
        self.tracker = create_tracker(tracker, model_id=tracker_model, device=device, cache_dir=tracker_cache)
        self.tracker_name = tracker
        self.automatic = None
        self.automatic_progress = None
        self.facing = None
        self.facing_references = {}
        self.facing_excluded = set()
        self.facing_fronts = {}
        self.facing_states = {}
        self.facing_recovery = None
        self.facing_progress = None
        if config.DVMNET_FACING_ENABLED:
            from components.facing.dvmnet import FacingEstimator
            from components.facing.recovery import FacingRecovery
            self.facing = FacingEstimator(config.DVMNET_FACING_CACHE, device, margin_deg=config.FACING_EDGE_MARGIN_DEG)
            self.facing_recovery = FacingRecovery(min_similarity=config.FACING_CHECK_MIN_SIMILARITY,
                alternative_margin=config.FACING_CHECK_ALTERNATIVE_MARGIN, consecutive=config.FACING_CHECK_CONSECUTIVE,
                min_coverage=config.FACING_CHECK_MIN_COVERAGE, retry_change=config.FACING_RETRY_APPEARANCE_CHANGE,
                retry_seconds=config.FACING_RETRY_MIN_SECONDS)
        if tracker == "edgetam" and AUTO_RECOVERY_ENABLED:
            from components.tracking.automatic_recovery import AutomaticRecoveryEngine
            self.automatic = AutomaticRecoveryEngine(device)
        self.tracker_initialized = self.tracker is None
        self.tray_search = tray_search
        self.previous_trays = {}
        self.previous_context = None
        self.timing_dir = None
        if profile:
            self.timing_dir = PROJECT_ROOT / "outputs/tracking_comparison" / f"sam_{uuid4().hex[:12]}"
            self.timing_dir.mkdir(parents=True)
            run = {"model": model_id, "tracker": tracker,
                   "tracker_model": self.tracker.model_id if self.tracker is not None else model_id,
                   "requested_device": device, "profile": True, "tray_search": tray_search,
                   "versions": {name: importlib.metadata.version(name) for name in ("torch", "transformers", "opencv-python")},
                   "model_precision": "float32", "inference_state_device": "cpu"}
            root = PROJECT_ROOT
            run["source_hashes"] = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in (
                "frontend/runtime/task_worker.py", "components/sam3/video/predictor.py", "components/boundary_detection/tray/detector.py")}
            if self.tracker is not None:
                name = f"components/tracking/{tracker}.py"
                run["source_hashes"][name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
            (self.timing_dir / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
            print(f"Tracking timing log: {self.timing_dir}", flush=True)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sam3-video")
        self.future = self.request = None
        self.prompts = []
        self.tray_context = None

    @property
    def busy(self):
        return self.future is not None

    @property
    def models_loaded(self):
        return self.predictor.model is not None and (self.tracker is None or self.tracker.model is not None)

    @property
    def load_progress(self):
        if self.facing_progress is not None:
            return self.facing_progress
        if self.automatic_progress is not None:
            return self.automatic_progress
        if self.request is not None and self.request["kind"] == "recalibrate":
            return ("Rebuilding tracking for calibration", None, None)
        if self.tracker is not None and self.request is not None and self.request["kind"] == "start_tracker":
            return self.tracker.load_progress or (f"Preparing {self.tracker_name} memory", None, None)
        return self.predictor.load_progress or (self.tracker.load_progress if self.tracker is not None else None)

    def _automatic_recovery(self, request):
        batch = request["automatic_request"]
        request["automatic_rows"] = []
        request["automatic_applied"] = []
        request["automatic_consumed"] = []
        try:
            if self.automatic is None:
                raise ValueError("Automatic recovery is unavailable for this backend")
            if self.tracker.source_frame != request["metadata"]["frame_index"]:
                raise ValueError("Automatic search requires the current tracking observation")
            initial = request["prediction"]
            occupied = np.zeros(request["frame"].shape[:2], bool)
            for obj, mask in zip(initial["object_ids"], initial["masks"]):
                if obj in batch["normal_ids"]:
                    occupied |= mask
            found = self.automatic.search(request["frame"], batch["reference_folder"], batch["targets"], occupied,
                                          prompt=batch["prompt"], detection_threshold=batch["detection_threshold"],
                                          similarity=batch["similarity"], margin=batch["margin"], cancelled=batch["cancelled"])
            rows, masks = found["rows"], found["masks"]
            request["automatic_rows"] = rows
            prediction, candidates = None, {}
            from components.tracking.recovery import RecoveryCandidate
            for row in rows:
                if batch["cancelled"].is_set():
                    break
                if row["unit_id"] not in batch["unit_ids"]:
                    continue
                index, obj = row["candidate_id"], row["object_id"]
                if index is None:
                    continue
                try:
                    if row["automatic"]:
                        if np.any(masks[index] & occupied):
                            raise ValueError("Candidate overlaps an occupied normal unit")
                        request["automatic_consumed"].append(obj)
                        prediction = self.tracker.update_mask(request["frame"], obj, masks[index],
                                                               source_frame=request["metadata"]["frame_index"])
                        request["automatic_applied"].append(obj)
                        occupied |= masks[index]
                    else:
                        if index not in candidates:
                            candidate = RecoveryCandidate()
                            candidate.requires_continuity = True
                            candidate.seed_mask(self.tracker, request["frame"], masks[index], request["metadata"]["frame_index"])
                            candidates[index] = candidate
                        row["candidate"] = candidates[index]
                except Exception as error:
                    row["reason"] = f"Recovery requires manual input: {error}"
            return prediction
        except Exception as error:
            request["automatic_error"] = str(error)
            return None

    def _run(self, request):
        started = perf_counter()
        kind = request["kind"]
        if kind == "load":
            self.predictor.load()
            if self.tracker is not None:
                self.tracker.load()
            if self.automatic is not None:
                self.automatic_progress = ("Loading recovery SAM text and DINO models", None, None)
                try:
                    self.automatic.load()
                except Exception as error:
                    print(f"Automatic recovery unavailable; manual recovery retained: {error}", flush=True)
                finally:
                    self.automatic_progress = None
            if self.facing is not None:
                self.facing_progress = ("Loading and warming DVMNet facing", None, None)
                try:
                    self.facing.device = self.predictor.device
                    self.facing.load()
                except Exception as error:
                    self.facing.error = str(error)
                    self.facing.model = None
                    print(f"DVMNet facing unavailable; tracking retained: {error}", flush=True)
                finally:
                    self.facing_progress = None
            return None
        if kind == "prepare":
            self.predictor.prepare_initial_frame(request["frame"], source_frame=request["metadata"]["frame_index"])
            return None
        if kind == "reset":
            self.predictor.reset()
            if self.tracker is not None:
                self.tracker.reset()
                self.tracker_initialized = False
            self.prompts.clear()
            self.previous_trays.clear()
            self.previous_context = None
            if self.automatic is not None:
                self.automatic.references.clear()
            self.facing_references.clear()
            self.facing_states.clear()
            self.facing_fronts.clear()
            return None
        if kind == "replace":
            old, new = _point_ids(self.prompts), _point_ids(request["clicks"])
            changed = [obj for obj in new if new[obj] != old.get(obj)]
            prediction = self.predictor.replace_initial_points(
                request["frame"], request["clicks"], changed_ids=changed,
                source_frame=request["metadata"]["frame_index"])
            self.prompts = deepcopy(request["clicks"])
            for click in request["clicks"]:
                click["session_frame"] = self.predictor.index
        elif kind == "click":
            prompt = request["prompt"]
            prediction = self.predictor.click(request["frame"], prompt["point"],
                object_id=prompt["object_id"], positive=prompt["positive"],
                source_frame=request["metadata"]["frame_index"])
            self.prompts.append(deepcopy(prompt))
        elif kind == "start_tracker":
            if self.tracker is None:
                raise ValueError("SAM3 does not require a tracker handoff")
            initial = request["prediction"]
            prediction = self.tracker.initialize(request["frame"], initial["object_ids"], initial["masks"],
                                                source_frame=request["metadata"]["frame_index"])
            self.tracker_initialized = True
        elif kind == "recalibrate":
            backend = copy(self.tracker if self.tracker is not None else self.predictor)
            # Detach the session before reset: the old backend remains valid until commit.
            if hasattr(backend, "session"):
                backend.session = None
            backend.reset()
            initial = request["prediction"]
            prediction = backend.initialize(request["frame"], initial["object_ids"], initial["masks"],
                                            source_frame=request["metadata"]["frame_index"])
            request["new_backend"] = backend
        elif kind == "propagate":
            if not self.tracker_initialized:
                raise ValueError("Finish the registered-mask handoff before tracking")
            backend = self.tracker if self.tracker is not None else self.predictor
            prediction = backend.propagate(request["frame"],
                source_frame=request["metadata"]["frame_index"])
            candidate = request.get("recovery_candidate")
            if candidate is not None and not candidate.cancelled.is_set():
                try:
                    request["candidate_result"] = candidate.advance(request["frame"], request["metadata"]["frame_index"])
                except Exception as error:
                    request["candidate_error"] = error
            request["automatic_updates"] = []
            for candidate in request.get("automatic_candidates", ()):
                if candidate.cancelled.is_set():
                    continue
                try:
                    result = candidate.advance(request["frame"], request["metadata"]["frame_index"])
                    request["automatic_updates"].append((candidate, result, None))
                except Exception as error:
                    request["automatic_updates"].append((candidate, None, error))
        elif kind == "automatic_recovery":
            prediction = self._automatic_recovery(request)
        elif kind in ("recovery_seed", "recovery_point", "recovery_advance"):
            candidate = request["recovery_candidate"]
            source_frame = request["metadata"]["frame_index"]
            if kind == "recovery_seed":
                return candidate.seed(self.predictor, self.tracker, request["frame"], request["prompt"]["point"], source_frame)
            if kind == "recovery_point":
                return candidate.correct(request["frame"], request["prompt"]["point"], request["prompt"]["positive"], source_frame)
            return candidate.advance(request["frame"], source_frame)
        elif kind == "recovery_commit":
            candidate = request["recovery_candidate"]
            result = candidate.advance(request["frame"], request["metadata"]["frame_index"])
            mask = result["masks"][0]
            if not mask.any():
                raise ValueError("Candidate disappeared before confirmation. Retry on a visible target.")
            candidate._check()
            normal_ids = (request.get("prompt") or {}).get("normal_ids", [])
            if normal_ids:
                if self.tracker.source_frame != request["metadata"]["frame_index"] or request.get("prediction") is None:
                    raise ValueError("Wait for matching normal-unit observations before confirming recovery")
                occupied = np.zeros(mask.shape, bool)
                for obj, other in zip(request["prediction"]["object_ids"], request["prediction"]["masks"]):
                    if obj in normal_ids:
                        occupied |= other
                if np.any(mask & occupied):
                    raise ValueError("Candidate overlaps another normally tracked unit. Clear / Retry.")
            request["recovery_applied"] = True
            prediction = self.tracker.update_mask(request["frame"], request["recovery_object_id"], mask,
                                                  source_frame=request["metadata"]["frame_index"])
        elif kind == "trays":
            prediction = dict(request["prediction"])
            prediction["timings_seconds"] = {}
        else:
            raise ValueError(f"Unknown SAM3 operation: {kind}")
        if prediction is not None:
            prediction = dict(prediction)
            operation_finished = perf_counter()
            if request["tray_context"] is not None:
                from components.boundary_detection.tray.batch import fit_registered_trays

                context = request["tray_context"]
                mapping = context["image_to_plane"]
                signature = (None if mapping is None else tuple(np.asarray(mapping).ravel()),
                             tuple(sorted((key, tuple(size)) for key, size in context["sizes"].items())))
                previous = self.previous_trays if (kind in ("propagate", "recovery_commit", "automatic_recovery") and self.tray_search == "local"
                                                   and signature == self.previous_context) else None
                if previous is not None and kind == "recovery_commit":
                    previous = {obj: tray for obj, tray in previous.items() if obj != request["recovery_object_id"]}
                if previous is not None and kind == "automatic_recovery":
                    previous = {obj: tray for obj, tray in previous.items() if obj not in request["automatic_applied"]}
                corrected = (request.get("automatic_applied", []) if kind == "automatic_recovery" else
                             [request["recovery_object_id"]] if kind == "recovery_commit" else [])
                if corrected and request.get("prediction") is not None:
                    # Recovery is frame-aligned: preserve other accepted geometry exactly.
                    selected = [i for i, obj in enumerate(prediction["object_ids"]) if obj in corrected]
                    target = {"object_ids": [prediction["object_ids"][i] for i in selected],
                              "masks": prediction["masks"][selected]}
                    trays, errors = fit_registered_trays(request["frame"], target, context)
                    prediction["trays"] = {**{obj: tray for obj, tray in request["prediction"].get("trays", {}).items()
                                              if obj not in corrected}, **trays}
                    prediction["tray_errors"] = {**{obj: error for obj, error in request["prediction"].get("tray_errors", {}).items()
                                                    if obj not in corrected}, **errors}
                else:
                    prediction["trays"], prediction["tray_errors"] = fit_registered_trays(
                        request["frame"], prediction, context, previous=previous)
                self.previous_trays = prediction["trays"]
                self.previous_context = signature
            else:
                self.previous_trays.clear()
                self.previous_context = None
            trays_finished = perf_counter()
            references = request.get("facing_references", {})
            if self.facing is not None and references:
                corrected = (request.get("automatic_applied", []) if kind == "automatic_recovery" else
                             [request["recovery_object_id"]] if kind == "recovery_commit" else None)
                previous_faces = (request.get("prediction") or {}).get("facing_results", {}) if corrected else {}
                excluded = set(request.get("facing_excluded", ())) - set(corrected or ())
                try:
                    faces, updates = self.facing_recovery.evaluate(self.facing, prediction, request.get("raw_frame"),
                        request["metadata"], request["tray_context"], references, request["facing_fronts"],
                        request["facing_states"], excluded, corrected, force=corrected or ())
                    request["next_facing_states"] = updates
                except Exception as error:
                    faces = {obj: {"status": "unknown", "reason": str(error), "unit_id": ref["unit_id"],
                                   "reference_id": ref["reference_id"], "frame_index": request["metadata"]["frame_index"],
                                   "calibration_version": request["metadata"].get("calibration_version")}
                             for obj, ref in references.items() if corrected is None or obj in corrected}
                prediction["facing_results"] = {**previous_faces, **faces}
            finished = perf_counter()
            prediction["timings_seconds"] = {**prediction.get("timings_seconds", {}),
                "worker_operation": operation_finished - started, "tray_fit": trays_finished - operation_finished,
                "facing": finished - trays_finished,
                "worker_total": finished - started}
            prediction["inference_seconds"] = finished - started
            metadata = request["metadata"]
            prediction.update(source_frame_index=metadata["frame_index"],
                              tracking_backend=self.tracker_name if kind in ("propagate", "start_tracker", "recalibrate", "recovery_commit", "automatic_recovery") else "sam3_registration",
                              observation_time_seconds=metadata.get("timestamp_seconds"),
                              task_submitted_at=request.get("submitted_at"), task_completed_at=finished)
        return prediction

    def _recorded_run(self, request):
        started, prediction, error = perf_counter(), None, None
        try:
            prediction = self._run(request)
            return prediction
        except Exception as exception:
            error = str(exception)
            raise
        finally:
            finished = perf_counter()
            metadata = request["metadata"] or {}
            record = {"kind": request["kind"], "generation": request["generation"],
                      "calibration_version": metadata.get("calibration_version"),
                      "source_frame_index": metadata.get("frame_index"),
                      "observation_time_seconds": metadata.get("timestamp_seconds"),
                      "submitted_at": request["submitted_at"], "started_at": started, "completed_at": finished,
                      "request_seconds": finished - started, "device": self.predictor.device,
                      "tracker": self.tracker_name, "error": error}
            if prediction is not None:
                record.update(object_ids=prediction["object_ids"], timings_seconds=prediction.get("timings_seconds", {}),
                              timing_gpu_synchronized=prediction.get("timing_gpu_synchronized", False),
                              inference_call_count=prediction.get("inference_call_count"),
                              object_score_logits=prediction.get("object_score_logits"),
                              trays={key: {name: row[name] for name in ("method", "mask_coverage", "edge_support")}
                                     for key, row in prediction.get("trays", {}).items()})
            if request["kind"] == "automatic_recovery":
                record.update(automatic_applied=request.get("automatic_applied", []),
                              automatic_error=request.get("automatic_error"),
                              automatic_rows=[{key: row.get(key) for key in ("unit_id", "reason", "top_two_margin")}
                                              for row in request.get("automatic_rows", [])])
            with (self.timing_dir / "observations.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record) + "\n")

    def submit(self, kind, *, frame=None, metadata=None, prompt=None, generation=0, clicks=None, prediction=None,
               tray_context=None, raw_frame=None, calibration_token=None, recovery_candidate=None, recovery_object_id=None,
               automatic_request=None, automatic_candidates=()):
        if self.busy:
            raise RuntimeError("A SAM3 request is already in flight")
        self.request = {"kind": kind, "frame": frame.copy() if frame is not None else None,
                        "metadata": dict(metadata) if metadata is not None else None,
                        "prompt": prompt, "generation": generation, "clicks": deepcopy(clicks),
                        "prediction": deepcopy(prediction) if kind in ("automatic_recovery", "recovery_commit") else prediction,
                        "raw_frame": raw_frame.copy() if raw_frame is not None else None,
                        "calibration_token": calibration_token,
                        "recovery_candidate": recovery_candidate, "recovery_object_id": recovery_object_id,
                        "automatic_request": automatic_request, "automatic_candidates": tuple(automatic_candidates),
                        "facing_references": dict(self.facing_references), "facing_excluded": tuple(self.facing_excluded),
                        "facing_fronts": deepcopy(self.facing_fronts), "facing_states": deepcopy(self.facing_states),
                        "tray_context": deepcopy(self.tray_context if tray_context is None else tray_context)}
        self.request["submitted_at"] = perf_counter()
        self.future = self.executor.submit(self._recorded_run if self.timing_dir is not None else self._run, self.request)

    def commit_facing(self, request, object_ids=None):
        """Owner-thread commit after generation/calibration and observation acceptance."""
        for obj, state in request.get("next_facing_states", {}).items():
            if object_ids is not None and obj not in object_ids:
                continue
            reference = self.facing_references.get(obj)
            if reference is not None and reference["reference_id"] == state["reference_id"]:
                self.facing_states[obj] = state

    def poll(self):
        if self.future is None or not self.future.done():
            return None
        future, request = self.future, self.request
        self.future = self.request = None
        try:
            return request, future.result(), None
        except Exception as error:
            return request, None, error

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
