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
