"""Opt-in controlled D integration on retained construction steps, then cuts.

These sampled construction intervals are a numerical operator, not elongation
events or measured biological time steps. Native Fichtl semantics are separate.
"""

import copy
import hashlib
import json

import numpy as np
import pandas as pd

from ..data_model import RootSimulationModel
from ..utils.current_length import STREAM_VERSION, _cdf_arrays, select_current_length
from ..utils.tropism import insertion_heading, order_sigma_metadata, row_axial_insertion_heading, validate_row_axial_kappas
from .so4_controlled import (
    Skeleton, XYZ, apply_boundary, derived_edges, digest, fichtl_proposal,
    frame, invariant_hashes, minimal_rotation, unit, validate_geometry,
)

VERSION = "so4-construction-steps-v1"
GRID = "construction_steps_v1"


def step_rng(seed, organ_id, step_index, purpose):
    """No node ID, graph rank, CDF identity or arm enters this versioned key."""
    key = hashlib.sha256(f"{VERSION}:{seed}:{organ_id}:{step_index}:{purpose}".encode()).digest()
    return np.random.default_rng(np.random.SeedSequence(np.frombuffer(key, dtype="<u4")))


def capture_construction_steps(skeleton, simulation):
    """Export original boundary identities and positioned geometry from live nodes."""
    skeleton.verify()
    payload = copy.deepcopy(skeleton.payload)
    live = {node.node_data.node_id: node.node_data for node in simulation.G.nodes}
    lookup = {int(organ.segments[0].node_data.organ_id): organ
              for order in (2, 3) for organ in simulation.organs[order]}
    for organ in payload["organs"]:
        if organ["order"] == 1:
            continue
        source = lookup[organ["organ_id"]]
        ids = source.construction_step_boundary_node_ids
        points = [live[nid] for nid in [organ["parent_id"], *ids]]
        organ["construction_steps"] = dict(
            version=VERSION, lengths_cm=source._construction_step_lengths_cm.tolist(),
            boundary_node_ids=list(ids), positioned_boundary_xyz=[[p.x, p.y, p.z] for p in points],
            sampler=copy.deepcopy(source.construction_step_provenance),
        )
    result = Skeleton(payload, digest(payload))
    validate_construction_metadata(result)
    return result


def _scope(skeleton, settings, arm, surface_z):
    skeleton.verify()
    if arm != "D" or surface_z != 20.:
        raise ValueError("Construction-step replay only supports D and surface z=20")
    for values in (skeleton.payload["parameters"], settings):
        seed = values.get("random_seed")
        if (isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer))
                or seed < 0 or seed != skeleton.payload["seed"] or values.get("research_current_length_grid") != GRID):
            raise ValueError("Construction-step route requires active grid and matching explicit seed")
    from .so4_controlled import validate_saved_primary_yaw_reversal
    validate_saved_primary_yaw_reversal(skeleton, settings)
    saved = RootSimulationModel(**skeleton.payload["parameters"])
    requested = RootSimulationModel(**settings)
    if saved.research_current_length_grid != GRID or requested.research_current_length_grid != GRID:
        raise ValueError("Missing construction-step route")
    saved_values, requested_values = saved.model_dump(), requested.model_dump()
    for key, value in saved_values.items():
        if not key.startswith("fichtl_") and key not in {"simulation_tag", "research_insertion_row_axial_kappa", "research_fichtl_sigma_by_order"}:
            if key == "research_primary_yaw_reverse_probability" and not requested_values[key] and not value:
                continue
            if requested_values[key] != value:
                raise ValueError(f"Construction settings disagree with INITIAL: {key}")
    if saved.research_base_depth_cm is not None and saved.soil_surface_z_cm != surface_z:
        raise ValueError("INITIAL origin surface disagrees with physical surface")
    return saved, requested


