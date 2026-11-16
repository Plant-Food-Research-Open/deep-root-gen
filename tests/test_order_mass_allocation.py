"""Invented constant-diameter cm cylinders; no data, simulations or fitting."""

import numpy as np
import pandas as pd
import pytest

from deeprootgen.research.order_mass_allocation import (
    InfeasibleMassBudget, allocate_order_mass, audit_root_mass,
)


def graph(diameters=(.2, .2, .2, .2, .2), lengths=None):
    lengths = (1.,) * len(diameters) if lengths is None else lengths
    rows = [dict(node_id=0, parent_id=-1, plant_id=1, organ_id=0, order=0,
                 x=0., y=0., z=0., diameter=999., length=999.,
                 root_tissue_density=-999., root_type="base", invalid_root=False,
                 segment_rank=0, random_seed=42)]
    for order, (diameter, length) in enumerate(zip(diameters, lengths), 1):
        rows.append(dict(node_id=order, parent_id=0, plant_id=1, organ_id=order, order=order,
                         x=0., y=0., z=-float(length), diameter=diameter, length=777.,
                         root_tissue_density=.25, root_type="structural", invalid_root=False,
                         segment_rank=1, random_seed=42))
    nodes = pd.DataFrame(rows)
    return nodes, edges_of(nodes)


def edges_of(nodes):
    return nodes.loc[nodes.order.gt(0), ["parent_id", "node_id"]].rename(columns={"node_id": "child_id"}).reset_index(drop=True)


def audit(nodes, edges, **kwargs):
    return audit_root_mass(nodes, edges, dry_density_g_cm3=kwargs.pop("dry_density_g_cm3", .25), **kwargs)


def allocate(nodes, edges, **kwargs):
    kwargs.setdefault("groups", [{"orders": [1, 2, 3], "share": .75}, {"orders": [4, 5], "share": .25}])
    return allocate_order_mass(nodes, edges, dry_density_g_cm3=kwargs.pop("dry_density_g_cm3", .25), **kwargs)


def test_analytic_cylinder_mass_geometry_order_and_diameter_classes():
    nodes, edges = graph((.2, .3), (5., 2.))
    result = audit(nodes, edges)
    assert result["totals"]["length_cm"] == 7.
    assert result["totals"]["volume_cm3"] == pytest.approx(np.pi * (.1**2 * 5 + .15**2 * 2))
    assert result["totals"]["mass_g"] == pytest.approx(result["totals"]["volume_cm3"] * .25)
    assert result["totals"]["specific_root_length_cm_g"] == pytest.approx(7 / result["totals"]["mass_g"])
    assert result["by_diameter_class"]["fine"]["length_cm"] == 5.
    assert result["by_diameter_class"]["coarse"]["length_cm"] == 2.
    assert result["by_order"][1]["segment_count"] == 1
    assert result["by_order"][1]["organ_count"] == 1
    assert result["diagnostics"]["base_node_count"] == 1
    assert result["diagnostics"]["density_metadata"] == "matching_nonbase_metadata"


def test_square_law_preserve_total_combined_order45_quarter_and_exact_inputs():
    nodes, edges = graph()
    nodes.index = [8, 7, 6, 5, 4, 3]
    nodes.attrs["source"] = "synthetic only"
    original_nodes, original_edges = nodes.copy(deep=True), edges.copy(deep=True)
    new_nodes, new_edges, diagnostics = allocate(nodes, edges)
    assert diagnostics["achieved_total_g"] == pytest.approx(diagnostics["original_total_g"])
    assert diagnostics["groups"][1]["achieved_share"] == pytest.approx(.25)
    for order in (4, 5):
        record = diagnostics["by_order"][order]
        assert record["achieved_share"] == pytest.approx(.125)  # combined .25, never each .25
        assert record["diameter_scale_factor"] == pytest.approx(np.sqrt(.625))
        assert record["achieved_mass_g"] / record["original_mass_g"] == pytest.approx(record["diameter_scale_factor"]**2)
    assert diagnostics["primary_evidence_would_be_modified"]
    pd.testing.assert_frame_equal(nodes, original_nodes)
    pd.testing.assert_frame_equal(edges, original_edges)
    pd.testing.assert_frame_equal(new_edges, edges)
    pd.testing.assert_frame_equal(new_nodes.drop(columns="diameter"), nodes.drop(columns="diameter"))
    assert new_nodes.loc[new_nodes.order.eq(0), "diameter"].equals(nodes.loc[nodes.order.eq(0), "diameter"])
    assert new_nodes.attrs == nodes.attrs
    assert new_edges is not edges


