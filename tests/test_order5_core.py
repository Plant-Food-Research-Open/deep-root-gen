"""Invented order-five topology; no observations or fitted coefficients."""

import copy

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import RootSimulationModel
from deeprootgen.model import RootSystemSimulation
from deeprootgen.research.so4_controlled import (
    construct_skeleton,
    digest,
    replay_arm,
    Skeleton,
    validate_geometry,
)
from deeprootgen.research.construction_step_replay import replay_construction_steps
from deeprootgen.utils.order_controls import (
    plan_child_quotas,
    validate_higher_order_tropism,
)
from tests.test_construction_step_replay import parameters as base_parameters

POLICY = "minimum_angle_projection"
COUNTS = {1: 2, 2: 3, 3: 4, 4: 2, 5: 1}


def parameters(grid=True, **updates):
    values = dict(
        max_order=5,
        inner_root_num=1,
        outer_root_num=1,
        research_current_length_grid="construction_steps_v1" if grid else None,
        research_root_counts_by_order=COUNTS,
        research_higher_order_tropism={
            4: dict(theta_deg=35.0, theta_sd_deg=2.0, probability_down=0.8, trials=1.0),
            5: dict(theta_deg=25.0, theta_sd_deg=0.0, probability_down=0.9, trials=0.5),
        },
        research_current_length_cdfs_cm={
            order: dict(lengths_cm=[float(7 - order)], cumulative_probabilities=[1.0])
            for order in range(2, 6)
        },
    )
    values.update(updates)
    return base_parameters(**values)


def assert_graph(nodes, edges):
    graph = nx.DiGraph(
        edges[["parent_id", "child_id"]].itertuples(index=False, name=None)
    )
    assert nx.is_directed_acyclic_graph(graph) and nx.is_weakly_connected(graph)
    assert [node for node, degree in graph.in_degree if degree == 0] == [0]
    assert (
        nodes.loc[nodes.order.gt(0)].groupby("order").organ_id.nunique().to_dict()
        == COUNTS
    )
    assert np.isfinite(nodes[["x", "y", "z", "length", "diameter"]]).all().all()
    for order in range(2, 6):
        np.testing.assert_allclose(
            nodes.loc[nodes.order.eq(order)].groupby("organ_id").length.sum(),
            7 - order,
            rtol=0,
            atol=1e-8,
        )
    validate_geometry(nodes, edges, 20.0)


@pytest.mark.parametrize("grid", [False, True])
def test_count_conditioned_order5_replay_is_finite_connected_deterministic(grid):
    p = parameters(grid)
    first, second = construct_skeleton(p, 42), construct_skeleton(p, 42)
    assert first.sha256 == second.sha256
    assert_graph(
        pd.DataFrame(first.payload["nodes"]), pd.DataFrame(first.payload["edges"])
    )
    replay = replay_construction_steps if grid else replay_arm
    outputs = [replay(first, "D", p.model_dump(), POLICY) for _ in range(2)]
    assert_graph(outputs[0]["nodes"], outputs[0]["edges"])
    pd.testing.assert_frame_equal(outputs[0]["nodes"], outputs[1]["nodes"])
    assert outputs[0]["diagnostics"] == outputs[1]["diagnostics"]
    assert outputs[0]["diagnostics"]["count_conditioning"][
        "realized_counts_by_order"
    ] == {str(k): v for k, v in COUNTS.items()}


def test_native_order5_has_explicit_direction_controls():
    p = parameters(False)
    sim = RootSystemSimulation(random_seed=42)
    sim.run(p)
    nodes, edges = sim.G.as_df()
    assert_graph(nodes, edges)
    assert set(sim.tropism_diagnostics["by_order"]) == {"2", "3", "4", "5"}


@pytest.mark.parametrize(
    "updates",
    [
        {"research_higher_order_tropism": None},
        {
            "research_higher_order_tropism": {
                4: dict(theta_deg=20, theta_sd_deg=1, probability_down=0.5, trials=1)
            }
        },
        {"research_root_counts_by_order": {**COUNTS, 5: 0}},
        {"research_root_counts_by_order": {**COUNTS, 5: 1.0}},
        {"research_root_counts_by_order": {**COUNTS, 6: 1}},
        {"research_root_counts_by_order": {1: 2, 2: 3, 3: 4, 4: 2}},
        {"research_root_counts_by_order": {**COUNTS, 1: 3}},
        {"random_seed": None},
        {
            "research_parent2_branch_zone_cm": dict(
                basal_cm=0.1, apical_cm=0.1, spacing_cm=0.2
            )
        },
        {"research_primary_attachment_distal_fraction": 0.1},
        {"research_tertiary_length_rank_strength": 0.1},
        {
            "research_current_length_cdfs_cm": {
                2: dict(lengths_cm=[2.0], cumulative_probabilities=[1.0])
            }
        },
    ],
)
def test_unsupported_or_missing_compositions_fail(updates):
    with pytest.raises(ValueError):
        parameters(**updates)


@pytest.mark.parametrize(
    "field,value",
    [
        ("theta_deg", 91),
        ("theta_sd_deg", -1),
        ("probability_down", 1.1),
        ("trials", 101),
        ("trials", True),
        ("theta_deg", np.nan),
        ("trials", "1"),
    ],
)
def test_higher_order_entries_require_explicit_finite_nonbool_numbers(field, value):
    entry = dict(theta_deg=20.0, theta_sd_deg=0.0, probability_down=0.5, trials=1.0)
    entry[field] = value
    with pytest.raises(ValueError):
        validate_higher_order_tropism({4: entry})