def _sampler_lengths(metadata, organ, parameters, seed):
    """Authenticate recorded sampler provenance without drawing replacement lengths."""
    sampler = metadata["sampler"]
    required = {"quantile", "support_index", "normalized_weights", "cdf_sha256", "sampled_current_length_cm",
                "pre_subdivision_length_cm", "post_subdivision_length_cm"}
    if not isinstance(sampler, dict) or not required.issubset(sampler):
        raise ValueError("Missing original construction sampler provenance")
    expected = dict(stream_version=STREAM_VERSION, seed=seed, order=organ["order"],
                    expected_organ_id=organ["organ_id"], allocated_organ_id=organ["organ_id"],
                    requested_segment_count=parameters.segments_per_root)
    if any(sampler.get(key) != value for key, value in expected.items()):
        raise ValueError("Construction sampler version/seed/order/identity/count mismatch")
    support, cumulative = _cdf_arrays(parameters.research_current_length_cdfs_cm[organ["order"]])
    identity = json.dumps(dict(lengths_cm=support.tolist(), cumulative_probabilities=cumulative.tolist()),
                          sort_keys=True, separators=(",", ":"), allow_nan=False)
    if sampler.get("cdf_sha256") != hashlib.sha256(identity.encode()).hexdigest():
        raise ValueError("Construction CDF provenance mismatch")
    sampled, index = select_current_length(parameters.research_current_length_cdfs_cm[organ["order"]], sampler["quantile"])
    weights = np.asarray(sampler["normalized_weights"], dtype=float)
    lengths = np.asarray(metadata["lengths_cm"], dtype=float)
    if (lengths.shape != (parameters.segments_per_root,) or weights.shape != lengths.shape
            or not np.isfinite(lengths).all() or not np.isfinite(weights).all()
            or (lengths <= 1e-12).any() or (weights <= 0).any() or (np.diff(weights) > 0).any()
            or not np.isclose(weights.sum(), 1., rtol=0, atol=1e-8)
            or not np.allclose(lengths, sampled * weights, rtol=0, atol=1e-8)
            or sampler.get("support_index") != index):
        raise ValueError("Invalid retained construction lengths/weights")
    for value in (lengths.sum(), sampler.get("sampled_current_length_cm"),
                  sampler.get("pre_subdivision_length_cm"), sampler.get("post_subdivision_length_cm")):
        if value is None or not np.isfinite(value) or not np.isclose(value, sampled, rtol=0, atol=1e-8):
            raise ValueError("Construction total/provenance disagreement")
    return lengths


def _partition(organ, nodes, parameters, seed):
    metadata = organ.get("construction_steps")
    if not isinstance(metadata, dict) or metadata.get("version") != VERSION:
        raise ValueError("Missing or unsupported original construction partition")
    if not {"sampler", "lengths_cm", "boundary_node_ids", "positioned_boundary_xyz"}.issubset(metadata):
        raise ValueError("Missing original construction boundary metadata")
    lengths = _sampler_lengths(metadata, organ, parameters, seed)
    ids, boundaries = organ["node_ids"], metadata["boundary_node_ids"]
    if (len(ids) != len(set(ids)) or len(boundaries) != len(lengths)
            or len(boundaries) != len(set(boundaries)) or any(nid not in ids for nid in boundaries)):
        raise ValueError("Missing/duplicate construction boundaries")
    chain = nodes.loc[ids]
    if (not chain.organ_id.eq(organ["organ_id"]).all() or not chain.order.eq(organ["order"]).all()
            or list(chain.parent_id) != [organ["parent_id"], *ids[:-1]]):
        raise ValueError("Construction graph membership/order/chain mismatch")
    cumulative = np.cumsum(chain.length.to_numpy(float))
    if (chain.length.to_numpy(float) <= 1e-12).any():
        raise ValueError("Construction graph fragments must have positive lengths")
    coordinates = np.asarray(metadata["positioned_boundary_xyz"], dtype=float)
    actual = nodes.loc[[organ["parent_id"], *boundaries], XYZ].to_numpy(float)
    if coordinates.shape != actual.shape or not np.isfinite(coordinates).all() or not np.allclose(coordinates, actual, rtol=0, atol=1e-8):
        raise ValueError("Positioned construction boundaries disagree with live INITIAL")
    previous, partitions = -1, []
    for step, (boundary, arc, length) in enumerate(zip(boundaries, np.cumsum(lengths), lengths)):
        matches = np.flatnonzero(np.isclose(cumulative, arc, rtol=0, atol=1e-8))
        end = ids.index(boundary)
        if len(matches) != 1 or int(matches[0]) != end or end <= previous:
            raise ValueError("Missing/ambiguous construction boundary arc")
        fragments = ids[previous + 1:end + 1]
        fractions = np.cumsum(nodes.loc[fragments, "length"].to_numpy(float)) / length
        if not np.isclose(fractions[-1], 1., rtol=0, atol=1e-8 / length):
            raise ValueError("Construction fragments do not conserve step length")
        # Fractions are recorded arc fractions; the authenticated boundary is
        # the exact step endpoint, not a rescaling of interior fragments.
        fractions[-1] = 1.
        original = nodes.loc[fragments, XYZ].to_numpy(float)
        expected = coordinates[step] + fractions[:, None] * (coordinates[step + 1] - coordinates[step])
        if (not np.isclose(np.linalg.norm(coordinates[step + 1] - coordinates[step]), length, rtol=0, atol=1e-8)
                or not np.allclose(original, expected, rtol=0, atol=1e-8)):
            raise ValueError("Missing original corner or noncollinear construction fragments")
        partitions.append(dict(step_index=step, length_cm=float(length), boundary_node_id=boundary,
                               node_ids=fragments, fractions=fractions.tolist()))
        previous = end
    if previous != len(ids) - 1:
        raise ValueError("Construction partition does not cover organ apex")
    return partitions


