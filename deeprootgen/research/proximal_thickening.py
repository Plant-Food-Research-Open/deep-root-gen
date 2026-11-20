"""Opt-in secondary thickening of the coarse, proximal part of a native taper."""

from dataclasses import dataclass
from math import log

import numpy as np
from scipy.optimize import brentq


@dataclass
class ThickeningResult:
    """Updated native taper dictionaries and dry-mass accounting for one vine."""

    profiles: list[dict]
    added_mass_kg: np.ndarray
    capacity_kg: float
    fraction_of_headroom: float
    final_mass_kg: float
    shortfall_kg: float


def _proximal_mass(base, rate, length, breaks, density):
    """Integrate stepped dry density against a woody exponential diameter in cm."""
    def volume_before(station):
        return (np.pi / 4) * base**2 * (-np.expm1(-2 * rate * station)) / (2 * rate)

    grams = density[0] * volume_before(length)
    for diameter, increment in zip(breaks, np.diff(density)):
        if increment:
            crossing = np.clip((np.log(base) - np.log(diameter)) / rate, 0, length)
            grams += increment * volume_before(crossing)
    return grams / 1000


def _validate_limits(max_order, parent_cap_fraction, coarse_min_cm, max_base_factor, max_rate_factor,
                     starting_mass_kg, target_mass_kg):
    if max_order not in (0, 1, 2):
        raise ValueError("max_order must be 0, 1 or 2")
    if not np.isfinite([parent_cap_fraction, coarse_min_cm, max_base_factor, max_rate_factor]).all():
        raise ValueError("Thickening limits must be finite")
    if not 0 < parent_cap_fraction <= 1 or coarse_min_cm <= 0 or min(max_base_factor, max_rate_factor) < 1:
        raise ValueError("Invalid parent cap fraction, coarse cutoff or growth limits")
    if not np.isfinite([starting_mass_kg, target_mass_kg]).all() or min(starting_mass_kg, target_mass_kg) < 0:
        raise ValueError("Starting and target masses must be finite and nonnegative")


def _axis_dimensions(length_cm, root_order, n):
    length = np.asarray(length_cm, dtype=float)
    order = np.asarray(root_order, dtype=float)
    if length.shape != (n,) or not np.all(np.isfinite(length) & (length > 0)):
        raise ValueError("Supply one finite positive length per axis")
    if order.shape != (n,) or not np.all(np.isfinite(order) & (order >= 1) & (order == np.floor(order))):
        raise ValueError("Supply one positive integer order per axis")
    return length, order


def _density_law(density_bounds_cm, density_g_cm3):
    breaks = np.asarray(density_bounds_cm, dtype=float)
    density = np.asarray(density_g_cm3, dtype=float)
    if (breaks.ndim != 1 or density.shape != (breaks.size + 1,)
            or not np.all(np.isfinite(breaks) & (breaks > 0)) or np.any(np.diff(breaks) <= 0)
            or not np.all(np.isfinite(density) & (density > 0)) or np.any(np.diff(density) < 0)):
        raise ValueError("Require increasing positive diameter breaks and positive nondecreasing densities")
    return breaks, density


def _coarse_section(profile, length, order, max_order, coarse_min_cm):
    diameter, tip, midpoint = (float(profile[name]) for name in ("base", "tip", "midpoint"))
    if not np.isfinite([diameter, tip, midpoint]).all() or not (0 <= tip <= diameter and 0 <= midpoint <= 1):
        raise ValueError("Invalid native taper diameter or midpoint")
    if "rate_per_cm" not in profile:
        return None
    rate, transition = float(profile["rate_per_cm"]), float(profile["thick_min_cm"])
    if not np.isfinite([rate, transition]).all() or rate < 0 or not 0 < transition <= diameter:
        raise ValueError("Invalid native exponential taper")
    if order > max_order or rate == 0 or diameter <= coarse_min_cm or transition < coarse_min_cm:
        return None
    span = min(length, (log(diameter) - log(transition)) / rate)
    return (diameter, rate, span) if span > 0 else None


def _headroom(section, order, maximum_base, parent_site, parent_cap_fraction, max_base_factor, max_rate_factor):
    diameter, rate, span = section
    limit = maximum_base
    if not np.isfinite(limit) or limit <= 0:
        raise ValueError("Eligible axes require a finite positive maximum base diameter")
    if order == 2:
        if not np.isfinite(parent_site) or parent_site <= 0:
            raise ValueError("Eligible secondaries require the original parent diameter at insertion")
        limit = min(limit, parent_cap_fraction * parent_site)
    if diameter > limit + 1e-9:
        raise ValueError("An input base diameter already exceeds its applicable cap")
    room = min(np.log(limit / diameter), np.log(max_base_factor), (max_rate_factor - 1) * rate * span)
    return max(0., room)


