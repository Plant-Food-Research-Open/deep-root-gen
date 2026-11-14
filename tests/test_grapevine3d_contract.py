"""Invented geometry only: explicit coordinate contracts, never observed vines."""

from dataclasses import replace
import math
from pathlib import Path
from xml.etree import ElementTree

import pytest

from scripts.data.grapevine3d_contract import (
    canonical_point, duplicate_ids, parse_raw_records, parse_rsml,
    read_canonical_vine, read_raw_records, signed_permutation,
    v2_candidate_contract, verify_mapping,
)
from scripts.data.grapevine3d_grid import (
    Segment, clip_to_soil, grid_vine, split_segment_into_cells,
)

RAW_POINTS = (
    ("0", "none", (8., -4., 1.)),
    ("1", "Node 0 Internode", (12., -3., 2.)),
    ("2", "1 Internode", (32., -2., 4.)),
    ("2.1.1", "2 Internode", (37., 3., -1.)),
    ("2.1.3", "2.1.1 Internode", (42., -1., 6.)),
    ("2.1.3", "2.1.1 Internode", (39., 7., 8.)),
    ("2.1.3.1.1", "Node 2.1.3 Internode", (44., 8., 10.)),
    ("2.1.1.1", "2.1.1 Internode", (37., 3., -1.)),
)


def raw_text(points=RAW_POINTS):
    modules = []
    for raw_id, parent, point in points:
        coordinates = ";".join(str(value) for value in (1., *point, 10., 20., 30.))
        modules.append(f"//Node\nID: {raw_id}\nParent: {parent}\n{coordinates}\n//EndModule")
    return "Invented-belowground-header\n" + "\n".join(modules)


def rsml_text(translation=(104., 204., 291.), *, namespace=False):
    # Explicitly construct the declared permutation; do not use tool under test.
    def transformed(index):
        x, y, z = RAW_POINTS[index][2]
        return (y + translation[0], -z + translation[1], x + translation[2])

    def geometry(root, indices):
        polyline = ElementTree.SubElement(ElementTree.SubElement(root, "geometry"), "polyline")
        for index in indices:
            point = transformed(index)
            ElementTree.SubElement(polyline, "point", dict(zip("xyz", map(str, point))))

    document = ElementTree.Element("rsml", {"xmlns": "urn:rsml:test"} if namespace else {})
    ElementTree.SubElement(ElementTree.SubElement(document, "metadata"), "unit").text = "cm"
    plant = ElementTree.SubElement(ElementTree.SubElement(document, "scene"), "plant", label="invented")
    stem = ElementTree.SubElement(plant, "root", label="stem", id="stem-id")
    geometry(stem, [1, 2])
    primary = ElementTree.SubElement(stem, "root", label="primary", id="primary-id")
    geometry(primary, [2, 3, 4])
    secondary = ElementTree.SubElement(primary, "root", label="secondary", id="secondary-id")
    geometry(secondary, [3, 5, 6])
    return ElementTree.tostring(document, encoding="unicode")


def test_raw_parser_keeps_hierarchical_ids_parent_annotations_and_duplicates(tmp_path):
    path = tmp_path / "invented.txt"
    path.write_text(raw_text())
    records = read_raw_records(path)
    assert len(records) == len(RAW_POINTS)
    assert records[6].record_id == "2.1.3.1.1"
    assert records[6].parent_id == "2.1.3"
    assert records[6].parent_annotation == "Node 2.1.3 Internode"
    assert records[1].parent_id == "0"
    assert records[0].parent_id is None
    assert records[0].coordinates_cm == RAW_POINTS[0][2]
    assert records[0].constant == 1 and records[0].angles == (10, 20, 30)
    assert duplicate_ids(records) == {"2.1.3": (4, 5)}
    assert records[4].coordinates_cm != records[5].coordinates_cm
    assert records[4].source_line < records[5].source_line


