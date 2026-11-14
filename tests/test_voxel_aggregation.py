"""Exact, numerical tests of DeepRootGen's segment-to-voxel aggregation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from deeprootgen.statistics.root_grid_aggregation import aggregate_root_grid


def test_single_segment_length_and_density(line_nodes, two_voxels):
    voxels, totals = aggregate_root_grid(line_nodes, two_voxels, "geometric")
    np.testing.assert_allclose(voxels.root_length_cm, [5.0, 5.0])
    np.testing.assert_allclose(
        voxels.rld_cm_cm3, [0.125, 0.125]
    )  # voxel volume = 40 cm3
    assert totals.iloc[0].totalRootLength == pytest.approx(10.0)


def test_root_length_conserved_on_subdivision(line_nodes, subdivided_line, two_voxels):
    original, original_totals = aggregate_root_grid(line_nodes, two_voxels, "geometric")
    split, split_totals = aggregate_root_grid(subdivided_line, two_voxels, "geometric")
    np.testing.assert_allclose(original.root_length_cm, split.root_length_cm)
    np.testing.assert_allclose(original.rld_cm_cm3, split.rld_cm_cm3)
    np.testing.assert_allclose(
        original_totals.totalRootLength, split_totals.totalRootLength
    )


def test_recorded_vs_geometric_length(line_nodes, two_voxels):
    nodes = line_nodes.copy()
    nodes.loc[nodes.node_id.eq(1), "length"] = 20.0
    actual, _ = aggregate_root_grid(nodes, two_voxels, "geometric")
    recorded, _ = aggregate_root_grid(nodes, two_voxels, "recorded")
    assert actual.root_length_cm.sum() == pytest.approx(10)
    assert recorded.root_length_cm.sum() == pytest.approx(20)
    np.testing.assert_allclose(recorded.root_length_cm, 2 * actual.root_length_cm)


def test_length_partly_clipped_outside_grid(line_nodes, two_voxels):
    nodes = line_nodes.copy()
    nodes.loc[nodes.node_id.eq(1), "x"] = 20.0
    nodes.loc[nodes.node_id.eq(1), "length"] = 20.0
    voxels, _ = aggregate_root_grid(nodes, two_voxels, "geometric")
    np.testing.assert_allclose(voxels.root_length_cm, [5.0, 10.0])
    assert voxels.root_length_cm.sum() == pytest.approx(15)


def test_segment_completely_outside_grid(line_nodes, two_voxels):
    nodes = line_nodes.copy()
    nodes.loc[:, "y"] = 10.0
    voxels, totals = aggregate_root_grid(nodes, two_voxels)
    assert voxels.root_length_cm.sum() == 0.0
    assert totals.iloc[0].totalRootLength == 0.0


def test_invalid_segment_excluded(line_nodes, two_voxels):
    nodes = line_nodes.copy()
    nodes.loc[nodes.node_id.eq(1), "invalid_root"] = True
    voxels, _ = aggregate_root_grid(nodes, two_voxels)
    assert voxels.root_length_cm.sum() == 0


def test_invalid_parent_node_is_still_geometric_anchor(line_nodes, two_voxels):
    nodes = line_nodes.copy()
    nodes.loc[nodes.node_id.eq(0), "invalid_root"] = True
    voxels, _ = aggregate_root_grid(nodes, two_voxels)
    assert voxels.root_length_cm.sum() == pytest.approx(10)


def test_missing_invalid_root_column_is_allowed(line_nodes, two_voxels):
    voxels, _ = aggregate_root_grid(line_nodes.drop(columns="invalid_root"), two_voxels)
    assert voxels.root_length_cm.sum() == pytest.approx(10)


def test_fine_and_structural_partition(rsa_nodes, soil_grid):
    voxels, totals = aggregate_root_grid(rsa_nodes, soil_grid, "geometric")
    assert voxels.fineRootLength.sum() == pytest.approx(7)
    assert voxels.structuralRootLength.sum() == pytest.approx(10)
    assert voxels.root_length_cm.sum() == pytest.approx(17)
    np.testing.assert_allclose(
        voxels.fineRootLength + voxels.structuralRootLength, voxels.root_length_cm
    )
    assert totals.iloc[0].totalRootLength == pytest.approx(17)


def test_dry_mass_cylinder_formula(line_nodes, two_voxels):
    voxels, totals = aggregate_root_grid(line_nodes, two_voxels, "geometric")
    expected = np.pi * (0.2 / 2) ** 2 * 10.0 * 0.2
    assert voxels.structuralRootDM.sum() == pytest.approx(expected)
    assert totals.iloc[0].totalRootDM == pytest.approx(expected)
    assert voxels.diameter.loc[voxels.root_length_cm > 0].eq(0.2).all()


def test_dry_mass_fraction_sum_is_one(rsa_nodes, soil_grid):
    voxels, totals = aggregate_root_grid(rsa_nodes, soil_grid)
    for metric, fraction in [
        ("fineRootDM", "fFineRoot"),
        ("structuralRootDM", "fStructuralRoot"),
    ]:
        if voxels[metric].sum() > 0:
            assert voxels[fraction].sum() == pytest.approx(1.0)
    assert totals.iloc[0].totalRootDM == pytest.approx(
        totals.iloc[0].totalFineRoot + totals.iloc[0].totalStructuralRoot
    )


def test_zero_length_segment_does_not_contribute(line_nodes, two_voxels):
    nodes = line_nodes.copy()
    nodes.loc[nodes.node_id.eq(1), "length"] = 0.0
    voxels, _ = aggregate_root_grid(nodes, two_voxels, "recorded")
    assert voxels.root_length_cm.sum() == 0.0


def test_full_grid_contains_zero_occupancy_cells(rsa_nodes, soil_grid):
    voxels, _ = aggregate_root_grid(rsa_nodes, soil_grid)
    assert len(voxels) == 8
    assert (voxels.root_length_cm == 0).any()
    assert (voxels.root_length_cm > 0).any()
    assert (voxels.soil_volume_cm3 == 1000).all()


def test_multiple_plants_get_separate_grid_tables(line_nodes, two_voxels):
    second = line_nodes.copy()
    second["plant_id"] = 2
    nodes = pd.concat([line_nodes, second], ignore_index=True)
    voxels, totals = aggregate_root_grid(nodes, two_voxels)
    assert len(voxels) == 4
    assert set(totals.plant_id) == {1, 2}
    assert len(voxels.id.unique()) == len(voxels)
    np.testing.assert_allclose(totals.totalRootLength, [10.0, 10.0])


def test_node_row_order_does_not_change_aggregation(rsa_nodes, soil_grid):
    first, _ = aggregate_root_grid(rsa_nodes, soil_grid)
    shuffled = rsa_nodes.sample(frac=1.0, random_state=123)
    second, _ = aggregate_root_grid(shuffled, soil_grid)
    np.testing.assert_allclose(first.root_length_cm, second.root_length_cm)


def test_three_dimensional_diagonal_length():
    nodes = pd.DataFrame(
        [
            dict(
                node_id=0,
                parent_id=-1,
                plant_id=1,
                order=0,
                x=0.0,
                y=0.0,
                z=0.0,
                length=0.0,
                diameter=1.0,
                root_tissue_density=0.2,
                root_type="base",
            ),
            dict(
                node_id=1,
                parent_id=0,
                plant_id=1,
                order=1,
                x=2.0,
                y=2.0,
                z=2.0,
                length=np.sqrt(12),
                diameter=1.0,
                root_tissue_density=0.2,
                root_type="structural",
            ),
        ]
    )
    boundaries = pd.MultiIndex.from_product(
        [[0.0, 1.0, 2.0]] * 3, names=["x", "y", "z"]
    ).to_frame(index=False)
    voxels, _ = aggregate_root_grid(nodes, boundaries, "geometric")
    assert voxels.root_length_cm.sum() == pytest.approx(np.sqrt(12))
    assert sorted(voxels.root_length_cm[voxels.root_length_cm > 0]) == pytest.approx(
        [np.sqrt(3), np.sqrt(3)]
    )


@pytest.mark.parametrize("value", ["invalid", "GEOMETRIC", ""])
def test_invalid_length_source_raises(line_nodes, two_voxels, value):
    with pytest.raises(ValueError, match="length_source"):
        aggregate_root_grid(line_nodes, two_voxels, value)


@pytest.mark.parametrize(
    "missing",
    [
        "node_id",
        "parent_id",
        "plant_id",
        "diameter",
        "root_type",
        "root_tissue_density",
    ],
)
def test_missing_node_fields_raise(line_nodes, two_voxels, missing):
    with pytest.raises(ValueError, match="Missing root columns"):
        aggregate_root_grid(line_nodes.drop(columns=missing), two_voxels)


@pytest.mark.parametrize("missing", ["x", "y", "z"])
def test_missing_grid_axis_raises(line_nodes, two_voxels, missing):
    with pytest.raises(ValueError, match="soil_df"):
        aggregate_root_grid(line_nodes, two_voxels.drop(columns=missing))


def test_invalid_grid_raises(line_nodes):
    with pytest.raises(ValueError, match="Soil grid"):
        aggregate_root_grid(line_nodes, pd.DataFrame({"x": [0], "y": [0], "z": [0]}))


def test_duplicate_node_id_within_plant_raises(line_nodes, two_voxels):
    with pytest.raises(ValueError, match="Duplicate node_id"):
        aggregate_root_grid(pd.concat([line_nodes, line_nodes.iloc[[1]]]), two_voxels)


def test_unknown_root_type_raises(line_nodes, two_voxels):
    nodes = line_nodes.copy()
    nodes.loc[nodes.node_id.eq(1), "root_type"] = "unknown"
    with pytest.raises(ValueError, match="Unknown root types"):
        aggregate_root_grid(nodes, two_voxels)


@pytest.mark.parametrize(
    "column,value",
    [
        ("length", -1.0),
        ("length", float("nan")),
        ("diameter", -0.1),
        ("diameter", float("nan")),
        ("root_tissue_density", -0.1),
        ("root_tissue_density", float("nan")),
    ],
)
def test_invalid_segment_attributes_raise(line_nodes, two_voxels, column, value):
    nodes = line_nodes.copy()
    nodes.loc[nodes.node_id.eq(1), column] = value
    with pytest.raises(ValueError, match="geometry|Negative"):
        aggregate_root_grid(nodes, two_voxels, length_source="recorded")


def test_coincident_endpoints_positive_recorded_length_raises(line_nodes, two_voxels):
    nodes = line_nodes.copy()
    nodes.loc[nodes.node_id.eq(1), "x"] = 0.0
    with pytest.raises(ValueError, match="coincident endpoints"):
        aggregate_root_grid(nodes, two_voxels, length_source="recorded")


def test_scalar_density_and_voxel_sum_are_consistent(rsa_nodes, soil_grid):
    from deeprootgen.statistics.summary_statistics import RootLengthDensity

    calc = RootLengthDensity(soil_df=soil_grid)
    voxels, _ = aggregate_root_grid(rsa_nodes, soil_grid, length_source="geometric")
    assert calc.calculate(rsa_nodes) == pytest.approx(
        voxels.root_length_cm.sum() / voxels.soil_volume_cm3.sum()
    )
    mapped = calc.calculate_per_voxel(rsa_nodes)
    np.testing.assert_allclose(mapped.root_length_cm, voxels.root_length_cm)
