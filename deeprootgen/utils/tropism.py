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


SIGMA_OPERATOR_VERSION = "research-fichtl-sigma-by-order-v1"


def validate_fichtl_sigma_by_order(mapping, max_order=3):
    """Selected order2..5 overrides in rad/sqrt(cm); zero retains normal draws."""
    if mapping is None:
        return None
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("Order sigma overrides require a nonempty mapping")
    result = {}
    for key, value in mapping.items():
        if (
            isinstance(key, (bool, np.bool_))
            or not isinstance(key, (int, np.integer, str))
            or str(key) not in {"2", "3", "4", "5"}
        ):
            raise ValueError(
                "Order sigma keys must be integer2..5 or exact JSON string keys"
            )
        order = int(key)
        if order > max_order or order in result:
            raise ValueError("Order sigma key is unsupported or duplicated")
        if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, float, np.integer, np.floating)
        ):
            raise ValueError(
                "Order sigma values must be finite nonnegative nonbool scalars"
            )
        try:
            value = float(value)
        except (ValueError, OverflowError) as error:
            raise ValueError("Order sigma values must be finite") from error
        if not np.isfinite(value) or value < 0:
            raise ValueError(
                "Order sigma values must be finite nonnegative nonbool scalars"
            )
        result[order] = value
    return result


def resolve_fichtl_sigma(global_sigma, order, mapping=None):
    """Return effective coefficient and active-only provenance, with no RNG."""
    if mapping is None:
        return global_sigma, {}
    overrides = validate_fichtl_sigma_by_order(mapping, 5)
    if (
        isinstance(order, (bool, np.bool_))
        or order not in (2, 3, 4, 5)
        or (global_sigma is not None and (not np.isfinite(global_sigma) or global_sigma < 0))
    ):
        raise ValueError("Order sigma resolution requires a valid order and a per-order or global sigma")
    sigma = overrides.get(order, global_sigma)
    if sigma is None:
        raise ValueError(f"Order {order} needs a per-order or global sigma")
    if sigma == global_sigma:
        sigma = global_sigma  # Preserve even signed-zero innovations when equal.
    return sigma, dict(
        sigma_operator_version=SIGMA_OPERATOR_VERSION,
        effective_sigma_rad_per_sqrt_cm=float(sigma),
        sigma_source="order_override" if order in overrides else "global_fallback",
    )


def sample_fichtl_alpha(length_cm, sigma, count, rng):
    """Original equation/draw schedule; callers validate length/sigma/count.

    Do not shortcut zero: the normal draw is part of the paired RNG schedule.
    """
    return sigma * np.sqrt(length_cm) * rng.normal(size=count)


def order_sigma_metadata(global_sigma, mapping=None, max_order=3):
    """Configured coefficients, including organs with no continuation search."""
    if mapping is None:
        return {}
    return dict(
        order_sigma_control={
            str(order): resolve_fichtl_sigma(global_sigma, order, mapping)[1]
            for order in range(
                2,
                max(max_order, 3, max(validate_fichtl_sigma_by_order(mapping, 5))) + 1,
            )
        }
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
    alpha = sample_fichtl_alpha(length_cm, sigma, extra + 1, rng)
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
    if (
        not np.isfinite(mean_deg)
        or not -180 <= mean_deg <= 180
        or not np.isfinite(kappa)
        or not 0 <= kappa <= 100
    ):
        raise ValueError(
            "Primary yaw needs finite mean in [-180,180] and kappa in [0,100]"
        )
    if (
        isinstance(random_seed, (bool, np.bool_))
        or not isinstance(random_seed, (int, np.integer))
        or random_seed < 0
        or isinstance(organ_id, (bool, np.bool_))
        or not isinstance(organ_id, (int, np.integer))
        or organ_id <= 0
    ):
        raise ValueError(
            "Primary yaw requires nonnegative integer seed and positive organ ID"
        )
    key = hashlib.sha256(
        f"drg-primary-yaw-v1:{random_seed}:{organ_id}".encode()
    ).digest()
    rng = np.random.default_rng(np.random.SeedSequence(np.frombuffer(key, dtype="<u4")))
    return float(rng.vonmises(math.radians(mean_deg), kappa))


PRIMARY_YAW_REVERSAL_VERSION = "drg-primary-yaw-reversal-v1"


def validate_primary_yaw_reverse_probability(value):
    """Strict dimensionless research probability; None and zero are inactive."""
    if value is None:
        return None
    if (
        isinstance(value, (bool, np.bool_))
        or not isinstance(value, (int, float, np.integer, np.floating))
        or not 0 <= value <= 1
        or not np.isfinite(value)
    ):
        raise ValueError(
            "Primary yaw reversal probability must be a finite nonbool number in [0,1]"
        )
    return float(value)


def reverse_primary_yaw(yaw, probability, random_seed, organ_id):
    """Independent Bernoulli pi reversal of an already sampled primary yaw."""
    probability = validate_primary_yaw_reverse_probability(probability)
    if not probability:
        return yaw, None
    if (
        not np.isfinite(yaw)
        or isinstance(random_seed, (bool, np.bool_))
        or not isinstance(random_seed, (int, np.integer))
        or random_seed < 0
        or isinstance(organ_id, (bool, np.bool_))
        or not isinstance(organ_id, (int, np.integer))
        or organ_id <= 0
    ):
        raise ValueError(
            "Primary yaw reversal requires finite yaw, nonnegative integer seed and positive organ ID"
        )
    key = hashlib.sha256(
        f"{PRIMARY_YAW_REVERSAL_VERSION}:{random_seed}:{organ_id}".encode()
    ).digest()
    rng = np.random.default_rng(np.random.SeedSequence(np.frombuffer(key, dtype="<u4")))
    uniform = float(rng.random())
    reversed_polarity = bool(uniform < probability)
    target = yaw + math.pi * reversed_polarity
    return target, dict(
        stream_version=PRIMARY_YAW_REVERSAL_VERSION,
        probability=probability,
        uniform=uniform,
        reversed=reversed_polarity,
        original_yaw_deg=math.degrees(yaw),
        target_yaw_deg=math.degrees(target),
    )


ROW_AXIAL_STREAM_VERSION = "drg-insertion-row-axial-v1"


def validate_row_axial_kappas(mapping, max_order=3):
    """Normalize explicit order keys, without inventing a concentration."""
    if mapping is None:
        return None
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("Row-axial insertion needs a nonempty order mapping")
    result = {}
    for key, value in mapping.items():
        if isinstance(key, (bool, np.bool_)) or str(key) not in {"2", "3", "4", "5"}:
            raise ValueError("Row-axial insertion supports selected orders 2..5")
        order = int(key)
        if order > max_order or order in result:
            raise ValueError("Row-axial insertion order is unsupported or duplicated")
        try:
            kappa = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Row-axial kappa must be finite and nonnegative"
            ) from error
        if not np.isfinite(kappa) or kappa < 0:
            raise ValueError("Row-axial kappa must be finite and nonnegative")
        result[order] = kappa
    return result