def validate_construction_metadata(skeleton):
    """Read-only preflight for a captured INITIAL; no simulation or length draws."""
    parameters, _ = _scope(skeleton, skeleton.payload["parameters"], "D", 20.)
    nodes, edges = pd.DataFrame(skeleton.payload["nodes"]), pd.DataFrame(skeleton.payload["edges"])
    validate_geometry(nodes, edges)
    if nodes.loc[nodes.order.le(1), "z"].max() > 20.:
        raise ValueError("Frozen primary scaffold exceeds physical soil surface")
    lookup = nodes.set_index("node_id", drop=False)
    return {organ["organ_id"]: _partition(organ, lookup, parameters, skeleton.payload["seed"])
            for organ in skeleton.payload["organs"] if organ["order"] > 1}


def _replay_organ(organ, partition, nodes, settings, seed, policy, surface_z, row_kappas, parent_tangent=None):
    oid, order, parent_id = organ["organ_id"], organ["order"], organ["parent_id"]
    parent = nodes.loc[parent_id]
    tangent = (unit(parent[XYZ].to_numpy(float) - nodes.loc[int(parent.parent_id), XYZ].to_numpy(float))
               if parent_tangent is None else unit(parent_tangent))
    assigned = insertion_heading(tangent, settings[f"fichtl_theta{order}_deg"], settings[f"fichtl_theta{order}_sd_deg"],
                                 step_rng(seed, oid, 0, "insertion"))
    row_report = None
    if row_kappas is not None:
        assigned, row_report = row_axial_insertion_heading(tangent, assigned, row_kappas.get(order), seed, oid, order)
        row_report.update(realisation_stage=VERSION, row_alignment_by_arc=[])
    assigned = unit(assigned)
    current_frame, position = frame(assigned), parent[XYZ].to_numpy(float)
    records, mappings, arc = [], [], 0.
    for part in partition:
        step, length = part["step_index"], part["length_cm"]
        proposed, proposal_receipt = (assigned.copy(), {}) if step == 0 else fichtl_proposal(
            current_frame, length, order, settings, step_rng(seed, oid, step, "continuation"))
        boundary_receipt = {}
        accepted, endpoint, intervention = apply_boundary(
            position, proposed, length, surface_z, policy,
            step_rng(seed, oid, step, "boundary"), boundary_receipt,
        )
        realised = position + length * accepted
        start_fraction = 0.
        for nid, fraction in zip(part["node_ids"], part["fractions"]):
            nodes.loc[nid, XYZ] = realised if fraction == 1. else position + fraction * (realised - position)
            mappings.append(dict(node_id=nid, parent_id=int(nodes.loc[nid, "parent_id"]), organ_id=oid,
                                 step_index=step, start_fraction=start_fraction, end_fraction=fraction,
                                 length_cm=float(nodes.loc[nid, "length"])))
            start_fraction = fraction
        record = dict(organ_id=oid, order=order, step_index=step, length_cm=length,
                      arc_start_cm=arc, arc_end_cm=arc + length, start_xyz=position.tolist(),
                      proposed_heading=proposed.tolist(), accepted_heading=accepted.tolist(),
                      proposed_endpoint=endpoint.tolist(), accepted_endpoint=realised.tolist(),
                      boundary_intervention=intervention,
                      correction_angle_rad=float(np.arccos(np.clip(proposed @ accepted, -1., 1.))) if intervention else 0.,
                      **boundary_receipt, **proposal_receipt)
        record["corrected_segment_length_cm"] = length if intervention else 0.
        record["correction_arc_cm"] = length * record["correction_angle_rad"]
        records.append(record)
        if row_report is not None:
            if step == 0:
                row_report["post_boundary_heading"] = accepted.tolist()
                row_report["post_boundary_polar_angle_deg"] = float(np.degrees(np.arccos(np.clip(accepted @ tangent, -1., 1.))))
            row_report["row_alignment_by_arc"].append(dict(
                step_index=step, arc_start_cm=arc, arc_end_cm=arc + length,
                row_projection=float(accepted[1]), axial_row_alignment=float(accepted[1]**2),
                alignment_with_insertion=float(accepted @ assigned), boundary_intervention=intervention,
            ))
        arc += length
        current_frame = minimal_rotation(current_frame[:, 0], accepted) @ current_frame
        position = realised
    receipt = dict(organ_id=oid, order=order, parent_id=parent_id, assigned_heading=assigned.tolist(),
                   realised_heading=records[0]["accepted_heading"], parent_tangent=tangent.tolist(),
                   parent_tangent_source="frozen_primary_incoming_edge" if parent_tangent is None else "incoming_construction_step",
                   assigned_angle_deg=float(np.degrees(np.arccos(np.clip(assigned @ tangent, -1., 1.)))),
                   realised_angle_deg=float(np.degrees(np.arccos(np.clip(np.array(records[0]["accepted_heading"]) @ tangent, -1., 1.)))),
                   initial_frame=frame(assigned).tolist(), construction_steps=copy.deepcopy(organ["construction_steps"]))
    if row_report is not None:
        receipt["row_axial_insertion"] = row_report
    return records, mappings, receipt


