#!/usr/bin/env python

######################################
# Imports
######################################

# mypy: ignore-errors

import os.path as osp

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
DATA_COMPONENT_KEY = "summary_data"

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
    Output(f"{PAGE_ID}-summary-data-collapse", "is_open"),
    [Input(f"{PAGE_ID}-summary-data-collapse-button", "n_clicks")],
    [State(f"{PAGE_ID}-summary-data-collapse", "is_open")],
)
def toggle_data_collapse(n: int, is_open: bool) -> bool:
    """Toggle the collapsible for statistics.

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
    Output(
        {"index": f"{PAGE_ID}-upload-obs-data-file-button", "type": ALL}, "children"
    ),
    Output({"index": f"{PAGE_ID}-clear-obs-data-file-button", "type": ALL}, "disabled"),
    Input("store-summary-data", "data"),
)
def update_summary_data(summary_data: dict) -> tuple:
    """Update the state of the summary data.

    Args:
        summary_data (dict | None):
            The summary data.

    Returns:
        tuple:
            The updated form state.
    """
    button_contents = "Load summary data"
    if summary_data is None:
        return [button_contents], [True]
    summary_label = summary_data.get("label")
    if summary_label is None:
        return [button_contents], [True]

    return [summary_label], [False]


@callback(
    Output("store-summary-data", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-load-toast", "is_open", allow_duplicate=True),
    Output(f"{PAGE_ID}-load-toast", "children", allow_duplicate=True),
    Input({"index": f"{PAGE_ID}-upload-obs-data-file-button", "type": ALL}, "contents"),
    State({"index": f"{PAGE_ID}-upload-obs-data-file-button", "type": ALL}, "filename"),
    prevent_initial_call=True,
)
def load_summary_data(list_of_contents: list, list_of_names: list) -> tuple:
    """Load statistics data from file.

    Args:
        list_of_contents (list):
            The list of file contents.
        list_of_names (list):
            The list of file names.

    Returns:
        tuple:
            The updated form state.
    """
    summary_data, toast_message = load_statistics_upload(list_of_contents, list_of_names)
    if toast_message is no_update:
        return no_update
    return summary_data, True, toast_message


@callback(
    Output("store-summary-data", "data", allow_duplicate=True),
    Output(
        {"index": f"{PAGE_ID}-upload-obs-data-file-button", "type": ALL}, "contents"
    ),
    Output(f"{PAGE_ID}-load-toast", "is_open", allow_duplicate=True),
    Output(f"{PAGE_ID}-load-toast", "children", allow_duplicate=True),
    Input({"index": f"{PAGE_ID}-clear-obs-data-file-button", "type": ALL}, "n_clicks"),
    State("store-summary-data", "data"),
    prevent_initial_call=True,
)
def clear_summary_data(n_clicks: int | list[int], summary_data: dict) -> tuple:
    """Clear summary data from the page.

    Args:
        n_clicks (int | list[int]):
            The number of form clicks.
        summary_data (dict):
            The exploratory data analysis data.

    Returns:
        tuple:
            The updated form state.
    """
    if n_clicks is None or len(n_clicks) == 0:  # type: ignore
        return no_update

    if n_clicks[0] is None or n_clicks[0] == 0:  # type: ignore
        return no_update

    summary_label = summary_data.get("label")
    if summary_data is None or summary_label is None:
        return no_update

    toast_message = f"Clearing: {summary_label}"
    return {}, [None], True, toast_message


def call_service(task: str, body: dict) -> tuple:
    """Call one model service; return (download, toast open, message)."""
    try:
        outfile, rows, info = model_services.predict(task, body, get_outdir(), get_datetime_now())
    except model_services.ServiceError as error:
        tone = "warning" if error.kind == "unreachable" else "danger"
        return no_update, True, message(model_services.TITLES[error.kind], str(error), tone=tone)
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
    Input({"index": f"{PAGE_ID}-call-snpe-button", "type": ALL}, "n_clicks"),
    State({"type": f"{PAGE_ID}-summary_statistics", "index": ALL}, "value"),
    prevent_initial_call=True,
)
def call_snpe(n_clicks: list, statistics_inputs: list) -> tuple:
    """Request posterior draws conditional on the entered statistics."""
    if not clicked(n_clicks):
        return no_update, no_update, no_update
    children = get_app().settings[FORM_NAME].components["summary_statistics"]["children"]
    summary_statistics = [
        {"statistic_name": child["param"], "statistic_value": value}
        for child, value in zip(children, statistics_inputs)
        if value is not None
    ]
    if not summary_statistics:
        return no_update, True, message(
            "Invalid input", "Enter or load at least one summary statistic value.", tone="danger")
    return call_service("snpe", {"summary_statistics": summary_statistics})


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


def layout() -> html.Div:
    """Return the page layout.

    Returns:
        html.Div: The page layout.
    """
    page_description = """
    Interact with model calibration deployments and download data
    """

    layout = get_common_layout(
        title=TITLE,
        page_id=PAGE_ID,
        page_description=page_description,
        parameter_form_name=FORM_NAME,
        simulation_form_name=FORM_NAME,
        procedure=PROCEDURE,
        task=TASK,
        data_key=DATA_COMPONENT_KEY,
    )

    return html.Div([
        html.Div([
            html.Button("Check model services", id=f"{PAGE_ID}-check-services",
                        className="btn btn-outline-primary m-2"),
            html.Div(id=f"{PAGE_ID}-service-status", className="mx-2"),
        ]),
        layout,
    ])
