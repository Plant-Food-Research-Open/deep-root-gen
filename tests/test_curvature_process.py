"""Analytic OU moments and invented frame geometry, without model simulation."""

import numpy as np
import pytest

from deeprootgen.research.curvature_process import (
    curvature_rng,
    ou_joint_step,
    ou_transition_coefficients,
    spherical_exp_heading,
    validate_curvature_controls,
)
from deeprootgen.research.so4_controlled import minimal_rotation


def test_joint_coefficients_match_independent_analytic_covariance():
    h, q, ell = 0.7, 1.4, 2.3
    a = np.exp(-h / ell)
    coefficients = ou_transition_coefficients(h, q, ell)
    sc = coefficients["curvature_noise_sd"]
    sj1 = coefficients["shared_integral_noise_sd"]
    sj2 = coefficients["independent_integral_noise_sd"]
    assert coefficients["decay"] == pytest.approx(a, rel=1e-14)
    assert coefficients["mean_integral_cm"] == pytest.approx(ell * (1 - a), rel=1e-14)
    assert sc**2 == pytest.approx(q * q * (1 - a * a), rel=1e-13)
    assert sc * sj1 == pytest.approx(q * q * ell * (1 - a) ** 2, rel=1e-13)
    assert sj1**2 + sj2**2 == pytest.approx(
        q * q * (2 * ell * h - 3 * ell * ell + 4 * ell * ell * a - ell * ell * a * a),
        rel=1e-12,
    )


def test_exact_zero_diffusion_deterministic_decay_and_integral_without_rng():
    class NoNoise:
        def normal(self, *args, **kwargs):
            raise AssertionError("Zero diffusion should not need normals")

    current = np.array([0.3, -0.2])
    next_curvature, integral = ou_joint_step(current, 2.0, 0.0, 3.0, NoNoise())
    np.testing.assert_allclose(next_curvature, np.exp(-2.0 / 3.0) * current, rtol=1e-14)
    np.testing.assert_allclose(
        integral, 3.0 * (1 - np.exp(-2.0 / 3.0)) * current, rtol=1e-14
    )
    zero, zero_integral = ou_joint_step(np.zeros(2), 0.01, 0.0, 3.0, NoNoise())
    np.testing.assert_array_equal(zero, [0.0, 0.0])
    np.testing.assert_array_equal(zero_integral, [0.0, 0.0])


@pytest.mark.parametrize("ratio", [1e-14, 1e-10, 1e-6, 1e-4])
def test_small_step_series_preserves_positive_conditional_variance(ratio):
    h, q, ell = 3.0 * ratio, 0.2, 3.0
    coefficients = ou_transition_coefficients(h, q, ell)
    assert np.isfinite(list(coefficients.values())).all()
    assert coefficients["independent_integral_noise_sd"] > 0
    expected_leading = q * h * np.sqrt(ratio / 6.0)
    assert coefficients["independent_integral_noise_sd"] == pytest.approx(
        expected_leading, rel=2e-9
    )
    assert coefficients["curvature_noise_sd"] == pytest.approx(
        q * np.sqrt(2 * ratio), rel=1e-4
    )
    assert coefficients["mean_integral_cm"] == pytest.approx(h, rel=1e-4)


def test_fixed_seed_joint_noise_moments_match_ou_covariance():
    # 60,000 independent invented replicates, fixed seed; 3% covariance
    # tolerance is about five standard errors for individual variances.
    n, h, q, ell = 60000, 0.7, 1.4, 2.3
    current = np.zeros((n, 2))
    next_curvature, integral = ou_joint_step(
        current, h, q, ell, np.random.default_rng(710)
    )
    a = np.exp(-h / ell)
    expected = np.array(
        [
            [q * q * (1 - a * a), q * q * ell * (1 - a) ** 2],
            [
                q * q * ell * (1 - a) ** 2,
                q
                * q
                * (2 * ell * h - 3 * ell * ell + 4 * ell * ell * a - ell * ell * a * a),
            ],
        ]
    )
    for dimension in range(2):
        actual = np.cov(
            np.column_stack([next_curvature[:, dimension], integral[:, dimension]]),
            rowvar=False,
        )
        np.testing.assert_allclose(actual, expected, rtol=0.03, atol=0)
    assert np.max(np.abs(next_curvature.mean(axis=0))) < 0.015
    assert np.max(np.abs(integral.mean(axis=0))) < 0.006


