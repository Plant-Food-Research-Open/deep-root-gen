"""Invented buried-origin fixtures; no empirical coordinates or trial seeds."""

import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import RootSimulationModel
from deeprootgen.archive.simulation import RootSystemSimulation
from deeprootgen.research.so4_controlled import construct_skeleton, replay_arm, validate_geometry

ORIGIN = dict(research_base_origin_x_cm=2., research_base_origin_y_cm=-3., research_base_depth_cm=7.)


def values(**updates):
    spec = json.loads((Path(__file__).parents[1] / "tests/fixtures/migration_inputs/synthetic_minimal.json").read_text())
    spec.update(max_order=3, min_sec_root_num=1, max_sec_root_num=2,
                min_sec_root_length=2., max_sec_root_length=3., interbranch_distance=2.,
                gravitropism=0., tropism_mode="fichtl2024", soil_surface_z_cm=20.,
                fichtl_probability_down=.5, fichtl_sigma=.1,
                fichtl_trials_type2=1., fichtl_trials_type3=1.,
                fichtl_theta2_deg=50., fichtl_theta2_sd_deg=10.,
                fichtl_theta3_deg=50., fichtl_theta3_sd_deg=10.)
    spec.update(updates)
    return spec


def parameters(**updates):
    return RootSimulationModel(**values(**updates))


def initial(settings):
    sim = RootSystemSimulation(random_seed=42)
    sim.init_organs(settings)
    sim.position_secondary_roots(settings)
    sim.position_primary_roots(settings)
    return sim


def edge_vectors(nodes):
    lookup = nodes.set_index("node_id")
    return np.array([np.array([row.x, row.y, row.z]) - lookup.loc[row.parent_id, ["x", "y", "z"]].to_numpy(float)
                     for row in nodes.loc[nodes.order.gt(0)].itertuples()])


def test_nonzero_existing_base_translates_every_node_preserving_relative_geometry_and_rng():
    sim = initial(parameters())
    old_origin = np.array([7., -4., 11.])
    for node in sim.G.nodes:
        node.node_data.x += old_origin[0]
        node.node_data.y += old_origin[1]
        node.node_data.z += old_origin[2]
    before, before_edges = sim.G.as_df()
    state = copy.deepcopy(sim.rng.bit_generator.state)
    sim.apply_root_origin_initialization(parameters(**ORIGIN))
    after, edges = sim.G.as_df()
    target = np.array([2., -3., 13.])
    expected = before[["x", "y", "z"]].to_numpy(float) + target - old_origin
    np.testing.assert_allclose(after[["x", "y", "z"]], expected, rtol=0, atol=1e-10)
    np.testing.assert_array_equal(after.loc[after.order.eq(0), ["x", "y", "z"]].to_numpy(float)[0], target)
    pd.testing.assert_frame_equal(before.drop(columns=["x", "y", "z"]), after.drop(columns=["x", "y", "z"]))
    pd.testing.assert_frame_equal(before_edges, edges)
    assert len(after) == len(before) and len(edges) == len(before_edges)
    assert state == sim.rng.bit_generator.state
    old_vectors, new_vectors = edge_vectors(before), edge_vectors(after)
    np.testing.assert_allclose(old_vectors, new_vectors, rtol=1e-5, atol=1e-6)
    old_directions = old_vectors / np.linalg.norm(old_vectors, axis=1)[:, None]
    new_directions = new_vectors / np.linalg.norm(new_vectors, axis=1)[:, None]
    np.testing.assert_allclose(old_directions @ old_directions.T, new_directions @ new_directions.T, atol=1e-12)
    validate_geometry(after, edges)
    assert np.linalg.norm(new_vectors, axis=1).sum() == pytest.approx(before.length.sum(), rel=0, abs=1e-8)
    assert sim.root_origin_diagnostics["old_base_cm"] == list(old_origin)
    assert sim.root_origin_diagnostics["target_base_cm"] == list(target)
    assert sim.root_origin_diagnostics["delta_cm"] == [-5., 1., 2.]
    assert sim.root_origin_diagnostics["translated_node_count"] == len(before)
    assert sim.root_origin_diagnostics["soil_surface_z_cm"] - target[2] == 7.


def test_positioning_hook_is_deterministic_after_yaw_and_before_tropism():
    yaw = dict(research_primary_yaw_mean_deg=35., research_primary_yaw_kappa=4.)
    baseline = initial(parameters(**yaw))
    opted_in = initial(parameters(**yaw, **ORIGIN))
    repeated = initial(parameters(**yaw, **ORIGIN))
    baseline_nodes, baseline_edges = baseline.G.as_df()
    nodes, edges = opted_in.G.as_df()
    np.testing.assert_allclose(nodes[["x", "y", "z"]], baseline_nodes[["x", "y", "z"]] + [2., -3., 13.],
                               rtol=0, atol=1e-10)
    pd.testing.assert_frame_equal(baseline_edges, edges)
    assert baseline.rng.bit_generator.state == opted_in.rng.bit_generator.state
    assert baseline.primary_yaw_diagnostics == opted_in.primary_yaw_diagnostics
    assert all(item["base_cm"] == [0., 0., 0.] for item in opted_in.primary_yaw_diagnostics)
    assert opted_in.root_origin_diagnostics["stage"] == "after_primary_positioning_and_yaw_before_tropism"
    assert not hasattr(opted_in, "tropism_diagnostics")
    for first, second in zip(opted_in.G.as_df(), repeated.G.as_df()):
        pd.testing.assert_frame_equal(first, second)


