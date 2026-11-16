"""Opt-in supplied primary arc fractions, independent of observation data.

Each primary receives exactly one daughter per supplied fraction f at s=f*L.
The original primary curve/material intervals survive subdivision. Site placement
consumes no randomness. Later parent orders retain their global branch window.
Mandatory keyed CDFs preserve daughter CURRENT lengths, but inherited diameter
still depends on the attachment cylinder; native Fichtl proposals still depend
on graph subdivision/shared RNG. This is a construction assumption, not fitting,
posthoc subtree relocation or a biological validation.
"""

import numpy as np

from .order_controls import validate_order_scope

FIELD = "research_primary_branch_fractions"
VERSION = "drg-primary-supplied-arc-fractions-v1"


def _number(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, float, np.integer, np.floating)
    ):
        raise ValueError(f"{name} must be a finite nonbool number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{name} must be finite") from error
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def validate_primary_branch_fractions(values):
    """Require a nonempty strictly increasing explicit list, with 0 < f < 1."""
    if values is None:
        return None
    if not isinstance(values, list) or not values:
        raise ValueError("Primary branch fractions require a nonempty explicit list")
    fractions = [_number(value, "Primary branch fraction") for value in values]
    if any(not 0 < value < 1 for value in fractions) or any(
        right <= left for left, right in zip(fractions, fractions[1:])
    ):
        raise ValueError(
            "Primary branch fractions must be strictly increasing within (0,1)"
        )
    return fractions


def validate_primary_branch_fractions_scope(parameters, constructor_seed=None):
    """Native static max3..5, soil0, explicit primary design and count/CDF route."""
    get = (
        parameters.get
        if isinstance(parameters, dict)
        else lambda key, default=None: getattr(parameters, key, default)
    )
    fractions = validate_primary_branch_fractions(get(FIELD))
    if fractions is None:
        return None
    if (
        get("tropism_mode") != "fichtl2024"
        or get("max_order") not in (3, 4, 5)
        or get("t") != 0
        or get("soil_surface_z_cm") != 0.0
        or get("research_current_length_grid") is not None
        or get("research_primary_design") is None
        or get("research_root_counts_by_order") is None
    ):
        raise ValueError(
            "Primary fractions require native static Fichtl/max3..5/soil0/explicit primary design/count-conditioned CDF lengths"
        )
    if get("research_primary_branch_zone_cm") is not None:
        raise ValueError(
            "Primary fractions cannot combine with an absolute primary branch zone"
        )
    counts = validate_order_scope(parameters, constructor_seed)
    if counts[2] != counts[1] * len(fractions):
        raise ValueError(
            "Primary fractions require count2 = count1 * number of fractions"
        )
    return fractions


def primary_fraction_sites(length_cm, retained_count, fractions):
    """Return f*L sites for the exact quota; no sampling or endpoint snapping."""
    values = validate_primary_branch_fractions(fractions)
    if values is None:
        raise ValueError("Primary fraction sites require active fractions")
    length = _number(length_cm, "Primary length_cm")
    if length <= 0:
        raise ValueError("Primary length_cm must be positive")
    if (
        isinstance(retained_count, (bool, np.bool_))
        or not isinstance(retained_count, (int, np.integer))
        or retained_count != len(values)
    ):
        raise ValueError(
            "Each primary quota must equal the number of supplied fractions"
        )
    sites = [float(value * length) for value in values]
    if (
        not np.isfinite(sites).all()
        or any(not 0 < value < length for value in sites)
        or any(right <= left for left, right in zip(sites, sites[1:]))
    ):
        raise ValueError(
            "Primary fraction sites must be representable, interior and strictly increasing"
        )
    return sites