def test_explicit_total_and_locked_primary_scale_only_unlocked_mass():
    nodes, edges = graph()
    mass = audit(nodes, edges)["totals"]["mass_g"]
    new_nodes, _, diagnostics = allocate(nodes, edges, target_total_g=mass * 2, locked_orders=(1,))
    assert new_nodes.loc[new_nodes.order.eq(1), "diameter"].equals(nodes.loc[nodes.order.eq(1), "diameter"])
    assert not diagnostics["primary_evidence_would_be_modified"]
    assert diagnostics["achieved_total_g"] == pytest.approx(mass * 2)
    assert diagnostics["groups"][0]["achieved_mass_g"] == pytest.approx(mass * 1.5)
    assert diagnostics["by_order"][2]["diameter_scale_factor"] == pytest.approx(np.sqrt(3.25))


def test_locked_mass_exceeding_group_budget_fails_without_mutation():
    nodes, edges = graph((2., .1, .1, .1, .1))
    original = nodes.copy(deep=True)
    with pytest.raises(InfeasibleMassBudget, match="Locked mass exceeds"):
        allocate(nodes, edges, locked_orders=(1,))
    pd.testing.assert_frame_equal(nodes, original)


def test_all_locked_exact_target_succeeds_and_unequal_target_fails():
    nodes, edges = graph((.2,), (1.,))
    groups = [{"orders": [1], "share": 1.}]
    new_nodes, _, diagnostics = allocate(nodes, edges, groups=groups, locked_orders=(1,))
    pd.testing.assert_frame_equal(new_nodes, nodes)
    assert diagnostics["by_order"][1]["diameter_scale_factor"] == 1
    with pytest.raises(InfeasibleMassBudget, match="zero unlocked source"):
        allocate(nodes, edges, groups=groups, locked_orders=(1,), target_total_g=1.)


def test_relative_taper_and_subdivision_invariance():
    nodes, edges = graph((.2,), (10.,))
    groups = [{"orders": [1], "share": 1.}]
    split = nodes.copy()
    split.loc[split.node_id.eq(1), "parent_id"] = 2
    midpoint = split.loc[split.node_id.eq(1)].copy()
    midpoint.loc[:, "node_id"] = 2
    midpoint.loc[:, "parent_id"] = 0
    midpoint.loc[:, "z"] = -4.
    split = pd.concat([split, midpoint], ignore_index=True)
    _, _, original = allocate(nodes, edges, groups=groups, target_total_g=1.)
    new_nodes, _, divided = allocate(split, edges_of(split), groups=groups, target_total_g=1.)
    assert original["original_total_g"] == pytest.approx(divided["original_total_g"])
    assert original["by_order"][1]["diameter_scale_factor"] == pytest.approx(divided["by_order"][1]["diameter_scale_factor"])
    assert divided["after"]["by_order"][1]["organ_count"] == 1
    assert divided["after"]["by_order"][1]["segment_count"] == 2
    split.loc[split.node_id.eq(1), "diameter"] = .1
    new_nodes, _, _ = allocate(split, edges_of(split), groups=groups, target_total_g=1.)
    assert new_nodes.loc[new_nodes.node_id.eq(1), "diameter"].iloc[0] / new_nodes.loc[new_nodes.node_id.eq(2), "diameter"].iloc[0] == pytest.approx(.5)


def test_fine_cutoff_migration_independent_of_root_type_and_root_order():
    nodes, edges = graph((.2,), (10.,))
    total = audit(nodes, edges)["totals"]["mass_g"]
    new_nodes, _, diagnostics = allocate(nodes, edges, groups=[{"orders": [1], "share": 1.}], target_total_g=total * 4)
    assert diagnostics["fine_cutoff_migration_count"] == 1
    assert diagnostics["fine_cutoff_migrations"][0]["original_class"] == "fine"
    assert diagnostics["fine_cutoff_migrations"][0]["allocated_class"] == "coarse"
    assert new_nodes.root_type.equals(nodes.root_type)
    assert diagnostics["after"]["by_diameter_class"]["coarse"]["length_cm"] == 10.


