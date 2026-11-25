"""Analytic and invariance checks on artificial core sections."""

import numpy as np
import pytest

from deeprootgen.research.relative_core_surface import (
    adjust_branching_odds,
    compose_relative_surfaces,
    relative_core_surface,
)


def surface(**updates):
    # Two co-located sections in tube A give a volume-weighted six units of RLD.
    data = dict(
        tube_ids=["A", "A", "B"],
        xyz=[[0, 0, 1], [0, 0, 1], [4, 0, 1]],
        rld=[0, 8, 2],
        volumes=[1, 3, 2],
        query_xyz=[[0, 0, 1]],
        periods=[8, 10],
        bandwidth=[8 / (2 * np.pi), 2, 3],
        depth_interval=[0, 2],
    )
    data.update(updates)
    return relative_core_surface(**data)


def test_analytic_volume_weighting_tube_shrinkage_and_odds():
    opposite = np.exp(-2)
    depth = (6 + 2) / 2
    local = (6 + opposite * 2 + depth) / (1 + opposite + 1)
    expected = np.log((local + 0.1 * depth) / (depth + 0.1 * depth))
    np.testing.assert_allclose(surface(), [expected], rtol=1e-13)
    multiplier = np.exp(expected)
    new_p = 0.25 * multiplier / (0.75 + 0.25 * multiplier)
    np.testing.assert_allclose(adjust_branching_odds(0.25, surface()), [new_p])


def test_vertical_support_and_pseudocount_are_estimated_from_training_tubes():
    # At a depth of zero, the second tube is weakly supported by one distant section.
    a_weights = np.array([1.0, 3 * np.exp(-0.5)]) / 2
    a_mean = np.average([0, 8], weights=a_weights)
    b_weight = np.exp(-2.0)
    depth_mean = (a_mean + b_weight * 2) / (1 + b_weight)
    b_spatial = b_weight * np.exp(-2.0)
    spatial_mean = (depth_mean + a_mean + b_spatial * 2) / (2 + b_spatial)
    # Equal weight per tube for the pseudocount, including each tube's distant sections.
    pseudocount = 0.25 * (6 + 2) / 2
    observed = surface(
        xyz=[[0, 0, 0], [0, 0, 1], [4, 0, 2]],
        query_xyz=[0, 0, 0],
        bandwidth=[8 / (2 * np.pi), 2, 1],
        pseudocount_fraction=0.25,
    )
    np.testing.assert_allclose(
        observed, np.log((spatial_mean + pseudocount) / (depth_mean + pseudocount))
    )


def test_declared_depth_support_query_shape_and_neutral_fields():
    query = np.array([[[0, 0, -0.01], [0, 0, 0]], [[0, 0, 2], [0, 0, 2.01]]])
    result = surface(query_xyz=query)
    assert result.shape == (2, 2)
    assert result[0, 0] == result[1, 1] == 0
    assert result[0, 1] > 0 and result[1, 0] > 0
    assert surface(query_xyz=[0, 0, 1]).shape == ()
    assert surface(query_xyz=np.empty((0, 3))).shape == (0,)
    for constant in (0, 7):
        np.testing.assert_array_equal(
            surface(rld=[constant] * 3, query_xyz=query), np.zeros((2, 2))
        )
    assert (
        surface(tube_ids=["A"] * 3, xyz=[[2, 3, 0], [2, 3, 1], [2, 3, 2]]).item() == 0
    )
    assert surface(max_log_ratio=0).item() == 0
    assert surface(max_log_ratio=0.01).item() == 0.01


