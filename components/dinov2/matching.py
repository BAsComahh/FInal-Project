"""Diagnostic retrieval for explicitly selected missing instances; no ID acceptance."""

import numpy as np

from .extractor import normalize_rows


def rank_candidates(unit_ids, reference_features, candidate_features):
    """Rank supplied missing-instance rows; an uncontested first choice is not acceptance."""
    references = normalize_rows(reference_features)
    candidates = normalize_rows(candidate_features)
    if (len(unit_ids) != len(references) or len(set(unit_ids)) != len(unit_ids)
            or not all(isinstance(unit_id, str) and unit_id.strip() for unit_id in unit_ids)):
        raise ValueError("Reference rows must have unique, non-empty instance IDs")
    if references.shape[1] != candidates.shape[1]:
        raise ValueError("Reference and candidate feature dimensions differ")
    similarities = np.clip(references @ candidates.T, -1, 1)
    rankings, choices = [], {}
    for unit_id, row in zip(unit_ids, similarities):
        order = np.argsort(-row, kind="stable").tolist()
        margin = float(row[order[0]] - row[order[1]]) if len(order) > 1 else None
        rankings.append({"unit_id": unit_id, "candidate_ids": order,
                         "scores": [float(row[index]) for index in order],
                         "top_two_margin": margin, "assigned_candidate_id": None,
                         "status": "unknown" if order else "no_candidates"})
        if order:
            choices.setdefault(order[0], []).append(unit_id)
    return {"unit_ids": list(unit_ids), "similarities": similarities.tolist(), "rankings": rankings,
            "top_choice_competitions": [{"candidate_id": index, "unit_ids": ids}
                                        for index, ids in choices.items() if len(ids) > 1]}
