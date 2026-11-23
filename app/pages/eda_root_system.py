#!/usr/bin/env python

######################################
# Imports
######################################

from html import escape

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import (
    ALL,
    Input,
    Output,
    State,
    callback,
    get_app,
    html,
    no_update,
    register_page,
)

from deeprootgen.form import get_common_layout
from deeprootgen.form.uploads import load_csv_upload
from deeprootgen.statistics import get_summary_statistic_func

px.defaults.template = "ggplot2"

######################################
# Constants
######################################

TITLE = "Exploratory Data Analysis"
TASK = "eda"
PAGE_ID = f"{TASK}-root-system-page"
FORM_NAME = "eda_form"
PROCEDURE = "exploratory-data-analysis"
DATA_COMPONENT_KEY = "simulated_data"

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
    Output(f"{PAGE_ID}-simulated-data-collapse", "is_open"),
    [Input(f"{PAGE_ID}-simulated-data-collapse-button", "n_clicks")],
    [State(f"{PAGE_ID}-simulated-data-collapse", "is_open")],
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
    Output({"index": f"{PAGE_ID}-simulation-runs-table", "type": ALL}, "data"),
    Input("store-simulation-run", "data"),
)
def update_table(runs: list | None) -> list | None:
    """Update the simulation run table.

    Args:
        runs (list | None):
            The list of simulation runs.

    Returns:
        list | None:
            The updated list of simulation runs.
    """
    if runs is None:
        return no_update
    return [runs]


@callback(
    Output(
        {"index": f"{PAGE_ID}-upload-node-data-file-button", "type": ALL}, "children"
    ),
    Output({"index": f"{PAGE_ID}-clear-obs-data-file-button", "type": ALL}, "disabled"),
    Output({"index": f"{PAGE_ID}-select-x-axis-dropdown", "type": ALL}, "options"),
    Output({"index": f"{PAGE_ID}-select-y-axis-dropdown", "type": ALL}, "options"),
    Output({"index": f"{PAGE_ID}-select-group-by-dropdown", "type": ALL}, "options"),
    Input("store-simulation-data", "data"),
)
def update_eda_data_state(eda_data: dict | None) -> tuple:
    """Update the state of the exploratory data analysis data.

    Args:
        eda_data (dict | None):
            The exploratory data analysis data.

    Returns:
        tuple:
            The updated form state.
    """
    eda_data = eda_data or {}
    eda_label = eda_data.get("label")
    eda_values = eda_data.get("values")
    if not eda_label or not eda_values:
        return ["Load simulation data"], [True], [[]], [[]], [[]]

    df_columns = pd.DataFrame(eda_values).columns
    columns = []
    for df_column in df_columns:
        columns.append(
            {"label": df_column.replace("_", " ").title(), "value": df_column}
        )

    return [eda_label], [False], [columns], [columns], [columns]


@callback(
    Output("store-simulation-data", "data", allow_duplicate=True),
    Output("store-raw-simulation-data", "data", allow_duplicate=True),
    Output(f"{PAGE_ID}-load-toast", "is_open", allow_duplicate=True),
    Output(f"{PAGE_ID}-load-toast", "children", allow_duplicate=True),
    Input(
        {"index": f"{PAGE_ID}-upload-node-data-file-button", "type": ALL}, "contents"
    ),
    State(
        {"index": f"{PAGE_ID}-upload-node-data-file-button", "type": ALL}, "filename"
    ),
    prevent_initial_call=True,
)
def load_node_data(list_of_contents: list | None, list_of_names: list | None) -> tuple:
    """Load node data from file.

    Args:
        list_of_contents (list):
            The list of file contents.
        list_of_names (list):
            The list of file names.

    Returns:
        tuple:
            The updated form state.
    """
    parsed, raw, message = load_csv_upload(list_of_contents, list_of_names)
    if message is no_update:
        return no_update
    return parsed, raw, True, message


