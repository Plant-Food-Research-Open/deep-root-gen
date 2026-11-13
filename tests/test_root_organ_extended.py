"""Additional deterministic tests for RootOrgan's less-covered methods.

Designed to accompany the existing DeepRootGen tests. No database, Dash,
Prefect, MLflow, network calls, or external root dataset required.
"""

from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace as NS

import numpy as np
import pytest

from deeprootgen.model import RootSystemSimulation

mod = import_module(RootSystemSimulation.__module__)
RootOrgan = mod.RootOrgan


def node(
    x=0.0,
    y=0.0,
    z=0.0,
    *,
    order=1,
    diameter=0.2,
    length=1.0,
    root_tissue_density=0.15,
    invalid_root=False,
):
    return NS(
        node_data=NS(
            x=float(x),
            y=float(y),
            z=float(z),
            order=order,
            diameter=diameter,
            length=length,
            root_tissue_density=root_tissue_density,
            invalid_root=invalid_root,
        )
    )


@pytest.fixture
def organ():
    obj = object.__new__(RootOrgan)
    obj.input_parameters = NS(
        max_order=3,
        min_sec_root_num=1,
        max_sec_root_num=2,
        growth_sec_root=0.0,
        interbranch_distance=2.0,
        floor_threshold=0.2,
        ceiling_threshold=0.8,
        root_vary=0.0,
        min_primary_length=10.0,
        max_primary_length=10.0,
        min_sec_root_length=4.0,
        max_sec_root_length=4.0,
        length_reduction=0.75,
        base_diameter=0.5,
        fine_root_threshold=0.15,
        diameter_reduction=0.2,
        root_tissue_density=0.15,
    )
    obj.rng = np.random.default_rng(23)
    obj.parent_node = node(order=0, diameter=0.5, length=0.0)
    obj.root_type = NS(
        root_type="structural", order_type="primary", position_type="outer"
    )
    obj.simulation_tag = "test"
    obj.proot_length_interval = np.array([10.0, 10.0])
    obj.sroot_length_interval = np.array([4.0, 4.0])
    obj.length_reduction = 0.75
    obj.fine_root_threshold = 0.15
    obj.base_diameter = 0.5
    obj.segments = []
    obj.child_organs = []
    obj.lateral_attachment_nodes = []
    obj.invalid_root = False
    obj.reset_transform()
    return obj


def test_local_coordinates_have_requested_geometric_lengths(organ):
    lengths = np.array([2.0, 3.0, 4.0])
    coords = organ.init_segment_coordinates(3, lengths)
    assert coords.shape == (3, 3)
    all_points = np.vstack(([0.0, 0.0, 0.0], coords))
    np.testing.assert_allclose(
        np.linalg.norm(np.diff(all_points, axis=0), axis=1), lengths
    )


def test_local_coordinates_deterministic_when_rng_reset(organ):
    organ.input_parameters.root_vary = 12.0
    a = organ.init_segment_coordinates(3, np.array([1.0, 2.0, 3.0]))
    organ.rng = np.random.default_rng(23)
    b = organ.init_segment_coordinates(3, np.array([1.0, 2.0, 3.0]))
    np.testing.assert_allclose(a, b)


def test_secondary_length_reduction(organ):
    organ.parent_node.node_data.order = 1
    assert organ.init_lengths(5).sum() == pytest.approx(4.0 * 0.75)


def test_length_generation_is_positive_and_conserves_total(organ):
    lengths = organ.init_lengths(10)
    assert np.all(lengths > 0)
    assert lengths.sum() == pytest.approx(10.0)


def test_diameter_generation_reproducible_with_seed(organ):
    d1 = organ.init_diameters(8, 0.05)
    organ.rng = np.random.default_rng(23)
    d2 = organ.init_diameters(8, 0.05)
    np.testing.assert_array_equal(d1, d2)
    assert np.all(np.diff(d1) <= 0)


