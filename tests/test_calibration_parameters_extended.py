"""Test calibration sampling utilities without starting a Dash server."""

from types import SimpleNamespace

import numpy as np
import pytest
import torch

for dependency in ("dash", "torch"):
    pytest.importorskip(dependency)

from deeprootgen.calibration import parameters as subject  # noqa: E402


@pytest.fixture
def sampling_inputs():
    intervals = {
        "elongation": {
            "lower_bound": 1.0,
            "upper_bound": 3.0,
            "data_type": "continuous",
        },
        "branches": {"lower_bound": 2, "upper_bound": 7, "data_type": "discrete"},
        "diameter": {
            "lower_bound": 10.0,
            "upper_bound": 20.0,
            "data_type": "continuous",
        },
    }
    return SimpleNamespace(
        statistics_comparison=SimpleNamespace(
            exclude_parameters=None, include_parameters=None
        ),
        parameter_intervals=SimpleNamespace(dict=lambda: intervals),
        calibration_parameters={
            "n_simulations": 8,
            "n_validation_simulations": 3,
            "n_holdout_simulations": 2,
        },
        random_seed=23,
    )


@pytest.mark.parametrize(
    "batch_shape,expected", [((), (2,)), ((1,), (2,)), ((7,), (7, 2))]
)
def test_prior_collection_values_and_shape(batch_shape, expected):
    torch.manual_seed(4)
    priors = [
        torch.distributions.Uniform(0.0, 1.0),
        torch.distributions.Uniform(3.0, 4.0),
    ]
    values = subject.PriorCollection(priors).sample(batch_shape)
    # sample((1,)) has a squeeze() edge case; check its element count.
    if batch_shape == (1,):
        assert values.numel() == 2
    else:
        assert tuple(values.shape) == expected
    values = values.reshape(-1, 2)
    assert bool(torch.all((values[:, 0] >= 0) & (values[:, 0] <= 1)))
    assert bool(torch.all((values[:, 1] >= 3) & (values[:, 1] <= 4)))


def test_prior_collection_keeps_distributions():
    prior = torch.distributions.Normal(0, 1)
    collection = subject.PriorCollection([prior])
    assert collection.priors[0] is prior


def test_get_simulation_parameters_uses_only_range_sliders(monkeypatch):
    children = [
        {"class_name": "dash.dcc.RangeSlider", "param": "a", "label": "A"},
        {"class_name": "dash.dcc.Input", "param": "skip", "label": "Skip"},
        {"class_name": "dash.dcc.RangeSlider", "param": "b", "label": "B"},
    ]
    form = SimpleNamespace(components={"parameters": {"children": children}})
    app = SimpleNamespace(settings={"custom_form": form})
    monkeypatch.setattr(subject, "get_app", lambda: app)
    assert subject.get_simulation_parameters("custom_form") == [
        {"value": "a", "label": "A"},
        {"value": "b", "label": "B"},
    ]


def test_get_simulation_parameters_empty(monkeypatch):
    form = SimpleNamespace(components={"parameters": {"children": []}})
    app = SimpleNamespace(settings={"calibration_form": form})
    monkeypatch.setattr(subject, "get_app", lambda: app)
    assert subject.get_simulation_parameters() == []


def test_latin_hypercube_sample_count_splits_and_unique_ids(sampling_inputs):
    sampled = subject.lhc_sample(sampling_inputs)
    assert sampled.shape[0] == 13
    assert sampled["sim_ids"].nunique() == 13
    assert sampled.training_data_split.value_counts().to_dict() == {0: 8, 1: 3, 2: 2}
    assert set(sampled.columns) == {
        "elongation",
        "branches",
        "diameter",
        "sim_ids",
        "training_data_split",
    }


@pytest.mark.parametrize(
    "name,lo,hi",
    [("elongation", 1.0, 3.0), ("branches", 2, 7), ("diameter", 10.0, 20.0)],
)
def test_latin_hypercube_respects_bounds(sampling_inputs, name, lo, hi):
    sampled = subject.lhc_sample(sampling_inputs)
    assert sampled[name].between(lo, hi).all()


def test_latin_hypercube_casts_discrete_parameters(sampling_inputs):
    sampled = subject.lhc_sample(sampling_inputs)
    assert sampled["branches"].dtype.kind in "iu"
    assert (sampled["branches"] == sampled["branches"].astype(int)).all()


@pytest.mark.parametrize(
    "include,exclude,expected_midpoint",
    [
        (["elongation"], None, {"branches": 4, "diameter": 15.0}),
        (None, ["diameter"], {"diameter": 15.0}),
        (["elongation", "branches"], ["branches"], {"branches": 4, "diameter": 15.0}),
    ],
)
def test_unselected_parameters_use_midpoints(
    sampling_inputs, include, exclude, expected_midpoint
):
    sampling_inputs.statistics_comparison.include_parameters = include
    sampling_inputs.statistics_comparison.exclude_parameters = exclude
    sampled = subject.lhc_sample(sampling_inputs)
    for name, midpoint in expected_midpoint.items():
        assert np.allclose(sampled[name], midpoint)
    if include == ["elongation"]:
        assert sampled["elongation"].nunique() > 1


def test_latin_hypercube_seed_controls_values(sampling_inputs):
    first = subject.lhc_sample(sampling_inputs)
    second = subject.lhc_sample(sampling_inputs)
    # Pandas shuffles rows without a fixed random_state, and UUIDs are random.
    for name in ["elongation", "branches", "diameter"]:
        np.testing.assert_allclose(np.sort(first[name]), np.sort(second[name]))


def test_latin_hypercube_preserves_empty_validation_split(sampling_inputs):
    sampling_inputs.calibration_parameters["n_validation_simulations"] = 0
    sampled = subject.lhc_sample(sampling_inputs)
    assert len(sampled) == 10
    assert 1 not in set(sampled.training_data_split)
