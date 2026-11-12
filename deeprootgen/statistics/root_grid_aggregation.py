"""Aggregate DeepRootGen root length and dry biomass within soil grid voxels.

The soil DataFrame must contain voxel *boundary points* with x and y horizontal
and z vertical (negative downward). Root coordinates and lengths are in cm;
root tissue density is in g/cm3.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def aggregate_root_grid(
    node_df: pd.DataFrame,
    soil_df: pd.DataFrame,
    length_source: str = "recorded",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (per-voxel metrics, per-plant in-grid biomass totals).

    Root segments are the edges from a parent node to each non-base child node.
    Each segment's length is clipped and split between the soil voxels it
    crosses. Dry mass for a segment is pi*(diameter/2)^2*length*RTD.

    length_source='recorded' allocates each stored segment length in proportion
    to the geometric fraction inside each voxel. 'geometric' uses endpoint
    distances instead. All lengths and dimensions are assumed to be cm.
    """
    if length_source not in {"recorded", "geometric"}:
        raise ValueError("length_source must be 'recorded' or 'geometric'")

    required_nodes = {
        "node_id", "parent_id", "plant_id", "x", "y", "z",
        "order", "length", "diameter", "root_tissue_density", "root_type",
    }
    missing = required_nodes.difference(node_df.columns)
    if missing:
        raise ValueError(f"Missing root columns: {sorted(missing)}")
    if not {"x", "y", "z"}.issubset(soil_df.columns):
        raise ValueError("soil_df must have x, y, z columns")

    edges = [np.sort(soil_df[a].dropna().unique().astype(float)) for a in ("x", "y", "z")]
    if any(len(e) < 2 or not np.all(np.isfinite(e)) or np.any(np.diff(e) <= 0) for e in edges):
        raise ValueError("Soil grid must define at least two distinct finite boundaries per axis")

    nx, ny, nz = [len(e) - 1 for e in edges]
    ix, iy, iz = np.indices((nx, ny, nz))
    ix, iy, iz = ix.ravel(), iy.ravel(), iz.ravel()
    x_edges, y_edges, z_edges = edges
    volume = (
        np.diff(x_edges)[ix] * np.diff(y_edges)[iy] * np.diff(z_edges)[iz]
    )
    base = pd.DataFrame({
        "id": np.arange(1, len(ix) + 1, dtype=int),
        "column": ix,
        "row": iy,
        "layer": iz,
        "vertical_layer": nz - iz,  # 1 is the shallowest layer
        "organ_type": "Grid",
        "x": (x_edges[ix] + x_edges[ix + 1]) / 2,
        "y": (y_edges[iy] + y_edges[iy + 1]) / 2,
        "z": (z_edges[iz] + z_edges[iz + 1]) / 2,
        "x_min": x_edges[ix],
        "x_max": x_edges[ix + 1],
        "y_min": y_edges[iy],
        "y_max": y_edges[iy + 1],
        "z_min": z_edges[iz],
        "z_max": z_edges[iz + 1],
        "gridSize": np.diff(x_edges)[ix],
        "soildepth": np.diff(z_edges)[iz],
        "soil_volume_cm3": volume,
    })
    # An example table uses a single 'gridSize' for both horizontal axes.
    # Supply a distinct y width when cells are rectangular.
    base["gridWidthY"] = np.diff(y_edges)[iy]

    result_frames: list[pd.DataFrame] = []
    totals_records: list[dict] = []
    eps = 1e-12

    for plant_id, plant_df in node_df.groupby("plant_id", sort=True):
        plant_df = plant_df.copy()
        if not plant_df["node_id"].is_unique:
            raise ValueError(f"Duplicate node_id within plant {plant_id}")
        parents = plant_df.set_index("node_id")
        valid = plant_df.loc[
            (plant_df["order"] > 0)
            & plant_df["parent_id"].isin(parents.index)
        ]
        if "invalid_root" in plant_df.columns:
            valid = valid.loc[~valid["invalid_root"].fillna(False).astype(bool)]
        if not valid["root_type"].isin(["fine", "structural"]).all():
            invalid_types = sorted(valid.loc[
                ~valid["root_type"].isin(["fine", "structural"]), "root_type"
            ].astype(str).unique())
            raise ValueError(f"Unknown root types: {invalid_types}")

        # Dimensions: (x voxel, y voxel, z voxel, metric)
        # 0 total length, 1 fine length, 2 structural length,
        # 3 fine DM, 4 structural DM, 5 diameter*length.
        accum = np.zeros((nx, ny, nz, 6), dtype=float)
        for segment in valid.itertuples(index=False):
            parent = parents.loc[segment.parent_id]
            start = np.array([parent.x, parent.y, parent.z], dtype=float)
            end = np.array([segment.x, segment.y, segment.z], dtype=float)
            delta = end - start
            geometric_length = float(np.linalg.norm(delta))
            recorded_length = float(segment.length)
            length = recorded_length if length_source == "recorded" else geometric_length
            diameter = float(segment.diameter)
            rtd = float(segment.root_tissue_density)
            if not (np.isfinite(length) and np.isfinite(diameter) and np.isfinite(rtd)):
                raise ValueError(f"Non-finite root geometry or RTD for node {segment.node_id}")
            if length < 0 or diameter < 0 or rtd < 0:
                raise ValueError(f"Negative root geometry or RTD for node {segment.node_id}")
            if length <= eps:
                continue
            if geometric_length <= eps:
                raise ValueError(
                    f"Node {segment.node_id} has positive length but coincident endpoints"
                )

            # Clip the entire 3D segment against the rectangular soil extent.
            enter, leave = 0.0, 1.0
            for j, boundary in enumerate(edges):
                if abs(delta[j]) <= eps:
                    if start[j] < boundary[0] or start[j] > boundary[-1]:
                        leave = -1.0
                        break
                else:
                    t_pair = (boundary[[0, -1]] - start[j]) / delta[j]
                    enter = max(enter, float(np.min(t_pair)))
                    leave = min(leave, float(np.max(t_pair)))
            if leave - enter <= eps:
                continue

            # Split at every plane crossed by the segment.
            cuts = [enter, leave]
            for j, boundary in enumerate(edges):
                if abs(delta[j]) > eps:
                    intersections = (boundary[1:-1] - start[j]) / delta[j]
                    cuts.extend(intersections[
                        (intersections > enter + eps) & (intersections < leave - eps)
                    ])
            cuts = np.sort(np.asarray(cuts, dtype=float))
            mass_per_length = np.pi * (diameter / 2.0) ** 2 * rtd
            for t0, t1 in zip(cuts[:-1], cuts[1:]):
                proportion = t1 - t0
                if proportion <= eps:
                    continue
                midpoint = start + ((t0 + t1) / 2) * delta
                voxel_index = tuple(
                    int(np.clip(
                        np.searchsorted(boundary, midpoint[j], side="right") - 1,
                        0, len(boundary) - 2,
                    ))
                    for j, boundary in enumerate(edges)
                )
                partial_length = length * proportion
                accum[(*voxel_index, 0)] += partial_length
                accum[(*voxel_index, 5)] += partial_length * diameter
                if segment.root_type == "fine":
                    accum[(*voxel_index, 1)] += partial_length
                    accum[(*voxel_index, 3)] += partial_length * mass_per_length
                else:
                    accum[(*voxel_index, 2)] += partial_length
                    accum[(*voxel_index, 4)] += partial_length * mass_per_length

        metrics = accum.reshape((-1, 6))
        table = base.copy()
        table.insert(1, "plant_id", plant_id)
        table["length"] = metrics[:, 0]
        table["root_length_cm"] = metrics[:, 0]
        table["fineRootLength"] = metrics[:, 1]
        table["structuralRootLength"] = metrics[:, 2]
        table["diameter"] = np.divide(
            metrics[:, 5], metrics[:, 0],
            out=np.zeros_like(metrics[:, 0]), where=metrics[:, 0] > 0,
        )
        table["fineRootDM"] = metrics[:, 3]
        table["structuralRootDM"] = metrics[:, 4]
        total_fine = float(metrics[:, 3].sum())
        total_structural = float(metrics[:, 4].sum())
        table["totalFineRoot"] = total_fine
        table["totalStructuralRoot"] = total_structural
        table["fFineRoot"] = (
            table["fineRootDM"] / total_fine if total_fine > 0 else 0.0
        )
        table["fStructuralRoot"] = (
            table["structuralRootDM"] / total_structural if total_structural > 0 else 0.0
        )
        table["rld_cm_cm3"] = table["length"] / table["soil_volume_cm3"]

        totals_records.append({
            "plant_id": plant_id,
            "totalFineRoot": total_fine,
            "totalStructuralRoot": total_structural,
            "totalRootDM": total_fine + total_structural,
            "totalRootLength": float(metrics[:, 0].sum()),
        })
        result_frames.append(table)

    voxel_df = pd.concat(result_frames, ignore_index=True) if result_frames else base.head(0)
    if len(result_frames) > 1:
        # Unique grid-cell identifiers across all plants.
        voxel_df["id"] = np.arange(1, len(voxel_df) + 1)
    totals_df = pd.DataFrame(totals_records)
    return voxel_df, totals_df
