"""Affine synthetic projections with independently known score and feasibility."""

import numpy as np
import pandas as pd
import pytest

from deeprootgen.research.core_placement_cost import (
    _depth_projection,
    _tube_weights,
    score_core_placement,
)
from deeprootgen.research.core_response_surface import (
    _physical_gradient,
    fit_core_response_surface,
)


def _training(values):
    lower = -30 * np.arange(1, len(values) + 1)
    return pd.DataFrame(
        dict(
            core_id="a",
            z_lower_cm=lower,
            z_upper_cm=lower + 30,
            core_volume_cm3=10,
            rld_est=values,
        )
    )


def _fit(training, offset, design, base=7, gradient=None, **kwargs):
    return fit_core_response_surface(
        training,
        offset,
        design,
        base,
        np.zeros(design.shape[1]) if gradient is None else gradient,
        **{"horizontal_penalty": 0, "depth_penalty": 0, **kwargs}
    )


def test_recover_two_training_sections_and_unchanged_score():
    data = _training([0.5, 1.5])
    design = np.zeros((2, 20))
    design[0, 0] = design[1, 4] = 1
    result = _fit(data, [1, 1], design)
    coef = np.array(result["coefficients"]).ravel()
    assert result["success"], result["message"]
    assert result["mass_status"] == "enforced"
    assert result["within_mass_bounds"] and result[
        "attainable_mass_range_kg"
    ] == [7, 7]
    assert result["loss"] < 1e-7
    assert result["loss"] == pytest.approx(
        score_core_placement(data, data, 1 + design @ coef)["loss"]
    )
    np.testing.assert_allclose(coef[[0, 4]], [-0.5, 0.5], atol=1e-6)


def test_field_corner_limits_all_interpolated_preferences():
    data = _training([3.5])
    design = np.zeros((1, 8))
    design[0, :4] = 1  # Section probes the (+1,+1) cosine corner.
    result = _fit(data, [1], design)
    assert result["success"]
    assert result["loss"] == pytest.approx(0.5 * (3.5 - 2) / 3.5, abs=1e-8)
    coef = np.array(result["coefficients"])
    for x in np.linspace(-1, 1, 9):
        for y in np.linspace(-1, 1, 9):
            at_knots = coef @ [1, x, y, x * y]
            assert np.max(np.abs(at_knots)) <= 1 + 1e-10


def test_mass_floor_enforced_and_iteration_limit_retains_feasibility():
    data = _training([1])
    design = np.zeros((1, 8))
    design[0, 0] = 1
    gradient = 2 * design[0]
    result = _fit(data, [1], design, 5.5, gradient)
    assert result["success"]
    assert result["mass_status"] == "enforced"
    assert result["attainable_mass_range_kg"] == [3.5, 7.5]
    assert result["predicted_mass_kg"] == pytest.approx(6)
    assert result["loss"] == pytest.approx(0.125)
    limited = _fit(data, [1], design, 5.5, gradient, maxiter=1)
    assert not limited["success"]
    assert limited["within_mass_bounds"]
    assert np.isfinite(limited["objective"])


def test_infeasible_floor_accounts_for_nonnegative_section_rld():
    data = _training([0.2])
    design = np.zeros((1, 8))
    design[0, 0] = 1
    gradient = -2 * design[0]
    result = _fit(data, [0.2], design, 5, gradient)
    assert result["success"] and result["mass_status"] == "infeasible"
    assert not result["within_mass_bounds"]
    np.testing.assert_allclose(result["attainable_mass_range_kg"], [3, 5.4])
    assert result["predicted_mass_kg"] == pytest.approx(5)
    assert result["score"]["loss"] == pytest.approx(0)
    optional = _fit(data, [0.2], design, 5, gradient, mass_bounds_kg=None)
    assert (
        optional["mass_status"] == "not_requested"
        and optional["within_mass_bounds"] is None
    )


@pytest.mark.parametrize("cap_multiple", [None, 0.4])
@pytest.mark.parametrize("different_sections", [False, True])
def test_physical_score_and_subgradient_against_public_scorer(
    cap_multiple, different_sections
):
    data = _training([1.0, 0.3, 1.6, 0.7])
    data.loc[2:, ["z_lower_cm", "z_upper_cm"]] = data.loc[
        :1, ["z_lower_cm", "z_upper_cm"]
    ].to_numpy()
    data.loc[2:, "core_id"] = "b"
    if different_sections:
        data.loc[2, "z_lower_cm"] = data.loc[3, "z_upper_cm"] = -15
    data["core_volume_cm3"] = [1, 3, 2, 1]
    observed = data.rld_est.to_numpy()
    p = np.array([0.5, 1.5, 1.8, 0.2])
    weights = _tube_weights(data, 0.25)
    mean = weights @ observed

    def expected(v):
        return score_core_placement(
            data, data, v, top30_weight=0.25, cap_multiple=cap_multiple
        )["loss"]

    loss, grad = _physical_gradient(
        p,
        observed,
        weights,
        mean,
        None if cap_multiple is None else mean * cap_multiple,
        weights * observed / mean,
        _depth_projection(data, 0.25),
    )
    assert loss == pytest.approx(expected(p))
    steps = 1e-6 * np.eye(len(p))
    numeric = [
        (expected(p + step) - expected(p - step)) / 2e-6 for step in steps
    ]
    np.testing.assert_allclose(grad, numeric, atol=1e-8)


def test_invalid_response_and_index_alignment():
    data = _training([1])
    with pytest.raises(ValueError, match="design and matching"):
        _fit(data, [1], np.ones((1, 7)))
    with pytest.raises(ValueError, match="index must match"):
        _fit(data, [1], pd.DataFrame(np.ones((1, 8)), index=[2]))


def test_capped_empty_baseline_can_reach_occupied_training_profile():
    data = _training([1, 1])
    design = np.zeros((2, 8))
    design[:, 0] = 2
    result = _fit(data, [0, 0], design, cap_multiple=0.2)
    assert result["success"], result["message"]
    assert result["loss"] < 1e-7
    assert result["max_abs_corner"] <= 1


def test_training_projection_rank_excludes_aliases_with_depth_and_other_horizontal_terms():
    data = _training([1, 1, 1, 1])
    design = np.zeros((4, 8))
    design[:, 0] = 1  # One independent depth-intercept column.
    design[:, 4] = 2
    design[:, 1] = -3  # Purely a multiple of the depth column.
    design[:, 2] = [1, -1, 0, 0]
    design[:, 7] = 2 * design[:, 2]
    result = _fit(data, [1, 1, 1, 1], design)
    assert (
        result["depth_response_rank"]
        == result["horizontal_residual_rank"]
        == 1
    )
    assert result["horizontal_column_count"] == 6
    assert result["response_rank_tolerance"] > 0
