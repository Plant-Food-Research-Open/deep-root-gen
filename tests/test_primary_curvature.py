"""Invented public primary paths: numerical conservation, not biological fit."""

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from deeprootgen.research.primary_curvature import curve_primary_roots


def fixture(lengths=(3.0,), depth=40.0, descendants=False):
    rows = [
        dict(
            node_id=0,
            parent_id=-1,
            organ_id=0,
            order=0,
            segment_rank=0,
            x=0.0,
            y=0.0,
            z=-depth,
            length=0.0,
            diameter=0.0,
            root_tissue_density=0.05,
            root_type="structural",
            order_type="base",
            position_type="base",
            invalid_root=False,
        )
    ]
    x = 0.0
    for index, length in enumerate(lengths, 1):
        x += length
        rows.append(
            dict(
                rows[0],
                node_id=index,
                parent_id=index - 1,
                organ_id=1,
                order=1,
                segment_rank=index,
                x=x,
                length=length,
                diameter=0.4 - 0.03 * index,
                root_tissue_density=0.04 + 0.01 * index,
                order_type="primary",
                position_type="outer",
            )
        )
    if descendants:
        parent = 1
        for order in range(2, 6):
            nid = len(rows)
            source = rows[parent]
            rows.append(
                dict(
                    source,
                    node_id=nid,
                    parent_id=parent,
                    organ_id=order,
                    order=order,
                    segment_rank=1,
                    y=source["y"] + 1.0,
                    length=1.0,
                    diameter=0.1 / order,
                )
            )
            parent = nid
    nodes = pd.DataFrame(rows)
    edges = nodes.loc[nodes.order.gt(0), ["parent_id", "node_id"]].rename(
        columns={"node_id": "child_id"}
    )
    return nodes, edges.reset_index(drop=True)


def entry(**changes):
    return {1: dict(initial_inclination_deg=30.0, initial_azimuth_deg=25.0, **changes)}


def run(nodes, edges, entries=None, **changes):
    controls = dict(
        seed=71, max_step_cm=2.0, curvature_sd_rad_cm=0.2, correlation_length_cm=4.0
    )
    controls.update(changes)
    return curve_primary_roots(
        nodes, edges, entry() if entries is None else entries, **controls
    )


def actual_moments(nodes):
    lookup = nodes.set_index("node_id")
    result = {}
    for oid, chain in nodes.loc[nodes.order.gt(0)].groupby("organ_id"):
        lengths = np.linalg.norm(
            chain[["x", "y", "z"]].to_numpy()
            - lookup.loc[chain.parent_id, ["x", "y", "z"]].to_numpy(),
            axis=1,
        )
        d2 = chain.diameter.to_numpy() ** 2
        result[oid] = [
            sum(lengths),
            lengths @ d2,
            lengths @ (d2 * chain.root_tissue_density),
        ]
    return result


@pytest.mark.parametrize("length", [3.0, 20.0])
def test_explicit_zero_q_has_exact_initial_heading_and_conserved_material(length):
    nodes, edges = fixture((length,))
    result, output_edges, report = run(nodes, edges, curvature_sd_rad_cm=0.0)
    alpha, phi = np.radians([30.0, 25.0])
    expected = [
        np.cos(alpha) * np.cos(phi),
        np.cos(alpha) * np.sin(phi),
        -np.sin(alpha),
    ]
    for step in report["primaries"][0]["physical_steps"]:
        np.testing.assert_allclose(
            step["accepted_heading"], expected, rtol=0, atol=1e-15
        )
    np.testing.assert_allclose(
        actual_moments(result)[1], actual_moments(nodes)[1], rtol=1e-14
    )
    assert len(output_edges) == len(result) - 1
    assert nx.is_arborescence(
        nx.DiGraph(zip(output_edges.parent_id, output_edges.child_id))
    )


