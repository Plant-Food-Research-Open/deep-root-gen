"""Tests for experiment tracking, file exports and UI parameter plumbing.

Prefect tasks are exercised through .fn so tests don't start a Prefect flow.
MLflow, remote deployments, Dash, profiling and plotting are mocked.
"""
import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import networkx as nx
import numpy as np
import pandas as pd
import pytest
import yaml

for dependency in ("mlflow", "prefect", "ydata_profiling"):
    pytest.importorskip(dependency)

from deeprootgen.pipeline import experiment as subject


def _fake_app():
    form = SimpleNamespace(components={
        "parameters": {"children": [{"param": "length"},
            {"param": "n_roots"}]},
        "optimisation": {"children": [{"param": "n_trials"},
            {"param": "algorithm"}]},
    })
    return SimpleNamespace(settings={"sample_form": form})


def test_datetime_format_is_filename_safe():
    value = subject.get_datetime_now()
    assert len(value) == 19
    assert value.count("-") == 5
    assert all(c.isdigit() or c == "-" for c in value)


def test_get_outdir_returns_configured_path(monkeypatch, tmp_path):
    monkeypatch.setattr(subject, "OUT_DIR", str(tmp_path))
    assert subject.get_outdir() == str(tmp_path)


def test_get_simulation_uuid_returns_distinct_valid_uuids():
    import uuid
    first = subject.get_simulation_uuid()
    second = subject.get_simulation_uuid()
    assert first != second
    assert str(uuid.UUID(first)) == first
    assert str(uuid.UUID(second)) == second


@pytest.mark.parametrize("already_exists", [False, True])
def test_begin_experiment_sets_tags_and_creates_if_needed(monkeypatch,
    already_exists):
    mlflow = SimpleNamespace(
        get_experiment_by_name=Mock(
            return_value=object() if already_exists else None
        ),
        create_experiment=Mock(), set_experiment=Mock(), set_tag=Mock(),
    )
    monkeypatch.setattr(subject, "mlflow", mlflow)
    monkeypatch.setattr(subject.context, "get_run_context",
        lambda: SimpleNamespace(
        task_run=SimpleNamespace(flow_run_id="flow-19")
    ))
    monkeypatch.delenv("APP_USER_HOST", raising=False)
    monkeypatch.delenv("APP_PREFECT_USER_HOST", raising=False)

    subject.begin_experiment.fn("simulation", "uuid-19", "my-tag")
    mlflow.get_experiment_by_name.assert_called_once_with(
        "root_model_simulation"
    )
    assert mlflow.create_experiment.call_count == (0 if already_exists else 1)
    mlflow.set_experiment.assert_called_once_with("root_model_simulation")
    tags = dict(call.args for call in mlflow.set_tag.call_args_list)
    assert tags["task"] == "simulation"
    assert tags["flow_run_id"] == "flow-19"
    assert tags["simulation_tag"] == "my-tag"
    assert tags["app_url"] == "http://localhost:8000"
    expected = "http://localhost:4200/flow-runs/flow-run/flow-19"
    assert expected in tags["prefect_flow_url"]


def test_begin_experiment_uses_public_hosts(monkeypatch):
    tags = []
    monkeypatch.setattr(subject, "mlflow", SimpleNamespace(
        get_experiment_by_name=lambda _: object(), set_experiment=Mock(),
        set_tag=lambda key, val: tags.append((key, val)),
    ))
    monkeypatch.setattr(subject.context, "get_run_context",
        lambda: SimpleNamespace(
        task_run=SimpleNamespace(flow_run_id="flow-2")
    ))
    monkeypatch.setenv("APP_USER_HOST", "https://roots.example.org")
    monkeypatch.setenv("APP_PREFECT_USER_HOST", "https://prefect.example.org")
    subject.begin_experiment.fn("calibration", "uuid", "tag")
    assert dict(tags)["app_url"] == "https://roots.example.org"
    assert dict(tags)["prefect_flow_url"].startswith(
        "https://prefect.example.org"
    )


