"""Optional birth-position rank association of existing tertiary length draws.

No new RNG key, marginal distribution, branch law or biological age is inferred.
"""

import copy

import numpy as np

from .branching import validate_parent2_branch_zone
from .current_length import _cdf_arrays, sample_current_lengths

VERSION = "drg-tertiary-length-rank-v1"
FIELD = "research_tertiary_length_rank_strength"


def validate_rank_strength(value):
    if value is None:
        return None
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating))
            or not 0 <= value <= 1 or not np.isfinite(value)):
        raise ValueError("Tertiary length rank strength must be a finite nonbool number in [0,1]")
    return float(value)


def validate_rank_scope(parameters, constructor_seed=None):
    """Fail closed on active schema-bypassed construction inputs before mutation."""
    get = parameters.get if isinstance(parameters, dict) else lambda key, default=None: getattr(parameters, key, default)
    strength = validate_rank_strength(get(FIELD))
    if not strength:
        return strength
    seed = get("random_seed")
    if (isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)) or seed < 0
            or (constructor_seed is not None and (isinstance(constructor_seed, (bool, np.bool_))
                or not isinstance(constructor_seed, (int, np.integer)) or constructor_seed != seed))):
        raise ValueError("Tertiary length rank requires matching explicit nonnegative integer seeds")
    cdfs = get("research_current_length_cdfs_cm")
    if (get("research_current_length_grid") != "construction_steps_v1" or get("max_order") != 3
            or get("tropism_mode") != "fichtl2024" or not isinstance(cdfs, dict) or set(cdfs) != {2, 3}
            or get("research_parent2_branch_zone_cm") is None):
        raise ValueError("Tertiary length rank requires controlled construction steps/Fichtl/max3/CDF2&3/parent2 zone")
    validate_parent2_branch_zone(get("research_parent2_branch_zone_cm"))
    for cdf in cdfs.values():
        _cdf_arrays(cdf)
    return strength


def rank_permutation(quantiles, strength):
    """Return source index at each destination, using stable exact float scores."""
    strength = validate_rank_strength(strength) or 0.
    values = np.asanyarray(quantiles)
    if (np.ma.isMaskedArray(values) or values.ndim != 1 or values.dtype.kind not in "fiu"
            or not np.isfinite(values).all() or ((values < 0) | (values >= 1)).any()):
        raise ValueError("Original quantiles must be a finite real 1-D pool in [0,1)")
    values = values.astype(float)
    n = len(values)
    birth_ranks = (np.arange(n) + .5) / n if n else np.array([], dtype=float)
    scores = (1. - strength) * values - strength * birth_ranks
    pool = sorted(range(n), key=lambda j: (values[j], j))
    destinations = sorted(range(n), key=lambda j: (scores[j], j))
    permutation = [0] * n
    for destination, source in zip(destinations, pool):
        permutation[destination] = source
    return permutation, scores.tolist()


def plan_tertiary_length_family(cdf, segments_per_root, seed, family_organ_id, first_child_id, sites_cm, strength):
    """Plan existing keyed draws once before allocating an order3 sibling family.

    The returned sampler has a NEW composite version. Nested original v1 draws
    retain their true owners; top expected/allocated IDs refer to destination.
    """
    strength = validate_rank_strength(strength)
    if strength is None:
        raise ValueError("Family planning requires explicit strength")
    for name, value, minimum in (("seed", seed, 0), ("segments_per_root", segments_per_root, 1)):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < minimum:
            raise ValueError(f"Family {name} must be an integer >= {minimum}")
    _cdf_arrays(cdf)
    for value in (family_organ_id, first_child_id):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value <= 0:
            raise ValueError("Family and prospective child IDs must be positive integers")
    sites = np.asarray(sites_cm, dtype=float)
    if (sites.ndim != 1 or not np.isfinite(sites).all() or (sites <= 0).any() or (np.diff(sites) <= 0).any()):
        raise ValueError("Family sites must be finite positive strictly increasing cm")
    ids = [int(first_child_id + j) for j in range(len(sites))]
    draws = [sample_current_lengths(cdf, segments_per_root, seed, oid, 3)[1] for oid in ids]
    quantiles = [draw['quantile'] for draw in draws]
    permutation, scores = rank_permutation(quantiles, strength)
    family = dict(version=VERSION, strength=strength, family_organ_id=int(family_organ_id),
                  destination_organ_ids=ids, sites_cm=sites.tolist(), original_quantiles=quantiles,
                  scores=scores, source_indices=permutation)
    plans = []
    for j, source_index in enumerate(permutation):
        destination, source = draws[j], draws[source_index]
        weights = np.asarray(destination['normalized_weights'])
        lengths = source['sampled_current_length_cm'] * weights
        if not np.isfinite(lengths).all() or (lengths <= 1e-12).any():
            raise ValueError("Rank-assigned segments violate existing finite positive length cutoff")
        sampled = source['sampled_current_length_cm']
        if not np.isclose(lengths.sum(), sampled, rtol=0, atol=1e-8):
            raise ValueError("Rank-assigned CURRENT length conservation exceeds 1e-8 cm")
        sampler = dict(stream_version=VERSION, seed=int(seed), order=3,
                       expected_organ_id=ids[j], requested_segment_count=int(segments_per_root),
                       cdf_sha256=destination['cdf_sha256'], length_source_organ_id=ids[source_index],
                       weight_source_organ_id=ids[j], normalized_weights=weights.tolist(),
                       sampled_current_length_cm=sampled, pre_subdivision_length_cm=float(lengths.sum()),
                       destination_draw=copy.deepcopy(destination), source_draw=copy.deepcopy(source),
                       length_rank=dict(version=VERSION, strength=strength, family_organ_id=int(family_organ_id),
                                        destination_index=j, source_index=source_index,
                                        source_organ_id=ids[source_index], source_quantile=source['quantile']))
        plans.append((lengths, sampler))
    return plans, family
