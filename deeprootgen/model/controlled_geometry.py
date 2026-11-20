"""Shared controlled-direction primitives; versioned stochastic semantics."""

import hashlib
import json
from typing import Any
import numpy as np
from ..utils.order_controls import direction_controls
from ..utils.tropism import _basis, sample_fichtl_alpha, resolve_fichtl_sigma


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, allow_nan=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def unit(vector):
    vector = np.asarray(vector, dtype=float)
    if vector.shape != (3,) or not np.isfinite(vector).all():
        raise ValueError("Expected finite 3-vector")
    norm = np.linalg.norm(vector)
    if norm <= 1e-12:
        raise ValueError("Degenerate direction")
    return vector / norm


def minimal_rotation(source, target):
    """Deterministic shortest rotation; antiparallel axis is the least aligned axis."""
    source, target = unit(source), unit(target)
    cross = np.cross(source, target)
    cosine = float(np.clip(source @ target, -1, 1))
    sine = np.linalg.norm(cross)
    if sine <= 1e-12:
        if cosine > 0:
            return np.eye(3)
        axis = _basis(source)[1]
        return 2 * np.outer(axis, axis) - np.eye(3)
    # Normalized-axis Rodrigues avoids the (1-c)/s² amplification near pi.
    axis = cross / sine
    angle = np.arctan2(sine, cosine)
    sine, cosine = np.sin(angle), np.cos(angle)
    skew = np.array(
        [[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]]
    )
    return cosine * np.eye(3) + (1 - cosine) * np.outer(axis, axis) + sine * skew


def frame(heading):
    return np.column_stack(_basis(heading))


def fichtl_proposal(previous_frame, length, order, settings, rng):
    """Select unconstrained candidate; boundary is a separate common operator."""
    control = direction_controls(settings, order)
    trials = control["trials"]
    sigma_map = settings.get("research_fichtl_sigma_by_order")
    if sigma_map is not None and settings.get("tropism_mode") != "fichtl2024":
        raise ValueError("Order sigma overrides require fichtl2024 mode")
    sigma, sigma_receipt = resolve_fichtl_sigma(
        settings["fichtl_sigma"], order, sigma_map
    )
    probability = control["probability_down"]
    previous_frame = np.asarray(previous_frame, dtype=float)
    if (
        not np.isfinite(length)
        or length <= 0
        or not np.isfinite(trials)
        or trials < 0
        or not np.isfinite(sigma)
        or sigma < 0
        or not np.isfinite(probability)
        or not 0 <= probability <= 1
        or previous_frame.shape != (3, 3)
        or not np.isfinite(previous_frame).all()
        or not np.allclose(
            previous_frame.T @ previous_frame, np.eye(3), rtol=0, atol=1e-10
        )
        or not np.isclose(np.linalg.det(previous_frame), 1, rtol=0, atol=1e-10)
    ):
        raise ValueError("Invalid Fichtl proposal inputs")
    scaled = trials * np.sqrt(length)
    extra = int(np.floor(scaled)) + int(rng.random() < scaled % 1)
    alpha = sample_fichtl_alpha(length, sigma, extra + 1, rng)
    beta = rng.uniform(0, 2 * np.pi, size=extra + 1)
    downward = bool(rng.random() < probability)
    local = np.column_stack(
        [np.cos(alpha), np.sin(alpha) * np.cos(beta), np.sin(alpha) * np.sin(beta)]
    )
    candidates = local @ previous_frame.T
    score = candidates[:, 2] if downward else np.abs(candidates[:, 2])
    selected = int(np.argmin(score))
    innovations = dict(alpha=alpha.tolist(), beta=beta.tolist(), downward=downward)
    return unit(candidates[selected]), dict(
        candidates=len(candidates),
        selected_candidate=selected,
        innovations_sha256=digest(innovations),
        **innovations,
        **sigma_receipt,
    )


def apply_boundary(
    start, heading, length, surface_z, policy, rng=None, diagnostics=None
):
    """Minimum-angle feasible heading projection, applied after arm selection.

    Preserve azimuth, set qz=(S-z)/L at a crossing; a pure-up proposal uses
    the keyed boundary stream. No candidate rejection, clipping or shortening.
    """
    if policy != "minimum_angle_projection":
        raise ValueError("Unapproved/unsupported common boundary policy")
    start = np.asarray(start, dtype=float)
    heading = np.asarray(heading, dtype=float)
    if (
        start.shape != (3,)
        or not np.isfinite(start).all()
        or not np.isfinite(surface_z)
        or not np.isfinite(length)
        or length <= 0
        or not np.isclose(np.linalg.norm(heading), 1, rtol=0, atol=1e-10)
    ):
        raise ValueError("Invalid boundary inputs")
    heading = unit(heading)
    if start[2] > surface_z:
        raise ValueError("Segment starts above shared physical soil surface")
    proposed = start + length * heading
    accepted = np.array(heading, copy=True)
    intervention = bool(proposed[2] > surface_z)
    nudges = 0
    if intervention:
        cap = (surface_z - start[2]) / length
        while start[2] + length * cap > surface_z:
            cap = np.nextafter(cap, -np.inf)
            nudges += 1
        horizontal = np.linalg.norm(heading[:2])
        if horizontal <= 1e-12:
            if rng is None:
                raise ValueError("Pure-up projection requires keyed boundary RNG")
            azimuth = rng.uniform(0, 2 * np.pi)
            azimuth_vector = np.array([np.cos(azimuth), np.sin(azimuth)])
        else:
            azimuth_vector = heading[:2] / horizontal
        accepted = np.r_[np.sqrt(1 - cap**2) * azimuth_vector, cap]
    if diagnostics is not None:
        diagnostics["boundary_ulp_nudges"] = nudges
    return accepted, proposed, intervention
