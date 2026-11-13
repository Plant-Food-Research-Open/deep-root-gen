"""MLflow/BentoML wrapper tests using mocks (no services or model training)."""
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
import torch
from sklearn.preprocessing import MinMaxScaler

for dependency in ("bentoml", "gpytorch", "mlflow", "zuko", "lampe",
    "torch_geometric"):
    pytest.importorskip(dependency)

from deeprootgen.calibration import model_versioning as subject


@pytest.fixture
def model_context():
    return SimpleNamespace(artifacts={}, model_config={})


def test_log_model_registers_artifacts_and_metadata(monkeypatch):
    log = Mock(return_value=SimpleNamespace(model_uri="runs:/123/calibration"))
    register = Mock(return_value=SimpleNamespace(version="3"))
    update = Mock()
    import_bento = Mock()
    monkeypatch.setattr(subject.mlflow.pyfunc, "log_model", log)
    monkeypatch.setattr(subject.mlflow, "register_model", register)
    monkeypatch.setattr(subject.mlflow, "get_tracking_uri",
        lambda: "sqlite:///mlruns.db")
    monkeypatch.setattr(subject.mlflow, "active_run", lambda: SimpleNamespace(
        data=SimpleNamespace(tags={"test": "yes"}, metrics={"mae": 0.5},
            params={"seed": 2})
    ))
    monkeypatch.setattr(subject, "MlflowClient",
        lambda uri: SimpleNamespace(update_model_version=update))
    monkeypatch.setattr(subject.bentoml.mlflow, "import_model", import_bento)

    calibrator = object()
    subject.log_model(
        "optimisation", SimpleNamespace(simulation_tag="unit"), calibrator,
        {"calibrator": "/tmp/model.bin"}, "uuid-7",
            model_config={"method": "abc"}
    )
    assert log.call_args.kwargs["signature"] is None
    assert log.call_args.kwargs["python_model"] is calibrator
    assert register.call_args.kwargs["tags"] == dict(
        task="optimisation", simulation_uuid="uuid-7", simulation_tag="unit")
    assert update.call_args.kwargs["version"] == "3"
    assert import_bento.call_args.args == ("optimisation",
        "runs:/123/calibration")
    assert import_bento.call_args.kwargs["metadata"]["metrics"] == {"mae": 0.5}


def test_log_model_infers_signature_when_data_provided(monkeypatch):
    inferred = object()
    infer = Mock(return_value=inferred)
    monkeypatch.setattr(subject, "infer_signature", infer)
    logged = Mock(return_value=SimpleNamespace(model_uri="runs:/x"))
    monkeypatch.setattr(subject.mlflow.pyfunc, "log_model", logged)
    monkeypatch.setattr(subject.mlflow, "register_model",
        Mock(return_value=SimpleNamespace(version=1)))
    monkeypatch.setattr(subject.mlflow, "get_tracking_uri", lambda: "tracking")
    monkeypatch.setattr(subject.mlflow, "active_run", lambda: SimpleNamespace(
        data=SimpleNamespace(tags={}, metrics={}, params={})
    ))
    monkeypatch.setattr(subject, "MlflowClient",
        lambda _: SimpleNamespace(update_model_version=Mock()))
    monkeypatch.setattr(subject.bentoml.mlflow, "import_model", Mock())
    X = pd.DataFrame({"x": [1., 2.]})
    y = pd.DataFrame({"y": [3., 4.]})
    subject.log_model("abc", SimpleNamespace(simulation_tag="x"), object(),
        {}, "id", X, y)
    infer.assert_called_once()
    assert logged.call_args.kwargs["signature"] is inferred


@pytest.mark.parametrize("cls", [
    subject.OptimisationModel, subject.SensitivityAnalysisModel,
    subject.AbcModel, subject.SnpeModel, subject.SurrogateModel,
])
def test_calibrators_reject_predict_before_loading(cls, model_context):
    with pytest.raises(ValueError, match="has not been loaded"):
        cls().predict(model_context, pd.DataFrame({"n_trials": [1]}))


@pytest.mark.parametrize("cls", [
    subject.OptimisationModel, subject.SensitivityAnalysisModel,
        subject.AbcModel,
])
def test_calibrators_load_joblib_artifacts(cls, model_context, monkeypatch):
    import joblib
    expected = object()
    load = Mock(return_value=expected)
    monkeypatch.setattr(joblib, "load", load)
    model_context.artifacts["calibrator"] = "fake-model.joblib"
    model = cls()
    model.load_context(model_context)
    load.assert_called_once_with("fake-model.joblib")
    assert model.calibrator is expected


