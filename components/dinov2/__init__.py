"""Frozen DINOv2 embeddings and updates from confirmed registration references."""

from .extractor import DinoV2Extractor
from .type_features import load_type_features, update_type_features

__all__ = ["DinoV2Extractor", "load_type_features", "update_type_features"]
