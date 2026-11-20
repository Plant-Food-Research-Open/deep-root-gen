"""Opt-in physical primary-only branch window for supplied topology.

Sites are n midpoint quantiles of [start_cm,end_cm] on the existing primary
contour. This consumes no RNG, changes no quota and preserves the original
primary curve and each incoming-cylinder diameter/density interval. It is a
construction input, not a pure transport of an already constructed tree.

Daughter CURRENT lengths are retained by the mandatory keyed CDF2..max route.
Daughter diameters still inherit the diameter at the new attachment cylinder;
this changes diameter/length covariance and can change mass. Native Fichtl
geometry still depends on graph subdivision and its shared proposal RNG.
"""

import numpy as np

from .order_controls import validate_order_scope

FIELD = "research_primary_branch_zone_cm"
VERSION = "drg-primary-physical-branch-zone-v1"


def _number(value, label):
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, float, np.integer, np.floating)
    ):
        raise ValueError(f"{label} must be a finite nonbool number")
    try:
        value = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{label} must be finite") from error
    if not np.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def validate_primary_branch_zone(zone):
    """Accept exactly start/end cm; inactive None preserves historical behavior."""
    if zone is None:
        return None
    if hasattr(zone, "model_dump"):
        zone = zone.model_dump()
    if not isinstance(zone, dict) or set(zone) != {"start_cm", "end_cm"}:
        raise ValueError("Primary branch zone requires exactly start_cm/end_cm")
    result = {key: _number(value, key) for key, value in zone.items()}
    if not 0 < result["start_cm"] < result["end_cm"]:
        raise ValueError("Primary branch zone requires 0 < start_cm < end_cm")
    return result


def validate_primary_branch_zone_scope(parameters, constructor_seed=None):
    """Native static max3..5, explicit primaries and count/CDF-conditioned lengths."""
    get = (
        parameters.get
        if isinstance(parameters, dict)
        else lambda key, default=None: getattr(parameters, key, default)
    )
    zone = validate_primary_branch_zone(get(FIELD))
    if zone is None:
        return None
    if (
        get("tropism_mode") != "fichtl2024"
        or get("max_order") not in (3, 4, 5)
        or get("t") != 0
        or get("research_current_length_grid") is not None
        or get("research_primary_design") is None
        or get("research_root_counts_by_order") is None
    ):
        raise ValueError(
            "Primary branch zone requires native static Fichtl/max3..5/explicit primary design/count-conditioned CDF lengths"
        )
    validate_order_scope(parameters, constructor_seed)
    entries = get("research_primary_design")
    if not isinstance(entries, list) or not entries:
        raise ValueError(
            "Primary branch zone requires nonempty explicit primary lengths"
        )
    for entry in entries:
        entry = entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)
        length = _number(entry.get("length_cm"), "Primary length_cm")
        if length <= zone["end_cm"]:
            raise ValueError(
                "Each explicit primary length must exceed primary branch-zone end_cm"
            )
    return zone


def primary_branch_zone_sites(length_cm, retained_count, zone):
    """Return exact supplied-count midpoint sites, rejecting unrepresentable cuts."""
    zone = validate_primary_branch_zone(zone)
    if zone is None:
        raise ValueError("Primary branch-zone sites require an active zone")
    length = _number(length_cm, "Primary length_cm")
    if length <= zone["end_cm"]:
        raise ValueError("Primary length must exceed branch-zone end_cm")
    if (
        isinstance(retained_count, (bool, np.bool_))
        or not isinstance(retained_count, (int, np.integer))
        or retained_count < 0
    ):
        raise ValueError("Primary branch quota must be a nonnegative integer")
    start, end = zone["start_cm"], zone["end_cm"]
    sites = [
        float(start + (index + 0.5) * (end - start) / retained_count)
        for index in range(retained_count)
    ]
    if (
        not np.isfinite(sites).all()
        or any(not start < site < end for site in sites)
        or any(right <= left for left, right in zip(sites, sites[1:]))
    ):
        raise ValueError(
            "Primary branch-zone sites must be representable, strictly interior and increasing"
        )
    return sites
