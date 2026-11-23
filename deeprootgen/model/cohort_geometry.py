"""Cohort geometry and exact taper primitives shared by native construction."""

import math
import numpy as np
from ..utils.tropism import _basis
from ..utils.primary_orientation import proper_rotation
from .curvature import ou_joint_step, spherical_exp_heading
from .row_alignment import ROW_AXIS, align_heading, check_alignment_step


def bounded_draw(spec, rng):
    """Bounded positive dimension; moments refer to the untruncated distribution."""
    mean, sd, lo, hi = (float(spec[k]) for k in ("mean", "sd", "min", "max"))
    if spec.get("law") == "truncated_normal":
        if not all(np.isfinite((mean, sd, lo, hi))) or not (0 < lo <= hi and sd >= 0):
            raise ValueError("Invalid truncated normal diameter support")
        if sd == 0:
            if lo <= mean <= hi:
                return mean
            raise ValueError("Fixed normal diameter is outside its support")
        z = sd * math.sqrt(2.)
        acceptance = .5 * (math.erf((hi - mean) / z) - math.erf((lo - mean) / z))
        if acceptance < .01:
            raise ValueError("Truncated normal diameter accepts less than one percent")
        for _ in range(10000):
            value = float(rng.normal(mean, sd))
            if lo <= value <= hi:
                return value
        raise ValueError("Truncated normal diameter exhausted its rejection budget")
    if not all(np.isfinite([mean, sd, lo, hi])) or not (
        0 < lo <= mean <= hi and sd >= 0
    ):
        raise ValueError("Invalid positive distribution")
    if sd == 0:
        return mean
    if lo == hi:
        raise ValueError("Nonzero SD needs a nonzero admissible interval")
    variance = math.log1p((sd / mean) ** 2)
    mu = math.log(mean) - variance / 2

    def cdf(x):
        return 0.5 * math.erfc(-(math.log(x) - mu) / math.sqrt(2 * variance))

    if cdf(hi) - cdf(lo) < 0.01:
        raise ValueError("Bounded distribution accepts less than one percent")
    for _ in range(10000):
        v = rng.lognormal(math.log(mean) - variance / 2, math.sqrt(variance))
        if lo <= v <= hi:
            return float(v)
    raise ValueError("Bounded distribution exhausted rejection budget")


def taper_diameter(s, length, base, tip, midpoint_fraction=0.5):
    mid = tip + (base - tip) * midpoint_fraction
    return np.interp(np.asarray(s), [0.0, length / 2, length], [base, mid, tip])


def material_cuts(
    length, stations, attachments, base, tip, cutoff, midpoint_fraction=0.5, *, minimum_interval_cm=1e-12
):
    cuts = [0.0, length, *stations, *attachments]
    if midpoint_fraction != 0.5:
        cuts.append(length / 2)
    mid = tip + (base - tip) * midpoint_fraction
    for a, b, da, db in [(0.0, length / 2, base, mid), (length / 2, length, mid, tip)]:
        if db < cutoff < da:
            cuts.append(a + (b - a) * (da - cutoff) / (da - db))
        elif cutoff == mid and tip < mid < base:
            cuts.append(length / 2)
    cuts = np.unique(np.asarray(cuts, float))
    if (
        not np.isfinite(cuts).all()
        or cuts[0] != 0
        or cuts[-1] != length
        or np.any(np.diff(cuts) <= minimum_interval_cm)
    ):
        raise ValueError("Unrepresentable or out-of-range material cuts")
    return cuts


def equivalent_diameter(a, b):
    return np.sqrt((a * a + a * b + b * b) / 3.0)


