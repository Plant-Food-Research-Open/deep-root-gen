"""Invented analytic root cylinders only; no measured inputs or model fitting."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deeprootgen.research.core_observation import (
    _cylinder_fractions,
    predict_core_observations,
    qualify_root_segments,
)


def graph(points=((0, 0, 0), (0, 0, -10)), diameters=None):
    diameters = diameters if diameters is not None else [.2] * (len(points) - 1)
    nodes = pd.DataFrame([
        dict(node_id=i, parent_id=i - 1, plant_id=1, order=int(i > 0),
             x=float(x), y=float(y), z=float(z), diameter=99. if i == 0 else diameters[i - 1],
             root_type="base" if i == 0 else "structural", invalid_root=False,
             length=999., root_tissue_density=999.)
        for i, (x, y, z) in enumerate(points)
    ])
    return nodes, edges_of(nodes)


def edges_of(nodes):
    return nodes.loc[nodes.order.gt(0), ["parent_id", "node_id"]].rename(columns={"node_id": "child_id"}).reset_index(drop=True)


def qualify(nodes=None, edges=None, **updates):
    if nodes is None:
        nodes, default_edges = graph()
    else:
        default_edges = edges_of(nodes)
    args = dict(coordinate_frame="invented-soil-frame", fine_diameter_max_mm=2., dry_density_g_cm3=.25)
    args.update(updates)
    return qualify_root_segments(nodes, default_edges if edges is None else edges, **args)


def core(**updates):
    row = dict(core_id="invented-core", x_cm=0., y_cm=0., z_lower_cm=-8., z_upper_cm=-2., radius_cm=1., sampled=True)
    row.update(updates)
    return row


@pytest.mark.parametrize("points,spec,expected", [
    (((0, 0, 0), (0, 0, -10)), {}, 6.),
    (((-3, 0, -4), (3, 0, -4)), {}, 2.),
    (((-3, 0, 0), (3, 0, -6)), {}, 2 * np.sqrt(2)),
    (((-3, 1, -4), (3, 1, -4)), {}, 0.),  # Tangent at a single point.
    (((1, 0, 0), (1, 0, -10)), {}, 6.),  # Vertical side boundary is included.
    (((-3, 0, -2), (3, 0, -2)), {}, 2.),  # Upper face is included.
    (((-3, 0, -8), (3, 0, -8)), {}, 2.),  # Lower face is included.
    (((-3, 0, -9), (3, 0, -9)), {}, 0.),
    (((0, 0, -10), (0, 0, 0)), {}, 6.),  # Reverse direction.
    (((2, 0, 0), (2, 0, -10)), {}, 0.),
])
def test_analytic_intersections_and_same_mass_fraction(points, spec, expected):
    nodes, edges = graph(points)
    support = qualify(nodes, edges)
    prediction = predict_core_observations(support, [core(**spec)]).cores.iloc[0]
    assert prediction.total_length_cm == pytest.approx(expected)
    assert prediction.fine_length_cm == pytest.approx(expected)
    assert prediction.coarse_length_cm == 0.
    assert prediction.total_root_volume_cm3 == pytest.approx(expected * np.pi * .1**2)
    assert prediction.total_dry_mass_g == pytest.approx(expected * np.pi * .1**2 * .25)
    assert prediction.total_rld_cm_cm3 == pytest.approx(expected / (6 * np.pi))


def test_explicit_units_threshold_child_diameter_and_no_base_double_count():
    nodes, edges = graph(((0, 0, 0), (0, 0, -4), (0, 0, -10)), [.2, .3])
    original = nodes.copy(deep=True)
    support = qualify(nodes, edges)
    result = predict_core_observations(support, [core(z_lower_cm=-10., z_upper_cm=0.)]).cores.iloc[0]
    assert result.fine_length_cm == 4  # Child diameter .2 cm == 2 mm, inclusive.
    assert result.coarse_length_cm == 6
    assert result.total_length_cm == 10
    assert result.fine_dry_mass_g == pytest.approx(4 * np.pi * .1**2 * .25)
    assert result.coarse_dry_mass_g == pytest.approx(6 * np.pi * .15**2 * .25)
    assert len(support.segments) == 2
    assert support.diagnostics["base_node_count"] == 1
    assert support.whole_system_totals["included"]["dry_mass_g"] == result.total_dry_mass_g
    pd.testing.assert_frame_equal(nodes, original)
    # Explicit dry density overrides unusable recorded metadata, by declaration.
    nodes["root_tissue_density"] = np.nan
    pd.testing.assert_frame_equal(support.segments, qualify(nodes, edges).segments)


def test_subdivision_preserves_length_volume_and_mass():
    whole = qualify(*graph(((-3, 0, -4), (3, 0, -4))))
    divided = qualify(*graph(((-3, 0, -4), (-.5, 0, -4), (0, 0, -4), (3, 0, -4))))
    a, b = (predict_core_observations(s, [core()]).cores for s in (whole, divided))
    pd.testing.assert_frame_equal(a, b, atol=1e-14, rtol=1e-14)
    for field in ("length_cm", "root_volume_cm3", "dry_mass_g"):
        assert whole.whole_system_totals["included"][field] == pytest.approx(divided.whole_system_totals["included"][field])


def test_unsampled_is_missing_sampled_empty_is_zero_and_core_order_preserved():
    support = qualify()
    spec = [core(core_id="missing", sampled=False), core(core_id="empty", x_cm=99.), core(core_id="hit")]
    result = predict_core_observations(support, pd.DataFrame(spec), by_plant=True)
    assert result.cores.core_id.tolist() == ["missing", "empty", "hit"]
    values = [c for c in result.cores.columns if c.endswith(("_length_cm", "_mass_g", "_rld_cm_cm3", "_root_volume_cm3"))]
    assert result.cores.loc[0, values].isna().all()
    assert result.cores.loc[1, values].eq(0).all()
    assert result.cores.loc[2, "total_length_cm"] == pytest.approx(6.)
    assert result.by_plant.loc[0, values].isna().all()
    assert result.cores.core_volume_cm3.eq(6 * np.pi).all()


@pytest.mark.parametrize("sampled", ["N", "Y", 0, 1, None, np.nan])
def test_sampled_requires_strict_booleans(sampled):
    with pytest.raises(ValueError, match="strict boolean"):
        predict_core_observations(qualify(), [core(sampled=sampled)])


def test_invalid_node_and_entire_descendant_support_excluded_consistently():
    nodes, edges = graph(((0, 0, 0), (0, 0, -2), (0, 0, -5), (0, 0, -9)))
    nodes.loc[nodes.node_id.eq(2), "invalid_root"] = True
    support = qualify(nodes, edges)
    assert support.segments.included.tolist() == [True, False, False]
    assert support.segments.exclusion_reason.tolist() == [None, "invalid_node", "invalid_ancestor"]
    assert support.whole_system_totals["included"]["length_cm"] == 2
    assert support.whole_system_totals["excluded"]["length_cm"] == 7
    assert support.whole_system_totals["all_root_cylinders"]["length_cm"] == 9
    result = predict_core_observations(support, [core(z_lower_cm=-20, z_upper_cm=1)]).cores.iloc[0]
    assert result.total_length_cm == 2
    assert result.total_dry_mass_g == support.whole_system_totals["included"]["dry_mass_g"]
    nodes.loc[nodes.node_id.eq(0), "invalid_root"] = True
    assert qualify(nodes, edges).whole_system_totals["included"]["segment_count"] == 0


def combine_plants():
    one, _ = graph()
    two = one.copy(deep=True)
    two["node_id"] += 10
    two.loc[two.parent_id.ge(0), "parent_id"] += 10
    two["plant_id"] = 2
    two["diameter"] = .3
    nodes = pd.concat([one, two], ignore_index=True)
    return nodes, edges_of(nodes)


def test_multiplant_additivity_determinism_and_perplant_roots():
    nodes, edges = combine_plants()
    support = qualify(nodes, edges)
    result = predict_core_observations(support, [core()], by_plant=True)
    assert support.diagnostics["base_node_count"] == 2
    assert result.cores.total_length_cm.iloc[0] == pytest.approx(12)
    assert result.by_plant.total_length_cm.tolist() == pytest.approx([6., 6.])
    assert result.cores.total_dry_mass_g.iloc[0] == pytest.approx(result.by_plant.total_dry_mass_g.sum())
    assert result.cores.fine_length_cm.iloc[0] == pytest.approx(6)
    assert result.cores.coarse_length_cm.iloc[0] == pytest.approx(6)
    shuffled = qualify(nodes.sample(frac=1, random_state=55), edges.sample(frac=1, random_state=42))
    repeated = predict_core_observations(shuffled, [core()], by_plant=True)
    pd.testing.assert_frame_equal(result.cores, repeated.cores)
    pd.testing.assert_frame_equal(result.by_plant, repeated.by_plant)
    pd.testing.assert_frame_equal(support.segments, shuffled.segments)
    assert support.whole_system_totals == shuffled.whole_system_totals


def test_base_only_graph_and_empty_batch_and_zero_geometry():
    support = qualify(*graph(((0, 0, 0),)))
    result = predict_core_observations(support, [core()], by_plant=True)
    assert result.cores.total_length_cm.iloc[0] == 0
    assert result.by_plant.total_dry_mass_g.iloc[0] == 0
    assert support.whole_system_totals["included"]["segment_count"] == 0
    assert predict_core_observations(support, []).cores.empty
    zero = qualify(*graph(((0, 0, 0), (0, 0, 0)), [0.]))
    assert zero.diagnostics["zero_length_segment_count"] == 1
    assert predict_core_observations(zero, [core()]).cores.total_dry_mass_g.iloc[0] == 0


@pytest.mark.parametrize("defect", ["duplicate_node", "duplicate_edge", "missing_parent", "edge_mismatch", "cycle", "two_bases", "no_base", "cross_plant", "stem", "invalid_flag"])
def test_reject_graph_defects_before_excluding_invalid_nodes(defect):
    nodes, edges = graph(((0, 0, 0), (0, 0, -4), (0, 0, -10)))
    if defect == "duplicate_node":
        nodes.loc[2, "node_id"] = 1
    elif defect == "duplicate_edge":
        edges = pd.concat([edges, edges.iloc[:1]], ignore_index=True)
    elif defect == "missing_parent":
        nodes.loc[2, "parent_id"] = 99
        edges = edges_of(nodes)
    elif defect == "edge_mismatch":
        edges.loc[1, "parent_id"] = 0
    elif defect == "cycle":
        nodes.loc[1, "parent_id"] = 2
        edges = edges_of(nodes)
    elif defect == "two_bases":
        nodes.loc[2, ["parent_id", "order", "root_type"]] = [-1, 0, "base"]
        edges = edges_of(nodes)
    elif defect == "no_base":
        nodes.loc[0, "order"] = 1
    elif defect == "cross_plant":
        nodes.loc[2, "plant_id"] = 2
    elif defect == "stem":
        nodes.loc[1, "root_type"] = "stem"
    elif defect == "invalid_flag":
        nodes["invalid_root"] = [False, "False", False]
    with pytest.raises(ValueError):
        qualify(nodes, edges)


@pytest.mark.parametrize("field,value", [("x", np.nan), ("z", np.inf), ("diameter", -1.), ("diameter", np.nan), ("diameter", 1e308)])
def test_reject_nonfinite_or_negative_geometry_even_on_excluded_segments(field, value):
    nodes, edges = graph()
    nodes.loc[1, "invalid_root"] = True
    nodes.loc[1, field] = value
    with pytest.raises(ValueError):
        qualify(nodes, edges)


@pytest.mark.parametrize("updates", [dict(dry_density_g_cm3=None), dict(dry_density_g_cm3=0.), dict(dry_density_g_cm3=True), dict(dry_density_g_cm3=np.inf), dict(fine_diameter_max_mm=0.), dict(coordinate_frame="")])
def test_density_threshold_and_frame_are_explicit(updates):
    with pytest.raises(ValueError):
        qualify(**updates)


def test_core_volume_and_manifest_validation():
    support = qualify()
    good = core(known_volume_cm3=6 * np.pi)
    assert predict_core_observations(support, [good]).cores.core_volume_cm3.iloc[0] == good["known_volume_cm3"]
    for row in [core(known_volume_cm3=99), core(radius_cm=0), core(radius_cm=1e308), core(x_cm=np.nan), core(z_upper_cm=-9)]:
        with pytest.raises(ValueError):
            predict_core_observations(support, [row])
    with pytest.raises(ValueError, match="unique"):
        predict_core_observations(support, [core(), core()])
    with pytest.raises(ValueError):
        predict_core_observations(support, "a-field-file.csv")


def test_existing_exact_intersection_parity_on_invented_random_segments():
    # Load the public standalone module without its statistics package's optional
    # neural/inference dependencies. This is the exact unchanged source routine.
    path = Path(__file__).parents[1] / "deeprootgen/statistics/spatial_rld.py"
    spec = importlib.util.spec_from_file_location("existing_spatial_rld", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rng = np.random.default_rng(731)
    points = rng.uniform(-10, 10, (500, 3))
    nodes, edges = graph(points)
    support = qualify(nodes, edges)
    cores = [core(core_id=i, x_cm=x, y_cm=y) for i, (x, y) in enumerate(rng.uniform(-5, 5, (20, 2)))]
    result = predict_core_observations(support, cores).cores
    for row in result.itertuples(index=False):
        expected = module.calculate_core_rld(nodes, x=row.x_cm, y=row.y_cm, z_lower_bound=row.z_lower_cm,
                                             z_upper_bound=row.z_upper_cm, core_radius=row.radius_cm, length_source="geometric")
        assert row.total_rld_cm_cm3 == pytest.approx(expected, rel=1e-13, abs=1e-13)


def test_batch_pruning_reports_only_nearby_candidates():
    nodes, edges = graph(tuple((i * 10., 0., -4.) for i in range(1001)))
    support = qualify(nodes, edges)
    result = predict_core_observations(support, [core(core_id=i, x_cm=i * 100.) for i in range(20)])
    assert result.diagnostics["candidate_segment_core_pairs"] < 50
    assert result.diagnostics["included_segment_count"] == 1000
    assert result.cores.total_length_cm.iloc[0] == 1.


def test_threshold_decimal_conversion_equality_and_genuinely_larger_diameter():
    nodes, edges = graph(((0, 0, 0), (0, 0, -1), (0, 0, -2)), [.07, .07001])
    support = qualify(nodes, edges, fine_diameter_max_mm=.7)
    assert support.segments.is_fine.tolist() == [True, False]


def test_cross_plant_parent_is_rejected_even_with_one_valid_base_per_plant():
    nodes, _ = combine_plants()
    nodes.loc[nodes.node_id.eq(11), "parent_id"] = 0
    with pytest.raises(ValueError, match="Cross-plant"):
        qualify(nodes, edges_of(nodes))


@pytest.mark.parametrize("start,end,limits,expected", [
    ((1 + 2e-8, 0, -10), (1 - 2e-8, 0, 0), (-8, -2), .3),
    ((-3, 0, -2e-13), (3, 0, 2e-13), (0, 1), 1 / 6),
])
def test_nearly_parallel_radial_and_depth_clipping_are_reversal_invariant(start, end, limits, expected):
    a, b = np.asarray([start]), np.asarray([end])
    forward = _cylinder_fractions(a, b, 0, 0, *limits, 1.)[0]
    reverse = _cylinder_fractions(b, a, 0, 0, *limits, 1.)[0]
    assert forward == pytest.approx(expected, abs=2e-9)
    assert reverse == pytest.approx(forward, abs=1e-14)
    predictions = []
    for points in ((start, end), (end, start)):
        support = qualify(*graph(points))
        result = predict_core_observations(support, [core(z_lower_cm=limits[0], z_upper_cm=limits[1])]).cores.iloc[0]
        predictions.append(result)
    for column in ("total_length_cm", "total_dry_mass_g", "total_root_volume_cm3"):
        assert predictions[0][column] == pytest.approx(predictions[1][column], abs=1e-14)


@pytest.mark.parametrize("points,limits", [
    (((1 + 2**-26, 0, -10), (1, 0, -5), (1 - 2**-26, 0, 0)), (-8, -2)),
    (((-3, 0, -2**-44), (0, 0, 0), (3, 0, 2**-44)), (0, 1)),
])
def test_nearly_parallel_subdivision_preserves_length_and_mass(points, limits):
    predictions = []
    for selected in ((points[0], points[-1]), points, tuple(reversed(points))):
        support = qualify(*graph(selected))
        predictions.append(predict_core_observations(
            support, [core(z_lower_cm=limits[0], z_upper_cm=limits[1])]).cores.iloc[0])
    for column in ("total_length_cm", "total_dry_mass_g", "total_root_volume_cm3"):
        assert [row[column] for row in predictions] == pytest.approx([predictions[0][column]] * 3, abs=1e-13)


def test_tiny_and_large_finite_geometry_uses_stable_distance():
    for length in (1e-200, 1e200):
        support = qualify(*graph(((0, 0, 0), (length, 0, 0))))
        assert support.segments.length_cm.iloc[0] == pytest.approx(length, rel=1e-14, abs=0)
    # Truly coincident points remain valid zero-length geometry.
    support = qualify(*graph(((1, 0, -4), (1, 0, -4))))
    assert predict_core_observations(support, [core()]).cores.total_length_cm.iloc[0] == 0
