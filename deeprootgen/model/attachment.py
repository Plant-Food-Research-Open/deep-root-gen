"""Pure primary cut operation shared by native execution and archived replay."""

import copy
import numpy as np
from .controlled_geometry import unit, minimal_rotation

XYZ = ["x", "y", "z"]
CUTOFF_CM = 1e-12
CURVE_ATOL_CM = 1e-8


def subdivide_primary(rows, curves, plans):
    next_id = max(rows) + 1
    attachments, inserted = {}, []
    for oid, curve in curves.items():
        arcs = np.asarray(curve["cumulative_cm"])
        old_ids = curve["node_ids"]
        points = np.asarray(curve["points_cm"])
        sites = sorted({p["new_arc_cm"] for p in plans if p["primary_organ_id"] == oid})
        cuts = sorted(set(arcs.tolist()) | set(sites))
        vertex_ids = dict(zip(arcs.tolist(), old_ids))
        previous_id, rank = old_ids[0], 0
        for arc in cuts[1:]:
            edge = int(np.searchsorted(arcs[1:], arc, side="left"))
            original_child = old_ids[edge + 1]
            if arc in vertex_ids:
                nid = vertex_ids[arc]
            else:
                nid, next_id = next_id, next_id + 1
                t = (arc - arcs[edge]) / (arcs[edge + 1] - arcs[edge])
                xyz = points[edge] + t * (points[edge + 1] - points[edge])
                rows[nid] = copy.deepcopy(rows[original_child])
                rows[nid].update(node_id=nid, **dict(zip(XYZ, xyz.tolist())))
                inserted.append(nid)
                vertex_ids[arc] = nid
            # Constant original child diameter and all other cylinder properties
            # over every split piece. Only chain/rank/length change on old nodes.
            row = rows[nid]
            previous_arc = cuts[rank]
            stored_length = curve["stored_lengths_cm"][edge] * (
                (arc - previous_arc) / (arcs[edge + 1] - arcs[edge])
            )
            distance = np.linalg.norm(
                np.array([row[c] for c in XYZ])
                - np.array([rows[previous_id][c] for c in XYZ])
            )
            if (
                stored_length <= CUTOFF_CM
                or distance <= CUTOFF_CM
                or not np.isfinite(distance)
            ):
                raise ValueError(
                    "Unsplittable positive primary edge; no epsilon snapping"
                )
            rank += 1
            row.update(
                parent_id=int(previous_id),
                segment_rank=rank,
                length=float(stored_length),
            )
            previous_id = nid
        for site in sites:
            attachments[(oid, site)] = vertex_ids[site]
    return attachments, inserted


def _primary_curves(organs, nodes):
    lookup = nodes.set_index("node_id")
    curves = {}
    for organ in sorted(organs, key=lambda o: o["organ_id"]):
        if organ["order"] != 1:
            continue
        ids = [organ["parent_id"], *organ["node_ids"]]
        points = lookup.loc[ids, XYZ].to_numpy(float)
        geometric = np.linalg.norm(np.diff(points, axis=0), axis=1)
        stored = lookup.loc[organ["node_ids"], "length"].to_numpy(float)
        if (
            not np.isfinite(geometric).all()
            or (geometric <= CUTOFF_CM).any()
            or not np.allclose(geometric, stored, rtol=0, atol=CURVE_ATOL_CM)
        ):
            raise ValueError("Original primary geometric/stored lengths disagree")
        curves[organ["organ_id"]] = dict(
            organ_id=organ["organ_id"],
            node_ids=ids,
            points_cm=points.tolist(),
            cumulative_cm=np.r_[0.0, np.cumsum(geometric)].tolist(),
            edge_lengths_cm=geometric.tolist(),
            stored_lengths_cm=stored.tolist(),
            child_diameters_cm=lookup.loc[organ["node_ids"], "diameter"].tolist(),
        )
    return curves


def distal_arc_cm(old_arc, total, fraction):
    """Distal relocation of a primary attachment on physical arclength."""
    return total if old_arc == total else fraction * total + (1.0 - fraction) * old_arc