@callback(
    Output("store-simulation-data", "data", allow_duplicate=True),
    Output("store-raw-simulation-data", "data", allow_duplicate=True),
    Output(
        {"type": f"{PAGE_ID}-parameters", "index": ALL}, "value", allow_duplicate=True
    ),
    Output(
        {"index": f"{PAGE_ID}-upload-node-data-file-button", "type": ALL}, "contents"
    ),
    Output(f"{PAGE_ID}-load-toast", "is_open", allow_duplicate=True),
    Output(f"{PAGE_ID}-load-toast", "children", allow_duplicate=True),
    Input({"index": f"{PAGE_ID}-clear-obs-data-file-button", "type": ALL}, "n_clicks"),
    State("store-simulation-data", "data"),
    prevent_initial_call=True,
)
def clear_observation_data(n_clicks: list[int] | None, eda_data: dict | None) -> tuple:
    """Clear observation data from the page.

    Args:
        n_clicks (list[int] | None):
            The number of form clicks.
        eda_data (dict | None):
            The exploratory data analysis data.

    Returns:
        tuple:
            The updated form state.
    """
    if not n_clicks or not n_clicks[0]:
        return no_update

    eda_label = (eda_data or {}).get("label")
    if not eda_label:
        return no_update

    toast_message = f"Clearing: {eda_label}"

    app = get_app()
    form_model = app.settings[FORM_NAME]
    clear_form = [None for _ in form_model.components["parameters"]["children"]]
    return {}, {}, clear_form, [None], True, toast_message


@callback(
    Output({"index": f"{PAGE_ID}-scatter-xy-plot", "type": ALL}, "figure"),
    Output({"index": f"{PAGE_ID}-heatmap-xy-plot", "type": ALL}, "figure"),
    Input({"index": f"{PAGE_ID}-select-x-axis-dropdown", "type": ALL}, "value"),
    Input({"index": f"{PAGE_ID}-select-y-axis-dropdown", "type": ALL}, "value"),
    Input({"index": f"{PAGE_ID}-select-group-by-dropdown", "type": ALL}, "value"),
    Input("store-simulation-data", "data"),
)
def update_xy_plots(
    x_axes: list | None,
    y_axes: list | None,
    group_bys: list | None,
    eda_data: dict | None,
) -> tuple | None:
    """Update the plot states.

    Args:
        x_axes (list | None):
            The x axis list of values.
        y_axes (list | None):
            The y axis list of values.
        group_bys (list | None):
            The column to group data by.
        eda_data (dict | None):
            The list of observed data.

    Returns:
        tuple | None:
            The updated plot states.
    """
    if not x_axes or not y_axes or not group_bys:
        return no_update

    x_axis = x_axes[0]
    y_axis = y_axes[0]
    group_by = group_bys[0]
    df = pd.DataFrame((eda_data or {}).get("values"))
    if x_axis not in df or y_axis not in df:
        return [{}], [{}]
    if group_by in df:
        df[group_by] = df[group_by].astype("category")
    else:
        group_by = None

    scatter_plot = px.scatter(
        title=f"{y_axis.title()} against {x_axis.title()}",
        data_frame=df,
        x=x_axis,
        y=y_axis,
        color=group_by,
    ).update_layout(xaxis_title=x_axis.title(), yaxis_title=y_axis.title())

    heatmap = px.density_heatmap(
        title=f"{y_axis.title()} against {x_axis.title()}",
        data_frame=df,
        x=x_axis,
        y=y_axis,
    ).update_layout(xaxis_title=x_axis.title(), yaxis_title=y_axis.title())

    return [scatter_plot], [heatmap]


