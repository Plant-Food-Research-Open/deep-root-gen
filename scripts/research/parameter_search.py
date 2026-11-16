#!/usr/bin/env python3
"""Local, opt-in notebook search integration; no services or automatic fitting."""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
VERSION = "local-research-parameter-search-v1"
ROUTES = {"graph_segments_v1", "construction_steps_v1"}
FROZEN_FIELDS = {
    "random_seed",
    "t",
    "max_order",
    "soil_surface_z_cm",
    "research_current_length_grid",
    "simulation_tag",
    "enable_soil",
}


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError(f"Nonfinite JSON number: {value}")

    return json.loads(
        Path(path).read_text(), object_pairs_hook=unique, parse_constant=nonfinite
    )


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, indent=2) + "\n"


def size(path):
    return (
        sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
        if path.exists()
        else 0
    )


def write_json(path, value, root, limit):
    data = canonical(value).encode()
    if size(root) + len(data) > limit:
        raise RuntimeError("Output budget exhausted")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def positive_number(value, name, integer=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
        or (integer and not isinstance(value, int))
    ):
        raise ValueError(
            f"{name} must be a positive {'integer' if integer else 'number'}"
        )


def validate_seeds(values, name):
    if (
        not isinstance(values, list)
        or not values
        or len(values) != len(set(values))
        or any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in values)
    ):
        raise ValueError(f"{name} requires distinct nonnegative integer seeds")


def load_config(path):
    path = Path(path).resolve()
    config = read_json(path)
    required = {
        "version",
        "parameters_file",
        "reference_file",
        "simulation_route",
        "objective_mode",
        "search_space",
        "seeds",
        "qualification_seeds",
        "sampler_seed",
        "budget",
    }
    if (
        not isinstance(config, dict)
        or set(config) != required
        or config["version"] != VERSION
    ):
        raise ValueError(
            f"Configuration requires exactly {sorted(required)} and version {VERSION}"
        )
    if config["simulation_route"] not in ROUTES:
        raise ValueError("Select an explicit supported simulation_route")
    if config["objective_mode"] not in {"population_mean", "per_seed_mean"}:
        raise ValueError("Select population_mean or per_seed_mean explicitly")
    validate_seeds(config["seeds"], "seeds")
    validate_seeds(config["qualification_seeds"], "qualification_seeds")
    if set(config["seeds"]) & set(config["qualification_seeds"]):
        raise ValueError("Search and qualification seeds must be disjoint")
    if (
        isinstance(config["sampler_seed"], bool)
        or not isinstance(config["sampler_seed"], int)
        or config["sampler_seed"] < 0
    ):
        raise ValueError("sampler_seed must be a nonnegative integer")
    budget = config["budget"]
    keys = {
        "n_trials",
        "n_startup_trials",
        "timeout_seconds",
        "per_seed_timeout_seconds",
        "output_stop_bytes",
    }
    if not isinstance(budget, dict) or set(budget) != keys:
        raise ValueError(f"Budget requires exactly {sorted(keys)}")
    for key in keys:
        positive_number(
            budget[key],
            key,
            key in {"n_trials", "n_startup_trials", "output_stop_bytes"},
        )
    if budget["n_trials"] <= budget["n_startup_trials"]:
        raise ValueError(
            "n_trials must exceed n_startup_trials so adaptive search can run"
        )
    files = {
        key: (path.parent / config[key]).resolve()
        for key in ("parameters_file", "reference_file")
    }
    parameters, reference = (
        read_json(files[key]) for key in ("parameters_file", "reference_file")
    )
    if not isinstance(config["search_space"], dict) or not config["search_space"]:
        raise ValueError("search_space must be a nonempty mapping")
    if set(config["search_space"]) & FROZEN_FIELDS:
        raise ValueError("Seed, time, order, frame and route fields must remain fixed")
    if not set(config["search_space"]) <= set(parameters):
        raise ValueError("Every search parameter must exist in the base parameter file")
    from deeprootgen.data_model import RootSimulationModel
    from deeprootgen.research.search_evaluation import (
        evaluate_samples,
        validate_simulation_parameters,
    )
    from deeprootgen.research.order5_population_evaluation import validate_root_orders

    if not set(config["search_space"]) <= set(RootSimulationModel.model_fields):
        raise ValueError("Search contains an unknown model parameter")
    model = RootSimulationModel(**parameters)
    orders = validate_root_orders(reference.get("root_orders"))
    if model.max_order != orders[-1]:
        raise ValueError("parameters.max_order must agree with reference.root_orders")
    if model.max_order not in (3, 4, 5) or model.soil_surface_z_cm != 20.0:
        raise ValueError(
            "This bridge requires explicit order1-3/4/5 and soil_surface_z_cm=20"
        )
    steps = model.research_current_length_grid == "construction_steps_v1"
    if steps != (config["simulation_route"] == "construction_steps_v1"):
        raise ValueError("Explicit route disagrees with construction-step parameters")
    validate_simulation_parameters(parameters, route=config["simulation_route"])
    # Validate the observation contract without a model run or rewriting inputs.
    evaluate_samples(
        reference,
        [
            dict(
                seed=0,
                traits=reference["trait_means"],
                profiles=reference["profiles"],
                diagnostics={"root_orders": orders},
            )
        ],
        objective_mode=config["objective_mode"],
    )
    return config, parameters, reference, files


