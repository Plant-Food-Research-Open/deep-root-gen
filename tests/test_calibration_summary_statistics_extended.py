"""Unit tests for calibration summary-statistic routing and discrepancies."""
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from deeprootgen.calibration import summary_statistics as subject


def make_input(statistics=None, selected=None, distances=None, **kwargs):
    values = dict(
        random_seed=17,
        simulation_tag="fixture",
        soil_layer_height=2,
        soil_layer_width=4,
        soil_n_layers=2,
        soil_n_cols=2,
        statistics_comparison=SimpleNamespace(
            distance_metrics=distances, summary_statistics=selected or []
        ),
        summary_statistics=statistics,
    )
    values.update(kwargs)
    return SimpleNamespace(**values)


def make_stat(name, value=3., **kwargs):
    values = dict(
        statistic_name=name, statistic_value=value,
        x=None, y=None, core_radius=None, z_lower_bound=None,
        z_upper_bound=None, diameter_max_mm=None, plant_id=None,
    )
    values.update(kwargs)
    obj = SimpleNamespace(**values)
    obj.dict = lambda: vars(obj).copy()
    return obj


@pytest.fixture
def fake_stat_model(monkeypatch):
    class Fake:
        @staticmethod
        def parse_obj(values):
            return SimpleNamespace(**values)
    monkeypatch.setattr(subject, "SummaryStatisticsModel", Fake)


def test_get_calibration_statistics_none_returns_empty(fake_stat_model,
    monkeypatch):
    monkeypatch.setattr(subject, "get_distance_metric_func",
        lambda name: lambda: SimpleNamespace(name=name))
    params = make_input(distances=["mae"])
    metrics, statistics = subject.get_calibration_summary_stats(params)
    assert [m.name for m in metrics] == ["mae"]
    assert statistics == []


def test_get_calibration_statistics_preserves_input_order(fake_stat_model,
    monkeypatch):
    monkeypatch.setattr(subject, "get_distance_metric_func",
        lambda name: lambda: SimpleNamespace(name=name))
    provided = [make_stat("total_length"), make_stat("root_number"),
        make_stat("average_length")]
    metrics, selected = subject.get_calibration_summary_stats(
        make_input(provided, ["root_number", "total_length"], ["mse", "mae"])
    )
    assert [stat.statistic_name for stat in selected] == ["total_length",
        "root_number"]
    assert [m.name for m in metrics] == ["mse", "mae"]


def test_get_calibration_stats_rejects_unknown_selection(fake_stat_model):
    with pytest.raises(ValueError, match="cannot be empty"):
        params = make_input([make_stat("length")], ["angle"])
        subject.get_calibration_summary_stats(params)


def test_nonlist_distance_metrics_are_ignored(fake_stat_model):
    params = make_input([make_stat("length")], ["length"], distances="MAE")
    _, result = subject.get_calibration_summary_stats(params)
    assert len(result) == 1


def test_run_calibration_simulation_sets_seed_and_runs(monkeypatch):
    parsed = object()
    parse = Mock(return_value=parsed)
    run = Mock()
    fake_sim = SimpleNamespace(run=run)
    ctor = Mock(return_value=fake_sim)
    monkeypatch.setattr(subject.RootSimulationModel, "parse_obj", parse)
    monkeypatch.setattr(subject, "RootSystemSimulation", ctor)
    params = {"root_growth_rate": 1.4}
    actual_sim, actual_params = subject.run_calibration_simulation(params,
        make_input())
    assert actual_sim is fake_sim and actual_params is parsed
    assert params["random_seed"] == 17
    parse.assert_called_once_with(params)
    ctor.assert_called_once_with(simulation_tag="fixture", random_seed=17)
    run.assert_called_once_with(parsed)


@pytest.fixture
def stub_simulation(monkeypatch):
    df = pd.DataFrame({"value": [3.0]})
    grid = pd.DataFrame({"x": [0], "y": [1], "z": [2]})
    soil = SimpleNamespace(create_soil_grid=Mock(return_value=grid))
    sim = SimpleNamespace(G=SimpleNamespace(as_df=lambda: (df,
        pd.DataFrame())), soil=soil)
    params = SimpleNamespace(root_tissue_density=0.21)
    monkeypatch.setattr(subject, "run_calibration_simulation",
        lambda *_: (sim, params))
    return sim, df, grid


def test_calculate_scalar_summary_statistics(stub_simulation, monkeypatch):
    seen = []
    class FakeStat:
        def __init__(self, root_tissue_density):
            seen.append(root_tissue_density)
        def calculate(self, node_df):
            return 10.0
    monkeypatch.setattr(subject, "get_summary_statistic_func",
        lambda _: FakeStat)
    simulated, observed = subject.calculate_summary_statistics(
        {}, make_input(), [make_stat("length", 8), make_stat("number", 3)]
    )
    np.testing.assert_array_equal(simulated, [10, 10])
    np.testing.assert_array_equal(observed, [8, 3])
    assert seen == [0.21, 0.21]


