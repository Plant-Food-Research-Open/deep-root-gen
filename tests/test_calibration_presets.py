"""Dashboard calibration defaults and settings round trips with invented data."""

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from dash import no_update
from omegaconf import OmegaConf

from deeprootgen.calibration import parameters
from deeprootgen.form import calibration_presets, components
from deeprootgen.form.calibration import validate_calibration_form
from deeprootgen.pipeline import experiment

ROOT = Path(__file__).resolve().parents[1]
FORM = "calibration_form"
RANGES = ROOT / "examples/research/ui_calibration_ranges_synthetic.yaml"


@pytest.fixture
def form(monkeypatch):
    cfg = OmegaConf.load(ROOT / f"app/conf/{FORM}/common.yaml")
    app = SimpleNamespace(settings={FORM: cfg})
    for module in (components, calibration_presets, experiment, parameters):
        monkeypatch.setattr(module, "get_app", lambda: app)
    return cfg.components


def _data(text):
    return base64.b64encode(text.encode()).decode()


def test_fresh_calibration_defaults_use_configured_switches_and_option_values(form):
    for task in ("optimisation", "sensitivity_analysis", "abc", "snpe", "surrogate"):
        values = dict(zip(
            (spec.param for spec in form[task].children),
            components.form_control_defaults(FORM, task),
        ))
        assert values["summary_statistics"] == ["root_number"]
        assert values["stat_by_soil_layer"] is False
        assert values["stat_by_soil_column"] is False
        if task in ("snpe", "surrogate"):
            assert values["use_summary_statistics"] is True
        if task != "snpe":
            assert values["distance_metrics"] == ["l1_norm"]
        if task == "surrogate":
            assert type(values["include_parameters"]) is list
            assert values["include_parameters"] == values["exclude_parameters"] == []


@pytest.mark.parametrize("task", ["snpe", "surrogate"])
def test_save_reset_and_load_preserve_validated_request(form, monkeypatch, tmp_path, task):
    callbacks = {}

    def register(*args, **kwargs):
        def capture(fn):
            callbacks[fn.__name__] = fn
            return fn
        return capture

    page = f"{task}-root-system-page"
    ctx = SimpleNamespace(triggered_id=None)
    monkeypatch.setattr(calibration_presets, "callback", register)
    monkeypatch.setattr(calibration_presets, "clientside_callback", lambda *args, **kwargs: None)
    monkeypatch.setattr(calibration_presets, "ctx", ctx)
    monkeypatch.setattr(calibration_presets, "s3_upload_file", lambda *_: None)
    monkeypatch.setattr(experiment, "OUT_DIR", str(tmp_path))
    calibration_presets.register_calibration_preset_callbacks(page, FORM, task)

    preset = yaml.safe_load(RANGES.read_text())
    preset.update(n_epochs=1, stat_by_soil_layer=True, stat_by_soil_column=True)
    if task == "snpe":
        preset.update(use_summary_statistics=False, summary_statistics=None)
    else:
        preset.update(input_columns=["x", "y"], output_columns=["length"])

    parameter_values = [preset[spec.param] for spec in form.parameters.children]
    values = [preset[spec.param] for spec in form[task].children if spec.get("handler") != "boolean_switch"]
    switches = [preset[spec.param] for spec in form[task].children if spec.get("handler") == "boolean_switch"]

    def request(values_by_group):
        params, settings, flags = values_by_group
        return components.build_calibration_parameters(
            FORM,
            task,
            params,
            calibration_presets.calibration_controls(FORM, task, settings, flags),
            summary_statistics=[{"statistic_name": "total_length", "statistic_value": 50}]
            if task == "surrogate" else [{"unused": "wrong schema"}],
            observed_data_content=_data("node_id,parent_id,x\n0,-1,0\n1,0,2\n"),
            raw_edge_content=_data("parent_id,child_id\n0,1\n"),
        )

    before = request((parameter_values, values, switches))
    downloaded = callbacks["save_preset"]([1], parameter_values, values, switches)
    exported = yaml.safe_load(base64.b64decode(downloaded["content"]))
    assert exported["random_seed"] == 0
    assert exported["n_epochs"] == 1
    assert exported["use_summary_statistics"] is (task == "surrogate")

    ctx.triggered_id = f"{page}-reset-params"
    reset = callbacks["restore_preset"]([None], 1, [None])
    assert reset[:3] != (parameter_values, values, switches)
    assert reset[2] == [True, False, False]

    ctx.triggered_id = {"index": f"{page}-upload-param-file-button", "type": f"{page}-simulation"}
    bad_upload = callbacks["restore_preset"](["data:text/yaml;base64,bad"], 1, ["bad.yaml"])
    assert bad_upload[:3] == (no_update, no_update, no_update)
    assert "Could not load parameter settings" in str(bad_upload[4])

    uploaded = "data:application/x-yaml;base64," + downloaded["content"]
    restored = callbacks["restore_preset"]([uploaded], 1, [downloaded["filename"]])
    assert restored[:3] == (parameter_values, values, switches)
    assert validate_calibration_form(task, before) == validate_calibration_form(task, request(restored[:3]))
    if task == "snpe":
        assert before["summary_statistics"] is None
    else:
        assert before["statistics_comparison"]["input_columns"] == ["x", "y"]
        assert before["statistics_comparison"]["output_columns"] == ["length"]


def test_legacy_preset_switch_and_dropdown_recovery(form):
    preset = yaml.safe_load(RANGES.read_text())
    preset.update(summary_statistics=[{"label": "Total Length", "value": "total_length"}])
    preset["use_summary_statistics"] = None
    del preset["stat_by_soil_column"]
    upload = "data:application/x-yaml;base64," + _data(yaml.safe_dump(preset))
    (_, controls), _ = experiment.load_form_parameters([upload], ["old.yaml"], FORM, "snpe")
    values = dict(zip((spec.param for spec in form.snpe.children), controls))
    assert values["use_summary_statistics"] is True
    assert values["stat_by_soil_column"] is False
    assert values["summary_statistics"] == ["total_length"]
