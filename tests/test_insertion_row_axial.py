"""Invented directional/crown fixtures only; no observed values or trial seeds."""

import copy
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import RootSimulationModel
from deeprootgen.model import RootSystemSimulation
from deeprootgen.research import so4_controlled as controlled
from deeprootgen.utils import tropism

POLICY = "minimum_angle_projection"


def parameters(seed=42, row=None, combined=True, **updates):
    values = json.loads((Path(__file__).parents[1] / "examples/synthetic_minimal.json").read_text())
    values.update(random_seed=seed, max_order=3, min_sec_root_num=2, max_sec_root_num=3,
                  min_primary_length=10., max_primary_length=12.,
                  min_sec_root_length=2., max_sec_root_length=3., root_vary=10.,
                  growth_sec_root=0., interbranch_distance=.75, segments_per_root=10,
                  floor_threshold=.1, ceiling_threshold=.9,
                  gravitropism=0., tropism_mode="fichtl2024", soil_surface_z_cm=20.,
                  fichtl_probability_down=.5, fichtl_sigma=.2,
                  fichtl_trials_type2=1., fichtl_trials_type3=1.,
                  fichtl_theta2_deg=50., fichtl_theta2_sd_deg=10.,
                  fichtl_theta3_deg=50., fichtl_theta3_sd_deg=10.,
                  research_insertion_row_axial_kappa=row)
    if combined:
        values.update(research_branch_placement="redistribute_capped",
                      research_current_length_cdfs_cm={
                          2: dict(lengths_cm=[4., 6.], cumulative_probabilities=[.5, 1.]),
                          3: dict(lengths_cm=[1., 2.], cumulative_probabilities=[.5, 1.]),
                      }, research_primary_yaw_mean_deg=35., research_primary_yaw_kappa=2.,
                      research_base_origin_x_cm=1., research_base_origin_y_cm=-2., research_base_depth_cm=7.)
    values.update(updates)
    return RootSimulationModel(**values)


def original(tangent, theta=50.):
    return tropism.insertion_heading(tangent, theta, 0., np.random.default_rng(42))


def test_helper_preserves_unit_norm_polar_angle_and_independent_keys():
    tangent = np.array([.3, .4, -np.sqrt(.75)])
    heading = original(tangent)
    biased, report = tropism.row_axial_insertion_heading(tangent, heading, 4., 42, 3, 2)
    repeated, same = tropism.row_axial_insertion_heading(tangent, heading, 4., 42, 3, 2)
    assert np.linalg.norm(biased) == pytest.approx(1., abs=1e-12)
    assert biased @ tangent == pytest.approx(heading @ tangent, abs=1e-12)
    np.testing.assert_array_equal(biased, repeated)
    assert report == same
    assert report["old_polar_angle_deg"] == pytest.approx(report["new_polar_angle_deg"], abs=1e-10)
    assert report["stream_used"] and report["fallback"] is None
    different, _ = tropism.row_axial_insertion_heading(tangent, heading, 4., 42, 4, 2)
    assert not np.array_equal(biased, different)
    different, _ = tropism.row_axial_insertion_heading(tangent, heading, 4., 43, 3, 2)
    assert not np.array_equal(biased, different)
    assert report["stream_identity"]["purposes"] == ["axial_angle", "axial_branch"]


@pytest.mark.parametrize("kappa", [None, 0.])
def test_disabled_zero_are_exact_and_need_no_random_stream(monkeypatch, kappa):
    heading = original([0., 0., -1.])

    def forbidden(*args):
        pytest.fail("Disabled/zero control created a random stream")

    monkeypatch.setattr(tropism, "_row_axial_stream", forbidden)
    actual, report = tropism.row_axial_insertion_heading([0., 0., -1.], heading, kappa)
    np.testing.assert_array_equal(actual, heading)
    assert actual is heading
    assert not report["stream_used"]
    assert report["fallback"] == ("disabled" if kappa is None else "zero_kappa")


@pytest.mark.parametrize("tangent,theta,reason", [
    ([0., 1., 0.], 50., "parent_parallel_row"),
    ([1e-13, 1., 0.], 50., "parent_parallel_row"),
    ([0., 0., -1.], 0., "zero_polar"),
])
def test_exact_and_near_degeneracies_keep_original_heading(monkeypatch, tangent, theta, reason):
    heading = original(tangent, theta)

    def forbidden(*args):
        pytest.fail("Degenerate control created a random stream")

    monkeypatch.setattr(tropism, "_row_axial_stream", forbidden)
    actual, report = tropism.row_axial_insertion_heading(tangent, heading, 4., 42, 3, 2)
    np.testing.assert_array_equal(actual, heading)
    assert report["fallback"] == reason and not report["stream_used"]


