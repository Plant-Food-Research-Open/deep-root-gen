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


ROW_AXIAL_STREAM_VERSION = "drg-insertion-row-axial-v1"


def validate_row_axial_kappas(mapping, max_order=3):
    """Normalize explicit order keys, without inventing a concentration."""
    if mapping is None:
        return None
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("Row-axial insertion needs a nonempty order mapping")
    result = {}
    for key, value in mapping.items():
        if isinstance(key, (bool, np.bool_)) or str(key) not in {"2", "3"}:
            raise ValueError("Row-axial insertion supports selected orders 2/3")
        order = int(key)
        if order > max_order or order in result:
            raise ValueError("Row-axial insertion order is unsupported or duplicated")
        try:
            kappa = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError("Row-axial kappa must be finite and nonnegative") from error
        if not np.isfinite(kappa) or kappa < 0:
            raise ValueError("Row-axial kappa must be finite and nonnegative")
        result[order] = kappa
    return result


def row_axial_controls_active(mapping):
    return mapping is not None and any(kappa > 0 for kappa in mapping.values())


def _row_axial_stream(seed, organ_id, order, purpose):
    key = hashlib.sha256(f"{ROW_AXIAL_STREAM_VERSION}:{seed}:{order}:{organ_id}:{purpose}".encode()).digest()
    return np.random.default_rng(np.random.SeedSequence(np.frombuffer(key, dtype="<u4")))


def row_axial_insertion_heading(parent_direction, original_heading, kappa,
                                seed=None, organ_id=None, order=None):
    """Bias azimuth around the projected row axis, preserving the polar draw.

    Invoke AFTER the unchanged original insertion sampler. No shared RNG is
    accepted or consumed. None/zero and geometric degeneracies return the exact
    original vector. This research anisotropy is not a Fichtl coefficient.
    """
    tangent = _basis(parent_direction)[0]
    original = np.asarray(original_heading, dtype=float)
    if (original.shape != (3,) or not np.isfinite(original).all()
            or not np.isclose(np.linalg.norm(original), 1., rtol=0, atol=1e-10)):
        raise ValueError("Original insertion heading must be a finite unit vector")
    if kappa is not None and (not np.isfinite(kappa) or kappa < 0):
        raise ValueError("Row-axial kappa must be finite and nonnegative")
    if kappa is not None and kappa > 0:
        if (isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)) or seed < 0
                or isinstance(organ_id, (bool, np.bool_)) or not isinstance(organ_id, (int, np.integer)) or organ_id <= 0
                or isinstance(order, (bool, np.bool_)) or not isinstance(order, (int, np.integer)) or order not in (2, 3)):
            raise ValueError("Active row-axial insertion requires explicit integer seed/organ/order")
    cosine = float(np.clip(original @ tangent, -1., 1.))
    sine = float(np.linalg.norm(original - cosine * tangent))
    projected = np.array([0., 1., 0.]) - tangent[1] * tangent
    rho = float(np.linalg.norm(projected))
    fallback = ("disabled" if kappa is None else "zero_kappa" if kappa == 0 else
                "parent_parallel_row" if rho < 1e-12 else "zero_polar" if sine < 1e-12 else None)
    phi = branch = eta = None
    chosen = original
    if fallback is None:
        first = projected / rho
        # Remove projection-rounding error near the parallel-row threshold.
        first = first - (first @ tangent) * tangent
        first /= np.linalg.norm(first)
        second = np.cross(tangent, first)
        second /= np.linalg.norm(second)
        eta = float(_row_axial_stream(seed, organ_id, order, "axial_angle").vonmises(0., kappa))
        branch = int(_row_axial_stream(seed, organ_id, order, "axial_branch").integers(0, 2))
        phi = float((eta / 2. + branch * np.pi) % (2. * np.pi))
        chosen = cosine * tangent + sine * (np.cos(phi) * first + np.sin(phi) * second)
        chosen /= np.linalg.norm(chosen)
    report = dict(
        old_heading=original.tolist(), new_heading=chosen.tolist(),
        old_polar_angle_deg=float(np.degrees(np.arccos(cosine))),
        new_polar_angle_deg=float(np.degrees(np.arccos(np.clip(chosen @ tangent, -1., 1.)))),
        row_projection_norm=rho, phi_rad=phi, eta_rad=eta, axial_branch=branch,
        kappa=None if kappa is None else float(kappa), fallback=fallback,
        stream_version=ROW_AXIAL_STREAM_VERSION,
        stream_used=fallback is None,
        stream_identity=dict(seed=None if seed is None else int(seed),
                             organ_id=None if organ_id is None else int(organ_id),
                             order=None if order is None else int(order),
                             purposes=["axial_angle", "axial_branch"]),
        old_row_projection=float(original[1]), new_row_projection=float(chosen[1]),
    )
    return chosen, report
