"""Physical-scale, within-organ polyline diagnostics (coordinates in cm).

No smoothing, graph traversal, model imports, data loading, or fitting occurs.
Supply each root separately, including its attachment point but never its parent
direction. ``summarize_curvature`` accepts mappings with ``order``, ``points``
(N x 3), and optional ``organ_id``. Its JSON-compatible result retains per-organ
angles and equal-organ pooled distributions; order/scale/phase keys are strings
(``"2"``, ``"5"``, ``"0.5"``). ``compare_curvature`` accepts two such results.

Angles are between consecutive h-cm chords after *linear* arclength sampling.
Station zero is phase_fraction*h; each angle needs 2*h of observed support.
No short tail is appended or extrapolated. Endpoint roundoff within 16 machine
epsilons of total length is snapped to the measured endpoint. Near-zero turns mean <1 degree;
a run of n consecutive eligible turns advances n*h cm between chord starts.
This run measure is not the full (n+1)*h support of those overlapping turns.
Only eligible organs receive mass: every organ has weight 1/N, divided equally
over its angles. Weighted quantiles use the left inverse empirical CDF.
Each pooled result also retains ``location_pooled_statistics``: every eligible
angle receives equal mass there, with NumPy's linear median/quantile convention.
These location diagnostics do not affect equal-organ Wasserstein distances.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np
from scipy.stats import wasserstein_distance


def clean_polyline(points) -> np.ndarray:
    """Validate finite N x 3 coordinates and remove consecutive exact duplicates.

    Empty and singleton roots remain valid inputs with insufficient support.
    Nonconsecutive repeated coordinates (e.g. closed loops) are preserved.
    """
    xyz = np.asarray(points, dtype=float)
    if xyz.size == 0 and xyz.shape == (0,):
        return np.empty((0, 3), dtype=float)
    if xyz.ndim != 2 or xyz.shape[1] != 3:
        raise ValueError("points must have shape (N, 3)")
    if not np.isfinite(xyz).all():
        raise ValueError("points must contain only finite coordinates")
    if len(xyz) < 2:
        return xyz.copy()
    return xyz[np.r_[True, np.any(np.diff(xyz, axis=0) != 0, axis=1)]].copy()


def _positive(value, name):
    result = float(value)
    if not np.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return result


def _geometry(points):
    xyz = clean_polyline(points)
    segments = np.linalg.norm(np.diff(xyz, axis=0), axis=1)
    if not np.isfinite(segments).all() or np.any(segments <= 0):
        raise ValueError("segment lengths must be representable, finite and positive")
    arc = np.r_[0.0, np.cumsum(segments)]
    if not np.isfinite(arc).all():
        raise ValueError("total arc length must be finite")
    return xyz, arc


def _interpolate(xyz, arc, stations):
    stations = np.minimum(stations, arc[-1])
    return np.column_stack(
        [np.interp(stations, arc, xyz[:, axis]) for axis in range(3)]
    )


def _starts(length, support, step, offset=0.0):
    # Explicit support bound prevents np.interp's endpoint clamping from
    # manufacturing an angle or tangent beyond the measured polyline.
    tolerance = 16 * np.finfo(float).eps * max(length, support, offset)
    if offset + support > length + tolerance:
        return np.empty(0)
    count = int(np.floor((length - support - offset + tolerance) / step)) + 1
    starts = offset + np.arange(count) * step
    return starts[starts + support <= length + tolerance]


def _near_zero_runs(angles, eligible_indices, h):
    runs = []
    count, previous = 0, -2
    for angle, index in zip(angles, eligible_indices):
        if angle < 1.0:
            if index != previous + 1 and count:
                runs.append(count * h)
                count = 0
            count += 1
        elif count:
            runs.append(count * h)
            count = 0
        previous = index
    if count:
        runs.append(count * h)
    return runs


def turning_angles(points, h_cm, phase_fraction=0.0) -> dict:
    """Return h-scale turns in degrees, eligible stations and explicit exclusions.

    A zero spatial chord (possible on a returning curve) has undefined direction
    and is excluded, never assigned zero turning. ``phase_fraction`` is in [0,1).
    """
    h = _positive(h_cm, "h_cm")
    phase = float(phase_fraction)
    if not np.isfinite(phase) or not 0 <= phase < 1:
        raise ValueError("phase_fraction must be finite in [0, 1)")
    xyz, arc = _geometry(points)
    starts = _starts(arc[-1], 2 * h, h, phase * h)
    result = dict(
        h_cm=h,
        phase_fraction=phase,
        arc_length_cm=float(arc[-1]),
        angles_deg=[],
        centres_cm=[],
        eligible_count=0,
        supported_count=len(starts),
        excluded_zero_chord_count=0,
        near_zero_runs_cm=[],
        status="insufficient_support",
    )
    if not len(starts):
        return result
    a = _interpolate(xyz, arc, starts)
    b = _interpolate(xyz, arc, starts + h)
    c = _interpolate(xyz, arc, starts + 2 * h)
    first, second = b - a, c - b
    norms1, norms2 = np.linalg.norm(first, axis=1), np.linalg.norm(second, axis=1)
    eligible = (norms1 > 0) & (norms2 > 0)
    cosine = np.sum(
        (first[eligible] / norms1[eligible, None])
        * (second[eligible] / norms2[eligible, None]),
        axis=1,
    )
    # atan2 avoids spurious 1e-6-degree turns from acos cancellation at zero.
    cross = np.linalg.norm(
        np.cross(
            first[eligible] / norms1[eligible, None],
            second[eligible] / norms2[eligible, None],
        ),
        axis=1,
    )
    angles = np.degrees(np.arctan2(cross, np.clip(cosine, -1.0, 1.0)))
    result.update(
        angles_deg=angles.tolist(),
        centres_cm=(starts[eligible] + h).tolist(),
        eligible_count=len(angles),
        excluded_zero_chord_count=int((~eligible).sum()),
        near_zero_runs_cm=_near_zero_runs(angles, np.flatnonzero(eligible), h),
        status="ok" if len(angles) else "zero_length_chords",
    )
    return result


def tangent_correlation(points, separations_cm, station_step_cm=1.0) -> list[dict]:
    """Mean tangent dot products at physical arclength separations in cm.

    Tangents are forward chords of ``station_step_cm``. Pairs start at integer
    multiples of that step; the second chord starts exactly separation_cm later.
    No interpolation of directions and no extrapolation of coordinates occurs.
    """
    step = _positive(station_step_cm, "station_step_cm")
    xyz, arc = _geometry(points)
    result = []
    for separation in separations_cm:
        distance = _positive(separation, "separation_cm")
        starts = _starts(arc[-1], distance + step, step)
        record = dict(
            separation_cm=distance,
            station_step_cm=step,
            eligible_count=0,
            supported_count=len(starts),
            excluded_zero_chord_count=0,
            correlation=None,
            status="insufficient_support",
        )
        if len(starts):
            first = _interpolate(xyz, arc, starts + step) - _interpolate(
                xyz, arc, starts
            )
            second = _interpolate(xyz, arc, starts + distance + step) - _interpolate(
                xyz, arc, starts + distance
            )
            n1, n2 = np.linalg.norm(first, axis=1), np.linalg.norm(second, axis=1)
            eligible = (n1 > 0) & (n2 > 0)
            dots = np.sum(
                (first[eligible] / n1[eligible, None])
                * (second[eligible] / n2[eligible, None]),
                axis=1,
            )
            record.update(
                eligible_count=len(dots),
                excluded_zero_chord_count=int((~eligible).sum()),
                correlation=(
                    float(np.clip(dots, -1.0, 1.0).mean()) if len(dots) else None
                ),
                status="ok" if len(dots) else "zero_length_chords",
            )
        result.append(record)
    return result


def tortuosity(points) -> dict:
    """Arc/chord ratio; return None with status for zero-length or closed roots."""
    xyz, arc = _geometry(points)
    length = float(arc[-1])
    chord = float(np.linalg.norm(xyz[-1] - xyz[0])) if len(xyz) > 1 else 0.0
    status = "zero_length" if length == 0 else "zero_chord" if chord == 0 else "ok"
    return dict(
        status=status,
        value=length / chord if status == "ok" else None,
        arc_length_cm=length,
        chord_length_cm=chord,
    )


def _angle_statistics(values, weights=None):
    values = np.asarray(values, dtype=float)
    if not len(values):
        return dict(
            median_deg=None, p90_deg=None, fraction_gt45_deg=None, fraction_lt1_deg=None
        )
    mass = (
        np.ones(len(values)) / len(values) if weights is None else np.asarray(weights)
    )
    mass = mass / mass.sum()
    indices = np.argsort(values, kind="stable")
    ordered, cdf = values[indices], np.cumsum(mass[indices])

    def quantile(q):
        return float(ordered[min(np.searchsorted(cdf, q), len(ordered) - 1)])

    return dict(
        median_deg=quantile(0.5),
        p90_deg=quantile(0.9),
        fraction_gt45_deg=float(mass[values > 45].sum()),
        fraction_lt1_deg=float(mass[values < 1].sum()),
    )


def _location_pooled_statistics(values):
    values = np.asarray(values, dtype=float)
    return dict(
        angle_weighting="equal eligible location",
        quantile_method="numpy_linear",
        median_deg=float(np.median(values)) if len(values) else None,
        p90_deg=(
            float(np.quantile(values, 0.9, method="linear")) if len(values) else None
        ),
        fraction_gt45_deg=float(np.mean(values > 45.0)) if len(values) else None,
        fraction_lt1_deg=float(np.mean(values < 1.0)) if len(values) else None,
    )


def summarize_curvature(
    polylines: Iterable[Mapping], scales_cm=(2, 5, 10), phases=(0, 0.5)
) -> dict:
    """Summarize independent organs by order with equal-organ angle weights.

    Distinct plants must have distinct organ_id values if IDs are supplied;
    IDs are retained as metadata and are not merged. Duplicate IDs raise an
    error to catch accidental pooling of repeated roots.
    """
    scales = [_positive(h, "scale_cm") for h in scales_cm]
    phases = [float(phase) for phase in phases]
    if (
        not scales
        or not phases
        or len(set(scales)) != len(scales)
        or len(set(phases)) != len(phases)
    ):
        raise ValueError("scales and phases must be nonempty and unique")
    if any(not np.isfinite(p) or not 0 <= p < 1 for p in phases):
        raise ValueError("phases must be finite in [0, 1)")
    if len({format(h, "g") for h in scales}) != len(scales) or len(
        {format(p, "g") for p in phases}
    ) != len(phases):
        raise ValueError("scales and phases must have unique formatted keys")
    result = dict(
        scales_cm=scales,
        phases=phases,
        by_order={},
        angle_weighting="equal eligible organ, equal angle within organ",
        near_zero_run_definition="consecutive <1 degree turns times h_cm",
    )
    seen = set()
    for index, root in enumerate(polylines):
        order = root["order"]
        if (
            isinstance(order, (bool, np.bool_))
            or not np.isfinite(float(order))
            or float(order) != int(order)
            or int(order) < 1
        ):
            raise ValueError("order must be a positive integer")
        organ_id = str(root.get("organ_id", index))
        if organ_id in seen:
            raise ValueError("organ_id must be unique across supplied polylines")
        seen.add(organ_id)
        xyz = clean_polyline(root["points"])
        record = dict(
            organ_id=organ_id,
            tortuosity=tortuosity(xyz),
            turning={},
            tangent_correlation=tangent_correlation(xyz, scales),
        )
        for h in scales:
            record["turning"][format(h, "g")] = {}
            for phase in phases:
                turns = turning_angles(xyz, h, phase)
                turns.update(_angle_statistics(turns["angles_deg"]))
                record["turning"][format(h, "g")][format(phase, "g")] = turns
        group = result["by_order"].setdefault(
            str(int(order)), dict(per_organ=[], pooled={}, organ_count=0)
        )
        group["per_organ"].append(record)
        group["organ_count"] += 1
    for group in result["by_order"].values():
        for h in scales:
            hs = format(h, "g")
            group["pooled"][hs] = {}
            for phase in phases:
                ps = format(phase, "g")
                turns = [r["turning"][hs][ps] for r in group["per_organ"]]
                eligible = [r for r in turns if r["eligible_count"]]
                values, weights = [], []
                for root in eligible:
                    values.extend(root["angles_deg"])
                    weights.extend(
                        [1 / (len(eligible) * root["eligible_count"])]
                        * root["eligible_count"]
                    )
                group["pooled"][hs][ps] = dict(
                    **_angle_statistics(values, weights),
                    quantile_method="weighted_left_inverse_empirical_cdf",
                    location_pooled_statistics=_location_pooled_statistics(values),
                    angles_deg=values,
                    angle_weights=weights,
                    eligible_organ_count=len(eligible),
                    ineligible_organ_count=len(turns) - len(eligible),
                    eligible_count=len(values),
                    supported_count=sum(r["supported_count"] for r in turns),
                    excluded_zero_chord_count=sum(
                        r["excluded_zero_chord_count"] for r in turns
                    ),
                    near_zero_runs_cm=[
                        run for r in eligible for run in r["near_zero_runs_cm"]
                    ],
                )
    return result


def compare_curvature(observed: Mapping, generated: Mapping) -> dict:
    """1D Wasserstein distance in degrees per order, physical scale and phase.

    Eligibility is independent in each population. Missing organs/orders or
    unsupported scales yield status/None, never a distance of zero. This function
    does not declare a construction successful or infer biological validation.
    """
    if (
        observed["scales_cm"] != generated["scales_cm"]
        or observed["phases"] != generated["phases"]
    ):
        raise ValueError("observed and generated scales/phases must match")
    output = dict(
        by_order={},
        distance_units="degrees",
        angle_weighting=observed["angle_weighting"],
    )
    for order in sorted(
        set(observed["by_order"]) | set(generated["by_order"]), key=int
    ):
        output["by_order"][order] = {}
        for h in observed["scales_cm"]:
            hs = format(h, "g")
            output["by_order"][order][hs] = {}
            for phase in observed["phases"]:
                ps = format(phase, "g")
                populations = []
                for summary in (observed, generated):
                    group = summary["by_order"].get(order)
                    populations.append(group["pooled"][hs][ps] if group else {})
                obs, gen = populations
                ok = bool(obs.get("eligible_count", 0) and gen.get("eligible_count", 0))
                output["by_order"][order][hs][ps] = dict(
                    wasserstein_deg=(
                        float(
                            wasserstein_distance(
                                obs["angles_deg"],
                                gen["angles_deg"],
                                obs["angle_weights"],
                                gen["angle_weights"],
                            )
                        )
                        if ok
                        else None
                    ),
                    status="ok" if ok else "insufficient_support",
                    observed_eligible_organ_count=obs.get("eligible_organ_count", 0),
                    generated_eligible_organ_count=gen.get("eligible_organ_count", 0),
                    observed_angle_count=obs.get("eligible_count", 0),
                    generated_angle_count=gen.get("eligible_count", 0),
                )
    return output
