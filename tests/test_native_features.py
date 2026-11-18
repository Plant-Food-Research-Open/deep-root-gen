"""Schema-3 features as leaf laws inside the one engine (invented inputs only)."""

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from deeprootgen.model import RootSystemSimulation
from deeprootgen.model.cohort_geometry import taper_diameter

ROOT = Path(__file__).resolve().parents[1]
BASE = json.loads((ROOT / "examples/design/native_feature_options.proposed.json").read_text())
CURVE_1 = BASE["features"]["curvature"]["settings"]["by_order"]["1"]
INSERTION = dict(CURVE_1, initial_heading="insertion_angle", insertion_mean_deg=45.0, insertion_sd_deg=10.0)
DISK = dict(layout="disk", radius_cm=0.5, depth_range_cm=[1.0, 2.0])
HEADING = dict(law="radial_inclination", inclination_mean_deg=30.0, inclination_sd_deg=10.0,
               inclination_bounds_deg=[0.0, 90.0])
MATURITY = dict(BASE["features"]["cohort_maturity"]["settings"], scale_branch_probability=True)
MODES = ["legacy", "fichtl2024"]


def spec(mode="fichtl2024", **features):
    value = copy.deepcopy(BASE)
    value["parameters"]["tropism_mode"] = mode
    if mode == "fichtl2024":
        value["parameters"]["gravitropism"] = 0.0
    for name, settings in features.items():
        value["features"][name]["enabled"] = True
        if settings is not None:
            value["features"][name]["settings"] = settings
    return value


def run(value):
    sim = RootSystemSimulation(random_seed=value["random_seed"], simulation_tag=value["simulation_tag"])
    sim.run(copy.deepcopy(value))
    return sim


def tables(sim):
    nodes, edges = sim.G.as_df()
    return tuple(hashlib.sha256(f.to_csv(index=False, float_format="%.17g").encode()).hexdigest() for f in (nodes, edges))


def organs(sim):
    return [o for order in sorted(sim.organs) for o in sim.organs[order]]


def arc_lookup(organ):
    return np.cumsum(organ.get_lengths())


ALONE = {
    "taper": dict(taper=None),
    "lengths": dict(lengths=None),
    "branching": dict(branching=None),
    "origins-point": dict(primary_origins=dict(layout="point", x_cm=1.0, y_cm=-2.0, depth_cm=3.0)),
    "origins-disk": dict(primary_origins=DISK),
    "curvature-1..3": dict(curvature=dict(by_order={"1": CURVE_1, "2": INSERTION, "3": INSERTION})),
}


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("name", sorted(ALONE))
def test_each_feature_alone_switches_off_to_the_exact_baseline(mode, name):
    baseline = run(spec(mode))
    on = run(spec(mode, **ALONE[name]))
    again = run(spec(mode))
    assert tables(baseline) == tables(again)
    assert tables(on) != tables(baseline)
    assert on.result.metadata["effective_model_sha256"] != baseline.result.metadata["effective_model_sha256"]


@pytest.mark.parametrize("mode", MODES)
def test_taper_keeps_geometry_conserves_volume_and_classifies_segments(mode):
    off, on = run(spec(mode)), run(spec(mode, taper=None))
    threshold_mm = BASE["parameters"]["fine_root_threshold"] * 10.0
    density = BASE["parameters"]["root_tissue_density"]
    for a, b in zip(organs(off), organs(on)):
        arcs_a, arcs_b = arc_lookup(a), arc_lookup(b)
        for arc, xyz in zip(arcs_a, a.get_coordinates()):
            k = int(np.argmin(np.abs(arcs_b - arc)))
            assert abs(arcs_b[k] - arc) < 1e-12
            np.testing.assert_array_equal(b.get_coordinates()[k], xyz)
        plan = b.plan
        length, base, tip, mid = plan["length"], plan["base"], plan["tip"], plan["midpoint"]
        middle = tip + mid * (base - tip)
        volume = np.pi / 12 * (length / 2) * ((base**2 + base * middle + middle**2) + (middle**2 + middle * tip + tip**2))
        assert b.mass == pytest.approx(density * volume, rel=1e-12)
        ends = np.r_[0.0, arcs_b]
        diameters = taper_diameter(ends, length, base, tip, mid)
        for (d0, d1), node in zip(zip(diameters[:-1], diameters[1:]), b.segments):
            fine = node.node_data.diameter * 10 <= np.nextafter(threshold_mm, np.inf)
            assert node.node_data.root_type == ("fine" if fine else "structural")
            # The fine cutoff is a cut: no segment straddles it (beyond rounding).
            cutoff = threshold_mm / 10
            assert not (min(d0, d1) < cutoff * (1 - 1e-12) and max(d0, d1) > cutoff * (1 + 1e-12))
    assert set(on.result.organ_table.material_law) == {"point_taper"}