def row_axial_controls_active(mapping):
    return mapping is not None and any(kappa > 0 for kappa in mapping.values())


def _row_axial_stream(seed, organ_id, order, purpose):
    key = hashlib.sha256(
        f"{ROW_AXIAL_STREAM_VERSION}:{seed}:{order}:{organ_id}:{purpose}".encode()
    ).digest()
    return np.random.default_rng(
        np.random.SeedSequence(np.frombuffer(key, dtype="<u4"))
    )


def row_axial_insertion_heading(
    parent_direction, original_heading, kappa, seed=None, organ_id=None, order=None
):
    """Bias azimuth around the projected row axis, preserving the polar draw.

    Invoke AFTER the unchanged original insertion sampler. No shared RNG is
    accepted or consumed. None/zero and geometric degeneracies return the exact
    original vector. This research anisotropy is not a Fichtl coefficient.
    """
    tangent = _basis(parent_direction)[0]
    original = np.asarray(original_heading, dtype=float)
    if (
        original.shape != (3,)
        or not np.isfinite(original).all()
        or not np.isclose(np.linalg.norm(original), 1.0, rtol=0, atol=1e-10)
    ):
        raise ValueError("Original insertion heading must be a finite unit vector")
    if kappa is not None and (not np.isfinite(kappa) or kappa < 0):
        raise ValueError("Row-axial kappa must be finite and nonnegative")
    if kappa is not None and kappa > 0:
        if (
            isinstance(seed, (bool, np.bool_))
            or not isinstance(seed, (int, np.integer))
            or seed < 0
            or isinstance(organ_id, (bool, np.bool_))
            or not isinstance(organ_id, (int, np.integer))
            or organ_id <= 0
            or isinstance(order, (bool, np.bool_))
            or not isinstance(order, (int, np.integer))
            or order not in (2, 3, 4, 5)
        ):
            raise ValueError(
                "Active row-axial insertion requires explicit integer seed/organ/order"
            )
    cosine = float(np.clip(original @ tangent, -1.0, 1.0))
    sine = float(np.linalg.norm(original - cosine * tangent))
    projected = np.array([0.0, 1.0, 0.0]) - tangent[1] * tangent
    rho = float(np.linalg.norm(projected))
    fallback = (
        "disabled"
        if kappa is None
        else (
            "zero_kappa"
            if kappa == 0
            else (
                "parent_parallel_row"
                if rho < 1e-12
                else "zero_polar" if sine < 1e-12 else None
            )
        )
    )
    phi = branch = eta = None
    chosen = original
    if fallback is None:
        first = projected / rho
        # Remove projection-rounding error near the parallel-row threshold.
        first = first - (first @ tangent) * tangent
        first /= np.linalg.norm(first)
        second = np.cross(tangent, first)
        second /= np.linalg.norm(second)
        eta = float(
            _row_axial_stream(seed, organ_id, order, "axial_angle").vonmises(0.0, kappa)
        )
        branch = int(
            _row_axial_stream(seed, organ_id, order, "axial_branch").integers(0, 2)
        )
        phi = float((eta / 2.0 + branch * np.pi) % (2.0 * np.pi))
        chosen = cosine * tangent + sine * (np.cos(phi) * first + np.sin(phi) * second)
        chosen /= np.linalg.norm(chosen)
    report = dict(
        old_heading=original.tolist(),
        new_heading=chosen.tolist(),
        old_polar_angle_deg=float(np.degrees(np.arccos(cosine))),
        new_polar_angle_deg=float(
            np.degrees(np.arccos(np.clip(chosen @ tangent, -1.0, 1.0)))
        ),
        row_projection_norm=rho,
        phi_rad=phi,
        eta_rad=eta,
        axial_branch=branch,
        kappa=None if kappa is None else float(kappa),
        fallback=fallback,
        stream_version=ROW_AXIAL_STREAM_VERSION,
        stream_used=fallback is None,
        stream_identity=dict(
            seed=None if seed is None else int(seed),
            organ_id=None if organ_id is None else int(organ_id),
            order=None if order is None else int(order),
            purposes=["axial_angle", "axial_branch"],
        ),
        old_row_projection=float(original[1]),
        new_row_projection=float(chosen[1]),
    )
    return chosen, report
