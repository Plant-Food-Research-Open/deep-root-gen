"""Reconcile raw hierarchical axes with nested RSML in the mature 5C archive."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
from math import dist
from pathlib import Path

from scripts.data.grapevine3d_contract import (
    TOLERANCE_CM,
    duplicate_ids,
    read_raw_records,
    read_rsml,
    signed_permutation,
    v2_candidate_contract,
)


RSML_ORDERS = {"primary": 1, "secondary": 2, "tertiary": 3, "quaternary": 4}


@dataclass(frozen=True)
class _RawAxis:
    parent_axis: str | None
    order: int
    points: tuple
    length_cm: float


def _raw_axis_id(point_id):
    parts = point_id.split(".")
    if len(parts) == 1:
        return None  # non-root scaffold landmarks
    if len(parts) % 2 != 1:
        raise ValueError(f"Unexpected hierarchical raw point ID {point_id!r}")
    return ".".join(parts[:-1])


def _index_raw_points(records, duplicate_policy):
    if duplicate_policy not in ("reject", "first", "last"):
        raise ValueError("Choose reject, first or last duplicate policy")
    duplicates = duplicate_ids(records)
    if duplicates and duplicate_policy == "reject":
        details = ", ".join(f"{key} (lines {[records[i].source_line for i in indices]})"
                            for key, indices in sorted(duplicates.items()))
        raise ValueError(f"Duplicate raw point IDs: {details}")
    for key, indices in duplicates.items():
        if len({records[i].parent_id for i in indices}) != 1:
            raise ValueError(f"Duplicate raw point {key!r} has conflicting parentage")
    selected = reversed(records) if duplicate_policy == "last" else records
    result = {}
    for record in selected:
        result.setdefault(record.record_id, record)
    return result, duplicates


def _raw_axes(nodes):
    groups = defaultdict(list)
    for record in nodes.values():
        axis_id = _raw_axis_id(record.record_id)
        if axis_id is not None:
            groups[axis_id].append(record)
    axes = {}
    for axis_id, group in groups.items():
        order = len(axis_id.split(".")) // 2
        group.sort(key=lambda record: int(record.record_id.rsplit(".", 1)[1]))
        parent_id = group[0].parent_id
        if parent_id not in nodes:
            raise ValueError(f"Raw axis {axis_id} lacks an attachment point")
        parent_axis = _raw_axis_id(parent_id)
        if (order == 1 and parent_axis is not None) or (
            order > 1 and parent_axis != axis_id.rsplit(".", 2)[0]
        ):
            raise ValueError(f"Raw axis {axis_id} has inconsistent anatomical parentage")
        previous = nodes[parent_id]
        length = 0.
        for index, record in enumerate(group, start=1):
            if record.record_id != f"{axis_id}.{index}" or record.parent_id != previous.record_id:
                raise ValueError(f"Discontinuous serial points on raw axis {axis_id}")
            length += dist(previous.coordinates_cm, record.coordinates_cm)
            previous = record
        axes[axis_id] = _RawAxis(parent_axis, order, tuple(record.coordinates_cm for record in group), length)
    return axes


def _source_sequences(records, duplicates):
    """Keep both occurrences on affected axes for a representation-only match."""
    affected = {_raw_axis_id(key) for key in duplicates}
    sequences = defaultdict(list)
    for record in records:
        axis_id = _raw_axis_id(record.record_id)
        if axis_id is not None and axis_id in affected:
            serial = int(record.record_id.rsplit(".", 1)[1])
            sequences[axis_id].append((serial, record.coordinates_cm))
    return {key: tuple(point for _, point in sorted(rows, key=lambda row: row[0]))
            for key, rows in sequences.items()}


def _reconcile(axes, nodes, architecture, duplicate_sequences):
    frame = v2_candidate_contract()
    stem = architecture.polylines[architecture.stem_index]
    if (set(nodes) & {"1", "2"} != {"1", "2"} or stem.points_cm[0] != (0., 0., 0.)
            or len(stem.points_cm) != 2):
        raise ValueError("Expected the archive's two soil/basal anchors")
    soil = nodes["1"].coordinates_cm

    def to_rsml(point):
        return signed_permutation(tuple(v - s for v, s in zip(point, soil)), frame)

    if dist(to_rsml(nodes["2"].coordinates_cm), stem.points_cm[1]) > TOLERANCE_CM:
        raise ValueError("Raw and RSML stem landmarks disagree under the declared frame")

    mapped = {architecture.stem_index: None}
    used = set()
    unmatched = []
    matches = []
    rsml_counts = Counter()
    seen = {stem.root_id}
    for index, polyline in enumerate(architecture.polylines):
        if index == architecture.stem_index:
            continue
        root_id = polyline.root_id
        if not root_id or root_id in seen:
            raise ValueError(f"Missing or duplicate RSML axis ID {root_id!r}")
        seen.add(root_id)
        if polyline.label not in RSML_ORDERS:
            raise ValueError(f"Unknown RSML root order label {polyline.label!r}")
        order = RSML_ORDERS[polyline.label]
        parent_label = architecture.polylines[polyline.parent_index].label
        if RSML_ORDERS.get(parent_label, 0) != order - 1:
            raise ValueError(f"RSML axis {root_id} has inconsistent anatomical parentage")
        rsml_counts[order] += 1
        candidates = {}
        if polyline.parent_index in mapped:
            for key, axis in axes.items():
                points = duplicate_sequences.get(key, axis.points)
                if (axis.parent_axis != mapped[polyline.parent_index] or axis.order != order
                        or len(points) != len(polyline.points_cm)):
                    continue
                residual = max(dist(to_rsml(a), b) for a, b in zip(points, polyline.points_cm))
                if residual <= TOLERANCE_CM:
                    candidates[key] = residual
        if len(candidates) != 1 or (candidates.keys() & used):
            unmatched.append(dict(rsml_id=root_id, order=order, candidates=sorted(candidates)))
            continue
        key, residual = next(iter(candidates.items()))
        used.add(key)
        mapped[index] = key
        matches.append(dict(rsml_id=root_id, raw_axis=key, order=order, max_residual_cm=residual,
                            matches_both_duplicate_occurrences=key in duplicate_sequences))
    return rsml_counts, used, matches, unmatched


def inspect_archive_pair(raw_path, rsml_path, *, duplicate_policy="reject"):
    """Match whole ordered coordinate sequences and nesting, retaining omissions."""
    raw_path, rsml_path = Path(raw_path), Path(rsml_path)
    records = read_raw_records(raw_path)
    nodes, duplicates = _index_raw_points(records, duplicate_policy)
    axes = _raw_axes(nodes)
    rsml_counts, used, matches, unmatched = _reconcile(
        axes, nodes, read_rsml(rsml_path), _source_sequences(records, duplicates)
    )
    raw_counts = Counter(axis.order for axis in axes.values())
    return dict(
        units="cm", frame="raw soil landmark 1 to RSML origin; (raw-y, -raw-z, raw-x)",
        raw_sha256=sha256(raw_path.read_bytes()).hexdigest(), rsml_sha256=sha256(rsml_path.read_bytes()).hexdigest(),
        raw_counts=dict(sorted(raw_counts.items())), rsml_counts=dict(sorted(rsml_counts.items())),
        inventories_agree=raw_counts == rsml_counts, duplicates=duplicates,
        duplicate_policy=duplicate_policy, included_in_geometric_summary=not duplicates,
        matches=matches, unmatched_rsml=unmatched,
        raw_only=[
            dict(raw_axis=key, order=axis.order, points=len(axis.points), length_cm=axis.length_cm,
                 parent_in_rsml=axis.parent_axis in used)
            for key, axis in sorted(axes.items()) if key not in used
        ],
    )