def test_log_config_saves_yaml_and_logs_each_parameter(monkeypatch, tmp_path):
    monkeypatch.setattr(subject, "OUT_DIR", str(tmp_path))
    monkeypatch.setattr(subject, "get_datetime_now",
        lambda: "2026-11-13-21-00-00")
    log_param, log_artifact = Mock(), Mock()
    monkeypatch.setattr(subject, "mlflow",
        SimpleNamespace(log_param=log_param, log_artifact=log_artifact))
    original = {"alpha": 2.5, "n_roots": 3}
    output = subject.log_config.fn(original, "simulation")
    assert Path(output).exists()
    assert yaml.safe_load(Path(output).read_text()) == original
    assert log_param.call_count == 2
    log_artifact.assert_called_once_with(output)


def test_calculate_graph_metrics_outputs_six_metrics(monkeypatch, tmp_path):
    monkeypatch.setattr(subject, "OUT_DIR", str(tmp_path))
    metric, artifact = Mock(), Mock()
    monkeypatch.setattr(subject, "mlflow",
        SimpleNamespace(log_metric=metric, log_artifact=artifact))
    # A connected path has unambiguous diameter=3, radius=2.
    result = subject.calculate_graph_metrics.fn(nx.path_graph(4), "now",
        "simulation")
    df = pd.read_csv(result)
    assert len(df) == 6
    assert df.set_index("metric_name").loc["diameter",
        "metric_value"] == pytest.approx(3.)
    assert df.set_index("metric_name").loc["radius",
        "metric_value"] == pytest.approx(2.)
    assert metric.call_count == 6
    artifact.assert_called_once_with(result)


def _uploaded_yaml(data):
    return "data:application/x-yaml;base64," + base64.b64encode(
        yaml.safe_dump(data).encode("utf-8")
    ).decode("ascii")


@pytest.mark.parametrize("task,expected", [
    ("", [2.4, 4]),
    ("optimisation", [[2.4, 4], [10, "tpe"]]),
])
def test_load_form_parameters_without_dash_server(monkeypatch, task, expected):
    monkeypatch.setattr(subject, "get_app", _fake_app)
    data = {"length": 2.4, "n_roots": 4, "n_trials": 10, "algorithm": "tpe"}
    parsed, toast = subject.load_form_parameters(
        [_uploaded_yaml(data)], ["parameters.yaml"], "sample_form", task
    )
    assert parsed == expected
    assert "parameters.yaml" in toast


def test_save_form_parameters_roundtrips_base_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(subject, "get_app", _fake_app)
    monkeypatch.setattr(subject, "OUT_DIR", str(tmp_path))
    monkeypatch.setattr(subject, "get_datetime_now", lambda: "now")
    output, filename = subject.save_form_parameters("simulation",
        "sample_form", [2.4, 4])
    assert filename == "now-simulation.yaml"
    assert yaml.safe_load(Path(output).read_text()) == {"length": 2.4,
        "n_roots": 4}


def test_save_form_parameters_includes_calibration_fields(monkeypatch,
    tmp_path):
    monkeypatch.setattr(subject, "get_app", _fake_app)
    monkeypatch.setattr(subject, "OUT_DIR", str(tmp_path))
    monkeypatch.setattr(subject, "get_datetime_now", lambda: "now")
    output, _ = subject.save_form_parameters(
        "calibrate", "sample_form", [2., 5], task="optimisation",
        calibration_inputs=[8, "cmaes"],
    )
    assert yaml.safe_load(Path(output).read_text()) == {
        "length": 2., "n_roots": 5, "n_trials": 8, "algorithm": "cmaes"
    }


def test_save_simulation_runs_writes_relative_outputs(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "outputs").mkdir()
    monkeypatch.setattr(subject, "get_datetime_now", lambda: "now")
    output, filename = subject.save_simulation_runs([{"task": "simulation",
        "tag": "a"}])
    assert filename == "now-root-simulation-runs.csv"
    assert Path(output).exists()
    assert pd.read_csv(output).to_dict("records") == [{"task": "simulation",
        "tag": "a"}]


