"""Tests for arc-length-based stochastic lateral insertion."""

from __future__ import annotations

import numpy as np
import pytest

from deeprootgen.utils.branching import sample_branch_sites


@pytest.fixture
def parent_polyline():
    # Length 30 cm, with a corner at 10 cm.
    return np.array([[0.0, 0.0, 0.0], [0.0, 0.0, -10.0], [20.0, 0.0, -10.0]])


def test_sites_lie_inside_eligible_arc_length_window(parent_polyline):
    sites = sample_branch_sites(
        parent_polyline,
        interbranch_distance=2.0,
        rng=np.random.default_rng(42),
        floor_threshold=0.25,
        ceiling_threshold=0.8,
    )
    assert sites
    assert all(7.5 <= position < 24 for position in sites)
    assert all(np.diff(sites) > 0)


def test_lateral_count_cap_is_enforced(parent_polyline):
    sites = sample_branch_sites(
        parent_polyline,
        interbranch_distance=0.5,
        rng=np.random.default_rng(1),
        max_branches=3,
    )
    assert len(sites) == 3


def test_max_branches_zero_is_empty(parent_polyline):
    assert (
        sample_branch_sites(
            parent_polyline, 2, np.random.default_rng(0), max_branches=0
        )
        == []
    )


def test_seed_reproducibility(parent_polyline):
    first = sample_branch_sites(parent_polyline, 2.0, np.random.default_rng(55))
    second = sample_branch_sites(parent_polyline, 2.0, np.random.default_rng(55))
    assert first == second


def test_different_random_seeds_change_sites(parent_polyline):
    a = sample_branch_sites(parent_polyline, 2.0, np.random.default_rng(42))
    b = sample_branch_sites(parent_polyline, 2.0, np.random.default_rng(43))
    assert a != b


def test_no_stochastic_interval_variation_when_log_sd_zero(parent_polyline):
    sites = sample_branch_sites(
        parent_polyline,
        1.5,
        np.random.default_rng(5),
        floor_threshold=0.2,
        ceiling_threshold=0.9,
        log_sd=0,
    )
    np.testing.assert_allclose(np.diff(sites), 1.5)


def test_threshold_window_can_exclude_every_branch():
    short = np.array([[0, 0, 0], [0, 0, -0.01]], dtype=float)
    sites = sample_branch_sites(
        short,
        interbranch_distance=5.0,
        rng=np.random.default_rng(4),
        floor_threshold=0.4,
        ceiling_threshold=0.5,
    )
    assert len(sites) <= 1


@pytest.mark.parametrize("distance", [-2.0, 0.0, np.inf, np.nan])
def test_bad_interbranch_distance_raises(parent_polyline, distance):
    with pytest.raises(ValueError, match="interbranch_distance"):
        sample_branch_sites(parent_polyline, distance, np.random.default_rng(5))


@pytest.mark.parametrize(
    "xyz",
    [
        np.array([0.0, 0.0, 0.0]),
        np.ones((1, 3)),
        np.ones((3, 2)),
        np.array([[0, 0, 0], [np.nan, 0, 1]]),
        np.zeros((2, 3)),
    ],
)
def test_bad_polyline_raises(xyz):
    with pytest.raises(ValueError, match="parent_xyz|zero-length|finite"):
        sample_branch_sites(xyz, 1.0, np.random.default_rng(3))


@pytest.mark.parametrize(
    "floor,ceiling",
    [
        (0.5, 0.5),
        (0.8, 0.2),
        (-0.1, 0.9),
        (0.0, 1.01),
    ],
)
def test_bad_eligibility_thresholds_raise(parent_polyline, floor, ceiling):
    with pytest.raises(ValueError, match="threshold"):
        sample_branch_sites(
            parent_polyline,
            1.0,
            np.random.default_rng(3),
            floor_threshold=floor,
            ceiling_threshold=ceiling,
        )


@pytest.mark.parametrize("sd", [-0.1, np.nan, np.inf])
def test_bad_log_sd_raises(parent_polyline, sd):
    with pytest.raises(ValueError, match="log_sd"):
        sample_branch_sites(parent_polyline, 1.0, np.random.default_rng(3), log_sd=sd)


def test_negative_branch_limit_raises(parent_polyline):
    with pytest.raises(ValueError, match="max_branches"):
        sample_branch_sites(
            parent_polyline, 1.0, np.random.default_rng(3), max_branches=-1
        )
