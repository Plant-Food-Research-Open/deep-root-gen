"""Invented fields and native vine geometries for the frozen 3-D preference."""

import numpy as np
import pytest
from pydantic import ValidationError
from scipy.special import logit

from deeprootgen.data_model.daughter_placement import (
    DaughterPlacement,
    OccurrenceProfile,
    Vineyard3DProfile,
)
from deeprootgen.model.daughter_placement import vineyard_3d_preference
from tests.test_daughter_placement import PROFILE
from tests.test_irrigation import forest, run


FIELD = dict(
    version="vineyard_3d_v1",
    depth_knots_cm=[0.0, 20.0],
    across_period_cm=17.0,
    along_period_cm=23.0,
    fade_cm=10.0,
    coefficients=[[0.1, 0.5, -0.2, 0.1], [-0.1, 0.15, 0.3, -0.2]],
)


def test_depth_interpolation_periodicity_and_tensor_product():
    profile = Vineyard3DProfile(**FIELD)
    depth = np.array([0.0, 10.0, 20.0])[:, None, None]
    x = np.array([0.0, 8.5])[None, :, None]
    y = np.array([0.0, 11.5])[None, None, :]
    scores = vineyard_3d_preference(profile, depth, x, y)
    top = np.array([[0.5, 0.7], [-0.7, -0.1]])
    bottom = np.array([[0.15, -0.05], [0.25, -0.75]])
    np.testing.assert_allclose(
        scores, np.stack([top, (top + bottom) / 2, bottom]), atol=1e-14
    )
    np.testing.assert_allclose(
        vineyard_3d_preference(profile, depth, -x + 34, -y - 23), scores, atol=1e-14
    )
    saturated = Vineyard3DProfile(
        **dict(FIELD, coefficients=[[4.0, 0.0, 0.0, 0.0], [-4.0, 0.0, 0.0, 0.0]])
    )
    np.testing.assert_allclose(
        vineyard_3d_preference(
            saturated, [-10.0, -5.0, 0.0, 10.0, 20.0, 25.0, 30.0], 0.0, 0.0
        ),
        [0.0, 0.5, 1.0, 0.0, -1.0, -0.5, 0.0],
    )


@pytest.mark.parametrize(
    "change",
    [
        dict(depth_knots_cm=[-1.0, 2.0]),
        dict(depth_knots_cm=[1.0]),
        dict(depth_knots_cm=[3.0, 3.0]),
        dict(coefficients=[[1.0, 2.0, 3.0, 4.0]]),
        dict(coefficients=[[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]]),
        dict(across_period_cm=0.0),
        dict(along_period_cm=float("nan")),
        dict(fade_cm=-1.0),
        dict(coefficients=[[float("inf"), 0.0, 0.0, 0.0]] * 2),
        dict(core_ids=[1]),
        dict(version="unknown"),
    ],
)
def test_schema_rejects_invalid_fields(change):
    with pytest.raises(ValidationError):
        DaughterPlacement(profile=dict(FIELD, **change))


def test_profile_versions_round_trip_with_unversioned_legacy_support():
    for data, expected in [(PROFILE, OccurrenceProfile), (FIELD, Vineyard3DProfile)]:
        settings = DaughterPlacement(profile=data)
        assert isinstance(settings.profile, expected)
        assert (
            DaughterPlacement.model_validate_json(settings.model_dump_json())
            == settings
        )
    with pytest.raises(ValidationError):
        Vineyard3DProfile(**FIELD).fade_cm = 1.0


def native_forest():
    config = forest()
    config["parameters"]["min_branching_diameter_cm"] = 0.093
    return config


def test_retention_odds_reproduce_offline_scores_at_realized_births():
    config = native_forest()
    config["daughter_placement"] = dict(mode="retention", strength=0.75, profile=FIELD)
    model = run(config)
    rows = model.result.diagnostics["daughter_placement"]["retentions"]
    depth, x, y, p = (
        np.array([r[k] for r in rows])
        for k in ("depth_cm", "x_cm", "y_cm", "probability")
    )
    score = vineyard_3d_preference(Vineyard3DProfile(**FIELD), depth, x, y)
    assert np.ptp(score) > 0.05
    assert p.mean() == pytest.approx(0.85, abs=1e-12)
    assert np.ptp(logit(p) - 0.75 * np.log(1.5) * score) < 1e-12


def test_integrated_branch_odds_are_invariant_to_crown_translation():
    def simulate(x, y):
        config = native_forest()
        config["parameters"]["root_vary"] = 0.1
        features = config["features"]
        features["curvature"]["settings"]["by_order"]["1"][
            "initial_heading"
        ] = "scaffold_chord"
        features["primary_origins"]["settings"] = dict(
            layout="point", x_cm=x, y_cm=y, depth_cm=12.0
        )
        features["branching"]["settings"]["by_order"]["4"]["branch_probability"] = 0.55
        config["daughter_placement"] = dict(
            profile=FIELD, mode="branch_probability", strength=1.0
        )
        return run(config).result.diagnostics["daughter_placement"]["parents"]

    first, shifted = simulate(0.0, 0.0), simulate(8.0, -11.0)
    assert len(first) == len(shifted) > 0
    assert any(abs(r["probability"] - r["baseline_probability"]) > 0.001 for r in first)
    for a, b in zip(first, shifted):
        assert a["probability"] == pytest.approx(b["probability"], abs=1e-12)
        assert a["multiplier"] == pytest.approx(b["multiplier"], abs=1e-12)
        assert a["selected"] == b["selected"]


def test_redistribution_preserves_count_and_anchored_first_birth():
    config = native_forest()
    baseline = run(config)
    config["daughter_placement"] = dict(
        profile=FIELD, mode="redistribute", strength=1.0
    )
    guided = run(config)
    births = sum(
        len(r["births"])
        for r in guided.result.diagnostics["daughter_placement"]["parents"]
    )
    assert births > 0
    for before, after in zip(baseline.organs[4], guided.organs[4], strict=True):
        assert len(before.child_organs) == len(after.child_organs)
        if before.child_organs:
            np.testing.assert_array_equal(
                before.child_organs[0].axis_state.curve.points,
                after.child_organs[0].axis_state.curve.points,
            )
