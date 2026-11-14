"""Optional Fichtl-inspired direction search, not an exact CPlantBox replay.

Lengths are cm, sigma is radians/sqrt(cm), insertion angles are degrees.
One objective is drawn per segment. CPlantBox's initial candidate plus
stochastically rounded N*sqrt(ds) extra candidates is retained. Surface
constraints reject candidates; a downward fallback keeps geometry in soil.
"""

import hashlib
import math

import numpy as np


def _basis(direction):
    direction = np.asarray(direction, dtype=float)
    if direction.shape != (3,) or not np.isfinite(direction).all():
        raise ValueError("Heading must be a finite 3-vector")
    norm = np.linalg.norm(direction)
    if norm <= 1e-12:
        raise ValueError("Heading must have positive norm")
    direction = direction / norm
    axis = np.eye(3)[np.argmin(np.abs(direction))]
    first = np.cross(direction, axis)
    first /= np.linalg.norm(first)
    return direction, first, np.cross(direction, first)


def insertion_heading(parent_direction, mean_deg, sd_deg, rng):
    """Truncated-normal insertion proxy about the local parent tangent."""
    if not 0 <= mean_deg <= 90 or not np.isfinite(sd_deg) or sd_deg < 0:
        raise ValueError("Insertion angle needs mean in [0,90] and finite SD >= 0")
    for _ in range(1000):
        angle = rng.normal(mean_deg, sd_deg) if sd_deg else mean_deg
        if 0 <= angle <= 90:
            break
    else:
        raise ValueError("Insertion angle rejection budget exhausted")
    heading, first, second = _basis(parent_direction)
    angle, azimuth = math.radians(angle), rng.uniform(0, 2 * np.pi)
    return np.cos(angle) * heading + np.sin(angle) * (
        np.cos(azimuth) * first + np.sin(azimuth) * second
    )


def sample_heading(
    previous,
    length_cm,
    probability_down,
    sigma,
    trials,
    rng,
    start_z=0.0,
    surface_z=np.inf,
):
    """Select a unit direction and return auditable objective/boundary flags."""
    if not np.isfinite(start_z) or np.isnan(surface_z) or start_z > surface_z:
        raise ValueError("Segment must start at or below the soil surface")
    if not np.isfinite(length_cm) or length_cm <= 0:
        raise ValueError("Segment length must be finite and positive")
    if not 0 <= probability_down <= 1:
        raise ValueError("Downward probability must be in [0,1]")
    if not np.isfinite(sigma) or sigma < 0 or not np.isfinite(trials) or trials < 0:
        raise ValueError("sigma and trials must be finite and nonnegative")
    heading, first, second = _basis(previous)
    scaled = trials * np.sqrt(length_cm)
    extra = int(np.floor(scaled)) + int(rng.random() < scaled % 1)
    alpha = sigma * np.sqrt(length_cm) * rng.normal(size=extra + 1)
    beta = rng.uniform(0, 2 * np.pi, size=extra + 1)
    candidates = np.cos(alpha)[:, None] * heading + np.sin(alpha)[:, None] * (
        np.cos(beta)[:, None] * first + np.sin(beta)[:, None] * second
    )
    downward = bool(rng.random() < probability_down)
    permitted = start_z + length_cm * candidates[:, 2] <= surface_z
    candidates = candidates[permitted]
    fallback = not len(candidates)
    if fallback:
        chosen = np.array([0.0, 0.0, -1.0])
    else:
        values = candidates[:, 2] if downward else np.abs(candidates[:, 2])
        chosen = candidates[np.argmin(values)]
    return chosen, {
        "downward": downward,
        "surface_fallback": fallback,
        "candidates": extra + 1,
        "rejected_surface": int((~permitted).sum()),
    }


def sample_primary_yaw(mean_deg, kappa, random_seed, organ_id):
    """Draw radians from an independent versioned seed/primary-organ stream.

    Mean is degrees from model x toward y; kappa is dimensionless. This is an
    opt-in initial-crown distribution, not a lateral tropism coefficient.
    """
    if (not np.isfinite(mean_deg) or not -180 <= mean_deg <= 180
            or not np.isfinite(kappa) or not 0 <= kappa <= 100):
        raise ValueError("Primary yaw needs finite mean in [-180,180] and kappa in [0,100]")
    if (isinstance(random_seed, (bool, np.bool_)) or not isinstance(random_seed, (int, np.integer))
            or random_seed < 0 or isinstance(organ_id, (bool, np.bool_))
            or not isinstance(organ_id, (int, np.integer)) or organ_id <= 0):
        raise ValueError("Primary yaw requires nonnegative integer seed and positive organ ID")
    key = hashlib.sha256(f"drg-primary-yaw-v1:{random_seed}:{organ_id}".encode()).digest()
    rng = np.random.default_rng(np.random.SeedSequence(np.frombuffer(key, dtype="<u4")))
    return float(rng.vonmises(math.radians(mean_deg), kappa))
