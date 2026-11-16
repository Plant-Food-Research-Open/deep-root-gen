"""Explicit, opt-in initial-tangent primary curvature in centimetres.

This table operator is independent of native construction and biological fitting.
``initial_inclination_deg`` is below horizontal; ``initial_azimuth_deg`` rotates
+x toward +y. Existing research-primary-design angles describe a chord and are
never interpreted as initial tangents here. Category/primary_id are metadata.

q is stationary normal curvature SD in rad/cm, ell is correlation length in cm,
and downward drift is rad/cm. q=None is inactive (ell/drift must be absent/zero).
q=0 with positive ell actively constructs a straight explicit initial tangent.
The exact joint OU latent transition is followed by numerical spherical/chord
integration, on global equal physical stations independent of graph fragments.
"""

import hashlib
from collections.abc import Mapping

import networkx as nx
import numpy as np

from .curvature_process import (
    ou_joint_step,
    spherical_exp_heading,
    validate_curvature_controls,
)
from .so4_controlled import (
    XYZ,
    apply_boundary,
    derived_edges,
    frame,
    minimal_rotation,
    unit,
)

VERSION = "drg-explicit-primary-initial-tangent-ou-v1"
POLICY = "minimum_angle_projection"


def primary_curvature_rng(seed, organ_id, step_index, purpose):
    """Separate versioned stream, excluding node IDs, categories and graph cuts."""
    key = hashlib.sha256(
        f"{VERSION}:{seed}:{organ_id}:{step_index}:{purpose}".encode()
    ).digest()
    return np.random.default_rng(
        np.random.SeedSequence(np.frombuffer(key, dtype="<u4"))
    )


