"""Analytic fixtures for scoring held synthetic core intervals."""

import numpy as np
import pandas as pd
import pytest

from deeprootgen.research.core_placement_cost import score_core_placement


def _frame(rows):
    return pd.DataFrame(
        rows,
        columns=[
            "core_id",
            "z_lower_cm",
            "z_upper_cm",
            "core_volume_cm3",
            "rld_est",
        ],
    )


def test_shallow_partial_interval_volume_normalized_within_each_tube():
    # A's effective volumes at weight 0.5 are 1 and 4.5; B has a single sample.
    training = _frame(
        [("A", -15, 0, 2, 11), ("A", -45, -15, 6, 0), ("B", -15, 0, 100, 8)]
    )
    held = training.assign(rld_est=[0, 11, 0])
    score = score_core_placement(training, held, [0, 0, 0], top30_weight=0.5)
    assert score["training_mean_rld"] == pytest.approx(5)
    assert score["weighted_mae"] == pytest.approx(4.5)
    assert score["normalized_mae"] == pytest.approx(0.9)
    assert score["loss"] == pytest.approx(0.95)
    assert score["joint_tv"] == score["depth_tv"] == 1


def test_joint_and_depth_tv_separate_tubes_and_use_weighted_rld():
    frame = _frame(
        [
            ("A", -30, 0, 1, 1),
            ("A", -60, -30, 2, 0),
            ("B", -30, 0, 1, 0),
            ("B", -60, -30, 2, 1),
        ]
    )
    swap_tubes = score_core_placement(
        frame, frame, [0, 1, 1, 0], top30_weight=0.5
    )
    assert swap_tubes["joint_tv"] == pytest.approx(1)
    assert swap_tubes["depth_tv"] == pytest.approx(0)
    shallow_only = score_core_placement(
        frame, frame, [1, 0, 0, 0], top30_weight=0.5
    )
    assert (
        shallow_only["depth_tv"]
        == shallow_only["joint_tv"]
        == pytest.approx(0.8)
    )


def test_training_scaled_symmetric_cap_only_affects_magnitude():
    training = _frame([("T", -30, 0, 5, 2)])
    held = _frame(
        [("A", -30, 0, 50, 10), ("B", -60, -30, 5, 2), ("C", -30, 0, 1, 0)]
    )
    predictions = [0, 4, 10]
    full = score_core_placement(training, held, predictions)
    capped = score_core_placement(training, held, predictions, cap_multiple=1)
    assert full["cap_rld"] is None and full["clipped_count"] == 0
    assert capped["cap_rld"] == 2 and capped["clipped_count"] == 2
    assert (
        capped["uncapped_weighted_mae"]
        == full["weighted_mae"]
        == pytest.approx(22 / 3)
    )
    assert capped["weighted_mae"] == pytest.approx(2)
    assert capped["joint_tv"] == full["joint_tv"] == pytest.approx(5 / 6)
    assert (
        capped["depth_tv"] == full["depth_tv"] == pytest.approx(2 / 7 - 1 / 6)
    )
    assert capped["loss"] == pytest.approx(
        0.5 + 0.25 * (5 / 6 + 2 / 7 - 1 / 6)
    )


@pytest.mark.parametrize(
    ("observed", "predicted", "tv"), [(0, 0, 0), (0, 2, 1), (2, 0, 1)]
)
def test_zero_profile_conventions(observed, predicted, tv):
    training = _frame([("T", -30, 0, 5, 2)])
    held = training.assign(rld_est=observed)
    score = score_core_placement(training, held, [predicted])
    assert score["joint_tv"] == score["depth_tv"] == tv
    assert score["loss"] == pytest.approx(
        0.25 * abs(observed - predicted) + 0.5 * tv
    )


@pytest.mark.parametrize(
    "kwargs", [{"cap_multiple": 0}, {"top30_weight": 0}, {"top30_weight": 1.5}]
)
def test_invalid_weight_or_cap(kwargs):
    frame = _frame([("A", -30, 0, 1, 1)])
    with pytest.raises(ValueError):
        score_core_placement(frame, frame, [0], **kwargs)


def test_invalid_support_normalization_and_alignment():
    frame = _frame([("A", -30, 0, 1, 1)])
    with pytest.raises(ValueError, match="positive training mean"):
        score_core_placement(frame.assign(rld_est=0), frame, [0])
    with pytest.raises(ValueError, match="unique tube"):
        score_core_placement(frame, pd.concat([frame, frame]), [1, 1])
    with pytest.raises(ValueError, match="index"):
        score_core_placement(frame, frame, pd.Series([1], index=[1]))
    with pytest.raises(ValueError, match="finite nonnegative"):
        score_core_placement(frame, frame, [np.nan])


def test_depth_distribution_matches_across_different_section_boundaries():
    frame = _frame(
        [("A", -30, 0, 30, 1), ("B", -15, 0, 15, 0), ("B", -30, -15, 15, 0)]
    )
    score = score_core_placement(frame, frame, [0, 1, 1])
    assert score["joint_tv"] == 1 and score["depth_tv"] == 0


def test_straddling_measurement_distributes_root_length_by_weighted_thickness():
    frame = _frame(
        [("A", -60, 0, 60, 1), ("B", -45, 0, 45, 0), ("B", -60, -45, 15, 0)]
    )
    equal = score_core_placement(frame, frame, [0, 1, 1], top30_weight=0.25)
    assert equal["depth_tv"] == pytest.approx(0)
    upper_only = score_core_placement(
        frame, frame, [0, 1, 0], top30_weight=0.25
    )
    assert upper_only["depth_tv"] == pytest.approx(15 / (30 + 0.25 * 30))


def test_depth_tv_matches_original_interval_grouping_on_aligned_grids():
    frame = _frame(
        [
            ("B", -60, -30, 10, 0.3),
            ("A", -30, 0, 3, 1.5),
            ("A", -60, -30, 7, 0.7),
            ("B", -30, 0, 2, 0.4),
        ]
    )
    prediction = np.array([1.0, 0.2, 1.0, 0.8])
    score = score_core_placement(frame, frame, prediction, top30_weight=0.25)
    volume = frame.core_volume_cm3 * np.where(frame.z_lower_cm >= -30, 0.25, 1)
    weights = volume / volume.groupby(frame.core_id).transform("sum") / 2
    observed = weights * frame.rld_est
    predicted = weights * prediction
    diff = observed / observed.sum() - predicted / predicted.sum()
    original = (
        0.5
        * diff.groupby([frame.z_lower_cm, frame.z_upper_cm], sort=False)
        .sum()
        .abs()
        .sum()
    )
    assert score["depth_tv"] == pytest.approx(original, abs=1e-15)


@pytest.mark.parametrize("which", ["training", "held"])
def test_reject_overlapping_increments_even_in_unsorted_tube(which):
    valid = _frame([("A", -30, 0, 1, 1)])
    overlap = _frame(
        [("A", -15, 0, 1, 1), ("B", -30, 0, 1, 1), ("A", -30, -10, 1, 1)]
    )
    training, held = (
        (overlap, valid) if which == "training" else (valid, overlap)
    )
    with pytest.raises(ValueError, match="overlap within a physical tube"):
        score_core_placement(training, held, np.ones(len(held)))
