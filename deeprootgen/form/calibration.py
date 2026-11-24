"""Validate the legacy calibration forms before any Prefect submission.

The checks mirror what each worker flow later samples or reads, so a form that
passes here does not fail on an input-shape problem in the worker. They do not
change any sampler, prior, objective or default.
"""

import base64
import csv
from io import StringIO
from math import isfinite

from ..data_model import RootCalibrationModel
from .optimisation import INTEGER_PARAMETERS, _validate_space, validate_optimisation_form

# Minimum whole-number settings per task (n_jobs is checked separately).
COUNTS = {
    "sensitivity_analysis": {"n_samples": 1},
    "abc": {
        "max_nr_populations": 1,
        "start_nr_particles": 1,
        "max_walltime": 1,
        "max_total_nr_simulations": 1,
    },
    "snpe": {
        "n_epochs": 1,
        "n_simulations": 1,
        "pp_samples": 1,
        "nn_num_hidden_features": 1,
        "nn_num_transforms": 1,
        "sbc_draws": 1,
    },
    "surrogate": {
        "n_epochs": 1,
        "early_stopping_patience": 0,
        "num_inducing_points": 1,
        "n_simulations": 1,
        "n_validation_simulations": 1,
        "n_holdout_simulations": 1,
    },
}
POSITIVE = {"snpe": ("lr",), "surrogate": ("lr",)}
NONNEGATIVE = {"abc": ("minimum_epsilon",)}
# Methods whose samplers or priors need lower < upper for these intervals.
STRICT = {
    "sensitivity_analysis": "all",
    "snpe": "all",
    "abc": "continuous",
    "surrogate": "sampled",
}
NODE_COLUMNS = {"node_id", "parent_id"}
EDGE_COLUMNS = {"parent_id", "child_id"}
METHOD_NAMES = {
    "sensitivity_analysis": "Sobol sampling",
    "abc": "The ABC uniform prior",
    "snpe": "The SNPE prior",
    "surrogate": "Latin-hypercube sampling",
}


def statistics_rows(rows: list[dict] | None) -> list[dict]:
    """Return statistics rows or explain the required CSV header."""
    if not rows:
        raise ValueError(
            "Load statistics data first: a CSV with columns statistic_name,statistic_value."
        )
    missing = {"statistic_name", "statistic_value"} - set(rows[0])
    if missing:
        raise ValueError(
            "The statistics CSV needs columns statistic_name,statistic_value; missing "
            + ", ".join(sorted(missing))
            + "."
        )
    return rows


def _csv_columns(content: str, label: str) -> set[str]:
    try:
        text = base64.b64decode(content, validate=True).decode("utf-8")
        header = next(csv.reader(StringIO(text)))
    except (ValueError, UnicodeDecodeError, StopIteration) as exc:
        raise ValueError(f"The {label} upload is not a readable CSV.") from exc
    return {name.strip() for name in header}


def _validate_graph_upload(model: RootCalibrationModel) -> None:
    if not model.observed_data_content or not model.raw_edge_content:
        raise ValueError(
            "Graph mode needs both node and edge CSVs from the same Simulation run. "
            "Upload them under Load simulation data and Load edge data, or turn on summary statistics."
        )
    for content, label, required in (
        (model.observed_data_content, "node", NODE_COLUMNS),
        (model.raw_edge_content, "edge", EDGE_COLUMNS),
    ):
        missing = required - _csv_columns(content, label)
        if missing:
            raise ValueError(f"The {label} CSV is missing columns: {', '.join(sorted(missing))}.")


