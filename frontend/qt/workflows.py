"""Qt adapters for existing live maintenance commands and read-only replay."""
from collections.abc import Mapping
import math
import re

import cv2
import numpy as np
from PIL import Image, ImageDraw
from PySide6.QtCore import QObject, Property, Signal, Slot

from components.homography import transform_points
from components.homography.geometry import order_corners
from .board import (
    _SELECTION_BGR,
    _SIDE_A_BGR,
    _SIDE_B_BGR,
    _TERRAIN_KIND_BGR,
    _badge_dict,
    _bgr_hex,
    _draw_dashed_poly,
    _ui_font,
    draw_corner_brackets,
    nearest_rect_points,
    place_badges,
    unit_badge_label,
    unit_list_side,
)


def _catalog_rows(roster, catalog, values):
    def records(entries):
        return [entry for entry in entries if isinstance(entry, Mapping)] if isinstance(entries, (list, tuple)) else []

    originals = records(catalog.get("source_entries"))
    original = originals[0] if originals else {}
    list_id = catalog.get("list_id")
    payload = roster.payload
    if list_id:
        payload = payload.get("lists", {}).get(list_id, {}).get("metadata", payload)
    sources = payload.get("sources") or ()
    index = original.get("source_index", 0)
    source = sources[index] if isinstance(sources, (list, tuple)) and isinstance(index, int) and 0 <= index < len(sources) else {}
    source = source if isinstance(source, Mapping) else {}
    appendix = source.get("appendix", {})
    appendix = appendix if isinstance(appendix, Mapping) else {}

    def row(label, value):
        return ("", label, value, "readonly", None)

    def names(entries):
        return {entry["name"].casefold(): entry for entry in records(entries) if isinstance(entry.get("name"), str)}

    def descriptions(labels, entries):
        lookup = names(entries)
        details = []
        for label in labels:
            key = label.casefold()
            base = re.sub(r"\s*\([^()]*\)$", "", key)
            definition = lookup.get(key) or lookup.get(base + " (n)") or lookup.get(base, {})
            if description := definition.get("description"):
                details.append(f"{label} — {description}")
        return "\n\n".join(details)

    rows = []
    title = catalog.get("unit_name") or catalog.get("name")
    profile = "\n".join(filter(None, (title, catalog.get("classification"))))
    if profile:
        rows.append(row("Unit profile", profile))
    stats = (("Melee", "melee"), ("Shooting", "shooting"), ("Defence", "defence"),
             ("Unit strength", "unit_strength"), ("Attacks", "attacks"), ("Nerve", "nerve"),
             ("Points", "points"))
    stat_text = "   ·   ".join(f"{label} {values[key] if values[key] is not None else '—'}"
                              for label, key in stats if key in values)
    if stat_text:
        rows.append(row("Combat stats", stat_text))
    summary, rows = rows, []
    if traits := values.get("traits"):
        rows.append(row("Traits", ", ".join(map(str, traits)) if isinstance(traits, (list, tuple)) else str(traits)))
    weapons = [f"{weapon['name']} ({weapon['range_in']:g} in)" for weapon in records(values.get("weapons"))
               if weapon.get("name") and isinstance(weapon.get("range_in"), (int, float))]
    if weapons:
        rows.append(row("Weapons", "\n".join(weapons)))
    for kind, section, label in (("", "", "Options"), ("spell", "spells", "Spells"),
                                 ("artefact", "artefacts", "Artefacts")):
        entries = names(appendix.get(section, ()))
        options = []
        for option in records(values.get("options")):
            if option.get("kind", "") != kind or not option.get("label"):
                continue
            heading = option["label"]
            if option.get("points") is not None:
                heading = f"{heading} · {option['points']} pts"
            definition = entries.get(str(option.get("name", "")).casefold(), {})
            notes = [f"Range: {definition['range']}" if definition.get("range") else "",
                     definition.get("targets"), definition.get("description")]
            options.append("\n".join(filter(None, (heading, *notes))))
        if options:
            rows.append(row(label, "\n\n".join(options)))
    rules = values.get("special_rules")
    if isinstance(rules, (list, tuple)) and (descriptions_text := descriptions(
            (rule for rule in rules if isinstance(rule, str)), appendix.get("special_rules", ()))):
        rows.append(row("Special rule reference", descriptions_text))
    if orders := [order for order in records(appendix.get("command_orders"))
                  if {"name", "target", "description"} <= order.keys()]:
        rows.append(row("Army command orders", "\n\n".join(
            f"{order['name']} · {order['target']}\n{order['description']}" for order in orders)))
    for label, details in (("Other unit notes", catalog.get("unparsed_details")),
                           ("Army list notes", appendix.get("unparsed_lines"))):
        if isinstance(details, (list, tuple)) and details:
            rows.append(row(label, "\n".join(map(str, details))))
    return summary, rows


def _step_start_corners_mm(event, scene):
    if not isinstance(event, Mapping):
        return None
    start = event.get("start")
    end = event.get("end")
    if not isinstance(start, Mapping) or not isinstance(end, Mapping):
        return None
    board = scene.get("calibration", {}).get("board", {})
    matrix = board.get("source_to_plane")
    corners = None
    compatible = (
        matrix is not None
        and start.get("corners_source") is not None
        and list(start.get("source_image_size") or ()) == list(end.get("source_image_size") or ())
        and start.get("source", {}).get("video") == end.get("source", {}).get("video")
    )
    if compatible:
        try:
            corners = transform_points(np.asarray(start["corners_source"], dtype=float), np.asarray(matrix, dtype=float))
        except (TypeError, ValueError):
            corners = None
    if corners is None:
        corners = start.get("corners_mm")
    try:
        arr = np.asarray(corners, dtype=float)
    except (TypeError, ValueError):
        return None
    if arr.shape != (4, 2) or not np.isfinite(arr).all():
        return None
    return arr


