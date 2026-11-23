"""Submit dashboard requests to Prefect and classify outcomes for the page.

Every worker-backed page uses one deployment name per task from the single
manifest ``app/flows/prefect.yaml``. A submission is checked before it is sent:
an unreachable API or a missing deployment is reported without creating a run.
Each send carries an idempotency key built from a page nonce and the request
payload, so a repeated click or a retry after an uncertain network error
returns the run that Prefect already accepted instead of creating another.
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import httpx

TASKS = (
    "simulation",
    "optimisation",
    "architecture_search",
    "sensitivity_analysis",
    "abc",
    "snpe",
    "surrogate",
)
DEPLOYMENTS = {task: f"{task}/run_{task}_flow" for task in TASKS}
FINAL_STATES = {"COMPLETED", "FAILED", "CRASHED", "CANCELLED"}
REGISTER_HINT = (
    "Register the manifest with the prefect-deployments service "
    "(see RUNNING.md, 'Dashboard stack')."
)


class SubmissionError(RuntimeError):
    """A classified submission failure.

    ``kind`` is one of ``unreachable`` (nothing was sent), ``missing_deployment``
    (nothing was sent), ``rejected`` (Prefect refused the request) or
    ``uncertain`` (the request may have been accepted; retry with the same form
    to recover the same run).
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class Submission:
    """An accepted request and what the page should tell the user."""

    task: str
    deployment: str
    flow_run_id: str
    simulation_uuid: str
    created: bool
    state: str
    notes: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return flow_run_url(self.flow_run_id)


def api_url() -> str:
    return os.environ.get("PREFECT_API_URL", "http://localhost:4200/api").rstrip("/")


def user_host() -> str:
    return os.environ.get("APP_PREFECT_USER_HOST", "http://localhost:4200").rstrip("/")


def flow_run_url(flow_run_id: str) -> str:
    return f"{user_host()}/flow-runs/flow-run/{UUID(str(flow_run_id))}"


def new_nonce() -> str:
    """Return a fresh page nonce; rotate it only after a definite outcome."""
    return uuid4().hex


def request_key(task: str, parameters: dict, nonce: str | None) -> str:
    """Return a stable idempotency key for one page request."""
    payload = json.dumps(parameters, sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode()).hexdigest()[:24]
    return f"dash:{task}:{nonce or 'none'}:{digest}"


def _get(path: str, timeout: float = 5.0) -> httpx.Response:
    return httpx.get(f"{api_url()}{path}", timeout=timeout)


