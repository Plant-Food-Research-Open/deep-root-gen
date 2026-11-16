"""Analytic graphs and invented targets only; no empirical search or data."""

import copy
import json

import numpy as np
import pandas as pd
import pytest

from deeprootgen.research import search_evaluation as search
from deeprootgen.research.population_evaluation import TRAIT_UNITS


def edges_for(nodes):
    return nodes.loc[nodes.order.gt(0), ["parent_id", "node_id"]].rename(
        columns={"node_id": "child_id"}
    )


def reference():
    return dict(
        population_id="invented-one-vine",
        n_architectures=1,
        trait_means={name: 10.0 for name in TRAIT_UNITS},
        profiles={axis: {"0": 1.0} for axis in ("across", "along", "depth")},
        comparison=dict(
            coordinate_frame="invented-soil-frame",
            operator="invented-operator",
            support="invented-order1-3-roots",
        ),
        root_orders=[1, 2, 3],
    )


def sample(seed=1, scale=1.0):
    ref = reference()
    return dict(
        seed=seed,
        traits={key: value * scale for key, value in ref["trait_means"].items()},
        profiles=ref["profiles"],
        diagnostics={},
    )


def test_source_operator_parity_and_json_round_trip(rsa_nodes):
    nodes = rsa_nodes.copy()
    nodes.z += 20
    nodes.loc[nodes.node_id.eq(0), "z"] = 22.0
    nodes.loc[nodes.node_id.eq(1), "length"] = 6.0
    before = nodes.copy(deep=True)
    edges = edges_for(nodes)
    result = search.summarize_sample(nodes, edges, seed=42)
    pilot = search._pilot_helpers()
    records, _ = pilot.node_segments(nodes, base_depth=20.0)
    metrics, cells, _ = pilot.summarize_geometry(records)
    assert result["traits"] == {name: metrics[name] for name in TRAIT_UNITS}
    assert result["diagnostics"]["above_surface_length_cm"] == pytest.approx(2.0)
    assert result["traits"]["soil_length_cm"] == pytest.approx(17.0)
    for index, axis in enumerate(("across", "along", "depth")):
        for key, fraction in result["profiles"][axis].items():
            expected = (
                sum(length for cell, length in cells.items() if cell[index] == int(key))
                / 17.0
            )
            assert fraction == pytest.approx(expected)
        assert sum(result["profiles"][axis].values()) == pytest.approx(1.0)
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    pd.testing.assert_frame_equal(nodes, before)


def test_invalid_child_is_excluded_but_parent_anchor_retained(rsa_nodes):
    nodes = rsa_nodes.copy()
    nodes.loc[nodes.node_id.eq(4), "invalid_root"] = True
    result = search.summarize_sample(nodes, edges_for(nodes), seed=1)
    assert result["traits"]["soil_length_cm"] == pytest.approx(15.0)
    assert result["diagnostics"]["invalid_soil_length_cm"] == pytest.approx(2.0)
    nodes.loc[nodes.node_id.eq(0), "invalid_root"] = True
    assert (
        search.summarize_sample(nodes, edges_for(nodes), seed=1)["traits"]
        == result["traits"]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("order", 4),
        ("order", -1),
        ("node_id", True),
        ("invalid_root", "False"),
        ("invalid_root", None),
        ("root_type", "stem"),
        ("diameter", -1.0),
        ("length", 0.0),
        ("x", np.inf),
    ],
)
def test_malformed_root_fields_rejected(rsa_nodes, field, value):
    nodes = rsa_nodes.astype({field: object}).copy()
    nodes.loc[nodes.index[-1], field] = value
    with pytest.raises((ValueError, TypeError)):
        search.summarize_sample(nodes, edges_for(nodes), seed=42)


@pytest.mark.parametrize(
    "problem", ["duplicate", "orphan", "cycle", "wrong_edges", "two_plants"]
)
def test_graph_identity_and_tree_errors_rejected(rsa_nodes, problem):
    nodes = rsa_nodes.copy()
    if problem == "duplicate":
        nodes = pd.concat([nodes, nodes.iloc[[-1]]], ignore_index=True)
    elif problem == "orphan":
        nodes.loc[nodes.node_id.eq(5), "parent_id"] = 99
    elif problem == "cycle":
        nodes.loc[nodes.node_id.eq(1), "parent_id"] = 2
    elif problem == "two_plants":
        nodes.loc[nodes.node_id.eq(5), "plant_id"] = 2
    edges = edges_for(nodes)
    if problem == "wrong_edges":
        edges.loc[edges.index[-1], "parent_id"] = 0
    with pytest.raises(ValueError):
        search.summarize_sample(nodes, edges, seed=42)


def test_absent_order_is_rejected_instead_of_inventing_zero_policy(rsa_nodes):
    nodes = rsa_nodes.loc[rsa_nodes.order.lt(3)].copy()
    with pytest.raises(ValueError, match="13-positive-trait"):
        search.summarize_sample(nodes, edges_for(nodes), seed=42)


