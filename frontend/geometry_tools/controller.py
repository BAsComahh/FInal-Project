"""Frozen-scene query selection, request epochs and asynchronous rule results."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy


def _query(scene, mode, unit_ids):
    from components.game_rules import line_of_sight, measure_distance, reachable_poses

    if mode == "distance":
        return measure_distance(scene, *unit_ids[:2])
    if mode == "los":
        result = line_of_sight(scene, *unit_ids[:2])
        if result.get("status") == "clear" and any("incomplete" in warning for warning in scene.get("warnings", [])):
            result.update(status="uncertain", reason="A registered unit has no valid tray; occlusion geometry is incomplete.")
        return result
    return reachable_poses(scene, unit_ids[0], order=mode)


class GeometryController:
    ORDERS = ("advance", "back", "sidestep_left", "sidestep_right", "change_facing", "halt")

    def __init__(self):
        self.mode = None
        self.selected = []
        self.result = self.overlay = self.request = self.future = self.last_key = None
        self.result_request = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="game-rules")
        self.epoch = 0
        self.note = "Select a rule tool, then click one or two units. Registered scene only."

    def invalidate(self):
        self.epoch += 1
        self.last_key = self.result = self.overlay = None
        self.result_request = None

    def select(self, object_id):
        if self.mode in ("distance", "los"):
            if object_id in self.selected:
                self.selected.remove(object_id)
            else:
                self.selected = (self.selected + [object_id])[-2:]
        else:
            self.selected = [object_id]
        self.invalidate()

    def query(self, mode):
        if mode == "move":
            self.mode = self.ORDERS[(self.ORDERS.index(self.mode) + 1) % len(self.ORDERS)] if self.mode in self.ORDERS else "advance"
        else:
            self.mode = None if self.mode == mode else mode
        self.invalidate()

    def tick(self, presentation, session):
        view = presentation
        changed = False
        if self.future is not None and self.future.done():
            future, self.future = self.future, None
            request = self.request
            if request["epoch"] == self.epoch and request["generation"] == session.generation:
                try:
                    self.result = future.result()
                except Exception as error:
                    self.result = {"status": "unavailable", "reason": str(error)}
                self.result_request = request
                self.overlay = None
                changed = True
        if session.data.current.prediction is None and self.result is not None:
            self.invalidate()
            changed = True
        if self.mode is None or view.current.prediction is None:
            return changed
        needed = 2 if self.mode in ("distance", "los") else 1
        if len(self.selected) < needed:
            self.note = f"{self.mode}: click {needed} unit{'s' if needed > 1 else ''}."
            return changed
        key = (self.mode, tuple(self.selected), view.current.view_revision, session.generation, self.epoch)
        if self.future is not None or key == self.last_key:
            return changed
        self.last_key = key
        try:
            scene = view.rules.scene(view.units, view.current.prediction, view.board.image_to_plane,
                                          view.board.board_size_mm, view.current.prediction_metadata)
            ids = [view.units.bindings[object_id] for object_id in self.selected[:needed]]
        except (ValueError, KeyError) as error:
            self.result = {"status": "unavailable", "reason": str(error)}
            self.result_request = None
            self.overlay = None
            return True
        self.request = {"epoch": self.epoch, "generation": session.generation,
                        "metadata": deepcopy(view.current.prediction_metadata), "image_to_plane": view.board.image_to_plane.copy()}
        self.future = self.executor.submit(_query, scene, self.mode, ids)
        return True

    def clear(self):
        self.mode = None
        self.selected.clear()
        self.invalidate()

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
