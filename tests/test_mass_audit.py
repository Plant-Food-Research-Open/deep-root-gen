"""Invented cm cylinders and population values; no empirical biomass targets."""

import copy
import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from deeprootgen.research.mass_audit import (
    DensitySource, MassAcceptanceContract, RepresentedRootWholeSystemSupport,
    audit_cylindrical_mass, evaluate_mass_acceptance, mean_population_mass,
)
from deeprootgen.statistics import summary_statistics as ss


def support(**updates):
    values = dict(coordinate_frame="invented-cm-frame-v1", order_to_compartment={1: "root", 2: "root", 3: "root"})
    values.update(updates)
    return RepresentedRootWholeSystemSupport(**values)


def density(mode="node", value=None, **updates):
    values = dict(mode=mode, provenance="invented fixture only", provenance_kind="assumption",
                  qualification="unqualified_assumption", uniform_density_g_cm3=value)
    values.update(updates)
    return DensitySource(**values)


def graph():
    # A 3-4-5 first edge, 2 cm second edge, unequal child diameters/densities.
    nodes = pd.DataFrame([
        dict(node_id=0, parent_id=-1, order=0, x=2., y=-1., z=3., diameter=999., root_tissue_density=-7.,
             length=999., invalid_root=False, root_type="base", organ_id=0, segment_rank=0),
        dict(node_id=1, parent_id=0, order=1, x=5., y=3., z=3., diameter=.2, root_tissue_density=.2,
             length=5., invalid_root=False, root_type="structural", organ_id=1, segment_rank=1),
        dict(node_id=2, parent_id=1, order=2, x=5., y=3., z=1., diameter=.1, root_tissue_density=.4,
             length=2., invalid_root=False, root_type="fine", organ_id=2, segment_rank=1),
    ])
    return nodes, edges_of(nodes)


def edges_of(nodes):
    return nodes.loc[nodes.order.gt(0), ["parent_id", "node_id"]].rename(columns={"node_id": "child_id"}).reset_index(drop=True)


def audit(nodes=None, edges=None, identity="invented-system", **kwargs):
    default_nodes, default_edges = graph()
    return audit_cylindrical_mass(default_nodes if nodes is None else nodes,
                                  default_edges if edges is None else edges,
                                  system_id=identity, support=kwargs.get("support", support()),
                                  density=kwargs.get("density", density()))


def test_analytic_unequal_cylinders_units_base_and_legacy_arithmetic_parity():
    nodes, edges = graph()
    result = audit(nodes, edges)
    total = result["totals"]["accepted"]
    assert total["length_cm"] == 7.
    assert total["volume_cm3"] == pytest.approx(np.pi * (.1**2 * 5. + .05**2 * 2.))
    assert total["mass_g"] == pytest.approx(np.pi * (.1**2 * 5. * .2 + .05**2 * 2. * .4))
    assert total["mass_g"] == pytest.approx(ss.TotalWeight(root_tissue_density=None).calculate(nodes))
    uniform = audit(nodes, edges, density=density("uniform", .3))
    assert uniform["totals"]["accepted"]["mass_g"] == pytest.approx(ss.TotalWeight(root_tissue_density=.3).calculate(nodes))
    assert result["base_exclusion"]["mass_g"] == 0.
    assert result["base_exclusion"]["node_count"] == 1
    assert result["by_order"]["3"]["accepted"]["mass_g"] == 0.
    assert result["qualification"] == "NOT_QUALIFIED"
    assert result == audit(nodes, edges)
    json.dumps(result, allow_nan=False)


def test_geometric_lengths_override_recorded_and_report_disagreement_without_mutation():
    nodes, edges = graph()
    original = nodes.copy(deep=True)
    nodes.loc[nodes.node_id.eq(1), "length"] = 123.
    result = audit(nodes, edges)
    assert result["per_edge"][0]["length_cm"] == 5.
    assert result["per_edge"][0]["geometric_minus_recorded_cm"] == -118.
    assert result["recorded_length_disagreement_count"] == 1
    assert result["totals"] == audit(original, edges)["totals"]
    assert nodes.loc[nodes.node_id.eq(1), "length"].iloc[0] == 123.
    assert result["source_hashes"] != audit(original, edges)["source_hashes"]
    assert audit(nodes.drop(columns="length"), edges)["totals"] == result["totals"]


