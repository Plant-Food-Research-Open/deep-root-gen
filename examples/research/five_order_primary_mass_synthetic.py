"""Invented, offline end-to-end numerical example; no observations or fitting.

From the repository root, with its qualified Python3.10 environment and locked
runtime dependencies available on PYTHONPATH::

    python examples/research/five_order_primary_mass_synthetic.py

Prints a JSON verification summary to stdout; reads the adjacent configuration and
writes no artifacts. All dimensions, density, directions, counts and mass shares
below are deliberately invented scenario assumptions. This exercises opt-in
mechanisms together; it does not change defaults or qualify biological accuracy.
"""

import hashlib
import json

import networkx as nx
import numpy as np
import pandas as pd

from pathlib import Path

from deeprootgen.data_model.canonical import RootConfig
from deeprootgen.model import RootSystemSimulation
from deeprootgen.research.order_mass_allocation import (
    allocate_order_mass,
    audit_root_mass,
)
from deeprootgen.research.primary_curvature import curve_primary_roots

SEED = 17
DRY_DENSITY_G_CM3 = 0.07
COUNTS = {1: 2, 2: 3, 3: 3, 4: 2, 5: 2}
MASS_GROUPS = [
    {"orders": [1, 2, 3], "share": 0.75},
    {"orders": [4, 5], "share": 0.25},
]


def invented_parameters():
    """Small explicit construction; the physical branch window affects order1."""
    return RootConfig.model_validate_json(Path(__file__).with_suffix(".json").read_text())


def check_graph(nodes, edges):
    """Check exported geometry, parent references, rooted connectivity and counts."""
    numeric = nodes[["x", "y", "z", "length", "diameter", "root_tissue_density"]]
    if not np.isfinite(numeric.to_numpy(float)).all() or nodes.invalid_root.any():
        raise RuntimeError("Example produced nonfinite or invalid roots")
    graph = nx.DiGraph(zip(edges.parent_id, edges.child_id))
    expected = set(
        zip(
            nodes.loc[nodes.order.gt(0), "parent_id"],
            nodes.loc[nodes.order.gt(0), "node_id"],
        )
    )
    if (
        not nodes.node_id.is_unique
        or not nx.is_arborescence(graph)
        or len(edges) != len(nodes) - 1
        or set(graph.nodes) != set(nodes.node_id)
        or set(zip(edges.parent_id, edges.child_id)) != expected
    ):
        raise RuntimeError(
            "Example produced inconsistent exported tree/parent references"
        )
    counts = nodes.loc[nodes.order.gt(0)].groupby("order").organ_id.nunique().to_dict()
    if counts != COUNTS:
        raise RuntimeError("Example changed supplied biological root counts")
    lookup = nodes.set_index("node_id")
    roots = nodes.loc[nodes.order.gt(0)]
    actual = np.linalg.norm(
        roots[["x", "y", "z"]].to_numpy(float)
        - lookup.loc[roots.parent_id, ["x", "y", "z"]].to_numpy(float),
        axis=1,
    )
    np.testing.assert_allclose(
        actual, roots.length.to_numpy(float), rtol=1e-9, atol=0.0
    )
    if nodes.z.max() > 0.0:
        raise RuntimeError("Example crosses its physical soil surface")
    return dict(
        finite=True,
        connected_rooted_tree=True,
        exported_parent_refs_match=True,
        nodes=len(nodes),
        edges=len(edges),
        root_counts_by_order=counts,
    )


