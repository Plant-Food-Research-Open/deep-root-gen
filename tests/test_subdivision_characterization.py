"""Characterize legacy subdivision coupling; this test does not repair the model."""

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from deeprootgen.data_model import RootSimulationModel, RootTypeModel
from deeprootgen.model.hgraph import RootSystemGraph
from deeprootgen.model.root import RootOrgan


def parameters():
    values = json.loads((Path(__file__).parents[1] / "tests/fixtures/migration_inputs/synthetic_minimal.json").read_text())
    values.update(random_seed=42, max_order=4, segments_per_root=10,
                  min_sec_root_num=2, max_sec_root_num=3, growth_sec_root=0.,
                  min_sec_root_length=10., max_sec_root_length=12.,
                  length_reduction=.5, interbranch_distance=.75,
                  floor_threshold=.1, ceiling_threshold=.9,
                  research_branch_placement="legacy_spacing", root_vary=15.)
    return RootSimulationModel(**values)


def construct_refined_fixture(fine):
    """Build actual orders 1–4 around one fixed bent order-2 parent curve."""
    p = parameters()
    graph = RootSystemGraph()
    root_type = RootTypeModel(root_type="structural", order_type="primary", position_type="outer")
    primary = RootOrgan(graph.base_node, p, root_type, "invented-subdivision", np.random.default_rng(0))
    primary._construct_segment_nodes(np.array([.3]), np.array([2.]),
                                     np.array([[0., 0., -2.]]), root_type, .05, [0])
    parent = primary.add_child_organ()
    if fine:
        parent_lengths = np.array([4., 1., 5.])
        parent_coordinates = np.array([[4., 0., -2.], [5., 0., -2.], [5., 0., -7.]])
        attachment_index = 1
    else:
        parent_lengths = np.array([5., 5.])
        parent_coordinates = np.array([[5., 0., -2.], [5., 0., -7.]])
        attachment_index = 0
    parent_type = RootTypeModel(root_type="structural", order_type="secondary", position_type="outer")
    parent._construct_segment_nodes(np.full(len(parent_lengths), .2), parent_lengths,
                                    parent_coordinates, parent_type, .05, [attachment_index])
    daughter = parent.add_child_organ()
    daughter.rng = np.random.default_rng(42)
    state_before = copy.deepcopy(daughter.rng.bit_generator.state)
    nominal, before_subdivision = [], []
    original_lengths = daughter.init_lengths
    original_prepare = daughter._prepare_branch_nodes

    def record_nominal(*args):
        result = original_lengths(*args)
        nominal.append(result.copy())
        return result

    def record_prepare(diameters, lengths, coordinates):
        before_subdivision.append(lengths.copy())
        return original_prepare(diameters, lengths, coordinates)

    # Wrappers observe actual methods and delegate without adding RNG draws.
    daughter.init_lengths = record_nominal
    daughter._prepare_branch_nodes = record_prepare
    daughter.construct_root_from_parent(10, p.apex_diameter)
    daughter.update_transform(translation=daughter.get_parent_origin())
    daughter.transform()
    insertion_count = len(daughter.lateral_attachment_nodes)
    while daughter.lateral_attachment_nodes:
        grandchild = daughter.add_child_organ()
        grandchild.construct_root_from_parent(10, p.apex_diameter)
        grandchild.update_transform(translation=grandchild.get_parent_origin())
        grandchild.transform()
    nodes, edges = graph.as_df()
    return dict(parent=parent, daughter=daughter, nodes=nodes, edges=edges,
                state_before=state_before, nominal=nominal[0],
                before_subdivision=before_subdivision[0], insertion_count=insertion_count,
                attachment_arc_cm=float(parent_lengths[:attachment_index + 1].sum()))


def assert_connected_geometric_tree(nodes, edges):
    assert nodes.node_id.is_unique
    ids = set(nodes.node_id)
    assert set(edges.parent_id) <= ids and set(edges.child_id) <= ids
    assert len(edges) == len(nodes) - 1
    assert set(edges.child_id) == set(nodes.loc[nodes.order.gt(0), "node_id"])
    assert np.isfinite(nodes[["x", "y", "z", "length", "diameter"]].to_numpy(float)).all()
    assert (nodes[["length", "diameter"]] >= 0).all().all()
    by_id = nodes.set_index("node_id")
    geometric_lengths = []
    for row in nodes.loc[nodes.order.gt(0)].itertuples():
        parent = by_id.loc[row.parent_id, ["x", "y", "z"]].to_numpy(float)
        length = np.linalg.norm(np.array([row.x, row.y, row.z]) - parent)
        assert length == pytest.approx(row.length, rel=1e-5, abs=1e-6)
        geometric_lengths.append(length)
        visited, node = set(), row.node_id
        while node != 0:
            assert node not in visited
            visited.add(node)
            node = int(by_id.loc[node, "parent_id"])
    assert sum(geometric_lengths) == pytest.approx(nodes.length.sum(), rel=0, abs=1e-8)


def test_legacy_order3_daughter_length_depends_on_incoming_parent_subdivision():
    coarse, fine = construct_refined_fixture(False), construct_refined_fixture(True)
    assert coarse["state_before"] == fine["state_before"]
    np.testing.assert_array_equal(coarse["nominal"], fine["nominal"])
    for fixture, incoming_length in ((coarse, 5.), (fine, 1.)):
        parent, daughter = fixture["parent"], fixture["daughter"]
        anchor = daughter.parent_node.node_data
        assert parent.get_lengths().sum() == pytest.approx(10., rel=0, abs=1e-8)
        assert fixture["attachment_arc_cm"] == 5.
        assert (anchor.x, anchor.y, anchor.z) == (5., 0., -2.)
        assert (anchor.order, anchor.diameter, anchor.root_tissue_density) == (2, .2, .05)
        assert anchor.length == incoming_length
        assert {node.node_data.order for node in daughter.segments} == {3}
        assert len(fixture["nominal"]) == 10
        np.testing.assert_allclose(fixture["before_subdivision"] - fixture["nominal"],
                                   np.full(10, incoming_length * .1**2), rtol=0, atol=1e-12)
        assert daughter.get_lengths().sum() == pytest.approx(
            fixture["nominal"].sum() + 10 * incoming_length * .1**2, rel=0, abs=1e-8)
        assert len(daughter.child_organs) == fixture["insertion_count"]
        assert fixture["nodes"].loc[fixture["nodes"].order.eq(4), "organ_id"].nunique() == fixture["insertion_count"]
        assert_connected_geometric_tree(fixture["nodes"], fixture["edges"])
    coarse_length = float(coarse["daughter"].get_lengths().sum())
    fine_length = float(fine["daughter"].get_lengths().sum())
    assert coarse_length - fine_length == pytest.approx(10 * (5 - 1) * .1**2, rel=0, abs=1e-8)
    # Branch count is measured rather than presumed to differ. Both fixtures
    # actually instantiate all order-4 daughters from the order-3 insertion list.
    print(json.dumps(dict(
        kind="invented_synthetic_legacy_characterization", nominal_order3_length_cm=float(coarse["nominal"].sum()),
        coarse_order3_length_cm=coarse_length, fine_order3_length_cm=fine_length,
        order3_length_difference_cm=coarse_length - fine_length,
        coarse_order3_branch_count=coarse["insertion_count"], fine_order3_branch_count=fine["insertion_count"],
        order3_branch_count_difference=coarse["insertion_count"] - fine["insertion_count"],
        coarse_order3_subsegments=len(coarse["daughter"].segments),
        fine_order3_subsegments=len(fine["daughter"].segments),
    ), sort_keys=True))
