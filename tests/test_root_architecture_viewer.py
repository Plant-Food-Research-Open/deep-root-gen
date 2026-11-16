"""Invented geometry tests for the standalone viewer; no empirical inputs."""

import copy
from html.parser import HTMLParser
import json

import pytest

from scripts.research.root_architecture_viewer import build_comparison_html


class _Document(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.scripts = {}
        self.active_script = None
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.tags.append((tag, attributes))
        if tag == "script":
            self.active_script = attributes.get("id", f"script-{len(self.scripts)}")
            self.scripts[self.active_script] = ""

    def handle_endtag(self, tag):
        if tag == "script":
            self.active_script = None

    def handle_data(self, data):
        if self.active_script is not None:
            self.scripts[self.active_script] += data


@pytest.fixture
def payload():
    return {
        "title": "Invented roots",
        "subtitle": "Geometry in shared example units",
        "panels": [
            {
                "title": "Example A",
                "description": "A disconnected literal pair",
                "polylines": [
                    {"order": 1, "points": [[-23, 8, 2], [-21.5, 12, 13]]},
                    {"order": 3, "points": [[17, -3, 4], [19, 0, 8]]},
                ],
            },
            {
                "title": "Example B",
                "description": "A separate invented architecture",
                "polylines": [
                    {"order": 2, "points": [[5, -17, -2], [15, 21, 29]]},
                    {"order": 5, "points": [[11, 3, 12], [12, 4, 15], [13, 7, 19]]},
                ],
            },
        ],
        "summary_rows": [
            {
                "label": "Illustrative length",
                "observed": "4.2 ± 0.3",
                "generated": "4.5",
                "unit": "example units",
            }
        ],
        "footer": "Entirely invented. No biological evaluation.",
    }


def test_literal_geometry_and_shared_physical_ranges(payload, tmp_path):
    original = copy.deepcopy(payload)
    output = build_comparison_html(payload, tmp_path / "nested" / "comparison.html")
    doc = _Document(output.read_text())
    embedded = json.loads(doc.scripts["comparison-data"])
    assert embedded == original
    assert payload == original
    display = json.loads(doc.scripts["display-config"])
    ranges = display["ranges"]
    all_points = [
        point
        for panel in payload["panels"]
        for line in panel["polylines"]
        for point in line["points"]
    ]
    for axis in range(3):
        assert ranges[axis][0] < min(point[axis] for point in all_points)
        assert ranges[axis][1] > max(point[axis] for point in all_points)
    assert ranges[2][0] <= 0 <= ranges[2][1]
    app = list(doc.scripts.values())[-1]
    spans = [high - low for low, high in ranges]
    assert display["aspectratio"] == dict(
        zip("xyz", (span / max(spans) for span in spans))
    )
    assert 'aspectmode:"manual",aspectratio:clone(display.aspectratio)' in app
    assert "connectgaps:false" in app
    assert "x.push(null);y.push(null);z.push(null)" in app
    assert "point[0]" in app and "point[1]" in app and "point[2]" in app
    assert 'zaxis:axis("Depth ↓",[ranges[2][1],ranges[2][0]])' in app
    assert "autorange:false" in app


@pytest.mark.parametrize("count", [0, 1, 3])
def test_exactly_two_panels_are_required(payload, count, tmp_path):
    payload["panels"] = [copy.deepcopy(payload["panels"][0]) for _ in range(count)]
    with pytest.raises(ValueError, match="exactly two"):
        build_comparison_html(payload, tmp_path / "invalid.html")
    assert not (tmp_path / "invalid.html").exists()


@pytest.mark.parametrize("order", [0, 6, -1, True, 1.5, "1"])
def test_orders_are_explicit_supported_integers(payload, order, tmp_path):
    payload["panels"][0]["polylines"][0]["order"] = order
    with pytest.raises(ValueError, match="order"):
        build_comparison_html(payload, tmp_path / "invalid.html")


@pytest.mark.parametrize(
    "coordinate",
    [float("nan"), float("inf"), -float("inf"), True, None, "1", 10**1000],
)
def test_coordinates_must_be_finite_numbers(payload, coordinate, tmp_path):
    payload["panels"][0]["polylines"][0]["points"][0][1] = coordinate
    with pytest.raises(ValueError, match="finite real"):
        build_comparison_html(payload, tmp_path / "invalid.html")


@pytest.mark.parametrize(
    "points", [[], [[0, 0, 0]], [[0, 0], [1, 1]], [[0, 0, 0, 0], [1, 1, 1]], "geometry"]
)
def test_incomplete_geometry_is_rejected(payload, points, tmp_path):
    payload["panels"][0]["polylines"][0]["points"] = points
    with pytest.raises(ValueError):
        build_comparison_html(payload, tmp_path / "invalid.html")


def test_unknown_metadata_is_rejected_without_writing(payload, tmp_path):
    destination = tmp_path / "existing.html"
    destination.write_text("preserve existing output")
    for target, field in (
        (payload, "source_path"),
        (payload["panels"][0], "raw_path"),
        (payload["panels"][0]["polylines"][0], "root_id"),
    ):
        target[field] = "/invented/private/location.csv"
        with pytest.raises(ValueError, match="unsupported"):
            build_comparison_html(payload, destination)
        assert destination.read_text() == "preserve existing output"
        del target[field]


def test_hostile_display_text_cannot_add_html_or_executable_script(payload, tmp_path):
    hostile = '</script><script src="https://invalid.example/steal.js">bad()</script><img src=x onerror=bad()> & \u2028\u2029 {{PLOTLY}} {{PAYLOAD}}'
    payload["title"] = hostile
    payload["subtitle"] = hostile
    payload["panels"][0]["title"] = hostile
    payload["panels"][0]["description"] = hostile
    payload["summary_rows"][0]["observed"] = hostile
    payload["footer"] = hostile
    source = build_comparison_html(payload, tmp_path / "safe.html").read_text()
    doc = _Document(source)
    assert len(doc.scripts) == 4
    assert not any(tag == "img" for tag, attrs in doc.tags)
    assert not any("src" in attrs for tag, attrs in doc.tags if tag == "script")
    assert not any(
        any(key.startswith("on") for key in attrs) for tag, attrs in doc.tags
    )
    assert json.loads(doc.scripts["comparison-data"]) == payload
    assert "\\u003c/script\\u003e" in doc.scripts["comparison-data"]
    assert "\\u2028\\u2029" in doc.scripts["comparison-data"]
    assert hostile not in source


def test_standalone_controls_and_offline_policy(payload, tmp_path):
    source = build_comparison_html(payload, tmp_path / "offline.html").read_text()
    doc = _Document(source)
    assert not any("src" in attrs or "href" in attrs for tag, attrs in doc.tags)
    assert "connect-src 'none'" in source
    assert "Plotly" in list(doc.scripts.values())[2]
    ids = {attrs.get("id") for tag, attrs in doc.tags}
    assert {
        "plot-0",
        "plot-1",
        "sync-camera",
        "show-soil",
        "viewer-status",
        "camera-perspective",
        "camera-front",
        "camera-side",
        "camera-top",
        "camera-reset",
        *(f"order-{order}" for order in range(1, 6)),
    } <= ids
    for control in (
        "sync-camera",
        "show-soil",
        *(f"order-{order}" for order in range(1, 6)),
    ):
        attrs = next(attrs for tag, attrs in doc.tags if attrs.get("id") == control)
        assert "checked" in attrs and attrs["type"] == "checkbox"
    assert "measured diameters are not represented" in source
    assert ">Oblique</button>" in source
    assert 'projection:{type:"perspective"}' not in list(doc.scripts.values())[-1]
    assert 'key==="scene.aspectratio"' in list(doc.scripts.values())[-1]
    assert (
        "setCamera(cameras[name],plots,display.aspectratio)"
        in list(doc.scripts.values())[-1]
    )
    assert "window.rootViewer=" in source


def test_zero_spread_geometry_has_usable_finite_axes(payload, tmp_path):
    for panel in payload["panels"]:
        panel["polylines"] = [{"order": 1, "points": [[0, 0, 0], [0, 0, 0]]}]
    source = build_comparison_html(payload, tmp_path / "point.html").read_text()
    display = json.loads(_Document(source).scripts["display-config"])
    assert all(low < 0 < high for low, high in display["ranges"])


def test_optional_summary_is_omitted_without_changing_geometry(payload, tmp_path):
    del payload["summary_rows"]
    del payload["footer"]
    del payload["subtitle"]
    source = build_comparison_html(payload, tmp_path / "minimal.html").read_text()
    doc = _Document(source)
    assert json.loads(doc.scripts["comparison-data"])["panels"] == payload["panels"]
    assert not any(tag == "table" for tag, attrs in doc.tags)
