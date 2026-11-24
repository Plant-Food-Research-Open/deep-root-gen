"""Save, restore and reset the settings shared by the calibration pages."""

from dash import ALL, Input, Output, State, callback, clientside_callback, ctx, dcc, get_app, no_update
from dash.exceptions import PreventUpdate

from ..io import s3_upload_file
from ..pipeline import load_form_parameters, save_form_parameters
from .components import form_control_defaults
from .run_feedback import message


def calibration_controls(form_name: str, task: str, values: list, switches: list) -> list:
    """Restore declaration order from the Dash value and on groups."""
    specs = get_app().settings[form_name].components[task]["children"]
    remaining_values = iter(values)
    remaining_switches = iter(switches)
    return [
        next(remaining_switches) if spec.get("handler") == "boolean_switch"
        else next(remaining_values)
        for spec in specs
    ]


def register_calibration_preset_callbacks(page_id: str, form_name: str, task: str) -> None:
    """Use the same form controls for saving, loading and checking a setup."""
    parameters = {"type": f"{page_id}-parameters", "index": ALL}
    calibration = {"type": f"{page_id}-{task}", "index": ALL}
    switches = {"type": f"{page_id}-{task}-switch", "index": ALL}
    upload = {"index": f"{page_id}-upload-param-file-button", "type": ALL}
    reset = f"{page_id}-reset-params"
    toast = f"{page_id}-load-toast"

    @callback(
        Output(f"{page_id}-download-params", "data"),
        Input({"index": f"{page_id}-save-param-button", "type": ALL}, "n_clicks"),
        State(parameters, "value"),
        State(calibration, "value"),
        State(switches, "on"),
        prevent_initial_call=True,
    )
    def save_preset(clicks, parameter_values, values, switch_values):
        if not clicks or not clicks[0]:
            raise PreventUpdate
        controls = calibration_controls(form_name, task, values, switch_values)
        outfile, filename = save_form_parameters(
            page_id, form_name, parameter_values, task, controls,
        )
        s3_upload_file(outfile, filename)
        return dcc.send_file(outfile)

    # Browsers only emit a file-change event when the native selection changes.
    clientside_callback(
        """
        function(clicks, uploadIds) {
            if (!clicks) return window.dash_clientside.no_update;
            return uploadIds.map(id => {
                const key = JSON.stringify(id, Object.keys(id).sort());
                const picker = document.getElementById(key)?.querySelector("input[type=file]");
                if (picker) picker.value = "";
                return null;
            });
        }
        """,
        Output(upload, "contents"),
        Input(reset, "n_clicks"),
        State(upload, "id"),
        prevent_initial_call=True,
    )

    @callback(
        Output(parameters, "value"),
        Output(calibration, "value"),
        Output(switches, "on"),
        Output(toast, "is_open", allow_duplicate=True),
        Output(toast, "children", allow_duplicate=True),
        Input(upload, "contents"),
        Input(reset, "n_clicks"),
        State(upload, "filename"),
        prevent_initial_call=True,
    )
    def restore_preset(contents, reset_clicks, filenames):
        if ctx.triggered_id == reset and reset_clicks:
            parameter_values = form_control_defaults(form_name, "parameters")
            controls = form_control_defaults(form_name, task)
            details = "Restored default parameter settings."
        elif contents and contents[0]:
            try:
                (parameter_values, controls), details = load_form_parameters(
                    contents, filenames, form_name, task,
                )
            except ValueError as error:
                return no_update, no_update, no_update, True, message(
                    "Could not load parameter settings", str(error), tone="danger"
                )
        else:
            raise PreventUpdate

        specs = get_app().settings[form_name].components[task]["children"]
        values = []
        switch_values = []
        for spec, value in zip(specs, controls):
            if spec.get("handler") == "boolean_switch":
                switch_values.append(value)
            else:
                values.append(value)
        return parameter_values, values, switch_values, True, details
