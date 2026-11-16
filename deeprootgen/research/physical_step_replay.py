"""Optional cap-based physical integration of authenticated controlled D INITIALs.

This separately versioned research operator introduces no native simulation
setting. Construction lengths and their sampler receipts remain authoritative;
physical stations subdivide those intervals independently of graph cuts. Sigma
retains the existing rad/sqrt(cm) rule. Candidate counts depend on step
length, so this is a new stochastic operator, not grid-invariant or native
Fichtl replay. These are numerical, not time, steps.
"""

import copy
import hashlib

import numpy as np
import pandas as pd

from ..utils.order_controls import direction_controls
from ..utils.tropism import (
    insertion_heading,
    order_sigma_metadata,
    row_axial_insertion_heading,
    validate_row_axial_kappas,
)
from .construction_step_replay import (
    GRID,
    _replay_organ,
    _scope,
    replay_construction_steps,
    step_rng,
    validate_construction_metadata,
)
from .so4_controlled import (
    XYZ,
    apply_boundary,
    derived_edges,
    fichtl_proposal,
    frame,
    invariant_hashes,
    minimal_rotation,
    unit,
    validate_geometry,
    validate_saved_order_controls,
)

from .curvature_process import (
    VERSION as OU_VERSION,
    curvature_rng,
    ou_joint_step,
    spherical_exp_heading,
    validate_curvature_controls,
)

VERSION = "so4-physical-steps-v1"


def physical_step_rng(seed, organ_id, step_index, purpose):
    """Versioned continuation/boundary stream; excludes graph nodes and fragments."""
    key = hashlib.sha256(
        f"{VERSION}:{seed}:{organ_id}:{step_index}:{purpose}".encode()
    ).digest()
    return np.random.default_rng(
        np.random.SeedSequence(np.frombuffer(key, dtype="<u4"))
    )


def _selected_orders(orders, maximum):
    try:
        selected = tuple(orders)
    except TypeError as error:
        raise ValueError(
            "Physical orders must be unique explicit integers 2..max_order"
        ) from error
    if any(
        isinstance(order, (bool, np.bool_))
        or not isinstance(order, (int, np.integer))
        or not 2 <= order <= maximum
        for order in selected
    ) or len(set(selected)) != len(selected):
        raise ValueError(
            "Physical orders must be unique explicit integers 2..max_order"
        )
    return tuple(sorted(int(order) for order in selected))


def _physical_stations(partition, cap):
    """Equal substeps per authenticated interval; never use graph endpoints."""
    stations, arc = [], 0.0
    for part in partition:
        count = int(np.ceil(part["length_cm"] / cap))
        for local in range(count):
            start = arc + part["length_cm"] * local / count
            end = arc + part["length_cm"] * (local + 1) / count
            stations.append((start, end, part["step_index"]))
        arc += part["length_cm"]
    return stations


def _ou_proposal(moving_frame, curvature, length, controls, seed, oid, index, assigned):
    """Advance latent curvature even on the preserved insertion chord."""
    next_curvature, integral = ou_joint_step(
        curvature,
        length,
        controls["curvature_sd_rad_cm"],
        controls["correlation_length_cm"],
        curvature_rng(seed, oid, index, "joint_curvature_integral"),
    )
    tangent = moving_frame[:, 0]
    down = np.array([0.0, 0.0, -1.0])
    row = np.array([0.0, 1.0, 0.0])
    row_sign = float(np.sign(assigned[1]))
    drift = controls["tropism_drift_rad_cm"] * (
        down - tangent * (tangent @ down)
    ) + controls["row_drift_rad_cm"] * row_sign * (row - tangent * (tangent @ row))
    drift_angle = length * (moving_frame[:, 1:].T @ drift)
    total_angle = integral + drift_angle
    proposed = (
        assigned.copy()
        if index == 0
        else spherical_exp_heading(moving_frame, total_angle)
    )
    return (
        proposed,
        next_curvature,
        dict(
            curvature_start_rad_cm=curvature.tolist(),
            curvature_end_rad_cm=next_curvature.tolist(),
            integrated_curvature_rad=integral.tolist(),
            drift_turn_rad=drift_angle.tolist(),
            integrated_turn_rad=total_angle.tolist(),
            integrated_turn_magnitude_rad=float(np.hypot(*total_angle)),
            integrated_turn_applied=index != 0,
            insertion_chord=index == 0,
            row_drift_frozen_sign=row_sign,
            candidate_selection="none_unselected_ou",
            latent_boundary_policy="retain_curvature_transport_frame_through_accepted_heading",
            antiparallel_transport_convention="deterministic_least_aligned_axis",
        ),
    )


