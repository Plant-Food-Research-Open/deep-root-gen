"""Page-side submission feedback and run-state refresh for worker-backed pages."""

import os
from pathlib import Path
from uuid import UUID

from dash import Input, Output, State, callback, html, no_update

from ..pipeline.submission import (
    FINAL_STATES,
    SubmissionError,
    flow_run_url,
    new_nonce,
    read_run_state,
    submit,
)

TITLES = {
    "unreachable": "Prefect is unreachable",
    "missing_deployment": "Deployment missing",
    "rejected": "Request rejected",
    "uncertain": "Submission result uncertain",
}
MLFLOW_TASKS = {"simulation", "optimisation", "sensitivity_analysis", "abc", "snpe", "surrogate"}


def message(title: str, *lines, tone: str = "info") -> html.Div:
    """Return a status message that screen readers announce."""
    return html.Div(
        [html.Strong(title)] + [html.P(line, className="mb-1") for line in lines if line],
        role="status",
        className=f"text-{tone}" if tone != "info" else None,
    )


def validation_message(error: Exception) -> html.Div:
    """Turn a ValueError or pydantic error into readable lines."""
    issues = error.errors(include_input=False, include_url=False) if hasattr(error, "errors") else None
    if issues:
        lines = [
            f"{'.'.join(str(part) for part in issue['loc']) or 'form'}: {issue['msg']}" for issue in issues
        ]
    else:
        lines = [str(error)]
    if any("allocation_controls" in line for line in lines):
        lines.append(
            "Fine-root fraction targets are optional values in [0, 1]. Leave both blank for an "
            "untargeted run, or add parameters.allocation_controls with per-order scale bounds "
            "in Advanced settings (JSON)."
        )
    return message("Check the form. Nothing was submitted.", *lines, tone="danger")


def submit_from_page(
    task: str,
    payload: dict,
    simulation_runs: list | None,
    nonce: str | None,
    tag: str | None,
    **flow_options,
) -> tuple:
    """Submit and return (runs, message, nonce) for a page callback.

    The nonce rotates only after Prefect has definitely accepted the request, so
    a retry after an uncertain error reuses the idempotency key.
    """
    runs = list(simulation_runs or [])
    nonce = nonce or new_nonce()
    try:
        result = submit(task, dict(input_parameters=payload, **flow_options), nonce)
    except SubmissionError as error:
        tone = "warning" if error.kind == "uncertain" else "danger"
        return no_update, message(TITLES.get(error.kind, "Submission failed"), str(error), tone=tone), nonce

    if not any(run.get("flow_run_id") == result.flow_run_id for run in runs):
        runs.append(
            {
                "workflow": f"<a href='{result.url}' target='_blank'>{result.simulation_uuid}</a>",
                "task": task,
                "date": _now(),
                "tag": tag,
                "state": "Scheduled",
                "flow_run_id": result.flow_run_id,
                "simulation_uuid": result.simulation_uuid,
            }
        )
    title = "Queued" if result.created else "Already queued"
    return runs, message(
        f"{title}: {task} run {result.simulation_uuid}",
        html.A("Open the Prefect run", href=result.url, target="_blank", rel="noopener noreferrer"),
        f"Deployment {result.deployment}. The State column updates as the worker progresses.",
        *result.notes,
    ), new_nonce()


def calibration_action(
    task: str,
    form_inputs: dict | None,
    preview: bool,
    simulation_runs: list | None,
    nonce: str | None,
) -> tuple:
    """Validate a calibration page, then preview or submit it.

    Returns:
        tuple: (runs, toast open, toast message, nonce) for the page callback.
    """
    from .calibration import describe_calibration, statistics_rows, validate_calibration_form

    if form_inputs is None:
        return no_update, True, validation_message(
            ValueError("Select at least one summary statistic and a distance metric.")
        ), no_update
    try:
        compare = form_inputs.get("statistics_comparison") or {}
        if compare.get("use_summary_statistics", True):
            statistics_rows(form_inputs.get("summary_statistics"))
        model = validate_calibration_form(task, form_inputs)
    except (TypeError, ValueError) as error:
        return no_update, True, validation_message(error), no_update
    if preview:
        return no_update, True, message(
            "Setup is valid. Nothing was submitted.", *describe_calibration(task, model)
        ), no_update
    # Send the page's own inputs with the validated whole-number counts. A JSON
    # dump of the model would serialize them through its bool|float|int|str
    # union as floats (24 -> 24.0), which Optuna and NumPy reject as sizes.
    payload = dict(form_inputs, calibration_parameters=dict(model.calibration_parameters))
    runs, status, nonce = submit_from_page(task, payload, simulation_runs, nonce, model.simulation_tag)
    return runs, True, status, nonce


