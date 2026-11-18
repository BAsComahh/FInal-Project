"""Bounded CPU tray fitting; model work remains on TaskWorker's serial queue."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from time import perf_counter

from components.boundary_detection.tray.batch import fit_registered_trays


def update_trays(request, prediction, *, search, stability, previous=None):
    """Fit requested IDs and merge their results, shared by registration and Live."""
    prediction = {**prediction, "geometry_pending": False}
    context, kind = request["tray_context"], request["kind"]
    metadata = request["metadata"]
    if kind == "facing":
        prediction.pop("facing_results", None)
    if context is None:
        prediction.update(trays={}, tray_errors={}, tray_fit_stats={})
        return prediction
    corrected = (request.get("automatic_applied", []) if kind == "automatic_recovery" else
                 [request["recovery_object_id"]] if kind == "recovery_commit" else [])
    targets = corrected if corrected else request.get("tray_ids")
    target = prediction
    if corrected:
        old = request.get("prediction") or {}
        if old.get("geometry_metadata", {}).get("frame_index") != request["metadata"]["frame_index"]:
            # A scoped mask commit still needs a common geometry frame for the other units.
            normal = [i for i, obj in enumerate(prediction["object_ids"]) if obj not in corrected
                      and obj not in old.get("unavailable_ids", ()) and obj not in old.get("inactive_ids", ())]
            batch = {"object_ids": [prediction["object_ids"][i] for i in normal], "masks": prediction["masks"][normal]}
            trays, errors = fit_registered_trays(request["frame"], batch, context,
                previous=old.get("trays", {}) if search != "full" else None, reuse_stable=search == "adaptive",
                stability=stability, source_frame=metadata["frame_index"], source_time=metadata.get("timestamp_seconds"))
            old = {**old, "trays": trays, "tray_errors": errors}
            request["prediction"] = old
    if targets is not None:
        selected = [i for i, obj in enumerate(prediction["object_ids"]) if obj in targets]
        target = {"object_ids": [prediction["object_ids"][i] for i in selected], "masks": prediction["masks"][selected]}
    elif kind == "facing":
        excluded = set(prediction.get("unavailable_ids", ())) | set(prediction.get("inactive_ids", ()))
        selected = [i for i, obj in enumerate(prediction["object_ids"]) if obj not in excluded]
        target = {"object_ids": [prediction["object_ids"][i] for i in selected], "masks": prediction["masks"][selected]}
    attempts = {}
    trays, errors = fit_registered_trays(request["frame"], target, context,
        previous=previous if search != "full" else None, reuse_stable=search == "adaptive",
        stability=stability, source_frame=metadata["frame_index"], source_time=metadata.get("timestamp_seconds"),
        attempts=attempts)
    if targets is not None:
        old = request.get("prediction") or {}
        prediction["trays"] = {**{obj: tray for obj, tray in old.get("trays", {}).items() if obj not in targets}, **trays}
        prediction["tray_errors"] = {**{obj: error for obj, error in old.get("tray_errors", {}).items() if obj not in targets}, **errors}
    else:
        prediction.update(trays=trays, tray_errors=errors)
    request["tray_attempts"] = attempts
    prediction["tray_fit_stats"] = dict(reused=sum(tray["method"] == "stable_reuse" for tray in trays.values()),
        refitted=sum(row["attempted"] for row in attempts.values()), unavailable=len(errors),
        retry_wait=sum(not row["attempted"] and "corners_image" not in row for row in attempts.values()))
    return prediction


class TrayWorker:
    """One running batch and one replaceable latest batch, committed by the owner."""
    def __init__(self, search, stability):
        self.search, self.stability = search, stability
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tray-fit")
        self.future = self.request = self.pending = self.awaiting = None
        self.epoch = 0
        self.attempts = {}

    @property
    def busy(self):
        return self.future is not None or self.pending is not None or self.awaiting is not None

    def invalidate(self, object_ids=None):
        self.epoch += 1
        self.pending = self.awaiting = None
        if object_ids is None:
            self.attempts.clear()
        else:
            for obj in object_ids:
                self.attempts.pop(obj, None)

    def offer(self, request, prediction, tracking):
        self.pending = {**{key: request[key] for key in ("frame", "metadata", "raw_frame", "generation")},
                        "kind": "facing", "prediction": dict(prediction),
                        "tray_context": deepcopy(request["tray_context"]), "tray_epoch": self.epoch,
                        "tracking": deepcopy(tracking)}

    def start(self, previous):
        if self.future is not None or self.awaiting is not None or self.pending is None:
            return
        request, self.pending = self.pending, None
        excluded = set(request["prediction"].get("unavailable_ids", ())) | set(request["prediction"].get("inactive_ids", ()))
        prior = {obj: row for obj, row in {**previous, **self.attempts}.items() if obj not in excluded}
        self.request = request
        self.future = self.executor.submit(self._fit, request, prior)

    def _fit(self, request, previous):
        started = perf_counter()
        prediction = update_trays(request, request["prediction"], search=self.search, stability=self.stability, previous=previous)
        prediction["timings_seconds"] = {**prediction.get("timings_seconds", {}), "tray_fit": perf_counter() - started}
        return prediction

    def take_ready(self):
        if self.future is None or not self.future.done():
            return None
        future, request = self.future, self.request
        self.future = self.request = None
        if request["tray_epoch"] != self.epoch:
            return None
        try:
            prediction = future.result()
        except Exception as error:
            prediction = {**request["prediction"], "trays": {},
                          "tray_errors": {obj: str(error) for obj in request["prediction"]["object_ids"]}}
        self.awaiting = request
        return request, prediction

    def accept(self, request, *, valid=True):
        if self.awaiting is None or request.get("tray_epoch") != self.epoch:
            return False
        if valid:
            self.attempts = request.get("tray_attempts") or {}
        self.awaiting = None
        return valid

    def close(self):
        self.invalidate()
        self.executor.shutdown(wait=False, cancel_futures=True)
