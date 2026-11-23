"""Seeded regression checks for realized terminal contour preferences."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from deeprootgen.model.daughter_placement import profile_preference, row_distance
from deeprootgen.data_model.daughter_placement import OccurrenceProfile
from tests.test_irrigation import forest, run


PROFILE = dict(
    coefficients=[0.0, 0.0, 0.0, 0.0, 0.4],
    training_mean=0.1,
    depth_range_cm=[0.0, 150.0],
    fade_cm=20.0,
    row_period_cm=300.0,
    zone_boundaries=[0.25, 0.75],
    zone_tube_counts=[2, 1, 2],
)


def test_relative_row_support_and_taper():
    profile = OccurrenceProfile.model_validate(PROFILE)
    np.testing.assert_allclose(
        row_distance(np.array([-320.0, -20.0, 280.0]), 300), 20 / 150
    )
    np.testing.assert_allclose(
        profile_preference(
            profile, np.array([30.0, 160.0, 170.0]), np.array([0.5, 1.0, 1.0])
        ),
        [0.0, 0.5, 0.0],
    )


def test_grazing_deep_add_completes_on_supported_contour_and_preserves_accepted_site():
    from deeprootgen.data_model.daughter_placement import DaughterPlacement
    from deeprootgen.model.daughter_placement import _sample_sites
    from deeprootgen.model.materialize import AxisCurve

    surface = 12.0
    depths = np.array([65.0, 90.01, 70.0])
    stations = np.r_[0.0, np.cumsum(abs(np.diff(depths)))]
    points = np.column_stack([np.zeros(3), np.zeros(3), surface - depths])
    curve = AxisCurve(9, stations, points, stations, {})
    settings = DaughterPlacement.model_validate(
        dict(
            mode="add",
            strength=1.0,
            layer_depths_cm=[90.0, 95.0, 145.0, 150.0],
        )
    )
    # Seed the first rejection batch with one accepted point on the downward
    # piece. Subsequent draws use an ordinary seeded stream across both pieces.
    accepted = 25.005
    initial = iter(([accepted / stations[-1], 0.1, 0.2], [0.0, 0.5, 0.5]))
    rng = np.random.default_rng(927)
    calls = []

    def random(size):
        calls.append(size)
        value = next(initial, None)
        return rng.random(size) if value is None else np.array(value)

    state = SimpleNamespace(
        laws=SimpleNamespace(surface_z_cm=surface, origins={}),
        vine_origin=None,
        streams=SimpleNamespace(keyed=lambda *keys: SimpleNamespace(random=random)),
    )
    parent = SimpleNamespace(axis_state=SimpleNamespace(biological_id=9))
    sites = _sample_sites(
        state, settings, parent, curve, stations[:-1], stations[1:], 3
    )
    assert len(calls) > 20000
    assert len(sites) == 3 and np.min(np.diff(sites)) > 1e-9
    assert any(abs(site - accepted) < 1e-12 for site in sites)
    birth_depths = surface - curve.position(sites)[:, 2]
    assert np.all((birth_depths > 90.0) & (birth_depths <= 90.01))


def test_placement_off_reproduces_graph_and_effective_hash():
    config = forest()
    before = run(config)
    after = run(dict(config, daughter_placement=dict(strength=0.0, profile=PROFILE)))
    for left, right in zip(before.G.as_df(), after.G.as_df()):
        pd.testing.assert_frame_equal(left, right, check_exact=True)
    assert "daughter_placement" not in after.result.diagnostics
    assert (
        before.result.metadata["effective_model_sha256"]
        == after.result.metadata["effective_model_sha256"]
    )
    assert before.result.engine["keyed_streams"] == after.result.engine["keyed_streams"]


def test_placement_keeps_counts_lengths_and_anchored_site():
    config = forest()
    config["parameters"]["min_branching_diameter_cm"] = 0.093
    before = run(config)
    active = dict(config, daughter_placement=dict(strength=1.0, profile=PROFILE))
    after = run(active)
    repeated = run(active)
    for left, right in zip(after.G.as_df(), repeated.G.as_df()):
        pd.testing.assert_frame_equal(left, right, check_exact=True)
    assert (
        sum(
            len(p["births"])
            for p in after.result.diagnostics["daughter_placement"]["parents"]
        )
        > 0
    )
    for old, new in zip(before.organs[4], after.organs[4]):
        np.testing.assert_array_equal(
            old.axis_state.curve.points, new.axis_state.curve.points
        )
        assert len(old.child_organs) == len(new.child_organs)
        if old.child_organs:
            np.testing.assert_array_equal(
                old.child_organs[0].axis_state.curve.points,
                new.child_organs[0].axis_state.curve.points,
            )
        for x, y in zip(old.child_organs, new.child_organs):
            assert x.axis_state.biological_id == y.axis_state.biological_id
            assert x.get_lengths().sum() == pytest.approx(
                y.get_lengths().sum(), rel=1e-12
            )


def test_retention_preserves_expected_count_and_paired_uniform_draws():
    config = forest()
    config["parameters"]["min_branching_diameter_cm"] = 0.093

    def retained(strength):
        model = run(
            dict(
                config,
                daughter_placement=dict(
                    mode="retention", strength=strength, profile=PROFILE
                ),
            )
        )
        rows = model.result.diagnostics["daughter_placement"]["retentions"]
        assert len(model.organs[5]) == sum(r["kept"] for r in rows)
        assert np.mean([r["probability"] for r in rows]) == pytest.approx(
            0.85, abs=1e-12
        )
        return rows

    neutral = retained(0.0)
    assert neutral == retained(0.0)
    assert all(row["probability"] == 0.85 for row in neutral)
    assert [r["daughter_id"] for r in retained(1.0)] == [
        r["daughter_id"] for r in neutral
    ]


def test_realized_floor_with_cohort_scaling():
    config = forest()
    cfg = config["features"]["lengths"]["settings"]["by_order"]["1"]
    cfg.update(mean=65.0, sd=30.0, min=15.0, max=300.0)
    rooted = run(dict(config, minimum_realized_primary_length_cm=50.0))
    assert all(o.get_lengths().sum() >= 50.0 - 1e-10 for o in rooted.organs[1])
    with pytest.raises(ValueError, match="leaves no probability mass"):
        run(dict(config, minimum_realized_primary_length_cm=301.0))


def test_odds_mode_reuses_parent_geometry_and_ordinary_site_law():
    config = forest()
    config["parameters"]["min_branching_diameter_cm"] = 0.093
    config["features"]["branching"]["settings"]["by_order"]["4"][
        "branch_probability"
    ] = 0.6
    before = run(config)
    profile = dict(PROFILE, coefficients=[0.3, 0.0, 0.0, 0.0, 0.0])
    after = run(
        dict(
            config,
            daughter_placement=dict(
                mode="branch_probability", strength=1.0, profile=profile
            ),
        )
    )
    rows = after.result.diagnostics["daughter_placement"]["parents"]
    assert any(row["probability"] > row["baseline_probability"] for row in rows)
    assert all(
        row["probability"]
        == pytest.approx(
            row["baseline_probability"] * 1.5 / (1 + row["baseline_probability"] * 0.5)
        )
        for row in rows
        if row["eligible_cm"]
    )
    for x, y in zip(before.organs[4], after.organs[4]):
        np.testing.assert_array_equal(
            x.axis_state.curve.points, y.axis_state.curve.points
        )


def test_depth_extra_and_uniform_match_counts_and_lengths():
    config = forest()
    config["parameters"]["min_branching_diameter_cm"] = 0.093
    config["features"]["primary_origins"]["settings"]["depth_range_cm"] = [110.0, 110.0]
    a, b = [
        run(dict(config, daughter_placement=dict(strength=1.0, mode=mode)))
        for mode in ("add", "uniform_extra")
    ]
    records = [m.result.diagnostics["daughter_placement"]["parents"] for m in (a, b)]
    assert sum(len(p["births"]) for p in records[0]) > 0
    for x, y in zip(*records):
        assert (
            x["drawn_extra"] == y["drawn_extra"] == len(x["births"]) == len(y["births"])
        )
    np.testing.assert_allclose(
        [o.get_lengths().sum() for o in a.organs[5]],
        [o.get_lengths().sum() for o in b.organs[5]],
        rtol=1e-13,
    )


def test_moving_daughters_reuses_stochastic_diameter_draws():
    config = forest()
    config["parameters"]["min_branching_diameter_cm"] = 0.093
    config["features"].pop("parent_diameter_cap", None)
    taper = config["features"]["taper"]["settings"]["by_order"]["5"]
    taper.update(
        base_cm=dict(mean=0.24, sd=0.01, min=0.17, max=0.32),
        tip_cm=dict(mean=0.14, sd=0.01, min=0.09, max=0.20),
    )
    before = run(config)
    after = run(dict(config, daughter_placement=dict(strength=1.0, profile=PROFILE)))
    assert (
        sum(
            len(p["births"])
            for p in after.result.diagnostics["daughter_placement"]["parents"]
        )
        > 0
    )
    for old, new in zip(before.organs[5], after.organs[5]):
        for field in ("base", "tip"):
            assert new.axis_state.material[field] == old.axis_state.material[field]


def test_schema_advanced_settings_round_trip():
    from deeprootgen.data_model.simulation_form import (
        simulation_controls,
        simulation_document,
    )

    config = dict(
        forest(),
        daughter_placement=dict(strength=1.0, profile=PROFILE),
        minimum_realized_primary_length_cm=10.0,
    )
    controls = ["simulation_tag", "random_seed", "advanced_settings"]
    restored = simulation_document(
        dict(zip(controls, simulation_controls(config, controls)))
    )
    assert restored["daughter_placement"] == config["daughter_placement"]
    assert restored["minimum_realized_primary_length_cm"] == 10.0


def test_uniform_branch_control_matches_expected_eligible_recruitment():
    config = forest()
    config["parameters"]["min_branching_diameter_cm"] = 0.093
    config["features"]["branching"]["settings"]["by_order"]["4"][
        "branch_probability"
    ] = 0.6
    profile = dict(PROFILE, row_depth_slope=0.6)
    receipts = []
    for mode in ("branch_probability", "branch_probability_uniform"):
        result = run(
            dict(
                config,
                daughter_placement=dict(mode=mode, strength=1.0, profile=profile),
            )
        )
        receipt = result.result.diagnostics["daughter_placement"]
        assert len(result.organs[5]) == sum(
            row["realized_daughters"] for row in receipt["parents"]
        )
        receipts.append(receipt)
    assert receipts[0]["expected_daughters"] == pytest.approx(
        receipts[1]["expected_daughters"], abs=1e-10
    )
    assert receipts[1]["uniform_multiplier"] is not None
    assert receipts[0]["expected_daughters"] > 0


def test_sparse_depth_and_uniform_use_the_same_realized_count():
    config = forest()
    config["parameters"]["min_branching_diameter_cm"] = 0.093
    config["features"]["primary_origins"]["settings"]["depth_range_cm"] = [110.0, 110.0]
    config["features"]["branching"]["settings"]["by_order"]["4"][
        "branch_probability"
    ] = 0.0
    receipts = []
    for mode in ("sparse_depth", "sparse_uniform"):
        result = run(dict(config, daughter_placement=dict(mode=mode, strength=0.75)))
        receipt = result.result.diagnostics["daughter_placement"]
        assert len(result.organs[5]) == receipt["deep_activated_parents"]
        assert len({row["parent_id"] for row in receipt["parents"]}) == len(
            result.organs[5]
        )
        assert all(len(row["births"]) == 1 for row in receipt["parents"])
        receipts.append(receipt)
    assert (
        receipts[0]["deep_activated_parents"]
        == receipts[1]["deep_activated_parents"]
        > 0
    )
    assert all(row["births"][0]["depth_cm"] > 90.0 for row in receipts[0]["parents"])


def test_carrier_kicks_in_only_after_downward_crossing():
    from deeprootgen.model.cohort_geometry import integrate_curve

    def curve(start, selected):
        receipt = {}
        stations, points, _ = integrate_curve(
            10.0,
            [0, 0, start],
            [1, 0, -1],
            1.0,
            0.001,
            10.0,
            0.01,
            np.random.default_rng(9),
            deep_carrier=dict(
                trigger_depth_cm=60.0, selected=selected, drift_multiplier=1.25
            ),
            carrier_receipt=receipt,
        )
        return stations, points, receipt

    _, base, untreated = curve(-58.0, False)
    _, moved, treated = curve(-58.0, True)
    crossing = np.flatnonzero(base[:, 2] <= -60.0)[0]
    np.testing.assert_array_equal(base[: crossing + 1], moved[: crossing + 1])
    assert moved[-1, 2] < base[-1, 2]
    assert untreated == dict(born_below=False, crossed=True, strengthened=False)
    assert treated == dict(born_below=False, crossed=True, strengthened=True)
    assert curve(-61.0, True)[2] == dict(
        born_below=True, crossed=False, strengthened=False
    )


def test_shallow_layer_support_and_peak():
    from deeprootgen.data_model.daughter_placement import DaughterPlacement
    from deeprootgen.model.daughter_placement import _weights

    layer = DaughterPlacement.model_validate(
        dict(
            mode="add",
            strength=0.5,
            layer_depths_cm=[0.0, 3.0, 25.0, 45.0],
            layer_peak_multiplier=4.0,
        )
    )
    points = np.zeros((5, 3))
    points[:, 2] = -np.array([0.0, 3.0, 25.0, 35.0, 45.0])
    np.testing.assert_allclose(_weights(layer, points, 0.0), [1.0, 2.5, 2.5, 1.75, 1.0])
    with pytest.raises(ValueError, match="ordered ramp"):
        DaughterPlacement.model_validate(
            dict(mode="add", layer_depths_cm=[0.0, 3.0, 2.0, 45.0])
        )
