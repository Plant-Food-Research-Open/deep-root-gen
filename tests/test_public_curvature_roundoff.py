"""Invented trailing-edge metadata reconciliation; no data or native simulation."""

import numpy as np
import pandas as pd
import pytest

from deeprootgen.research import primary_curvature as curve
from deeprootgen.research.native_roundoff import reconcile_native_edge_lengths


def fixture(
    tiny=1e-6, *, trailing=True, whole_organ=False, y_origin=0.0, ideal_metadata=False
):
    rows = [
        dict(
            node_id=0,
            parent_id=-1,
            organ_id=0,
            order=0,
            segment_rank=0,
            x=100.0,
            y=float(y_origin),
            z=-100.0,
            length=0.0,
            diameter=0.0,
            root_tissue_density=0.1,
            root_type="base",
            invalid_root=False,
        ),
        dict(
            node_id=1,
            parent_id=0,
            organ_id=1,
            order=1,
            segment_rank=1,
            x=110.0,
            y=float(y_origin),
            z=-100.0,
            length=10.0,
            diameter=0.4,
            root_tissue_density=0.1,
            root_type="structural",
            invalid_root=False,
        ),
    ]
    segments = [tiny] if whole_organ else [1.0, tiny] if trailing else [tiny, 1.0]
    parent, y = 1, float(y_origin)
    for rank, segment in enumerate(segments, 1):
        nid = len(rows)
        next_y = y + segment
        rows.append(
            dict(
                rows[1],
                node_id=nid,
                parent_id=parent,
                organ_id=2,
                order=2,
                segment_rank=rank,
                y=next_y,
                length=float(segment if ideal_metadata else abs(next_y - y)),
                diameter=0.2,
            )
        )
        parent, y = nid, next_y
    nodes = pd.DataFrame(rows)
    edges = (
        nodes.loc[nodes.order.gt(0), ["parent_id", "node_id"]]
        .rename(columns={"node_id": "child_id"})
        .reset_index(drop=True)
    )
    return nodes, edges


def apply(nodes, edges, **changes):
    kwargs = dict(
        seed=71,
        surface_z_cm=0.0,
        max_step_cm=2.0,
        curvature_sd_rad_cm=0.0,
        correlation_length_cm=3.0,
        strict_initial_angle=True,
    )
    kwargs.update(changes)
    return curve.curve_primary_roots(
        nodes,
        edges,
        {1: dict(initial_inclination_deg=0.0, initial_azimuth_deg=90.0)},
        **kwargs
    )


def test_rotated_tiny_trailing_segment_default_rejects_and_explicit_recovery_passes():
    nodes, edges = fixture()
    snapshots = (nodes.copy(deep=True), edges.copy(deep=True))
    curve._audit(nodes, edges)  # Input already passes the original strict audit.
    with pytest.raises(ValueError, match="edge lengths"):
        apply(nodes, edges)
    output, output_edges, report = apply(nodes, edges, reconcile_length_roundoff=True)
    stages = report["length_roundoff_reconciliation"]
    assert stages["input"]["changed_node_ids"] == []
    assert stages["output"]["changed_node_ids"] == [3]
    assert stages["output"]["existing_strict_graph_validator_passed"]
    record = stages["output"]["changes"][0]
    assert record["absolute_error_cm"] <= record["absolute_guard_cm"]
    assert record["relative_error"] <= record["relative_guard"]
    curve._audit(output, output_edges)
    assert report["conservation"]["relative_tolerance"] == 1e-9
    assert report["conservation"]["original_node_arc_identity_preserved"]
    # The long first segment makes the original whole-organ and retained-node
    # prefix-arc checks meaningful despite a short trailing metadata adjustment.
    old_length = nodes.loc[nodes.order.eq(2), "length"].sum()
    new_length = output.loc[output.order.eq(2), "length"].sum()
    assert np.isclose(old_length, new_length, rtol=1e-9, atol=0.0)
    for actual, expected in zip((nodes, edges), snapshots):
        pd.testing.assert_frame_equal(actual, expected, check_exact=True)


def test_input_and_output_reconciliation_are_separate_and_metadata_only():
    nodes, edges = fixture(y_origin=99.0, ideal_metadata=True)
    with pytest.raises(ValueError, match="edge lengths"):
        curve._audit(nodes, edges)
    output, output_edges, report = apply(nodes, edges, reconcile_length_roundoff=True)
    stages = report["length_roundoff_reconciliation"]
    assert stages["input"]["changed_node_ids"] == [3]
    assert stages["input"]["geometry_changed"] is False
    assert stages["output"]["geometry_changed"] is False
    curve._audit(output, output_edges)


