"""Opt-in straight-root-cylinder observation operator, using only supplied tables.

No file reader, fitting, biological qualification, density inference or coordinate
conversion is provided. Geometry/diameters are cm; density is explicitly dry
g/cm3. Each nonbase node supplies its incoming segment's *constant* diameter.
Fine means child diameter * 10 <= the caller's threshold in mm. Length is the
Euclidean endpoint distance (recorded lengths and root_type classes do not
determine length/fine/coarse). Cylinder clipping uses the root centreline and
applies the same clipped fraction to length, root volume and dry mass; it does
not intersect the root's finite cross section with the soil core boundary.

Graphs must be root-only forests with globally unique integer IDs, one base per
plant and no cross-plant edges. Invalid nodes and all their descendants are
excluded from both core and whole-system support. Legacy statistics are intact.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

VERSION = "finite-cylinder-root-observation-v1"
_CORE_FIELDS = ("core_id", "x_cm", "y_cm", "z_lower_cm", "z_upper_cm", "radius_cm", "sampled")
_VALUE_FIELDS = ("fine_length_cm", "coarse_length_cm", "total_length_cm",
                 "fine_volume_cm3", "coarse_volume_cm3", "total_root_volume_cm3",
                 "fine_dry_mass_g", "coarse_dry_mass_g", "total_dry_mass_g",
                 "fine_rld_cm_cm3", "coarse_rld_cm_cm3", "total_rld_cm_cm3")


@dataclass(frozen=True)
class QualifiedRootSegments:
    """Algorithm-qualified support only; not biological biomass qualification.

    ``segments`` includes excluded cylinders for transparent accounting. Treat
    this table as read-only; obtain a fresh support object after any graph edit.
    """

    segments: pd.DataFrame
    plant_ids: tuple
    coordinate_frame: str
    fine_diameter_max_mm: float
    dry_density_g_cm3: float
    diagnostics: dict
    whole_system_totals: dict


@dataclass(frozen=True)
class CoreObservationPrediction:
    cores: pd.DataFrame
    by_plant: pd.DataFrame | None
    support: QualifiedRootSegments
    diagnostics: dict


def _number(value, name, *, positive=False):
    if isinstance(value, (bool, np.bool_)) or not np.isscalar(value) or np.iscomplexobj(value):
        raise ValueError(f"{name} must be a finite real number")
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError(f"{name} must be a finite real number") from error
    if not np.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{name} must be finite" + (" and positive" if positive else ""))
    return result


def _integers(values, name, minimum=0):
    result = []
    for value in values:
        if (isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer))
                or value < minimum):
            raise ValueError(f"{name} must contain integers >= {minimum}")
        result.append(int(value))
    return result


def _graph_order(nodes, edges):
    """Validate the full topology before excluding anything; O(nodes + edges)."""
    required = {"node_id", "parent_id", "order", "x", "y", "z", "diameter", "root_type", "invalid_root"}
    if not isinstance(nodes, pd.DataFrame) or not isinstance(edges, pd.DataFrame):
        raise ValueError("Nodes and edges must be DataFrames")
    if not required.issubset(nodes) or not {"parent_id", "child_id"}.issubset(edges):
        raise ValueError("Missing root-only node/edge columns")
    if nodes.empty or nodes.columns.duplicated().any() or edges.columns.duplicated().any():
        raise ValueError("Empty graph or duplicate columns")
    nodes = nodes.copy(deep=True)
    if "plant_id" not in nodes:
        nodes["plant_id"] = 0
    ids = _integers(nodes.node_id, "node_id")
    if len(set(ids)) != len(ids):
        raise ValueError("Node IDs must be globally unique")
    parents = dict(zip(ids, _integers(nodes.parent_id, "parent_id", -1)))
    orders = dict(zip(ids, _integers(nodes.order, "order")))
    plants = dict(zip(ids, _integers(nodes.plant_id, "plant_id")))
    if not all(isinstance(flag, (bool, np.bool_)) for flag in nodes.invalid_root):
        raise ValueError("invalid_root must contain strict booleans")
    base_ids = {node for node in ids if orders[node] == 0}
    if (any(parents[node] != -1 for node in base_ids)
            or {node for node in ids if parents[node] == -1} != base_ids
            or len(base_ids) != len(set(plants.values()))
            or len({plants[node] for node in base_ids}) != len(base_ids)):
        raise ValueError("Require exactly one order-0 base per plant")
    base = nodes.node_id.isin(base_ids)
    if not nodes.loc[base, "root_type"].eq("base").all() or not nodes.loc[~base, "root_type"].isin(["fine", "structural"]).all():
        raise ValueError("Only root-only base/fine/structural root_type values are supported")
    children = {node: [] for node in ids}
    expected = set()
    for child, parent in parents.items():
        if child in base_ids:
            continue
        if parent not in parents:
            raise ValueError("Missing parent reference")
        if plants[parent] != plants[child]:
            raise ValueError("Cross-plant edge")
        children[parent].append(child)
        expected.add((parent, child))
    pairs = list(zip(_integers(edges.parent_id, "edge parent"), _integers(edges.child_id, "edge child")))
    if len(pairs) != len(expected) or set(pairs) != expected:
        raise ValueError("Edge/parent agreement or unique incoming edge failed")
    # A rooted traversal proves reachability and rules out disconnected cycles.
    traversal = sorted(base_ids)
    for node in traversal:
        traversal.extend(children[node])
    if len(traversal) != len(ids):
        raise ValueError("Cycle or disconnected root component")
    return nodes.sort_values("node_id").reset_index(drop=True), parents, traversal, base_ids


def _totals(segments):
    result = {"segment_count": len(segments)}
    for name in ("length_cm", "root_volume_cm3", "dry_mass_g"):
        result[name] = math.fsum(segments[name])
        for fine, label in ((True, "fine"), (False, "coarse")):
            result[f"{label}_{name}"] = math.fsum(segments.loc[segments.is_fine.eq(fine), name])
    return result


def qualify_root_segments(nodes, edges, *, coordinate_frame, fine_diameter_max_mm, dry_density_g_cm3):
    """Validate and construct one segment table for all observation calculations.

    The frame name declares an already shared frame; no transformation occurs.
    Dry density is a required caller assumption, never taken from node metadata.
    Zero diameter/zero geometric length are allowed and contribute zero mass.
    Base metadata diameter/length/density does not create an incoming cylinder.
    """
    if not isinstance(coordinate_frame, str) or not coordinate_frame.strip():
        raise ValueError("An explicit coordinate_frame is required")
    threshold = _number(fine_diameter_max_mm, "fine_diameter_max_mm", positive=True)
    density = _number(dry_density_g_cm3, "dry_density_g_cm3", positive=True)
    nodes, parents, traversal, base_ids = _graph_order(nodes, edges)
    try:
        coords = nodes[["x", "y", "z"]].to_numpy(dtype=float)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("Coordinates must be finite cm values") from error
    if not np.isfinite(coords).all():
        raise ValueError("Coordinates must be finite cm values")
    index = {node: i for i, node in enumerate(nodes.node_id)}
    invalid = dict(zip(nodes.node_id, nodes.invalid_root))
    excluded = {}
    for node in traversal:
        excluded[node] = bool(invalid[node] or (node not in base_ids and excluded[parents[node]]))
    roots = nodes.loc[~nodes.node_id.isin(base_ids)]
    start = coords[[index[parent] for parent in roots.parent_id]]
    end = coords[[index[child] for child in roots.node_id]]
    diameter = np.asarray([_number(value, "child diameter") for value in roots.diameter])
    if (diameter < 0).any():
        raise ValueError("Child diameters must be nonnegative cm values")
    with np.errstate(over="ignore", invalid="ignore"):
        delta = end - start
        length = np.hypot(np.hypot(delta[:, 0], delta[:, 1]), delta[:, 2])
        volume = np.pi * (diameter / 2) ** 2 * length
        mass = density * volume
    if not all(np.isfinite(values).all() for values in (length, volume, mass)):
        raise ValueError("Nonfinite geometric cylinder arithmetic")
    segments = pd.DataFrame(dict(
        child_id=roots.node_id.to_numpy(), parent_id=roots.parent_id.to_numpy(),
        plant_id=roots.plant_id.to_numpy(), diameter_cm=diameter,
        # One floating-point ULP prevents a mathematically equal mm/cm
        # conversion (e.g. .07 cm vs .7 mm) becoming a coarse segment.
        is_fine=diameter * 10. <= np.nextafter(threshold, np.inf), length_cm=length,
        root_volume_cm3=volume, dry_mass_g=mass,
        included=[not excluded[node] for node in roots.node_id],
        exclusion_reason=[("invalid_node" if invalid[node] else "invalid_ancestor") if excluded[node] else None
                          for node in roots.node_id],
    ))
    # Explicit dtypes make root-only/base-only graphs valid empty support.
    segments["included"] = segments.included.astype(bool)
    segments["is_fine"] = segments.is_fine.astype(bool)
    for axis, label in enumerate("xyz"):
        segments[f"start_{label}_cm"] = start[:, axis]
        segments[f"end_{label}_cm"] = end[:, axis]
    accepted, rejected = segments.loc[segments.included], segments.loc[~segments.included]
    totals = dict(included=_totals(accepted), excluded=_totals(rejected), all_root_cylinders=_totals(segments))
    diagnostics = dict(version=VERSION, qualification="ALGORITHM_SUPPORT_ONLY", length_source="geometric",
                       cylinder_attributes="constant_child_diameter_and_explicit_uniform_dry_density",
                       invalid_policy="exclude_invalid_nodes_and_descendants", base_node_count=len(base_ids),
                       invalid_node_segment_count=int(segments.exclusion_reason.eq("invalid_node").sum()),
                       invalid_ancestor_segment_count=int(segments.exclusion_reason.eq("invalid_ancestor").sum()),
                       zero_length_segment_count=int((length == 0).sum()), zero_diameter_segment_count=int((diameter == 0).sum()))
    return QualifiedRootSegments(segments, tuple(sorted(nodes.plant_id.unique())), coordinate_frame,
                                 threshold, density, diagnostics, totals)


def _cylinder_fractions(start, end, x, y, lower, upper, radius):
    """Analytic straight-segment intersection, with true-zero parallel tests.

    This opt-in implementation corrects the legacy spatial_rld near-parallel
    reversal/subdivision edge case. The legacy function/defaults/tolerances are
    unchanged. Scaled radial quadratic roots avoid subtracting nearly equal
    squares and the unstable small-root formula; finite-z clipping is exact.
    Extended intermediates preserve ratios of finite float64 coordinates.
    No voxels, positive boundary tolerance or midpoint allocation are used.
    """
    start, end = np.asarray(start, dtype=np.longdouble), np.asarray(end, dtype=np.longdouble)
    d = end - start
    dx, dy, dz = d.T
    rx, ry = start[:, 0] - x, start[:, 1] - y
    enter, leave = np.zeros(len(start), dtype=np.longdouble), np.ones(len(start), dtype=np.longdouble)
    valid = np.ones(len(start), dtype=bool)
    parallel = (dx == 0) & (dy == 0)
    valid[parallel] = np.hypot(rx[parallel], ry[parallel]) <= radius
    varying = ~parallel
    speed = np.hypot(dx[varying], dy[varying])
    magnitude = np.maximum(np.maximum(np.abs(rx[varying]), np.abs(ry[varying])), radius)
    # Binary scaling is exact: arbitrary normalization would lose precision
    # in the small (distance - radius) term for nearly vertical crossings.
    _, exponent = np.frexp(magnitude)
    scale = np.ldexp(np.ones_like(magnitude), exponent - 1)
    px, py, r = rx[varying] / scale, ry[varying] / scale, radius / scale
    ux, uy = dx[varying] / speed, dy[varying] / speed
    projection = px * ux + py * uy
    perpendicular = np.abs(px * uy - py * ux)
    discriminant = (r - perpendicular) * (r + perpendicular)
    valid[varying] = discriminant >= 0
    square = np.sqrt(np.maximum(discriminant, 0))
    # Solve s**2 + 2*projection*s + c = 0 for displacement along
    # the horizontal unit direction, scaled by the radial coordinate scale.
    q = -projection - np.copysign(square, projection)
    distance = np.hypot(px, py)
    c = (distance - r) * (distance + r)
    other = np.divide(c, q, out=np.zeros_like(q), where=q != 0)
    first = np.minimum(q, other) * scale / speed
    last = np.maximum(q, other) * scale / speed
    enter[varying] = np.maximum(enter[varying], first)
    leave[varying] = np.minimum(leave[varying], last)
    vertical = dz != 0
    valid[~vertical] &= (start[~vertical, 2] >= lower) & (start[~vertical, 2] <= upper)
    if np.any(vertical):
        low = (lower - start[vertical, 2]) / dz[vertical]
        high = (upper - start[vertical, 2]) / dz[vertical]
        enter[vertical] = np.maximum(enter[vertical], np.minimum(low, high))
        leave[vertical] = np.minimum(leave[vertical], np.maximum(low, high))
    return np.asarray(np.where(valid, np.maximum(leave - enter, 0), 0), dtype=float)


def _validate_cores(cores):
    if not isinstance(cores, (pd.DataFrame, list, tuple)):
        raise ValueError("Supply an in-memory core DataFrame or sequence of records")
    cores = pd.DataFrame(cores).copy(deep=True)
    if cores.empty and not len(cores.columns):
        cores = pd.DataFrame(columns=_CORE_FIELDS)
    if cores.columns.duplicated().any() or not set(_CORE_FIELDS).issubset(cores):
        raise ValueError(f"Require unique columns including {_CORE_FIELDS}")
    if cores.core_id.isna().any() or not cores.core_id.is_unique:
        raise ValueError("core_id must be present and unique")
    records = []
    for row in cores.to_dict("records"):
        if not isinstance(row["sampled"], (bool, np.bool_)):
            raise ValueError("sampled must be a strict boolean; False means missing observation")
        row = {key: row[key] for key in _CORE_FIELDS} | {"known_volume_cm3": row.get("known_volume_cm3")}
        for field in _CORE_FIELDS[1:-1]:
            row[field] = _number(row[field], field, positive=field == "radius_cm")
        if row["z_upper_cm"] <= row["z_lower_cm"]:
            raise ValueError("Require z_upper_cm > z_lower_cm")
        with np.errstate(over="ignore", invalid="ignore"):
            volume = np.pi * np.square(row["radius_cm"]) * (row["z_upper_cm"] - row["z_lower_cm"])
        if not np.isfinite(volume) or volume <= 0:
            raise ValueError("Invalid core volume arithmetic")
        known = row["known_volume_cm3"]
        if known is not None and not pd.isna(known):
            known = _number(known, "known_volume_cm3", positive=True)
            # Numerical agreement check, not a biological tolerance.
            if not np.isclose(known, volume, rtol=1e-9, atol=1e-12):
                raise ValueError("known_volume_cm3 disagrees with the cylinder geometry")
        row["core_volume_cm3"] = float(volume)
        records.append(row)
    return records


def _prediction_values(fractions, segments, volume, sampled):
    if not sampled:
        return dict.fromkeys(_VALUE_FIELDS, np.nan)
    values = {}
    fine = segments.is_fine.to_numpy()
    for source, target in (("length_cm", "length_cm"), ("root_volume_cm3", "volume_cm3"), ("dry_mass_g", "dry_mass_g")):
        weighted = fractions * segments[source].to_numpy()
        values[f"fine_{target}"] = float(weighted[fine].sum())
        values[f"coarse_{target}"] = float(weighted[~fine].sum())
        total = "total_root_volume_cm3" if target == "volume_cm3" else f"total_{target}"
        values[total] = values[f"fine_{target}"] + values[f"coarse_{target}"]
    for label in ("fine", "coarse", "total"):
        values[f"{label}_rld_cm_cm3"] = values[f"{label}_length_cm"] / volume
    return values


def predict_core_observations(support, cores, *, by_plant=False):
    """Batch predictions, preserving input core order and explicit missingness.

    Core fields are core_id, x_cm, y_cm, z_lower_cm, z_upper_cm, radius_cm,
    sampled (strict bool), and optionally known_volume_cm3. All coordinates
    must already share ``support.coordinate_frame``. Overlapping cores are
    separate observations; summing them is not a whole-system mass estimate.
    Bounded boxes prune candidates before exact segment intersection, requiring
    O(segments) memory rather than an all-cores-by-all-segments matrix.
    """
    if not isinstance(support, QualifiedRootSegments):
        raise ValueError("Require qualify_root_segments output")
    if not isinstance(by_plant, (bool, np.bool_)):
        raise ValueError("by_plant must be a strict boolean")
    records = _validate_cores(cores)
    segments = support.segments.loc[support.segments.included].reset_index(drop=True)
    start = segments[[f"start_{axis}_cm" for axis in "xyz"]].to_numpy()
    end = segments[[f"end_{axis}_cm" for axis in "xyz"]].to_numpy()
    low, high = np.minimum(start, end), np.maximum(start, end)
    results, per_plant, candidates = [], [], 0
    for core in records:
        radius, x, y = core["radius_cm"], core["x_cm"], core["y_cm"]
        mask = ((high[:, 0] >= x - radius) & (low[:, 0] <= x + radius)
                & (high[:, 1] >= y - radius) & (low[:, 1] <= y + radius)
                & (high[:, 2] >= core["z_lower_cm"]) & (low[:, 2] <= core["z_upper_cm"]))
        if not core["sampled"]:
            mask[:] = False
        selected = segments.loc[mask]
        fractions = _cylinder_fractions(start[mask], end[mask], x, y, core["z_lower_cm"], core["z_upper_cm"], radius)
        candidates += len(selected)
        values = _prediction_values(fractions, selected, core["core_volume_cm3"], core["sampled"])
        results.append(core | values)
        if by_plant:
            for plant in support.plant_ids:
                plant_mask = selected.plant_id.eq(plant).to_numpy()
                per_plant.append(core | {"plant_id": plant} | _prediction_values(
                    fractions[plant_mask], selected.loc[plant_mask], core["core_volume_cm3"], core["sampled"]))
    columns = list(_CORE_FIELDS) + ["known_volume_cm3", "core_volume_cm3"] + list(_VALUE_FIELDS)
    return CoreObservationPrediction(
        pd.DataFrame(results, columns=columns),
        pd.DataFrame(per_plant, columns=columns + ["plant_id"]) if by_plant else None,
        support, dict(version=VERSION, candidate_segment_core_pairs=candidates,
                      included_segment_count=len(segments), core_count=len(records),
                      sampled_core_count=sum(bool(core["sampled"]) for core in records),
                      coordinate_frame=support.coordinate_frame,
                      intersection="exact_straight_segment_finite_vertical_cylinder",
                      mass_support="same_centreline_fraction_as_length"))
