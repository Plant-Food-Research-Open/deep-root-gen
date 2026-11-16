#!/usr/bin/env python3
"""Bounded local four-arm replay. No observations, services or automatic retries."""
from __future__ import annotations

import os
for _variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_variable] = "2"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

import argparse
import contextlib
import fcntl
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from deeprootgen.research.so4_controlled import Skeleton, construct_skeleton, digest, replay_arm

LIMIT = 1073741824
BUDGET = dict(new_ensemble_attempts=40, per_attempt_seconds=60, generation_seconds=900,
              end_to_end_seconds=1800, workers=1, threads=2, new_output_bytes=LIMIT,
              automatic_retries=0)
TERMINAL = {"complete", "failed", "abandoned"}


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frozen_identity(config_path, parameters_path, references=()):
    paths = [Path(config_path).resolve(), Path(parameters_path).resolve(), ROOT / "poetry.lock",
             ROOT / "pyproject.toml", ROOT / "docs/research/SO4_CONTROLLED_METHOD.md",
             ROOT / "tests/test_so4_controlled.py", Path(__file__).resolve()]
    paths += sorted((ROOT / "deeprootgen").rglob("*.py"))
    paths += [Path(p).resolve() for p in references]
    hashes = {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): file_hash(p) for p in paths}
    return dict(source_hashes=hashes, sha256=digest(hashes),
                packages={d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
                python=sys.version, executable=sys.executable, platform=platform.platform())


def output_size(directory):
    return sum(p.stat().st_size for p in directory.rglob("*") if p.is_file())


def write_output(path, data, root, exclusive=False):
    """Fsync unique temporary bytes, atomic link-for-create or replace, fsync dir."""
    data = data.encode() if isinstance(data, str) else data
    if output_size(root) + len(data) > LIMIT:
        raise RuntimeError("New-output storage budget exhausted")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive:
            os.link(temporary, path)  # Complete file appears atomically, fails if final exists.
            temporary.unlink()
        else:
            os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def dump(path, value, root, exclusive=False):
    write_output(path, json.dumps(value, sort_keys=True, allow_nan=False, indent=2), root, exclusive)


def read_ledger(directory):
    """A corrupt reservation still consumes its numbered slot; never recreate it."""
    entries = []
    for path in sorted((directory / "ledger").glob("attempt-*.json")):
        try:
            record = json.loads(path.read_text())
            number = int(path.stem.split("-")[1])
            if (record["attempt"] != number or record["status"] not in TERMINAL | {"reserved", "running"}
                    or not isinstance(record["seed"], int) or record["arm"] not in {"A", "B", "C", "D"}
                    or "identity_sha256" not in record):
                raise ValueError("Invalid reservation schema")
        except (ValueError, KeyError, TypeError) as error:
            raise RuntimeError(f"Unreadable consumed ledger slot {path.name}; no slot regeneration") from error
        entries.append((path, record))
    return entries


@contextlib.contextmanager
def attempt_lock(path):
    with path.with_suffix(".worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def recover_interrupted(directory):
    """Under controller lock, retire orphaned work; live orphan workers block resume."""
    for path, record in read_ledger(directory):
        if record["status"] in {"reserved", "running"}:
            try:
                with attempt_lock(path):
                    record = json.loads(path.read_text())
                    if record["status"] in {"reserved", "running"}:
                        record.update(status="abandoned", completed_unix=time.time(),
                                      error="Interrupted attempt consumed; no retry")
                        dump(path, record, directory)
            except BlockingIOError as error:
                raise RuntimeError("An orphan worker remains active; no concurrent resume") from error


def verified_initial(directory, seed, required=False):
    path = directory / "initial" / f"seed-{seed}.json"
    if not path.exists():
        if required:
            raise RuntimeError("Consumed seed has no valid INITIAL; stop without reconstruction")
        return None
    try:
        initial = Skeleton.load(path)
    except (ValueError, KeyError, TypeError) as error:
        raise RuntimeError("Invalid/truncated INITIAL; stop before reserving other arms") from error
    if initial.payload["seed"] != seed:
        raise RuntimeError("INITIAL seed mismatch")
    for _, record in read_ledger(directory):
        if record["seed"] == seed and record.get("skeleton_sha256", initial.sha256) != initial.sha256:
            raise RuntimeError("Saved INITIAL changed between arms")
    return initial


def verify_completed(directory, record, identity):
    if record["identity_sha256"] != identity["sha256"]:
        raise RuntimeError("Completed attempt identity mismatch")
    seed, arm = record["seed"], record["arm"]
    verified_initial(directory, seed, required=True)
    for name, expected in record["artifact_sha256"].items():
        if file_hash(directory / f"seed-{seed}" / arm / name) != expected:
            raise RuntimeError("Completed artifact changed")


def reserve_attempt(directory, seed, arm, identity):
    """Exclusive reservation; all prior outcomes consume the pair without retry."""
    ledger = directory / "ledger"
    ledger.mkdir(exist_ok=True)
    with (ledger / "reservation.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        entries = read_ledger(directory)
        previous = [record for _, record in entries if record["seed"] == seed and record["arm"] == arm]
        if previous:
            if len(previous) != 1 or previous[0]["identity_sha256"] != identity["sha256"]:
                raise RuntimeError("Duplicate pair or changed reservation identity")
            if previous[0]["status"] == "complete":
                verify_completed(directory, previous[0], identity)
            return None
        number = max([record["attempt"] for _, record in entries], default=0) + 1
        if number > 40:
            raise RuntimeError("40-attempt cap exhausted")
        path = ledger / f"attempt-{number:03d}.json"
        dump(path, dict(attempt=number, seed=seed, arm=arm, status="reserved",
                       identity_sha256=identity["sha256"], reserved_unix=time.time(),
                       scaffold_constructions=0, replays={"physical": 0, "counterfactual": 0}),
             directory, exclusive=True)
        return path


def worker(args):
    directory = Path(args.outdir).resolve()
    reservation = Path(args.worker_attempt).resolve()
    if reservation.parent != directory / "ledger":
        raise RuntimeError("Worker reservation outside ledger")
    with attempt_lock(reservation):
        record = json.loads(reservation.read_text())
        manifest = json.loads((directory / "manifest.json").read_text())
        if (record["status"] != "reserved"
                or record["identity_sha256"] != manifest["identity"]["sha256"]
                or frozen_identity(args.config, args.parameters, args.reference) != manifest["identity"]):
            raise RuntimeError("Worker requires an unused reservation and frozen identities")
        dump(reservation.with_suffix(".claim"), {"pid": os.getpid(), "started_unix": time.time()},
             directory, exclusive=True)
        record.update(status="running", worker_started_unix=time.time())
        dump(reservation, record, directory)
        seed, arm = record["seed"], record["arm"]
        parameters = json.loads(Path(args.parameters).read_text())
        initial = verified_initial(directory, seed)
        if initial is None:
            prior = [r for _, r in read_ledger(directory) if r["seed"] == seed]
            if len(prior) != 1:
                raise RuntimeError("Consumed INITIAL preparation cannot be retried")
            record.update(scaffold_constructions=1, scaffold_construction_started_unix=time.time())
            dump(reservation, record, directory)
            initial = construct_skeleton(parameters, seed)
            dump(directory / "initial" / f"seed-{seed}.json",
                 dict(sha256=initial.sha256, payload=initial.payload), directory, exclusive=True)
        record["skeleton_sha256"] = initial.sha256
        record["replays"]["physical"] = 1
        dump(reservation, record, directory)
        result = replay_arm(initial, arm, parameters, "minimum_angle_projection")
        invariant_path = directory / "initial" / f"seed-{seed}-invariants.json"
        invariants = result["diagnostics"]["invariant_hashes"]
        if invariant_path.exists():
            if json.loads(invariant_path.read_text()) != invariants:
                raise RuntimeError("Four-arm persisted invariant hashes disagree")
        else:
            dump(invariant_path, invariants, directory, exclusive=True)
        destination = directory / f"seed-{seed}" / arm
        for name in ("nodes", "edges", "proposals"):
            write_output(destination / f"{name}.csv", result[name].to_csv(index=False), directory, exclusive=True)
        dump(destination / "diagnostics.json", result["diagnostics"], directory, exclusive=True)
        record.update(status="complete", completed_unix=time.time(), invariant_hashes=invariants,
                      artifact_sha256={p.name: file_hash(p) for p in destination.iterdir()})
        dump(reservation, record, directory)


def validate_design(config, parameter_path):
    if (config["version"] != "SO4-T2-controlled-v1"
            or config["seeds"] != list(range(4101, 4111)) or config["arms"] != ["A", "B", "C", "D"]
            or config["boundary_policy"] != "minimum_angle_projection" or config["surface_z_cm"] != 20
            or config["budget"] != BUDGET):
        raise ValueError("Frozen design/budgets required")
    parameter_path = Path(parameter_path).resolve()
    if parameter_path != (ROOT / config["parameters"]).resolve():
        raise ValueError("--parameters must match the frozen config parameter path")
    if file_hash(parameter_path) != config["parameter_sha256"]:
        raise ValueError("Frozen parameter bytes changed")
    parameters = json.loads(parameter_path.read_text())
    for key, value in config["required_settings"].items():
        if parameters.get(key) != value:
            raise ValueError(f"Frozen parameter setting changed: {key}")


def persist_receipt(directory, manifest, error=None):
    """Whole-ledger accounting, including old failures and unreadable consumed slots."""
    records, unreadable = [], []
    for path in sorted((directory / "ledger").glob("attempt-*.json")):
        try:
            record = json.loads(path.read_text())
            if not isinstance(record, dict) or record.get("status") not in TERMINAL | {"reserved", "running"}:
                raise ValueError("Invalid reservation schema")
            records.append(record)
        except (ValueError, TypeError):
            unreadable.append(path.name)
    complete = sum(r.get("status") == "complete" for r in records)
    status = "complete" if complete == 40 and not unreadable else "partial"
    dump(directory / "generation_receipt.json", dict(status=status, controller_error=error,
         elapsed_seconds=time.time() - manifest.get("generation_started_unix", time.time()),
         failures=[r for r in records if r.get("status") != "complete"], unreadable_consumed_slots=unreadable,
         attempts=len(records) + len(unreadable), complete=complete,
         scaffold_constructions=sum(r.get("scaffold_constructions", 0) for r in records),
         physical_replays_started=sum(r.get("replays", {}).get("physical", 0) for r in records),
         counterfactual_replays=0, output_bytes=output_size(directory),
         identity_sha256=manifest["identity"]["sha256"]), directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--parameters", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--reference", action="append", default=[])
    parser.add_argument("--worker-attempt", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text())
    validate_design(config, args.parameters)
    if not args.execute and not args.prepare:
        print(json.dumps(dict(status="prepared_only", identity=frozen_identity(args.config, args.parameters, args.reference))))
        return
    if args.worker_attempt:
        worker(args)
        return
    directory = Path(args.outdir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        identity = frozen_identity(args.config, args.parameters, args.reference)
        manifest_path = directory / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            if manifest["identity"] != identity:
                raise RuntimeError("Resume refused: source/config/environment identity changed")
        else:
            manifest = dict(format="so4-controlled-run-v1", created_unix=time.time(), identity=identity,
                            design=config, parameters=json.loads(Path(args.parameters).read_text()),
                            synthetic=False, budget=BUDGET)
            dump(manifest_path, manifest, directory, exclusive=True)
        for name, expected in identity["source_hashes"].items():
            path = Path(name) if Path(name).is_absolute() else ROOT / name
            destination = directory / "frozen_inputs" / expected
            if not destination.exists():
                write_output(destination, path.read_bytes(), directory, exclusive=True)
            if file_hash(destination) != expected:
                raise RuntimeError("Frozen byte snapshot mismatch")
        if args.prepare and not args.execute:
            print("Prepared manifest and frozen bytes; zero ensemble attempts.")
            return
        if "generation_started_unix" not in manifest:
            manifest["generation_started_unix"] = time.time()
            dump(manifest_path, manifest, directory)
        controller_error = None
        try:
            recover_interrupted(directory)
            for seed in config["seeds"]:
                prior = [r for _, r in read_ledger(directory) if r["seed"] == seed]
                if prior:
                    verified_initial(directory, seed, required=True)
                for arm in config["arms"]:
                    elapsed = time.time() - manifest["generation_started_unix"]
                    if elapsed + 60 > 900:
                        raise RuntimeError("Insufficient durable generation budget for a full 60-second attempt")
                    if frozen_identity(args.config, args.parameters, args.reference) != identity:
                        raise RuntimeError("Frozen inputs changed during execution")
                    reservation = reserve_attempt(directory, seed, arm, identity)
                    if reservation is None:
                        continue
                    command = [sys.executable, str(Path(__file__).resolve()), "--config", str(Path(args.config).resolve()),
                               "--parameters", str(Path(args.parameters).resolve()), "--outdir", str(directory),
                               "--execute", "--worker-attempt", str(reservation)]
                    for reference in args.reference:
                        command += ["--reference", str(Path(reference).resolve())]
                    try:
                        completed = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE,
                                                   stderr=subprocess.PIPE, timeout=60, check=False)
                        if completed.returncode:
                            raise RuntimeError(f"worker exit {completed.returncode}: {completed.stderr.decode(errors='replace')[-4000:]}")
                    except (subprocess.TimeoutExpired, RuntimeError, OSError) as error:
                        record = json.loads(reservation.read_text())
                        record.update(status="failed", completed_unix=time.time(), error=str(error))
                        dump(reservation, record, directory)
                        verified_initial(directory, seed, required=True)
        except BaseException as error:
            controller_error = f"{type(error).__name__}: {error}"
            raise
        finally:
            persist_receipt(directory, manifest, controller_error)
        print("Generation finished; inspect local receipt and ledger.")


if __name__ == "__main__":
    main()
