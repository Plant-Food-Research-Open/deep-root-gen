"""Exercise dashboard workflows through Dash's own callback endpoint.

The script sends the same ``/_dash-update-component`` requests a browser sends
after a file upload or button click, using only the repository's synthetic
examples. It then follows the Prefect run to a terminal state and lists the
result artifacts tied to that run. It reads no observation data or credentials.

    python scripts/local/dash_workflow_check.py simulation optimisation \
        --dash http://127.0.0.1:18003 --prefect http://127.0.0.1:14203 \
        --mlflow http://127.0.0.1:15003 --receipt receipt.json

``--check-only`` presses Check setup (or Run with an invalid form) without
queuing work. This is an HTTP harness, not a browser: it shows the text a page
would display, not its rendering.
"""

import argparse
import base64
import csv
import io
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONF = ROOT / "app/conf"
EXAMPLES = ROOT / "examples"
RANGES = EXAMPLES / "research/ui_calibration_ranges_synthetic.yaml"
TOTAL_LENGTH = EXAMPLES / "research/ui_total_length_synthetic.csv"
ROOT_NUMBER = EXAMPLES / "research/optimisation_summary_synthetic.csv"
MINIMAL = EXAMPLES / "synthetic_minimal.json"
CONFIG = None  # --config replaces the Simulation upload
PAGES = {
    "simulation": "simulation-root-system-page",
    "optimisation": "optimisation-root-system-page",
    "sensitivity_analysis": "sensitivity-analysis-root-system-page",
    "abc": "abc-root-system-page",
    "snpe": "snpe-root-system-page",
    "surrogate": "surrogate-root-system-page",
}
# Settings from docs/DASH_UI_EXAMPLES.md applied after Load parameters.
OVERRIDES = {
    "optimisation": {"summary_statistics": ["root_number"], "n_trials": 5, "n_startup_trials": 2},
    "sensitivity_analysis": {"n_samples": 4, "n_jobs": 1},
    "abc": {"start_nr_particles": 4, "max_nr_populations": 1, "max_total_nr_simulations": 80,
            "max_walltime": 2, "minimum_epsilon": 0.1},
    "snpe": {"n_simulations": 64, "pp_samples": 10, "sbc_draws": 10,
             "nn_num_hidden_features": 5, "nn_num_transforms": 2},
    "surrogate": {"n_simulations": 16, "n_validation_simulations": 4, "n_holdout_simulations": 4,
                  "n_epochs": 5, "num_inducing_points": 8, "lr": 0.01,
                  "include_parameters": ["min_primary_length", "max_primary_length"]},
}
PARAMETER_OVERRIDES = {
    "optimisation": {"max_order": [1, 1], "segments_per_root": [5, 5], "primary_root_count": [2, 4]},
}
SWITCHES = {"stat-by-soil-layer-switch": False, "stat-by-soil-col-switch": False,
            "use-summary-statistics-switch": True, "use-cost-emulation-switch": True,
            "enable-soil-input": False}


def http(url, body=None, timeout=180):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        text = response.read().decode()
        return response.status, (json.loads(text) if text else None)


def data_url(path, kind):
    return f"data:{kind};base64," + base64.b64encode(Path(path).read_bytes()).decode()


def text_of(node):
    """Flatten a Dash component to its visible text."""
    if node is None or isinstance(node, bool):
        return ""
    if isinstance(node, (str, int, float)):
        return str(node)
    if isinstance(node, list):
        return " ".join(filter(None, (text_of(item) for item in node)))
    if isinstance(node, dict):
        props = node.get("props", {})
        text = text_of(props.get("children"))
        href = props.get("href")
        return f"{text} <{href}>" if href else text
    return ""


def key(component_id):
    return component_id if isinstance(component_id, str) else json.dumps(
        component_id, separators=(",", ":"), sort_keys=True)


