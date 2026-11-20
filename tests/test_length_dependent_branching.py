"""Count, support, material and budget checks for the Poisson branch law."""

from copy import deepcopy
from math import exp
from types import SimpleNamespace

import numpy as np
import pytest

from deeprootgen.cli import simulate
from deeprootgen.data_model import resolve_config
from deeprootgen.model.branch_eligibility import filter_branch_sites
from deeprootgen.model.branching_laws import LENGTH_POISSON_LAW, LENGTH_POISSON_STREAM, length_poisson_sites
from tests.test_schema4_branching_receipts import five_orders, run


def poisson(**overrides):
    return dict(dict(law=LENGTH_POISSON_LAW, basal_exclusion_cm=10., apical_exclusion_cm=10.,
                     mean_spacing_cm=10., branch_probability=1.), **overrides)


def small_forest():
    spec = five_orders()
    spec["parameters"]["max_order"] = 2
    for name in ("curvature", "taper", "lengths", "branching"):
        orders = spec["features"][name]["settings"]["by_order"]
        spec["features"][name]["settings"]["by_order"] = {key: law for key, law in orders.items() if int(key) <= 2}
    spec["features"]["branching"]["settings"]["by_order"]["1"] = poisson(
        basal_exclusion_cm=.45, apical_exclusion_cm=.55, mean_spacing_cm=.8
    )
    return spec


@pytest.mark.parametrize(("length", "probability", "reason"), [(20., 1., "empty_zone"), (60., 0., "inactive")])
def test_empty_or_inactive_zone_issues_no_stream(length, probability, reason):
    def unexpected(*args):
        pytest.fail("Empty or inactive zone requested a draw or capacity")

    sites, report = length_poisson_sites(poisson(branch_probability=probability), length, unexpected, unexpected)
    assert sites == [] and not report["active"] and report["decision"] == reason
    assert report["first_proposed_site_cm"] is None


def test_exact_position_bounds_and_budget_before_uniform_draw():
    calls = []

    def uniform(low, high, count):
        assert calls == [2] and (low, high, count) == (10., 50., 2)
        return np.array([high, low])  # includes a rounded exclusive endpoint

    rng = SimpleNamespace(poisson=lambda mean: 2, uniform=uniform)
    sites, report = length_poisson_sites(poisson(), 60., lambda: rng, calls.append)
    assert sites == [10., np.nextafter(50., 10.)]
    assert report["proposed"] == 2 and report["first_proposed_site_cm"] == 10.

    def reject(count):
        raise ValueError("proposals over budget")

    rng.uniform = lambda *args: pytest.fail("Position array allocated before budget check")
    with pytest.raises(ValueError, match="proposals over budget"):
        length_poisson_sites(poisson(), 60., lambda: rng, reject)
    rng.poisson = lambda _: 0
    sites, report = length_poisson_sites(poisson(), 60., lambda: rng, reject)
    assert sites == [] and report["active"] and report["decision"] == "poisson_zero"


def test_proposal_mean_increases_with_usable_contour():
    rng = np.random.default_rng(212)
    for length, expected in ((60., 4.), (100., 8.)):
        counts = [len(length_poisson_sites(poisson(), length, lambda: rng, lambda count: None)[0])
                  for _ in range(12_000)]
        # At the larger mean the standard error is sqrt(8/12000) < .026.
        assert np.mean(counts) == pytest.approx(expected, abs=.12)


def test_eligible_count_mean_variance_and_zero_probability():
    rng = np.random.default_rng(868)
    p, mean = .7, 2.
    counts = []
    for _ in range(20_000):
        sites, _ = length_poisson_sites(poisson(branch_probability=p), 60., lambda: rng, lambda count: None)
        # 20 cm eligible across two disjoint pieces, out of the 40 cm zone.
        counts.append(sum(10 <= site < 20 or 28 <= site < 38 for site in sites))
    # Fixed bounds are more than four sampling standard errors for this mixture.
    assert np.mean(counts) == pytest.approx(p * mean, abs=.05)
    assert np.var(counts) == pytest.approx(p * mean + p * (1 - p) * mean**2, abs=.13)
    assert np.mean(np.asarray(counts) == 0) == pytest.approx(1 - p + p * exp(-mean), abs=.018)


def test_shared_diameter_filter_can_accept_disjoint_cylinder_support():
    nodes = [SimpleNamespace(node_data=SimpleNamespace(order=1)) for _ in range(3)]
    parent = SimpleNamespace(segments=nodes, lateral_attachment_nodes=list(nodes),
                             get_diameters=lambda: np.array([.093, .061, .112]),
                             get_lengths=lambda: np.ones(3), axis_state=SimpleNamespace(material=None))
    state = SimpleNamespace(parameters=SimpleNamespace(min_branching_diameter_cm=.093),
                            diagnostics={}, laws=SimpleNamespace(relocation=None))
    filter_branch_sites(state, parent)
    assert len(parent.lateral_attachment_nodes) == 2
    assert parent.lateral_attachment_nodes[0] is nodes[0] and parent.lateral_attachment_nodes[1] is nodes[2]


