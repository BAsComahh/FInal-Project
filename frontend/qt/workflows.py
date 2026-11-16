"""Qt adapters for existing live maintenance commands and read-only replay."""
import math

import cv2
import numpy as np
from PySide6.QtCore import QObject, Property, Signal, Slot

from components.homography import transform_points
from components.homography.geometry import order_corners


def _replay_board(state, replay, preview_size):
    width = max(320, int(preview_size[0]))
    height = max(220, int(preview_size[1]))
    panel = np.full((height, width, 3), (36, 29, 19), dtype=np.uint8)
    scene = replay.scene
    if scene is None:
        return panel

    dimensions = np.asarray(scene["board_size_mm"], dtype=float)
    margin_x, margin_y = 24, 24
    scale = min((width - margin_x * 2) / dimensions[0], (height - margin_y * 2) / dimensions[1])
    board_w, board_h = np.maximum(1, np.rint(dimensions * scale).astype(int))
    origin_x = (width - board_w) // 2
    origin_y = (height - board_h) // 2

    board = None
    background = scene.get("background")
    if background is not None:
        try:
            matrix = np.asarray(scene["calibration"]["board"]["image_to_plane"], dtype=float)
            if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
                raise ValueError("Invalid image calibration")
            board = cv2.warpPerspective(
                background,
                np.diag([scale, scale, 1.0]) @ matrix,
                (int(board_w), int(board_h)),
            )
        except (KeyError, TypeError, ValueError, cv2.error):
            board = None
    if board is None:
        board = np.full((int(board_h), int(board_w), 3), (44, 52, 46), dtype=np.uint8)
        step_px = max(24, int(round(150.0 * scale)))
        for gx in range(step_px, int(board_w), step_px):
            cv2.line(board, (gx, 0), (gx, int(board_h)), (56, 66, 60), 1)
        for gy in range(step_px, int(board_h), step_px):
            cv2.line(board, (0, gy), (int(board_w), gy), (56, 66, 60), 1)

    highlight = scene["step"]["unit_id"]
    overlay = board.copy()
    valid = []
    for unit_id, unit in scene["units"].items():
        corners = unit.get("corners_mm")
        try:
            points = np.asarray(corners, dtype=float) if corners is not None else np.empty((0, 2))
        except (TypeError, ValueError):
            points = np.empty((0, 2))
        if (unit.get("active", True) and unit.get("position_status") == "available"
                and points.shape == (4, 2) and np.isfinite(points).all()):
            unit_entry = state.units.units.get(unit_id, {})
            side = state.units.types.get(unit_entry.get("type_id", ""), {}).get("list_id", "A")
            valid.append((unit_id, side, np.rint(points * scale).astype(np.int32)))

    for unit_id, side, polygon in valid:
        is_active = unit_id == highlight
        fill_bgr = (68, 198, 245) if is_active else ((188, 130, 52) if side == "A" else (90, 80, 198))
        cv2.fillPoly(overlay, [polygon], fill_bgr)
    cv2.addWeighted(overlay, 0.34, board, 0.66, 0, board)

    for unit_id, side, polygon in valid:
        is_active = unit_id == highlight
        stroke_bgr = (72, 215, 255) if is_active else ((210, 152, 68) if side == "A" else (106, 94, 224))
        if is_active:
            cv2.polylines(board, [polygon], True, (24, 34, 42), 5, cv2.LINE_AA)
            cv2.polylines(board, [polygon], True, stroke_bgr, 3, cv2.LINE_AA)
        else:
            cv2.polylines(board, [polygon], True, (20, 30, 38), 3, cv2.LINE_AA)
            cv2.polylines(board, [polygon], True, stroke_bgr, 2, cv2.LINE_AA)

        cx, cy = polygon.mean(axis=0)
        font_scale = max(0.42, min(0.62, board_h / 950.0))
        thick = max(1, round(font_scale * 2.2))
        (tw, th), _ = cv2.getTextSize(unit_id, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thick)
        bx = max(4, min(int(board_w) - tw - 14, int(round(cx - tw / 2 - 7))))
        by = max(4, min(int(board_h) - th - 10, int(round(cy - th / 2 - 5))))
        bg_color = (26, 44, 58) if not is_active else (20, 34, 46)
        border_color = stroke_bgr if is_active else (180, 198, 212)
        cv2.rectangle(board, (bx, by), (bx + tw + 12, by + th + 9), bg_color, -1)
        cv2.rectangle(board, (bx, by), (bx + tw + 12, by + th + 9), border_color, 1)
        cv2.putText(board, unit_id, (bx + 6, by + th + 4), cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale, (250, 252, 255), thick, cv2.LINE_AA)

    cv2.rectangle(board, (0, 0), (int(board_w) - 1, int(board_h) - 1), (112, 134, 150), 1)
    panel[origin_y:origin_y + int(board_h), origin_x:origin_x + int(board_w)] = board
    return panel


