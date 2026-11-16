"""Owned Qt images and decoupled video / async mask-overlay / fast interactive rendering."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import cv2
import numpy as np
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from components.homography import transform_points
from frontend.shared.drawing import draw_text
from frontend.shared.layers import QueryLayers

_SIDE_A_BGR = (
    (208, 138, 42),
    (188, 114, 38),
    (186, 162, 52),
    (224, 158, 78),
    (168, 128, 46),
    (200, 174, 88),
)

_SIDE_B_BGR = (
    (92, 82, 214),
    (78, 116, 230),
    (110, 74, 192),
    (74, 146, 224),
    (124, 98, 224),
    (94, 108, 184),
)

_UNBOUND_BGR = (
    (176, 152, 46),
    (98, 176, 86),
    (208, 128, 72),
    (90, 174, 218),
    (186, 108, 168),
    (140, 182, 92),
)

_TERRAIN_KIND_BGR = {
    "blocking": (82, 92, 196),
    "difficult": (54, 166, 224),
    "obstacle": (182, 120, 88),
    "hill": (96, 168, 102),
    "decorative": (154, 164, 172),
}


def _empty_argb():
    img = QImage(1, 1, QImage.Format_ARGB32)
    img.fill(0)
    return img


def _side_for_object(state, object_id):
    unit_id = state.units.bindings.get(object_id)
    if unit_id is None:
        return ""
    unit = state.units.units.get(unit_id)
    if unit is None:
        return ""
    return state.units.types.get(unit["type_id"], {}).get("list_id", "A")


def _object_color(object_id, side):
    palette = _SIDE_A_BGR if side == "A" else _SIDE_B_BGR if side == "B" else _UNBOUND_BGR
    return palette[(object_id - 1) % len(palette)]


def _measure_badge(text, scale, has_dot):
    text = str(text)
    font_scale = max(0.40, 0.45 * scale)
    thickness = max(1, round(1.25 * scale))
    pad_x = max(5, round(6 * scale))
    pad_y = max(3, round(4 * scale))
    dot_r = max(3, round(3.3 * scale)) if has_dot else 0
    dot_gap = max(5, round(5 * scale)) if has_dot else 0

    if text.isascii():
        (text_w, text_h), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
    else:
        text_h = max(13, round(14 * scale))
        text_w = max(22, round(len(text) * text_h * 0.85))
        baseline = max(3, round(3 * scale))

    box_w = pad_x * 2 + text_w + (dot_r * 2 + dot_gap if has_dot else 0)
    box_h = pad_y * 2 + text_h + baseline // 2
    return box_w, box_h, font_scale, thickness, pad_x, pad_y, dot_r, dot_gap, text_h


def _draw_badge_at(rgba, text, box, metrics, scale, *, dot_bgr=None, fill_rgba=(20, 32, 42, 222)):
    x, y, x2, y2 = box
    _, _, font_scale, thickness, pad_x, pad_y, dot_r, dot_gap, text_h = metrics
    cv2.rectangle(rgba, (x, y), (x2, y2), fill_rgba, -1)
    cv2.rectangle(rgba, (x, y), (x2, y2), (214, 228, 238, 175), max(1, round(scale)))

    text_x = x + pad_x
    if dot_bgr is not None:
        dot_cx = x + pad_x + dot_r
        dot_cy = (y + y2) // 2
        cv2.circle(rgba, (dot_cx, dot_cy), dot_r, (*dot_bgr, 255), -1, cv2.LINE_AA)
        text_x += dot_r * 2 + dot_gap

    text_y = y + pad_y + text_h
    text = str(text)
    if text.isascii():
        cv2.putText(rgba, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                    (248, 251, 255, 255), thickness, cv2.LINE_AA)
    else:
        draw_text(rgba, text, (text_x, text_y), (248, 251, 255, 255), size=max(13, round(14 * scale)))


def _rect_overlap(a, b):
    ix0 = max(a[0], b[0])
    iy0 = max(a[1], b[1])
    ix1 = min(a[2], b[2])
    iy1 = min(a[3], b[3])
    return max(0, ix1 - ix0) * max(0, iy1 - iy0)


def _rect_distance(box, target):
    dx = max(target[0] - box[2], box[0] - target[2], 0)
    dy = max(target[1] - box[3], box[1] - target[3], 0)
    return float((dx * dx + dy * dy) ** 0.5)


def _nearest_points(box, target):
    bx = min(max((box[0] + box[2]) / 2.0, target[0]), target[2])
    by = min(max((box[1] + box[3]) / 2.0, target[1]), target[3])
    px = min(max(bx, box[0]), box[2])
    py = min(max(by, box[1]), box[3])
    return (int(round(px)), int(round(py))), (int(round(bx)), int(round(by)))


def _place_label_box(unit_box, box_w, box_h, frame_w, frame_h, scale, integral, ds, placed_boxes):
    ux0, uy0, ux1, uy1 = unit_box
    umx = (ux0 + ux1) * 0.5
    umy = (uy0 + uy1) * 0.5
    max_x = max(4, frame_w - box_w - 4)
    max_y = max(4, frame_h - box_h - 4)
    margin = max(3, round(3.5 * scale))
    ih, iw = integral.shape[0] - 1, integral.shape[1] - 1

    def occ_score(x, y):
        qx0 = max(0, (x - margin) // ds)
        qy0 = max(0, (y - margin) // ds)
        qx1 = min(iw, (x + box_w + margin + ds - 1) // ds)
        qy1 = min(ih, (y + box_h + margin + ds - 1) // ds)
        if qx1 <= qx0 or qy1 <= qy0:
            return 0
        return int(integral[qy1, qx1] - integral[qy0, qx1] - integral[qy1, qx0] + integral[qy0, qx0])

    best_box = None
    best_score = None
    gaps = (round(6 * scale), round(14 * scale), round(26 * scale), round(42 * scale), round(64 * scale), round(92 * scale))

    for ring_idx, gap in enumerate(gaps):
        candidates = (
            (umx - box_w * 0.5, uy0 - gap - box_h, 0.0),      # top-center
            (umx - box_w * 0.5, uy1 + gap, 1.0),              # bottom-center
            (ux0 - gap - box_w, umy - box_h * 0.5, 2.0),      # left-center
            (ux1 + gap, umy - box_h * 0.5, 2.5),              # right-center
            (ux0, uy0 - gap - box_h, 3.0),                    # top-left
            (ux1 - box_w, uy0 - gap - box_h, 3.2),            # top-right
            (ux0, uy1 + gap, 3.5),                            # bottom-left
            (ux1 - box_w, uy1 + gap, 3.7),                    # bottom-right
            (ux0 - gap - box_w, uy0, 4.0),                    # left-top
            (ux0 - gap - box_w, uy1 - box_h, 4.2),            # left-bottom
            (ux1 + gap, uy0, 4.4),                            # right-top
            (ux1 + gap, uy1 - box_h, 4.6),                    # right-bottom
        )
        if ring_idx >= 2:
            candidates = candidates + (
                (ux0 - gap - box_w, uy0 - gap - box_h, 5.0),
                (ux1 + gap, uy0 - gap - box_h, 5.2),
                (ux0 - gap - box_w, uy1 + gap, 5.4),
                (ux1 + gap, uy1 + gap, 5.6),
            )

        found_clean_in_ring = False
        for raw_x, raw_y, dir_bias in candidates:
            x = int(max(4, min(max_x, round(raw_x))))
            y = int(max(4, min(max_y, round(raw_y))))
            cand = (x, y, x + box_w, y + box_h)
            padded = (x - margin, y - margin, x + box_w + margin, y + box_h + margin)
            lbl_overlap = sum(_rect_overlap(padded, prev) for prev in placed_boxes)
            occ_blocks = occ_score(x, y)
            dist = _rect_distance(cand, unit_box)
            score = lbl_overlap * 10000.0 + occ_blocks * 250.0 + dist * 1.2 + dir_bias
            if best_score is None or score < best_score:
                best_score = score
                best_box = cand
            if lbl_overlap == 0 and occ_blocks == 0:
                found_clean_in_ring = True
        if found_clean_in_ring and ring_idx == 0:
            break
        if found_clean_in_ring:
            break

    if best_box is None:
        x = int(max(4, min(max_x, round(umx - box_w * 0.5))))
        y = int(max(4, min(max_y, round(uy0 - round(6 * scale) - box_h))))
        best_box = (x, y, x + box_w, y + box_h)
    return best_box


def _draw_corner_brackets(frame, x, y, right, bottom, color, thickness, span):
    span = max(6, min(span, (right - x) // 3, (bottom - y) // 3))
    for cx, cy, dx, dy in (
        (x, y, 1, 1),
        (right, y, -1, 1),
        (x, bottom, 1, -1),
        (right, bottom, -1, -1),
    ):
        cv2.line(frame, (cx, cy), (cx + dx * span, cy), color, thickness, cv2.LINE_AA)
        cv2.line(frame, (cx, cy), (cx, cy + dy * span), color, thickness, cv2.LINE_AA)


def _bake_static_overlay(state, size, *, selected, masks, trays):
    """Build transparent BGRA overlay (terrain + masks + trays + smart name tags) off the hot video path."""
    width, height = size
    scale = max(1.0, height / 720.0)
    rgba = np.zeros((height, width, 4), np.uint8)
    has_terrain = state.stage in ("register", "playback") and state.board.homography is not None and bool(state.rules.terrain)
    prediction = state.current.prediction
    if not has_terrain and (prediction is None or (not masks and not trays)):
        return None

    if has_terrain:
        matrix = state.board.homography["matrix"]
        for item in state.rules.terrain:
            polygon = (transform_points(item["polygon_source"], matrix)
                       if item.get("polygon_source") is not None else np.asarray(item["polygon_image"]))
            points = np.clip(np.rint(polygon), -1_000_000_000, 1_000_000_000).astype(np.int32)
            if len(points) >= 3:
                bgr = _TERRAIN_KIND_BGR.get(item.get("kind"), (154, 164, 172))
                cv2.fillPoly(rgba, [points], (*bgr, 52))
                cv2.polylines(rgba, [points], True, (22, 32, 42, 185), max(3, round(3.2 * scale)), cv2.LINE_AA)
                cv2.polylines(rgba, [points], True, (*bgr, 230), max(1, round(1.8 * scale)), cv2.LINE_AA)
                center = points.mean(axis=0)
                label = item.get("label") or item.get("terrain_id") or "Terrain"
                metrics = _measure_badge(label, scale * 0.88, True)
                bw, bh = metrics[0], metrics[1]
                bx = int(max(4, min(width - bw - 4, round(center[0] - bw * 0.5))))
                by = int(max(4, min(height - bh - 4, round(center[1] - bh * 0.5))))
                _draw_badge_at(rgba, label, (bx, by, bx + bw, by + bh), metrics, scale * 0.88,
                               dot_bgr=bgr, fill_rgba=(20, 32, 42, 185))

    if prediction is None or (not masks and not trays):
        return rgba

    occ = np.zeros((height, width), np.uint8)
    bindings = state.units.bindings
    pred_trays = prediction.get("trays", {})
    items = []

    for object_id, mask in zip(prediction["object_ids"], prediction["masks"]):
        side = _side_for_object(state, object_id)
        color = _object_color(object_id, side)
        is_reg_selected = state.stage == "register" and object_id == selected

        mask_arr = mask
        if mask_arr.shape != (height, width):
            mask_arr = cv2.resize(mask_arr.astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST) != 0

        ys = np.flatnonzero(mask_arr.any(axis=1))
        xs = np.flatnonzero(mask_arr.any(axis=0))
        x0 = y0 = x1 = y1 = None
        contours = None
        if len(xs):
            x0, y0, x1, y1 = int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1
            sub = mask_arr[y0:y1, x0:x1].astype(np.uint8)
            occ[y0:y1, x0:x1][sub != 0] = 1
            if masks:
                fill_alpha = 122 if is_reg_selected else 90
                roi = rgba[y0:y1, x0:x1]
                roi[sub != 0] = (*color, fill_alpha)
                contours, _ = cv2.findContours(sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE, offset=(x0, y0))
                if is_reg_selected:
                    cv2.drawContours(rgba, contours, -1, (255, 255, 255, 245), max(3, round(3.4 * scale)), cv2.LINE_AA)
                cv2.drawContours(rgba, contours, -1, (*color, 235), max(1, round(1.8 * scale)), cv2.LINE_AA)

        tray = pred_trays.get(object_id)
        polygon = None
        if tray is not None:
            polygon = np.clip(np.rint(np.asarray(tray["corners_image"])), -1_000_000_000, 1_000_000_000).astype(np.int32)
            if len(polygon):
                cv2.fillPoly(occ, [polygon], 1)
                tx0, ty0 = int(polygon[:, 0].min()), int(polygon[:, 1].min())
                tx1, ty1 = int(polygon[:, 0].max()) + 1, int(polygon[:, 1].max()) + 1
                x0 = tx0 if x0 is None else min(x0, tx0)
                y0 = ty0 if y0 is None else min(y0, ty0)
                x1 = tx1 if x1 is None else max(x1, tx1)
                y1 = ty1 if y1 is None else max(y1, ty1)
            if trays and len(polygon):
                cv2.polylines(rgba, [polygon], True, (18, 28, 36, 180), max(3, round(3.6 * scale)), cv2.LINE_AA)
                cv2.polylines(rgba, [polygon], True, (*color, 255), max(2, round(2.0 * scale)), cv2.LINE_AA)

        if x0 is not None:
            unit_box = (max(0, x0), max(0, y0), min(width, x1), min(height, y1))
            area = max(1, (unit_box[2] - unit_box[0]) * (unit_box[3] - unit_box[1]))
            label = bindings.get(object_id, f"Mask {object_id}")
            dot = (196, 138, 48) if side == "A" else (92, 82, 212) if side == "B" else None
            items.append((area, unit_box, label, dot, color))

    # Avoid covering registration prompt pins as well.
    if state.stage == "register":
        pin_occ_r = max(11, round(13 * scale))
        for prompt in state.registration_prompts:
            if prompt["object_id"] == selected:
                px, py = (int(round(v)) for v in prompt["point"])
                cv2.circle(occ, (px, py), pin_occ_r, 1, -1)

    if not items:
        return rgba

    ds = 4
    small_w, small_h = max(1, width // ds), max(1, height // ds)
    occ_small = cv2.resize(occ, (small_w, small_h), interpolation=cv2.INTER_AREA)
    integral = cv2.integral((occ_small > 0).astype(np.uint8))

    placed_boxes = []
    # Place smaller / tighter cluster units first so inner units claim close open pockets cleanly.
    for _, unit_box, label, dot, color in sorted(items, key=lambda entry: (entry[0], entry[1][1], entry[1][0])):
        metrics = _measure_badge(label, scale, dot is not None)
        bw, bh = metrics[0], metrics[1]
        box = _place_label_box(unit_box, bw, bh, width, height, scale, integral, ds, placed_boxes)
        placed_boxes.append(box)

        dist = _rect_distance(box, unit_box)
        if dist > round(9 * scale):
            p_lbl, p_unit = _nearest_points(box, unit_box)
            cv2.line(rgba, p_lbl, p_unit, (18, 28, 36, 200), max(3, round(3.0 * scale)), cv2.LINE_AA)
            cv2.line(rgba, p_lbl, p_unit, (*color, 240), max(1, round(1.5 * scale)), cv2.LINE_AA)
            cv2.circle(rgba, p_unit, max(3, round(3.2 * scale)), (248, 251, 255, 245), -1, cv2.LINE_AA)

        _draw_badge_at(rgba, label, box, metrics, scale, dot_bgr=dot)

    return rgba


class BoardImages(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.Image)
        self._lock = Lock()
        self._empty = _empty_argb()
        self._images = {"video": self._empty, "overlay": self._empty, "interactive": self._empty}

    def publish(self, frame, kind="video"):
        if frame is None:
            image = self._empty
        elif isinstance(frame, QImage):
            image = QImage(frame)
        else:
            arr = np.ascontiguousarray(frame)
            height, width = arr.shape[:2]
            fmt = QImage.Format_ARGB32 if arr.ndim == 3 and arr.shape[2] == 4 else QImage.Format_BGR888
            image = QImage(arr.data, width, height, arr.strides[0], fmt).copy()
        with self._lock:
            self._images[kind] = image

    def requestImage(self, image_id, size, requested_size):
        kind = image_id.split("/", 1)[0]
        if kind not in self._images:
            kind = "video"
        with self._lock:
            return QImage(self._images[kind])


class BoardRenderer:
    def __init__(self):
        self._overlay_key = self._in_flight_key = None
        self._pending_overlay = None
        self._future = None
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qt-overlay")
        self._bounds_key = None
        self._selection = self._target = None
        self._interactive_key = None
        self.query_layers = QueryLayers()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._pending_overlay = None
        if self._future is not None:
            self._future.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def overlay_key(state, *, selected, masks, trays):
        size = state.current.frame.shape[1::-1]
        return (
            state.source_ref.generation,
            state.current.view_revision,
            selected if state.stage == "register" else None,
            size,
            state.stage,
            masks,
            trays,
            state.board.calibration_version,
            len(state.rules.terrain),
            tuple(sorted(state.units.bindings.items())),
            tuple(prompt["click_id"] for prompt in state.registration_prompts) if state.stage == "register" else (),
        )

    def _start_pending(self):
        if self._closed or self._future is not None or self._pending_overlay is None:
            return
        key, args = self._pending_overlay
        self._pending_overlay = None
        self._in_flight_key = key
        self._future = self._executor.submit(self._bake_task, key, args)

    @staticmethod
    def _bake_task(key, args):
        state, size, selected, masks, trays = args
        return key, _bake_static_overlay(state, size, selected=selected, masks=masks, trays=trays)

    def sync_overlay(self, state, *, selected, masks, trays):
        """Return (updated, has_overlay, overlay_rgba_or_None). Heavy builds run off the GUI thread while playing."""
        key = self.overlay_key(state, selected=selected, masks=masks, trays=trays)
        if key == self._overlay_key:
            return False, None
        size = state.current.frame.shape[1::-1]
        if not state.playing:
            self._pending_overlay = None
            self._overlay_key = key
            return True, _bake_static_overlay(state, size, selected=selected, masks=masks, trays=trays)
        if key != self._in_flight_key:
            self._pending_overlay = (key, (state, size, selected, masks, trays))
            self._start_pending()
        return False, None

    def poll_overlay(self, current_generation=None):
        if self._future is None or not self._future.done():
            return False, None
        future, self._future = self._future, None
        self._in_flight_key = None
        try:
            key, rgba = future.result()
        except Exception:
            self._start_pending()
            return False, None
        if current_generation is not None and key[0] != current_generation:
            self._start_pending()
            return False, None
        if key == self._overlay_key:
            self._start_pending()
            return False, None
        self._overlay_key = key
        self._start_pending()
        return True, rgba

    def _selection_bounds(self, state, selected, target):
        size = state.current.frame.shape[1::-1]
        key = (state.source_ref.generation, state.current.view_revision, selected, target, size, state.stage)
        if key != self._bounds_key:
            self._selection = self._target = None
            prediction = state.current.prediction
            if prediction is not None and state.stage == "playback" and (selected is not None or target is not None):
                for object_id, mask in zip(prediction["object_ids"], prediction["masks"]):
                    if object_id in (selected, target):
                        ys = np.flatnonzero(mask.any(axis=1))
                        xs = np.flatnonzero(mask.any(axis=0))
                        if len(xs):
                            bounds = (int(xs[0]), int(ys[0]), int(xs[-1]), int(ys[-1]))
                            if object_id == selected:
                                self._selection = bounds
                            else:
                                self._target = bounds
            self._bounds_key = key

    def render_interactive(self, state, *, selected, target=None, queries=None, trays=True,
                           corners=(), points=(), flow=None):
        """Lightweight vector / corner / query overlay built only when interactive inputs change."""
        flow_key = flow.interactive_key(state) if flow is not None else None
        key = (
            state.source_ref.generation,
            state.current.view_revision,
            selected,
            target,
            trays,
            id(queries.result) if queries is not None else None,
            tuple(prompt["click_id"] for prompt in state.registration_prompts) if state.stage == "register" else (),
            repr(corners) if state.stage == "table" else None,
            tuple(map(tuple, points)) if state.stage == "table" else (),
            state.stage,
            state.board.calibration_version,
            flow_key,
        )
        if key == self._interactive_key:
            return False, None
        self._interactive_key = key

        base_frame = state.source_image if (flow is not None and flow.kind(state) == "recalibrate") else state.current.frame
        width, height = base_frame.shape[1::-1]
        scale = max(1.0, height / 720.0)
        self._selection_bounds(state, selected, target)

        has_fronts = bool(trays and state.current.prediction is not None and state.rules.fronts)
        has_prompts = state.stage == "register" and bool(state.registration_prompts)
        has_corners = state.stage == "table" and (bool(corners) or bool(points))
        has_query = queries is not None and queries.result is not None and queries.result_request is not None and queries.result_current(state)
        has_flow = flow is not None and flow.has_interactive(state)

        if not (self._selection or self._target or has_fronts or has_prompts or has_corners or has_query or has_flow):
            return True, None

        rgba = np.zeros((height, width, 4), np.uint8)

        if self._selection is not None:
            x, y, right, bottom = self._selection
            pad = max(4, round(5 * scale))
            bx1, by1, bx2, by2 = x - pad, y - pad, right + pad, bottom + pad
            cv2.rectangle(rgba, (bx1, by1), (bx2, by2), (58, 42, 23, 240), max(4, round(4.8 * scale)), cv2.LINE_AA)
            cv2.rectangle(rgba, (bx1, by1), (bx2, by2), (255, 255, 255, 255), max(2, round(2.0 * scale)), cv2.LINE_AA)
            _draw_corner_brackets(rgba, bx1, by1, bx2, by2, (230, 195, 70, 255), max(2, round(2.4 * scale)), round(14 * scale))

        if self._target is not None:
            x, y, right, bottom = self._target
            pad = max(3, round(4 * scale))
            bx1, by1, bx2, by2 = x - pad, y - pad, right + pad, bottom + pad
            cv2.rectangle(rgba, (bx1, by1), (bx2, by2), (48, 88, 32, 240), max(4, round(4.2 * scale)), cv2.LINE_AA)
            cv2.rectangle(rgba, (bx1, by1), (bx2, by2), (160, 235, 115, 255), max(2, round(2.0 * scale)), cv2.LINE_AA)

        if has_query:
            q_bgr = np.zeros((height, width, 3), np.uint8)
            self.query_layers.draw(q_bgr, queries, state)
            q_mask = q_bgr.any(axis=2)
            if np.any(q_mask):
                rgba[q_mask, :3] = np.clip(q_bgr[q_mask].astype(np.float32) / 0.6, 0, 255).astype(np.uint8)
                rgba[q_mask, 3] = 205

        if has_fronts:
            trays_map = state.current.prediction.get("trays", {})
            matrix = state.board.homography["matrix"]
            for object_id in trays_map:
                front = state.rules.fronts.get(object_id)
                if front is not None and front.get("source_ray") is not None:
                    ray = np.rint(transform_points(front["source_ray"], matrix)).astype(int)
                    cv2.arrowedLine(rgba, tuple(ray[0]), tuple(ray[1]), (24, 42, 32, 220),
                                    max(4, round(4.4 * scale)), cv2.LINE_AA, tipLength=0.3)
                    cv2.arrowedLine(rgba, tuple(ray[0]), tuple(ray[1]), (90, 235, 155, 255),
                                    max(2, round(2.4 * scale)), cv2.LINE_AA, tipLength=0.3)

        if has_prompts:
            pin_r = max(7, round(8.5 * scale))
            arm = max(3, round(4.0 * scale))
            stroke = max(2, round(2.0 * scale))
            for prompt in state.registration_prompts:
                if prompt["object_id"] == selected:
                    cx, cy = (int(round(v)) for v in prompt["point"])
                    fill = (96, 123, 25, 255) if prompt["positive"] else (67, 57, 194, 255)
                    cv2.circle(rgba, (cx, cy), pin_r + 1, (20, 28, 34, 240), -1, cv2.LINE_AA)
                    cv2.circle(rgba, (cx, cy), pin_r, fill, -1, cv2.LINE_AA)
                    cv2.circle(rgba, (cx, cy), pin_r, (255, 255, 255, 255), stroke, cv2.LINE_AA)
                    cv2.line(rgba, (cx - arm, cy), (cx + arm, cy), (255, 255, 255, 255), stroke, cv2.LINE_AA)
                    if prompt["positive"]:
                        cv2.line(rgba, (cx, cy - arm), (cx, cy + arm), (255, 255, 255, 255), stroke, cv2.LINE_AA)

        if corners:
            polygon = np.rint(list(corners.values())).astype(np.int32)
            cv2.polylines(rgba, [polygon], True, (18, 32, 44, 230), max(5, round(5.0 * scale)), cv2.LINE_AA)
            cv2.polylines(rgba, [polygon], True, (242, 196, 68, 255), max(2, round(2.6 * scale)), cv2.LINE_AA)
            node_r = max(6, round(7.5 * scale))
            for name, point in corners.items():
                px, py = (int(round(v)) for v in point)
                cv2.circle(rgba, (px, py), node_r + 2, (20, 34, 46, 240), -1, cv2.LINE_AA)
                cv2.circle(rgba, (px, py), node_r, (255, 255, 255, 255), -1, cv2.LINE_AA)
                cv2.circle(rgba, (px, py), max(3, round(3.8 * scale)), (137, 107, 36, 255), -1, cv2.LINE_AA)
                font_scale = max(0.48, 0.55 * scale)
                thick = max(1, round(1.5 * scale))
                (tw, th), _ = cv2.getTextSize(name, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thick)
                bx = max(4, min(width - tw - 16, px + node_r + 6))
                by = max(4, min(height - th - 14, py - th - 10))
                cv2.rectangle(rgba, (bx, by), (bx + tw + 12, by + th + 10), (20, 32, 42, 230), -1)
                cv2.rectangle(rgba, (bx, by), (bx + tw + 12, by + th + 10), (242, 196, 68, 255), max(1, round(scale)))
                cv2.putText(rgba, name, (bx + 6, by + th + 5), cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                            (255, 255, 255, 255), thick, cv2.LINE_AA)
        elif points:
            pts = np.rint(list(points)).astype(np.int32)
            if len(pts) >= 2:
                cv2.polylines(rgba, [pts], False, (18, 32, 44, 220), max(4, round(4.2 * scale)), cv2.LINE_AA)
                cv2.polylines(rgba, [pts], False, (242, 196, 68, 255), max(2, round(2.2 * scale)), cv2.LINE_AA)
            node_r = max(9, round(10.5 * scale))
            for idx, (px, py) in enumerate(pts, start=1):
                cv2.circle(rgba, (int(px), int(py)), node_r + 2, (20, 32, 42, 240), -1, cv2.LINE_AA)
                cv2.circle(rgba, (int(px), int(py)), node_r, (242, 196, 68, 255), -1, cv2.LINE_AA)
                label = str(idx)
                font_scale = max(0.45, 0.5 * scale)
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, max(1, round(1.5 * scale)))
                cv2.putText(rgba, label, (int(px - tw / 2), int(py + th / 2)), cv2.FONT_HERSHEY_SIMPLEX,
                            font_scale, (20, 32, 42, 255), max(1, round(1.5 * scale)), cv2.LINE_AA)

        if has_flow:
            flow.draw_interactive(state, rgba)

        return True, rgba
