"""Owned Qt images and decoupled video / async mask-overlay / fast interactive rendering."""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from threading import Lock

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from components.homography import transform_points
from frontend.shared.layers import QueryLayers

# Tightly harmonized team palettes in BGR so adjacent units remain distinguishable
# without drifting into Replay amber (#e8a23a) or Recovery yellow-gold.
_SIDE_A_BGR = (
    (224, 166, 76),
    (212, 146, 60),
    (232, 184, 96),
    (196, 130, 52),
    (216, 174, 114),
    (184, 152, 68),
)

_SIDE_B_BGR = (
    (112, 94, 226),
    (102, 76, 210),
    (130, 108, 236),
    (122, 82, 232),
    (142, 98, 218),
    (108, 86, 222),
)

_UNBOUND_BGR = (
    (194, 174, 72),
    (126, 194, 110),
    (212, 148, 86),
    (124, 184, 214),
    (188, 130, 182),
    (152, 194, 112),
)

_TERRAIN_KIND_BGR = {
    "blocking": (108, 104, 214),
    "difficult": (74, 178, 232),
    "obstacle": (196, 138, 92),
    "hill": (122, 188, 114),
    "decorative": (162, 174, 184),
}

# Unified high-contrast selection highlight (Ice Cyan #4ce8ff in BGR)
_SELECTION_BGR = (255, 232, 76)
_TARGET_BGR = (153, 211, 54)
_RECOVERY_BGR = (64, 208, 250)


@lru_cache(maxsize=16)
def _ui_font(size, bold=True):
    fonts_dir = Path("C:/Windows/Fonts")
    candidates = ("seguisb.ttf", "segoeui.ttf", "msyhbd.ttc", "msyh.ttc") if bold else ("segoeui.ttf", "msyh.ttc")
    for name in candidates:
        path = fonts_dir / name
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return ImageFont.load_default()


def _bgr_hex(bgr):
    return f"#{int(bgr[2]):02x}{int(bgr[1]):02x}{int(bgr[0]):02x}"


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


def unit_badge_label(state, unit_id):
    """Display the unit's readable army-list name on board badges, falling back to unit_id."""
    if not unit_id:
        return ""
    unit = state.units.units.get(unit_id)
    if unit is None:
        return str(unit_id)
    catalog = state.units.types.get(unit["type_id"], {})
    name = str(catalog.get("unit_name") or "").strip()
    if not name:
        raw = str(catalog.get("name") or "").strip()
        if raw and len(raw) <= 28:
            name = raw
    return name or str(unit_id)


def _object_color(object_id, side):
    palette = _SIDE_A_BGR if side == "A" else _SIDE_B_BGR if side == "B" else _UNBOUND_BGR
    return palette[(object_id - 1) % len(palette)]


def measure_pill_box(text, scale, has_dot=True):
    """Measure frame-space capsule bounds matching QML BoardBadges proportions."""
    text = str(text)
    font_px = max(14, round(15.5 * scale))
    font = _ui_font(font_px, bold=True)
    bbox = font.getbbox(text)
    text_w = max(14, bbox[2] - bbox[0])
    pad_x = max(8, round(9.0 * scale))
    dot_d = max(7, round(8.0 * scale)) if has_dot else 0
    dot_gap = max(5, round(5.5 * scale)) if has_dot else 0
    box_w = pad_x * 2 + text_w + (dot_d + dot_gap if has_dot else 0) + 4
    box_h = max(22, round(24.0 * scale))
    return int(box_w), int(box_h)


