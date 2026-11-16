"""Explicit observation-frame declarations and point-set checks, using stdlib only.

Raw landmark meanings follow Fichtl2024. Raw-to-RSML mappings remain caller
contracts: a successful fixed-transform check does not establish topology.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from scripts.data.grapevine3d_grid import Segment, Vine

Point = tuple[float, float, float]
TOLERANCE_CM = 1e-8


@dataclass(frozen=True)
class RawRecord:
    """One coordinate row, retaining textual IDs, annotations and occurrence."""

    record_id: str
    parent_id: str | None
    coordinates_cm: Point
    constant: float
    angles: Point
    source_line: int
    module_kind: str
    id_annotation: str
    parent_annotation: str
    annotations: tuple[str, ...]


def duplicate_ids(records: tuple[RawRecord, ...]) -> dict[str, tuple[int, ...]]:
    """Indices of every repeated ID; records are never overwritten or merged."""
    groups: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        groups[record.record_id].append(index)
    return {key: tuple(indices) for key, indices in groups.items() if len(indices) > 1}


def _identifier(annotation: str, *, parent: bool = False) -> str | None:
    value = annotation.strip()
    if parent and value.lower() in {"none", "null", "-1"}:
        return None
    if parent:
        value = re.sub(r"^Node\s+", "", value, flags=re.IGNORECASE)
    token = re.split(r"[\s;]+", value, maxsplit=1)[0]
    if not re.fullmatch(r"\d+(?:\.\d+)*", token):
        raise ValueError(f"Expected a textual hierarchical ID: {annotation!r}")
    return token


def _coordinate_row(line: str, number: int) -> tuple[float, ...]:
    fields = line.split(";")
    if len(fields) != 7:
        raise ValueError(f"Line {number}: expected seven semicolon fields")
    try:
        values = tuple(float(field.strip()) for field in fields)
    except ValueError as error:
        raise ValueError(f"Line {number}: invalid numeric coordinate row") from error
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"Line {number}: nonfinite raw value")
    return values


def _module_records(lines: list[tuple[int, str]]) -> tuple[RawRecord, ...]:
    ids, parents, coordinates, annotations = [], [], [], []
    for number, line in lines:
        match = re.fullmatch(r"(ID|Parent)\s*:\s*(.+)", line, flags=re.IGNORECASE)
        if match:
            (ids if match[1].lower() == "id" else parents).append(match[2])
        elif ";" in line:
            coordinates.append((number, _coordinate_row(line, number)))
        elif not re.fullmatch(r"[\w -]+(?::.*)?", line):
            raise ValueError(f"Line {number}: unsupported module annotation")
        annotations.append(line)
    if len(ids) != 1 or len(parents) != 1 or not coordinates:
        raise ValueError("Every Node module requires one ID, one Parent and coordinate rows")
    record_id = _identifier(ids[0])
    parent_id = _identifier(parents[0], parent=True)
    return tuple(RawRecord(
        record_id=record_id, parent_id=parent_id,
        coordinates_cm=values[1:4], constant=values[0], angles=values[4:7],
        source_line=number, module_kind="Node", id_annotation=ids[0],
        parent_annotation=parents[0], annotations=tuple(annotations),
    ) for number, values in coordinates)


def parse_raw_records(text: str, *, units: str = "cm") -> tuple[RawRecord, ...]:
    """Parse //Node ... //EndModule blocks; raw IDs are strings, never floats.

    Header text before the first module is permitted. IDs and Parent annotations
    may include suffix kinds, and Parent may have a leading Node token. All
    coordinate rows and duplicate IDs survive. Declared units must be cm.
    """
    if units != "cm":
        raise ValueError("Raw contract requires declared cm units")
    records: list[RawRecord] = []
    module: list[tuple[int, str]] | None = None
    seen_module = False
    for number, original in enumerate(text.splitlines(), 1):
        line = original.strip().lstrip("\ufeff")
        if not line:
            continue
        if line.lower() == "//node":
            if module is not None:
                raise ValueError(f"Line {number}: nested module")
            module, seen_module = [], True
        elif line.lower() == "//endmodule":
            if module is None:
                raise ValueError(f"Line {number}: EndModule without Node")
            records.extend(_module_records(module))
            module = None
        elif module is not None:
            module.append((number, line))
        elif seen_module or line.startswith("//"):
            raise ValueError(f"Line {number}: unexpected text outside a Node module")
    if module is not None or not records:
        raise ValueError("Unterminated module or no raw coordinate records")
    return tuple(records)


def read_raw_records(path: str | Path, *, units: str = "cm") -> tuple[RawRecord, ...]:
    return parse_raw_records(Path(path).read_text(encoding="utf-8-sig"), units=units)


@dataclass(frozen=True)
class RsmlPolyline:
    label: str
    points_cm: tuple[Point, ...]
    parent_index: int | None
    root_id: str | None


@dataclass(frozen=True)
class RsmlArchitecture:
    plant_label: str
    polylines: tuple[RsmlPolyline, ...]
    stem_index: int


def _children(element, tag):
    return [child for child in element if child.tag.rsplit("}", 1)[-1] == tag]


def _child(element, tag):
    matches = _children(element, tag)
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one RSML {tag}")
    return matches[0]


def _rsml_point(element) -> Point:
    try:
        coordinates = tuple(float(element.attrib[axis]) for axis in "xyz")
    except (KeyError, ValueError) as error:
        raise ValueError("RSML points require numeric x/y/z") from error
    if not all(math.isfinite(value) for value in coordinates):
        raise ValueError("Nonfinite RSML point")
    return coordinates


def parse_rsml(text: str | bytes) -> RsmlArchitecture:
    """Read 3-D cm geometry and nesting without frame inference or attachment repair."""
    document = ElementTree.fromstring(text)
    if (_child(_child(document, "metadata"), "unit").text or "").strip() != "cm":
        raise ValueError("RSML contract requires cm units")
    plant = _child(_child(document, "scene"), "plant")
    top_roots = _children(plant, "root")
    if len(top_roots) != 1 or top_roots[0].get("label") != "stem":
        raise ValueError("Expected one top-level RSML root labelled stem")
    polylines: list[RsmlPolyline] = []

    def visit(root, parent_index):
        polyline = _child(_child(root, "geometry"), "polyline")
        points = tuple(_rsml_point(point) for point in _children(polyline, "point"))
        if not points:
            raise ValueError("Empty RSML root polyline")
        index = len(polylines)
        polylines.append(RsmlPolyline(root.get("label", "other"), points,
                                      parent_index, root.get("id")))
        for child in _children(root, "root"):
            visit(child, index)

    visit(top_roots[0], None)
    return RsmlArchitecture(plant.get("label", ""), tuple(polylines), 0)


def read_rsml(path: str | Path) -> RsmlArchitecture:
    return parse_rsml(Path(path).read_bytes())


@dataclass(frozen=True)
class FrameContract:
    """Caller declaration, not an automatically established empirical mapping."""

    name: str
    soil_stem_index: int
    basal_stem_index: int
    soil_raw_id: str
    basal_raw_id: str
    axis_permutation: tuple[int, int, int]
    axis_signs: tuple[int, int, int]
    soil_raw_occurrence: int | None = None
    basal_raw_occurrence: int | None = None

    def __post_init__(self):
        if (not self.name or sorted(self.axis_permutation) != [0, 1, 2]
                or len(self.axis_signs) != 3 or any(sign not in (-1, 1) for sign in self.axis_signs)
                or self.soil_stem_index == self.basal_stem_index
                or min(self.soil_stem_index, self.basal_stem_index) < 0):
            raise ValueError("Invalid explicit frame contract")
        _identifier(self.soil_raw_id)
        _identifier(self.basal_raw_id)


def v2_candidate_contract() -> FrameContract:
    """Explicit opt-in candidate; public documentation does not verify its mapping."""
    return FrameContract("grapevine3d-frame-v2-candidate", 0, 1, "1", "2",
                         (1, 2, 0), (1, -1, 1))


def _stem_anchors(architecture, contract):
    stem = architecture.polylines[architecture.stem_index]
    if len(stem.points_cm) != 2:
        raise ValueError("This declared contract requires a two-point RSML stem")
    try:
        return (stem.points_cm[contract.soil_stem_index],
                stem.points_cm[contract.basal_stem_index])
    except IndexError as error:
        raise ValueError("Declared stem index outside RSML stem") from error


def _raw_anchor(records, record_id, occurrence):
    candidates = [index for index, record in enumerate(records) if record.record_id == record_id]
    if not candidates:
        raise ValueError(f"Missing raw anchor ID {record_id}")
    if occurrence is None:
        if len(candidates) != 1:
            raise ValueError(f"Duplicate raw anchor ID {record_id} needs explicit occurrence")
        occurrence = 0
    if not isinstance(occurrence, int) or occurrence < 0 or occurrence >= len(candidates):
        raise ValueError(f"Invalid raw anchor occurrence for ID {record_id}")
    return candidates[occurrence]


def signed_permutation(point: Point, contract: FrameContract) -> Point:
    if len(point) != 3 or not all(math.isfinite(value) for value in point):
        raise ValueError("Expected a finite 3-D point")
    return tuple(sign * point[axis] for sign, axis in zip(contract.axis_signs, contract.axis_permutation))


def canonical_point(point: Point, soil_anchor: Point,
                    explicit_contract: FrameContract | None = None) -> Point:
    """Invert declared axes, then use raw (z,y,x) as across/along/depth.

    Two arguments are an explicitly v2-only shorthand. Generic callers must
    supply their contract; read_canonical_vine always passes its contract.
    Translation cancels by subtracting the declared RSML soil anchor first.
    """
    if not all(math.isfinite(value) for value in (*point, *soil_anchor)) or len(point) != 3 or len(soil_anchor) != 3:
        raise ValueError("Expected finite 3-D point and explicit soil anchor")
    contract = v2_candidate_contract() if explicit_contract is None else explicit_contract
    if not isinstance(contract, FrameContract):
        raise TypeError("Expected an explicit FrameContract")
    delta = tuple(value - origin for value, origin in zip(point, soil_anchor))
    raw_delta = [0., 0., 0.]
    for index, (axis, sign) in enumerate(zip(contract.axis_permutation, contract.axis_signs)):
        raw_delta[axis] = sign * delta[index]
    return raw_delta[2], raw_delta[1], raw_delta[0]


@dataclass(frozen=True)
class PointMatch:
    polyline_index: int
    point_index: int
    raw_record_indices: tuple[int, ...]
    raw_ids: tuple[str, ...]
    distances_cm: tuple[float, ...]


@dataclass(frozen=True)
class MappingVerification:
    contract: FrameContract
    tolerance_cm: float
    translation_cm: Point
    raw_soil_record_index: int
    raw_basal_record_index: int
    basal_residual_cm: float
    matches: tuple[PointMatch, ...]
    duplicate_raw_ids: dict[str, tuple[int, ...]]
    unmatched_raw_record_indices: tuple[int, ...]
    maximum_nearest_residual_cm: float
    topology_verified: bool = False
    status: str = "fixed_contract_point_set_verified_only"


def verify_mapping(records: tuple[RawRecord, ...], architecture: RsmlArchitecture,
                   contract: FrameContract) -> MappingVerification:
    """Check a supplied mapping at 1e-8 cm; no transform fitting or optimization.

    Translation uses only the declared soil anchors. Every RSML point must match
    at least one transformed raw record. All ties and unused raw records survive
    in the report; point-set inclusion does not establish edges/attachments.
    """
    soil, basal = _stem_anchors(architecture, contract)
    soil_index = _raw_anchor(records, contract.soil_raw_id, contract.soil_raw_occurrence)
    basal_index = _raw_anchor(records, contract.basal_raw_id, contract.basal_raw_occurrence)
    raw_soil = signed_permutation(records[soil_index].coordinates_cm, contract)
    translation = tuple(soil[axis] - raw_soil[axis] for axis in range(3))
    transformed = tuple(tuple(value + shift for value, shift in zip(
        signed_permutation(record.coordinates_cm, contract), translation)) for record in records)
    basal_residual = math.dist(transformed[basal_index], basal)
    if basal_residual > TOLERANCE_CM:
        raise ValueError(f"Declared basal mapping failed at {TOLERANCE_CM} cm")
    matches, used, nearest_residuals = [], set(), []
    for polyline_index, polyline in enumerate(architecture.polylines):
        for point_index, point in enumerate(polyline.points_cm):
            distances = tuple(math.dist(point, candidate) for candidate in transformed)
            candidates = tuple(index for index, distance in enumerate(distances) if distance <= TOLERANCE_CM)
            if not candidates:
                raise ValueError(f"Unmatched exported RSML point {polyline_index}:{point_index}")
            used.update(candidates)
            nearest_residuals.append(min(distances))
            matches.append(
                PointMatch(
                    polyline_index, point_index, candidates,
                    tuple(records[index].record_id for index in candidates),
                    tuple(distances[index] for index in candidates),
                )
            )
    return MappingVerification(contract, TOLERANCE_CM, translation, soil_index,
                               basal_index, basal_residual, tuple(matches), duplicate_ids(records),
                               tuple(index for index in range(len(records)) if index not in used),
                               max(nearest_residuals))


@dataclass(frozen=True)
class CanonicalVine(Vine):
    frame_contract: FrameContract
    mapping_status: str = "declared_contract_only_raw_mapping_not_checked"


def read_canonical_vine(rsml_path: str | Path, explicit_contract: FrameContract) -> CanonicalVine:
    """Read consecutive nonstem segments in the declared canonical frame.

    This function does not read raw data and therefore does not verify the
    raw-to-RSML mapping. Call verify_mapping separately on explicitly supplied
    paired inputs; neither function infers attachment edges between polylines.
    Returned vines reuse the unchanged grid_vine/clip/split helpers.
    """
    if not isinstance(explicit_contract, FrameContract):
        raise TypeError("An explicit FrameContract is required")
    path = Path(rsml_path)
    architecture = read_rsml(path)
    soil, _ = _stem_anchors(architecture, explicit_contract)
    segments = []
    for index, polyline in enumerate(architecture.polylines):
        if index == architecture.stem_index:
            continue
        canonical = tuple(canonical_point(point, soil, explicit_contract) for point in polyline.points_cm)
        segments.extend(Segment(first, second, polyline.label)
                        for first, second in zip(canonical, canonical[1:]))
    if not segments:
        raise ValueError("No consecutive nonstem RSML segments")
    return CanonicalVine(path.parent.name, path.stem, architecture.plant_label, path,
                         soil, tuple(segments), explicit_contract)
