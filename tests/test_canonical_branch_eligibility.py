"""Diameter at a daughter site, parent-order count overrides and native draws."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from deeprootgen.model import RootSystemSimulation


def config():
    return json.loads((Path(__file__).resolve().parents[1] / "examples/design/native_crown_0_20cm.json").read_text())


def run(value):
    simulation = RootSystemSimulation(random_seed=value["random_seed"])
    simulation.run(value)
    return simulation


def counts(simulation):
    return [len(organs) for organs in simulation.organs.values()]


def test_apex_controls_diameters_and_default_branch_threshold_controls_births():
    value = config()
    value["parameters"].update(base_diameter=.10, apex_diameter=.05, diameter_reduction=.9)
    value["parameters"]["min_branching_diameter_cm"] = 0.
    off = run(value)
    assert counts(off) == [2, 2, 4]
    parent_diameters = [org.parent_node.node_data.diameter for org in off.organs[2] + off.organs[3]]
    assert max(parent_diameters) < .093
    assert sum(d < .05 for d in parent_diameters) == 3
    del value["parameters"]["min_branching_diameter_cm"]
    on = run(value)
    assert counts(on) == [2, 0, 0]
    receipt = on.result.engine["law_receipts"]["branch_eligibility"]
    assert receipt["min_branching_diameter_cm"] == .093
    assert receipt["by_parent_order"]["1"] == dict(candidates=2, eligible=0, diameter_below_branch_minimum=2)


@pytest.mark.parametrize("local_diameter, expected", [
    (np.nextafter(.093, 0.), 0), (.093, 1), (np.nextafter(.093, 1.), 1),
])
def test_native_cylinder_exact_equality_including_one_primary(local_diameter, expected):
    value = config()
    value["parameters"].update(
        min_branching_diameter_cm=.093, base_diameter=float(local_diameter), apex_diameter=float(local_diameter),
        diameter_reduction=0., primary_root_count=1, outer_primary_fraction=1.,
        daughters_by_parent_order={"1": 1, "2": 0},
    )
    value["parameters"].pop("daughters_per_parent", None)
    sim = run(value)
    assert counts(sim) == [1, expected, 0]


def test_active_taper_uses_final_relocated_site_before_spending_organ_budget():
    value = config()
    value["parameters"].update(primary_root_count=1, outer_primary_fraction=0., min_branching_diameter_cm=.093)
    taper = value["features"]["taper"]
    taper["enabled"] = True
    taper["settings"]["by_order"] = {"1": taper["settings"]["by_order"]["1"]}
    on_original_site = run(value)
    assert len(on_original_site.organs[2]) == 1
    relocation = value["features"]["attachment_relocation"]
    relocation["enabled"] = True
    relocation["settings"]["distal_fraction"] = .6
    value["limits"] = {"max_organs": 1}
    moved = run(value)
    assert counts(moved) == [1, 0, 0]
    assert moved.result.engine["law_receipts"]["branch_eligibility"]["by_parent_order"]["1"][
        "diameter_below_branch_minimum"] == 1


def test_tapered_daughter_cap_tracks_relocated_parent_material():
    from deeprootgen.model.cohort_geometry import taper_diameter

    value = config()
    value["parameters"].update(primary_root_count=1, min_branching_diameter_cm=0.)
    value["features"]["taper"]["enabled"] = True
    value["features"]["parent_diameter_cap"] = dict(enabled=True, settings={"fraction_max": .4})
    original = run(value)
    relocation = value["features"]["attachment_relocation"]
    relocation["enabled"] = True
    relocation["settings"]["distal_fraction"] = .6
    moved = run(value)
    source, relocated = original.organs[2][0], moved.organs[2][0]
    assert relocated.axis_state.material["base"] < source.axis_state.material["base"]
    for sim, daughter in [(original, source), (moved, relocated)]:
        parent = sim.organs[1][0]
        arc = np.cumsum(parent.get_lengths())[parent.segments.index(daughter.parent_node)]
        profile = parent.axis_state.material
        local = taper_diameter(arc, profile["length"], profile["base"], profile["tip"], profile["midpoint"])
        assert daughter.axis_state.material["base"] == pytest.approx(.4 * local, rel=1e-12)


def test_material_replacement_skips_native_diameter_draw_and_keeps_length_partition_draws():
    value = config()
    value["parameters"]["min_branching_diameter_cm"] = 0.
    for key in ("lengths", "taper"):
        value["features"][key]["enabled"] = True
    laws = value["features"]["lengths"]["settings"]["by_order"]
    laws["1"] = dict(law="bounded_lognormal", mean=5., sd=0., min=5., max=5.)
    sim = run(value)
    organ = sim.organs[1][0]
    organ.rng = np.random.default_rng(913)
    reference = copy.deepcopy(organ.rng)
    organ.init_diameters(3, apex_diameter=None)
    proportions = organ.init_lengths(3)
    expected = np.sort(reference.uniform(size=3))[::-1]
    np.testing.assert_array_equal(proportions, expected / expected.sum())
    assert organ.rng.bit_generator.state == reference.bit_generator.state
    cdf_organ = sim.organs[2][0]
    cdf_organ.rng = reference
    cdf_organ.init_lengths(3)
    assert reference.bit_generator.state == organ.rng.bit_generator.state
    assert cdf_organ.current_length_diagnostics["legacy_compatibility_draw_count"] == 0


def test_fixed_material_and_length_do_not_require_keyed_seed():
    value = config()
    value["random_seed"] = None
    value["parameters"].update(max_order=1, primary_root_count=1)
    value["features"] = {
        "lengths": dict(enabled=True, settings=dict(by_order={"1": 5.})),
        "taper": dict(enabled=True, settings=dict(by_order={"1": dict(base_cm=.1, tip_cm=.01)})),
    }
    sim = run(value)
    assert counts(sim) == [1]
    assert sim.result.engine["keyed_streams"] == []


@pytest.mark.parametrize("threshold, expected", [(.07, [2, 2, 8]), (.16, [2, 0, 0])])
def test_diameter_gate_uses_only_eligible_sites_for_sibling_rank(threshold, expected):
    from deeprootgen.data_model.migration import convert_input
    from tests.test_tertiary_length_rank import parameters

    value = convert_input(parameters(.7).model_dump(mode="json", exclude_none=True))
    value["parameters"]["min_branching_diameter_cm"] = threshold
    sim = run(value)
    assert counts(sim) == expected
    for parent in sim.organs[2]:
        family = parent.tertiary_length_rank_family
        assert len(family["source_indices"]) == len(parent.child_organs)


def test_exact_order_quota_reports_blocked_sites_before_child_allocation():
    from deeprootgen.data_model.migration import convert_input
    from tests.test_order5_core import parameters

    value = convert_input(parameters(False).model_dump(mode="json", exclude_none=True))
    value["parameters"]["min_branching_diameter_cm"] = 1.
    sim = RootSystemSimulation(random_seed=value["random_seed"])
    with pytest.raises(ValueError, match="Exact daughter count infeasible"):
        sim.run(value)
    assert not sim.organs[2] and sim.result is None


def test_first_curved_interval_uses_its_arclength_and_realized_endpoint():
    from deeprootgen.model.materialize import AxisCurve
    from deeprootgen.model.root import RootOrgan

    points = np.array([[0., 0., 0.], [0., 0., -1.], [1., 0., -1.]])
    curve = AxisCurve(2, np.arange(3.), points, np.array([2.]), {})
    organ = RootOrgan.__new__(RootOrgan)
    organ.parent_node = SimpleNamespace(node_data=SimpleNamespace(x=0., y=0., z=0.))
    end = SimpleNamespace(x=1., y=0., z=-1., length=2., order=2)
    organ.segments = [SimpleNamespace(node_data=end)]
    organ.child_organs = []
    organ.invalid_root = False
    organ.axis_state = SimpleNamespace(curve=curve)
    organ.input_parameters = SimpleNamespace(canonical_generation=True)
    organ.rng = np.random.default_rng(1)
    organ.validate(0., allow_reorient=False)
    assert not organ.invalid_root
    end.x += .1
    organ.validate(0., allow_reorient=False)
    assert organ.invalid_root
