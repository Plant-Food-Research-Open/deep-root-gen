"""Opt-in controlled D integration on retained construction steps, then cuts.

These sampled construction intervals are a numerical operator, not elongation
events or measured biological time steps. Native Fichtl semantics are separate.
"""

from ..model.interval_geometry import construction_rng as step_rng

import copy
import hashlib
import json

import numpy as np
import pandas as pd

from ..data_model import RootSimulationModel
from ..utils.order_controls import direction_controls
from ..utils.current_length import STREAM_VERSION, _cdf_arrays, select_current_length
from ..utils.primary_attachment import FIELD as ATTACH_FIELD
from ..utils.tertiary_length_rank import FIELD as RANK_FIELD, VERSION as RANK_VERSION, plan_tertiary_length_family
from ..utils.tropism import insertion_heading, order_sigma_metadata, row_axial_insertion_heading, validate_row_axial_kappas
from .so4_controlled import (
    Skeleton, XYZ, apply_boundary, derived_edges, digest, fichtl_proposal,
    invariant_hashes, minimal_rotation, unit, validate_geometry, validate_saved_order_controls,
)

VERSION = "so4-construction-steps-v1"
GRID = "construction_steps_v1"


class ReplayParameters(RootSimulationModel):
    """INITIAL records from schema 4 omit retired static-generation controls."""

    root_ratio: float | None = None
    mechanical_constraints: float | None = None
    t: int | None = None


def capture_construction_steps(skeleton, simulation):
    """Export original boundary identities and positioned geometry from live nodes."""
    skeleton.verify()
    payload = copy.deepcopy(skeleton.payload)
    live = {node.node_data.node_id: node.node_data for node in simulation.G.nodes}
    lookup = {int(organ.segments[0].node_data.organ_id): organ
              for order in range(2, max(simulation.organs) + 1) for organ in simulation.organs[order]}
    for organ in payload["organs"]:
        if organ["order"] == 1:
            continue
        source = lookup[organ["organ_id"]]
        if hasattr(source, "tertiary_length_rank_family"):
            organ["tertiary_length_rank_family"] = copy.deepcopy(source.tertiary_length_rank_family)
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
    from .so4_controlled import validate_saved_primary_yaw_reversal, validate_saved_tertiary_length_rank, validate_saved_primary_attachment
    validate_saved_primary_yaw_reversal(skeleton, settings)
    validate_saved_tertiary_length_rank(skeleton, settings)
    validate_saved_primary_attachment(skeleton, settings)
    validate_saved_order_controls(skeleton, settings)
    saved = ReplayParameters.model_validate(skeleton.payload["parameters"])
    requested = ReplayParameters.model_validate(settings)
    if saved.research_current_length_grid != GRID or requested.research_current_length_grid != GRID:
        raise ValueError("Missing construction-step route")
    saved_values, requested_values = saved.model_dump(), requested.model_dump()
    for key, value in saved_values.items():
        if not key.startswith("fichtl_") and key not in {"simulation_tag", "research_insertion_row_axial_kappa", "research_fichtl_sigma_by_order"}:
            if key in {"research_primary_yaw_reverse_probability", RANK_FIELD, ATTACH_FIELD} and not requested_values[key] and not value:
                continue
            if requested_values[key] != value:
                raise ValueError(f"Construction settings disagree with INITIAL: {key}")
    if saved.research_base_depth_cm is not None and saved.soil_surface_z_cm != surface_z:
        raise ValueError("INITIAL origin surface disagrees with physical surface")
    return saved, requested


