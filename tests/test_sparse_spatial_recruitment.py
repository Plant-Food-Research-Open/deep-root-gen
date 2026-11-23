"""Synthetic spatial balancing and paired sixth-order recruitment checks."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from deeprootgen.data_model.daughter_placement import DaughterPlacement
from deeprootgen.model.daughter_placement import _balanced_cell_selection
from tests.test_irrigation import forest, run


def test_spatial_rounds_spread_births_across_unequal_pools():
    # Four separated clusters of identical XY coordinates, with unequal parent counts.
    group = np.repeat(np.arange(4), [25, 5, 2, 1])
    xy = np.column_stack([100 * group - 150, np.zeros(len(group))])
    for count in (0, 3, 4, 7, 11, len(xy)):
        picked, receipt = _balanced_cell_selection(xy, count, 10., np.random.default_rng(2))
        assert len(np.unique(picked)) == count
        assert receipt["occupied_candidate_cells"] == 4
        assert receipt["occupied_birth_cells"] == min(count, 4)
        if count == 7:
            np.testing.assert_array_equal(np.bincount(group[picked]), [2, 2, 2, 1])
    winners = [
        _balanced_cell_selection(xy, 1, 10., np.random.default_rng(seed))[0][0]
        for seed in range(24)
    ]
    assert set(group[winners]) == {0, 1, 2, 3}


def six_order_forest(depth=110.):
    config = forest()
    config["parameters"].update(max_order=6, min_branching_diameter_cm=.093)
    features = config["features"]
    features.pop("parent_diameter_cap")
    features["primary_origins"]["settings"]["depth_range_cm"] = [depth, depth]
    for feature in features.values():
        orders = feature["settings"].get("by_order")
        if orders:
            orders["6"] = deepcopy(orders["5"])
    features["branching"]["settings"]["by_order"]["5"]["branch_probability"] = 0.
    return config


def simulate(config, strength, balanced):
    settings = dict(parent_order=5, mode="sparse_depth", strength=strength)
    if balanced:
        settings.update(mode="sparse_depth_balanced", spatial_cell_width_cm=15.)
    return run(dict(config, daughter_placement=settings))


@pytest.mark.parametrize("strength", [.5, 1.])
def test_sixth_order_count_scaffold_and_candidate_arcs_are_paired(strength):
    config = six_order_forest()
    baseline = simulate(config, strength, balanced=False)
    balanced = simulate(config, strength, balanced=True)
    repeated = simulate(config, strength, balanced=True)
    old = baseline.result.diagnostics["daughter_placement"]
    new = balanced.result.diagnostics["daughter_placement"]
    assert repeated.result.diagnostics["daughter_placement"] == new
    assert 0 < new["deep_activated_parents"] == old["deep_activated_parents"] == len(balanced.organs[6])
    for before, after in zip(baseline.organs[5], balanced.organs[5], strict=True):
        np.testing.assert_array_equal(before.axis_state.curve.points, after.axis_state.curve.points)

    def births(receipt):
        return {row["parent_id"]: row["births"][0] for row in receipt["parents"]}

    old_births, new_births = births(old), births(new)
    assert len(new_births) == len(balanced.organs[6])
    assert old_births.keys() & new_births.keys()
    for parent in old_births.keys() & new_births.keys():
        assert old_births[parent]["arc_cm"] == new_births[parent]["arc_cm"]
    expected_cells = min(new["deep_activated_parents"], new["occupied_candidate_cells"])
    assert new["occupied_birth_cells"] == expected_cells
    if strength == .5:
        old_xy = np.array([[birth["x_cm"], birth["y_cm"]] for birth in old_births.values()])
        old_cells = np.floor((old_xy - new["grid_origin_offset_cm"]) / 15.)
        assert len(np.unique(old_cells, axis=0)) == 2
        assert new["occupied_birth_cells"] == 3
    assert all(row["depth_cm"] > 90. for row in new_births.values())
    for child in balanced.organs[6]:
        parent = child.parent_node.organ
        birth = new_births[parent.axis_state.biological_id]
        assert birth["daughter_id"] == child.axis_state.biological_id
        assert child.segments[0].node_data.parent_id == child.parent_node.node_data.node_id
        np.testing.assert_allclose(child.axis_state.curve.points[0], [
            birth["x_cm"], birth["y_cm"], -birth["depth_cm"],
        ])
    reference = baseline if strength == 1. else repeated
    for left, right in zip(reference.G.as_df(), balanced.G.as_df(), strict=True):
        pd.testing.assert_frame_equal(left, right, check_exact=True)


def test_absent_deep_contour_and_disabled_mode():
    config = six_order_forest(depth=2.)
    active = simulate(config, 1., balanced=True)
    receipt = active.result.diagnostics["daughter_placement"]
    assert receipt["all_depth_eligible_parents"] > 0
    assert receipt["deep_eligible_parents"] == receipt["occupied_candidate_cells"] == 0
    assert not active.organs[6]
    baseline = run(config)
    disabled = simulate(config, 0., balanced=True)
    assert "daughter_placement" not in disabled.result.diagnostics
    assert disabled.result.metadata["effective_model_sha256"] == baseline.result.metadata["effective_model_sha256"]
    for left, right in zip(disabled.G.as_df(), baseline.G.as_df(), strict=True):
        pd.testing.assert_frame_equal(left, right, check_exact=True)


@pytest.mark.parametrize("mode,width", [
    ("sparse_depth_balanced", None), ("sparse_depth_balanced", 0.),
    ("sparse_depth_balanced", float("inf")), ("sparse_depth", 10.),
])
def test_width_is_positive_finite_and_exclusive_to_balanced_mode(mode, width):
    with pytest.raises(ValidationError, match="spatial_cell_width_cm"):
        DaughterPlacement(mode=mode, spatial_cell_width_cm=width)