def source_identity(config_path, files):
    paths = sorted((ROOT / "deeprootgen").rglob("*.py"))
    paths += [
        ROOT / "poetry.lock",
        ROOT / "pyproject.toml",
        Path(__file__),
        ROOT / "scripts/research/grapevine3d_so4_pilot.py",
        ROOT / "scripts/data/grapevine3d_grid.py",
        Path(config_path).resolve(),
        *files.values(),
    ]
    return dict(
        files={str(p.resolve()): sha(p) for p in paths},
        python=sys.version,
        packages={
            name: importlib.metadata.version(name)
            for name in (
                "optuna",
                "numpy",
                "pandas",
                "scipy",
                "pydantic",
                "torch",
                "torch-geometric",
            )
        },
    )


def verify_identity(identity):
    if any(sha(path) != value for path, value in identity["files"].items()):
        from deeprootgen.research.parameter_search import SearchStopped

        raise SearchStopped("Frozen source/input bytes changed")


def worker(input_path, output_path):
    payload = read_json(input_path)

    def expired(signum, frame):
        raise TimeoutError("Worker's independent deadline expired")

    with Path(input_path).with_name("worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt = read_json(Path(input_path).with_name("receipt.json"))
        if receipt["status"] != "running" or receipt["input_sha256"] != sha(input_path):
            raise RuntimeError("Worker requires an active authenticated reservation")
        remaining = payload["deadline_unix"] - time.time()
        if remaining <= 0:
            raise TimeoutError("Worker deadline already expired")
        previous = signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, remaining)
        try:
            verify_identity(payload["identity"])
            from deeprootgen.research.search_evaluation import simulate_sample

            result = simulate_sample(
                payload["parameters"], payload["seed"], route=payload["route"]
            )
            verify_identity(payload["identity"])
            data = canonical(result).encode()
            if len(data) > payload["max_sample_bytes"]:
                raise RuntimeError("Worker sample exceeds reserved output bytes")
            output = Path(output_path)
            with output.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)


def recover_call_workers(outdir, limit):
    """Do not overlap orphan workers or silently retry their consumed calls."""
    for path in (outdir / "calls").glob("*/receipt.json"):
        record = read_json(path)
        if record["status"] == "running":
            with path.with_name("worker.lock").open("a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise RuntimeError(
                        "An orphan worker is still active; resume cannot overlap it"
                    ) from error
                record.update(
                    status="abandoned",
                    finished_unix=time.time(),
                    error="Interrupted call consumed; no automatic retry",
                )
                write_json(path, record, outdir, limit)