@pytest.mark.parametrize("mode", MODES)
def test_length_laws_respect_their_support(mode):
    on = run(spec(mode, lengths=None))
    for organ in on.organs[2]:
        assert min(abs(organ.get_lengths().sum() - v) for v in (2.0, 3.0)) < 1e-9
    for organ in on.organs.get(3, []):
        assert 1.0 <= organ.get_lengths().sum() <= 3.0


@pytest.mark.parametrize("mode", MODES)
def test_branching_law_sites_counts_and_terminal_order(mode):
    on = run(spec(mode, branching=None))
    for organ in on.organs[1] + on.organs[2]:
        daughters = organ.child_organs
        assert len(daughters) <= 2
        arcs = sorted(float(arc_lookup(organ)[organ.segments.index(d.parent_node)]) for d in daughters)
        if arcs:
            assert abs(arcs[0] - 0.5) < 1e-12 and all(a >= 0.5 for a in arcs)
    assert all(not organ.child_organs for organ in on.organs.get(3, []))


@pytest.mark.parametrize("mode", MODES)
def test_origins_translate_complete_trees(mode):
    off = run(spec(mode))
    point = run(spec(mode, primary_origins=dict(layout="point", x_cm=1.0, y_cm=-2.0, depth_cm=3.0)))
    base = point.G.base_node.node_data
    assert (base.x, base.y, base.z) == (1.0, -2.0, -3.0)
    disk = run(spec(mode, primary_origins=DISK))
    assert len(disk.G.bases) == len(disk.organs[1]) == 2
    for primary_off, primary_on, anchor in zip(off.organs[1], disk.organs[1], disk.G.bases):
        a = anchor.node_data
        assert primary_on.parent_node is anchor
        assert np.hypot(a.x, a.y) <= 0.5 and -2.0 <= a.z <= -1.0
        if mode == "fichtl2024" or not primary_off.validation_reorientations:
            np.testing.assert_allclose(primary_on.get_coordinates() - [a.x, a.y, a.z], primary_off.get_coordinates(),
                                       atol=1e-9)
    nodes, _ = disk.result.observation_tables(disk.G)
    assert nodes.vine_id.nunique() == 1 and nodes.loc[nodes.order.eq(0)].plant_id.nunique() == 2


def test_maturity_scales_primaries_and_never_moves_origins():
    with_taper = dict(taper=None, branching=None, primary_origins=DISK)
    off, on = run(spec(**with_taper)), run(spec(**with_taper, cohort_maturity=MATURITY))
    for a, b in zip(off.organs[1], on.organs[1]):
        m = b.plan["maturity"]
        assert (b.plan["label"], m == 1.0) in (("established", True), ("later", False))
        assert b.get_lengths().sum() == pytest.approx(a.get_lengths().sum() * m ** MATURITY["length_power"], rel=1e-12)
        assert b.plan["base"] == pytest.approx(a.plan["base"] * m ** MATURITY["diameter_power"], rel=1e-12)
    origins = lambda sim: [(n.node_data.x, n.node_data.y, n.node_data.z) for n in sim.G.bases]  # noqa: E731
    assert origins(off) == origins(on)


def test_parent_cap_limits_daughter_base_at_the_birth_site():
    on = run(spec(taper=None, parent_diameter_cap=dict(fraction_max=0.5)))
    checked = 0
    for daughter in organs(on):
        parent = getattr(daughter.parent_node, "organ", None)
        if parent is None:
            continue
        site = float(arc_lookup(parent)[parent.segments.index(daughter.parent_node)])
        limit = 0.5 * taper_diameter(site, parent.plan["length"], parent.plan["base"], parent.plan["tip"],
                                     parent.plan["midpoint"])
        assert daughter.plan["base"] <= limit * (1 + 1e-15)
        checked += 1
    assert checked