def _number(value, name):
    if (
        isinstance(value, (bool, np.bool_))
        or not isinstance(value, (int, float, np.integer, np.floating))
        or not np.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite nonbool number")
    return float(value)


def _integer(value, name):
    if (
        isinstance(value, (bool, np.bool_))
        or not isinstance(value, (int, np.integer))
        or value < 0
    ):
        raise ValueError(f"{name} must be an explicit nonnegative integer")
    return int(value)


def _entries(entries, nodes, q, ell, drift):
    if isinstance(entries, Mapping):
        records = []
        for oid, entry in entries.items():
            if not isinstance(entry, Mapping) or (
                "organ_id" in entry and entry["organ_id"] != oid
            ):
                raise ValueError("Primary mapping keys must match explicit organ_id")
            records.append(dict(entry, organ_id=oid))
    elif isinstance(entries, list):
        records = entries
    else:
        raise ValueError("primary_entries must be an explicit mapping or list")
    allowed = {
        "organ_id",
        "initial_inclination_deg",
        "initial_azimuth_deg",
        "category",
        "primary_id",
        "curvature_sd_rad_cm",
        "correlation_length_cm",
        "downward_drift_rad_cm",
    }
    result = {}
    primary_ids = set(nodes.loc[nodes.order.eq(1), "organ_id"])
    for entry in records:
        if not isinstance(entry, Mapping) or set(entry) - allowed:
            raise ValueError(
                "Use explicit initial-tangent fields; unsupported primary entry fields"
            )
        oid = _integer(entry.get("organ_id"), "organ_id")
        if oid not in primary_ids or oid in result:
            raise ValueError("Primary entries need unique existing order1 organ IDs")
        angle = _number(entry.get("initial_inclination_deg"), "initial_inclination_deg")
        azimuth = _number(entry.get("initial_azimuth_deg"), "initial_azimuth_deg")
        if not -90 <= angle <= 90 or not -180 <= azimuth <= 180:
            raise ValueError(
                "Initial inclination must be -90..90 and azimuth -180..180 degrees"
            )
        controls = validate_curvature_controls(
            entry.get("curvature_sd_rad_cm", q),
            entry.get("correlation_length_cm", ell),
            entry.get("downward_drift_rad_cm", drift),
        )
        alpha, phi = np.radians([angle, azimuth])
        heading = np.array(
            [np.cos(alpha) * np.cos(phi), np.cos(alpha) * np.sin(phi), -np.sin(alpha)]
        )
        result[oid] = (dict(entry), controls, unit(heading))
    if not result:
        raise ValueError("primary_entries must not be empty")
    return result


def _audit(nodes, edges):
    """Audit actual exported geometry, never rely solely on stored lengths."""
    required = {
        "node_id",
        "parent_id",
        "organ_id",
        "order",
        "segment_rank",
        "length",
        "diameter",
        "root_tissue_density",
        *XYZ,
    }
    if not required.issubset(nodes.columns) or not {"parent_id", "child_id"}.issubset(
        edges.columns
    ):
        raise ValueError("Expected native node and edge table columns")
    if not nodes.node_id.is_unique or nodes.empty:
        raise ValueError("Nodes must have unique IDs")
    for name in ("node_id", "organ_id", "order", "segment_rank"):
        if any(
            isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, np.integer))
            for v in nodes[name]
        ):
            raise ValueError(f"{name} must contain integers")
    if "invalid_root" in nodes and any(
        not isinstance(v, (bool, np.bool_)) for v in nodes.invalid_root
    ):
        raise ValueError("invalid_root must contain explicit boolean flags")
    numeric = nodes[[*XYZ, "length", "diameter", "root_tissue_density"]].to_numpy(float)
    if not np.isfinite(numeric).all() or (numeric[:, 3:] < 0).any():
        raise ValueError(
            "Graph geometry/material values must be finite and nonnegative"
        )
    if not nodes.order.between(0, 5).all() or nodes.order.eq(0).sum() != 1:
        raise ValueError("Expected one base and root orders1..5")
    roots = nodes.loc[nodes.order.gt(0)]
    expected = list(zip(roots.parent_id, roots.node_id))
    pairs = list(zip(edges.parent_id, edges.child_id))
    graph = nx.DiGraph(pairs)
    if (
        len(pairs) != len(expected)
        or set(pairs) != set(expected)
        or set(graph.nodes) != set(nodes.node_id)
        or not nx.is_arborescence(graph)
    ):
        raise ValueError(
            "Graph must be a connected directed tree matching node parent references"
        )
    base_id = int(nodes.loc[nodes.order.eq(0), "node_id"].iloc[0])
    if graph.in_degree(base_id) != 0:
        raise ValueError("Base must be the rooted-tree origin")
    lookup = nodes.set_index("node_id")
    lengths = np.linalg.norm(
        roots[XYZ].to_numpy(float) - lookup.loc[roots.parent_id, XYZ].to_numpy(float),
        axis=1,
    )
    stored = roots.length.to_numpy(float)
    if np.any(stored <= 0) or not np.allclose(lengths, stored, rtol=1e-9, atol=0):
        raise ValueError(
            "Actual exported edge lengths disagree with positive stored lengths"
        )
    # Gather and sort once; keep per-organ reductions in the same segment-rank
    # order as before, including independent cumulative sums for arc identities.
    ids = roots.node_id.to_numpy()
    parents = roots.parent_id.to_numpy()
    organs = roots.organ_id.to_numpy()
    orders = roots.order.to_numpy()
    ranks = roots.segment_rank.to_numpy()
    parent_orders = lookup.loc[parents, "order"].to_numpy()
    diameters = roots.diameter.to_numpy(float)
    densities = roots.root_tissue_density.to_numpy(float)
    permutation = np.lexsort((ranks, organs))
    sorted_organs = organs[permutation]
    boundaries = np.r_[0, np.flatnonzero(sorted_organs[1:] != sorted_organs[:-1]) + 1, len(roots)]
    moments, arcs, counts = {}, {}, {}
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        take = permutation[start:end]
        oid = int(organs[take[0]])
        chain_ids, chain_parents = ids[take], parents[take]
        chain_orders, chain_ranks = orders[take], ranks[take]
        if (
            not np.all(chain_orders == chain_orders[0])
            or np.any(chain_ranks[1:] == chain_ranks[:-1])
            or not np.array_equal(chain_parents[1:], chain_ids[:-1])
            or chain_parents[0] in chain_ids
        ):
            raise ValueError("Each organ must be one ordered unbranched chain")
        if int(chain_orders[0]) != int(parent_orders[take[0]]) + 1:
            raise ValueError("Organ parent must have preceding root order")
        actual = lengths[take]
        d2 = diameters[take] ** 2
        moments[oid] = [
            float(actual.sum()),
            float(actual @ d2),
            float(actual @ (d2 * densities[take])),
        ]
        if not np.isfinite(moments[oid]).all():
            raise ValueError("Derived length/d²L/mass moments must be finite")
        arcs.update({int(nid): float(arc) for nid, arc in zip(chain_ids, np.cumsum(stored[take]))})
        order = int(chain_orders[0])
        counts[order] = counts.get(order, 0) + 1
    return moments, arcs, counts


