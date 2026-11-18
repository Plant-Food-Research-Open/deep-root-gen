"""Tracked runs: durable records, an append-only ledger and reproduction."""

import hashlib
import json
from pathlib import Path

import pytest

from deeprootgen.run_records import read_ledger, repository_state, tracked_run

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/design/native_feature_options.proposed.json"


def curvature(enabled):
    def edit(spec):
        spec["features"]["curvature"]["enabled"] = enabled

    return edit


def test_tracked_off_on_off_runs_and_reproduction(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    labels = [("off-1", False), ("on", True), ("off-2", False)]
    records = [
        tracked_run(EXAMPLE, tmp_path / label, label=label, ledger=ledger, edit=curvature(enabled))
        for label, enabled in labels
    ]
    assert [r["label"] for r in read_ledger(ledger)] == [label for label, _ in labels]
    off_1, on, off_2 = records
    assert off_1["outputs"]["nodes.csv"] == off_2["outputs"]["nodes.csv"]
    assert off_1["model_identity"] == off_2["model_identity"]
    assert on["active_features"] == ["curvature"] and off_1["active_features"] == []
    assert off_1["config_file_sha256"] == hashlib.sha256(EXAMPLE.read_bytes()).hexdigest()
    assert off_1["source_schema"] == "3" and off_1["edited_before_run"] is True
    assert set(off_1["repository"]) == {"commit", "tracked_changes"}
    saved = json.loads((Path(on["outdir"]) / "run_record.json").read_text())
    assert saved == on
    # The saved input reproduces the model, run identity and outputs exactly.
    again = tracked_run(Path(on["outdir"]) / "parameters.json", tmp_path / "again", label="again")
    for key in ("effective_model_sha256", "run_identity_sha256"):
        assert again["model_identity"][key] == on["model_identity"][key]
    assert again["outputs"]["nodes.csv"] == on["outputs"]["nodes.csv"]
    with pytest.raises(FileExistsError):
        tracked_run(EXAMPLE, tmp_path / "on", label="duplicate")
    assert len(read_ledger(ledger)) == 3


def test_repository_state_never_fails_outside_git(tmp_path):
    assert repository_state(tmp_path) == dict(commit=None, tracked_changes=None)