def _draw_rotation_cue(canvas, start_poly, end_poly, rot_deg, scale):
    center = end_poly.mean(axis=0)
    cx, cy = int(round(center[0])), int(round(center[1]))
    edges = np.roll(start_poly, -1, axis=0)[:2] - start_poly[:2]
    lengths = np.linalg.norm(edges, axis=1)
    edge = edges[int(np.argmax(lengths))]
    theta0 = math.degrees(math.atan2(edge[1], edge[0]))
    sweep = float(rot_deg) if isinstance(rot_deg, (int, float)) and math.isfinite(rot_deg) else 0.0
    diag = float(np.linalg.norm(end_poly[2] - end_poly[0]))
    radius = max(round(38 * scale), min(round(68 * scale), int(round(diag * 0.75))))

    # Radial reference spokes from center along start & end axis
    r_inner = max(round(12 * scale), int(round(diag * 0.30)))
    for ang, col, thick in ((theta0, (245, 232, 200), max(1, round(1.4 * scale))),
                            (theta0 + sweep, _SELECTION_BGR, max(2, round(2.0 * scale)))):
        rad = math.radians(ang)
        p0 = (int(round(cx + r_inner * math.cos(rad))), int(round(cy + r_inner * math.sin(rad))))
        p1 = (int(round(cx + (radius + round(8 * scale)) * math.cos(rad))),
              int(round(cy + (radius + round(8 * scale)) * math.sin(rad))))
        cv2.line(canvas, p0, p1, (26, 20, 12), thick + 2, cv2.LINE_AA)
        cv2.line(canvas, p0, p1, col, thick, cv2.LINE_AA)

    if abs(sweep) >= 1.0:
        start_a, end_a = (theta0, theta0 + sweep) if sweep > 0 else (theta0 + sweep, theta0)
        cv2.ellipse(canvas, (cx, cy), (radius, radius), 0, start_a, end_a, (26, 20, 12), max(4, round(4.4 * scale)), cv2.LINE_AA)
        cv2.ellipse(canvas, (cx, cy), (radius, radius), 0, start_a, end_a, _SELECTION_BGR, max(2, round(2.4 * scale)), cv2.LINE_AA)
        tip_rad = math.radians(theta0 + sweep)
        tang = tip_rad + (math.pi / 2 if sweep > 0 else -math.pi / 2)
        tx, ty = cx + radius * math.cos(tip_rad), cy + radius * math.sin(tip_rad)
        tail = (int(round(tx - 12 * scale * math.cos(tang))), int(round(ty - 12 * scale * math.sin(tang))))
        head = (int(round(tx + 3 * scale * math.cos(tang))), int(round(ty + 3 * scale * math.sin(tang))))
        cv2.arrowedLine(canvas, tail, head, (26, 20, 12), max(4, round(4.4 * scale)), cv2.LINE_AA, tipLength=0.65)
        cv2.arrowedLine(canvas, tail, head, _SELECTION_BGR, max(2, round(2.4 * scale)), cv2.LINE_AA, tipLength=0.65)
    return radius


