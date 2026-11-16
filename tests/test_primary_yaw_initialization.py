"""Invented crown initialization checks; no observed values or ensemble seeds."""

import copy
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import RootSimulationModel
from deeprootgen.model import RootSystemSimulation
from deeprootgen.model import root as root_module
from deeprootgen.utils.tropism import sample_primary_yaw


def parameters(**updates):
    values = json.loads((Path(__file__).parents[1] / "examples/synthetic_minimal.json").read_text())
    values.update(max_order=3, min_sec_root_num=2, max_sec_root_num=3,
                  min_sec_root_length=4., max_sec_root_length=6.,
                  interbranch_distance=2., length_reduction=.7,
                  research_branch_placement="redistribute_capped", gravitropism=0.)
    values.update(updates)
    return RootSimulationModel(**values)


def initial(parameters):
    sim = RootSystemSimulation(random_seed=42)
    sim.init_organs(parameters)
    sim.position_secondary_roots(parameters)
    sim.position_primary_roots(parameters)
    return sim


def assert_geometry(nodes, edges):
    assert nodes.node_id.is_unique
    assert len(edges) == len(nodes) - 1
    assert set(edges.child_id) == set(nodes.loc[nodes.order.gt(0), "node_id"])
    by_id = nodes.set_index("node_id")
    assert np.isfinite(nodes[["x", "y", "z", "length", "diameter"]].to_numpy(float)).all()
    lengths = []
    for row in nodes.loc[nodes.order.gt(0)].itertuples():
        start = by_id.loc[row.parent_id, ["x", "y", "z"]].to_numpy(float)
        length = np.linalg.norm(np.array([row.x, row.y, row.z]) - start)
        assert length == pytest.approx(row.length, rel=1e-5, abs=1e-6)
        lengths.append(length)
        visited, node = set(), row.node_id
        while node:
            assert node not in visited
            visited.add(node)
            node = int(by_id.loc[node, "parent_id"])
    assert sum(lengths) == pytest.approx(nodes.length.sum(), rel=0, abs=1e-8)


def test_rigid_subtree_yaw_about_nonzero_base_preserves_z_lengths_and_attachments(monkeypatch):
    sim = initial(parameters())
    origin = np.array([7., -4., 11.])
    for node in sim.G.nodes:
        data = node.node_data
        data.x += origin[0]
        data.y += origin[1]
        data.z += origin[2]
    before, before_edges = sim.G.as_df()
    old = before.set_index("node_id")
    state = copy.deepcopy(sim.rng.bit_generator.state)
    monkeypatch.setattr(root_module, "sample_primary_yaw", lambda *args: math.pi / 2)
    settings = parameters(research_primary_yaw_mean_deg=90., research_primary_yaw_kappa=4.)
    sim.apply_primary_yaw_initialization(settings)
    after, edges = sim.G.as_df()
    actual = after.set_index("node_id")
    pd.testing.assert_frame_equal(before_edges, edges)
    pd.testing.assert_frame_equal(before.drop(columns=["x", "y"]), after.drop(columns=["x", "y"]))
    pd.testing.assert_series_equal(old.loc[0], actual.loc[0])
    assert state == sim.rng.bit_generator.state
    for primary in sim.organs[1]:
        apex_id = primary.segments[-1].node_data.node_id
        chord = old.loc[apex_id, ["x", "y", "z"]].to_numpy(float) - origin
        delta = math.pi / 2 - math.atan2(chord[1], chord[0])
        rotation = np.array([[math.cos(delta), -math.sin(delta)],
                             [math.sin(delta), math.cos(delta)]])
        subtree = [primary]
        while subtree:
            organ = subtree.pop()
            for node in organ.segments:
                nid = node.node_data.node_id
                expected = (old.loc[nid, ["x", "y"]].to_numpy(float) - origin[:2]) @ rotation.T + origin[:2]
                np.testing.assert_allclose(actual.loc[nid, ["x", "y"]].to_numpy(float), expected,
                                           rtol=0, atol=1e-10)
            subtree.extend(organ.child_organs)
        # Basal-to-apex inclination is preserved, even for bent primary paths.
        new_chord = actual.loc[apex_id, ["x", "y", "z"]].to_numpy(float) - origin
        assert np.linalg.norm(new_chord[:2]) == pytest.approx(np.linalg.norm(chord[:2]), abs=1e-10)
        assert new_chord[2] == chord[2]
    for receipt in sim.primary_yaw_diagnostics:
        assert receipt["assigned_yaw_deg"] == pytest.approx(90.)
        assert receipt["realised_yaw_deg"] == pytest.approx(90.)
        assert receipt["base_cm"] == list(origin)
    assert_geometry(after, edges)


def test_native_positioning_hook_is_deterministic_finite_and_does_not_advance_rng():
    legacy = initial(parameters())
    settings = parameters(research_primary_yaw_mean_deg=35., research_primary_yaw_kappa=4.)
    opted_in, repeated = initial(settings), initial(settings)
    baseline_nodes, baseline_edges = legacy.G.as_df()
    nodes, edges = opted_in.G.as_df()
    assert opted_in.rng.bit_generator.state == legacy.rng.bit_generator.state
    pd.testing.assert_frame_equal(baseline_edges, edges)
    pd.testing.assert_frame_equal(baseline_nodes.drop(columns=["x", "y"]), nodes.drop(columns=["x", "y"]))
    for a, b in zip(opted_in.G.as_df(), repeated.G.as_df()):
        pd.testing.assert_frame_equal(a, b)
    assert not baseline_nodes[["x", "y"]].equals(nodes[["x", "y"]])
    assert len(opted_in.primary_yaw_diagnostics) == 2
    for receipt in opted_in.primary_yaw_diagnostics:
        residual = math.radians(receipt["realised_yaw_deg"] - receipt["assigned_yaw_deg"])
        assert math.atan2(math.sin(residual), math.cos(residual)) == pytest.approx(0, abs=1e-12)
        assert receipt["stream_version"] == "drg-primary-yaw-v1"
    assert_geometry(nodes, edges)


