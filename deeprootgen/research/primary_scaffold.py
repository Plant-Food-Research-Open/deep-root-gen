"""Pure matched-primary reference isolation for controlled construction studies."""

import copy

import numpy as np
import pandas as pd

from .construction_step_replay import validate_construction_metadata
from .so4_controlled import Skeleton, XYZ, digest, invariant_hashes, minimal_rotation, unit, validate_geometry

VERSION = "so4-primary-scaffold-reference-v1"


def _reference_match(new, reference, nodes, target):
    if new.payload["seed"] != reference.payload["seed"]:
        raise ValueError("Primary reference seed mismatch")
    primary = nodes.loc[nodes.order.le(1)].sort_values("node_id").reset_index(drop=True)
    expected = target.loc[target.order.le(1)].sort_values("node_id").reset_index(drop=True)
    if set(primary.columns) != set(expected.columns):
        raise ValueError("Primary reference schema fields disagree")
    primary = primary.reindex(columns=sorted(primary.columns))
    expected = expected.reindex(columns=primary.columns)
    try:
        pd.testing.assert_frame_equal(primary.drop(columns=XYZ), expected.drop(columns=XYZ), check_exact=True)
        pd.testing.assert_frame_equal(primary.loc[primary.order.eq(0)], expected.loc[expected.order.eq(0)], check_exact=True)
    except AssertionError as error:
        raise ValueError("Primary reference identities/base/lengths/dimensions disagree") from error
    roots = [{o["organ_id"]: o for o in source.payload["organs"] if o["order"] == 2}
             for source in (new, reference)]
    if roots[0].keys() != roots[1].keys():
        raise ValueError("Primary reference order2 identities disagree")
    for oid, organ in roots[0].items():
        other = roots[1][oid]
        if organ["parent_id"] != other["parent_id"] or organ["attachment_arc_cm"] != other["attachment_arc_cm"]:
            raise ValueError("Primary reference attachment mismatch")
        first, second = organ["construction_steps"], other["construction_steps"]
        keys = ("stream_version", "seed", "order", "expected_organ_id", "quantile", "cdf_sha256", "normalized_weights")
        if first["lengths_cm"] != second["lengths_cm"] or any(first["sampler"][key] != second["sampler"][key] for key in keys):
            raise ValueError("Primary reference order2 construction steps/sampler disagree")
    return roots[0]


def _subtree_ids(first, children):
    pending, result = [first], set()
    while pending:
        node = pending.pop()
        if node in result:
            raise ValueError("Repeated/cyclic primary-reference subtree")
        result.add(node)
        pending.extend(children[node])
    return result


def freeze_primary_scaffold(new, reference):
    """Return a new INITIAL; neither input nor any RNG is mutated.

    Match base, primary records and primary->order2 attachments, transport each
    complete order2 subtree by a deterministic minimal tangent rotation, then
    copy reference primary coordinates exactly. Tertiary identities/samples and
    inherited diameters remain those of NEW, not matched to the reference.
    """
    new.verify()
    reference.verify()
    validate_construction_metadata(new)
    validate_construction_metadata(reference)
    original = pd.DataFrame(new.payload["nodes"])
    target = pd.DataFrame(reference.payload["nodes"])
    organs = _reference_match(new, reference, original, target)
    nodes = original.set_index("node_id", drop=False).copy(deep=True)
    lookup = target.set_index("node_id")
    children = {int(nid): [] for nid in nodes.node_id}
    for row in nodes.loc[nodes.order.gt(0)].itertuples():
        children[int(row.parent_id)].append(int(row.node_id))
    assigned, transforms = set(), []
    for oid, organ in sorted(organs.items()):
        parent = nodes.loc[organ["parent_id"]]
        endpoint = lookup.loc[organ["parent_id"]]
        old_anchor, new_anchor = parent[XYZ].to_numpy(float), endpoint[XYZ].to_numpy(float)
        old_tangent = unit(old_anchor - nodes.loc[int(parent.parent_id), XYZ].to_numpy(float))
        new_tangent = unit(new_anchor - lookup.loc[int(endpoint.parent_id), XYZ].to_numpy(float))
        rotation = minimal_rotation(old_tangent, new_tangent)
        ids = _subtree_ids(organ["node_ids"][0], children)
        if ids & assigned or not nodes.loc[list(ids), "order"].gt(1).all():
            raise ValueError("Overlapping or non-root2 primary-reference subtree")
        if not (np.array_equal(old_anchor, new_anchor) and np.array_equal(rotation, np.eye(3))):
            coordinates = nodes.loc[list(ids), XYZ].to_numpy(float)
            nodes.loc[list(ids), XYZ] = new_anchor + (coordinates - old_anchor) @ rotation.T
        assigned.update(ids)
        transforms.append(dict(organ_id=oid, parent_id=int(organ["parent_id"]), node_ids=sorted(ids),
                               old_anchor_cm=old_anchor.tolist(), reference_anchor_cm=new_anchor.tolist(),
                               old_tangent=old_tangent.tolist(), reference_tangent=new_tangent.tolist(), rotation=rotation.tolist()))
    if assigned != set(nodes.loc[nodes.order.gt(1), "node_id"]):
        raise ValueError("Primary-reference subtrees do not cover higher orders")
    primary_ids = nodes.loc[nodes.order.le(1), "node_id"].tolist()
    nodes.loc[primary_ids, XYZ] = lookup.loc[primary_ids, XYZ].to_numpy(float)
    realised = nodes.reset_index(drop=True)
    edges = pd.DataFrame(new.payload["edges"])
    validate_geometry(realised, edges)
    before, after = invariant_hashes(original), invariant_hashes(realised)
    if any(before[key] != after[key] for key in ("frozen_nodes", "edges", "attachments")):
        raise ValueError("Primary reference changed frozen dimensions/topology/attachments")
    result = Skeleton.from_tables(realised, edges, new.payload["seed"], copy.deepcopy(new.payload["parameters"]))
    old_organs = {organ["organ_id"]: organ for organ in new.payload["organs"]}
    live = realised.set_index("node_id")
    for organ in result.payload["organs"]:
        for key, value in old_organs[organ["organ_id"]].items():
            if key not in organ:
                organ[key] = copy.deepcopy(value)
        if "construction_steps" in organ:
            metadata = organ["construction_steps"]
            ids = [organ["parent_id"], *metadata["boundary_node_ids"]]
            metadata["positioned_boundary_xyz"] = live.loc[ids, XYZ].to_numpy(float).tolist()
    result.payload["primary_scaffold_reference"] = dict(
        version=VERSION, reference_sha256=reference.sha256, source_sha256=new.sha256, transforms=transforms,
        retained_couplings=["tertiary birth keys may differ", "new attachment-dependent daughter diameters retained"],
    )
    result.sha256 = digest(result.payload)
    validate_construction_metadata(result)
    return result