def test_diameter_squared_density_linear_and_uniform_override_are_explicit():
    nodes, edges = graph()
    baseline = audit(nodes, edges)["totals"]["accepted"]["mass_g"]
    changed = nodes.copy()
    changed.loc[changed.order.gt(0), "diameter"] *= 2.
    assert audit(changed, edges)["totals"]["accepted"]["mass_g"] == pytest.approx(4. * baseline)
    changed = nodes.copy()
    changed.loc[changed.order.gt(0), "root_tissue_density"] *= 2.
    assert audit(changed, edges)["totals"]["accepted"]["mass_g"] == pytest.approx(2. * baseline)
    # Explicit uniform selection does not fall back to an unused node column.
    nodes.loc[nodes.order.gt(0), "root_tissue_density"] = np.nan
    assert audit(nodes, edges, density=density("uniform", .3))["totals"]["accepted"]["mass_g"] > 0.
    with pytest.raises(ValueError, match="density"):
        audit(nodes, edges)


def test_rigid_motion_and_constant_diameter_subdivision_conserve_mass():
    nodes, edges = graph()
    baseline = audit(nodes, edges)["totals"]["accepted"]
    moved = nodes.copy()
    rotation = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
    moved[["x", "y", "z"]] = nodes[["x", "y", "z"]].to_numpy() @ rotation.T + [9., -4., 7.]
    assert audit(moved, edges)["totals"]["accepted"] == baseline
    midpoint = nodes.loc[nodes.node_id.eq(1)].copy()
    midpoint.loc[:, "node_id"] = 3
    midpoint.loc[:, ["x", "y", "z"]] = [[3.5, 1., 3.]]
    midpoint.loc[:, "length"] = 2.5
    fine = nodes.copy()
    fine.loc[fine.node_id.eq(1), "parent_id"] = 3
    fine.loc[fine.node_id.eq(1), "length"] = 2.5
    fine = pd.concat([fine, midpoint], ignore_index=True)
    result = audit(fine, edges_of(fine))["totals"]["accepted"]
    assert result["segment_count"] == baseline["segment_count"] + 1
    for metric in ("length_cm", "volume_cm3", "mass_g"):
        assert result[metric] == pytest.approx(baseline[metric], abs=1e-12)


def test_invalid_child_exclusion_keeps_valid_descendant_and_audits_every_cylinder():
    nodes, edges = graph()
    nodes.loc[nodes.node_id.eq(1), "invalid_root"] = True
    result = audit(nodes, edges)
    assert result["totals"]["accepted"]["length_cm"] == 2.
    assert result["totals"]["excluded"]["length_cm"] == 5.
    assert result["valid_child_invalid_parent_count"] == 1
    assert result["per_edge"][0]["reason"] == "invalid_child"
    assert result["per_edge"][1]["accepted"]
    for metric in ("segment_count", "length_cm", "volume_cm3", "mass_g"):
        assert result["totals"]["accepted"][metric] + result["totals"]["excluded"][metric] == pytest.approx(
            result["totals"]["all_root_cylinders"][metric])
    assert result["totals"]["accepted"]["mass_g"] == pytest.approx(ss.TotalWeight(None).calculate(nodes))


def test_zero_diameter_is_reported_and_base_only_attributes_create_no_cylinder():
    nodes, edges = graph()
    nodes.loc[nodes.node_id.eq(1), "diameter"] = 0.
    nodes.loc[nodes.node_id.eq(0), "diameter"] = np.nan
    result = audit(nodes, edges)
    assert result["zero_diameter_count"] == 1
    assert result["per_edge"][0]["mass_g"] == 0.
    assert result["totals"]["accepted"]["length_cm"] == 7.
    assert result["base_exclusion"]["volume_cm3"] == 0.
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("field,value", [("diameter", -.1), ("diameter", np.nan),
                                         ("root_tissue_density", 0.), ("root_tissue_density", -1.),
                                         ("root_tissue_density", np.inf), ("x", np.nan)])
def test_malformed_excluded_cylinders_cannot_be_hidden(field, value):
    nodes, edges = graph()
    nodes.loc[nodes.node_id.eq(1), "invalid_root"] = True
    nodes.loc[nodes.node_id.eq(1), field] = value
    with pytest.raises(ValueError):
        audit(nodes, edges)


@pytest.mark.parametrize("case", ["duplicate", "missing_parent", "multiple_base", "cycle", "isolated_base_cycle",
                                  "missing_edge", "duplicate_edge", "zero_length", "nonbool", "mixed_plants", "unknown_type"])
