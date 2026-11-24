"""Regression checks for dashboard submission, validation and model-service feedback.

All network calls are replaced with test doubles; no Prefect, MLflow or BentoML
service is contacted.
"""

import base64
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import requests
import yaml
from dash import no_update

from deeprootgen.data_model.simulation_form import simulation_document
from deeprootgen.form import model_services, run_feedback
from deeprootgen.form.architecture_targets import parse_seeds, parse_targets
from deeprootgen.form.calibration import validate_calibration_form
from deeprootgen.pipeline import submission

ROOT = Path(__file__).resolve().parents[1]
RANGES = yaml.safe_load((ROOT / "examples/research/ui_calibration_ranges_synthetic.yaml").read_text())


def calibration_form(task, **calibration):
    """The payload build_calibration_parameters makes from the synthetic preset."""
    spec = yaml.safe_load((ROOT / "app/conf/calibration_form/common.yaml").read_text())["components"]
    values = {"parameter_intervals": {}, "calibration_parameters": {}, "statistics_comparison": {}}
    for item in spec["parameters"]["children"]:
        name = item["param"]
        if "data_type" in item:
            low, high = RANGES[name]
            values["parameter_intervals"][name] = dict(lower_bound=low, upper_bound=high, data_type=item["data_type"])
        else:
            values[name] = RANGES[name]
    for item in spec[task]["children"]:
        name = item["param"]
        target = "statistics_comparison" if item.get("statistic_parameter") else "calibration_parameters"
        values[target][name] = calibration.get(name, RANGES.get(name))
    values["statistics_comparison"].update(stat_by_soil_layer=False, stat_by_soil_column=False,
                                           use_summary_statistics=True)
    values["summary_statistics"] = [{"statistic_name": "total_length", "statistic_value": 50}]
    values["observed_data_content"] = values["raw_edge_content"] = ""
    return values


def csv_content(text):
    return base64.b64encode(text.encode()).decode()


# Prefect submission -------------------------------------------------------


def response(status, payload=None):
    return httpx.Response(status, json=payload or {}, request=httpx.Request("GET", "http://prefect"))


def test_missing_deployment_is_reported_without_submitting(monkeypatch):
    calls = []
    monkeypatch.setattr(submission, "_get", lambda path, timeout=5: response(404 if "deployments" in path else 200))
    monkeypatch.setattr("prefect.deployments.run_deployment", lambda *a, **k: calls.append(a))
    with pytest.raises(submission.SubmissionError) as error:
        submission.submit("simulation", {"input_parameters": {}}, "nonce")
    assert error.value.kind == "missing_deployment"
    assert "simulation/run_simulation_flow" in str(error.value)
    assert calls == []


def test_unreachable_prefect_is_reported_before_sending(monkeypatch):
    def refuse(path, timeout=5):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(submission, "_get", refuse)
    with pytest.raises(submission.SubmissionError) as error:
        submission.check_deployment("abc")
    assert error.value.kind == "unreachable"
    assert "Nothing was submitted" in str(error.value)


def fake_prefect(monkeypatch, existing=None, error=None, pool_status="READY"):
    sent = []

    def get(path, timeout=5):
        if path.startswith("/work_pools/"):
            return response(200, {"status": pool_status})
        if path.startswith("/deployments/name/"):
            return response(200, {"work_pool_name": "default"})
        return response(200)

    def run_deployment(name, parameters, flow_run_name, timeout, idempotency_key):
        sent.append(dict(name=name, parameters=parameters, key=idempotency_key))
        if error is not None:
            raise error
        uuid = existing or parameters["simulation_uuid"]
        # Prefect returns the same flow run for a repeated idempotency key.
        run_id = UUID(int=hash(idempotency_key) % 2**128) if existing else uuid4()
        return SimpleNamespace(id=run_id, name=uuid, parameters={"simulation_uuid": uuid},
                               state=SimpleNamespace(type=SimpleNamespace(value="SCHEDULED")))

    monkeypatch.setattr(submission, "_get", get)
    monkeypatch.setattr("prefect.deployments.run_deployment", run_deployment)
    return sent


