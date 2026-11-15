"""Coalesced live-observation queries with independent asynchronous results."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event
from .contracts import CommandReceipt, freeze


def _query(scene, mode, unit_ids):
    from components.game_rules import line_of_sight, measure_distance, reachable_poses

    if mode == "distance":
        return measure_distance(scene, *unit_ids[:2])
    if mode == "los":
        return line_of_sight(scene, *unit_ids[:2])
    return reachable_poses(scene, unit_ids[0], order=mode)


def _snapshot_distance(view, unit_ids, context, cancelled):
    """Fit one detached observation; never publish geometry to the live match."""
    from .tray_worker import update_trays
    from components.boundary_detection.tray.temporal import TrayStability

    prediction, metadata = view.current.prediction, view.current.prediction_metadata
    selected = {obj for obj, uid in view.units.bindings.items() if uid in unit_ids}
    prediction = {**prediction, "trays": {}, "tray_errors": {}, "facing_results": {}}
    request = dict(kind="query", frame=view.current.prediction_frame, metadata=metadata,
                   prediction=prediction, tray_context=context, tray_ids=tuple(selected), tray_cancelled=cancelled)
    prediction = update_trays(request, prediction, search="full", stability=TrayStability())
    if cancelled.is_set():
        raise ValueError("Snapshot query cancelled")
    rectangles = {obj: tray["corners_image"] for obj, tray in prediction["trays"].items() if obj in selected}
    missing = selected - prediction["trays"].keys()
    if missing:
        reasons = [f"{view.units.bindings[obj]}: {prediction['tray_errors'].get(obj, 'No tray dimensions or usable mask')}"
                   for obj in sorted(missing)]
        return {"status": "unavailable", "reason": "; ".join(reasons)}, rectangles
    scene = view.rules.scene(view.units, prediction, view.board.image_to_plane,
        view.board.board_size_mm, metadata, source_to_plane=view.board.source_to_plane)
    result = _query(scene, "distance", unit_ids)
    result["warnings"] = [*result.get("warnings", ()),
        f"Snapshot at {metadata['timestamp_seconds']:.2f}s; playback continues and this result stays fixed."]
    return result, rectangles


class GeometryQueries:
    def __init__(self, session):
        self._session = session
        self._parameters = None
        self.result = self._request = self._future = self._last_key = None
        self.result_request = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="game-rules")
        self.epoch = 0
        self._cancelled = Event()
        self._pending = None

    def invalidate(self):
        self._cancelled.set()
        self._cancelled = Event()
        self._pending = None
        self.epoch += 1
        self._last_key = self.result = None
        self.result_request = None

    def result_current(self, view):
        request = self.result_request
        metadata = (view.current.prediction or {}).get("geometry_metadata", view.current.prediction_metadata)
        if (request is None or request["epoch"] != self.epoch or request["generation"] != self._session.generation
                or request["metadata"].get("calibration_version") != view.board.calibration_version):
            return False
        if request.get("fixed"):
            return True
        return (metadata is not None and
                request["view_revision"] == view.current.geometry_revision and
                request["metadata"]["frame_index"] == metadata["frame_index"])

    def query(self, mode, unit_ids, reference, revision):
        session, data = self._session, self._session.data
        self._parameters = None
        self.invalidate()
        if mode is None:
            return CommandReceipt("accepted")
        metadata = data.current.prediction_metadata
        if (session.closed or reference is None or metadata is None or reference.generation != session.generation or
                reference.calibration_version != data.board.calibration_version or
                reference.frame_index != metadata["frame_index"] or revision != data.current.view_revision):
            return CommandReceipt("rejected", "Query requires the current accepted observation.")
        if any(uid not in data.units.units for uid in unit_ids):
            return CommandReceipt("rejected", "A selected unit is no longer registered.")
        if not session.tray_fitting and mode != "distance":
            self.result = freeze({"status": "not_implemented", "reason": "Not implemented"})
            return CommandReceipt("accepted", "Not implemented")
        needed = 2 if mode in ("distance", "los") else 1
        if len(unit_ids) != needed:
            return CommandReceipt("rejected", f"{mode}: click {needed} unit{'s' if needed > 1 else ''}.")
        self._parameters = mode, tuple(unit_ids)
        if not session.tray_fitting:
            prediction = data.current.prediction
            selected = {obj for obj, uid in data.units.bindings.items() if uid in unit_ids}
            unavailable = (set(prediction.get("unavailable_ids", ())) | set(prediction.get("inactive_ids", ()))
                           | set(prediction.get("estimated_ids", ())))
            masks = dict(zip(prediction["object_ids"], prediction["masks"]))
            if len(selected) != needed or any(obj in unavailable or obj not in masks or not masks[obj].any() for obj in selected):
                return CommandReceipt("rejected", "Snapshot queries require accepted, visible unit masks.")
            if session.worker.tray_context is None:
                return CommandReceipt("rejected", "Confirm metric table calibration before querying geometry.")
            request = {"epoch": self.epoch, "generation": session.generation, "fixed": True,
                       "mode": mode, "unit_ids": tuple(unit_ids), "view_revision": revision,
                       "metadata": deepcopy(metadata), "image_to_plane": data.board.image_to_plane.copy()}
            self._pending = request, data.snapshot(), deepcopy(session.worker.tray_context), self._cancelled
        return CommandReceipt("pending", request_id=self.epoch)

    def tick(self):
        session = self._session
        view = session.data
        changed = False
        if self._future is not None and self._future.done():
            future, self._future = self._future, None
            request = self._request
            if request["epoch"] == self.epoch and request["generation"] == session.generation:
                try:
                    result = future.result()
                    if request.get("fixed"):
                        result, rectangles = result
                        request = {**request, "rectangles": rectangles}
                    self.result = freeze(result)
                except Exception as error:
                    self.result = freeze({"status": "unavailable", "reason": str(error)})
                self.result_request = freeze(request)
                changed = True
        if session.data.current.prediction is None and self.result is not None:
            self.invalidate()
            changed = True
        if self._pending is not None and self._future is None:
            request, snapshot, context, cancelled = self._pending
            self._pending = None
            if (request["generation"] == session.generation and
                    request["metadata"].get("calibration_version") == view.board.calibration_version):
                self._request = request
                self._future = self._executor.submit(_snapshot_distance, snapshot, request["unit_ids"], context, cancelled)
        if not session.tray_fitting or self._parameters is None or view.current.prediction is None:
            return changed
        mode, ids = self._parameters
        key = (self._parameters, view.current.geometry_revision, session.generation, self.epoch)
        if self._future is not None or key == self._last_key:
            return changed
        self._last_key = key
        try:
            scene = view.rules.scene(view.units, view.current.prediction, view.board.image_to_plane,
                                      view.board.board_size_mm,
                                      view.current.prediction.get("geometry_metadata", view.current.prediction_metadata),
                                      source_to_plane=view.board.source_to_plane)
        except ValueError as error:
            self.result = freeze({"status": "unavailable", "reason": str(error)})
            self.result_request = None
            return True
        self._request = {"epoch": self.epoch, "generation": session.generation,
                        "view_revision": view.current.geometry_revision,
                        "metadata": deepcopy(view.current.prediction.get("geometry_metadata", view.current.prediction_metadata)),
                        "image_to_plane": view.board.image_to_plane.copy()}
        self._future = self._executor.submit(_query, scene, mode, ids)
        return True

    def clear(self):
        self._parameters = None
        self.invalidate()

    def close(self):
        self._cancelled.set()
        self._pending = None
        self._executor.shutdown(wait=False, cancel_futures=True)
