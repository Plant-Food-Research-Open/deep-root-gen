"""Invented geometry only; no model simulation or measured/rootstock data."""

import json

import numpy as np
import pytest

from deeprootgen.research.curvature_diagnostics import (
    clean_polyline,
    compare_curvature,
    summarize_curvature,
    tangent_correlation,
    tortuosity,
    turning_angles,
)


def line(length=30):
    return np.array([[0.0, 0.0, 0.0], [length, 0.0, 0.0]])


def circle(radius=20.0, stop=np.pi, count=10001):
    theta = np.linspace(0.0, stop, count)
    return np.column_stack(
        [radius * np.cos(theta), radius * np.sin(theta), np.zeros(count)]
    )


def root(points, organ_id="one", order=2):
    return dict(points=points, organ_id=organ_id, order=order)


def pool(summary, scale="5", phase="0", order="2"):
    return summary["by_order"][order]["pooled"][scale][phase]


@pytest.mark.parametrize("phase,count", [(0.0, 5), (0.5, 4)])
def test_straight_physical_support_and_runs(phase, count):
    turns = turning_angles(line(), 5.0, phase)
    assert turns["eligible_count"] == count
    np.testing.assert_array_equal(turns["angles_deg"], np.zeros(count))
    assert turns["near_zero_runs_cm"] == [count * 5.0]
    assert turns["centres_cm"][0] == 5.0 + 5.0 * phase
    assert tortuosity(line())["value"] == 1.0
    assert all(r["correlation"] == 1.0 for r in tangent_correlation(line(), [2, 5, 10]))


def test_tail_is_never_appended_or_extrapolated():
    turns = turning_angles(line(12.0), 5.0)
    assert turns["centres_cm"] == [5.0]
    assert turning_angles(line(9.99), 5.0)["status"] == "insufficient_support"
    assert turning_angles(line(10.0), 5.0, 0.5)["eligible_count"] == 0
    assert tangent_correlation(line(5.99), [5.0])[0]["correlation"] is None
    assert tangent_correlation(line(6.0), [5.0])[0]["eligible_count"] == 1


def test_circle_angle_and_physical_tangent_correlation():
    radius = 20.0
    xyz = circle(radius)
    for h in (2.0, 5.0, 10.0):
        turns = turning_angles(xyz, h)
        np.testing.assert_allclose(
            turns["angles_deg"], np.degrees(h / radius), atol=2e-5
        )
    correlations = tangent_correlation(xyz, [2.0, 5.0, 10.0], station_step_cm=0.5)
    np.testing.assert_allclose(
        [r["correlation"] for r in correlations],
        np.cos(np.array([2.0, 5.0, 10.0]) / radius),
        atol=1e-7,
    )
    assert tortuosity(xyz)["value"] == pytest.approx(np.pi / 2, rel=1e-7)


def test_zigzag_turns_retain_unsmoothed_angles():
    zigzag = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [2.0, 1.0, 0.0],
            [2.0, 2.0, 0.0],
        ]
    )
    np.testing.assert_allclose(
        turning_angles(zigzag, 1.0)["angles_deg"], [90.0, 90.0, 90.0]
    )
    assert turning_angles(zigzag, 1.0)["near_zero_runs_cm"] == []
    assert tangent_correlation(zigzag, [1.0, 2.0])[0]["correlation"] == pytest.approx(
        0.0
    )
    assert tangent_correlation(zigzag, [1.0, 2.0])[1]["correlation"] == pytest.approx(
        1.0
    )


def subdivide(points, fractions=(0.13, 0.41, 0.87)):
    result = []
    for start, end in zip(points[:-1], points[1:]):
        result.append(start)
        result.extend(start + (end - start) * fraction for fraction in fractions)
    return np.array(result + [points[-1]])


def test_irregular_sampling_and_collinear_subdivision_invariant():
    xyz = np.array(
        [
            [0.0, 0.0, 0.0],
            [7.0, 0.0, 0.0],
            [7.0, 9.0, 0.0],
            [12.0, 9.0, 0.0],
            [12.0, 9.0, 12.0],
        ]
    )
    irregular = subdivide(xyz)
    for phase in (0.0, 0.5):
        for h in (2.0, 5.0, 10.0):
            a, b = turning_angles(xyz, h, phase), turning_angles(irregular, h, phase)
            np.testing.assert_allclose(a["angles_deg"], b["angles_deg"], atol=1e-12)
            assert a["centres_cm"] == b["centres_cm"]
    assert tortuosity(xyz)["value"] == pytest.approx(tortuosity(irregular)["value"])
    for a, b in zip(
        tangent_correlation(xyz, [2.0, 5.0, 10.0]),
        tangent_correlation(irregular, [2.0, 5.0, 10.0]),
    ):
        assert a["correlation"] == pytest.approx(b["correlation"])


