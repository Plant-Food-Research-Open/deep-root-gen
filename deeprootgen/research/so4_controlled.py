"""Paired static SO4 replay, with immutable INITIAL scaffolds and keyed innovations.

This is a diagnostic factorization, not native legacy growth or CPlantBox replay.
All distances are cm; insertion angles are degrees; sigma is rad/sqrt(cm).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from deeprootgen.utils.order_controls import (
    HIGHER_FIELD, COUNTS_FIELD, QUOTA_VERSION, direction_controls, plan_child_quotas, validate_order_scope,
)

from deeprootgen.utils.tropism import (
    _basis, insertion_heading, row_axial_controls_active,
    order_sigma_metadata, resolve_fichtl_sigma, row_axial_insertion_heading, sample_fichtl_alpha,
    validate_fichtl_sigma_by_order, validate_row_axial_kappas, validate_primary_yaw_reverse_probability,
)

from deeprootgen.utils.tertiary_length_rank import FIELD as RANK_FIELD, validate_rank_strength
from deeprootgen.utils.primary_attachment import FIELD as ATTACH_FIELD, validate_distal_fraction
from deeprootgen.utils.primary_design import FIELD as DESIGN_FIELD

from ..model.controlled_geometry import digest, unit, minimal_rotation, frame, fichtl_proposal, apply_boundary

ARMS = {
    "A": ("legacy", "legacy"),
    "B": ("fichtl", "legacy"),
    "C": ("legacy", "fichtl"),
    "D": ("fichtl", "fichtl"),
}
XYZ = ["x", "y", "z"]


def keyed_rng(seed: int, organ: int, segment: int, purpose: str):
    """Stable substream: independent of arm, loop order and other stream draws."""
    key = hashlib.sha256(
        f"so4-controlled-v1:{seed}:{organ}:{segment}:{purpose}".encode()
    ).digest()
    return np.random.default_rng(
        np.random.SeedSequence(np.frombuffer(key, dtype="<u4"))
    )


@dataclass
class Skeleton:
    """Serializable INITIAL construction; payload hash detects mutation."""

    payload: dict
    sha256: str

    @classmethod
    def from_tables(cls, nodes, edges, seed, parameters=None):
        # Preserve historical table-built INITIAL identities for inactive zones.
        if parameters is not None and parameters.get("research_primary_branch_zone_cm") is None:
            parameters = dict(parameters)
            parameters.pop("research_primary_branch_zone_cm", None)
        if parameters is not None and parameters.get("research_primary_branch_fractions") is None:
            parameters = dict(parameters)
            parameters.pop("research_primary_branch_fractions", None)
        nodes = nodes.sort_values("node_id").reset_index(drop=True).copy()
        edges = edges.sort_values(["parent_id", "child_id"]).reset_index(drop=True)
        by_id = nodes.set_index("node_id")
        organs = []
        for organ_id, chain in nodes.loc[nodes.order.gt(0)].groupby("organ_id"):
            chain = chain.sort_values("segment_rank")
            parent_id = int(chain.iloc[0].parent_id)
            order = int(chain.iloc[0].order)
            coords = np.vstack(
                [by_id.loc[parent_id, XYZ].to_numpy(float), chain[XYZ].to_numpy(float)]
            )
            vectors = np.diff(coords, axis=0)
            lengths = chain.length.to_numpy(float)
            if np.any(lengths <= 1e-12):
                raise ValueError("Nonpositive skeleton segment")
            np.testing.assert_allclose(
                np.linalg.norm(vectors, axis=1), lengths, rtol=1e-5, atol=1e-6
            )
            parent = by_id.loc[parent_id]
            tangent = (
                [0.0, 0.0, -1.0]
                if order == 1
                else unit(
                    parent[XYZ].to_numpy(float)
                    - by_id.loc[int(parent.parent_id), XYZ].to_numpy(float)
                ).tolist()
            )
            parent_chain = nodes.loc[
                (nodes.organ_id == parent.organ_id)
                & (nodes.segment_rank <= parent.segment_rank)
            ]
            organs.append(
                dict(
                    organ_id=int(organ_id),
                    order=order,
                    parent_id=parent_id,
                    node_ids=chain.node_id.astype(int).tolist(),
                    headings=(
                        vectors / np.linalg.norm(vectors, axis=1)[:, None]
                    ).tolist(),
                    parent_tangent=tangent,
                    attachment_arc_cm=(
                        float(parent_chain.length.sum()) if order > 1 else 0.0
                    ),
                )
            )
        payload = dict(
            format="so4-initial-v1",
            seed=int(seed),
            parameters=parameters or {},
            nodes=nodes.to_dict("records"),
            edges=edges.to_dict("records"),
            organs=organs,
        )
        return cls(payload, digest(payload))

    def verify(self):
        if digest(self.payload) != self.sha256:
            raise ValueError("INITIAL skeleton identity mismatch")

    def save(self, path):
        self.verify()
        path = Path(path)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".tmp-initial-", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "w") as handle:
                json.dump(
                    dict(sha256=self.sha256, payload=self.payload),
                    handle,
                    allow_nan=False,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, path)
            directory = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(temporary).unlink(missing_ok=True)

    @classmethod
    def load(cls, path):
        value = json.loads(Path(path).read_text())
        result = cls(value["payload"], value["sha256"])
        result.verify()
        return result


def _initial_saved_parameters(parameters):
    """Retain the historical saved payload shape for inactive controls."""
    saved_parameters = parameters.model_dump()
    if saved_parameters.get("research_primary_branch_fractions") is None:
        saved_parameters.pop("research_primary_branch_fractions", None)
    if saved_parameters.get("research_primary_branch_zone_cm") is None:
        saved_parameters.pop("research_primary_branch_zone_cm", None)
    if saved_parameters[DESIGN_FIELD] is None:
        saved_parameters.pop(DESIGN_FIELD)
    for key in (HIGHER_FIELD, COUNTS_FIELD):
        if saved_parameters[key] is None:
            saved_parameters.pop(key)
    # Capture the equivalent untreated INITIAL first; relocation is pure tables.
    saved_parameters.pop(ATTACH_FIELD, None)
    if parameters.research_current_length_grid is None:
        saved_parameters.pop("research_current_length_grid", None)
    if parameters.research_parent2_branch_zone_cm is None:
        saved_parameters.pop("research_parent2_branch_zone_cm", None)
    if parameters.research_fichtl_sigma_by_order is None:
        saved_parameters.pop("research_fichtl_sigma_by_order", None)
    if not parameters.research_primary_yaw_reverse_probability:
        saved_parameters.pop("research_primary_yaw_reverse_probability", None)
    if not parameters.research_tertiary_length_rank_strength:
        saved_parameters.pop(RANK_FIELD, None)
    return saved_parameters


def construct_skeleton(parameters, seed: int) -> Skeleton:
    """One INITIAL construction; deliberately never calls run/validate/gravity."""
    from deeprootgen.data_model import RootSimulationModel
    from deeprootgen.archive.simulation import RootSystemSimulation

    values = (
        parameters.model_dump()
        if hasattr(parameters, "model_dump")
        else dict(parameters)
    )
    reversal = validate_primary_yaw_reverse_probability(values.get("research_primary_yaw_reverse_probability"))
    distal = validate_distal_fraction(values.get(ATTACH_FIELD))
    if values.get(DESIGN_FIELD) is not None or values.get(COUNTS_FIELD) is not None or distal or reversal or validate_rank_strength(values.get(RANK_FIELD)) or values.get("research_current_length_grid") is not None:
        if (isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer))
                or not isinstance(values.get("random_seed"), (int, np.integer))
                or values.get("random_seed") != seed or isinstance(values.get("random_seed"), (bool, np.bool_))):
            raise ValueError("Construction-step INITIAL requires matching explicit seeds")
    # Legacy construction is treatment-independent. Optional yaw/origin stages
    # now run during primary positioning; controlled origin surface is fixed.
    values.update(random_seed=int(seed), simulation_tag="SO4-T2-controlled-INITIAL")
    p = RootSimulationModel(**values)
    explicit_design = p.research_primary_design is not None
    surface_z = 0.0 if explicit_design else 20.0
    if p.research_base_depth_cm is not None and p.soil_surface_z_cm != surface_z:
        raise ValueError("Controlled origin initialization requires soil surface z=20 cm")
    sim = RootSystemSimulation(simulation_tag=p.simulation_tag, random_seed=seed)
    sim.init_organs(p)
    sim.position_secondary_roots(p)
    sim.position_primary_roots(p)
    return capture_initial(sim, p)


def capture_initial(sim, p):
    """Read-only recorder for native preparation; never constructs or replays."""
    surface_z = 0.0 if p.research_primary_design is not None else 20.0
    nodes, edges = sim.G.as_df()
    if nodes.invalid_root.any():
        raise ValueError("INITIAL unexpectedly contains invalid nodes")
    saved_parameters = _initial_saved_parameters(p)
    skeleton = Skeleton.from_tables(nodes, edges, sim.random_seed, saved_parameters)
    if p.research_root_counts_by_order is not None:
        skeleton.payload["count_conditioning"] = copy.deepcopy(sim.count_conditioning_diagnostics)
        skeleton.sha256 = digest(skeleton.payload)
    if p.research_current_length_grid is not None:
        from .construction_step_replay import capture_construction_steps
        skeleton = capture_construction_steps(skeleton, sim)
    if p.research_parent2_branch_zone_cm is not None:
        live_organs = {int(organ.segments[0].node_data.organ_id): organ for organ in sim.organs[2]}
        for organ in skeleton.payload["organs"]:
            if organ["order"] == 2:
                organ["parent2_branch_zone"] = copy.deepcopy(live_organs[organ["organ_id"]].parent2_zone_diagnostics)
        skeleton.sha256 = digest(skeleton.payload)
    if nodes.loc[nodes.order.le(1), "z"].max() > surface_z:
        raise ValueError("Frozen primary scaffold exceeds common surface; no repairs")
    by_id = nodes.set_index("node_id")
    if any(
        float(by_id.loc[o["parent_id"], "z"]) > surface_z
        for o in skeleton.payload["organs"]
        if o["order"] == 2
    ):
        raise ValueError("Frozen primary attachment exceeds common surface")
    if p.research_primary_attachment_distal_fraction:
        from .primary_attachment import relocate_primary_attachments
        return relocate_primary_attachments(skeleton, p.research_primary_attachment_distal_fraction)
    return skeleton


def derived_edges(nodes):
    """Derive exported edge identities from the realised graph node records."""
    return (
        nodes.loc[nodes.order.gt(0), ["parent_id", "node_id"]]
        .rename(columns={"node_id": "child_id"})
        .sort_values(["parent_id", "child_id"])
        .reset_index(drop=True)
    )


def derived_attachments(nodes):
    """Recompute lateral attachment node and parent arc coordinate from nodes."""
    attachments = []
    lookup = nodes.set_index("node_id")
    for oid, chain in nodes.loc[nodes.order.gt(1)].groupby("organ_id"):
        first = chain.sort_values("segment_rank").iloc[0]
        parent_id = int(first.parent_id)
        parent = lookup.loc[parent_id]
        parent_chain = nodes.loc[
            (nodes.organ_id == parent.organ_id)
            & (nodes.segment_rank <= parent.segment_rank)
        ]
        attachments.append(
            dict(
                organ_id=int(oid),
                parent_id=parent_id,
                attachment_arc_cm=float(parent_chain.length.sum()),
            )
        )
    return sorted(attachments, key=lambda entry: entry["organ_id"])


def invariant_hashes(nodes):
    identity_columns = [c for c in nodes.columns if c not in XYZ + ["invalid_root"]]
    return dict(
        frozen_nodes=digest(nodes[identity_columns].to_dict("records")),
        edges=digest(derived_edges(nodes).to_dict("records")),
        scaffold=digest(nodes.loc[nodes.order.le(1)].to_dict("records")),
        attachments=digest(derived_attachments(nodes)),
    )


def _controlled_row_kappas(settings, insertion_mode, seed):
    """Validate the optional insertion control before mutating replay nodes."""
    kappas = validate_row_axial_kappas(settings.get("research_insertion_row_axial_kappa"), settings.get("max_order", 3))
    if row_axial_controls_active(kappas):
        if insertion_mode != "fichtl" or settings.get("tropism_mode") != "fichtl2024":
            raise ValueError("Active row-axial controls require Fichtl insertion (arms B/D) and mode")
        input_seed = settings.get("random_seed")
        if (isinstance(input_seed, (bool, np.bool_)) or not isinstance(input_seed, (int, np.integer))
                or input_seed != seed):
            raise ValueError("Active row-axial input seed must match saved skeleton seed")
    return kappas


def _controlled_order_sigma(settings, continuation_mode):
    mapping = settings.get("research_fichtl_sigma_by_order")
    if mapping is None:
        return None
    mapping = validate_fichtl_sigma_by_order(mapping, settings.get("max_order", 3))
    if continuation_mode != "fichtl" or settings.get("tropism_mode") != "fichtl2024":
        raise ValueError("Order sigma overrides require Fichtl continuation (arms C/D) and mode")
    return mapping


def validate_saved_primary_yaw_reversal(skeleton, settings):
    """Reversal is INITIAL construction, never a replay-time direction control."""
    key = "research_primary_yaw_reverse_probability"
    saved = validate_primary_yaw_reverse_probability(skeleton.payload["parameters"].get(key)) or 0.
    requested = validate_primary_yaw_reverse_probability(settings.get(key)) or 0.
    if saved != requested:
        raise ValueError("Primary yaw reversal setting disagrees with saved INITIAL")


def validate_saved_tertiary_length_rank(skeleton, settings, legacy=False):
    saved = validate_rank_strength(skeleton.payload["parameters"].get(RANK_FIELD)) or 0.
    requested = validate_rank_strength(settings.get(RANK_FIELD)) or 0.
    if saved != requested:
        raise ValueError("Tertiary length rank setting disagrees with saved INITIAL")
    if saved and legacy:
        raise ValueError("Tertiary length rank requires named construction-step replay, not legacy replay_arm")
    return saved


def validate_saved_primary_attachment(skeleton, settings, legacy=False):
    saved = validate_distal_fraction(skeleton.payload["parameters"].get(ATTACH_FIELD)) or 0.
    requested = validate_distal_fraction(settings.get(ATTACH_FIELD)) or 0.
    if saved != requested:
        raise ValueError("Primary attachment placement setting disagrees with saved INITIAL")
    if saved and legacy:
        raise ValueError("Primary attachment placement requires named construction-step replay")
    return saved


def _validate_counted_graph(skeleton, counts):
    """Check population and complete organ-chain membership in the live tables."""
    organs = skeleton.payload["organs"]
    nodes = pd.DataFrame(skeleton.payload["nodes"]).set_index("node_id", drop=False)
    if nodes.index.has_duplicates:
        raise ValueError("Count-conditioned graph has duplicated nodes")
    if nodes.loc[nodes.order.gt(0)].groupby("order").organ_id.nunique().to_dict() != counts:
        raise ValueError("Count-conditioned actual graph population disagrees")
    ids = [organ["organ_id"] for organ in organs]
    if len(ids) != len(set(ids)) or set(ids) != set(nodes.loc[nodes.order.gt(0), "organ_id"]):
        raise ValueError("Count-conditioned organ provenance is incomplete or duplicated")
    for organ in organs:
        chain = nodes.loc[nodes.organ_id.eq(organ["organ_id"])].sort_values("segment_rank")
        if (chain.node_id.tolist() != organ["node_ids"] or not chain.order.eq(organ["order"]).all()
                or chain.parent_id.tolist() != [organ["parent_id"], *organ["node_ids"][:-1]]):
            raise ValueError("Count-conditioned graph/organ chain provenance disagrees")
    return nodes


def _validate_counted_sites(organs, nodes, parameters, quotas):
    """Authenticate each balanced parent quota and its unchanged arc rule."""
    for order in range(1, parameters.max_order):
        parents = sorted((o for o in organs if o["order"] == order), key=lambda o: o["organ_id"])
        for parent, quota in zip(parents, quotas[str(order)]):
            chain = nodes.loc[parent["node_ids"]]
            children = [o for o in organs if o["order"] == order + 1 and o["parent_id"] in parent["node_ids"]]
            if len(children) != quota:
                raise ValueError("Count-conditioned per-parent quota mismatch")
            total = float(chain.length.sum())
            start, end = parameters.floor_threshold * total, parameters.ceiling_threshold * total
            expected_sites = [start + (j + .5) * (end - start) / quota for j in range(quota)]
            actual_sites = []
            for child in children:
                rank = nodes.loc[child["parent_id"], "segment_rank"]
                arc = float(chain.loc[chain.segment_rank.le(rank), "length"].sum())
                if not np.isclose(child["attachment_arc_cm"], arc, rtol=0, atol=1e-8):
                    raise ValueError("Count-conditioned attachment provenance mismatch")
                actual_sites.append(arc)
            if not np.allclose(sorted(actual_sites), expected_sites, rtol=0, atol=1e-8):
                raise ValueError("Count-conditioned arc sites disagree with declared parent window")


def validate_saved_primary_design(skeleton, settings):
    """Explicit primary geometry is construction, never a replay-time treatment."""
    from deeprootgen.data_model import RootSimulationModel
    saved_values = skeleton.payload["parameters"]
    if saved_values.get(DESIGN_FIELD) is None and settings.get(DESIGN_FIELD) is None:
        return
    saved, requested = RootSimulationModel(**saved_values), RootSimulationModel(**settings)
    for key in (DESIGN_FIELD, "random_seed", "outer_root_num", "inner_root_num", "max_order",
                "research_base_origin_x_cm", "research_base_origin_y_cm", "research_base_depth_cm",
                "soil_surface_z_cm"):
        if getattr(saved, key) != getattr(requested, key):
            raise ValueError(f"Explicit primary design setting disagrees with saved INITIAL: {key}")
    if saved.random_seed != skeleton.payload["seed"]:
        raise ValueError("Explicit primary design seed disagrees with saved INITIAL")


def validate_saved_order_controls(skeleton, settings):
    """Authenticate active topology and higher-order inputs before replay mutation."""
    from deeprootgen.data_model import RootSimulationModel
    # Fractions are a native-only construction input, never silently replayed.
    if any(values.get("research_primary_branch_fractions") is not None
           for values in (skeleton.payload["parameters"], settings)):
        raise ValueError("Primary branch fractions require native construction; controlled replay is unsupported")
    # Both graph-segment and construction-step replay call this authenticator.
    validate_saved_primary_design(skeleton, settings)
    saved_values = skeleton.payload["parameters"]
    active = any(values.get(key) is not None for values in (saved_values, settings)
                 for key in (HIGHER_FIELD, COUNTS_FIELD))
    if not active:
        if "count_conditioning" in skeleton.payload:
            raise ValueError("Inactive count conditioning cannot retain active provenance")
        return {}
    saved, requested = RootSimulationModel(**saved_values), RootSimulationModel(**settings)
    for key in (HIGHER_FIELD, COUNTS_FIELD, "max_order"):
        if getattr(saved, key) != getattr(requested, key):
            raise ValueError(f"Research order settings disagree with INITIAL: {key}")
    counts = validate_order_scope(saved)
    if counts is None:
        if "count_conditioning" in skeleton.payload:
            raise ValueError("Inactive count conditioning cannot retain active provenance")
        return {}
    for key in ("random_seed", "inner_root_num", "outer_root_num", "floor_threshold", "ceiling_threshold",
                "research_current_length_cdfs_cm", "research_branch_placement", "research_current_length_grid"):
        if getattr(saved, key) != getattr(requested, key):
            raise ValueError(f"Count-conditioned construction settings disagree: {key}")
    if saved.random_seed != skeleton.payload["seed"]:
        raise ValueError("Count-conditioned seed disagrees with INITIAL")
    quotas = {str(order): plan_child_quotas(saved.random_seed, order + 1, counts[order], counts[order + 1])
              for order in range(1, saved.max_order)}
    organs = skeleton.payload["organs"]
    realized = {str(order): sum(o["order"] == order for o in organs) for order in counts}
    expected = dict(version=QUOTA_VERSION, interpretation="supplied topology conditioning; not count prediction",
                    requested_counts_by_order={str(k): v for k, v in counts.items()},
                    realized_counts_by_order=realized, child_quotas_by_parent_order=quotas, seed=saved.random_seed)
    if realized != expected["requested_counts_by_order"] or digest(skeleton.payload.get("count_conditioning")) != digest(expected):
        raise ValueError("Count-conditioned provenance/realized counts mismatch")
    nodes = _validate_counted_graph(skeleton, counts)
    _validate_counted_sites(organs, nodes, saved, quotas)
    return dict(count_conditioning=copy.deepcopy(expected))


def replay_arm(
    skeleton: Skeleton,
    arm: str,
    settings: dict,
    boundary_policy: str,
    surface_z: float = 20.0,
):
    """One physical replay; uncorrected one-step proposals are diagnostic records."""
    skeleton.verify()
    explicit_design = skeleton.payload["parameters"].get(DESIGN_FIELD) is not None
    if arm not in ARMS or surface_z != (0.0 if explicit_design else 20.0):
        raise ValueError("Controlled design needs arms A-D and shared surface z=20 cm")
    parameters = skeleton.payload["parameters"]
    quota_receipt = validate_saved_order_controls(skeleton, settings)
    validate_saved_primary_yaw_reversal(skeleton, settings)
    validate_saved_tertiary_length_rank(skeleton, settings, legacy=True)
    validate_saved_primary_attachment(skeleton, settings, legacy=True)
    if (parameters.get("research_current_length_grid") is not None
            or settings.get("research_current_length_grid") is not None
            or parameters.get("research_parent2_branch_zone_cm") is not None
            or settings.get("research_parent2_branch_zone_cm") is not None):
        raise ValueError("Construction-step grid requires replay_construction_steps, not legacy replay_arm")
    if (parameters.get("research_base_depth_cm") is not None
            and parameters.get("soil_surface_z_cm") != surface_z):
        raise ValueError("Saved origin surface disagrees with controlled replay surface")
    insertion_mode, continuation_mode = ARMS[arm]
    sigma_map = _controlled_order_sigma(settings, continuation_mode)
    row_kappas = _controlled_row_kappas(settings, insertion_mode, skeleton.payload["seed"])
    original = pd.DataFrame(skeleton.payload["nodes"]).set_index("node_id", drop=False)
    nodes = original.copy(deep=True)
    edges = pd.DataFrame(skeleton.payload["edges"])
    if nodes.loc[nodes.order.le(1), "z"].max() > surface_z:
        raise ValueError("Frozen primary scaffold exceeds common physical surface")
    seed = skeleton.payload["seed"]
    diagnostics = []
    organ_receipts = []
    for organ in sorted(
        skeleton.payload["organs"], key=lambda o: (o["order"], o["organ_id"])
    ):
        order, oid, parent_id = organ["order"], organ["organ_id"], organ["parent_id"]
        if order == 1:
            continue
        control = direction_controls(settings, order)
        stored = np.asarray(organ["headings"])
        parent = nodes.loc[parent_id]
        tangent = unit(
            parent[XYZ].to_numpy(float)
            - nodes.loc[int(parent.parent_id), XYZ].to_numpy(float)
        )
        parent_rotation = minimal_rotation(organ["parent_tangent"], tangent)
        legacy_first = parent_rotation @ stored[0]
        assigned = (
            legacy_first
            if insertion_mode == "legacy"
            else insertion_heading(
                tangent,
                control["theta_deg"],
                control["theta_sd_deg"],
                keyed_rng(seed, oid, 0, "insertion"),
            )
        )
        row_report = None
        if row_kappas is not None and insertion_mode == "fichtl":
            assigned, row_report = row_axial_insertion_heading(
                tangent, assigned, row_kappas.get(order), seed, oid, order,
            )
            row_report.update(realisation_stage="controlled_exact_first_segment_then_common_projection",
                              row_alignment_by_arc=[])
        assigned = unit(assigned)
        old_frame = frame(stored[0])
        current_frame = minimal_rotation(stored[0], assigned) @ old_frame
        initial_frame = current_frame.copy()
        arc = 0.
        for index, nid in enumerate(organ["node_ids"]):
            length = float(nodes.loc[nid, "length"])
            start_id = int(nodes.loc[nid, "parent_id"])
            start = nodes.loc[start_id, XYZ].to_numpy(float)
            receipt = {}
            if index == 0:
                proposal = assigned.copy()
            elif continuation_mode == "legacy":
                local_turn = old_frame.T @ stored[index]
                proposal = unit(current_frame @ local_turn)
            else:
                proposal, receipt = fichtl_proposal(
                    current_frame,
                    length,
                    order,
                    settings,
                    keyed_rng(seed, oid, index, "continuation"),
                )
            boundary_receipt = {}
            accepted, attempted_endpoint, intervened = apply_boundary(
                start,
                proposal,
                length,
                surface_z,
                boundary_policy,
                keyed_rng(seed, oid, nid, "boundary"),
                diagnostics=boundary_receipt,
            )
            nodes.loc[nid, XYZ] = start + length * accepted
            if row_report is not None:
                if index == 0:
                    row_report["post_boundary_heading"] = accepted.tolist()
                    row_report["post_boundary_polar_angle_deg"] = float(np.degrees(np.arccos(np.clip(accepted @ tangent, -1., 1.))))
                row_report["row_alignment_by_arc"].append(dict(
                    node_id=nid, arc_start_cm=arc, arc_end_cm=arc + length,
                    row_projection=float(accepted[1]), axial_row_alignment=float(accepted[1]**2),
                    alignment_with_insertion=float(accepted @ assigned), boundary_intervention=intervened,
                ))
            arc += length
            if index > 0:
                old_frame = (
                    minimal_rotation(stored[index - 1], stored[index]) @ old_frame
                )
            current_frame = (
                minimal_rotation(current_frame[:, 0], accepted) @ current_frame
            )
            diagnostics.append(
                dict(
                    node_id=nid,
                    organ_id=oid,
                    order=order,
                    segment_index=index + 1,
                    length_cm=length,
                    parent_id=start_id,
                    start_xyz=start.tolist(),
                    proposed_heading=proposal.tolist(),
                    accepted_heading=accepted.tolist(),
                    proposed_endpoint=attempted_endpoint.tolist(),
                    boundary_intervention=intervened,
                    correction_angle_rad=(
                        float(np.arccos(np.clip(proposal @ accepted, -1, 1)))
                        if intervened
                        else 0.0
                    ),
                    corrected_segment_length_cm=length if intervened else 0.0,
                    correction_arc_cm=(
                        length * float(np.arccos(np.clip(proposal @ accepted, -1, 1)))
                        if intervened
                        else 0.0
                    ),
                    **boundary_receipt,
                    **receipt,
                )
            )
            if index == 0:
                organ_receipts.append(
                    dict(
                        organ_id=oid,
                        order=order,
                        parent_id=parent_id,
                        assigned_heading=assigned.tolist(),
                        realised_heading=accepted.tolist(),
                        assigned_angle_deg=float(
                            np.degrees(np.arccos(np.clip(assigned @ tangent, -1, 1)))
                        ),
                        realised_angle_deg=float(
                            np.degrees(np.arccos(np.clip(accepted @ tangent, -1, 1)))
                        ),
                        transported_initial_frame=initial_frame.tolist(),
                        parent_tangent=tangent.tolist(),
                    )
                )
                if row_report is not None:
                    organ_receipts[-1]["row_axial_insertion"] = row_report
    nodes = nodes.reset_index(drop=True)
    expected = invariant_hashes(original.reset_index(drop=True))
    actual = invariant_hashes(nodes)
    if actual != expected:
        raise AssertionError(
            "Frozen scaffold/topology/length/diameter/attachment invariant changed"
        )
    validate_geometry(nodes, edges, surface_z)
    edges = derived_edges(nodes)
    proposals = pd.DataFrame(
        [
            dict(
                node_id=r["node_id"],
                parent_id=r["parent_id"],
                organ_id=r["organ_id"],
                order=r["order"],
                segment_index=r["segment_index"],
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
            for r in diagnostics
        ]
    )
    return dict(
        nodes=nodes,
        edges=edges,
        proposals=proposals,
        diagnostics=dict(
            arm=arm,
            seed=seed,
            insertion=insertion_mode,
            continuation=continuation_mode,
            skeleton_sha256=skeleton.sha256,
            invariant_hashes=actual,
            organs=organ_receipts,
            segments=diagnostics,
            boundary_policy=boundary_policy,
            surface_z_cm=surface_z,
            replays={"physical": 1, "counterfactual": 0},
            proposals="One-step unconstrained endpoints from actual origins; not a coherent graph",
            **quota_receipt,
            **(order_sigma_metadata(settings["fichtl_sigma"], sigma_map, settings.get("max_order", 3)) if sigma_map is not None else {}),
        ),
    )


def _validate_rooted_tree(nodes, pairs):
    """Check structural tree validity separately from numerical geometry."""
    roots = nodes.loc[nodes.order.eq(0)]
    if (len(roots) != 1 or roots.iloc[0].parent_id != -1
            or int(nodes.parent_id.eq(-1).sum()) != 1
            or not nodes.loc[nodes.order.ne(0), "order"].gt(0).all()):
        raise ValueError("Graph requires exactly one base/root with parent -1")
    base_id = int(roots.iloc[0].node_id)
    ids = set(nodes.node_id)
    parents = {int(row.node_id): int(row.parent_id)
               for row in nodes.loc[nodes.order.gt(0)].itertuples()}
    if any(parent not in ids for parent in parents.values()):
        raise ValueError("Graph contains a missing parent reference")
    finished = {base_id}
    for start in parents:
        current, path = start, set()
        while current not in finished:
            if current in path:
                raise ValueError("Graph contains a directed cycle")
            path.add(current)
            current = parents[current]
        finished.update(path)
    children = {node: [] for node in ids}
    for parent, child in pairs:
        children[parent].append(child)
    reachable, pending = set(), [base_id]
    while pending:
        node = pending.pop()
        reachable.add(node)
        pending.extend(children[node])
    if reachable != ids:
        raise ValueError("Graph contains nodes unreachable from its base")


def validate_geometry(nodes, edges, surface_z=None):
    """Finite connected graph and conserved per-segment lengths; no apex constraint."""
    if (
        not nodes.node_id.is_unique
        or not np.isfinite(nodes[XYZ + ["length", "diameter"]].to_numpy(float)).all()
    ):
        raise ValueError("Nonfinite geometry or duplicate IDs")
    lookup = nodes.set_index("node_id")
    pairs = set(zip(edges.parent_id, edges.child_id))
    expected = {
        (int(row.parent_id), int(row.node_id))
        for row in nodes.itertuples()
        if row.order > 0
    }
    if pairs != expected or len(edges) != len(expected):
        raise ValueError("Graph edge/parent mismatch")
    _validate_rooted_tree(nodes, pairs)
    measured, stored = [], []
    for row in nodes.itertuples():
        if row.order <= 0:
            continue
        parent = lookup.loc[row.parent_id, XYZ].to_numpy(float)
        measured.append(np.linalg.norm(np.asarray([row.x, row.y, row.z]) - parent))
        stored.append(row.length)
    np.testing.assert_allclose(measured, stored, rtol=1e-5, atol=1e-6)
    if not np.isclose(sum(measured), sum(stored), rtol=0, atol=1e-8):
        raise ValueError("Length conservation exceeds 1e-8 cm")
    if surface_z is not None and nodes.z.max() > surface_z + 1e-8:
        raise ValueError("Geometry above physical surface")