def test_filter_uses_inclusive_final_diameter_and_receipts_balance():
    spec = small_forest()
    spec["parameters"]["min_branching_diameter_cm"] = .093
    taper = spec["features"]["taper"]["settings"]["by_order"]["1"]
    taper.update(base_cm=.093, tip_cm=.093)
    dense = run(spec)
    report = dense.result.diagnostics["branching"]["by_parent_order"]["1"]
    assert report["proposed"] > 0 and report["proposed"] == report["accepted"] == len(dense.organs[2])
    assert report["sampled_first_sites"] == []
    for axis in report["length_poisson_sites"]:
        assert axis["usable_length_cm"] == pytest.approx(4.)
        assert axis["placed_sites"] == axis["accepted"] == axis["proposed"]
        assert axis["invalid_descendants"] == 0
        if axis["accepted"]:
            assert .45 <= axis["first_proposed_site_cm"] < 4.45
            assert axis["first_accepted_site_cm"] == pytest.approx(axis["first_proposed_site_cm"])
    taper.update(base_cm=.09299, tip_cm=.09299)
    thin = run(spec)
    report2 = thin.result.diagnostics["branching"]["by_parent_order"]["1"]
    assert report2["proposed"] == report["proposed"] and report2["accepted"] == 0
    assert report2["rejections"]["diameter_below_branch_minimum"] == report["proposed"]
    assert all(axis["first_accepted_site_cm"] is None for axis in report2["length_poisson_sites"])


def test_terminal_law_remains_inactive_and_uses_no_stream():
    spec = small_forest()
    orders = spec["features"]["branching"]["settings"]["by_order"]
    orders["1"]["branch_probability"] = 0.
    orders["2"] = poisson()
    sim = run(spec)
    assert not sim.organs[2]
    assert all(row["namespace"] != LENGTH_POISSON_STREAM for row in sim.streams.issued)
    assert list(sim.result.diagnostics["branching"]["by_parent_order"]) == ["1"]


@pytest.mark.parametrize("overrides", [
    {"basal_exclusion_cm": 0.}, {"apical_exclusion_cm": -1.}, {"mean_spacing_cm": float("inf")},
    {"branch_probability": 1.1}, {"first_branch_cm": {}}, {"daughter_probabilities": [1.]},
])
def test_illegal_poisson_settings_cannot_cross_law_boundaries(overrides):
    spec = small_forest()
    spec["features"]["branching"]["settings"]["by_order"]["1"].update(overrides)
    with pytest.raises(ValueError):
        resolve_config(spec)


def test_competing_site_count_and_activation_owners_fail_at_resolution():
    spec = small_forest()
    other = deepcopy(spec)
    other["parameters"]["daughters_by_parent_order"] = {"1": 3}
    with pytest.raises(ValueError, match="Two daughter-count laws"):
        resolve_config(other)
    other = deepcopy(spec)
    other["features"]["branch_sites"] = dict(enabled=True, settings=dict(counts_by_order={"1": 3, "2": 5}))
    with pytest.raises(ValueError, match="conflicts with replacement branching"):
        resolve_config(other)
    other = deepcopy(spec)
    other["features"]["attachment_relocation"] = dict(enabled=True, settings=dict(orders=[2], distal_fraction=.3))
    with pytest.raises(ValueError, match="conflicts with order-2 attachment relocation"):
        resolve_config(other)
    other = deepcopy(spec)
    other["features"]["cohort_maturity"] = dict(enabled=True, settings=dict(
        groups=[dict(label="synthetic", primary_indices=[0, 1, 2], maturity_range=[.5, .5])],
        length_power=0., diameter_power=0., diameter_target="base_anchor", scale_branch_probability=True,
    ))
    with pytest.raises(ValueError, match="conflicts with maturity-scaled"):
        resolve_config(other)


@pytest.mark.parametrize(("limits", "message"), [
    ({"max_branch_proposals": 1}, "Branch proposal limit exceeded"),
    ({"max_nodes": 20}, "Node limit exceeded"),
])
def test_large_draw_is_rejected_without_writing_graph(tmp_path, limits, message):
    spec = small_forest()
    spec["limits"] = limits
    spec["features"]["branching"]["settings"]["by_order"]["1"]["mean_spacing_cm"] = .002
    with pytest.raises(ValueError, match=message):
        simulate(spec, tmp_path / "failed")
    assert not (tmp_path / "failed").exists()


def test_proposal_limit_is_execution_only():
    spec = small_forest()
    limited = deepcopy(spec)
    limited["limits"] = {"max_branch_proposals": 1000}
    a, b = map(resolve_config, (spec, limited))
    assert a.hashes["effective_model_sha256"] == b.hashes["effective_model_sha256"]
    assert a.limits["max_branch_proposals"] == 100_000
    assert b.limits["max_branch_proposals"] == 1000
