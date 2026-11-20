"""Training-tube interpolation and optional odds adjustments for root placement."""

import numpy as np
from scipy.special import logsumexp


def _finite(values, name):
    array = np.asarray(values)
    if array.dtype.kind not in "iuf":
        raise ValueError(f"{name} must contain real numbers")
    array = np.asarray(array, dtype=float)
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain finite values")
    return array


def _log_limit(value):
    limit = _finite(value, "max_log_ratio")
    if limit.ndim or limit < 0:
        raise ValueError("max_log_ratio must be a nonnegative scalar")
    return float(limit)


def _horizontal_kernel(query, origin, period, bandwidth):
    # Chord distance makes each axis periodic; averaging both signs gives reflection symmetry.
    x = np.remainder(query, period) / period
    x0 = np.remainder(origin, period) / period
    weight = np.zeros_like(x)
    for delta in (x - x0, x + x0):
        turns = delta - np.rint(delta)
        chord = (period / np.pi) * np.sin(np.pi * turns)
        with np.errstate(over="ignore"):
            weight += 0.5 * np.exp(-0.5 * np.square(chord / bandwidth))
    return weight


def relative_core_surface(
    tube_ids,
    xyz,
    rld,
    volumes,
    query_xyz,
    *,
    periods,
    bandwidth,
    depth_interval,
    pseudocount_fraction=0.1,
    max_log_ratio=2.0,
):
    """Return signed local-to-depth log RLD ratios at arbitrary query points.

    Supply only training sections. Each row of `xyz` gives cross-row position,
    along-row position and positive-down depth for one measured section. Each
    tube ID (text or integer) has a constant horizontal position. `rld` is
    nonnegative observed root length per sampled volume. `volumes` gives each
    section's positive sampled volume. Query coordinates may have shape
    `(..., 3)`; the result has the leading query shape.

    Both horizontal periods, the three kernel bandwidths and the closed depth
    interval share the coordinate length unit. Within each tube, a Gaussian
    depth kernel gives a sampled-volume-weighted RLD. Its total kernel weight,
    in units of the median sampled volume of that tube, caps at one. This same
    support weight enters the depth-only and horizontal estimates. One extra
    tube of depth-only weight shrinks the local estimate toward the layer mean.
    The pseudocount is a fraction of mean training RLD, giving each tube equal
    weight and each section its share of the tube's sampled volume.

    Points outside the declared interval receive a neutral zero contrast.
    Training sections must lie inside that interval. The caller owns all
    tube exclusions, bandwidth selection and subsequent probability updates.
    """
    train = _finite(xyz, "xyz")
    query = _finite(query_xyz, "query_xyz")
    if train.ndim != 2 or train.shape[1] != 3 or len(train) == 0:
        raise ValueError("xyz must contain one or more rows of three coordinates")
    if not query.ndim or query.shape[-1] != 3:
        raise ValueError("query_xyz must have final dimension three")
    values = _finite(rld, "rld")
    volume = _finite(volumes, "volumes")
    ids = np.asarray(tube_ids, dtype=object)
    if any(a.shape != (len(train),) for a in (ids, values, volume)):
        raise ValueError("tube_ids, rld and volumes must align with training rows")
    if np.any(values < 0) or np.any(volume <= 0):
        raise ValueError("RLD must be nonnegative and volumes positive")
    period = _finite(periods, "periods")
    width = _finite(bandwidth, "bandwidth")
    interval = _finite(depth_interval, "depth_interval")
    if (
        period.shape != (2,)
        or width.shape != (3,)
        or np.any(period <= 0)
        or np.any(width <= 0)
    ):
        raise ValueError(
            "two positive horizontal periods and three positive bandwidths are required"
        )
    if interval.shape != (2,) or not 0 <= interval[0] < interval[1]:
        raise ValueError("depth_interval must have nonnegative increasing bounds")
    if np.any((train[:, 2] < interval[0]) | (train[:, 2] > interval[1])):
        raise ValueError("training depths lie outside depth_interval")
    fraction = _finite(pseudocount_fraction, "pseudocount_fraction")
    if fraction.ndim or fraction <= 0:
        raise ValueError("pseudocount_fraction must be a positive scalar")
    limit = _log_limit(max_log_ratio)

    groups = {}
    for index, tube in enumerate(ids):
        if (
            isinstance(tube, (bool, np.bool_))
            or not isinstance(tube, (int, np.integer, str))
            or tube == ""
        ):
            raise ValueError("each tube ID must be nonempty text or an integer")
        groups.setdefault(tube, []).append(index)

    result = np.zeros(query.shape[:-1])
    inside = (query[..., 2] >= interval[0]) & (query[..., 2] <= interval[1])
    points = query[inside]
    depth_sum = np.zeros(len(points))
    depth_weight = np.zeros(len(points))
    local_sum = np.zeros(len(points))
    local_weight = np.zeros(len(points))
    # A common density scale cancels in the ratio, also for very small RLD units.
    maximum = values.max()
    scaled = values / maximum if maximum > 0 else values
    tube_log_means = []
    for rows in groups.values():
        tube = train[rows]
        origin = tube[0, :2]
        if not np.all(tube[:, :2] == origin):
            raise ValueError("each tube must have a single horizontal position")
        size = volume[rows]
        observed = scaled[rows]
        log_volume = np.log(size)
        with np.errstate(divide="ignore"):
            tube_log_means.append(
                logsumexp(log_volume + np.log(values[rows])) - logsumexp(log_volume)
            )
        ordered = np.sort(size)
        left, right = ordered[(len(size) - 1) // 2], ordered[len(size) // 2]
        median_volume = left + 0.5 * (right - left)
        with np.errstate(over="ignore"):
            dz = (points[:, 2, None] - tube[:, 2]) / width[2]
            log_weight = log_volume - np.log(median_volume) - 0.5 * dz**2
        total = logsumexp(log_weight, axis=1)
        normalizer = np.where(np.isfinite(total), total, 0.0)
        tube_rld = np.exp(log_weight - normalizer[:, None]) @ observed
        support = np.exp(np.minimum(total, 0.0))
        spatial = support.copy()
        for axis in range(2):
            spatial *= _horizontal_kernel(
                points[:, axis], origin[axis], period[axis], width[axis]
            )
        depth_sum += support * tube_rld
        depth_weight += support
        local_sum += spatial * tube_rld
        local_weight += spatial

    if maximum != values.min() and len(groups) > 1:
        depth = np.divide(
            depth_sum,
            depth_weight,
            out=np.zeros_like(depth_sum),
            where=depth_weight > 0,
        )
        local = (local_sum + depth) / (local_weight + 1.0)
        # Work in log units so a small positive pseudocount remains effective.
        log_pseudocount = (
            np.log(fraction)
            + logsumexp(tube_log_means)
            - np.log(len(groups))
            - np.log(maximum)
        )
        with np.errstate(divide="ignore"):
            contrast = np.logaddexp(np.log(local), log_pseudocount) - np.logaddexp(
                np.log(depth), log_pseudocount
            )
        result[inside] = np.clip(contrast, -limit, limit)
    return result


def compose_relative_surfaces(
    vine_log_ratio, auxiliary_log_ratio, coefficient, *, max_log_ratio=2.0
):
    """Add a supplied signed auxiliary term to the clipped vine log ratio.

    Inputs broadcast, so a depth-specific coefficient can vary across a grid.
    The combined log ratio is clipped to the same symmetric limit.
    """
    primary = _finite(vine_log_ratio, "vine_log_ratio")
    auxiliary = _finite(auxiliary_log_ratio, "auxiliary_log_ratio")
    slope = _finite(coefficient, "coefficient")
    limit = _log_limit(max_log_ratio)
    with np.errstate(over="ignore"):
        return np.clip(
            np.clip(primary, -limit, limit) + slope * auxiliary, -limit, limit
        )


def adjust_branching_odds(probability, log_ratio, strength=1.0):
    """Multiply prior odds by exp(strength * log_ratio), with NumPy broadcasting.

    Use a branching or retention probability as the prior. Structural zero and
    one probabilities remain exact. A zero contrast or strength also preserves
    the original probability exactly.
    """
    prior, contrast, factor = np.broadcast_arrays(
        _finite(probability, "probability"),
        _finite(log_ratio, "log_ratio"),
        _finite(strength, "strength"),
    )
    if np.any((prior < 0) | (prior > 1)):
        raise ValueError("probability must be between zero and one")
    active = (prior > 0) & (prior < 1) & (contrast != 0) & (factor != 0)
    updated = prior.copy()
    p = prior[active]
    with np.errstate(over="ignore"):
        log_odds = np.log(p) - np.log1p(-p) + contrast[active] * factor[active]
        updated[active] = np.exp(-np.logaddexp(0.0, -log_odds))
    return updated
