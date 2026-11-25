"""Dashboard CSV and EDA dataset replacement checks with no external services."""

import base64
from pathlib import Path
from runpy import run_path

import dash
import pytest
from dash import no_update

from deeprootgen.form.uploads import load_csv_upload


def _upload(text):
    return "data:text/csv;base64," + base64.b64encode(text.encode()).decode()


@pytest.mark.parametrize(
    "contents,problem",
    [
        ("data:text/csv;base64,!", "base64"),
        (_upload("node_id,parent_id\n"), "data rows"),
        (_upload("node_id,node_id\n1,2\n"), "duplicate"),
        (_upload("node_id,parent_id\n1,2,3\n"), "number of fields"),
        (_upload('node_id,parent_id\n"1,2\n'), "unexpected end of data"),
        (_upload("column_a,column_b\n1,2\n"), "Missing columns"),
    ],
)
def test_invalid_csv_preserves_both_stores(contents, problem):
    parsed, raw, message = load_csv_upload(
        [contents], ["bad.csv"], required_columns=("node_id", "parent_id")
    )
    assert parsed is no_update
    assert raw is no_update
    assert problem in message


@pytest.fixture
def eda(monkeypatch):
    callbacks = {}

    def callback(*dependencies, **_):
        def register(function):
            callbacks[function.__name__] = dependencies
            return function

        return register

    monkeypatch.setattr(dash, "register_page", lambda *_, **__: None)
    monkeypatch.setattr(dash, "callback", callback)
    root = Path(__file__).resolve().parents[1]
    namespace = run_path(str(root / "app/pages/eda_root_system.py"))
    return namespace, callbacks


def test_replacing_data_refreshes_plots_with_the_same_axis_selection(eda):
    namespace, callbacks = eda
    load = namespace["load_node_data"]
    plot = namespace["update_xy_plots"]
    old_file = _upload("x,y,group\n2,4,7\n")
    new_file = _upload("x,y,group\n20,40,7\n")

    previous, _, _, _ = load([old_file], ["previous.csv"])
    replacement, raw, opened, _ = load([new_file], ["replacement.csv"])
    assert opened
    assert raw == {"values": new_file.split(",", 1)[1]}

    for name in (
        "update_xy_plots",
        "update_x_plots",
        "update_y_plots",
        "update_x_statistic_plot",
        "update_y_statistic_plot",
        "update_xy_statistic_plot",
    ):
        assert dash.Input("store-simulation-data", "data") in [
            item for item in callbacks[name] if isinstance(item, dash.Input)
        ]
    before, _ = plot(["x"], ["y"], ["group"], previous)
    after, _ = plot(["x"], ["y"], ["group"], replacement)
    assert before[0].data[0].x.tolist() == [2]
    assert after[0].data[0].x.tolist() == [20]
    assert plot(["missing"], ["y"], ["group"], replacement) == ([{}], [{}])
    assert plot(["x"], ["y"], ["group"], None) == ([{}], [{}])


def test_incompatible_dataset_shows_statistic_feedback(eda):
    namespace, _ = eda
    (figure,) = namespace["update_x_statistic_plot"](
        ["total_length"], {"values": [{"x": 1, "y": 2}]}
    )
    assert "Missing root graph columns" in figure.layout.annotations[0].text