def test_native_run_and_initial_replay_api_use_translated_base():
    settings = parameters(**ORIGIN)
    sim = RootSystemSimulation(random_seed=42)
    sim.run(settings)
    nodes, edges = sim.G.as_df()
    np.testing.assert_array_equal(nodes.loc[nodes.order.eq(0), ["x", "y", "z"]].to_numpy(float)[0], [2., -3., 13.])
    validate_geometry(nodes, edges, 20.)
    assert not nodes.invalid_root.any()
    assert sim.root_origin_diagnostics["target_base_cm"] == [2., -3., 13.]
    skeleton = construct_skeleton(settings, 42)
    result = replay_arm(skeleton, "D", settings.model_dump(), "minimum_angle_projection")
    np.testing.assert_array_equal(result["nodes"].loc[result["nodes"].order.eq(0), ["x", "y", "z"]].to_numpy(float)[0],
                                  [2., -3., 13.])
    validate_geometry(result["nodes"], result["edges"], 20.)
    assert len(result["edges"]) == len(result["nodes"]) - 1


def test_absent_and_explicit_none_controls_preserve_default_legacy_graphs():
    spec = json.loads((Path(__file__).parents[1] / "tests/fixtures/migration_inputs/synthetic_minimal.json").read_text())
    graphs = []
    for extras in ({}, dict(research_base_origin_x_cm=None, research_base_origin_y_cm=None, research_base_depth_cm=None)):
        settings = RootSimulationModel(**{**spec, **extras})
        sim = RootSystemSimulation(random_seed=42)
        sim.run(settings)
        assert not hasattr(sim, "root_origin_diagnostics")
        graphs.append(sim.G.as_df())
    for first, second in zip(*graphs):
        pd.testing.assert_frame_equal(first, second)


@pytest.mark.parametrize("updates", [
    {"research_base_origin_x_cm": 2.},
    {"research_base_origin_x_cm": 2., "research_base_origin_y_cm": -3.},
    {"research_base_origin_y_cm": -3., "research_base_depth_cm": 7.},
    {**ORIGIN, "research_base_origin_x_cm": np.inf},
    {**ORIGIN, "research_base_origin_y_cm": np.nan},
    {**ORIGIN, "research_base_depth_cm": np.inf},
    {**ORIGIN, "research_base_depth_cm": 0.},
    {**ORIGIN, "research_base_depth_cm": -1.},
    {**ORIGIN, "soil_surface_z_cm": np.inf},
    {**ORIGIN, "tropism_mode": "legacy"},
])
def test_incomplete_nonfinite_nonpositive_and_unsupported_controls_rejected(updates):
    with pytest.raises(ValueError):
        parameters(**updates)


def test_origin_controls_require_explicit_surface_not_implicit_default():
    spec = values(**ORIGIN)
    del spec["soil_surface_z_cm"]
    with pytest.raises(ValueError, match="explicit soil_surface_z_cm"):
        RootSimulationModel(**spec)


def test_direct_origin_application_rejects_unvalidated_input_before_mutation():
    sim = initial(parameters())
    before = sim.G.as_df()
    invalid = parameters(**ORIGIN).model_copy(update={"research_base_depth_cm": -1.})
    with pytest.raises(ValueError, match="positive depth"):
        sim.apply_root_origin_initialization(invalid)
    for original, actual in zip(before, sim.G.as_df()):
        pd.testing.assert_frame_equal(original, actual)


def test_native_optional_initialization_fails_if_shallow_burial_needs_primary_reorientation(monkeypatch):
    from deeprootgen.model.root import RootOrgan

    def upward_curve(organ, count, lengths):
        # Invented, length-conserving upward initial geometry guarantees crossing.
        contour = np.cumsum(lengths)
        return np.column_stack((.6 * contour, np.zeros(count), .8 * contour))

    monkeypatch.setattr(RootOrgan, "init_segment_coordinates", upward_curve)
    settings = parameters(**{**ORIGIN, "research_base_depth_cm": .001})
    sim = RootSystemSimulation(random_seed=42)
    with pytest.raises(ValueError, match="Primary validation changed or invalidated"):
        sim.run(settings)
    assert any(organ.validation_reorientations > 0 or organ.invalid_root for organ in sim.organs[1])


def test_normal_native_yaw_origin_initialization_has_zero_primary_reorientation():
    settings = parameters(**ORIGIN, research_primary_yaw_mean_deg=35., research_primary_yaw_kappa=4.)
    sim = RootSystemSimulation(random_seed=42)
    sim.run(settings)
    assert all(organ.validation_reorientations == 0 and not organ.invalid_root for organ in sim.organs[1])


def test_controlled_origin_surface_rejected_before_simulator_construction(monkeypatch):
    import deeprootgen.model as model

    def forbidden(*args, **kwargs):
        pytest.fail("S25 origin must be rejected before constructing simulator")

    monkeypatch.setattr(model, "RootSystemSimulation", forbidden)
    with pytest.raises(ValueError, match="soil surface z=20"):
        construct_skeleton(parameters(**ORIGIN, soil_surface_z_cm=25.), 42)