def test_near_parallel_nondegenerate_projection_retains_polar_angle():
    tangent = np.array([1e-10, 1., 0.])
    tangent /= np.linalg.norm(tangent)
    heading = original(tangent)
    biased, report = tropism.row_axial_insertion_heading(tangent, heading, 4., 42, 3, 2)
    assert report["fallback"] is None
    assert biased @ tangent == pytest.approx(heading @ tangent, abs=1e-12)
    assert np.linalg.norm(biased) == pytest.approx(1., abs=1e-12)


def test_axial_branches_reverse_transverse_component_not_entire_heading(monkeypatch):
    class FixedStream:
        def __init__(self, branch):
            self.branch = branch

        def vonmises(self, mean, kappa):
            return 0.

        def integers(self, low, high):
            return self.branch

    tangent = np.array([0., 0., -1.])
    heading = original(tangent, 60.)
    results = []
    for branch in (0, 1):
        monkeypatch.setattr(tropism, "_row_axial_stream", lambda *args, branch=branch: FixedStream(branch))
        biased, report = tropism.row_axial_insertion_heading(tangent, heading, 4., 42, 3, 2)
        assert report["axial_branch"] == branch
        results.append(biased)
    np.testing.assert_allclose(results[0], [0., np.sqrt(3.) / 2., -.5], atol=1e-12)
    np.testing.assert_allclose(results[1], [0., -np.sqrt(3.) / 2., -.5], atol=1e-12)
    np.testing.assert_allclose(results[0] + results[1], tangent, atol=1e-12)


def test_combined_arm_d_fixture_preserves_invariants_and_continuation_innovations():
    plain, enabled = parameters(), parameters(row={2: 4., 3: 4.})
    initial = controlled.construct_skeleton(plain, 42)
    baseline = controlled.replay_arm(initial, "D", plain.model_dump(), POLICY)
    result = controlled.replay_arm(initial, "D", enabled.model_dump(), POLICY)
    repeat = controlled.replay_arm(initial, "D", enabled.model_dump(), POLICY)
    for name in ("nodes", "edges", "proposals"):
        pd.testing.assert_frame_equal(result[name], repeat[name], check_exact=True)
    assert result["diagnostics"] == repeat["diagnostics"]
    assert result["diagnostics"]["invariant_hashes"] == baseline["diagnostics"]["invariant_hashes"]
    primary = baseline["nodes"].order.le(1)
    pd.testing.assert_frame_equal(baseline["nodes"].loc[primary], result["nodes"].loc[primary], check_exact=True)
    pd.testing.assert_frame_equal(baseline["edges"], result["edges"], check_exact=True)
    assert not baseline["nodes"][["x", "y", "z"]].equals(result["nodes"][["x", "y", "z"]])
    assert [r["innovations_sha256"] for r in baseline["diagnostics"]["segments"] if "innovations_sha256" in r] == [
        r["innovations_sha256"] for r in result["diagnostics"]["segments"] if "innovations_sha256" in r]
    controlled.validate_geometry(result["nodes"], result["edges"], 20.)
    for organ in result["diagnostics"]["organs"]:
        report = organ["row_axial_insertion"]
        assert report["realisation_stage"] == "controlled_exact_first_segment_then_common_projection"
        np.testing.assert_array_equal(report["post_boundary_heading"], organ["realised_heading"])
        assert report["old_polar_angle_deg"] == pytest.approx(report["new_polar_angle_deg"], abs=1e-10)
        profile = report["row_alignment_by_arc"]
        assert profile[0]["arc_start_cm"] == 0.
        assert all(part["arc_end_cm"] > part["arc_start_cm"] for part in profile)
        assert all(0. <= part["axial_row_alignment"] <= 1. + 1e-12 for part in profile)
        organ_length = result["nodes"].loc[result["nodes"].organ_id.eq(organ["organ_id"]), "length"].sum()
        assert profile[-1]["arc_end_cm"] == pytest.approx(organ_length, rel=0, abs=1e-8)
    fresh_settings = parameters(seed=43, row={2: 4., 3: 4.})
    fresh = controlled.construct_skeleton(fresh_settings, 43)
    fresh_result = controlled.replay_arm(fresh, "D", fresh_settings.model_dump(), POLICY)
    controlled.validate_geometry(fresh_result["nodes"], fresh_result["edges"], 20.)
    assert fresh_result["diagnostics"]["seed"] == 43 and fresh.sha256 != initial.sha256