def test_dispatch_new_run_calls_prefect_and_updates_run_list(monkeypatch):
    dispatch = Mock(return_value=SimpleNamespace(id="prefect-42"))
    monkeypatch.setattr(subject, "run_deployment", dispatch)
    monkeypatch.setattr(subject, "get_simulation_uuid", lambda: "sim-42")
    monkeypatch.setattr(subject, "get_datetime_now", lambda: "today")
    monkeypatch.setenv("APP_PREFECT_USER_HOST", "https://prefect.example.org")
    runs = [{"task": "old"}]
    result, toast = subject.dispatch_new_run("optimisation",
        {"simulation_tag": "my-run"}, runs)
    assert result is runs and len(result) == 2
    assert dispatch.call_args.args[0] == "optimisation/run_optimisation_flow"
    assert dispatch.call_args.kwargs["timeout"] == 0
    assert dispatch.call_args.kwargs["flow_run_name"] == "sim-42"
    assert dispatch.call_args.kwargs["parameters"] == {
        "input_parameters": {"simulation_tag": "my-run"},
            "simulation_uuid": "sim-42"
    }
    expected = "https://prefect.example.org/flow-runs/flow-run/prefect-42"
    assert expected in runs[-1]["workflow"]
    assert runs[-1]["tag"] == "my-run"
    assert "sim-42" in toast


class FakeFigure:
    def write_html(self, path):
        Path(path).write_text("<html>fixture</html>")


class FakeProfile:
    def __init__(self, *args, **kwargs):
        pass
    def to_file(self, path):
        Path(path).write_text("<html>profile</html>")


@pytest.fixture
def log_simulation_setup(monkeypatch, tmp_path):
    """Produce real local files but no remote writes."""
    monkeypatch.setattr(subject, "OUT_DIR", str(tmp_path))
    monkeypatch.setattr(subject, "get_datetime_now", lambda: "now")
    metric, artifact = Mock(), Mock()
    monkeypatch.setattr(subject, "mlflow",
        SimpleNamespace(log_metric=metric, log_artifact=artifact))
    monkeypatch.setattr(subject, "ProfileReport", FakeProfile)
    graph = SimpleNamespace(
        as_df=lambda: (pd.DataFrame({"x": [0., 1.], "y": [0., 0.], "z": [0.,
            1.]}),
                       pd.DataFrame({"from": [0], "to": [1]})),
        as_networkx=lambda: nx.path_graph(2),
    )
    soil = SimpleNamespace(create_soil_grid=Mock(return_value=pd.DataFrame({
        "x": [0.], "y": [1.], "z": [2.], "soil_volume_cm3": [100.]
    })))
    sim = SimpleNamespace(
        G=graph, soil=soil,
        init_fig=lambda *_: FakeFigure(),
        plot_root_system=lambda *_: FakeFigure(),
        plot_hierarchical_graph=lambda *_: FakeFigure(),
    )
    params = SimpleNamespace(soil_layer_height=None, soil_layer_width=None,
                             soil_n_layers=None, soil_n_cols=None,
                                 root_tissue_density=0.2)
    return sim, params, metric, artifact, tmp_path


def test_log_simulation_artifacts_and_scalar_metric(
    log_simulation_setup, monkeypatch
):
    sim, params, metric, artifact, folder = log_simulation_setup
    monkeypatch.setattr(subject, "get_summary_statistics",
        lambda: [{"value": "root_number"}])
    class RootNumber:
        def __init__(self, **kwargs):
            assert kwargs["root_tissue_density"] == 0.2
        def calculate(self, node_df):
            return 2.0
    monkeypatch.setattr(subject, "get_summary_statistic_func",
        lambda _: RootNumber)
    subject.log_simulation.fn(params, sim, "simulation")
    metrics = dict(call.args for call in metric.call_args_list)
    assert metrics == {"root_number": 2.}
    assert (folder / "now-simulation_nodes.csv").exists()
    assert (folder / "now-simulation_edges.csv").exists()
    assert (folder / "now-simulation_summary_statistics.csv").exists()
    assert (folder / "now-simulation_roots.html").exists()
    assert (folder / "now-simulation_hgraph.html").exists()
    assert (folder / "now-simulation_data_profile.html").exists()
    assert artifact.call_count == 6