def test_structural_or_geometry_failures_rejected_before_filtering(case):
    nodes, edges = graph()
    if case == "duplicate":
        nodes = pd.concat([nodes, nodes.iloc[[1]]], ignore_index=True)
    elif case == "missing_parent":
        nodes.loc[nodes.node_id.eq(2), "parent_id"] = 99
        edges = edges_of(nodes)
    elif case == "multiple_base":
        nodes.loc[nodes.node_id.eq(2), ["order", "parent_id"]] = [0, -1]
        edges = edges_of(nodes)
    elif case in {"cycle", "isolated_base_cycle"}:
        nodes.loc[nodes.node_id.eq(1), "parent_id"] = 2
        edges = edges_of(nodes)
        if case == "isolated_base_cycle":
            nodes.loc[nodes.order.gt(0), "invalid_root"] = True
    elif case == "missing_edge":
        edges = edges.iloc[:1]
    elif case == "duplicate_edge":
        edges = pd.concat([edges, edges.iloc[[0]]], ignore_index=True)
    elif case == "zero_length":
        nodes.loc[nodes.node_id.eq(2), ["x", "y", "z"]] = [[5., 3., 3.]]
    elif case == "nonbool":
        nodes["invalid_root"] = [False, "False", False]
    elif case == "mixed_plants":
        nodes["plant_id"] = [1, 1, 2]
    elif case == "unknown_type":
        nodes.loc[nodes.node_id.eq(1), "root_type"] = "stem"
    with pytest.raises(ValueError):
        audit(nodes, edges)


@pytest.mark.parametrize("updates", [dict(kind="voxel_prism"), dict(coordinate_unit="mm"), dict(diameter_unit="mm"),
                                     dict(density_unit="g/cm3"), dict(schema="unknown"), dict(order_to_compartment={1: "stem"}),
                                     dict(order_to_compartment={1: "root"}), dict(order_to_compartment={"1": "root"}),
                                     dict(order_to_compartment={}), dict(coordinate_frame="")])
def test_unknown_support_units_or_order_mapping_rejected(updates):
    with pytest.raises(ValueError):
        audit(support=support(**updates))


@pytest.mark.parametrize("updates", [dict(mode="auto"), dict(provenance=""), dict(unit="kg/m3"),
                                     dict(provenance_kind="guessed"), dict(qualification="qualified"),
                                     dict(provenance_kind="generator_default", qualification="evidenced"),
                                     dict(uniform_density_g_cm3=.2)])
def test_density_requires_explicit_source_provenance_and_assumption_label(updates):
    with pytest.raises(ValueError):
        audit(density=density(**updates))


@pytest.mark.parametrize("value", [None, 0., -1., np.nan, np.inf])
def test_uniform_density_must_be_explicit_positive_finite(value):
    with pytest.raises(ValueError):
        audit(density=density("uniform", value))


def test_population_mean_not_sum_and_audits_support_and_identities_retained():
    nodes, edges = graph()
    first = audit(nodes, edges, identity="one")
    nodes.loc[nodes.order.gt(0), "diameter"] *= 2.
    second = audit(nodes, edges, identity="two")
    result = mean_population_mass({"one": first, "two": second})
    expected = (first["totals"]["accepted"]["mass_g"] + second["totals"]["accepted"]["mass_g"]) / 2.
    assert result["n_systems"] == 2 and result["mean_dry_mass_g"] == pytest.approx(expected)
    assert result["mean_dry_mass_g"] != pytest.approx(2. * expected)
    assert result["system_audits"] == {"one": first, "two": second}
    assert result["mean_by_order"]["1"]["accepted"]["mass_g"] == pytest.approx(
        (first["by_order"]["1"]["accepted"]["mass_g"] + second["by_order"]["1"]["accepted"]["mass_g"]) / 2.)
    assert evaluate_mass_acceptance(result) == dict(
        status="NOT_QUALIFIED", mean_dry_mass_g=result["mean_dry_mass_g"],
        passed=None, support_sha256=result["support_sha256"],
    )
    with pytest.raises(ValueError, match="identity"):
        mean_population_mass({"wrong": first})
    with pytest.raises(ValueError, match="Incompatible"):
        mean_population_mass({"one": first, "two": audit(identity="two", support=support(coordinate_frame="other"))})
    tampered = copy.deepcopy(first)
    tampered["totals"]["accepted"]["mass_g"] *= 2.
    with pytest.raises(ValueError, match="identity"):
        mean_population_mass({"one": tampered})
    with pytest.raises(ValueError):
        mean_population_mass({})


