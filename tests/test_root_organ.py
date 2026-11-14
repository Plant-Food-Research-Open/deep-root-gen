"""Unit tests of the revised RootOrgan segment-subdivision implementation.

These call RootOrgan's isolated methods with a lightweight fake parameter
object. They do not run a complete root-system simulation or external services.
"""

from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace

import numpy as np
import pytest

from deeprootgen.model import RootSystemSimulation

# Discover the actual module instead of assuming root.py/root_system.py.
root_module = import_module(RootSystemSimulation.__module__)
RootOrgan = root_module.RootOrgan


@pytest.fixture
def organ(monkeypatch):
    p = SimpleNamespace(
        max_order=3,
        min_sec_root_num=2,
        max_sec_root_num=3,
        growth_sec_root=0.0,
        interbranch_distance=2.0,
        floor_threshold=0.1,
        ceiling_threshold=0.9,
        root_vary=0.0,
        min_primary_length=10,
        max_primary_length=10,
        min_sec_root_length=3,
        max_sec_root_length=3,
        length_reduction=0.7,
        base_diameter=0.5,
        diameter_reduction=0.2,
    )
    obj = object.__new__(RootOrgan)
    obj.input_parameters = p
    obj.parent_node = SimpleNamespace(node_data=SimpleNamespace(order=0))
    obj.rng = np.random.default_rng(42)
    obj.proot_length_interval = np.array([10.0, 10.0])
    obj.sroot_length_interval = np.array([3.0, 3.0])
    obj.length_reduction = 0.7
    return obj


def test_subdivide_at_known_arc_length_sites(organ, monkeypatch):
    monkeypatch.setattr(organ, "_draw_lateral_count", lambda: 2)
    monkeypatch.setattr(root_module, "sample_branch_sites", lambda **kwargs: [2.0, 8.0])
    diameters = np.array([0.3, 0.2])
    lengths = np.array([4.0, 6.0])
    coordinates = np.array([[0, 0, -4], [0, 0, -10]], dtype=float)
    d, l, xyz, attachment_indices = organ._prepare_branch_nodes(
        diameters, lengths, coordinates
    )
    np.testing.assert_allclose(l, [2.0, 2.0, 4.0, 2.0])
    np.testing.assert_allclose(d, [0.3, 0.3, 0.2, 0.2])
    np.testing.assert_allclose(xyz[:, 2], [-2, -4, -8, -10])
    assert attachment_indices == [0, 2]
    assert l.sum() == pytest.approx(lengths.sum())


def test_original_corner_attachment_does_not_create_zero_segment(organ, monkeypatch):
    monkeypatch.setattr(organ, "_draw_lateral_count", lambda: 1)
    monkeypatch.setattr(root_module, "sample_branch_sites", lambda **kwargs: [4.0])
    d, l, xyz, attachments = organ._prepare_branch_nodes(
        np.array([0.3, 0.2]),
        np.array([4.0, 6.0]),
        np.array([[0, 0, -4], [0, 0, -10]], dtype=float),
    )
    np.testing.assert_allclose(l, [4.0, 6.0])
    assert attachments == [0]


def test_no_laterals_returns_same_polyline(organ, monkeypatch):
    monkeypatch.setattr(organ, "_draw_lateral_count", lambda: 0)
    d = np.array([0.3, 0.2])
    L = np.array([4.0, 6.0])
    xyz = np.array([[0, 0, -4], [0, 0, -10]], dtype=float)
    d2, l2, xyz2, attachments = organ._prepare_branch_nodes(d, L, xyz)
    np.testing.assert_array_equal(d2, d)
    np.testing.assert_array_equal(l2, L)
    np.testing.assert_array_equal(xyz2, xyz)
    assert not attachments


def test_out_of_bounds_attachment_raises(organ, monkeypatch):
    monkeypatch.setattr(organ, "_draw_lateral_count", lambda: 1)
    monkeypatch.setattr(root_module, "sample_branch_sites", lambda **kwargs: [-1.0])
    with pytest.raises(ValueError, match="strictly inside"):
        organ._prepare_branch_nodes(
            np.array([0.2]), np.array([10.0]), np.array([[0, 0, -10]], dtype=float)
        )


def test_mismatched_nominal_and_geometric_lengths_raise(organ, monkeypatch):
    monkeypatch.setattr(organ, "_draw_lateral_count", lambda: 1)
    with pytest.raises(AssertionError):
        organ._prepare_branch_nodes(
            np.array([0.2]), np.array([10.0]), np.array([[0, 0, -5]], dtype=float)
        )


def test_terminal_order_requests_no_laterals(organ):
    organ.parent_node.node_data.order = 2
    assert organ._draw_lateral_count() == 0


