#!/usr/bin/env python

######################################
# Imports
######################################

# mypy: ignore-errors

import os.path as osp

import dash_bootstrap_components as dbc
from dash import (
    ALL,
    Input,
    Output,
    State,
    callback,
    dcc,
    get_app,
    html,
    no_update,
    register_page,
)

from deeprootgen.data_model.snpe_targets import conditioning_rows
from deeprootgen.data_model.surrogate_inputs import surrogate_form_row
from deeprootgen.form import get_common_layout
from deeprootgen.form import model_services
from deeprootgen.form.run_feedback import load_statistics_upload, message
from deeprootgen.pipeline import get_datetime_now, get_outdir

######################################
# Constants
######################################

TITLE = "Deployments"
TASK = "deployments"
PAGE_ID = f"{TASK}-root-system-page"
FORM_NAME = "deployments_form"
PROCEDURE = "Calibration"
SNPE_MODEL_INFO = f"{PAGE_ID}-snpe-model-info"
SNPE_SOURCE = f"{PAGE_ID}-snpe-source"
SNPE_UPLOAD = f"{PAGE_ID}-snpe-target-upload"
SNPE_INPUTS = {"type": f"{PAGE_ID}-summary_statistics", "index": ALL}
SNPE_PREDICT = {"index": f"{PAGE_ID}-call-snpe-button", "type": f"{PAGE_ID}-simulation"}
UPLOAD_BUTTON = {
    "index": f"{PAGE_ID}-upload-obs-data-file-button", "type": f"{PAGE_ID}-summary_data"
}
CLEAR_UPLOAD = {
    "index": f"{PAGE_ID}-clear-obs-data-file-button", "type": f"{PAGE_ID}-summary_data"
}

######################################
# Callbacks
######################################


@callback(
    Output(f"{PAGE_ID}-sidebar-fade", "is_in"),
    Output(f"{PAGE_ID}-output-fade", "is_in"),
    Input(f"{PAGE_ID}-sidebar-fade", "is_in"),
)
def fade_in(is_in: bool) -> tuple:
    """Fade the page contents in.

    Args:
        is_in (bool):
            Whether the sidebar is in the page.

    Returns:
        tuple:
            A tuple for displaying the page contents.
    """
    if is_in:
        return True, True
    return True, True


@callback(
    Output(f"{PAGE_ID}-parameters-collapse", "is_open"),
    [Input(f"{PAGE_ID}-parameters-collapse-button", "n_clicks")],
    [State(f"{PAGE_ID}-parameters-collapse", "is_open")],
)
def toggle_parameters_collapse(n: int, is_open: bool) -> bool:
    """Toggle the collapsible for parameters.

    Args:
        n (int):
            The number of times that the button has been clicked.
        is_open (bool):
            Whether the collapsible is open.

    Returns:
        bool: The collapsible state.
    """
    if n:
        return not is_open
    return is_open


@callback(
    Output(f"{PAGE_ID}-external-links-collapse", "is_open"),
    [Input(f"{PAGE_ID}-external-links-collapse-button", "n_clicks")],
    [State(f"{PAGE_ID}-external-links-collapse", "is_open")],
)
def toggle_external_links_collapse(n: int, is_open: bool) -> bool:
    """Toggle the collapsible for external links.

    Args:
        n (int):
            The number of times that the button has been clicked.
        is_open (bool):
            Whether the collapsible is open.

    Returns:
        bool: The collapsible state.
    """
    if n:
        return not is_open
    return is_open


@callback(
    Output(f"{PAGE_ID}-deployments-collapse", "is_open"),
    [Input(f"{PAGE_ID}-deployments-collapse-button", "n_clicks")],
    [State(f"{PAGE_ID}-deployments-collapse", "is_open")],
)
def toggle_deployments_collapse(n: int, is_open: bool) -> bool:
    """Toggle the collapsible for deployments.

    Args:
        n (int):
            The number of times that the button has been clicked.
        is_open (bool):
            Whether the collapsible is open.

    Returns:
        bool: The collapsible state.
    """
    if n:
        return not is_open
    return is_open