def test_idempotency_key_depends_on_nonce_and_payload(monkeypatch):
    sent = fake_prefect(monkeypatch)
    submission.submit("simulation", {"input_parameters": {"a": 1}}, "n1")
    submission.submit("simulation", {"input_parameters": {"a": 1}}, "n1")
    submission.submit("simulation", {"input_parameters": {"a": 2}}, "n1")
    submission.submit("simulation", {"input_parameters": {"a": 1}}, "n2")
    keys = [item["key"] for item in sent]
    assert keys[0] == keys[1] and len(set(keys)) == 3
    assert sent[0]["name"] == "simulation/run_simulation_flow"
    assert sent[0]["parameters"]["simulation_uuid"] != sent[1]["parameters"]["simulation_uuid"]


def test_existing_run_returned_for_repeated_request(monkeypatch):
    fake_prefect(monkeypatch, existing="11111111-1111-1111-1111-111111111111")
    result = submission.submit("abc", {"input_parameters": {}}, "n1")
    assert not result.created
    assert result.simulation_uuid == "11111111-1111-1111-1111-111111111111"
    assert "already accepted" in result.notes[0]


def test_idle_work_pool_is_reported(monkeypatch):
    fake_prefect(monkeypatch, pool_status="NOT_READY")
    result = submission.submit("abc", {"input_parameters": {}}, "n1")
    assert any("No worker" in note for note in result.notes)


def test_uncertain_send_keeps_nonce_and_never_appends(monkeypatch):
    fake_prefect(monkeypatch, error=httpx.ReadTimeout("slow"))
    runs, status, nonce = run_feedback.submit_from_page("simulation", {}, [], "keep-me", "tag")
    assert runs is no_update and nonce == "keep-me"
    assert "may have been queued" in str(status)


def test_accepted_run_appends_once_and_rotates_nonce(monkeypatch):
    fake_prefect(monkeypatch, existing="22222222-2222-2222-2222-222222222222")
    runs, _, nonce = run_feedback.submit_from_page("simulation", {}, [], "n1", "tag")
    assert len(runs) == 1 and runs[0]["state"] == "Scheduled" and nonce != "n1"
    again, _, _ = run_feedback.submit_from_page("simulation", {}, runs, "n1", "tag")
    assert again == runs  # the same flow run id is not added twice


def test_refresh_reports_failure_and_completed_artifacts(monkeypatch):
    states = {"a": ("FAILED", "Failed"), "b": ("COMPLETED", "Completed")}
    monkeypatch.setattr(run_feedback, "read_run_state", lambda run_id: states[run_id])
    monkeypatch.setattr(run_feedback, "artifact_summary", lambda task, uuid: "no MLflow run with this UUID")
    rows = [dict(flow_run_id="a", task="abc", simulation_uuid="x", state="Scheduled"),
            dict(flow_run_id="b", task="abc", simulation_uuid="y", state="Running")]
    updated = run_feedback.refresh_runs(rows)
    assert updated[0]["state"].startswith("Failed · open the run link")
    assert updated[1]["state"] == "Completed · no MLflow run with this UUID"
    assert run_feedback.refresh_runs(updated) is None  # final states are not polled again


# Page-boundary validation -----------------------------------------------