def _preserve_endpoint(base, rate, transition, length, whole):
    # Native point_taper treats a join exactly at the tip as fully woody.
    # At that boundary one ulp can otherwise expose a fictitious thin tip.
    numerator = log(base) - log(transition)
    if (numerator / rate >= length) == whole:
        return rate
    rate = numerator / length
    direction = 0. if whole else np.inf
    while (numerator / rate >= length) != whole:
        rate = np.nextafter(rate, direction)
    return rate


def thicken_proximal_axes(
    profiles, length_cm, root_order, *, maximum_base_cm, parent_site_cm,
    parent_cap_fraction, coarse_min_cm, max_order, starting_mass_kg, target_mass_kg,
    density_bounds_cm, density_g_cm3, max_base_factor=1.5, max_rate_factor=2.0,
):
    """Add coarse dry tissue toward a minimum whole-vine mass on fixed geometry.

    Supply one native material dictionary, arc length and botanical order per
    axis. A native exponential taper uses `base`, `tip`, `midpoint`,
    `rate_per_cm` and `thick_min_cm`. A two-slope taper omits the last two.
    The caller supplies `maximum_base_cm` after maturity and allocation scaling,
    and `parent_site_cm` from the unchanged parent's taper at the actual
    insertion. These caps can be scalar or per-axis; a primary needs no parent
    value. Set `max_order` to 0 for the control, 1 for primaries, or 2 to
    include secondaries. Starting and target mass must use the same convention.

    Only an existing exponentially declining section with base above the
    coarse cutoff and transition diameter at or above it can grow. The new
    diameter is B exp(a) exp(−(k + a/J)s) up to its original join J. The
    original distal profile, centreline and parent insertion remain in place.
    A shorter axis uses its tip station for J. A common fraction of each
    axis's logarithmic headroom delivers the requested mass or uses the entire
    available capacity. Positive nondecreasing dry densities in g/cm³ apply
    between successive diameter breaks in cm. An empty break list gives a
    constant density. All updated profiles are copies.
    """
    result = [dict(profile) for profile in profiles]
    n = len(result)
    _validate_limits(max_order, parent_cap_fraction, coarse_min_cm, max_base_factor, max_rate_factor,
                     starting_mass_kg, target_mass_kg)
    length, order = _axis_dimensions(length_cm, root_order, n)
    breaks, density = _density_law(density_bounds_cm, density_g_cm3)
    max_base = np.broadcast_to(np.asarray(maximum_base_cm, dtype=float), (n,))
    parent = np.broadcast_to(np.asarray(parent_site_cm, dtype=float), (n,))
    selected, sections, headroom = [], [], []
    for i, profile in enumerate(result):
        section = _coarse_section(profile, length[i], order[i], max_order, coarse_min_cm)
        if section is None:
            continue
        selected.append(i)
        sections.append(section)
        headroom.append(_headroom(section, order[i], max_base[i], parent[i], parent_cap_fraction,
                                  max_base_factor, max_rate_factor))
    base, rate, join = np.asarray(sections).reshape(-1, 3).T
    headroom = np.asarray(headroom)
    original_mass = _proximal_mass(base, rate, join, breaks, density)

    def parameters(fraction):
        change = fraction * headroom
        return base * np.exp(change), rate + change / join

    def added_mass(fraction):
        new_base, new_rate = parameters(fraction)
        return _proximal_mass(new_base, new_rate, join, breaks, density) - original_mass

    capacity = float(added_mass(1.).sum())
    requested = max(0., target_mass_kg - starting_mass_kg)
    if requested <= 0 or capacity <= 0:
        fraction = 0.
    elif requested >= capacity:
        fraction = 1.
    else:
        fraction = brentq(lambda f: added_mass(f).sum() - requested, 0., 1., xtol=5e-15)

    new_base, new_rate = parameters(fraction)
    for j, i in enumerate(selected):
        if fraction * headroom[j] == 0:
            continue
        new_rate[j] = _preserve_endpoint(new_base[j], new_rate[j], result[i]["thick_min_cm"],
                                         length[i], join[j] == length[i])
        result[i].update(base=float(new_base[j]), rate_per_cm=float(new_rate[j]))
    increments = np.zeros(n)
    increments[selected] = _proximal_mass(new_base, new_rate, join, breaks, density) - original_mass
    final = float(starting_mass_kg + increments.sum())
    return ThickeningResult(result, increments, capacity, fraction, final, max(0., target_mass_kg - final))