def main():
    parameters = invented_parameters()
    simulation = RootSystemSimulation(random_seed=SEED)
    simulation.run(parameters)
    native_nodes, native_edges = simulation.G.as_df()
    native_graph = check_graph(native_nodes, native_edges)
    native_mass = audit_root_mass(
        native_nodes, native_edges, dry_density_g_cm3=DRY_DENSITY_G_CM3
    )

    # These NEW fields specify initial unit tangents. Native primary-design
    # inclination/azimuth above specify full chords and are never reinterpreted.
    initial_tangents = {
        int(organ.segments[0].node_data.organ_id): dict(
            initial_inclination_deg=inclination,
            initial_azimuth_deg=azimuth,
            category="invented initial tangent",
        )
        for organ, inclination, azimuth in zip(
            simulation.organs[1], [20.0, 45.0], [0.0, 100.0]
        )
    }
    curved_nodes, curved_edges, curvature = curve_primary_roots(
        native_nodes,
        native_edges,
        initial_tangents,
        seed=SEED,
        surface_z_cm=0.0,
        max_step_cm=1.25,
        curvature_sd_rad_cm=0.06,
        correlation_length_cm=3.0,
        downward_drift_rad_cm=0.005,
        strict_initial_angle=True,
    )
    curved_graph = check_graph(curved_nodes, curved_edges)
    curved_mass = audit_root_mass(
        curved_nodes, curved_edges, dry_density_g_cm3=DRY_DENSITY_G_CM3
    )
    for metric in ("length_cm", "volume_cm3", "mass_g"):
        np.testing.assert_allclose(
            curved_mass["totals"][metric],
            native_mass["totals"][metric],
            rtol=1e-9,
            atol=0.0,
        )
    for report in curvature["primaries"]:
        np.testing.assert_allclose(
            report["realised_initial_heading"],
            report["requested_initial_heading"],
            rtol=0.0,
            atol=1e-12,
        )

    # Orders4+5 COMBINED receive25%; neither order is individually assigned25%.
    # All orders are unlocked in this demonstration, so primary diameters can
    # change. This is explicitly a mass-allocation scenario, not measured biomass.
    allocated_nodes, allocated_edges, allocation = allocate_order_mass(
        curved_nodes,
        curved_edges,
        dry_density_g_cm3=DRY_DENSITY_G_CM3,
        groups=MASS_GROUPS,
    )
    allocated_graph = check_graph(allocated_nodes, allocated_edges)
    pd.testing.assert_frame_equal(
        allocated_nodes.drop(columns="diameter"), curved_nodes.drop(columns="diameter")
    )
    pd.testing.assert_frame_equal(allocated_edges, curved_edges)
    np.testing.assert_allclose(
        allocation["achieved_total_g"],
        allocation["original_total_g"],
        rtol=1e-12,
        atol=0.0,
    )
    np.testing.assert_allclose(
        allocation["groups"][1]["achieved_share"], 0.25, rtol=1e-12, atol=0.0
    )

    spec_bytes = json.dumps(
        parameters.model_dump(), sort_keys=True, separators=(",", ":")
    ).encode()
    summary = dict(
        qualification="INVENTED_NUMERICAL_EXAMPLE_NOT_BIOLOGICAL_VALIDATION",
        seed=SEED,
        parameter_sha256=hashlib.sha256(spec_bytes).hexdigest(),
        explicit_dry_density_g_cm3=DRY_DENSITY_G_CM3,
        native_graph=native_graph,
        curved_graph=curved_graph,
        allocated_graph=allocated_graph,
        primary_branch_window_cm=parameters.features.branch_sites.settings.primary_zone_cm,
        primary_branch_sites_cm=[
            organ.primary_branch_zone_diagnostics["sites_cm"]
            for organ in simulation.organs[1]
        ],
        primary_initial_angles=[
            {
                key: report[key]
                for key in (
                    "organ_id",
                    "requested_initial_inclination_deg",
                    "realised_initial_inclination_deg",
                    "requested_initial_azimuth_deg",
                    "realised_initial_azimuth_deg",
                    "initial_angle_mismatch",
                )
            }
            for report in curvature["primaries"]
        ],
        curvature_conservation=dict(
            length_volume_mass_preserved=True,
            original_node_arcs_preserved=True,
            added_degree2_nodes=curvature["conservation"]["added_degree2_node_count"],
            descendant_boundary_repairs=len(
                curvature["descendant_boundary_interventions"]
            ),
        ),
        allocation=dict(
            total_mass_preserved=True,
            original_total_g=allocation["original_total_g"],
            achieved_total_g=allocation["achieved_total_g"],
            groups=[
                {
                    key: group[key]
                    for key in (
                        "orders",
                        "target_share",
                        "achieved_share",
                        "unlocked_diameter_scale_factor",
                    )
                }
                for group in allocation["groups"]
            ],
            primary_diameters_modified=allocation["primary_evidence_would_be_modified"],
            fine_diameter_cutoff_mm=2.5,
            fine_cutoff_migration_count=allocation["fine_cutoff_migration_count"],
            hierarchy_violation_count=allocation["hierarchy_violation_count"],
            geometry_lengths_labels_and_topology_preserved=True,
        ),
    )
    print(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