def _placements(organs, nodes, curves, fraction):
    lookup = nodes.set_index("node_id")
    plans = []
    for organ in sorted(organs, key=lambda o: o["organ_id"]):
        if organ["order"] != 2:
            continue
        parent = lookup.loc[organ["parent_id"]]
        if int(parent.order) != 1 or int(parent.organ_id) not in curves:
            raise ValueError("Root2 must attach to an original primary curve")
        curve = curves[int(parent.organ_id)]
        old_index = curve["node_ids"].index(organ["parent_id"])
        if old_index == 0:
            raise ValueError(
                "Root2 origin cannot use a primary base with no incoming tangent"
            )
        old_arc, total = curve["cumulative_cm"][old_index], curve["cumulative_cm"][-1]
        if not np.isclose(
            organ["attachment_arc_cm"], old_arc, rtol=0, atol=CURVE_ATOL_CM
        ):
            raise ValueError("Original physical Root2 arc disagrees with primary curve")
        new_arc = distal_arc_cm(old_arc, total, fraction)
        if not np.isfinite(new_arc) or (
            old_arc < total and not old_arc < new_arc < total
        ):
            raise ValueError(
                "Distal site cannot be represented without endpoint snapping/nonprogress"
            )
        plans.append(
            dict(
                organ_id=organ["organ_id"],
                primary_organ_id=int(parent.organ_id),
                old_parent_id=organ["parent_id"],
                old_arc_cm=old_arc,
                new_arc_cm=new_arc,
                primary_length_cm=total,
            )
        )
    for oid in curves:
        family = [p for p in plans if p["primary_organ_id"] == oid]
        for a, b in zip(
            sorted(family, key=lambda p: p["old_arc_cm"]),
            sorted(family, key=lambda p: p["old_arc_cm"])[1:],
        ):
            if (
                a["old_arc_cm"] != b["old_arc_cm"]
                and a["new_arc_cm"] == b["new_arc_cm"]
            ):
                raise ValueError("Distinct distal sites rounded to a collision")
    return plans


def _subtree_ids(first, children):
    pending, found = [first], set()
    while pending:
        node = pending.pop()
        if node in found:
            raise ValueError("Cycle in primary attachment subtree")
        found.add(node)
        pending.extend(children[node])
    return found


def transform_rows(records, organs, curves, plans):
    rows = {int(row["node_id"]): copy.deepcopy(row) for row in records}
    source_rows = copy.deepcopy(rows)
    attachments, inserted = subdivide_primary(rows, curves, plans)
    children = {nid: [] for nid in source_rows}
    for row in records:
        if row["order"] > 0:
            children[row["parent_id"]].append(row["node_id"])
    organ_lookup = {o["organ_id"]: o for o in organs}
    covered, transforms = set(), []
    for plan in plans:
        organ = organ_lookup[plan["organ_id"]]
        old_parent_id = plan["old_parent_id"]
        new_parent_id = attachments[(plan["primary_organ_id"], plan["new_arc_cm"])]
        old_parent, new_parent = source_rows[old_parent_id], rows[new_parent_id]
        old_anchor = np.array([old_parent[c] for c in XYZ])
        new_anchor = np.array([new_parent[c] for c in XYZ])
        old_tangent = unit(
            old_anchor
            - np.array([source_rows[old_parent["parent_id"]][c] for c in XYZ])
        )
        new_tangent = unit(
            new_anchor - np.array([rows[new_parent["parent_id"]][c] for c in XYZ])
        )
        rotation = minimal_rotation(old_tangent, new_tangent)
        ids = _subtree_ids(organ["node_ids"][0], children)
        if covered & ids or any(source_rows[nid]["order"] <= 1 for nid in ids):
            raise ValueError("Overlapping/non-Root2 subtree in primary placement")
        for nid in sorted(ids):
            point = np.array([source_rows[nid][c] for c in XYZ])
            xyz = new_anchor + rotation @ (point - old_anchor)
            rows[nid].update(dict(zip(XYZ, xyz.tolist())))
        rows[organ["node_ids"][0]]["parent_id"] = int(new_parent_id)
        covered.update(ids)
        transforms.append(
            dict(
                **plan,
                new_parent_id=int(new_parent_id),
                subtree_node_ids=sorted(ids),
                old_anchor_cm=old_anchor.tolist(),
                new_anchor_cm=new_anchor.tolist(),
                old_tangent=old_tangent.tolist(),
                new_tangent=new_tangent.tolist(),
                rotation=rotation.tolist()
            )
        )
    if covered != {nid for nid, row in source_rows.items() if row["order"] > 1}:
        raise ValueError("Primary placement subtrees do not cover all higher orders")
    return rows, inserted, transforms