def test_opposite_seed_errors_cancel_only_in_population_objective():
    samples = [sample(1, 0.8), sample(2, 1.2)]
    population = search.evaluate_samples(
        reference(), samples, objective_mode="population_mean"
    )
    individual = search.evaluate_samples(
        reference(), samples, objective_mode="per_seed_mean"
    )
    assert population["loss"] == 0.0 and population["population_report"]["passed"]
    assert individual["loss"] == pytest.approx(2.0)
    assert individual["per_seed_pass_fraction"] == 0.0
    assert (
        individual["per_seed_criterion_pass_fractions"]["trait/soil_length_cm"] == 0.0
    )
    assert individual["per_seed_criterion_pass_fractions"]["profile/depth"] == 1.0
    assert population["population_report"] == individual["population_report"]
    assert (
        not individual["biological_validation"]
        and not individual["mass_constraint_included"]
    )
    assert individual["qualification"] == "RECONSTRUCTION_DIAGNOSTIC"
    assert json.loads(json.dumps(individual, allow_nan=False)) == individual


def test_one_seed_and_single_vine_reference_supported_without_heldout_claim():
    result = search.evaluate_samples(
        reference(), [sample()], objective_mode="per_seed_mean"
    )
    assert result["loss"] == 0 and result["per_seed_pass_fraction"] == 1.0
    assert result["population_report"]["reference"]["n_architectures"] == 1
    assert "no held-out" in result["reference_scope"]


def test_sparse_union_keeps_negative_and_overflow_bins_for_every_seed():
    ref = reference()
    ref["profiles"]["across"] = {"-2": 1.0}
    first, second = sample(1), sample(2)
    first["profiles"]["across"] = {"100": 1.0}
    second["profiles"]["across"] = {"-2": 1.0}
    result = search.evaluate_samples(
        ref, [first, second], objective_mode="population_mean"
    )
    profile = result["population_report"]["profiles"]["across"]
    assert profile["bin_edges_cm"] == [float(i * 10) for i in range(-2, 102)]
    assert profile["candidate"][0] == profile["candidate"][-1] == 0.5
    assert profile["total_variation"] == 0.5
    assert result["per_seed_reports"][0]["profiles"]["across"]["total_variation"] == 1.0
    assert result["per_seed_reports"][1]["profiles"]["across"]["total_variation"] == 0.0


def test_profiles_average_architectures_not_lengths_and_are_not_renormalized():
    first, second = sample(1), sample(2)
    first["traits"]["soil_length_cm"] = 1000.0
    first["profiles"]["depth"] = {"0": 1.0}
    second["profiles"]["depth"] = {"1": 1.000000001}
    result = search.evaluate_samples(
        reference(), [first, second], objective_mode="population_mean"
    )
    assert result["population_report"]["profiles"]["depth"]["candidate"] == [
        0.5,
        0.5000000005,
    ]


@pytest.mark.parametrize("key", ["01", "-0", "+1", "1.0", " 1", 1, True])
def test_profile_bin_aliases_rejected(key):
    candidate = sample()
    candidate["profiles"]["depth"] = {key: 1.0}
    with pytest.raises(ValueError, match="canonical integer"):
        search.evaluate_samples(
            reference(), [candidate], objective_mode="population_mean"
        )


@pytest.mark.parametrize("bad", [0.0, -1.0, np.nan, np.inf, True, 1j, None])
def test_zero_undefined_and_malformed_traits_rejected(bad):
    candidate = sample()
    candidate["traits"]["tertiary_count"] = bad
    with pytest.raises(ValueError, match="13-positive-trait"):
        search.evaluate_samples(
            reference(), [candidate], objective_mode="per_seed_mean"
        )


@pytest.mark.parametrize("bad", [0.5, np.nan, np.inf, -1.0, True])
def test_unnormalized_or_invalid_profile_rejected(bad):
    candidate = sample()
    candidate["profiles"]["depth"] = {"0": bad}
    with pytest.raises(ValueError):
        search.evaluate_samples(
            reference(), [candidate], objective_mode="population_mean"
        )


@pytest.mark.parametrize(
    "orders", [[1, 2], [1, 2, 3, 5], [True, 2, 3], [1.0, 2.0, 3.0], [3, 2, 1]]
)
def test_reference_support_must_explicitly_cover_exact_current_orders(orders):
    ref = reference()
    ref["root_orders"] = orders
    with pytest.raises(ValueError, match="root_orders"):
        search.evaluate_samples(ref, [sample()], objective_mode="population_mean")


def test_objective_mode_required_and_duplicate_seeds_rejected():
    with pytest.raises(TypeError):
        search.evaluate_samples(reference(), [sample()])
    with pytest.raises(ValueError, match="objective_mode"):
        search.evaluate_samples(reference(), [sample()], objective_mode="best_seed")
    with pytest.raises(ValueError, match="Duplicate"):
        search.evaluate_samples(
            reference(), [sample(), sample()], objective_mode="population_mean"
        )


