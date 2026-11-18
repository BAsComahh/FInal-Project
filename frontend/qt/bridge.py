"""Qt registration and Live inputs; business facts stay in application."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot

from application.contracts import CommandReceipt
from components.boundary_detection.table import detect_table
from components.homography import transform_points
from components.homography.geometry import order_corners
from .board import BoardImages, BoardRenderer
from .live import LiveSelection, MOVE_ORDERS
from .workflows import Workflows


class MatchBridge(QObject):
    changed = Signal()
    uncertaintyChanged = Signal()
    catalogChanged = Signal()
    badgesChanged = Signal()

    def __init__(self, match, parent=None):
        super().__init__(parent)
        self.match = match
        self.images = BoardImages()
        self.renderer = BoardRenderer()
        self.live = LiveSelection(match)
        self.selected = 1
        self._last_bound = None
        self._hover_object_id = None
        self.mode = "Points"
        self._manual_vertices = []
        self.show_masks = True
        self.show_trays = True
        self.table_mode = "detecting"
        self.corners, self.corner_points = None, []
        self.corner_method = "lsd"
        self.notice = ""
        self._view = {}
        self._catalog_a = []
        self._catalog_b = []
        self._catalog_key = None
        self._badges = []
        self._uncertainty = dict(rowsA=[], rowsB=[], count=0, showFacing=False)
        self._shown = self._video_key = self._published_key = None
        self._image_revision = 0
        self._overlay_revision = 0
        self._interactive_revision = 0
        self._has_overlay = False
        self._has_interactive = False
        self._local_revision = 0
        self._closed = False
        self._detection = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qt-table")
        self._snapshot = match.snapshot()
        self.flow = Workflows(self)
        self.timer = QTimer(self)
        self.timer.setInterval(15)
        self.timer.timeout.connect(self.advance)
        self.detectCorners()
        self._publish()
        self.timer.start()

    @Property("QVariantMap", notify=changed)
    def state(self):
        return self._view

    @Property("QVariantList", notify=catalogChanged)
    def catalogA(self):
        return self._catalog_a

    @Property("QVariantList", notify=catalogChanged)
    def catalogB(self):
        return self._catalog_b

    @Property("QVariantList", constant=True)
    def moveOrders(self):
        return [dict(id=key, label=label) for key, label in MOVE_ORDERS]

    @Property("QVariantMap", notify=uncertaintyChanged)
    def uncertainty(self):
        return self._uncertainty

    @Property("QVariantList", notify=badgesChanged)
    def badges(self):
        return self._badges

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
        overlay_done, overlay_rgba = self.renderer.poll_overlay(self.match.snapshot().source_ref.generation)
        if overlay_done:
            self.images.publish(overlay_rgba, kind="overlay")
            self._has_overlay = overlay_rgba is not None
            self._overlay_revision += 1
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
        self.flow.publish(state)
        uncertainty = self.live.uncertainty(state)
        if uncertainty != self._uncertainty:
            self._uncertainty = uncertainty
            self.uncertaintyChanged.emit()
        live = state.stage in ("playback", "recalibrate")
        selected = self.live.object_id(state, self.live.unit_id) if live else self.selected
        target = self.live.object_id(state, self.live.target_id) if live else None
        queries = self.match.geometry if live and self.flow.kind(state) == "live" and self.live.tool != "select" else None
        flow_kind = self.flow.kind(state)

        video_key = (
            state.source_ref,
            flow_kind,
            self.match.replay.selected if flow_kind == "replay" else None,
            state.revision if flow_kind == "replay" else None,
        )
        if video_key != self._video_key:
            video_frame = self.flow.render_video(state, state.current.frame)
            self.images.publish(video_frame, kind="video")
            self._display_size = video_frame.shape[1::-1]
            self.match.present(state.source_ref)
            self._video_key = video_key
            self._image_revision += 1
        # Same displayed frame; keep the latest masks/bindings for hit tests (registration never changes frame).
        self._shown = state

        overlay_updated, overlay_rgba = self.renderer.sync_overlay(
            state, selected=selected, masks=self.show_masks, trays=self.show_trays
        )
        if overlay_updated:
            self.images.publish(overlay_rgba, kind="overlay")
            self._has_overlay = overlay_rgba is not None
            self._overlay_revision += 1

        int_updated, int_rgba = self.renderer.render_interactive(
            state,
            selected=selected,
            target=target,
            queries=queries,
            trays=self.show_trays,
            corners=self.corners if state.stage == "table" else None,
            points=self.corner_points if state.stage == "table" else (),
            flow=self.flow,
        )
        if int_updated:
            self.images.publish(int_rgba, kind="interactive")
            self._has_interactive = int_rgba is not None
            self._interactive_revision += 1

        active_badges = (
            self.flow.replay_badges if flow_kind == "replay"
            else self.renderer.badges if (self._has_overlay and (not live or flow_kind in ("live", "recovery")))
            else []
        )
        if active_badges != self._badges:
            self._badges = active_badges
            self.badgesChanged.emit()

        catalog_key = (state.stage, id(state.units.types), tuple(
            (type_id, row.get("list_id", "A"),
             row.get("unit_name") or row.get("name") or row.get("classification") or type_id,
             row.get("classification") or row.get("formation") or "")
            for type_id, row in state.units.types.items()
        ))
        if catalog_key != self._catalog_key:
            types = []
            for type_id, row in state.units.types.items():
                title = row.get("unit_name") or row.get("name") or row.get("classification") or type_id
                subtitle = row.get("classification") or row.get("formation") or ""
                if subtitle == title:
                    subtitle = ""
                side = row.get("list_id", "A")
                types.append(dict(id=type_id, side=side, title=title, subtitle=subtitle))
            self._catalog_a = [row for row in types if row["side"] == "A"]
            self._catalog_b = [row for row in types if row["side"] == "B"]
            self._catalog_key = catalog_key
            self.catalogChanged.emit()

        prediction = state.current.prediction
        object_ids = set(prediction["object_ids"]) if prediction is not None else set()
        masks_list = list(zip(prediction["object_ids"], prediction["masks"])) if prediction is not None else []
        unconfirmed_ids = set(getattr(state, "registration_unconfirmed", ()))
        selected_unit = state.units.bindings.get(self.selected)
        progress = state.load_progress
        model_label = (progress[0] if progress else "Model ready" if state.startup_ready else "Preparing model")
        if state.model_failed:
            model_label = "Model error · reset to retry"
        observation = state.observation_ref
        age = (max(0, state.source_ref.timestamp_seconds - observation.timestamp_seconds)
               if observation is not None else None)
        geometry = (prediction or {}).get("geometry_metadata")
        editable = state.stage == "register" and not state.registration_locked
        self._view = dict(
            stage=state.stage,
            locked=state.registration_locked,
            editable=editable,
            ready=state.startup_ready and not state.model_failed,
            mode=self.mode,
            manualVertices=self._manual_vertices.copy(),
            selected=self.selected,
            hoverObjectId=self._hover_object_id if (editable and self._hover_object_id in object_ids) else -1,
            selectedLabel=selected_unit or f"Mask {self.selected}",
            hasSelection=self.selected in object_ids,
            canFront=bool(editable and selected_unit and prediction is not None and
                          self.selected in prediction.get("trays", {})),
            assigned=len(state.units.bindings),
            total=len(object_ids),
            unassigned=[
                dict(id=int(obj), label=f"Mask {obj}" if mask.any() else f"Mask {obj} (empty)")
                for obj, mask in masks_list if obj not in state.units.bindings
            ],
            unconfirmed=[
                dict(id=int(obj), label=f"{state.units.bindings[obj]} · Mask {obj}")
                for obj in sorted(unconfirmed_ids & state.units.bindings.keys()) if obj in object_ids
            ],
            undo=bool(self._manual_vertices) or self.match.registration.can_undo,
            typesA=self._catalog_a,
            typesB=self._catalog_b,
            types=self._catalog_a + self._catalog_b,
            imageRevision=self._image_revision,
            overlayRevision=self._overlay_revision,
            hasOverlay=self._has_overlay,
            interactiveRevision=self._interactive_revision,
            hasInteractive=self._has_interactive,
            imageWidth=self._display_size[0],
            imageHeight=self._display_size[1],
            tableMode=self.table_mode,
            cornerCount=len(self.corner_points),
            canConfirmCorners=self.corners is not None,
            boardWidth=f"{state.board.board_size_mm[0] / 25.4:g}",
            boardDepth=f"{state.board.board_size_mm[1] / 25.4:g}",
            modelLabel=model_label,
            loading=not state.startup_ready and not state.model_failed,
            progress=(progress[1] / progress[2] if progress and progress[1] is not None and progress[2] else -1),
            note=self.notice or state.note,
            noticeError=bool(self.notice),
            historyWarning=state.history_warning or "",
            sourceTime=f"{state.source_ref.timestamp_seconds:.2f}",
            observationTime=f"{observation.timestamp_seconds:.2f}" if observation else "—",
            observationAge=f"{age:.2f}" if age is not None else "—",
            geometryTime=f"{geometry['timestamp_seconds']:.2f}" if geometry else "—",
            playing=state.playing,
            pendingPlay=state.pending_play,
            console=self.live.data(state),
            reference=str(state.reference_folder or ""),
            masks=self.show_masks,
            trays=self.show_trays,
            trayStatus=state.tray_status,
            terrainCount=len(state.rules.terrain),
            inputsFolder=QUrl.fromLocalFile(str(Path(__file__).resolve().parents[2] / "inputs")).toString(),
        )
        self._view["archivesFolder"] = QUrl.fromLocalFile(str(Path(__file__).resolve().parents[2] / "outputs/sam3_registration")).toString()
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
        width, height = self._display_size
        if not (0 <= x < width and 0 <= y < height):
            return
        if self.flow.click(x, y, positive, shown):
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
        if self.mode in ("Quad", "Rectangle"):
            if not positive:
                self.undo()
            elif self.mode == "Quad":
                vertices = [*self._manual_vertices, [x, y]]
                if len(vertices) == 4:
                    self._submit_manual_mask(vertices)
                else:
                    self._manual_vertices = vertices
                    self._refresh()
            return
        if self.mode == "Assign":
            hit = self._unit_object_at(shown, x, y)
            if hit is None:
                self.notice = "No mask here. Click a mask or its label to select it."
                self._local_revision += 1
                self._publish()
                return
            self.selected = hit
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

    def _submit_manual_mask(self, vertices):
        receipt = self.match.registration.manual_mask(self.selected, vertices, self._shown.source_ref)
        if receipt.status == "accepted":
            self._manual_vertices.clear()
        self._refresh(receipt)

    @Slot(float, float, float, float, int)
    def drawMaskRectangle(self, x0, y0, x1, y1, image_revision):
        if self._closed or self.mode != "Rectangle" or not self._view["editable"] or image_revision != self._image_revision:
            return
        width, height = self._display_size
        left, right = sorted((x0, min(max(x1, 0), width - 1)))
        top, bottom = sorted((y0, min(max(y1, 0), height - 1)))
        self._submit_manual_mask([[left, top], [right, top], [right, bottom], [left, bottom]])

    def _unit_object_at(self, state, x, y):
        if state is None:
            return None
        prediction = state.current.prediction
        if prediction is None:
            return None
        height, width = state.current.frame.shape[:2]
        if not (0 <= x < width and 0 <= y < height):
            return None
        ix, iy = int(x), int(y)
        for obj, mask in reversed(list(zip(prediction["object_ids"], prediction["masks"]))):
            if mask[iy, ix]:
                return int(obj)
        trays = prediction.get("trays", {})
        for obj in reversed(list(prediction["object_ids"])):
            tray = trays.get(obj)
            if tray is not None and cv2.pointPolygonTest(
                    np.asarray(tray["corners_image"], np.float32), (float(x), float(y)), False) >= 0:
                return int(obj)
        nx, ny = x / max(1, width), y / max(1, height)
        pad_x, pad_y = 4.0 / max(1, width), 4.0 / max(1, height)
        for badge in reversed(self._badges):
            if badge.get("kind") == "unit" and int(badge.get("objectId", -1)) > 0:
                bx, by, bw, bh = badge["x"], badge["y"], badge["w"], badge["h"]
                if bx - pad_x <= nx <= bx + bw + pad_x and by - pad_y <= ny <= by + bh + pad_y:
                    return int(badge["objectId"])
        return None

    @Slot(str)
    def setMode(self, mode):
        if mode in ("Points", "Assign", "Front", "Quad", "Rectangle") and self._view["editable"]:
            if mode != self.mode:
                self._manual_vertices.clear()
            self.mode = mode
            ids = (self.match.snapshot().current.prediction or {}).get("object_ids", ())
            if mode == "Assign" and self.selected not in ids and ids:
                # Points mode pre-selects a not-yet-created mask; fall back to the last assigned one.
                self.selected = self._last_bound if self._last_bound in ids else ids[-1]
            self._refresh()

    @Slot(int)
    def selectMask(self, object_id):
        if self._view["editable"]:
            self._manual_vertices.clear()
            self.selected, self.mode = object_id, "Assign"
            self._refresh()

    @Slot()
    def newObject(self):
        if self._view["editable"]:
            self._manual_vertices.clear()
            self.selected = max(self.match.registration.known_ids(), default=0) + 1
            if self.mode not in ("Quad", "Rectangle"):
                self.mode = "Points"
            self._refresh()

    @Slot(str)
    def assign(self, type_id, object_id=None):
        if not self._closed:
            object_id = self.selected if object_id is None else object_id
            receipt = self.match.registration.bind(object_id, type_id)
            self._hover_object_id = None
            if receipt.status != "rejected":
                self._manual_vertices.clear()
                self.selected = self._last_bound = object_id
                if self.mode in ("Points", "Quad", "Rectangle"):
                    self.newObject()
                    return
                self.mode = "Assign"
            self._refresh(receipt)

    @Slot(float, float, int)
    def hoverType(self, x, y, image_revision):
        if image_revision != self._image_revision or not self._view["editable"]:
            hit = None
        else:
            hit = self._unit_object_at(self._shown, x, y)
        if hit != self._hover_object_id:
            self._hover_object_id = hit
            self._local_revision += 1
            self._publish()

    @Slot()
    def clearHover(self):
        if self._hover_object_id is not None:
            self._hover_object_id = None
            self._local_revision += 1
            self._publish()

    @Slot(str, float, float, int)
    def dropType(self, type_id, x, y, image_revision):
        self._hover_object_id = None
        if image_revision != self._image_revision or not self._view["editable"]:
            return
        object_id = self._unit_object_at(self._shown, x, y)
        if object_id is None:
            self.notice = "Drop the type onto a mask, tray, or unit label."
            self._local_revision += 1
            self._publish()
            return
        self.assign(type_id, object_id)

    @Slot()
    def unbind(self):
        if self._last_bound == self.selected:
            self._last_bound = None
        self._hover_object_id = None
        self._refresh(self.match.registration.unbind(self.selected))

    @Slot()
    def undo(self):
        if self._snapshot.stage == "table":
            if self.table_mode == "manual" and self.corner_points:
                self.corner_points.pop()
                self.corners = None
            self._refresh()
        else:
            if self._manual_vertices:
                self._manual_vertices.pop()
                self._refresh()
                return
            prompts = self.match.snapshot().registration_prompts
            receipt = self.match.registration.undo_point()
            if receipt.value is not None:
                self.selected = receipt.value
            elif prompts and receipt.status != "rejected":
                self.selected = prompts[-1]["object_id"]
            self._refresh(receipt)

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
        return self._refresh(receipt)

    @Slot(QUrl, str)
    def importList(self, url, side):
        if url.isLocalFile():
            self._refresh(self.match.registration.import_unit_list(url.toLocalFile(), side))

    @Slot()
    def finish(self):
        if self._manual_vertices:
            self._refresh(CommandReceipt("rejected", "Finish the four corners or undo the draft before saving."))
            return
        self._refresh(self.match.registration.finish_registration())

    @Slot()
    def start(self):
        if self._manual_vertices:
            self._refresh(CommandReceipt("rejected", "Finish the four corners or undo the draft before starting."))
            return
        self._refresh(self.match.start())

    @Slot()
    def reset(self):
        self.flow.action("cancel")
        receipt = self.match.reset()
        if receipt.status != "rejected":
            self.selected, self.mode = 1, "Points"
            self._manual_vertices.clear()
            self._last_bound = None
            self._hover_object_id = None
            self.live.clear()
        self._refresh(receipt)

    @Slot(QUrl)
    def loadArchive(self, path):
        receipt = self.match.registration.load_archive(path.toLocalFile())
        if receipt.status != "rejected":
            self.live.clear()
            state = self.match.snapshot()
            self.selected = next(iter(state.current.prediction["object_ids"]), 1)
            self._last_bound = None
            self._hover_object_id = None
            self.mode = "Assign"
            self._manual_vertices.clear()
            self.corners, self.corner_points = None, []
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

    @Slot(float, float)
    def moveUnitCard(self, x, y):
        if not self._closed:
            self.live.set_card_anchor(x, y)
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
            if self.flow.kind(self.match.snapshot()) != "live":
                self.flow.action("cancel")
                return
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
        self.renderer.close()
        self.match.close()
