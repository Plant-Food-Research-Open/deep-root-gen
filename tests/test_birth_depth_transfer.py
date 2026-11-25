"""Invented paired forests for depth-dependent, count-conserving daughter births."""

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import resolve_config
from deeprootgen.data_model.simulation_form import (
    simulation_controls,
    simulation_document,
)
from deeprootgen.model import RootSystemSimulation
from tests.test_irrigation import forest, run


TRANSFER = dict(
    parent_orders=[1, 2, 3],
    shallow_depth_cm=12.5,
    deep_depth_cm=13.0,
    transfer_probability=1.0,
)


def branching_forest():
    value = forest()
    value["features"]["branching"]["settings"]["by_order"]["1"][
        "daughter_probabilities"
    ] = [0] * 5 + [1.0]
    value["parameters"]["min_branching_diameter_cm"] = 0.093
    return value


def test_transfer_preserves_anchors_material_budget_and_descendant_connections():
    value = branching_forest()
    before = run(value)
    active = dict(value, birth_depth_transfer=TRANSFER)
    after = run(active)
    repeated = run(active)
    for left, right in zip(after.G.as_df(), repeated.G.as_df()):
        pd.testing.assert_frame_equal(left, right, check_exact=True)
    assert after.rng.bit_generator.state == before.rng.bit_generator.state
    assert (
        after.result.diagnostics["birth_depth_transfer"]
        == repeated.result.diagnostics["birth_depth_transfer"]
    )
    assert not after.result.organ_table.invalid_root.any()
    report = after.result.diagnostics["birth_depth_transfer"]["by_parent_order"]["1"]
    assert 0 < report["moved"] < report["selected"]
    assert report["shortfall"] == report["selected"] - report["moved"]
    assert report["anchored_shallow"] == len(after.organs[1])
    assert (
        report["shallow_before"] - report["shallow_after"]
        == report["deep_after"] - report["deep_before"]
        == report["moved"]
    )
    cols = ["organ_id", "order", "parent_organ_id", "primary_tree_id"]
    pd.testing.assert_frame_equal(
        before.result.organ_table[cols], after.result.organ_table[cols]
    )
    for col in ("length_cm", "mass_g"):
        np.testing.assert_allclose(
            before.result.organ_table[col], after.result.organ_table[col], rtol=1e-12
        )
    for old, new in zip(before.organs[1], after.organs[1]):
        np.testing.assert_array_equal(
            old.axis_state.curve.points, new.axis_state.curve.points
        )
        np.testing.assert_array_equal(
            old.child_organs[0].axis_state.curve.points,
            new.child_organs[0].axis_state.curve.points,
        )
    changed = []
    for old, new in zip(before.organs[2], after.organs[2]):
        np.testing.assert_array_equal(
            old.axis_state.sampled_lengths_cm, new.axis_state.sampled_lengths_cm
        )
        assert old.axis_state.material == new.axis_state.material
        if not np.array_equal(
            old.axis_state.curve.points[0], new.axis_state.curve.points[0]
        ):
            changed.append(new)
            assert -old.axis_state.curve.points[0, 2] < TRANSFER["shallow_depth_cm"]
            assert -new.axis_state.curve.points[0, 2] > TRANSFER["deep_depth_cm"]
            for child in new.child_organs:
                node = child.parent_node.node_data
                assert node.organ_id == new.axis_state.biological_id
                np.testing.assert_array_equal(
                    child.axis_state.curve.points[0], [node.x, node.y, node.z]
                )
    assert len(changed) == report["moved"]
    assert any(axis.child_organs for axis in changed)


def test_off_replay_and_form_roundtrip():
    value = branching_forest()
    baseline = run(value)
    config = dict(value, birth_depth_transfer=dict(TRANSFER, transfer_probability=0.0))
    off = run(config)
    fields = ["random_seed", "simulation_tag", "advanced_settings"]
    back = simulation_document(dict(zip(fields, simulation_controls(config, fields))))
    assert back["birth_depth_transfer"] == config["birth_depth_transfer"]
    assert "birth_depth_transfer" not in off.result.diagnostics
    assert (
        baseline.result.metadata["effective_model_sha256"]
        == off.result.metadata["effective_model_sha256"]
    )
    assert baseline.result.engine["keyed_streams"] == off.result.engine["keyed_streams"]
    for a, b in zip(baseline.G.as_df(), off.G.as_df()):
        pd.testing.assert_frame_equal(a, b, check_exact=True)


def test_taper_cap_blocks_a_deeper_move_that_would_shrink_the_daughter():
    value = branching_forest()
    taper = value["features"]["taper"]["settings"]["by_order"]
    taper["1"].update(base_cm=0.3, tip_cm=0.1)
    result = run(dict(value, birth_depth_transfer=TRANSFER))
    rows = result.result.diagnostics["birth_depth_transfer"]["by_parent_order"]["1"]
    assert rows["selected"] > 0
    assert rows["shortfall"] == rows["selected"]
    assert rows["moved"] == 0


