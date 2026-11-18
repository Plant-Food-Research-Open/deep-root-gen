"""Physical point diameters and exact squared-diameter integrals on an axis."""

import math

import numpy as np

from .cohort_geometry import equivalent_diameter, material_cuts, taper_diameter


def thick_end(profile, length):
    """Arc where the exponential piece ends, including a wholly thick axis."""
    rate = profile["rate_per_cm"]
    if rate == 0:
        return length
    return min(length, (math.log(profile["base"]) - math.log(profile["thick_min_cm"])) / rate)


def _thin_tip(profile):
    return min(profile["tip"], profile["thick_min_cm"])


def point_diameter(arcs, length, profile):
    """Evaluate the final profile after applying size and parent-diameter limits."""
    base, tip, midpoint = (profile[key] for key in ("base", "tip", "midpoint"))
    if "rate_per_cm" not in profile:
        return taper_diameter(arcs, length, base, tip, midpoint)
    arcs = np.asarray(arcs, dtype=float)
    join = thick_end(profile, length)
    if join == length:
        return base * np.exp(-profile["rate_per_cm"] * arcs)
    thin = taper_diameter(
        arcs - join, length - join, profile["thick_min_cm"], _thin_tip(profile), midpoint,
    )
    thick = base * np.exp(-profile["rate_per_cm"] * np.minimum(arcs, join))
    return np.where(arcs < join, thick, thin)


def profile_cuts(length, profile, cutoff_cm):
    """Interior cuts at material-law changes and the reporting cutoff."""
    base, tip, midpoint = (profile[key] for key in ("base", "tip", "midpoint"))
    if "rate_per_cm" not in profile:
        return material_cuts(length, [], [], base, tip, cutoff_cm, midpoint, minimum_interval_cm=0.)[1:-1]
    join = thick_end(profile, length)
    parts = []
    rate = profile["rate_per_cm"]
    if rate > 0 and point_diameter(join, length, profile) < cutoff_cm < base:
        crossing = (math.log(base) - math.log(cutoff_cm)) / rate
        if 0. < crossing < join:
            parts.append(crossing)
    if 0. < join < length:
        parts.append(join)
    if join < length:
        tail = material_cuts(
            length - join, [], [], profile["thick_min_cm"], _thin_tip(profile),
            cutoff_cm, midpoint, minimum_interval_cm=0.,
        )
        parts.extend(join + tail[1:-1])
    return np.unique(parts)


def exponential_mean_square(start_diameter, rate_times_length):
    """Mean d² on an exponential interval, with the constant-diameter limit."""
    exponent = -2. * np.asarray(rate_times_length, dtype=float)
    factor = np.divide(np.expm1(exponent), exponent, out=np.ones_like(exponent), where=exponent != 0.)
    return np.asarray(start_diameter)**2 * factor


def exponential_profile_integral(starts, ends, length, profile):
    """Integrate d² ds, even if one exported interval straddles a material join."""
    join = thick_end(profile, length)
    rate = profile["rate_per_cm"]
    a, b = np.minimum(starts, join), np.minimum(ends, join)
    widths = b - a
    result = widths * exponential_mean_square(profile["base"] * np.exp(-rate * a), rate * widths)
    if join < length:
        # The thin part retains the two slopes of the existing taper.
        mid = (length + join) / 2.
        for lo, hi in ((join, mid), (mid, length)):
            left = np.clip(starts, lo, hi)
            right = np.clip(ends, lo, hi)
            da = point_diameter(left, length, profile)
            db = point_diameter(right, length, profile)
            result += (right - left) * equivalent_diameter(da, db)**2
    return result
