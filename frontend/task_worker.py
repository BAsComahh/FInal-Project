"""Serialize model operations outside the playback/UI thread."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from time import perf_counter

from components.sam3.video import VideoPredictor


def _point_ids(clicks):
    groups = {}
    for click in clicks:
        groups.setdefault(click["object_id"], []).append(click["click_id"])
    return groups


class TaskWorker:
    """One in-flight request; playback never waits for its result."""

    def __init__(self, model_id="facebook/sam3", device=None):
        self.predictor = VideoPredictor(model_id, device)
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
        else:
            raise ValueError(f"Unknown SAM3 operation: {kind}")
        if prediction is not None:
            if request["tray_context"] is not None:
                from components.boundary_detection.tray.batch import fit_registered_trays

                prediction["trays"], prediction["tray_errors"] = fit_registered_trays(
                    request["frame"], prediction, request["tray_context"])
            prediction["inference_seconds"] = perf_counter() - started
        return prediction

    def submit(self, kind, *, frame=None, metadata=None, prompt=None, generation=0, clicks=None, prediction=None):
        if self.busy:
            raise RuntimeError("A SAM3 request is already in flight")
        self.request = {"kind": kind, "frame": frame.copy() if frame is not None else None,
                        "metadata": dict(metadata) if metadata is not None else None,
                        "prompt": prompt, "generation": generation, "clicks": deepcopy(clicks),
                        "prediction": prediction, "tray_context": deepcopy(self.tray_context)}
        self.future = self.executor.submit(self._run, self.request)

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
