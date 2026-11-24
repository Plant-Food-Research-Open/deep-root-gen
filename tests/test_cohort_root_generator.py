"""Invented cohort fixtures only; no field data."""

import copy

import numpy as np
import pandas as pd
import pytest

from deeprootgen.research.cohort_root_generator import (
    CohortRootGenerator,
    bounded_draw,
    equivalent_diameter,
    integrate_curve,
    material_cuts,
    taper_diameter,
)


def config():
    def fixed(x):
        return dict(mean=x, sd=0, min=x, max=x)

    return dict(
        step_cm=3.0,
        dry_density_g_cm3=0.3,
        fine_cutoff_mm=2.5,
        max_organs=100,
        crown_mass_g=0.0,
        crown_depth_cm=[5.0, 8.0],
        crown_radius_cm=1.0,
        later_maturity=[0.3, 0.6],
        maturity_length_power=0.5,
        maturity_diameter_power=0.5,
        child_diameter_fraction_max=0.8,
        inclination_mean_deg=30.0,
        inclination_sd_deg=10.0,
        inclination_bounds_deg=[0.0, 90.0],
        insertion_mean_deg=40.0,
        insertion_sd_deg=5.0,
        orders={
            str(o): dict(
                length_cm=fixed(10.0),
                base_diameter_cm=fixed(0.8 / o),
                tip_diameter_cm=fixed(0.05),
                first_branch_cm=fixed(4.0),
                branch_probability=1.0,
                daughter_probabilities=[1.0],
                curvature_sd_rad_cm=0.005,
                correlation_cm=10.0,
                downward_drift_per_cm=0.0,
            )
            for o in range(1, 6)
        },
    )


def test_material_integral_and_cutoff_are_subdivision_invariant():
    vols = []
    fines = []
    for stations in ([0.0, 10.0], [0.0, 1.0, 3.0, 10.0]):
        cuts = material_cuts(10.0, stations, [2.0, 4.0, 8.0], 0.8, 0.1, 0.25)
        d = taper_diameter(cuts, 10.0, 0.8, 0.1)
        e = equivalent_diameter(d[:-1], d[1:])
        vols.append(np.pi / 4 * np.dot(np.diff(cuts), e**2))
        fines.append(np.diff(cuts)[e <= 0.25].sum())
    np.testing.assert_allclose(
        vols, np.pi * 10 * (0.8**2 + 0.8 * 0.1 + 0.1**2) / 12, rtol=1e-12
    )
    np.testing.assert_allclose(fines, 10 * (0.25 - 0.1) / (0.8 - 0.1), rtol=1e-12)


def test_reproducible_connected_projection_and_dimensions():
    g = CohortRootGenerator(config())
    a, b = g.generate(9, 2, 1), g.generate(9, 2, 1)
    pd.testing.assert_frame_equal(a.nodes, b.nodes)
    ids = set(a.nodes.node_id)
    assert len(a.edges) == len(ids) - 1
    assert all(p < c for p, c in a.edges.to_numpy())
    assert set(a.organs.order) == set(range(1, 6))
    assert len(a.organs.query("order==1")) == 3
    assert set(a.organs.query("order==1").cohort) == {"A", "B"}
    assert (a.nodes.z <= 0).all()
    assert (a.organs.dropna(subset=["first_branch_cm"]).first_branch_cm == 4.0).all()
    assert a.observation_nodes.query("order==0").shape[0] == 3
    np.testing.assert_allclose(
        a.organs.dry_mass_g.sum(),
        a.diagnostics["root_totals"]["dry_mass_g"],
        rtol=1e-12,
    )
    for _, organ in a.organs.iterrows():
        rows = a.nodes.loc[a.nodes.organ_id.eq(organ.organ_id)]
        np.testing.assert_allclose(rows.length.sum(), organ.length_cm, rtol=1e-12)
        for _, row in rows.iterrows():
            parent = a.nodes.loc[a.nodes.node_id.eq(row.parent_id)].iloc[0]
            np.testing.assert_allclose(
                np.linalg.norm(
                    row[["x", "y", "z"]].to_numpy(float)
                    - parent[["x", "y", "z"]].to_numpy(float)
                ),
                row.length,
                rtol=1e-9,
                atol=0,
            )


def test_branch_beyond_axis_is_unbranched_not_extended():
    c = config()
    c["orders"]["1"]["first_branch_cm"] = dict(mean=20.0, sd=0, min=20.0, max=20.0)
    a = CohortRootGenerator(c).generate(2, 1, 0)
    assert len(a.organs) == 1
    assert a.organs.iloc[0].length_cm == 10.0
    assert a.diagnostics["branch_beyond_tip"] == 1


