"""Fault injection proves diagnostics retain exact bytes and failing assertions."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from tests import hash_failure_diagnostics as evidence


def test_disabled_collection_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("DRG_SYNTHETIC_FAILURE_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    evidence.record_failure("physical-cap", {"actual": {"x": 1.0}}, "old")
    assert list(tmp_path.iterdir()) == []


def test_exact_serialization_and_metadata_no_environment_dump(tmp_path, monkeypatch):
    monkeypatch.setenv("DRG_SYNTHETIC_FAILURE_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_TEST_SENTINEL", "must-not-be-collected")
    payload = {"zero": -0.0, "tiny": 1e-100, "nested": [1, 1.0, None]}
    evidence.record_failure("physical-cap", {"actual": payload}, "original")
    (folder,) = tmp_path.iterdir()
    raw = (folder / "actual.json").read_bytes()
    assert raw == evidence.canonical_bytes(payload)
    meta = json.loads((folder / "metadata.json").read_text())
    assert meta["payloads"]["actual"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert meta["expected_sha256"] == "original"
    assert "must-not-be-collected" not in (folder / "metadata.json").read_text()
    assert "python" in meta and "numpy" in meta["packages"]


def test_writer_failure_does_not_replace_assertion(tmp_path, monkeypatch):
    path = tmp_path / "not-directory"
    path.write_text("keep")
    monkeypatch.setenv("DRG_SYNTHETIC_FAILURE_DIR", str(path))
    with pytest.warns(UserWarning, match="evidence unavailable"):
        evidence.record_failure("physical-cap", {"actual": {}}, "old")
    assert path.read_text() == "keep"


def test_real_physical_assertion_emits_payload_only_on_failure(tmp_path, monkeypatch):
    from tests import test_physical_step_replay as case

    monkeypatch.setenv("DRG_SYNTHETIC_FAILURE_DIR", str(tmp_path))
    saved, settings = case.invented_initial(3)
    result = case.physical.replay_physical_steps(
        saved, settings, orders=(), max_step_cm=2.0, direction_seed=None
    )
    expected = case.digest(
        {
            key: value.to_dict("records") if hasattr(value, "to_dict") else value
            for key, value in result.items()
        }
    )
    case.test_cap_default_output_bytes_match_pre_ou_source_epoch(
        3, (), 2.0, None, expected
    )
    assert not list(tmp_path.iterdir())
    with pytest.raises(AssertionError):
        case.test_cap_default_output_bytes_match_pre_ou_source_epoch(
            3, (), 2.0, None, "injected-mismatch"
        )
    (folder,) = tmp_path.iterdir()
    assert hashlib.sha256((folder / "actual.json").read_bytes()).hexdigest() == expected


def test_real_initial_assertion_emits_both_variants(tmp_path, monkeypatch):
    from tests import test_primary_design as case

    monkeypatch.setenv("DRG_SYNTHETIC_FAILURE_DIR", str(tmp_path))
    original = case.construct_skeleton

    def corrupted_identity(*args, **kwargs):
        result = original(*args, **kwargs)
        return SimpleNamespace(payload=result.payload, sha256="injected-failure")

    monkeypatch.setattr(case, "construct_skeleton", corrupted_identity)
    with pytest.raises(AssertionError):
        case.test_inactive_field_retains_preimplementation_initial_identity()
    (folder,) = tmp_path.iterdir()
    assert (folder / "omitted.json").read_bytes() == (
        folder / "explicit_none.json"
    ).read_bytes()