@callback(
    Output(f"{PAGE_ID}-calibration-parameters-collapse", "is_open"),
    [Input(f"{PAGE_ID}-calibration-parameters-collapse-button", "n_clicks")],
    [State(f"{PAGE_ID}-calibration-parameters-collapse", "is_open")],
)
def toggle_calibration_parameters_collapse(n: int, is_open: bool) -> bool:
    """Toggle the collapsible for calibration inputs.

    Args:
        n (int):
            The number of times that the button has been clicked.
        is_open (bool):
            Whether the collapsible is open.

    Returns:
        bool: The collapsible state.
    """
    if n:
        return not is_open
    return is_open


@callback(
    Output(f"{PAGE_ID}-calibration-collapse", "is_open"),
    [Input(f"{PAGE_ID}-calibration-collapse-button", "n_clicks")],
    [State(f"{PAGE_ID}-calibration-collapse", "is_open")],
)
def toggle_calibration_collapse(n: int, is_open: bool) -> bool:
    """Toggle the collapsible for calibration inputs.

    Args:
        n (int):
            The number of times that the button has been clicked.
        is_open (bool):
            Whether the collapsible is open.

    Returns:
        bool: The collapsible state.
    """
    if n:
        return not is_open
    return is_open


@callback(
    Output(SNPE_MODEL_INFO, "data"),
    Input(f"{PAGE_ID}-check-services", "n_clicks"),
)
def refresh_snpe_model(_: int | None) -> dict:
    """Refresh the schema from the loaded SNPE model."""
    try:
        return model_services.model_info("snpe", timeout=3.0)
    except model_services.ServiceError as error:
        return {"prediction_detail": str(error)}


@callback(
    Output(SNPE_UPLOAD, "data", allow_duplicate=True),
    Output(UPLOAD_BUTTON, "contents", allow_duplicate=True),
    Output(f"{PAGE_ID}-load-toast", "is_open", allow_duplicate=True),
    Output(f"{PAGE_ID}-load-toast", "children", allow_duplicate=True),
    Input(UPLOAD_BUTTON, "contents"),
    State(UPLOAD_BUTTON, "filename"),
    prevent_initial_call=True,
)
def load_summary_data(contents: str | None, filename: str | None) -> tuple:
    """Read the target CSV while retaining any earlier valid upload on error."""
    summary_data, feedback = load_statistics_upload([contents], [filename or "upload"])
    if feedback is no_update:
        return no_update, no_update, no_update, no_update
    return summary_data, None, True, feedback


@callback(
    Output(SNPE_UPLOAD, "data", allow_duplicate=True),
    Input(CLEAR_UPLOAD, "n_clicks"),
    prevent_initial_call=True,
)
def clear_summary_data(n_clicks: int | None) -> dict:
    return {} if n_clicks else no_update


@callback(
    Output(f"{PAGE_ID}-snpe-upload-label", "children"),
    Output(CLEAR_UPLOAD, "disabled"),
    Input(SNPE_UPLOAD, "data"),
)
def describe_upload(upload: dict | None) -> tuple[str, bool]:
    filename = (upload or {}).get("label")
    return (f"Loaded {filename}", False) if filename else ("Choose a statistics CSV", True)


def statistic_names(model_info: dict | None) -> list[str]:
    info = model_info or {}
    if not info.get("available") or not info.get("prediction_ready") or not info.get("tag"):
        return []
    schema = info.get("input_schema") or {}
    names = schema.get("statistic_names") if isinstance(schema, dict) else None
    if not isinstance(names, list) or not all(isinstance(name, str) and name for name in names):
        return []
    return list(dict.fromkeys(names))


