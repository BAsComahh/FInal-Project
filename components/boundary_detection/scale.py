"""Convert percentage length settings at image/ROI boundaries, keeping geometry isotropic."""

from math import isfinite
from numbers import Real


def image_short_side(image_shape):
    """Use the smaller raster dimension as a single Euclidean reference length."""
    if len(image_shape) < 2:
        raise ValueError("Image shape needs height and width.")
    dimensions = image_shape[:2]
    if any(isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value) or value <= 0
           for value in dimensions):
        raise ValueError("Image height and width must be finite and positive.")
    return float(min(dimensions))


def percent_to_length(percent, reference, *, name="length", allow_zero=False):
    """Five means 5%, not 0.05; convert once to the reference coordinate units."""
    if (isinstance(percent, bool) or not isinstance(percent, Real) or not isfinite(percent)
            or percent < 0 or (percent == 0 and not allow_zero)):
        raise ValueError(f"{name} must be a finite {'non-negative' if allow_zero else 'positive'} percentage.")
    if isinstance(reference, bool) or not isinstance(reference, Real) or not isfinite(reference) or reference <= 0:
        raise ValueError("Reference length must be finite and positive.")
    result = float(percent) * float(reference) / 100
    if not isfinite(result):
        raise ValueError(f"{name} produces a non-finite length.")
    return result
