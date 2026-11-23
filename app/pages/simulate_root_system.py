#!/usr/bin/env python

######################################
# Imports
######################################

from dash import (
    ALL,
    Input,
    Output,
    State,
    callback,
    ctx,
    dcc,
    get_app,
    html,
    no_update,
    register_page,
)

import base64
import json

import yaml

from deeprootgen.data_model.simulation_form import SoilDisplay, simulation_controls, simulation_document
from deeprootgen.form import get_common_layout
from deeprootgen.form.run_feedback import (
    message,
    register_run_status_callback,
    submit_from_page,
    validation_message,
)
from deeprootgen.io import load_data_from_file, s3_upload_file
from deeprootgen.pipeline import (
    save_simulation_runs,
)

######################################
# Constants
######################################

TASK = "simulation"
PAGE_ID = f"{TASK}-root-system-page"
FORM_NAME = "simulation_form"
PROCEDURE = "simulation"

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
    Output({"index": f"{PAGE_ID}-simulation-runs-table", "type": ALL}, "data"),
    Output({"index": f"{PAGE_ID}-save-runs-button", "type": ALL}, "disabled"),
    Output({"index": f"{PAGE_ID}-clear-runs-button", "type": ALL}, "disabled"),
    Input("store-simulation-run", "data"),
)
def update_table(runs: list | None) -> tuple | None:
    """Update the simulation run table.

    Args:
        runs (list | None):
            The list of simulation runs.

    Returns:
        tuple | None:
            The updated form state.
    """
    if runs is None:
        return no_update
    if len(runs) == 0:
        return [runs], [True], [True]

    return [runs], [False], [False]


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
    Output(f"{PAGE_ID}-{PROCEDURE}-collapse", "is_open"),
    [Input(f"{PAGE_ID}-{PROCEDURE}-collapse-button", "n_clicks")],
    [State(f"{PAGE_ID}-{PROCEDURE}-collapse", "is_open")],
)
def toggle_procedure_collapse(n: int, is_open: bool) -> bool:
    f"""Toggle the collapsible for {PROCEDURE} management.

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
    Output(f"{PAGE_ID}-download-params", "data"),
    [Input({"index": f"{PAGE_ID}-save-param-button", "type": ALL}, "n_clicks")],
    State({"type": f"{PAGE_ID}-parameters", "index": ALL}, "value"),
    prevent_initial_call=True,
)
def save_param(n_clicks: int | list[int], param_inputs: list) -> None:
    """Save parameter form values.

    Args:
        n_clicks (int | list[int]):
            The number of times that the button has been clicked.
        param_inputs (list):
            The parameter input data.
    """
    if n_clicks is None or len(n_clicks) == 0:  # type: ignore
        return no_update

    if n_clicks[0] is None or n_clicks[0] == 0:  # type: ignore
        return no_update

    fields = [v["param"] for v in get_app().settings[FORM_NAME].components["parameters"]["children"]]
    document = simulation_document(dict(zip(fields, param_inputs)))
    return dcc.send_string(json.dumps(document, indent=2), "root-system.json")


@callback(
    Output(f"{PAGE_ID}-download-results", "data"),
    [Input({"index": f"{PAGE_ID}-save-runs-button", "type": ALL}, "n_clicks")],
    State("store-simulation-run", "data"),
    prevent_initial_call=True,
)
def save_runs(n_clicks: int | list[int], simulation_runs: list) -> None:
    """Save simulation runs to file.

    Args:
        n_clicks (int | list[int]):
            The number of times that the button has been clicked.
        simulation_runs (list):
            A list of simulation run data.
    """
    if n_clicks is None or len(n_clicks) == 0:  # type: ignore
        return no_update

    if n_clicks[0] is None or n_clicks[0] == 0:  # type: ignore
        return no_update

    if simulation_runs is None or len(simulation_runs) == 0:
        return no_update

    outfile, file_name = save_simulation_runs(simulation_runs)
    s3_upload_file(outfile, file_name)
    return dcc.send_file(outfile)


@callback(
    Output("store-simulation-run", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-load-toast", "is_open", allow_duplicate=True),
    Output(f"{PAGE_ID}-load-toast", "children", allow_duplicate=True),
    Input({"index": f"{PAGE_ID}-upload-runs-file-button", "type": ALL}, "contents"),
    State({"index": f"{PAGE_ID}-upload-runs-file-button", "type": ALL}, "filename"),
    prevent_initial_call=True,
)
def load_runs(list_of_contents: list, list_of_names: list) -> tuple:
    """Load simulation runs from file.

    Args:
        list_of_contents (list):
            The list of file contents.
        list_of_names (list):
            The list of file names.

    Returns:
        tuple:
            The updated form state.
    """
    if list_of_contents is None or len(list_of_contents) == 0:
        return no_update

    if list_of_contents[0] is None or list_of_contents[0] == 0:
        return no_update

    simulation_runs, _, toast_message = load_data_from_file(
        list_of_contents, list_of_names
    )
    return simulation_runs, True, toast_message


@callback(
    Output("store-simulation-run", "data", allow_duplicate=True),
    [Input({"index": f"{PAGE_ID}-clear-runs-button", "type": ALL}, "n_clicks")],
    prevent_initial_call=True,
)
def clear_runs(n_clicks: int | list[int]) -> list:
    """Clear the simulation runs table.

    Args:
        n_clicks (int | list[int]):
            The number of times that the button has been clicked.

    Returns:
        list:
            An empty list.
    """
    if n_clicks is None or len(n_clicks) == 0:  # type: ignore
        return no_update

    if n_clicks[0] is None or n_clicks[0] == 0:  # type: ignore
        return no_update

    return []


@callback(
    Output({"type": f"{PAGE_ID}-parameters", "index": ALL}, "value"),
    Output(f"{PAGE_ID}-load-toast", "is_open", allow_duplicate=True),
    Output(f"{PAGE_ID}-load-toast", "children", allow_duplicate=True),
    Input({"index": f"{PAGE_ID}-upload-param-file-button", "type": ALL}, "contents"),
    State({"index": f"{PAGE_ID}-upload-param-file-button", "type": ALL}, "filename"),
    prevent_initial_call=True,
)
def load_params(list_of_contents: list, list_of_names: list) -> tuple:
    """Load the simulation parameters from file.

    Args:
        list_of_contents (list):
            The list of file contents.
        list_of_names (list):
            The list of file names.

    Returns:
        tuple:
            The updated form state.
    """
    if list_of_contents is None or len(list_of_contents) == 0:
        return no_update

    if list_of_contents[0] is None or list_of_contents[0] == 0:
        return no_update

    fields = [v["param"] for v in get_app().settings[FORM_NAME].components["parameters"]["children"]]
    try:
        document = yaml.safe_load(base64.b64decode(list_of_contents[0].split(",", 1)[1]))
        inputs = simulation_controls(document, fields, current_soil={k: no_update for k in SoilDisplay.model_fields})
    except (ValueError, TypeError, yaml.YAMLError) as error:
        return no_update, True, str(error)
    return inputs, True, f"Loaded {list_of_names[0]}"


@callback(
    Output("store-simulation-run", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-results-toast", "is_open"),
    Output(f"{PAGE_ID}-results-toast", "children"),
    Output(f"{PAGE_ID}-submission-nonce", "data"),
    Input({"index": f"{PAGE_ID}-run-sim-button", "type": ALL}, "n_clicks"),
    Input(f"{PAGE_ID}-preview", "n_clicks"),
    State({"type": f"{PAGE_ID}-parameters", "index": ALL}, "value"),
    State({"index": f"{PAGE_ID}-enable-soil-input", "type": ALL}, "on"),
    State("store-simulation-run", "data"),
    State(f"{PAGE_ID}-submission-nonce", "data"),
    prevent_initial_call=True,
)
def run_root_model(
    n_clicks: list,
    preview_clicks: int | None,
    form_values: list,
    enable_soils: list,
    simulation_runs: list,
    nonce: str | None,
) -> tuple:
    """Check the schema-4 form, or validate and queue one simulation.

    Args:
        n_clicks (list):
            Number of times Run procedure has been clicked.
        preview_clicks (int | None):
            Number of times Check setup has been clicked; never submits.
        form_values (list):
            The form input data.
        enable_soils (list):
            Enable visualisation of soil data.
        simulation_runs (list):
            A list of simulation run data.
        nonce (str | None):
            The page submission nonce (see deeprootgen.form.run_feedback).

    Returns:
        tuple:
            The run table, toast state and message, and submission nonce.
    """
    preview = ctx.triggered_id == f"{PAGE_ID}-preview"
    if not (preview_clicks if preview else n_clicks and n_clicks[0]):
        return no_update, no_update, no_update, no_update

    form_inputs = {}
    app = get_app()
    form_model = app.settings[FORM_NAME]
    for i, input in enumerate(form_model.components["parameters"]["children"]):
        form_inputs[input["param"]] = form_values[i]
    form_inputs["enable_soil"] = bool(enable_soils and enable_soils[0])

    try:
        document = simulation_document(form_inputs)
        soil = SoilDisplay.model_validate({k: form_inputs[k] for k in SoilDisplay.model_fields})
    except (TypeError, ValueError) as error:
        return no_update, True, validation_message(error), no_update
    if preview:
        parameters = document["parameters"]
        targets = [k for k in ("root_ratio_biomass", "root_ratio_length") if parameters.get(k) is not None]
        return no_update, True, message(
            "Setup is valid. Nothing was submitted.",
            f"Schema 4 · seed {document.get('random_seed')} · tag {document.get('simulation_tag')}",
            f"Maximum order {parameters.get('max_order')} · {parameters.get('primary_root_count')} primary roots",
            "Fine-root targets: " + (", ".join(targets) if targets else "none (untargeted run)"),
        ), no_update
    runs, status, nonce = submit_from_page(
        TASK, document, simulation_runs, nonce, document.get("simulation_tag"),
        soil_display=soil.model_dump(),
    )
    return runs, True, status, nonce


######################################
# Layout
######################################

register_page(__name__, name="Simulation", top_nav=True, path="/")


def layout() -> html.Div:
    """Return the page layout.

    Returns:
        html.Div: The page layout.
    """
    title = "Run Simulation"
    page_description = """
    Create synthetic root data by running the root system architecture simulation
    """

    layout = get_common_layout(
        title=title,
        page_id=PAGE_ID,
        page_description=page_description,
        parameter_form_name=FORM_NAME,
        simulation_form_name=FORM_NAME,
        procedure=PROCEDURE.title(),
        task=TASK,
    )
    return html.Div([
        html.Button("Check setup", id=f"{PAGE_ID}-preview", className="btn btn-outline-primary m-2"),
        layout,
    ])


register_run_status_callback(PAGE_ID)
