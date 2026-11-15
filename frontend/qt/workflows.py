"""Qt adapters for existing live maintenance commands and read-only replay."""
import math

import cv2
import numpy as np
from PySide6.QtCore import QObject, Property, Signal, Slot

from components.homography import transform_points
from components.homography.geometry import order_corners
from frontend.replay.view import ReplayView


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
        self._calibration_pending = False
        self._data = dict(kind="live", rows=[], note="", busy=False, review=False,
                          candidateGeneration=0, pointCount=0, step=0, steps=0)
        self.replay_view = ReplayView(self.match.replay)
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

    def kind(self, state):
        return "recovery" if state.recovery["active"] else "replay" if self.match.replay.active else self.mode

    def publish(self, state):
        recovery, replay = state.recovery, self.match.replay
        if self._calibration_pending and self.match.calibration.status is None:
            self.mode, self._calibration_pending = "live", False
            self.points = []
        kind = self.kind(state)
        rows = [dict(id=uid, side=state.units.types[state.units.units[uid]["type_id"]].get("list_id", "A"))
                for uid in recovery["labels"]]
        note = recovery["note"] if kind == "recovery" else replay.error if kind == "replay" else state.note
        if kind == "replay" and replay.steps:
            note = f"Step {replay.selected}: {replay.steps[replay.selected]['label']} | " + note
        candidate = recovery["preview"]
        self._data = dict(kind=kind, rows=rows, note=note, busy=recovery["busy"] or recovery["committing"],
                          review=recovery["review_unit_id"] is not None,
                          candidateGeneration=recovery["candidate_generation"],
                          candidateTime=(f"{candidate['metadata']['timestamp_seconds']:.2f}s" if candidate else "—"),
                          pointCount=len(self.points), step=replay.selected, steps=len(replay.steps),
                          calibrationPending=self._calibration_pending)
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
            self.show_form("profile", [(key, label, values.get(key), kind) for key, label, kind in (
                ("speed_in", "Speed (inches)", "number"), ("height", "Rule height", "number"),
                ("side", "Side / army", "text"), ("unit_kind", "ordinary / war_engine / individual", "text"),
                ("special_rules", "Special rules (comma separated)", "rules"),
                ("engaged", "Engaged", "bool"), ("wavering", "Wavering", "bool"))])
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
        self._fields = [dict(key=key, label=label, kind=field_kind,
                             value=bool(value) if field_kind == "bool" else
                             (", ".join(value) if isinstance(value, (tuple, list)) else str(value or ""))
                             if field_kind == "rules" else "" if value is None else str(value))
                        for key, label, value, field_kind in rows]
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
                elif row["kind"] != "bool":
                    value = str(value).strip() or None
                values[row["key"]] = value
        except ValueError as error:
            from application.contracts import CommandReceipt
            return self.refresh(CommandReceipt("rejected", str(error)))
        if self._form_kind == "profile":
            receipt = self.match.scene_editing.update_unit_profile(self._unit_id, values, self._reference)
        else:
            receipt = self.match.scene_editing.add_terrain(self.points, values, self._reference)
            if receipt.status != "rejected":
                self.mode, self.points = "live", []
        return self.refresh(receipt)

    @Slot()
    def finishTerrain(self):
        if self.mode == "terrain" and len(self.points) >= 3:
            self.show_form("terrain", [("label", "Label", "Terrain", "text"),
                ("kind", "blocking / difficult / obstacle / hill / decorative", "blocking", "text"),
                ("height", "Rule height", None, "number")])

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

    def render(self, state, frame):
        kind = self.kind(state)
        if kind == "replay":
            height, width = frame.shape[:2]
            replay = self.match.replay
            scene = replay.scene
            observed = scene["observation"] if scene is not None else {}
            key = (replay.epoch, replay.selected, replay.has_index, scene is None, replay.error,
                   replay.steps[replay.selected]["event_id"] if replay.steps else None,
                   replay.steps[replay.selected]["end_sequence"] if replay.steps else None,
                   observed.get("timestamp_seconds"), observed.get("observation_timestamp_seconds"),
                   observed.get("calibration_version"), width, height)
            if key != self._replay_key:
                self._replay_image = self.replay_view.render((width, height))[:height, :width]
                self._replay_key = key
            return self._replay_image
        if kind == "recalibrate":
            frame = state.source_image.copy()
        if kind == "recovery" and state.recovery["preview"] is not None:
            mask = state.recovery["preview"]["prediction"]["masks"][0]
            if mask.shape == frame.shape[:2]:
                frame[mask] = (frame[mask] * .55 + np.array([40, 210, 245]) * .45).astype(np.uint8)
                contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(frame, contours, -1, (40, 220, 255), 2)
        if self.points and kind in ("terrain", "recalibrate"):
            points = np.asarray(self.points) if kind == "recalibrate" else transform_points(self.points, state.board.homography["matrix"])
            points = np.rint(points).astype(np.int32)
            cv2.polylines(frame, [points], False, (40, 220, 255), 2)
            for i, point in enumerate(points):
                cv2.circle(frame, tuple(point), 5, (40, 220, 255), -1)
                cv2.putText(frame, str(i + 1), tuple(point), cv2.FONT_HERSHEY_SIMPLEX, .7, (255, 255, 255), 2)
        return frame