def _physical_organ(
    organ,
    partition,
    nodes,
    settings,
    seed,
    policy,
    surface_z,
    row_kappas,
    cap,
    next_id,
    parent_tangent,
    curvature_controls=None,
):
    oid, order, parent_id = organ["organ_id"], organ["order"], organ["parent_id"]
    parent = nodes.loc[parent_id]
    tangent = (
        unit(
            parent[XYZ].to_numpy(float)
            - nodes.loc[int(parent.parent_id), XYZ].to_numpy(float)
        )
        if parent_tangent is None
        else unit(parent_tangent)
    )
    control = direction_controls(settings, order)
    # Preserve the existing insertion innovation; only continuation/boundary
    # integration uses the new physical-step stream.
    assigned = insertion_heading(
        tangent,
        control["theta_deg"],
        control["theta_sd_deg"],
        step_rng(seed, oid, 0, "insertion"),
    )
    route = VERSION if curvature_controls is None else OU_VERSION
    row_report = None
    if row_kappas is not None:
        assigned, row_report = row_axial_insertion_heading(
            tangent,
            assigned,
            row_kappas.get(order),
            seed,
            oid,
            order,
        )
        row_report.update(realisation_stage=route, row_alignment_by_arc=[])
    assigned = unit(assigned)
    current_frame, position = frame(assigned), parent[XYZ].to_numpy(float)
    curvature = None
    if curvature_controls is not None:
        curvature = curvature_controls["curvature_sd_rad_cm"] * curvature_rng(
            seed, oid, 0, "stationary_curvature_start"
        ).normal(size=2)
    records = []
    for index, (start, end, construction_index) in enumerate(
        _physical_stations(partition, cap)
    ):
        length = end - start
        if curvature_controls is None:
            proposed, proposal_receipt = (
                (assigned.copy(), {})
                if index == 0
                else fichtl_proposal(
                    current_frame,
                    length,
                    order,
                    settings,
                    physical_step_rng(seed, oid, index, "continuation"),
                )
            )
        else:
            proposed, curvature, proposal_receipt = _ou_proposal(
                current_frame,
                curvature,
                length,
                curvature_controls,
                seed,
                oid,
                index,
                assigned,
            )
        boundary_receipt = {}
        accepted, endpoint, intervention = apply_boundary(
            position,
            proposed,
            length,
            surface_z,
            policy,
            (
                physical_step_rng(seed, oid, index, "boundary")
                if curvature_controls is None
                else curvature_rng(seed, oid, index, "boundary")
            ),
            boundary_receipt,
        )
        if curvature_controls is not None:
            proposal_receipt["antiparallel_frame_transport"] = bool(
                current_frame[:, 0] @ accepted < 0
                and np.linalg.norm(np.cross(current_frame[:, 0], accepted)) <= 1e-12
            )
        realised = position + length * accepted
        correction = (
            float(np.arccos(np.clip(proposed @ accepted, -1.0, 1.0)))
            if intervention
            else 0.0
        )
        records.append(
            dict(
                organ_id=oid,
                order=order,
                step_index=index,
                construction_step_index=construction_index,
                length_cm=length,
                arc_start_cm=start,
                arc_end_cm=end,
                start_xyz=position.tolist(),
                proposed_heading=proposed.tolist(),
                accepted_heading=accepted.tolist(),
                proposed_endpoint=endpoint.tolist(),
                accepted_endpoint=realised.tolist(),
                boundary_intervention=intervention,
                correction_angle_rad=correction,
                corrected_segment_length_cm=length if intervention else 0.0,
                correction_arc_cm=length * correction,
                **boundary_receipt,
                **proposal_receipt,
            )
        )
        if row_report is not None:
            if index == 0:
                row_report["post_boundary_heading"] = accepted.tolist()
                row_report["post_boundary_polar_angle_deg"] = float(
                    np.degrees(np.arccos(np.clip(accepted @ tangent, -1.0, 1.0)))
                )
            row_report["row_alignment_by_arc"].append(
                dict(
                    step_index=index,
                    arc_start_cm=start,
                    arc_end_cm=end,
                    row_projection=float(accepted[1]),
                    axial_row_alignment=float(accepted[1] ** 2),
                    alignment_with_insertion=float(accepted @ assigned),
                    boundary_intervention=intervention,
                )
            )
        current_frame = minimal_rotation(current_frame[:, 0], accepted) @ current_frame
        position = realised

    original = nodes.loc[organ["node_ids"]].copy(deep=True)
    original_arcs = np.cumsum(original.length.to_numpy(float))
    physical_arcs = np.array([record["arc_end_cm"] for record in records])
    # Floating arithmetic can encode the same station with adjacent floats.
    # Keep the exact original arc/ID in that case; never merge original nodes.
    epsilon = 32 * np.finfo(float).eps * max(1.0, physical_arcs[-1])
    union = [
        (float(arc), int(nid), True)
        for arc, nid in zip(original_arcs, organ["node_ids"])
    ]
    for arc in physical_arcs:
        if np.min(np.abs(original_arcs - arc)) > epsilon:
            union.append((float(arc), next_id, False))
            next_id += 1
    union.sort(key=lambda value: value[0])
    previous_arc, previous_id = 0.0, parent_id
    mappings, incoming = [], {}
    first_rank = int(original.iloc[0].segment_rank)
    for rank, (arc, nid, retained) in enumerate(union, first_rank):
        physical_index = min(
            int(np.searchsorted(physical_arcs, arc - epsilon, side="left")),
            len(records) - 1,
        )
        record = records[physical_index]
        offset = np.clip(arc - record["arc_start_cm"], 0.0, record["length_cm"])
        position = (
            np.asarray(record["accepted_endpoint"])
            if abs(arc - record["arc_end_cm"]) <= epsilon
            else np.asarray(record["start_xyz"])
            + offset * np.asarray(record["accepted_heading"])
        )
        if not retained:
            source_index = min(
                int(np.searchsorted(original_arcs, arc, side="left")), len(original) - 1
            )
            row = original.iloc[source_index].copy()
            row["node_id"] = nid
            nodes.loc[nid] = row
        nodes.loc[nid, XYZ] = position
        nodes.loc[nid, ["parent_id", "segment_rank", "length"]] = [
            previous_id,
            rank,
            arc - previous_arc,
        ]
        incoming[nid] = record["accepted_heading"]
        mappings.append(
            dict(
                node_id=nid,
                parent_id=previous_id,
                organ_id=oid,
                step_index=physical_index,
                arc_start_cm=previous_arc,
                arc_end_cm=arc,
                length_cm=arc - previous_arc,
                retained_initial_node=retained,
                start_fraction=(previous_arc - record["arc_start_cm"])
                / record["length_cm"],
                end_fraction=(arc - record["arc_start_cm"]) / record["length_cm"],
            )
        )
        previous_arc, previous_id = arc, nid
    receipt = dict(
        organ_id=oid,
        order=order,
        parent_id=parent_id,
        assigned_heading=assigned.tolist(),
        realised_heading=records[0]["accepted_heading"],
        parent_tangent=tangent.tolist(),
        parent_tangent_source=(
            "frozen_primary_incoming_edge"
            if parent_tangent is None
            else "incoming_physical_step"
        ),
        assigned_angle_deg=float(
            np.degrees(np.arccos(np.clip(assigned @ tangent, -1.0, 1.0)))
        ),
        realised_angle_deg=float(
            np.degrees(
                np.arccos(
                    np.clip(
                        np.asarray(records[0]["accepted_heading"]) @ tangent, -1.0, 1.0
                    )
                )
            )
        ),
        initial_frame=frame(assigned).tolist(),
        construction_steps=copy.deepcopy(organ["construction_steps"]),
        integration_route=route,
    )
    if curvature_controls is not None:
        receipt["curvature_process"] = dict(
            **curvature_controls,
            initial_state="stationary_isotropic_normal",
            continuation="unselected_joint_ou_integral_plus_tangent_plane_drift",
            first_chord="preserved_insertion_with_latent_process_advanced",
        )
    if row_report is not None:
        receipt["row_axial_insertion"] = row_report
    return records, mappings, receipt, incoming, next_id


