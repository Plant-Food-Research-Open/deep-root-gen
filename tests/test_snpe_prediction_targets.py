"""Check the conditioning contract and browser-facing service links."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import joblib
import pandas as pd
import pytest
from bentoml.exceptions import BadInput
from mlflow.models import Model

from deeprootgen import serving
from deeprootgen.data_model.snpe_targets import conditioning_rows
from deeprootgen.form.components import get_external_links


def row(name, value):
    return {"statistic_name": name, "statistic_value": value}


def test_conditioning_rows_use_training_order_and_keep_zero():
    uploaded = [row("root_number", 0), row("total_volume", 99), row("total_length", "50.25")]
    assert conditioning_rows(["total_length", "root_number"], uploaded) == [
        row("total_length", 50.25), row("root_number", 0.0)
    ]


@pytest.mark.parametrize(
    "rows, error",
    [
        ([row("root_number", 2)], "Supply a value for total_length"),
        ([row("total_length", 1), row("total_length", 2)], "exactly one value"),
        ([row("total_length", float("inf"))], "finite numeric value"),
        ([row("total_length", True)], "finite numeric value"),
    ],
)
def test_invalid_targets_cannot_produce_a_conditioning_vector(rows, error):
    with pytest.raises(ValueError, match=error):
        conditioning_rows(["total_length"], rows)


def test_snpe_service_reads_existing_model_artifact_and_checks_selected_tag(tmp_path, monkeypatch):
    from bentoml.mlflow import MLFLOW_MODEL_FOLDER

    model_dir = tmp_path / MLFLOW_MODEL_FOLDER
    model_dir.mkdir()
    joblib.dump([row("root_number", 2), row("total_length", 50)], model_dir / "statistics.pkl")
    manifest = Model()
    manifest.add_flavor(
        "python_function",
        config={"inference_type": "summary_statistics"},
        artifacts={"statistics_list": {"path": "statistics.pkl"}},
    )
    manifest.save(str(model_dir / "MLmodel"))
    sent = []

    def predict(frame):
        sent.append(frame[["statistic_name", "statistic_value"]].to_dict("records"))
        return pd.DataFrame({"primary_root_count": [3]})

    model = SimpleNamespace(tag="snpe:selected", path_of=lambda name: str(tmp_path / name))
    monkeypatch.setattr(serving, "load", lambda task: (model, ""))
    monkeypatch.setattr(
        serving, "service",
        lambda *args, **kwargs: (SimpleNamespace(api=lambda **options: lambda function: function),
                                 SimpleNamespace(predict=SimpleNamespace(run=predict))),
    )
    module_name = "app.deployments.snpe_service"
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    service = importlib.import_module(module_name)
    try:
        assert service.prediction_info["input_schema"]["statistic_names"] == [
            "root_number", "total_length"
        ]
        assert not service.read_prediction_info(Path(tmp_path))["prediction_ready"]
        targets = [row("total_length", 77), row("root_number", 0)]
        with pytest.raises(BadInput, match="model changed"):
            service.predict(service.SnpeFeatures(summary_statistics=targets, model_tag="snpe:old"))
        with pytest.raises(BadInput, match="total_length"):
            service.predict(service.SnpeFeatures(summary_statistics=[row("root_number", 0)]))
        result = service.predict(service.SnpeFeatures(summary_statistics=targets, model_tag="snpe:selected"))
        assert result.to_dict("records") == [{"primary_root_count": 3}]
        assert sent == [[row("root_number", 0), row("total_length", 77)]]
    finally:
        sys.modules.pop(module_name, None)


def test_external_links_follow_public_ports_and_skip_hidden_consoles(monkeypatch):
    for name in ("APP_ARANGODB_USER_HOST", "APP_MINIO_USER_HOST", "APP_METABASE_USER_HOST",
                 "APP_CLOUDBEAVER_USER_HOST"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_PREFECT_USER_HOST", "http://127.0.0.1:14203")
    monkeypatch.setenv("APP_MLFLOW_USER_HOST", "http://127.0.0.1:15003")
    links = {item.children.children: item.children.href for item in get_external_links().children}
    assert links == {"MLflow": "http://127.0.0.1:15003", "Prefect": "http://127.0.0.1:14203"}
    monkeypatch.setenv("APP_MINIO_USER_HOST", "https://storage.example.com/console")
    assert get_external_links().children[-1].children.href == "https://storage.example.com/console"
