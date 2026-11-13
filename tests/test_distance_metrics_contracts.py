"""Numerical contracts for DeepRootGen distance metrics.

The tests deliberately use exact, small numeric examples and test the public
metric classes rather than reimplementing any source code.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from deeprootgen.statistics import distance_metrics as metrics


METRICS = (
    "L1Norm",
    "MeanSquaredError",
    "MeanAbsoluteError",
    "RootMeanSquaredError",
    "MedianAbsoluteError",
    "MeanAbsolutePercentageError",
    "MeanPinballLoss",
)

SYMMETRIC_METRICS = (
    "L1Norm",
    "MeanSquaredError",
    "MeanAbsoluteError",
    "RootMeanSquaredError",
    "MedianAbsoluteError",
)


def _construct(name):
    """Pass a name/quantile only when the actual constructor requires one."""
    cls = getattr(metrics, name)
    sig = inspect.signature(cls)
    kwargs = {}
    for pname, p in sig.parameters.items():
        if p.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
            continue
        if p.default is not inspect.Parameter.empty:
            continue
        if pname in ("name", "metric_name", "statistic"):
            kwargs[pname] = name
        elif pname in ("alpha", "quantile", "q"):
            kwargs[pname] = 0.5
        else:
            pytest.fail(
                f"{name} has an unknown required constructor argument: {pname}. "
                "Update the test fixture to match the module's public API."
            )
    return cls(**kwargs)


def _value(name, a, b):
    obj = _construct(name)
    answer = obj.calculate(np.asarray(a, dtype=float), np.asarray(b, dtype=float))
    result = np.asarray(answer)
    assert result.size == 1, f"{name}.calculate() should produce one scalar distance"
    return float(result.reshape(-1)[0])


@pytest.mark.parametrize("name", METRICS)
def test_identical_arrays_have_zero_discrepancy(name):
    values = [1.0, 2.0, 4.0]
    assert _value(name, values, values) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("name", METRICS)
def test_nonidentical_positive_arrays_have_finite_nonnegative_discrepancy(name):
    result = _value(name, [1.0, 2.0, 4.0], [2.0, 4.0, 6.0])
    assert np.isfinite(result)
    assert result >= 0.0


@pytest.mark.parametrize("name", SYMMETRIC_METRICS)
def test_symmetric_distances_are_order_independent(name):
    a, b = [1.0, 2.0, 4.0], [2.0, 4.0, 7.0]
    assert _value(name, a, b) == pytest.approx(_value(name, b, a))


@pytest.mark.parametrize(
    "name,expected",
    [
        ("L1Norm", 7.0),
        ("MeanSquaredError", 7.0),
        ("MeanAbsoluteError", 7.0 / 3.0),
        ("RootMeanSquaredError", np.sqrt(7.0)),
        ("MedianAbsoluteError", 2.0),
    ],
)
def test_known_numerical_discrepancies(name, expected):
    # Absolute errors = 1, 2, 4.
    assert _value(name, [1.0, 2.0, 4.0], [2.0, 4.0, 8.0]) == pytest.approx(expected)


@pytest.mark.parametrize("name", SYMMETRIC_METRICS)
def test_error_does_not_decrease_after_scaling_residuals(name):
    true = np.array([2.0, 3.0, 5.0])
    error = np.array([0.5, 1.0, 2.0])
    small = _value(name, true, true + error)
    large = _value(name, true, true + 2 * error)
    assert large > small