class Dash:
    def __init__(self, base):
        self.base = base.rstrip("/")
        _, self.deps = http(f"{self.base}/_dash-dependencies")

    def dep(self, input_fragment, output_fragment=""):
        for dep in self.deps:
            if any(input_fragment in spec["id"] for spec in dep["inputs"]) and output_fragment in dep["output"]:
                return dep
        raise KeyError(f"No callback with input {input_fragment!r} and output {output_fragment!r}")

    def call(self, dep, values, outputs=None, trigger=None):
        """Send a callback. ``values`` maps (id fragment, property) to a value or entry list."""
        def entries(specs):
            result = []
            for spec in specs:
                match = next((v for (frag, prop), v in values.items()
                              if frag in spec["id"] and prop == spec["property"]), None)
                if isinstance(match, list) and match and isinstance(match[0], dict) and "property" in match[0]:
                    result.append(match)
                elif "ALL" in spec["id"]:
                    result.append([])
                else:
                    result.append({"id": spec["id"], "property": spec["property"], "value": match})
            return result

        body = {"output": dep["output"], "inputs": entries(dep["inputs"]), "state": entries(dep["state"]),
                "changedPropIds": [trigger] if trigger else []}
        if outputs is None:  # explicit specs for non-wildcard outputs, as the renderer sends
            outputs = []
            for part in dep["output"].strip(".").split("..."):
                component, prop = part.rsplit(".", 1)
                outputs.append({"id": component, "property": prop})
            outputs = outputs[0] if len(outputs) == 1 and not dep["output"].startswith("..") else outputs
        body["outputs"] = outputs
        status, data = http(f"{self.base}/_dash-update-component", body)
        return status, (data or {}).get("response", {})


def children(form, section):
    return yaml.safe_load((CONF / f"{form}/common.yaml").read_text())["components"][section]["children"]


def defaults(form, section):
    """Layout values a browser keeps when a callback leaves a field unchanged."""
    return [c.get("kwargs", {}).get("value") for c in children(form, section)]


def returned(response, component_ids, fallback):
    return [response[key(i)]["value"] if key(i) in response else default
            for i, default in zip(component_ids, fallback)]


def ids(page, form, section):
    return [{"index": f"{page}-{c['id']}", "type": f"{page}-{section}"} for c in children(form, section)]


def entries(component_ids, prop, values):
    return [{"id": i, "property": prop, "value": v} for i, v in zip(component_ids, values)]


def button(page, name, prop="n_clicks", value=1, section="simulation"):
    component = {"index": f"{page}-{name}", "type": f"{page}-{section}"}
    return [{"id": component, "property": prop, "value": value}], key(component) + "." + prop


def upload(dash, page, name, path, kind, output_fragment, outputs=None, section="simulation"):
    dep = dash.dep(f"{page}-{name}", output_fragment)
    contents, trigger = button(page, name, "contents", data_url(path, kind), section)
    filename, _ = button(page, name, "filename", Path(path).name, section)
    return dash.call(dep, {(f"{page}-{name}", "contents"): contents, (f"{page}-{name}", "filename"): filename},
                     outputs=outputs, trigger=trigger)


def wait_for_run(prefect, run_id, limit):
    deadline = time.time() + limit
    while True:
        _, data = http(f"{prefect}/api/flow_runs/{run_id}")
        if data["state_type"] in {"COMPLETED", "FAILED", "CRASHED", "CANCELLED"} or time.time() > deadline:
            return data
        time.sleep(5)


def mlflow_run(mlflow, task, simulation_uuid):
    _, exp = http(f"{mlflow}/api/2.0/mlflow/experiments/get-by-name?experiment_name=root_model_{task}")
    _, runs = http(f"{mlflow}/api/2.0/mlflow/runs/search", {
        "experiment_ids": [exp["experiment"]["experiment_id"]],
        "filter": f"tags.simulation_uuid = '{simulation_uuid}'"})
    run_id = runs["runs"][0]["info"]["run_id"]
    _, listing = http(f"{mlflow}/api/2.0/mlflow/artifacts/list?run_id={run_id}")
    return run_id, sorted(f["path"] for f in listing.get("files", []))


def mlflow_rows(mlflow, run_id, path):
    query = urllib.parse.urlencode({"path": path, "run_uuid": run_id})
    with urllib.request.urlopen(f"{mlflow}/get-artifact?{query}", timeout=60) as response:
        return list(csv.DictReader(io.StringIO(response.read().decode())))