def _conservation(original, nodes, skeleton):
    """Check actual exported geometry and child-diameter cylinder support."""
    lookup = nodes.set_index("node_id")
    if not original.node_id.isin(nodes.node_id).all():
        raise ValueError("Physical replay lost INITIAL node IDs")
    pd.testing.assert_frame_equal(
        original.loc[original.order.le(1)].reset_index(drop=True),
        nodes.loc[nodes.order.le(1)].reset_index(drop=True),
        check_dtype=False,
        check_exact=True,
    )
    reports = []
    for organ in skeleton.payload["organs"]:
        old = original.loc[original.organ_id.eq(organ["organ_id"])].sort_values(
            "segment_rank"
        )
        chain = nodes.loc[nodes.organ_id.eq(organ["organ_id"])].sort_values(
            "segment_rank"
        )
        ids = chain.node_id.astype(int).tolist()
        if not chain.order.eq(organ["order"]).all() or chain.parent_id.astype(
            int
        ).tolist() != [organ["parent_id"], *ids[:-1]]:
            raise ValueError(
                "Physical replay changed organ topology or attachment identity"
            )
        measured = np.linalg.norm(
            chain[XYZ].to_numpy(float)
            - lookup.loc[chain.parent_id.astype(int), XYZ].to_numpy(float),
            axis=1,
        )
        expected_length = float(old.length.sum())
        expected_mass = float((old.diameter**2 * old.length).sum())
        old_density = (
            old.root_tissue_density
            if "root_tissue_density" in old
            else np.ones(len(old))
        )
        density = (
            chain.root_tissue_density.to_numpy(float)
            if "root_tissue_density" in chain
            else np.ones(len(chain))
        )
        expected_dry_mass = float(np.sum(old_density * old.diameter**2 * old.length))
        actual_length = float(measured.sum())
        actual_mass = float(np.sum(chain.diameter.to_numpy(float) ** 2 * measured))
        actual_dry_mass = float(
            np.sum(density * chain.diameter.to_numpy(float) ** 2 * measured)
        )
        if (
            not np.allclose(
                measured, chain.length.to_numpy(float), rtol=1e-9, atol=1e-12
            )
            or not np.isclose(actual_length, expected_length, rtol=1e-9, atol=0)
            or not np.isclose(actual_mass, expected_mass, rtol=1e-9, atol=0)
            or not np.isclose(actual_dry_mass, expected_dry_mass, rtol=1e-9, atol=0)
        ):
            raise ValueError(
                "Physical replay changed per-organ arc length or child-diameter cylinder mass"
            )
        reports.append(
            dict(
                organ_id=organ["organ_id"],
                initial_length_cm=expected_length,
                exported_length_cm=actual_length,
                initial_diameter2_length_cm3=expected_mass,
                exported_diameter2_length_cm3=actual_mass,
                initial_density_diameter2_length=expected_dry_mass,
                exported_density_diameter2_length=actual_dry_mass,
            )
        )
    return reports