def _validate_statistics(task: str, model: RootCalibrationModel) -> None:
    compare = model.statistics_comparison
    if compare is None or not compare.summary_statistics:
        raise ValueError("Select at least one summary statistic.")
    if task != "snpe" and not compare.distance_metrics:
        raise ValueError("Select a distance metric.")
    selected = set(compare.summary_statistics)
    rows = [row for row in model.summary_statistics or [] if row.statistic_name in selected]
    present = {row.statistic_name for row in rows}
    if present != selected:
        raise ValueError(
            "The statistics upload has no value for: " + ", ".join(sorted(selected - present)) + "."
        )
    if any(not isfinite(row.statistic_value) for row in rows):
        raise ValueError("Every selected statistic needs a finite numeric value in the upload.")


def _validate_counts(task: str, model: RootCalibrationModel) -> None:
    counts = model.calibration_parameters
    for name, minimum in COUNTS.get(task, {}).items():
        value = counts.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not float(value).is_integer() or value < minimum:
            raise ValueError(f"{name} must be a whole number of at least {minimum}.")
        counts[name] = int(value)
    if "n_jobs" in counts:
        value = counts["n_jobs"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not float(value).is_integer() or value == 0 or value < -1:
            raise ValueError("n_jobs must be -1 (all CPUs) or a positive whole number.")
        counts["n_jobs"] = int(value)
    for name in POSITIVE.get(task, ()):
        value = counts.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a positive number.")
    for name in NONNEGATIVE.get(task, ()):
        value = counts.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
            raise ValueError(f"{name} must be zero or a positive number.")


def _sampled(task: str, model: RootCalibrationModel) -> set[str]:
    intervals = model.parameter_intervals.model_dump()
    if task != "surrogate":
        return set(intervals)
    compare = model.statistics_comparison
    exclude = set(compare.exclude_parameters or []) if compare else set()
    include = set(compare.include_parameters or []) - exclude if compare else set()
    return {name for name in intervals if name not in exclude and (not include or name in include)}


def _validate_widths(task: str, model: RootCalibrationModel) -> None:
    rule = STRICT.get(task)
    if rule is None:
        return
    intervals = model.parameter_intervals.model_dump()
    sampled = _sampled(task, model)
    if task == "surrogate" and not sampled:
        raise ValueError("Include at least one parameter to sample.")
    for name, interval in intervals.items():
        if name not in sampled:
            continue
        if rule == "continuous" and name in INTEGER_PARAMETERS:
            continue
        if interval["lower_bound"] >= interval["upper_bound"]:
            raise ValueError(
                f"{METHOD_NAMES[task]} needs a lower bound below the upper bound for {name}."
            )


def validate_calibration_form(task: str, values: dict) -> RootCalibrationModel:
    """Raise a readable ValueError for an invalid calibration form."""
    if task == "optimisation":
        return validate_optimisation_form(values)
    model = RootCalibrationModel.model_validate(values)
    compare = model.statistics_comparison
    use_summary = True if compare is None else compare.use_summary_statistics is not False
    if task == "surrogate" and not use_summary:
        raise ValueError(
            "The surrogate flow trains only the summary-statistic cost emulator. Graph-mode "
            "surrogate training is not implemented; turn on summary statistics."
        )
    if use_summary:
        _validate_statistics(task, model)
    else:
        _validate_graph_upload(model)
    _validate_counts(task, model)
    _validate_space(model)
    _validate_widths(task, model)
    return model


def describe_calibration(task: str, model: RootCalibrationModel) -> list[str]:
    """Summarize a validated request without submitting it."""
    intervals = model.parameter_intervals.model_dump()
    varying = [k for k, v in intervals.items() if v["lower_bound"] != v["upper_bound"]]
    compare = model.statistics_comparison
    lines = [f"Search ranges for {len(varying)} parameters: " + (", ".join(varying) or "none")]
    if compare is not None and compare.use_summary_statistics is False:
        lines.append("Graph mode with uploaded node and edge tables")
    elif compare is not None:
        metrics = list(compare.distance_metrics or [])
        lines.append("Statistics " + ", ".join(list(compare.summary_statistics or []) + metrics))
    counts = {k: v for k, v in model.calibration_parameters.items() if not isinstance(v, bool)}
    lines.append("Settings " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    return lines
