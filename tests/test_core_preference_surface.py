"""Synthetic core geometries with analytic aliasing and smoothing behaviour."""

import json

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model.daughter_placement import Vineyard3DProfile
from deeprootgen.model.daughter_placement import vineyard_3d_preference
from deeprootgen.research.core_preference_surface import (
    fit_core_preference_surface,
)


PERIODS = {"across_period_cm": 300.0, "along_period_cm": 200.0}


def _design():
    rows = []
    for i, (x, y) in enumerate([(0, 0), (0, 100), (150, 0), (150, 100)]):
        cx, cy = np.cos(2 * np.pi * x / 300), np.cos(2 * np.pi * y / 200)
        for depth in (15, 45):
            target = 0.1 + 0.2 * cx - 0.25 * cy + 0.12 * cx * cy
            rows.append((i, depth, x, y, target))
    return pd.DataFrame(
        rows, columns=["core_id", "depth_cm", "cross_cm", "along_cm", "target"]
    )


def test_full_field_has_analytic_ridge_solution_and_runs_natively():
    data = _design()
    penalty = 0.1
    spec = fit_core_preference_surface(
        data,
        **PERIODS,
        depth_knots_cm=[15, 45],
        horizontal_penalty=penalty,
    )
    expected = [0.1, *(np.array([0.2, -0.25, 0.12]) / (1 + 2 * penalty))]
    np.testing.assert_allclose(
        spec["coefficients"], [expected, expected], atol=1e-12
    )
    profile = Vineyard3DProfile.model_validate_json(json.dumps(spec))
    answer = vineyard_3d_preference(
        profile, [15, 30, 45], [0, 300, -300], [0, -200, 200]
    )
    np.testing.assert_allclose(answer, sum(expected))
    repeat = fit_core_preference_surface(
        data.sample(frac=1, random_state=5),
        **PERIODS,
        depth_knots_cm=[15, 45],
        horizontal_penalty=penalty,
    )
    np.testing.assert_allclose(
        repeat["coefficients"], spec["coefficients"], atol=1e-12
    )


def test_depth_only_and_depth_smoothness():
    frame = _design().assign(
        target=lambda d: np.where(d.depth_cm == 15, -1.0, 1.0)
    )
    specs = [
        fit_core_preference_surface(
            frame,
            **PERIODS,
            mode="depth_only",
            depth_knots_cm=[15, 45],
            depth_penalty=penalty,
        )
        for penalty in (0.01, 0.5)
    ]
    for spec, penalty in zip(specs, (0.01, 0.5)):
        coefficients = np.asarray(spec["coefficients"])
        np.testing.assert_array_equal(coefficients[:, 1:], 0)
        np.testing.assert_allclose(
            coefficients[:, 0], np.array([-1, 1]) / (1 + 4 * penalty)
        )


def test_unresolvable_horizontal_directions_are_removed():
    # The diagonal samples confound the two cosine main effects. The product
    # is constant and therefore indistinguishable from the depth intercept.
    diagonal = _design().query("core_id == 0 or core_id == 3").copy()
    diagonal["target"] = np.where(diagonal["cross_cm"].eq(0), 0.75, -0.25)
    fit = fit_core_preference_surface(
        diagonal, **PERIODS, depth_knots_cm=[15, 45]
    )
    coefs = np.asarray(fit["coefficients"])
    assert np.all(coefs[:, 1] > 0)
    np.testing.assert_allclose(coefs[:, 1], coefs[:, 2], atol=1e-12)
    np.testing.assert_allclose(coefs[:, 3], 0, atol=1e-12)

    # With a single position per depth all apparent spatial variation aliases depth.
    confounded = diagonal.loc[
        ((diagonal.depth_cm == 15) == (diagonal.cross_cm == 0))
    ]
    fit = fit_core_preference_surface(
        confounded, **PERIODS, depth_knots_cm=[15, 45]
    )
    np.testing.assert_array_equal(np.asarray(fit["coefficients"])[:, 1:], 0)


def test_weights_balance_tubes_and_zero_weight_tubes_have_no_influence():
    frame = pd.DataFrame(
        dict(
            core_id=["A", "A", "B", "C"],
            depth_cm=15,
            target=[-1, 1, 1, -1],
            volume=[1, 3, 8, 0],
        )
    )
    spec = fit_core_preference_surface(
        frame, **PERIODS, mode="depth_only", weight_column="volume"
    )
    np.testing.assert_allclose(np.array(spec["coefficients"])[:, 0], 0.75)


def test_fit_handles_endpoint_fade_consistently_with_native_evaluation():
    frame = pd.DataFrame(
        dict(core_id=["A", "B"], depth_cm=[0, 150], target=0.2)
    )
    profile = Vineyard3DProfile.model_validate(
        fit_core_preference_surface(frame, **PERIODS, mode="depth_only")
    )
    np.testing.assert_allclose(np.asarray(profile.coefficients)[:, 0], 0.4)
    np.testing.assert_allclose(
        vineyard_3d_preference(profile, frame.depth_cm, 0, 0), frame.target
    )
    with pytest.raises(ValueError, match="inside the profile support"):
        fit_core_preference_surface(
            frame.assign(depth_cm=300), **PERIODS, mode="depth_only"
        )


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"depth_knots_cm": [15, 15]}, "Depth knots"),
        ({"along_period_cm": 0}, "Periods"),
        ({"fade_cm": np.inf}, "Periods"),
        ({"mode": "other"}, "mode"),
    ],
)
def test_invalid_controls(kwargs, match):
    with pytest.raises(ValueError, match=match):
        fit_core_preference_surface(_design(), **{**PERIODS, **kwargs})


def test_invalid_training_data():
    with pytest.raises(ValueError, match="Sample weights"):
        fit_core_preference_surface(
            _design().assign(w=0), **PERIODS, weight_column="w"
        )
    with pytest.raises(ValueError, match="target"):
        fit_core_preference_surface(_design().assign(target=1.1), **PERIODS)