def _sampler_lengths(metadata, organ, parameters, seed, rank_expected=None):
    """Authenticate recorded sampler provenance without drawing replacement lengths."""
    sampler = metadata["sampler"]
    if rank_expected is not None:
        if not isinstance(sampler, dict):
            raise ValueError("Missing tertiary rank composite sampler provenance")
        expected_lengths, expected = rank_expected
        expected = copy.deepcopy(expected)
        expected.update(allocated_organ_id=organ["organ_id"], legacy_compatibility_draw_count=1 + parameters.segments_per_root)
        reported = copy.deepcopy(sampler)
        post = reported.pop("post_subdivision_length_cm", None)
        if digest(reported) != digest(expected):
            raise ValueError("Tertiary rank composite sampler/source/destination provenance mismatch")
        lengths = np.asarray(metadata["lengths_cm"], dtype=float)
        if (lengths.shape != expected_lengths.shape or not np.isfinite(lengths).all()
                or not np.array_equal(lengths, expected_lengths) or post is None
                or isinstance(post, bool) or not isinstance(post, (int, float)) or not np.isfinite(post)
                or not np.isclose(post, expected_lengths.sum(), rtol=0, atol=1e-8)):
            raise ValueError("Tertiary rank assigned construction lengths/provenance mismatch")
        return lengths
    if isinstance(sampler, dict) and sampler.get("stream_version") == RANK_VERSION:
        raise ValueError("Tertiary rank sampler is missing authenticated family")
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


def _partition(organ, nodes, parameters, seed, rank_expected=None):
    metadata = organ.get("construction_steps")
    if not isinstance(metadata, dict) or metadata.get("version") != VERSION:
        raise ValueError("Missing or unsupported original construction partition")
    if not {"sampler", "lengths_cm", "boundary_node_ids", "positioned_boundary_xyz"}.issubset(metadata):
        raise ValueError("Missing original construction boundary metadata")
    lengths = _sampler_lengths(metadata, organ, parameters, seed, rank_expected)
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


def _validate_rank_families(skeleton, parameters, nodes):
    """Recompute the declared keyed pool and exact family bijection, not a fit.

    Re-deriving existing keyed records for authentication introduces no new
    architecture innovations or shared RNG consumption.
    """
    from ..utils.branching import parent2_zone_sites, validate_parent2_branch_zone
    from ..utils.current_length import sample_current_lengths

    organs = skeleton.payload["organs"]
    by_id = {o["organ_id"]: o for o in organs}
    if (len(by_id) != len(organs) or set(by_id) != set(nodes.loc[nodes.order.gt(0), "organ_id"])):
        raise ValueError("Tertiary rank family/graph organ membership is incomplete or duplicated")
    parents = sorted((o for o in organs if o["order"] == 2), key=lambda o: o["organ_id"])
    next_id = int(nodes.loc[nodes.order.le(2), "organ_id"].max()) + 1
    seed = skeleton.payload["seed"]
    zone = validate_parent2_branch_zone(parameters.research_parent2_branch_zone_cm)
    expected, covered = {}, set()
    lookup = nodes.set_index("node_id")
    for parent in parents:
        metadata = parent.get("construction_steps")
        if not isinstance(metadata, dict) or not isinstance(metadata.get("sampler"), dict):
            raise ValueError("Missing parent2 construction sampler for tertiary rank family")
        _, draw = sample_current_lengths(parameters.research_current_length_cdfs_cm[2],
                                         parameters.segments_per_root, seed, parent["organ_id"], 2)
        sampler = metadata["sampler"]
        if any(digest(sampler.get(key)) != digest(value) for key, value in draw.items()):
            raise ValueError("Parent2 family CURRENT sampler does not match original keyed draw")
        sites = parent2_zone_sites(draw["sampled_current_length_cm"], **zone)
        children = [o for o in organs if o["order"] == 3 and o["parent_id"] in parent["node_ids"]]
        if any(isinstance(o.get("attachment_arc_cm"), bool)
               or not isinstance(o.get("attachment_arc_cm"), (int, float))
               or not np.isfinite(o["attachment_arc_cm"]) for o in children):
            raise ValueError("Tertiary rank family requires finite physical attachment arcs")
        children.sort(key=lambda o: (o["attachment_arc_cm"], o["organ_id"]))
        ids = [next_id + j for j in range(len(sites))]
        if (len(children) != len(sites) or [o["organ_id"] for o in children] != ids
                or not np.allclose([o["attachment_arc_cm"] for o in children], sites, rtol=0, atol=1e-8)):
            raise ValueError("Tertiary rank family IDs/sites disagree with original parent2 zone/birth order")
        # Authenticate origins against the actual graph, not only the receipt.
        for child, site in zip(children, sites):
            parent_node = lookup.loc[child["parent_id"]]
            arc = lookup.loc[parent["node_ids"]].loc[lambda frame: frame.segment_rank.le(parent_node.segment_rank), "length"].sum()
            if (int(parent_node.organ_id) != parent["organ_id"] or int(parent_node.order) != 2
                    or not np.isclose(arc, site, rtol=0, atol=1e-8)):
                raise ValueError("Tertiary rank family site disagrees with actual parent graph")
        plans, family = plan_tertiary_length_family(
            parameters.research_current_length_cdfs_cm[3], parameters.segments_per_root,
            seed, parent["organ_id"], next_id, sites, parameters.research_tertiary_length_rank_strength,
        )
        if digest(parent.get("tertiary_length_rank_family")) != digest(family):
            raise ValueError("Tertiary rank family permutation/quantiles/strength provenance mismatch")
        expected.update(zip(ids, plans))
        covered.update(o["organ_id"] for o in children)
        next_id += len(ids)
    if covered != {o["organ_id"] for o in organs if o["order"] == 3}:
        raise ValueError("Tertiary rank family authentication does not cover all order3 organs")
    return expected


