"""Check synthetic minimum-size Surrogate jobs without tracking services."""

from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
import torch


@pytest.fixture
def worker():
    from app.flows import run_surrogate

    return run_surrogate


def test_cost_worker_trains_and_reports_one_epoch_and_one_row_per_split(
    worker, monkeypatch, tmp_path
):
    inputs = SimpleNamespace(
        parameter_intervals=SimpleNamespace(dict=lambda: {"fixed": {}, "varying": {}}),
        calibration_parameters={
            "num_inducing_points": 1,
            "lr": 0.01,
            "n_epochs": 1,
            "early_stopping_patience": 0,
        },
    )
    samples = pd.DataFrame(
        {
            "fixed": [7.0, 7.0, 7.0],
            "varying": [1.0, 2.0, 3.0],
            "training_data_split": [0, 1, 2],
            "sim_ids": ["train", "validation", "holdout"],
        }
    )
    monkeypatch.setattr(
        worker, "calculate_summary_statistic_discrepancy", lambda *_: 9.5
    )
    monkeypatch.setattr(worker, "get_datetime_now", lambda: "minimum")
    monkeypatch.setattr(worker, "get_outdir", lambda: str(tmp_path))
    monkeypatch.setattr(worker, "create_table_artifact", Mock())
    monkeypatch.setattr(worker, "log_model", Mock())
    for operation in ("log_artifact", "log_metric", "set_tag"):
        monkeypatch.setattr(worker.mlflow, operation, Mock())

    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(0)
        trained = worker.perform_summary_stat_task.fn(inputs, samples, [], [])
    try:
        worker.log_summary_stat_task.fn(inputs, *trained, "simulation")
    finally:
        worker.plt.close("all")

    assert worker.log_model.call_args.args[5] == [
        {"varying": 1.0},
        {"varying": 2.0},
        {"varying": 3.0},
    ]
    predictions = pd.read_csv(tmp_path / "minimum-surrogate_test_actual_predicted.csv")
    assert len(predictions) == 1
    assert predictions["test_varying"].tolist() == [3.0]
    assert predictions["test_actual"].tolist() == [9.5]
    assert np.isfinite(predictions["test_predicted"]).all()
    assert worker.mlflow.log_metric.call_count == 15
    assert all(
        np.isfinite(call.args[1]) for call in worker.mlflow.log_metric.call_args_list
    )


def test_worker_rejects_graph_training_before_starting_experiment(worker, monkeypatch):
    begin = Mock()
    monkeypatch.setattr(worker, "begin_experiment", begin)
    graph_request = SimpleNamespace(
        statistics_comparison=SimpleNamespace(use_summary_statistics=False)
    )
    with pytest.raises(ValueError, match="summary-statistic cost emulation"):
        worker.run_surrogate.fn(graph_request, "simulation")
    begin.assert_not_called()