def _physical_curve(
    position, total, cap, assigned, controls, seed, oid, surface, strict
):
    count = int(np.ceil(total / cap))
    arcs = np.linspace(0.0, total, count + 1)
    current_frame = frame(assigned)
    q, ell = controls["curvature_sd_rad_cm"], controls["correlation_length_cm"]
    curvature = q * primary_curvature_rng(
        seed, oid, 0, "stationary_curvature_start"
    ).normal(size=2)
    records = []
    for index, (start, end) in enumerate(zip(arcs[:-1], arcs[1:])):
        length = end - start
        old_curvature = curvature.copy()
        curvature, integral = ou_joint_step(
            curvature,
            length,
            q,
            ell,
            primary_curvature_rng(seed, oid, index, "joint_curvature_integral"),
        )
        tangent = current_frame[:, 0]
        down = np.array([0.0, 0.0, -1.0])
        drift = controls["tropism_drift_rad_cm"] * (down - tangent * (tangent @ down))
        turn = integral + length * (current_frame[:, 1:].T @ drift)
        proposed = (
            assigned.copy()
            if index == 0
            else spherical_exp_heading(current_frame, turn)
        )
        receipt = {}
        accepted, proposed_endpoint, intervention = apply_boundary(
            position,
            proposed,
            length,
            surface,
            POLICY,
            primary_curvature_rng(seed, oid, index, "boundary"),
            receipt,
        )
        if strict and index == 0 and intervention:
            raise ValueError(
                "Initial tangent requires soil projection: strict initial-angle mismatch"
            )
        endpoint = position + length * accepted
        records.append(
            dict(
                step_index=index,
                arc_start_cm=float(start),
                arc_end_cm=float(end),
                length_cm=float(length),
                start_xyz=position.tolist(),
                accepted_endpoint=endpoint.tolist(),
                proposed_endpoint=proposed_endpoint.tolist(),
                proposed_heading=proposed.tolist(),
                accepted_heading=accepted.tolist(),
                boundary_intervention=intervention,
                correction_angle_rad=(
                    float(np.arccos(np.clip(proposed @ accepted, -1.0, 1.0)))
                    if intervention
                    else 0.0
                ),
                curvature_start_rad_cm=old_curvature.tolist(),
                curvature_end_rad_cm=curvature.tolist(),
                integrated_curvature_rad=integral.tolist(),
                integrated_turn_rad=turn.tolist(),
                integrated_turn_applied=index != 0,
                **receipt,
            )
        )
        current_frame = minimal_rotation(tangent, accepted) @ current_frame
        position = endpoint
    return records