def test_controlled_zero_preserves_every_arm_output_exactly():
    plain, zero = parameters(), parameters(row={2: 0., 3: 0.})
    initial = controlled.construct_skeleton(plain, 42)
    for arm in "ABCD":
        baseline = controlled.replay_arm(initial, arm, plain.model_dump(), POLICY)
        result = controlled.replay_arm(initial, arm, zero.model_dump(), POLICY)
        for name in ("nodes", "edges", "proposals"):
            pd.testing.assert_frame_equal(baseline[name], result[name], check_exact=True)


def test_combined_json_roundtrip_keeps_positive_order_controls_and_initial_graph():
    plain = parameters()
    enabled = parameters(row={2: 4., 3: 4.})
    raw_settings = json.loads(json.dumps(enabled.model_dump()))
    assert set(raw_settings["research_insertion_row_axial_kappa"]) == {"2", "3"}
    initial = controlled.construct_skeleton(plain, 42)
    configured_initial = controlled.construct_skeleton(RootSimulationModel(**raw_settings), 42)
    for name in ("nodes", "edges", "organs"):
        assert initial.payload[name] == configured_initial.payload[name]
    typed = controlled.replay_arm(initial, "D", enabled.model_dump(), POLICY)
    raw = controlled.replay_arm(initial, "D", raw_settings, POLICY)
    for name in ("nodes", "edges", "proposals"):
        pd.testing.assert_frame_equal(typed[name], raw[name], check_exact=True)
    assert typed["diagnostics"] == raw["diagnostics"]
    reports = [o["row_axial_insertion"] for o in raw["diagnostics"]["organs"]]
    assert {o["order"] for o in raw["diagnostics"]["organs"]} == {2, 3}
    assert all(report["kappa"] == 4. and report["stream_used"] for report in reports)


def test_controlled_original_sampler_called_once_and_polar_rng_schedule_unchanged(monkeypatch):
    sampler = controlled.insertion_heading
    calls = []

    def observed(tangent, mean, sd, rng):
        heading = sampler(tangent, mean, sd, rng)
        calls.append((copy.deepcopy(rng.bit_generator.state), float(heading @ (tangent / np.linalg.norm(tangent)))))
        return heading

    monkeypatch.setattr(controlled, "insertion_heading", observed)
    plain, enabled = parameters(), parameters(row={2: 4., 3: 4.})
    initial = controlled.construct_skeleton(plain, 42)
    baseline = controlled.replay_arm(initial, "B", plain.model_dump(), POLICY)
    old_calls = calls[:]
    calls.clear()
    controlled.replay_arm(initial, "B", enabled.model_dump(), POLICY)
    assert len(calls) == len(old_calls) == len(baseline["diagnostics"]["organs"])
    assert [call[0] for call in calls] == [call[0] for call in old_calls]
    np.testing.assert_allclose([call[1] for call in calls], [call[1] for call in old_calls], atol=1e-12)


def test_native_shared_rng_zero_identity_and_explicit_first_search_stage():
    outputs, states = [], []
    for row in (None, {2: 0., 3: 0.}, {2: 4., 3: 4.}):
        p = parameters(row=row)
        sim = RootSystemSimulation(random_seed=42)
        sim.run(p)
        outputs.append(sim.G.as_df())
        states.append(copy.deepcopy(sim.rng.bit_generator.state))
        if row is not None:
            for report in sim.row_insertion_diagnostics:
                assert report["realisation_stage"] == "native_search_from_segment1_with_candidate_surface_filter"
                assert len(report["post_boundary_heading"]) == 3
                assert all("rejected_surface_candidates" in part for part in report["row_alignment_by_arc"])
                assert report["old_polar_angle_deg"] == pytest.approx(report["new_polar_angle_deg"], abs=1e-10)
        controlled.validate_geometry(*sim.G.as_df(), 20.)
    for first, second in zip(outputs[0], outputs[1]):
        pd.testing.assert_frame_equal(first, second, check_exact=True)
    assert states[0] == states[1] == states[2]