@pytest.mark.parametrize("n_trials,expected", [(1, [1]), (2, [1, 2]), (5,
    [1, 2, 3]), (0, [])])
def test_optimisation_returns_best_trials(n_trials, expected, model_context):
    model = subject.OptimisationModel()
    trials = pd.DataFrame({"number": [3, 1, 2], "value": [9., 1., 5.]})
    model.calibrator = SimpleNamespace(
        trials_dataframe=Mock(return_value=trials)
    )
    output = model.predict(model_context,
        pd.DataFrame({"n_trials": [n_trials]}))
    assert output["number"].tolist() == expected
    assert output["value"].tolist() == sorted(output["value"].tolist())


@pytest.mark.parametrize("wanted,expected", [
    (["a"], ["a"]), (["c"], []), (["b", "a"], ["a", "b"]),
])
def test_sensitivity_filters_parameter_names(wanted, expected, model_context):
    model = subject.SensitivityAnalysisModel()
    model.calibrator = SimpleNamespace(
        total_si_df=pd.DataFrame({"name": ["a", "b"], "S1": [0.1, 0.9]})
    )
    output = model.predict(model_context, pd.DataFrame({"name": wanted}))
    assert output["name"].tolist() == expected


@pytest.mark.parametrize("times,expected", [
    ([-1], [0, 1, 2]), ([], [0, 1, 2]), ([1], [1]), ([0, 2], [0, 2]),
])
def test_abc_selects_requested_iterations(times, expected, model_context):
    model = subject.AbcModel()
    model.calibrator = pd.DataFrame({"t": [0, 1, 2], "score": [0.1, 0.2, 0.3]})
    output = model.predict(model_context, pd.DataFrame({"t": times}))
    assert output["t"].tolist() == expected


def test_snpe_loads_all_artifacts(model_context, monkeypatch):
    import joblib
    artifacts = {
        "inference": "f-inference", "posterior": "f-posterior",
        "parameter_intervals": "f-intervals", "statistics_list": "f-stats",
    }
    objects = {
        "f-inference": object(), "f-posterior": object(),
        "f-intervals": {"a": [0, 1]},
        "f-stats": [{"statistic_name": "root_number", "statistic_value": 3.0}],
    }
    model_context.artifacts = artifacts
    monkeypatch.setattr(joblib, "load", lambda name: objects[name])
    model = subject.SnpeModel()
    model.load_context(model_context)
    assert model.inference is objects["f-inference"]
    assert model.posterior is objects["f-posterior"]
    assert model.parameter_intervals == objects["f-intervals"]
    assert model.statistics_df.statistic_name.tolist() == ["root_number"]


def _loaded_snpe():
    model = subject.SnpeModel()
    model.inference = object()
    sample = Mock(return_value=torch.full((100, 2), 0.5))
    model.posterior = SimpleNamespace(sample=sample)
    model.parameter_intervals = {"a": object(), "b": object()}
    model.statistics_df = pd.DataFrame({"statistic_name": ["length", "count"]})
    return model, sample


def test_snpe_observation_order_is_aligned_to_training_stats(model_context):
    model, sample = _loaded_snpe()
    model_context.model_config = {"inference_type": "summary_statistics"}
    # Input is in reverse order; posterior input must use [length, count].
    observations = pd.DataFrame({
        "statistic_name": ["count", "length", "unused"],
        "statistic_value": [20., 10., 500.],
    })
    result = model.predict(model_context, observations)
    assert result.shape == (100, 2)
    assert list(result.columns) == ["a", "b"]
    np.testing.assert_allclose(sample.call_args.kwargs["x"], [10., 20.])
    assert sample.call_args.args == ((100,),)


def test_snpe_returns_empty_when_no_observations_match(model_context):
    model, sample = _loaded_snpe()
    model_context.model_config = {"inference_type": "summary_statistics"}
    observations = pd.DataFrame({"statistic_name": ["other"],
        "statistic_value": [5.]})
    assert model.predict(model_context, observations).empty
    sample.assert_not_called()


def test_snpe_explicitly_rejects_output_inference(model_context):
    model, _ = _loaded_snpe()
    model_context.model_config = {"inference_type": "outputs"}
    with pytest.raises(NotImplementedError, match="outputs unsupported"):
        model.predict(model_context, pd.DataFrame())


