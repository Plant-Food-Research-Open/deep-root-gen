"""Invented binary64 endpoint metadata only; no observations or simulations."""

import numpy as np
import pandas as pd
import pytest

from deeprootgen.research.native_roundoff import (
    EPS,
    RELATIVE_CAP,
    reconcile_native_edge_lengths,
)
from deeprootgen.research.primary_curvature import _audit


def graph(offset=100.0, ideal=1e-6, mixed=False):
    rows = [
        dict(
            node_id=0,
            parent_id=-1,
            organ_id=0,
            order=0,
            segment_rank=0,
            x=float(offset),
            y=0.0,
            z=0.0,
            length=0.0,
            diameter=0.0,
            root_tissue_density=0.0,
            root_type="base",
            invalid_root=False,
            plant_id=1,
        ),
        dict(
            node_id=1,
            parent_id=0,
            organ_id=1,
            order=1,
            segment_rank=1,
            x=float(offset + ideal),
            y=0.0,
            z=0.0,
            length=float(ideal),
            diameter=0.4,
            root_tissue_density=0.2,
            root_type="structural",
            invalid_root=False,
            plant_id=1,
        ),
    ]
    if mixed:
        rows.extend(
            [
                dict(
                    rows[1],
                    node_id=2,
                    parent_id=1,
                    organ_id=2,
                    order=2,
                    segment_rank=1,
                    x=float(offset + ideal + 1.0),
                    length=1.0,
                    diameter=0.2,
                    root_tissue_density=0.1,
                ),
                dict(
                    rows[1],
                    node_id=3,
                    parent_id=2,
                    organ_id=2,
                    order=2,
                    segment_rank=2,
                    x=float(offset + ideal + 2.0),
                    length=1.0 + 5e-10,
                    diameter=0.1,
                    root_tissue_density=0.05,
                ),
            ]
        )
    nodes = pd.DataFrame(rows)
    edges = (
        nodes.loc[nodes.order.gt(0), ["parent_id", "node_id"]]
        .rename(columns={"node_id": "child_id"})
        .reset_index(drop=True)
    )
    return nodes, edges


def test_translated_positive_tiny_edge_passes_both_guards_and_original_validator_afterward():
    nodes, edges = graph()
    before = nodes.copy(deep=True)
    with pytest.raises(ValueError, match="edge lengths"):
        _audit(nodes, edges)
    output, output_edges, report = reconcile_native_edge_lengths(nodes, edges)
    actual = float(
        np.linalg.norm(
            nodes.loc[1, ["x", "y", "z"]].to_numpy(float)
            - nodes.loc[0, ["x", "y", "z"]].to_numpy(float)
        )
    )
    assert output.loc[1, "length"] == actual
    assert not np.isclose(actual, nodes.loc[1, "length"], rtol=1e-9, atol=0.0)
    change = report["changes"][0]
    assert change["absolute_error_cm"] <= change["absolute_guard_cm"]
    assert 1e-9 < change["relative_error"] <= RELATIVE_CAP
    assert report["changed_node_ids"] == [1]
    assert report["existing_strict_graph_validator_passed"]
    assert report["strict_test"] == dict(rtol=1e-9, atol=0.0)
    _audit(output, output_edges)
    pd.testing.assert_frame_equal(nodes, before, check_exact=True)
    pd.testing.assert_frame_equal(
        output.drop(columns="length"), nodes.drop(columns="length"), check_exact=True
    )
    pd.testing.assert_frame_equal(output_edges, edges, check_exact=True)


