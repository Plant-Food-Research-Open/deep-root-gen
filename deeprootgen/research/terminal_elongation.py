"""Opt-in research design for reallocating elongation among terminal roots.

Each group contains three terminal courses whose integrated dry masses scale
linearly with length under both supplied material conventions. Scale a selected
course about its own insertion, retaining its normalized taper. For a taper
with an exponential rate per unit length, divide the rate by the length scale.
The caller supplies feasible scale limits from the order-specific length domain
and the soil boundary and remeasures the resulting physical graph.

For example, these synthetic masses leave different terminals free to elongate
in each direction. Multiplication by either mass vector gives the same total
before and after the exchange.

>>> assay, structural = [1, 2, 1], [2, 1, 1]
>>> options = exchange_scales(assay, structural, [0.9, 0.1, 0.1], [2, 2, 1.5])
>>> options[1].round(2).tolist()
[0.9, 0.9, 1.3]
>>> np.allclose(options @ assay, 4) and np.allclose(options @ structural, 4)
True
"""

import numpy as np
import pandas as pd
from scipy.stats import qmc


PARAMETERS = (
    "intercept", "shallow", "middle", "upper_deep", "lower_deep",
    "row", "crowding", "surface",
)


def mass_matched_triplets(assay_mass, marks):
    """Group eligible terminal indices by comparable assay mass.

    Sort by mass, then sort within successive blocks of 72 by one fixed
    random mark per biological axis. Any last one or two axes stay unchanged.
    """
    mass = np.asarray(assay_mass, dtype=float)
    marks = np.asarray(marks, dtype=float)
    if mass.ndim != 1 or marks.shape != mass.shape:
        raise ValueError("Supply a one-dimensional mass and mark for each eligible terminal")
    if not np.all(np.isfinite(mass) & (mass > 0)) or not np.isfinite(marks).all():
        raise ValueError("Terminal masses must be positive and masses and marks must be finite")

    order = np.argsort(mass, kind="stable")
    groups = []
    for start in range(0, len(order), 72):
        block = order[start:start + 72]
        shuffled = block[np.argsort(marks[block], kind="stable")]
        groups.append(shuffled[:len(block) - len(block) % 3].reshape(-1, 3))
    return np.concatenate(groups) if groups else np.empty((0, 3), dtype=np.intp)


def exchange_scales(assay_mass, structural_mass, min_scale, max_scale):
    """Return unchanged, positive and negative elongation scales for each triplet.

    Both mass arrays have the same shape ending in three and use the same unit.
    Limits broadcast to that shape and must contain unity. The output has an
    extra leading axis of length three. In each signed alternative the greatest
    fractional movement is 0.80 or the first binding individual limit. Different
    bounds can give different amplitudes in the positive and negative directions.

    A difference of two mass ratios gives each member's exchange in assay-mass
    units. The resulting vector sums to zero under both material conventions.
    When the ratios coincide within 1e-11 (absolute and relative to their
    largest value), exchange assay mass between the first two members only.
    In that numerical limit the second budget is conserved to the same relative
    tolerance. No axis receives mass from a different triplet.
    """
    assay = np.asarray(assay_mass, dtype=float)
    structural = np.asarray(structural_mass, dtype=float)
    if assay.ndim == 0 or assay.shape[-1] != 3 or structural.shape != assay.shape:
        raise ValueError("Mass arrays must have the same shape with three members per group")
    if not np.all(np.isfinite(assay) & (assay > 0)):
        raise ValueError("Assay masses must be finite and positive")
    if not np.all(np.isfinite(structural) & (structural >= 0)):
        raise ValueError("Structural masses must be finite and nonnegative")

    low = np.broadcast_to(np.asarray(min_scale, dtype=float), assay.shape)
    high = np.broadcast_to(np.asarray(max_scale, dtype=float), assay.shape)
    if not np.all(np.isfinite(low) & np.isfinite(high) & (low >= 0) & (low <= 1) & (high >= 1)):
        raise ValueError("Finite scale limits must be nonnegative and contain the unchanged state")

    # Extended precision also permits widely separated input masses without
    # overflowing the ratio or its division by a small assay mass.
    ratio = structural.astype(np.longdouble) / assay
    direction = np.roll(ratio, -1, axis=-1) - np.roll(ratio, -2, axis=-1)
    proportional = np.ptp(ratio, axis=-1) <= 1e-11 * np.minimum(1, ratio.max(axis=-1))
    direction[proportional] = (1, -1, 0)
    fraction = direction / assay
    fraction /= np.max(np.abs(fraction), axis=-1, keepdims=True)
    fraction = np.asarray(0.80 * fraction, dtype=float)

    alternatives = [np.ones_like(assay)]
    for sign in (1, -1):
        movement = sign * fraction
        room = np.where(movement > 0, high - 1, 1 - low)
        # Movement is already limited to 80%. Ignore movements with enough
        # room before division, including zeros, so no overlarge ratio is needed.
        magnitude = np.abs(movement)
        limit = np.divide(room, magnitude, out=np.ones_like(assay), where=room < magnitude)
        step = limit.min(axis=-1, keepdims=True)
        alternatives.append(1 + step * movement)
    return np.stack(alternatives)