def run_one(parameters, seed, *, route, outdir, identity, budget, deadline, phase):
    from deeprootgen.research.parameter_search import SearchStopped

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SearchStopped("Invocation time budget exhausted before the next seed")
    calls = outdir / "calls"
    calls.mkdir(exist_ok=True)
    number = (
        max(
            [int(p.name) for p in calls.iterdir() if p.is_dir() and p.name.isdigit()],
            default=0,
        )
        + 1
    )
    folder = calls / f"{number:06d}"
    folder.mkdir()
    limit = budget["output_stop_bytes"]
    payload = dict(
        parameters=dict(parameters, random_seed=seed),
        seed=seed,
        route=route,
        identity=identity,
        deadline_unix=time.time() + min(budget["per_seed_timeout_seconds"], remaining),
        max_sample_bytes=max(
            0, limit - size(outdir) - 2 * len(canonical(identity).encode()) - 16384
        ),
    )
    if payload["max_sample_bytes"] <= 0:
        raise SearchStopped("Insufficient output bytes for worker and failure receipt")
    write_json(folder / "input.json", payload, outdir, limit)
    receipt = dict(
        status="running",
        seed=seed,
        phase=phase,
        call_number=number,
        started_unix=time.time(),
        input_sha256=sha(folder / "input.json"),
    )
    write_json(folder / "receipt.json", receipt, outdir, limit)
    env = dict(
        os.environ,
        CUDA_VISIBLE_DEVICES="",
        OMP_NUM_THREADS="2",
        MKL_NUM_THREADS="2",
        OPENBLAS_NUM_THREADS="2",
        NUMEXPR_NUM_THREADS="2",
        PYTHONDONTWRITEBYTECODE="1",
    )
    try:
        remaining = min(
            deadline - time.monotonic(), payload["deadline_unix"] - time.time()
        )
        if remaining <= 0:
            raise SearchStopped("Time budget exhausted before worker launch")
        run = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker-input",
                str(folder / "input.json"),
                "--worker-output",
                str(folder / "sample.json"),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=remaining,
            check=False,
        )
        if run.returncode:
            raise RuntimeError(f"Worker exit {run.returncode}: {run.stderr[-4000:]}")
        result = read_json(folder / "sample.json")
        verify_identity(identity)
        if size(outdir) > limit:
            raise SearchStopped("Output budget exhausted after worker")
        receipt.update(status="complete", sample_sha256=sha(folder / "sample.json"))
        return result
    except BaseException as error:
        receipt.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        receipt["finished_unix"] = time.time()
        write_json(folder / "receipt.json", receipt, outdir, limit)