def load_statistics_upload(contents: list | None, names: list | None) -> tuple:
    """Read an uploaded statistics CSV and check its header.

    Returns:
        tuple: (store data or no_update, toast message).
    """
    import base64
    from io import StringIO

    import pandas as pd

    from .calibration import statistics_rows

    if not contents or contents[0] is None:
        return no_update, no_update
    name = (names or ["upload"])[0]
    try:
        _, encoded = contents[0].split(",", 1)
        frame = pd.read_csv(StringIO(base64.b64decode(encoded).decode("utf-8")), skipinitialspace=True)
        frame.columns = [str(column).strip() for column in frame.columns]
        rows = statistics_rows(frame.to_dict("records"))
        values = pd.to_numeric(frame["statistic_value"], errors="coerce")
        if values.isna().any():
            raise ValueError("Every statistic_value must be a number.")
    except (ValueError, UnicodeDecodeError, pd.errors.ParserError) as error:
        return no_update, message(f"Could not use {name}", str(error), tone="danger")
    return {"label": name, "values": rows}, f"Loaded {len(rows)} statistics from {name}"


def _now() -> str:
    from ..pipeline import get_datetime_now

    return get_datetime_now()


def artifact_summary(task: str, simulation_uuid: str) -> str:
    """Describe the result artifacts tied to one run, or why they are missing."""
    if task == "architecture_search":
        from ..pipeline import get_outdir

        folder = Path(get_outdir()) / "architecture-search" / str(UUID(simulation_uuid))
        names = [name for name in ("summary.json", "trials.csv", "best-configuration.json")
                 if (folder / name).is_file()]
        if not names:
            return "no result files in the shared output folder"
        return "results: " + ", ".join(names)
    if task not in MLFLOW_TASKS:
        return ""
    try:
        import mlflow
        from mlflow.tracking import MlflowClient

        experiment = mlflow.get_experiment_by_name(f"root_model_{task}")
        if experiment is None:
            return f"no MLflow experiment root_model_{task}"
        client = MlflowClient()
        found = client.search_runs(
            [experiment.experiment_id], filter_string=f"tags.simulation_uuid = '{simulation_uuid}'"
        )
        if not found:
            return "no MLflow run with this UUID"
        count = len(client.list_artifacts(found[0].info.run_id))
        if count == 0:
            return f"MLflow run {found[0].info.run_id[:8]} has no artifacts"
        host = os.environ.get("APP_MLFLOW_USER_HOST", "")
        return f"MLflow run {found[0].info.run_id[:8]} · {count} artifacts" + (f" at {host}" if host else "")
    except Exception as exc:  # MLflow is optional for the page; report, never raise.
        return f"artifact check unavailable ({type(exc).__name__})"


def refresh_runs(runs: list | None, limit: int = 8) -> list | None:
    """Update pending rows from Prefect; return None when nothing changed."""
    changed = False
    updated = []
    checked = 0
    for run in runs or []:
        run = dict(run)
        run_id = run.get("flow_run_id")
        if run_id and run.get("state_type") not in FINAL_STATES | {"MISSING"} and checked < limit:
            checked += 1
            try:
                state_type, state_name = read_run_state(run_id)
            except SubmissionError as error:
                if error.kind == "missing_run":
                    run.update(state="Not on this Prefect server", state_type="MISSING")
                    changed = True
                updated.append(run)
                continue
            except Exception:
                updated.append(run)
                continue
            text = state_name
            if state_type == "COMPLETED":
                summary = artifact_summary(run.get("task", ""), run.get("simulation_uuid", ""))
                text = f"Completed · {summary}" if summary else "Completed"
            elif state_type in {"FAILED", "CRASHED"}:
                text = f"{state_name} · open the run link for the worker log"
            if text != run.get("state") or state_type != run.get("state_type"):
                run.update(state=text, state_type=state_type)
                changed = True
        updated.append(run)
    return updated if changed else None


def register_run_status_callback(page_id: str) -> None:
    """Poll pending runs for the page's run table."""

    @callback(
        Output("store-simulation-run", "data", allow_duplicate=True),
        Input(f"{page_id}-run-status-poll", "n_intervals"),
        State("store-simulation-run", "data"),
        prevent_initial_call=True,
    )
    def refresh(_, runs):
        updated = refresh_runs(runs)
        return no_update if updated is None else updated


__all__ = [
    "message",
    "validation_message",
    "calibration_action",
    "load_statistics_upload",
    "submit_from_page",
    "refresh_runs",
    "register_run_status_callback",
    "flow_run_url",
]