def test_passing_nonexact_rows_indices_attributes_and_all_other_bits_remain_unchanged():
    nodes, edges = graph(mixed=True)
    nodes.index = [8, 8, 4, 3]  # duplicate row labels must not target two rows
    nodes.attrs["invented"] = {"metadata": ["preserve"]}
    edges.attrs["invented"] = "edges"
    output, output_edges, report = reconcile_native_edge_lengths(nodes, edges)
    assert output.length.iloc[3] == nodes.length.iloc[3]
    assert output.length.iloc[3] != np.linalg.norm(
        output.iloc[3][["x", "y", "z"]].to_numpy(float)
        - output.iloc[2][["x", "y", "z"]].to_numpy(float)
    )
    assert output.length.iloc[0] == nodes.length.iloc[0]
    np.testing.assert_array_equal(
        output.length.iloc[2:].to_numpy().view(np.uint64),
        nodes.length.iloc[2:].to_numpy().view(np.uint64),
    )
    pd.testing.assert_frame_equal(
        output.drop(columns="length"), nodes.drop(columns="length"), check_exact=True
    )
    pd.testing.assert_frame_equal(output_edges, edges, check_exact=True)
    assert output.attrs == nodes.attrs and output_edges.attrs == edges.attrs
    assert output.dtypes.equals(nodes.dtypes)
    assert report["changed_edge_count"] == 1


def test_per_order_stored_length_cylinder_and_mass_delta_accounting_is_explicit():
    nodes, edges = graph(mixed=True)
    output, _, report = reconcile_native_edge_lengths(nodes, edges)
    delta = output.length.iloc[1] - nodes.length.iloc[1]
    factors = dict(
        length_cm=1.0,
        diameter2_length_cm3=0.4**2,
        density_diameter2_length_g=0.2 * 0.4**2,
        cylinder_volume_cm3=np.pi / 4 * 0.4**2,
        dry_mass_g=np.pi / 4 * 0.2 * 0.4**2,
    )
    for name, factor in factors.items():
        metric = report["per_order"][1]["moments"][name]
        assert metric["delta"] == pytest.approx(delta * factor, rel=2e-7, abs=0.0)
        assert metric["relative_delta"] == pytest.approx(
            delta / nodes.length.iloc[1], rel=2e-7, abs=0.0
        )
        assert report["per_order"][2]["moments"][name]["delta"] == 0.0
        assert report["geometric_moment_deltas"][name] == 0.0
    assert report["reported_moment_basis"] == "stored_length_metadata_before_and_after"
    assert report["material_attributes_changed"] is False


def test_no_change_exact_parity_including_passing_nonexact_stored_metadata():
    nodes, edges = graph(offset=0.0, ideal=1.0)
    nodes.loc[1, "length"] = 1.0 + 5e-10
    nodes.attrs["tag"] = "invented exact copy"
    left, right, report = reconcile_native_edge_lengths(nodes, edges)
    pd.testing.assert_frame_equal(left, nodes, check_exact=True)
    pd.testing.assert_frame_equal(right, edges, check_exact=True)
    assert left is not nodes and right is not edges
    assert report["changed_node_ids"] == []
    assert report["changed_edge_count"] == 0
    assert all(metric["delta"] == 0.0 for metric in report["totals"].values())


def test_far_offset_tiny_edge_inside_absolute_guard_but_above_relative_cap_rejected():
    nodes, edges = graph(offset=1e10, ideal=1e-6)
    actual = nodes.x.iloc[1] - nodes.x.iloc[0]
    error = abs(actual - nodes.length.iloc[1])
    absolute_guard = (
        64 * EPS * (abs(nodes.x.iloc[0]) + abs(nodes.x.iloc[1]) + nodes.length.iloc[1])
    )
    assert error <= absolute_guard
    assert error / min(actual, nodes.length.iloc[1]) > RELATIVE_CAP
    with pytest.raises(ValueError, match="roundoff agreement guard"):
        reconcile_native_edge_lengths(nodes, edges)


def test_honest_geometric_defect_and_absolute_guard_miss_fail_closed():
    for offset, ideal, stored in [(0.0, 1.0, 0.9), (1e5, 1.0, 1.0 + 4e-9)]:
        nodes, edges = graph(offset, ideal)
        nodes.loc[1, "length"] = stored
        snapshot = nodes.copy(deep=True)
        with pytest.raises(ValueError, match="roundoff agreement guard"):
            reconcile_native_edge_lengths(nodes, edges)
        pd.testing.assert_frame_equal(nodes, snapshot, check_exact=True)