def _try_unprojected_subtree(daughter, anchor, rotation, child_map, old, working, surface):
    """Batch unchanged-rotation edges; defer every crossing to sequential repair.

    Two normalisations reproduce the proposal and boundary normalisations. The
    topological accumulation still uses each stored edge length, rather than
    assuming recorded lengths equal measured chords beyond audit tolerance.
    No RNG is needed unless a crossing occurs; the fallback retains its keys.
    """
    pending, ids = [daughter], []
    while pending:
        child = pending.pop()
        ids.append(child)
        pending.extend(child_map.get(child, []))
    rows = old.loc[ids]
    parents = rows.parent_id.to_numpy()
    vectors = rows[XYZ].to_numpy(float) - old.loc[parents, XYZ].to_numpy(float)
    proposed = vectors @ rotation.T
    norms = np.linalg.norm(proposed, axis=1)
    if not np.isfinite(norms).all() or np.any(norms <= 1e-12):
        return False  # Preserve unit()'s original degenerate-direction failure.
    proposed /= norms[:, None]
    proposed /= np.linalg.norm(proposed, axis=1)[:, None]
    steps = rows.length.to_numpy(float)[:, None] * proposed
    positions = np.empty_like(steps)
    parent_positions = {anchor: -1}
    origin = working.loc[anchor, XYZ].to_numpy(float)
    for index, (child, parent) in enumerate(zip(ids, parents)):
        parent_index = parent_positions[parent]
        positions[index] = (origin if parent_index == -1 else positions[parent_index]) + steps[index]
        parent_positions[child] = index
    # A conservative arithmetic envelope prevents batched-dot roundoff from
    # deciding a surface intervention differently from the sequential route.
    # This selects an implementation path only, never a new boundary tolerance.
    envelope = 128 * np.finfo(float).eps * (
        abs(surface) + np.abs(origin).sum() + np.cumsum(np.abs(steps).sum(axis=1))
    )
    if not np.isfinite(positions).all() or np.any(positions[:, 2] >= surface - envelope):
        return False
    working.loc[ids, XYZ] = positions
    return True


def _reattach_daughters(
    ids, incoming, oid, child_map, old, working, old_arcs, seed, surface, diagnostics
):
    """Rotate each daughter subtree using the incoming chord at its old arc."""
    for nid in ids:
        daughters = [
            child
            for child in child_map.get(nid, [])
            if int(old.loc[child, "organ_id"]) != oid
        ]
        if not daughters:
            continue
        old_tangent = unit(
            old.loc[nid, XYZ].to_numpy(float)
            - old.loc[int(old.loc[nid, "parent_id"]), XYZ].to_numpy(float)
        )
        rotation = minimal_rotation(old_tangent, incoming[nid])
        for daughter in daughters:
            diagnostics["attachments"].append(
                dict(
                    child_organ_id=int(old.loc[daughter, "organ_id"]),
                    primary_organ_id=oid,
                    parent_node_id=int(nid),
                    attachment_arc_cm=old_arcs[nid],
                    old_primary_tangent=old_tangent.tolist(),
                    new_primary_tangent=incoming[nid].tolist(),
                    rotation=rotation.tolist(),
                )
            )
            if _try_unprojected_subtree(daughter, nid, rotation, child_map, old, working, surface):
                continue
            pending = [(daughter, rotation)]
            while pending:
                child, current_rotation = pending.pop()
                parent = int(old.loc[child, "parent_id"])
                length = float(old.loc[child, "length"])
                old_vector = old.loc[child, XYZ].to_numpy(float) - old.loc[
                    parent, XYZ
                ].to_numpy(float)
                proposed = unit(current_rotation @ old_vector)
                start = working.loc[parent, XYZ].to_numpy(float)
                accepted, proposed_endpoint, intervention = apply_boundary(
                    start,
                    proposed,
                    length,
                    surface,
                    POLICY,
                    primary_curvature_rng(
                        seed,
                        int(old.loc[child, "organ_id"]),
                        int(old.loc[child, "segment_rank"]),
                        "descendant_boundary",
                    ),
                )
                working.loc[child, XYZ] = start + length * accepted
                if intervention:
                    diagnostics["descendant_boundary_interventions"].append(
                        dict(
                            node_id=child,
                            organ_id=int(old.loc[child, "organ_id"]),
                            order=int(old.loc[child, "order"]),
                            proposed_heading=proposed.tolist(),
                            accepted_heading=accepted.tolist(),
                            proposed_endpoint=proposed_endpoint.tolist(),
                            length_cm=length,
                            correction_angle_rad=float(
                                np.arccos(np.clip(proposed @ accepted, -1.0, 1.0))
                            ),
                        )
                    )
                    current_rotation = (
                        minimal_rotation(proposed, accepted) @ current_rotation
                    )
                pending.extend(
                    (descendant, current_rotation)
                    for descendant in child_map.get(child, [])
                )


def _roundoff_stage_diagnostics(enabled):
    if not isinstance(enabled, (bool, np.bool_)):
        raise ValueError("reconcile_length_roundoff must be a strict boolean")
    return {} if enabled else None


