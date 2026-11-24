"""Contour-length-dependent daughter proposals, before material eligibility."""

import math

import numpy as np


LENGTH_POISSON_LAW = "length_poisson_sites_v1"
LENGTH_POISSON_STREAM = "feature.branching_length_poisson"
LENGTH_POISSON_VERSION = "1"


def length_poisson_sites(law, length_cm, rng_for_parent, reserve):
    """Return ordered sites and a receipt. Acquire draws only on a usable zone."""
    basal, apical, spacing = (law[key] for key in ("basal_exclusion_cm", "apical_exclusion_cm", "mean_spacing_cm"))
    stop = length_cm - apical
    width = max(0.0, stop - basal)
    probability = law["branch_probability"]
    mean = width / spacing
    receipt = dict(
        law=LENGTH_POISSON_LAW, parent_length_cm=length_cm, basal_exclusion_cm=basal, apical_exclusion_cm=apical,
        usable_length_cm=width, mean_spacing_cm=spacing, branch_probability=probability,
        conditional_mean_proposals=mean, active=False, proposed=0, first_proposed_site_cm=None,
    )
    if not width:
        return [], dict(receipt, decision="empty_zone")
    if probability == 0.0:
        return [], dict(receipt, decision="inactive", conditional_mean_proposals=mean if math.isfinite(mean) else None)
    if not math.isfinite(mean):
        raise ValueError("Nonfinite Poisson intensity for this parent and mean_spacing_cm")
    rng = rng_for_parent()
    if probability < 1.0 and rng.random() >= probability:
        return [], dict(receipt, decision="inactive")
    try:
        count = int(rng.poisson(mean))
    except ValueError as error:
        raise ValueError("Poisson site intensity exceeds the supported count range") from error
    if not count:
        return [], dict(receipt, active=True, decision="poisson_zero")
    reserve(count)
    # A rounded uniform draw can touch the exclusive upper endpoint.
    sites = np.minimum(rng.uniform(basal, stop, count), np.nextafter(stop, basal))
    sites.sort()
    return sites.tolist(), dict(receipt, active=True, decision="proposed",
                                proposed=count, first_proposed_site_cm=float(sites[0]))
