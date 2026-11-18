"""Traceable runs for notebooks and scripts.

``tracked_run`` parses and resolves one input with the shared resolver, runs
the single native engine, exports with the offline CLI exporter and records:

* ``<outdir>/run_record.json``: label, time, input file and its hash, model
  identities (supplied input, effective model, run), active features, seed,
  counts, output hashes, generator source hash, git state and environment;
* ``<outdir>/parameters.json``: the exact input used, reloadable by the CLI;
* an optional append-only JSON-lines ledger with one record per run.

Outputs are never overwritten. Nothing is uploaded and no service is started.
"""

import copy
import datetime
import hashlib
import json
import subprocess
from pathlib import Path


def repository_state(root=None):
    """Git commit and whether tracked files differ from it; never fails a run."""
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10, check=True
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=root, capture_output=True, text=True, timeout=10, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return dict(commit=None, tracked_changes=None)
    return dict(commit=commit, tracked_changes=bool(status.strip()))


def tracked_run(config, outdir, *, label, ledger=None, edit=None):
    """Run once through the shared engine and write a durable run record.

    ``config`` is a JSON path or an input dict. ``edit(spec)`` may change a
    deep copy before running (for example ``features.curvature.enabled``);
    the edited input is saved as ``parameters.json`` and hashed.
    """
    from .cli import simulate
    from .data_model.resolution import load_json_config

    path = Path(config) if isinstance(config, (str, Path)) else None
    spec = load_json_config(path) if path is not None else copy.deepcopy(config)
    if edit is not None:
        edit(spec)
    manifest = simulate(spec, outdir)
    target = Path(outdir).expanduser().resolve()
    resolved_file = target / "resolved_config.json"
    resolved = json.loads(resolved_file.read_text()) if resolved_file.exists() else {}
    record = dict(
        label=label,
        created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        outdir=str(target),
        config_path=None if path is None else str(path.resolve()),
        config_file_sha256=None if path is None else hashlib.sha256(path.read_bytes()).hexdigest(),
        edited_before_run=edit is not None,
        source_schema=resolved.get("source_schema"),
        seed=manifest["seed"],
        model_identity=manifest.get("model_identity", {}),
        active_features=sorted(resolved.get("features", {}).get("active", {})),
        node_count=manifest["node_count"],
        edge_count=manifest["edge_count"],
        invalid_node_count=manifest["invalid_node_count"],
        outputs=manifest["outputs"],
        source_sha256=manifest.get("source_sha256"),
        repository=manifest.get("repository"),
        environment=dict(python=manifest["python"], **manifest["dependencies"]),
    )
    (target / "run_record.json").write_text(json.dumps(record, indent=2) + "\n")
    if ledger is not None:
        ledger = Path(ledger)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def read_ledger(path):
    """All run records from a JSON-lines ledger, oldest first."""
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