def load_page_inputs(dash, task):
    """Use the page's own upload callbacks, then apply the documented settings."""
    page = PAGES[task]
    form = "simulation_form" if task == "simulation" else "calibration_form"
    parameter_ids = ids(page, form, "parameters")
    if task == "simulation":
        outputs = [[{"id": i, "property": "value"} for i in parameter_ids],
                   {"id": f"{page}-load-toast", "property": "is_open"},
                   {"id": f"{page}-load-toast", "property": "children"}]
        _, response = upload(dash, page, "upload-param-file-button", CONFIG or MINIMAL, "application/json",
                             "parameters", outputs)
        values = returned(response, parameter_ids, defaults(form, "parameters"))
        return {"parameters": values, "toast": text_of(response.get(f"{page}-load-toast", {}).get("children"))}

    task_ids = ids(page, form, task)
    outputs = [[{"id": i, "property": "value"} for i in parameter_ids],
               [{"id": i, "property": "value"} for i in task_ids],
               {"id": f"{page}-load-toast", "property": "is_open"},
               {"id": f"{page}-load-toast", "property": "children"}]
    _, response = upload(dash, page, "upload-param-file-button", RANGES, "application/x-yaml",
                         "parameters", outputs)
    parameters = returned(response, parameter_ids, defaults(form, "parameters"))
    calibration = returned(response, task_ids, defaults(form, task))
    toast = text_of(response.get(f"{page}-load-toast", {}).get("children"))
    for spec, i in zip(children(form, "parameters"), range(len(parameters))):
        if spec["param"] in PARAMETER_OVERRIDES.get(task, {}):
            parameters[i] = PARAMETER_OVERRIDES[task][spec["param"]]
    for spec, i in zip(children(form, task), range(len(calibration))):
        if spec["param"] in OVERRIDES.get(task, {}):
            calibration[i] = OVERRIDES[task][spec["param"]]
    target = ROOT_NUMBER if task == "optimisation" else TOTAL_LENGTH
    name = "upload-summary-data-file-button" if task in {"snpe", "surrogate"} else "upload-obs-data-file-button"
    _, response = upload(dash, page, name, target, "text/csv", "store-summary-data", section="summary_data")
    summary = response.get("store-summary-data", {}).get("data")
    return {"parameters": parameters, "calibration": calibration, "summary": summary, "toast": toast,
            "summary_toast": text_of(response.get(f"{page}-load-toast", {}).get("children"))}


def page_values(dash, task, loaded, extra=None):
    page = PAGES[task]
    form = "simulation_form" if task == "simulation" else "calibration_form"
    values = {(f"{page}-parameters", "value"): entries(ids(page, form, "parameters"), "value", loaded["parameters"]),
              ("store-simulation-run", "data"): [], ("submission-nonce", "data"): None}
    if task != "simulation":
        values[(f"{page}-{task}\"", "value")] = entries(ids(page, form, task), "value", loaded["calibration"])
        values[("store-summary-data", "data")] = loaded["summary"]
        values[("store-raw-simulation-data", "data")] = {}
        values[("store-raw-edge-data", "data")] = {}
    for name, value in SWITCHES.items():
        component = {"index": f"{page}-{name}", "type": f"{page}-x"}
        values[(f"{page}-{name}", "on")] = [{"id": component, "property": "on", "value": value}]
    values.update(extra or {})
    return values


def submit(dash, task, values, check_only=False):
    page = PAGES[task]
    if check_only:
        dep = dash.dep(f"{page}-preview", "results-toast")
        values[(f"{page}-preview", "n_clicks")] = 1
        trigger = f"{page}-preview.n_clicks"
    else:
        dep = dash.dep(f"{page}-run-sim-button", "results-toast")
        entry, trigger = button(page, "run-sim-button")
        values[(f"{page}-run-sim-button", "n_clicks")] = entry
    status, response = dash.call(dep, values, trigger=trigger)
    runs = (response.get("store-simulation-run") or {}).get("data")
    toast = text_of((response.get(f"{page}-results-toast") or {}).get("children"))
    return status, toast, runs