@contextlib.contextmanager
def locked(outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    with (outdir / ".cli.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def qualification(config, reference, outdir, identity, deadline, design):
    from deeprootgen.research.parameter_search import read_verified_search_result
    from deeprootgen.research.search_evaluation import evaluate_samples

    best = read_verified_search_result(outdir / "search", design)
    if best["best_parameters"] is None:
        raise ValueError("No completed search candidate to qualify")
    parameters = best["best_parameters"]
    plan = dict(
        parameters=parameters,
        best_trial_number=best["best_trial_number"],
        search_summary_sha256=sha(outdir / "search/summary.json"),
        seeds=config["qualification_seeds"],
        identity=identity,
    )
    plan_path = outdir / "qualification_plan.json"
    limit = config["budget"]["output_stop_bytes"]
    if plan_path.exists():
        if read_json(plan_path) != plan:
            raise ValueError(
                "Frozen qualification candidate/seed/source identity changed"
            )
    else:
        write_json(plan_path, plan, outdir, limit)
    samples = []
    for seed in config["qualification_seeds"]:
        prior = [
            p
            for p in (outdir / "calls").glob("*/receipt.json")
            if read_json(p)["phase"] == "qualify" and read_json(p)["seed"] == seed
        ]
        if prior:
            if len(prior) != 1:
                raise RuntimeError("Duplicate qualification attempt")
            record = read_json(prior[0])
            sample = prior[0].with_name("sample.json")
            if record["status"] != "complete" or sha(sample) != record["sample_sha256"]:
                raise RuntimeError(
                    "Consumed incomplete qualification seed; no automatic retry"
                )
            samples.append(read_json(sample))
        else:
            samples.append(
                run_one(
                    parameters,
                    seed,
                    route=config["simulation_route"],
                    outdir=outdir,
                    identity=identity,
                    budget=config["budget"],
                    deadline=deadline,
                    phase="qualify",
                )
            )
    report = evaluate_samples(
        reference, samples, objective_mode=config["objective_mode"]
    )
    report.update(
        stage="fresh_seed_qualification",
        biological_validation=False,
        parameter_fitting=False,
        best_trial_number=best["best_trial_number"],
        qualification_plan_sha256=sha(plan_path),
    )
    write_json(outdir / "qualification.json", report, outdir, limit)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--outdir")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--phase", choices=("search", "qualify"), default="search")
    parser.add_argument("--worker-input", help=argparse.SUPPRESS)
    parser.add_argument("--worker-output", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    for name in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[name] = "2"
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    if args.worker_input:
        if not args.worker_output:
            parser.error("Worker output required")
        worker(args.worker_input, args.worker_output)
        return 0
    if not args.config or not args.outdir:
        parser.error("--config and --outdir required")
    config, parameters, reference, files = load_config(args.config)
    identity = source_identity(args.config, files)
    from deeprootgen.research.parameter_search import validate_search_inputs

    budget = config["budget"]
    design = validate_search_inputs(
        base_parameters=parameters,
        search_space=config["search_space"],
        seeds=config["seeds"],
        n_trials=budget["n_trials"],
        n_startup_trials=budget["n_startup_trials"],
        sampler_seed=config["sampler_seed"],
        timeout_seconds=budget["timeout_seconds"],
        identity=identity,
    )
    outdir = Path(args.outdir).resolve()
    if not args.execute:
        print(
            canonical(
                dict(
                    status="VALIDATED_NOT_EXECUTED",
                    phase=args.phase,
                    workers=1,
                    threads=2,
                    simulation_route=config["simulation_route"],
                    budget=config["budget"],
                    search_seeds=config["seeds"],
                    qualification_seeds=config["qualification_seeds"],
                )
            )
        )
        return 0
    from deeprootgen.research.parameter_search import run_parameter_search
    from deeprootgen.research.search_evaluation import evaluate_samples

    manifest = dict(version=VERSION, config=config, identity=identity)
    deadline = time.monotonic() + config["budget"]["timeout_seconds"]
    with locked(outdir):
        manifest_path = outdir / "manifest.json"
        if manifest_path.exists():
            if not args.resume or read_json(manifest_path) != manifest:
                raise ValueError(
                    "Existing output needs --resume and identical configuration/source/input bytes"
                )
        else:
            if (
                any(p.name != ".cli.lock" for p in outdir.iterdir())
                or args.resume
                or args.phase == "qualify"
            ):
                raise ValueError(
                    "New search requires an empty output directory; qualification needs its search"
                )
            write_json(
                manifest_path, manifest, outdir, config["budget"]["output_stop_bytes"]
            )
        recover_call_workers(outdir, config["budget"]["output_stop_bytes"])
        if args.phase == "qualify":
            result = qualification(
                config, reference, outdir, identity, deadline, design
            )
        else:
            if (outdir / "qualification_plan.json").exists():
                raise ValueError(
                    "Candidate frozen for qualification; use a new search directory"
                )

            def evaluate(candidate, seeds):
                verify_identity(identity)
                samples = [
                    run_one(
                        candidate,
                        seed,
                        route=config["simulation_route"],
                        outdir=outdir,
                        identity=identity,
                        budget=config["budget"],
                        deadline=deadline,
                        phase="search",
                    )
                    for seed in seeds
                ]
                report = evaluate_samples(
                    reference, samples, objective_mode=config["objective_mode"]
                )
                if (
                    size(outdir) + 3 * len(canonical(report).encode()) + 65536
                    > config["budget"]["output_stop_bytes"]
                ):
                    from deeprootgen.research.parameter_search import SearchStopped

                    raise SearchStopped(
                        "Insufficient output bytes for search result/checkpoint"
                    )
                return report

            budget = config["budget"]

            def before_trial():
                from deeprootgen.research.parameter_search import SearchStopped

                verify_identity(identity)
                if time.monotonic() >= deadline:
                    raise SearchStopped("Invocation deadline reached")
                # Admission reserve, not a filesystem quota: SQLite and terminal
                # receipts still require space after stopping new work.
                if size(outdir) + 262144 > budget["output_stop_bytes"]:
                    raise SearchStopped("Output admission threshold reached")

            result = run_parameter_search(
                base_parameters=parameters,
                search_space=config["search_space"],
                seeds=config["seeds"],
                outdir=outdir / "search",
                n_trials=budget["n_trials"],
                n_startup_trials=budget["n_startup_trials"],
                sampler_seed=config["sampler_seed"],
                timeout_seconds=budget["timeout_seconds"],
                identity=identity,
                evaluate=evaluate,
                resume=args.resume,
                before_trial=before_trial,
            )
        print(canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