@callback(
    Output({"index": f"{PAGE_ID}-histogram-x-plot", "type": ALL}, "figure"),
    Output({"index": f"{PAGE_ID}-box-x-plot", "type": ALL}, "figure"),
    Input({"index": f"{PAGE_ID}-select-x-axis-dropdown", "type": ALL}, "value"),
    Input({"index": f"{PAGE_ID}-select-group-by-dropdown", "type": ALL}, "value"),
    Input("store-simulation-data", "data"),
)
def update_x_plots(
    x_axes: list | None, group_bys: list | None, eda_data: dict | None
) -> tuple | None:
    """Update the x axis plot states.

    Args:
        x_axes (list | None):
            The x axis list of values.
        group_bys (list | None):
            The column to group data by.
        eda_data (dict | None):
            The list of observed data.

    Returns:
        tuple | None:
            The updated plot states.
    """
    if not x_axes or not group_bys:
        return no_update

    x_axis = x_axes[0]
    group_by = group_bys[0]
    df = pd.DataFrame((eda_data or {}).get("values"))
    if x_axis not in df:
        return [{}], [{}]
    if group_by in df:
        df[group_by] = df[group_by].astype("category")
    else:
        group_by = None

    hist_x = px.histogram(
        title=x_axis.title(),
        data_frame=df,
        x=x_axis,
    ).update_layout(xaxis_title=x_axis.title(), yaxis_title="Count")

    box_x = px.box(
        title=x_axis.title(), data_frame=df, y=x_axis, x=group_by
    ).update_layout(
        yaxis_title=x_axis.title(),
    )

    return [hist_x], [box_x]


@callback(
    Output({"index": f"{PAGE_ID}-histogram-y-plot", "type": ALL}, "figure"),
    Output({"index": f"{PAGE_ID}-box-y-plot", "type": ALL}, "figure"),
    Input({"index": f"{PAGE_ID}-select-y-axis-dropdown", "type": ALL}, "value"),
    Input({"index": f"{PAGE_ID}-select-group-by-dropdown", "type": ALL}, "value"),
    Input("store-simulation-data", "data"),
)
def update_y_plots(
    y_axes: list | None, group_bys: list | None, eda_data: dict | None
) -> tuple | None:
    """Update the x axis plot states.

    Args:
        y_axes (list | None):
            The y axis list of values.
        group_bys (list | None):
            The column to group data by.
        eda_data (dict | None):
            The list of observed data.

    Returns:
        tuple | None:
            The updated plot states.
    """
    if not y_axes or not group_bys:
        return no_update

    y_axis = y_axes[0]
    group_by = group_bys[0]
    df = pd.DataFrame((eda_data or {}).get("values"))
    if y_axis not in df:
        return [{}], [{}]
    if group_by in df:
        df[group_by] = df[group_by].astype("category")
    else:
        group_by = None

    hist_y = px.histogram(
        title=y_axis.title(),
        data_frame=df,
        x=y_axis,
    ).update_layout(xaxis_title=y_axis.title(), yaxis_title="Count")

    box_y = px.box(
        title=y_axis.title(), data_frame=df, y=y_axis, x=group_by
    ).update_layout(
        yaxis_title=y_axis.title(),
    )

    return [hist_y], [box_y]


def _make_statistic(name: str, nodes: pd.DataFrame):
    statistic = get_summary_statistic_func(name)
    if statistic is None:
        raise ValueError(f"Unknown summary statistic {name}.")
    density = (
        nodes["root_tissue_density"].iloc[0] if "root_tissue_density" in nodes else None
    )
    return statistic(root_tissue_density=density)


def _statistic_message(error: Exception) -> go.Figure:
    return (
        go.Figure()
        .add_annotation(
            text=f"Cannot plot this statistic for the current dataset.<br>{escape(str(error))}",
            showarrow=False,
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
        )
        .update_xaxes(visible=False)
        .update_yaxes(visible=False)
    )


def _statistic_figure(summary_stats: list | None, eda_data: dict | None):
    if not summary_stats:
        return no_update
    df = pd.DataFrame((eda_data or {}).get("values"))
    if not summary_stats[0] or df.empty:
        return [{}]
    try:
        return [_make_statistic(summary_stats[0], df).visualise(df)]
    except (KeyError, TypeError, ValueError) as exc:
        return [_statistic_message(exc)]


