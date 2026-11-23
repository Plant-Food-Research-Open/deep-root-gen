"""Observation support for partial excavations, independent of root generation."""

import math
from dataclasses import dataclass
from numbers import Real
from typing import Literal

import numpy as np


_UNITS = {
    "crown_axis_count": "count",
    "daughter_count": "count",
    "whole_axis_length": "cm",
    "segment_to_branch_length": "cm",
    "local_diameter": "cm",
    "taper_rate": "1/cm",
}


@dataclass(frozen=True)
class ExcavationObservation:
    """A measurement with known support. A lower bound is one-sided evidence."""

    quantity: str
    status: Literal["observed", "lower_bound", "missing"]
    value: float | None = None

    def __post_init__(self):
        if self.quantity not in _UNITS or self.status not in ("observed", "lower_bound", "missing"):
            raise ValueError("Unknown excavation quantity or observation status")
        if self.status == "missing":
            if self.value is not None:
                raise ValueError("Missing observations have no numeric value")
            return
        value = self.value
        if not isinstance(value, Real) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
            raise ValueError("Observed excavation values must be finite nonnegative numbers")
        if self.unit == "count" and int(value) != value:
            raise ValueError("Excavated axis counts must be integers")
        if self.status == "lower_bound" and self.quantity not in ("whole_axis_length", "daughter_count"):
            raise ValueError("A censored whole-axis length or daughter count needs its own measurement")

    @property
    def unit(self):
        return _UNITS[self.quantity]

    @property
    def bounds(self):
        """Return (lower, upper); None represents an unavailable bound."""
        if self.status == "missing":
            return None, None
        return self.value, self.value if self.status == "observed" else None


def length_in_excavation(points_cm, lower_cm, upper_cm, *, complete_recovery):
    """Clip a whole-axis polyline to an explicit XYZ box in the same cm frame.

    A clipped or damaged recovered axis only supplies a lower bound on whole
    length. A local segment alone should instead be recorded as its own quantity.
    """
    points = np.asarray(points_cm, dtype=float)
    lower = np.asarray(lower_cm, dtype=float)
    upper = np.asarray(upper_cm, dtype=float)
    if (points.ndim != 2 or points.shape[1] != 3 or len(points) < 2
            or lower.shape != (3,) or upper.shape != (3,)
            or not all(np.isfinite(x).all() for x in (points, lower, upper))
            or np.any(lower >= upper) or type(complete_recovery) is not bool):
        raise ValueError("Supply a finite XYZ polyline, a nonempty XYZ box and explicit completeness")
    start, delta = points[:-1], np.diff(points, axis=0)
    # Slab intersection. Parallel segments must be inside that coordinate slab.
    moving = delta != 0
    first = np.divide(lower - start, delta, out=np.zeros_like(delta), where=moving)
    last = np.divide(upper - start, delta, out=np.ones_like(delta), where=moving)
    enter = np.maximum(0., np.max(np.minimum(first, last), axis=1))
    exit = np.minimum(1., np.min(np.maximum(first, last), axis=1))
    fraction = np.maximum(0., exit - enter)
    inside = (((start >= lower) & (start <= upper)) | moving).all(axis=1)
    length = float(np.dot(np.linalg.norm(delta, axis=1), fraction * inside))
    if length == 0:
        return ExcavationObservation("whole_axis_length", "missing")
    clipped = bool(np.any((points < lower) | (points > upper)))
    status = "observed" if complete_recovery and not clipped else "lower_bound"
    return ExcavationObservation("whole_axis_length", status, length)


def recovery_daughter_probabilities(probabilities, multiplier):
    """Scale conditional daughter counts on one declared sampled parent order.

    The assumed detection fraction is 1/multiplier. If a branch-positive
    parent's reference draw is N, the comparison proposes multiplier*N
    daughters. Neither the draw probability nor independently measured core
    targets enter this transform.
    """
    if type(multiplier) is not int or multiplier not in (1, 2, 3):
        raise ValueError("Use an explicit excavation sensitivity multiplier of 1, 2 or 3")
    probabilities = np.asarray(probabilities, dtype=float)
    if (probabilities.ndim != 1 or not len(probabilities) or not np.isfinite(probabilities).all()
            or np.any(probabilities < 0) or abs(probabilities.sum() - 1) > 1e-12):
        raise ValueError("Conditional daughter probabilities must be a nonnegative distribution")
    result = np.zeros(len(probabilities) * multiplier)
    result[multiplier - 1::multiplier] = probabilities
    return result.tolist()
