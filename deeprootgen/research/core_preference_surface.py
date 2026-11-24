"""Fit a vineyard placement preference from training-core signed deficits."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


def _sample_weights(
    frame: pd.DataFrame, weight_column: str | None
) -> np.ndarray:
    if frame.empty or frame["core_id"].isna().any():
        raise ValueError("Training rows require physical core IDs")
    weights = (
        np.ones(len(frame))
        if weight_column is None
        else frame[weight_column].to_numpy(dtype=float)
    )
    if (
        not np.isfinite(weights).all()
        or np.any(weights < 0)
        or not np.any(weights > 0)
    ):
        raise ValueError(
            "Sample weights must be finite, nonnegative and contain positive support"
        )
    tubes, _ = pd.factorize(frame["core_id"])
    totals = np.bincount(tubes, weights=weights)
    tube_totals = totals[tubes]
    within_tube = np.divide(
        weights, tube_totals, out=np.zeros_like(weights), where=tube_totals > 0
    )
    return within_tube / np.count_nonzero(totals)


def _horizontal_subspace(
    weighted_depth: np.ndarray, weighted_horizontal: np.ndarray
) -> np.ndarray:
    """Keep only contrasts distinguishable from the depth-only fit on these tubes."""
    depth_projection = np.linalg.lstsq(
        weighted_depth, weighted_horizontal, rcond=None
    )[0]
    contrasts = weighted_horizontal - weighted_depth @ depth_projection
    _, singular_values, directions = np.linalg.svd(
        contrasts, full_matrices=False
    )
    # Reference the original design scale, including when all contrasts cancel.
    tolerance = (
        np.finfo(float).eps
        * max(contrasts.shape)
        * np.linalg.norm(weighted_depth)
    )
    return directions[singular_values > tolerance].T


def fit_core_preference_surface(
    training: pd.DataFrame,
    *,
    across_period_cm: float,
    along_period_cm: float,
    mode: str = "all",
    depth_knots_cm: Sequence[float] = (15, 45, 75, 105, 135),
    horizontal_penalty: float = 0.02,
    depth_penalty: float = 0.05,
    fade_cm: float = 30.0,
    weight_column: str | None = None,
    target_column: str = "target",
) -> dict:
    """Return a native vineyard_3d_v1 profile fit exclusively to supplied rows.

    Positive target values in [-1, 1] request more recruitment. Depth is cm
    below soil, cross_cm and along_cm are crown-relative, and core_id identifies
    each physical tube. The caller supplies any normalization of the signed
    deficit and the two planting periods. Each positive-weight tube contributes
    equally; optional weights distribute its contribution among its samples.

    Linear depth hats multiply [1, cos(cross phase), cos(along phase), product].
    The cosine terms assume reflection symmetry about the crown axes. The fit
    minimizes weighted squared error plus horizontal_penalty times the sum of
    squared horizontal coefficients and depth_penalty times the sum of squared
    adjacent-knot differences for all four coefficient series. Exact horizontal
    contrasts that the sampled geometry cannot resolve are set to zero. The
    depth_only mode fixes all horizontal coefficients to zero.

    Fitting uses the linear predictor with endpoint fading. The native
    evaluator additionally bounds preferences to [-1, 1] before fading.
    """
    knots = np.asarray(depth_knots_cm, dtype=float)
    if (
        knots.ndim != 1
        or len(knots) < 2
        or not np.isfinite(knots).all()
        or knots[0] < 0
        or np.any(np.diff(knots) <= 0)
    ):
        raise ValueError(
            "Depth knots must be finite, increasing nonnegative depths"
        )
    controls = [
        across_period_cm,
        along_period_cm,
        fade_cm,
        horizontal_penalty,
        depth_penalty,
    ]
    if not np.isfinite(controls).all() or np.any(np.asarray(controls) <= 0):
        raise ValueError(
            "Periods, fade and penalties must be finite and positive"
        )
    if mode not in ("depth_only", "all"):
        raise ValueError("mode must be depth_only or all")
    weights = _sample_weights(training, weight_column)
    target = training[target_column].to_numpy(dtype=float)
    depth = training["depth_cm"].to_numpy(dtype=float)
    if not np.isfinite(target).all() or np.any(np.abs(target) > 1):
        raise ValueError("Training target must be finite and in [-1, 1]")
    if not np.isfinite(depth).all() or np.any(depth < 0):
        raise ValueError("depth_cm must be finite and nonnegative")

    knot_count = len(knots)
    hats = np.column_stack(
        [np.interp(depth, knots, row) for row in np.eye(knot_count)]
    )
    outside = np.maximum(np.maximum(knots[0] - depth, depth - knots[-1]), 0)
    fade = np.clip(1 - outside / fade_cm, 0, 1)
    weighted_depth = hats * (fade * np.sqrt(weights))[:, None]
    if not np.any(weighted_depth):
        raise ValueError(
            "Training has no positive-weight samples inside the profile support"
        )

    if mode == "depth_only":
        weighted_horizontal = np.zeros((len(training), 3 * knot_count))
        directions = np.empty((3 * knot_count, 0))
    else:
        coordinates = training[["cross_cm", "along_cm"]].to_numpy(dtype=float)
        if not np.isfinite(coordinates).all():
            raise ValueError("Horizontal coordinates must be finite")
        periods = np.array([across_period_cm, along_period_cm])
        phases = np.remainder(coordinates, periods) / periods
        cross, along = np.cos(2 * np.pi * phases).T
        features = np.column_stack([cross, along, cross * along])
        weighted_horizontal = (
            weighted_depth[:, :, None] * features[:, None, :]
        ).reshape(len(training), -1)
        directions = _horizontal_subspace(weighted_depth, weighted_horizontal)

    # Map free parameters into the native knot-by-four coefficient table.
    free_count = knot_count + directions.shape[1]
    native_map = np.zeros((knot_count, 4, free_count))
    native_map[:, 0, :knot_count] = np.eye(knot_count)
    native_map[:, 1:, knot_count:] = directions.reshape(
        knot_count, 3, directions.shape[1]
    )
    design = np.column_stack(
        [weighted_depth, weighted_horizontal @ directions]
    )
    horizontal_rows = np.sqrt(horizontal_penalty) * native_map[
        :, 1:, :
    ].reshape(-1, free_count)
    difference_rows = np.sqrt(depth_penalty) * np.diff(
        native_map, axis=0
    ).reshape(-1, free_count)
    system = np.vstack([design, horizontal_rows, difference_rows])
    responses = np.r_[
        np.sqrt(weights) * target,
        np.zeros(len(horizontal_rows) + len(difference_rows)),
    ]
    fitted = np.linalg.lstsq(system, responses, rcond=None)[0]
    return {
        "version": "vineyard_3d_v1",
        "depth_knots_cm": knots.tolist(),
        "coefficients": (native_map @ fitted).tolist(),
        "across_period_cm": float(across_period_cm),
        "along_period_cm": float(along_period_cm),
        "fade_cm": float(fade_cm),
    }
