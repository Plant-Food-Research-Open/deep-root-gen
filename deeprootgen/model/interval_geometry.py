"""One interval trajectory implementation for live organs and saved replay."""

import copy
import hashlib
import numpy as np
from ..utils.order_controls import direction_controls
from ..utils.tropism import (
    insertion_heading as default_insertion,
    row_axial_insertion_heading,
)
from .controlled_geometry import (
    unit,
    frame,
    minimal_rotation,
    apply_boundary,
    fichtl_proposal as default_proposal,
)

VERSION = "so4-construction-steps-v1"
XYZ = ["x", "y", "z"]


def construction_rng(seed, organ_id, step_index, purpose):
    """No node ID, graph rank, CDF identity or arm enters this versioned key."""
    key = hashlib.sha256(
        f"{VERSION}:{seed}:{organ_id}:{step_index}:{purpose}".encode()
    ).digest()
    return np.random.default_rng(
        np.random.SeedSequence(np.frombuffer(key, dtype="<u4"))
    )


def realize_intervals(
    organ,
    partition,
    nodes,
    settings,
    seed,
    policy,
    surface_z,
    row_kappas,
    parent_tangent=None,
    *,
    rng_factory=None,
    insertion=None,
    proposal=None,
):
    step_rng = rng_factory or construction_rng
    insertion_heading = insertion or default_insertion
    fichtl_proposal = proposal or default_proposal
    oid, order, parent_id = organ["organ_id"], organ["order"], organ["parent_id"]
    parent = nodes[parent_id]
    tangent = (
        unit(
            np.array([parent[k] for k in XYZ])
            - np.array([nodes[int(parent["parent_id"])][k] for k in XYZ])
        )
        if parent_tangent is None
        else unit(parent_tangent)
    )
    control = direction_controls(settings, order)
    assigned = insertion_heading(
        tangent,
        control["theta_deg"],
        control["theta_sd_deg"],
        step_rng(seed, oid, 0, "insertion"),
    )
    row_report = None
    if row_kappas is not None:
        assigned, row_report = row_axial_insertion_heading(
            tangent, assigned, row_kappas.get(order), seed, oid, order
        )
        row_report.update(realisation_stage=VERSION, row_alignment_by_arc=[])
    assigned = unit(assigned)
    current_frame, position = frame(assigned), np.array([parent[k] for k in XYZ])
    records, mappings, arc = [], [], 0.0
    for part in partition:
        step, length = part["step_index"], part["length_cm"]
        proposed, proposal_receipt = (
            (assigned.copy(), {})
            if step == 0
            else fichtl_proposal(
                current_frame,
                length,
                order,
                settings,
                step_rng(seed, oid, step, "continuation"),
            )
        )
        boundary_receipt = {}
        accepted, endpoint, intervention = apply_boundary(
            position,
            proposed,
            length,
            surface_z,
            policy,
            step_rng(seed, oid, step, "boundary"),
            boundary_receipt,
        )
        realised = position + length * accepted
        start_fraction = 0.0
        for nid, fraction in zip(part["node_ids"], part["fractions"]):
            point = (
                realised
                if fraction == 1.0
                else position + fraction * (realised - position)
            )
            nodes[nid].update(dict(zip(XYZ, point)))
            mappings.append(
                dict(
                    node_id=nid,
                    parent_id=int(nodes[nid]["parent_id"]),
                    organ_id=oid,
                    step_index=step,
                    start_fraction=start_fraction,
                    end_fraction=fraction,
                    length_cm=float(nodes[nid]["length"]),
                )
            )
            start_fraction = fraction
        record = dict(
            organ_id=oid,
            order=order,
            step_index=step,
            length_cm=length,
            arc_start_cm=arc,
            arc_end_cm=arc + length,
            start_xyz=position.tolist(),
            proposed_heading=proposed.tolist(),
            accepted_heading=accepted.tolist(),
            proposed_endpoint=endpoint.tolist(),
            accepted_endpoint=realised.tolist(),
            boundary_intervention=intervention,
            correction_angle_rad=(
                float(np.arccos(np.clip(proposed @ accepted, -1.0, 1.0)))
                if intervention
                else 0.0
            ),
            **boundary_receipt,
            **proposal_receipt,
        )
        record["corrected_segment_length_cm"] = length if intervention else 0.0
        record["correction_arc_cm"] = length * record["correction_angle_rad"]
        records.append(record)
        if row_report is not None:
            if step == 0:
                row_report["post_boundary_heading"] = accepted.tolist()
                row_report["post_boundary_polar_angle_deg"] = float(
                    np.degrees(np.arccos(np.clip(accepted @ tangent, -1.0, 1.0)))
                )
            row_report["row_alignment_by_arc"].append(
                dict(
                    step_index=step,
                    arc_start_cm=arc,
                    arc_end_cm=arc + length,
                    row_projection=float(accepted[1]),
                    axial_row_alignment=float(accepted[1] ** 2),
                    alignment_with_insertion=float(accepted @ assigned),
                    boundary_intervention=intervention,
                )
            )
        arc += length
        current_frame = minimal_rotation(current_frame[:, 0], accepted) @ current_frame
        position = realised
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
            else "incoming_construction_step"
        ),
        assigned_angle_deg=float(
            np.degrees(np.arccos(np.clip(assigned @ tangent, -1.0, 1.0)))
        ),
        realised_angle_deg=float(
            np.degrees(
                np.arccos(
                    np.clip(
                        np.array(records[0]["accepted_heading"]) @ tangent, -1.0, 1.0
                    )
                )
            )
        ),
        initial_frame=frame(assigned).tolist(),
        construction_steps=copy.deepcopy(organ["construction_steps"]),
    )
    if row_report is not None:
        receipt["row_axial_insertion"] = row_report
    return records, mappings, receipt
