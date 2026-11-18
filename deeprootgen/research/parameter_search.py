"""Local, sequential parameter search with durable, identity-bound trials.

The callback evaluates one candidate against the entire fixed seed tuple. It
must bound its own work: ``timeout_seconds`` is checked between callback trials,
not a hard interruption of a running callback. Failures consume the total trial
budget. Interrupted trials are failed on resume, never automatically retried.

This module fits a caller-defined loss. It does not qualify a model, choose
validation seeds, run fresh validation, or infer biological parameter certainty.
Caller ``identity`` must identify all relevant sources, inputs and operators;
the module cannot infer those dependencies from a Python callable. Output files
contain full parameters and callback diagnostics and must remain local when
their contents are private.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
import platform
import sqlite3
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

import optuna
from optuna.trial import TrialState


VERSION = "drg-parameter-search-v1"
STUDY_NAME = "parameter_search"
SAMPLER_OPTIONS = {"n_ei_candidates": 24, "multivariate": False}


class SearchStopped(RuntimeError):
    """Stop admission or evaluation without automatically spending more slots.

    Raised by ``before_trial``: no trial has been reserved. Raised by ``evaluate``:
    the current attempted trial is retained as FAIL and consumes one budget slot.
    A storage admission threshold is a soft stop, not a filesystem quota.
    """

    def __init__(self, reason: str, diagnostics: dict | None = None):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("SearchStopped requires a nonempty reason")
        if diagnostics is not None and not isinstance(diagnostics, dict):
            raise ValueError("SearchStopped diagnostics must be a JSON dictionary")
        super().__init__(reason)
        self.reason = reason
        self.diagnostics = _json(diagnostics or {})


def _json(value):
    """Return detached canonical JSON data; reject coercion of mapping keys."""

    def check(item):
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ValueError("JSON dictionary keys must be strings")
            for child in item.values():
                check(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                check(child)

    check(value)
    try:
        return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(
            "Inputs and callback diagnostics must be finite JSON data"
        ) from error


def _bytes(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _atomic_json(path, value):
    data = _bytes(value) + b"\n"
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}, not bool")
    return value


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite numeric data, not bool")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(f"{name} must be finite") from error
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _candidate(base, suggestions):
    candidate = copy.deepcopy(base)
    settings = candidate["parameters"] if candidate.get("schema_version") == 4 else candidate
    settings.update(suggestions)
    return candidate


def _space(search_space):
    if not isinstance(search_space, dict) or not search_space:
        raise ValueError("search_space must be a nonempty dictionary")
    result = {}
    for name, spec in search_space.items():
        if not isinstance(name, str) or not name or any(c in name for c in ".[]"):
            raise ValueError("Search names must be nonempty top-level parameter names")
        if not isinstance(spec, dict):
            raise ValueError(
                "Each search parameter requires a specification dictionary"
            )
        kind = spec.get("kind")
        if kind in ("float", "int"):
            if set(spec) - {"kind", "low", "high", "log"} or not {"low", "high"} <= set(
                spec
            ):
                raise ValueError(
                    "Numeric search specifications require low/high and optional log"
                )
            low, high = (_number(spec[key], key) for key in ("low", "high"))
            if kind == "int":
                if type(spec["low"]) is not int or type(spec["high"]) is not int:
                    raise ValueError("Integer search bounds must be integers")
                low, high = spec["low"], spec["high"]
            logarithmic = spec.get("log", False)
            if (
                type(logarithmic) is not bool
                or low >= high
                or (logarithmic and low <= 0)
            ):
                raise ValueError(
                    "Require low < high, boolean log and positive logarithmic bounds"
                )
            result[name] = dict(kind=kind, low=low, high=high, log=logarithmic)
        elif kind == "categorical":
            choices = spec.get("choices")
            if (
                set(spec) != {"kind", "choices"}
                or not isinstance(choices, (list, tuple))
                or not choices
            ):
                raise ValueError("Categorical search requires nonempty choices only")
            choices = _json(choices)
            if any(
                choice is not None and type(choice) not in (str, int, float, bool)
                for choice in choices
            ):
                raise ValueError("Categorical choices must be JSON scalars")
            if any(
                left == right
                for i, left in enumerate(choices)
                for right in choices[i + 1 :]
            ):
                raise ValueError("Categorical choices must be distinct")
            result[name] = dict(kind=kind, choices=choices)
        else:
            raise ValueError("Search kind must be float, int or categorical")
    return _json(result)


def _trial_seed(seed, number):
    key = hashlib.sha256(f"{VERSION}:{seed}:{number}".encode()).digest()
    return int.from_bytes(key[:4], "little")


def _receipt_path(outdir, number):
    return outdir / "trials" / f"trial_{number:06d}.json"


def _read_receipt(outdir, number, identity_sha256):
    path = _receipt_path(outdir, number)
    if not path.exists():
        return None
    record = _json(json.loads(path.read_text()))
    if (
        record.get("trial_number") != number
        or record.get("identity_sha256") != identity_sha256
    ):
        raise ValueError("Trial receipt identity mismatch")
    return record


def _recover(study, outdir, design, identity_sha256):
    """Reconcile writes without repeating callbacks or regenerating consumed slots."""
    trials = study.get_trials(deepcopy=False)
    if [trial.number for trial in trials] != list(range(len(trials))):
        raise ValueError("Study has a noncontiguous trial history")
    if len(trials) > design["n_trials"]:
        raise ValueError("SQLite history exceeds the frozen total trial budget")
    for trial in trials:
        record = _read_receipt(outdir, trial.number, identity_sha256)
        if record is not None:
            if record.get("seeds") != design["seeds"] or record.get("parameters") != _candidate(design["base_parameters"], trial.params):
                raise ValueError(
                    "Trial receipt candidate or seeds disagree with the frozen design"
                )
        if trial.state in (TrialState.RUNNING, TrialState.WAITING):
            record = record or dict(
                trial_number=trial.number,
                identity_sha256=identity_sha256,
                parameters=_candidate(design["base_parameters"], trial.params),
                suggested_parameters=trial.params,
                seeds=design["seeds"],
                sampler_seed=_trial_seed(design["sampler_seed"], trial.number),
            )
            record.update(
                state="FAIL",
                interrupted=True,
                error=record.get("error")
                or dict(
                    type="InterruptedTrial",
                    message="Interrupted trial consumed on resume; callback not retried",
                ),
            )
            _atomic_json(_receipt_path(outdir, trial.number), record)
            study.tell(trial.number, state=TrialState.FAIL)
        elif trial.state in (TrialState.COMPLETE, TrialState.FAIL):
            if record is None:
                raise ValueError(
                    "Terminal trial is missing its durable callback receipt"
                )
            if record.get("suggested_parameters") != trial.params:
                raise ValueError(
                    "Trial receipt parameters disagree with SQLite history"
                )
            if trial.state == TrialState.COMPLETE:
                loss = _number(record.get("result", {}).get("loss"), "stored loss")
                if loss != trial.value or record.get("state") not in (
                    "EVALUATED",
                    "COMPLETE",
                ):
                    raise ValueError(
                        "Completed trial receipt disagrees with SQLite history"
                    )
                if record["state"] == "EVALUATED":
                    record["state"] = "COMPLETE"
                    _atomic_json(_receipt_path(outdir, trial.number), record)
            elif record.get("state") != "FAIL":
                raise ValueError("Failed trial receipt disagrees with SQLite history")
        else:
            raise ValueError("Unexpected trial state in private parameter-search study")


def _summary(study, outdir, identity_sha256, reason, started, stop_diagnostics=None):
    trials = study.get_trials(deepcopy=False)
    completed = [trial for trial in trials if trial.state == TrialState.COMPLETE]
    best = (
        min(completed, key=lambda trial: (trial.value, trial.number))
        if completed
        else None
    )
    record = _read_receipt(outdir, best.number, identity_sha256) if best else None
    result = dict(
        format=VERSION,
        identity_sha256=identity_sha256,
        stop_reason=reason,
        attempted_trials=len(trials),
        completed_trials=len(completed),
        failed_trials=sum(trial.state == TrialState.FAIL for trial in trials),
        pending_trials=sum(
            trial.state in (TrialState.RUNNING, TrialState.WAITING) for trial in trials
        ),
        best_trial_number=best.number if best else None,
        best_loss=float(best.value) if best else None,
        best_parameters=record["parameters"] if record else None,
        invocation_elapsed_seconds=max(0.0, time.monotonic() - started),
        model_qualified=False,
        fresh_validation_run=False,
    )
    if stop_diagnostics is not None:
        result["stop_diagnostics"] = _json(stop_diagnostics)
    _atomic_json(outdir / "summary.json", result)
    return result


def validate_search_inputs(
    *,
    base_parameters: dict,
    search_space: dict,
    seeds: list[int],
    n_trials: int,
    n_startup_trials: int,
    sampler_seed: int,
    timeout_seconds: float,
    identity: dict,
) -> dict:
    """Validate and detach the search design without filesystem or study writes.

    Numeric bounds, seeds and loss values do not accept booleans. Categorical
    choices may be any finite JSON scalar, including explicit boolean choices.
    The caller supplies source/input/operator identity; no source is opened here.
    """
    _integer(n_trials, "n_trials", 2)
    _integer(n_startup_trials, "n_startup_trials", 1)
    _integer(sampler_seed, "sampler_seed")
    if n_trials <= n_startup_trials:
        raise ValueError("Require n_trials > n_startup_trials >= 1")
    timeout_seconds = _number(timeout_seconds, "timeout_seconds")
    if timeout_seconds <= 0:
        raise ValueError("Require positive timeout_seconds")
    if not isinstance(seeds, (list, tuple)) or not seeds:
        raise ValueError("seeds must be a nonempty list of distinct integer seeds")
    for seed in seeds:
        _integer(seed, "seed")
    if len(set(seeds)) != len(seeds):
        raise ValueError("Seeds must be distinct; no implicit replicate reweighting")
    if (
        not isinstance(base_parameters, dict)
        or not isinstance(identity, dict)
        or not identity
    ):
        raise ValueError(
            "Require base_parameters dictionary and nonempty caller identity"
        )
    return _json(
        dict(
            format=VERSION,
            base_parameters=_json(base_parameters),
            search_space=_space(search_space),
            seeds=list(seeds),
            n_trials=n_trials,
            n_startup_trials=n_startup_trials,
            sampler_seed=sampler_seed,
            timeout_seconds=timeout_seconds,
            identity=_json(identity),
        )
    )


def _manifest(validated, outdir):
    design = _json(
        dict(
            **validated,
            output_directory=str(outdir),
            python_version=platform.python_version(),
            optuna_version=optuna.__version__,
            engine_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            sampler="TPESampler",
            sampler_options=SAMPLER_OPTIONS,
            sampler_seed_scheme=f"SHA256({VERSION}:seed:global_trial_number)[:4]-little-endian",
            timeout_policy="check_between_callback_trials_no_hard_interruption",
            callback_identity_policy="evaluate_and_optional_before_trial_bound_by_caller_identity",
        )
    )
    return dict(
        design=design, identity_sha256=hashlib.sha256(_bytes(design)).hexdigest()
    )


def read_verified_search_result(outdir: Path, expected_design: dict) -> dict:
    """Authenticate a saved result without creating a study or evaluating anything.

    ``expected_design`` is the detached return from ``validate_search_inputs``.
    The manifest must match current engine/dependency identity and that design.
    A shared lock excludes a running search; SQLite is opened read-only. Best
    parameters/loss/trial and all state counts are checked against SQLite and
    the completed trial receipt. Pending trials require explicit search resume.
    This authenticates search provenance, not scientific qualification.
    """
    if (
        not isinstance(expected_design, dict)
        or expected_design.get("format") != VERSION
    ):
        raise ValueError("Expected the normalized validate_search_inputs design")
    inputs = {key: value for key, value in expected_design.items() if key != "format"}
    validated = validate_search_inputs(**inputs)
    if validated != expected_design:
        raise ValueError("Expected design is not normalized")
    outdir = Path(outdir).resolve()
    expected = _manifest(validated, outdir)
    with (outdir / ".search.lock").open("rb") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                "Cannot verify while a parameter search holds the output lock"
            ) from error
        if json.loads((outdir / "manifest.json").read_text()) != expected:
            raise ValueError("Saved search manifest identity mismatch")
        summary = _json(json.loads((outdir / "summary.json").read_text()))
        uri = "file:" + quote(str(outdir / "study.sqlite3"), safe="/") + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            connection.execute("BEGIN")
            row = connection.execute(
                "SELECT study_id FROM studies WHERE study_name = ?", (STUDY_NAME,)
            ).fetchone()
            if row is None:
                raise ValueError("Saved SQLite study is missing")
            study_id = row[0]
            attribute = connection.execute(
                "SELECT value_json FROM study_user_attributes WHERE study_id = ? AND key = ?",
                (study_id, "identity_sha256"),
            ).fetchone()
            directions = connection.execute(
                "SELECT objective, direction FROM study_directions WHERE study_id = ?",
                (study_id,),
            ).fetchall()
            if (
                attribute is None
                or json.loads(attribute[0]) != expected["identity_sha256"]
                or directions != [(0, "MINIMIZE")]
            ):
                raise ValueError("Saved SQLite study identity or direction mismatch")
            trials = connection.execute(
                "SELECT trial_id, number, state FROM trials WHERE study_id = ? ORDER BY number",
                (study_id,),
            ).fetchall()
            if (
                [row[1] for row in trials] != list(range(len(trials)))
                or len(trials) > validated["n_trials"]
                or any(row[2] not in {"COMPLETE", "FAIL"} for row in trials)
            ):
                raise ValueError(
                    "Saved trial history is pending or invalid; resume before verification"
                )
            completed = []
            for trial_id, number, state in trials:
                if state != "COMPLETE":
                    continue
                values = connection.execute(
                    "SELECT objective, value, value_type FROM trial_values WHERE trial_id = ?",
                    (trial_id,),
                ).fetchall()
                if len(values) != 1 or values[0][0] != 0 or values[0][2] != "FINITE":
                    raise ValueError("Completed SQLite trial lacks one finite loss")
                completed.append(
                    (_number(values[0][1], "SQLite loss"), number, trial_id)
                )
            best = min(completed) if completed else None
            best_parameters = None
            if best is not None:
                loss, number, trial_id = best
                suggestions = {
                    name: optuna.distributions.json_to_distribution(
                        distribution
                    ).to_external_repr(value)
                    for name, value, distribution in connection.execute(
                        "SELECT param_name, param_value, distribution_json FROM trial_params WHERE trial_id = ?",
                        (trial_id,),
                    ).fetchall()
                }
                record = _read_receipt(outdir, number, expected["identity_sha256"])
                best_parameters = _candidate(validated["base_parameters"], suggestions)
                if (
                    record is None
                    or record.get("state") != "COMPLETE"
                    or record.get("suggested_parameters") != suggestions
                    or record.get("parameters") != best_parameters
                    or record.get("seeds") != validated["seeds"]
                    or _number(record.get("result", {}).get("loss"), "receipt loss")
                    != loss
                ):
                    raise ValueError(
                        "Best completed trial receipt disagrees with SQLite/design"
                    )
            authoritative = dict(
                format=VERSION,
                identity_sha256=expected["identity_sha256"],
                attempted_trials=len(trials),
                completed_trials=len(completed),
                failed_trials=len(trials) - len(completed),
                pending_trials=0,
                best_trial_number=best[1] if best else None,
                best_loss=best[0] if best else None,
                best_parameters=best_parameters,
                model_qualified=False,
                fresh_validation_run=False,
            )
            if any(summary.get(key) != value for key, value in authoritative.items()):
                raise ValueError(
                    "Saved summary disagrees with authenticated SQLite/receipt result"
                )
            return summary
        finally:
            connection.close()


def _open_study(outdir, manifest, resume):
    """Open or recover the identity-bound study while the caller holds its lock."""
    design, identity_sha256 = manifest["design"], manifest["identity_sha256"]
    manifest_path, database = outdir / "manifest.json", outdir / "study.sqlite3"
    if resume:
        if (
            not manifest_path.is_file()
            or json.loads(manifest_path.read_text()) != manifest
        ):
            raise ValueError(
                "Resume identity mismatch or missing manifest; no evaluations started"
            )
        if not database.is_file():
            raise ValueError(
                "Resume SQLite history is missing; consumed trials cannot be reconstructed"
            )
    else:
        if any(
            path.exists()
            for path in (
                manifest_path,
                database,
                outdir / "summary.json",
                outdir / "trials",
            )
        ):
            raise FileExistsError(
                "Search output already exists; use matching resume or a fresh directory"
            )
        _atomic_json(manifest_path, manifest)
        (outdir / "trials").mkdir()
    storage = f"sqlite:///{database.as_posix()}"
    study = (
        optuna.load_study(study_name=STUDY_NAME, storage=storage)
        if resume
        else optuna.create_study(
            study_name=STUDY_NAME, direction="minimize", storage=storage
        )
    )
    if resume:
        if study.user_attrs.get("identity_sha256") != identity_sha256:
            raise ValueError("SQLite study identity mismatch")
        _recover(study, outdir, design, identity_sha256)
    else:
        study.set_user_attr("identity_sha256", identity_sha256)
    return study


def _evaluate_trial(study, trial, design, record, outdir, execution_seeds, evaluate):
    """Persist one reserved trial; return an explicit stop without retrying it."""
    path = _receipt_path(outdir, trial.number)
    try:
        suggestions = {}
        for name, spec in design["search_space"].items():
            options = {key: value for key, value in spec.items() if key != "kind"}
            suggestions[name] = getattr(trial, "suggest_" + spec["kind"])(name, **options)
        candidate = _candidate(design["base_parameters"], suggestions)
        record.update(
            parameters=_json(candidate), suggested_parameters=_json(trial.params)
        )
        _atomic_json(path, record)
        result = evaluate(copy.deepcopy(candidate), execution_seeds)
        if not isinstance(result, dict) or "loss" not in result:
            raise ValueError("Callback must return a JSON dictionary containing loss")
        loss = _number(result["loss"], "loss")
        record.update(result=_json(result), state="EVALUATED")
        _atomic_json(path, record)
    except SearchStopped as error:
        record.update(
            state="FAIL",
            error=dict(type=type(error).__name__, message=str(error)),
            stop_diagnostics=error.diagnostics,
            suggested_parameters=_json(trial.params),
        )
        record.setdefault("parameters", _candidate(design["base_parameters"], trial.params))
        _atomic_json(path, record)
        study.tell(trial, state=TrialState.FAIL)
        return error
    except Exception as error:
        record.update(
            state="FAIL",
            error=dict(type=type(error).__name__, message=str(error)),
            suggested_parameters=_json(trial.params),
        )
        record.setdefault("parameters", _candidate(design["base_parameters"], trial.params))
        _atomic_json(path, record)
        study.tell(trial, state=TrialState.FAIL)
    else:
        study.tell(trial, loss)
        record["state"] = "COMPLETE"
        _atomic_json(path, record)
    return None


def run_parameter_search(
    *,
    base_parameters: dict,
    search_space: dict,
    seeds: list[int],
    outdir: Path,
    n_trials: int,
    n_startup_trials: int,
    sampler_seed: int,
    timeout_seconds: float,
    identity: dict,
    evaluate,
    resume: bool = False,
    before_trial=None,
) -> dict:
    """Run sequential ask/evaluate/tell trials and return a JSON-compatible summary.

    ``n_trials`` is a TOTAL budget including failures and interrupted reservations.
    Every resume must supply the identical design, budgets and caller identity.
    Each global trial number gets a new deterministically seeded TPESampler; its
    proposals depend on the persisted completed history, without pickle state.
    Adaptive TPE begins only after ``n_startup_trials`` completed evaluations.
    The callback receives a fresh parameter dict and the unchanged seed tuple.
    ``Exception`` failures are retained and the next budget slot may proceed;
    process interrupts propagate and their pending slot is consumed on resume.
    Optional ``before_trial()`` runs before reservation and may raise SearchStopped
    for admission/deadline checks. Its behavior must be bound in caller identity.
    Storage admission checks are soft thresholds, not filesystem quotas.
    """
    started = time.monotonic()
    validated = validate_search_inputs(
        base_parameters=base_parameters,
        search_space=search_space,
        seeds=seeds,
        n_trials=n_trials,
        n_startup_trials=n_startup_trials,
        sampler_seed=sampler_seed,
        timeout_seconds=timeout_seconds,
        identity=identity,
    )
    if (
        type(resume) is not bool
        or not callable(evaluate)
        or (before_trial is not None and not callable(before_trial))
    ):
        raise ValueError(
            "Require boolean resume, callable evaluate and optional callable before_trial"
        )
    timeout_seconds = validated["timeout_seconds"]
    execution_seeds = tuple(validated["seeds"])
    outdir = Path(outdir).resolve()
    manifest = _manifest(validated, outdir)
    design, identity_sha256 = manifest["design"], manifest["identity_sha256"]
    outdir.mkdir(parents=True, exist_ok=True)
    with (outdir / ".search.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                "Another parameter-search invocation holds the output lock"
            ) from error
        study = _open_study(outdir, manifest, resume)
        try:
            while len(study.trials) < n_trials:
                if time.monotonic() - started >= timeout_seconds:
                    return _summary(
                        study, outdir, identity_sha256, "invocation_timeout", started
                    )
                if before_trial is not None:
                    try:
                        before_trial()
                    except SearchStopped as error:
                        return _summary(
                            study,
                            outdir,
                            identity_sha256,
                            error.reason,
                            started,
                            error.diagnostics,
                        )
                if time.monotonic() - started >= timeout_seconds:
                    return _summary(
                        study, outdir, identity_sha256, "invocation_timeout", started
                    )
                number = len(study.trials)
                seed = _trial_seed(sampler_seed, number)
                study.sampler = optuna.samplers.TPESampler(
                    seed=seed,
                    n_startup_trials=n_startup_trials,
                    **SAMPLER_OPTIONS,
                )
                adaptive = (
                    sum(t.state == TrialState.COMPLETE for t in study.trials)
                    >= n_startup_trials
                )
                trial = study.ask()
                if trial.number != number:
                    raise RuntimeError(
                        "Unexpected concurrent mutation of SQLite trial history"
                    )
                record = dict(
                    trial_number=number,
                    identity_sha256=identity_sha256,
                    state="RUNNING",
                    seeds=list(execution_seeds),
                    sampler_seed=seed,
                    sampler_phase="tpe" if adaptive else "startup",
                )
                stopped = _evaluate_trial(
                    study, trial, design, record, outdir, execution_seeds, evaluate
                )
                if stopped is not None:
                    return _summary(
                        study,
                        outdir,
                        identity_sha256,
                        stopped.reason,
                        started,
                        stopped.diagnostics,
                    )
                _summary(study, outdir, identity_sha256, "running", started)
            return _summary(
                study, outdir, identity_sha256, "trial_budget_exhausted", started
            )
        except BaseException:
            _summary(study, outdir, identity_sha256, "interrupted", started)
            raise