class Workflows(QObject):
    changed = Signal()
    formRequested = Signal()

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge, self.match = bridge, bridge.match
        self.mode = "live"
        self.points = []
        self._reference = None
        self._fields = []
        self._form_kind = self._unit_id = ""
        self._form_error = ""
        self._calibration_pending = False
        self._data = dict(
            kind="live", rows=[], note="", busy=False, review=False,
            candidateGeneration=0, candidateTime="—", pointCount=0,
            step=0, steps=0, calibrationPending=False,
            replayInfo=dict(stepText="", stepLabel="", stepUnit="", endTime="—",
                            observedTime="—", recordedTime="—", calibrationVersion="—",
                            unavailable="", backgroundNote="", boardDimensions="",
                            loading=False, error="", hasIndex=False),
        )
        self._replay_key = self._replay_image = None

    @Property("QVariantMap", notify=changed)
    def state(self):
        return self._data

    @Property("QVariantList", notify=changed)
    def fields(self):
        return self._fields

    @Property(str, notify=changed)
    def formTitle(self):
        return f"Unit information · {self._unit_id}" if self._form_kind == "profile" else "Terrain information"

    @Property(str, notify=changed)
    def formError(self):
        return self._form_error

    @Slot()
    def clearFormError(self):
        if self._form_error:
            self._form_error = ""
            self.changed.emit()

    def kind(self, state):
        return "recovery" if state.recovery["active"] else "replay" if self.match.replay.active else self.mode

    def publish(self, state):
        recovery, replay = state.recovery, self.match.replay
        if self._calibration_pending and self.match.calibration.status is None:
            self.mode, self._calibration_pending = "live", False
            self.points = []
        kind = self.kind(state)
        rows = []
        for uid in recovery["labels"]:
            unit = state.units.units[uid]
            catalog = state.units.types[unit["type_id"]]
            tracking = state.tracking.get(uid)
            status = ("review" if uid == recovery["review_unit_id"] or
                      (tracking is not None and tracking.recovery_phase == "review")
                      else "failed" if (tracking is not None and tracking.status == "failed")
                      else "active")
            rows.append(dict(
                id=uid,
                side=catalog.get("list_id", "A"),
                name=catalog.get("classification") or catalog.get("unit_name") or catalog.get("name") or unit["type_id"],
                status=status,
            ))

        note = recovery["note"] if kind == "recovery" else replay.error if kind == "replay" else state.note
        scene = replay.scene
        step = replay.steps[replay.selected] if replay.steps else None
        unavailable = []
        observed_time = recorded_time = calib_ver = dimensions = bg_note = "—"
        if scene is not None:
            obs = scene["observation"]
            stamp = lambda value: "unknown" if value is None else f"{value:.2f}s"
            observed_time = stamp(obs.get("observation_timestamp_seconds"))
            recorded_time = stamp(obs.get("timestamp_seconds"))
            calib_ver = f"v{obs['calibration_version']}"
            dims = scene["board_size_mm"]
            dimensions = f"{dims[0]:g} × {dims[1]:g} mm"
            bg_note = scene.get("background_note", "")
            for uid, unit in scene["units"].items():
                corners = unit.get("corners_mm")
                try:
                    pts = np.asarray(corners, dtype=float) if corners is not None else np.empty((0, 2))
                except (TypeError, ValueError):
                    pts = np.empty((0, 2))
                if not (unit.get("active", True) and unit.get("position_status") == "available"
                        and pts.shape == (4, 2) and np.isfinite(pts).all()):
                    reason = "inactive" if not unit.get("active", True) else "unavailable"
                    unavailable.append(f"{uid} ({reason})")
        else:
            dimensions = ""
            bg_note = ""

        replay_info = dict(
            stepText=(f"Step {replay.selected} / {len(replay.steps) - 1}" if replay.steps
                      else "Loading history…" if replay.loading else "No steps"),
            stepLabel=step["label"] if step else "",
            stepUnit=(step.get("unit_id") or "") if step else "",
            endTime=f"{step['end_timestamp_seconds']:.2f}s" if step else "—",
            observedTime=observed_time,
            recordedTime=recorded_time,
            calibrationVersion=calib_ver,
            unavailable=", ".join(unavailable),
            backgroundNote=bg_note,
            boardDimensions=dimensions,
            loading=replay.loading,
            hasIndex=replay.has_index,
            error=replay.error or "",
        )
        if kind == "replay" and step is not None:
            note = f"Step {replay.selected}: {step['label']} | " + (note or "")

        candidate = recovery["preview"]
        self._data = dict(
            kind=kind,
            rows=rows,
            note=note,
            busy=recovery["busy"] or recovery["committing"],
            review=recovery["review_unit_id"] is not None,
            candidateGeneration=recovery["candidate_generation"],
            candidateTime=(f"{candidate['metadata']['timestamp_seconds']:.2f}s" if candidate else "—"),
            pointCount=len(self.points),
            step=replay.selected,
            steps=len(replay.steps),
            calibrationPending=self._calibration_pending,
            replayInfo=replay_info,
        )
        self.changed.emit()

    def refresh(self, receipt=None):
        return self.bridge._refresh(receipt)

    @Slot(str)
    def open(self, tool):
        if self.bridge._closed:
            return
        state = self.match.snapshot()
        if state.stage != "playback" or state.recovery["committing"]:
            return
        if tool == "profile":
            uid = self.bridge.live.unit_id
            unit = state.units.units.get(uid)
            if unit is None:
                return
            values = {**state.units.types[unit["type_id"]].get("attributes", {}), **unit["attributes"]}
            self._unit_id, self._reference = uid, state.source_ref
            self.show_form("profile", [
                ("speed_in", "Speed (inches)", values.get("speed_in"), "number", None),
                ("height", "Rule height", values.get("height"), "number", None),
                ("side", "Side / army", values.get("side"), "text", None),
                ("unit_kind", "Unit kind", values.get("unit_kind"), "choice",
                 [("", "Unknown / Unset"), ("ordinary", "Ordinary"),
                  ("war_engine", "War Engine"), ("individual", "Individual")]),
                ("special_rules", "Special rules (comma separated)", values.get("special_rules"), "rules", None),
                ("engaged", "Currently engaged", values.get("engaged"), "bool", None),
                ("wavering", "Currently wavering", values.get("wavering"), "bool", None),
            ])
            return
        if self.mode == "recalibrate":
            self.match.calibration.cancel_recalibration()
        self.match.recovery.cancel()
        self.match.replay.clear()
        self.bridge.live.done()
        self.mode, self.points, self._calibration_pending = "live", [], False
        if tool in ("correct", "recover"):
            uid = self.bridge.live.unit_id if tool == "correct" else None
            receipt = self.match.recovery.open(uid)
            if receipt.status != "rejected" and uid:
                receipt = self.match.recovery.report_error(uid)
            self.refresh(receipt)
        elif tool == "recalibrate":
            receipt = self.match.calibration.begin_recalibration()
            if receipt.status != "rejected":
                self.mode = "recalibrate"
            self.refresh(receipt)
        elif tool == "replay":
            self.refresh(self.match.replay.open())
        elif tool == "terrain":
            self.mode, self._reference = "terrain", state.source_ref
            self.refresh()

    def show_form(self, kind, rows):
        self._form_kind = kind
        self._form_error = ""
        self._fields = [
            dict(
                key=key,
                label=label,
                kind=field_kind,
                value=(
                    bool(value) if field_kind == "bool"
                    else (", ".join(value) if isinstance(value, (tuple, list)) else str(value or "")) if field_kind == "rules"
                    else ("" if value is None else str(value))
                ),
                options=[opt[0] for opt in options] if options else [],
                optionLabels=[opt[1] for opt in options] if options else [],
            )
            for key, label, value, field_kind, options in rows
        ]
        self.changed.emit()
        self.formRequested.emit()

    @Slot("QVariantList", result=bool)
    def saveForm(self, rows):
        values = {}
        try:
            for row in rows:
                value = row["value"]
                if row["kind"] == "number":
                    value = None if str(value).strip() == "" else float(value)
                    if value is not None and (not math.isfinite(value) or value < 0):
                        raise ValueError("Enter finite, non-negative numbers, or leave unknown values empty.")
                elif row["kind"] == "rules":
                    value = [part.strip() for part in str(value).split(",") if part.strip()]
                elif row["kind"] == "choice":
                    value = str(value).strip() or None
                elif row["kind"] != "bool":
                    value = str(value).strip() or None
                values[row["key"]] = value
        except ValueError as error:
            self._form_error = str(error)
            self.changed.emit()
            return False

        if self._form_kind == "profile":
            receipt = self.match.scene_editing.update_unit_profile(self._unit_id, values, self._reference)
        else:
            receipt = self.match.scene_editing.add_terrain(self.points, values, self._reference)
            if receipt.status != "rejected":
                self.mode, self.points = "live", []

        if receipt.status == "rejected":
            self._form_error = receipt.reason
            self.changed.emit()
            return False

        self._form_error = ""
        return self.refresh(receipt)

    @Slot()
    def finishTerrain(self):
        if self.mode == "terrain" and len(self.points) >= 3:
            self.show_form("terrain", [
                ("label", "Label", "Terrain", "text", None),
                ("kind", "Terrain kind", "blocking", "choice",
                 [("blocking", "Blocking"), ("difficult", "Difficult"), ("obstacle", "Obstacle"),
                  ("hill", "Hill"), ("decorative", "Decorative")]),
                ("height", "Rule height (optional)", None, "number", None),
            ])

    @Slot(str)
    def action(self, action):
        if self.bridge._closed:
            return
        if action == "undoTerrain":
            self.refresh(self.match.scene_editing.undo_terrain())
        elif action == "cancel":
            if self.match.snapshot().recovery["committing"]:
                return
            self.match.recovery.cancel()
            self.match.replay.clear()
            self.match.calibration.cancel_recalibration()
            self.mode, self.points, self._calibration_pending = "live", [], False
            self._form_error = ""
            self.refresh()
        elif action == "clear":
            self.refresh(self.match.recovery.clear_candidate())
        elif action == "correct":
            state = self.bridge._shown
            self.refresh(self.match.recovery.bind(state.recovery["review_unit_id"], state.recovery["candidate_generation"]))
        elif action == "reject":
            self.refresh(self.match.recovery.reject())
        elif action == "refresh":
            self.refresh(self.match.replay.refresh())
        elif action in ("previous", "next"):
            self.refresh(self.match.replay.navigate(-1 if action == "previous" else 1))

    @Slot(str)
    def selectCandidate(self, uid):
        self.refresh(self.match.recovery.select_unit(uid))

    @Slot(str, str, result=bool)
    def applyCalibration(self, width, depth):
        from application.contracts import CommandReceipt
        try:
            size = [float(width), float(depth)]
            if not all(math.isfinite(value) and value > 0 for value in size):
                raise ValueError("Enter positive, finite dimensions.")
            corners = order_corners(self.points)
        except ValueError as error:
            return self.refresh(CommandReceipt("rejected", str(error)))
        boundary = dict(success=True, corners=corners, method="manual", estimated=False,
                        dimensions_confirmed=True, coordinate_space="source_image_pixels")
        receipt = self.match.calibration.apply_recalibration(corners, boundary, board_size_in=size)
        self._calibration_pending = receipt.status != "rejected"
        return self.refresh(receipt)

    def click(self, x, y, positive, state):
        kind = self.kind(state)
        if kind == "live":
            return False
        if kind == "recalibrate" and not self._calibration_pending:
            if positive and len(self.points) < 4:
                self.points.append([x, y])
            elif not positive and self.points:
                self.points.pop()
            self.refresh()
        elif kind in ("recovery", "terrain"):
            source = transform_points([x, y], state.board.homography["inverse_matrix"])
            if kind == "recovery":
                self.refresh(self.match.recovery.point(source, positive, state.source_ref))
            else:
                if positive:
                    self.points.append(source.tolist())
                elif self.points:
                    self.points.pop()
                self.refresh()
        return True

    @Slot(str, float, float, int, int)
    def dropUnit(self, uid, x, y, revision, generation):
        state = self.bridge._shown
        candidate = state.recovery["preview"]
        if revision != self.bridge._image_revision or candidate is None:
            return
        mask = candidate["prediction"]["masks"][0]
        if not (0 <= y < mask.shape[0] and 0 <= x < mask.shape[1] and mask[int(y), int(x)]):
            return
        prediction = state.current.prediction
        if prediction is not None:
            for obj, normal in zip(prediction["object_ids"], prediction["masks"]):
                other = state.units.bindings.get(obj)
                tracking = state.tracking.get(other)
                if other != uid and tracking and tracking.active and tracking.status == "tracking" and normal[int(y), int(x)]:
                    return
        self.refresh(self.match.recovery.bind(uid, generation))

    def interactive_key(self, state):
        kind = self.kind(state)
        if kind == "recovery":
            candidate = state.recovery["preview"]
            return (kind, state.recovery["candidate_generation"], id(candidate))
        if kind in ("terrain", "recalibrate"):
            return (kind, tuple(map(tuple, self.points)), state.board.calibration_version)
        return None

    def has_interactive(self, state):
        kind = self.kind(state)
        if kind == "recovery":
            return state.recovery["preview"] is not None
        if kind in ("terrain", "recalibrate"):
            return bool(self.points)
        return False

    def draw_interactive(self, state, rgba):
        kind = self.kind(state)
        scale = max(1.0, rgba.shape[0] / 720.0)
        if kind == "recovery" and state.recovery["preview"] is not None:
            mask = state.recovery["preview"]["prediction"]["masks"][0]
            if mask.shape == rgba.shape[:2]:
                ys = np.flatnonzero(mask.any(axis=1))
                xs = np.flatnonzero(mask.any(axis=0))
                if len(xs):
                    x0, y0, x1, y1 = int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1
                    sub = mask[y0:y1, x0:x1].astype(np.uint8)
                    rgba[y0:y1, x0:x1][sub != 0] = (45, 205, 250, 128)
                    contours, _ = cv2.findContours(sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE, offset=(x0, y0))
                    cv2.drawContours(rgba, contours, -1, (18, 30, 40, 240), max(3, round(3.8 * scale)), cv2.LINE_AA)
                    cv2.drawContours(rgba, contours, -1, (55, 222, 255, 255), max(2, round(2.0 * scale)), cv2.LINE_AA)
        if self.points and kind in ("terrain", "recalibrate"):
            points = np.asarray(self.points) if kind == "recalibrate" else transform_points(self.points, state.board.homography["matrix"])
            points = np.rint(points).astype(np.int32)
            line_bgra = (120, 215, 130, 255) if kind == "terrain" else (242, 196, 68, 255)
            if len(points) >= 2:
                cv2.polylines(rgba, [points], False, (18, 30, 40, 230), max(4, round(4.2 * scale)), cv2.LINE_AA)
                cv2.polylines(rgba, [points], False, line_bgra, max(2, round(2.2 * scale)), cv2.LINE_AA)
            node_r = max(8, round(9.5 * scale))
            font_scale = max(0.45, 0.5 * scale)
            thick = max(1, round(1.5 * scale))
            for i, point in enumerate(points):
                px, py = int(point[0]), int(point[1])
                cv2.circle(rgba, (px, py), node_r + 2, (18, 30, 40, 240), -1, cv2.LINE_AA)
                cv2.circle(rgba, (px, py), node_r, line_bgra, -1, cv2.LINE_AA)
                label = str(i + 1)
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thick)
                cv2.putText(rgba, label, (int(px - tw / 2), int(py + th / 2)),
                            cv2.FONT_HERSHEY_SIMPLEX, font_scale, (18, 30, 40, 255), thick, cv2.LINE_AA)

    def render_video(self, state, frame):
        kind = self.kind(state)
        if kind == "replay":
            height, width = frame.shape[:2]
            replay = self.match.replay
            scene = replay.scene
            observed = scene["observation"] if scene is not None else {}
            key = (
                replay.epoch, replay.selected, replay.has_index, scene is None, replay.error,
                replay.steps[replay.selected]["event_id"] if replay.steps else None,
                replay.steps[replay.selected]["end_sequence"] if replay.steps else None,
                observed.get("timestamp_seconds"), observed.get("observation_timestamp_seconds"),
                observed.get("calibration_version"), width, height,
            )
            if key != self._replay_key:
                self._replay_image = _replay_board(state, replay, (width, height))
                self._replay_key = key
            return self._replay_image
        if kind == "recalibrate":
            return state.source_image
        return frame