def test_physical_heading_unchanged_by_attachment_cuts():
    args = (10.0, [0, 0, -2], [1.0, 0, 0], 3.0, 0.005, 10.0, 0.0)
    arc, xyz, _ = integrate_curve(*args, np.random.default_rng(9))
    for attachments in ([], [2.0, 4.0, 8.0]):
        cuts = material_cuts(10.0, arc, attachments, 0.8, 0.1, 0.25)
        split = np.column_stack([np.interp(cuts, arc, xyz[:, k]) for k in range(3)])
        np.testing.assert_allclose(
            np.linalg.norm(np.diff(split, axis=0), axis=1).sum(), 10.0, rtol=1e-12
        )
        np.testing.assert_allclose(
            split[np.searchsorted(cuts, arc)], xyz, rtol=0, atol=0
        )


@pytest.mark.parametrize(
    "spec",
    [
        dict(mean=-1, sd=0, min=-2, max=1),
        dict(mean=1, sd=-1, min=0.1, max=2),
        dict(mean=1, sd=1, min=2, max=3),
    ],
)
def test_invalid_distribution_rejected(spec):
    with pytest.raises(ValueError):
        bounded_draw(spec, np.random.default_rng(1))


def test_budget_fails_instead_of_silent_truncation():
    c = config()
    c["max_organs"] = 2
    with pytest.raises(ValueError, match="budget"):
        CohortRootGenerator(c).generate(0, 1, 0)


def test_midpoint_taper_integral_and_cutoff():
    results = []
    for stations in ([0.0, 10.0], [0.0, 1.0, 7.0, 10.0]):
        cuts = material_cuts(10.0, stations, [2.0, 8.0], 0.8, 0.1, 0.25, 0.75)
        d = taper_diameter(cuts, 10.0, 0.8, 0.1, 0.75)
        e = equivalent_diameter(d[:-1], d[1:])
        results.append(np.pi / 4 * np.dot(np.diff(cuts), e**2))
        assert 5.0 in cuts
        assert taper_diameter(5.0, 10.0, 0.8, 0.1, 0.75) == pytest.approx(0.625)
        crossing = 5 + 5 * (0.625 - 0.25) / (0.625 - 0.1)
        assert np.min(abs(cuts - crossing)) < 1e-12
    expected = (
        np.pi * 5 / 12 * (0.8**2 + 0.8 * 0.625 + 2 * 0.625**2 + 0.625 * 0.1 + 0.1**2)
    )
    np.testing.assert_allclose(results, expected, rtol=1e-12)


def test_multiple_step_endpoint_and_input_immutability():
    heading = np.array([1.0, 0.0, 0.0])
    original = heading.copy()
    arc, points, _ = integrate_curve(
        0.9, [0, 0, -1], heading, 0.3, 0.0, 10.0, 0.0, np.random.default_rng(2)
    )
    np.testing.assert_array_equal(heading, original)
    np.testing.assert_allclose(np.diff(arc), [0.3, 0.3, 0.3], rtol=1e-12)
    np.testing.assert_allclose(points[-1], [0.9, 0, -1], rtol=1e-12)


def test_nearly_coincident_material_cuts_fail_without_relaxed_tolerance():
    with pytest.raises(ValueError, match="material cuts"):
        material_cuts(10.0, [0.0, 2.0, 10.0], [np.nextafter(2.0, 3.0)], 0.8, 0.1, 0.25)


def test_reflection_and_above_soil_rejection():
    arc, xyz, n = integrate_curve(
        10.0, [0, 0, -0.1], [0, 0, 1.0], 1.0, 0.01, 10.0, 0.0, np.random.default_rng(0)
    )
    assert n >= 1 and (xyz[:, 2] <= 0).all()
    np.testing.assert_allclose(
        np.linalg.norm(np.diff(xyz, axis=0), axis=1), np.diff(arc), rtol=1e-9, atol=0
    )
    with pytest.raises(ValueError, match="soil start"):
        integrate_curve(
            1.0, [0, 0, 1.0], [1.0, 0, 0], 1.0, 0.0, 10.0, 0.0, np.random.default_rng(0)
        )


@pytest.mark.parametrize(
    "key,value",
    [
        ("crown_mass_g", float("nan")),
        ("crown_depth_cm", [-1, 2]),
        ("later_maturity", [0.8, 0.2]),
        ("crown_radius_cm", -1),
        ("max_organs", 2.5),
    ],
)
def test_invalid_controls_reject_before_generation(key, value):
    c = config()
    c[key] = value
    with pytest.raises(ValueError):
        CohortRootGenerator(c)