def test_inclusive_cutoff_and_reverse_migration():
    nodes, edges = graph((.25,))
    assert audit(nodes, edges)["by_diameter_class"]["fine"]["segment_count"] == 1
    nodes.loc[nodes.order.eq(1), "diameter"] = .5
    total = audit(nodes, edges)["totals"]["mass_g"]
    _, _, diagnostics = allocate(nodes, edges, groups=[{"orders": [1], "share": 1.}], target_total_g=total / 4)
    assert diagnostics["fine_cutoff_migrations"][0]["allocated_class"] == "fine"


def test_branch_diameter_inversion_diagnosed_never_clamped_and_base_exempt():
    nodes, _ = graph((.1, .3))
    nodes.loc[nodes.node_id.eq(2), "parent_id"] = 1
    nodes.loc[nodes.node_id.eq(2), "z"] = -2.
    edges = edges_of(nodes)
    result = audit(nodes, edges)
    violation = result["diagnostics"]["hierarchy_violations"][0]
    assert violation["child_id"] == 2
    assert violation["parent_attachment_diameter_cm"] == .1
    new_nodes, _, diagnostics = allocate(nodes, edges, groups=[{"orders": [1, 2], "share": 1.}])
    pd.testing.assert_frame_equal(new_nodes, nodes)
    assert diagnostics["hierarchy_violation_count"] == 1
    assert audit(nodes.drop(columns="organ_id"), edges)["diagnostics"]["hierarchy_violation_count"] == 1


def test_hierarchy_uses_first_organ_segment_not_internal_taper_increase():
    nodes, _ = graph((.1, .3))
    nodes.loc[nodes.node_id.eq(2), ["parent_id", "order", "organ_id", "z"]] = [1, 1, 1, -2]
    assert audit(nodes, edges_of(nodes))["diagnostics"]["hierarchy_violation_count"] == 0


@pytest.mark.parametrize("branched", [False, True])
def test_organ_metadata_requires_single_connected_unbranched_chain(branched):
    nodes, _ = graph((.2, .2, .2))
    nodes.loc[nodes.order.gt(0), ["order", "organ_id"]] = [1, 1]
    if branched:
        nodes.loc[nodes.node_id.isin([2, 3]), "parent_id"] = 1
    with pytest.raises(ValueError, match="organ"):
        audit(nodes, edges_of(nodes))


def test_forest_distinct_organ_counts_are_per_plant():
    nodes, edges = graph((.2,))
    second = nodes.copy()
    second.loc[:, "node_id"] += 2
    second.loc[second.order.gt(0), "parent_id"] = 2
    second.loc[:, "plant_id"] = 2
    forest = pd.concat([nodes, second], ignore_index=True)
    result = audit(forest, edges_of(forest))
    assert result["by_order"][1]["organ_count"] == 2
    assert result["totals"]["mass_g"] == pytest.approx(2 * audit(nodes, edges)["totals"]["mass_g"])


@pytest.mark.parametrize("value", [True, "0.25", None, -1., 0., np.nan, np.inf, 1 + 2j])
def test_strict_density(value):
    with pytest.raises(ValueError):
        audit(*graph(), dry_density_g_cm3=value)


@pytest.mark.parametrize("value", [True, "2.5", 0., -1., np.nan, np.inf])
def test_strict_cutoff(value):
    with pytest.raises(ValueError):
        audit(*graph(), fine_diameter_max_mm=value)


@pytest.mark.parametrize("column,value", [("x", True), ("y", "1"), ("z", np.inf),
                                         ("diameter", True), ("diameter", "0.1"), ("diameter", -1.),
                                         ("diameter", np.nan), ("order", True), ("order", 1.5),
                                         ("invalid_root", 0), ("invalid_root", True),
                                         ("root_tissue_density", .5), ("root_tissue_density", np.nan)])
def test_invalid_values_fail_closed(column, value):
    nodes, edges = graph()
    nodes[column] = nodes[column].astype(object)
    nodes.loc[nodes.node_id.eq(1), column] = value
    with pytest.raises(ValueError):
        audit(nodes, edges)
    with pytest.raises(InfeasibleMassBudget):
        allocate(nodes, edges)


@pytest.mark.parametrize("groups", [None, [], True, [{"orders": [1, 2, 3, 4, 5], "share": True}],
    [{"orders": [1, 2, 3, 4, 5], "share": np.nan}],
    [{"orders": [1, 2, 3, 4, 5], "share": .5}],
    [{"orders": [1, 2, 3, 4], "share": 1.}],
    [{"orders": [1, 2, 3, 4, 5, 6], "share": 1.}],
    [{"orders": [1, 2, 3, 4, 5, 5], "share": 1.}],
    [{"orders": [True, 2, 3, 4, 5], "share": 1.}],
    [{"orders": [1, 2, 3, 4, 5], "share": 1., "other": 0}],
    [{"orders": [], "share": .5}, {"orders": [1, 2, 3, 4, 5], "share": .5}],
    [{"orders": [1, 2, 3], "share": .5}, {"orders": [3, 4, 5], "share": .5}]])