def elongation_design(seed=913706):
    """Return 5,000 prescriptions indexed by design_id, with no fitted inputs.

    Family 0 uses original primary bearings and family 1 uses independently
    randomized primary bearings. Both receive the same five controls and the
    same 2,495 Latin-hypercube combinations. The intercept spans [-4, 2] and
    each of the seven spatial coefficients spans [-3, 3] in the sampled rows.
    """
    controls = [
        [-1000, 0, 0, 0, 0, 0, 0, 0],  # unchanged
        [0, 0, 0, 0, 0, 0, 0, 0],      # equal option odds
        [-0.5, 0, 0, 0, 0, 0, -1.5, 0],
        [-0.5, -1, 0, 1, 1, 0, 0, 0],
        [-0.5, 0, 0, 0, 0, 0, 0, 1.5],
    ]
    samples = qmc.LatinHypercube(len(PARAMETERS), seed=seed).random(2495)
    coefficients = 6 * samples + np.array([-4, -3, -3, -3, -3, -3, -3, -3])
    per_scaffold = np.vstack([controls, coefficients])
    design = pd.DataFrame(np.tile(per_scaffold, (2, 1)), columns=PARAMETERS)
    design.insert(0, "family", np.repeat((0, 1), len(per_scaffold)))
    return design.rename_axis("design_id")


def choose_exchange(coefficients, feature_changes, uniform_marks):
    """Choose one of the three physical alternatives per triplet for one rule.

    Supply eight design coefficients in PARAMETERS order, and the seven
    standardized deposition changes versus unchanged for each signed option
    (shape 2 × groups × 7). Supply three independent, fixed U[0,1] marks per
    group (shape 3 × groups), reused when comparing rules. Output 0, 1 or 2
    indexes the leading axis of exchange_scales. All three options draw once.
    """
    theta = np.asarray(coefficients, dtype=float)
    changes = np.asarray(feature_changes, dtype=float)
    marks = np.asarray(uniform_marks, dtype=float)
    if theta.shape != (len(PARAMETERS),):
        raise ValueError("Supply one coefficient for each of the eight design parameters")
    if changes.ndim != 3 or changes.shape[0] != 2 or changes.shape[2] != 7:
        raise ValueError("Supply two sets of seven feature changes per group")
    if marks.shape != (3, changes.shape[1]) or not np.all((marks >= 0) & (marks <= 1)):
        raise ValueError("Supply three unit-interval marks per group")
    if not np.isfinite(theta).all() or not np.isfinite(changes).all():
        raise ValueError("Coefficients and feature changes must be finite")
    gumbel = -np.log(-np.log(np.clip(marks, 1e-15, 1 - 1e-15)))
    utilities = gumbel.copy()
    utilities[1:] += theta[0] + changes @ theta[1:]
    return np.argmax(utilities, axis=0)
