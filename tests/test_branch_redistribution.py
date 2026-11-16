"""Synthetic checks for the one-factor opt-in branch-placement experiment."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import RootSimulationModel, RootTypeModel
from deeprootgen.model import RootSystemSimulation
from deeprootgen.model import root as root_module
from deeprootgen.model.hgraph import RootSystemGraph
from deeprootgen.utils.branching import redistribute_capped_sites, sample_branch_sites

BENT = np.array([[0., 0., 0.], [0., 0., -10.], [30., 0., -10.]])


def parameters(mode=None):
    values = json.loads((Path(__file__).parents[1] / "examples/synthetic_minimal.json").read_text())
    values.update(max_order=2, min_sec_root_num=4, max_sec_root_num=5,
                  growth_sec_root=0., interbranch_distance=.5,
                  floor_threshold=.1, ceiling_threshold=.9,
                  min_primary_length=40., max_primary_length=40.,
                  min_sec_root_length=4., max_sec_root_length=6., random_seed=42)
    if mode is not None:
        values["research_branch_placement"] = mode
    return RootSimulationModel(**values)


def prepared_organ(mode=None, distance=.5):
    organ = object.__new__(root_module.RootOrgan)
    values = dict(interbranch_distance=distance, floor_threshold=.1, ceiling_threshold=.9)
    if mode is not None:
        values["research_branch_placement"] = mode
    organ.input_parameters = SimpleNamespace(**values)
    organ.rng = np.random.default_rng(42)
    organ._draw_lateral_count = lambda: 4
    return organ


def assert_tree_geometry(nodes, edges):
    assert nodes.node_id.is_unique
    by_id = nodes.set_index("node_id")
    assert set(edges.parent_id) <= set(nodes.node_id)
    assert set(edges.child_id) == set(nodes.loc[nodes.order.gt(0), "node_id"])
    assert len(edges) == len(nodes) - 1
    assert np.isfinite(nodes[["x", "y", "z", "length", "diameter"]].to_numpy(float)).all()
    assert (nodes[["length", "diameter"]] >= 0).all().all()
    lengths = []
    for row in nodes.loc[nodes.order.gt(0)].itertuples():
        parent = by_id.loc[row.parent_id, ["x", "y", "z"]].to_numpy(float)
        length = np.linalg.norm(np.array([row.x, row.y, row.z]) - parent)
        assert length == pytest.approx(row.length, rel=1e-5, abs=1e-6)
        lengths.append(length)
        visited, nid = set(), row.node_id
        while nid != 0:
            assert nid not in visited
            visited.add(nid)
            nid = int(by_id.loc[nid, "parent_id"])
    assert sum(lengths) == pytest.approx(nodes.length.sum(), rel=0, abs=1e-8)


def test_analytic_straight_parent_quantile_sites():
    straight = np.array([[0., 0., 0.], [40., 0., 0.]])
    assert redistribute_capped_sites(straight, 4, .1, .9) == [8., 16., 24., 32.]
    assert redistribute_capped_sites(straight, 0, .1, .9) == []
    assert redistribute_capped_sites(straight, 1, 0., 1.) == [20.]
    assert redistribute_capped_sites(BENT, np.int64(4), .1, .9) == [8., 16., 24., 32.]


def test_actual_bent_parent_construction_preserves_corners_lengths_and_attachments(monkeypatch):
    p = parameters("redistribute_capped")
    graph = RootSystemGraph()
    organ = root_module.RootOrgan(
        graph.base_node, p,
        RootTypeModel(root_type="structural", order_type="primary", position_type="outer"),
        "synthetic-bent", np.random.default_rng(42),
    )
    monkeypatch.setattr(organ, "init_diameters", lambda *args: np.array([.3, .2]))
    monkeypatch.setattr(organ, "init_lengths", lambda *args: np.array([10., 30.]))
    monkeypatch.setattr(organ, "init_segment_coordinates", lambda *args: BENT[1:].copy())
    monkeypatch.setattr(organ, "_draw_lateral_count", lambda: 4)
    organ.construct_root(2, .02, .05)
    attachment_ids = [node.node_data.node_id for node in organ.lateral_attachment_nodes]
    sites = np.cumsum(organ.get_lengths())
    nodes, edges = graph.as_df()
    attachment_nodes = nodes.loc[nodes.node_id.isin(attachment_ids)]
    np.testing.assert_allclose(attachment_nodes[["x", "y", "z"]],
                               [[0, 0, -8], [6, 0, -10], [14, 0, -10], [22, 0, -10]],
                               rtol=1e-5, atol=1e-6)
    np.testing.assert_allclose([sites[index] for index, node in enumerate(organ.segments)
                                if node.node_data.node_id in attachment_ids], [8, 16, 24, 32],
                               rtol=0, atol=1e-8)
    assert any(np.array_equal(point, BENT[1]) for point in organ.get_coordinates())
    assert organ.get_lengths().sum() == pytest.approx(40, rel=0, abs=1e-8)
    assert_tree_geometry(nodes, edges)
    daughters = [organ.add_child_organ() for _ in range(4)]
    assert [daughter.parent_node.node_data.node_id for daughter in daughters] == attachment_ids
    assert not organ.lateral_attachment_nodes


def test_sampler_called_once_with_same_arguments_count_and_rng_state(monkeypatch):
    calls = []

    def record_sampler(**kwargs):
        sites = sample_branch_sites(**kwargs)
        calls.append((kwargs, sites, copy.deepcopy(kwargs["rng"].bit_generator.state)))
        return sites

    monkeypatch.setattr(root_module, "sample_branch_sites", record_sampler)
    results, final_states = [], []
    for mode in (None, "legacy_spacing", "redistribute_capped"):
        organ = prepared_organ(mode)
        results.append(organ._prepare_branch_nodes(np.array([.3, .2]), np.array([10., 30.]), BENT[1:]))
        assert organ.rng.bit_generator.state == calls[-1][2]  # redistribution consumes no draws
        final_states.append(copy.deepcopy(organ.rng.bit_generator.state))
    assert len(calls) == 3
    assert all(state == final_states[0] for state in final_states)
    for kwargs, sites, _ in calls:
        np.testing.assert_array_equal(kwargs["parent_xyz"], BENT)
        assert kwargs["interbranch_distance"] == .5
        assert kwargs["floor_threshold"] == .1 and kwargs["ceiling_threshold"] == .9
        assert kwargs["max_branches"] == 4 and len(sites) == 4
    assert calls[0][1] == calls[1][1] == calls[2][1]
    assert len(results[0][3]) == len(results[1][3]) == len(results[2][3]) == 4
    for first, second in zip(results[0], results[1]):
        np.testing.assert_array_equal(first, second)
    assert not np.array_equal(results[0][2], results[2][2])


def test_zero_retained_count_keeps_sampler_call_and_geometry(monkeypatch):
    calls = []

    def record_sampler(**kwargs):
        sites = sample_branch_sites(**kwargs)
        calls.append(sites)
        return sites

    monkeypatch.setattr(root_module, "sample_branch_sites", record_sampler)
    organ = prepared_organ("redistribute_capped", distance=500.)
    d, lengths, coordinates, attachments = organ._prepare_branch_nodes(
        np.array([.3, .2]), np.array([10., 30.]), BENT[1:],
    )
    assert calls == [[]] and attachments == []
    np.testing.assert_array_equal(d, [.3, .2])
    np.testing.assert_array_equal(lengths, [10., 30.])
    np.testing.assert_array_equal(coordinates, BENT[1:])


def test_opt_in_initial_graphs_are_deterministic_connected_and_retain_parent_counts():
    graphs = []
    for mode in ("legacy_spacing", "redistribute_capped", "redistribute_capped"):
        p = parameters(mode)
        sim = RootSystemSimulation(random_seed=42)
        sim.init_organs(p)
        sim.position_secondary_roots(p)
        sim.position_primary_roots(p)
        nodes, edges = sim.G.as_df()
        assert_tree_geometry(nodes, edges)
        assert nodes.loc[nodes.order.eq(1), "organ_id"].nunique() == 2
        assert nodes.loc[nodes.order.eq(2), "organ_id"].nunique() == 8
        assert nodes.loc[nodes.order.eq(1), "length"].sum() == pytest.approx(80, rel=0, abs=1e-8)
        graphs.append((nodes, edges))
    for first, second in zip(graphs[1], graphs[2]):
        pd.testing.assert_frame_equal(first, second)
    # The unchanged daughter formula uses parent subsegment lengths; no assertion
    # of whole-system length identity is made for the opt-in mode.
    assert not graphs[0][0][["x", "y", "z"]].equals(graphs[1][0][["x", "y", "z"]])


def test_default_and_explicit_legacy_model_graphs_match():
    implicit, explicit = parameters(), parameters("legacy_spacing")
    assert implicit.research_branch_placement == "legacy_spacing"
    graphs = []
    for p in (implicit, explicit):
        sim = RootSystemSimulation(random_seed=42)
        sim.run(p)
        graphs.append(sim.G.as_df())
    for first, second in zip(*graphs):
        pd.testing.assert_frame_equal(first, second)
    with pytest.raises(ValueError):
        RootSimulationModel(**{**implicit.model_dump(), "research_branch_placement": "unknown"})


@pytest.mark.parametrize("count", [-1, 1.5, True, np.bool_(False), "4"])
def test_invalid_retained_count_rejected(count):
    with pytest.raises((TypeError, ValueError), match="retained_count"):
        redistribute_capped_sites(BENT, count, .1, .9)


@pytest.mark.parametrize("floor,ceiling", [(-.1, .9), (.9, .1), (.5, .5), (0, 1.1),
                                           (np.nan, .9), (.1, np.inf)])
def test_invalid_fraction_window_rejected_even_with_zero_count(floor, ceiling):
    with pytest.raises(ValueError, match="threshold"):
        redistribute_capped_sites(BENT, 0, floor, ceiling)


@pytest.mark.parametrize("coordinates", [
    [0, 0, 0], [[0, 0, 0]], [[0, 0], [1, 1]],
    [[0, 0, 0], [0, 0, 0]], [[0, 0, 0], [np.nan, 0, 1]],
])
def test_invalid_parent_geometry_rejected_even_with_zero_count(coordinates):
    with pytest.raises(ValueError, match="parent_xyz|zero-length|finite"):
        redistribute_capped_sites(coordinates, 0, .1, .9)
