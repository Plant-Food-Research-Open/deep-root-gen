"""Invented higher-order geometry and references only; no measured inputs."""

import copy
import json

import numpy as np
import pandas as pd
import pytest

from deeprootgen.research import population_evaluation as legacy
from deeprootgen.research import search_evaluation as search
from deeprootgen.research.order5_population_evaluation import trait_units_for_orders, validate_root_orders
from scripts.research import parameter_search as cli
from tests.test_parameter_search_cli import setup_files, change
from tests.test_search_evaluation import edges_for, reference as legacy_reference, sample as legacy_sample


def reference(max_order=5):
    orders = list(range(1, max_order + 1))
    result = legacy_reference()
    result.update(root_orders=orders, population_id="invented-higher-order-population",
                  trait_means={name: 10. for name in trait_units_for_orders(orders)})
    result["comparison"]["support"] = f"invented-orders1-{max_order}"
    return result


def sample(seed=1, scale=1., max_order=5):
    ref = reference(max_order)
    return dict(seed=seed, traits={name: value * scale for name, value in ref["trait_means"].items()},
                profiles=ref["profiles"], diagnostics={"root_orders": ref["root_orders"]})


def higher_nodes(rsa_nodes, max_order=5):
    nodes = rsa_nodes.copy()
    for order in range(4, max_order + 1):
        row = nodes.iloc[-1].copy()
        row.update(dict(node_id=order + 2, parent_id=order + 1, organ_id=order,
                        order=order, segment_rank=1, x=3. + order, y=2. + order,
                        z=-4. - 2 * order))
        parent = nodes.loc[nodes.node_id.eq(row.parent_id)].iloc[0]
        row.length = np.linalg.norm(row[["x", "y", "z"]].to_numpy(float)
                                    - parent[["x", "y", "z"]].to_numpy(float))
        nodes = pd.concat([nodes, row.to_frame().T], ignore_index=True)
    for name in ("node_id", "parent_id", "plant_id", "organ_id", "order", "segment_rank"):
        nodes[name] = nodes[name].astype(int)
    nodes[["x", "y", "z", "length", "diameter"]] = nodes[["x", "y", "z", "length", "diameter"]].astype(float)
    nodes["invalid_root"] = nodes.invalid_root.astype(bool)
    return nodes


@pytest.mark.parametrize("maximum,ntraits", [(4, 15), (5, 17)])
def test_higher_order_self_comparison_has_separate_contract(maximum, ntraits):
    result = search.evaluate_samples(reference(maximum), [sample(max_order=maximum)], objective_mode="population_mean")
    assert result["loss"] == 0. and result["population_report"]["passed"]
    assert len(result["population_report"]["traits"]) == ntraits
    assert len(result["population_report"]["error_vector"]) == ntraits + 3
    assert result["version"] == f"research-search-evaluation-order{maximum}-v1"
    assert result["population_report"]["version"] == f"architecture-population-order{maximum}-eps0.10-v1"
    assert not result["biological_validation"] and not result["mass_constraint_included"]
    assert json.loads(json.dumps(result, allow_nan=False)) == result


@pytest.mark.parametrize("name", ["quaternary_count", "quaternary_mean_length_cm", "quinary_count", "quinary_mean_length_cm"])
def test_only_higher_order_defect_controls_worst_J(name):
    candidate = sample()
    candidate["traits"][name] = 12.
    result = search.evaluate_samples(reference(), [candidate], objective_mode="per_seed_mean")
    assert result["loss"] == 2.
    assert result["population_report"]["worst_criteria"] == [f"trait/{name}"]
    assert not result["population_report"]["passed"]


def test_legacy_contract_units_versions_and_direct_report_remain_exact():
    units = dict(legacy.TRAIT_UNITS)
    result = search.evaluate_samples(legacy_reference(), [legacy_sample()], objective_mode="population_mean")
    support = legacy.ArchitectureComparisonSupport(
        **legacy_reference()["comparison"],
        bin_edges_cm={axis: [0., 10.] for axis in legacy.PROFILE_AXES})
    traits = legacy_reference()["trait_means"]
    profiles = {axis: [1.] for axis in legacy.PROFILE_AXES}
    observed = legacy.PopulationArchitecture("invented-one-vine", 1, traits, profiles, support)
    proposed = legacy.PopulationArchitecture("generated-seed-ensemble", 1, traits, profiles, support)
    expected = legacy.evaluate_population_architecture(observed, proposed, legacy.Architecture10PercentContract(support))
    assert result["population_report"] == expected
    assert result["version"] == search.VERSION == "research-search-evaluation-v1"
    assert len(units) == 13 and len(expected["error_vector"]) == 16
    extended = trait_units_for_orders([1, 2, 3, 4, 5])
    extended["primary_count"] = "changed"
    assert legacy.TRAIT_UNITS == units


