"""Strict opt-in scope for a static primary-curve attachment sensitivity."""

import numpy as np

from .current_length import _cdf_arrays

FIELD = "research_primary_attachment_distal_fraction"


def validate_distal_fraction(value):
    if value is None:
        return None
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating))
            or not 0 <= value < 1 or not np.isfinite(value)):
        raise ValueError("Primary attachment distal fraction must be finite nonbool numeric in [0,1)")
    return float(value)


def validate_distal_scope(parameters, constructor_seed=None):
    get = parameters.get if isinstance(parameters, dict) else lambda key, default=None: getattr(parameters, key, default)
    value = validate_distal_fraction(get(FIELD))
    if not value:
        return value
    seed = get('random_seed')
    if (isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)) or seed < 0
            or (constructor_seed is not None and (isinstance(constructor_seed, (bool, np.bool_))
                or not isinstance(constructor_seed, (int, np.integer)) or constructor_seed != seed))):
        raise ValueError("Primary attachment placement requires matching explicit nonnegative integer seeds")
    cdfs = get('research_current_length_cdfs_cm')
    if (get('research_current_length_grid') != 'construction_steps_v1' or get('max_order') != 3
            or get('tropism_mode') != 'fichtl2024' or not isinstance(cdfs, dict) or set(cdfs) != {2, 3}):
        raise ValueError("Primary attachment placement requires controlled construction steps/Fichtl/max3/CDF2&3")
    for cdf in cdfs.values():
        _cdf_arrays(cdf)
    return value