def architecture_values(dash, targets, lower=2, upper=4):
    load = dash.dep("architecture-upload", "architecture-base")
    _, response = dash.call(load, {("architecture-upload", "contents"): data_url(MINIMAL, "application/json")},
                            trigger="architecture-upload.contents")
    base = response["architecture-base"]["data"]
    rows = response["architecture-controls"]["data"]
    for row in rows:
        if row["id"] == "primary_root_count":
            row.update(lower=lower, upper=upper)
    status_text = text_of(response["architecture-model-status"]["children"])
    return status_text, {("architecture-base", "data"): base, ("architecture-controls", "data"): rows,
                         ("architecture-targets", "value"): targets, ("architecture-metric", "value"): "mae",
                         ("architecture-trials", "value"): 5, ("architecture-startup", "value"): 2,
                         ("architecture-seeds", "value"): "0, 1", ("architecture-method", "value"): "tpe",
                         ("architecture-nonce", "data"): None}


def run_architecture(dash, args, targets="statistic_name,statistic_value\nroot_number,3\n"):
    record = {"task": "architecture_search", "page": "/architecture-search"}
    loaded, values = architecture_values(dash, targets)
    record["load_feedback"] = loaded
    dep = dash.dep("architecture-launch", "architecture-message")
    button_id = "architecture-preview" if args.check_only else "architecture-launch"
    values[(button_id, "n_clicks")] = 1
    status, response = dash.call(dep, values, trigger=f"{button_id}.n_clicks")
    record.update(http_status=status, feedback=text_of(response.get("architecture-message", {}).get("children")))
    run = (response.get("architecture-run") or {}).get("data")
    if args.check_only or not run:
        return record
    record.update(flow_run_id=run["run"], simulation_uuid=run["job"])
    final = wait_for_run(args.prefect, run["run"], args.timeout)
    record.update(state=final["state_type"], state_name=final["state"]["name"], duration_s=final.get("total_run_time"))
    state_dep = dash.dep("architecture-poll", "architecture-state")
    _, response = dash.call(state_dep, {("architecture-run", "data"): run, ("architecture-poll", "n_intervals"): 1},
                            trigger="architecture-poll.n_intervals")
    record["page_state"] = text_of(response.get("architecture-state", {}).get("children"))
    record["best_enabled"] = not response.get("architecture-best", {}).get("disabled", True)
    download = dash.dep("architecture-best", "architecture-download")
    for name in ("architecture-best", "architecture-trial-table"):
        _, response = dash.call(download, {(name, "n_clicks"): 1, ("architecture-run", "data"): run},
                                trigger=f"{name}.n_clicks")
        sent = (response.get("architecture-download") or {}).get("data") or {}
        content = base64.b64decode(sent["content"]).decode() if sent.get("base64") else sent.get("content", "")
        record[name] = {"filename": sent.get("filename"), "bytes": len(content)}
        if name == "architecture-best" and content:
            best = json.loads(content)
            record["best_primary_root_count"] = best["parameters"]["primary_root_count"]
            record["best_random_seed"] = best.get("random_seed")
        if name == "architecture-trial-table" and content:
            rows = list(csv.DictReader(io.StringIO(content)))
            record["trial_rows"] = len(rows)
            record["trial_columns"] = list(rows[0]) if rows else []
    return record


def run_core_comparison(dash, args):
    dep = dash.dep("core-comparison-run", "core-comparison-status")
    values = {("core-comparison-file", "contents"): data_url(EXAMPLES / "research/core_comparison_synthetic.csv", "text/csv"),
              ("core-comparison-threshold", "value"): 0, ("core-comparison-run", "n_clicks"): 1}
    status, response = dash.call(dep, values, trigger="core-comparison-run.n_clicks")
    rows = (response.get("core-comparison-table") or {}).get("data") or []
    return {"task": "core_comparison", "http_status": status,
            "feedback": text_of(response.get("core-comparison-status", {}).get("children")), "rows": rows}