def test_check_setup_never_submits(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("Check setup submitted a job")

    monkeypatch.setattr(run_feedback, "submit_from_page", refuse)
    runs, is_open, status, nonce = run_feedback.calibration_action(
        "abc", calibration_form("abc"), True, [], None)
    assert runs is no_update and nonce is no_update and is_open
    assert "Nothing was submitted" in json.dumps(status.to_plotly_json(), default=str)


def test_submitted_counts_are_whole_numbers(monkeypatch):
    captured = {}

    def capture(task, payload, runs, nonce, tag, **options):
        captured.update(payload)
        return runs, "queued", "next"

    monkeypatch.setattr(run_feedback, "submit_from_page", capture)
    form = calibration_form("optimisation", summary_statistics=["total_length"], n_trials=5,
                            n_startup_trials=2, n_ei_candidates=24.0, n_jobs=1)
    form["parameter_intervals"]["max_order"].update(lower_bound=1, upper_bound=1)
    run_feedback.calibration_action("optimisation", form, False, [], None)
    counts = captured["calibration_parameters"]
    assert counts["n_ei_candidates"] == 24 and isinstance(counts["n_ei_candidates"], int)
    assert json.dumps(counts).count(".0") == 0


@pytest.mark.parametrize("task", ["sensitivity_analysis", "abc", "snpe", "surrogate"])
def test_synthetic_calibration_presets_are_valid(task):
    validate_calibration_form(task, calibration_form(task))


@pytest.mark.parametrize("task,parameter", [
    ("abc", "base_diameter"), ("sensitivity_analysis", "max_order"), ("snpe", "segments_per_root"),
])
def test_zero_width_ranges_are_rejected_where_the_sampler_needs_width(task, parameter):
    form = calibration_form(task)
    form["parameter_intervals"][parameter]["upper_bound"] = form["parameter_intervals"][parameter]["lower_bound"]
    with pytest.raises(ValueError, match=parameter):
        validate_calibration_form(task, form)


def test_abc_accepts_a_fixed_discrete_parameter():
    form = calibration_form("abc")
    form["parameter_intervals"]["max_order"].update(lower_bound=2, upper_bound=2)
    validate_calibration_form("abc", form)


def test_reversed_range_and_missing_statistic_are_rejected():
    form = calibration_form("abc")
    form["parameter_intervals"]["root_vary"].update(lower_bound=30, upper_bound=20)
    with pytest.raises(ValueError, match="root_vary"):
        validate_calibration_form("abc", form)
    form = calibration_form("abc")
    form["summary_statistics"] = [{"statistic_name": "root_number", "statistic_value": 3}]
    with pytest.raises(ValueError, match="total_length"):
        validate_calibration_form("abc", form)


def test_graph_mode_needs_matching_node_and_edge_csvs():
    form = calibration_form("snpe")
    form["statistics_comparison"]["use_summary_statistics"] = False
    with pytest.raises(ValueError, match="node and edge"):
        validate_calibration_form("snpe", form)
    form["observed_data_content"] = csv_content("node_id,parent_id,x\n0,-1,0\n")
    form["raw_edge_content"] = csv_content("source,target\n0,1\n")
    with pytest.raises(ValueError, match="edge CSV is missing columns: child_id, parent_id"):
        validate_calibration_form("snpe", form)
    form["raw_edge_content"] = csv_content("parent_id,child_id\n0,1\n")
    validate_calibration_form("snpe", form)


def test_graph_mode_surrogate_reports_the_gap():
    form = calibration_form("surrogate")
    form["statistics_comparison"]["use_summary_statistics"] = False
    with pytest.raises(ValueError, match="not implemented"):
        validate_calibration_form("surrogate", form)


def upload(text):
    return [f"data:text/csv;base64,{csv_content(text)}"], ["targets.csv"]


def test_statistics_upload_checks_header_and_values():
    data, toast = run_feedback.load_statistics_upload(*upload("statistic_name, statistic_value\ntotal_length, 50\n"))
    assert data["values"] == [{"statistic_name": "total_length", "statistic_value": 50}]
    assert "Loaded 1 statistics" in toast
    data, toast = run_feedback.load_statistics_upload(*upload("name,value\ntotal_length,50\n"))
    assert data is no_update and "statistic_name" in json.dumps(toast.to_plotly_json(), default=str)
    data, toast = run_feedback.load_statistics_upload(*upload("statistic_name,statistic_value\ntotal_length,many\n"))
    assert data is no_update


def test_fraction_targets_without_allocation_controls_explain_the_fix():
    document = json.loads((ROOT / "examples/synthetic_minimal.json").read_text())
    fields = {k: v for k, v in document["parameters"].items() if not isinstance(v, dict)}
    fields.update(random_seed=42, simulation_tag="t", root_ratio_length=0.5)
    with pytest.raises(ValueError) as error:
        simulation_document(fields)
    status = json.dumps(run_feedback.validation_message(error.value).to_plotly_json(), default=str)
    assert "allocation_controls" in status and "[0, 1]" in status
    fields["root_ratio_length"] = 1.5
    with pytest.raises(ValueError):
        simulation_document(fields)
    fields.pop("root_ratio_length")
    assert simulation_document(fields)["parameters"]["primary_root_count"] == 2


# Architecture Search targets ----------------------------------------------


@pytest.mark.parametrize("text", [
    "statistic_name,statistic_value\nroot_number,3\n",
    "statistic_name\tstatistic_value\nroot_number\t3\n",
    "statistic_name   statistic_value\r\nroot_number   3\r\n",
    "statistic_name;statistic_value\nroot_number;3\n",
    " statistic_name , statistic_value \n root_number , 3 \n",
])
def test_pasted_targets_accept_spreadsheet_delimiters(text):
    assert parse_targets(text) == [{"statistic_name": "root_number", "statistic_value": "3"}]


def test_pasted_targets_keep_optional_scale_and_report_bad_headers():
    rows = parse_targets("statistic_name\tstatistic_value\tscale\nroot_number\t3\t2\ntotal_length\t50\n")
    assert rows == [{"statistic_name": "root_number", "statistic_value": "3", "scale": "2"},
                    {"statistic_name": "total_length", "statistic_value": "50"}]
    with pytest.raises(ValueError, match="found name, value"):
        parse_targets("name,value\nroot_number,3\n")
    with pytest.raises(ValueError, match="Line 2"):
        parse_targets("statistic_name,statistic_value\nroot_number,3,4\n")
    assert parse_seeds("0, 1") == [0, 1] and parse_seeds("0 1") == [0, 1]
    with pytest.raises(ValueError, match="whole numbers"):
        parse_seeds("0, one")


# Optional model services --------------------------------------------------


class Reply:
    def __init__(self, status, payload):
        self.status_code, self.payload, self.text = status, payload, json.dumps(payload)

    def json(self):
        return self.payload


def serve(monkeypatch, predict_reply, info=None):
    def post(url, json=None, timeout=None):
        if isinstance(predict_reply, Exception):
            raise predict_reply
        return Reply(200, info or {"available": True, "tag": "abc:v1", "simulation_uuid": "u"}) \
            if url.endswith("/info") else predict_reply

    monkeypatch.setattr(model_services.requests, "post", post)


@pytest.mark.parametrize("reply,kind", [
    (requests.ConnectionError("no route"), "unreachable"),
    (Reply(404, {"error": "No 'abc:latest' model version"}), "missing_model"),
    (Reply(400, {"error": "t must be a list"}), "invalid_input"),
    (Reply(501, {"error": "graph-mode inference is not served"}), "unsupported"),
    (Reply(500, {"error": "boom"}), "service_error"),
    (Reply(500, "BentoML returns a bare JSON string"), "service_error"),
    (Reply(200, []), "invalid_input"),
])
def test_service_failures_are_classified(monkeypatch, tmp_path, reply, kind):
    serve(monkeypatch, reply)
    with pytest.raises(model_services.ServiceError) as error:
        model_services.predict("abc", {"t": [0]}, str(tmp_path), "stamp")
    assert error.value.kind == kind


def test_service_success_writes_a_readable_csv(monkeypatch, tmp_path):
    serve(monkeypatch, Reply(200, [{"t": 0, "w": 0.5, "primary_root_count": 3}]))
    outfile, rows, info = model_services.predict("abc", {"t": [0]}, str(tmp_path), "stamp")
    assert rows == 1 and info["tag"] == "abc:v1"
    assert Path(outfile).read_text().splitlines() == ["t,w,primary_root_count", "0,0.5,3"]


def test_empty_bento_error_body_still_explains(monkeypatch, tmp_path):
    serve(monkeypatch, Reply(404, ""))
    with pytest.raises(model_services.ServiceError, match="no model version to serve"):
        model_services.predict("snpe", {}, str(tmp_path), "stamp")
    serve(monkeypatch, Reply(501, ""))
    with pytest.raises(model_services.ServiceError, match="graph-mode inference"):
        model_services.predict("snpe", {}, str(tmp_path), "stamp")
