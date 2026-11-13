"""Live window selection and query presentation, derived from application snapshots."""
import cv2
import numpy as np

from frontend.presentation import unit_uncertainties
from components.homography import transform_points


MOVE_ORDERS = (
    ("advance", "Advance"), ("double", "Double"), ("back", "Back"),
    ("sidestep_left", "Sidestep left"), ("sidestep_right", "Sidestep right"),
    ("change_facing", "Change facing"), ("halt", "Halt"),
)


class LiveSelection:
    def __init__(self, match):
        self.match = match
        self.unit_id = self.target_id = None
        self.tool, self.order = "select", "advance"
        self.anchor = (0.5, 0.5)
        self.note = ""
        self._generation = None
        self._center_key = None
        self._center = None

    def clear(self):
        self.unit_id = self.target_id = None
        self.tool, self.note = "select", ""
        self.match.geometry.clear()

    def sync(self, state):
        if self._generation != state.source_ref.generation or state.stage != "playback":
            if self.unit_id is not None or self.tool != "select":
                self.clear()
            self._generation = state.source_ref.generation
        if self.unit_id is not None and self.unit_id not in state.units.units:
            self.clear()
        if self.target_id is not None and self.target_id not in state.units.units:
            self.target_id = None
            self.match.geometry.clear()

    @staticmethod
    def object_id(state, unit_id):
        return next((obj for obj, uid in state.units.bindings.items() if uid == unit_id), None)

    @staticmethod
    def hit(state, x, y):
        prediction = state.current.prediction or {}
        for obj, mask in reversed(list(zip(prediction.get("object_ids", ()), prediction.get("masks", ())))):
            if obj not in state.units.bindings:
                continue
            tray = prediction.get("trays", {}).get(obj)
            if mask[int(y), int(x)] or (tray is not None and cv2.pointPolygonTest(
                    np.asarray(tray["corners_image"], np.float32), (float(x), float(y)), False) >= 0):
                return state.units.bindings[obj]
        return None

    def unavailable(self, state, unit_id):
        obj = self.object_id(state, unit_id)
        if obj is None:
            return "Select a registered unit."
        prediction = state.current.prediction or {}
        tracking = state.tracking.get(unit_id)
        if (obj in prediction.get("unavailable_ids", ()) or obj in prediction.get("inactive_ids", ()) or
                tracking is not None and (not tracking.active or tracking.status == "failed")):
            return "This unit has no accepted tracking position."
        if obj in prediction.get("estimated_ids", ()):
            return "Confirm the Estimated mask before querying this unit."
        if obj not in prediction.get("trays", {}):
            return "No accepted tray geometry is available for this unit."
        return ""

    def click(self, state, x, y, positive=True):
        if state.stage != "playback":
            return
        if not positive:
            self.escape()
            return
        unit_id = self.hit(state, x, y)
        if unit_id is None:
            self.clear()
            return
        if self.tool in ("distance", "los"):
            self.target_id = unit_id if unit_id != self.unit_id else None
            self.request(state)
            return
        self.unit_id, self.target_id = unit_id, None
        self.tool, self.note = "select", ""
        height, width = state.current.frame.shape[:2]
        self.anchor = (x / width, y / height)
        self.match.geometry.clear()

    def inspect(self, unit_id, state):
        if state.stage != "playback" or unit_id not in state.units.units:
            return
        self.unit_id, self.target_id = unit_id, None
        self.tool, self.note = "select", ""
        center = self.center(state, self.object_id(state, unit_id))
        self.anchor = tuple(center) if center is not None else (0.5, 0.5)
        self.match.geometry.clear()

    def uncertainty(self, state):
        rows = {"A": [], "B": []}
        if state.stage == "playback":
            for obj, unit_id in state.units.bindings.items():
                issues = unit_uncertainties(state, obj)
                if not issues:
                    continue
                unit = state.units.units[unit_id]
                catalog = state.units.types[unit["type_id"]]
                rows[catalog.get("list_id", "A")].append(dict(
                    unitId=unit_id, name=catalog.get("unit_name", catalog.get("name", unit["type_id"])),
                    details="\n".join(f"{kind.title()}: {status}" for kind, status in issues.items())))
        return dict(rowsA=rows["A"], rowsB=rows["B"], count=len(rows["A"]) + len(rows["B"]))

    def set_tool(self, tool, state):
        if state.stage != "playback" or tool not in ("distance", "los", "move"):
            return
        self.tool, self.target_id = tool, None
        self.request(state)

    def set_order(self, order, state):
        if self.tool == "move" and order in dict(MOVE_ORDERS) and order != self.order:
            self.order = order
            self.request(state)

    def request(self, state):
        self.note = self.unavailable(state, self.unit_id)
        if self.note or self.tool == "select":
            self.match.geometry.clear()
            return
        if self.tool in ("distance", "los"):
            if self.target_id is None:
                self.match.geometry.clear()
                return
            self.note = self.unavailable(state, self.target_id)
            if self.note:
                self.match.geometry.clear()
                return
        ids = [self.unit_id] + ([self.target_id] if self.tool in ("distance", "los") else [])
        receipt = self.match.geometry.query(self.order if self.tool == "move" else self.tool,
                                            ids, state.observation_ref, state.current.view_revision)
        self.note = receipt.reason if receipt.status == "rejected" else ""

    def done(self):
        self.tool, self.target_id, self.note = "select", None, ""
        self.match.geometry.clear()

    def escape(self):
        self.done() if self.tool != "select" else self.clear()

    def center(self, state, obj):
        key = (state.source_ref.generation, state.current.view_revision, obj)
        if key != self._center_key:
            self._center_key, self._center = key, None
            prediction = state.current.prediction or {}
            if obj not in (*prediction.get("unavailable_ids", ()), *prediction.get("inactive_ids", ())):
                tray = prediction.get("trays", {}).get(obj)
                if tray is not None:
                    self._center = np.asarray(tray["corners_image"]).mean(axis=0)
                else:
                    for object_id, mask in zip(prediction.get("object_ids", ()), prediction.get("masks", ())):
                        if object_id == obj:
                            yy, xx = np.nonzero(mask)
                            if len(xx):
                                self._center = np.array([(xx.min() + xx.max()) / 2, (yy.min() + yy.max()) / 2])
                            break
        if self._center is None:
            return None
        return (self._center / np.asarray(state.current.frame.shape[1::-1])).tolist()

    def query_view(self, state):
        title = {"distance": "Distance", "los": "Line of sight", "move": "Movement preview"}.get(self.tool, "")
        reason = self.note or ("Click a second unit." if self.tool in ("distance", "los") and self.target_id is None
                               else "Waiting for the current observation…")
        result = self.match.geometry.result
        request = self.match.geometry.result_request
        current = result is not None and (request is None or self.match.geometry.result_current(state))
        view = dict(title=title, status="waiting", metric="", reason=reason, warnings=[], observed="—",
                    showDistance=False, labelX=0.5, labelY=0.5)
        if not current:
            return view
        view.update(status=result.get("status", "unavailable"), reason=result.get("reason", ""),
                    warnings=list(result.get("warnings", ())))
        if "distance_in" in result:
            view["metric"] = f"{result['distance_in']:.2f} in · {result['distance_mm']:.1f} mm"
            if self.tool == "distance" and request is not None:
                points = transform_points([result["point_a_mm"], result["point_b_mm"]],
                                          np.linalg.inv(request["image_to_plane"]))
                center = points.mean(axis=0) / np.asarray(state.current.frame.shape[1::-1])
                view.update(showDistance=True, labelX=float(center[0]), labelY=float(center[1]))
        elif self.tool == "move" and result.get("status") != "unavailable":
            view["metric"] = f"{len(result.get('poses', ()))} sampled poses"
        if request is not None:
            view["observed"] = f"{request['metadata']['timestamp_seconds']:.2f}s"
        return view

    def data(self, state):
        obj = self.object_id(state, self.unit_id)
        unit = state.units.units.get(self.unit_id)
        catalog = state.units.types.get(unit["type_id"], {}) if unit else {}
        profile = {**catalog.get("attributes", {}), **unit["attributes"]} if unit else {}
        text = lambda value: "—" if value is None else str(value)
        speed = profile.get("speed_in")
        center = self.center(state, obj) if obj is not None else None
        unavailable = self.unavailable(state, self.unit_id) if self.unit_id else "Select a unit on the board."
        return dict(selected=unit is not None, unitId=self.unit_id or "", targetId=self.target_id or "",
                    name=catalog.get("unit_name", catalog.get("name", "")), damage=text(profile.get("damage")),
                    speed="—" if speed is None else f"{speed}″", tool=self.tool, order=self.order,
                    anchorX=self.anchor[0], anchorY=self.anchor[1], centerX=center[0] if center else 0,
                    centerY=center[1] if center else 0, hasPosition=center is not None,
                    canQuery=unit is not None and not unavailable, queryBlock=unavailable,
                    query=self.query_view(state),
                    caption=(f"{self.tool.title()} · {self.unit_id}" if self.tool != "select" else
                             f"{self.unit_id} selected · Esc clears" if self.unit_id else "Select a unit on the board"))
