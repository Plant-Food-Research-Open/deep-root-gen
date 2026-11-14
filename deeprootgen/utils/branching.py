"""Utilities for sampling lateral-root branching locations."""

import numpy as np
from decimal import Decimal
from fractions import Fraction

MAX_PARENT2_BRANCH_SITES = 10000
PARENT2_DECIMAL_POLICY = "exact_rationals_of_str_binary64_v1"


def validate_parent2_branch_zone(zone):
    """Explicit finite positive numeric cm inputs; bools/strings are rejected."""
    if hasattr(zone, "model_dump"):
        zone = zone.model_dump()
    keys = {"basal_cm", "apical_cm", "spacing_cm"}
    if not isinstance(zone, dict) or set(zone) != keys:
        raise ValueError("Parent2 zone requires exactly basal_cm/apical_cm/spacing_cm")
    result = {}
    for key, value in zone.items():
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
            raise ValueError("Parent2 zone inputs must be explicit positive finite numbers")
        try:
            value = float(value)
        except (ValueError, OverflowError) as error:
            raise ValueError("Parent2 zone inputs must be finite") from error
        if not np.isfinite(value) or value <= 0:
            raise ValueError("Parent2 zone inputs must be explicit positive finite numbers")
        result[key] = value
    return result


def parent2_zone_sites(length_cm, basal_cm, apical_cm, spacing_cm):
    """Deterministic zone on CURRENT length, no tolerance band or truncation.

    Convert numeric inputs to binary64, then interpret their shortest roundtrip
    decimal spellings str(float(value)) as exact rationals. Count and sites use
    that exact arithmetic, so adjacent floats remain distinct. At most 10,000
    sites may be allocated; larger counts fail before allocation. Final sites
    must remain strictly interior/increasing when represented as binary64.
    """
    zone = validate_parent2_branch_zone(dict(basal_cm=basal_cm, apical_cm=apical_cm, spacing_cm=spacing_cm))
    if isinstance(length_cm, (bool, np.bool_)) or not isinstance(length_cm, (int, float, np.integer, np.floating)):
        raise ValueError("Current parent length must be positive and finite")
    try:
        length_cm = float(length_cm)
    except (ValueError, OverflowError) as error:
        raise ValueError("Current parent length must be positive and finite") from error
    if not np.isfinite(length_cm) or length_cm <= 0:
        raise ValueError("Current parent length must be positive and finite")
    length, basal, apical, spacing = [Fraction(Decimal(str(value)))
                                      for value in (length_cm, zone["basal_cm"], zone["apical_cm"], zone["spacing_cm"])]
    available = length - basal - apical
    count = 0 if available < 0 else 1 + available // spacing
    if count > MAX_PARENT2_BRANCH_SITES:
        raise ValueError("Parent2 zone exceeds the numerical allocation limit of 10000 sites")
    sites = [float(basal + index * spacing) for index in range(count)]
    if (any(not np.isfinite(site) or not 0 < site < length_cm for site in sites)
            or any(right <= left for left, right in zip(sites, sites[1:]))):
        raise ValueError("Parent2 zone sites are not strictly interior/increasing representable values")
    return sites