def test_multiple_coordinate_rows_never_overwrite_a_module_id():
    text = raw_text(RAW_POINTS[:1]).replace("//EndModule", "1;1;2;3;0;0;0\n//EndModule")
    records = parse_raw_records(text)
    assert len(records) == 2 and duplicate_ids(records) == {"0": (0, 1)}


def test_fixed_mapping_all_points_ties_duplicates_and_unused_graft():
    records = parse_raw_records(raw_text())
    architecture = parse_rsml(rsml_text(namespace=True))
    report = verify_mapping(records, architecture, v2_candidate_contract())
    assert report.translation_cm == (104, 204, 291)
    assert report.tolerance_cm == 1e-8 and report.basal_residual_cm == 0
    assert report.maximum_nearest_residual_cm == 0
    assert len(report.matches) == 8
    assert report.duplicate_raw_ids == {"2.1.3": (4, 5)}
    assert report.unmatched_raw_record_indices == (0,)
    assert any(match.raw_record_indices == (3, 7) for match in report.matches)
    assert report.topology_verified is False
    assert report.status == "fixed_contract_point_set_verified_only"


@pytest.mark.parametrize("updates", [
    {"soil_stem_index": 1, "basal_stem_index": 0},
    {"axis_signs": (1, 1, 1)},
    {"axis_permutation": (2, 1, 0)},
])
def test_deliberately_wrong_contract_rejected(updates):
    contract = replace(v2_candidate_contract(), **updates)
    with pytest.raises(ValueError):
        verify_mapping(parse_raw_records(raw_text()), parse_rsml(rsml_text()), contract)


def test_translation_is_soil_only_and_basal_is_an_independent_check():
    document = ElementTree.fromstring(rsml_text())
    basal = document.findall("./scene/plant/root/geometry/polyline/point")[1]
    basal.set("z", str(float(basal.get("z")) + .1))
    with pytest.raises(ValueError, match="basal mapping"):
        verify_mapping(parse_raw_records(raw_text()), parse_rsml(ElementTree.tostring(document)),
                       v2_candidate_contract())


def test_every_exported_point_checked_at_fixed_euclidean_tolerance():
    document = ElementTree.fromstring(rsml_text())
    point = document.findall(".//point")[-1]
    point.set("x", str(float(point.get("x")) + 2e-8))
    with pytest.raises(ValueError, match="Unmatched exported RSML point"):
        verify_mapping(parse_raw_records(raw_text()), parse_rsml(ElementTree.tostring(document)),
                       v2_candidate_contract())
    point.set("x", str(float(point.get("x")) - 2e-8 + 1e-9))
    assert verify_mapping(parse_raw_records(raw_text()), parse_rsml(ElementTree.tostring(document)),
                          v2_candidate_contract()).maximum_nearest_residual_cm < 1e-8


def test_duplicate_anchor_requires_explicit_occurrence_and_is_reported():
    points = (*RAW_POINTS, ("1", "0 Internode", (99., 98., 97.)))
    records = parse_raw_records(raw_text(points))
    architecture = parse_rsml(rsml_text())
    with pytest.raises(ValueError, match="Duplicate raw anchor"):
        verify_mapping(records, architecture, v2_candidate_contract())
    report = verify_mapping(records, architecture, replace(v2_candidate_contract(), soil_raw_occurrence=0))
    assert report.duplicate_raw_ids["1"] == (1, 8)
    assert 8 in report.unmatched_raw_record_indices
    with pytest.raises(ValueError):
        verify_mapping(records, architecture, replace(v2_candidate_contract(), soil_raw_occurrence=1))


@pytest.mark.parametrize("units", ["mm", "m", "", "CM"])
def test_cm_validation(units):
    with pytest.raises(ValueError, match="cm units"):
        parse_raw_records(raw_text(), units=units)
    document = ElementTree.fromstring(rsml_text())
    document.find("./metadata/unit").text = units
    with pytest.raises(ValueError, match="cm units"):
        parse_rsml(ElementTree.tostring(document))