def test_attachment_relocation_moves_sites_distally_and_keeps_dimensions():
    off = run(spec())
    on = run(spec(attachment_relocation=None))
    fraction = BASE["features"]["attachment_relocation"]["settings"]["distal_fraction"]
    for p_off, p_on in zip(off.organs[1], on.organs[1]):
        total = float(arc_lookup(p_off)[-1])
        assert float(arc_lookup(p_on)[-1]) == pytest.approx(total, rel=1e-12)
        for d_off, d_on in zip(p_off.child_organs, p_on.child_organs):
            old = float(arc_lookup(p_off)[p_off.segments.index(d_off.parent_node)])
            new = float(arc_lookup(p_on)[p_on.segments.index(d_on.parent_node)])
            assert new == pytest.approx(fraction * total + (1 - fraction) * old, rel=1e-12)
            np.testing.assert_array_equal(d_on.get_lengths(), d_off.get_lengths())
            np.testing.assert_array_equal(d_on.get_diameters(), d_off.get_diameters())


@pytest.mark.parametrize("mode", MODES)
def test_daughter_order_curvature_starts_at_realized_parents(mode):
    on = run(spec(mode, curvature=dict(by_order={"1": CURVE_1, "2": INSERTION})))
    assert {r["order"] for r in on.result.diagnostics["curvature"]} == {1, 2}
    for organ in on.organs[2]:
        attachment = organ.parent_node.node_data
        first = organ.get_coordinates()[0] - [attachment.x, attachment.y, attachment.z]
        assert np.linalg.norm(first) == pytest.approx(organ.segments[0].node_data.length, rel=1e-9)
    issued = {(s["namespace"], s["ids"][0]) for s in on.streams.issued}
    assert all(("feature.insertion", int(o.segments[0].node_data.organ_id)) in issued for o in on.organs[2])


def test_legacy_curvature_must_cover_a_prefix_of_orders():
    with pytest.raises(ValueError, match="prefix"):
        run(spec("legacy", curvature=dict(by_order={"2": INSERTION})))


PLANNED = dict(
    curvature=dict(by_order={"1": dict(CURVE_1, initial_heading="origin_heading"), "2": INSERTION, "3": INSERTION}),
    taper=None,
    lengths=dict(by_order={k: dict(law="bounded_lognormal", mean=m, sd=m / 10, min=m / 2, max=m * 2)
                           for k, m in (("1", 8.0), ("2", 3.0), ("3", 1.0))}),
    branching=None,
    primary_origins=dict(DISK, heading=HEADING),
    cohort_maturity=MATURITY,
    parent_diameter_cap=None,
)


def test_fully_replaced_construction_draws_nothing_natively():
    sim = run(spec(**PLANNED))
    assert sim.result.resolved["laws"]["construction"] == "planned"
    assert sim.rng.bit_generator.state == RootSystemSimulation(random_seed=42).rng.bit_generator.state
    assert len(sim.G.bases) == 2 and sim.result.metadata["capabilities"]["tree_to_vine_map"]
    assert set(sim.result.node_metadata.cohort) <= {"established", "later"}
    for organ in organs(sim):
        bounds = {1: (4.0, 16.0), 2: (1.5, 6.0), 3: (0.5, 2.0)}[organ.plan["order"]]
        maturity = organ.plan["maturity"] ** MATURITY["length_power"]
        assert bounds[0] * maturity - 1e-12 <= organ.plan["length"] <= bounds[1] * maturity + 1e-12
    edited = spec(**PLANNED)
    edited["parameters"].update(min_primary_length=1.0, root_vary=89.0)  # dormant native fallbacks
    again = run(edited)
    assert tables(again) == tables(sim)
    assert again.result.metadata["effective_model_sha256"] == sim.result.metadata["effective_model_sha256"]