def test_lateral_count_reproducible_for_fixed_seed(organ):
    a = organ._draw_lateral_count()
    organ.rng = np.random.default_rng(42)
    b = organ._draw_lateral_count()
    assert a == b
    assert a == 2


def test_initial_lengths_sum_to_valid_root_length(organ):
    result = organ.init_lengths(6)
    assert result.shape == (6,)
    assert result.sum() == pytest.approx(10.0)
    assert np.all(result > 0)


def test_diameters_are_sorted_decreasing(organ):
    obj = organ
    obj.base_diameter = 0.5
    result = obj.init_diameters(6, apex_diameter=0.05)
    assert len(result) == 6
    assert (np.diff(result) <= 0).all()
    assert (result >= 0.05).all()


def test_lateral_count_growth_factor(organ):
    organ.parent_node.node_data.order = 1
    organ.input_parameters.growth_sec_root = 0.5
    assert organ._draw_lateral_count() == 4


@pytest.mark.parametrize("growth", [-0.01, 1.0, 2.0])
def test_invalid_lateral_growth_factor_raises(organ, growth):
    organ.input_parameters.growth_sec_root = growth
    with pytest.raises(ValueError, match="growth_sec_root"):
        organ._draw_lateral_count()


def test_root_organ_reset_transform(organ):
    np.testing.assert_allclose(organ.reset_transform(), np.eye(4))


def test_root_organ_node_coordinate_and_property_access(organ):
    organ.segments = [
        SimpleNamespace(
            node_data=SimpleNamespace(x=0.0, y=0.0, z=-2.0, length=2.0, diameter=0.2)
        ),
        SimpleNamespace(
            node_data=SimpleNamespace(
                x=0.0, y=1.0, z=-3.0, length=np.sqrt(2), diameter=0.1
            )
        ),
    ]
    np.testing.assert_allclose(
        organ.get_coordinates(), [[0.0, 0.0, -2.0], [0.0, 1.0, -3.0]]
    )
    np.testing.assert_allclose(organ.get_lengths(), [2.0, np.sqrt(2)])
    np.testing.assert_allclose(organ.get_diameters(), [0.2, 0.1])
    np.testing.assert_allclose(organ.get_apex_coordinates(), [0.0, 1.0, -3.0])
    organ.set_coordinates([(1.0, 2.0, -3.0), (2.0, 3.0, -4.0)])
    np.testing.assert_allclose(organ.get_coordinates(), [[1, 2, -3], [2, 3, -4]])


def test_root_organ_calculate_mass(organ):
    organ.segments = [
        SimpleNamespace(node_data=SimpleNamespace(diameter=0.2, length=2.0)),
        SimpleNamespace(node_data=SimpleNamespace(diameter=0.1, length=4.0)),
    ]
    organ.input_parameters.root_tissue_density = 0.15
    expected = np.pi * ((0.2 / 2) ** 2 * 2.0 + (0.1 / 2) ** 2 * 4.0) * 0.15
    assert organ.calculate_mass() == pytest.approx(expected)


def test_set_invalid_root_marks_every_segment(organ):
    organ.segments = [
        SimpleNamespace(node_data=SimpleNamespace(invalid_root=False)),
        SimpleNamespace(node_data=SimpleNamespace(invalid_root=False)),
    ]
    organ.invalid_root = False
    organ.set_invalid_root()
    assert organ.invalid_root is True
    assert all(n.node_data.invalid_root for n in organ.segments)


def test_cascading_invalid_root_marks_child_organs(organ):
    organ.segments = [SimpleNamespace(node_data=SimpleNamespace(invalid_root=False))]
    organ.invalid_root = False
    child = object.__new__(RootOrgan)
    child.segments = [SimpleNamespace(node_data=SimpleNamespace(invalid_root=False))]
    child.invalid_root = False
    child.child_organs = []
    organ.child_organs = [child]
    organ.cascading_set_invalid_root()
    assert organ.invalid_root and child.invalid_root
    assert organ.segments[0].node_data.invalid_root
    assert child.segments[0].node_data.invalid_root


def test_transform_identity_round_trip(organ):
    organ.segments = [
        SimpleNamespace(node_data=SimpleNamespace(x=0.0, y=0.0, z=-2.0)),
        SimpleNamespace(node_data=SimpleNamespace(x=1.0, y=1.0, z=-3.0)),
    ]
    original = organ.get_coordinates().copy()
    organ.reset_transform()
    organ.transform()
    np.testing.assert_allclose(organ.get_coordinates(), original)
    np.testing.assert_allclose(organ.transform_matrix, np.eye(4))
