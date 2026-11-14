"""Small soil-grid tests that don't require running the simulator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from deeprootgen.model.soil import Soil


@pytest.mark.parametrize(
    "layer_height,n_layers,layer_width,n_cols",
    [
        (5.0, 1, 5.0, 1),
        (10.0, 2, 5.0, 3),
        (3.0, 4, 2.0, 2),
    ],
)
def test_soil_grid_has_finite_xyz_coordinates(
    layer_height, n_layers, layer_width, n_cols
):
    df = Soil().create_soil_grid(layer_height, n_layers, layer_width, n_cols)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert {"x", "y", "z"}.issubset(df.columns)
    assert np.isfinite(df[["x", "y", "z"]].to_numpy(dtype=float)).all()


@pytest.mark.parametrize("n_layers", [1, 2, 4])
def test_grid_contains_both_soil_surface_and_subsurface(n_layers):
    df = Soil().create_soil_grid(10.0, n_layers, 5.0, 2)
    z = df["z"].to_numpy(dtype=float)
    assert z.min() <= 0.0
    assert z.max() >= z.min()
    assert np.isfinite(z).all()


def test_soil_figure_is_a_plotly_figure():
    soil = Soil()
    df = soil.create_soil_grid(5.0, 2, 5.0, 2)
    fig = soil.create_soil_fig(df)
    assert isinstance(fig, go.Figure)
    # Ensure output can be serialized; catches invalid plotly trace contents.
    assert isinstance(fig.to_plotly_json(), dict)