def test_diameter_generation_scales_with_parent_order(organ):
    organ.parent_node.node_data.order = 2
    d = organ.init_diameters(12, 0.01)
    assert np.all(d >= 0.01)
    assert np.all(d <= 0.5 * 0.8**2)


def test_get_parent_and_local_origin(organ):
    organ.parent_node = node(3.0, -2.0, 7.0)
    np.testing.assert_allclose(organ.get_parent_origin(), [3.0, -2.0, 7.0])
    np.testing.assert_allclose(organ.get_local_origin(), [3.0, -2.0, 7.0])


def test_getters_support_python_lists(organ):
    organ.segments = [
        node(1.0, 2.0, 3.0, diameter=0.4, length=2.0),
        node(4.0, 5.0, 6.0, diameter=0.2, length=3.0),
    ]
    assert organ.get_coordinates(as_array=False) == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    assert organ.get_diameters(as_array=False) == [0.4, 0.2]
    assert organ.get_lengths(as_array=False) == [2.0, 3.0]


def test_update_transform_composes_translation(organ):
    organ.update_transform(translation=[1.0, 2.0, 3.0])
    organ.update_transform(translation=[4.0, 5.0, 6.0])
    # Transform matrix implementation is separately tested in the spatial module.
    assert organ.transform_matrix.shape == (4, 4)
    assert np.isfinite(organ.transform_matrix).all()


def test_transform_resets_after_application(organ):
    organ.segments = [node(0.0, 0.0, -2.0), node(0.0, 0.0, -3.0)]
    organ.update_transform(translation=[1.0, 2.0, 3.0])
    organ.transform()
    np.testing.assert_allclose(organ.transform_matrix, np.eye(4))


def test_transform_translates_segment_coordinates(organ):
    organ.segments = [node(0.0, 0.0, -2.0), node(1.0, 0.0, -5.0)]
    organ.update_transform(translation=[2.0, -3.0, 4.0])
    organ.transform()
    np.testing.assert_allclose(
        organ.get_coordinates(),
        [[2.0, -3.0, 2.0], [3.0, -3.0, -1.0]],
    )


def test_cascading_update_transform_visits_all_descendants(organ, monkeypatch):
    calls = []
    child = NS(cascading_update_transform=lambda **kw: calls.append(("child", kw)))
    organ.child_organs = [child]
    monkeypatch.setattr(
        organ, "update_transform", lambda **kw: calls.append(("parent", kw))
    )
    organ.cascading_update_transform(pitch=15.0, translation=[2.0, 0.0, 0.0])
    assert [name for name, _ in calls] == ["parent", "child"]
    assert calls[0][1] == calls[1][1]


def test_cascading_transform_visits_descendants(organ, monkeypatch):
    calls = []
    organ.child_organs = [NS(cascading_transform=lambda: calls.append("child"))]
    monkeypatch.setattr(organ, "transform", lambda: calls.append("parent"))
    organ.cascading_transform()
    assert calls == ["parent", "child"]


def test_world_origin_update_has_negative_parent_translation(organ, monkeypatch):
    calls = []
    organ.parent_node = node(2.0, -3.0, 5.0)
    monkeypatch.setattr(
        organ, "cascading_update_transform", lambda **kw: calls.append(kw)
    )
    organ.cascading_to_world_origin()
    np.testing.assert_array_equal(calls[0]["translation"], [-2.0, 3.0, -5.0])


