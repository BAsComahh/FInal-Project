"""Serialize model operations outside the playback/UI thread."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib.metadata
import hashlib
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import numpy as np

from components.sam3.video import VideoPredictor


def _point_ids(clicks):
    groups = {}
    for click in clicks:
        groups.setdefault(click["object_id"], []).append(click["click_id"])
    return groups


class TaskWorker:
    """One in-flight request; playback never waits for its result."""

    def __init__(self, model_id="facebook/sam3", device=None, *, profile=False, tray_search="full"):
        if tray_search not in ("full", "local"):
            raise ValueError("tray_search must be full or local")
        self.predictor = VideoPredictor(model_id, device, profile=profile)
        self.tray_search = tray_search
        self.previous_trays = {}
        self.previous_context = None
        self.timing_dir = None
        if profile:
            self.timing_dir = Path(__file__).resolve().parents[1] / "outputs/tracking_comparison" / f"sam_{uuid4().hex[:12]}"
            self.timing_dir.mkdir(parents=True)
            run = {"model": model_id, "requested_device": device, "profile": True, "tray_search": tray_search,
                   "versions": {name: importlib.metadata.version(name) for name in ("torch", "transformers", "opencv-python")},
                   "model_precision": "float32", "inference_state_device": "cpu"}
            root = Path(__file__).resolve().parents[1]
            run["source_hashes"] = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in (
                "frontend/task_worker.py", "components/sam3/video/predictor.py", "components/boundary_detection/tray/detector.py")}
            (self.timing_dir / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
            print(f"Tracking timing log: {self.timing_dir}", flush=True)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sam3-video")
        self.future = self.request = None
        self.prompts = []
        self.tray_context = None

    @property
    def busy(self):
        return self.future is not None

    def _run(self, request):
        started = perf_counter()
        kind = request["kind"]
        if kind == "load":
            self.predictor.load()
            return None
        if kind == "prepare":
            self.predictor.prepare_initial_frame(request["frame"], source_frame=request["metadata"]["frame_index"])
            return None
        if kind == "reset":
            self.predictor.reset()
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
        elif kind == "propagate":
            prediction = self.predictor.propagate(request["frame"],
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
                      "source_frame_index": metadata.get("frame_index"),
                      "observation_time_seconds": metadata.get("timestamp_seconds"),
                      "submitted_at": request["submitted_at"], "started_at": started, "completed_at": finished,
                      "request_seconds": finished - started, "device": self.predictor.device, "error": error}
            if prediction is not None:
                record.update(object_ids=prediction["object_ids"], timings_seconds=prediction["timings_seconds"],
                              timing_gpu_synchronized=prediction.get("timing_gpu_synchronized", False),
                              inference_call_count=prediction.get("inference_call_count"),
                              object_score_logits=prediction.get("object_score_logits"),
                              trays={key: {name: row[name] for name in ("method", "mask_coverage", "edge_support")}
                                     for key, row in prediction.get("trays", {}).items()})
            with (self.timing_dir / "observations.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record) + "\n")

    def submit(self, kind, *, frame=None, metadata=None, prompt=None, generation=0, clicks=None, prediction=None):
        if self.busy:
            raise RuntimeError("A SAM3 request is already in flight")
        self.request = {"kind": kind, "frame": frame.copy() if frame is not None else None,
                        "metadata": dict(metadata) if metadata is not None else None,
                        "prompt": prompt, "generation": generation, "clicks": deepcopy(clicks),
                        "prediction": prediction, "tray_context": deepcopy(self.tray_context)}
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
