"""Compare already projected candidate architectures on one held physical support."""
import base64

from dash import Input, Output, State, callback, dash_table, dcc, html, register_page
from dash.dash_table.Format import Format, Scheme
from dash.dash_table.FormatTemplate import percentage
import dash_bootstrap_components as dbc

from deeprootgen.form.core_comparison import compare_core_csv


register_page(__name__, name="Core Comparison", top_nav=True, path="/core-comparison")


def layout():
    numeric = Format(precision=4, scheme=Scheme.fixed)
    rate = percentage(1)
    cols = [
        ("Candidate", "candidate"), ("Spatial loss", "loss"), ("Normalized MAE", "nmae"),
        ("Tube × depth TV", "joint_tv"), ("Depth TV", "depth_tv"),
        ("Underprediction", "under"), ("Overprediction", "over"),
        ("Misses given field hit", "miss"), ("False hits given field zero", "false_hit"),
    ]
    columns = [{"name": name, "id": key, "type": "numeric", "format": rate if key in {"miss", "false_hit"} else numeric}
               if key != "candidate" else {"name": name, "id": key} for name, key in cols]
    return dbc.Container([
        html.H1("Core Comparison", className="my-3"),
        html.P("Score projected root length density on held physical tubes. Use a local dashboard for restricted field files."),
        html.Details([
            html.Summary("CSV format"),
            html.P("Use split, candidate, core_id, z_lower_cm, z_upper_cm, core_volume_cm3, rld_est and predicted_rld."),
            html.P("Include observed training rows once with split train. Repeat the identical measured held rows for each candidate "
                   "with split held and fill in its predicted RLD. Use elevation in cm with the soil surface at zero."),
        ], className="mb-3"),
        dcc.Upload(id="core-comparison-file", children=dbc.Button("Load core CSV", outline=True)),
        html.Label("Presence threshold (cm/cm³)", htmlFor="core-comparison-threshold", className="d-block mt-3"),
        dbc.Input(id="core-comparison-threshold", type="number", value=0, min=0, step="any"),
        dbc.Button("Compare candidates", id="core-comparison-run", className="mt-3"),
        html.Div(id="core-comparison-status", role="status", className="my-3"),
        dash_table.DataTable(id="core-comparison-table", columns=columns, sort_action="native",
                             style_cell={"textAlign": "left"}, style_table={"overflowX": "auto"}),
        html.P("The presence rates describe the supplied prediction fields. A field averaged over simulated vines describes mean-field presence.",
               className="mt-3"),
    ])


@callback(Output("core-comparison-status", "children"), Output("core-comparison-table", "data"),
          Input("core-comparison-run", "n_clicks"), State("core-comparison-file", "contents"),
          State("core-comparison-threshold", "value"), prevent_initial_call=True)
def compare(_clicks, contents, threshold):
    if not contents:
        return "Load an aligned physical-core CSV.", []
    try:
        encoded = contents.split(",", 1)[1]
        if len(encoded) > 2_000_000:
            raise ValueError("Supply a core-comparison CSV under 1.5 MB.")
        rows, train, held = compare_core_csv(base64.b64decode(encoded, validate=True).decode("utf-8"),
                                             threshold_rld=0 if threshold is None else float(threshold))
    except (IndexError, TypeError, ValueError) as exc:
        return str(exc), []
    return f"{len(rows)} candidates · {train} training tubes · {held} held tubes · lower loss is better", rows