@pytest.mark.parametrize("grid", [False, True])
def test_replays_authenticate_counts_higher_controls_and_provenance(grid):
    p = parameters(grid)
    original = construct_skeleton(p, 42)
    replay = replay_construction_steps if grid else replay_arm
    for change in ["counts", "higher", "receipt", "sites"]:
        skeleton = Skeleton(copy.deepcopy(original.payload), original.sha256)
        settings = p.model_dump()
        if change == "counts":
            settings["research_root_counts_by_order"][5] = 2
        elif change == "higher":
            settings["research_higher_order_tropism"][5]["trials"] = 2.0
        elif change == "receipt":
            skeleton.payload["count_conditioning"]["seed"] = 41
        else:
            next(o for o in skeleton.payload["organs"] if o["order"] == 2)[
                "attachment_arc_cm"
            ] += 0.1
        skeleton.sha256 = digest(skeleton.payload)
        with pytest.raises(ValueError):
            replay(skeleton, "D", settings, POLICY)


def test_inactive_new_fields_are_absent_and_explicit_none_is_identical():
    p = base_parameters()
    q = RootSimulationModel(
        **{
            **p.model_dump(),
            "research_higher_order_tropism": None,
            "research_root_counts_by_order": None,
        }
    )
    first, second = construct_skeleton(p, 42), construct_skeleton(q, 42)
    assert first.sha256 == second.sha256
    assert "research_higher_order_tropism" not in first.payload["parameters"]
    assert "research_root_counts_by_order" not in first.payload["parameters"]
    assert "count_conditioning" not in first.payload


def test_quota_planner_balances_totals_and_uses_no_shared_rng():
    a = plan_child_quotas(42, 4, 11, 7)
    assert a == plan_child_quotas(42, 4, 11, 7)
    assert sum(a) == 7 and max(a) - min(a) <= 1
    assert plan_child_quotas(42, 3, 2, 4) == [2, 2]


def test_explicit_order5_sigma_row_and_exact_json_keys():
    p = parameters(
        research_fichtl_sigma_by_order={"4": 0.0, "5": 0.2},
        research_insertion_row_axial_kappa={"4": 2.0, "5": 3.0},
        research_root_counts_by_order={str(k): v for k, v in COUNTS.items()},
    )
    result = replay_construction_steps(
        construct_skeleton(p, 42), "D", p.model_dump(), POLICY
    )
    assert set(result["diagnostics"]["order_sigma_control"]) == {"2", "3", "4", "5"}
    receipts = result["diagnostics"]["organs"]
    assert all(
        "row_axial_insertion" in receipt
        for receipt in receipts
        if receipt["order"] in (4, 5)
    )
    assert_graph(result["nodes"], result["edges"])


def test_conditioned_sites_bypass_spacing_growth_and_preserve_parent_curve(monkeypatch):
    from deeprootgen.model.root import RootOrgan
    from deeprootgen.model.hgraph import RootSystemGraph
    from deeprootgen.data_model import RootTypeModel

    p = parameters(False, interbranch_distance=1e10, growth_sec_root=0.99)
    sim = RootSystemSimulation(random_seed=42)
    organ = RootOrgan(
        sim.G.base_node,
        p,
        RootTypeModel(
            root_type="structural", order_type="primary", position_type="inner"
        ),
        "toy",
        np.random.default_rng(42),
    )
    organ._conditioned_child_quota = 5
    monkeypatch.setattr(
        organ,
        "_draw_lateral_count",
        lambda: pytest.fail("Quota mode consumed legacy count draws"),
    )
    xyz = np.array([[3.0, 0.0, 0.0], [3.0, 4.0, 0.0]])
    diameters, lengths, coords, attachments = organ._prepare_branch_nodes(
        np.array([0.2, 0.1]), np.array([3.0, 4.0]), xyz
    )
    assert len(attachments) == 5
    assert lengths.sum() == pytest.approx(7.0, abs=1e-8)
    assert any(np.array_equal(point, xyz[0]) for point in coords)
    np.testing.assert_array_equal(coords[-1], xyz[-1])
    cumulative = np.cumsum(lengths)
    np.testing.assert_allclose(
        cumulative[attachments],
        0.4 * 7 + (np.arange(5) + 0.5) * (0.9 - 0.4) * 7 / 5,
        rtol=0,
        atol=1e-8,
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"random_seed": True},
        {"random_seed": 42.0},
        {
            "research_current_length_cdfs_cm": {
                2.0: dict(lengths_cm=[2.0], cumulative_probabilities=[1.0])
            }
        },
        {
            "research_higher_order_tropism": {
                4: dict(
                    theta_deg=20,
                    theta_sd_deg=0,
                    probability_down=0.5,
                    trials=1,
                    sigma=0.1,
                )
            }
        },
    ],
)
def test_controls_fail_before_lossy_schema_coercion(updates):
    with pytest.raises(ValueError):
        parameters(**updates)


def test_missing_constructor_seed_does_not_bypass_active_count_controls():
    sim = object.__new__(RootSystemSimulation)
    with pytest.raises(ValueError, match="Research keyed initialization"):
        sim._validate_primary_yaw_seed(parameters(False))
    sim.random_seed = 43
    with pytest.raises(ValueError, match="matching explicit"):
        sim._validate_primary_yaw_seed(parameters(False))