def _replay_board(state, replay, preview_size, *, trays=True, labels=True):
    width = max(320, int(preview_size[0]))
    height = max(220, int(preview_size[1]))
    panel = np.full((height, width, 3), (19, 14, 9), dtype=np.uint8)
    scene = replay.scene
    if scene is None:
        return panel, []

    dimensions = np.asarray(scene["board_size_mm"], dtype=float)
    margin_x, margin_y = 14, 14
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
        board = np.full((int(board_h), int(board_w), 3), (38, 32, 26), dtype=np.uint8)
        step_px = max(24, int(round(150.0 * scale)))
        for gx in range(step_px, int(board_w), step_px):
            cv2.line(board, (gx, 0), (gx, int(board_h)), (52, 44, 36), 1)
        for gy in range(step_px, int(board_h), step_px):
            cv2.line(board, (0, gy), (int(board_w), gy), (52, 44, 36), 1)

    step = scene["step"]
    highlight = step["unit_id"]
    event = step.get("event")
    draw_scale = max(1.0, height / 720.0)
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
            front_edge = unit.get("front_edge")
            valid.append((unit_id, side, front_edge, np.rint(points * scale).astype(np.int32)))

    occ = np.zeros((height, width), np.uint8)
    end_active_poly = None
    if trays:
        overlay = board.copy()
        # Translucent 13% tray fill so miniatures underneath remain crisp and visible
        for unit_id, side, _, polygon in valid:
            is_active = unit_id == highlight
            fill_bgr = _SELECTION_BGR if is_active else (_SIDE_A_BGR[0] if side == "A" else _SIDE_B_BGR[0])
            cv2.fillPoly(overlay, [polygon], fill_bgr)
        cv2.addWeighted(overlay, 0.13, board, 0.87, 0, board)

        # Extra subtle tint for the highlighted step unit
        for unit_id, _, _, polygon in valid:
            if unit_id == highlight:
                hi = board.copy()
                cv2.fillPoly(hi, [polygon], _SELECTION_BGR)
                cv2.addWeighted(hi, 0.10, board, 0.90, 0, board)
                break

    for unit_id, side, front_edge, polygon in valid:
        is_active = unit_id == highlight
        panel_poly = polygon + np.array([origin_x, origin_y], dtype=np.int32)
        cv2.fillPoly(occ, [panel_poly], 1)
        if not trays:
            continue
        stroke_bgr = _SELECTION_BGR if is_active else (_SIDE_A_BGR[0] if side == "A" else _SIDE_B_BGR[0])
        if is_active:
            end_active_poly = polygon.astype(float)
            cv2.polylines(board, [polygon], True, (26, 20, 12), max(4, round(4.8 * draw_scale)), cv2.LINE_AA)
            cv2.polylines(board, [polygon], True, stroke_bgr, max(2, round(2.6 * draw_scale)), cv2.LINE_AA)
            bx0, by0 = int(polygon[:, 0].min()), int(polygon[:, 1].min())
            bx1, by1 = int(polygon[:, 0].max()), int(polygon[:, 1].max())
            pad = max(3, round(4 * draw_scale))
            draw_corner_brackets(
                board,
                max(2, bx0 - pad), max(2, by0 - pad),
                min(int(board_w) - 3, bx1 + pad), min(int(board_h) - 3, by1 + pad),
                (255, 255, 255), max(2, round(2.2 * draw_scale)), round(12 * draw_scale),
            )
        else:
            cv2.polylines(board, [polygon], True, (26, 20, 12), max(3, round(3.4 * draw_scale)), cv2.LINE_AA)
            cv2.polylines(board, [polygon], True, stroke_bgr, max(1, round(1.8 * draw_scale)), cv2.LINE_AA)
        if isinstance(front_edge, int) and 0 <= front_edge < 4:
            p0 = tuple(polygon[front_edge])
            p1 = tuple(polygon[(front_edge + 1) % 4])
            cv2.line(board, p0, p1, (255, 255, 255), max(2, round(2.4 * draw_scale)), cv2.LINE_AA)

    # Render start ghost + motion trajectory / rotation arc for Move & Rotate steps
    start_corners_mm = _step_start_corners_mm(event, scene) if trays else None
    if trays and event is not None and start_corners_mm is not None and end_active_poly is not None:
        start_poly = start_corners_mm * scale
        start_int = np.rint(start_poly).astype(np.int32)
        cv2.fillPoly(occ, [start_int + np.array([origin_x, origin_y], dtype=np.int32)], 1)
        _draw_dashed_poly(board, start_poly, (245, 232, 200), thickness=max(1, round(1.6 * draw_scale)))
        if event.get("kind") == "translation":
            sc = start_poly.mean(axis=0)
            ec = end_active_poly.mean(axis=0)
            sc_i = (int(round(sc[0])), int(round(sc[1])))
            ec_i = (int(round(ec[0])), int(round(ec[1])))
            cv2.circle(board, sc_i, max(4, round(4.5 * draw_scale)), (26, 20, 12), -1, cv2.LINE_AA)
            cv2.circle(board, sc_i, max(3, round(3.2 * draw_scale)), (245, 232, 200), 2, cv2.LINE_AA)
            dist_px = float(np.hypot(ec[0] - sc[0], ec[1] - sc[1]))
            if dist_px > 6.0:
                tip = max(0.14, min(0.32, 14.0 * draw_scale / dist_px))
                cv2.arrowedLine(board, sc_i, ec_i, (26, 20, 12), max(4, round(4.5 * draw_scale)), cv2.LINE_AA, tipLength=tip)
                cv2.arrowedLine(board, sc_i, ec_i, _SELECTION_BGR, max(2, round(2.4 * draw_scale)), cv2.LINE_AA, tipLength=tip)
                cv2.line(occ, (sc_i[0] + origin_x, sc_i[1] + origin_y), (ec_i[0] + origin_x, ec_i[1] + origin_y), 1, max(8, round(10 * draw_scale)))
        elif event.get("kind") == "rotation":
            arc_r = _draw_rotation_cue(board, start_poly, end_active_poly, event.get("rotation_deg_estimate"), draw_scale)
            ec = end_active_poly.mean(axis=0)
            cv2.circle(occ, (int(round(ec[0])) + origin_x, int(round(ec[1])) + origin_y), int(arc_r * 0.8), 1, -1)

    cv2.rectangle(board, (0, 0), (int(board_w) - 1, int(board_h) - 1), (96, 78, 62), 1)
    panel[origin_y:origin_y + int(board_h), origin_x:origin_x + int(board_w)] = board

    if not labels:
        return panel, []

    # Place non-overlapping capsule labels using the shared integral occupancy solver
    entries = []
    for idx, (unit_id, side, _, polygon) in enumerate(valid):
        is_active = unit_id == highlight
        px0 = max(0, int(polygon[:, 0].min()) + origin_x)
        py0 = max(0, int(polygon[:, 1].min()) + origin_y)
        px1 = min(width, int(polygon[:, 0].max()) + 1 + origin_x)
        py1 = min(height, int(polygon[:, 1].max()) + 1 + origin_y)
        unit_box = (px0, py0, px1, py1)
        area = max(1, (px1 - px0) * (py1 - py0))
        dot = _SIDE_A_BGR[0] if side == "A" else _SIDE_B_BGR[0]
        border_bgr = _SELECTION_BGR if is_active else dot
        entries.append((area, unit_box, unit_badge_label(state, unit_id), dot, border_bgr, idx, is_active))

    placed = place_badges(entries, occ, width, height, draw_scale)
    badges = []
    for box, entry, dist in placed:
        _, unit_box, label, dot, border_bgr, idx, is_active = entry
        unit_id = valid[idx][0]
        if dist > round(9 * draw_scale):
            p_lbl, p_unit = nearest_rect_points(box, unit_box)
            cv2.line(panel, p_lbl, p_unit, (26, 20, 12), max(3, round(3.0 * draw_scale)), cv2.LINE_AA)
            cv2.line(panel, p_lbl, p_unit, border_bgr, max(1, round(1.5 * draw_scale)), cv2.LINE_AA)
            cv2.circle(panel, p_unit, max(3, round(3.2 * draw_scale)), (247, 243, 237), -1, cv2.LINE_AA)
        badges.append(_badge_dict(
            box, width, height, label, dot, border_bgr,
            kind="unit", unit_id=unit_id, active=is_active,
        ))
    return panel, badges


def _step_summary_text(step):
    if step is None:
        return ""
    event = step.get("event")
    if event is None:
        return "Baseline snapshot"
    if event.get("kind") == "translation":
        disp = event.get("net_displacement_mm")
        if isinstance(disp, (int, float)) and math.isfinite(disp):
            return f"{disp / 25.4:.2f} in · {disp:.1f} mm"
    elif event.get("kind") == "rotation":
        deg = event.get("rotation_deg_estimate")
        if isinstance(deg, (int, float)) and math.isfinite(deg):
            return f"{deg:+.1f}°"
    return ""