def integrate_curve(length, start, heading, step, q, ell, downward, rng, surface_z=0.0, *, row_alignment_per_cm=0.0, deep_carrier=None, carrier_receipt=None):
    """Integrate before inserting material/attachment nodes; z-positive up.

    ``surface_z`` is the declared soil surface of the caller's frame; the
    cohort frame keeps its historical surface at zero.
    """
    if not (np.isfinite(length) and length > 0 and np.isfinite(step) and step > 0):
        raise ValueError("Positive finite length/step required")
    start = np.array(start, dtype=float, copy=True)
    heading = np.array(heading, dtype=float, copy=True)
    if (
        start.shape != (3,)
        or heading.shape != (3,)
        or not np.isfinite(start).all()
        or not np.isfinite(heading).all()
        or start[2] > surface_z
        or np.linalg.norm(heading) <= 1e-12
    ):
        raise ValueError("Finite soil start and nonzero heading required")
    if not np.isfinite(downward) or downward < 0 or step * downward >= 1:
        raise ValueError("Require finite nonnegative drift with step*drift < 1")
    check_alignment_step(row_alignment_per_cm, step)
    stations = np.arange(0.0, length, step)
    if len(stations) > 1 and length - stations[-1] <= 64 * np.finfo(float).eps * max(
        length, step
    ):
        stations = stations[:-1]
    stations = np.r_[stations, length]
    points = [np.asarray(start, float)]
    heading /= np.linalg.norm(heading)
    frame = np.column_stack(_basis(heading))
    state = np.zeros(2)
    reflections = 0
    drift = downward
    trigger = None
    if deep_carrier is not None:
        trigger = surface_z - deep_carrier["trigger_depth_cm"]
        if carrier_receipt is not None:
            carrier_receipt.update(born_below=bool(start[2] <= trigger), crossed=False, strengthened=False)
    for h in np.diff(stations):
        state, turn = ou_joint_step(state, h, q, ell, rng)
        previous_heading = heading.copy()
        heading = spherical_exp_heading(frame, turn)
        heading = heading + h * drift * np.array([0.0, 0.0, -1.0])
        heading /= np.linalg.norm(heading)
        if row_alignment_per_cm:
            heading = align_heading(heading, ROW_AXIS, row_alignment_per_cm * h)
        if points[-1][2] + h * heading[2] > surface_z:
            heading[2] = -abs(heading[2])
            reflections += 1
            state = np.zeros(2)
        frame = proper_rotation(previous_heading, heading) @ frame
        points.append(points[-1] + h * heading)
        if trigger is not None and points[-2][2] > trigger >= points[-1][2]:
            if carrier_receipt is not None:
                carrier_receipt.update(crossed=True, strengthened=deep_carrier["selected"])
            if deep_carrier["selected"]:
                drift = downward * deep_carrier["drift_multiplier"]
            trigger = None
    return stations, np.asarray(points), reflections


def reconcile_interval_lengths(coords, stored, enabled=False):
    """Bounded metadata reconciliation; never moves geometry or cuts.

    Reject intervals below a 64-epsilon coordinate-scale resolution floor.
    Remaining strict failures are ValueError, not a caller-visible assertion.
    """
    coords = np.asarray(coords, float)
    result = np.asarray(stored, float).copy()
    if (
        type(enabled) is not bool
        or coords.shape != (len(result) + 1, 3)
        or not np.isfinite(coords).all()
        or not np.isfinite(result).all()
        or np.any(result <= 0)
    ):
        raise ValueError("Invalid interval geometry/metadata")
    actual = np.linalg.norm(np.diff(coords, axis=0), axis=1)
    eps = np.finfo(float).eps
    scale = np.linalg.norm(coords[:-1], axis=1) + np.linalg.norm(coords[1:], axis=1)
    floor = 64 * eps * scale
    if np.any(actual <= floor) or np.any(result <= floor):
        raise ValueError("Interval below coordinate-scale resolution floor")
    records = []
    for k in np.flatnonzero(~np.isclose(actual, result, rtol=1e-9, atol=0)):
        if not enabled:
            raise ValueError(
                f"Interval {k} fails strict geometric length; reconciliation disabled"
            )
        error = abs(actual[k] - result[k])
        guard = 64 * eps * (scale[k] + result[k])
        relative = error / min(actual[k], result[k])
        if error > guard:
            raise ValueError(f"Interval {k} exceeds absolute roundoff agreement guard")
        if relative > np.sqrt(eps):
            raise ValueError(f"Interval {k} exceeds relative roundoff agreement guard")
        records.append(
            dict(
                interval=int(k),
                before_cm=float(result[k]),
                after_cm=float(actual[k]),
                absolute_error_cm=float(error),
                relative_error=float(relative),
            )
        )
        result[k] = actual[k]
    np.testing.assert_allclose(actual, result, rtol=1e-9, atol=0)
    return result, records