def test_periodic_both_reflections_and_units():
    coord = np.array([[-1, 1.5, 0.25], [-1, 1.5, 1], [2.3, -3.1, 2]])
    query = np.array([[0.75, 1.875, 0.3], [2.5, -3.2, 1.5]])
    baseline = surface(xyz=coord, query_xyz=query)
    for sign in ([1, -1, 1], [-1, 1, 1], [-1, -1, 1]):
        np.testing.assert_allclose(
            surface(xyz=coord, query_xyz=query * sign + [16, -30, 0]),
            baseline,
            atol=3e-15,
        )
        np.testing.assert_allclose(
            surface(xyz=coord * sign, query_xyz=query), baseline, atol=3e-15
        )
    np.testing.assert_allclose(
        surface(
            xyz=coord * 10,
            query_xyz=query * 10,
            periods=[80, 100],
            bandwidth=[80 / (2 * np.pi), 20, 30],
            depth_interval=[0, 20],
            volumes=[1000, 3000, 2000],
            rld=[0, 0.08, 0.02],
        ),
        baseline,
        atol=2e-15,
    )
    np.testing.assert_allclose(
        surface(
            xyz=coord[[2, 0, 1]],
            tube_ids=["B", "A", "A"],
            rld=[2, 0, 8],
            volumes=[2, 1, 3],
            query_xyz=query,
        ),
        baseline,
        atol=1e-15,
    )


def test_distinct_depth_support_and_far_query():
    depths = [[0, 0, 0], [0, 0, 0], [4, 0, 2]]
    # Near either end only the local tube contributes, so the depth and spatial estimates agree.
    result = surface(
        xyz=depths,
        query_xyz=[[0, 0, 0], [4, 0, 2], [0, 0, 1]],
        bandwidth=[1, 1, 1e-100],
    )
    np.testing.assert_allclose(result, np.zeros(3), atol=1e-15)


@pytest.mark.parametrize(
    "bad",
    [
        {"rld": [-1, 2, 3]},
        {"rld": [0, np.inf, 1]},
        {"volumes": [1, 0, 1]},
        {"volumes": [1, 2]},
        {"tube_ids": ["A", None, "B"]},
        {"tube_ids": [np.nan, 1, 2]},
        {"tube_ids": ["A", "", "B"]},
        {"xyz": [[0, 0, 1], [0, 1, 1], [0, 0, 2]]},
        {"xyz": [[0, 0, -1], [0, 0, 1], [4, 0, 1]]},
        {"query_xyz": [1, 2]},
        {"query_xyz": [[0, np.nan, 1]]},
        {"periods": [0, 4]},
        {"periods": [3]},
        {"bandwidth": [2, -1, 4]},
        {"bandwidth": [1, 2]},
        {"depth_interval": [2, 1]},
        {"depth_interval": [-1, 3]},
        {"pseudocount_fraction": 0},
        {"pseudocount_fraction": [0.1]},
        {"max_log_ratio": -1},
        {"rld": []},
        {"rld": [True, False, True]},
    ],
)
def test_invalid_training_and_query_inputs(bad):
    with pytest.raises(ValueError):
        surface(**bad)


def test_composed_relative_fields_broadcast_and_stable_probability_limits():
    base = np.array([[0.5], [3.0]])
    np.testing.assert_allclose(
        compose_relative_surfaces(base, [1.0, 0.5], [-1.0, 2.0]),
        [[-0.5, 1.5], [1.0, 2.0]],
    )
    p = np.array([[0], [0.2], [1]])
    out = adjust_branching_odds(p, np.log([4, 4]), [-1, 1])
    np.testing.assert_allclose(out, [[0, 0], [1 / 17, 0.5], [1, 1]])
    np.testing.assert_array_equal(adjust_branching_odds(p, 1e300, 0), p)
    np.testing.assert_array_equal(adjust_branching_odds(p, 0, -1e300), p)
    np.testing.assert_array_equal(
        adjust_branching_odds(0.4, [-1e308, 1e308], 10), [0, 1]
    )
    assert adjust_branching_odds(0.5, -720).item() > 0


@pytest.mark.parametrize(
    "fn,args",
    [
        (adjust_branching_odds, (1.01, 1)),
        (adjust_branching_odds, (-0.1, 1)),
        (adjust_branching_odds, (0.5, np.nan)),
        (adjust_branching_odds, (0.5, 1, np.inf)),
        (compose_relative_surfaces, (0, np.inf, 0)),
        (compose_relative_surfaces, ([1, 2], [1, 2, 3], 1)),
    ],
)
def test_invalid_log_odds_and_broadcast(fn, args):
    with pytest.raises(ValueError):
        fn(*args)