def test_canonical_frame_translation_length_labels_and_no_added_attachments(tmp_path):
    vines = []
    for index, translation in enumerate([(104., 204., 291.), (-20., 1000., 800.)]):
        path = tmp_path / "invented-T2" / f"toy-{index}.rsml"
        path.parent.mkdir(exist_ok=True)
        path.write_text(rsml_text(translation))
        vines.append(read_canonical_vine(path, v2_candidate_contract()))
    assert vines[0].segments == vines[1].segments
    assert len(vines[0].segments) == 4  # two per nonstem chain, no stem/junction connectors
    assert [segment.root_class for segment in vines[0].segments] == ["primary", "primary", "secondary", "secondary"]
    assert vines[0].segments[0].start == (2, 1, 20)
    assert vines[0].segments[0].end == (-3, 6, 25)
    for segment in vines[0].segments:
        assert math.dist(segment.start, segment.end) > 0
    raw_distance = math.dist(RAW_POINTS[2][2], RAW_POINTS[3][2])
    assert math.dist(vines[0].segments[0].start, vines[0].segments[0].end) == pytest.approx(raw_distance)
    assert vines[0].mapping_status == "declared_contract_only_raw_mapping_not_checked"
    assert canonical_point((101, 202, 303), (101, 202, 303)) == (0, 0, 0)
    grid, receipt = grid_vine(vines[0], 10.)
    assert grid and receipt["grid_length_cm"] == pytest.approx(receipt["soil_length_cm"])
    with pytest.raises(TypeError, match="explicit FrameContract"):
        read_canonical_vine(vines[0].source, None)


def test_soil_crossing_and_exact_face_ties_use_unchanged_splitter(tmp_path):
    # Invented RSML coordinates already in the declared soil-reference frame.
    path = tmp_path / "toy.rsml"
    path.write_text('''<rsml><metadata><unit>cm</unit></metadata><scene><plant label="toy">
      <root label="stem"><geometry><polyline><point x="0" y="0" z="0"/><point x="0" y="0" z="20"/></polyline></geometry>
        <root label="unusual-label"><geometry><polyline><point x="10" y="-10" z="-5"/><point x="10" y="-10" z="15"/></polyline></geometry></root>
      </root></plant></scene></rsml>''')
    vine = read_canonical_vine(path, v2_candidate_contract())
    segment = vine.segments[0]
    assert segment.root_class == "unusual-label"
    kept, excluded = clip_to_soil(segment)
    assert excluded == pytest.approx(5)
    assert kept.start == (10, 10, 0)
    pieces = split_segment_into_cells(kept, 10)
    assert [cell for cell, _ in pieces] == [(1, 1, 0), (1, 1, 1)]
    assert [length for _, length in pieces] == pytest.approx([10., 5.])
    cells, summary = grid_vine(vine, 10)
    assert set(cells) == {(1, 1, 0), (1, 1, 1)}
    assert summary["original_length_cm"] == pytest.approx(20)
    assert summary["above_surface_length_cm"] == pytest.approx(5)
    assert summary["soil_length_cm"] == pytest.approx(15)
    assert summary["grid_length_cm"] == pytest.approx(15)


@pytest.mark.parametrize("text", [
    "header only", "//Node\nID: 2.1.3", "//EndModule",
    "//Node\nID: 1\nParent: 0\n1;1;2;3;4;5\n//EndModule",
    "//Node\nID: 1\nParent: 0\n1;nan;2;3;4;5;6\n//EndModule",
    "//Node\nID: 1\nID: 2\nParent: 0\n1;1;2;3;4;5;6\n//EndModule",
])
def test_malformed_raw_never_silently_discards_modules(text):
    with pytest.raises(ValueError):
        parse_raw_records(text)