def _terrain_row(state, item):
    tid = str(item.get("terrain_id") or "")
    kind = str(item.get("kind") or "blocking")
    label = str(item.get("label") or tid or "Terrain")
    height = item.get("height")
    is_obstacle = kind == "obstacle"
    height_text = "1 (fixed)" if is_obstacle else (f"{height:g}" if isinstance(height, (int, float)) else "—")
    height_raw = "1" if is_obstacle else ("" if height is None else f"{height:g}")
    bgr = _TERRAIN_KIND_BGR.get(kind, (162, 174, 184))

    frame_h, frame_w = state.current.frame.shape[:2]
    matrix = state.board.homography["matrix"] if state.board.homography is not None else None
    if item.get("polygon_source") is not None and matrix is not None:
        poly_img = transform_points(item["polygon_source"], matrix)
    elif item.get("polygon_image") is not None:
        poly_img = np.asarray(item["polygon_image"], dtype=float)
    else:
        poly_img = np.empty((0, 2), dtype=float)
    vertices = int(len(poly_img))
    if vertices >= 3 and np.isfinite(poly_img).all():
        center = poly_img.mean(axis=0)
        cx = float(np.clip(center[0] / max(1, frame_w), 0.02, 0.98))
        cy = float(np.clip(center[1] / max(1, frame_h), 0.02, 0.98))
    else:
        cx, cy = 0.5, 0.5

    area_text = f"{vertices} vertices"
    try:
        if item.get("polygon_source") is not None and state.board.source_to_plane is not None:
            pts_mm = transform_points(item["polygon_source"], state.board.source_to_plane)
        elif item.get("polygon_image") is not None and state.board.image_to_plane is not None:
            pts_mm = transform_points(item["polygon_image"], state.board.image_to_plane)
        else:
            pts_mm = None
        if pts_mm is not None and len(pts_mm) >= 3 and np.isfinite(pts_mm).all():
            xs, ys = pts_mm[:, 0], pts_mm[:, 1]
            area_mm2 = 0.5 * abs(float(np.dot(xs, np.roll(ys, -1)) - np.dot(ys, np.roll(xs, -1))))
            if area_mm2 > 0:
                area_in2 = area_mm2 / (25.4 * 25.4)
                area_text = f"{vertices} pts · {area_in2:.1f} sq in"
    except (TypeError, ValueError):
        pass

    return dict(
        id=tid,
        label=label,
        kind=kind,
        kindLabel=kind.title(),
        heightText=height_text,
        heightRaw=height_raw,
        color=_bgr_hex(bgr),
        vertices=vertices,
        areaText=area_text,
        centerX=cx,
        centerY=cy,
    )


