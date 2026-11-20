import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from deeprootgen.research.lateral_orientation import (
    ANGLES_DEG, PARAMETERS, lateral_orientation_design, roll_options, roll_probabilities,
)


def test_design_crosses_backgrounds_with_identical_seeded_controls_and_draws():
    design = lateral_orientation_design()
    assert len(design) == 5000
    assert not design.duplicated().any()
    np.testing.assert_array_equal(design, lateral_orientation_design())
    blocks = list(design.groupby(["scaffold", "order"], sort=False))
    assert [k for k, _ in blocks] == [(0, 2), (0, 3), (1, 2), (1, 3)]
    for _, rows in blocks:
        np.testing.assert_array_equal(rows[list(PARAMETERS)], blocks[0][1][list(PARAMETERS)])
        assert (rows.iloc[10::5].surface == 0).all()
        assert rows.iloc[10:].turn.between(-4, 2).all()
    assert not np.array_equal(design, lateral_orientation_design(seed=12))


def test_attached_subtree_matches_independent_rotation_and_preserves_join_and_angle():
    anchor = np.array([3., -2., -10.])
    tangent = np.array([2., -3., -4.])
    points = anchor + [[0, 0, 0], [1, -2, 1], [2, -3, -1], [1, -2, 1], [0, 1, 1]]
    curves, legal = roll_options(points, anchor, tangent)
    assert legal.all()
    np.testing.assert_array_equal(curves[0], points)
    axis = tangent / np.linalg.norm(tangent)
    for angle, xyz in zip(ANGLES_DEG, curves):
        expected = Rotation.from_rotvec(np.deg2rad(angle) * axis).apply(points - anchor) + anchor
        np.testing.assert_allclose(xyz, expected, atol=1e-12)
        np.testing.assert_array_equal(xyz[0], anchor)
        np.testing.assert_array_equal(xyz[1], xyz[3])
        np.testing.assert_allclose((xyz[1] - anchor) @ axis, (points[1] - anchor) @ axis)


def test_aboveground_descendant_masks_entire_subtree():
    points = [[0, 0, -1], [1, 0, -1], [2, 0, -3], [2, 0, -5]]
    curves, legal = roll_options(points, points[0], [1, 0, 0])
    np.testing.assert_array_equal(legal, [True, True, True, False, False, False])
    assert curves[-1, -1, 2] == 3
    probs = roll_probabilities(np.zeros(8), 0, np.zeros((6, 5)), legal)
    np.testing.assert_allclose(probs, np.array([5, 1, 1, 0, 0, 0]) / 7)


def test_generic_and_informed_probabilities_use_relative_odds():
    delta = np.zeros((6, 5))
    delta[2, -1] = np.log(2.)
    coefficients = np.zeros(8)
    valid = np.ones(6, dtype=bool)
    generic = roll_probabilities(coefficients, 0, delta, valid)
    np.testing.assert_allclose(generic, [.5, .1, .1, .1, .1, .1])
    coefficients[-1] = 1
    informed = roll_probabilities(coefficients, 0, delta, valid)
    np.testing.assert_allclose(informed[2] / informed[0], 2 * generic[2] / generic[0])
    coefficients[0] = -1000
    np.testing.assert_array_equal(roll_probabilities(coefficients, 1, delta, valid), [1, 0, 0, 0, 0, 0])


@pytest.mark.parametrize("points,tangent", [
    ([], [1, 0, 0]), ([[1, 2, 3]], [1, 0, 0]),
    ([[0, 0, -1]], [0, 0, 0]), ([[np.nan, 0, 0]], [1, 0, 0]),
])
def test_invalid_geometry(points, tangent):
    with pytest.raises(ValueError):
        roll_options(points, [0, 0, -1], tangent)
