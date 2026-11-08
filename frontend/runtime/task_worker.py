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

from ..config import DEFAULT_TRACKER, PROJECT_ROOT
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
        if self.request is not None and self.request["kind"] == "recalibrate":
            return ("Rebuilding tracking for calibration", None, None)
        if self.tracker is not None and self.request is not None and self.request["kind"] == "start_tracker":
            return self.tracker.load_progress or (f"Preparing {self.tracker_name} memory", None, None)
        return self.predictor.load_progress or (self.tracker.load_progress if self.tracker is not None else None)

    def _run(self, request):
        started = perf_counter()
        kind = request["kind"]
        if kind == "load":
            self.predictor.load()
            if self.tracker is not None:
                self.tracker.load()
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
                previous = self.previous_trays if (kind == "propagate" and self.tray_search == "local"
                                                   and signature == self.previous_context) else None
                prediction["trays"], prediction["tray_errors"] = fit_registered_trays(
                    request["frame"], prediction, context, previous=previous)
                self.previous_trays = prediction["trays"]
                self.previous_context = signature
            else:
                self.previous_trays.clear()
                self.previous_context = None
            finished = perf_counter()
            prediction["timings_seconds"] = {**prediction.get("timings_seconds", {}),
                "worker_operation": operation_finished - started, "tray_fit": finished - operation_finished,
                "worker_total": finished - started}
            prediction["inference_seconds"] = finished - started
            metadata = request["metadata"]
            prediction.update(source_frame_index=metadata["frame_index"],
                              tracking_backend=self.tracker_name if kind in ("propagate", "start_tracker", "recalibrate") else "sam3_registration",
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
                record.update(object_ids=prediction["object_ids"], timings_seconds=prediction["timings_seconds"],
                              timing_gpu_synchronized=prediction.get("timing_gpu_synchronized", False),
                              inference_call_count=prediction.get("inference_call_count"),
                              object_score_logits=prediction.get("object_score_logits"),
                              trays={key: {name: row[name] for name in ("method", "mask_coverage", "edge_support")}
                                     for key, row in prediction.get("trays", {}).items()})
            with (self.timing_dir / "observations.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record) + "\n")

    def submit(self, kind, *, frame=None, metadata=None, prompt=None, generation=0, clicks=None, prediction=None,
               tray_context=None, raw_frame=None, calibration_token=None):
        if self.busy:
            raise RuntimeError("A SAM3 request is already in flight")
        self.request = {"kind": kind, "frame": frame.copy() if frame is not None else None,
                        "metadata": dict(metadata) if metadata is not None else None,
                        "prompt": prompt, "generation": generation, "clicks": deepcopy(clicks),
                        "prediction": prediction,
                        "raw_frame": raw_frame.copy() if raw_frame is not None else None,
                        "calibration_token": calibration_token,
                        "tray_context": deepcopy(self.tray_context if tray_context is None else tray_context)}
        self.request["submitted_at"] = perf_counter()
        self.future = self.executor.submit(self._recorded_run if self.timing_dir is not None else self._run, self.request)

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