@pytest.mark.parametrize("orders", [
    None, [1, 2], [1, 3, 4], [1, 2, 3, 5], [1, 2, 3, 4, 5, 6],
    [1., 2., 3., 4.], [True, 2, 3, 4], (1, 2, 3), [4, 3, 2, 1],
])
def test_missing_extra_unknown_or_noncontiguous_orders_rejected(orders):
    with pytest.raises(ValueError, match="root_orders"):
        validate_root_orders(orders)


@pytest.mark.parametrize("bad", [0., None, np.nan, np.inf, True])
def test_absent_undefined_higher_order_traits_fail_closed(bad):
    candidate = sample()
    candidate["traits"]["quinary_count"] = bad
    with pytest.raises(ValueError, match="17-positive-trait"):
        search.evaluate_samples(reference(), [candidate], objective_mode="population_mean")


@pytest.mark.parametrize("orders", [[1, 2, 3], [1, 2, 3, 4], None])
def test_sample_diagnostics_cannot_mismatch_higher_order_reference(orders):
    candidate = sample()
    candidate["diagnostics"] = {} if orders is None else {"root_orders": orders}
    with pytest.raises(ValueError, match="root_orders"):
        search.evaluate_samples(reference(), [candidate], objective_mode="population_mean")


def test_legacy_sample_diagnostics_mismatch_also_rejected():
    candidate = legacy_sample()
    candidate["diagnostics"] = {"root_orders": [1, 2, 3, 4, 5]}
    with pytest.raises(ValueError, match="root_orders"):
        search.evaluate_samples(legacy_reference(), [candidate], objective_mode="population_mean")


@pytest.mark.parametrize("maximum", [4, 5])
def test_geometry_includes_all_declared_orders_and_exact_operator_profiles(rsa_nodes, maximum):
    nodes = higher_nodes(rsa_nodes, maximum)
    result = search.summarize_sample(nodes, edges_for(nodes), seed=1, root_orders=list(range(1, maximum + 1)))
    pilot = search._pilot_helpers()
    records, _ = pilot.node_segments(nodes, base_depth=20.)
    metrics, cells, _ = pilot.summarize_geometry(records)
    assert result["traits"] == {name: metrics[name] for name in trait_units_for_orders(list(range(1, maximum + 1)))}
    assert result["traits"]["soil_length_cm"] == pytest.approx(nodes.length.sum())
    assert result["traits"]["soil_length_cm"] > 17.
    for axis_index, axis in enumerate(legacy.PROFILE_AXES):
        for key, fraction in result["profiles"][axis].items():
            expected = sum(length for cell, length in cells.items() if cell[axis_index] == int(key)) / nodes.length.sum()
            assert fraction == pytest.approx(expected)
    if maximum == 5:
        with pytest.raises(ValueError, match="root order"):
            search.summarize_sample(nodes, edges_for(nodes), seed=1, root_orders=[1, 2, 3, 4])


def test_absent_graph_order_rejected_without_zero_policy(rsa_nodes):
    nodes = higher_nodes(rsa_nodes, 4)
    with pytest.raises(ValueError, match="17-positive-trait"):
        search.summarize_sample(nodes, edges_for(nodes), seed=1, root_orders=[1, 2, 3, 4, 5])


def test_higher_order_full_profile_union_and_distinct_objectives():
    ref = reference()
    ref["profiles"]["across"] = {"-2": 1.}
    samples = [sample(1, .8), sample(2, 1.2)]
    samples[0]["profiles"]["across"] = {"100": 1.}
    samples[1]["profiles"]["across"] = {"-2": 1.000000001}
    population = search.evaluate_samples(ref, samples, objective_mode="population_mean")
    individual = search.evaluate_samples(ref, samples, objective_mode="per_seed_mean")
    profile = population["population_report"]["profiles"]["across"]
    assert profile["bin_edges_cm"] == [float(i * 10) for i in range(-2, 102)]
    assert profile["candidate"][0] == .5000000005 and profile["candidate"][-1] == .5
    assert individual["loss"] != population["loss"]
    samples[0]["profiles"]["across"] = {str(search.MAX_PROFILE_BINS): 1.}
    with pytest.raises(ValueError, match="no bins were truncated"):
        search.evaluate_samples(ref, samples, objective_mode="population_mean")


