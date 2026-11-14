"""Invented primary-subtree geometry only; no observations or trial seeds."""

import copy

import numpy as np
import pandas as pd
import pytest

from deeprootgen.model import RootSystemSimulation
from deeprootgen.research.so4_controlled import construct_skeleton, replay_arm, validate_geometry
from deeprootgen.utils.primary_orientation import inclination_rotation, proper_rotation
from tests.test_root_origin_initialization import parameters as origin_parameters


def parameters(**updates):
    values = dict(min_primary_length=5., max_primary_length=6., root_vary=2.,
                  segments_per_root=3, interbranch_distance=.5)
    values.update(updates)
    return origin_parameters(**values)


def initial(settings):
    sim = RootSystemSimulation(random_seed=settings.random_seed)
    sim.init_organs(settings)
    sim.position_secondary_roots(settings)
    sim.position_primary_roots(settings)
    return sim


def subtree_ids(primary):
    pending, result = [primary], []
    while pending:
        organ = pending.pop()
        result.extend(node.node_data.node_id for node in organ.segments)
        pending.extend(organ.child_organs)
    return result


@pytest.mark.parametrize("source,target", [
    ([1., 0., 0.], [0., 0., -1.]), ([0., 0., -1.], [0., 0., -1.]),
    ([0., 0., 1.], [0., 0., -1.]), ([1e-9, 0., 1.], [0., 0., -1.]),
])
def test_proper_rotations_are_deterministic_orthogonal_and_handle_antiparallel(source, target):
    rotation = proper_rotation(source, target)
    np.testing.assert_array_equal(rotation, proper_rotation(source, target))
    np.testing.assert_allclose(rotation.T @ rotation, np.eye(3), rtol=0, atol=1e-12)
    assert np.linalg.det(rotation) == pytest.approx(1., abs=1e-12)
    np.testing.assert_allclose(rotation @ (np.array(source) / np.linalg.norm(source)),
                               np.array(target) / np.linalg.norm(target), rtol=0, atol=1e-12)


def test_analytic_horizontal_bias_and_vertical_parallel_and_zero_target():
    rotation, report = inclination_rotation([3., 4., 0.], .5)
    target = np.array([.6, .8, -.5]) / np.sqrt(1.25)
    np.testing.assert_allclose(rotation @ [.6, .8, 0.], target, atol=1e-12)
    assert report["target_angles"]["inclination_down_deg"] == pytest.approx(np.degrees(np.arctan(.5)))
    assert report["target_angles"]["azimuth_deg"] == pytest.approx(np.degrees(np.arctan2(4., 3.)))
    downward, report = inclination_rotation([0., 0., -3.], 1.)
    np.testing.assert_array_equal(downward, np.eye(3))
    assert report["target_angles"]["azimuth_deg"] is None
    for chord, bias in [([0., 0., 0.], .5), ([0., 0., 3.], 1.)]:
        with pytest.raises(ValueError, match="zero or degenerate"):
            inclination_rotation(chord, bias)


@pytest.mark.parametrize("curved", [False, True])
def test_multiple_actual_primary_subtrees_rigidly_rotate_about_nonzero_base(curved):
    sim = initial(parameters())
    base = np.array([7., -4., 9.])
    for node in sim.G.nodes:
        data = node.node_data
        data.x += base[0]
        data.y += base[1]
        data.z += base[2]
    for index, primary in enumerate(sim.organs[1]):
        curve = np.array([[1., 0., 0.], [2., 1. if curved else 0., 0.], [3., 1. if curved else 0., 0.]])
        curve[:, :2] *= (-1 if index else 1)
        primary.set_coordinates(curve + base)
    # Establish consistent invented segment metadata after placing the curves.
    lookup = {node.node_data.node_id: node.node_data for node in sim.G.nodes}
    for node in sim.G.nodes:
        data = node.node_data
        if data.order:
            parent = lookup[data.parent_id]
            data.length = np.linalg.norm(np.array([data.x - parent.x, data.y - parent.y, data.z - parent.z]))
    before, before_edges = sim.G.as_df()
    old = before.set_index("node_id")
    state = copy.deepcopy(sim.rng.bit_generator.state)
    sim.apply_primary_inclination_initialization(parameters(research_primary_inclination_bias=.5))
    after, edges = sim.G.as_df()
    new = after.set_index("node_id")
    pd.testing.assert_frame_equal(before.drop(columns=["x", "y", "z"]), after.drop(columns=["x", "y", "z"]))
    pd.testing.assert_frame_equal(before_edges, edges)
    pd.testing.assert_series_equal(old.loc[0], new.loc[0])
    assert state == sim.rng.bit_generator.state
    assert len(sim.primary_inclination_diagnostics) == len(sim.organs[1]) == 2
    for primary, report in zip(sim.organs[1], sim.primary_inclination_diagnostics):
        ids = subtree_ids(primary)
        rotation = np.array(report["rotation"])
        expected = (old.loc[ids, ["x", "y", "z"]].to_numpy(float) - base) @ rotation.T + base
        np.testing.assert_allclose(new.loc[ids, ["x", "y", "z"]], expected, rtol=0, atol=1e-12)
        np.testing.assert_allclose(report["target_chord_unit"], report["realised_chord_unit"], atol=1e-12)
        assert report["target_angles"]["inclination_down_deg"] > report["original_angles"]["inclination_down_deg"]
        assert report["target_angles"]["azimuth_deg"] == pytest.approx(report["original_angles"]["azimuth_deg"])
        assert report["maximum_edge_length_residual_cm"] <= 1e-8
        if curved:
            points = new.loc[[node.node_data.node_id for node in primary.segments], ["x", "y", "z"]].to_numpy(float)
            assert np.linalg.norm(np.cross(points[1] - points[0], points[2] - points[1])) > .5
    validate_geometry(after, edges)


