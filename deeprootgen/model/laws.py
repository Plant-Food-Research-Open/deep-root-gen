"""Leaf laws selected per stage and order by the resolved law table.

Each law receives only the state it needs (an organ's sampled values, its
parent's material or realized point/tangent, settings and a random stream) and
returns values. None can construct a simulator, allocate graph identities,
write files or call observation/search services.

Stream policy ``cohort_v5`` reproduces the historical cohort streams and draw
order: maturity, origin and heading share ``SeedSequence([seed, organ, 0])``;
length, taper and branching share purpose 1; curvature uses 2; insertion 3.
Policy ``feature_keyed_v1`` gives every purpose an independent keyed stream,
so disabling one feature cannot change another feature's draws.
"""

import numpy as np

from ..data_model.features import CURVATURE_LAW_VERSION, CURVATURE_STREAM_NAMESPACE, FEATURE_STREAM_VERSION
from .cohort_geometry import bounded_draw, taper_diameter

COHORT_V5_PURPOSE = dict(maturity=0, origin=0, heading=0, length=1, taper=1, branching=1, curvature=2, insertion=3)
INCLINATION_REJECTION_BUDGET = 10000


def law_stream(streams, policy, purpose, organ_id):
    """The random stream owned by one law purpose of one biological organ."""
    if policy == "cohort_v5":
        return streams.cohort_v5(organ_id, COHORT_V5_PURPOSE[purpose])
    if purpose == "curvature":
        return streams.keyed(CURVATURE_STREAM_NAMESPACE, CURVATURE_LAW_VERSION, organ_id)
    return streams.keyed(f"feature.{purpose}", FEATURE_STREAM_VERSION, organ_id)


def primary_maturity(law, index, rng):
    """Dimensionless maturity of one primary (never chronological age)."""
    for group in law["groups"]:
        if index in group["primary_indices"]:
            if group["draw"] == "fixed":
                return float(group["maturity_range"][0]), group["label"]
            return float(rng.uniform(*group["maturity_range"])), group["label"]
    raise ValueError(f"Primary index {index} belongs to no maturity group")


def first_branch_sites(law, order, max_order, length, maturity, scale_probability, rng, counters):
    """First-branch draw, censored probability, daughter count and uniform sites."""
    first_draw = bounded_draw(law["first_branch_cm"], rng)
    factor = maturity if scale_probability else 1.0
    sites = []
    if order < max_order and rng.uniform() < law["branch_probability"] * factor:
        if first_draw < length:
            weights = law["daughter_probabilities"]
            n = int(rng.choice(np.arange(1, len(weights) + 1), p=weights))
            sites = [first_draw]
            if n > 1:
                sites += sorted(rng.uniform(first_draw, length, n - 1).tolist())
        else:
            counters["branch_beyond_tip"] += 1
    return first_draw, sites


def point_taper_dimensions(law, maturity, diameter_power, parent_diameter, cap, rng, counters, *, diameter_scale=1.):
    """Base (scaled, then capped) and tip (limited to the base) diameters, cm."""
    base = bounded_draw(law["base_cm"], rng) * diameter_scale
    if diameter_power is not None:
        base = base * maturity**diameter_power
    if parent_diameter is not None and cap is not None:
        limit = parent_diameter * cap["fraction_max"]
        if base > limit:
            counters["diameter_constrained"] += 1
            base = limit
    tip_draw = bounded_draw(law["tip_cm"], rng) * diameter_scale
    counters["tip_constrained"] += int(tip_draw > base)
    return base, min(tip_draw, base)


def sample_planned_organ(order, max_order, maturity, parent_diameter, laws, rngs, counters):
    """Fully replaced construction: sampling -> maturity -> cap -> tip -> censoring.

    Draw order within one stream is the historical cohort order: length, base,
    tip, first branch, branch probability, daughter count, daughter sites.
    """
    maturity_law = laws.maturity
    length = bounded_draw(laws.lengths[order], rngs["length"])
    if maturity_law is not None:
        length = length * maturity ** maturity_law["length_power"]
    taper = laws.taper[order]
    base, tip = point_taper_dimensions(
        taper, maturity, None if maturity_law is None else maturity_law["diameter_power"],
        parent_diameter, laws.cap, rngs["taper"], counters,
    )
    first_draw, sites = None, []
    if order in laws.branching:
        first_draw, sites = first_branch_sites(
            laws.branching[order], order, max_order, length, maturity,
            maturity_law is not None and maturity_law["scale_branch_probability"], rngs["branching"], counters,
        )
    midpoint = taper["midpoint_diameter_fraction"]
    return dict(length=length, base=base, tip=tip, midpoint=midpoint, first_draw=first_draw, sites=sites)


def site_diameter(plan, site):
    """Parent point diameter at a birth site (the cap's reference material)."""
    return float(taper_diameter(site, plan["length"], plan["base"], plan["tip"], plan["midpoint"]))


def disk_origin(law, rng):
    """Uniform-area disk position and its polar angle; z below the surface."""
    phi = rng.uniform(-np.pi, np.pi)
    radius = law["radius_cm"] * np.sqrt(rng.uniform())
    start = np.array(
        [radius * np.cos(phi), radius * np.sin(phi), -(rng.uniform(*law["depth_range_cm"]) - law["surface_z_cm"])]
    )
    return start, phi


def radial_inclination(law, phi, rng):
    """Radially outward azimuth with a bounded normal inclination below horizontal."""
    low, high = law["inclination_bounds_deg"]
    for _ in range(INCLINATION_REJECTION_BUDGET):
        angle = rng.normal(law["inclination_mean_deg"], law["inclination_sd_deg"])
        if low <= angle <= high:
            break
    else:
        raise ValueError("Inclination rejection budget exhausted")
    a = np.deg2rad(angle)
    return [np.cos(a) * np.cos(phi), np.cos(a) * np.sin(phi), -np.sin(a)]
