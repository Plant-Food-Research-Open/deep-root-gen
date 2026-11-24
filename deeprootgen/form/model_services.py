"""Call the optional BentoML calibration services and classify each outcome."""

import os
import os.path as osp

import pandas as pd
import requests

SERVICES = {
    "optimisation": ("Optimisation calibrator", "http://optimisation:3000"),
    "sensitivity_analysis": ("Sensitivity calibrator", "http://sensitivity_analysis:3000"),
    "abc": ("Bayesian calibrator (ABC)", "http://abc:3000"),
    "snpe": ("Neural density calibrator (SNPE)", "http://snpe:3000"),
    "surrogate": ("Emulation calibrator (surrogate)", "http://surrogate:3000"),
}
START_HINT = (
    "Model serving is optional. Start it with the serving profile after a completed run of "
    "this method on the same stack (RUNNING.md, 'Optional model serving')."
)


class ServiceError(RuntimeError):
    """``kind``: unreachable, missing_model, invalid_input, unsupported or service_error."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def endpoint(task: str) -> str:
    return os.environ.get(f"DEPLOYMENT_{task.upper()}_INTERNAL_LINK", SERVICES[task][1]).rstrip("/")


def _detail(response: requests.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        data = response.text
    if isinstance(data, dict):
        text = data.get("error") or data.get("detail") or data.get("message") or str(data)
    else:
        text = data
    return str(text)[:400]


def model_info(task: str, timeout: float = 5.0) -> dict:
    """Return the served model identity, or raise ServiceError."""
    url = endpoint(task)
    try:
        response = requests.post(f"{url}/info", json={}, timeout=timeout)
    except requests.RequestException as exc:
        raise ServiceError("unreachable", f"No {task} model service answered at {url}. {START_HINT}") from exc
    if response.status_code != 200:
        raise ServiceError("service_error", f"{url}/info returned HTTP {response.status_code}: {_detail(response)}")
    return response.json()


def predict(task: str, body: dict, outdir: str, stamp: str, timeout: float = 120.0) -> tuple[str, int, dict]:
    """POST ``body`` to the service and save the rows as CSV.

    Returns:
        tuple: (CSV path, row count, served model identity).
    """
    url = endpoint(task)
    try:
        response = requests.post(f"{url}/predict", json=body, timeout=timeout)
    except requests.RequestException as exc:
        raise ServiceError("unreachable", f"No {task} model service answered at {url}. {START_HINT}") from exc
    detail = _detail(response) if response.status_code != 200 else ""
    if response.status_code == 404:
        raise ServiceError("missing_model", detail or (
            f"The {task} service at {url} has no model version to serve. Complete a {task} run "
            "on this stack, then restart the service."))
    if response.status_code in (400, 422):
        raise ServiceError("invalid_input", f"The {task} service rejected these inputs: "
                           f"{detail or 'check the values against the served model signature'}")
    if response.status_code == 501:
        raise ServiceError("unsupported", detail or (
            f"The served {task} model cannot answer this request; served SNPE supports "
            "summary-statistic posteriors only, not graph-mode inference."))
    if response.status_code != 200:
        raise ServiceError("service_error", f"The {task} service failed (HTTP {response.status_code}): {detail}")
    frame = pd.DataFrame(response.json())
    if frame.empty:
        raise ServiceError("invalid_input", f"The {task} service returned no rows for these inputs.")
    outfile = osp.join(outdir, f"{stamp}-{task}-predict.csv")
    frame.to_csv(outfile, index=False)
    try:
        info = model_info(task)
    except ServiceError:
        info = {}
    return outfile, len(frame), info


TITLES = {
    "unreachable": "Model service not running",
    "missing_model": "No model version to serve",
    "invalid_input": "Invalid input",
    "unsupported": "Not supported by the served model",
    "service_error": "Model service error",
}


def service_status() -> list[tuple[str, str, str]]:
    """Return (label, state, detail) for every configured service."""
    rows = []
    for task, (label, _) in SERVICES.items():
        try:
            info = model_info(task, timeout=3.0)
        except ServiceError as error:
            rows.append((label, "not running" if error.kind == "unreachable" else "error", str(error)))
            continue
        if info.get("available"):
            rows.append((label, "serving", f"{info.get('tag')} from run {info.get('simulation_uuid')}"))
        else:
            rows.append((label, "no model", f"Running at {endpoint(task)} without a {task} model version."))
    return rows