def check_deployment(task: str, timeout: float = 5.0) -> dict:
    """Confirm the API, deployment and work pool before sending anything.

    Returns:
        dict: ``deployment`` JSON, ``pool`` name (or None) and ``pool_status``.
    """
    name = DEPLOYMENTS[task]
    try:
        _get("/health", timeout).raise_for_status()
        response = _get(f"/deployments/name/{name}", timeout)
    except httpx.TransportError as exc:
        raise SubmissionError(
            "unreachable",
            f"The Prefect API at {user_host()} is unreachable ({type(exc).__name__}). "
            "Nothing was submitted. Check the prefect-server service, then retry.",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise SubmissionError(
            "unreachable",
            f"The Prefect API at {user_host()} is not healthy "
            f"(HTTP {exc.response.status_code}). Nothing was submitted.",
        ) from exc
    if response.status_code == 404:
        raise SubmissionError(
            "missing_deployment",
            f"Prefect at {user_host()} has no deployment '{name}'. Nothing was submitted. "
            + REGISTER_HINT,
        )
    if response.status_code >= 400:
        raise SubmissionError(
            "unreachable",
            f"Prefect returned HTTP {response.status_code} for deployment '{name}'. "
            "Nothing was submitted.",
        )
    deployment = response.json()
    pool = deployment.get("work_pool_name")
    pool_status = None
    if pool:
        try:
            pool_response = _get(f"/work_pools/{pool}", timeout)
            if pool_response.status_code == 200:
                pool_status = pool_response.json().get("status")
        except httpx.TransportError:
            pool_status = None
    return {"deployment": deployment, "pool": pool, "pool_status": pool_status}


def submit(
    task: str,
    parameters: dict,
    nonce: str | None,
    simulation_uuid: str | None = None,
    key_parameters: dict | None = None,
) -> Submission:
    """Queue one deployment run and classify every failure.

    Args:
        task: One of TASKS.
        parameters: Flow parameters, excluding ``simulation_uuid``.
        nonce: The page nonce; equal nonce and payload return the same run.
        simulation_uuid: A new UUID for this request; generated when omitted.
        key_parameters: Parameters used for the idempotency key; defaults to
            ``parameters``.
    """
    from prefect.deployments import run_deployment
    from prefect.exceptions import ObjectNotFound, PrefectHTTPStatusError

    info = check_deployment(task)
    name = DEPLOYMENTS[task]
    simulation_uuid = simulation_uuid or str(uuid4())
    key = request_key(task, key_parameters if key_parameters is not None else parameters, nonce)
    try:
        flow_run = run_deployment(
            name,
            parameters=dict(parameters, simulation_uuid=simulation_uuid),
            flow_run_name=simulation_uuid,
            timeout=0,
            idempotency_key=key,
        )
    except ObjectNotFound as exc:
        raise SubmissionError(
            "missing_deployment",
            f"Prefect has no deployment '{name}'. Nothing was submitted. " + REGISTER_HINT,
        ) from exc
    except httpx.ConnectError as exc:
        raise SubmissionError(
            "unreachable",
            f"The Prefect API at {user_host()} became unreachable. Nothing was submitted.",
        ) from exc
    except httpx.TransportError as exc:
        raise SubmissionError(
            "uncertain",
            f"The connection to Prefect failed while sending ({type(exc).__name__}); "
            "the run may have been queued. Click Run again without changing the form: "
            "the same request returns the existing run instead of starting another.",
        ) from exc
    except PrefectHTTPStatusError as exc:
        status = exc.response.status_code
        if status >= 500:
            raise SubmissionError(
                "uncertain",
                f"Prefect returned HTTP {status}; the run may have been queued. Click Run "
                "again without changing the form to recover the same run.",
            ) from exc
        raise SubmissionError(
            "rejected", f"Prefect rejected the request (HTTP {status}): {exc.response.text[:300]}"
        ) from exc

    accepted_uuid = (flow_run.parameters or {}).get("simulation_uuid", flow_run.name)
    created = accepted_uuid == simulation_uuid
    notes = []
    if not created:
        notes.append(
            "This exact request was already accepted; showing that run instead of starting "
            "another. Change the tag, seed or any input to submit a new run."
        )
    if info["pool"] and info["pool_status"] not in (None, "READY"):
        notes.append(
            f"No worker is currently polling work pool '{info['pool']}' "
            f"(status {info['pool_status']}); the run stays Scheduled until a worker starts."
        )
    state = flow_run.state.type.value if flow_run.state else "SCHEDULED"
    return Submission(task, name, str(flow_run.id), str(accepted_uuid), created, state, notes)


def read_run_state(flow_run_id: str, timeout: float = 3.0) -> tuple[str, str]:
    """Return (state type, state name); raise SubmissionError if unavailable."""
    try:
        response = _get(f"/flow_runs/{UUID(str(flow_run_id))}", timeout)
    except httpx.TransportError as exc:
        raise SubmissionError("unreachable", "The Prefect API is unreachable.") from exc
    if response.status_code == 404:
        raise SubmissionError(
            "missing_run", "This run is not on the current Prefect server."
        )
    response.raise_for_status()
    data = response.json()
    state = data.get("state") or {}
    return data.get("state_type") or "SCHEDULED", state.get("name") or "Scheduled"
