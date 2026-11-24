"""The scalar dashboard must validate the same intervals the worker samples."""
from pathlib import Path

import pytest
import yaml

from deeprootgen.form.optimisation import optimisation_statistics, validate_optimisation_form


@pytest.fixture
def form_values():
    path = Path(__file__).resolve().parents[1] / "app/conf/calibration_form/common.yaml"
    components = yaml.safe_load(path.read_text())["components"]
    values = {
        "parameter_intervals": {},
        "statistics_comparison": {
            "summary_statistics": ["root_number"],
            "distance_metrics": ["mean_absolute_error"],
        },
        "summary_statistics": [{"statistic_name": "root_number", "statistic_value": 3}],
    }
    for item in components["parameters"]["children"]:
        name = item["param"]
        if "data_type" in item:
            values["parameter_intervals"][name] = {
                "lower_bound": item["min_value"],
                "upper_bound": item["max_value"],
                "data_type": item["data_type"],
            }
        else:
            values[name] = item["kwargs"]["value"]
    values["calibration_parameters"] = {
        item["param"]: item["kwargs"]["value"]
        for item in components["optimisation"]["children"]
        if not item.get("statistic_parameter")
    }
    return values


def test_dashboard_defaults_resolve(form_values):
    model = validate_optimisation_form(form_values)
    assert model.calibration_parameters["n_trials"] > model.calibration_parameters["n_startup_trials"]
    assert 0 <= model.parameter_intervals.gravitropism.lower_bound <= 1
    assert 0 <= model.parameter_intervals.gravitropism.upper_bound <= 1


@pytest.mark.parametrize("name,field,value,message", [
    ("primary_root_count", "upper_bound", 10.5, "integer bounds"),
    ("gravitropism", "upper_bound", 9, "between 0 and 1"),
    ("min_primary_length", "upper_bound", 30, "range for min_primary_length"),
    ("diameter_reduction", "upper_bound", float("nan"), "bounds and type"),
])
def test_preflight_rejects_invalid_parameter_ranges(form_values, name, field, value, message):
    form_values["parameter_intervals"][name][field] = value
    with pytest.raises(ValueError, match=message):
        validate_optimisation_form(form_values)


def test_preflight_rejects_unavailable_spatial_objective(form_values):
    options = {item["value"] for item in optimisation_statistics()}
    assert {"root_number", "total_length", "total_weight"} <= options
    assert "root_length_density" not in options
    assert "depth_distribution" not in options
    form_values["statistics_comparison"]["stat_by_soil_layer"] = True
    with pytest.raises(ValueError, match="layer and column"):
        validate_optimisation_form(form_values)


def test_preflight_rejects_missing_or_nonfinite_target(form_values):
    form_values["summary_statistics"][0]["statistic_value"] = float("inf")
    with pytest.raises(ValueError, match="finite numeric value"):
        validate_optimisation_form(form_values)
