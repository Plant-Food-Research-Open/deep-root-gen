"""Numerical surrogate data-preparation and training-loop contracts."""
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
import torch
from torch.utils.data import DataLoader, TensorDataset

for dependency in ("gpytorch", "torch"):
    pytest.importorskip(dependency)

from deeprootgen.calibration import surrogates as subject


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "feature_a": [0., 1., 2., 3., 4., 5., 6., 7., 8.],
        "feature_b": [0., 2., 4., 1., 3., 5., 2., 5., 8.],
        "constant": [99] * 9,
        "discrepancy": [10., 20., 30., 5., 15., 25., 40., 50., 60.],
        "sim_ids": [f"sim-{k}" for k in range(9)],
        "training_data_split": [0, 0, 0, 1, 1, 1, 2, 2, 2],
    })


def test_prepare_surrogate_data_counts_training_rows(sample_df):
    loaders, scalers, cleaned, num_data = subject.prepare_surrogate_data(
        sample_df, batch_size=2
    )
    assert num_data == 3
    assert len(loaders) == 3
    assert len(scalers) == 2
    assert "constant" not in cleaned
    assert "sim_ids" in cleaned


def test_prepare_surrogate_data_scales_using_training_only(sample_df):
    loaders, (xs, ys), _, _ = subject.prepare_surrogate_data(sample_df)
    train_x, train_y = next(iter(loaders[0]))
    np.testing.assert_allclose(train_x.numpy(),
        xs.transform(sample_df.iloc[:3][["feature_a", "feature_b"]]))
    np.testing.assert_allclose(train_y.numpy(), [0., 0.5, 1.])
    assert train_x.dtype == torch.float64
    assert train_y.dtype == torch.float64
    assert ys.data_min_[0] == 10. and ys.data_max_[0] == 30.
    # Holdout is not fitted separately, so its scaled X can exceed 1.
    test_x, _ = next(iter(loaders[2]))
    assert torch.max(test_x) > 1.


def test_prepare_surrogate_data_respects_batch_size(sample_df):
    loaders, _, _, _ = subject.prepare_surrogate_data(sample_df, batch_size=2)
    assert [len(batch[0]) for batch in loaders[0]] == [2, 1]
    assert [len(batch[0]) for batch in loaders[1]] == [2, 1]


def test_prepare_surrogate_data_supports_multiple_outputs(sample_df):
    sample_df["secondary"] = sample_df["discrepancy"] * 2
    loaders, scalers, _, n = subject.prepare_surrogate_data(
        sample_df, output_names=["discrepancy", "secondary"], batch_size=4
    )
    x, y = next(iter(loaders[0]))
    assert n == 3
    assert tuple(y.shape) == (3, 2)
    assert tuple(x.shape) == (3, 2)
    np.testing.assert_allclose(y.numpy(), [[0., 0.], [0.5, 0.5], [1., 1.]])
    assert scalers[1].n_features_in_ == 2


@pytest.mark.parametrize("patience,losses,expected", [
    (1, [1., 2.], [False, True]),
    (2, [1., 1.2, 1.3], [False, False, True]),
    (2, [3., 4., 2., 2.5, 3.], [False, False, False, False, True]),
])
def test_early_stopper_counts_worsening_losses(patience, losses, expected):
    stopper = subject.EarlyStopper(patience=patience)
    assert [stopper.early_stop(loss) for loss in losses] == expected


def test_early_stopper_resets_on_improvement():
    stopper = subject.EarlyStopper(patience=2)
    stopper.early_stop(3.)
    stopper.early_stop(4.)
    assert stopper.counter == 1
    assert stopper.early_stop(2.) is False
    assert stopper.counter == 0
    assert stopper.min_validation_loss == pytest.approx(2.)


