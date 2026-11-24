"""Configure a canonical architecture search and retrieve its local outputs."""
import base64
import json
from pathlib import Path
from uuid import UUID

from dash import Input, Output, State, callback, ctx, dash_table, dcc, html, no_update, register_page
import dash_bootstrap_components as dbc
from deeprootgen.form.architecture_targets import parse_seeds, parse_targets
from deeprootgen.form.optimisation import optimisation_statistics
from deeprootgen.pipeline.submission import FINAL_STATES, SubmissionError, flow_run_url, new_nonce, read_run_state, submit
from deeprootgen.pipeline import get_outdir
from deeprootgen.research.architecture_search import describe_controls, validate_architecture_search


register_page(__name__, name="Architecture Search", top_nav=True, path="/architecture-search")


def layout():
    return dbc.Container([
        html.H1("Architecture Search", className="my-3"),
        html.P("Fit a saved schema-4 architecture to whole-root targets with adaptive Optuna or a Latin-hypercube screen."),
        dcc.Store(id="architecture-base"),
        dcc.Store(id="architecture-run"),
        dcc.Store(id="architecture-nonce"),
        dcc.Interval(id="architecture-poll", interval=3000, disabled=True),
        dcc.Upload(id="architecture-upload", children=dbc.Button("Load architecture JSON", outline=True)),
        html.P(id="architecture-model-status", className="mt-2"),
        html.Details([html.Summary("Active laws by order"), html.Pre(id="architecture-laws", style={"whiteSpace": "pre-wrap"})]),
        html.P("Fill in both bounds for each control to vary. Leave other ranges blank.", className="mt-3"),
        dash_table.DataTable(id="architecture-controls", columns=[
            {"name": "Control", "id": "label"}, {"name": "Unit", "id": "unit"},
            {"name": "Current", "id": "value", "type": "numeric"},
            {"name": "Lower", "id": "lower", "type": "numeric", "editable": True},
            {"name": "Upper", "id": "upper", "type": "numeric", "editable": True},
        ], style_cell={"textAlign": "left"}, style_table={"overflowX": "auto"}),
        html.H2("Targets and trials", className="h4 mt-4"),
        html.P("Paste a header row statistic_name,statistic_value (optional scale) and one row per target. "
               "Commas, tabs (spreadsheet copy), semicolons or spaces separate the columns."),
        html.Details([html.Summary("Supported statistics"),
                      html.P(", ".join(option["value"] for option in optimisation_statistics()))],
                     className="mb-2"),
        dcc.Textarea(id="architecture-targets", placeholder="statistic_name,statistic_value\nroot_number,3",
                     style={"width": "100%", "minHeight": "7rem"}),
        html.Label("Search method", htmlFor="architecture-method"),
        dcc.Dropdown(id="architecture-method", options=[
            {"label": "Adaptive Optuna TPE", "value": "tpe"},
            {"label": "Latin-hypercube screening", "value": "latin_hypercube"},
        ], value="tpe", clearable=False, className="mb-2"),
        dbc.Row([
            dbc.Col([html.Label("Loss", htmlFor="architecture-metric"), dcc.Dropdown(
                id="architecture-metric", options=[{"label": "Normalized MAE", "value": "mae"},
                                                   {"label": "Normalized RMSE", "value": "rmse"}],
                value="mae", clearable=False)], md=3),
            dbc.Col([html.Label("Trials", htmlFor="architecture-trials"),
                     dbc.Input(id="architecture-trials", type="number", min=2, max=60, step=1, value=10)], md=2),
            dbc.Col([html.Label("Startup", htmlFor="architecture-startup"),
                     dbc.Input(id="architecture-startup", type="number", min=1, max=30, step=1, value=3)], md=2),
            dbc.Col([html.Label("Seeds, separated by commas", htmlFor="architecture-seeds"),
                     dbc.Input(id="architecture-seeds", value="0, 1")], md=5),
        ], className="mb-3"),
        dbc.Button("Check setup", id="architecture-preview", outline=True, className="me-2"),
        dbc.Button("Run search", id="architecture-launch"),
        html.Div(id="architecture-message", role="status", className="my-3"),
        html.Div(id="architecture-state", role="status"),
        dbc.Button("Best configuration", id="architecture-best", disabled=True, outline=True, className="me-2"),
        dbc.Button("Trial table", id="architecture-trial-table", disabled=True, outline=True),
        dcc.Download(id="architecture-download"),
    ], className="pb-4")


@callback(Output("architecture-base", "data"), Output("architecture-controls", "data"),
          Output("architecture-model-status", "children"), Output("architecture-laws", "children"),
          Input("architecture-upload", "contents"), prevent_initial_call=True)
def load_architecture(contents):
    if not contents:
        return None, [], "Load a schema-4 JSON file.", ""
    try:
        _, raw = contents.split(",", 1)
        if len(raw) > 2_000_000:
            raise ValueError("Use a configuration JSON under 1.5 MB.")
        base, controls, description = describe_controls(json.loads(base64.b64decode(raw, validate=True)))
    except ValueError as error:
        return None, [], str(error), ""
    rows = [dict(id=key, label=item["label"], unit=item["unit"], value=item["value"], lower=None, upper=None)
            for key, item in controls.items()]
    stages = ("dimensions", "material", "branching", "direction")
    laws = description["laws"]["by_order"]

    def law_name(stage):
        return (stage.get("law") or stage.get("replaces")) if isinstance(stage, dict) else stage

    view = {order: {stage: law_name(data[stage]) for stage in stages} for order, data in laws.items()}
    return base, rows, f"Schema 4 · {len(rows)} searchable controls", json.dumps(view, indent=2)