def replay_physical_steps(
    skeleton,
    settings,
    boundary_policy="minimum_angle_projection",
    surface_z=20.0,
    max_step_cm=2.0,
    orders=(2,),
    direction_seed=None,
    curvature_sd_rad_cm=None,
    correlation_length_cm=None,
    tropism_drift_rad_cm=0.0,
    row_drift_rad_cm=0.0,
):
    """Replay selected orders with capped steps, retaining INITIAL arc landmarks.

    Empty ``orders`` delegates unchanged to construction-step replay, including
    its exact diagnostics. Other orders keep the existing construction operator
    and RNG, but follow their parent's moved attachment and incoming tangent.
    ``direction_seed`` optionally changes only direction/boundary innovations;
    source sampler authentication always uses the immutable INITIAL seed.
    Optional paired q/ell controls select a separate transported OU law with
    declared downward/row drift; they are engineering assumptions. None keeps
    the original capped Fichtl operator and its RNG/output exactly unchanged.
    """
    _, requested = _scope(skeleton, settings, "D", surface_z)
    selected = _selected_orders(orders, requested.max_order)
    curvature_controls = validate_curvature_controls(
        curvature_sd_rad_cm,
        correlation_length_cm,
        tropism_drift_rad_cm,
        row_drift_rad_cm,
    )
    if curvature_controls is not None and not selected:
        raise ValueError("Active OU curvature requires at least one selected order")
    route = VERSION if curvature_controls is None else OU_VERSION
    if direction_seed is not None and (
        isinstance(direction_seed, (bool, np.bool_))
        or not isinstance(direction_seed, (int, np.integer))
        or direction_seed < 0
    ):
        raise ValueError(
            "direction_seed must be an explicit nonnegative integer or None"
        )
    replay_seed = (
        skeleton.payload["seed"] if direction_seed is None else int(direction_seed)
    )
    if (
        isinstance(max_step_cm, (bool, np.bool_))
        or not isinstance(max_step_cm, (int, float, np.integer, np.floating))
        or not np.isfinite(max_step_cm)
        or max_step_cm <= 1e-12
    ):
        raise ValueError("max_step_cm must be finite and greater than 1e-12 cm")
    if boundary_policy != "minimum_angle_projection":
        raise ValueError("Unapproved/unsupported common boundary policy")
    if not selected and direction_seed is None:
        return replay_construction_steps(
            skeleton, "D", settings, boundary_policy, surface_z
        )
    partitions = validate_construction_metadata(skeleton)
    original = pd.DataFrame(skeleton.payload["nodes"])
    nodes = original.set_index("node_id", drop=False).copy(deep=True)
    row_kappas = validate_row_axial_kappas(
        requested.research_insertion_row_axial_kappa, requested.max_order
    )
    settings = requested.model_dump()
    steps, fragments, organs, incoming = [], [], [], {}
    next_id = int(nodes.node_id.max()) + 1
    for organ in sorted(
        skeleton.payload["organs"],
        key=lambda value: (value["order"], value["organ_id"]),
    ):
        if organ["order"] == 1:
            continue
        if organ["order"] in selected:
            records, mapping, receipt, current_incoming, next_id = _physical_organ(
                organ,
                partitions[organ["organ_id"]],
                nodes,
                settings,
                replay_seed,
                boundary_policy,
                surface_z,
                row_kappas,
                float(max_step_cm),
                next_id,
                incoming.get(organ["parent_id"]),
                curvature_controls,
            )
        else:
            records, mapping, receipt = _replay_organ(
                organ,
                partitions[organ["organ_id"]],
                nodes,
                settings,
                replay_seed,
                boundary_policy,
                surface_z,
                row_kappas,
                incoming.get(organ["parent_id"]),
            )
            current_incoming = {
                item["node_id"]: records[item["step_index"]]["accepted_heading"]
                for item in mapping
            }
            receipt["integration_route"] = "so4-construction-steps-v1"
            if incoming.get(organ["parent_id"]) is not None:
                receipt["parent_tangent_source"] = "incoming_parent_integration_step"
        for record in records:
            record["integration_route"] = receipt["integration_route"]
        incoming.update(current_incoming)
        steps.extend(records)
        fragments.extend(mapping)
        organs.append(receipt)
    nodes = nodes.reset_index(drop=True)
    for column in ("node_id", "parent_id", "organ_id", "order", "segment_rank"):
        nodes[column] = nodes[column].astype(original[column].dtype)
    edges = derived_edges(nodes)
    conservation = _conservation(original, nodes, skeleton)
    validate_geometry(nodes, edges, surface_z)
    proposals = pd.DataFrame(
        [
            dict(
                organ_id=r["organ_id"],
                order=r["order"],
                step_index=r["step_index"],
                length_cm=r["length_cm"],
                start_x=r["start_xyz"][0],
                start_y=r["start_xyz"][1],
                start_z=r["start_xyz"][2],
                proposed_x=r["proposed_endpoint"][0],
                proposed_y=r["proposed_endpoint"][1],
                proposed_z=r["proposed_endpoint"][2],
                boundary_intervention=r["boundary_intervention"],
                boundary_ulp_nudges=r["boundary_ulp_nudges"],
            )
            for r in steps
        ]
    )
    return dict(
        nodes=nodes,
        edges=edges,
        proposals=proposals,
        diagnostics=dict(
            route=route,
            grid=GRID,
            arm="D",
            seed=skeleton.payload["seed"],
            surface_z_cm=surface_z,
            source_sampler_seed=skeleton.payload["seed"],
            direction_seed=replay_seed,
            boundary_policy=boundary_policy,
            max_step_cm=float(max_step_cm),
            orders=list(selected),
            skeleton_sha256=skeleton.sha256,
            invariant_hashes=invariant_hashes(nodes),
            initial_invariant_hashes=invariant_hashes(original),
            conservation=conservation,
            organs=organs,
            physical_steps=[r for r in steps if r["integration_route"] == route],
            construction_steps=steps,
            graph_fragments=fragments,
            replays=dict(physical=1, counterfactual=0),
            proposals="One-step integration proposals from actual starts; not a coherent graph; no per-fragment searches",
            **(
                {
                    "curvature_process": dict(
                        **curvature_controls,
                        process="stationary_isotropic_ou_in_transported_coordinates",
                        candidate_selection="none",
                        tropism_drift="lambda_d * P_t(-ez)",
                        row_drift="lambda_r * sign(assigned_y) * P_t(ey)",
                        geometric_integration="spherical_exponential_then_length_preserving_chord",
                        boundary_latent_state="retained_after_projection",
                    )
                }
                if curvature_controls is not None
                else {}
            ),
            **validate_saved_order_controls(skeleton, settings),
            **order_sigma_metadata(
                requested.fichtl_sigma,
                requested.research_fichtl_sigma_by_order,
                requested.max_order,
            ),
        ),
    )