@callback(
    Output(f"{PAGE_ID}-snpe-manual", "children"),
    Input(SNPE_MODEL_INFO, "data"),
    State(SNPE_INPUTS, "id"),
    State(SNPE_INPUTS, "value"),
)
def render_manual_targets(model_info: dict, input_ids: list, values: list) -> list:
    """Render the served model's inputs and retain entered values on refresh."""
    previous = {item["index"]: value for item, value in zip(input_ids, values)}
    names = statistic_names(model_info)
    return [
        html.Label(
            [
                html.Span(name.replace("_", " ").capitalize(), className="form-label mb-1"),
                dcc.Input(
                    id={"type": SNPE_INPUTS["type"], "index": name},
                    type="number",
                    step="any",
                    value=previous.get(name),
                    className="form-control",
                ),
            ],
            className="col",
        )
        for name in names
    ]


@callback(
    Output(f"{PAGE_ID}-snpe-manual", "hidden"),
    Output(f"{PAGE_ID}-snpe-upload-panel", "hidden"),
    Input(SNPE_SOURCE, "value"),
)
def show_target_source(source: str) -> tuple[bool, bool]:
    return source != "manual", source != "upload"


def snpe_request(
    source: str,
    upload: dict | None,
    model_info: dict | None,
    input_ids: list,
    values: list,
) -> dict:
    """Resolve the chosen target source against the served model schema."""
    info = model_info or {}
    names = statistic_names(info)
    if not names:
        raise ValueError(
            info.get("prediction_detail")
            or "The SNPE service has not provided a model schema. Check model services."
        )
    if source == "upload":
        rows = (upload or {}).get("values") or []
        if not rows:
            raise ValueError("Choose a CSV with statistic_name and statistic_value columns.")
    elif source == "manual":
        rows = [
            {"statistic_name": item["index"], "statistic_value": value}
            for item, value in zip(input_ids, values)
        ]
    else:
        raise ValueError("Choose a source for the SNPE targets.")
    return {"summary_statistics": conditioning_rows(names, rows), "model_tag": info["tag"]}


@callback(
    Output(f"{PAGE_ID}-snpe-preview", "children"),
    Output(SNPE_PREDICT, "disabled"),
    Input(SNPE_SOURCE, "value"),
    Input(SNPE_UPLOAD, "data"),
    Input(SNPE_MODEL_INFO, "data"),
    Input(SNPE_INPUTS, "id"),
    Input(SNPE_INPUTS, "value"),
)
def preview_snpe_targets(source, upload, model_info, input_ids, values) -> tuple:
    """Show the exact values used by the prediction callback."""
    try:
        request = snpe_request(source, upload, model_info, input_ids, values)
    except ValueError as error:
        return html.P(str(error), className="mb-0"), True
    source_label = f"CSV · {upload['label']}" if source == "upload" else "Manual values"
    return [
        html.P(f"{source_label} · {request['model_tag']}", className="mb-1"),
        dbc.Table(
            [
                html.Thead(html.Tr([html.Th("Statistic", scope="col"), html.Th("Value", scope="col")])),
                html.Tbody([
                    html.Tr([
                        html.Th(row["statistic_name"], scope="row"),
                        html.Td(str(row["statistic_value"]).removesuffix(".0")),
                    ])
                    for row in request["summary_statistics"]
                ]),
            ],
            size="sm",
            responsive=True,
            className="mb-0",
        ),
    ], False


def call_service(task: str, body: dict, model_identity: dict | None = None) -> tuple:
    """Call one model service; return (download, toast open, message)."""
    try:
        outfile, rows, info = model_services.predict(task, body, get_outdir(), get_datetime_now())
    except model_services.ServiceError as error:
        tone = "warning" if error.kind == "unreachable" else "danger"
        return no_update, True, message(model_services.TITLES[error.kind], str(error), tone=tone)
    info = model_identity if model_identity is not None else info
    source = (f"Served model {info.get('tag')} from run {info.get('simulation_uuid')}"
              if info.get("available") else "Served model identity unavailable")
    return dcc.send_file(outfile), True, message(
        f"Downloaded {rows} rows from the {task} service", source, f"Saved as {osp.basename(outfile)}"
    )


def clicked(n_clicks) -> bool:
    return bool(n_clicks) and bool(n_clicks[0])