def draw_pill_tag(rgba, text, x, y, scale, *, border_bgr=(255, 232, 76), fill_bgra=(34, 25, 16, 235), text_bgra=(247, 243, 237, 255)):
    """Draw a crisp anti-aliased rounded pill tag directly onto a BGRA canvas ROI."""
    text = str(text)
    font_px = max(14, round(15.5 * scale))
    font = _ui_font(font_px, bold=True)
    bbox = font.getbbox(text)
    tw = max(10, bbox[2] - bbox[0])
    th = max(12, bbox[3] - bbox[1])
    pad_x = max(8, round(8.5 * scale))
    pad_y = max(5, round(5.5 * scale))
    bw = tw + pad_x * 2
    bh = th + pad_y * 2
    h, w = rgba.shape[:2]
    x0 = max(4, min(w - bw - 4, int(round(x))))
    y0 = max(4, min(h - bh - 4, int(round(y))))
    x1 = min(w - 1, x0 + bw)
    y1 = min(h - 1, y0 + bh)
    if x1 <= x0 or y1 <= y0:
        return
    roi = rgba[y0:y1, x0:x1]
    pil_roi = Image.fromarray(roi, "RGBA")
    draw = ImageDraw.Draw(pil_roi)
    radius = min((x1 - x0) // 2, (y1 - y0) // 2)
    draw.rounded_rectangle(
        [0, 0, x1 - x0 - 1, y1 - y0 - 1],
        radius=radius,
        fill=fill_bgra,
        outline=(*border_bgr, 245),
        width=max(1, round(1.3 * scale)),
    )
    tx = (x1 - x0 - tw) // 2 - bbox[0]
    ty = (y1 - y0 - th) // 2 - bbox[1]
    draw.text((tx, ty), text, font=font, fill=text_bgra)
    rgba[y0:y1, x0:x1] = np.asarray(pil_roi)


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


def nearest_rect_points(box, target):
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
    margin = max(4, round(4.5 * scale))
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
    gaps = (round(7 * scale), round(16 * scale), round(28 * scale), round(44 * scale), round(66 * scale), round(94 * scale))

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
        if found_clean_in_ring:
            break

    if best_box is None:
        x = int(max(4, min(max_x, round(umx - box_w * 0.5))))
        y = int(max(4, min(max_y, round(uy0 - round(7 * scale) - box_h))))
        best_box = (x, y, x + box_w, y + box_h)
    return best_box


def place_badges(entries, occ, frame_w, frame_h, scale, *, pre_placed=()):
    """Place unit badges with 1/4-res integral occupancy & collision avoidance.

    Each entry is (area, unit_box, label, dot_bgr, border_bgr, object_id, active).
    Returns list of (box, entry, leader_dist).
    """
    if not entries:
        return []
    ds = 4
    small_w, small_h = max(1, frame_w // ds), max(1, frame_h // ds)
    occ_small = cv2.resize(occ, (small_w, small_h), interpolation=cv2.INTER_AREA)
    integral = cv2.integral((occ_small > 0).astype(np.uint8))

    placed_boxes = list(pre_placed)
    results = []
    # Smaller / inner cluster units claim close open pockets first.
    for entry in sorted(entries, key=lambda item: (item[0], item[1][1], item[1][0])):
        _, unit_box, label, dot_bgr, _, _, _ = entry
        bw, bh = measure_pill_box(label, scale, has_dot=dot_bgr is not None)
        box = _place_label_box(unit_box, bw, bh, frame_w, frame_h, scale, integral, ds, placed_boxes)
        placed_boxes.append(box)
        dist = _rect_distance(box, unit_box)
        results.append((box, entry, dist))
    return results


def draw_corner_brackets(frame, x, y, right, bottom, color, thickness, span):
    span = max(6, min(span, (right - x) // 3, (bottom - y) // 3))
    for cx, cy, dx, dy in (
        (x, y, 1, 1),
        (right, y, -1, 1),
        (x, bottom, 1, -1),
        (right, bottom, -1, -1),
    ):
        cv2.line(frame, (cx, cy), (cx + dx * span, cy), color, thickness, cv2.LINE_AA)
        cv2.line(frame, (cx, cy), (cx, cy + dy * span), color, thickness, cv2.LINE_AA)


def _badge_dict(box, width, height, label, dot_bgr, border_bgr, *, kind="unit", object_id=-1, unit_id="", active=False, unconfirmed=False):
    return {
        "x": box[0] / width,
        "y": box[1] / height,
        "w": (box[2] - box[0]) / width,
        "h": (box[3] - box[1]) / height,
        "text": str(label),
        "dot": _bgr_hex(dot_bgr) if dot_bgr is not None else "",
        "border": _bgr_hex(border_bgr),
        "kind": kind,
        "objectId": int(object_id),
        "unitId": str(unit_id),
        "active": bool(active),
        "unconfirmed": bool(unconfirmed),
    }


def _draw_dashed_poly(canvas, points, color, *, halo=(26, 20, 12), thickness=2, dash=9, gap=6):
    pts = np.asarray(points, dtype=float)
    n = len(pts)
    for i in range(n):
        p0, p1 = pts[i], pts[(i + 1) % n]
        vec = p1 - p0
        length = float(np.hypot(vec[0], vec[1]))
        if length < 1e-3:
            continue
        unit = vec / length
        pos = 0.0
        while pos < length:
            end = min(length, pos + dash)
            a = tuple(np.rint(p0 + unit * pos).astype(int))
            b = tuple(np.rint(p0 + unit * end).astype(int))
            cv2.line(canvas, a, b, halo, thickness + 2, cv2.LINE_AA)
            cv2.line(canvas, a, b, color, thickness, cv2.LINE_AA)
            pos += dash + gap


def _bake_static_overlay(state, size, *, selected, masks, trays, labels=True, terrain=True, selected_terrain=""):
    """Build transparent BGRA overlay (terrain + masks + trays + leader lines) & crisp QML badge coords."""
    width, height = size
    scale = max(1.0, height / 720.0)
    rgba = np.zeros((height, width, 4), np.uint8)
    has_terrain = (
        terrain
        and state.stage in ("register", "playback")
        and state.board.homography is not None
        and bool(state.rules.terrain)
    )
    prediction = state.current.prediction
    has_units = prediction is not None and (masks or trays or labels)
    if not has_terrain and not has_units:
        return None, []

    badges = []
    pre_placed = []

    if has_terrain:
        matrix = state.board.homography["matrix"]
        for item in state.rules.terrain:
            polygon = (transform_points(item["polygon_source"], matrix)
                       if item.get("polygon_source") is not None else np.asarray(item["polygon_image"]))
            points = np.clip(np.rint(polygon), -1_000_000_000, 1_000_000_000).astype(np.int32)
            if len(points) >= 3:
                tid = str(item.get("terrain_id") or "")
                is_sel_terrain = state.stage == "register" and bool(selected_terrain) and tid == selected_terrain
                bgr = _TERRAIN_KIND_BGR.get(item.get("kind"), (162, 174, 184))
                if is_sel_terrain:
                    cv2.fillPoly(rgba, [points], (*bgr, 76))
                    cv2.polylines(rgba, [points], True, (14, 22, 28, 235), max(4, round(4.8 * scale)), cv2.LINE_AA)
                    cv2.polylines(rgba, [points], True, (*_SELECTION_BGR, 255), max(2, round(2.6 * scale)), cv2.LINE_AA)
                else:
                    cv2.fillPoly(rgba, [points], (*bgr, 40))
                    cv2.polylines(rgba, [points], True, (14, 22, 28, 195), max(3, round(3.4 * scale)), cv2.LINE_AA)
                    cv2.polylines(rgba, [points], True, (*bgr, 235), max(1, round(1.8 * scale)), cv2.LINE_AA)
                if labels:
                    center = points.mean(axis=0)
                    label = item.get("label") or tid or "Terrain"
                    bw, bh = measure_pill_box(label, scale * 0.92, has_dot=True)
                    bx = int(max(4, min(width - bw - 4, round(center[0] - bw * 0.5))))
                    by = int(max(4, min(height - bh - 4, round(center[1] - bh * 0.5))))
                    t_box = (bx, by, bx + bw, by + bh)
                    pre_placed.append(t_box)
                    badges.append(_badge_dict(
                        t_box, width, height, label, bgr,
                        _SELECTION_BGR if is_sel_terrain else bgr,
                        kind="terrain", unit_id=tid, active=is_sel_terrain,
                    ))

    if not has_units:
        return rgba, badges

    occ = np.zeros((height, width), np.uint8)
    bindings = state.units.bindings
    unconfirmed_ids = set(getattr(state, "registration_unconfirmed", ())) if state.stage == "register" else set()
    pred_trays = prediction.get("trays", {})
    held_ids = set()
    if trays and state.stage == "playback" and state.mode == "live" and state.board.image_to_plane is not None:
        held_ids = (set(prediction.get("tray_errors", ())) - pred_trays.keys()
                    - set(prediction.get("unavailable_ids", ())) - set(prediction.get("inactive_ids", ())))
    plane_to_image = np.linalg.inv(state.board.image_to_plane) if held_ids else None
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
        if len(xs):
            x0, y0, x1, y1 = int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1
            sub = mask_arr[y0:y1, x0:x1].astype(np.uint8)
            occ[y0:y1, x0:x1][sub != 0] = 1
            if masks:
                if state.stage == "register":
                    fill_alpha = 88 if is_reg_selected else 56
                else:
                    fill_alpha = 40 if trays else 58
                roi = rgba[y0:y1, x0:x1]
                roi[sub != 0] = (*color, fill_alpha)
                contours, _ = cv2.findContours(sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE, offset=(x0, y0))
                if is_reg_selected:
                    cv2.drawContours(rgba, contours, -1, (16, 24, 32, 235), max(4, round(4.8 * scale)), cv2.LINE_AA)
                    cv2.drawContours(rgba, contours, -1, (*_SELECTION_BGR, 255), max(2, round(2.6 * scale)), cv2.LINE_AA)
                else:
                    cv2.drawContours(rgba, contours, -1, (14, 22, 28, 170), max(2, round(2.8 * scale)), cv2.LINE_AA)
                    cv2.drawContours(rgba, contours, -1, (*color, 235), max(1, round(1.8 * scale)), cv2.LINE_AA)

        tray = pred_trays.get(object_id)
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
                cv2.polylines(rgba, [polygon], True, (12, 20, 26, 215), max(3, round(3.8 * scale)), cv2.LINE_AA)
                cv2.polylines(rgba, [polygon], True, (*color, 255), max(2, round(2.0 * scale)), cv2.LINE_AA)
        elif object_id in held_ids and x0 is not None:
            tracking = state.tracking.get(bindings.get(object_id))
            last = tracking.last_accepted_position if tracking is not None else None
            if last and last["calibration_version"] == state.board.calibration_version:
                corners = transform_points(last["corners_mm"], plane_to_image)
                _draw_dashed_poly(rgba, corners, (*color, 185), halo=(12, 20, 26, 135),
                                  thickness=max(1, round(1.6 * scale)), dash=round(9 * scale), gap=round(8 * scale))

        if labels and x0 is not None:
            unit_box = (max(0, x0), max(0, y0), min(width, x1), min(height, y1))
            area = max(1, (unit_box[2] - unit_box[0]) * (unit_box[3] - unit_box[1]))
            unit_id = bindings.get(object_id, "")
            label = unit_badge_label(state, unit_id) if unit_id else f"Mask {object_id}"
            dot = _SIDE_A_BGR[0] if side == "A" else _SIDE_B_BGR[0] if side == "B" else None
            items.append((area, unit_box, label, dot, _SELECTION_BGR if is_reg_selected else color, object_id, is_reg_selected))

    if labels:
        # Avoid covering registration prompt pins as well.
        if state.stage == "register":
            pin_occ_r = max(12, round(14 * scale))
            for prompt in state.registration_prompts:
                if prompt["object_id"] == selected:
                    px, py = (int(round(v)) for v in prompt["point"])
                    cv2.circle(occ, (px, py), pin_occ_r, 1, -1)

        placed = place_badges(items, occ, width, height, scale, pre_placed=pre_placed)
        for box, entry, dist in placed:
            _, unit_box, label, dot, border_bgr, object_id, is_active = entry
            if dist > round(9 * scale):
                p_lbl, p_unit = nearest_rect_points(box, unit_box)
                cv2.line(rgba, p_lbl, p_unit, (12, 20, 26, 220), max(3, round(3.2 * scale)), cv2.LINE_AA)
                cv2.line(rgba, p_lbl, p_unit, (*border_bgr, 245), max(1, round(1.6 * scale)), cv2.LINE_AA)
                cv2.circle(rgba, p_unit, max(3, round(3.5 * scale)), (12, 20, 26, 240), -1, cv2.LINE_AA)
                cv2.circle(rgba, p_unit, max(2, round(2.5 * scale)), (237, 243, 247, 255), -1, cv2.LINE_AA)
            badges.append(_badge_dict(
                box, width, height, label, dot, border_bgr,
                kind="unit", object_id=object_id, unit_id=bindings.get(object_id, ""),
                active=is_active, unconfirmed=object_id in unconfirmed_ids,
            ))

    return rgba, badges


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
        self.badges = []
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
    def overlay_key(state, *, selected, masks, trays, labels=True, terrain=True, selected_terrain=""):
        size = state.current.frame.shape[1::-1]
        return (
            state.source_ref.generation,
            state.current.view_revision,
            selected if state.stage == "register" else None,
            selected_terrain if state.stage == "register" else "",
            size,
            state.stage,
            masks,
            trays,
            labels,
            terrain,
            state.board.calibration_version,
            tuple((item.get("terrain_id"), item.get("label"), item.get("kind"), item.get("height"))
                  for item in state.rules.terrain),
            id(state.units.types),
            tuple(sorted(state.units.bindings.items())),
            tuple(getattr(state, "registration_unconfirmed", ())) if state.stage == "register" else (),
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
        state, size, selected, masks, trays, labels, terrain, selected_terrain = args
        rgba, badges = _bake_static_overlay(
            state, size, selected=selected, masks=masks, trays=trays,
            labels=labels, terrain=terrain, selected_terrain=selected_terrain,
        )
        return key, rgba, badges

    def sync_overlay(self, state, *, selected, masks, trays, labels=True, terrain=True, selected_terrain=""):
        """Return (updated, overlay_rgba_or_None); updates self.badges in lockstep."""
        key = self.overlay_key(
            state, selected=selected, masks=masks, trays=trays,
            labels=labels, terrain=terrain, selected_terrain=selected_terrain,
        )
        if key == self._overlay_key:
            return False, None
        size = state.current.frame.shape[1::-1]
        if not state.playing:
            self._pending_overlay = None
            self._overlay_key = key
            rgba, badges = _bake_static_overlay(
                state, size, selected=selected, masks=masks, trays=trays,
                labels=labels, terrain=terrain, selected_terrain=selected_terrain,
            )
            self.badges = badges
            return True, rgba
        if key != self._in_flight_key:
            self._pending_overlay = (key, (state, size, selected, masks, trays, labels, terrain, selected_terrain))
            self._start_pending()
        return False, None

    def poll_overlay(self, current_generation=None):
        if self._future is None or not self._future.done():
            return False, None
        future, self._future = self._future, None
        self._in_flight_key = None
        try:
            key, rgba, badges = future.result()
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
        self.badges = badges
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
            pad = max(5, round(5.5 * scale))
            bx1, by1, bx2, by2 = x - pad, y - pad, right + pad, bottom + pad
            cv2.rectangle(rgba, (bx1, by1), (bx2, by2), (14, 22, 28, 235), max(4, round(5.0 * scale)), cv2.LINE_AA)
            cv2.rectangle(rgba, (bx1, by1), (bx2, by2), (*_SELECTION_BGR, 255), max(2, round(2.0 * scale)), cv2.LINE_AA)
            draw_corner_brackets(rgba, bx1, by1, bx2, by2, (255, 255, 255, 255), max(2, round(2.4 * scale)), round(14 * scale))

        if self._target is not None:
            x, y, right, bottom = self._target
            pad = max(4, round(4.5 * scale))
            bx1, by1, bx2, by2 = x - pad, y - pad, right + pad, bottom + pad
            cv2.rectangle(rgba, (bx1, by1), (bx2, by2), (14, 26, 22, 235), max(4, round(4.4 * scale)), cv2.LINE_AA)
            cv2.rectangle(rgba, (bx1, by1), (bx2, by2), (*_TARGET_BGR, 255), max(2, round(2.0 * scale)), cv2.LINE_AA)

        if has_query:
            q_bgr = np.zeros((height, width, 3), np.uint8)
            self.query_layers.draw(q_bgr, queries, state)
            q_mask = q_bgr.any(axis=2)
            if np.any(q_mask):
                rgba[q_mask, :3] = np.clip(q_bgr[q_mask].astype(np.float32) / 0.6, 0, 255).astype(np.uint8)
                rgba[q_mask, 3] = 230

        if has_fronts:
            trays_map = state.current.prediction.get("trays", {})
            matrix = state.board.homography["matrix"]
            for object_id in trays_map:
                front = state.rules.fronts.get(object_id)
                if front is not None and front.get("source_ray") is not None:
                    ray = np.rint(transform_points(front["source_ray"], matrix)).astype(int)
                    cv2.arrowedLine(rgba, tuple(ray[0]), tuple(ray[1]), (14, 24, 20, 230),
                                    max(4, round(4.4 * scale)), cv2.LINE_AA, tipLength=0.3)
                    cv2.arrowedLine(rgba, tuple(ray[0]), tuple(ray[1]), (153, 211, 54, 255),
                                    max(2, round(2.4 * scale)), cv2.LINE_AA, tipLength=0.3)

        if has_prompts:
            pin_r = max(7, round(8.5 * scale))
            arm = max(3, round(4.0 * scale))
            stroke = max(2, round(2.0 * scale))
            for prompt in state.registration_prompts:
                if prompt["object_id"] == selected:
                    cx, cy = (int(round(v)) for v in prompt["point"])
                    fill = (153, 211, 54, 255) if prompt["positive"] else (82, 74, 217, 255)
                    cv2.circle(rgba, (cx, cy), pin_r + 2, (14, 22, 28, 245), -1, cv2.LINE_AA)
                    cv2.circle(rgba, (cx, cy), pin_r, fill, -1, cv2.LINE_AA)
                    cv2.circle(rgba, (cx, cy), pin_r, (255, 255, 255, 255), stroke, cv2.LINE_AA)
                    cv2.line(rgba, (cx - arm, cy), (cx + arm, cy), (255, 255, 255, 255), stroke, cv2.LINE_AA)
                    if prompt["positive"]:
                        cv2.line(rgba, (cx, cy - arm), (cx, cy + arm), (255, 255, 255, 255), stroke, cv2.LINE_AA)

        if corners:
            polygon = np.rint(list(corners.values())).astype(np.int32)
            cv2.polylines(rgba, [polygon], True, (14, 22, 28, 235), max(5, round(5.2 * scale)), cv2.LINE_AA)
            cv2.polylines(rgba, [polygon], True, (*_SELECTION_BGR, 255), max(2, round(2.6 * scale)), cv2.LINE_AA)
            node_r = max(6, round(7.5 * scale))
            for name, point in corners.items():
                px, py = (int(round(v)) for v in point)
                cv2.circle(rgba, (px, py), node_r + 2, (14, 22, 28, 245), -1, cv2.LINE_AA)
                cv2.circle(rgba, (px, py), node_r, (255, 255, 255, 255), -1, cv2.LINE_AA)
                cv2.circle(rgba, (px, py), max(3, round(3.8 * scale)), (*_SELECTION_BGR, 255), -1, cv2.LINE_AA)
                bx = max(6, min(width - 44, px + node_r + 6))
                by = max(6, min(height - 32, py - round(24 * scale)))
                draw_pill_tag(rgba, name, bx, by, scale, border_bgr=_SELECTION_BGR)
        elif points:
            pts = np.rint(list(points)).astype(np.int32)
            if len(pts) >= 2:
                cv2.polylines(rgba, [pts], False, (14, 22, 28, 230), max(4, round(4.4 * scale)), cv2.LINE_AA)
                cv2.polylines(rgba, [pts], False, (*_SELECTION_BGR, 255), max(2, round(2.2 * scale)), cv2.LINE_AA)
            node_r = max(10, round(11.0 * scale))
            font = _ui_font(max(13, round(14 * scale)), bold=True)
            for idx, (px, py) in enumerate(pts, start=1):
                cv2.circle(rgba, (int(px), int(py)), node_r + 2, (14, 22, 28, 245), -1, cv2.LINE_AA)
                cv2.circle(rgba, (int(px), int(py)), node_r, (*_SELECTION_BGR, 255), -1, cv2.LINE_AA)
                label = str(idx)
                bbox = font.getbbox(label)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                x0 = max(0, int(px - node_r))
                y0 = max(0, int(py - node_r))
                x1 = min(width, x0 + node_r * 2)
                y1 = min(height, y0 + node_r * 2)
                if x1 > x0 and y1 > y0:
                    pil_roi = Image.fromarray(rgba[y0:y1, x0:x1], "RGBA")
                    ImageDraw.Draw(pil_roi).text(
                        ((x1 - x0 - tw) // 2 - bbox[0], (y1 - y0 - th) // 2 - bbox[1]),
                        label, font=font, fill=(28, 22, 14, 255),
                    )
                    rgba[y0:y1, x0:x1] = np.asarray(pil_roi)

        if has_flow:
            flow.draw_interactive(state, rgba)

        return True, rgba
