"""Isolated RootSystemSimulation tests without constructing the full model."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import plotly.graph_objects as go
import pytest

from deeprootgen.model import RootSystemSimulation


def fake_graph(nodes):
    """A tiny hierarchy: base -> primary segment -> lateral segment."""
    specs = [
        (0, -1, (0.0, 0.0, 0.0)),
        (1, 0, (3.0, 0.0, 0.0)),
        (2, 1, (3.0, 4.0, 0.0)),
    ]
    return SimpleNamespace(
        nodes=[
            SimpleNamespace(
                node_data=SimpleNamespace(node_id=n, parent_id=p, x=x, y=y, z=z)
            )
            for n, p, (x, y, z) in specs[:nodes]
        ]
    )


@pytest.fixture
def sim():
    model = object.__new__(RootSystemSimulation)
    model.G = fake_graph(3)
    return model


@pytest.mark.parametrize(
    "n_roots,expected",
    [
        (1, (360.0, 18.0, 360.0)),
        (2, (180.0, 9.0, 180.0)),
        (4, (90.0, 4.5, 90.0)),
        (8, (45.0, 2.25, 45.0)),
    ],
)
def test_root_yaw_spacing(sim, n_roots, expected):
    assert sim.get_yaw(n_roots) == pytest.approx(expected)


@pytest.mark.parametrize("gravity", [-0.1, 1.01, 2.0])
def test_gravitropism_outside_unit_interval_raises(sim, gravity):
    with pytest.raises(ValueError, match="gravitropism"):
        sim.apply_gravitropism(gravity)


def test_zero_gravitropism_does_not_move_nodes(sim):
    original = [(n.node_data.x, n.node_data.y, n.node_data.z) for n in sim.G.nodes]
    sim.apply_gravitropism(0.0)
    assert original == [
        (n.node_data.x, n.node_data.y, n.node_data.z) for n in sim.G.nodes
    ]


def test_full_gravitropism_points_segments_downward(sim):
    sim.apply_gravitropism(1.0)
    np.testing.assert_allclose(
        [[n.node_data.x, n.node_data.y, n.node_data.z] for n in sim.G.nodes],
        [[0, 0, 0], [0, 0, -3], [0, 0, -7]],
    )


def test_partial_gravitropism_preserves_every_segment_length(sim):
    before = [
        np.array([n.node_data.x, n.node_data.y, n.node_data.z]) for n in sim.G.nodes
    ]
    sim.apply_gravitropism(0.35)
    after = [
        np.array([n.node_data.x, n.node_data.y, n.node_data.z]) for n in sim.G.nodes
    ]
    for index in (1, 2):
        assert np.linalg.norm(after[index] - after[index - 1]) == pytest.approx(
            np.linalg.norm(before[index] - before[index - 1])
        )
        assert after[index][2] < after[index - 1][2]


def test_gravitropism_uses_each_child_parent_not_previous_node(sim):
    # Make node 2 a lateral directly off base (and not from node 1).
    sim.G.nodes[2].node_data.parent_id = 0
    sim.apply_gravitropism(1.0)
    n1, n2 = [sim.G.nodes[i].node_data for i in (1, 2)]
    assert n1.z == pytest.approx(-3.0)
    assert n2.z == pytest.approx(-5.0)


def test_gravitropism_zero_length_segment_does_not_crash(sim):
    sim.G.nodes[1].node_data.x = 0.0
    sim.apply_gravitropism(0.5)
    n1 = sim.G.nodes[1].node_data
    assert (n1.x, n1.y, n1.z) == pytest.approx((0.0, 0.0, 0.0))


def test_gravitropism_straight_down_remains_straight_down(sim):
    sim.G.nodes[1].node_data.x = 0.0
    sim.G.nodes[1].node_data.z = -3.0
    sim.G.nodes[2].node_data.x = 0.0
    sim.G.nodes[2].node_data.y = 0.0
    sim.G.nodes[2].node_data.z = -7.0
    sim.apply_gravitropism(0.7)
    assert sim.G.nodes[1].node_data.z == pytest.approx(-3.0)
    assert sim.G.nodes[2].node_data.z == pytest.approx(-7.0)


def test_init_figure_without_soil_is_plotly(sim):
    params = SimpleNamespace(enable_soil=False)
    result = sim.init_fig(params)
    assert isinstance(result, go.Figure)


def test_run_calls_stages_in_the_expected_order(sim, monkeypatch):
    calls = []
    for name in [
        "init_organs",
        "position_secondary_roots",
        "position_primary_roots",
        "apply_gravitropism",
        "validate",
    ]:
        monkeypatch.setattr(
            sim, name, lambda *args, _name=name, **kwargs: calls.append(_name)
        )
    params = SimpleNamespace(gravitropism=0.1)
    sim.run(params)
    assert calls == [
        "init_organs",
        "position_secondary_roots",
        "position_primary_roots",
        "apply_gravitropism",
        "validate",
    ]