@callback(
    Output({"index": f"{PAGE_ID}-x-summary-statistic-plot", "type": ALL}, "figure"),
    Input(
        {"index": f"{PAGE_ID}-select-x-summary-stats-dropdown", "type": ALL}, "value"
    ),
    Input("store-simulation-data", "data"),
)
def update_x_statistic_plot(summary_stats: list | None, eda_data: dict | None):
    """Update the x summary-statistic plot for the current dataset."""
    return _statistic_figure(summary_stats, eda_data)


@callback(
    Output({"index": f"{PAGE_ID}-y-summary-statistic-plot", "type": ALL}, "figure"),
    Input(
        {"index": f"{PAGE_ID}-select-y-summary-stats-dropdown", "type": ALL},
        "value",
    ),
    Input("store-simulation-data", "data"),
)
def update_y_statistic_plot(summary_stats: list | None, eda_data: dict | None):
    """Update the y summary-statistic plot for the current dataset."""
    return _statistic_figure(summary_stats, eda_data)


@callback(
    Output({"index": f"{PAGE_ID}-scatter-statistics-plot", "type": ALL}, "figure"),
    Output({"index": f"{PAGE_ID}-heatmap-statistics-plot", "type": ALL}, "figure"),
    Input(
        {"index": f"{PAGE_ID}-select-x-summary-stats-dropdown", "type": ALL},
        "value",
    ),
    Input(
        {"index": f"{PAGE_ID}-select-y-summary-stats-dropdown", "type": ALL},
        "value",
    ),
    Input("store-simulation-data", "data"),
)
def update_xy_statistic_plot(
    x_summary_stats: list | None, y_summary_stats: list | None, eda_data: dict | None
) -> tuple | None:
    """Update the y summary statistic plot state.

    Args:
        x_summary_stats (list | None):
            The list of summary statistics for the x axis.
        y_summary_stats (list | None):
            The list of summary statistics for the x axis.
        eda_data (dict | None):
            The list of observed data.

    Returns:
        tuple | None:
            The updated plot state.
    """
    if not x_summary_stats or not y_summary_stats:
        return no_update
    df = pd.DataFrame((eda_data or {}).get("values"))
    x_summary_stat, y_summary_stat = x_summary_stats[0], y_summary_stats[0]
    if df.empty or not x_summary_stat or not y_summary_stat:
        return [{}], [{}]

    try:
        x_data = _make_statistic(x_summary_stat, df).get_xy_comparison_data(df, 10)
        y_data = _make_statistic(y_summary_stat, df).get_xy_comparison_data(df, 10)
        if len(x_data) != len(y_data):
            raise ValueError("Choose two statistics with the same number of values.")
        x_label = x_summary_stat.replace("_", " ").title()
        y_label = y_summary_stat.replace("_", " ").title()
        scatter_plot = px.scatter(x=x_data, y=y_data).update_layout(
            xaxis_title=x_label, yaxis_title=y_label
        )
        heatmap = px.density_heatmap(x=x_data, y=y_data).update_layout(
            xaxis_title=x_label, yaxis_title=y_label
        )
    except (KeyError, TypeError, ValueError) as exc:
        invalid = _statistic_message(exc)
        return [invalid], [invalid]

    return [scatter_plot], [heatmap]


######################################
# Layout
######################################


register_page(__name__, name=TITLE, top_nav=True, path=f"/{TASK}")


def layout() -> html.Div:
    """Return the page layout.

    Returns:
        html.Div: The page layout.
    """
    page_description = "Upload a simulation CSV, then choose columns or root statistics to plot."

    layout = get_common_layout(
        title=TITLE,
        page_id=PAGE_ID,
        page_description=page_description,
        parameter_form_name=FORM_NAME,
        simulation_form_name=FORM_NAME,
        procedure=TITLE,
        task=TASK,
        data_key=DATA_COMPONENT_KEY,
        left_sticky=True,
        right_sticky=False,
    )
    return layout
