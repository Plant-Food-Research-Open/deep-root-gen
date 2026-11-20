"""Preflight the whole-root scalar optimisation form before Prefect dispatch."""

from math import isfinite

from ..data_model import RootCalibrationModel
from ..data_model.canonical import RootConfig
from ..data_model.resolution import resolve_config
from ..statistics import get_distance_metrics, get_summary_statistics


SCALAR_STATISTICS = {
    "root_number", "total_volume", "average_volume", "total_length",
    "average_length", "total_diameter", "average_diameter",
    "total_specific_root_length", "average_specific_root_length",
    "total_weight", "average_weight", "convex_hull_area", "convex_hull_volume",
}
INTEGER_PARAMETERS = {"max_order", "primary_root_count", "daughters_per_parent", "segments_per_root"}


def optimisation_statistics():
    """Expose scalar objectives for which the dashboard can supply matching data."""
    return [option for option in get_summary_statistics() if option["value"] in SCALAR_STATISTICS]


def _validate_space(model):
    intervals = model.parameter_intervals.model_dump()
    endpoints = ({}, {})
    for name, interval in intervals.items():
        low, high = interval["lower_bound"], interval["upper_bound"]
        integer = name in INTEGER_PARAMETERS
        kind = "discrete" if integer else "continuous"
        if interval["data_type"] != kind or not (isfinite(low) and isfinite(high) and low <= high):
            raise ValueError(f"Check the bounds and type for {name}.")
        if integer and not (low.is_integer() and high.is_integer()):
            raise ValueError(f"Use integer bounds for {name}.")
        for point, value in zip(endpoints, (low, high)):
            point[name] = int(value) if integer else value

    for lo, hi in (("min_primary_length", "max_primary_length"), ("min_lateral_length", "max_lateral_length")):
        if endpoints[1][lo] > endpoints[0][hi]:
            raise ValueError(f"The range for {lo} must end at or below the start of {hi}.")
    if not 0 <= endpoints[0]["gravitropism"] <= endpoints[1]["gravitropism"] <= 1:
        raise ValueError("Set both gravitropism bounds between 0 and 1.")
    for point in endpoints:
        resolve_config(RootConfig(schema_version=4, random_seed=model.random_seed, parameters=point))


def _validate_targets(model):
    compare = model.statistics_comparison
    if compare is None or not compare.summary_statistics or not compare.distance_metrics:
        raise ValueError("Select at least one statistic and one distance metric.")
    if compare.stat_by_soil_layer or compare.stat_by_soil_column:
        raise ValueError("Turn off the layer and column switches for whole-root optimisation.")
    if set(compare.summary_statistics) - SCALAR_STATISTICS:
        raise ValueError("Use a whole-root scalar statistic for this page.")
    if set(compare.distance_metrics) - {d["value"] for d in get_distance_metrics()}:
        raise ValueError("Select a recognized distance metric.")
    selected = set(compare.summary_statistics)
    rows = [row for row in model.summary_statistics or [] if row.statistic_name in selected]
    if {row.statistic_name for row in rows} != selected or any(not isfinite(row.statistic_value) for row in rows):
        raise ValueError("The upload must contain a finite numeric value for every selected statistic.")
    if any(row.x is not None or row.y is not None or row.core_radius is not None
           or row.z_lower_bound not in (0, None) or row.z_upper_bound not in (0, None) for row in rows):
        raise ValueError("Use whole-root observations without coordinates or depth bounds.")


def validate_optimisation_form(values):
    """Raise a meaningful ValueError for an invalid form before dispatch."""
    model = RootCalibrationModel.model_validate(values)
    _validate_targets(model)
    _validate_space(model)
    counts = model.calibration_parameters
    bounds = {"n_trials": 2, "n_startup_trials": 0, "n_ei_candidates": 1, "n_jobs": 1}
    for name, minimum in bounds.items():
        value = counts.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not float(value).is_integer() or value < minimum:
            raise ValueError(f"{name} must be a whole number greater than or equal to {minimum}.")
        counts[name] = int(value)
    if counts["n_startup_trials"] >= counts["n_trials"]:
        raise ValueError("Use fewer startup trials than total trials to run adaptive search.")
    return model
