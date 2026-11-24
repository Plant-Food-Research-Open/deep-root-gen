"""Synthetic tests for the opt-in two-budget terminal elongation design."""

import numpy as np
import pandas as pd
import pytest

from deeprootgen.research.terminal_elongation import (
    PARAMETERS,
    choose_exchange,
    elongation_design,
    exchange_scales,
    mass_matched_triplets,
)


def test_independent_budgets_and_a_bound_on_each_side():
    assay = np.array([1.0, 2.0, 1.0])
    structural = np.array([2.0, 1.0, 1.0])
    scales = exchange_scales(assay, structural, [0.9, 0.1, 0.1], [2., 2., 1.5])
    np.testing.assert_allclose(scales, [
        [1, 1, 1],
        [0.9, 0.9, 1.3],
        [1 + 0.8 / 3, 1 + 0.8 / 3, 0.2],
    ])
    for mass in (assay, structural):
        np.testing.assert_allclose(scales @ mass, mass.sum())
    np.testing.assert_array_equal(assay, [1, 2, 1])


def test_batched_proportional_budgets_and_frozen_member():
    assay = np.array([[1., 3., 2.], [3., 1., 2.]])
    structural = 2 * assay
    scale = exchange_scales(assay, structural, 0.5, [[1, 1.5, 2], [2, 3, 1.4]])
    np.testing.assert_array_equal(scale[1, 0], np.ones(3))
    np.testing.assert_array_equal(scale[:, :, 2], np.ones((3, 2)))
    np.testing.assert_allclose((scale * assay).sum(axis=-1), np.full((3, 2), 6.))
    np.testing.assert_allclose((scale * structural).sum(axis=-1), np.full((3, 2), 12.))
    assert (scale[2, 0] != 1).any() and (scale[1, 1] != 1).any()


@pytest.mark.parametrize("mass,structural,low,high", [
    ([0, 1, 2], [1, 1, 1], 0, 2),
    ([1, 1], [1, 1], 0, 2),
    ([1, 1, 1], [1, np.nan, 1], 0, 2),
    ([1, 1, 1], [1, 1, 1], 1.01, 2),
    ([1, 1, 1], [1, 1, 1], 0, 0.99),
])
def test_invalid_budgets_or_domain(mass, structural, low, high):
    with pytest.raises(ValueError):
        exchange_scales(mass, structural, low, high)


def test_matching_keeps_mass_blocks_and_leaves_only_incomplete_triplet():
    mass = np.arange(77, 0, -1)
    marks = np.random.default_rng(3).uniform(size=77)
    idx = mass_matched_triplets(mass, marks)
    np.testing.assert_array_equal(idx, mass_matched_triplets(mass, marks))
    assert idx.shape == (25, 3)
    assert len(np.unique(idx)) == 75
    assert (mass[idx[:24]] <= 72).all()
    assert (mass[idx[-1]] > 72).all()
    assert mass_matched_triplets([], []).shape == (0, 3)


def test_design_and_synthetic_application():
    design = elongation_design()
    pd.testing.assert_frame_equal(design, elongation_design())
    assert design.index.name == "design_id"
    assert list(design.columns) == ["family", *PARAMETERS]
    assert len(design) == 5000
    np.testing.assert_array_equal(design.family, np.repeat([0, 1], 2500))
    params = design.loc[:, PARAMETERS].to_numpy()
    np.testing.assert_array_equal(params[:2500], params[2500:])
    np.testing.assert_array_equal(params[0], [-1000, 0, 0, 0, 0, 0, 0, 0])
    np.testing.assert_array_equal(params[1], np.zeros(8))
    lower = [-4, -3, -3, -3, -3, -3, -3, -3]
    bins = np.floor((params[5:2500] - lower) / 6 * 2495).astype(int)
    for column in bins.T:
        np.testing.assert_array_equal(np.sort(column), np.arange(2495))

    # Three triplets use common marks. Equal odds give three different states.
    changes = np.zeros((2, 3, 7))
    marks = np.array([[0.8, 0.2, 0.1], [0.2, 0.8, 0.2], [0.1, 0.1, 0.9]])
    np.testing.assert_array_equal(choose_exchange(params[0], changes, marks), [0, 0, 0])
    np.testing.assert_array_equal(choose_exchange(params[1], changes, marks), [0, 1, 2])
    # Equal marks isolate the two opposite responses to the predefined surface coefficient.
    changes[:, :, -1] = [[1, -1, 0], [-1, 1, 0]]
    np.testing.assert_array_equal(choose_exchange(params[4], changes, np.full((3, 3), 0.5)), [1, 2, 0])


def test_remaining_degrees_of_freedom_zero_budget_and_small_independent_budget():
    assay = np.array([1., 1., 1.])
    all_zero = exchange_scales(assay, np.zeros(3), 0, 2)
    np.testing.assert_array_equal(all_zero[:, 2], np.ones(3))
    # Tiny independent budgets remain independent of the assay budget.
    small = np.array([1., 2., 4.]) * 1.e-16
    scales = exchange_scales(assay, small, 0, 2)
    np.testing.assert_allclose(scales @ small, small.sum(), atol=0., rtol=1e-14)
    assert scales[1, 2] != 1
    assert exchange_scales(np.empty((0, 3)), np.empty((0, 3)), 0, 2).shape == (3, 0, 3)