def test_early_stopper_min_delta_requires_meaningful_improvement():
    stopper = subject.EarlyStopper(patience=2, min_delta=0.25)

    assert not stopper.early_stop(1.0)

    # Improvement of 0.1 is insufficient.
    assert not stopper.early_stop(0.9)
    assert stopper.counter == 1

    # Improvement of 0.3 resets patience.
    assert not stopper.early_stop(0.7)
    assert stopper.counter == 0
    assert stopper.min_validation_loss == pytest.approx(0.7)

    # Two consecutive plateaus trigger stopping.
    assert not stopper.early_stop(0.7)
    assert stopper.early_stop(0.7)

def test_early_stopper_plateau_should_eventually_stop():
    stopper = subject.EarlyStopper(patience=2)

    assert not stopper.early_stop(1.0)
    assert not stopper.early_stop(1.0)
    assert stopper.early_stop(1.0)


def _linear_training_fixture():
    model = torch.nn.Linear(1, 1)
    with torch.no_grad():
        model.weight.fill_(0.0)
        model.bias.fill_(0.0)
    x = torch.tensor([[0.], [1.], [2.]], dtype=torch.float32)
    y = torch.tensor([[0.], [1.], [2.]], dtype=torch.float32)
    loader = DataLoader(TensorDataset(x, y), batch_size=3)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.1)
    # training_loop negates the ELBO-like objective.
    def objective(output, target):
        return -torch.mean((output - target) ** 2)
    return model, loader, optimizer, objective


def test_training_loop_updates_weights_and_returns_model():
    model, loader, optimizer, objective = _linear_training_fixture()
    result = subject.training_loop(model, loader, loader, n_epochs=3,
                                   mll=objective, optimizer=optimizer,
                                       silent=True)
    assert result is model
    assert model.weight.item() > 0


def test_training_loop_calls_optional_optimizers_and_scheduler():
    model, loader, optimizer, objective = _linear_training_fixture()
    ngd = SimpleNamespace(zero_grad=Mock(), step=Mock())
    scheduler = SimpleNamespace(step=Mock())
    subject.training_loop(model, loader, loader, n_epochs=2, mll=objective,
                          optimizer=optimizer, variational_ngd_optimizer=ngd,
                          scheduler=scheduler, silent=True)
    assert ngd.zero_grad.call_count == 2
    assert ngd.step.call_count == 2
    assert scheduler.step.call_count == 2


def test_training_loop_stops_when_early_stopper_requests():
    model, loader, optimizer, objective = _linear_training_fixture()
    stopper = SimpleNamespace(early_stop=Mock(return_value=True))
    result = subject.training_loop(model, loader, loader, n_epochs=8,
        mll=objective,
                                   optimizer=optimizer,
                                       early_stopper=stopper, silent=True)
    assert result is model
    stopper.early_stop.assert_called_once()


def test_training_loop_prints_progress_when_requested(capsys):
    model, loader, optimizer, objective = _linear_training_fixture()
    subject.training_loop(model, loader, loader, n_epochs=1, mll=objective,
                          optimizer=optimizer, silent=False)
    captured = capsys.readouterr().out
    assert "Training loss:" in captured
    assert "Validation loss:" in captured


def test_training_loop_zero_epochs_keeps_model_weights():
    model, loader, optimizer, objective = _linear_training_fixture()
    before = model.weight.detach().clone()
    assert subject.training_loop(model, loader, loader, n_epochs=0,
        mll=objective,
                                 optimizer=optimizer, silent=True) is model
    torch.testing.assert_close(before, model.weight)


def test_variational_gp_forward_has_finite_mean_and_covariance():
    inducing = torch.tensor([[0.], [1.], [2.]], dtype=torch.float64)
    gp = subject.SingleTaskVariationalGPModel(inducing).double()
    x = torch.tensor([[0.25], [0.75]], dtype=torch.float64)
    # Test .forward directly; this avoids invoking the variational strategy.
    prediction = gp.forward(x)
    assert prediction.mean.shape == torch.Size([2])
    assert torch.isfinite(prediction.mean).all()
    assert torch.all(prediction.variance > 0)