def test_fixed_seed_stationary_covariance_and_integral_variance():
    n, h, q, ell = 60000, 0.8, 0.4, 2.0
    rng = np.random.default_rng(201)
    initial = rng.normal(scale=q, size=(n, 2))
    current, integral = ou_joint_step(initial, h, q, ell, rng)
    expected_integral_variance = (
        2 * q * q * (ell * h - ell * ell * (1 - np.exp(-h / ell)))
    )
    np.testing.assert_allclose(current.var(axis=0), q * q, rtol=0.03, atol=0)
    np.testing.assert_allclose(
        integral.var(axis=0), expected_integral_variance, rtol=0.03, atol=0
    )
    for _ in range(2):
        current, _ = ou_joint_step(current, h, q, ell, rng)
    expected_covariance = q * q * np.exp(-3 * h / ell)
    actual_covariance = np.mean(
        (initial - initial.mean(axis=0)) * (current - current.mean(axis=0)), axis=0
    )
    np.testing.assert_allclose(
        actual_covariance, expected_covariance, rtol=0.04, atol=0
    )


def test_spherical_exponential_straight_quarter_circle_and_uncapped_wrapping():
    moving_frame = np.eye(3)
    np.testing.assert_array_equal(
        spherical_exp_heading(moving_frame, [0.0, 0.0]), [1.0, 0.0, 0.0]
    )
    np.testing.assert_allclose(
        spherical_exp_heading(moving_frame, [np.pi / 2.0, 0.0]),
        [0.0, 1.0, 0.0],
        atol=1e-15,
    )
    np.testing.assert_allclose(
        spherical_exp_heading(moving_frame, [2 * np.pi, 0.0]),
        [1.0, 0.0, 0.0],
        atol=1e-15,
    )
    # Constant signed normal curvature gives a deterministic planar rotation;
    # four quarter-turn chords close a square, not an exact spatial circle.
    position = np.zeros(3)
    for _ in range(4):
        heading = spherical_exp_heading(moving_frame, [np.pi / 2.0, 0.0])
        position += heading
        moving_frame = minimal_rotation(moving_frame[:, 0], heading) @ moving_frame
    np.testing.assert_allclose(position, np.zeros(3), atol=1e-14)
    np.testing.assert_allclose(moving_frame, np.eye(3), atol=1e-14)


def test_keyed_ou_streams_repeat_and_separate_seed_organ_purpose():
    expected = curvature_rng(7, 2, 3, "joint").normal(size=10)
    np.testing.assert_array_equal(
        expected, curvature_rng(7, 2, 3, "joint").normal(size=10)
    )
    for args in (
        (8, 2, 3, "joint"),
        (7, 3, 3, "joint"),
        (7, 2, 4, "joint"),
        (7, 2, 3, "boundary"),
    ):
        assert not np.array_equal(expected, curvature_rng(*args).normal(size=10))


@pytest.mark.parametrize(
    "q,ell,down,row",
    [
        (None, 2.0, 0.0, 0.0),
        (None, None, 0.1, 0.0),
        (None, None, 0.0, 0.1),
        (True, 2.0, 0.0, 0.0),
        (-1.0, 2.0, 0.0, 0.0),
        (0.1, True, 0.0, 0.0),
        (0.1, 0.0, 0.0, 0.0),
        (0.1, -1.0, 0.0, 0.0),
        (0.1, None, 0.0, 0.0),
        (0.1, np.inf, 0.0, 0.0),
        (0.1, 2.0, True, 0.0),
        (0.1, 2.0, 0.0, np.nan),
    ],
)
def test_curvature_controls_fail_closed(q, ell, down, row):
    with pytest.raises(ValueError):
        validate_curvature_controls(q, ell, down, row)


@pytest.mark.parametrize(
    "h,q,ell",
    [
        (0.0, 0.1, 2.0),
        (-1.0, 0.1, 2.0),
        (True, 0.1, 2.0),
        (1.0, True, 2.0),
        (1.0, 0.1, False),
        (1.0, 0.1, np.nan),
    ],
)
def test_transition_rejects_invalid_inputs(h, q, ell):
    with pytest.raises(ValueError):
        ou_transition_coefficients(h, q, ell)


@pytest.mark.parametrize("h,ell", [(1e308, 1e-308), (1e-308, 1e308)])
@pytest.mark.parametrize("q", [0.0, 0.1])
def test_transition_rejects_nonrepresentable_finite_input_ratio(h, ell, q):
    with pytest.raises(ValueError, match="ratio must be representable and finite"):
        ou_transition_coefficients(h, q, ell)