def parameters(maximum=5, route="construction_steps_v1"):
    from tests.test_construction_step_replay import parameters as base
    return base(active=route == "construction_steps_v1", max_order=maximum,
                research_current_length_cdfs_cm={
                    order: dict(lengths_cm=[2.], cumulative_probabilities=[1.]) for order in range(2, maximum + 1)},
                research_higher_order_tropism={
                    order: dict(theta_deg=45., theta_sd_deg=5., probability_down=.8, trials=1.) for order in range(4, maximum + 1)},
                research_root_counts_by_order={order: 2 for order in range(1, maximum + 1)}).model_dump()


@pytest.mark.parametrize("maximum", [4, 5])
@pytest.mark.parametrize("route", search.ROUTES)
def test_both_routes_higher_order_preflight_and_tiny_simulation(maximum, route):
    values = parameters(maximum, route)
    original = copy.deepcopy(values)
    assert search.validate_simulation_parameters(values, route=route) == values
    samples = [search.simulate_sample(dict(values, random_seed=seed), seed, route=route) for seed in range(11, 16)]
    assert values == original
    assert all(s["diagnostics"]["root_orders"] == list(range(1, maximum + 1)) for s in samples)
    assert all(s["traits"][f"{name}_count"] == 2 for s in samples
               for name in ("primary", "secondary", "tertiary", "quaternary", "quinary")[:maximum])
    assert len({s["diagnostics"]["initial_sha256"] for s in samples}) == 5
    for objective in search.OBJECTIVE_MODES:
        report = search.evaluate_samples(reference(maximum), samples, objective_mode=objective)
        assert np.isfinite(report["loss"]) and len(report["per_seed_reports"]) == 5


@pytest.mark.parametrize("route", search.ROUTES)
def test_cli_preflight_supports_five_orders_without_workers(tmp_path, monkeypatch, capsys, route):
    config = setup_files(tmp_path)
    (tmp_path / "search_synthetic_parameters.json").write_text(json.dumps(parameters(5, route)))
    (tmp_path / "search_synthetic_reference.json").write_text(json.dumps(reference()))
    change(config, lambda d: d.update(simulation_route=route))
    monkeypatch.setattr(cli, "run_one", lambda *a, **k: pytest.fail("Preflight launched a worker"))
    monkeypatch.setattr(search, "simulate_sample", lambda *a, **k: pytest.fail("Preflight simulated"))
    out = tmp_path / "out"
    assert cli.main(["--config", str(config), "--outdir", str(out)]) == 0
    assert "VALIDATED_NOT_EXECUTED" in capsys.readouterr().out and not out.exists()


def test_cli_parameter_reference_orders_must_match_before_workers(tmp_path, monkeypatch):
    config = setup_files(tmp_path)
    (tmp_path / "search_synthetic_reference.json").write_text(json.dumps(reference()))
    monkeypatch.setattr(cli, "run_one", lambda *a, **k: pytest.fail("Mismatch launched a worker"))
    with pytest.raises(ValueError, match="max_order must agree"):
        cli.main(["--config", str(config), "--outdir", str(tmp_path / "out")])
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("problem", ["missing", "extra", "unknown"])
def test_higher_order_traits_require_exact_declared_keys(problem):
    candidate = sample()
    if problem == "missing":
        del candidate["traits"]["quinary_count"]
    else:
        candidate["traits"]["senary_count" if problem == "unknown" else "above_surface_length_cm"] = 10.
    with pytest.raises(ValueError, match="Exactly the 17"):
        search.evaluate_samples(reference(), [candidate], objective_mode="population_mean")


@pytest.mark.parametrize("maximum", [4, 5, 6])
def test_missing_higher_order_settings_or_unsupported_maximum_fail_before_construction(maximum, monkeypatch):
    from tests.test_construction_step_replay import parameters as base
    from deeprootgen.research import so4_controlled
    values = base(active=False).model_dump()
    values["max_order"] = maximum
    monkeypatch.setattr(so4_controlled, "construct_skeleton", lambda *a, **k: pytest.fail("Invalid scope constructed"))
    with pytest.raises(ValueError):
        search.simulate_sample(values, 42, route="graph_segments_v1")
