"""Frozen DINOv2 reference embeddings and diagnostic missing-instance retrieval."""

from .extractor import DinoV2Extractor
from .matching import rank_candidates
from .type_features import load_type_features, update_type_features

__all__ = ["DinoV2Extractor", "load_type_features", "update_type_features", "rank_candidates"]