def test_rigid_transform_invariant():
    xyz = circle()
    rotation, _ = np.linalg.qr(np.random.default_rng(12).normal(size=(3, 3)))
    transformed = xyz @ rotation + np.array([7.0, -14.0, 33.0])
    for phase in (0.0, 0.5):
        np.testing.assert_allclose(
            turning_angles(xyz, 5.0, phase)["angles_deg"],
            turning_angles(transformed, 5.0, phase)["angles_deg"],
            atol=1e-10,
        )
    for a, b in zip(
        tangent_correlation(xyz, [2.0, 5.0]),
        tangent_correlation(transformed, [2.0, 5.0]),
    ):
        assert a["correlation"] == pytest.approx(b["correlation"], abs=1e-12)
    assert tortuosity(transformed)["value"] == pytest.approx(tortuosity(xyz)["value"])


def test_duplicates_are_removed_but_closed_path_is_preserved():
    xyz = np.array(
        [
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
        ]
    )
    assert len(clean_polyline(xyz)) == 3
    assert turning_angles(xyz, 1.0)["angles_deg"] == [180.0]
    result = tortuosity(xyz)
    assert result["status"] == "zero_chord"
    assert result["value"] is None
    assert result["arc_length_cm"] == 2.0
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(
    "xyz", [[], [[1.0, 2.0, 3.0]], [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]]]
)
def test_empty_singleton_and_zero_length_have_explicit_status(xyz):
    assert turning_angles(xyz, 1.0)["status"] == "insufficient_support"
    assert tortuosity(xyz)["status"] == "zero_length"
    assert tortuosity(xyz)["value"] is None
    assert tangent_correlation(xyz, [1.0])[0]["correlation"] is None


def test_zero_chord_excluded_and_breaks_zero_turn_run():
    # h=1 chord doubles back on itself during the middle interval.
    xyz = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [2.5, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [3.0, 0.0, 0.0],
            [4.0, 0.0, 0.0],
        ]
    )
    turns = turning_angles(xyz, 1.0)
    assert turns["supported_count"] == 4
    assert turns["excluded_zero_chord_count"] == 2
    assert turns["angles_deg"] == [0.0, 0.0]
    assert turns["near_zero_runs_cm"] == [1.0, 1.0]
    assert tangent_correlation(xyz, [1.0])[0]["excluded_zero_chord_count"] == 2


def test_all_zero_chords_have_explicit_undefined_status():
    xyz = [
        [0.0, 0.0, 0.0],
        [0.5, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        [0.5, 0.0, 0.0],
        [0.0, 0.0, 0.0],
    ]
    turns = turning_angles(xyz, 1.0)
    assert turns["status"] == "zero_length_chords"
    assert turns["eligible_count"] == 0
    assert turns["excluded_zero_chord_count"] == 1
    correlation = tangent_correlation(xyz, [1.0])[0]
    assert correlation["status"] == "zero_length_chords"
    assert correlation["correlation"] is None


@pytest.mark.parametrize(
    "xyz", [[[1.0, 2.0]], [[1.0, np.nan, 2.0]], [[np.inf, 0.0, 0.0]], [1.0, 2.0, 3.0]]
)
def test_bad_coordinates_rejected(xyz):
    with pytest.raises(ValueError):
        clean_polyline(xyz)


@pytest.mark.parametrize(
    "h,phase",
    [(0.0, 0.0), (-1.0, 0.0), (np.inf, 0.0), (2.0, 1.0), (2.0, -0.1), (2.0, np.nan)],
)
def test_bad_angle_controls_rejected(h, phase):
    with pytest.raises(ValueError):
        turning_angles(line(), h, phase)


def test_equal_organ_weights_eligibility_and_wasserstein():
    # Nine straight angles versus one 90-degree angle. Each root receives 1/2.
    observed = summarize_curvature(
        [
            root(line(10.0), "long"),
            root([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]], "short"),
            root(line(0.9), "ineligible"),
        ],
        scales_cm=(1,),
        phases=(0,),
    )
    pooled = pool(observed, "1")
    assert pooled["eligible_organ_count"] == 2
    assert pooled["ineligible_organ_count"] == 1
    np.testing.assert_allclose(pooled["angle_weights"][:9], np.full(9, 1 / 18))
    assert pooled["angle_weights"][-1] == 0.5
    assert pooled["fraction_gt45_deg"] == pytest.approx(0.5)
    assert pooled["fraction_lt1_deg"] == pytest.approx(0.5)
    assert pooled["p90_deg"] == 90.0
    generated = summarize_curvature([root(line(50.0))], scales_cm=(1,), phases=(0,))
    comparison = compare_curvature(observed, generated)["by_order"]["2"]["1"]["0"]
    assert comparison["wasserstein_deg"] == pytest.approx(45.0)
    assert comparison["observed_eligible_organ_count"] == 2
    assert comparison["generated_eligible_organ_count"] == 1
    json.dumps(observed, allow_nan=False)
    assert (
        compare_curvature(observed, observed)["by_order"]["2"]["1"]["0"][
            "wasserstein_deg"
        ]
        == 0.0
    )