def test_dense_capacity_failure_never_truncates():
    candidate = sample()
    candidate["profiles"]["depth"] = {str(search.MAX_PROFILE_BINS): 1.0}
    with pytest.raises(ValueError, match="no bins were truncated"):
        search.evaluate_samples(
            reference(), [candidate], objective_mode="population_mean"
        )


@pytest.mark.parametrize("route", search.ROUTES)
def test_real_tiny_route_is_repeatable_fresh_and_retains_requested_identity(
    route, monkeypatch
):
    from tests.test_construction_step_replay import parameters
    from deeprootgen.research import so4_controlled

    values = parameters(active=route == "construction_steps_v1").model_dump()
    values["simulation_tag"] = "invented-notebook-run"
    original = copy.deepcopy(values)
    calls, construct = [], so4_controlled.construct_skeleton

    def record(*args):
        result = construct(*args)
        calls.append(result)
        return result

    monkeypatch.setattr(so4_controlled, "construct_skeleton", record)
    first = search.simulate_sample(values, 42, route=route)
    second = search.simulate_sample(values, 42, route=route)
    assert first == second and len(calls) == 2 and calls[0] is not calls[1]
    assert values == original
    assert first["diagnostics"]["simulation_route"] == route
    assert first["diagnostics"]["requested_simulation_tag"] == "invented-notebook-run"
    assert (
        first["diagnostics"]["constructor_simulation_tag"]
        == "SO4-T2-controlled-INITIAL"
    )
    assert first["diagnostics"]["initial_sha256"] == calls[0].sha256
    assert first["diagnostics"]["fresh_initial_construction"]
    assert all(value > 0 for value in first["traits"].values())
    assert json.loads(json.dumps(first, allow_nan=False)) == first


def test_changed_dimensions_construct_a_new_initial(monkeypatch):
    from tests.test_construction_step_replay import parameters

    values = parameters().model_dump()
    first = search.simulate_sample(values, 42, route="construction_steps_v1")
    values.update(min_primary_length=7.0, max_primary_length=8.0)
    second = search.simulate_sample(values, 42, route="construction_steps_v1")
    assert (
        first["diagnostics"]["initial_sha256"]
        != second["diagnostics"]["initial_sha256"]
    )
    assert (
        first["diagnostics"]["run_identity_sha256"]
        != second["diagnostics"]["run_identity_sha256"]
    )
    assert (
        first["traits"]["primary_mean_length_cm"]
        != second["traits"]["primary_mean_length_cm"]
    )


def test_shared_route_preflight_does_not_construct_and_rejects_legacy_and_unknown(
    monkeypatch,
):
    from tests.test_construction_step_replay import parameters
    from deeprootgen.research import so4_controlled

    monkeypatch.setattr(
        so4_controlled,
        "construct_skeleton",
        lambda *args: pytest.fail("Preflight constructed a graph"),
    )
    values = parameters(active=False).model_dump()
    result = search.validate_simulation_parameters(values, route="graph_segments_v1")
    assert result == values and result is not values
    with pytest.raises(ValueError, match="Fichtl"):
        search.validate_simulation_parameters(
            {**values, "tropism_mode": "legacy"}, route="graph_segments_v1"
        )
    with pytest.raises(ValueError, match="Unknown simulation parameters"):
        search.validate_simulation_parameters(
            {**values, "pretend_parameter": 1.0}, route="graph_segments_v1"
        )


@pytest.mark.parametrize(
    "updates,route",
    [
        ({"random_seed": 43}, "graph_segments_v1"),
        ({"random_seed": True}, "graph_segments_v1"),
        ({"soil_surface_z_cm": 0.0}, "graph_segments_v1"),
        ({"max_order": 4}, "graph_segments_v1"),
        (
            {"research_current_length_grid": "construction_steps_v1"},
            "graph_segments_v1",
        ),
        ({"research_parent2_branch_zone_cm": {}}, "graph_segments_v1"),
        ({"research_tertiary_length_rank_strength": 0.5}, "graph_segments_v1"),
        ({"research_primary_attachment_distal_fraction": 0.2}, "graph_segments_v1"),
        ({}, "construction_steps_v1"),
        ({}, "unknown"),
    ],
)
def test_route_seed_and_scope_mismatch_rejected_before_construction(
    updates, route, monkeypatch
):
    from tests.test_construction_step_replay import parameters
    from deeprootgen.research import so4_controlled

    values = parameters(active=False).model_dump()
    values.update(updates)
    monkeypatch.setattr(
        so4_controlled,
        "construct_skeleton",
        lambda *args: pytest.fail("Constructed before rejecting mismatch"),
    )
    with pytest.raises(ValueError):
        search.simulate_sample(values, 42, route=route)