def test_log_simulation_skips_rld_without_soil_grid(log_simulation_setup,
    monkeypatch):
    sim, params, metric, artifact, folder = log_simulation_setup
    monkeypatch.setattr(subject, "get_summary_statistics",
        lambda: [{"value": "root_length_density"}])
    subject.log_simulation.fn(params, sim, "simulation")
    metric.assert_not_called()
    assert not list(folder.glob("*_rld_*"))


def test_log_simulation_skips_non_scalar_values(
    log_simulation_setup, monkeypatch
):
    sim, params, metric, _, folder = log_simulation_setup
    names = ["tuple", "vector", "notfinite"]
    monkeypatch.setattr(subject, "get_summary_statistics",
        lambda: [{"value": name} for name in names])
    class Metric:
        def __init__(self, name, **kwargs):
            self.name = name
        def calculate(self, node_df):
            return {"tuple": (2., 4.), "vector": [1., 2.],
                "notfinite": np.nan}[self.name]
    monkeypatch.setattr(subject, "get_summary_statistic_func",
        lambda name: lambda **kw: Metric(name, **kw))
    subject.log_simulation.fn(params, sim, "simulation")
    logged = dict(call.args for call in metric.call_args_list)
    assert logged == {"average_tuple": 3.0}
    df = pd.read_csv(folder / "now-simulation_summary_statistics.csv")
    assert df.statistic_name.tolist() == ["average_tuple"]


def test_log_simulation_rld_dry_mass_and_grid_exports(log_simulation_setup,
    monkeypatch):
    sim, params, metric, artifact, folder = log_simulation_setup
    params.soil_layer_height = 2.
    params.soil_layer_width = 4.
    params.soil_n_layers = 2
    params.soil_n_cols = 2
    monkeypatch.setattr(subject, "get_summary_statistics", lambda: [
        {"value": "root_length_density"},
            {"value": "root_dry_mass_by_diameter"}
    ])
    class RLD:
        def __init__(self, soil_df):
            assert soil_df.loc[0, "z"] == 1.  # soil axes renamed
        def calculate_per_voxel(self, node_df):
            return pd.DataFrame({"root_length_cm": [10., 20.],
                "soil_volume_cm3": [100., 100.]})
        def aggregate(self, voxel_df, resolution):
            return pd.DataFrame({"resolution": [resolution]})
    class Mass:
        def __init__(self, **kwargs):
            pass
        def calculate_df(self, node_df):
            return pd.DataFrame({"diameter_mm": [0.5], "mass_g": [0.2]})
    monkeypatch.setattr(subject, "RootLengthDensity", RLD)
    monkeypatch.setattr(subject, "RootDryMassByDiameter", Mass)
    monkeypatch.setattr(subject, "aggregate_root_grid", lambda nodes, soil: (
        pd.DataFrame({"voxel": [0]}), pd.DataFrame({"mass": [0.2]})
    ))
    subject.log_simulation.fn(params, sim, "simulation")
    assert metric.call_args_list[0].args == ("root_length_density", 0.15)
    assert (folder / "now-simulation_rld_voxels.csv").exists()
    assert (folder / "now-simulation_rld_rows.csv").exists()
    assert (folder / "now-simulation_rld_columns.csv").exists()
    assert (folder / "now-simulation_rld_layers.csv").exists()
    assert (folder / "now-simulation_dry_mass_by_diameter.csv").exists()
    assert (folder / "now-simulation_root_grid_aggregates.csv").exists()
    assert (folder / "now-simulation_root_biomass_totals.csv").exists()
    assert sim.soil.create_soil_grid.call_count == 2
