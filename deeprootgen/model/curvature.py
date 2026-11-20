"""Unselected transported OU curvature primitives for optional research replay.

The scalar OU transition and its joint arc integral are exact in their moving
coordinates. Spherical heading/chord integration remains a numerical spatial
construction. q is stationary per-component rad/cm; ell and h are cm.
"""

import hashlib

import numpy as np

VERSION = "so4-physical-ou-curvature-v1"


def _number(value, name, positive=False):
    if (
        isinstance(value, (bool, np.bool_))
        or not isinstance(value, (int, float, np.integer, np.floating))
        or not np.isfinite(value)
        or value < 0
        or (positive and value == 0)
    ):
        raise ValueError(
            f"{name} must be a finite {'positive' if positive else 'nonnegative'} number"
        )
    return float(value)


def validate_curvature_controls(q, ell, downward_drift=0.0, row_drift=0.0):
    """Require paired active controls; inactive drift/ell cannot act silently."""
    downward = _number(downward_drift, "tropism_drift_rad_cm")
    row = _number(row_drift, "row_drift_rad_cm")
    if q is None:
        if ell is not None or downward != 0 or row != 0:
            raise ValueError(
                "Inactive OU curvature forbids correlation length and nonzero drift"
            )
        return None
    return dict(
        curvature_sd_rad_cm=_number(q, "curvature_sd_rad_cm"),
        correlation_length_cm=_number(ell, "correlation_length_cm", positive=True),
        tropism_drift_rad_cm=downward,
        row_drift_rad_cm=row,
    )


def curvature_rng(seed, organ_id, step_index, purpose):
    """Versioned latent/boundary streams independent of graph cuts and IDs."""
    key = hashlib.sha256(
        f"{VERSION}:{seed}:{organ_id}:{step_index}:{purpose}".encode()
    ).digest()
    return np.random.default_rng(
        np.random.SeedSequence(np.frombuffer(key, dtype="<u4"))
    )


def ou_transition_coefficients(h, q, ell):
    """Stable Cholesky factors of joint (curvature innovation, arc integral).

    Returns c_next=a*c+s_c*z1 and J=m*c+s_shared*z1+s_independent*z2.
    Independent normals z1/z2 per component produce the required covariance.
    The small-x conditional integral variance uses the series of
    [2*x-4*tanh(x/2)]/x**2, avoiding subtraction of nearly equal numbers.
    """
    h = _number(h, "h", positive=True)
    q = _number(q, "q")
    ell = _number(ell, "ell", positive=True)
    x = h / ell
    if not np.isfinite(x) or x <= 0:
        raise ValueError("Positive h/ell ratio must be representable and finite")
    one_minus = -np.expm1(-x)
    decay = np.exp(-x)
    mean_integral = h * (one_minus / x)
    if q == 0:
        return dict(
            decay=float(decay),
            mean_integral_cm=float(mean_integral),
            curvature_noise_sd=0.0,
            shared_integral_noise_sd=0.0,
            independent_integral_noise_sd=0.0,
        )
    curvature_sd = q * np.sqrt(one_minus * (2.0 - one_minus))
    shared_sd = q * mean_integral * np.sqrt(one_minus / (2.0 - one_minus))
    if x < 0.01:
        conditional_ratio = x * (
            1.0 / 6.0
            + x * x * (-1.0 / 60.0 + x * x * (17.0 / 10080.0 - x * x * 31.0 / 181440.0))
        )
    else:
        conditional_ratio = (2.0 - 4.0 * np.tanh(x / 2.0) / x) / x
    independent_sd = q * h * np.sqrt(conditional_ratio)
    coefficients = dict(
        decay=float(decay),
        mean_integral_cm=float(mean_integral),
        curvature_noise_sd=float(curvature_sd),
        shared_integral_noise_sd=float(shared_sd),
        independent_integral_noise_sd=float(independent_sd),
    )
    if not np.isfinite(list(coefficients.values())).all():
        raise ValueError("OU coefficients exceed finite numeric range")
    return coefficients


def ou_joint_step(curvature, h, q, ell, rng):
    """Joint next curvature and integral; accepts (...,2) vectors for probes."""
    curvature = np.asarray(curvature, dtype=float)
    if (
        curvature.ndim < 1
        or curvature.shape[-1] != 2
        or not np.isfinite(curvature).all()
    ):
        raise ValueError("Expected finite two-component curvature")
    coefficients = ou_transition_coefficients(h, q, ell)
    if q == 0:
        # Deterministic decay also supports explicit analytic nonstationary tests.
        return (
            coefficients["decay"] * curvature,
            coefficients["mean_integral_cm"] * curvature,
        )
    z1, z2 = rng.normal(size=(2, *curvature.shape))
    next_curvature = (
        coefficients["decay"] * curvature + coefficients["curvature_noise_sd"] * z1
    )
    integral = (
        coefficients["mean_integral_cm"] * curvature
        + coefficients["shared_integral_noise_sd"] * z1
        + coefficients["independent_integral_noise_sd"] * z2
    )
    if not np.isfinite(next_curvature).all() or not np.isfinite(integral).all():
        raise ValueError("OU state/integral exceeds finite numeric range")
    return next_curvature, integral


def spherical_exp_heading(moving_frame, normal_angle_rad):
    """Spherical exponential, without an angle cap, in an orthonormal frame."""
    moving_frame = np.asarray(moving_frame, dtype=float)
    angle = np.asarray(normal_angle_rad, dtype=float)
    if (
        moving_frame.shape != (3, 3)
        or angle.shape != (2,)
        or not np.isfinite(moving_frame).all()
        or not np.isfinite(angle).all()
        or not np.allclose(moving_frame.T @ moving_frame, np.eye(3), rtol=0, atol=1e-10)
        or not np.isclose(np.linalg.det(moving_frame), 1.0, rtol=0, atol=1e-10)
    ):
        raise ValueError("Expected proper moving frame and finite two-component angle")
    theta = np.hypot(angle[0], angle[1])
    if not np.isfinite(theta):
        raise ValueError("Integrated turn exceeds finite numeric range")
    if theta == 0:
        return moving_frame[:, 0].copy()
    proposed = np.cos(theta) * moving_frame[:, 0] + np.sin(theta) * (
        moving_frame[:, 1:] @ (angle / theta)
    )
    return proposed / np.linalg.norm(proposed)