def test_zero_sigma_continuation_keeps_the_insertion_direction_without_extra_row_force():
    p = parameters(row={2: 4., 3: 4.}, fichtl_sigma=0.)
    initial = controlled.construct_skeleton(p, 42)
    result = controlled.replay_arm(initial, "D", p.model_dump(), POLICY)
    for organ in result["diagnostics"]["organs"]:
        profile = organ["row_axial_insertion"]["row_alignment_by_arc"]
        assert not any(part["boundary_intervention"] for part in profile)
        np.testing.assert_allclose([part["row_projection"] for part in profile], organ["assigned_heading"][1], atol=1e-12)
        np.testing.assert_allclose([part["alignment_with_insertion"] for part in profile], 1., atol=1e-12)


@pytest.mark.parametrize("arm", ["A", "C"])
def test_active_controls_rejected_for_legacy_insertion(arm):
    p = parameters(row={2: 4.})
    initial = controlled.construct_skeleton(p, 42)
    with pytest.raises(ValueError, match="Fichtl insertion"):
        controlled.replay_arm(initial, arm, p.model_dump(), POLICY)


def test_active_replay_requires_authoritative_seed_match():
    p = parameters(row={2: 4.})
    initial = controlled.construct_skeleton(p, 42)
    with pytest.raises(ValueError, match="match saved skeleton seed"):
        controlled.replay_arm(initial, "D", {**p.model_dump(), "random_seed": 43}, POLICY)


@pytest.mark.parametrize("constructor_seed", [None, 43])
def test_active_native_seed_guard_precedes_graph_and_rng_mutation(constructor_seed):
    p = parameters(row={2: 4.}, combined=False)
    sim = RootSystemSimulation(random_seed=constructor_seed)
    before, state = sim.G.as_df(), copy.deepcopy(sim.rng.bit_generator.state)
    with pytest.raises(ValueError, match="equal explicit constructor and parameter seeds"):
        sim.init_organs(p)
    for first, second in zip(before, sim.G.as_df()):
        pd.testing.assert_frame_equal(first, second)
    assert sim.rng.bit_generator.state == state


@pytest.mark.parametrize("row,updates", [
    ({}, {}), ({1: 4.}, {}), ({4: 4.}, {}), ({2: -1.}, {}),
    ({2: np.inf}, {}), ({2: np.nan}, {}),
    ({2: 4.}, {"random_seed": None}), ({2: 4.}, {"tropism_mode": "legacy"}),
])
def test_invalid_schema_and_active_mode_rejected(row, updates):
    with pytest.raises(ValueError):
        parameters(row=row, combined=False, **updates)


def test_controlled_boundary_override_is_separate_from_preserved_insertion_polar_angle(rsa_nodes, monkeypatch):
    class FixedStream:
        def vonmises(self, mean, kappa):
            return np.pi / 2.

        def integers(self, low, high):
            return 0

    monkeypatch.setattr(tropism, "_row_axial_stream", lambda *args: FixedStream())
    nodes = rsa_nodes.copy()
    nodes.loc[:, ["x", "y", "z"]] = [
        [0., 0., 19.9], [4., 0., 19.9], [10., 0., 19.9],
        [4., 3., 19.9], [4., 5., 19.9], [4., 3., 17.9],
    ]
    p = parameters(row={2: 4., 3: 4.}, combined=False)
    edges = nodes.loc[nodes.order.gt(0), ["parent_id", "node_id"]].rename(columns={"node_id": "child_id"})
    initial = controlled.Skeleton.from_tables(nodes, edges, 42, p.model_dump())
    result = controlled.replay_arm(initial, "D", p.model_dump(), POLICY)
    report = result["diagnostics"]["organs"][0]["row_axial_insertion"]
    assert report["old_polar_angle_deg"] == pytest.approx(report["new_polar_angle_deg"], abs=1e-10)
    assert report["row_alignment_by_arc"][0]["boundary_intervention"]
    assert report["post_boundary_polar_angle_deg"] != pytest.approx(report["new_polar_angle_deg"])
    assert result["nodes"].z.max() <= 20.
    controlled.validate_geometry(result["nodes"], result["edges"], 20.)


def test_zero_control_does_not_impose_new_seed_requirement_on_native_noop():
    outputs, states = [], []
    for row in (None, {2: 0., 3: 0.}):
        p = parameters(seed=None, row=row, combined=False)
        sim = RootSystemSimulation(random_seed=42)
        sim.run(p)
        outputs.append(sim.G.as_df())
        states.append(copy.deepcopy(sim.rng.bit_generator.state))
    for first, second in zip(*outputs):
        pd.testing.assert_frame_equal(first, second, check_exact=True)
    assert states[0] == states[1]