def test_graph_complete_reproducibility_and_multiple_daughters():
    c = config()
    c["orders"]["1"]["daughter_probabilities"] = [0.0, 1.0]
    a = CohortRootGenerator(c).generate(21, 2, 1)
    b = CohortRootGenerator(c).generate(21, 2, 1)
    for name in ("nodes", "edges", "organs", "observation_nodes", "observation_edges"):
        pd.testing.assert_frame_equal(getattr(a, name), getattr(b, name))
    assert a.diagnostics == b.diagnostics
    assert a.edges.child_id.is_unique
    assert set(a.edges.child_id) == set(a.nodes.node_id) - {0}
    assert set(a.edges.parent_id) <= set(a.nodes.node_id)
    assert a.organs.query('order==1 and cohort=="A"').daughter_count.eq(2).all()
    other = CohortRootGenerator(c).generate(22, 2, 1)
    assert not a.nodes.equals(other.nodes)


def test_nonzero_sd_sampling_is_bounded():
    rng = np.random.default_rng(2)
    x = [
        bounded_draw(dict(mean=2.0, sd=1.0, min=0.5, max=4.0), rng) for _ in range(1000)
    ]
    assert min(x) >= 0.5 and max(x) <= 4 and np.std(x) > 0.2


def test_roundoff_option_preserves_normal_geometry_and_rejects_nonbool():
    c = config()
    a = CohortRootGenerator(c).generate(21, 2, 0)
    c["reconcile_length_metadata"] = True
    b = CohortRootGenerator(c).generate(21, 2, 0)
    pd.testing.assert_frame_equal(a.nodes, b.nodes)
    assert b.diagnostics["length_metadata_reconciliations"] == []
    c["reconcile_length_metadata"] = "yes"
    with pytest.raises(ValueError):
        CohortRootGenerator(c)


def test_reconciliation_accept_and_each_guard():
    from deeprootgen.research.cohort_root_generator import reconcile_interval_lengths

    coords = np.array([[1e5, 0.0, 0.0], [1e5 + 1e-4, 0.0, 0.0]])
    actual = np.linalg.norm(coords[1] - coords[0])
    stored = np.array([actual * (1 + 2e-9)])
    with pytest.raises(ValueError, match="disabled"):
        reconcile_interval_lengths(coords, stored)
    fixed, records = reconcile_interval_lengths(coords, stored, True)
    assert fixed[0] == actual and len(records) == 1 and stored[0] != actual
    with pytest.raises(ValueError, match="absolute"):
        reconcile_interval_lengths([[0, 0, 0], [100, 0, 0]], [100 * (1 + 2e-9)], True)
    with pytest.raises(ValueError, match="relative"):
        reconcile_interval_lengths(coords, [actual * (1 + 1e-6)], True)
    with pytest.raises(ValueError, match="resolution"):
        reconcile_interval_lengths([[1e5, 0, 0], [1e5 + 1e-12, 0, 0]], [1e-12], True)
    # A sub-micron interval at ordinary coordinates (a native site 7.3e-7 cm from a curve
    # station, Site 4 search): roundoff-level disagreement is reconciled, not rejected.
    a = np.array([120.0, -95.0, -73.0])
    b = a + 7.287751628837214e-07 * np.array([0.6, 0.0, -0.8])
    chord = np.linalg.norm(b - a)
    fixed, records = reconcile_interval_lengths([a, b], [chord * (1 + 1.6e-8)], True, roundoff_scaled=True)
    assert fixed[0] == chord and records[0]["relative_error"] > np.sqrt(np.finfo(float).eps)
    with pytest.raises(ValueError, match="relative"):          # historical sqrt(eps) rule by default
        reconcile_interval_lengths([a, b], [chord * (1 + 1.6e-8)], True)
    with pytest.raises(ValueError, match="relative"):          # beyond what endpoint rounding explains
        reconcile_interval_lengths([a, b], [chord * (1 + 5e-6)], True, roundoff_scaled=True)


def test_missing_controls_and_impossible_inclination_rejected():
    c = config()
    del c["crown_mass_g"]
    with pytest.raises(ValueError, match="Missing"):
        CohortRootGenerator(c)
    c = config()
    c["inclination_bounds_deg"] = [30.0, 30.0]
    with pytest.raises(ValueError, match="Inclination"):
        CohortRootGenerator(c)
