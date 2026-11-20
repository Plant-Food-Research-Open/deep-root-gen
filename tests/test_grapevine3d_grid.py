"""Small analytic checks for the standalone Grapevine3D observation grid."""

import math
from pathlib import Path

import pytest

from scripts.data.grapevine3d_grid import Segment, Vine, clip_to_soil, grid_vine, read_vine, split_segment_into_cells


def test_segment_is_split_at_faces_and_length_is_conserved() -> None:
    segment = Segment((-5.0, 5.0, 5.0), (15.0, 5.0, 5.0), "primary")
    pieces = split_segment_into_cells(segment, 10.0)
    assert [cell for cell, _ in pieces] == [(-1, 0, 0), (0, 0, 0), (1, 0, 0)]
    assert [length for _, length in pieces] == pytest.approx([5.0, 10.0, 5.0])


def test_diagonal_and_soil_clip_conserve_length() -> None:
    segment = Segment((-5.0, -5.0, -5.0), (15.0, 15.0, 15.0), "secondary")
    kept, excluded = clip_to_soil(segment)
    assert kept is not None
    assert kept.start == pytest.approx((0.0, 0.0, 0.0))
    assert excluded == pytest.approx(5 * math.sqrt(3))
    vine = Vine("T1", "test", "SO4", Path("test.rsml"), (0, 0, 0), (segment,))
    cells, summary = grid_vine(vine, 10.0)
    assert set(cells) == {(0, 0, 0), (1, 1, 1)}
    assert summary["soil_length_cm"] == pytest.approx(15 * math.sqrt(3))
    assert summary["grid_length_cm"] == pytest.approx(summary["soil_length_cm"])


def test_nested_rsml_roots_exclude_stem_and_use_surface_origin(tmp_path: Path) -> None:
    path = tmp_path / "T1" / "B-01.rsml"
    path.parent.mkdir()
    path.write_text("""<rsml><metadata><unit>cm</unit></metadata><scene><plant label="101-14">
      <root label="stem"><geometry><polyline><point x="0" y="0" z="0"/><point x="2" y="3" z="20"/></polyline></geometry>
        <root label="primary"><geometry><polyline><point x="2" y="3" z="20"/><point x="12" y="3" z="20"/></polyline></geometry>
          <root label="secondary"><geometry><polyline><point x="32" y="3" z="20"/><point x="32" y="3" z="30"/></polyline></geometry></root>
        </root>
      </root></plant></scene></rsml>""")
    vine = read_vine(path)
    assert len(vine.segments) == 2
    assert vine.surface_rsml_cm == (2, 3, 20)
    cells, summary = grid_vine(vine, 10)
    assert summary["soil_length_cm"] == pytest.approx(20)
    assert sum(sum(classes.values()) for classes in cells.values()) == pytest.approx(20)
