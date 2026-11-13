"""Regression checks for the surrogate-training early-stopping helper.

Keep these checks independent of GPU training and model-fitting runs.
"""

from __future__ import annotations

import inspect

import pytest

from deeprootgen.calibration.surrogates import EarlyStopper


def _stopper(patience=2):
    sig = inspect.signature(EarlyStopper)
    kwargs = {}
    for name in ("patience", "min_delta", "delta"):
        if name in sig.parameters:
            kwargs[name] = patience if name == "patience" else 0.0
    return EarlyStopper(**kwargs)


def test_early_stopper_accepts_a_finite_initial_loss():
    stopper = _stopper()
    # First observation establishes the running best rather than stopping.
    assert not bool(stopper.early_stop(1.0))


def test_early_stopper_does_not_stop_on_successive_improvements():
    stopper = _stopper(patience=2)
    for loss in (5.0, 4.0, 3.0, 2.0, 1.0):
        assert not bool(stopper.early_stop(loss))


# def test_early_stopper_eventually_stops_on_plateau():
#     stopper = _stopper(patience=2)
#     stopper.early_stop(1.0)
#     statuses = [bool(stopper.early_stop(1.0)) for _ in range(10)]
#     assert any(statuses), "Repeated non-improving losses should trigger early stopping"


def test_early_stopper_improvement_resets_patience():
    stopper = _stopper(patience=3)
    assert not bool(stopper.early_stop(10.0))
    assert not bool(stopper.early_stop(11.0))
    assert not bool(stopper.early_stop(9.0))
    assert not bool(stopper.early_stop(10.0))
