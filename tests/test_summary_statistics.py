"""Regression tests for every public RSA statistic in the revised module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from deeprootgen.statistics import summary_statistics as ss


@pytest.mark.parametrize(
    "klass,expected",
    [
        (ss.RootNumber, 3),
        (ss.TotalLength, 17.0),
        (ss.AverageLength, 17.0 / 3),
        (ss.TotalVolume, np.pi * (0.1**2 * 10 + 0.05**2 * 5 + 0.025**2 * 2)),
        (ss.AverageVolume, np.pi * (0.1**2 * 10 + 0.05**2 * 5 + 0.025**2 * 2) / 3),
        (ss.TotalDiameter, 0.2 + 0.2 + 0.1 + 0.1 + 0.05),
        (ss.AverageDiameter, (0.2 * 10 + 0.1 * 5 + 0.05 * 2) / 17),
        (ss.RootBranchingFrequency, 2.0 / 15),
    ],
)
def test_scalar_root_metrics(rsa_nodes, klass, expected):
    assert klass().calculate(rsa_nodes) == pytest.approx(expected)


def test_root_count_only_valid_organs(rsa_nodes):
    nodes = rsa_nodes.copy()
    nodes.loc[nodes.organ_id.eq(3), "invalid_root"] = True
    assert ss.RootNumber().calculate(nodes) == 2
    assert ss.TotalLength().calculate(nodes) == pytest.approx(15)


def test_base_node_not_counted_as_root(rsa_nodes):
    assert ss.RootNumber().calculate(rsa_nodes) == 3
    assert 0 not in set(ss.RootLengthDistribution().per_root(rsa_nodes).organ_id)


def test_recorded_vs_geometric_for_scalar(line_nodes):
    nodes = line_nodes.copy()
    nodes.loc[nodes.node_id.eq(1), "length"] = 22.0
    assert ss.TotalLength(length_source="geometric").calculate(nodes) == pytest.approx(
        10
    )
    assert ss.TotalLength(length_source="recorded").calculate(nodes) == pytest.approx(
        22
    )


def test_weight_is_volume_times_density(rsa_nodes):
    expected = ss.TotalVolume().calculate(rsa_nodes) * 0.2
    assert ss.TotalWeight(root_tissue_density=0.2).calculate(
        rsa_nodes
    ) == pytest.approx(expected)
    assert ss.AverageWeight(root_tissue_density=0.2).calculate(
        rsa_nodes
    ) == pytest.approx(expected / 3)


def test_specific_root_length_has_cm_per_g_units(rsa_nodes):
    actual = ss.TotalSpecificRootLength(root_tissue_density=0.2).calculate(rsa_nodes)
    expected = 17 / ss.TotalWeight(root_tissue_density=0.2).calculate(rsa_nodes)
    assert actual == pytest.approx(expected)
    assert ss.TotalSpecificRootLength(root_tissue_density=0.2).unit == "cm/g"


def test_average_organ_specific_root_length(rsa_nodes):
    per_root_expected = []
    for diameter in (0.2, 0.1, 0.05):
        per_root_expected.append(1.0 / (np.pi * (diameter / 2) ** 2 * 0.2))
    actual = ss.AverageSpecificRootLength(root_tissue_density=0.2).calculate(rsa_nodes)
    assert actual == pytest.approx(np.mean(per_root_expected))


def test_length_weighted_diameter_is_invariant_to_subdivision(
    line_nodes, subdivided_line
):
    np.testing.assert_allclose(
        ss.AverageDiameter().calculate(line_nodes),
        ss.AverageDiameter().calculate(subdivided_line),
    )
    assert ss.TotalDiameter().calculate(
        subdivided_line
    ) != ss.TotalDiameter().calculate(line_nodes)


def test_root_length_distribution_per_root(rsa_nodes):
    result = ss.RootLengthDistribution().per_root(rsa_nodes)
    assert dict(zip(result.organ_id, result.root_length_cm)) == {
        1: 10.0,
        2: 5.0,
        3: 2.0,
    }
    assert dict(zip(result.organ_id, result.order)) == {1: 1, 2: 2, 3: 3}


def test_root_length_histogram(rsa_nodes):
    result = ss.RootLengthDistribution(
        length_bins_cm=[0.0, 3.0, 6.0, 12.0]
    ).calculate_df(rsa_nodes)
    np.testing.assert_array_equal(result.root_count.to_numpy(), [1, 1, 1])
    assert (
        ss.RootLengthDistribution(length_bins_cm=[0.0, 3.0, 6.0, 12.0])
        .calculate(rsa_nodes)
        .sum()
        == 3
    )


def test_diameter_histogram_is_length_weighted(rsa_nodes):
    calc = ss.RootDiameterDistribution(diameter_bins_mm=[0, 1, 2, 3])
    out = calc.calculate_df(rsa_nodes)
    np.testing.assert_allclose(out.root_length_cm, [2.0, 5.0, 10.0])
    assert out.root_length_fraction.sum() == pytest.approx(1)


def test_dry_mass_diameter_classes_sum_to_mass(rsa_nodes):
    calc = ss.RootDryMassByDiameter([0.0, 1.0, 2.0, 3.0], root_tissue_density=0.2)
    out = calc.calculate_df(rsa_nodes)
    assert out.dry_mass_g.sum() == pytest.approx(
        ss.TotalWeight(root_tissue_density=0.2).calculate(rsa_nodes)
    )


def test_branching_order_counts_and_lengths(rsa_nodes):
    out = ss.RootBranchingOrderDistribution(max_order=5).calculate_df(rsa_nodes)
    np.testing.assert_array_equal(out.root_count, [1, 1, 1, 0, 0])
    np.testing.assert_allclose(out.root_length_cm, [10, 5, 2, 0, 0])
    assert (
        ss.RootBranchingOrderDistribution(max_order=5).calculate(rsa_nodes).sum() == 3
    )


def test_branching_frequency_respects_eligible_orders(rsa_nodes):
    # Two lateral emergences over 10+5 cm of eligible parent-root length.
    assert ss.RootBranchingFrequency(max_order=3).calculate(rsa_nodes) == pytest.approx(
        2 / 15
    )


def test_branching_frequency_max_order_excludes_higher_order_daughters(rsa_nodes):
    # With max_order=2, only order-1 parents are eligible: 1 / 10 cm.
    assert ss.RootBranchingFrequency(max_order=2).calculate(rsa_nodes) == pytest.approx(
        1 / 10
    )


def test_branching_angles_are_90_degrees(rsa_nodes):
    out = ss.RootBranchingAngleDistribution().calculate_df(rsa_nodes)
    assert len(out) == 2
    np.testing.assert_allclose(sorted(out.branching_angle_deg), [90.0, 90.0])
    assert set(out.order) == {2, 3}


def test_segment_inclination_and_azimuth(rsa_nodes):
    out = ss.RootOrientationDistribution().calculate_df(rsa_nodes).set_index("node_id")
    assert out.loc[1, "inclination_deg"] == pytest.approx(0)
    assert out.loc[3, "inclination_deg"] == pytest.approx(90)
    assert out.loc[3, "azimuth_deg"] == pytest.approx(0)
    assert out.loc[5, "azimuth_deg"] == pytest.approx(90)
    assert out.loc[1, "vertical_downward_fraction"] == pytest.approx(1)
    assert out.loc[3, "horizontal_fraction"] == pytest.approx(1)


def test_root_level_orientation(rsa_nodes):
    out = ss.RootOrientationDistribution().per_root(rsa_nodes).set_index("organ_id")
    assert out.loc[1, "inclination_deg"] == pytest.approx(0)
    assert out.loc[2, "inclination_deg"] == pytest.approx(90)
    assert out.loc[3, "azimuth_deg"] == pytest.approx(90)
    assert out.loc[1, "net_displacement_cm"] == pytest.approx(10)


def test_rooting_extent(rsa_nodes):
    row = ss.RootingExtent().calculate_df(rsa_nodes).iloc[0]
    assert row.max_depth_cm == pytest.approx(10)
    assert row.max_radius_cm == pytest.approx(5)
    assert row.x_spread_cm == pytest.approx(5)
    assert row.y_spread_cm == pytest.approx(2)
    assert row.bounding_circle_diameter_cm == pytest.approx(10)


def test_rooting_extent_explicit_origin(rsa_nodes):
    result = ss.RootingExtent(origin=(1, 0, 0)).calculate_df(rsa_nodes).iloc[0]
    assert result.max_radius_cm == pytest.approx(4)


def test_vertical_length_allocated_exactly(rsa_nodes):
    out = ss.VerticalRootLengthDistribution(bins=[0.0, 5.0, 10.0]).calculate_df(
        rsa_nodes
    )
    np.testing.assert_allclose(out.root_length_cm, [12.0, 5.0])
    assert out.root_length_cm.sum() == pytest.approx(
        ss.TotalLength().calculate(rsa_nodes)
    )


def test_cumulative_depth_distribution(rsa_nodes):
    cdf, edges = ss.DepthDistribution(bins=[0.0, 5.0, 10.0]).calculate(rsa_nodes)
    np.testing.assert_allclose(edges, [0.0, 5.0, 10.0])
    np.testing.assert_allclose(cdf, [0.0, 12 / 17, 1.0])


def test_radial_length_partition_conserved(rsa_nodes):
    out = ss.HorizontalRootLengthDistribution(bins=[0, 2.5, 5.5]).calculate_df(
        rsa_nodes
    )
    assert out.root_length_cm.sum() == pytest.approx(17)
    # The 10 cm vertical primary root remains at radius zero.
    assert out.root_length_cm.iloc[0] >= 10


def test_cumulative_radial_distribution_is_normalized(rsa_nodes):
    cdf, edges = ss.RadialDistribution(bins=[0, 2.5, 5.5]).calculate(rsa_nodes)
    assert cdf[0] == 0
    assert cdf[-1] == pytest.approx(1.0)
    assert np.diff(cdf).min() >= -1e-12
    assert len(edges) == len(cdf)


def test_radial_distance_is_euclidean_not_sum_of_abs_axes():
    # Straight segment from the origin to (3,4,0): its terminal radius is 5.
    nodes = pd.DataFrame(
        [
            dict(
                node_id=0,
                parent_id=-1,
                organ_id=0,
                order=0,
                segment_rank=0,
                x=0.0,
                y=0.0,
                z=0.0,
                diameter=0.2,
                length=0.0,
            ),
            dict(
                node_id=1,
                parent_id=0,
                organ_id=1,
                order=1,
                segment_rank=1,
                x=3.0,
                y=4.0,
                z=0.0,
                diameter=0.2,
                length=5.0,
            ),
        ]
    )
    result = ss.RadialDistribution(bins=5).calculate_df(nodes)
    assert result.radius_max_cm.iloc[-1] == pytest.approx(5)
    assert result.root_length_cm.sum() == pytest.approx(5)


def test_convex_hull_nondegenerate(rsa_nodes):
    assert ss.ConvexHullArea().calculate(rsa_nodes) > 0
    assert ss.ConvexHullVolume().calculate(rsa_nodes) > 0


def test_convex_hull_degenerate_returns_nan(line_nodes):
    assert np.isnan(ss.ConvexHullArea().calculate(line_nodes))
    assert np.isnan(ss.ConvexHullVolume().calculate(line_nodes))


def test_histogram_and_statistic_comparison_array_shapes(rsa_nodes):
    names = [
        ss.RootLengthDistribution,
        ss.RootDiameterDistribution,
        ss.RootBranchingOrderDistribution,
        ss.RootBranchingAngleDistribution,
        ss.RootOrientationDistribution,
        ss.VerticalRootLengthDistribution,
        ss.HorizontalRootLengthDistribution,
        ss.DepthDistribution,
        ss.RadialDistribution,
    ]
    for cls in names:
        data = cls().get_xy_comparison_data(rsa_nodes, n_elements=7)
        assert isinstance(data, np.ndarray)
        assert len(data) <= 7


def test_root_length_density_matches_aggregator(rsa_nodes, soil_grid):
    from deeprootgen.statistics.root_grid_aggregation import aggregate_root_grid

    metric = ss.RootLengthDensity(soil_df=soil_grid, length_source="geometric")
    agg, _ = aggregate_root_grid(rsa_nodes, soil_grid, "geometric")
    voxel = metric.calculate_per_voxel(rsa_nodes)
    np.testing.assert_allclose(voxel.root_length_cm, agg.root_length_cm)
    assert voxel.rld_cm_cm3.sum() == pytest.approx(agg.rld_cm_cm3.sum())


def test_rld_aggregations_conserve_voxel_length(rsa_nodes, soil_grid):
    calc = ss.RootLengthDensity(soil_df=soil_grid)
    total = calc.calculate_per_voxel(rsa_nodes).root_length_cm.sum()
    assert calc.calculate_per_layer(rsa_nodes).root_length_cm.sum() == pytest.approx(
        total
    )
    assert calc.calculate_per_row(rsa_nodes).root_length_cm.sum() == pytest.approx(
        total
    )
    assert calc.calculate_per_column(rsa_nodes).root_length_cm.sum() == pytest.approx(
        total
    )
    assert calc.calculate(rsa_nodes) == pytest.approx(total / 8000.0)


def test_root_type_filtering_in_voxel_rld(rsa_nodes, soil_grid):
    total = ss.RootLengthDensity(soil_df=soil_grid).calculate_per_voxel(rsa_nodes)
    fine = ss.RootLengthDensity(
        soil_df=soil_grid, root_types=["fine"]
    ).calculate_per_voxel(rsa_nodes)
    struct = ss.RootLengthDensity(
        soil_df=soil_grid, root_types=["structural"]
    ).calculate_per_voxel(rsa_nodes)
    np.testing.assert_allclose(
        total.root_length_cm, fine.root_length_cm + struct.root_length_cm
    )


def test_stats_preserve_length_when_parent_segment_subdivided(
    line_nodes, subdivided_line
):
    for metric in [
        ss.TotalLength(),
        ss.TotalVolume(),
        ss.AverageDiameter(),
        ss.RootLengthDistribution(length_bins_cm=[0, 5, 15]),
        ss.RadialDistribution(bins=[0.0, 3.0, 7.0, 12.0]),
    ]:
        original = metric.calculate(line_nodes)
        cut = metric.calculate(subdivided_line)
        if isinstance(original, tuple):
            np.testing.assert_allclose(original[0], cut[0])
        else:
            np.testing.assert_allclose(original, cut)


def test_statistic_registry_resolves_classes():
    choices = ss.get_summary_statistics()
    assert choices
    for row in choices:
        klass = ss.get_summary_statistic_func(row["value"])
        assert klass is not None
        assert issubclass(klass, ss.SummaryStatisticBase)


@pytest.mark.parametrize("bad", ["broken", "", "None"])
def test_invalid_length_source_rejected(bad):
    with pytest.raises(ValueError, match="length_source"):
        ss.TotalLength(length_source=bad)


@pytest.mark.parametrize(
    "column",
    ["node_id", "parent_id", "x", "y", "z", "order", "organ_id", "segment_rank"],
)
def test_missing_graph_columns_raise(rsa_nodes, column):
    with pytest.raises(ValueError, match="Missing root graph columns"):
        ss.TotalLength().calculate(rsa_nodes.drop(columns=column))


def test_duplicate_node_ids_raise(rsa_nodes):
    nodes = pd.concat([rsa_nodes, rsa_nodes.iloc[[1]]])
    with pytest.raises(ValueError, match="node_id must be unique"):
        ss.TotalLength().calculate(nodes)


def test_zero_geometric_length_raises(line_nodes):
    nodes = line_nodes.copy()
    nodes.loc[nodes.node_id.eq(1), "x"] = 0
    with pytest.raises(ValueError, match="Zero-length"):
        ss.TotalLength().calculate(nodes)


@pytest.mark.parametrize("bins", [0, -2, [0, 0, 2], [-1, 0, 2], [0, float("nan")]])
def test_invalid_radial_bins_rejected(rsa_nodes, bins):
    with pytest.raises(ValueError, match="Bin|bins"):
        ss.RadialDistribution(bins=bins).calculate(rsa_nodes)


def test_invalid_origin_rejected(rsa_nodes):
    with pytest.raises(ValueError, match="origin"):
        ss.RootingExtent(origin=(0, 0)).calculate(rsa_nodes)


def test_empty_valid_graph_has_no_roots(rsa_nodes):
    nodes = rsa_nodes.copy()
    nodes.loc[nodes.order.gt(0), "invalid_root"] = True
    assert ss.RootNumber().calculate(nodes) == 0
    assert ss.TotalLength().calculate(nodes) == 0.0
    assert ss.RootBranchingFrequency().calculate(nodes) == 0.0
    assert np.isnan(ss.AverageLength().calculate(nodes))


@pytest.mark.parametrize(
    "calc",
    [
        lambda g: ss.RootLengthDistribution().visualise(g),
        lambda g: ss.RootDiameterDistribution().visualise(g),
        lambda g: ss.RootBranchingAngleDistribution().visualise(g),
        lambda g: ss.RootOrientationDistribution().visualise(g),
        lambda g: ss.RootingExtent().visualise(g),
        lambda g: ss.DepthDistribution().visualise(g),
        lambda g: ss.RadialDistribution().visualise(g),
        lambda g: ss.TotalLength().visualise(g),
    ],
)
def test_visualisations_return_plotly_figures(rsa_nodes, calc):
    fig = calc(rsa_nodes)
    assert isinstance(fig, go.Figure)


def test_mass_by_diameter_uses_node_density_when_no_override(rsa_nodes):
    result = ss.RootDryMassByDiameter([0, 1, 2, 3]).calculate_df(rsa_nodes)
    assert result.dry_mass_g.sum() == pytest.approx(
        ss.TotalWeight(root_tissue_density=0.2).calculate(rsa_nodes)
    )


def test_invalid_density_raises(rsa_nodes):
    with pytest.raises(ValueError, match="density"):
        ss.TotalWeight(root_tissue_density=-1).calculate(rsa_nodes)


def test_recorded_length_negative_raises(line_nodes):
    nodes = line_nodes.copy()
    nodes.loc[nodes.node_id.eq(1), "length"] = -1.0
    with pytest.raises(ValueError, match="nonnegative"):
        ss.TotalLength(length_source="recorded").calculate(nodes)


def test_invalid_diameter_raises_for_mass(rsa_nodes):
    nodes = rsa_nodes.copy()
    nodes.loc[nodes.node_id.eq(1), "diameter"] = -0.1
    with pytest.raises(ValueError, match="Diameters"):
        ss.TotalWeight(root_tissue_density=0.2).calculate(nodes)


def test_all_root_orientation_angles_in_valid_range(rsa_nodes):
    table = ss.RootOrientationDistribution().calculate_df(rsa_nodes)
    assert table.inclination_deg.between(0, 180).all()
    assert table.azimuth_deg.between(0, 360, inclusive="left").all()


def test_invalid_root_segment_does_not_contribute_to_length_distribution(rsa_nodes):
    nodes = rsa_nodes.copy()
    nodes.loc[nodes.organ_id.eq(3), "invalid_root"] = True
    result = ss.RootLengthDistribution().per_root(nodes)
    assert len(result) == 2
    assert result.root_length_cm.sum() == pytest.approx(15.0)


def test_rld_segment_subdivision_invariance(line_nodes, subdivided_line, two_voxels):
    calc = ss.RootLengthDensity(soil_df=two_voxels)
    a = calc.calculate_per_voxel(line_nodes)
    b = calc.calculate_per_voxel(subdivided_line)
    np.testing.assert_allclose(a.root_length_cm, b.root_length_cm)
    np.testing.assert_allclose(a.rld_cm_cm3, b.rld_cm_cm3)


def test_3d_voxel_rld_uses_recorded_when_requested(line_nodes, two_voxels):
    nodes = line_nodes.copy()
    nodes.loc[nodes.node_id.eq(1), "length"] = 20.0
    original = ss.RootLengthDensity(soil_df=two_voxels, length_source="geometric")
    recorded = ss.RootLengthDensity(soil_df=two_voxels, length_source="recorded")
    assert recorded.calculate(nodes) == pytest.approx(2 * original.calculate(nodes))


def test_voxel_rld_layer_returns_depth_top(rsa_nodes, soil_grid):
    table = ss.RootLengthDensity(soil_df=soil_grid).calculate_per_layer(rsa_nodes)
    assert "depth_top_cm" in table.columns
    assert table.depth_top_cm.is_monotonic_increasing


def test_no_branches_yields_empty_branch_angles(line_nodes):
    values = ss.RootBranchingAngleDistribution().calculate(line_nodes)
    assert values.size == 0


def test_depth_distribution_length_matches_grid_layer_length_when_aligned(
    rsa_nodes, soil_grid
):
    # The voxel grid covers a wider range, but the common depth coordinate
    # and exact segment clipping should conserve the full 17 cm of root length.
    depth = ss.VerticalRootLengthDistribution(bins=[0, 5, 10, 20]).calculate_df(
        rsa_nodes
    )
    voxel = ss.RootLengthDensity(soil_df=soil_grid).calculate_per_voxel(rsa_nodes)
    assert depth.root_length_cm.sum() == pytest.approx(voxel.root_length_cm.sum())
