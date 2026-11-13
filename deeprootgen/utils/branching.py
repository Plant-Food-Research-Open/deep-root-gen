
"""Utilities for sampling lateral-root branching locations."""

import numpy as np


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
        raise ValueError(
            "parent_xyz must have shape (n_points >= 2, 3)."
        )

    if not np.isfinite(xyz).all():
        raise ValueError(
            "Parent coordinates must be finite."
        )

    if (
        not np.isfinite(interbranch_distance)
        or interbranch_distance <= 0
    ):
        raise ValueError(
            "interbranch_distance must be positive and finite."
        )

    if not 0 <= floor_threshold < ceiling_threshold <= 1:
        raise ValueError(
            "Expected 0 <= floor_threshold < ceiling_threshold <= 1."
        )

    if not np.isfinite(log_sd) or log_sd < 0:
        raise ValueError(
            "log_sd must be finite and nonnegative."
        )

    if max_branches is not None:
        if not isinstance(max_branches, (int, np.integer)):
            raise TypeError("max_branches must be an integer.")

        if max_branches < 0:
            raise ValueError(
                "max_branches must be nonnegative."
            )

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
        raise ValueError(
            "Parent root contains zero-length segments."
        )

    total_length = float(segment_lengths.sum())

    # Eligible branching region.
    start = floor_threshold * total_length
    end = ceiling_threshold * total_length

    # --------------------------------------------------
    # Sample stochastic insertion positions
    # --------------------------------------------------

    sites = []

    # Randomise the initial branching position.
    position = (
        start
        + rng.uniform(0.0, interbranch_distance)
    )

    while position < end:

        sites.append(float(position))

        # Stop after reaching the branch-count cap.
        if (
            max_branches is not None
            and len(sites) >= max_branches
        ):
            break

        # Lognormal distribution with arithmetic mean
        # equal to interbranch_distance.
        spacing = (
            interbranch_distance
            * rng.lognormal(
                mean=-0.5 * log_sd**2,
                sigma=log_sd,
            )
        )

        position += spacing

    return sites
