"""Synthetic checks for random angular and arclength stratification."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import resolve_config
from deeprootgen.model.sibling_placement import sector_bearings, transported_normals
import json
from pathlib import Path
from deeprootgen.model import RootSystemSimulation

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def document(name):
    return json.loads((EXAMPLES / f"{name}.json").read_text())


def run(config):
    model = RootSystemSimulation(random_seed=config["random_seed"])
    model.run(config)
    return model


def three_orders():
    value = document("design/native_features_fully_replaced")
    parameters = value["parameters"]
    parameters.update(
        max_order=3, root_vary=0.0, primary_root_count=3, outer_primary_fraction=0.5
    )
    for key in [name for name in parameters if name.startswith("fichtl_")]:
        parameters.pop(key)
    features = value["features"]
    features["cohort_maturity"]["enabled"] = False
    features["lengths"]["settings"]["by_order"] = {
        str(order): 5.0 for order in range(1, 4)
    }
    law = dict(
        law="first_branch_and_daughter_count",
        branch_probability=1.0,
        first_branch_cm=dict(mean=1.0, sd=0.0, min=1.0, max=1.0),
        daughter_probabilities=[1.0],
    )
    features["branching"]["settings"]["by_order"] = {
        str(order): deepcopy(law) for order in range(1, 3)
    }
    return value


def siblings():
    cfg = three_orders()
    cfg["parameters"]["min_branching_diameter_cm"] = 0.0
    cfg["features"]["branching"]["settings"]["by_order"]["2"][
        "daughter_probabilities"
    ] = [0.0] * 5 + [1.0]
    return cfg


def test_random_phase_jitter_and_frame_transport():
    rng = np.random.default_rng(984)
    angles = np.array([sector_bearings(6, rng) for _ in range(1500)])
    assert np.max(abs(np.exp(1j * angles).mean(axis=0))) < 0.09
    # One point per sector implies no circular gap can exceed two sector widths.
    ordered = np.sort(angles % (2 * np.pi), axis=1)
    gaps = np.diff(np.column_stack((ordered, ordered[:, 0] + 2 * np.pi)), axis=1)
    assert gaps.max() < 4 * np.pi / 6
    t, u = transported_normals(
        np.array([[0.0, 0.0, 1.0], [0.01, 0.0, 1.0], [0.0, 0.01, 1.0]])
    )
    np.testing.assert_allclose((t * u).sum(1), 0.0, atol=1e-12)
    np.testing.assert_allclose(np.linalg.norm(u, axis=1), 1.0)
    assert np.min((u[1:] * u[:-1]).sum(1)) > 0.999


def test_daughter_bearings_change_on_fixed_scaffold_with_matched_polar_angle():
    cfg = siblings()
    ref = run(cfg)
    law = cfg["features"]["curvature"]["settings"]["by_order"]["3"]
    law["sibling_sectors"] = dict(window_cm=15.0, fraction=0.0)
    same = run(cfg)
    for a, b in zip(ref.G.as_df(), same.G.as_df()):
        pd.testing.assert_frame_equal(a, b, check_exact=True)
    assert ref.streams.issued == same.streams.issued
    law["sibling_sectors"]["fraction"] = 1.0
    alt = run(cfg)
    repeat = run(cfg)
    for a, b in zip(alt.G.as_df(), repeat.G.as_df()):
        pd.testing.assert_frame_equal(a, b, check_exact=True)
    for order in range(1, 3):
        for a, b in zip(ref.organs[order], alt.organs[order]):
            np.testing.assert_array_equal(
                a.axis_state.curve.points, b.axis_state.curve.points
            )
    assert len(ref.organs[3]) == len(alt.organs[3]) > 6
    for a, b in zip(ref.organs[3], alt.organs[3]):
        left, right = a.axis_state.curve, b.axis_state.curve
        np.testing.assert_array_equal(left.points[0], right.points[0])
        np.testing.assert_array_equal(left.stations, right.stations)
        assert right.receipt["sibling_sector_applied"]
        parent = b.parent_node.organ.axis_state.curve
        arc = b.parent_node.organ.segments.index(b.parent_node)
        # Materialization can insert parent vertices. Locate the original
        # attachment by its exact station along the emitted polyline.
        distance = np.cumsum(b.parent_node.organ.get_lengths())[arc]
        j = np.argmin(abs(parent.construction_arcs - distance))
        tangent = parent.tangent(parent.construction_arcs[j])
        heading_a = np.array(left.receipt["initial_heading_unit"])
        heading_b = np.array(right.receipt["initial_heading_unit"])
        assert tangent @ heading_a == pytest.approx(tangent @ heading_b, abs=1e-10)
        assert not np.allclose(heading_a, heading_b)


def test_stratified_attachment_retains_first_site_count_and_uses_each_interval():
    cfg = siblings()
    law = cfg["features"]["branching"]["settings"]["by_order"]["2"]
    law["stratify_distal_sites"] = True
    model = run(cfg)
    for parent in model.organs[2]:
        first, *tail = parent.plan["sites"]
        assert first == 1.0 and len(tail) == 5
        length = parent.axis_state.curve.stations[-1]
        cells = np.floor((np.array(tail) - first) / (length - first) * len(tail))
        np.testing.assert_array_equal(cells, np.arange(5))
    bad = deepcopy(cfg)
    bad["features"]["curvature"]["settings"]["by_order"]["1"]["sibling_sectors"] = dict(
        window_cm=15.0, fraction=0.5
    )
    with pytest.raises(ValueError, match="lateral insertion_angle"):
        resolve_config(bad)


def test_terminal_recruitment_preserves_parents_and_uses_birth_depth():
    from scripts.research.realize_terminal_recruitment import retained_terminals

    ids = np.arange(20000)
    depths = np.repeat([0.0, 130.0], len(ids) // 2)
    orders = np.full(len(ids), 5)
    orders[:100] = 4
    keep = retained_terminals(orders, ids, depths, 981, 0.4, 30.0)
    assert keep[:100].all()
    assert 0.97 < keep[:10000].mean() < 1.0
    assert 0.38 < keep[10000:].mean() < 0.42
    reverse = retained_terminals(orders[::-1], ids[::-1], depths[::-1], 981, 0.4, 30.0)
    np.testing.assert_array_equal(keep, reverse[::-1])
    assert retained_terminals(orders, ids, depths, 981, 1.0, 30.0).all()