def test_curved_long_primary_is_tortuous_reproducible_and_inputs_unchanged():
    nodes, edges = fixture((20.0,))
    originals = (nodes.copy(deep=True), edges.copy(deep=True))
    first, second = run(nodes, edges), run(nodes, edges)
    pd.testing.assert_frame_equal(first[0], second[0], check_exact=True)
    pd.testing.assert_frame_equal(first[1], second[1], check_exact=True)
    assert first[2] == second[2]
    chord = np.linalg.norm(
        first[0].set_index("node_id").loc[1, ["x", "y", "z"]].to_numpy(float)
        - nodes.iloc[0][["x", "y", "z"]].to_numpy(float)
    )
    assert 20.0 / chord > 1.01
    assert not first[2]["primaries"][0]["physical_steps"][0]["integrated_turn_applied"]
    assert (
        first[2]["primaries"][0]["physical_steps"][0]["curvature_start_rad_cm"]
        != first[2]["primaries"][0]["physical_steps"][0]["curvature_end_rad_cm"]
    )
    for expected, actual in zip(originals, (nodes, edges)):
        pd.testing.assert_frame_equal(actual, expected, check_exact=True)


def test_collinear_graph_subdivision_keeps_physical_steps_endpoint_and_rng():
    coarse, coarse_edges = fixture((20.0,))
    split, split_edges = fixture((1.0, 3.0, 5.0, 11.0))
    # Same inherited material in both representations.
    split.loc[split.order.gt(0), "diameter"] = coarse.iloc[1].diameter
    split.loc[split.order.gt(0), "root_tissue_density"] = coarse.iloc[
        1
    ].root_tissue_density
    a, b = run(coarse, coarse_edges), run(split, split_edges)
    assert (
        a[2]["primaries"][0]["physical_steps"] == b[2]["primaries"][0]["physical_steps"]
    )
    np.testing.assert_array_equal(
        a[0].set_index("node_id").loc[1, ["x", "y", "z"]],
        b[0].set_index("node_id").loc[4, ["x", "y", "z"]],
    )
    np.testing.assert_allclose(
        actual_moments(a[0])[1], actual_moments(b[0])[1], rtol=1e-14
    )


def test_attachment_uses_incoming_local_tangent_and_descendants_rotate_conservatively_through_order5():
    nodes, edges = fixture((3.0, 17.0), descendants=True)
    result, _, report = run(nodes, edges)
    old, new = nodes.set_index("node_id"), result.set_index("node_id")
    attachment = report["attachments"][0]
    assert attachment["parent_node_id"] == 1
    assert attachment["attachment_arc_cm"] == 3.0
    rotation = np.asarray(attachment["rotation"])
    np.testing.assert_allclose(rotation.T @ rotation, np.eye(3), atol=1e-14)
    assert np.linalg.det(rotation) == pytest.approx(1.0, abs=1e-14)
    np.testing.assert_allclose(
        rotation @ [1.0, 0.0, 0.0], attachment["new_primary_tangent"], atol=1e-14
    )
    assert not report["descendant_boundary_interventions"]
    for row in nodes.loc[nodes.order.gt(1)].itertuples():
        before = old.loc[row.node_id, ["x", "y", "z"]].to_numpy(float) - old.loc[
            row.parent_id, ["x", "y", "z"]
        ].to_numpy(float)
        after = new.loc[row.node_id, ["x", "y", "z"]].to_numpy(float) - new.loc[
            row.parent_id, ["x", "y", "z"]
        ].to_numpy(float)
        np.testing.assert_allclose(after, rotation @ before, rtol=0, atol=1e-14)
    for oid, moments in actual_moments(nodes).items():
        np.testing.assert_allclose(actual_moments(result)[oid], moments, rtol=1e-13)


def test_surface_projects_first_chord_reports_mismatch_and_strict_option_fails():
    nodes, edges = fixture((3.0,), depth=0.0)
    entries = {1: dict(initial_inclination_deg=-45.0, initial_azimuth_deg=10.0)}
    result, _, report = run(nodes, edges, entries, curvature_sd_rad_cm=0.0)
    primary = report["primaries"][0]
    assert report["initial_angle_mismatch"] and primary["initial_angle_mismatch"]
    assert primary["requested_initial_inclination_deg"] == -45.0
    assert primary["realised_initial_inclination_deg"] == 0.0
    assert primary["root_boundary_interventions"] >= 1
    assert result.z.max() <= 0.0
    with pytest.raises(ValueError, match="strict initial-angle mismatch"):
        run(nodes, edges, entries, curvature_sd_rad_cm=0.0, strict_initial_angle=True)


