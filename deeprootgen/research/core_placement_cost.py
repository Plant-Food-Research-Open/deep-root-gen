"""Held-core placement loss for measured depth intervals and aligned RLD predictions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike


def _weighted_thickness(lower, upper, top30_weight):
    shallow = np.maximum(0.0, upper - np.maximum(lower, -30.0))
    return (upper - lower - shallow) + top30_weight * shallow


@dataclass(frozen=True)
class _DepthProjection:
    section: np.ndarray
    band: np.ndarray
    fraction: np.ndarray

    def shares_by_depth(self, section_shares):
        return np.bincount(
            self.band, weights=self.fraction * section_shares[self.section]
        )

    def gradient_by_section(self, depth_gradient):
        return np.bincount(
            self.section, weights=self.fraction * depth_gradient[self.band]
        )


def _depth_projection(
    frame: pd.DataFrame, top30_weight: float
) -> _DepthProjection:
    """Partition each increment across the union of all physical depth boundaries."""
    lower, upper = frame[["z_lower_cm", "z_upper_cm"]].to_numpy(dtype=float).T
    edges = np.unique(np.r_[lower, upper])
    starts, stops = np.searchsorted(edges, [lower, upper])
    counts = stops - starts
    section = np.repeat(np.arange(len(frame)), counts)
    # Enumerate each interval's consecutive elementary bands in row order.
    first = np.cumsum(counts) - counts
    band = starts[section] + np.arange(len(section)) - first[section]
    band_thickness = _weighted_thickness(edges[:-1], edges[1:], top30_weight)
    section_thickness = _weighted_thickness(lower, upper, top30_weight)
    fraction = band_thickness[band] / section_thickness[section]
    # Preserve first-seen band order, including the original aligned-grid sum.
    band, _ = pd.factorize(band)
    return _DepthProjection(section, band, fraction)


def _tube_weights(frame: pd.DataFrame, top30_weight: float) -> np.ndarray:
    """Give each tube equal total weight and each interval its effective volume."""
    keys = ["core_id", "z_lower_cm", "z_upper_cm"]
    if (
        frame.empty
        or frame["core_id"].isna().any()
        or frame.duplicated(keys).any()
    ):
        raise ValueError(
            "Each sample requires a unique tube and depth interval"
        )
    bounds = frame[["z_lower_cm", "z_upper_cm"]].to_numpy(dtype=float)
    lower, upper = bounds.T
    if (
        not np.isfinite(bounds).all()
        or np.any(upper <= lower)
        or np.any(upper > 0)
    ):
        raise ValueError(
            "Require finite z_lower_cm < z_upper_cm <= 0 (surface)"
        )
    volume = frame["core_volume_cm3"].to_numpy(dtype=float)
    if not np.isfinite(volume).all() or np.any(volume <= 0):
        raise ValueError("core_volume_cm3 must be finite and positive")

    tube_codes, tubes = pd.factorize(frame["core_id"])
    order = np.lexsort((lower, tube_codes))
    left, right = order[:-1], order[1:]
    if np.any(
        (tube_codes[left] == tube_codes[right]) & (upper[left] > lower[right])
    ):
        raise ValueError(
            "Sampled depth intervals overlap within a physical tube"
        )
    effective_volume = volume * (
        _weighted_thickness(lower, upper, top30_weight) / (upper - lower)
    )
    tube_totals = np.bincount(tube_codes, weights=effective_volume)
    return effective_volume / tube_totals[tube_codes] / len(tubes)


def _rld_vector(values: ArrayLike, size: int) -> np.ndarray:
    vector = np.asarray(values, dtype=float)
    if (
        vector.shape != (size,)
        or not np.isfinite(vector).all()
        or np.any(vector < 0)
    ):
        raise ValueError(
            "RLD must be an aligned vector of finite nonnegative values"
        )
    return vector


def score_core_placement(
    training: pd.DataFrame,
    held: pd.DataFrame,
    predictions: ArrayLike,
    *,
    top30_weight: float = 1.0,
    cap_multiple: float | None = None,
) -> dict[str, float | int | None]:
    """Score core RLD predictions in held row order with a training-only magnitude scale.

    Each frame must contain core_id (physical tube), z_lower_cm, z_upper_cm
    (below-ground coordinates with the surface at zero), core_volume_cm3 and
    rld_est. Within each tube the shallow fraction of each interval's volume
    receives top30_weight in (0, 1]. All tubes then carry equal weight.

    Only absolute residuals are optionally capped, at cap_multiple times the
    weighted training mean. A positive training mean is required. Both TVs use
    shares of the weighted, uncapped RLD. Depth TV apportions each increment
    uniformly by volume onto common depth bands, accounting for its shallow
    fraction. Overlapping increments in one tube are invalid. One empty profile versus one occupied
    profile has unit TV; two empty profiles have zero TV.
    """
    if not np.isfinite(top30_weight) or not 0 < top30_weight <= 1:
        raise ValueError("top30_weight must be finite and in (0, 1]")
    if cap_multiple is not None and (
        not np.isfinite(cap_multiple) or cap_multiple <= 0
    ):
        raise ValueError("cap_multiple must be finite and positive")
    training_rld = _rld_vector(training["rld_est"], len(training))
    training_mean = float(
        np.dot(_tube_weights(training, top30_weight), training_rld)
    )
    if training_mean <= 0:
        raise ValueError(
            "A positive training mean RLD is required for normalization"
        )

    weights = _tube_weights(held, top30_weight)
    observed = _rld_vector(held["rld_est"], len(held))
    if isinstance(predictions, pd.Series) and not predictions.index.equals(
        held.index
    ):
        raise ValueError(
            "Prediction Series index must match held rows in order"
        )
    predicted = _rld_vector(predictions, len(held))
    errors = np.abs(observed - predicted)
    cap = None if cap_multiple is None else float(cap_multiple * training_mean)
    clipped = 0 if cap is None else int(np.count_nonzero(errors > cap))
    uncapped_mae = float(np.dot(weights, errors))
    mae = (
        uncapped_mae
        if cap is None
        else float(np.dot(weights, np.minimum(errors, cap)))
    )
    normalized_mae = mae / training_mean

    observed_mass = weights * observed
    predicted_mass = weights * predicted
    observed_total, predicted_total = observed_mass.sum(), predicted_mass.sum()
    if min(observed_total, predicted_total) == 0:
        joint_tv = depth_tv = float(observed_total != predicted_total)
    else:
        difference = (
            observed_mass / observed_total - predicted_mass / predicted_total
        )
        joint_tv = float(0.5 * np.abs(difference).sum())
        # Marginalize the signed shares over tubes before taking absolute values.
        projection = _depth_projection(held, top30_weight)
        depth_tv = float(
            0.5 * np.abs(projection.shares_by_depth(difference)).sum()
        )

    return {
        "loss": 0.5 * normalized_mae + 0.25 * (joint_tv + depth_tv),
        "normalized_mae": normalized_mae,
        "weighted_mae": mae,
        "uncapped_weighted_mae": uncapped_mae,
        "joint_tv": joint_tv,
        "depth_tv": depth_tv,
        "training_mean_rld": training_mean,
        "cap_rld": cap,
        "clipped_count": clipped,
    }
