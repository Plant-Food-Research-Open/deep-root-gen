"""Deterministic tests for RootSystemSimulation's untested orchestration paths."""

from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace as NS

import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from deeprootgen.model import RootSystemSimulation

mod = import_module(RootSystemSimulation.__module__)


def bare_sim():
    sim = object.__new__(RootSystemSimulation)
    sim.rng = np.random.default_rng(123)
    sim.simulation_tag = "test"
    sim.G = NS(base_node=NS())
    sim.organs = {}
    return sim


def fake_organ(position_type="outer"):
    calls = []
    obj = NS(
        root_type=NS(position_type=position_type),
        update_transform=lambda **kw: calls.append(("update", kw)),
        transform=lambda: calls.append(("transform", None)),
        cascading_update_transform=lambda **kw: calls.append(("cascade_update", kw)),
        cascading_transform=lambda: calls.append(("cascade_transform", None)),
        get_parent_origin=lambda: np.array([1.0, 2.0, -3.0]),
        validate=lambda *a: calls.append(("validate", a)),
        grow=lambda *a: calls.append(("grow", a)),
    )
    return obj, calls


def test_init_fig_uses_soil_grid_if_enabled():
    sim = bare_sim()
    calls = []
    soil_grid = pd.DataFrame({"x": [0.0], "y": [0.0], "z": [-10.0]})
    fig = go.Figure()
    sim.soil = NS(
        create_soil_grid=lambda *a: (calls.append(("grid", a)) or soil_grid),
        create_soil_fig=lambda g: (calls.append(("figure", g)) or fig),
    )
    params = NS(
        enable_soil=True,
        soil_layer_height=10.0,
        soil_n_layers=3,
        soil_layer_width=5.0,
        soil_n_cols=4,
    )
    result = sim.init_fig(params)
    assert result is fig
    assert calls[0] == ("grid", (10.0, 3, 5.0, 4))
    assert calls[1][0] == "figure"
    assert calls[1][1] is soil_grid


def test_plot_hierarchical_graph_returns_lines_and_nodes():
    sim = bare_sim()
    graph = nx.Graph()
    defaults = dict(
        organ_id=1,
        order=1,
        segment_rank=1,
        diameter=0.2,
        length=2.0,
        root_type="structural",
        order_type="primary",
        position_type="outer",
        simulation_tag="test",
    )
    for idx, xyz in enumerate([(0.0, 0.0, 0.0), (0.0, 0.0, -2.0)]):
        graph.add_node(idx, x=dict(x=xyz[0], y=xyz[1], z=xyz[2], **defaults))
    graph.add_edge(0, 1)
    fig = sim.plot_hierarchical_graph(graph)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2
    assert list(fig.data[0].x) == [0.0, 0.0, None]
    assert list(fig.data[1].z) == [0.0, -2.0]


def test_plot_root_system_filters_invalid_nodes():
    sim = bare_sim()
    rows = [
        dict(
            x=0.0,
            y=0.0,
            z=-2.0,
            organ_id=1,
            order=1,
            segment_rank=1,
            diameter=0.2,
            length=2.0,
            root_type="structural",
            order_type="primary",
            position_type="outer",
            simulation_tag="test",
            invalid_root=False,
        ),
        dict(
            x=0.0,
            y=0.0,
            z=-4.0,
            organ_id=1,
            order=1,
            segment_rank=2,
            diameter=0.2,
            length=2.0,
            root_type="structural",
            order_type="primary",
            position_type="outer",
            simulation_tag="test",
            invalid_root=True,
        ),
    ]
    fig = sim.plot_root_system(go.Figure(), pd.DataFrame(rows))
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    assert list(fig.data[0].z) == [-2.0]


@pytest.mark.parametrize("max_order", [1, 2, 3])
def test_validation_visits_each_organ_once(max_order):
    sim = bare_sim()
    organs = [fake_organ()[0] for _ in range(max_order)]
    logs = [[] for _ in organs]
    for organ, log in zip(organs, logs):
        organ.validate = lambda *a, _log=log: _log.append(a)
    sim.organs = {order: [organs[order - 1]] for order in range(1, max_order + 1)}
    sim.validate(
        NS(max_order=max_order, no_root_zone=-0.5, max_val_attempts=10), pitch=45
    )
    assert logs == [[(-0.5, 45, 10)] for _ in organs]


def test_grow_visits_only_secondary_and_higher_order_roots():
    sim = bare_sim()
    first, first_log = fake_organ()
    second, second_log = fake_organ()
    third, third_log = fake_organ()
    sim.organs = {1: [first], 2: [second], 3: [third]}
    params = NS(max_order=3, t=2)
    sim.grow(sim, params)
    assert first_log == []
    assert len([name for name, _ in second_log if name == "grow"]) == 2
    assert len([name for name, _ in third_log if name == "grow"]) == 2


def test_position_secondary_roots_applies_transforms_and_translation():
    sim = bare_sim()
    second, log2 = fake_organ()
    third, log3 = fake_organ()
    sim.organs = {1: [], 2: [second], 3: [third]}
    sim.position_secondary_roots(NS(max_order=3))
    for log in (log2, log3):
        assert [n for n, _ in log] == [
            "update",
            "update",
            "transform",
            "update",
            "transform",
            "cascade_update",
            "cascade_transform",
        ]
        np.testing.assert_array_equal(log[-2][1]["translation"], [1.0, 2.0, -3.0])