def sample_branch_sites(
    parent_xyz: np.ndarray,
    interbranch_distance: float,
    rng: np.random.Generator,
    floor_threshold: float = 0.4,
    ceiling_threshold: float = 0.9,
    max_branches: int | None = None,
    log_sd: float = 0.2,
) -> list[float]:
    """
    Sample lateral-root insertion positions along a parent root.

    Parameters
    ----------
    parent_xyz : np.ndarray
        Ordered 3D coordinates of the parent root, including
        its basal origin and apex, in centimetres.

    interbranch_distance : float
        Mean distance between successive lateral-root
        insertion positions, in centimetres.

    rng : np.random.Generator
        Random number generator.

    floor_threshold : float
        Fraction of parent-root length where branching begins.

    ceiling_threshold : float
        Fraction of parent-root length where branching ends.

    max_branches : int or None
        Maximum number of lateral branches. None means
        no explicit upper limit.

    log_sd : float
        Log-scale standard deviation of interbranch spacing.

    Returns
    -------
    list[float]
        Insertion positions measured in centimetres along
        the parent root's cumulative arc length.
    """

    xyz = np.asarray(parent_xyz, dtype=float)

    # --------------------------------------------------
    # Validate inputs
    # --------------------------------------------------

    if xyz.ndim != 2 or xyz.shape[1] != 3 or len(xyz) < 2:
        raise ValueError("parent_xyz must have shape (n_points >= 2, 3).")

    if not np.isfinite(xyz).all():
        raise ValueError("Parent coordinates must be finite.")

    if not np.isfinite(interbranch_distance) or interbranch_distance <= 0:
        raise ValueError("interbranch_distance must be positive and finite.")

    if not 0 <= floor_threshold < ceiling_threshold <= 1:
        raise ValueError("Expected 0 <= floor_threshold < ceiling_threshold <= 1.")

    if not np.isfinite(log_sd) or log_sd < 0:
        raise ValueError("log_sd must be finite and nonnegative.")

    if max_branches is not None:
        if not isinstance(max_branches, (int, np.integer)):
            raise TypeError("max_branches must be an integer.")

        if max_branches < 0:
            raise ValueError("max_branches must be nonnegative.")

        if max_branches == 0:
            return []

    # --------------------------------------------------
    # Calculate parent-root arc length
    # --------------------------------------------------

    segment_lengths = np.linalg.norm(
        np.diff(xyz, axis=0),
        axis=1,
    )

    if np.any(segment_lengths <= 1e-12):
        raise ValueError("Parent root contains zero-length segments.")

    total_length = float(segment_lengths.sum())

    # Eligible branching region.
    start = floor_threshold * total_length
    end = ceiling_threshold * total_length

    # --------------------------------------------------
    # Sample stochastic insertion positions
    # --------------------------------------------------

    sites = []

    # Randomise the initial branching position.
    position = start + rng.uniform(0.0, interbranch_distance)

    while position < end:

        sites.append(float(position))

        # Stop after reaching the branch-count cap.
        if max_branches is not None and len(sites) >= max_branches:
            break

        # Lognormal distribution with arithmetic mean
        # equal to interbranch_distance.
        spacing = interbranch_distance * rng.lognormal(
            mean=-0.5 * log_sd**2,
            sigma=log_sd,
        )

        position += spacing

    return sites


def redistribute_capped_sites(
    parent_xyz: np.ndarray,
    retained_count: int,
    floor_threshold: float = 0.4,
    ceiling_threshold: float = 0.9,
) -> list[float]:
    """Place a legacy-retained count at midpoint quantiles of its eligible window.

    Research assumption: retain n from the unchanged stochastic sampler, then
    use f*L+(j+.5)*(c-f)*L/n, j=0,...,n-1. L is the geometric parent contour
    length in cm. This pure function consumes no randomness and does not change
    the existing sampler. It does not preserve downstream daughter lengths:
    those use parent subsegment lengths in the unchanged construction formula.
    """
    xyz = np.asarray(parent_xyz, dtype=float)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or len(xyz) < 2:
        raise ValueError("parent_xyz must have shape (n_points >= 2, 3).")
    if not np.isfinite(xyz).all():
        raise ValueError("Parent coordinates must be finite.")
    if isinstance(retained_count, (bool, np.bool_)) or not isinstance(retained_count, (int, np.integer)):
        raise TypeError("retained_count must be an integer.")
    if retained_count < 0:
        raise ValueError("retained_count must be nonnegative.")
    if (not np.isfinite(floor_threshold) or not np.isfinite(ceiling_threshold)
            or not 0 <= floor_threshold < ceiling_threshold <= 1):
        raise ValueError("Expected finite 0 <= floor_threshold < ceiling_threshold <= 1.")
    lengths = np.linalg.norm(np.diff(xyz, axis=0), axis=1)
    if not np.isfinite(lengths).all() or np.any(lengths <= 1e-12):
        raise ValueError("Parent contains nonfinite or zero-length segments.")
    total_length = float(lengths.sum())
    if not np.isfinite(total_length):
        raise ValueError("Parent contour length must be finite.")
    if retained_count == 0:
        return []
    start, end = floor_threshold * total_length, ceiling_threshold * total_length
    sites = [float(start + (index + 0.5) * (end - start) / retained_count)
             for index in range(retained_count)]
    if (not np.isfinite(sites).all() or any(not 0 < site < total_length for site in sites)
            or any(not start < site < end for site in sites)
            or any(right <= left for left, right in zip(sites, sites[1:]))):
        raise ValueError("Redistributed sites must be finite, ordered and strictly interior.")
    return sites
