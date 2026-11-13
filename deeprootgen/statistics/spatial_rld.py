"""Spatial matching of simulated roots to field soil cores."""

import numpy as np
import pandas as pd


def calculate_core_rld(
    node_df: pd.DataFrame,
    *,
    x: float,
    y: float,
    z_lower_bound: float,
    z_upper_bound: float,
    core_radius: float,
    diameter_max_mm: float | None = None,
    plant_id: int | None = None,
    length_source: str = "recorded",
) -> float:
    """Calculate RLD inside a cylindrical field sampling volume.

    Coordinates and lengths are in cm.
    z=0 is ground level; negative z represents depth.

    Args:
        node_df: Simulated root node dataframe.
        x, y: Horizontal soil core centre, relative to the plant.
        z_lower_bound: Bottom of the sampled depth interval.
        z_upper_bound: Top of the sampled depth interval.
        core_radius: Soil core radius (cm).
        diameter_max_mm: Optional maximum root diameter (mm).
        plant_id: Optional plant identifier.
        length_source: 'recorded' or 'geometric'.

    Returns:
        Root length density (cm/cm3).
    """
    if core_radius <= 0 or z_upper_bound <= z_lower_bound:
        raise ValueError("Require radius > 0 and upper depth > lower depth.")

    if diameter_max_mm is not None and diameter_max_mm <= 0:
        raise ValueError("diameter_max_mm must be positive.")

    if length_source not in {"recorded", "geometric"}:
        raise ValueError("Invalid length_source.")

    required = {
        "node_id",
        "parent_id",
        "x",
        "y",
        "z",
        "diameter",
        "length",
    }
    missing = required - set(node_df.columns)

    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    nodes = node_df.copy()

    # Exclude invalid roots and their disconnected descendants.
    if "invalid_root" in nodes:
        nodes = nodes.loc[~nodes["invalid_root"].fillna(False).astype(bool)]

    if plant_id is not None:
        nodes = nodes.loc[nodes["plant_id"] == plant_id]

    parents = nodes.set_index("node_id", verify_integrity=True)

    children = nodes.loc[nodes["parent_id"].isin(parents.index)]

    if "order" in children:
        children = children.loc[children["order"] > 0]

    # Match the diameter range included in field measurements.
    if diameter_max_mm is not None:
        children = children.loc[children["diameter"] * 10 <= diameter_max_mm]

    if children.empty:
        return 0.0

    # Parent and child coordinates define straight segments.
    start = parents.loc[children["parent_id"], ["x", "y", "z"]].to_numpy(dtype=float)

    end = children[["x", "y", "z"]].to_numpy(dtype=float)

    d = end - start
    geometric_lengths = np.linalg.norm(d, axis=1)

    lengths = (
        children["length"].to_numpy(dtype=float)
        if length_source == "recorded"
        else geometric_lengths
    )

    if np.any(~np.isfinite(lengths)) or np.any(lengths < 0):
        raise ValueError("Invalid segment lengths.")

    if np.any((geometric_lengths < 1e-12) & (lengths > 1e-12)):
        raise ValueError("Positive segment length with coincident endpoints.")

    # Parameterise each segment as start + t * d,
    # with 0 <= t <= 1.
    dx, dy, dz = d.T

    rx = start[:, 0] - x
    ry = start[:, 1] - y

    # Horizontal circle intersection:
    # A*t² + B*t + C <= 0
    A = dx**2 + dy**2
    B = 2 * (rx * dx + ry * dy)
    C = rx**2 + ry**2 - core_radius**2

    t_enter = np.zeros(len(children))
    t_exit = np.ones(len(children))
    valid = np.ones(len(children), dtype=bool)

    # Segments parallel to the core's vertical axis.
    parallel = A <= 1e-14
    valid[parallel] = C[parallel] <= 1e-12

    varying = ~parallel
    disc = B[varying] ** 2 - 4 * A[varying] * C[varying]

    valid[varying] = disc >= 0

    sqrt_disc = np.sqrt(np.maximum(disc, 0))

    t_enter[varying] = np.maximum(
        t_enter[varying],
        (-B[varying] - sqrt_disc) / (2 * A[varying]),
    )

    t_exit[varying] = np.minimum(
        t_exit[varying],
        (-B[varying] + sqrt_disc) / (2 * A[varying]),
    )

    # Intersect with the observed soil depth interval.
    vertical = np.abs(dz) > 1e-12

    valid[~vertical] &= (start[~vertical, 2] >= z_lower_bound) & (
        start[~vertical, 2] <= z_upper_bound
    )

    if np.any(vertical):
        a = (z_lower_bound - start[vertical, 2]) / dz[vertical]

        b = (z_upper_bound - start[vertical, 2]) / dz[vertical]

        t_enter[vertical] = np.maximum(
            t_enter[vertical],
            np.minimum(a, b),
        )

        t_exit[vertical] = np.minimum(
            t_exit[vertical],
            np.maximum(a, b),
        )

    # Fraction of each segment contained within the core.
    fractions = np.where(
        valid,
        np.maximum(t_exit - t_enter, 0),
        0,
    )

    root_length_in_core = float(np.dot(fractions, lengths))

    core_volume = np.pi * core_radius**2 * (z_upper_bound - z_lower_bound)

    return root_length_in_core / core_volume