def test_surface_repairs_rotated_lateral_edges_conservatively():
    nodes, edges = fixture((3.0,), depth=0.0, descendants=True)
    # A downward primary rotates an old negative-x daughter upward. Four
    # one-cm daughter edges rise from z=-3; order5 crosses the surface.
    nodes.loc[nodes.order.gt(1), "x"] = 3.0 - (
        nodes.loc[nodes.order.gt(1), "order"] - 1.0
    )
    nodes.loc[nodes.order.gt(1), "y"] = 0.0
    entries = {1: dict(initial_inclination_deg=90.0, initial_azimuth_deg=0.0)}
    result, _, report = run(nodes, edges, entries, curvature_sd_rad_cm=0.0)
    assert result.z.max() <= 0.0
    assert report["descendant_boundary_interventions"]
    assert report["descendant_boundary_interventions"][-1]["order"] == 5
    for oid, moments in actual_moments(nodes).items():
        np.testing.assert_allclose(actual_moments(result)[oid], moments, rtol=1e-13)


def test_inactive_curvature_is_exact_copy_without_changing_orientation():
    nodes, edges = fixture((3.0,))
    result, output_edges, report = curve_primary_roots(nodes, edges, entry(), seed=4)
    pd.testing.assert_frame_equal(result, nodes, check_exact=True)
    pd.testing.assert_frame_equal(output_edges, edges, check_exact=True)
    assert not report["active"]
    for controls in [dict(correlation_length_cm=2.0), dict(downward_drift_rad_cm=0.1)]:
        with pytest.raises(ValueError, match="Inactive"):
            curve_primary_roots(nodes, edges, entry(), seed=4, **controls)


@pytest.mark.parametrize("seed", [None, True, -1, 1.5, "7"])
def test_explicit_seed_required(seed):
    nodes, edges = fixture()
    with pytest.raises(ValueError, match="seed"):
        run(nodes, edges, seed=seed)


def test_entry_fields_and_controls_fail_closed_and_category_is_metadata_only():
    nodes, edges = fixture((20.0,))
    with pytest.raises(ValueError, match="initial-tangent"):
        run(nodes, edges, {1: dict(inclination_deg=30.0, azimuth_deg=25.0)})
    a, b = run(nodes, edges), run(
        nodes, edges, entry(category="invented", primary_id="metadata")
    )
    pd.testing.assert_frame_equal(a[0], b[0], check_exact=True)
    assert (
        a[2]["primaries"][0]["physical_steps"] == b[2]["primaries"][0]["physical_steps"]
    )
    explicit_list = [
        dict(organ_id=1, initial_inclination_deg=30.0, initial_azimuth_deg=25.0)
    ]
    pd.testing.assert_frame_equal(a[0], run(nodes, edges, explicit_list)[0])
    for bad in [
        dict(curvature_sd_rad_cm=True),
        dict(correlation_length_cm=0.0),
        dict(max_step_cm=True),
        dict(downward_drift_rad_cm=-1.0),
    ]:
        with pytest.raises(ValueError):
            run(nodes, edges, **bad)


def test_per_entry_controls_and_seed_separate_streams():
    nodes, edges = fixture((20.0,))
    entries = entry(curvature_sd_rad_cm=0.0, correlation_length_cm=3.0)
    zero = run(nodes, edges, entries)[0]
    other_zero = run(nodes, edges, entries, seed=222)[0]
    pd.testing.assert_frame_equal(zero, other_zero, check_exact=True)
    assert not run(nodes, edges)[0].equals(run(nodes, edges, seed=222)[0])


def test_original_material_breaks_node_arcs_and_child_attachment_ids_survive():
    nodes, edges = fixture((3.0, 17.0), descendants=True)
    result, output_edges, _ = run(nodes, edges)
    chain = result.loc[result.order.eq(1)].sort_values("segment_rank")
    cumulative = chain.length.cumsum()
    assert cumulative.loc[chain.node_id.eq(1)].iloc[0] == pytest.approx(3.0, abs=1e-14)
    assert cumulative.loc[chain.node_id.eq(2)].iloc[0] == pytest.approx(20.0, abs=1e-14)
    proximal = chain.loc[cumulative <= 3.0]
    distal = chain.loc[cumulative > 3.0]
    assert proximal.diameter.eq(nodes.iloc[1].diameter).all()
    assert distal.diameter.eq(nodes.iloc[2].diameter).all()
    assert proximal.root_tissue_density.eq(nodes.iloc[1].root_tissue_density).all()
    assert distal.root_tissue_density.eq(nodes.iloc[2].root_tissue_density).all()
    first_daughter = nodes.loc[nodes.order.eq(2)].iloc[0]
    assert result.set_index("node_id").loc[first_daughter.node_id, "parent_id"] == 1
    graph = nx.DiGraph(zip(output_edges.parent_id, output_edges.child_id))
    new_ids = set(result.node_id) - set(nodes.node_id)
    assert all(graph.in_degree(nid) == graph.out_degree(nid) == 1 for nid in new_ids)