def test_location_pooled_diagnostics_distinguish_unequal_root_lengths():
    summary = summarize_curvature(
        [
            root(line(10.0), "nine_straight_turns"),
            root(
                [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]], "one_right_angle"
            ),
        ],
        scales_cm=(1,),
        phases=(0,),
    )
    pooled = pool(summary, "1")
    locations = pooled["location_pooled_statistics"]
    assert pooled["quantile_method"] == "weighted_left_inverse_empirical_cdf"
    assert locations["quantile_method"] == "numpy_linear"
    assert locations["angle_weighting"] == "equal eligible location"
    assert locations["median_deg"] == 0.0
    assert locations["p90_deg"] == pytest.approx(9.0)
    assert pooled["p90_deg"] == 90.0
    assert locations["fraction_gt45_deg"] == pytest.approx(0.1)
    assert pooled["fraction_gt45_deg"] == pytest.approx(0.5)
    assert locations["fraction_lt1_deg"] == pytest.approx(0.9)
    assert pooled["fraction_lt1_deg"] == pytest.approx(0.5)
    empty = pool(
        summarize_curvature([root(line(0.9))], scales_cm=(1,), phases=(0,)), "1"
    )
    assert all(
        empty["location_pooled_statistics"][key] is None
        for key in ("median_deg", "p90_deg", "fraction_gt45_deg", "fraction_lt1_deg")
    )


def test_no_branch_angle_is_introduced_between_independent_roots():
    roots = [
        root([[0.0, 0.0, 0.0], [30.0, 0.0, 0.0]], "parent", 1),
        root([[10.0, 0.0, 0.0], [10.0, 30.0, 0.0]], "child", 2),
    ]
    summary = summarize_curvature(roots)
    assert pool(summary, order="1")["fraction_lt1_deg"] == 1.0
    assert pool(summary, order="2")["fraction_lt1_deg"] == 1.0


def test_missing_orders_and_unsupported_scales_are_not_zero_distance():
    observed = summarize_curvature([root(line(3.0))])
    generated = summarize_curvature([root(line(30.0), order=1)])
    for order in ("1", "2"):
        result = compare_curvature(observed, generated)["by_order"][order]["5"]["0"]
        assert result["wasserstein_deg"] is None
        assert result["status"] == "insufficient_support"
    assert pool(observed)["median_deg"] is None


def test_summary_rejects_ambiguous_inputs():
    with pytest.raises(ValueError, match="unique"):
        summarize_curvature([root(line()), root(line())])
    with pytest.raises(ValueError, match="order"):
        summarize_curvature([root(line(), order=1.5)])
    with pytest.raises(ValueError, match="phases"):
        summarize_curvature([], phases=(1.0,))
    with pytest.raises(ValueError, match="unique"):
        summarize_curvature([], scales_cm=(2.0, 2.0))
    with pytest.raises(ValueError, match="formatted"):
        summarize_curvature([], scales_cm=(2.0, 2.0000001))
    with pytest.raises(ValueError, match="formatted"):
        summarize_curvature([], phases=(0.5, 0.50000001))
    with pytest.raises(ValueError, match="match"):
        compare_curvature(
            summarize_curvature([]), summarize_curvature([], scales_cm=(1,))
        )