@callback(
    Output(f"{PAGE_ID}-download-results", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-results-toast", "is_open", allow_duplicate=True),
    Output(f"{PAGE_ID}-results-toast", "children", allow_duplicate=True),
    Input({"index": f"{PAGE_ID}-call-optimiser-button", "type": ALL}, "n_clicks"),
    State({"index": f"{PAGE_ID}-n-trials-input", "type": ALL}, "value"),
    prevent_initial_call=True,
)
def call_optimisation(n_clicks: list, n_trials_list: list) -> tuple:
    """Request the best stored optimisation trials."""
    if not clicked(n_clicks):
        return no_update, no_update, no_update
    n_trials = n_trials_list[0] if n_trials_list else None
    if not isinstance(n_trials, int) or isinstance(n_trials, bool) or n_trials < 1:
        return no_update, True, message("Invalid input", "Number of trials must be a whole number of at least 1.",
                                        tone="danger")
    return call_service("optimisation", {"n_trials": n_trials})


@callback(
    Output(f"{PAGE_ID}-download-results", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-results-toast", "is_open", allow_duplicate=True),
    Output(f"{PAGE_ID}-results-toast", "children", allow_duplicate=True),
    Input({"index": f"{PAGE_ID}-call-sa-button", "type": ALL}, "n_clicks"),
    State({"index": f"{PAGE_ID}-parameter-names-dropdown", "type": ALL}, "value"),
    prevent_initial_call=True,
)
def call_sensitivity_analysis(n_clicks: list, parameter_names_list: list) -> tuple:
    """Request total-order indices for the selected parameters."""
    if not clicked(n_clicks):
        return no_update, no_update, no_update
    names = parameter_names_list[0] if parameter_names_list else None
    names = [names] if isinstance(names, str) else list(names or [])
    if not names:
        return no_update, True, message("Invalid input", "Select at least one parameter name.", tone="danger")
    return call_service("sensitivity_analysis", {"names": names})


@callback(
    Output(f"{PAGE_ID}-download-results", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-results-toast", "is_open", allow_duplicate=True),
    Output(f"{PAGE_ID}-results-toast", "children", allow_duplicate=True),
    Input({"index": f"{PAGE_ID}-call-abc-button", "type": ALL}, "n_clicks"),
    State({"index": f"{PAGE_ID}-t-input", "type": ALL}, "value"),
    prevent_initial_call=True,
)
def call_abc(n_clicks: list, ts: list) -> tuple:
    """Request ABC particles for one population (-1 for all)."""
    if not clicked(n_clicks):
        return no_update, no_update, no_update
    t = ts[0] if ts else None
    if not isinstance(t, int) or isinstance(t, bool) or t < -1:
        return no_update, True, message("Invalid input", "Enter a population index of 0 or more, or -1 for all.",
                                        tone="danger")
    return call_service("abc", {"t": [t]})


@callback(
    Output(f"{PAGE_ID}-download-results", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-results-toast", "is_open", allow_duplicate=True),
    Output(f"{PAGE_ID}-results-toast", "children", allow_duplicate=True),
    Input(SNPE_PREDICT, "n_clicks"),
    State(SNPE_SOURCE, "value"),
    State(SNPE_UPLOAD, "data"),
    State(SNPE_MODEL_INFO, "data"),
    State(SNPE_INPUTS, "id"),
    State(SNPE_INPUTS, "value"),
    prevent_initial_call=True,
)
def call_snpe(n_clicks, source, upload, model_info, input_ids, values) -> tuple:
    """Request posterior draws from the model identified in the target preview."""
    if not n_clicks:
        return no_update, no_update, no_update
    try:
        body = snpe_request(source, upload, model_info, input_ids, values)
    except ValueError as error:
        return no_update, True, message("Invalid SNPE targets", str(error), tone="danger")
    return call_service("snpe", body, model_identity=model_info)


@callback(
    Output(f"{PAGE_ID}-download-results", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-results-toast", "is_open", allow_duplicate=True),
    Output(f"{PAGE_ID}-results-toast", "children", allow_duplicate=True),
    Input({"index": f"{PAGE_ID}-call-surrogate-button", "type": ALL}, "n_clicks"),
    State({"type": f"{PAGE_ID}-parameters", "index": ALL}, "value"),
    prevent_initial_call=True,
)
def call_surrogate(n_clicks: list, feature_inputs: list) -> tuple:
    """Request a surrogate prediction for one feature row."""
    if not clicked(n_clicks):
        return no_update, no_update, no_update
    children = get_app().settings[FORM_NAME].components["parameters"]["children"]
    try:
        row = surrogate_form_row(children, feature_inputs)
    except ValueError as exc:
        return no_update, True, message("Invalid input", str(exc), tone="danger")
    return call_service("surrogate", {"data": [row]})


@callback(
    Output(f"{PAGE_ID}-service-status", "children"),
    Input(f"{PAGE_ID}-check-services", "n_clicks"),
)
def show_service_status(_: int | None) -> html.Div:
    """List which optional model services are reachable and what they serve."""
    rows = model_services.service_status()
    return html.Div([
        html.P("Optional model services. Each needs a completed run of its method on this stack and the "
               "serving profile; until then its calls report why they are unavailable.", className="mb-1"),
        html.Ul([html.Li(f"{label}: {state} — {detail}") for label, state, detail in rows]),
    ], role="status")


######################################
# Layout
######################################


register_page(__name__, name=TITLE, top_nav=True, path=f"/{TASK}")


def snpe_target_card() -> dbc.Card:
    """Group target source, preview and prediction together."""
    return dbc.Card(
        dbc.CardBody([
            dcc.Store(id=SNPE_MODEL_INFO),
            dcc.Store(id=SNPE_UPLOAD, storage_type="session", data={}),
            html.H2("SNPE prediction", className="h5"),
            html.Fieldset([
                html.Legend("Target source", className="form-label fs-6 mb-1"),
                dcc.RadioItems(
                    id=SNPE_SOURCE,
                    options=[
                        {"label": "Manual entry", "value": "manual"},
                        {"label": "Uploaded CSV", "value": "upload"},
                    ],
                    value="manual",
                    labelClassName="me-3",
                    inputClassName="me-1",
                    inline=True,
                ),
            ], className="mb-3"),
            html.Div(
                id=f"{PAGE_ID}-snpe-manual",
                className="row row-cols-1 row-cols-sm-2 row-cols-xl-3 g-2 mb-3",
            ),
            html.Div([
                html.P("Use a CSV with statistic_name and statistic_value columns.", className="mb-2"),
                html.Div([
                    dcc.Upload(
                        id=UPLOAD_BUTTON,
                        accept=".csv,text/csv",
                        children=html.Span(
                            "Choose a statistics CSV", id=f"{PAGE_ID}-snpe-upload-label",
                            className="btn btn-outline-primary",
                        ),
                    ),
                    dbc.Button(
                        "Clear CSV", id=CLEAR_UPLOAD, outline=True, color="secondary", disabled=True,
                    ),
                ], className="d-flex align-items-center flex-wrap gap-2"),
            ], id=f"{PAGE_ID}-snpe-upload-panel", hidden=True, className="mb-3"),
            html.H3("Conditioning values", className="h6"),
            html.Div(
                "Checking the served model…", id=f"{PAGE_ID}-snpe-preview",
                role="status", className="mb-3",
            ),
            dbc.Button("Neural density calibrator", id=SNPE_PREDICT, disabled=True, color="primary"),
        ]),
        className="my-3",
    )


def layout() -> html.Div:
    """Return the Deployments page."""
    layout = get_common_layout(
        title=TITLE,
        page_id=PAGE_ID,
        page_description="Retrieve predictions and calibration results from deployed models.",
        parameter_form_name=FORM_NAME,
        simulation_form_name=FORM_NAME,
        procedure=PROCEDURE,
        task=TASK,
    )
    return html.Div([
        dbc.Container([
            html.Button("Check model services", id=f"{PAGE_ID}-check-services",
                        className="btn btn-outline-primary my-2"),
            html.Div(id=f"{PAGE_ID}-service-status"),
            snpe_target_card(),
        ], fluid=True),
        layout,
    ])