def run_eda(dash, args):
    page = "eda-root-system-page"
    if not args.nodes:
        raise ValueError("EDA needs --nodes with a Simulation node CSV")
    _, response = upload(dash, page, "upload-node-data-file-button", args.nodes, "text/csv", "store-simulation-data")
    data = response.get("store-simulation-data", {}).get("data")
    record = {"task": "eda", "load_feedback": text_of(response.get(f"{page}-load-toast", {}).get("children")),
              "rows_loaded": len((data or {}).get("values", []) if isinstance(data, dict) else data or [])}
    figures = {}
    for inputs, output in ((("select-x-axis-dropdown", "diameter"), ("select-y-axis-dropdown", "length"),
                            ("select-group-by-dropdown", "order")), "scatter-xy-plot"), \
                          ((("select-x-axis-dropdown", "diameter"), ("select-group-by-dropdown", "order")), "histogram-x-plot"), \
                          ((("select-x-summary-stats-dropdown", "total_length"),), "x-summary-statistic-plot"):
        dep = dash.dep(f"{page}-{inputs[0][0]}", output)
        values = {}
        for name, value in inputs:
            component = {"index": f"{page}-{name}", "type": f"{page}-x"}
            values[(f"{page}-{name}", "value")] = [{"id": component, "property": "value", "value": value}]
        values[("store-simulation-data", "data")] = data
        outputs = []
        for part in dep["output"].strip(".").split("..."):
            spec, prop = part.rsplit(".", 1)
            spec = json.loads(spec)
            outputs.append([{"id": {"index": spec["index"], "type": f"{page}-x"}, "property": prop}])
        single_output = not dep["output"].startswith("..")
        status, response = dash.call(dep, values, outputs=outputs[0] if single_output else outputs,
                                     trigger=key({"index": f"{page}-{inputs[0][0]}", "type": f"{page}-x"}) + ".value")
        traces = [len(v.get("figure", {}).get("data", [])) for v in response.values()]
        figures[output] = {"http_status": status, "traces": traces}
    record["figures"] = figures
    return record


def run_deployments(dash, args):
    """Press each calibrator button on Deployments with the guide's inputs."""
    page = "deployments-root-system-page"
    form = "deployments_form"
    record = {"task": "deployments"}
    status_dep = dash.dep(f"{page}-check-services", "service-status")
    _, response = dash.call(status_dep, {(f"{page}-check-services", "n_clicks"): 1},
                            trigger=f"{page}-check-services.n_clicks")
    record["service_status"] = text_of(response.get(f"{page}-service-status", {}).get("children"))
    statistics = [50 if c["param"] == "total_length" else None for c in children(form, "summary_statistics")]
    features = [json.dumps(args.surrogate_row) if c["param"] == "trained_features_json" else None
                for c in children(form, "parameters")]
    calls = {
        "optimisation": ("call-optimiser-button", {(f"{page}-n-trials-input", "value"): button(page, "n-trials-input", "value", 1)[0]}),
        "sensitivity_analysis": ("call-sa-button", {(f"{page}-parameter-names-dropdown", "value"):
                                 button(page, "parameter-names-dropdown", "value", ["primary_root_count"])[0]}),
        "abc": ("call-abc-button", {(f"{page}-t-input", "value"): button(page, "t-input", "value", 0)[0]}),
        "snpe": ("call-snpe-button", {(f"{page}-summary_statistics", "value"):
                 entries(ids(page, form, "summary_statistics"), "value", statistics)}),
        "surrogate": ("call-surrogate-button", {(f"{page}-parameters", "value"):
                      entries(ids(page, form, "parameters"), "value", features)}),
    }
    for task, (name, values) in calls.items():
        dep = dash.dep(f"{page}-{name}", "download-results")
        entry, trigger = button(page, name)
        values[(f"{page}-{name}", "n_clicks")] = entry
        status, response = dash.call(dep, values, trigger=trigger)
        sent = (response.get(f"{page}-download-results") or {}).get("data") or {}
        content = base64.b64decode(sent["content"]).decode() if sent.get("base64") else sent.get("content", "")
        rows = list(csv.DictReader(io.StringIO(content))) if content else []
        record[task] = {"http_status": status, "feedback": text_of((response.get(f"{page}-results-toast") or {}).get("children")),
                        "filename": sent.get("filename"), "rows": len(rows),
                        "columns": list(rows[0]) if rows else [], "first_row": rows[0] if rows else None}
    return record


