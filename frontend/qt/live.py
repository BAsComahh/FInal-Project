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
        self.card_anchor = (0.35, 0.5)
        self.note = ""
        self._generation = None
        self._center_key = None
        self._center = None

    def clear(self):
        self.unit_id = self.target_id = None
        self.tool, self.note = "select", ""
        self.card_anchor = (0.35, 0.5)
        self.match.geometry.clear()

    def set_card_anchor(self, x, y):
        self.card_anchor = (float(np.clip(x, 0.02, 0.98)), float(np.clip(y, 0.02, 0.98)))

    @staticmethod
    def _unit_boxes(state):
        prediction = state.current.prediction or {}
        height, width = state.current.frame.shape[:2]
        excluded = set(prediction.get("unavailable_ids", ())) | set(prediction.get("inactive_ids", ()))
        trays = prediction.get("trays", {})
        boxes = {}
        for obj, mask in zip(prediction.get("object_ids", ()), prediction.get("masks", ())):
            if obj in excluded:
                continue
            tray = trays.get(obj)
            if tray is not None:
                pts = np.asarray(tray["corners_image"], dtype=float)
                boxes[obj] = (pts[:, 0].min() / width, pts[:, 1].min() / height,
                              pts[:, 0].max() / width, pts[:, 1].max() / height)
            else:
                ys = np.flatnonzero(mask.any(axis=1))
                xs = np.flatnonzero(mask.any(axis=0))
                if len(xs):
                    boxes[obj] = (xs[0] / width, ys[0] / height, (xs[-1] + 1) / width, (ys[-1] + 1) / height)
        return boxes

    def _place_card(self, state, selected_obj, arc_anchor):
        """Place the floating left stat card via sparse sampling, penalizing distance and occluded units."""
        height, width = state.current.frame.shape[:2]
        cw = min(0.45, max(0.16, 224.0 / max(1, width)))
        ch = min(0.55, max(0.20, 185.0 / max(1, height)))
        min_x, max_x = cw * 0.5 + 0.015, max(cw * 0.5 + 0.015, 1.0 - cw * 0.5 - 0.015)
        min_y, max_y = ch * 0.5 + 0.02, max(ch * 0.5 + 0.02, 1.0 - ch * 0.5 - 0.02)

        ux, uy = float(arc_anchor[0]), float(arc_anchor[1])
        arc_cx = min(max(ux, min(0.88, 240.0 / max(1, width))), max(0.12, 1.0 - 180.0 / max(1, width)))
        arc_box = np.array([[max(0.0, arc_cx), max(0.0, uy - 0.19),
                             min(1.0, arc_cx + 185.0 / max(1, width)), min(1.0, uy + 0.19)]], dtype=float)

        boxes = self._unit_boxes(state)
        self_raw = boxes.get(selected_obj)
        self_boxes = (np.array([[max(0.0, self_raw[0] - 0.01), max(0.0, self_raw[1] - 0.01),
                                 min(1.0, self_raw[2] + 0.01), min(1.0, self_raw[3] + 0.01)]], dtype=float)
                      if self_raw is not None else np.empty((0, 4), dtype=float))
        others = [box for obj, box in boxes.items() if obj != selected_obj]
        other_boxes = np.asarray(others, dtype=float) if others else np.empty((0, 4), dtype=float)

        # Ultra-sparse candidate set: preferred left spot + 4 local rings (x16) + 8x6 full-screen grid
        cands = [(ux - cw * 0.5 - 0.03, uy)]
        angles = np.linspace(0.0, 2.0 * np.pi, 16, endpoint=False)
        for radius in (0.16, 0.24, 0.33, 0.44):
            for ang in angles:
                cands.append((ux + radius * float(np.cos(ang)), uy + radius * 0.85 * float(np.sin(ang))))
        gx = np.linspace(min_x, max_x, 8)
        gy = np.linspace(min_y, max_y, 6)
        for py in gy:
            for px in gx:
                cands.append((float(px), float(py)))

        centers = np.asarray(cands, dtype=float)
        centers[:, 0] = np.clip(centers[:, 0], min_x, max_x)
        centers[:, 1] = np.clip(centers[:, 1], min_y, max_y)

        rect_x0 = centers[:, 0:1] - cw * 0.5
        rect_y0 = centers[:, 1:2] - ch * 0.5
        rect_x1 = centers[:, 0:1] + cw * 0.5
        rect_y1 = centers[:, 1:2] + ch * 0.5
        card_area = cw * ch

        def overlap_metrics(targets):
            if not len(targets):
                return np.zeros(len(centers)), np.zeros(len(centers))
            ix = np.maximum(0.0, np.minimum(rect_x1, targets[:, 2][None, :]) - np.maximum(rect_x0, targets[:, 0][None, :]))
            iy = np.maximum(0.0, np.minimum(rect_y1, targets[:, 3][None, :]) - np.maximum(rect_y0, targets[:, 1][None, :]))
            inter = ix * iy
            ratio = inter.sum(axis=1) / max(1e-6, card_area)
            count = (inter > 1e-5).sum(axis=1).astype(float)
            return ratio, count

        self_ratio, self_cnt = overlap_metrics(self_boxes)
        arc_ratio, arc_cnt = overlap_metrics(arc_box)
        other_ratio, other_cnt = overlap_metrics(other_boxes)

        aspect = width / max(1.0, height)
        dist = np.hypot((centers[:, 0] - ux) * aspect, centers[:, 1] - uy) / np.hypot(aspect, 1.0)
        right_bias = np.where(centers[:, 0] > ux, 0.04, 0.0)

        cost = (8.0 * self_ratio + 2.5 * self_cnt
                + 6.0 * arc_ratio + 1.8 * arc_cnt
                + 4.0 * other_ratio + 0.85 * other_cnt
                + 1.35 * dist + right_bias)
        best = int(np.argmin(cost))
        return float(centers[best, 0]), float(centers[best, 1])

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
        if tracking is not None and tracking.active and tracking.recovery_update_error:
            return "Recovery failed. Open Recover units to try again."
        if (obj in prediction.get("unavailable_ids", ()) or obj in prediction.get("inactive_ids", ()) or
                tracking is not None and (not tracking.active or tracking.status == "failed")):
            return "This unit has no accepted tracking position."
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
        self.card_anchor = self._place_card(state, self.object_id(state, unit_id), self.anchor)
        self.match.geometry.clear()

    def inspect(self, unit_id, state):
        if state.stage != "playback" or unit_id not in state.units.units:
            return
        self.unit_id, self.target_id = unit_id, None
        self.tool, self.note = "select", ""
        obj = self.object_id(state, unit_id)
        center = self.center(state, obj)
        self.anchor = tuple(center) if center is not None else (0.5, 0.5)
        self.card_anchor = self._place_card(state, obj, self.anchor)
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
                    unitId=unit_id,
                    name=catalog.get("classification") or catalog.get("unit_name") or catalog.get("name") or unit["type_id"],
                    details="\n".join(f"{kind.title()}: {status}" for kind, status in issues.items())))
        return dict(rowsA=rows["A"], rowsB=rows["B"], count=len(rows["A"]) + len(rows["B"]),
                    showFacing=state.rules.track_facing)

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
        speed_text = "—" if speed is None else f"{speed:g}″"
        name = catalog.get("unit_name") or catalog.get("name") or ""
        classification = catalog.get("classification") or catalog.get("formation") or ""
        if classification == name:
            classification = ""
        points = profile.get("points")
        points_text = f"{points} pts" if points is not None else ""
        status_tags = [tag for tag, flag in (("Engaged", profile.get("engaged")), ("Wavering", profile.get("wavering"))) if flag]
        special_rules = profile.get("special_rules") or ()
        rules_summary = ", ".join(str(rule) for rule in special_rules if str(rule).strip())
        stats = [
            dict(label="Spd", value=speed_text, objectName="unitSpeed"),
            dict(label="Mel", value=text(profile.get("melee")), objectName=""),
            dict(label="Sh", value=text(profile.get("shooting")), objectName=""),
            dict(label="Def", value=text(profile.get("defence")), objectName=""),
            dict(label="Att", value=text(profile.get("attacks")), objectName=""),
            dict(label="Nrv", value=text(profile.get("nerve")), objectName=""),
            dict(label="US", value=text(profile.get("unit_strength")), objectName=""),
            dict(label="Hgt", value=text(profile.get("height")), objectName=""),
        ]
        center = self.center(state, obj) if obj is not None else None
        unavailable = self.unavailable(state, self.unit_id) if self.unit_id else "Select a unit on the board."
        side = catalog.get("list_id", "A") if unit else ""
        if self.tool == "distance":
            caption = (f"Distance · {self.unit_id} → {self.target_id}" if self.target_id
                       else f"Distance · {self.unit_id} · Click a second unit · Esc cancels")
        elif self.tool == "los":
            caption = (f"LOS · {self.unit_id} → {self.target_id}" if self.target_id
                       else f"LOS · {self.unit_id} · Click target unit · Esc cancels")
        elif self.tool == "move":
            caption = f"Move · {self.unit_id} · {dict(MOVE_ORDERS).get(self.order, self.order)} · Esc cancels"
        elif self.unit_id:
            caption = f"{self.unit_id} selected · D distance · L LOS · V move · Esc clears"
        else:
            caption = "Click a unit on the board · D distance · L LOS · V move"
        return dict(selected=unit is not None, unitId=self.unit_id or "", targetId=self.target_id or "",
                    side=side, name=name, classification=classification, pointsText=points_text,
                    statusTags=status_tags, stats=stats, rulesSummary=rules_summary,
                    speed=speed_text,
                    tool=self.tool, order=self.order,
                    anchorX=self.anchor[0], anchorY=self.anchor[1],
                    cardX=self.card_anchor[0], cardY=self.card_anchor[1],
                    centerX=center[0] if center else 0,
                    centerY=center[1] if center else 0, hasPosition=center is not None,
                    canQuery=unit is not None and not unavailable, queryBlock=unavailable,
                    query=self.query_view(state), caption=caption)
