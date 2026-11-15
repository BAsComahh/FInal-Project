"""Apply the existing tray fitter to a matching frame and object masks."""

from copy import deepcopy
from time import perf_counter

import cv2
import numpy as np

from .detector import fit_tray
from .temporal import TrayStability, describe_mask


def fit_registered_trays(frame, prediction, context, *, previous=None, reuse_stable=False,
                         stability=None, source_frame=None, attempts=None, cancelled=None):
    """Return observed proposals keyed by SAM object ID, plus per-unit errors.

    context has image_to_plane and sizes (object_id -> width/depth in mm).
    Missing dimensions and empty masks produce no tray; no boxes are invented.
    """
    trays, errors = {}, {}
    stability = stability or TrayStability()
    mapping = context["image_to_plane"]
    mapping_key = None if mapping is None else tuple(float(value) for value in np.asarray(mapping).ravel())
    for object_id, mask in zip(prediction["object_ids"], prediction["masks"]):
        if cancelled is not None and cancelled.is_set():
            break
        started = perf_counter()
        size = context["sizes"].get(object_id)
        if size is None or not mask.any():
            continue
        sample = None
        try:
            if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3 or mask.shape != frame.shape[:2]:
                raise ValueError("Tray masks must match the current uint8 BGR frame")
            cache_context = (mapping_key, tuple(float(value) for value in size), tuple(mask.shape))
            prior = (previous or {}).get(object_id)
            if prior is not None and (prior.get("cache_context") != cache_context or
                    source_frame is not None and prior.get("observation_frame_index") is not None and
                    prior["observation_frame_index"] > source_frame):
                prior = None
            sample = describe_mask(mask) if reuse_stable else None
            check = None
            if reuse_stable and prior is not None and prior.get("fit_sample") is not None:
                corners = prior.get("corners_image")
                short_side = (np.linalg.norm(np.roll(corners, -1, axis=0) - corners, axis=1).min()
                              if corners is not None else min(prior["fit_sample"]["bbox"][2:]))
                stable, check = stability.compare(prior["fit_sample"], sample, short_side)
                if stable:
                    if corners is not None:
                        tray = deepcopy(prior)
                        tray.update(method="stable_reuse", fit_method=prior.get("fit_method", prior["method"]),
                                    observation_frame_index=source_frame, reuse_check=check)
                        trays[object_id] = tray
                    else:
                        errors[object_id] = "Tray fit waits for mask change after failure"
                    if attempts is not None:
                        attempts[object_id] = dict(prior, observation_frame_index=source_frame, reuse_check=check,
                                                   attempted=False, seconds=perf_counter() - started)
                    continue
            initial = prior.get("corners_image") if prior is not None else None
            result = fit_tray(frame, mask, size, image_to_plane=context["image_to_plane"], initial_corners=initial)
            if result["success"]:
                tray = result["best"]
                tray.update(cache_context=cache_context, observation_frame_index=source_frame)
                if sample is not None:
                    tray["fit_sample"] = dict(sample, frame_index=source_frame)
                if check is not None:
                    tray["reuse_check"] = check
                trays[object_id] = tray
            else:
                errors[object_id] = "Tray fit needs review"
            if attempts is not None:
                attempts[object_id] = dict(trays.get(object_id, {}), cache_context=cache_context,
                    fit_sample=dict(sample, frame_index=source_frame) if sample is not None else None,
                    observation_frame_index=source_frame, reuse_check=check, attempted=True,
                    seconds=perf_counter() - started, error=errors.get(object_id))
        except (ValueError, cv2.error) as error:
            errors[object_id] = str(error)
            if attempts is not None and sample is not None:
                attempts[object_id] = dict(cache_context=cache_context, fit_sample=dict(sample, frame_index=source_frame),
                    observation_frame_index=source_frame, attempted=True, seconds=perf_counter() - started,
                    reuse_check=check, error=str(error))
    return trays, errors