COMBINATIONS = {
    "curvature+taper": dict(curvature=dict(by_order={"1": CURVE_1}), taper=None),
    "origins+curvature": dict(curvature=dict(by_order={"1": dict(CURVE_1, initial_heading="origin_heading")}),
                              primary_origins=dict(DISK, heading=HEADING)),
    "taper+cap": dict(taper=None, parent_diameter_cap=None),
    "maturity+taper": dict(taper=None, cohort_maturity=dict(MATURITY, scale_branch_probability=False)),
    "maturity+probability-branching": dict(taper=None, branching=None, cohort_maturity=MATURITY),
}


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("name", sorted(COMBINATIONS))
def test_representative_combinations_run_and_conserve_material(mode, name):
    sim = run(spec(mode, **COMBINATIONS[name]))
    density = BASE["parameters"]["root_tissue_density"]
    for organ in organs(sim):
        if getattr(organ, "plan", {}).get("base") is None:
            continue
        plan = organ.plan
        middle = plan["tip"] + plan["midpoint"] * (plan["base"] - plan["tip"])
        volume = np.pi / 12 * (plan["length"] / 2) * (
            plan["base"] ** 2 + plan["base"] * middle + 2 * middle**2 + middle * plan["tip"] + plan["tip"] ** 2
        )
        assert organ.mass == pytest.approx(density * volume, rel=1e-12)
    assert sim.result.engine["lifecycle"][-1] == "publish"


def test_fully_replaced_example_file_runs_with_no_native_fallback_values():
    path = ROOT / "examples/design/native_features_fully_replaced.json"
    value = json.loads(path.read_text())
    assert "min_primary_length" not in value["parameters"]
    sim = RootSystemSimulation(random_seed=value["random_seed"], simulation_tag=value["simulation_tag"])
    sim.run(path)
    assert sim.result.resolved["laws"]["construction"] == "planned"
    assert len(sim.G.bases) == value["parameters"]["outer_root_num"] + value["parameters"]["inner_root_num"]


def test_corner_one_ulp_from_a_material_cut_merges_instead_of_failing():
    """Review case: curve corner at 1.0 and taper midpoint cut at 1.0000000000000002."""
    value = spec(
        curvature=dict(by_order={"1": CURVE_1, "2": dict(INSERTION, step_cm=0.5)}),
        taper=dict(by_order={"2": dict(BASE["features"]["taper"]["settings"]["by_order"]["2"],
                                       midpoint_diameter_fraction=0.7)}),
        lengths=dict(by_order={"2": dict(law="discrete_cdf", lengths_cm=[2.0], cumulative_probabilities=[1.0])}),
    )
    density = BASE["parameters"]["root_tissue_density"]
    for seed in range(40):
        value["random_seed"] = seed
        sim = run(value)
        for organ in sim.organs[2]:
            plan = organ.plan
            middle = plan["tip"] + plan["midpoint"] * (plan["base"] - plan["tip"])
            volume = np.pi / 12 * (plan["length"] / 2) * (
                plan["base"] ** 2 + plan["base"] * middle + 2 * middle**2 + middle * plan["tip"] + plan["tip"] ** 2
            )
            assert organ.mass == pytest.approx(density * volume, rel=1e-9)


@pytest.mark.parametrize(
    "features,match",
    [
        (dict(primary_origins=dict(DISK, heading=dict(HEADING, inclination_bounds_deg=[30.0, 30.0001])),
              curvature=dict(by_order={"1": dict(CURVE_1, initial_heading="origin_heading")})), "Inclination law"),
        (dict(curvature=dict(by_order={"1": CURVE_1, "2": dict(INSERTION, insertion_mean_deg=0.0,
                                                               insertion_sd_deg=1e6)})), "insertion law"),
    ],
)
def test_rejection_samplers_must_accept_enough_before_any_state(features, match):
    value = spec(**features)
    sim = RootSystemSimulation(random_seed=value["random_seed"])
    state = copy.deepcopy(sim.rng.bit_generator.state)
    with pytest.raises(ValueError, match=match):
        sim.run(value)
    assert len(sim.G.nodes) == 1 and not sim.organs and sim.rng.bit_generator.state == state


def test_native_primary_groups_must_be_nonempty_for_native_placement():
    value = spec()
    value["parameters"]["inner_root_num"] = 0
    with pytest.raises(ValueError, match="at least 1"):
        run(value)
