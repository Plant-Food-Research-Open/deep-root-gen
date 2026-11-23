"""Shared model loading for the optional BentoML calibration services.

A service starts even when its model is not yet in the Bento store, so the
dashboard can tell a missing model version (HTTP 404 from ``predict``) apart
from a service that is not running (connection failure). ``info`` reports the
served artifact's identity.
"""

import os
from http import HTTPStatus

import bentoml
from bentoml.exceptions import BentoMLException, NotFound
from bentoml.io import JSON


class Unsupported(BentoMLException):
    """A request the served model cannot answer (HTTP 501)."""

    error_code = HTTPStatus.NOT_IMPLEMENTED


def load(task: str):
    """Return (model or None, reason when missing) for ``<TASK>_MODEL_TAG`` or latest."""
    tag = os.environ.get(f"{task.upper()}_MODEL_TAG", f"{task}:latest")
    try:
        return bentoml.mlflow.get(tag), ""
    except bentoml.exceptions.NotFound:
        home = os.environ.get("BENTOML_HOME", "~/bentoml")
        return None, (
            f"No '{tag}' model version in the Bento store at {home}. Complete a {task} run on "
            "this stack (its worker imports the model into the shared store), then restart "
            "this service."
        )


def identity(task: str, model) -> dict:
    """The served model's tag and the run that produced it."""
    if model is None:
        return {"task": task, "available": False}
    labels = model.info.labels or {}
    return {
        "task": task,
        "available": True,
        "tag": str(model.tag),
        "simulation_uuid": labels.get("simulation_uuid"),
        "simulation_tag": labels.get("simulation_tag"),
        "flow_run_id": labels.get("flow_run_id"),
        "created": str(model.info.creation_time),
    }


def service(task: str, model):
    """Create the service and its ``info`` endpoint."""
    runners = [model.to_runner()] if model is not None else []
    svc = bentoml.Service(task, runners=runners)

    @svc.api(input=JSON(), output=JSON(), route="/info")
    def info(_: dict) -> dict:
        return identity(task, model)

    return svc, (runners[0] if runners else None)


def require(runner, reason: str):
    """Raise a 404 that names the missing model, or return the runner."""
    if runner is None:
        raise NotFound(reason)
    return runner
