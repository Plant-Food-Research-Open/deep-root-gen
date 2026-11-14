"""Paired static SO4 replay, with immutable INITIAL scaffolds and keyed innovations.

This is a diagnostic factorization, not native legacy growth or CPlantBox replay.
All distances are cm; insertion angles are degrees; sigma is rad/sqrt(cm).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from deeprootgen.utils.tropism import (
    _basis, insertion_heading, row_axial_controls_active,
    row_axial_insertion_heading, validate_row_axial_kappas,
)

ARMS = {
    "A": ("legacy", "legacy"),
    "B": ("fichtl", "legacy"),
    "C": ("legacy", "fichtl"),
    "D": ("fichtl", "fichtl"),
}
XYZ = ["x", "y", "z"]


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, allow_nan=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def keyed_rng(seed: int, organ: int, segment: int, purpose: str):
    """Stable substream: independent of arm, loop order and other stream draws."""
    key = hashlib.sha256(
        f"so4-controlled-v1:{seed}:{organ}:{segment}:{purpose}".encode()
    ).digest()
    return np.random.default_rng(
        np.random.SeedSequence(np.frombuffer(key, dtype="<u4"))
    )


def unit(vector):
    vector = np.asarray(vector, dtype=float)
    if vector.shape != (3,) or not np.isfinite(vector).all():
        raise ValueError("Expected finite 3-vector")
    norm = np.linalg.norm(vector)
    if norm <= 1e-12:
        raise ValueError("Degenerate direction")
    return vector / norm


def minimal_rotation(source, target):
    """Deterministic shortest rotation; antiparallel axis is the least aligned axis."""
    source, target = unit(source), unit(target)
    cross = np.cross(source, target)
    cosine = float(np.clip(source @ target, -1, 1))
    sine = np.linalg.norm(cross)
    if sine <= 1e-12:
        if cosine > 0:
            return np.eye(3)
        axis = _basis(source)[1]
        return 2 * np.outer(axis, axis) - np.eye(3)
    # Normalized-axis Rodrigues avoids the (1-c)/s² amplification near pi.
    axis = cross / sine
    angle = np.arctan2(sine, cosine)
    sine, cosine = np.sin(angle), np.cos(angle)
    skew = np.array(
        [[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]]
    )
    return cosine * np.eye(3) + (1 - cosine) * np.outer(axis, axis) + sine * skew


def frame(heading):
    return np.column_stack(_basis(heading))


@dataclass
class Skeleton:
    """Serializable INITIAL construction; payload hash detects mutation."""

    payload: dict
    sha256: str

    @classmethod
    def from_tables(cls, nodes, edges, seed, parameters=None):
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


def construct_skeleton(parameters, seed: int) -> Skeleton:
    """One INITIAL construction; deliberately never calls run/validate/gravity."""
    from deeprootgen.data_model import RootSimulationModel
    from deeprootgen.model import RootSystemSimulation

    values = (
        parameters.model_dump()
        if hasattr(parameters, "model_dump")
        else dict(parameters)
    )
    # Legacy construction is treatment-independent. Optional yaw/origin stages
    # now run during primary positioning; controlled origin surface is fixed.
    values.update(random_seed=int(seed), simulation_tag="SO4-T2-controlled-INITIAL")
    p = RootSimulationModel(**values)
    if p.research_base_depth_cm is not None and p.soil_surface_z_cm != 20.0:
        raise ValueError("Controlled origin initialization requires soil surface z=20 cm")
    sim = RootSystemSimulation(simulation_tag=p.simulation_tag, random_seed=seed)
    sim.init_organs(p)
    sim.position_secondary_roots(p)
    sim.position_primary_roots(p)
    nodes, edges = sim.G.as_df()
    if nodes.invalid_root.any():
        raise ValueError("INITIAL unexpectedly contains invalid nodes")
    skeleton = Skeleton.from_tables(nodes, edges, seed, p.model_dump())
    if nodes.loc[nodes.order.le(1), "z"].max() > 20.0:
        raise ValueError("Frozen primary scaffold exceeds common surface; no repairs")
    by_id = nodes.set_index("node_id")
    if any(
        float(by_id.loc[o["parent_id"], "z"]) > 20.0
        for o in skeleton.payload["organs"]
        if o["order"] == 2
    ):
        raise ValueError("Frozen primary attachment exceeds common surface")
    return skeleton


def fichtl_proposal(previous_frame, length, order, settings, rng):
    """Select unconstrained candidate; boundary is a separate common operator."""
    if order not in (2, 3):
        raise ValueError("Fichtl proposal supports orders 2 and 3")
    trials = settings[f"fichtl_trials_type{order}"]
    sigma = settings["fichtl_sigma"]
    probability = settings["fichtl_probability_down"]
    previous_frame = np.asarray(previous_frame, dtype=float)
    if (
        not np.isfinite(length)
        or length <= 0
        or not np.isfinite(trials)
        or trials < 0
        or not np.isfinite(sigma)
        or sigma < 0
        or not np.isfinite(probability)
        or not 0 <= probability <= 1
        or previous_frame.shape != (3, 3)
        or not np.isfinite(previous_frame).all()
        or not np.allclose(
            previous_frame.T @ previous_frame, np.eye(3), rtol=0, atol=1e-10
        )
        or not np.isclose(np.linalg.det(previous_frame), 1, rtol=0, atol=1e-10)
    ):
        raise ValueError("Invalid Fichtl proposal inputs")
    scaled = trials * np.sqrt(length)
    extra = int(np.floor(scaled)) + int(rng.random() < scaled % 1)
    alpha = settings["fichtl_sigma"] * np.sqrt(length) * rng.normal(size=extra + 1)
    beta = rng.uniform(0, 2 * np.pi, size=extra + 1)
    downward = bool(
        rng.random() < (settings["fichtl_probability_down"] if order == 2 else 1.0)
    )
    local = np.column_stack(
        [np.cos(alpha), np.sin(alpha) * np.cos(beta), np.sin(alpha) * np.sin(beta)]
    )
    candidates = local @ previous_frame.T
    score = candidates[:, 2] if downward else np.abs(candidates[:, 2])
    selected = int(np.argmin(score))
    innovations = dict(alpha=alpha.tolist(), beta=beta.tolist(), downward=downward)
    return unit(candidates[selected]), dict(
        candidates=len(candidates),
        selected_candidate=selected,
        innovations_sha256=digest(innovations),
        **innovations,
    )


def apply_boundary(
    start, heading, length, surface_z, policy, rng=None, diagnostics=None
):
    """Minimum-angle feasible heading projection, applied after arm selection.

    Preserve azimuth, set qz=(S-z)/L at a crossing; a pure-up proposal uses
    the keyed boundary stream. No candidate rejection, clipping or shortening.
    """
    if policy != "minimum_angle_projection":
        raise ValueError("Unapproved/unsupported common boundary policy")
    start = np.asarray(start, dtype=float)
    heading = np.asarray(heading, dtype=float)
    if (
        start.shape != (3,)
        or not np.isfinite(start).all()
        or not np.isfinite(surface_z)
        or not np.isfinite(length)
        or length <= 0
        or not np.isclose(np.linalg.norm(heading), 1, rtol=0, atol=1e-10)
    ):
        raise ValueError("Invalid boundary inputs")
    heading = unit(heading)
    if start[2] > surface_z:
        raise ValueError("Segment starts above shared physical soil surface")
    proposed = start + length * heading
    accepted = np.array(heading, copy=True)
    intervention = bool(proposed[2] > surface_z)
    nudges = 0
    if intervention:
        cap = (surface_z - start[2]) / length
        while start[2] + length * cap > surface_z:
            cap = np.nextafter(cap, -np.inf)
            nudges += 1
        horizontal = np.linalg.norm(heading[:2])
        if horizontal <= 1e-12:
            if rng is None:
                raise ValueError("Pure-up projection requires keyed boundary RNG")
            azimuth = rng.uniform(0, 2 * np.pi)
            azimuth_vector = np.array([np.cos(azimuth), np.sin(azimuth)])
        else:
            azimuth_vector = heading[:2] / horizontal
        accepted = np.r_[np.sqrt(1 - cap**2) * azimuth_vector, cap]
    if diagnostics is not None:
        diagnostics["boundary_ulp_nudges"] = nudges
    return accepted, proposed, intervention


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
    kappas = validate_row_axial_kappas(settings.get("research_insertion_row_axial_kappa"))
    if row_axial_controls_active(kappas):
        if insertion_mode != "fichtl" or settings.get("tropism_mode") != "fichtl2024":
            raise ValueError("Active row-axial controls require Fichtl insertion (arms B/D) and mode")
        input_seed = settings.get("random_seed")
        if (isinstance(input_seed, (bool, np.bool_)) or not isinstance(input_seed, (int, np.integer))
                or input_seed != seed):
            raise ValueError("Active row-axial input seed must match saved skeleton seed")
    return kappas


def replay_arm(
    skeleton: Skeleton,
    arm: str,
    settings: dict,
    boundary_policy: str,
    surface_z: float = 20.0,
):
    """One physical replay; uncorrected one-step proposals are diagnostic records."""
    skeleton.verify()
    if arm not in ARMS or surface_z != 20.0:
        raise ValueError("Controlled design needs arms A-D and shared surface z=20 cm")
    parameters = skeleton.payload["parameters"]
    if (parameters.get("research_base_depth_cm") is not None
            and parameters.get("soil_surface_z_cm") != surface_z):
        raise ValueError("Saved origin surface disagrees with controlled replay surface")
    insertion_mode, continuation_mode = ARMS[arm]
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
        if order not in (2, 3):
            raise ValueError("Controlled SO4 supports orders 1-3 only")
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
                settings[f"fichtl_theta{order}_deg"],
                settings[f"fichtl_theta{order}_sd_deg"],
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