def test_admitted_whole_organ_correction_still_fails_original_moment_conservation(
    monkeypatch,
):
    nodes, edges = fixture(whole_organ=True)
    curve._audit(nodes, edges)
    calls = []
    from deeprootgen.research import native_roundoff

    original = native_roundoff.reconcile_native_edge_lengths

    def observed(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result[2])
        return result

    monkeypatch.setattr(native_roundoff, "reconcile_native_edge_lengths", observed)
    with pytest.raises(ValueError, match="length/d²L/mass conservation"):
        apply(nodes, edges, reconcile_length_roundoff=True)
    assert calls[-1]["changed_node_ids"] == [2]
    assert calls[-1]["existing_strict_graph_validator_passed"]


def test_admitted_early_arc_correction_still_fails_original_retained_node_arc_check():
    nodes, edges = fixture(trailing=False)
    curve._audit(nodes, edges)
    with pytest.raises(ValueError, match="Original node arc identity changed"):
        apply(nodes, edges, reconcile_length_roundoff=True)


def test_default_and_explicit_false_keep_exact_ordinary_outputs_and_diagnostics():
    nodes, edges = fixture(tiny=0.5)
    omitted = apply(nodes, edges)
    explicit = apply(nodes, edges, reconcile_length_roundoff=False)
    pd.testing.assert_frame_equal(omitted[0], explicit[0], check_exact=True)
    pd.testing.assert_frame_equal(omitted[1], explicit[1], check_exact=True)
    assert omitted[2] == explicit[2]
    assert "length_roundoff_reconciliation" not in omitted[2]
    opted = apply(nodes, edges, reconcile_length_roundoff=True)
    pd.testing.assert_frame_equal(omitted[0], opted[0], check_exact=True)
    pd.testing.assert_frame_equal(omitted[1], opted[1], check_exact=True)
    assert (
        opted[2]["length_roundoff_reconciliation"]["input"]["changed_edge_count"] == 0
    )
    assert (
        opted[2]["length_roundoff_reconciliation"]["output"]["changed_edge_count"] == 0
    )


@pytest.mark.parametrize("flag", [None, 0, 1, "true", [], {}])
def test_opt_in_requires_a_strict_boolean(flag):
    nodes, edges = fixture(tiny=0.5)
    with pytest.raises(ValueError, match="strict boolean"):
        apply(nodes, edges, reconcile_length_roundoff=flag)


def test_true_geometric_input_defect_still_rejects_without_repair():
    nodes, edges = fixture(tiny=0.5)
    nodes.loc[nodes.node_id.eq(2), "length"] = 0.9
    snapshot = nodes.copy(deep=True)
    with pytest.raises(ValueError, match="roundoff agreement guard"):
        apply(nodes, edges, reconcile_length_roundoff=True)
    pd.testing.assert_frame_equal(nodes, snapshot, check_exact=True)


def test_true_output_defect_still_rejects_with_no_coordinate_repair(monkeypatch):
    nodes, edges = fixture(tiny=0.5)
    original = curve._reattach_daughters

    def broken(*args, **kwargs):
        original(*args, **kwargs)
        working = args[5]
        working.loc[3, "x"] += 0.1

    monkeypatch.setattr(curve, "_reattach_daughters", broken)
    with pytest.raises(ValueError, match="roundoff agreement guard"):
        apply(nodes, edges, reconcile_length_roundoff=True)


def test_explicit_reconciliation_with_inactive_curvature_logs_both_stages():
    nodes, edges = fixture(y_origin=99.0, ideal_metadata=True)
    expected, expected_edges, _ = reconcile_native_edge_lengths(nodes, edges)
    result, result_edges, report = apply(
        nodes,
        edges,
        curvature_sd_rad_cm=None,
        correlation_length_cm=None,
        reconcile_length_roundoff=True,
    )
    pd.testing.assert_frame_equal(result, expected, check_exact=True)
    pd.testing.assert_frame_equal(result_edges, expected_edges, check_exact=True)
    assert report["active"] is False
    assert report["length_roundoff_reconciliation"]["input"]["changed_node_ids"] == [3]
    assert report["length_roundoff_reconciliation"]["output"]["changed_node_ids"] == []
