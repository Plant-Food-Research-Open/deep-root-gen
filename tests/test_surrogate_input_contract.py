"""Exercise the HTTP prediction entrypoint with real signatures and a local stub runner."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import bentoml
from bentoml.exceptions import BadInput
from mlflow.models import Model, infer_signature
import numpy as np
import pandas as pd
import pytest
import yaml

from deeprootgen.data_model import RootCalibrationIntervals
from deeprootgen.data_model.surrogate_inputs import SurrogateFeatures, surrogate_form_row

ROOT = Path(__file__).resolve().parents[1]


def service_with_signature(tmp_path, monkeypatch, training_frame):
    # Local metadata only. Never query a model registry or start a Bento service.
    folder = tmp_path / bentoml.mlflow.MLFLOW_MODEL_FOLDER
    folder.mkdir()
    Model(signature=infer_signature(training_frame)).save(str(folder / "MLmodel"))
    runner = Mock()
    runner.predict.run.side_effect = lambda frame: pd.DataFrame({"sum": frame.sum(axis=1)})
    saved = SimpleNamespace(tag="surrogate:chosen", to_runner=lambda: runner, path_of=lambda name: str(tmp_path / name))
    get = Mock(return_value=saved)
    monkeypatch.setattr(bentoml.mlflow, "get", get)
    monkeypatch.setattr(bentoml, "Service", lambda *args, **kwargs: SimpleNamespace(api=lambda **io: lambda fn: fn))
    monkeypatch.setenv("SURROGATE_MODEL_TAG", str(saved.tag))
    spec = spec_from_file_location("test_bento_surrogate", ROOT / "app/deployments/surrogate_service.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    get.assert_called_once_with(str(saved.tag))
    return module, runner


def test_current_form_defaults_match_current_trained_dimensions(tmp_path, monkeypatch):
    form = yaml.safe_load((ROOT / "app/conf/deployments_form/common.yaml").read_text())
    children = form["components"]["parameters"]["children"]
    row = surrogate_form_row(children, [c["kwargs"].get("value") for c in children])
    assert set(row) == set(RootCalibrationIntervals.model_fields)
    # Verify service projects by name, even if the submitted fields arrived in another order.
    trained = pd.DataFrame([row], columns=list(reversed(row)))
    service, runner = service_with_signature(tmp_path, monkeypatch, trained)
    got = service.predict(SurrogateFeatures(data=[row, row]))
    pd.testing.assert_frame_equal(runner.predict.run.call_args.args[0], pd.concat([trained, trained], ignore_index=True))
    np.testing.assert_allclose(got["sum"], [sum(row.values())] * 2)


def test_archived_signature_accepts_its_names_and_rejects_current_row(tmp_path, monkeypatch):
    trained = pd.DataFrame({"fine_root_threshold": [0.06], "outer_root_num": [7]})
    service, runner = service_with_signature(tmp_path, monkeypatch, trained)
    fields = [{"param": "primary_root_count"}, {"param": "trained_features_json"}]
    old = surrogate_form_row(fields, [18, '{"outer_root_num": 7.0, "fine_root_threshold": 0.06}'])
    service.predict(SurrogateFeatures(data=[old]))
    pd.testing.assert_frame_equal(runner.predict.run.call_args.args[0], trained)
    runner.predict.run.reset_mock()
    for row, message in [
        ({"primary_root_count": 18}, "missing trained feature 'fine_root_threshold'"),
        (dict(old, outer_root_num=4.5), "requires an integer"),
        (dict(old, outer_root_num=True), "requires a finite number"),
        (dict(old, fine_root_threshold=float("nan")), "requires a finite number"),
    ]:
        with pytest.raises(BadInput, match=message):
            service.predict(SurrogateFeatures(data=[old, row]))
        runner.predict.run.assert_not_called()
