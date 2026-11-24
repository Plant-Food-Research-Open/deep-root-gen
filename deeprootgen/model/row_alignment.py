"""Deterministic heading preference for either direction along the row."""

import math

import numpy as np


ROW_AXIS = (0.0, 1.0, 0.0)
ROW_ALIGNMENT_LAW = "nematic_heading_v1"


def check_alignment_step(strength, step):
    if not math.isfinite(strength) or strength < 0 or strength * step > 0.5:
        raise ValueError("row_alignment_per_cm must be finite and nonnegative with row_alignment_per_cm * step_cm <= 0.5")


def align_heading(heading, axis, exposure):
    """Exact isolated update on unit vectors for exposure equal to strength times arclength."""
    component = float(np.dot(heading, axis))
    if exposure == 0.0 or component == 0.0:
        return heading
    parallel = component * np.asarray(axis)
    perpendicular = heading - parallel
    if not np.any(perpendicular):
        return heading
    aligned = parallel + math.exp(-exposure) * perpendicular
    return aligned / np.linalg.norm(aligned)