def test_calculate_summary_statistics_skips_vector_outputs(stub_simulation,
    monkeypatch):
    class VectorStat:
        def __init__(self, **kwargs):
            pass
        def calculate(self, node_df):
            return np.array([1, 2])
    monkeypatch.setattr(subject, "get_summary_statistic_func",
        lambda _: VectorStat)
    actual, observed = subject.calculate_summary_statistics({},
        make_input(), [make_stat("vector")])
    assert actual.size == observed.size == 0


def test_whole_grid_rld_creates_grid_and_calculates(stub_simulation,
    monkeypatch):
    sim, _, _ = stub_simulation
    init_calls = []
    class FakeRLD:
        def __init__(self, soil_df):
            init_calls.append(soil_df)
        def calculate(self, node_df):
            return 6.75
    monkeypatch.setattr(subject, "RootLengthDensity", FakeRLD)
    simulated, observed = subject.calculate_summary_statistics(
        {}, make_input(), [make_stat("root_length_density", 5)]
    )
    np.testing.assert_array_equal(simulated, [6.75])
    np.testing.assert_array_equal(observed, [5])
    sim.soil.create_soil_grid.assert_called_once_with(2, 2, 4, 2)
    # Historic Soil implementation swaps the names of the vertical axes.
    assert init_calls[0].loc[0, "z"] == 1
    assert init_calls[0].loc[0, "y"] == 2


@pytest.mark.parametrize("field,value", [("soil_layer_height", 0),
    ("soil_n_cols", None), ("soil_n_layers", -1)])
def test_rld_rejects_invalid_soil_dimensions(stub_simulation, field, value):
    with pytest.raises(ValueError, match="valid soil dimensions"):
        subject.calculate_summary_statistics(
            {}, make_input(**{field: value}),
                [make_stat("root_length_density")]
        )


@pytest.mark.parametrize("missing", ["x", "y", "core_radius"])
def test_spatial_rld_requires_all_three_coordinates(stub_simulation, missing):
    values = {"x": 1, "y": 2, "core_radius": 0.5}
    values[missing] = None
    with pytest.raises(ValueError, match="requires x, y and core_radius"):
        subject.calculate_summary_statistics(
            {}, make_input(), [make_stat("root_length_density", **values)]
        )


def test_spatial_rld_passes_core_bounds_and_filter(stub_simulation,
    monkeypatch):
    calculate = Mock(return_value=7.25)
    monkeypatch.setattr(subject, "calculate_core_rld", calculate)
    statistic = make_stat(
        "root_length_density", 6.0, x=1, y=2, core_radius=0.5,
        z_lower_bound=3, z_upper_bound=5, diameter_max_mm=0.7, plant_id=4,
    )
    simulated, observed = subject.calculate_summary_statistics({},
        make_input(), [statistic])
    np.testing.assert_array_equal(simulated, [7.25])
    np.testing.assert_array_equal(observed, [6.0])
    kwargs = calculate.call_args.kwargs
    assert kwargs == dict(x=1, y=2, z_lower_bound=3, z_upper_bound=5,
                          core_radius=0.5, diameter_max_mm=0.7, plant_id=4)


@pytest.mark.parametrize("actual,observed,expected", [
    ([1., 3.], [2., 5.], 3.),
    ([1., 2.], [1., 2.], 0.),
])
def test_calibration_discrepancy_sums_metrics(monkeypatch, actual, observed,
    expected):
    monkeypatch.setattr(
        subject, "calculate_summary_statistics",
        lambda *_: (np.array(actual), np.array(observed)),
    )
    distances = [SimpleNamespace(calculate=lambda o, s: abs(o-s).sum())]
    value = subject.calculate_summary_statistic_discrepancy({},
        make_input(), [], distances)
    assert value == pytest.approx(expected)


def test_calibration_discrepancy_multiple_metrics(monkeypatch):
    monkeypatch.setattr(subject, "calculate_summary_statistics",
        lambda *_: (np.array([3., 4.]), np.array([1., 1.])))
    distances = [
        SimpleNamespace(calculate=lambda o, s: abs(o-s).sum()),
        SimpleNamespace(calculate=lambda o, s: ((o-s)**2).sum()),
    ]
    # L1 = 5; squared error sum = 13.
    assert subject.calculate_summary_statistic_discrepancy({}, make_input(),
        [], distances) == pytest.approx(18)