def test_independent_versioned_streams_and_bounds():
    first = sample_primary_yaw(35., 4., 42, 1)
    assert first == sample_primary_yaw(35., 4., 42, 1)
    assert first != sample_primary_yaw(35., 4., 42, 2)
    assert first != sample_primary_yaw(35., 4., 43, 1)
    for mean, kappa in [(-180., 0.), (180., 100.), (0., 10.)]:
        assert -math.pi <= sample_primary_yaw(mean, kappa, 42, 1) <= math.pi


def test_explicit_absent_controls_preserve_default_graph():
    implicit = initial(parameters())
    explicit = initial(parameters(research_primary_yaw_mean_deg=None, research_primary_yaw_kappa=None))
    for a, b in zip(implicit.G.as_df(), explicit.G.as_df()):
        pd.testing.assert_frame_equal(a, b)
    assert not hasattr(implicit, "primary_yaw_diagnostics")
    assert not hasattr(explicit, "primary_yaw_diagnostics")


def test_zero_horizontal_chord_rejected_before_any_rotation():
    sim = initial(parameters())
    final_primary = sim.organs[1][-1]
    apex = final_primary.segments[-1].node_data
    apex.x, apex.y = sim.G.base_node.node_data.x, sim.G.base_node.node_data.y
    before, _ = sim.G.as_df()
    with pytest.raises(ValueError, match="zero-horizontal chord"):
        settings = parameters(research_primary_yaw_mean_deg=35., research_primary_yaw_kappa=4.)
        sim.apply_primary_yaw_initialization(settings)
    after, _ = sim.G.as_df()
    pd.testing.assert_frame_equal(before, after)


@pytest.mark.parametrize("updates", [
    {"research_primary_yaw_mean_deg": 35.},
    {"research_primary_yaw_kappa": 4.},
    {"research_primary_yaw_mean_deg": np.nan, "research_primary_yaw_kappa": 4.},
    {"research_primary_yaw_mean_deg": np.inf, "research_primary_yaw_kappa": 4.},
    {"research_primary_yaw_mean_deg": 181., "research_primary_yaw_kappa": 4.},
    {"research_primary_yaw_mean_deg": -181., "research_primary_yaw_kappa": 4.},
    {"research_primary_yaw_mean_deg": 35., "research_primary_yaw_kappa": -1.},
    {"research_primary_yaw_mean_deg": 35., "research_primary_yaw_kappa": 101.},
    {"research_primary_yaw_mean_deg": 35., "research_primary_yaw_kappa": np.inf},
    {"research_primary_yaw_mean_deg": 35., "research_primary_yaw_kappa": np.nan},
    {"research_primary_yaw_mean_deg": 35., "research_primary_yaw_kappa": 4., "random_seed": None},
])
def test_missing_nonfinite_and_out_of_range_controls_rejected(updates):
    with pytest.raises(ValueError):
        parameters(**updates)


@pytest.mark.parametrize("seed,organ", [(None, 1), (-1, 1), (True, 1), (42, 0), (42, 1.5)])
def test_sampler_rejects_invalid_stream_keys(seed, organ):
    with pytest.raises(ValueError):
        sample_primary_yaw(35., 4., seed, organ)


@pytest.mark.parametrize("constructor_seed", [None, 43])
@pytest.mark.parametrize("method", ["run", "position_secondary_roots", "position_primary_roots", "apply_primary_yaw_initialization"])
def test_yaw_seed_guard_rejects_before_position_or_rng_mutation(constructor_seed, method):
    settings = parameters(research_primary_yaw_mean_deg=35., research_primary_yaw_kappa=4.)
    sim = RootSystemSimulation(random_seed=constructor_seed)
    assert sim.random_seed == constructor_seed
    sim.init_organs(parameters())
    before = sim.G.as_df()
    rng_before = copy.deepcopy(sim.rng.bit_generator.state)
    with pytest.raises(ValueError, match="equal explicit constructor and parameter seeds"):
        getattr(sim, method)(settings)
    for original, actual in zip(before, sim.G.as_df()):
        pd.testing.assert_frame_equal(original, actual)
    assert rng_before == sim.rng.bit_generator.state
    assert not hasattr(sim, "primary_yaw_diagnostics")


def test_yaw_guard_rejects_missing_input_seed_even_if_validation_was_bypassed():
    settings = parameters(research_primary_yaw_mean_deg=35., research_primary_yaw_kappa=4.)
    # model_copy deliberately represents hand-assembled/unvalidated caller input.
    invalid = settings.model_copy(update={"random_seed": None})
    sim = RootSystemSimulation(random_seed=42)
    sim.init_organs(settings)
    before = sim.G.as_df()
    with pytest.raises(ValueError, match="equal explicit constructor and parameter seeds"):
        sim.position_primary_roots(invalid)
    for original, actual in zip(before, sim.G.as_df()):
        pd.testing.assert_frame_equal(original, actual)


def test_default_legacy_positioning_retains_constructor_seed_authority():
    sim = RootSystemSimulation(random_seed=43)
    settings = parameters()  # legacy input seed42 historically does not override constructor43
    sim.init_organs(settings)
    sim.position_secondary_roots(settings)
    sim.position_primary_roots(settings)
    assert sim.random_seed == 43
    assert not hasattr(sim, "primary_yaw_diagnostics")
    assert_geometry(*sim.G.as_df())