def test_point_and_contract_validation():
    with pytest.raises(ValueError):
        canonical_point((1, 2, math.nan), (0, 0, 0))
    with pytest.raises(ValueError):
        signed_permutation((1, 2, math.inf), v2_candidate_contract())
    with pytest.raises(ValueError):
        replace(v2_candidate_contract(), axis_permutation=(0, 0, 2))


def test_leading_zero_id_components_are_not_coerced():
    records = parse_raw_records(raw_text((("02.01.003", "Node 02.01 Internode", (1., 2., 3.)),)))
    assert records[0].record_id == "02.01.003"
    assert records[0].parent_id == "02.01"


def test_euclidean_tolerance_is_not_a_per_axis_box():
    document = ElementTree.fromstring(rsml_text())
    point = document.findall(".//point")[-1]
    for axis in "xyz":
        point.set(axis, str(float(point.get(axis)) + 8e-9))
    with pytest.raises(ValueError, match="Unmatched exported"):
        verify_mapping(parse_raw_records(raw_text()), parse_rsml(ElementTree.tostring(document)),
                       v2_candidate_contract())


def test_negative_face_tie_uses_floor_without_coordinate_shift():
    pieces = split_segment_into_cells(Segment((-10., -10., 0.), (-10., -10., 10.), "primary"), 10.)
    assert pieces == [((-1, -1, 0), 10.)]


def test_missing_soil_anchor_and_invalid_explicit_occurrence_rejected():
    records = parse_raw_records(raw_text(RAW_POINTS[2:]))
    with pytest.raises(ValueError, match="Missing raw anchor ID 1"):
        verify_mapping(records, parse_rsml(rsml_text()), v2_candidate_contract())
    with pytest.raises(ValueError, match="Invalid raw anchor occurrence"):
        verify_mapping(parse_raw_records(raw_text()), parse_rsml(rsml_text()),
                       replace(v2_candidate_contract(), soil_raw_occurrence=-1))


def test_two_declared_export_permutations_produce_same_verified_canonical_vine(tmp_path):
    """The canonical frame depends on raw axes, not the export permutation."""
    first_path = tmp_path / "first-export.rsml"
    first_path.write_text(rsml_text())
    second_document = ElementTree.fromstring(rsml_text())
    for point in second_document.findall(".//point"):
        # Undo this fixture's known first export using literal independent math.
        raw_x = float(point.get("z")) - 291.
        raw_y = float(point.get("x")) - 104.
        raw_z = 204. - float(point.get("y"))
        # Another signed permutation, with a separate arbitrary translation.
        point.set("x", str(-raw_z + 500.))
        point.set("y", str(raw_x - 100.))
        point.set("z", str(-raw_y + 80.))
    second_path = tmp_path / "second-export.rsml"
    second_path.write_text(ElementTree.tostring(second_document, encoding="unicode"))
    first_contract = v2_candidate_contract()
    second_contract = replace(first_contract, name="invented-alternate-export",
                              axis_permutation=(2, 0, 1), axis_signs=(-1, 1, -1))
    raw_records = parse_raw_records(raw_text())
    first_report = verify_mapping(raw_records, parse_rsml(first_path.read_text()), first_contract)
    second_report = verify_mapping(raw_records, parse_rsml(second_path.read_text()), second_contract)
    assert first_report.maximum_nearest_residual_cm == 0
    assert second_report.maximum_nearest_residual_cm == 0
    assert second_report.translation_cm == (500, -100, 80)
    first = read_canonical_vine(first_path, first_contract)
    second = read_canonical_vine(second_path, second_contract)
    assert first.segments == second.segments
    assert second.segments[0].start == (2, 1, 20)
    assert second.segments[0].end == (-3, 6, 25)
    # The v2 shorthand remains explicit and equivalent only to the v2 contract.
    assert canonical_point((107., 205., 328.), (101., 202., 303.)) == canonical_point(
        (107., 205., 328.), (101., 202., 303.), first_contract)
