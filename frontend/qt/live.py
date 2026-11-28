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
        self.viewport_size = None
        self.badge_boxes = []

    def set_viewport_size(self, width, height):
        if width > 0 and height > 0 and np.isfinite(width) and np.isfinite(height):
            self.viewport_size = (float(width), float(height))

    def set_badges(self, badges):
        """Cache active normalized unit/terrain label pills so card placement avoids covering them."""
        boxes = []
        for badge in badges or ():
            try:
                x = float(badge["x"])
                y = float(badge["y"])
                w = float(badge["w"])
                h = float(badge["h"])
            except (KeyError, TypeError, ValueError):
                continue
            if w > 0 and h > 0:
                boxes.append((
                    max(0.0, x - 0.004),
                    max(0.0, y - 0.004),
                    min(1.0, x + w + 0.004),
                    min(1.0, y + h + 0.004),
                    int(badge.get("objectId", -1)),
                ))
        self.badge_boxes = boxes

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
        """Place the floating left stat card near the unit while excluding the semicircle menu."""
        height, width = state.current.frame.shape[:2]
        # Prefer actual QML boardSurface dimensions so fixed-pixel card & menu footprints stay exact.
        vw, vh = (self.viewport_size if self.viewport_size is not None
                  else (min(float(width), 1080.0), min(float(height), 620.0)))
        scale = max(0.25, min(1.0, (vw - 24.0) / 416.0, (vh - 24.0) / 266.0))
        eff_w = max(1.0, vw / scale)
        eff_h = max(1.0, vh / scale)
        card_px_h = 162.0
        uid = state.units.bindings.get(selected_obj) if getattr(state, "units", None) is not None else None
        if uid is not None and uid in state.units.units:
            unit = state.units.units[uid]
            catalog = state.units.types.get(unit["type_id"], {})
            profile = {**catalog.get("attributes", {}), **unit.get("attributes", {})}
            if profile.get("engaged") or profile.get("wavering"):
                card_px_h = 186.0
        cw = min(0.46, max(0.16, 278.0 / eff_w))
        ch = min(0.46, max(0.16, card_px_h / eff_h))
        min_x, max_x = cw * 0.5 + 0.01, max(cw * 0.5 + 0.01, 1.0 - cw * 0.5 - 0.01)
        min_y, max_y = ch * 0.5 + 0.015, max(ch * 0.5 + 0.015, 1.0 - ch * 0.5 - 0.015)

        ux, uy = float(arc_anchor[0]), float(arc_anchor[1])
        menu_w = min(0.36, max(0.12, 166.0 / eff_w))
        menu_right_ext = min(0.38, max(0.14, 180.0 / eff_w))
        menu_half_h = min(0.42, max(0.16, 126.0 / eff_h))
        menu_clamp_h = min(0.45, max(0.17, 133.0 / eff_h))
        menu_cx = float(np.clip(ux, 0.01, max(0.01, 1.0 - menu_right_ext - 0.01)))
        menu_cy = float(np.clip(uy, menu_clamp_h + 0.01, max(menu_clamp_h + 0.01, 1.0 - menu_clamp_h - 0.01)))
        ax0 = max(0.0, menu_cx + 2.0 / eff_w)
        ay0 = max(0.0, menu_cy - menu_half_h)
        ax1 = min(1.0, menu_cx + menu_w)
        ay1 = min(1.0, menu_cy + menu_half_h)
        arc_box = np.array([[ax0, ay0, ax1, ay1]], dtype=float)

        boxes = self._unit_boxes(state)
        self_raw = boxes.get(selected_obj)
        self_boxes = (np.array([[max(0.0, self_raw[0] - 0.005), max(0.0, self_raw[1] - 0.005),
                                 min(1.0, self_raw[2] + 0.005), min(1.0, self_raw[3] + 0.005)]], dtype=float)
                      if self_raw is not None else np.empty((0, 4), dtype=float))
        others = [box for obj, box in boxes.items() if obj != selected_obj]
        other_boxes = np.asarray(others, dtype=float) if others else np.empty((0, 4), dtype=float)
        other_badges = [box[:4] for box in self.badge_boxes if box[4] != selected_obj]
        badge_boxes = np.asarray(other_badges, dtype=float) if other_badges else np.empty((0, 4), dtype=float)

        # Ultra-sparse candidate set: adjacent menu-hugging anchors + 4 local rings + 8x6 full-screen grid
        gap = 0.012
        cands = [
            (ax0 - cw * 0.5 - gap, uy),
            (ax0 - cw * 0.5 - gap, uy - ch * 0.45),
            (ax0 - cw * 0.5 - gap, uy + ch * 0.45),
            (ux - cw * 0.25, ay0 - ch * 0.5 - gap),
            (ux, ay0 - ch * 0.5 - gap),
            (ux - cw * 0.25, ay1 + ch * 0.5 + gap),
            (ux, ay1 + ch * 0.5 + gap),
            (ax1 + cw * 0.5 + gap, uy),
        ]
        angles = np.linspace(0.0, 2.0 * np.pi, 16, endpoint=False)
        for radius in (0.14, 0.22, 0.30, 0.40):
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
                zeros = np.zeros(len(centers))
                return zeros, zeros, zeros
            ix = np.maximum(0.0, np.minimum(rect_x1, targets[:, 2][None, :]) - np.maximum(rect_x0, targets[:, 0][None, :]))
            iy = np.maximum(0.0, np.minimum(rect_y1, targets[:, 3][None, :]) - np.maximum(rect_y0, targets[:, 1][None, :]))
            inter = ix * iy
            ratio = inter.sum(axis=1) / max(1e-6, card_area)
            count = (inter > 1e-5).sum(axis=1).astype(float)
            return ratio, count, inter

        _, self_cnt, self_inter = overlap_metrics(self_boxes)
        if len(self_boxes):
            self_area = max(1e-4, float((self_boxes[0, 2] - self_boxes[0, 0]) * (self_boxes[0, 3] - self_boxes[0, 1])))
            self_occ = self_inter[:, 0] / self_area
        else:
            self_occ = np.zeros(len(centers))
        arc_ratio, arc_cnt, _ = overlap_metrics(arc_box)
        other_ratio, other_cnt, _ = overlap_metrics(other_boxes)
        _, badge_cnt, badge_inter = overlap_metrics(badge_boxes)
        if len(badge_boxes):
            badge_areas = np.maximum(1e-4, (badge_boxes[:, 2] - badge_boxes[:, 0]) * (badge_boxes[:, 3] - badge_boxes[:, 1]))
            badge_occ = (badge_inter / badge_areas[None, :]).sum(axis=1)
        else:
            badge_occ = np.zeros(len(centers))

        aspect = width / max(1.0, height)
        dx_edge = np.maximum(0.0, np.maximum(rect_x0[:, 0] - ux, ux - rect_x1[:, 0]))
        dy_edge = np.maximum(0.0, np.maximum(rect_y0[:, 0] - uy, uy - rect_y1[:, 0]))
        lead_dist = np.hypot(dx_edge * aspect, dy_edge)
        ctr_dist = np.hypot((centers[:, 0] - ux) * aspect, centers[:, 1] - uy)
        dist_cost = 2.8 * lead_dist + 3.0 * (lead_dist ** 2) + 0.95 * ctr_dist
        right_bias = np.where(centers[:, 0] > ux, 0.04, 0.0)
        menu_exclude = np.where(arc_cnt > 0, 1e6, 0.0) if (arc_cnt == 0).any() else 0.0

        cost = (menu_exclude
                + 2.4 * self_occ + 0.35 * self_cnt
                + 6.0 * arc_ratio + 1.8 * arc_cnt
                + 4.5 * other_ratio + 0.06 * other_cnt
                + 1.05 * badge_occ + 0.30 * badge_cnt
                + dist_cost + right_bias)
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
        elif (self.tool == "distance" and self.target_id is not None and self.note
              and not self.unavailable(state, self.unit_id) and not self.unavailable(state, self.target_id)):
            self.request(state)

    @staticmethod
    def object_id(state, unit_id):
        return next((obj for obj, uid in state.units.bindings.items() if uid == unit_id), None)

    @staticmethod
    def hit(state, x, y):
        prediction = state.current.prediction or {}
        height, width = state.current.frame.shape[:2]
        if not (0 <= x < width and 0 <= y < height):
            return None
        ix, iy = int(x), int(y)
        for obj, mask in reversed(list(zip(prediction.get("object_ids", ()), prediction.get("masks", ())))):
            if obj not in state.units.bindings:
                continue
            tray = prediction.get("trays", {}).get(obj)
            on_mask = iy < mask.shape[0] and ix < mask.shape[1] and mask[iy, ix]
            if on_mask or (tray is not None and cv2.pointPolygonTest(
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
            dict(label="Sp", value=speed_text, objectName="unitSpeed"),
            dict(label="Me", value=text(profile.get("melee")), objectName=""),
            dict(label="Sh", value=text(profile.get("shooting")), objectName=""),
            dict(label="De", value=text(profile.get("defence")), objectName=""),
            dict(label="US", value=text(profile.get("unit_strength")), objectName=""),
            dict(label="Att", value=text(profile.get("attacks")), objectName=""),
            dict(label="Ne", value=text(profile.get("nerve")), objectName=""),
            dict(label="Ht", value=text(profile.get("height")), objectName=""),
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
