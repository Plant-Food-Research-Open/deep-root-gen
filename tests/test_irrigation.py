"""Synthetic checks of wet contour integration and seeded terminal recruitment."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import resolve_config
from deeprootgen.data_model.irrigation import Irrigation
from deeprootgen.data_model.simulation_form import (
    simulation_controls,
    simulation_document,
)
from deeprootgen.model import RootSystemSimulation
from deeprootgen.model.irrigation import WetContour, exposure, survey_points
from deeprootgen.model.irrigation_branching import _support
from deeprootgen.research.neighbourhood import generate_neighbourhood, layout_origins

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
BROAD = dict(treatment="broad_surface", irrigation_depth_cm=0, peak_multiplier=2)


def surface_line(**opts):
    return Irrigation(
        **dict(
            dict(
                treatment="surface_drip",
                irrigation_depth_cm=0.0,
                across_radius_cm=0.02,
                line_offsets_cm=[0.37],
            ),
            **opts
        )
    )


def contour(x, zone, diam=0.093):
    s = np.asarray(x, float)
    curve = SimpleNamespace(
        stations=s, points=np.stack([s, s * 0, s * 0 - 30], axis=-1)
    )
    return WetContour(
        zone, curve, 0.0, s[0], s[-1], None, s[1:], np.full(len(s) - 1, diam), 0.093
    )


def test_depth_and_outlet_geometry():
    d = np.array([-1.0, 0.0, 25.0, 30.0, 40.0, 45.0, 50.0, 60.0])
    xyz = np.stack([d * 0, d * 0, d], axis=-1)
    np.testing.assert_allclose(
        exposure(Irrigation(**BROAD), xyz), [0, 1, 1, 1, 1, 0.5, 0, 0]
    )
    buried = Irrigation(
        treatment="buried_drip",
        irrigation_depth_cm=30.0,
        upper_radius_cm=10.0,
        lower_radius_cm=20.0,
        across_radius_cm=5.0,
        line_offsets_cm=[0.0, 4.0],
        emitter_spacing_cm=20.0,
        emitter_origin_y_cm=5.0,
        along_radius_cm=8.0,
    )
    np.testing.assert_allclose(
        exposure(
            buried,
            [[0, 5, 30], [4, 25, 30], [0, 5, 25], [0, 5, 40], [0, 15, 30], [9, 5, 30]],
        ),
        [1, 1, 0.5, 0.5, 0, 0],
    )
    q = surface_line(origin_x_cm=5, reflect_x=-1, reflect_y=-1)
    np.testing.assert_array_equal(
        survey_points(np.array([[2, 3, -4]]), q, 2), [[3, -3, 6]]
    )


def test_narrow_crossing_and_partition_invariance():
    wet = surface_line()
    a = contour([0, 2], wet)
    b = contour(np.linspace(0, 2, 53), wet)
    for item in [a, b]:
        assert item.eligible == pytest.approx(2)
        assert item.H == pytest.approx(0.02, abs=2e-12)
    assert contour([0, 2], wet, diam=np.nextafter(0.093, 0)).H == 0

    def draw(item):
        return item.sample(np.random.default_rng(4277), 50, True)

    np.testing.assert_allclose(draw(a), draw(b), atol=2e-12)
    assert np.all(np.abs(draw(a) - 0.37) < 0.02)


def test_poisson_example_and_active_zero():
    law = dict(
        basal_exclusion_cm=0,
        apical_exclusion_cm=0,
        mean_spacing_cm=10,
        active=True,
        decision="poisson_zero",
    )
    parent = SimpleNamespace(plan=dict(length_poisson=law))
    _, _, rate, active, decision = _support(
        parent, SimpleNamespace(stations=[0, 100.0])
    )
    assert active and decision == "poisson_zero"
    zone = surface_line(across_radius_cm=20.0, line_offsets_cm=[50.0])
    item = contour([0, 100], zone)
    assert rate * item.eligible == pytest.approx(10.0)
    assert rate * item.H == pytest.approx(2.0)
    rng = np.random.default_rng(94256)
    counts = rng.poisson(rate * item.H, size=10000)
    assert abs(counts.mean() - 2) < 0.06 and abs(counts.var() - 2) < 0.15


def forest():
    d = json.loads((EXAMPLES / "research/native_cohort_synthetic.json").read_text())
    for k, law in d["features"]["branching"]["settings"]["by_order"].items():
        if int(k) < 5:
            law.update(
                branch_probability=1.0,
                daughter_probabilities=[0, 0, 1] if k == "4" else [1.0],
            )
    fixed = dict(mean=0.3, sd=0.0, min=0.3, max=0.3)
    for law in d["features"]["taper"]["settings"]["by_order"].values():
        law.update(base_cm=fixed, tip_cm=fixed)
    d["limits"] = {}
    d["features"].pop("diameter_cap", None)
    return d


def run(d):
    sim = RootSystemSimulation(random_seed=d["random_seed"])
    sim.run(d)
    return sim


def test_off_forms_and_form_round_trip():
    d = forest()
    reference = run(d)
    for off in [
        None,
        "rainfed",
        {"irrigation_depth_cm": None},
        {"irrigation_depth_cm": "rainfed"},
        dict(BROAD, peak_multiplier=1),
    ]:
        actual = run(dict(d, irrigation=off))
        for x, y in zip(reference.G.as_df(), actual.G.as_df()):
            pd.testing.assert_frame_equal(x, y, check_exact=True)
        assert actual.rng.bit_generator.state == reference.rng.bit_generator.state
        assert "irrigation" not in actual.result.diagnostics
        assert (
            reference.result.metadata["effective_model_sha256"]
            == actual.result.metadata["effective_model_sha256"]
        )
    config = dict(d, irrigation=BROAD)
    keys = ["simulation_tag", "random_seed", "advanced_settings"]
    back = simulation_document(dict(zip(keys, simulation_controls(config, keys))))
    assert back["irrigation"] == BROAD
    with pytest.raises(ValueError):
        resolve_config(dict(d, irrigation=dict(BROAD, parent_order=2)))


def test_paired_controls_and_attachment_coordinates():
    d = forest()
    base = run(d)
    results = {
        mode: run(dict(d, irrigation=dict(BROAD, response=mode)))
        for mode in ("add", "redistribute", "uniform_extra")
    }
    base_ids = set(o.axis_state.biological_id for o in base.organs[5])

    def by_parent(sim):
        return sim.result.diagnostics["irrigation"]["parents"]

    assert [p["drawn_extra"] for p in by_parent(results["add"])] == [
        p["drawn_extra"] for p in by_parent(results["uniform_extra"])
    ]
    assert (
        len(results["add"].organs[5])
        > len(base_ids)
        == len(results["redistribute"].organs[5])
    )
    for mode, sim in results.items():
        organs = {o.axis_state.biological_id: o for o in sim.organs[5]}
        for before in base.organs[5]:
            if mode != "redistribute":
                np.testing.assert_allclose(
                    before.axis_state.curve.points,
                    organs[before.axis_state.biological_id].axis_state.curve.points,
                    atol=1e-11,
                )
        for p in by_parent(sim):
            assert p["accepted_extra"] == p["drawn_extra"]
            for b in p["births"]:
                organ = organs[b["daughter_id"]]
                np.testing.assert_allclose(
                    organ.axis_state.curve.points[0] * [1, 1, -1]
                    + [0, 0, d["parameters"].get("soil_surface_z_cm", 0)],
                    [b["x_cm"], b["y_cm"], b["depth_cm"]],
                    atol=1e-10,
                )
                assert (
                    organ.parent_node.organ.axis_state.biological_id == p["parent_id"]
                )
                if mode == "add":
                    assert b["exposure"] > 0
    with pytest.raises(ValueError, match="proposal limit"):
        run(dict(d, irrigation=BROAD, limits={"max_branch_proposals": 1}))


def test_spacings_and_explicit_origins():
    xy = layout_origins(None, 170.0, 280.0)
    assert (
        xy[4] == (0.0, 0.0) and xy[0] == (-280.0, -170.0) and xy[-1] == (280.0, 170.0)
    )
    for args in [(None, 0.0, 280.0), (None, 170.0, None), (xy, 170.0, 280.0)]:
        with pytest.raises(ValueError):
            layout_origins(*args)
    d = json.loads((EXAMPLES / "synthetic_minimal.json").read_text())
    g = generate_neighbourhood(
        d, mode="independent", vine_distance_cm=170.0, row_distance_cm=280.0
    )
    assert len(g.plants) == g.plants.seed.nunique() == 9
    assert list(zip(g.plants.x_cm, g.plants.y_cm)) == xy


def test_export_reload_and_seeded_poisson_with_irrigation(tmp_path):
    from deeprootgen.cli import simulate

    d = forest()
    d["features"]["cohort_maturity"]["enabled"] = False
    law = dict(
        law="length_poisson_sites_v1",
        basal_exclusion_cm=0.5,
        apical_exclusion_cm=0.5,
        mean_spacing_cm=0.8,
        branch_probability=1.0,
    )
    d["features"]["branching"]["settings"]["by_order"]["4"] = law
    d["irrigation"] = BROAD
    output = tmp_path / "wet"
    simulate(d, output)
    records = json.loads((output / "irrigation.json").read_text())["parents"]
    assert any(r["drawn_extra"] for r in records)
    assert all(p["rate_per_cm"] == 1.25 for p in records)
    saved = json.loads((output / "parameters.json").read_text())
    again = run(saved)
    assert records == again.result.diagnostics["irrigation"]["parents"]


def test_translated_seed_re_evaluates_surveyed_one_sided_strip():
    d = forest()
    d["irrigation"] = dict(
        treatment="surface_drip",
        irrigation_depth_cm=0,
        line_offsets_cm=[45.0],
        origin_x_cm=45.0,
        reflect_x=-1,
        across_radius_cm=40.0,
        peak_multiplier=8.0,
    )
    origins = [(0.0, 0.0), (200.0, 0.0)]
    planted = generate_neighbourhood(d, origins)
    assert list(planted.plants.x_cm) == [45, 245]
    np.testing.assert_array_equal(planted.plants.seed, [d["random_seed"]] * 2)
    # The first crown lies beside the surveyed line, the second is outside its footprint.
    counts = planted.nodes.query("order==5").groupby("plant_id").organ_id.nunique()
    assert counts[0] > counts[1]
    direct = run(dict(d, irrigation="rainfed"))
    assert counts[1] == len(direct.organs[5])
    for xy, origin in zip(origins, planted.plants.itertuples()):
        native = run(dict(d, irrigation=dict(d["irrigation"], origin_x_cm=origin.x_cm)))
        nodes, _ = native.G.as_df()
        out = planted.nodes[planted.nodes.plant_id == origin.plant_id]
        np.testing.assert_allclose(out.x, origin.x_cm - nodes.x)


UPSTREAM = dict(BROAD, order_sensitivity={"4": 1.0})


def test_non_terminal_recruitment_keeps_existing_axes_and_builds_subtrees():
    d = forest()
    # Several order-4 sites per order-3 parent give a positive recruitment rate.
    d["features"]["branching"]["settings"]["by_order"]["3"]["daughter_probabilities"] = [0, 0, 1]
    terminal = run(dict(d, irrigation=BROAD))
    wet = run(dict(d, irrigation=UPSTREAM))
    report = wet.result.diagnostics["irrigation"]
    upstream = report["upstream"]["4"]["parents"]
    added = sum(p["accepted_extra"] for p in upstream)
    subtree = sum(p["subtree_organs"] for p in upstream)
    assert added > 0 and subtree > 0
    assert all(p["accepted_extra"] == p["drawn_extra"] for p in upstream)
    assert len(wet.organs[4]) == len(terminal.organs[4]) + added
    # Native order-5 children of recruited order-4 axes, plus terminal wet births.
    rainfed = run(dict(d, irrigation=None))
    extra5 = sum(p["accepted_extra"] for p in report["parents"])
    assert len(wet.organs[5]) == len(rainfed.organs[5]) + subtree + extra5
    # Recruitment inserts attachment nodes but never moves an existing axis.
    for order in (3, 4):
        realized = {o.axis_state.biological_id: o for o in wet.organs[order]}
        for before in terminal.organs[order]:
            np.testing.assert_allclose(
                before.axis_state.curve.points,
                realized[before.axis_state.biological_id].axis_state.curve.points,
                atol=1e-11,
            )
    # Every recruited axis is realized from its wet attachment on its parent.
    born = {b["daughter_id"]: b for p in upstream for b in p["births"]}
    for organ in wet.organs[4]:
        if organ.axis_state.biological_id in born:
            b = born[organ.axis_state.biological_id]
            np.testing.assert_allclose(
                organ.axis_state.curve.points[0] * [1, 1, -1]
                + [0, 0, d["parameters"].get("soil_surface_z_cm", 0)],
                [b["x_cm"], b["y_cm"], b["depth_cm"]],
                atol=1e-10,
            )
            assert b["exposure"] > 0
    nodes, edges = wet.G.as_df()
    assert len(edges) == len(nodes) - (nodes.order == 0).sum()
    assert set(edges.parent_id) <= set(nodes.node_id)
    again = run(dict(d, irrigation=UPSTREAM))
    assert again.result.diagnostics["irrigation"] == report
    # Zero sensitivity is the terminal-only law, draw for draw.
    zero = run(dict(d, irrigation=dict(BROAD, order_sensitivity={"4": 0.0})))
    for x, y in zip(terminal.G.as_df(), zero.G.as_df()):
        pd.testing.assert_frame_equal(x, y, check_exact=True)


@pytest.mark.parametrize(
    "bad",
    [
        {"order_sensitivity": {"6": 1.0}},
        {"order_sensitivity": {"1": 1.0}},
        {"order_sensitivity": {"5": 0.5}},
        {"order_sensitivity": {"4": 1.5}},
        {"order_sensitivity": {"4": 0.5}, "response": "redistribute"},
    ],
)
def test_order_sensitivity_validation(bad):
    with pytest.raises(ValueError):
        resolve_config(dict(forest(), irrigation=dict(BROAD, **bad)))


def test_primary_azimuth_bias_and_uniform_default():
    d = forest()
    count = len(run(d).organs[1])
    biased = json.loads(json.dumps(d))
    biased["features"]["primary_origins"]["settings"]["azimuth_groups"] = [
        dict(primary_indices=list(range(count)), mean_deg=180.0, concentration=50.0)]
    sim = run(biased)
    angles = np.array(
        [r["polar_angle_rad"] for r in sim.result.diagnostics["primary_origins"]["primaries"]]
    )
    assert np.all(np.abs(np.angle(np.exp(1j * (angles - np.pi)))) < 0.6)
    starts = np.array([o.axis_state.curve.points[0] for o in sim.organs[1]])
    assert np.all(starts[:, 0] <= 0)
    for bad in ([dict(primary_indices=[0], mean_deg=180.0)], [dict(primary_indices=[0], concentration=2.0)]):
        wrong = json.loads(json.dumps(d))
        wrong["features"]["primary_origins"]["settings"]["azimuth_groups"] = bad
        with pytest.raises(ValueError):
            resolve_config(wrong)
    for removed in ({"azimuth_mean_deg": 180.0, "azimuth_concentration": 1.0}, {"azimuth_primary_indices": [0]}):
        wrong = json.loads(json.dumps(d))
        wrong["features"]["primary_origins"]["settings"].update(removed)
        with pytest.raises(ValueError):                      # one bearing option only
            resolve_config(wrong)
    point = json.loads(json.dumps(d))
    point["features"]["primary_origins"]["settings"] = dict(
        layout="point", x_cm=0.0, y_cm=0.0, depth_cm=5.0,
        azimuth_groups=[dict(primary_indices=[0], mean_deg=0.0, concentration=1.0)],
    )
    with pytest.raises(ValueError):
        resolve_config(point)


def test_primary_azimuth_bias_on_listed_primaries_only():
    d = forest()
    uniform = run(d)
    listed = json.loads(json.dumps(d))
    listed["features"]["primary_origins"]["settings"]["azimuth_groups"] = [
        dict(primary_indices=[0], mean_deg=180.0, concentration=50.0)]
    sim = run(listed)
    angles = [r["polar_angle_rad"] for r in sim.result.diagnostics["primary_origins"]["primaries"]]
    before = [r["polar_angle_rad"] for r in uniform.result.diagnostics["primary_origins"]["primaries"]]
    assert abs(np.angle(np.exp(1j * (angles[0] - np.pi)))) < 0.6
    # Unlisted primaries keep their uniform draws exactly.
    assert angles[1:] == before[1:] and len(angles) > 1
    count = len(angles)
    for bad in ([count], [0, 0], [], [-1]):
        wrong = json.loads(json.dumps(listed))
        wrong["features"]["primary_origins"]["settings"]["azimuth_groups"][0]["primary_indices"] = bad
        with pytest.raises(ValueError):
            resolve_config(wrong)


def test_integrator_bias_is_deterministic_and_optional():
    from deeprootgen.model.cohort_geometry import integrate_curve

    def curve(bias):
        rng = np.random.default_rng(7)
        return integrate_curve(60.0, [0, 0, -5.0], [0, 1.0, -0.2], 2.0, 0.02, 15.0, 0.002, rng, bias=bias)

    plain, zero = curve(None), curve(lambda p: np.zeros(3))
    np.testing.assert_array_equal(plain[1], zero[1])
    pulled = curve(lambda p: np.array([0.05, 0.0, 0.0]))
    assert pulled[1][-1, 0] > plain[1][-1, 0] + 10


def test_moisture_tropism_points_into_the_wet_zone():
    from deeprootgen.model.irrigation import MoistureTropism

    zone = Irrigation(treatment="buried_drip", irrigation_depth_cm=30.0, line_offsets_cm=[0.0],
                      across_radius_cm=40.0, upper_radius_cm=20.0, lower_radius_cm=60.0, peak_multiplier=3.0)
    pull = MoistureTropism(zone, 0.0, 1.0)
    assert pull([20.0, 5.0, -30.0])[0] < 0 < pull([-20.0, 5.0, -30.0])[0]   # across the row, towards the line
    assert pull([0.0, 0.0, -15.0])[2] < 0 < pull([0.0, 0.0, -60.0])[2]      # z up: down from above, up from below
    np.testing.assert_array_equal(pull([80.0, 0.0, -30.0]), np.zeros(3))      # beyond the footprint
    np.testing.assert_allclose(pull([20.0, 0.0, -30.0])[0], -np.pi / 80 * np.sin(np.pi / 2) / 1, rtol=1e-3)


def test_moisture_tropism_end_to_end():
    from deeprootgen.model.irrigation import exposure, survey_points

    d = forest()
    zone = dict(treatment="buried_drip", irrigation_depth_cm=10.0, line_offsets_cm=[15.0], across_radius_cm=20.0,
                upper_radius_cm=10.0, lower_radius_cm=30.0, peak_multiplier=2.0)
    base = run(dict(d, irrigation=zone))
    zero = run(dict(d, irrigation=dict(zone, moisture_tropism={"2": 0.0})))
    for x, y in zip(base.G.as_df(), zero.G.as_df()):
        pd.testing.assert_frame_equal(x, y, check_exact=True)
    gains = {"1": 0.0, "2": 1.5, "3": 1.5, "4": 1.5, "5": 1.5}
    wet = run(dict(d, irrigation=dict(zone, moisture_tropism=gains)))
    assert wet.result.diagnostics["moisture_tropism"] == {"2": 1.5, "3": 1.5, "4": 1.5, "5": 1.5}
    surface = d["parameters"].get("soil_surface_z_cm", 0)
    zone_model = Irrigation(**zone)

    def mean_exposure(sim):
        nodes, _ = sim.G.as_df()
        roots = nodes[nodes.order >= 2]
        return exposure(zone_model, survey_points(roots[["x", "y", "z"]].to_numpy(), zone_model, surface)).mean()

    assert mean_exposure(wet) > mean_exposure(base)
    again = run(dict(d, irrigation=dict(zone, moisture_tropism=gains)))
    for x, y in zip(wet.G.as_df(), again.G.as_df()):
        pd.testing.assert_frame_equal(x, y, check_exact=True)
    with pytest.raises(ValueError):
        resolve_config(dict(d, irrigation=dict(zone, moisture_tropism={"9": 1.0})))
    with pytest.raises(ValueError):
        resolve_config(dict(d, irrigation=dict(zone, moisture_tropism={"0": 1.0})))


def test_primary_azimuth_groups():
    d = forest()
    groups = json.loads(json.dumps(d))
    groups["features"]["primary_origins"]["settings"]["azimuth_groups"] = [
        dict(primary_indices=[0], mean_deg=0.0, concentration=50.0),
        dict(primary_indices=[1], mean_deg=180.0, concentration=50.0),
    ]
    sim = run(groups)
    angles = [r["polar_angle_rad"] for r in sim.result.diagnostics["primary_origins"]["primaries"]]
    assert abs(angles[0]) < 0.6 and abs(np.angle(np.exp(1j * (angles[1] - np.pi)))) < 0.6
    for bad in (
        [dict(primary_indices=[0], mean_deg=0.0, concentration=1.0), dict(primary_indices=[0], mean_deg=90.0, concentration=1.0)],
        [dict(primary_indices=[0], mean_deg=0.0)],
        [],
    ):
        wrong = json.loads(json.dumps(d))
        wrong["features"]["primary_origins"]["settings"]["azimuth_groups"] = bad
        with pytest.raises(ValueError):
            resolve_config(wrong)
    both = json.loads(json.dumps(groups))
    both["features"]["primary_origins"]["settings"].update(azimuth_mean_deg=0.0)
    with pytest.raises(ValueError):
        resolve_config(both)


def _zones():
    base = dict(line_offsets_cm=[-40.0], across_radius_cm=40.0, peak_multiplier=3.0)
    return {
        "buried_periodic": Irrigation(treatment="buried_drip", irrigation_depth_cm=20.0, row_period_cm=300.0,
                                      upper_radius_cm=30.0, lower_radius_cm=60.0, **base),
        "buried_lines": Irrigation(treatment="buried_drip", irrigation_depth_cm=25.0, line_offsets_cm=[-40.0, 60.0],
                                   across_radius_cm=35.0, upper_radius_cm=15.0, lower_radius_cm=50.0,
                                   peak_multiplier=3.0),
        "buried_emitters": Irrigation(treatment="buried_drip", irrigation_depth_cm=20.0, emitter_spacing_cm=50.0,
                                      emitter_origin_y_cm=5.0, along_radius_cm=20.0, upper_radius_cm=25.0,
                                      lower_radius_cm=45.0, reflect_x=-1, **base),
        "surface_plateau": Irrigation(treatment="surface_drip", irrigation_depth_cm=0.0, **base),
        "surface_peak": Irrigation(treatment="surface_drip", irrigation_depth_cm=0.0, surface_profile="deep_peak", **base),
        "broad": Irrigation(**BROAD),
    }


def test_analytic_gradient_matches_finite_differences_inside_the_soil():
    from deeprootgen.model.irrigation import exposure_gradient

    rng = np.random.default_rng(3)
    for name, zone in _zones().items():
        pts = np.column_stack([rng.uniform(-120, 120, 400), rng.uniform(-60, 60, 400), rng.uniform(2, 120, 400)])
        e = 1e-5
        fd = np.column_stack([(exposure(zone, pts + e * u) - exposure(zone, pts - e * u)) / (2 * e) for u in np.eye(3)])
        np.testing.assert_allclose(exposure_gradient(zone, pts), fd, atol=2e-6, err_msg=name)


def test_gradient_boundaries_centre_surface_edge_and_reflection():
    from deeprootgen.model.cohort_geometry import integrate_curve
    from deeprootgen.model.irrigation import MoistureTropism, exposure_gradient

    zones = _zones()
    buried = zones["buried_periodic"]
    # Outlet centre (true maximum): exactly zero, so no spurious downward pull.
    np.testing.assert_array_equal(exposure_gradient(buried, [[-40.0, 0.0, 20.0]]), np.zeros((1, 3)))
    # Footprint edge and beyond: continuous to zero.
    edge = exposure_gradient(buried, [[-40.0 + 39.999, 0, 20.0], [-40.0 + 40.0, 0, 20.0], [-40.0 + 55, 0, 20.0]])
    assert abs(edge[0, 0]) < 1e-4 and not edge[1:].any()
    # Flat plateau just below the surface: zero (the finite difference probed air here).
    np.testing.assert_array_equal(exposure_gradient(zones["broad"], [[0.0, 0.0, 0.1], [0.0, 0.0, 0.0]]), np.zeros((2, 3)))
    np.testing.assert_array_equal(exposure_gradient(buried, [[-40.0, 0.0, -0.5]]), np.zeros((1, 3)))   # air
    # An initially upward heading at the surface integrates without a vanishing direction.
    pull = MoistureTropism(zones["broad"], 0.0, 0.5)
    stations, points, _ = integrate_curve(30.0, [0, 0, -0.1], [0, 0.2, 1.0], 1.0, 0.0, 15.0, 0.0,
                                          np.random.default_rng(0), bias=pull)
    assert np.isfinite(points).all()
    # Reflected survey frame: model x-gradient flips sign with reflect_x.
    reflected = zones["buried_emitters"]
    plain = Irrigation(**dict(reflected.model_dump(exclude_none=True), reflect_x=1))
    point = np.array([25.0, 3.0, -30.0])
    a, b = MoistureTropism(reflected, 0.0, 1.0)(point), MoistureTropism(plain, 0.0, 1.0)(-point * [1, 0, 0] + point * [0, 1, 1])
    assert np.sign(a[0]) == -np.sign(b[0]) and a[2] == pytest.approx(b[2])


def test_tropism_step_size_sensitivity_is_small():
    from deeprootgen.model.cohort_geometry import integrate_curve
    from deeprootgen.model.irrigation import MoistureTropism

    pull = MoistureTropism(_zones()["buried_periodic"], 0.0, 1.0)
    ends = []
    for step in (2.0, 1.0, 0.5):
        _, pts, _ = integrate_curve(80.0, [0.0, 0.0, -25.0], [-1.0, 0.3, -0.1], step, 0.0, 15.0, 0.0,
                                    np.random.default_rng(0), bias=pull)
        ends.append(pts[-1])
    assert np.linalg.norm(ends[0] - ends[2]) < 0.05 * 80 and np.linalg.norm(ends[1] - ends[2]) < 0.03 * 80


def test_tropism_guard_and_canonical_keys():
    d = forest()
    zone = dict(treatment="buried_drip", irrigation_depth_cm=10.0, line_offsets_cm=[15.0], across_radius_cm=20.0,
                upper_radius_cm=10.0, lower_radius_cm=30.0, peak_multiplier=2.0)
    with pytest.raises(ValueError, match="reverse a heading"):
        resolve_config(dict(d, irrigation=dict(zone, moisture_tropism={"4": 10.0})))
    for bad in ({"moisture_tropism": {"02": 1.0}}, {"order_sensitivity": {"04": 0.5}}):
        with pytest.raises(ValueError):
            resolve_config(dict(d, irrigation=dict(zone, **bad)))


def test_half_plane_bearing_groups():
    d = forest()
    count = len(run(d).organs[1])
    toward = list(range(count - 1)); away = [count - 1]

    def groups(flag):
        g = json.loads(json.dumps(d))
        g["features"]["primary_origins"]["settings"]["azimuth_groups"] = [
            dict(primary_indices=toward, mean_deg=180.0, concentration=0.3, **flag),
            dict(primary_indices=away, mean_deg=0.0, concentration=0.3, **flag),
        ]
        return g

    for seed in range(42, 48):
        cfg = dict(groups({"half_plane": True}), random_seed=seed)
        sim = run(cfg)
        rec = sim.result.diagnostics["primary_origins"]["primaries"]
        for i, r in enumerate(rec):
            mean = np.pi if i in toward else 0.0
            assert np.cos(r["polar_angle_rad"] - mean) >= 0
        for i, organ in enumerate(sim.organs[1]):
            mean = np.pi if i in toward else 0.0
            h = np.asarray(organ.axis_state.curve.receipt["initial_heading_unit"])
            assert h[0] * np.cos(mean) + h[1] * np.sin(mean) >= -1e-12   # emitted heading on its side
        again = run(cfg)
        for x, y in zip(sim.G.as_df(), again.G.as_df()):
            pd.testing.assert_frame_equal(x, y, check_exact=True)
    # Opt-out keeps the single legacy draw; unlisted primaries keep uniform draws exactly.
    for x, y in zip(run(groups({})).G.as_df(), run(groups({"half_plane": False})).G.as_df()):
        pd.testing.assert_frame_equal(x, y, check_exact=True)
    partial = json.loads(json.dumps(d))
    partial["features"]["primary_origins"]["settings"]["azimuth_groups"] = [
        dict(primary_indices=[0], mean_deg=0.0, concentration=5.0, half_plane=True)]
    a = [r["polar_angle_rad"] for r in run(partial).result.diagnostics["primary_origins"]["primaries"]]
    b = [r["polar_angle_rad"] for r in run(d).result.diagnostics["primary_origins"]["primaries"]]
    assert a[1:] == b[1:]


def test_recruitment_budget():
    d = forest()
    zone = dict(treatment="buried_drip", irrigation_depth_cm=10.0, line_offsets_cm=[15.0], across_radius_cm=20.0,
                upper_radius_cm=10.0, lower_radius_cm=30.0, peak_multiplier=6.0)
    free = run(dict(d, irrigation=zone))
    roomy = run(dict(d, irrigation=dict(zone, max_extra_fraction=1e6)))
    for x, y in zip(free.G.as_df(), roomy.G.as_df()):
        pd.testing.assert_frame_equal(x, y, check_exact=True)
    tight = run(dict(d, irrigation=dict(zone, max_extra_fraction=0.05)))
    budget = tight.result.diagnostics["irrigation"]["budget"]
    expected = sum(p.get("expected_extra", 0) for p in tight.result.diagnostics["irrigation"]["parents"])
    if budget["uncapped_expected_extra"] > 0.05 * budget["baseline_daughters"]:
        assert budget["scale"] < 1
        assert expected == pytest.approx(0.05 * budget["baseline_daughters"])
    with pytest.raises(ValueError):
        resolve_config(dict(d, irrigation=dict(zone, response="redistribute", max_extra_fraction=0.5)))
