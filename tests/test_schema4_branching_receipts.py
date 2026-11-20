"""Invented cases for resolved direction ownership and branching observations."""

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import lognorm

from deeprootgen.cli import simulate
from deeprootgen.data_model import resolve_config
from deeprootgen.data_model.simulation_form import simulation_controls, simulation_document
from deeprootgen.model import RootSystemSimulation
from deeprootgen.model.laws import first_branch_sites


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def document(name):
    return json.loads((EXAMPLES / f"{name}.json").read_text())


def run(config):
    model = RootSystemSimulation(random_seed=config["random_seed"])
    model.run(config)
    return model


def five_orders():
    value = document("design/native_features_fully_replaced")
    parameters = value["parameters"]
    parameters.update(max_order=5, root_vary=0., primary_root_count=3, outer_primary_fraction=.5)
    for key in [name for name in parameters if name.startswith("fichtl_")]:
        parameters.pop(key)
    features = value["features"]
    features["cohort_maturity"]["enabled"] = False
    for owner in ("curvature", "taper"):
        orders = features[owner]["settings"]["by_order"]
        orders.update({order: deepcopy(orders["3"]) for order in ("4", "5")})
    features["lengths"]["settings"]["by_order"] = {str(order): 5. for order in range(1, 6)}
    law = dict(law="first_branch_and_daughter_count", branch_probability=1.,
               first_branch_cm=dict(mean=1., sd=0., min=1., max=1.), daughter_probabilities=[1.])
    features["branching"]["settings"]["by_order"] = {str(order): deepcopy(law) for order in range(1, 5)}
    return value


def test_all_curved_fichtl_scope_survives_cli_form_and_reload(tmp_path):
    value = five_orders()
    direct = run(value)
    fields = ["random_seed", "simulation_tag", "primary_root_count", "advanced_settings"]
    from_form = simulation_document(dict(zip(fields, simulation_controls(value, fields))))
    # Inactive globals carry supplied-input provenance only.
    from_form["parameters"].update(fichtl_sigma=1., fichtl_theta3_deg=30.)
    rebuilt = run(from_form)
    assert rebuilt.result.metadata["supplied_input_sha256"] != direct.result.metadata["supplied_input_sha256"]
    for key in ("effective_model_sha256", "run_identity_sha256"):
        assert rebuilt.result.metadata[key] == direct.result.metadata[key]
    assert rebuilt.rng.bit_generator.state == direct.rng.bit_generator.state
    for a, b in zip(direct.G.as_df(), rebuilt.G.as_df()):
        pd.testing.assert_frame_equal(a, b, check_exact=True)
    assert direct.result.metadata["resolved_primary_counts"] == dict(total=3, outer=2, inner=1)
    assert direct.result.organ_table.groupby("order").size().tolist() == [3] * 5
    assert not direct.result.organ_table.invalid_root.any()

    first, second = tmp_path / "first", tmp_path / "second"
    simulate(value, first)
    simulate(first / "parameters.json", second)
    for file in ("nodes.csv", "edges.csv", "organs.csv", "root_summary.json", "branching.json", "execution.json"):
        assert (first / file).read_bytes() == (second / file).read_bytes()
    receipt = json.loads((first / "branching.json").read_text())["by_parent_order"]
    assert list(receipt) == ["1", "2", "3", "4"]
    for order in receipt.values():
        assert order["proposed"] == order["accepted"] == 3
        assert {row["first_site_cm"] for row in order["sampled_first_sites"]} == {1.}


def test_partial_fichtl_fallback_requires_only_its_own_controls():
    value = five_orders()
    value["features"]["curvature"]["settings"]["by_order"].pop("5")
    with pytest.raises(ValueError, match=r"active Fichtl orders \['5'\]"):
        resolve_config(value)
    settings = dict(higher_order_tropism={"5": dict(theta_deg=35., theta_sd_deg=0., probability_down=1., trials=0.)},
                    sigma_by_order={"5": .1})
    value["features"]["direction"] = dict(enabled=True, settings=settings)
    simulation = run(value)
    assert simulation.organs[5]
    assert set(simulation.tropism_diagnostics["by_order"]) == {"5"}
    assert not simulation.result.organ_table.invalid_root.any()


