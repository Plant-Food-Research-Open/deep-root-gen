"""Invented fields and unconstrained native insertion axes for bearing guidance."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import resolve_config
from deeprootgen.data_model.daughter_placement import DaughterPlacement
from deeprootgen.model.daughter_placement import (
    surface_bearing_heading,
    vineyard_3d_preference,
)
from deeprootgen.model.streams import RandomStreams
from tests.test_irrigation import forest, run
from tests.test_vineyard_3d_preference import FIELD


def settings(orders=(2, 3, 4, 5), strength=1.0, coefficients=None):
    field = dict(
        FIELD,
        depth_knots_cm=[0.0, 150.0],
        coefficients=(
            [[0.0, 1.2, 0.8, 0.2], [0.0, 0.8, 0.8, -0.2]]
            if coefficients is None
            else coefficients
        ),
    )
    return dict(
        mode="surface_bearing",
        strength=strength,
        profile=field,
        bearing_orders=list(orders),
    )


def state():
    return SimpleNamespace(
        streams=RandomStreams(3188),
        laws=SimpleNamespace(surface_z_cm=0.0, origins=None),
        vine_origin=None,
    )


def test_draw_frequencies_match_the_softmax_of_the_four_physical_scores():
    system = state()
    placement = DaughterPlacement(**settings())
    tangent = np.array([0.0, 0.0, 1.0])
    bearings = np.array(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, -1.0, 0.0]]
    )
    origin = np.array([4.0, 5.0, -55.0])
    tips = origin + 40.0 * bearings
    scores = vineyard_3d_preference(
        placement.profile, -tips[:, 2], tips[:, 0], tips[:, 1]
    )
    weights = np.exp(2.0 * scores)
    counts = np.zeros(4, dtype=int)
    for oid in range(2400):
        initial = oid % 4
        new, receipt = surface_bearing_heading(
            system, placement, tangent, bearings[initial], origin, 80.0, 2, oid
        )
        final = (initial + receipt["quarter_turns"]) % 4
        np.testing.assert_array_equal(new, bearings[final])
        assert receipt["selected_preference"] >= receipt["native_preference"]
        counts[final] += 1
    np.testing.assert_allclose(
        counts / counts.sum(), weights / weights.sum(), atol=0.025
    )


def test_probe_stops_at_the_tip_and_reflects_crossing_steps_into_soil():
    placement = DaughterPlacement(
        **settings(coefficients=[[0.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]])
    )
    _, receipt = surface_bearing_heading(
        state(),
        placement,
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 0.0, 1.0]),
        np.array([0.0, 0.0, -2.0]),
        6.0,
        2,
        1,
    )
    assert receipt["probe_cm"] == 6.0
    assert receipt["reflected_probes"] == 1
    assert receipt["native_preference"] == pytest.approx(8.0 / 150.0)


def test_disabled_and_neutral_fields_reproduce_native_graph_and_streams():
    config = forest()
    baseline = run(config)
    for opts in [settings(strength=0.0), settings(coefficients=[[0.0] * 4, [0.0] * 4])]:
        actual = run(dict(config, daughter_placement=opts))
        for a, b in zip(actual.G.as_df(), baseline.G.as_df(), strict=True):
            pd.testing.assert_frame_equal(a, b, check_exact=True)
        assert (
            actual.result.engine["keyed_streams"]
            == baseline.result.engine["keyed_streams"]
        )
        if opts["strength"] == 0.0:
            assert (
                actual.result.metadata["effective_model_sha256"]
                == baseline.result.metadata["effective_model_sha256"]
            )


def test_active_bearings_keep_native_polar_draws_and_curvature_streams():
    config = forest()
    native = run(config)
    config["daughter_placement"] = settings()
    guided = run(config)
    repeated = run(config)
    for a, b in zip(guided.G.as_df(), repeated.G.as_df(), strict=True):
        pd.testing.assert_frame_equal(a, b, check_exact=True)
    n_changed = 0
    for order in (2, 3, 4, 5):
        for before, after in zip(
            native.organs[order], guided.organs[order], strict=True
        ):
            original, altered = before.axis_state.curve, after.axis_state.curve
            np.testing.assert_array_equal(original.stations, altered.stations)
            cosines = []
            for daughter in (before, after):
                curve = daughter.axis_state.curve
                parent_curve = daughter.parent_node.organ.axis_state.curve
                sites = parent_curve.construction_arcs
                index = np.argmin(
                    np.linalg.norm(
                        parent_curve.position(sites) - curve.points[0], axis=1
                    )
                )
                tangent = parent_curve.tangent(sites[index], coincidence_cm=1.0e-9)
                cosines.append(tangent @ curve.receipt["initial_heading_unit"])
            assert cosines[0] == pytest.approx(cosines[1], abs=1e-12)
            receipt = altered.receipt["surface_bearing"]
            assert receipt["probe_cm"] == pytest.approx(min(40.0, altered.stations[-1]))
            n_changed += receipt["quarter_turns"] != 0
    assert n_changed > 0
    assert "surface_bearing" not in guided.organs[1][0].axis_state.curve.receipt
    # Recheck the actual generator states after all curves have been integrated.
    for key, generator in native.streams._cache.items():
        assert (
            generator.bit_generator.state
            == guided.streams._cache[key].bit_generator.state
        )


def test_selected_orders_cannot_override_other_active_bearing_controls():
    cfg = forest()
    cfg["daughter_placement"] = settings(orders=[3])
    law = cfg["features"]["curvature"]["settings"]["by_order"]["3"]
    law["sibling_sectors"] = dict(window_cm=15.0, fraction=0.5)
    with pytest.raises(ValueError, match="conflicts"):
        resolve_config(cfg)
    law["sibling_sectors"]["fraction"] = 0.0
    cfg["features"]["insertion"] = dict(
        enabled=True, settings=dict(row_axial_kappa_by_order={"3": 2.0})
    )
    with pytest.raises(ValueError, match="conflicts"):
        resolve_config(cfg)
    cfg["daughter_placement"] = settings(orders=[2])
    resolve_config(cfg)
    cfg["daughter_placement"] = settings(orders=[6])
    with pytest.raises(ValueError, match="order 6"):
        resolve_config(cfg)
    with pytest.raises(ValueError, match="distinct"):
        DaughterPlacement(**settings(orders=(2, 2)))
