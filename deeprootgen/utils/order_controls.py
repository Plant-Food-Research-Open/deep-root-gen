"""Explicit research assumptions for higher orders and supplied population counts.

These are topology conditioning inputs, not inferred counts or paper coefficients.
Inactive controls neither draw randomness nor add provenance.
"""

import hashlib

import numpy as np

HIGHER_FIELD = "research_higher_order_tropism"
COUNTS_FIELD = "research_root_counts_by_order"
QUOTA_VERSION = "drg-count-conditioned-topology-v1"


def _order_map(mapping, allowed, label):
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError(f"{label} requires a nonempty explicit mapping")
    result = {}
    for key, value in mapping.items():
        if (
            isinstance(key, (bool, np.bool_))
            or not isinstance(key, (int, np.integer, str))
            or str(key) not in {str(order) for order in allowed}
            or int(key) in result
        ):
            raise ValueError(f"{label} has unsupported or duplicate order keys")
        result[int(key)] = value
    return result


def validate_higher_order_tropism(mapping, max_order=5):
    if mapping is None:
        return None
    result = _order_map(mapping, range(4, max_order + 1), "Higher-order tropism")
    fields = {"theta_deg", "theta_sd_deg", "probability_down", "trials"}
    for order, entry in result.items():
        if not isinstance(entry, dict) or set(entry) != fields:
            raise ValueError(
                "Higher-order tropism requires exactly theta_deg/theta_sd_deg/probability_down/trials"
            )
        result[order] = {}
        for key, value in entry.items():
            if (
                isinstance(value, (bool, np.bool_))
                or not isinstance(value, (int, float, np.integer, np.floating))
                or value < 0
            ):
                raise ValueError(
                    "Higher-order tropism values must be explicit finite nonbool nonnegative numbers"
                )
            try:
                value = float(value)
            except (OverflowError, ValueError) as error:
                raise ValueError(
                    "Higher-order tropism values must be finite"
                ) from error
            if not np.isfinite(value):
                raise ValueError("Higher-order tropism values must be finite")
            limit = {"theta_deg": 90, "probability_down": 1, "trials": 100}.get(key)
            if limit is not None and value > limit:
                raise ValueError(f"Higher-order {key} exceeds {limit}")
            result[order][key] = float(value)
    return result


def direction_controls(settings, order):
    get = (
        settings.get
        if isinstance(settings, dict)
        else lambda key, default=None: getattr(settings, key, default)
    )
    if order in (2, 3):
        return dict(
            theta_deg=get(f"fichtl_theta{order}_deg"),
            theta_sd_deg=get(f"fichtl_theta{order}_sd_deg"),
            probability_down=get("fichtl_probability_down") if order == 2 else 1.0,
            trials=get(f"fichtl_trials_type{order}"),
        )
    mapping = validate_higher_order_tropism(get(HIGHER_FIELD), get("max_order", 5))
    if order not in (4, 5) or mapping is None or order not in mapping:
        raise ValueError(
            "Orders 4/5 require explicit research higher-order tropism assumptions"
        )
    return mapping[order]


def validate_count_mapping(mapping, max_order=5):
    if mapping is None:
        return None
    result = _order_map(mapping, range(1, max_order + 1), "Root counts")
    for value in result.values():
        if (
            isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, np.integer))
            or value <= 0
        ):
            raise ValueError("Root counts must be explicit positive nonbool integers")
    return {key: int(value) for key, value in result.items()}


def validate_order_scope(parameters, constructor_seed=None):
    get = (
        parameters.get
        if isinstance(parameters, dict)
        else lambda key, default=None: getattr(parameters, key, default)
    )
    maximum = get("max_order", 3)
    if not get("canonical_generation", False):
        higher = validate_higher_order_tropism(get(HIGHER_FIELD))
        expects_higher = get("tropism_mode") == "fichtl2024" and maximum > 3
        if (higher is not None or expects_higher) and (
            not expects_higher or maximum not in (4, 5)
            or higher is None or set(higher) != set(range(4, maximum + 1))
        ):
            raise ValueError(
                "Fichtl orders4/5 require exactly the explicit higher-order entries4..max"
            )
    counts = validate_count_mapping(get(COUNTS_FIELD))
    if counts is None:
        return None
    seed = get("random_seed")
    cdfs = get("research_current_length_cdfs_cm")
    if (
        maximum not in (3, 4, 5)
        or set(counts) != set(range(1, maximum + 1))
        or counts[1] != get("inner_root_num") + get("outer_root_num")
        or get("tropism_mode") != "fichtl2024"
        or not isinstance(cdfs, dict)
        or set(cdfs) != set(range(2, maximum + 1))
    ):
        raise ValueError(
            "Count conditioning requires Fichtl/max3..5/exact counts1..max/CDFs2..max and matching primary total"
        )
    if (
        isinstance(seed, (bool, np.bool_))
        or not isinstance(seed, (int, np.integer))
        or seed < 0
        or (
            constructor_seed is not None
            and (
                isinstance(constructor_seed, (bool, np.bool_))
                or not isinstance(constructor_seed, (int, np.integer))
                or constructor_seed != seed
            )
        )
    ):
        raise ValueError(
            "Count conditioning requires matching explicit nonnegative integer seeds"
        )
    if (
        get("research_parent2_branch_zone_cm") is not None
        or get("research_tertiary_length_rank_strength")
        or get("research_primary_attachment_distal_fraction")
    ):
        raise ValueError(
            "Count conditioning composition with parent2 zone/rank/distal controls is unsupported"
        )
    return counts


def plan_child_quotas(seed, child_order, nparents, nchildren):
    """Balanced quotas; separate keyed stream excludes arm and parent/node IDs."""
    if (
        isinstance(seed, (bool, np.bool_))
        or not isinstance(seed, (int, np.integer))
        or seed < 0
        or child_order not in (2, 3, 4, 5)
        or nparents <= 0
        or nchildren <= 0
    ):
        raise ValueError(
            "Quota planning requires valid seed/order/positive population totals"
        )
    key = hashlib.sha256(f"{QUOTA_VERSION}:{seed}:{child_order}".encode()).digest()
    rng = np.random.default_rng(np.random.SeedSequence(np.frombuffer(key, dtype="<u4")))
    quotient, remainder = divmod(nchildren, nparents)
    quotas = np.full(nparents, quotient, dtype=int)
    if remainder:
        quotas[rng.choice(nparents, size=remainder, replace=False)] += 1
    return quotas.tolist()