def replay_construction_steps(skeleton, arm, settings, boundary_policy, surface_z=20.):
    """One controlled D replay: search/project steps once, interpolate fragments."""
    _, requested = _scope(skeleton, settings, arm, surface_z)
    partitions = validate_construction_metadata(skeleton)
    original = pd.DataFrame(skeleton.payload["nodes"])
    nodes = original.set_index("node_id", drop=False).copy(deep=True)
    row_kappas = validate_row_axial_kappas(requested.research_insertion_row_axial_kappa)
    steps, fragments, organs, incoming = [], [], [], {}
    for organ in sorted(skeleton.payload["organs"], key=lambda value: (value["order"], value["organ_id"])):
        if organ["order"] == 1:
            continue
        records, mapping, receipt = _replay_organ(
            organ, partitions[organ["organ_id"]], nodes, requested.model_dump(),
            skeleton.payload["seed"], boundary_policy, surface_z, row_kappas, incoming.get(organ["parent_id"]),
        )
        for fragment in mapping:
            incoming[fragment["node_id"]] = records[fragment["step_index"]]["accepted_heading"]
        steps.extend(records)
        fragments.extend(mapping)
        organs.append(receipt)
    nodes = nodes.reset_index(drop=True)
    hashes = invariant_hashes(nodes)
    if hashes != invariant_hashes(original):
        raise ValueError("Construction-step replay changed frozen graph invariants")
    edges = derived_edges(nodes)
    validate_geometry(nodes, edges, surface_z)
    proposals = pd.DataFrame([dict(organ_id=r["organ_id"], order=r["order"], step_index=r["step_index"], length_cm=r["length_cm"],
                                   start_x=r["start_xyz"][0], start_y=r["start_xyz"][1], start_z=r["start_xyz"][2],
                                   proposed_x=r["proposed_endpoint"][0], proposed_y=r["proposed_endpoint"][1], proposed_z=r["proposed_endpoint"][2],
                                   boundary_intervention=r["boundary_intervention"], boundary_ulp_nudges=r["boundary_ulp_nudges"])
                              for r in steps])
    return dict(nodes=nodes, edges=edges, proposals=proposals, diagnostics=dict(
        route=VERSION, grid=GRID, arm="D", seed=skeleton.payload["seed"], surface_z_cm=surface_z,
        boundary_policy=boundary_policy, skeleton_sha256=skeleton.sha256, invariant_hashes=hashes,
        organs=organs, construction_steps=steps, graph_fragments=fragments,
        replays=dict(physical=1, counterfactual=0),
        proposals="One-step construction-step proposals from actual starts; not a coherent graph; no per-fragment searches",
        **order_sigma_metadata(requested.fichtl_sigma, requested.research_fichtl_sigma_by_order),
    ))