@pytest.mark.parametrize("failure", ["zero_chord", "zero_target", "nonfinite_descendant"])
def test_all_subtrees_planned_before_atomic_failure(failure):
    sim = initial(parameters())
    primary = sim.organs[1][-1]
    apex = primary.segments[-1].node_data
    base = sim.G.base_node.node_data
    if failure == "zero_chord":
        apex.x, apex.y, apex.z = base.x, base.y, base.z
    elif failure == "zero_target":
        apex.x, apex.y, apex.z = base.x, base.y, base.z + 3.
    else:
        sim.G.nodes[-1].node_data.x = np.nan
    before = sim.G.as_df()
    state = copy.deepcopy(sim.rng.bit_generator.state)
    with pytest.raises(ValueError):
        sim.apply_primary_inclination_initialization(parameters(research_primary_inclination_bias=1.))
    for a, b in zip(before, sim.G.as_df()):
        pd.testing.assert_frame_equal(a, b)
    assert not hasattr(sim, "primary_inclination_diagnostics")
    assert sim.rng.bit_generator.state == state


def test_yaw_then_inclination_then_origin_composition_native_and_controlled_shared_stage():
    settings = parameters(research_primary_yaw_mean_deg=35., research_primary_yaw_kappa=4.,
                          research_primary_inclination_bias=.4, research_base_origin_x_cm=2.,
                          research_base_origin_y_cm=-3., research_base_depth_cm=8.)
    manual = initial(parameters())
    manual.apply_primary_yaw_initialization(settings)
    manual.apply_primary_inclination_initialization(settings)
    manual.apply_root_origin_initialization(settings)
    automatic, repeated = initial(settings), initial(settings)
    for expected, actual, repeat in zip(manual.G.as_df(), automatic.G.as_df(), repeated.G.as_df()):
        pd.testing.assert_frame_equal(expected, actual, check_exact=True)
        pd.testing.assert_frame_equal(actual, repeat, check_exact=True)
    assert manual.rng.bit_generator.state == automatic.rng.bit_generator.state == initial(parameters()).rng.bit_generator.state
    saved = construct_skeleton(settings, 42)
    saved_nodes = pd.DataFrame(saved.payload["nodes"])
    actual = automatic.G.as_df()[0]
    pd.testing.assert_frame_equal(saved_nodes.drop(columns="simulation_tag"), actual.drop(columns="simulation_tag"))
    replayed = replay_arm(saved, "D", settings.model_dump(), "minimum_angle_projection")
    validate_geometry(replayed["nodes"], replayed["edges"], 20.)
    native = RootSystemSimulation(random_seed=42)
    native.run(settings)
    native_nodes, native_edges = native.G.as_df()
    pd.testing.assert_frame_equal(actual.loc[actual.order.le(1)].reset_index(drop=True),
                                  native_nodes.loc[native_nodes.order.le(1)].reset_index(drop=True))
    assert all(primary.validation_reorientations == 0 and not primary.invalid_root for primary in native.organs[1])
    validate_geometry(native_nodes, native_edges, 20.)


def test_disabled_zero_exact_graph_and_rng_and_legacy_seed_authority():
    baseline = initial(parameters())
    for bias in (None, 0.):
        sim = initial(parameters(research_primary_inclination_bias=bias))
        for a, b in zip(baseline.G.as_df(), sim.G.as_df()):
            pd.testing.assert_frame_equal(a, b, check_exact=True)
        assert sim.rng.bit_generator.state == baseline.rng.bit_generator.state
        assert not hasattr(sim, "primary_inclination_diagnostics")
    sim = RootSystemSimulation(random_seed=43)
    sim.init_organs(parameters(research_primary_inclination_bias=0.))


@pytest.mark.parametrize("bias", [-.1, 1.1, np.inf, np.nan])
def test_invalid_bias_bounds_rejected(bias):
    with pytest.raises(ValueError):
        parameters(research_primary_inclination_bias=bias)


@pytest.mark.parametrize("seed", [None, 43])
def test_positive_seed_consistency_precedes_mutation(seed):
    settings = parameters(research_primary_inclination_bias=.3)
    sim = RootSystemSimulation(random_seed=seed)
    before, state = sim.G.as_df(), copy.deepcopy(sim.rng.bit_generator.state)
    with pytest.raises(ValueError, match="equal explicit constructor and parameter seeds"):
        sim.run(settings)
    for a, b in zip(before, sim.G.as_df()):
        pd.testing.assert_frame_equal(a, b)
    assert state == sim.rng.bit_generator.state
    with pytest.raises(ValueError, match="explicit random_seed"):
        parameters(research_primary_inclination_bias=.3, random_seed=None)


def test_optional_primary_guard_rejects_later_reorientation_or_invalidation():
    settings = parameters(research_primary_inclination_bias=.3)
    sim = initial(settings)
    for attribute, value in [("validation_reorientations", 1), ("invalid_root", True)]:
        primary = sim.organs[1][0]
        setattr(primary, attribute, value)
        with pytest.raises(ValueError, match="inclination initialization"):
            sim._check_optional_primary_validation(settings)
        setattr(primary, attribute, 0 if attribute == "validation_reorientations" else False)