def test_construct_segment_nodes_tracks_attachments_and_mass(organ, monkeypatch):
    def add_child(
        parent_node,
        diameters,
        lengths,
        coordinates,
        root_type,
        root_tissue_density,
        i,
        new_organ=False,
    ):
        child = node(*coordinates[i], diameter=diameters[i], length=lengths[i])
        child.parent = parent_node
        child.new_organ = new_organ
        organ.segments.append(child)
        return child

    monkeypatch.setattr(organ, "add_child_node", add_child)
    xyz = np.array([[0.0, 0.0, -2.0], [0.0, 0.0, -5.0], [0.0, 0.0, -10.0]])
    result = organ._construct_segment_nodes(
        np.array([0.4, 0.3, 0.2]),
        np.array([2.0, 3.0, 5.0]),
        xyz,
        organ.root_type,
        0.15,
        [0, 2],
    )
    assert result is organ.segments
    assert len(result) == 3
    assert organ.base_node is result[0]
    assert organ.lateral_attachment_nodes == [result[0], result[2]]
    assert [seg.new_organ for seg in result] == [True, False, False]
    assert result[1].parent is result[0]
    expected = (
        np.pi * np.sum((np.array([0.4, 0.3, 0.2]) / 2) ** 2 * [2.0, 3.0, 5.0]) * 0.15
    )
    assert organ.mass == pytest.approx(expected)


def test_construct_segment_nodes_cannot_run_twice(organ):
    organ.segments = [node()]
    with pytest.raises(RuntimeError, match="already been constructed"):
        organ._construct_segment_nodes(
            np.array([0.2]),
            np.array([2.0]),
            np.array([[0.0, 0.0, -2.0]]),
            organ.root_type,
            0.15,
            [],
        )


def test_add_child_organ_without_sites_raises(organ):
    with pytest.raises(RuntimeError, match="No lateral insertion"):
        organ.add_child_organ()


def test_add_child_organ_consumes_sites_in_order(organ):
    first, second = node(z=-3.0), node(z=-7.0)
    organ.lateral_attachment_nodes = [first, second]
    a = organ.add_child_organ()
    b = organ.add_child_organ()
    assert a.parent_node is first
    assert b.parent_node is second
    assert organ.child_organs == [a, b]
    assert organ.lateral_attachment_nodes == []
    assert a.rng is organ.rng


def test_validate_returns_without_touching_invalid_organ(organ, monkeypatch):
    organ.invalid_root = True
    monkeypatch.setattr(
        organ,
        "get_coordinates",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("unexpected")),
    )
    organ.validate(no_root_zone=0.0)


def test_validate_good_primary_organ(organ):
    organ.segments = [node(0.0, 0.0, -2.0, order=1)]
    organ.validate(no_root_zone=0.0)
    assert organ.invalid_root is False


def test_validate_secondary_with_correct_segment_length(organ):
    organ.parent_node = node(0.0, 0.0, 0.0)
    organ.segments = [node(0.0, 0.0, -3.0, order=2, length=3.0)]
    organ.validate(no_root_zone=0.0)
    assert organ.invalid_root is False


def test_validate_secondary_mismatched_segment_length_invalidates(organ):
    organ.parent_node = node(0.0, 0.0, 0.0)
    organ.segments = [node(0.0, 0.0, -3.0, order=2, length=5.0)]
    organ.validate(no_root_zone=0.0)
    assert organ.invalid_root is True
    assert organ.segments[0].node_data.invalid_root is True


def test_validate_upward_secondary_invalidates_when_cannot_reorient(organ, monkeypatch):
    organ.segments = [node(0.0, 0.0, 2.0, order=2)]
    monkeypatch.setattr(organ, "cascading_to_world_origin", lambda: None)
    monkeypatch.setattr(organ, "cascading_transform", lambda: None)
    monkeypatch.setattr(organ, "cascading_update_transform", lambda **kw: None)
    organ.validate(no_root_zone=0.0, max_attempts=0)
    assert organ.invalid_root


def test_validate_root_above_soil_invalidates_when_cannot_reorient(organ, monkeypatch):
    organ.segments = [node(0.0, 0.0, 2.0, order=1)]
    monkeypatch.setattr(organ, "cascading_to_world_origin", lambda: None)
    monkeypatch.setattr(organ, "cascading_transform", lambda: None)
    monkeypatch.setattr(organ, "cascading_update_transform", lambda **kw: None)
    organ.validate(no_root_zone=0.0, max_attempts=0)
    assert organ.invalid_root