def test_invalid_groups(groups):
    with pytest.raises(InfeasibleMassBudget):
        allocate(*graph(), groups=groups)


@pytest.mark.parametrize("kwargs", [{"target_total_g": True}, {"target_total_g": -1.},
                                    {"target_total_g": np.inf}, {"locked_orders": (True,)},
                                    {"locked_orders": (6,)}, {"locked_orders": (1, 1)}])
def test_invalid_budget_and_locked_orders(kwargs):
    with pytest.raises(InfeasibleMassBudget):
        allocate(*graph(), **kwargs)


def test_zero_source_positive_budget_is_infeasible_but_zero_scenario_is_defined():
    nodes, edges = graph((0.,))
    groups = [{"orders": [1], "share": 1.}]
    with pytest.raises(InfeasibleMassBudget, match="zero unlocked source"):
        allocate(nodes, edges, groups=groups, target_total_g=1.)
    new_nodes, _, diagnostics = allocate(nodes, edges, groups=groups)
    pd.testing.assert_frame_equal(new_nodes, nodes)
    assert diagnostics["achieved_total_g"] == 0.
    assert diagnostics["after"]["totals"]["specific_root_length_cm_g"] is None
    nodes, edges = graph((.2,))
    new_nodes, _, diagnostics = allocate(nodes, edges, groups=groups, target_total_g=0.)
    assert new_nodes.loc[new_nodes.order.eq(1), "diameter"].iloc[0] == 0.
    assert diagnostics["after"]["totals"]["length_cm"] == 1.
    assert diagnostics["achieved_total_g"] == 0.


def test_zero_length_and_base_only_audit_have_explicit_undefined_srl():
    nodes, edges = graph((.2,), (0.,))
    assert audit(nodes, edges)["totals"]["mass_g"] == 0.
    base = nodes.loc[nodes.order.eq(0)]
    result = audit(base, edges_of(base))
    assert result["totals"]["segment_count"] == 0
    assert result["totals"]["specific_root_length_cm_g"] is None
    assert result["by_order"] == {}
    with pytest.raises(InfeasibleMassBudget):
        allocate(base, edges_of(base))


@pytest.mark.parametrize("kind", ["missing_parent", "duplicate_edge", "missing_edge", "cycle", "cross_plant", "duplicate_node"])
def test_invalid_topology(kind):
    nodes, edges = graph()
    if kind == "missing_parent":
        nodes.loc[nodes.node_id.eq(1), "parent_id"] = 999
        edges = edges_of(nodes)
    elif kind == "duplicate_edge":
        edges = pd.concat([edges, edges.iloc[[0]]], ignore_index=True)
    elif kind == "missing_edge":
        edges = edges.iloc[1:]
    elif kind == "cycle":
        nodes.loc[nodes.node_id.eq(1), "parent_id"] = 2
        nodes.loc[nodes.node_id.eq(2), "parent_id"] = 1
        edges = edges_of(nodes)
    elif kind == "cross_plant":
        nodes.loc[nodes.node_id.eq(1), "plant_id"] = 2
    else:
        nodes.loc[nodes.node_id.eq(1), "node_id"] = 2
    with pytest.raises(ValueError):
        audit(nodes, edges)


def test_missing_density_metadata_is_explicit_assumption_not_inferred():
    nodes, edges = graph()
    result = audit(nodes.drop(columns="root_tissue_density"), edges)
    assert result["diagnostics"]["density_metadata"] == "not_supplied"
    assert result["diagnostics"]["density_source"] == "explicit_caller_uniform_dry_density_assumption"
    with pytest.raises(TypeError):
        audit_root_mass(nodes, edges)


def test_tiny_positive_mass_reports_nonfinite_srl_as_undefined():
    nodes, edges = graph((1e-160,))
    result = audit(nodes, edges)
    assert result["totals"]["mass_g"] > 0
    assert result["totals"]["specific_root_length_cm_g"] is None
    assert result["totals"]["specific_root_length_undefined_reason"] == "nonfinite_length_mass_ratio"