@pytest.mark.parametrize(
    "defect",
    [
        "zero_geometry",
        "zero_stored",
        "negative_stored",
        "negative_diameter",
        "negative_density",
        "nan_coordinate",
        "infinite_length",
        "bool_coordinate",
        "string_length",
        "duplicate_node",
        "duplicate_edge",
        "edge_parent_mismatch",
        "missing_parent",
        "base_parent",
        "cycle",
        "order_jump",
        "organ_chain",
        "invalid_flag",
        "noninteger_node",
        "noninteger_edge",
        "duplicate_column",
        "missing_column",
        "cross_plant",
        "nonfinite_moment",
    ],
)
def test_invalid_native_tables_reject_without_mutating_inputs(defect):
    nodes, edges = graph(offset=0.0, ideal=1.0)
    cell_changes = {
        "zero_geometry": (1, "x", 0.0),
        "zero_stored": (1, "length", 0.0),
        "negative_stored": (1, "length", -1.0),
        "negative_diameter": (1, "diameter", -0.2),
        "negative_density": (1, "root_tissue_density", -0.1),
        "nan_coordinate": (1, "x", np.nan),
        "infinite_length": (1, "length", np.inf),
        "duplicate_node": (1, "node_id", 0),
        "base_parent": (0, "parent_id", 999),
        "order_jump": (1, "order", 2),
        "organ_chain": (1, "organ_id", 0),
        "cross_plant": (1, "plant_id", 2),
        "nonfinite_moment": (1, "diameter", 1e200),
    }
    if defect in cell_changes:
        row, column, value = cell_changes[defect]
        nodes.loc[row, column] = value
    elif defect == "bool_coordinate":
        nodes["x"] = True
    elif defect == "string_length":
        nodes["length"] = ["0", "1"]
    elif defect == "duplicate_edge":
        edges = pd.concat([edges, edges], ignore_index=True)
    elif defect == "edge_parent_mismatch":
        edges.loc[0, "parent_id"] = 1
    elif defect == "missing_parent":
        nodes.loc[1, "parent_id"] = 99
        edges.loc[0, "parent_id"] = 99
    elif defect == "cycle":
        nodes.loc[1, "parent_id"] = 1
        edges.loc[0, "parent_id"] = 1
    elif defect == "invalid_flag":
        nodes["invalid_root"] = "False"
    elif defect == "noninteger_node":
        nodes["node_id"] = nodes.node_id.astype(float)
    elif defect == "noninteger_edge":
        edges["child_id"] = edges.child_id.astype(float)
    elif defect == "duplicate_column":
        nodes = pd.concat([nodes, nodes[["length"]]], axis=1)
    elif defect == "missing_column":
        nodes = nodes.drop(columns="diameter")
    snapshots = (nodes.copy(deep=True), edges.copy(deep=True))
    with np.errstate(over="ignore", invalid="ignore"), pytest.raises(ValueError):
        reconcile_native_edge_lengths(nodes, edges)
    for table, snapshot in zip((nodes, edges), snapshots):
        pd.testing.assert_frame_equal(table, snapshot, check_exact=True)


def test_correction_never_promotes_or_rounds_a_nonbinary64_length_column():
    nodes, edges = graph(offset=20.0, ideal=1e-6)
    nodes["length"] = nodes.length.astype(np.float32)
    with pytest.raises(ValueError, match="binary64 dtype"):
        reconcile_native_edge_lengths(nodes, edges)


def test_changed_ids_preserve_large_integer_identity_without_series_float_coercion():
    nodes, edges = graph()
    nodes = nodes.drop(columns=["root_type"])
    large = 2**53 + 7
    nodes.loc[1, "node_id"] = large
    edges.loc[0, "child_id"] = large
    _, _, report = reconcile_native_edge_lengths(nodes, edges)
    assert report["changed_node_ids"] == [large]