def test_independent_invented_mass_acceptance_contract_and_support_no_architecture_epsilon():
    population = mean_population_mass({"invented-system": audit(density=density(
        provenance_kind="evidence", qualification="evidenced"))})
    mass = population["mean_dry_mass_g"]
    contract = MassAcceptanceContract(version="invented-only-mass-contract-v1", evidence_id="invented-fixture-not-observation",
                                      support_sha256=population["support_sha256"], uncertainty="invented absolute bound",
                                      target_mean_dry_mass_g=mass, absolute_tolerance_g=.001)
    assert evaluate_mass_acceptance(population, contract)["passed"]
    assert not evaluate_mass_acceptance(population, replace(contract, target_mean_dry_mass_g=mass + 1.))["passed"]
    relative = replace(contract, absolute_tolerance_g=None, relative_tolerance=.001)
    assert evaluate_mass_acceptance(population, relative)["passed"]
    interval = replace(contract, target_mean_dry_mass_g=None, absolute_tolerance_g=None, interval_g=(mass, mass + .001))
    assert evaluate_mass_acceptance(population, interval)["passed"]
    for invalid in (replace(contract, support_sha256="other"), replace(contract, evidence_id=""),
                    replace(contract, uncertainty=""), replace(contract, absolute_tolerance_g=0.),
                    replace(contract, relative_tolerance=.1), replace(interval, interval_g=(mass, mass))):
        with pytest.raises(ValueError):
            evaluate_mass_acceptance(population, invalid)


@pytest.mark.parametrize("kind", ["generator_default", "assumption"])
def test_evidenced_target_cannot_qualify_any_unqualified_system_density(kind):
    first = audit(identity="first", density=density(provenance_kind="evidence", qualification="evidenced"))
    second = audit(identity="second", density=density(provenance_kind=kind))
    population = mean_population_mass({"first": first, "second": second})
    contract = MassAcceptanceContract("invented-v1", "invented-evidence", population["support_sha256"],
                                      "invented uncertainty", interval_g=(0., 1.))
    result = evaluate_mass_acceptance(population, contract)
    assert result["status"] == "NOT_QUALIFIED" and result["passed"] is None
    assert result["cause"] == "UNQUALIFIED_DENSITY"
    assert result["unqualified_system_ids"] == ["second"]
    assert evaluate_mass_acceptance(population)["status"] == "NOT_QUALIFIED"


def test_support_and_acceptance_interval_snapshot_caller_containers():
    coverage = {1: "root", 2: "root", 3: "root"}
    declared = support(order_to_compartment=coverage)
    before = audit(support=declared)
    coverage[1] = "stem"
    assert audit(support=declared)["support_sha256"] == before["support_sha256"]
    with pytest.raises(TypeError):
        declared.order_to_compartment[1] = "stem"
    population = mean_population_mass({"invented-system": audit(density=density(
        provenance_kind="evidence", qualification="evidenced"))})
    bounds = [0., .001]
    contract = MassAcceptanceContract("invented-v1", "invented-evidence", population["support_sha256"],
                                      "invented uncertainty", interval_g=bounds)
    assert not evaluate_mass_acceptance(population, contract)["passed"]
    bounds[1] = 1.
    assert contract.interval_g == (0., .001)
    assert not evaluate_mass_acceptance(population, contract)["passed"]


def test_population_report_detaches_systems_and_rejects_direct_result_tampering():
    original = audit()
    population = mean_population_mass({"invented-system": original})
    identity = population["population_sha256"]
    original["support"]["coordinate_frame"] = "changed-after-snapshot"
    original["totals"]["accepted"]["mass_g"] = 123.
    assert population["support"]["coordinate_frame"] == "invented-cm-frame-v1"
    assert population["system_audits"]["invented-system"]["totals"]["accepted"]["mass_g"] != 123.
    assert population["population_sha256"] == identity
    assert evaluate_mass_acceptance(population)["status"] == "NOT_QUALIFIED"
    population["support"]["coordinate_frame"] = "tampered-population-result"
    with pytest.raises(ValueError, match="identity mismatch"):
        evaluate_mass_acceptance(population)


def test_source_hash_distinguishes_literal_metadata_from_nonfinite_markers_and_key_types():
    nodes, edges = graph()
    nodes["diameter"] = nodes["diameter"].astype(object)
    nodes.at[0, "diameter"] = np.nan
    nonfinite = audit(nodes, edges)
    nodes.at[0, "diameter"] = {"__nonfinite_float__": "nan"}
    literal = audit(nodes, edges)
    assert literal["source_hashes"]["nodes"] != nonfinite["source_hashes"]["nodes"]
    nodes.at[0, "diameter"] = {1: "integer key", "1": "string key"}
    first = audit(nodes, edges)
    nodes.at[0, "diameter"] = {1: "changed integer key", "1": "string key"}
    assert audit(nodes, edges)["source_hashes"]["nodes"] != first["source_hashes"]["nodes"]


@pytest.mark.parametrize("value", [np.ma.array([.2], mask=[True]), np.array([.2]), np.complex128(.2 + 1j)])
def test_masked_complex_or_array_density_cannot_be_coerced_to_a_scalar(value):
    with pytest.raises(ValueError):
        audit(density=density("uniform", value))