def form_request(base, rows, targets, metric, trials, startup, seeds, method="tpe"):
    if not base:
        raise ValueError("Load a schema-4 configuration first.")
    observations = parse_targets(targets)
    ranges = [dict(control=r["id"], lower=r.get("lower"), upper=r.get("upper"))
              for r in rows or [] if r.get("lower") is not None or r.get("upper") is not None]
    request = dict(base=base, ranges=ranges, targets=observations, metric=metric, method=method,
                   trials=trials, startup=startup, seeds=parse_seeds(seeds))
    job, _, _, _, _ = validate_architecture_search(request)
    request = job.model_dump(mode="json", exclude_unset=True)
    return request, f"{len(job.ranges)} controls · {len(job.targets)} targets · {job.trials} trials × {len(job.seeds)} seeds"


@callback(Output("architecture-startup", "disabled"), Input("architecture-method", "value"))
def startup_disabled(method):
    return method != "tpe"


@callback(Output("architecture-message", "children"), Output("architecture-run", "data"),
          Output("architecture-poll", "disabled"), Output("architecture-nonce", "data"),
          Input("architecture-preview", "n_clicks"), Input("architecture-launch", "n_clicks"),
          State("architecture-base", "data"), State("architecture-controls", "data"),
          State("architecture-targets", "value"), State("architecture-metric", "value"),
          State("architecture-trials", "value"), State("architecture-startup", "value"),
          State("architecture-seeds", "value"), State("architecture-method", "value"),
          State("architecture-nonce", "data"), prevent_initial_call=True)
def submit_search(_preview, _launch, base, rows, targets, metric, trials, startup, seeds, method="tpe", nonce=None):
    try:
        request, message = form_request(base, rows, targets, metric, trials, startup, seeds, method)
    except (TypeError, ValueError) as error:
        return f"Check the setup. Nothing was submitted. {error}", no_update, no_update, no_update
    if ctx.triggered_id == "architecture-preview":
        return f"Setup is valid. Nothing was submitted. {message}", no_update, no_update, no_update
    nonce = nonce or new_nonce()
    try:
        result = submit("architecture_search", {"input_parameters": request}, nonce)
    except SubmissionError as error:
        return str(error), no_update, no_update, nonce
    prefix = "Queued" if result.created else "Already queued (same request)"
    text = html.Span([f"{prefix}: run {result.simulation_uuid}. {message}. ",
                      html.A("Open the Prefect run", href=result.url, target="_blank", rel="noopener noreferrer"),
                      *[html.Span(f" {note}") for note in result.notes]])
    return text, dict(job=result.simulation_uuid, run=result.flow_run_id), False, new_nonce()


def output_folder(run):
    return Path(get_outdir()) / "architecture-search" / str(UUID(run["job"]))


@callback(Output("architecture-state", "children"), Output("architecture-best", "disabled"),
          Output("architecture-trial-table", "disabled"),
          Output("architecture-poll", "disabled", allow_duplicate=True),
          Input("architecture-run", "data"), Input("architecture-poll", "n_intervals"), prevent_initial_call=True)
def show_search(run, _):
    if not run:
        return "", True, True, True
    try:
        folder = output_folder(run)
    except (KeyError, TypeError, ValueError):
        return "This run record is not readable; queue the search again.", True, True, True
    result = folder / "summary.json"
    if result.is_file():
        data = json.loads(result.read_text())
        completed, failed = data["completed_trials"], data["failed_trials"]
        value = data["best_loss"]
        loss = f" · best loss {value:.5g}" if value is not None else ""
        return (f"Completed · {completed} trials completed · {failed} failed{loss}",
                not (folder / "best-configuration.json").is_file(), False, True)
    link = html.A("Prefect run", href=flow_run_url(run["run"]), target="_blank", rel="noopener noreferrer")
    try:
        state_type, state_name = read_run_state(run["run"])
    except SubmissionError as error:
        if error.kind == "missing_run":
            return "This run is not on the current Prefect server.", True, True, True
        return "Prefect is unreachable; the run state is unknown. Retrying.", True, True, False
    except Exception:
        return "Worker state is currently unavailable. Retrying.", True, True, False
    if state_type == "COMPLETED":
        return (html.Span(["Completed, but the result files are missing from the shared output folder. "
                           "Check that the app and worker mount the same /app/outputs. ", link]), True, True, True)
    if state_type in {"FAILED", "CRASHED"}:
        return html.Span([f"{state_name}. Open the worker log: ", link]), True, True, True
    return html.Span([f"{state_name} · ", link]), True, True, state_type in FINAL_STATES


@callback(Output("architecture-download", "data"), Input("architecture-best", "n_clicks"),
          Input("architecture-trial-table", "n_clicks"), State("architecture-run", "data"),
          prevent_initial_call=True)
def download_search(_best, _table, run):
    if not run:
        return no_update
    name = "best-configuration.json" if ctx.triggered_id == "architecture-best" else "trials.csv"
    try:
        file = output_folder(run) / name
    except (KeyError, TypeError, ValueError):
        return no_update
    return dcc.send_file(file) if file.is_file() else no_update
