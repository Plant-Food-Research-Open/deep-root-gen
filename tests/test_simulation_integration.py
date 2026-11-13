"""Opt-in, reproducible simulator checks; no database/network services needed.

Run: poetry run pytest tests --run-integration -m integration -q
"""

from __future__ import annotations

import networkx as nx
import numpy as np
import pytest

from deeprootgen.data_model import RootSimulationModel
from deeprootgen.model import RootSystemSimulation
from deeprootgen.statistics.summary_statistics import RootNumber, TotalLength
from deeprootgen.statistics.root_grid_aggregation import aggregate_root_grid


@pytest.fixture
def simulation_parameters():
    return dict(
        max_order=2,
        root_ratio=0.5,
        fine_root_threshold=0.15,
        outer_root_num=2,
        inner_root_num=1,
        min_primary_length=15.0,
        max_primary_length=20.0,
        base_diameter=0.5,
        diameter_reduction=0.2,
        apex_diameter=0.05,
        min_sec_root_num=3,
        max_sec_root_num=4,
        growth_sec_root=0.1,
        min_sec_root_length=3.0,
        max_sec_root_length=8.0,
        segments_per_root=5,
        length_reduction=0.7,
        root_vary=5.0,
        interbranch_distance=2.0,
        mechanical_constraints=0.0,
        root_tissue_density=0.15,
        gravitropism=0.1,
        t=1,
        enable_soil=False,
        soil_layer_height=10.0,
        soil_n_layers=10,
        soil_layer_width=10.0,
        soil_n_cols=10,
    )


def _run(params, seed):
    model = RootSimulationModel(random_seed=seed, **params)
    sim = RootSystemSimulation(random_seed=seed)
    sim.run(model)
    return sim.G.as_df()


@pytest.mark.integration
def test_simulation_exports_parent_child_tree(simulation_parameters):
    nodes, edges = _run(simulation_parameters, 42)
    assert not nodes.empty
    assert not edges.empty
    assert nodes.node_id.is_unique
    ids = set(nodes.node_id)
    assert set(edges.parent_id) <= ids
    assert set(edges.child_id) <= ids
    g = nx.DiGraph(edges[["parent_id", "child_id"]].itertuples(index=False, name=None))
    g.add_nodes_from(ids)
    assert nx.is_arborescence(g)
    assert len(edges) == len(nodes) - 1
    indexed = nodes.set_index("node_id")
    for row in nodes.itertuples(index=False):
        if row.parent_id not in indexed.index:
            assert row.order == 0
            continue
        parent = indexed.loc[row.parent_id]
        if row.segment_rank == 1:
            assert row.order == parent.order + 1
            assert row.organ_id != parent.organ_id
        else:
            assert row.order == parent.order
            assert row.organ_id == parent.organ_id
            assert row.segment_rank == parent.segment_rank + 1


@pytest.mark.integration
def test_simulation_is_reproducible_with_seed(simulation_parameters):
    a, ae = _run(simulation_parameters, 12)
    b, be = _run(simulation_parameters, 12)
    cols = [
        "node_id",
        "parent_id",
        "organ_id",
        "order",
        "segment_rank",
        "x",
        "y",
        "z",
        "length",
        "diameter",
        "invalid_root",
    ]
    a = a.sort_values("node_id")[cols].reset_index(drop=True)
    b = b.sort_values("node_id")[cols].reset_index(drop=True)
    from pandas.testing import assert_frame_equal

    assert_frame_equal(a, b, check_exact=False, rtol=1e-10, atol=1e-10)
    assert_frame_equal(
        ae.sort_values(["parent_id", "child_id"]).reset_index(drop=True),
        be.sort_values(["parent_id", "child_id"]).reset_index(drop=True),
    )


@pytest.mark.integration
def test_simulation_statistics_and_voxel_length_agree_on_large_grid(
    simulation_parameters,
):
    nodes, _ = _run(simulation_parameters, 99)
    assert RootNumber().calculate(nodes) > 0
    total = TotalLength().calculate(nodes)
    assert total > 0
    # Cover a generous cube and verify that no length is lost to clipping.
    # For exceptionally large simulations, check extents before this test.
    coords = nodes[["x", "y", "z"]].to_numpy(float)
    mins = np.floor(coords.min(axis=0) / 10) * 10 - 10
    maxs = np.ceil(coords.max(axis=0) / 10) * 10 + 10
    axes = [np.arange(lo, hi + 1, 10.0) for lo, hi in zip(mins, maxs)]
    import pandas as pd

    grid = pd.MultiIndex.from_product(axes, names=["x", "y", "z"]).to_frame(index=False)
    voxels, _ = aggregate_root_grid(nodes, grid, length_source="geometric")
    assert voxels.root_length_cm.sum() == pytest.approx(total, rel=1e-6, abs=1e-6)
