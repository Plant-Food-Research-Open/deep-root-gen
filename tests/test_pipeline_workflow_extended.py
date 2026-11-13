"""Tests for Prefect/MLflow run metadata logging without a live backend."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

for dependency in ("mlflow", "prefect"):
    pytest.importorskip(dependency)

from deeprootgen.pipeline import workflow as subject


@pytest.mark.parametrize("hosts,expected_app,expected_mlflow", [
    ({}, "http://localhost:8000", "http://localhost:5000"),
    ({"APP_USER_HOST": "https://roots.example.org",
      "APP_MLFLOW_USER_HOST": "https://mlflow.example.org"},
     "https://roots.example.org", "https://mlflow.example.org"),
])
def test_log_experiment_details_creates_markdown_artifact(
    monkeypatch, hosts, expected_app, expected_mlflow
):
    for key in ["APP_USER_HOST", "APP_MLFLOW_USER_HOST"]:
        monkeypatch.delenv(key, raising=False)
    for key, value in hosts.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(subject.mlflow, "active_run", lambda: SimpleNamespace(
        info=SimpleNamespace(experiment_id="exp-3", run_id="run-4")
    ))
    artifact = Mock()
    monkeypatch.setattr(subject, "create_markdown_artifact", artifact)

    subject.log_experiment_details.fn("uuid-2")

    artifact.assert_called_once()
    kwargs = artifact.call_args.kwargs
    assert kwargs["key"] == "root-simulation-run"
    assert kwargs["description"] == "Root simulation run."
    message = kwargs["markdown"]
    assert "uuid-2" in message
    assert expected_app in message
    assert f"{expected_mlflow}/#/experiments/exp-3/runs/run-4" in message