def test_grow_adds_one_apical_segment(organ, monkeypatch):
    organ.segments = [node(0.0, 0.0, -2.0, diameter=0.3, length=2.0)]
    captured = []
    monkeypatch.setattr(organ, "init_lengths", lambda n: np.array([2.0]))
    monkeypatch.setattr(
        organ,
        "init_segment_coordinates",
        lambda n, lengths: np.array([[0.0, 0.0, -float(lengths[0])]]),
    )

    def capture(
        parent_node,
        diameters,
        lengths,
        coordinates,
        root_type,
        root_tissue_density,
        i,
        new_organ,
    ):
        captured.append((parent_node, diameters, lengths, coordinates, i, new_organ))

    monkeypatch.setattr(organ, "add_child_node", capture)
    organ.grow(simulation=None, input_parameters=organ.input_parameters)
    assert len(captured) == 1
    parent, diameters, lengths, coordinates, i, new_organ = captured[0]
    assert parent is organ.segments[-1]
    assert i == 1 and not new_organ
    assert lengths[-1] == pytest.approx(1.0)
    np.testing.assert_allclose(coordinates[-1], [0.0, 0.0, -3.0])
    assert diameters[0] > 0.3
    assert diameters[-1] == pytest.approx(0.3)


def test_init_populates_empty_graph_and_reproducible_rng(organ):
    obj = RootOrgan(
        parent_node=organ.parent_node,
        input_parameters=organ.input_parameters,
        root_type=organ.root_type,
        simulation_tag="seed-check",
        rng=np.random.default_rng(7),
    )
    assert obj.segments == []
    assert obj.child_organs == []
    assert obj.lateral_attachment_nodes == []
    assert not obj.invalid_root
    assert obj.simulation_tag == "seed-check"
    np.testing.assert_array_equal(obj.transform_matrix, np.eye(4))
    assert obj.rng.random() == pytest.approx(np.random.default_rng(7).random())


def test_add_child_node_records_graph_node_and_organ(organ, monkeypatch):
    records = []
    parent = NS(
        add_child_node=lambda data, new_organ=False: (
            records.append((data, new_organ)) or NS(node_data=data)
        )
    )
    monkeypatch.setattr(mod, "RootNodeModel", lambda **kw: NS(**kw))
    result = organ.add_child_node(
        parent_node=parent,
        diameters=np.array([0.4]),
        lengths=np.array([3.0]),
        coordinates=np.array([[1.0, 2.0, -3.0]]),
        root_type=organ.root_type,
        root_tissue_density=0.2,
        i=0,
        new_organ=True,
    )
    assert records[0][1] is True
    assert records[0][0].length == pytest.approx(3.0)
    assert records[0][0].diameter == pytest.approx(0.4)
    assert (records[0][0].x, records[0][0].y, records[0][0].z) == (1.0, 2.0, -3.0)
    assert result.organ is organ
    assert organ.segments == [result]


def test_construct_root_delegates_segment_preparation(organ, monkeypatch):
    invoked = []
    monkeypatch.setattr(organ, "init_diameters", lambda n, apex: np.array([0.3, 0.2]))
    monkeypatch.setattr(organ, "init_lengths", lambda n: np.array([2.0, 3.0]))
    monkeypatch.setattr(
        organ,
        "init_segment_coordinates",
        lambda n, lengths: np.array([[0.0, 0.0, -2.0], [0.0, 0.0, -5.0]]),
    )
    monkeypatch.setattr(
        organ, "_prepare_branch_nodes", lambda d, L, xyz: (d, L, xyz, [0])
    )
    monkeypatch.setattr(
        organ,
        "_construct_segment_nodes",
        lambda *args: (invoked.append(args) or ["built"]),
    )
    assert organ.construct_root(2, 0.01, 0.15) == ["built"]
    assert len(invoked) == 1
    d, L, xyz, root_type, density, sites = invoked[0]
    np.testing.assert_array_equal(d, [0.3, 0.2])
    np.testing.assert_array_equal(L, [2.0, 3.0])
    assert density == 0.15 and sites == [0]
    assert root_type is organ.root_type