def validate_construction_metadata(skeleton):
    """Read-only preflight for a captured INITIAL; no simulation or length draws."""
    parameters, _ = _scope(skeleton, skeleton.payload["parameters"], "D", 20.)
    from .primary_attachment import validate_primary_attachment_provenance
    validate_primary_attachment_provenance(skeleton)
    nodes, edges = pd.DataFrame(skeleton.payload["nodes"]), pd.DataFrame(skeleton.payload["edges"])
    validate_geometry(nodes, edges)
    if nodes.loc[nodes.order.le(1), "z"].max() > 20.:
        raise ValueError("Frozen primary scaffold exceeds physical soil surface")
    lookup = nodes.set_index("node_id", drop=False)
    if (not parameters.research_tertiary_length_rank_strength
            and any("tertiary_length_rank_family" in organ for organ in skeleton.payload["organs"])):
        raise ValueError("Inactive tertiary rank cannot retain active family provenance")
    ranked = _validate_rank_families(skeleton, parameters, nodes) if parameters.research_tertiary_length_rank_strength else {}
    return {organ["organ_id"]: _partition(organ, lookup, parameters, skeleton.payload["seed"], ranked.get(organ["organ_id"]))
            for organ in skeleton.payload["organs"] if organ["order"] > 1}


def _replay_organ(organ, partition, nodes, settings, seed, policy, surface_z, row_kappas, parent_tangent=None):
    """Saved-table adapter to the same kernel used by native live execution."""
    from ..model.interval_geometry import realize_intervals
    rows = nodes.to_dict("index")
    result = realize_intervals(organ, partition, rows, settings, seed, policy, surface_z,
                               row_kappas, parent_tangent, rng_factory=step_rng,
                               insertion=insertion_heading, proposal=fichtl_proposal)
    ids = [nid for part in partition for nid in part["node_ids"]]
    for nid in ids:
        nodes.loc[nid, XYZ] = [rows[nid][k] for k in XYZ]
    return result


def replay_construction_steps(skeleton, arm, settings, boundary_policy, surface_z=20.):
    """One controlled D replay: search/project steps once, interpolate fragments."""
    _, requested = _scope(skeleton, settings, arm, surface_z)
    partitions = validate_construction_metadata(skeleton)
    original = pd.DataFrame(skeleton.payload["nodes"])
    nodes = original.set_index("node_id", drop=False).copy(deep=True)
    row_kappas = validate_row_axial_kappas(requested.research_insertion_row_axial_kappa, requested.max_order)
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
        **validate_saved_order_controls(skeleton, settings),
        **order_sigma_metadata(requested.fichtl_sigma, requested.research_fichtl_sigma_by_order, requested.max_order),
    ))
