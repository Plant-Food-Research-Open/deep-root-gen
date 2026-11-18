"""Small deterministic DeepRootGen node graphs with known geometry."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def rsa_nodes() -> pd.DataFrame:
    """3 organs, 5 valid segments, two 90-degree lateral junctions.

    Order 1: z 0 -> -4 -> -10 (10 cm, diameter 0.2 cm)
    Order 2: (0,0,-4) -> (3,0,-4) -> (5,0,-4) (5 cm, 0.1 cm)
    Order 3: (3,0,-4) -> (3,2,-4) (2 cm, 0.05 cm)
    Total = 17 cm. Every nonbase node represents its incoming segment.
    """
    entries = [
        # id, parent, organ, order, rank, xyz, diameter, length, type
        (0, -1, 0, 0, 0, (0, 0, 0), 0.5, 0.0, "base"),
        (1, 0, 1, 1, 1, (0, 0, -4), 0.2, 4.0, "structural"),
        (2, 1, 1, 1, 2, (0, 0, -10), 0.2, 6.0, "structural"),
        (3, 1, 2, 2, 1, (3, 0, -4), 0.1, 3.0, "fine"),
        (4, 3, 2, 2, 2, (5, 0, -4), 0.1, 2.0, "fine"),
        (5, 3, 3, 3, 1, (3, 2, -4), 0.05, 2.0, "fine"),
    ]
    rows = []
    for nid, pid, oid, order, rank, xyz, d, l, kind in entries:
        rows.append(
            dict(
                node_id=nid,
                parent_id=pid,
                plant_id=1,
                organ_id=oid,
                order=order,
                segment_rank=rank,
                x=float(xyz[0]),
                y=float(xyz[1]),
                z=float(xyz[2]),
                length=l,
                diameter=d,
                root_tissue_density=0.2,
                root_type=kind,
                invalid_root=False,
            )
        )
    return pd.DataFrame(rows)


@pytest.fixture
def soil_grid() -> pd.DataFrame:
    """Two x bins, two y bins, two z bins, all containing the example RSA."""
    return pd.MultiIndex.from_product(
        [[-10.0, 0.0, 10.0], [-10.0, 0.0, 10.0], [-20.0, -10.0, 0.0]],
        names=["x", "y", "z"],
    ).to_frame(index=False)


@pytest.fixture
def line_nodes() -> pd.DataFrame:
    """Single length-10 horizontal segment with valid graph fields."""
    return pd.DataFrame(
        [
            dict(
                node_id=0,
                parent_id=-1,
                plant_id=1,
                organ_id=0,
                order=0,
                segment_rank=0,
                x=0.0,
                y=0.0,
                z=0.0,
                length=0.0,
                diameter=0.2,
                root_tissue_density=0.2,
                root_type="base",
                invalid_root=False,
            ),
            dict(
                node_id=1,
                parent_id=0,
                plant_id=1,
                organ_id=1,
                order=1,
                segment_rank=1,
                x=10.0,
                y=0.0,
                z=0.0,
                length=10.0,
                diameter=0.2,
                root_tissue_density=0.2,
                root_type="structural",
                invalid_root=False,
            ),
        ]
    )


@pytest.fixture
def two_voxels() -> pd.DataFrame:
    return pd.MultiIndex.from_product(
        [[-5.0, 5.0, 15.0], [-1.0, 1.0], [-1.0, 1.0]],
        names=["x", "y", "z"],
    ).to_frame(index=False)


@pytest.fixture
def subdivided_line(line_nodes) -> pd.DataFrame:
    """Same physical horizontal segment cut into 4 + 6 cm subsegments."""
    result = line_nodes.copy()
    result.loc[result.node_id.eq(1), ["x", "length"]] = [4.0, 4.0]
    extra = line_nodes.loc[line_nodes.node_id.eq(1)].copy()
    extra.loc[:, "node_id"] = 2
    extra.loc[:, "parent_id"] = 1
    extra.loc[:, "segment_rank"] = 2
    extra.loc[:, "length"] = 6.0
    return pd.concat([result, extra], ignore_index=True)


@pytest.fixture
def length_only() -> pd.DataFrame:
    return pd.DataFrame({"length": [1.0, 2.0, 3.0]})


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run complete stochastic DeepRootGen simulator tests.",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: full simulator checks, opt-in with --run-integration"
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-integration"):
        return
    marker = pytest.mark.skip(
        reason="Requires --run-integration and a working DeepRootGen simulator"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(marker)
