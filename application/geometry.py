"""Coalesced live-observation queries with independent asynchronous results."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from .contracts import CommandReceipt, freeze


def _query(scene, mode, unit_ids):
    from components.game_rules import line_of_sight, measure_distance, reachable_poses

    if mode == "distance":
        return measure_distance(scene, *unit_ids[:2])
    if mode == "los":
        return line_of_sight(scene, *unit_ids[:2])
    return reachable_poses(scene, unit_ids[0], order=mode)


class GeometryQueries:
    def __init__(self, session):
        self._session = session
        self._parameters = None
        self.result = self._request = self._future = self._last_key = None
        self.result_request = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="game-rules")
        self.epoch = 0

    def invalidate(self):
        self.epoch += 1
        self._last_key = self.result = None
        self.result_request = None

    def result_current(self, view):
        request = self.result_request
        metadata = view.current.prediction_metadata
        return (request is not None and metadata is not None and
                request["view_revision"] == view.current.view_revision and
                request["metadata"]["frame_index"] == metadata["frame_index"] and
                request["metadata"].get("calibration_version") == view.board.calibration_version)

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
        needed = 2 if mode in ("distance", "los") else 1
        if len(unit_ids) != needed:
            return CommandReceipt("rejected", f"{mode}: click {needed} unit{'s' if needed > 1 else ''}.")
        self._parameters = mode, tuple(unit_ids)
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
                    self.result = freeze(future.result())
                except Exception as error:
                    self.result = freeze({"status": "unavailable", "reason": str(error)})
                self.result_request = freeze(request)
                changed = True
        if session.data.current.prediction is None and self.result is not None:
            self.invalidate()
            changed = True
        if self._parameters is None or view.current.prediction is None:
            return changed
        mode, ids = self._parameters
        key = (self._parameters, view.current.view_revision, session.generation, self.epoch)
        if self._future is not None or key == self._last_key:
            return changed
        self._last_key = key
        try:
            scene = view.rules.scene(view.units, view.current.prediction, view.board.image_to_plane,
                                      view.board.board_size_mm, view.current.prediction_metadata,
                                      source_to_plane=view.board.source_to_plane)
        except ValueError as error:
            self.result = freeze({"status": "unavailable", "reason": str(error)})
            self.result_request = None
            return True
        self._request = {"epoch": self.epoch, "generation": session.generation,
                        "view_revision": view.current.view_revision,
                        "metadata": deepcopy(view.current.prediction_metadata), "image_to_plane": view.board.image_to_plane.copy()}
        self._future = self._executor.submit(_query, scene, mode, ids)
        return True

    def clear(self):
        self._parameters = None
        self.invalidate()

    def close(self):
        self._executor.shutdown(wait=False, cancel_futures=True)