class Workflows(QObject):
    changed = Signal()
    recoveryRowsChanged = Signal()
    replayStepsChanged = Signal()
    terrainRowsChanged = Signal()
    terrainLoaded = Signal()
    formRequested = Signal()
    profileLoaded = Signal()

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge, self.match = bridge, bridge.match
        self.mode = "live"
        self.points = []
        self.recovery_tool = "Points"
        self.recovery_vertices = []
        self._recovery_target = ""
        self._recovery_hover = False
        self._recovery_rows = []
        self._replay_steps = []
        self._replay_steps_key = None
        self._terrain_rows = []
        self._selected_terrain_id = ""
        self._terrain_info_open = False
        self._terrain_card_anchor = (0.35, 0.5)
        self._reference = None
        self._fields = []
        self._form_kind = self._unit_id = ""
        self._profile_open = False
        self._form_error = ""
        self._debug_note = ""
        self._data = dict(
            kind="live", rows=[], note="", busy=False, review=False,
            reviewUnitId="", targetUnitId="", hasCandidate=False, canConfirmTarget=False,
            tool="Points", quadVertices=[],
            candidateGeneration=0, candidateTime="—", pointCount=0,
            step=0, steps=0, calibrationPending=False,
            profileOpen=False, profileUnitId="",
            selectedTerrainId="", terrainInfoOpen=False, selectedTerrain={},
            terrainCenterX=0.5, terrainCenterY=0.5, terrainCardX=0.35, terrainCardY=0.5,
            replayInfo=dict(stepText="", stepLabel="", stepUnit="", stepKind="", stepSide="",
                            stepSummary="", endTime="—", firstTime="—", lastTime="—",
                            observedTime="—", recordedTime="—",
                            calibrationVersion="—", unavailable="", unavailableCount=0,
                            backgroundNote="", boardDimensions="",
                            loading=False, error="", hasIndex=False),
        )
        self._replay_key = self._replay_image = None
        self.replay_badges = []

    @Property("QVariantMap", notify=changed)
    def state(self):
        return self._data

    @Property("QVariantList", notify=recoveryRowsChanged)
    def recoveryRows(self):
        return self._recovery_rows

    @Property("QVariantList", notify=replayStepsChanged)
    def replaySteps(self):
        return self._replay_steps

    @Property("QVariantList", notify=terrainRowsChanged)
    def terrainRows(self):
        return self._terrain_rows

    @property
    def selected_terrain_id(self):
        return self._selected_terrain_id

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

    @staticmethod
    def _build_fields(rows):
        return [
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

    def _load_profile(self, state, uid):
        unit = state.units.units.get(uid)
        if unit is None:
            return False
        catalog = state.units.types[unit["type_id"]]
        values = {**catalog.get("attributes", {}), **unit["attributes"]}
        summary, reference = _catalog_rows(state.units, catalog, values)
        self._unit_id, self._reference, self._form_kind = uid, state.source_ref, "profile"
        self._fields = self._build_fields(summary + [
            ("speed_in", "Speed (inches)", values.get("speed_in"), "number", None),
            ("height", "Rule height", values.get("height"), "number", None),
            ("side", "Side / army", values.get("side"), "text", None),
            ("unit_kind", "Unit kind", values.get("unit_kind"), "choice",
             [("", "Unknown / Unset"), ("ordinary", "Ordinary"),
              ("war_engine", "War Engine"), ("individual", "Individual")]),
            ("special_rules", "Special rules (comma separated)", values.get("special_rules"), "rules", None),
            ("engaged", "Currently engaged", values.get("engaged"), "bool", None),
            ("wavering", "Currently wavering", values.get("wavering"), "bool", None),
        ] + reference)
        self.profileLoaded.emit()
        return True

    @Slot()
    def closeProfile(self):
        if self._profile_open or self._form_error:
            self._profile_open = False
            self._form_error = ""
            self.refresh()

    @staticmethod
    def _place_terrain_card(cx, cy):
        card_x = cx - 0.16 if cx > 0.30 else cx + 0.16
        return (float(np.clip(card_x, 0.12, 0.88)), float(np.clip(cy, 0.14, 0.86)))

    def publish(self, state, calibration):
        recovery, replay = state.recovery, self.match.replay
        if self.mode == "recalibrate" and calibration is None:
            self.mode, self.points = "live", []
        if state.stage != "register" or state.registration_locked:
            if self.mode == "terrain":
                self.mode, self.points, self._form_error = "live", [], ""
            self._selected_terrain_id = ""
            self._terrain_info_open = False
        kind = self.kind(state)
        if kind != "recovery":
            self.recovery_vertices.clear()
            self._recovery_hover = False
            self._recovery_target = ""
        if self._profile_open:
            uid = self.bridge.live.unit_id
            if state.stage != "playback" or kind != "live" or not uid or uid not in state.units.units:
                self._profile_open = False
            elif uid != self._unit_id:
                self._form_error = ""
                self._load_profile(state, uid)

        terrain_rows = (
            [_terrain_row(state, item) for item in state.rules.terrain]
            if state.stage == "register" and state.board.homography is not None else []
        )
        if terrain_rows != self._terrain_rows:
            self._terrain_rows = terrain_rows
            self.terrainRowsChanged.emit()
        selected_terrain = next((row for row in terrain_rows if row["id"] == self._selected_terrain_id), None)
        if self._selected_terrain_id and selected_terrain is None:
            self._selected_terrain_id = ""
            self._terrain_info_open = False

        labels = list(recovery["labels"])
        if self._recovery_target and self._recovery_target not in labels:
            self._recovery_target = ""
        target_uid = self._recovery_target or (labels[0] if len(labels) == 1 else "")
        rows = []
        for uid in labels:
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
                name=catalog.get("unit_name") or catalog.get("name") or catalog.get("classification") or unit["type_id"],
                subtitle=catalog.get("classification") or catalog.get("formation") or "",
                status=status,
            ))
        if rows != self._recovery_rows:
            self._recovery_rows = rows
            self.recoveryRowsChanged.emit()

        replay_steps_key = (
            (replay.epoch, replay.steps,
             tuple((uid, unit_list_side(state, uid, default="")) for uid in state.units.units))
            if kind == "replay" else None
        )
        if replay_steps_key != self._replay_steps_key:
            self._replay_steps_key = replay_steps_key
            timeline = []
            if kind == "replay" and replay.steps:
                for idx, entry in enumerate(replay.steps):
                    u_id = entry.get("unit_id") or ""
                    u_side = unit_list_side(state, u_id, default="")
                    timeline.append(dict(
                        index=idx,
                        kind=entry["kind"],
                        label=entry["label"],
                        unit=u_id,
                        side=u_side,
                        time=f"{entry['end_timestamp_seconds']:.1f}s",
                        summary=_step_summary_text(entry),
                    ))
            if timeline != self._replay_steps:
                self._replay_steps = timeline
                self.replayStepsChanged.emit()

        note = recovery["note"] if kind == "recovery" else replay.error if kind == "replay" else state.note
        if kind == "debug":
            note = self._debug_note
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

        step_unit = (step.get("unit_id") or "") if step else ""
        step_side = ""
        if step_unit and step_unit in state.units.units:
            step_type = state.units.units[step_unit]["type_id"]
            step_side = state.units.types.get(step_type, {}).get("list_id", "")
        step_summary = _step_summary_text(step)

        replay_info = dict(
            stepText=(f"Step {replay.selected} / {len(replay.steps) - 1}" if replay.steps
                      else "Loading history…" if replay.loading else "No steps"),
            stepLabel=step["label"] if step else "",
            stepUnit=step_unit,
            stepKind=step["kind"] if step else "",
            stepSide=step_side,
            stepSummary=step_summary,
            endTime=f"{step['end_timestamp_seconds']:.2f}s" if step else "—",
            firstTime=f"{replay.steps[0]['end_timestamp_seconds']:.1f}s" if replay.steps else "—",
            lastTime=f"{replay.steps[-1]['end_timestamp_seconds']:.1f}s" if replay.steps else "—",
            observedTime=observed_time,
            recordedTime=recorded_time,
            calibrationVersion=calib_ver,
            unavailable=", ".join(unavailable),
            unavailableCount=len(unavailable),
            backgroundNote=bg_note,
            boardDimensions=dimensions,
            loading=replay.loading,
            hasIndex=replay.has_index,
            error=replay.error or "",
        )
        if kind == "replay" and step is not None:
            note = f"Step {replay.selected}: {step['label']} | " + (note or "")

        candidate = recovery["preview"]
        has_candidate = bool(candidate is not None and candidate["prediction"]["masks"][0].any())
        busy = recovery["busy"] or recovery["committing"]
        review = recovery["review_unit_id"] is not None
        view = dict(
            kind=kind,
            rows=rows,
            note=note,
            busy=busy,
            review=review,
            reviewUnitId=recovery["review_unit_id"] or "",
            targetUnitId=target_uid,
            hasCandidate=has_candidate,
            canConfirmTarget=bool(has_candidate and not review and target_uid and not busy),
            tool=self.recovery_tool,
            quadVertices=self.recovery_vertices.copy(),
            candidateGeneration=recovery["candidate_generation"],
            candidateTime=(f"{candidate['metadata']['timestamp_seconds']:.2f}s" if candidate else "—"),
            pointCount=len(self.points),
            step=replay.selected,
            steps=len(replay.steps),
            calibrationPending=bool(calibration and (calibration["pending"] or calibration["draft"])),
            profileOpen=self._profile_open,
            profileUnitId=self._unit_id,
            selectedTerrainId=self._selected_terrain_id,
            terrainInfoOpen=self._terrain_info_open,
            selectedTerrain=selected_terrain or {},
            terrainCenterX=selected_terrain["centerX"] if selected_terrain else 0.5,
            terrainCenterY=selected_terrain["centerY"] if selected_terrain else 0.5,
            terrainCardX=float(self._terrain_card_anchor[0]),
            terrainCardY=float(self._terrain_card_anchor[1]),
            replayInfo=replay_info,
        )
        if kind != "replay" or view != self._data:
            self._data = view
            self.changed.emit()

    def refresh(self, receipt=None):
        return self.bridge._refresh(receipt)

    @Slot(str)
    def open(self, tool):
        if self.bridge._closed:
            return
        state = self.match.snapshot()
        if tool == "terrain":
            if state.stage != "register" or state.registration_locked or state.board.homography is None:
                return
            self.bridge._manual_vertices.clear()
            self.mode, self.points, self._reference = "terrain", [], state.source_ref
            self._form_error = ""
            self.refresh()
            return
        if state.stage != "playback" or state.recovery["committing"]:
            return
        if self.mode == "debug":
            return
        if tool == "debug":
            if self.kind(state) != "live":
                return
            receipt = self.match.pause_debug()
            if receipt.status == "accepted":
                self.bridge.live.done()
                self.mode = "debug"
                self._debug_note = "Video paused. Save the current frame, masks, trays and tracking state."
            self.refresh(receipt)
            return
        if tool == "profile":
            uid = self.bridge.live.unit_id
            if uid is None or uid not in state.units.units:
                return
            self._profile_open = True
            self._form_error = ""
            self._load_profile(state, uid)
            self.refresh()
            return
        if self.mode == "recalibrate":
            self.match.calibration.cancel_recalibration()
        self.match.recovery.cancel()
        self.match.replay.clear()
        self.bridge.live.done()
        self.mode, self.points = "live", []
        if tool in ("correct", "recover"):
            uid = self.bridge.live.unit_id if tool == "correct" else None
            self.recovery_tool = "Points"
            self.recovery_vertices.clear()
            self._recovery_hover = False
            self._recovery_target = uid or ""
            receipt = self.match.recovery.open(uid, manual=tool == "correct")
            self.refresh(receipt)
        elif tool == "recalibrate":
            receipt = self.match.calibration.begin_recalibration()
            if receipt.status != "rejected":
                self.mode = "recalibrate"
            self.refresh(receipt)
        elif tool == "replay":
            self.refresh(self.match.replay.open())

    def show_form(self, kind, rows):
        self._form_kind = kind
        self._form_error = ""
        self._fields = self._build_fields(rows)
        self.changed.emit()
        self.formRequested.emit()

    @Slot("QVariantList", result=bool)
    def saveForm(self, rows):
        values = {}
        try:
            for row in rows:
                if row["kind"] == "readonly":
                    continue
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
                self.points = []
                state = self.match.snapshot()
                self._reference = state.source_ref
                self.match.set_note(
                    f"Terrain saved ({len(state.rules.terrain)} total). Click vertices for another polygon, or press Esc / Done."
                )

        if receipt.status == "rejected":
            self._form_error = receipt.reason
            self.changed.emit()
            return False

        self._form_error = ""
        if self._form_kind == "profile" and self._profile_open:
            self._load_profile(self.match.snapshot(), self._unit_id)
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

    @Slot(int)
    def selectReplayStep(self, index):
        if self.bridge._closed:
            return
        if self.match.replay.active:
            self.refresh(self.match.replay.select(int(index)))

    @Slot(str)
    @Slot(str, bool)
    @Slot(str, bool, float, float)
    def selectTerrain(self, terrain_id, open_info=False, anchor_x=-1.0, anchor_y=-1.0):
        if self.bridge._closed:
            return
        state = self.match.snapshot()
        if state.stage != "register" or state.registration_locked:
            return
        item = next((t for t in state.rules.terrain if t.get("terrain_id") == terrain_id), None)
        if item is None:
            return
        row = _terrain_row(state, item)
        self._selected_terrain_id = terrain_id
        if open_info:
            self._terrain_info_open = True
        cx = row["centerX"] if anchor_x < 0 else float(np.clip(anchor_x, 0.02, 0.98))
        cy = row["centerY"] if anchor_y < 0 else float(np.clip(anchor_y, 0.02, 0.98))
        self._terrain_card_anchor = self._place_terrain_card(cx, cy)
        self._form_error = ""
        self.refresh()
        self.terrainLoaded.emit()

    @Slot()
    @Slot(str)
    def openTerrainInfo(self, terrain_id=""):
        if self.bridge._closed:
            return
        state = self.match.snapshot()
        if state.stage != "register" or state.registration_locked:
            return
        tid = terrain_id or self._selected_terrain_id
        if not tid:
            return
        if not any(t.get("terrain_id") == tid for t in state.rules.terrain):
            return
        if tid != self._selected_terrain_id:
            self.selectTerrain(tid, True)
            return
        self._terrain_info_open = not self._terrain_info_open if not terrain_id else True
        self._form_error = ""
        self.refresh()
        if self._terrain_info_open:
            self.terrainLoaded.emit()

    @Slot()
    def closeTerrainInfo(self):
        if self.bridge._closed:
            return
        changed = False
        if self.mode == "terrain":
            if self._selected_terrain_id or self._terrain_info_open or self._form_error:
                self._selected_terrain_id = ""
                self._terrain_info_open = False
                self._form_error = ""
                changed = True
        elif self._terrain_info_open or self._form_error:
            self._terrain_info_open = False
            self._form_error = ""
            changed = True
        if changed:
            self.refresh()

    @Slot()
    def clearTerrainSelection(self):
        if self._selected_terrain_id or self._terrain_info_open or self._form_error:
            self._selected_terrain_id = ""
            self._terrain_info_open = False
            self._form_error = ""
            self.refresh()

    @Slot(float, float)
    def moveTerrainCard(self, x, y):
        if not self.bridge._closed:
            self._terrain_card_anchor = (float(np.clip(x, 0.04, 0.96)), float(np.clip(y, 0.04, 0.96)))
            self.refresh()

    @Slot(str, str, str, str, result=bool)
    def saveTerrainEdit(self, terrain_id, label, kind, height_text):
        if self.bridge._closed:
            return False
        state = self.match.snapshot()
        try:
            clean_label = str(label or "").strip()
            if not clean_label:
                raise ValueError("Enter a terrain label.")
            clean_kind = str(kind or "").strip() or "blocking"
            values = {"label": clean_label, "kind": clean_kind}
            if clean_kind != "obstacle":
                raw_h = str(height_text if height_text is not None else "").strip()
                if raw_h == "":
                    values["height"] = None
                else:
                    h_val = float(raw_h)
                    if not math.isfinite(h_val) or h_val < 0:
                        raise ValueError("Enter a finite, non-negative height, or leave unknown values empty.")
                    values["height"] = h_val
        except ValueError as error:
            self._form_error = str(error)
            self.changed.emit()
            return False
        receipt = self.match.scene_editing.update_terrain(terrain_id, values, state.source_ref)
        if receipt.status == "rejected":
            self._form_error = receipt.reason
            self.changed.emit()
            return False
        self._form_error = ""
        self.match.set_note(f"Updated terrain {clean_label} ({terrain_id}).")
        self.refresh(receipt)
        self.terrainLoaded.emit()
        return True

    @Slot(str, result=bool)
    def deleteTerrain(self, terrain_id):
        if self.bridge._closed:
            return False
        state = self.match.snapshot()
        receipt = self.match.scene_editing.delete_terrain(terrain_id, state.source_ref)
        if receipt.status == "rejected":
            self._form_error = receipt.reason
            self.changed.emit()
            return False
        if self._selected_terrain_id == terrain_id:
            self._selected_terrain_id = ""
            self._terrain_info_open = False
        self._form_error = ""
        self.match.set_note(f"Removed terrain {terrain_id}.")
        self.refresh(receipt)
        return True

    @Slot(str)
    def action(self, action):
        if self.bridge._closed:
            return
        if self.mode == "debug":
            if action == "saveDebug":
                receipt = self.match.save_debug()
                if receipt.status == "accepted":
                    self._debug_note = f"Saved snapshot: {receipt.value}"
                self.refresh(receipt)
            elif action == "cancel":
                receipt = self.match.resume_debug()
                self.mode = "live"
                self.refresh(receipt)
            return
        if action == "undoTerrain":
            self.refresh(self.match.scene_editing.undo_terrain())
        elif action == "cancel":
            if self.match.snapshot().recovery["committing"]:
                return
            self.match.recovery.cancel()
            self.match.replay.clear()
            self.match.calibration.cancel_recalibration()
            self.mode, self.points = "live", []
            self._selected_terrain_id = ""
            self._terrain_info_open = False
            self.recovery_vertices.clear()
            self._recovery_hover = False
            self._recovery_target = ""
            self._form_error = ""
            self.refresh()
        elif action == "clear":
            self.recovery_vertices.clear()
            self._recovery_hover = False
            self.refresh(self.match.recovery.clear_candidate())
        elif action == "correct":
            state = self.bridge._shown
            self.refresh(self.match.recovery.bind(state.recovery["review_unit_id"], state.recovery["candidate_generation"]))
        elif action == "reject":
            self.recovery_vertices.clear()
            self._recovery_hover = False
            self.refresh(self.match.recovery.reject())
        elif action == "refresh":
            self.refresh(self.match.replay.refresh())
        elif action in ("previous", "next"):
            self.refresh(self.match.replay.navigate(-1 if action == "previous" else 1))

    @Slot(str)
    def setRecoveryTool(self, tool):
        if not self.bridge._closed and tool in ("Points", "Rectangle", "Quad"):
            if tool != self.recovery_tool:
                self.recovery_vertices.clear()
            self.recovery_tool = tool
            self.refresh()

    @Slot()
    def undoRecoveryVertex(self):
        if not self.bridge._closed and self.recovery_vertices:
            self.recovery_vertices.pop()
            self.refresh()

    @Slot(float, float, float, float)
    def drawRecoveryRectangle(self, x0, y0, x1, y1):
        if self.bridge._closed or self.recovery_tool != "Rectangle":
            return
        state = self.bridge._shown or self.match.snapshot()
        if self.kind(state) != "recovery" or state.recovery["busy"] or state.recovery["committing"]:
            return
        width, height = self.bridge._display_size
        left, right = sorted((min(max(x0, 0), width - 1), min(max(x1, 0), width - 1)))
        top, bottom = sorted((min(max(y0, 0), height - 1), min(max(y1, 0), height - 1)))
        receipt = self.match.recovery.manual_mask([[left, top], [right, top], [right, bottom], [left, bottom]], state.source_ref)
        if receipt.status != "rejected":
            self.recovery_vertices.clear()
            self._recovery_hover = False
        self.refresh(receipt)

    @Slot()
    def confirmTarget(self):
        if self.bridge._closed:
            return
        state = self.match.snapshot()
        target = self._data.get("targetUnitId") or ""
        if self.kind(state) == "recovery" and target:
            self.refresh(self.match.recovery.bind(target, state.recovery["candidate_generation"]))

    @Slot(str)
    def selectCandidate(self, uid):
        if self.bridge._closed:
            return
        state = self.match.snapshot()
        rec = state.recovery
        if self.kind(state) != "recovery" or rec["busy"] or rec["committing"]:
            return
        preview = rec["preview"]
        has_candidate = preview is not None and preview["prediction"]["masks"][0].any()
        if has_candidate and rec["review_unit_id"] is None:
            self._recovery_hover = False
            self.refresh(self.match.recovery.bind(uid, rec["candidate_generation"]))
            return
        if uid != rec["review_unit_id"]:
            receipt = self.match.recovery.select_unit(uid)
            if receipt.status != "rejected":
                self._recovery_target = uid
                self.recovery_vertices.clear()
                self._recovery_hover = False
                self.refresh(receipt)
                return
        self._recovery_target = uid
        self.bridge.notice = (
            f"Reviewing {uid}: click Correct to confirm, No to search again, or redraw."
            if uid == rec["review_unit_id"]
            else f"Target {uid} selected. Use Points, Rectangle, or Four corners to draw a mask, then click or drag {uid} to confirm."
        )
        self.bridge._local_revision += 1
        self.bridge._publish()

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
        return self.refresh(receipt)

    def click(self, x, y, positive, state):
        kind = self.kind(state)
        if kind == "live":
            return False
        if kind == "recalibrate" and not self._data["calibrationPending"]:
            if positive and len(self.points) < 4:
                self.points.append([x, y])
            elif not positive and self.points:
                self.points.pop()
            self.refresh()
        elif kind in ("recovery", "terrain"):
            if kind == "terrain" and (state.stage != "register" or state.registration_locked or state.board.homography is None):
                return False
            if kind == "recovery":
                if self.recovery_tool == "Quad":
                    if not positive:
                        if self.recovery_vertices:
                            self.recovery_vertices.pop()
                            self.refresh()
                        else:
                            self.bridge.notice = "Right-click removes unfinished corners. Use Clear / Retry to clear the candidate."
                            self.bridge._local_revision += 1
                            self.bridge._publish()
                        return True
                    vertices = [*self.recovery_vertices, [x, y]]
                    if len(vertices) == 4:
                        receipt = self.match.recovery.manual_mask(vertices, state.source_ref)
                        if receipt.status != "rejected":
                            self.recovery_vertices.clear()
                            self._recovery_hover = False
                        self.refresh(receipt)
                    else:
                        self.recovery_vertices = vertices
                        self.refresh()
                    return True
                if self.recovery_tool == "Rectangle":
                    if not positive:
                        self.bridge.notice = "Drag with the left button to draw a rectangle, or use Clear / Retry."
                        self.bridge._local_revision += 1
                        self.bridge._publish()
                    return True
                source = transform_points([x, y], state.board.homography["inverse_matrix"])
                self.refresh(self.match.recovery.point(source, positive, state.source_ref))
            else:
                source = transform_points([x, y], state.board.homography["inverse_matrix"])
                if positive:
                    self.points.append(source.tolist())
                elif self.points:
                    self.points.pop()
                self.refresh()
        return True

    @staticmethod
    def _hits_candidate(candidate, x, y, pad=8):
        if candidate is None:
            return False
        mask = candidate["prediction"]["masks"][0]
        h, w = mask.shape[:2]
        if not (0 <= y < h and 0 <= x < w):
            return False
        ix, iy = int(x), int(y)
        if mask[iy, ix]:
            return True
        x0, x1 = max(0, ix - pad), min(w, ix + pad + 1)
        y0, y1 = max(0, iy - pad), min(h, iy + pad + 1)
        return bool(mask[y0:y1, x0:x1].any())

    @Slot(float, float)
    def hoverRecovery(self, x, y):
        state = self.bridge._shown or self.match.snapshot()
        hit = self.kind(state) == "recovery" and self._hits_candidate(state.recovery["preview"], x, y)
        if hit != self._recovery_hover:
            self._recovery_hover = hit
            self.bridge._local_revision += 1
            self.bridge._publish()

    @Slot()
    def clearRecoveryHover(self):
        if self._recovery_hover:
            self._recovery_hover = False
            self.bridge._local_revision += 1
            self.bridge._publish()

    @Slot(str, float, float, int, int)
    def dropUnit(self, uid, x, y, revision, generation):
        self._recovery_hover = False
        state = self.bridge._shown or self.match.snapshot()
        candidate = state.recovery["preview"]
        if self.kind(state) != "recovery" or candidate is None:
            self.bridge.notice = "Draw a candidate mask first, then click or drag the unit ID."
            self.bridge._local_revision += 1
            self.bridge._publish()
            return
        if not self._hits_candidate(candidate, x, y):
            self.bridge.notice = "Drop the unit ID onto the yellow candidate mask, or click its card to confirm."
            self.bridge._local_revision += 1
            self.bridge._publish()
            return
        self.refresh(self.match.recovery.bind(uid, generation))

    def interactive_key(self, state):
        kind = self.kind(state)
        if kind == "recovery":
            candidate = state.recovery["preview"]
            return (kind, state.recovery["candidate_generation"], id(candidate), self._recovery_hover)
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
                    fill = (120, 210, 90, 82) if self._recovery_hover else (64, 208, 250, 72)
                    stroke = (153, 211, 54, 255) if self._recovery_hover else (72, 224, 255, 255)
                    rgba[y0:y1, x0:x1][sub != 0] = fill
                    contours, _ = cv2.findContours(sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE, offset=(x0, y0))
                    cv2.drawContours(rgba, contours, -1, (26, 20, 12, 240), max(4, round(4.4 * scale)), cv2.LINE_AA)
                    cv2.drawContours(rgba, contours, -1, stroke, max(2, round(2.4 * scale)), cv2.LINE_AA)
        if self.points and kind in ("terrain", "recalibrate"):
            if kind == "terrain" and state.board.homography is None:
                return
            points = np.asarray(self.points) if kind == "recalibrate" else transform_points(self.points, state.board.homography["matrix"])
            points = np.rint(points).astype(np.int32)
            line_bgra = (150, 218, 100, 255) if kind == "terrain" else (255, 232, 76, 255)
            if kind == "terrain" and len(points) >= 3:
                cv2.fillPoly(rgba, [points], (130, 212, 92, 34))
                cv2.line(rgba, tuple(points[-1]), tuple(points[0]), (28, 22, 14, 150), max(3, round(3.0 * scale)), cv2.LINE_AA)
                cv2.line(rgba, tuple(points[-1]), tuple(points[0]), (150, 218, 100, 170), max(1, round(1.5 * scale)), cv2.LINE_AA)
            if len(points) >= 2:
                cv2.polylines(rgba, [points], False, (28, 22, 14, 235), max(4, round(4.4 * scale)), cv2.LINE_AA)
                cv2.polylines(rgba, [points], False, line_bgra, max(2, round(2.2 * scale)), cv2.LINE_AA)
            node_r = max(10, round(11.0 * scale))
            font = _ui_font(max(13, round(14 * scale)), bold=True)
            height, width = rgba.shape[:2]
            for i, point in enumerate(points):
                px, py = int(point[0]), int(point[1])
                cv2.circle(rgba, (px, py), node_r + 2, (28, 22, 14, 245), -1, cv2.LINE_AA)
                cv2.circle(rgba, (px, py), node_r, line_bgra, -1, cv2.LINE_AA)
                label = str(i + 1)
                bbox = font.getbbox(label)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                x0 = max(0, px - node_r)
                y0 = max(0, py - node_r)
                x1 = min(width, x0 + node_r * 2)
                y1 = min(height, y0 + node_r * 2)
                if x1 > x0 and y1 > y0:
                    pil_roi = Image.fromarray(rgba[y0:y1, x0:x1], "RGBA")
                    ImageDraw.Draw(pil_roi).text(
                        ((x1 - x0 - tw) // 2 - bbox[0], (y1 - y0 - th) // 2 - bbox[1]),
                        label, font=font, fill=(28, 22, 14, 255),
                    )
                    rgba[y0:y1, x0:x1] = np.asarray(pil_roi)

    @property
    def replay_image_key(self):
        return self._replay_key

    def render_video(self, state, frame):
        kind = self.kind(state)
        if kind == "replay":
            height, width = frame.shape[:2]
            replay = self.match.replay
            scene = replay.scene
            observed = scene["observation"] if scene is not None else {}
            show_trays = bool(self.bridge.show_trays)
            show_labels = bool(self.bridge.show_labels)
            key = (
                replay.epoch, replay.selected, replay.has_index, scene is None, replay.error,
                replay.steps[replay.selected]["event_id"] if replay.steps else None,
                replay.steps[replay.selected]["end_sequence"] if replay.steps else None,
                observed.get("timestamp_seconds"), observed.get("observation_timestamp_seconds"),
                observed.get("calibration_version"), width, height, show_trays, show_labels,
                tuple((uid, unit_list_side(state, uid),
                       unit_badge_label(state, uid) if show_labels else "")
                      for uid in scene["units"]) if scene is not None else (),
            )
            if key != self._replay_key:
                self._replay_image, self.replay_badges = _replay_board(
                    state, replay, (width, height), trays=show_trays, labels=show_labels,
                )
                self._replay_key = key
            return self._replay_image
        if kind == "recalibrate":
            return state.source_image
        return frame
