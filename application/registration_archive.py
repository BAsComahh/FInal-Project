"""Read and validate a completed registration without modifying the live match."""
from copy import deepcopy
import json
from pathlib import Path

import cv2
import numpy as np

from components.game_data import BoardData
from components.homography import transform_points
from components.image_io import load_image
from components.registration.units import UnitRoster
from components.registration.rule_state import RuleState
from components.boundary_detection.tray.temporal import describe_mask
from components.video_io import VideoSource
from components.game_rules.scene import validate_scene
from . import config


def _json(path):
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return value


def _inside(root, relative):
    if not isinstance(relative, str) or not relative:
        raise ValueError("Invalid archive file path")
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Archive file paths must stay inside the registration directory")
    return path


def _matrix(value):
    matrix = np.asarray(value, dtype=float)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all() or np.linalg.matrix_rank(matrix) != 3:
        raise ValueError("Invalid archive calibration matrix")
    return matrix


def read_archive(path, video):
    """Return a detached initial observation and an already-positioned video source."""
    path = Path(path).expanduser().resolve()
    root = path.parent if path.is_file() and path.name == "prompts.json" else path
    source = None
    try:
        metadata = _json(root / "prompts.json")
        if metadata.get("registration_complete") is not True:
            raise ValueError("Choose a completed registration directory")
        roster = UnitRoster.from_snapshot(_json(root / "units.json"))
        ids = metadata["object_ids"]
        if (not isinstance(ids, list) or not ids or any(type(obj) is not int or obj < 1 for obj in ids)
                or len(set(ids)) != len(ids) or not roster.bindings.keys() <= set(ids)):
            raise ValueError("Archive object IDs do not match the saved bindings")
        frame = load_image(root / "frame.png")
        overlay = load_image(root / "overlay.png")
        if overlay.shape != frame.shape:
            raise ValueError("Archive overlay does not match its frame")
        if list(frame.shape[1::-1]) != metadata["image_size"]:
            raise ValueError("Archive masks/frame dimensions disagree")
        entries = _json(root / "instances.json")["instances"]
        if not isinstance(entries, list) or len(entries) != len(ids):
            raise ValueError("Invalid archive instance list")
        masks = {}
        for row in entries:
            obj = row["object_id"]
            if obj not in ids or obj in masks:
                raise ValueError("Duplicate or unknown archived object")
            selection = _inside(root, row["selection"])
            item = _json(selection)
            if item["object_id"] != obj or item.get("unit_id") != roster.bindings.get(obj):
                raise ValueError("Archive object/unit identities disagree")
            uid = roster.bindings.get(obj)
            if uid is not None and item.get("type_id") != roster.units[uid]["type_id"]:
                raise ValueError("Archive unit types disagree")
            mask = load_image(_inside(root, str(selection.parent.relative_to(root) / item["mask"])), mode="gray") != 0
            if mask.shape != frame.shape[:2]:
                raise ValueError("Archived mask does not match its registration frame")
            masks[obj] = mask
        if not any(mask.any() for mask in masks.values()):
            raise ValueError("Archive has no usable masks")
        homography = deepcopy(metadata["homography"])
        matrix, inverse = _matrix(homography["matrix"]), _matrix(homography["inverse_matrix"])
        output_size = homography["output_size"]
        if (output_size != list(frame.shape[1::-1]) or
                not np.allclose(matrix @ inverse, np.eye(3), rtol=1e-5, atol=1e-5)):
            raise ValueError("Archive homography does not match its frame")
        homography.update(matrix=matrix, inverse_matrix=inverse)
        plane = _matrix(metadata["image_to_plane"])
        size = np.asarray(metadata["board_size_mm"], dtype=float)
        if size.shape != (2,) or not np.isfinite(size).all() or (size <= 0).any():
            raise ValueError("Invalid archived board dimensions")
        source = VideoSource(video)
        index = metadata["frame_index"]
        if (type(index) is not int or not 0 <= index < source.frame_count or
                not np.isclose(float(metadata["fps"]), source.fps, rtol=0, atol=1e-6)):
            raise ValueError("Archive frame or FPS does not match this video")
        raw = source.read_frame(index)
        if list(raw.shape[1::-1]) != metadata["source_image_size"]:
            raise ValueError("Archive source dimensions do not match this video")
        aligned = cv2.warpPerspective(raw, matrix, tuple(output_size))
        if not np.array_equal(frame, aligned):
            raise ValueError("Archive frame does not match this video at the saved frame number")
        board = BoardData(calibration_version=int(metadata.get("calibration_version", 1)),
            source_size=raw.shape[1::-1], board_size_mm=tuple(size), source_to_plane=plane @ matrix,
            image_to_plane=plane, homography=homography, table_boundary=deepcopy(metadata.get("table_boundary")))
        rules = RuleState()
        inputs = metadata.get("rule_inputs", {})
        rules.fronts = {int(obj): deepcopy(row) for obj, row in inputs.get("fronts", {}).items() if int(obj) in ids}
        rules.terrain = deepcopy(inputs.get("terrain", []))
        rules.track_facing = config.FACING_TRACKING_ENABLED
        trays = {}
        for unit in metadata.get("rule_scene", {}).get("units", []):
            obj, uid = unit["object_id"], unit["unit_id"]
            if roster.bindings.get(obj) != uid:
                raise ValueError("Archive scene identities disagree")
            corners = np.asarray(unit["corners_mm"], dtype=float)
            if corners.shape != (4, 2) or not np.isfinite(corners).all():
                raise ValueError("Invalid saved tray corners")
            dimension = roster.types[roster.units[uid]["type_id"]].get("dimension")
            if dimension is None or not masks[obj].any():
                continue
            trays[obj] = dict(method="archive", fit_method="archive", corners_plane=corners.tolist(),
                corners_image=transform_points(corners, np.linalg.inv(plane)).tolist(), center_plane=corners.mean(axis=0).tolist(),
                mask_coverage=None, edge_support=None, observation_frame_index=index,
                cache_context=(tuple(plane.ravel()), (dimension["width_mm"], dimension["depth_mm"]), tuple(frame.shape[:2])),
                fit_sample=dict(describe_mask(masks[obj]), frame_index=index))
        clicks = metadata.get("clicks", [])
        if not isinstance(clicks, list) or any(row["object_id"] not in ids or
                type(row["click_id"]) is not int or row["click_id"] < 0 or type(row["positive"]) is not bool or
                row["video_frame"] != index or np.asarray(row["point"]).shape != (2,) or
                not np.isfinite(row["point"]).all() for row in clicks):
            raise ValueError("Invalid saved registration prompts")
        if len({row["click_id"] for row in clicks}) != len(clicks):
            raise ValueError("Duplicate saved prompt IDs")
        metadata.update(source.metadata(), restored_from=str(root))
        prediction = dict(object_ids=ids, masks=np.stack([masks[obj] for obj in ids]), frame_idx=0, trays=trays, tray_errors={})
        validate_scene(rules.scene(roster, prediction, plane, size, metadata, source_to_plane=board.source_to_plane))
        return dict(root=root, source=source, raw=raw, frame=frame, overlay=overlay, board=board, rules=rules,
                    roster=roster, metadata=metadata, prediction=prediction)
    except (KeyError, TypeError, AttributeError, UnicodeError) as error:
        if source is not None:
            source.close()
        raise ValueError(f"Invalid registration archive: {error}") from error
    except Exception:
        if source is not None:
            source.close()
        raise