def _optional_length_roundoff(nodes, edges, stage_diagnostics, stage):
    if stage_diagnostics is None:
        return nodes, edges
    # Local import: the optional adapter imports the unchanged _audit.
    from .native_roundoff import reconcile_native_edge_lengths
    result, result_edges, report = reconcile_native_edge_lengths(nodes, edges)
    stage_diagnostics[stage] = report
    return result, result_edges


def curve_primary_roots(
    nodes,
    edges,
    primary_entries,
    *,
    seed,
    surface_z_cm=0.0,
    max_step_cm=2.0,
    curvature_sd_rad_cm=None,
    correlation_length_cm=None,
    downward_drift_rad_cm=0.0,
    strict_initial_angle=False,
    reconcile_length_roundoff=False,
):
    """Return copied (nodes, edges, diagnostics), conserving cylinders and arcs.

    Entries may select a subset of existing primary organs. All root orders1..5
    are retained. Original IDs and material breaks survive; physical vertices
    add only degree2 nodes. Daughters rotate from the old incoming primary
    tangent to the accepted local tangent at the same attachment node/arc.
    At exact physical knots the incoming chord defines the local tangent.
    Surface repairs rotate downstream subtrees while preserving each edge length.
    No counts, lengths, diameters, classes or defaults are fitted or changed.
    Explicit reconcile_length_roundoff=True admits only the separately guarded
    stored-length metadata reconciliation at input/output; original moment and
    arc conservation checks remain unchanged and may still reject the result.
    """
    roundoff_stages = _roundoff_stage_diagnostics(reconcile_length_roundoff)
    seed = _integer(seed, "seed")
    surface = _number(surface_z_cm, "surface_z_cm")
    cap = _number(max_step_cm, "max_step_cm")
    if cap <= 0 or not isinstance(strict_initial_angle, (bool, np.bool_)):
        raise ValueError(
            "max_step_cm must be positive and strict_initial_angle boolean"
        )
    validate_curvature_controls(
        curvature_sd_rad_cm, correlation_length_cm, downward_drift_rad_cm
    )
    original = nodes.copy(deep=True)
    original, _ = _optional_length_roundoff(original, edges, roundoff_stages, "input")
    baseline, old_arcs, counts = _audit(original, edges)
    entries = _entries(
        primary_entries,
        original,
        curvature_sd_rad_cm,
        correlation_length_cm,
        downward_drift_rad_cm,
    )
    diagnostics = dict(
        version=VERSION,
        seed=seed,
        boundary_policy=POLICY,
        active=False,
        primaries=[],
        descendant_boundary_interventions=[],
        attachments=[],
        initial_angle_mismatch=False,
    )
    if roundoff_stages is not None:
        diagnostics["length_roundoff_reconciliation"] = roundoff_stages
    active = {oid: value for oid, value in entries.items() if value[1] is not None}
    if not active:
        diagnostics["inactive_policy"] = (
            "no_curvature_explicit_length_metadata_reconciliation"
            if roundoff_stages is not None else "exact_copy_no_orientation_or_geometry_change"
        )
        original, output_edges = _optional_length_roundoff(original, edges.copy(deep=True), roundoff_stages, "output")
        return original, output_edges, diagnostics
    if original.z.max() > surface:
        raise ValueError("Input graph starts above physical soil surface")
    diagnostics["active"] = True
    old = original.set_index("node_id", drop=False)
    working = old.copy(deep=True)
    next_id = max(int(nid) for nid in old.index) + 1
    child_map = {}
    for row in original.loc[original.order.gt(0)].itertuples():
        child_map.setdefault(int(row.parent_id), []).append(int(row.node_id))
    for oid, (entry, controls, assigned) in sorted(active.items()):
        chain = old.loc[(old.order == 1) & (old.organ_id == oid)].sort_values(
            "segment_rank"
        )
        ids = chain.node_id.tolist()
        parent_id = int(chain.parent_id.iloc[0])
        original_arcs = np.cumsum(chain.length.to_numpy(float))
        total = float(original_arcs[-1])
        records = _physical_curve(
            working.loc[parent_id, XYZ].to_numpy(float),
            total,
            cap,
            assigned,
            controls,
            seed,
            oid,
            surface,
            strict_initial_angle,
        )
        physical_arcs = np.array([r["arc_end_cm"] for r in records])
        epsilon = 32 * np.finfo(float).eps * max(1.0, total)
        union = [(float(arc), int(nid), True) for arc, nid in zip(original_arcs, ids)]
        for arc in physical_arcs:
            if np.min(np.abs(original_arcs - arc)) > epsilon:
                union.append((float(arc), next_id, False))
                next_id += 1
        union.sort()
        previous_arc, previous_id = 0.0, parent_id
        incoming = {}
        for rank, (arc, nid, retained) in enumerate(
            union, int(chain.segment_rank.iloc[0])
        ):
            index = min(
                int(np.searchsorted(physical_arcs, arc - epsilon, side="left")),
                len(records) - 1,
            )
            record = records[index]
            tangent = np.asarray(record["accepted_heading"])
            if not retained:
                source_index = min(
                    int(np.searchsorted(original_arcs, arc, side="left")),
                    len(chain) - 1,
                )
                row = chain.iloc[source_index].copy()
                row["node_id"] = nid
                working.loc[nid] = row
            offset = np.clip(arc - record["arc_start_cm"], 0.0, record["length_cm"])
            working.loc[nid, XYZ] = np.asarray(record["start_xyz"]) + offset * tangent
            working.loc[nid, ["parent_id", "segment_rank", "length"]] = [
                previous_id,
                rank,
                arc - previous_arc,
            ]
            incoming[nid] = tangent
            previous_arc, previous_id = arc, nid
        _reattach_daughters(
            ids,
            incoming,
            oid,
            child_map,
            old,
            working,
            old_arcs,
            seed,
            surface,
            diagnostics,
        )
        realised = np.asarray(records[0]["accepted_heading"])
        mismatch = bool(records[0]["boundary_intervention"])
        diagnostics["initial_angle_mismatch"] |= mismatch
        diagnostics["primaries"].append(
            dict(
                organ_id=oid,
                entry=entry,
                controls=controls,
                requested_initial_heading=assigned.tolist(),
                realised_initial_heading=realised.tolist(),
                requested_initial_inclination_deg=float(
                    entry["initial_inclination_deg"]
                ),
                realised_initial_inclination_deg=float(
                    np.degrees(-np.arcsin(np.clip(realised[2], -1.0, 1.0)))
                ),
                requested_initial_azimuth_deg=float(entry["initial_azimuth_deg"]),
                realised_initial_azimuth_deg=float(
                    np.degrees(np.arctan2(realised[1], realised[0]))
                ),
                initial_angle_mismatch=mismatch,
                physical_steps=records,
                root_boundary_interventions=sum(
                    r["boundary_intervention"] for r in records
                ),
            )
        )
    result = working.reset_index(drop=True).astype(original.dtypes.to_dict())
    exported_edges = derived_edges(result)
    result, exported_edges = _optional_length_roundoff(result, exported_edges, roundoff_stages, "output")
    after, after_arcs, after_counts = _audit(result, exported_edges)
    if baseline.keys() != after.keys() or counts != after_counts:
        raise ValueError("Primary curvature changed biological root identities/counts")
    for oid in baseline:
        if not np.allclose(after[oid], baseline[oid], rtol=1e-9, atol=0):
            raise ValueError("Actual exported length/d²L/mass conservation failed")
    for nid, arc in old_arcs.items():
        if not np.isclose(after_arcs[nid], arc, rtol=1e-9, atol=0):
            raise ValueError("Original node arc identity changed")
    if result.z.max() > surface + 1e-12:
        raise ValueError("Realised graph crosses physical soil surface")
    diagnostics["conservation"] = dict(
        actual_moments_before=baseline,
        actual_moments_after=after,
        root_counts_by_order=counts,
        retained_original_node_count=len(original),
        added_degree2_node_count=len(result) - len(original),
        relative_tolerance=1e-9,
        original_node_arc_identity_preserved=True,
    )
    return result, exported_edges, diagnostics
