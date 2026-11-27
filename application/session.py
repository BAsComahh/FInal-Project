"""Source clock, one serial model queue and accepted observations/history."""
from copy import deepcopy
import faulthandler
import json
from pathlib import Path
import sys
from time import perf_counter, time
import cv2
import numpy as np
from components.video_io import VideoSource
from components.tracking.status import validate_disappearance_seconds
from components.motion_history import MotionRecorder
from . import config
from .automatic_recovery import AutomaticRecovery
from .task_worker import TaskWorker
from .tray_worker import TrayWorker

class MatchSession:
    def __init__(self, video, data, *, model_id="facebook/sam3", device=None, start=0, seconds=None,
                 inference_fps=config.DEFAULT_INFERENCE_FPS, output_dir=None,
                 profile=False, tray_search=config.DEFAULT_TRAY_SEARCH, tracker=config.DEFAULT_TRACKER, tracker_model=None, tracker_cache=None):
        if seconds is not None and (seconds <= 0 or not np.isfinite(seconds)):
            raise ValueError("seconds must be positive")
        if inference_fps is not None and (inference_fps <= 0 or not np.isfinite(inference_fps)):
            raise ValueError("inference-fps must be positive")
        self.disappearance_seconds = validate_disappearance_seconds(config.TRACKING_DISAPPEARANCE_SECONDS)
        self.data = data
        self.data.rules.track_facing = config.FACING_TRACKING_ENABLED
        self.data.motion_recorder = MotionRecorder(position_tolerance_mm=config.MOTION_POSITION_TOLERANCE_MM,
                                                   rotation_tolerance_deg=config.MOTION_ROTATION_TOLERANCE_DEG,
                                                   settle_seconds=config.MOTION_SETTLE_SECONDS)
        self.output_dir = Path(output_dir) if output_dir is not None else config.DEFAULT_OUTPUT_DIR
        self._fault_file = None
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self._fault_file = (self.output_dir / "crash_traceback.log").open("a", encoding="utf-8")
            faulthandler.enable(file=self._fault_file, all_threads=True)
        except Exception:
            self._fault_file = None
        self.worker = TaskWorker(model_id, device, profile=profile, tray_search=tray_search,
                                 tracker=tracker, tracker_model=tracker_model, tracker_cache=tracker_cache)
        self.trays = TrayWorker(tray_search, self.worker.tray_stability)
        self.worker.submit("load", generation=0)
        self.source = None
        try:
            self.source = VideoSource(video)
            self.data.current.frame = self.source.read_at(start)
        except Exception:
            if self.source is not None:
                self.source.close()
            self.worker.close()
            self.trays.close()
            if self._fault_file is not None:
                self._fault_file.close()
                self._fault_file = None
            raise
        self.initial_frame = self.data.current.frame
        self.registration_start_frame = self.source.frame_index
        self.data.board.source_size = self.data.current.frame.shape[1::-1]
        self.start = start
        self.playback_seconds = seconds
        self.end_index = self.source.frame_count - 1
        if seconds is not None:
            self.end_index = min(self.end_index, int((start + seconds) * self.source.fps) - 1)
        self.inference_fps = inference_fps
        self.load_progress = None
        self.pending_trays = set()
        self.tray_versions = {}
        self._geometry_visible = set()
        self.generation = 0
        self.needs_reset = False
        self.needs_load = False
        self.needs_prepare = True
        self.startup_ready = False
        self.model_failed = self.closed = self.playing = False
        self.pending_play = False
        self.playback_started = False
        self.prediction_raw_frame = None
        self.presented_frame = None
        self.recovery = None
        self.automatic_recovery = AutomaticRecovery(self)
        self.next_inference_time = 0.0
        self.last_submitted_frame = -1
        self.retired_histories = []
        self._history_errors = ()
        self.configure_trays()
        self.note = "Loading SAM3 and preparing the first frame. Confirm the table boundary first."

    @property
    def registration_locked(self):
        return self.data.reference_folder is not None

    @property
    def inference_interval(self):
        return 0.0 if self.inference_fps is None else 1 / self.inference_fps

    def _write_diagnostics(self, event, *, request=None, error=None, extra=None):
        try:
            folder = Path(self.data.reference_folder) if self.data.reference_folder is not None else self.output_dir
            folder.mkdir(parents=True, exist_ok=True)
            metadata = (request or {}).get("metadata") or {}
            payload = {
                "wall_time": time(),
                "event": event,
                "generation": self.generation if request is None else request.get("generation", self.generation),
                "kind": None if request is None else request.get("kind"),
                "backend": self.worker.tracker_name,
                "source_frame_index": metadata.get("frame_index", self.source.frame_index if self.source is not None else None),
                "source_timestamp_seconds": metadata.get("timestamp_seconds"),
                "diagnostics": ((request or {}).get("runtime_diagnostics")
                                or (self.worker.diagnostics(request) if not self.worker.busy else self.worker.last_diagnostics)),
            }
            if error is not None:
                payload["error"] = str(error)
                payload["error_type"] = type(error).__name__ if isinstance(error, BaseException) else "Error"
            if request is not None and request.get("error_traceback"):
                payload["traceback"] = request["error_traceback"]
            if extra:
                payload.update(extra)
            with (folder / "runtime_diagnostics.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _history_stores(self):
        current = [self.data.history_store] if self.data.history_store is not None else []
        return current + self.retired_histories

    @property
    def history_warning(self):
        failed = [store for store in self._history_stores() if store.error is not None]
        if not failed:
            return None
        count = sum(store.pending_count for store in failed)
        return f"History not saved: {count} updates pending. Retrying; RAM may grow. {failed[0].error}"

    def _poll_history(self):
        self.data.poll_history()
        for store in self.retired_histories[:]:
            store.poll()
            if not store.pending_count:
                store.close()
                self.retired_histories.remove(store)
        errors = tuple((str(store.path), store.error) for store in self._history_stores() if store.error is not None)
        if errors != self._history_errors:
            for path, error in errors:
                print(f"History not saved: {path}: {error}. Retrying; pending data retained in RAM.", file=sys.stderr, flush=True)
                self._write_diagnostics("history_error", error=error, extra={"history_path": path})
            if not errors and self._history_errors:
                print("History writes resumed; any remaining queued updates are draining.", flush=True)
            self._history_errors = errors

    def _warp_frame(self, frame):
        if self.data.board.homography is None:
            return frame
        return cv2.warpPerspective(frame, self.data.board.homography["matrix"], self.data.board.homography["output_size"])

    def frame_metadata(self, *, board=None, frame=None, source_metadata=None):
        board = self.data.board if board is None else board
        frame = self.data.current.frame if frame is None else frame
        metadata = self.source.metadata() if source_metadata is None else dict(source_metadata)
        if board.homography is not None:
            metadata.update(
                coordinate_space="rectified_table_pixels", image_size=list(frame.shape[1::-1]),
                source_image_size=list(board.source_size), calibration_version=board.calibration_version,
                homography={key: value.tolist() if isinstance(value, np.ndarray) else value
                            for key, value in board.homography.items()},
            )
            if board.image_to_plane is not None:
                metadata.update(image_to_plane=board.image_to_plane.tolist(), board_size_mm=list(board.board_size_mm))
        return metadata

    def configure_trays(self, object_ids=None, *, refit=True):
        sizes = {}
        if self.data.units:
            for object_id, unit_id in self.data.units.bindings.items():
                type_id = self.data.units.units[unit_id]["type_id"]
                dimension = self.data.units.types[type_id].get("dimension", {})
                if "width_mm" in dimension and "depth_mm" in dimension:
                    sizes[object_id] = (dimension["width_mm"], dimension["depth_mm"])
        self.worker.tray_context = ({"image_to_plane": self.data.board.image_to_plane, "sizes": sizes}
                                    if self.data.board.image_to_plane is not None else None)
        targets = (set(object_ids) if object_ids is not None else
                   set(sizes) | set((self.data.current.prediction or {}).get("object_ids", ())))
        self.invalidate_trays(targets)
        if refit:
            unconfirmed = self.registration.unconfirmed if hasattr(self, "registration") else set()
            self.pending_trays.update((targets & sizes.keys()) - unconfirmed)

    def invalidate_trays(self, object_ids):
        """Invalidate only edited objects; a running fit cannot restore their old trays."""
        targets = set(object_ids)
        if not targets:
            return
        self.trays.invalidate(targets)
        self.pending_trays.difference_update(targets)
        for obj in targets:
            self.tray_versions[obj] = self.tray_versions.get(obj, 0) + 1
        current = self.data.current
        if current.prediction is not None:
            current.prediction = {**current.prediction, **{key: {obj: row for obj, row in
                current.prediction.get(key, {}).items() if obj not in targets}
                for key in ("trays", "tray_errors", "facing_results")}}

    def capture_facing_references(self):
        """Freeze initial manual facing material once, alongside registration."""
        self.worker.facing_references.clear()
        self.worker.facing_states.clear()
        if self.worker.facing is None:
            return
        from components.facing import make_reference
        current = self.data.current
        masks = dict(zip(current.prediction["object_ids"], current.prediction["masks"]))
        for obj, front in self.data.rules.fronts.items():
            uid = self.data.units.bindings.get(obj)
            if uid is None or front.get("source") != "manual":
                continue
            try:
                reference = make_reference(self.prediction_raw_frame, masks[obj], current.prediction_metadata,
                                           front, current.prediction["trays"][obj], uid)
            except Exception as error:
                reference = {"unit_id": uid, "reference_id": f"unavailable-{uid}", "error": str(error),
                             "frame_index": current.prediction_metadata["frame_index"],
                             "calibration_version": self.data.board.calibration_version}
            self.worker.facing_references[obj] = reference
            front["appearance_reference_id"] = reference["reference_id"]
        self.worker.facing_fronts = deepcopy(self.data.rules.fronts)

    def mark_changed(self, *, geometry=True):
        self.data.current.view_revision += 1
        if geometry:
            self.data.current.geometry_revision += 1

    def source_sample(self):
        return {"frame": self.data.current.frame, "metadata": self.frame_metadata(),
                "generation": self.generation, "raw_frame": self.source.frame}

    def tray_status(self):
        if self.data.board.image_to_plane is None:
            return "NO CALIB"
        if not self.worker.tray_context["sizes"]:
            return "NO SIZES"
        if self.data.current.prediction is None:
            return "WAIT MASK"
        trays = self.data.current.prediction.get("trays", {})
        if trays:
            return f"ON ({len(trays)})"
        if self.data.current.prediction.get("tray_errors"):
            return "CHECK FIT"
        if self.pending_trays or self.worker.busy or self.trays.busy:
            return "FITTING"
        return "NO FIT"

    def start_stream(self, now=None):
        if not self.data.rules.track_facing:
            self.data.rules.fronts.clear()
        self._geometry_visible = self._visible_geometry_ids()
        self.resume_source(now)
        self.pending_play = False

    def resume_source(self, now=None):
        self.play_start = perf_counter() if now is None else now
        self.play_start_frame = self.source.frame_index
        self.playing = True

    def schedule(self, now=None):
        registration, calibration = self.registration, self.calibration
        now = perf_counter() if now is None else now
        self.worker.facing_fronts = deepcopy(self.data.rules.fronts) if self.data.rules.track_facing else {}
        self.worker.facing_excluded = {obj for obj, uid in (self.data.units.bindings.items() if self.data.units else ())
                                       if uid in self.data.tracking and
                                       (not self.data.tracking[uid].active or self.data.tracking[uid].status == "failed")}
        self.automatic_recovery.observe()
        if self.worker.busy or self.closed:
            return
        if calibration._context is not None and calibration.submit_pending():
            return
        if self.needs_reset:
            self.needs_reset = False
            self.worker.submit("reset", generation=self.generation)
        elif self.needs_load:
            self.needs_load = False
            self.worker.submit("load", generation=self.generation)
        elif self.needs_prepare and self.data.board.homography is not None and not self.model_failed:
            self.needs_prepare = False
            self.worker.submit("prepare", frame=self.data.current.frame, metadata=self.frame_metadata(), generation=self.generation)
        elif not self.model_failed and self.recovery is not None and (request := self.recovery.take_request()) is not None:
            kind, values = request
            self.worker.submit(kind, **values)
            if kind == "propagate":
                self.last_submitted_frame = values["metadata"]["frame_index"]
                self.next_inference_time = now + self.inference_interval
        elif (request := registration.take_pending_request()) is not None:
            kind, values = request
            self.worker.submit(kind, **values, generation=self.generation, raw_frame=self.source.frame)
        elif self.pending_trays and self.data.current.prediction is not None:
            targets = tuple(sorted(self.pending_trays))
            self.pending_trays.clear()
            self.worker.submit("trays", frame=self.data.current.prediction_frame,
                               metadata=self.frame_metadata(frame=self.data.current.prediction_frame,
                                                            source_metadata=self.data.current.prediction_metadata),
                               prediction=self.data.current.prediction, generation=self.generation, raw_frame=self.prediction_raw_frame,
                               tray_ids=targets, tray_versions={obj: self.tray_versions[obj] for obj in targets})
        elif self.pending_play and not self.worker.tracker_initialized and not self.model_failed:
            self.worker.submit("start_tracker", frame=self.data.current.prediction_frame, metadata=self.data.current.prediction_metadata,
                               prediction=self.data.current.prediction, generation=self.generation, raw_frame=self.prediction_raw_frame,
                               previous_trays={**self.data.current.prediction.get("trays", {}), **self.trays.attempts})
        elif not self.model_failed and self._needs_facing_task() and (ready := self.trays.take_ready()) is not None:
            request, prediction, error = ready
            if error is not None:
                self._accept_geometry(request, prediction, error, direct=True)
            else:
                self.worker.submit("facing", frame=request["frame"], metadata=request["metadata"],
                    raw_frame=request.get("raw_frame"), prediction=prediction, generation=request["generation"],
                    tray_context=request["tray_context"], tray_epoch=request["tray_epoch"],
                    tray_attempts=request.get("tray_attempts", {}), tracking=request["tracking"])
        elif calibration._context is None and (request := self.automatic_recovery.take_request()) is not None:
            kind, values = request
            self.worker.submit(kind, **values)
        elif (self.playing and self.data.current.prediction is not None and not self.model_failed and not registration.updating_points
              and now >= self.next_inference_time):
            values = self.source_sample()
            backend = self.worker.tracker if self.worker.tracker is not None else self.worker.predictor
            consumed = backend.source_frame
            if values["metadata"]["frame_index"] <= max(self.last_submitted_frame, consumed if consumed is not None else -1):
                return
            candidate = self.recovery.for_propagation() if self.recovery is not None else None
            self.worker.submit("propagate", **values, recovery_candidate=candidate,
                               automatic_candidates=self.automatic_recovery.candidates())
            self.last_submitted_frame = values["metadata"]["frame_index"]
            self.next_inference_time = now + self.inference_interval
        elif not self.model_failed and self.recovery is not None and not self.playing:
            candidate = self.recovery.for_propagation()
            if candidate is not None and self.source.frame_index > candidate.backend.source_frame:
                self.worker.submit("recovery_advance", **self.source_sample(), recovery_candidate=candidate)

    def _accept_recovery_result(self, request, prediction, error):
        if prediction is not None and self.pending_trays:
            prediction = {**prediction, "trays": {}, "tray_errors": {}}
        if request["metadata"].get("calibration_version") != self.data.board.calibration_version:
            self.recovery.accept(request, None, ValueError("Calibration changed. Start a new recovery."))
            return
        candidate = request["recovery_candidate"]
        cancelled = candidate is not self.recovery._candidate or candidate.cancelled.is_set()
        consumed = request.get("recovery_consumed")
        if cancelled:
            if request["kind"] != "recovery_commit" or not consumed:
                return
            error = ValueError("Confirmed update was invalidated after the backend consumed it.")
        if request["kind"] == "recovery_commit" and consumed:
            self.trays.invalidate((request["recovery_object_id"],))
            object_id = request["recovery_object_id"]
            method = (request.get("prompt") or {}).get("method", "manual")
            if error is None:
                try:
                    self.data.accept_recovery(prediction, request["frame"], request["metadata"], object_id,
                                              source=self.source.metadata(), disappearance_seconds=self.disappearance_seconds, method=method)
                    self.worker.commit_facing(request, (object_id,))
                    self.trays.attempts.update(request.get("tray_attempts") or {})
                    self.prediction_raw_frame = request.get("raw_frame")
                    self._geometry_visible.update(self._visible_geometry_ids() & {object_id})
                except Exception as failure:
                    error = failure
            if error is not None:
                self.data.fail_recovery(object_id, self.source.metadata(), method=method, error=error)
            self.last_submitted_frame = max(self.last_submitted_frame, self.worker.tracker.source_frame)
            self.next_inference_time = perf_counter() + self.inference_interval
        self.recovery.accept(request, prediction, error)
        self.mark_changed()

    def _accept_automatic_result(self, request, prediction, error):
        if prediction is not None and self.pending_trays:
            prediction = {**prediction, "trays": {}, "tray_errors": {}}
        valid = self.automatic_recovery.valid(request)
        if request.get("automatic_consumed"):
            self.trays.invalidate(request["automatic_consumed"])
        rows = {row["object_id"]: row for row in request.get("automatic_rows", ())}
        for obj in request.get("automatic_consumed", []):
            row = rows.get(obj, {})
            failure = error or row.get("update_error") or request.get("automatic_error")
            if valid and error is None and prediction is not None and obj in request.get("automatic_applied", []):
                try:
                    self.data.accept_recovery(prediction, request["frame"], request["metadata"], obj,
                                              source=self.source.metadata(), disappearance_seconds=self.disappearance_seconds,
                                              method="automatic")
                    self.worker.commit_facing(request, (obj,))
                    self.trays.attempts.update(request.get("tray_attempts") or {})
                    self.prediction_raw_frame = request.get("raw_frame")
                    self._geometry_visible.update(self._visible_geometry_ids() & {obj})
                    continue
                except Exception as accept_error:
                    failure = accept_error
                    row["reason"] = str(accept_error) or type(accept_error).__name__
            if request["metadata"].get("calibration_version") == self.data.board.calibration_version:
                self.data.fail_recovery(obj, self.source.metadata(), method="automatic", error=failure)
        self.automatic_recovery.accept(request, error or request.get("automatic_error"))
        consumed = self.worker.tracker.source_frame
        if consumed is not None:
            self.last_submitted_frame = max(self.last_submitted_frame, consumed)
        self.next_inference_time = perf_counter()
        if valid:
            unresolved = sum(self.data.tracking.get(uid) is not None and self.data.tracking[uid].status == "failed"
                             for uid in request["automatic_request"]["unit_ids"])
            self.note = (f"Recovery: {unresolved} unit(s) need human input." if unresolved else
                         f"Recovery: {len(request.get('automatic_applied', []))} unit(s) recovered automatically.")
        self.mark_changed()

    def _needs_facing_task(self):
        return bool(self.worker.facing is not None and self.worker.facing_references)

    def _poll_direct_trays(self):
        """Accept completed TrayWorker geometry immediately when facing evaluation is inactive."""
        if self.model_failed or self._needs_facing_task():
            return
        ready = self.trays.take_ready()
        if ready is None:
            return
        self._accept_geometry(*ready, direct=True)

    def _accept_geometry(self, request, prediction, error, *, direct=False):
        if request["generation"] != self.generation:
            self.trays.accept(request, valid=False)
            return
        if error is not None:
            self.trays.accept(request, valid=False)
            if direct:
                self.worker.record_direct_geometry(request, prediction, error)
            self.note = f"Tray/facing update failed; mask tracking continues: {error}"
            return
        current = self.data.current
        metadata = request["metadata"]
        previous = (current.prediction or {}).get("geometry_metadata")
        valid = (metadata.get("calibration_version") == self.data.board.calibration_version and
                 current.prediction is not None and metadata["frame_index"] <= current.prediction_metadata["frame_index"] and
                 (previous is None or metadata["frame_index"] >= previous["frame_index"]))
        if not self.trays.accept(request, valid=valid):
            return
        if direct:
            self.worker.record_direct_geometry(request, prediction, None)
        prediction = self.data.accept_geometry(prediction, request["frame"], metadata)
        self.worker.commit_facing(request)
        self.data.record_history(source=self.source.metadata(),
                                 observation=(prediction, request["frame"], metadata), tracking=request["tracking"])
        self.mark_changed()
        self.note = self._tracking_note()

    def _tracking_note(self):
        prediction = self.data.current.prediction or {}
        times = prediction.get("timings_seconds") or {}
        backend = prediction.get("tracking_backend", "model")
        mask_time = times.get("worker_operation", prediction.get("inference_seconds", 0.0))
        tray_time = times.get("tray_fit", 0.0)
        stats = prediction.get("tray_fit_stats") or {}
        detail = (f" (reuse {stats.get('reused', 0)}, refit {stats.get('refitted', 0)}, "
                  f"retry wait {stats.get('retry_wait', 0)})" if stats else "")
        return f"Mask ({backend}) {mask_time:.2f}s | tray {tray_time:.2f}s{detail}"

    def _visible_geometry_ids(self):
        prediction = self.data.current.prediction or {}
        unavailable = set(prediction.get("unavailable_ids", ())) | set(prediction.get("inactive_ids", ()))
        return {obj for obj, mask in zip(prediction.get("object_ids", ()), prediction.get("masks", ()))
                if obj not in unavailable and mask.any()}

    def _queue_geometry(self, request):
        prediction = self.data.current.prediction
        visible = self._visible_geometry_ids()
        if visible != self._geometry_visible:
            lost = self._geometry_visible - visible
            self.trays.invalidate(self._geometry_visible ^ visible)
            if lost:
                self.data.record_history(kind="tracking_gap", source=self.source.metadata(),
                    interruptions=[self.data.units.bindings[obj] for obj in lost if obj in self.data.units.bindings])
            self._geometry_visible = visible
            self.data.current.geometry_revision += 1
        if not self.pending_trays:
            self.trays.offer(request, prediction, self.data.tracking)

    def advance(self, now=None):
        registration, calibration = self.registration, self.calibration
        if self.closed:
            return
        now = perf_counter() if now is None else now
        self._poll_direct_trays()
        completed = self.worker.poll()
        if completed is not None:
            request, prediction, error = completed
            diag_error = error or request.get("automatic_error") or request.get("candidate_error")
            if diag_error is not None or request.get("runtime_diagnostics") is not None:
                self._write_diagnostics("task_error" if diag_error is not None else request["kind"],
                                        request=request, error=diag_error)
            if request["generation"] == self.generation:
                if request["kind"] == "facing":
                    self._accept_geometry(request, prediction, error)
                    prediction = error = None
                elif request["kind"] == "automatic_recovery":
                    self._accept_automatic_result(request, prediction, error)
                    prediction = error = None
                elif request["kind"].startswith("recovery_"):
                    self._accept_recovery_result(request, prediction, error)
                    prediction = error = None
                elif request.get("recovery_candidate") is not None and self.recovery is not None:
                    self.recovery.accept(request, request.get("candidate_result"), request.get("candidate_error"))
                self.automatic_recovery.accept_propagation(request)
                if self.recovery is not None:
                    for candidate, result, failure in request.get("automatic_updates", []):
                        if candidate is self.recovery._candidate:
                            self.recovery.accept({**request, "recovery_candidate": candidate}, result, failure)
                registration.accept_prompt_result(request, prediction)
                if request["kind"] == "trays" and self.data.current.prediction is None:
                    prediction = None
                if request["kind"] == "recalibrate" and not calibration.accept_result(request, prediction, error):
                    prediction = error = None
                if error is not None:
                    self.trays.invalidate()
                    self.data.finish_motion("model_error", self.source.metadata())
                    self.model_failed = True
                    if self.recovery is not None:
                        self.recovery.cancel(force=True)
                    self.note = f"Model/tracking error: {error}. R resets the session."
                elif prediction is not None:
                    prediction["accepted_at"] = perf_counter()
                    prediction = registration.merge_trays(request, prediction)
                    propagation = request["kind"] == "propagate"
                    recovery_target = None
                    if propagation and self.recovery is not None:
                        uid = (self.data.units.bindings.get(self.recovery.pending_binding)
                               if self.recovery.pending_binding is not None else self.recovery.review_unit_id)
                        state = self.data.tracking.get(uid)
                        if state is not None and state.status == "failed":
                            recovery_target = state
                    accepted = self.data.accept_observation(
                        prediction, request["frame"], request["metadata"],
                        disappearance_seconds=self.disappearance_seconds if self.registration_locked else None,
                        resume_visible_masks=propagation)
                    if accepted and request["kind"] != "propagate":
                        self.worker.commit_facing(request)
                        self.trays.attempts.update(request.get("tray_attempts") or {})
                    self.prediction_raw_frame = request.get("raw_frame")
                    if accepted and propagation:
                        if recovery_target is not None and recovery_target.status == "tracking":
                            self.recovery.cancel()
                        self._queue_geometry(request)
                    if accepted and request["kind"] == "recalibrate":
                        self._geometry_visible = self._visible_geometry_ids()
                        if self.registration_locked:
                            self.data.record_history(kind="recalibration", source=self.source.metadata())
                    if request["kind"] == "click":
                        self.last_submitted_frame = max(self.last_submitted_frame, request["metadata"]["frame_index"])
                        self.next_inference_time = now + self.inference_interval
                    elif request["kind"] == "replace":
                        self.last_submitted_frame = request["metadata"]["frame_index"]
                        self.next_inference_time = now + self.inference_interval
                    elif request["kind"] == "start_tracker":
                        self.start_stream(now)
                    self.mark_changed(geometry=request["kind"] != "propagate")
                    self.note = self._tracking_note()
                    if request["kind"] in ("click", "replace"):
                        self.note = "Mask updated. Assign its type to confirm and fit this unit's tray."
                elif request["kind"] == "replace":
                    self.last_submitted_frame = -1
                    self.note = ("Point undone. Manual masks remain." if self.data.current.prediction is not None else
                                 "Point undone. No objects remain; click to register again.")
                elif request["kind"] == "load":
                    self.note = ("Weights loaded. Preparing rectified first-frame features." if self.data.board.homography is not None else
                                 "Weights loaded. Confirm the table corners to focus the battlefield.")
                elif request["kind"] == "prepare":
                    self.startup_ready = True
                    self.note = f"SAM3 and first-frame features ready on {self.worker.predictor.device}. Segment targets; Tab labels."
                if (request["kind"] in ("reset", "load") and self.registration_locked and not self.playback_started
                        and self.worker.models_loaded and not self.needs_load and error is None):
                    self.startup_ready = True
                    self.capture_facing_references()
                    self.note = "Saved registration loaded. Start video when ready."
        if self.playing:
            target = min(self.end_index, self.play_start_frame + int((now - self.play_start) * self.source.fps))
            if target > self.source.frame_index:
                try:
                    self.data.current.frame = self._warp_frame(self.source.read_frame(target))
                except (OSError, ValueError, cv2.error) as error:
                    self.playing = False
                    self.note = str(error)
            if target >= self.end_index:
                self.playing = False
                if not self.model_failed:
                    self.note = "Video interval complete. Final registration references are already saved."
        self._poll_direct_trays()
        self.trays.start((self.data.current.prediction or {}).get("trays", {}))
        self.schedule(now)
        self._poll_history()

        progress = self.worker.load_progress
        if progress != self.load_progress or progress is not None:
            self.load_progress = progress

    def pause_source(self):
        self.playing = False

    def reset(self):
        self.trays.invalidate()
        self.pending_trays.clear()
        self.worker.tracker_initialized = self.worker.tracker is None
        self.tray_versions.clear()
        self._geometry_visible = set()
        self.worker.facing_references.clear()
        self.worker.facing_states.clear()
        self.worker.facing_fronts.clear()
        self.automatic_recovery.invalidate("Registration reset", reset=True)
        if self.recovery is not None:
            self.recovery.cancel(force=True)
        self.presented_frame = None
        self.playing = self.pending_play = self.playback_started = False
        self.data.finish_motion("reset", self.source.metadata())
        if self.data.history_store is not None:
            self.retired_histories.append(self.data.history_store)
            self.data.history_store = None
        self.data.reference_folder = None
        self.data.history.clear()
        self.data.global_history.clear()
        self.data.motion_recorder.reset()
        self.data.tracking.clear()
        self.data.rules.fronts.clear()
        self.generation += 1
        self.needs_reset = True
        self.needs_load = not self.worker.models_loaded
        self.needs_prepare = True
        self.startup_ready = False
        self.data.current.frame = self._warp_frame(self.source.read_frame(self.registration_start_frame))
        self.data.current.prediction = self.data.current.prediction_frame = self.data.current.prediction_metadata = None
        self.data.current.geometry_frame = None
        self.prediction_raw_frame = None
        self.last_submitted_frame = -1
        self.next_inference_time = 0
        self.model_failed = False
        self.mark_changed()
        self.note = "Reset. Old in-flight results will be discarded."

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.automatic_recovery.invalidate("Session closed", reset=True)
        if self.recovery is not None:
            self.recovery.cancel(force=True)
        self.playing = False
        self.data.finish_motion("session_closed", self.source.metadata())
        self.source.close()
        self.worker.close()
        self.trays.close()
        for store in self._history_stores():
            if not store.close():
                print(f"History not saved on exit: {store.path}: {store.pending_count} updates remain in RAM; "
                      f"they will be lost when the process exits. {store.error}", file=sys.stderr, flush=True)
        self._write_diagnostics("session_closed")
        if self._fault_file is not None:
            try:
                faulthandler.disable()
                self._fault_file.close()
            except Exception:
                pass
            self._fault_file = None