def test_init_organs_constructs_requested_primary_roots(monkeypatch):
    sim = bare_sim()
    constructed = []

    class FakeRoot:
        def __init__(
            self, parent_node, input_parameters, root_type, simulation_tag, rng
        ):
            self.parent_node = parent_node
            self.root_type = root_type
            self.lateral_attachment_nodes = []
            constructed.append(self)

        def construct_root(self, nsegments, apex_diameter, density):
            assert (nsegments, apex_diameter, density) == (5, 0.05, 0.15)

    enum_value = lambda value: NS(value=value)  # noqa: E731
    monkeypatch.setattr(mod, "RootOrgan", FakeRoot)
    monkeypatch.setattr(mod, "RootTypeModel", lambda **kw: NS(**kw))
    monkeypatch.setattr(
        mod,
        "RootType",
        NS(
            STRUCTURAL=enum_value("structural"),
            PRIMARY=enum_value("primary"),
            OUTER=enum_value("outer"),
            INNER=enum_value("inner"),
        ),
    )
    p = NS(
        max_order=1,
        outer_root_num=3,
        inner_root_num=2,
        segments_per_root=5,
        apex_diameter=0.05,
        root_tissue_density=0.15,
    )
    result = sim.init_organs(p)
    assert len(constructed) == 5
    assert list(result) == [1]
    assert result[1] == constructed
    assert [v.root_type.position_type for v in constructed] == [
        "outer",
        "outer",
        "outer",
        "inner",
        "inner",
    ]


def test_init_organs_constructs_higher_order_daughters(monkeypatch):
    sim = bare_sim()
    created = []

    class FakeRoot:
        def __init__(
            self, parent_node, input_parameters, root_type, simulation_tag, rng
        ):
            self.parent_node = parent_node
            self.root_type = root_type
            self.lateral_attachment_nodes = []
            created.append(self)

        def construct_root(self, nsegments, apex_diameter, density):
            self.lateral_attachment_nodes = ["site"]

        def add_child_organ(self, **kw):
            self.lateral_attachment_nodes.pop(0)
            child = FakeRoot("parent", None, self.root_type, "test", None)
            return child

        def construct_root_from_parent(self, nsegments, apex_diameter):
            self.lateral_attachment_nodes = []

    enum_value = lambda value: NS(value=value)  # noqa: E731
    monkeypatch.setattr(mod, "RootOrgan", FakeRoot)
    monkeypatch.setattr(mod, "RootTypeModel", lambda **kw: NS(**kw))
    monkeypatch.setattr(
        mod,
        "RootType",
        NS(
            STRUCTURAL=enum_value("structural"),
            PRIMARY=enum_value("primary"),
            OUTER=enum_value("outer"),
            INNER=enum_value("inner"),
        ),
    )
    p = NS(
        max_order=2,
        outer_root_num=1,
        inner_root_num=0,
        segments_per_root=5,
        apex_diameter=0.05,
        root_tissue_density=0.15,
        floor_threshold=0.25,
        ceiling_threshold=0.9,
    )
    result = sim.init_organs(p)
    assert len(result[1]) == 1
    assert len(result[2]) == 1
    assert len(created) == 2


def test_run_orders_simulation_steps_correctly():
    sim = bare_sim()
    stages = []
    for method in (
        "init_organs",
        "position_secondary_roots",
        "position_primary_roots",
        "apply_gravitropism",
        "validate",
    ):
        setattr(sim, method, lambda *args, _method=method, **kw: stages.append(_method))
    sim.run(NS(gravitropism=0.15))
    assert stages == [
        "init_organs",
        "position_secondary_roots",
        "position_primary_roots",
        "apply_gravitropism",
        "validate",
    ]


def test_init_creates_fresh_graph_and_reproducible_rng(monkeypatch):
    graph = NS(base_node=NS())
    soil = NS()
    monkeypatch.setattr(mod, "RootSystemGraph", lambda: graph)
    monkeypatch.setattr(mod, "Soil", lambda: soil)
    sim = RootSystemSimulation(simulation_tag="unit", random_seed=42)
    assert sim.G is graph
    assert sim.soil is soil
    assert sim.organs == {}
    assert sim.simulation_tag == "unit"
    assert sim.rng.random() == pytest.approx(np.random.default_rng(42).random())


def test_position_primary_roots_transforms_outer_and_inner(monkeypatch):
    sim = bare_sim()
    outer_a, log_a = fake_organ("outer")
    outer_b, log_b = fake_organ("outer")
    inner, log_i = fake_organ("inner")
    sim.organs = {1: [outer_a, outer_b, inner]}
    monkeypatch.setattr(
        mod, "RootType", NS(OUTER=NS(value="outer"), INNER=NS(value="inner"))
    )
    sim.position_primary_roots(NS(outer_root_num=2, inner_root_num=1))
    for log in (log_a, log_b, log_i):
        assert [name for name, _ in log] == ["cascade_update", "cascade_transform"]
        assert "pitch" in log[0][1]
        assert "yaw" in log[0][1]
    assert log_a[0][1]["yaw"] == pytest.approx(180.0)
    assert log_i[0][1]["yaw"] == pytest.approx(360.0)


def test_position_primary_roots_skips_unrecognised_positions(monkeypatch):
    sim = bare_sim()
    other, calls = fake_organ("unknown")
    sim.organs = {1: [other]}
    monkeypatch.setattr(
        mod, "RootType", NS(OUTER=NS(value="outer"), INNER=NS(value="inner"))
    )
    sim.position_primary_roots(NS(outer_root_num=1, inner_root_num=1))
    assert calls == []
