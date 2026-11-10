"""One-frame SAM search and missing-instance retrieval, without business-state writes."""
import cv2
import numpy as np
from PIL import Image

from components.dinov2 import DinoV2Extractor, rank_candidates
from components.dinov2.type_features import _references
from components.registration.references import extract_references
from components.sam3 import Sam3Segmenter


def decide_matches(unit_ids, references, candidates, masks, occupied, *, similarity, margin):
    """Conservative gating; never force a one-to-one assignment or steal occupied pixels."""
    if (not np.isfinite([similarity, margin]).all() or not -1 <= similarity <= 1 or not 0 <= margin <= 2):
        raise ValueError("Invalid automatic-recovery similarity/margin configuration")
    eligible = [i for i, mask in enumerate(masks) if mask.any() and not np.any(mask & occupied)]
    ranked = rank_candidates(unit_ids, references, candidates[eligible])
    rows = ranked["rankings"]
    for row in rows:
        row["candidate_ids"] = [eligible[i] for i in row["candidate_ids"]]
    contested = set()
    for i, row in enumerate(rows):
        if not row["candidate_ids"]:
            continue
        for other in rows[i + 1:]:
            if other["candidate_ids"] and np.any(masks[row["candidate_ids"][0]] & masks[other["candidate_ids"][0]]):
                contested.update((row["unit_id"], other["unit_id"]))
    for row in rows:
        index = row["candidate_ids"][0] if row["candidate_ids"] else None
        reason = ("No unoccupied candidate" if index is None else
                  "Competing missing instances" if row["unit_id"] in contested else
                  "No runner-up for margin check" if row["top_two_margin"] is None else
                  "Low similarity or small margin" if row["scores"][0] < similarity or row["top_two_margin"] < margin else
                  "Automatic match")
        row.update(candidate_id=index, automatic=reason == "Automatic match", reason=reason)
    return rows


class AutomaticRecoveryEngine:
    def __init__(self, device=None):
        self.segmenter = Sam3Segmenter(device=device)
        self.extractor = DinoV2Extractor(device=device)
        self.references = {}
        self.load_error = None

    def load(self):
        try:
            self.segmenter._load_model()
            self.extractor.load()
        except Exception as error:
            self.load_error = str(error)
            raise

    def search(self, frame, folder, targets, occupied, *, prompt, detection_threshold, similarity, margin, cancelled):
        if self.load_error is not None:
            raise ValueError(f"Automatic recovery models unavailable: {self.load_error}")
        if cancelled.is_set():
            raise ValueError("Automatic search cancelled")
        root, images, samples, _ = _references(folder)
        available = {sample["unit_id"]: image for sample, image in zip(samples, images)}
        ids = [target["unit_id"] for target in targets]
        if len(set(ids)) != len(ids) or set(ids) - available.keys():
            raise ValueError("Automatic targets must be registered missing instances")
        new_ids = [uid for uid in ids if (str(root), uid) not in self.references]
        if new_ids:
            vectors = self.extractor.encode([available[uid] for uid in new_ids])
            self.references.update({(str(root), uid): vector for uid, vector in zip(new_ids, vectors)})
        detection = self.segmenter.segment(frame, prompt, threshold=detection_threshold)
        if cancelled.is_set():
            raise ValueError("Automatic search cancelled")
        cutouts = extract_references(frame, {"object_ids": list(range(len(detection["masks"]))), "masks": detection["masks"]})
        nonempty = [item for item in cutouts if item["cutout"] is not None]
        masks = np.asarray([item["mask"] for item in nonempty], dtype=bool).reshape(-1, *frame.shape[:2])
        vectors = self.extractor.encode([Image.fromarray(cv2.cvtColor(item["cutout"], cv2.COLOR_BGRA2RGBA))
                                         for item in nonempty])
        if cancelled.is_set():
            raise ValueError("Automatic search cancelled")
        rows = decide_matches(ids, np.asarray([self.references[(str(root), uid)] for uid in ids]), vectors,
                              masks, occupied, similarity=similarity, margin=margin)
        for target, row in zip(targets, rows):
            row["object_id"] = target["object_id"]
        return {"rows": rows, "masks": masks, "raw_candidate_count": len(detection["masks"])}
