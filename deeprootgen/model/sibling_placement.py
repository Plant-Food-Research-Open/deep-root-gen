"""Couple sibling azimuths locally while keeping a uniform random group rotation."""

from collections import defaultdict

import numpy as np

from ..utils.primary_orientation import proper_rotation
from ..utils.tropism import _basis


def sector_bearings(count, rng):
    phase = rng.uniform(0, 2 * np.pi)
    sectors = rng.permutation(count)
    return phase + (sectors + rng.random(count)) * (2 * np.pi / count)


def transported_normals(steps):
    """Parallel transport a normal along the ordered incoming parent tangents."""
    tangents = steps / np.linalg.norm(steps, axis=1)[:, None]
    normals = np.empty_like(tangents)
    normals[0] = _basis(tangents[0])[1]
    for i in range(1, len(steps)):
        normal = proper_rotation(tangents[i - 1], tangents[i]) @ normals[i - 1]
        normal -= (normal @ tangents[i]) * tangents[i]
        normals[i] = normal / np.linalg.norm(normal)
    return tangents, normals


def sibling_directions(state, daughters, settings):
    """Map daughter IDs to transverse unit vectors on the already realized parent."""
    families = defaultdict(list)
    minimum_depth = settings.get("min_birth_depth_cm")
    for child in daughters:
        if minimum_depth is not None:
            depth = state.laws.surface_z_cm - child.parent_node.node_data.z
            if depth <= minimum_depth:
                continue
        if not child.invalid_root:
            families[child.parent_node.organ].append(child)
    directions = {}
    eligible_groups = selected_groups = 0
    for parent, children in families.items():
        if len(children) < 2:
            continue
        parent_id = int(parent.segments[0].node_data.organ_id)
        curve = state.curves.get(parent_id)
        indices = {id(n): i for i, n in enumerate(parent.segments)}
        if curve is None:
            head = parent.parent_node.node_data
            points = np.vstack(([head.x, head.y, head.z], parent.get_coordinates()))
            arcs = np.cumsum(parent.get_lengths())
            stations = np.r_[0., arcs]
        else:
            points, arcs, stations = curve.points, curve.construction_arcs, curve.stations
        groups = defaultdict(list)
        for child in children:
            arc = arcs[indices[id(child.parent_node)]]
            oid = int(child.segments[0].node_data.organ_id)
            groups[int(arc // settings["window_cm"])].append((arc, oid))
        frame = None
        for window, members in groups.items():
            if len(members) < 2:
                continue
            eligible_groups += 1
            rng = state.streams.keyed("feature.insertion.sibling_sectors", "v1", parent_id, window)
            if rng.random() >= settings["fraction"]:
                continue
            selected_groups += 1
            if frame is None:
                frame = transported_normals(np.diff(points, axis=0))
            tangents, normals = frame
            for (arc, oid), phi in zip(sorted(members), sector_bearings(len(members), rng)):
                j = np.clip(np.searchsorted(stations, arc, side="left") - 1, 0, len(normals) - 1)
                directions[oid] = normals[j] * np.cos(phi) + np.cross(tangents[j], normals[j]) * np.sin(phi)
    if minimum_depth is not None:
        state.diagnostics.setdefault("depth_sibling_sectors", []).append(dict(
            eligible_groups=eligible_groups, selected_groups=selected_groups,
            daughters_steered=len(directions),
        ))
    return directions