@pytest.mark.parametrize(
    "sampled_sites",
    [
        [-1.0],
        [0.0],
        [10.0],
        [11.0],
        [np.nan],
        [np.inf],
        [[2.0]],
    ],
)
def test_prepare_branch_nodes_rejects_invalid_sites(organ, monkeypatch, sampled_sites):
    monkeypatch.setattr(organ, "_draw_lateral_count", lambda: 1)
    monkeypatch.setattr(mod, "sample_branch_sites", lambda **kw: sampled_sites)
    with pytest.raises(ValueError):
        organ._prepare_branch_nodes(
            np.array([0.2]), np.array([10.0]), np.array([[0.0, 0.0, -10.0]])
        )


def test_prepare_branch_nodes_retains_duplicate_site_once(organ, monkeypatch):
    monkeypatch.setattr(organ, "_draw_lateral_count", lambda: 2)
    monkeypatch.setattr(mod, "sample_branch_sites", lambda **kw: [3.0, 3.0])
    _, lengths, xyz, attachments = organ._prepare_branch_nodes(
        np.array([0.2]), np.array([10.0]), np.array([[0.0, 0.0, -10.0]])
    )
    np.testing.assert_allclose(lengths, [3.0, 7.0])
    np.testing.assert_allclose(xyz[:, 2], [-3.0, -10.0])
    assert attachments == [0]


def test_prepare_branch_nodes_no_sampled_sites_preserves_segments(organ, monkeypatch):
    monkeypatch.setattr(organ, "_draw_lateral_count", lambda: 2)
    monkeypatch.setattr(mod, "sample_branch_sites", lambda **kw: [])
    diameters = np.array([0.3, 0.2])
    lengths = np.array([4.0, 6.0])
    coordinates = np.array([[0.0, 0.0, -4.0], [0.0, 0.0, -10.0]])
    d, l, c, attachments = organ._prepare_branch_nodes(diameters, lengths, coordinates)
    np.testing.assert_array_equal(d, diameters)
    np.testing.assert_array_equal(l, lengths)
    np.testing.assert_array_equal(c, coordinates)
    assert attachments == []


def test_construct_root_from_parent_sets_secondary_type_and_inherits_density(
    organ, monkeypatch
):
    organ.parent_node = node(
        0.0, 0.0, -4.0, order=1, diameter=0.3, length=2.0, root_tissue_density=0.18
    )
    organ.fine_root_threshold = 0.05
    monkeypatch.setattr(organ, "init_diameters", lambda n, apex: np.array([0.2]))
    monkeypatch.setattr(organ, "init_lengths", lambda n: np.array([3.0]))
    monkeypatch.setattr(
        organ,
        "init_segment_coordinates",
        lambda n, lengths: np.array([[0.0, 0.0, -float(lengths[0])]]),
    )
    monkeypatch.setattr(
        organ, "_prepare_branch_nodes", lambda d, L, xyz: (d, L, xyz, [])
    )
    captured = []
    monkeypatch.setattr(
        organ,
        "_construct_segment_nodes",
        lambda *args: (captured.append(args) or ["lateral"]),
    )
    monkeypatch.setattr(mod, "RootTypeModel", lambda **kw: NS(**kw))
    monkeypatch.setattr(
        mod,
        "RootType",
        NS(
            STRUCTURAL=NS(value="structural"),
            FINE=NS(value="fine"),
            SECONDARY=NS(value="secondary"),
        ),
    )
    result = organ.construct_root_from_parent(1, 0.01)
    assert result == ["lateral"]
    d, l, xyz, root_type, density, sites = captured[0]
    np.testing.assert_allclose(d, [0.23])  # .2 + .3 * .1**1
    np.testing.assert_allclose(l, [3.2])  # 3.0 + 2.0 * .1**1
    assert density == pytest.approx(0.18)
    assert root_type.root_type == "structural"
    assert root_type.order_type == "secondary"
    assert sites == []
