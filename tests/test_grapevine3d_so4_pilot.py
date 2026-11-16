"""Synthetic agreement, support accounting and scoring tests for the local pilot."""

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location(
    "g3d_pilot_test",
    Path(__file__).parents[1] / "scripts/research/grapevine3d_so4_pilot.py",
)
pilot = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pilot
spec.loader.exec_module(pilot)


def test_reflected_depth_face_matches_prepared_operator():
    nodes = pd.DataFrame(
        [
            dict(
                node_id=0,
                parent_id=-1,
                organ_id=0,
                order=0,
                x=0.0,
                y=0.0,
                z=0.0,
                invalid_root=False,
            ),
            dict(
                node_id=1,
                parent_id=0,
                organ_id=1,
                order=1,
                x=10.0,
                y=0.0,
                z=0.0,
                invalid_root=False,
            ),
        ]
    )
    records, _ = pilot.node_segments(nodes, base_depth=10)
    metrics, cells, _ = pilot.summarize_geometry(records)
    assert cells == {(0, 0, 1): 10.0}
    assert metrics["soil_length_cm"] == 10
    assert pilot.converter.split_segment_into_cells(records[0][0], 10) == [
        ((0, 0, 1), 10.0)
    ]


def test_surface_clipping_exterior_and_shape_error():
    segment = pilot.converter.Segment((-5.0, 0.0, -5.0), (15.0, 0.0, 15.0), "primary")
    metrics, cells, _ = pilot.summarize_geometry([(segment, 1)])
    assert metrics["above_surface_length_cm"] == pytest.approx(5 * np.sqrt(2))
    assert metrics["soil_length_cm"] == pytest.approx(15 * np.sqrt(2))
    assert sum(cells.values()) == pytest.approx(metrics["soil_length_cm"])
    observed = pd.DataFrame(
        [
            dict(ix=0, iy=0, iz=0, root_length_cm=10 * np.sqrt(2)),
            dict(ix=1, iy=0, iz=0, root_length_cm=0.0),
        ]
    )
    score = pilot.score_grid(cells, observed, 0.01)
    assert score["normalized_mae"] == pytest.approx(0)
    assert score["exterior_length_cm"] == pytest.approx(5 * np.sqrt(2))
    assert score["full_shape_tv"] == pytest.approx(0)


def test_invalid_child_excluded_but_parent_coordinate_retained():
    nodes = pd.DataFrame(
        [
            dict(
                node_id=0,
                parent_id=-1,
                organ_id=0,
                order=0,
                x=0.0,
                y=0.0,
                z=0.0,
                invalid_root=False,
            ),
            dict(
                node_id=1,
                parent_id=0,
                organ_id=1,
                order=1,
                x=0.0,
                y=0.0,
                z=-2.0,
                invalid_root=True,
            ),
            dict(
                node_id=2,
                parent_id=1,
                organ_id=2,
                order=2,
                x=3.0,
                y=0.0,
                z=-2.0,
                invalid_root=False,
            ),
        ]
    )
    records, invalid = pilot.node_segments(nodes, base_depth=0)
    assert len(records) == len(invalid) == 1
    assert pilot.summarize_geometry(records)[0]["soil_length_cm"] == 3
    assert pilot.summarize_geometry(invalid)[0]["soil_length_cm"] == 2
