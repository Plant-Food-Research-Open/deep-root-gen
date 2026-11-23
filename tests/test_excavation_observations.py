"""Invented excavation windows and a raw/RSML discrepancy."""

import pytest

from deeprootgen.research.excavation import (
    ExcavationObservation,
    length_in_excavation,
    recovery_daughter_probabilities,
)
from scripts.data.mature_vine_archive import inspect_archive_pair


def test_censoring_retains_measurement_quantity_and_true_zero():
    assert ExcavationObservation("daughter_count", "observed", 0).bounds == (0, 0)
    assert ExcavationObservation("daughter_count", "missing").bounds == (None, None)
    assert ExcavationObservation("whole_axis_length", "lower_bound", 17).bounds == (17, None)
    assert ExcavationObservation("segment_to_branch_length", "observed", 17).quantity == "segment_to_branch_length"
    assert ExcavationObservation("taper_rate", "observed", .0066).unit == "1/cm"
    with pytest.raises(ValueError, match="no numeric value"):
        ExcavationObservation("daughter_count", "missing", 0)
    with pytest.raises(ValueError, match="own measurement"):
        ExcavationObservation("segment_to_branch_length", "lower_bound", 17)
    with pytest.raises(ValueError, match="must be integers"):
        ExcavationObservation("crown_axis_count", "observed", 1.5)


def test_excavation_clips_at_boundaries_and_ignores_vertices_outside_support():
    lower, upper = [0., 0., 0.], [2., 2., 2.]
    complete = length_in_excavation([[.5, 1., 1.], [1.5, 1., 1.]], lower, upper, complete_recovery=True)
    assert complete.bounds == (1., 1.)
    crossing = length_in_excavation([[-1., 1., 1.], [3., 1., 1.], [1., 1., 1.]],
                                    lower, upper, complete_recovery=True)
    assert crossing.bounds == (3., None)
    # Even uncut recorded coordinates can be broken before recording.
    broken = length_in_excavation([[.5, 1., 1.], [1.5, 1., 1.]], lower, upper, complete_recovery=False)
    assert broken.bounds == (1., None)
    missed = length_in_excavation([[.5, 3., 1.], [1.5, 3., 1.]], lower, upper, complete_recovery=True)
    assert missed.status == "missing" and missed.value is None


@pytest.mark.parametrize("factor", [1, 2, 3])
def test_recovery_scales_only_the_conditional_daughter_count(factor):
    reference = [.25, .75]
    expanded = recovery_daughter_probabilities(reference, factor)
    assert expanded[factor - 1::factor] == reference
    assert sum((index + 1) * p for index, p in enumerate(expanded)) == pytest.approx(factor * 1.75)
    assert reference == [.25, .75]


def test_raw_axis_omission_and_conflicting_duplicate_remain_visible(tmp_path):
    raw, rsml = tmp_path / "vine.txt", tmp_path / "vine.rsml"
    modules = [
        ("1", "none", (0, 0, 0)), ("2", "1", (1, 0, 0)),
        ("2.1.1", "2", (2, 0, 0)), ("2.1.2", "2.1.1", (3, 0, 0)),
        ("2.1.2", "2.1.1", (4, 0, 0)), ("2.1.2.1.1", "2.1.2", (3, 1, 0)),
    ]
    raw.write_text("\n".join(
        f"//Node\nID: {id_}\nParent: {parent}\n1;{x};{y};{z};0;0;0\n//EndModule"
        for id_, parent, (x, y, z) in modules
    ))
    stem = "".join(f'<point x="0" y="0" z="{z}"/>' for z in (0, 1))
    primary = "".join(f'<point x="0" y="0" z="{z}"/>' for z in (2, 3, 4))
    rsml.write_text(f"""<rsml><metadata><unit>cm</unit></metadata><scene><plant>
      <root id="0" label="stem"><geometry><polyline>{stem}</polyline></geometry>
      <root id="1" label="primary"><geometry><polyline>{primary}</polyline></geometry></root>
      </root></plant></scene></rsml>""")
    with pytest.raises(ValueError, match=r"Duplicate raw point IDs: 2\.1\.2"):
        inspect_archive_pair(raw, rsml)
    for policy in ("first", "last"):
        audit = inspect_archive_pair(raw, rsml, duplicate_policy=policy)
        assert audit["raw_counts"] == {1: 1, 2: 1}
        assert audit["rsml_counts"] == {1: 1}
        assert not audit["inventories_agree"] and not audit["included_in_geometric_summary"]
        assert not audit["unmatched_rsml"]
        assert audit["matches"][0]["matches_both_duplicate_occurrences"]
        assert audit["raw_only"][0]["raw_axis"] == "2.1.2.1"