def test_flat_parent_at_the_exact_forward_diameter_cap_remains_eligible():
    value = branching_forest()
    value["features"]["taper"]["settings"]["by_order"]["1"].update(
        base_cm=0.1, tip_cm=0.1
    )
    assert 0.1 * 0.8 / 0.8 > 0.1  # Rounded inverse would reject the whole parent.
    sim = run(dict(value, birth_depth_transfer=dict(TRANSFER, parent_orders=[1])))
    report = sim.result.diagnostics["birth_depth_transfer"]["by_parent_order"]["1"]
    assert report["moved"] > 0
    assert all(axis.axis_state.material["base"] <= 0.1 * 0.8 for axis in sim.organs[2])


def test_parent_cuts_spend_nodes_and_preserve_the_organ_budget():
    value = branching_forest()
    base = run(value)
    cfg = dict(
        value,
        birth_depth_transfer=TRANSFER,
        limits={"max_organs": len(base.result.organ_table)},
    )
    active = run(cfg)
    moved = sum(
        row["moved"]
        for row in active.result.diagnostics["birth_depth_transfer"][
            "by_parent_order"
        ].values()
    )
    assert len(active.G.nodes) == len(base.G.nodes) + moved
    cfg["limits"]["max_nodes"] = len(active.G.nodes) - 1
    simulation = RootSystemSimulation(random_seed=cfg["random_seed"])
    with pytest.raises(ValueError, match="Node limit exceeded"):
        simulation.run(cfg)
    assert simulation.result is None
    cfg["limits"]["max_nodes"] += 1
    repaired = run(cfg)
    assert len(repaired.G.nodes) == cfg["limits"]["max_nodes"]


def test_unrepresentably_narrow_deep_support_keeps_the_birth_at_its_original_site():
    cfg = branching_forest()
    cfg["features"]["primary_origins"]["settings"]["radius_cm"] = 1.0e6
    reference = run(cfg)
    parent = reference.organs[1][0]
    deepest = -np.min(parent.axis_state.curve.points[:, 2])
    settings = dict(
        TRANSFER,
        parent_orders=[1],
        shallow_depth_cm=deepest - 0.1,
        deep_depth_cm=deepest - 1.0e-8,
    )
    result = run(dict(cfg, birth_depth_transfer=settings))
    rows = result.result.diagnostics["birth_depth_transfer"]["by_parent_order"]["1"][
        "births"
    ]
    affected = [
        r
        for r in rows
        if r["parent_id"] == parent.axis_state.biological_id
        and r["decision"] != "first_accepted_anchor"
    ]
    assert affected and all(
        r["decision"] == "no_eligible_deep_contour" for r in affected
    )
    assert all(r["original_arc_cm"] == r["final_arc_cm"] for r in affected)


def test_poisson_has_exclusions_but_no_fixed_first_anchor():
    value = branching_forest()
    value["features"]["branching"]["settings"]["by_order"]["1"] = dict(
        law="length_poisson_sites_v1",
        mean_spacing_cm=0.6,
        branch_probability=1.0,
        basal_exclusion_cm=1.0,
        apical_exclusion_cm=1.0,
    )
    value["features"]["cohort_maturity"]["settings"]["scale_branch_probability"] = False
    sim = run(dict(value, birth_depth_transfer=TRANSFER))
    report = sim.result.diagnostics["birth_depth_transfer"]["by_parent_order"]["1"]
    assert report["anchored_shallow"] == 0
    assert report["moved"] > 0
    for row in report["births"]:
        parent = sim.organs[1][row["parent_id"] - 1]
        assert 1.0 <= row["final_arc_cm"] < parent.get_lengths().sum() - 1.0


def test_upstream_transfer_and_downstream_sparse_recruitment_compose():
    value = branching_forest()
    value["features"]["primary_origins"]["settings"]["depth_range_cm"] = [105.0, 108.0]
    value["features"]["branching"]["settings"]["by_order"]["4"][
        "branch_probability"
    ] = 0.0
    value.update(
        birth_depth_transfer=dict(
            TRANSFER, shallow_depth_cm=112.5, deep_depth_cm=113.0
        ),
        daughter_placement=dict(
            mode="sparse_depth_balanced",
            parent_order=4,
            spatial_cell_width_cm=10.0,
            strength=1.0,
        ),
    )
    sim = run(value)
    receipts = sim.result.diagnostics
    assert receipts["birth_depth_transfer"]["by_parent_order"]["1"]["moved"] > 0
    recruits = receipts["daughter_placement"]["parents"]
    assert len(sim.organs[5]) == len(recruits) > 0
    assert all(row["births"][0]["depth_cm"] > 90.0 for row in recruits)
    assert not sim.result.organ_table.invalid_root.any()


@pytest.mark.parametrize(
    "updates",
    [
        {"parent_orders": [1, 1]},
        {"parent_orders": [5]},
        {"deep_depth_cm": 11.0},
        {"transfer_probability": 1.1},
    ],
)
def test_invalid_active_settings_fail_at_resolution(updates):
    with pytest.raises(ValueError):
        resolve_config(
            dict(branching_forest(), birth_depth_transfer=dict(TRANSFER, **updates))
        )