def run_task(dash, args, task):
    if task == "deployments":
        return run_deployments(dash, args)
    if task == "core_comparison":
        return run_core_comparison(dash, args)
    if task == "eda":
        return run_eda(dash, args)
    if task == "architecture_search":
        return run_architecture(dash, args)
    record = {"task": task, "page": PAGES[task]}
    loaded = load_page_inputs(dash, task)
    record["load_feedback"] = [loaded.get("toast"), loaded.get("summary_toast")]
    values = page_values(dash, task, loaded)
    status, toast, runs = submit(dash, task, values, args.check_only)
    record.update(http_status=status, feedback=toast)
    if args.check_only or not runs:
        record["runs"] = runs
        return record
    run = dict(runs[-1])
    if "flow_run_id" not in run:  # rows written before run ids were stored
        match = re.search(r"flow-run/([0-9a-f-]{36})'[^>]*>([0-9a-f-]{36})<", run["workflow"])
        run.update(flow_run_id=match.group(1), simulation_uuid=match.group(2))
    record.update(flow_run_id=run.get("flow_run_id"), simulation_uuid=run.get("simulation_uuid"))
    final = wait_for_run(args.prefect, run["flow_run_id"], args.timeout)
    record.update(state=final["state_type"], state_name=final["state"]["name"],
                  deployment_id=final.get("deployment_id"), duration_s=final.get("total_run_time"))
    if final["state_type"] == "COMPLETED" and args.mlflow:
        run_id, files = mlflow_run(args.mlflow, task, run["simulation_uuid"])
        record.update(mlflow_run_id=run_id, artifacts=files)
        if task == "simulation":
            nodes = next(f for f in files if f.endswith("_nodes.csv"))
            edges = next(f for f in files if f.endswith("_edges.csv"))
            record["nodes"] = len(mlflow_rows(args.mlflow, run_id, nodes))
            record["edges"] = len(mlflow_rows(args.mlflow, run_id, edges))
            node_rows = mlflow_rows(args.mlflow, run_id, nodes)
            record["primary_roots"] = sum(1 for row in node_rows if row["order"] == "1" and row["segment_rank"] == "1")
            config = next(f for f in files if f.endswith("_config.yaml"))
            with urllib.request.urlopen(f"{args.mlflow}/get-artifact?" + urllib.parse.urlencode(
                    {"path": config, "run_uuid": run_id})) as response:
                document = yaml.safe_load(response.read())
            record["replayed_seed"] = document.get("random_seed")
            record["replayed_primary_root_count"] = document.get("parameters", {}).get("primary_root_count")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tasks", nargs="+", choices=sorted(PAGES) + ["architecture_search", "eda", "core_comparison", "deployments"])
    parser.add_argument("--surrogate-row", type=json.loads, default={"min_primary_length": 19.5, "max_primary_length": 28.5})
    parser.add_argument("--nodes", type=Path, help="Simulation node CSV for the EDA check")
    parser.add_argument("--dash", default="http://127.0.0.1:8000")
    parser.add_argument("--prefect", default="http://127.0.0.1:4200")
    parser.add_argument("--mlflow", default="http://127.0.0.1:5000")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--config", type=Path, help="Schema-4 JSON for the Simulation upload (e.g. a best configuration)")
    args = parser.parse_args()
    global CONFIG
    CONFIG = args.config
    dash = Dash(args.dash)
    records = []
    for task in args.tasks:
        try:
            record = run_task(dash, args, task)
        except Exception as exc:  # report and continue with the next page
            record = {"task": task, "error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(record, indent=1, default=str), flush=True)
        records.append(record)
    if args.receipt:
        args.receipt.write_text(json.dumps(records, indent=1, default=str))


if __name__ == "__main__":
    main()