def test_construction_step_overrides_need_no_unused_global_sigma():
    value = document("research/native_steps_synthetic")
    settings = value["features"]["direction"]["settings"]
    settings["sigma_by_order"] = {"2": .14, "3": .19}
    first = run(value)
    value["parameters"].pop("fichtl_sigma")
    again = run(value)
    assert again.result.metadata["effective_model_sha256"] == first.result.metadata["effective_model_sha256"]
    for a, b in zip(first.G.as_df(), again.G.as_df()):
        pd.testing.assert_frame_equal(a, b, check_exact=True)
    settings["sigma_by_order"].pop("3")
    with pytest.raises(ValueError, match="missing native parameters.*fichtl_sigma"):
        resolve_config(value)


@pytest.mark.parametrize("key", ["1\n", "01"])
def test_reject_ambiguous_order_before_allocation(key):
    value = five_orders()
    orders = value["features"]["branching"]["settings"]["by_order"]
    orders[key] = deepcopy(orders["1"])
    with pytest.raises(ValueError, match="canonical positive order"):
        resolve_config(value)


def test_terminal_branching_is_accepted_as_inactive_input():
    value = five_orders()
    baseline = run(value)
    laws = value["features"]["branching"]["settings"]["by_order"]
    laws["5"] = deepcopy(laws["1"])
    simulated = run(value)
    assert simulated.result.resolved["features"]["inactive"]["branching"]["by_order"] == {"5": laws["5"]}
    for key in ("effective_model_sha256", "run_identity_sha256"):
        assert simulated.result.metadata[key] == baseline.result.metadata[key]
    assert "5" not in simulated.result.diagnostics["branching"]["by_parent_order"]
    assert simulated.rng.bit_generator.state == baseline.rng.bit_generator.state
    for a, b in zip(simulated.G.as_df(), baseline.G.as_df()):
        pd.testing.assert_frame_equal(a, b, check_exact=True)


@pytest.mark.parametrize("updates", [
    {"branch_probability": float("nan")}, {"branch_probability": -.1},
    {"daughter_probabilities": [1.2, -.2]}, {"daughter_probabilities": [.9]},
    {"first_branch_cm": dict(mean=1., sd=.4, min=2., max=1.)},
])
def test_rejects_invalid_branching_law_before_allocation(updates):
    value = five_orders()
    value["features"]["branching"]["settings"]["by_order"]["1"].update(updates)
    with pytest.raises(ValueError):
        resolve_config(value)


def test_bounded_first_site_censoring_and_conditional_count_match_analytic_expectation():
    spec = dict(mean=5., sd=3., min=2., max=8.)
    p = .7
    weights = [.65, .35]
    law = dict(first_branch_cm=spec, branch_probability=p, daughter_probabilities=weights)
    shape = np.sqrt(np.log1p((spec["sd"] / spec["mean"]) ** 2))
    unbounded = lognorm(s=shape, scale=spec["mean"] * np.exp(-shape * shape / 2))
    probability = p * (unbounded.cdf(5) - unbounded.cdf(2)) / (unbounded.cdf(8) - unbounded.cdf(2))
    expected = probability * 1.35
    rng = np.random.default_rng(811)
    counters = dict(branch_beyond_tip=0)
    results = [first_branch_sites(law, 2, 3, 5., 1., False, rng, counters) for _ in range(16_000)]
    draws, sites = zip(*results)
    assert min(draws) >= 2 and max(draws) <= 8
    assert np.mean([bool(s) for s in sites]) == pytest.approx(probability, abs=.02)
    assert np.mean([len(s) for s in sites]) == pytest.approx(expected, abs=.02)
    law.update(first_branch_cm=dict(mean=5., sd=0., min=5., max=5.), branch_probability=1.)
    assert first_branch_sites(law, 2, 3, 5., 1., False, rng, counters) == (5., [])
    assert first_branch_sites(law, 3, 3, 10., 1., False, rng, counters) == (5., [])


def test_rejected_sites_differ_from_zero_proposal():
    value = five_orders()
    value["parameters"]["min_branching_diameter_cm"] = .5
    report = run(value).result.diagnostics["branching"]["by_parent_order"]["1"]
    assert report["proposed"] == report["placed_sites"] == 3 and report["accepted"] == 0
    assert report["rejections"]["diameter_below_branch_minimum"] == 3
    value["features"]["branching"]["settings"]["by_order"]["1"]["branch_probability"] = 0.
    report = run(value).result.diagnostics["branching"]["by_parent_order"]["1"]
    assert report["proposed"] == 0 and report["accepted"] == 0
    assert report["rejections"]["bernoulli_rejected"] == 3