class _FakeGP:
    def __init__(self):
        self.loaded_state = None
        self.evaluated = False
        self.last_x = None

    def double(self):
        return self

    def load_state_dict(self, state):
        self.loaded_state = state

    def eval(self):
        self.evaluated = True

    def __call__(self, X):
        self.last_x = X
        return X


class _FakeLikelihood:
    def double(self):
        return self

    def __call__(self, x):
        n = len(x)
        return SimpleNamespace(
            mean=torch.tensor([0.25, 0.50][:n], dtype=torch.double),
            confidence_region=lambda: (
                torch.tensor([0.10, 0.30][:n], dtype=torch.double),
                torch.tensor([0.40, 0.80][:n], dtype=torch.double),
            ),
        )


def _loaded_surrogate(monkeypatch, model_context):
    model = subject.SurrogateModel()
    gp = _FakeGP()
    monkeypatch.setattr(subject, "SingleTaskVariationalGPModel", lambda _: gp)
    monkeypatch.setattr(subject.gpytorch.likelihoods, "GaussianLikelihood",
        lambda: _FakeLikelihood())
    monkeypatch.setattr(subject.torch, "load", lambda path: (
        {"weights": 1} if path == "state" else torch.tensor([[0.], [1.]])
    ))
    X_scaler = MinMaxScaler().fit(np.array([[0.], [10.]]))
    Y_scaler = MinMaxScaler().fit(np.array([[10.], [30.]]))
    objects = {"x": X_scaler, "y": Y_scaler, "cols": ["feature"]}
    import joblib
    monkeypatch.setattr(joblib, "load", lambda path: objects[path])
    model_context.artifacts = dict(
        state_dict="state", inducing_points="inducing",
        X_scaler="x", Y_scaler="y", column_names="cols",
    )
    model_context.model_config = {"surrogate_type": "cost_emulator"}
    return model, gp


def test_surrogate_model_loads_artifacts_without_training(monkeypatch,
    model_context):
    model, gp = _loaded_surrogate(monkeypatch, model_context)
    model.load_context(model_context)
    assert gp.loaded_state == {"weights": 1}
    assert gp.evaluated
    assert model.column_names == ["feature"]
    assert model.state_dict == {"weights": 1}


def test_surrogate_model_predicts_inverse_scaled_bounds(monkeypatch,
    model_context):
    model, gp = _loaded_surrogate(monkeypatch, model_context)
    model.load_context(model_context)
    inputs = pd.DataFrame({"feature": [5., 10.], "ignored": [123, 456]})
    result = model.predict(model_context, inputs)
    assert list(result.columns) == ["discrepancy", "lower_bound",
        "upper_bound"]
    np.testing.assert_allclose(result.discrepancy, [15., 20.])
    np.testing.assert_allclose(result.lower_bound, [12., 16.])
    np.testing.assert_allclose(result.upper_bound, [18., 26.])
    np.testing.assert_allclose(gp.last_x.numpy().flatten(), [0.5, 1.0])


def test_graph_extractor_encodes_graph_and_calls_npe(monkeypatch):
    class FakeSAGE(torch.nn.Module):
        def __init__(self, in_channels, out_channels, **kwargs):
            super().__init__()
            self.proj = torch.nn.Linear(in_channels, out_channels)
        def forward(self, x, edge_index):
            return self.proj(x)

    class FakeNPE:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.flow = Mock(return_value="flow-distribution")
            self.forward = Mock(return_value=torch.tensor(7.0))
        def __call__(self, theta, x):
            assert tuple(x.shape) == (2,)
            return self.forward(theta, x)

    monkeypatch.setattr(subject, "SAGEConv", FakeSAGE)
    monkeypatch.setattr(subject, "NPE", FakeNPE)
    monkeypatch.setattr(subject, "global_max_pool", lambda x,
        batch: x.max(dim=0, keepdim=True).values)

    model = subject.GraphFlowFeatureExtractor(
        theta_dim=3, organ_keys=["plant_id"], hidden_features=(8, 8),
        transforms=(2, 2), organ_features=["length", "diameter"],
    )
    graph = (torch.tensor([[1., 2.], [2., 3.], [3., 4.]]), torch.tensor([[0,
        1], [1, 2]]))
    embedding = model.encode(graph)
    assert tuple(embedding.shape) == (2,)
    assert torch.isfinite(embedding).all()
    assert model.forward(torch.ones(3), graph).item() == 7.0
    assert model.flow(graph) == "flow-distribution"
