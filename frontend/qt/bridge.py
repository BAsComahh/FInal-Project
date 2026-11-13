"""Qt registration and Live inputs; business facts stay in application."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot

from components.boundary_detection.table import detect_table
from components.homography import transform_points
from components.homography.geometry import order_corners
from .board import BoardImages, BoardRenderer
from .live import LiveSelection, MOVE_ORDERS


class MatchBridge(QObject):
    changed = Signal()
    uncertaintyChanged = Signal()

    def __init__(self, match, parent=None):
        super().__init__(parent)
        self.match = match
        self.images = BoardImages()
        self.renderer = BoardRenderer()
        self.live = LiveSelection(match)
        self.selected = 1
        self.mode = "Points"
        self.show_masks = self.show_trays = True
        self.table_mode = "detecting"
        self.corners, self.corner_points = None, []
        self.corner_method = "lsd"
        self.notice = ""
        self._view = {}
        self._uncertainty = dict(rowsA=[], rowsB=[], count=0)
        self._shown = self._image_key = self._published_key = None
        self._image_revision = 0
        self._local_revision = 0
        self._closed = False
        self._detection = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qt-table")
        self._snapshot = match.snapshot()
        self._board_size = [value / 25.4 for value in self._snapshot.board.board_size_mm]
        self.timer = QTimer(self)
        self.timer.setInterval(15)
        self.timer.timeout.connect(self.advance)
        self.detectCorners()
        self._publish()
        self.timer.start()

    @Property("QVariantMap", notify=changed)
    def state(self):
        return self._view

    @Property("QVariantList", constant=True)
    def moveOrders(self):
        return [dict(id=key, label=label) for key, label in MOVE_ORDERS]

    @Property("QVariantMap", notify=uncertaintyChanged)
    def uncertainty(self):
        return self._uncertainty

    @Slot()
    def advance(self):
        if self._closed:
            return
        self.match.tick()
        if self._detection is not None and self._detection.done():
            future, self._detection = self._detection, None
            if self.table_mode == "detecting" and self.match.snapshot().stage == "table":
                try:
                    result = future.result()
                except Exception as error:
                    result = {"success": False, "reason": str(error)}
                self.corners = result["corners"] if result["success"] else None
                self.table_mode = "review" if self.corners else "manual"
                self.notice = ("Check TL / TR / BR / BL before continuing." if self.corners else
                               "Automatic table boundary detection failed. Click four table corners manually.")
                self._local_revision += 1
        self._publish()

    def _publish(self):
        state = self.match.snapshot()
        self.live.sync(state)
        key = (state.revision, self._local_revision)
        if key == self._published_key:
            return
        self._snapshot = state
        self._published_key = key
        uncertainty = self.live.uncertainty(state)
        if uncertainty != self._uncertainty:
            self._uncertainty = uncertainty
            self.uncertaintyChanged.emit()
        live = state.stage == "playback"
        selected = self.live.object_id(state, self.live.unit_id) if live else self.selected
        target = self.live.object_id(state, self.live.target_id) if live else None
        queries = self.match.geometry if live and self.live.tool != "select" else None
        image_key = (state.source_ref, state.current.view_revision, selected, target, self.show_masks, self.show_trays,
                     id(queries.result) if queries is not None else None,
                     tuple(prompt["click_id"] for prompt in state.registration_prompts),
                     repr(self.corners), tuple(map(tuple, self.corner_points)), state.stage)
        if image_key != self._image_key:
            self.images.publish(self.renderer.render(state, selected=selected, target=target, queries=queries,
                                             masks=self.show_masks, trays=self.show_trays,
                                             corners=self.corners if state.stage == "table" else None,
                                             points=self.corner_points if state.stage == "table" else ()))
            self.match.present(state.source_ref)
            self._shown = state
            self._image_key = image_key
            self._image_revision += 1
        types = []
        for type_id, row in state.units.types.items():
            title = row.get("classification") or row.get("unit_name") or row.get("name") or type_id
            side = row.get("list_id", "A")
            types.append(dict(id=type_id, side=side, title=title))
        prediction = state.current.prediction
        object_ids = set(prediction["object_ids"]) if prediction is not None else set()
        selected_unit = state.units.bindings.get(self.selected)
        progress = state.load_progress
        model_label = (progress[0] if progress else "Model ready" if state.startup_ready else "Preparing model")
        if state.model_failed:
            model_label = "Model error · reset to retry"
        observation = state.observation_ref
        age = (max(0, state.source_ref.timestamp_seconds - observation.timestamp_seconds)
               if observation is not None else None)
        editable = state.stage == "register" and not state.registration_locked
        self._view = dict(stage=state.stage, locked=state.registration_locked, editable=editable,
                          ready=state.startup_ready and not state.model_failed, mode=self.mode, selected=self.selected,
                          selectedLabel=selected_unit or f"Mask {self.selected}", hasSelection=self.selected in object_ids,
                          canFront=bool(editable and selected_unit and prediction is not None and
                                        self.selected in prediction.get("trays", {})),
                          assigned=len(state.units.bindings), total=len(object_ids), undo=bool(state.registration_prompts),
                          typesA=[row for row in types if row["side"] == "A"],
                          typesB=[row for row in types if row["side"] == "B"], types=types,
                          imageRevision=self._image_revision, imageWidth=state.current.frame.shape[1],
                          imageHeight=state.current.frame.shape[0], tableMode=self.table_mode,
                          cornerCount=len(self.corner_points), canConfirmCorners=self.corners is not None,
                          boardWidth=f"{self._board_size[0]:g}", boardDepth=f"{self._board_size[1]:g}",
                          modelLabel=model_label, loading=not state.startup_ready and not state.model_failed,
                          progress=(progress[1] / progress[2] if progress and progress[1] is not None and progress[2] else -1),
                          note=self.notice or state.note, historyWarning=state.history_warning or "",
                          sourceTime=f"{state.source_ref.timestamp_seconds:.2f}",
                          observationTime=f"{observation.timestamp_seconds:.2f}" if observation else "—",
                          observationAge=f"{age:.2f}" if age is not None else "—",
                          playing=state.playing, pendingPlay=state.pending_play, console=self.live.data(state),
                          reference=str(state.reference_folder or ""), masks=self.show_masks, trays=self.show_trays,
                          inputsFolder=QUrl.fromLocalFile(str(Path(__file__).resolve().parents[2] / "inputs")).toString())
        self.changed.emit()

    def _refresh(self, receipt=None):
        self.notice = receipt.reason if receipt is not None and receipt.status == "rejected" else ""
        self._local_revision += 1
        self._publish()
        return receipt is None or receipt.status != "rejected"

    @Slot(float, float, bool, int)
    def click(self, x, y, positive, image_revision):
        if self._closed:
            return
        if image_revision != self._image_revision or self._shown is None:
            self.notice = "The displayed frame changed. Please click again."
            self._local_revision += 1
            self._publish()
            return
        shown = self._shown
        height, width = shown.current.frame.shape[:2]
        if not (0 <= x < width and 0 <= y < height):
            return
        if shown.stage == "table":
            if self.table_mode == "manual":
                if not positive:
                    self.undo()
                    return
                if len(self.corner_points) < 4:
                    self.corner_points.append([x, y])
                self.corners = None
                if len(self.corner_points) == 4:
                    try:
                        self.corners = order_corners(self.corner_points)
                    except ValueError as error:
                        self.notice = str(error)
                        self._local_revision += 1
                        self._publish()
                        return
                self._refresh()
            return
        if shown.stage == "playback":
            self.live.click(shown, x, y, positive)
            self._refresh()
            return
        if shown.stage != "register" or shown.registration_locked:
            return
        if self.mode == "Assign":
            prediction = shown.current.prediction
            if prediction is not None:
                self.selected = next((obj for obj, mask in reversed(list(zip(prediction["object_ids"], prediction["masks"])))
                                      if mask[int(y), int(x)]), self.selected)
            self._refresh()
            return
        source = transform_points([x, y], shown.board.homography["inverse_matrix"])
        if self.mode == "Front":
            unit_id = shown.units.bindings.get(self.selected)
            if unit_id is None or shown.observation_ref is None:
                self.notice = "Bind a type and wait for a tray before marking its front."
                self._local_revision += 1
                self._publish()
                return
            receipt = self.match.scene_editing.set_front(unit_id, source, shown.observation_ref)
            if receipt.status != "rejected":
                self.mode = "Assign"
        else:
            receipt = self.match.registration.point(self.selected, source, shown.source_ref, positive=positive)
        self._refresh(receipt)

    @Slot(str)
    def setMode(self, mode):
        if mode in ("Points", "Assign", "Front") and self._view["editable"]:
            self.mode = mode
            self._refresh()

    @Slot()
    def newObject(self):
        if self._view["editable"]:
            self.selected = max(self.match.registration.known_ids(), default=0) + 1
            self.mode = "Points"
            self._refresh()

    @Slot(str)
    def assign(self, type_id, object_id=None):
        if not self._closed:
            object_id = self.selected if object_id is None else object_id
            receipt = self.match.registration.bind(object_id, type_id)
            if receipt.status != "rejected":
                self.selected = object_id
                if self.mode == "Points":
                    self.newObject()
                    return
                self.mode = "Assign"
            self._refresh(receipt)

    @Slot(str, float, float, int)
    def dropType(self, type_id, x, y, image_revision):
        if image_revision != self._image_revision or not self._view["editable"]:
            return
        shown = self._shown
        prediction = shown.current.prediction
        if prediction is not None and 0 <= x < shown.current.frame.shape[1] and 0 <= y < shown.current.frame.shape[0]:
            object_id = next((obj for obj, mask in reversed(list(zip(prediction["object_ids"], prediction["masks"])))
                              if mask[int(y), int(x)]), None)
            if object_id is not None:
                self.assign(type_id, object_id)

    @Slot()
    def unbind(self):
        self._refresh(self.match.registration.unbind(self.selected))

    @Slot()
    def undo(self):
        if self._snapshot.stage == "table":
            if self.table_mode == "manual" and self.corner_points:
                self.corner_points.pop()
                self.corners = None
            self._refresh()
        else:
            prompts = self.match.snapshot().registration_prompts
            if prompts:
                self.selected = prompts[-1]["object_id"]
            self._refresh(self.match.registration.undo_point())

    @Slot()
    def detectCorners(self):
        if self._closed or self.match.snapshot().stage != "table" or self._detection is not None:
            return
        self.table_mode, self.corner_method = "detecting", "lsd"
        self.corners, self.corner_points = None, []
        self._detection = self._executor.submit(detect_table, self.match.snapshot().source_image.copy())
        self._refresh()

    @Slot()
    def manualCorners(self):
        if self._snapshot.stage == "table":
            self.table_mode, self.corner_method = "manual", "manual"
            self.corners, self.corner_points = None, []
            self._refresh()

    @Slot()
    def reviewDimensions(self):
        if self.corners is not None:
            self.table_mode = "dimensions"
            self._refresh()

    @Slot()
    def backToCorners(self):
        self.table_mode = "manual" if self.corner_method == "manual" else "review"
        self._refresh()

    @Slot(str, str, result=bool)
    def confirmTable(self, width, depth):
        try:
            size = [float(width), float(depth)]
        except ValueError:
            self.notice = "Enter positive, finite table dimensions in both fields."
            self._local_revision += 1
            self._publish()
            return False
        boundary = dict(corners=self.corners, corner_order=["TL", "TR", "BR", "BL"], method=self.corner_method,
                        confirmed=True, board_size_in=size, board_size_mm=[value * 25.4 for value in size],
                        dimensions_confirmed=True, coordinate_space="source_image_pixels")
        receipt = self.match.calibration.confirm_table(self.corners, boundary, board_size_in=size)
        if receipt.status != "rejected":
            self._board_size = size
        return self._refresh(receipt)

    @Slot(QUrl, str)
    def importList(self, url, side):
        if url.isLocalFile():
            self._refresh(self.match.registration.import_unit_list(url.toLocalFile(), side))

    @Slot()
    def finish(self):
        self._refresh(self.match.registration.finish_registration())

    @Slot()
    def start(self):
        self._refresh(self.match.start())

    @Slot()
    def reset(self):
        receipt = self.match.reset()
        if receipt.status != "rejected":
            self.selected, self.mode = 1, "Points"
            self.live.clear()
        self._refresh(receipt)

    @Slot(str)
    def liveTool(self, tool):
        if not self._closed:
            self.live.set_tool(tool, self.match.snapshot())
            self._refresh()

    @Slot(str)
    def inspectUnit(self, unit_id):
        if not self._closed:
            self.live.inspect(unit_id, self.match.snapshot())
            self._refresh()

    @Slot(str)
    def moveOrder(self, order):
        if not self._closed:
            self.live.set_order(order, self.match.snapshot())
            self._refresh()

    @Slot()
    def clearSelection(self):
        if not self._closed:
            self.live.clear()
            self._refresh()

    @Slot()
    def doneTool(self):
        if not self._closed:
            self.live.done()
            self._refresh()

    @Slot()
    def escapeLive(self):
        if not self._closed:
            self.live.escape()
            self._refresh()

    @Slot(str, bool)
    def setOverlay(self, overlay, enabled):
        if overlay == "masks":
            self.show_masks = enabled
        elif overlay == "trays":
            self.show_trays = enabled
        self._refresh()

    @Slot()
    def close(self):
        if self._closed:
            return
        self._closed = True
        self.timer.stop()
        if self._detection is not None:
            self._detection.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)
        self.match.close()