@pytest.mark.parametrize(
    "change", ["cycle", "stored_length", "nan", "material_overflow", "nonbool_invalid"]
)
def test_malformed_graph_and_nonfinite_derived_moments_fail_closed(change):
    nodes, edges = fixture((3.0,))
    if change == "cycle":
        nodes.loc[1, "parent_id"] = 1
        edges.loc[0, "parent_id"] = 1
    elif change == "stored_length":
        nodes.loc[1, "length"] += 0.01
    elif change == "nan":
        nodes.loc[1, "x"] = np.nan
    elif change == "material_overflow":
        nodes.loc[1, "diameter"] = 1e200
    else:
        nodes["invalid_root"] = "false"
    with np.errstate(over="ignore", invalid="ignore"), pytest.raises(ValueError):
        run(nodes, edges)


def test_downward_drift_with_zero_diffusion_is_explicit_deterministic_bend():
    nodes, edges = fixture((20.0,))
    result, _, report = run(
        nodes,
        edges,
        {1: dict(initial_inclination_deg=0.0, initial_azimuth_deg=0.0)},
        curvature_sd_rad_cm=0.0,
        downward_drift_rad_cm=0.03,
    )
    steps = report["primaries"][0]["physical_steps"]
    np.testing.assert_array_equal(steps[0]["accepted_heading"], [1.0, 0.0, 0.0])
    assert steps[-1]["accepted_heading"][2] < -0.3
    assert result.z.min() < nodes.z.min()


@pytest.mark.parametrize("near_surface", [False, True])
def test_batched_descendant_path_matches_unchanged_sequential_fallback(monkeypatch, near_surface):
    from deeprootgen.research import primary_curvature as module

    nodes, edges = fixture((3.0, 17.0), depth=0. if near_surface else 40., descendants=True)
    entries = {1: dict(initial_inclination_deg=0., initial_azimuth_deg=0.)} if near_surface else entry()
    controls = dict(curvature_sd_rad_cm=0.) if near_surface else {}
    batched = run(nodes, edges, entries, **controls)
    monkeypatch.setattr(module, "_try_unprojected_subtree", lambda *args: False)
    sequential = run(nodes, edges, entries, **controls)
    np.testing.assert_allclose(batched[0][["x", "y", "z"]], sequential[0][["x", "y", "z"]], rtol=0., atol=1e-14)
    pd.testing.assert_frame_equal(batched[0].drop(columns=["x", "y", "z"]), sequential[0].drop(columns=["x", "y", "z"]), check_exact=True)
    pd.testing.assert_frame_equal(batched[1], sequential[1], check_exact=True)
    for key in ("primaries", "attachments", "descendant_boundary_interventions"):
        assert batched[2][key] == sequential[2][key]


def test_exact_surface_and_ulp_near_surface_defer_to_sequential_boundary(monkeypatch):
    from deeprootgen.research import primary_curvature as module

    original = module._try_unprojected_subtree
    selected = []

    def record(*args):
        accepted = original(*args)
        selected.append(accepted)
        return accepted
    monkeypatch.setattr(module, "_try_unprojected_subtree", record)
    for depth in (0., np.finfo(float).eps, 1e-14):
        nodes, edges = fixture((3.,), depth=depth, descendants=True)
        run(nodes, edges, {1: dict(initial_inclination_deg=0., initial_azimuth_deg=0.)}, curvature_sd_rad_cm=0.)
    assert selected == [False, False, False]


def test_batched_route_retains_degenerate_descendant_direction_rejection():
    nodes, edges = fixture((3.,), descendants=True)
    nodes.loc[nodes.order.gt(1), "y"] *= 1e-13
    nodes.loc[nodes.order.gt(1), "length"] = 1e-13
    with pytest.raises(ValueError, match="Degenerate direction"):
        run(nodes, edges)
