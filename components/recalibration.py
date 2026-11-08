"""Prepare new board geometry and annotations without changing the live match."""

from copy import deepcopy

import cv2
import numpy as np

from components.game_data import BoardData
from components.homography import transform_points, warp_table


def prepare_recalibration(data, source_frame, corners, boundary, board_size_mm):
    old = data.board
    prediction = data.current.prediction
    if prediction is None or data.units is None or old.homography is None or old.image_to_plane is None:
        raise ValueError("A registered observation and existing calibration are required.")
    result = warp_table(source_frame, corners, board_size=board_size_mm)
    board = BoardData(
        calibration_version=old.calibration_version + 1,
        source_size=source_frame.shape[1::-1], board_size_mm=tuple(map(float, board_size_mm)),
        source_to_plane=result["image_to_board"],
        image_to_plane=result["image_to_board"] @ result["inverse_matrix"],
        homography={key: value for key, value in result.items() if key != "image"},
        table_boundary=deepcopy(boundary),
    )
    image_mapping = result["matrix"] @ old.homography["inverse_matrix"]
    ids, masks = [], []
    for object_id, mask in zip(prediction["object_ids"], prediction["masks"]):
        if object_id not in data.units.bindings:
            continue
        mapped = cv2.warpPerspective(mask.astype(np.uint8), image_mapping, result["output_size"],
                                     flags=cv2.INTER_NEAREST).astype(bool)
        if mapped.any():
            ids.append(object_id)
            masks.append(mapped)
    if not ids:
        raise ValueError("No usable registered masks at this frame. Cancel and retry on a clearer frame.")

    rules = deepcopy(data.rules)
    for item in rules.terrain:
        if item.get("polygon_source") is None:
            item["polygon_source"] = transform_points(item["polygon_image"], old.homography["inverse_matrix"]).tolist()
        item["polygon_image"] = transform_points(item["polygon_source"], board.homography["matrix"]).tolist()

    for object_id, front in rules.fronts.items():
        angle = np.radians(front["angle_deg"])
        direction = np.array([np.cos(angle), np.sin(angle)])
        tray = prediction.get("trays", {}).get(object_id)
        if front.get("source_ray") is None and tray is not None:
            center = np.asarray(tray["center_plane"])
            plane_to_source = old.homography["inverse_matrix"] @ np.linalg.inv(old.image_to_plane)
            front["source_ray"] = transform_points([center, center + direction], plane_to_source).tolist()
        if front.get("source_ray") is not None:
            ray = transform_points(front["source_ray"], board.source_to_plane)
            direction = ray[1] - ray[0]
        else:
            direction *= np.asarray(board.board_size_mm) / old.board_size_mm
        front.update(angle_deg=float(np.degrees(np.arctan2(direction[1], direction[0]))),
                     parity=None, source="recalibrated_estimate")

    return {"board": board, "rules": rules, "frame": result["image"],
            "prediction": {"object_ids": ids, "masks": np.stack(masks)},
            "unseeded_units": [unit for obj, unit in data.units.bindings.items() if obj not in ids]}
