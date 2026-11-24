"""Synthetic row-alignment checks at the numerical and engine entrypoints."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import resolve_config
from deeprootgen.model.cohort_geometry import integrate_curve
from deeprootgen.model.row_alignment import ROW_AXIS, align_heading
from tests.test_schema4_branching_receipts import document, five_orders, run


@pytest.mark.parametrize("sign", [-1., 1.])
def test_alignment_is_axial_and_exact_for_an_isolated_step(sign):
    axis = np.asarray(ROW_AXIS)
    h = np.array([.8, .6 * sign, 0.])
    exposure = .4
    transverse = .8 * np.exp(-exposure)
    expected = np.array([transverse, .6 * sign, 0.]) / np.hypot(transverse, .6)
    result = align_heading(h, axis, exposure)
    np.testing.assert_allclose(result, expected, rtol=1e-12, atol=1e-12)
    np.testing.assert_array_equal(result, align_heading(h, -axis, exposure))
    np.testing.assert_allclose(result, align_heading(align_heading(h, axis, .17), axis, .23), atol=1e-12)
    assert np.linalg.norm(result) == pytest.approx(1., abs=1e-12)
    assert sign * result[1] > .6


@pytest.mark.parametrize("heading", [(.6, 0., .8), (0., 1., 0.), (0., -1., 0.)])
def test_exact_fixed_headings(heading):
    h = np.asarray(heading)
    np.testing.assert_array_equal(align_heading(h, ROW_AXIS, .3), h)


@pytest.mark.parametrize("strength", [float("nan"), float("inf"), -.1, .25001])
def test_invalid_row_alignment_fails_at_config_resolution(strength):
    config = five_orders()
    config["features"]["curvature"]["settings"]["by_order"]["2"]["row_alignment_per_cm"] = strength
    with pytest.raises(ValueError, match="row_alignment_per_cm"):
        resolve_config(config)


def test_omitted_disabled_and_zero_keep_existing_geometry_and_streams():
    config = five_orders()
    prepared = deepcopy(config)
    prepared["features"]["curvature"]["settings"]["by_order"]["2"]["row_alignment_per_cm"] = 0.
    baseline, zero = run(config), run(prepared)
    for left, right in zip(baseline.G.as_df(), zero.G.as_df()):
        pd.testing.assert_frame_equal(left, right, check_exact=True)
    assert baseline.result.metadata["root_summary"] == zero.result.metadata["root_summary"]
    assert baseline.result.metadata["effective_model_sha256"] == zero.result.metadata["effective_model_sha256"]
    assert baseline.rng.bit_generator.state == zero.rng.bit_generator.state
    assert baseline.streams.issued == zero.streams.issued
    assert [rng.bit_generator.state for rng in baseline.streams._cache.values()] == [
        rng.bit_generator.state for rng in zero.streams._cache.values()
    ]
    dormant = document("synthetic_minimal")
    prepared = deepcopy(dormant)
    prepared["features"]["curvature"] = dict(
        enabled=False, settings={"by_order": {"2": {"row_alignment_per_cm": 8.0}}}
    )
    for left, right in zip(run(dormant).G.as_df(), run(prepared).G.as_df()):
        pd.testing.assert_frame_equal(left, right, check_exact=True)
    assert resolve_config(dormant).hashes["effective_model_sha256"] == resolve_config(prepared).hashes[
        "effective_model_sha256"
    ]


def test_reflection_downward_drift_and_step_refinement():
    def trajectory(step, *, downward=0., q=0., initial=(.8, .6, 0.)):
        return integrate_curve(8., [0., 0., 0.], initial, step, q, 2., downward,
                               np.random.default_rng(821), row_alignment_per_cm=.15)

    coarse = trajectory(.5)[1][-1]
    fine = trajectory(.25)[1][-1]
    reference = trajectory(.015625)[1][-1]
    error = np.linalg.norm(fine - reference)
    assert error < .08
    assert error < .55 * np.linalg.norm(coarse - reference)
    arc, points, reflections = trajectory(.5, downward=.01, q=.03, initial=(.6, .48, .64))
    assert reflections > 0 and np.max(points[:, 2]) <= 0.
    np.testing.assert_allclose(np.linalg.norm(np.diff(points, axis=0), axis=1), np.diff(arc), atol=1e-12)


def test_extra_material_cuts_do_not_change_aligned_physical_axes():
    config = five_orders()
    config["features"]["curvature"]["settings"]["by_order"]["2"]["row_alignment_per_cm"] = .11
    normal = run(config)
    config["parameters"]["threshold_root_diameter_cm"] = .135
    split = run(config)
    assert len(normal.G.nodes) != len(split.G.nodes)
    assert normal.streams.issued == split.streams.issued
    for group, other in zip(normal.organs.values(), split.organs.values()):
        assert len(group) == len(other)
        for left, right in zip(group, other):
            a, b = left.axis_state.curve, right.axis_state.curve
            np.testing.assert_array_equal(a.stations, b.stations)
            np.testing.assert_array_equal(a.points, b.points)
            assert left.mass == pytest.approx(right.mass, rel=1e-12)
            assert left.get_lengths().sum() == pytest.approx(right.get_lengths().sum(), rel=1e-12)
    for organ in normal.organs[2]:
        receipt = organ.axis_state.curve.receipt["row_alignment"]
        assert receipt["law"] == "nematic_heading_v1" and receipt["axis"] == [0., 1., 0.]
        assert 0. <= receipt["length_weighted_squared_row_component"] <= 1.
