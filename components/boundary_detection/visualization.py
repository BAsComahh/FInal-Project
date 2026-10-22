"""Overlays shared by batch exports and the interactive viewer."""

import cv2
import numpy as np


def draw_lines(image, lines, color, thickness=2):
    overlay = image.copy()
    for line in np.rint(lines).astype(int):
        cv2.line(overlay, tuple(map(int, line[:2])), tuple(map(int, line[2:])), color, thickness, cv2.LINE_AA)
    return overlay


def draw_border_lines(image, selected):
    overlay = image.copy()
    colors = {"top": (0, 0, 255), "bottom": (30, 210, 30),
              "left": (255, 150, 0), "right": (220, 40, 220)}
    height, width = image.shape[:2]
    for side, record in selected.items():
        if record is None:
            continue
        line = np.rint(record["line"]).astype(int)
        color = colors[side]
        cv2.line(overlay, tuple(map(int, line[:2])), tuple(map(int, line[2:])), color, 3, cv2.LINE_AA)
        center = ((line[:2] + line[2:]) / 2).astype(int)
        label = (max(5, min(width - 90, int(center[0]) + 8)),
                 max(20, min(height - 8, int(center[1]) - 8)))
        cv2.putText(overlay, side, label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(overlay, side, label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)
    return overlay


def draw_frame_connections(image, selected, frame):
    segments = [record["line"] for record in selected.values() if record is not None]
    junction_overlay = draw_lines(image, np.asarray(segments).reshape(-1, 4), (170, 170, 170))
    for junction in frame["junctions"]:
        if not junction["connected"]:
            continue
        point = tuple(np.rint(junction["point"]).astype(int).tolist())
        cv2.circle(junction_overlay, point, 6, (0, 220, 255), -1, cv2.LINE_AA)
        label = (point[0] + 10, max(20, point[1] - 10))
        cv2.putText(junction_overlay, junction["name"], label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(junction_overlay, junction["name"], label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 220, 255), 1, cv2.LINE_AA)
    final_overlay = image.copy()
    if frame["valid"]:
        polygon = np.rint(frame["polygon"]).astype(np.int32)
        cv2.polylines(final_overlay, [polygon], True, (30, 210, 30), 3, cv2.LINE_AA)
        for point in polygon:
            cv2.circle(final_overlay, tuple(map(int, point)), 6, (0, 220, 255), -1, cv2.LINE_AA)
    return junction_overlay, final_overlay


def draw_completion(image, completion):
    """Green: observed connections; orange rings: extrapolated corners."""
    overlay = image.copy()
    if not completion["available"]:
        return overlay
    points = np.asarray(completion["polygon"], dtype=float)
    # Drawing is clipped to the image; the JSON keeps unmodified intersections.
    height, width = image.shape[:2]
    for i, point in enumerate(points):
        following = points[(i + 1) % 4]
        endpoints = np.clip(np.rint(np.r_[point, following]), -1_000_000_000, 1_000_000_000).astype(int)
        visible, a, b = cv2.clipLine((0, 0, width, height), tuple(endpoints[:2]), tuple(endpoints[2:]))
        if visible:
            color = (0, 160, 255) if completion["estimated"] else (30, 210, 30)
            cv2.line(overlay, a, b, color, 3, cv2.LINE_AA)
    for junction in completion["junctions"]:
        x, y = np.rint(junction["point"]).tolist()
        if not 0 <= x < width or not 0 <= y < height:
            continue
        point = (int(x), int(y))
        inferred = junction["inferred"]
        color = (0, 160, 255) if inferred else (30, 210, 30)
        cv2.circle(overlay, point, 9 if inferred else 6, color, 2 if inferred else -1, cv2.LINE_AA)
        label = junction["name"] + ("*" if inferred else "")
        position = (max(3, min(width - 45, point[0] + 10)), max(18, min(height - 5, point[1] - 10)))
        cv2.putText(overlay, label, position, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(overlay, label, position, cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1, cv2.LINE_AA)
    return overlay


def draw_merge_round(image, raw, merge_round):
    fits = np.asarray([g["line"] for g in merge_round["groups"]], dtype=float).reshape(-1, 4)
    return draw_lines(draw_lines(image, raw, (130, 130, 130), 1), fits, (255, 230, 0), 3)
