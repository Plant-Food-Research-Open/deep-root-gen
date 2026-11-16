"""Synthetic callback tests only: no simulator, observations or fitted arrays."""

import fcntl
import json
import sqlite3

import optuna
import pytest

from deeprootgen.research import parameter_search as search


def settings(outdir, **updates):
    values = dict(
        base_parameters={"x": .5, "fixed": {"operator": "invented"}, "count": 1},
        search_space={"x": {"kind": "float", "low": .01, "high": 1., "log": True},
                      "count": {"kind": "int", "low": 1, "high": 3},
                      "label": {"kind": "categorical", "choices": ["a", "b"]}},
        seeds=[7, 11], outdir=outdir, n_trials=6, n_startup_trials=2,
        sampler_seed=123, timeout_seconds=60., identity={"operator": "synthetic-v1"},
    )
    values.update(updates)
    return values


def objective(parameters, seeds):
    return dict(loss=(parameters["x"] - .3) ** 2 + parameters["count"] * .01,
                diagnostics={"seeds": list(seeds), "label": parameters["label"], "nested": [1, {"ok": True}]})


def receipts(path):
    return [json.loads(file.read_text()) for file in sorted((path / "trials").glob("trial_*.json"))]


def test_complete_adaptive_search_saves_full_candidates_and_diagnostics(tmp_path):
    seen = []

    def evaluate(parameters, seeds):
        assert seeds == (7, 11)
        assert parameters["fixed"] == {"operator": "invented"}
        result = objective(parameters, seeds)
        parameters["fixed"]["operator"] = "callback mutation"
        seen.append(seeds)
        return result

    summary = search.run_parameter_search(**settings(tmp_path), evaluate=evaluate)
    records = receipts(tmp_path)
    assert len(seen) == summary["attempted_trials"] == summary["completed_trials"] == 6
    assert summary["failed_trials"] == 0 and summary["pending_trials"] == 0
    assert [r["sampler_phase"] for r in records] == ["startup"] * 2 + ["tpe"] * 4
    assert len({r["sampler_seed"] for r in records}) == 6
    assert all(r["parameters"]["fixed"] == {"operator": "invented"} for r in records)
    best = min(records, key=lambda r: (r["result"]["loss"], r["trial_number"]))
    assert summary["best_parameters"] == best["parameters"]
    assert summary["best_loss"] == best["result"]["loss"]
    assert best["result"]["diagnostics"]["nested"] == [1, {"ok": True}]
    assert not summary["model_qualified"] and not summary["fresh_validation_run"]
    assert json.loads((tmp_path / "summary.json").read_text()) == summary
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["design"]["optuna_version"] == optuna.__version__
    assert manifest["design"]["n_trials"] == 6


def test_timeout_resume_matches_uninterrupted_adaptive_proposals(tmp_path, monkeypatch):
    clock = [0.]
    monkeypatch.setattr(search.time, "monotonic", lambda: clock[0])
    split, whole = tmp_path / "split", tmp_path / "whole"

    def slow(parameters, seeds):
        clock[0] += 10.
        return objective(parameters, seeds)

    first = search.run_parameter_search(**settings(split, timeout_seconds=15.), evaluate=slow)
    assert first["stop_reason"] == "invocation_timeout" and first["attempted_trials"] == 2
    resumed = search.run_parameter_search(**settings(split, timeout_seconds=15.), evaluate=objective, resume=True)
    full = search.run_parameter_search(**settings(whole, timeout_seconds=15.), evaluate=objective)
    for left, right in zip(receipts(split), receipts(whole)):
        assert left["parameters"] == right["parameters"]
        assert left["result"] == right["result"]
        assert left["sampler_seed"] == right["sampler_seed"]
    assert resumed["best_parameters"] == full["best_parameters"]
    assert resumed["attempted_trials"] == 6
    again = search.run_parameter_search(**settings(split, timeout_seconds=15.),
                                        evaluate=lambda *_: pytest.fail("budget must not restart"), resume=True)
    assert again["attempted_trials"] == 6


def test_callback_failures_count_toward_total_without_seed_replacement(tmp_path):
    calls = []

    def failing(parameters, seeds):
        calls.append(seeds)
        if len(calls) in (1, 3):
            raise RuntimeError("invented bounded worker failure")
        return objective(parameters, seeds)

    result = search.run_parameter_search(**settings(tmp_path), evaluate=failing)
    assert result["attempted_trials"] == 6 and result["failed_trials"] == 2
    assert result["completed_trials"] == 4 and calls == [(7, 11)] * 6
    assert receipts(tmp_path)[0]["error"] == {"type": "RuntimeError", "message": "invented bounded worker failure"}
    assert receipts(tmp_path)[3]["sampler_phase"] == "startup"
    assert receipts(tmp_path)[4]["sampler_phase"] == "tpe"


def test_mutating_caller_seed_list_cannot_change_frozen_execution(tmp_path):
    original_seeds, calls = [7, 11], []

    def evaluate(parameters, seeds):
        calls.append(seeds)
        original_seeds[:] = [999]
        return objective(parameters, seeds)

    search.run_parameter_search(**settings(tmp_path, seeds=original_seeds), evaluate=evaluate)
    assert calls == [(7, 11)] * 6
    assert all(record["seeds"] == [7, 11] for record in receipts(tmp_path))


def test_interrupted_trial_is_consumed_on_resume_without_retry(tmp_path):
    seen = []

    def interrupt(parameters, seeds):
        seen.append(parameters)
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        search.run_parameter_search(**settings(tmp_path), evaluate=interrupt)
    assert receipts(tmp_path)[0]["state"] == "RUNNING"
    result = search.run_parameter_search(**settings(tmp_path), evaluate=objective, resume=True)
    assert len(seen) == 1
    assert result["attempted_trials"] == 6 and result["failed_trials"] == 1
    assert result["completed_trials"] == 5
    failed = receipts(tmp_path)[0]
    assert failed["interrupted"] and failed["error"]["type"] == "InterruptedTrial"
    assert failed["state"] == "FAIL"


def test_interruption_between_callback_and_sqlite_completion_retains_diagnostics(tmp_path, monkeypatch):
    original_tell = optuna.study.Study.tell

    def interrupt_tell(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(optuna.study.Study, "tell", interrupt_tell)
    with pytest.raises(KeyboardInterrupt):
        search.run_parameter_search(**settings(tmp_path), evaluate=objective)
    evaluated = receipts(tmp_path)[0]
    assert evaluated["state"] == "EVALUATED" and "result" in evaluated
    monkeypatch.setattr(optuna.study.Study, "tell", original_tell)
    result = search.run_parameter_search(**settings(tmp_path), evaluate=objective, resume=True)
    assert result["attempted_trials"] == 6 and result["failed_trials"] == 1
    assert receipts(tmp_path)[0]["result"] == evaluated["result"]


def test_resume_finalizes_completed_sqlite_trial_without_callback_retry(tmp_path, monkeypatch):
    atomic = search._atomic_json

    def interrupt_final_receipt(path, record):
        if path.name.startswith("trial_") and record.get("state") == "COMPLETE":
            raise KeyboardInterrupt()
        return atomic(path, record)

    monkeypatch.setattr(search, "_atomic_json", interrupt_final_receipt)
    with pytest.raises(KeyboardInterrupt):
        search.run_parameter_search(**settings(tmp_path), evaluate=objective)
    assert receipts(tmp_path)[0]["state"] == "EVALUATED"
    monkeypatch.setattr(search, "_atomic_json", atomic)
    seen = []

    def evaluate(parameters, seeds):
        seen.append(parameters)
        return objective(parameters, seeds)

    result = search.run_parameter_search(**settings(tmp_path), evaluate=evaluate, resume=True)
    assert result["completed_trials"] == 6 and result["failed_trials"] == 0
    assert len(seen) == 5 and receipts(tmp_path)[0]["state"] == "COMPLETE"


@pytest.mark.parametrize("updates", [
    {"identity": {"operator": "changed"}}, {"seeds": [7, 12]}, {"n_trials": 7},
    {"timeout_seconds": 61.}, {"n_startup_trials": 2}, {"sampler_seed": 124},
    {"base_parameters": {"x": .1}},
    {"search_space": {"x": {"kind": "float", "low": 0., "high": 2.}}},
])
def test_changed_design_rejects_before_evaluation(tmp_path, updates):
    search.run_parameter_search(**settings(tmp_path, n_trials=3, n_startup_trials=1), evaluate=objective)
    before = (tmp_path / "summary.json").read_bytes()
    changed = settings(tmp_path, n_trials=3, n_startup_trials=1)
    changed.update(updates)
    with pytest.raises(ValueError, match="identity mismatch"):
        search.run_parameter_search(**changed, evaluate=lambda *_: pytest.fail("must reject before evaluation"), resume=True)
    assert (tmp_path / "summary.json").read_bytes() == before


@pytest.mark.parametrize("updates", [
    {"seeds": [True]}, {"seeds": [float("inf")]}, {"seeds": []}, {"seeds": [1, 1]},
    {"sampler_seed": True}, {"n_trials": True}, {"n_trials": 2}, {"identity": {}},
    {"timeout_seconds": float("nan")},
    {"search_space": {"x": {"kind": "float", "low": False, "high": 1.}}},
    {"search_space": {"x": {"kind": "float", "low": 0., "high": float("inf")}}},
    {"search_space": {"x": {"kind": "int", "low": 1., "high": 4}}},
    {"search_space": {"x": {"kind": "float", "low": 0., "high": 1., "log": True}}},
    {"search_space": {"nested.x": {"kind": "float", "low": 0., "high": 1.}}},
    {"search_space": {"x": {"kind": "categorical", "choices": ["a", "a"]}}},
])
def test_invalid_inputs_reject_before_any_output(tmp_path, updates):
    outdir = tmp_path / "invalid"
    with pytest.raises(ValueError):
        search.run_parameter_search(**settings(outdir, **updates), evaluate=objective)
    assert not outdir.exists()


@pytest.mark.parametrize("result", [
    {"loss": True}, {"loss": float("nan")}, {"loss": float("inf")},
    {"loss": "0.1"}, {"loss": .1, "diagnostics": [float("nan")]}, {"missing": .1},
])
def test_invalid_callback_results_are_durable_failed_trials(tmp_path, result):
    summary = search.run_parameter_search(**settings(tmp_path, n_trials=3, n_startup_trials=1),
                                          evaluate=lambda *_: result)
    assert summary["failed_trials"] == summary["attempted_trials"] == 3
    assert summary["completed_trials"] == 0 and summary["best_parameters"] is None
    assert summary["best_trial_number"] is None and summary["best_loss"] is None
    assert all(r["state"] == "FAIL" and r["error"]["type"] == "ValueError" for r in receipts(tmp_path))


def test_exclusive_output_lock_blocks_second_invocation(tmp_path):
    with (tmp_path / ".search.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="holds the output lock"):
            search.run_parameter_search(**settings(tmp_path), evaluate=lambda *_: pytest.fail("locked"))
    assert not (tmp_path / "manifest.json").exists()


def test_public_validator_is_pure_and_returns_detached_normalized_design(tmp_path, monkeypatch):
    monkeypatch.setattr(optuna, "create_study", lambda **_: pytest.fail("validation must not create a study"))
    config = settings(tmp_path)
    config.pop("outdir")
    result = search.validate_search_inputs(**config)
    result["base_parameters"]["fixed"]["operator"] = "changed copy"
    assert config["base_parameters"]["fixed"]["operator"] == "invented"
    assert result["search_space"]["count"]["log"] is False
    assert list(tmp_path.iterdir()) == []


def test_existing_outputs_need_explicit_resume_and_terminal_receipts(tmp_path):
    config = settings(tmp_path, n_trials=3, n_startup_trials=1)
    search.run_parameter_search(**config, evaluate=objective)
    with pytest.raises(FileExistsError):
        search.run_parameter_search(**config, evaluate=objective)
    (tmp_path / "trials" / "trial_000001.json").unlink()
    with pytest.raises(ValueError, match="missing its durable callback receipt"):
        search.run_parameter_search(**config, evaluate=lambda *_: pytest.fail("missing history"), resume=True)


def validated(config):
    return search.validate_search_inputs(**{key: value for key, value in config.items() if key != "outdir"})


def test_saved_best_is_verified_read_only_against_manifest_sqlite_and_receipt(tmp_path, monkeypatch):
    config = settings(tmp_path, n_trials=3, n_startup_trials=1)
    summary = search.run_parameter_search(**config, evaluate=objective)
    before = {str(path.relative_to(tmp_path)): (path.read_bytes(), path.stat().st_mtime_ns)
              for path in tmp_path.rglob("*") if path.is_file()}
    monkeypatch.setattr(optuna, "create_study", lambda **_: pytest.fail("verification must not create a study"))
    assert search.read_verified_search_result(tmp_path, validated(config)) == summary
    after = {str(path.relative_to(tmp_path)): (path.read_bytes(), path.stat().st_mtime_ns)
             for path in tmp_path.rglob("*") if path.is_file()}
    assert before == after


@pytest.mark.parametrize("target", ["summary", "receipt", "sqlite", "identity"])
def test_verification_rejects_modified_best_or_identity(tmp_path, target):
    config = settings(tmp_path, n_trials=3, n_startup_trials=1)
    summary = search.run_parameter_search(**config, evaluate=objective)
    expected = validated(config)
    if target == "summary":
        summary["best_parameters"]["x"] = 99.
        (tmp_path / "summary.json").write_text(json.dumps(summary))
    elif target == "receipt":
        path = tmp_path / "trials" / f"trial_{summary['best_trial_number']:06d}.json"
        record = json.loads(path.read_text())
        record["parameters"]["fixed"] = "modified"
        path.write_text(json.dumps(record))
    elif target == "sqlite":
        with sqlite3.connect(tmp_path / "study.sqlite3") as connection:
            connection.execute("UPDATE trial_values SET value = value + 1000")
    else:
        expected["identity"]["operator"] = "changed"
    with pytest.raises(ValueError, match="mismatch|disagrees"):
        search.read_verified_search_result(tmp_path, expected)


def test_verification_requires_pending_trial_recovery(tmp_path):
    config = settings(tmp_path)

    def interrupt(*_):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        search.run_parameter_search(**config, evaluate=interrupt)
    with pytest.raises(ValueError, match="pending or invalid"):
        search.read_verified_search_result(tmp_path, validated(config))


def test_callback_stop_consumes_current_slot_and_preserves_reason(tmp_path):
    seen = []

    def evaluate(parameters, seeds):
        seen.append(seeds)
        raise search.SearchStopped("source_identity_changed", {"scope": "synthetic callback"})

    summary = search.run_parameter_search(**settings(tmp_path), evaluate=evaluate)
    assert summary["attempted_trials"] == summary["failed_trials"] == 1
    assert seen == [(7, 11)]
    assert summary["stop_reason"] == "source_identity_changed"
    assert summary["stop_diagnostics"] == {"scope": "synthetic callback"}
    assert receipts(tmp_path)[0]["error"]["type"] == "SearchStopped"


def test_admission_stop_consumes_no_new_slot(tmp_path):
    calls = []

    def guard():
        if calls:
            raise search.SearchStopped("output_stop_bytes", {"reserved_bytes": 262144})

    def evaluate(parameters, seeds):
        calls.append(seeds)
        return objective(parameters, seeds)

    summary = search.run_parameter_search(**settings(tmp_path), evaluate=evaluate, before_trial=guard)
    assert summary["attempted_trials"] == summary["completed_trials"] == 1
    assert summary["failed_trials"] == 0 and summary["stop_reason"] == "output_stop_bytes"
    assert len(receipts(tmp_path)) == 1
    assert search.read_verified_search_result(tmp_path, validated(settings(tmp_path))) == summary


def test_resume_rejects_changed_full_receipt_parameters(tmp_path):
    config = settings(tmp_path, n_trials=3, n_startup_trials=1)
    search.run_parameter_search(**config, evaluate=objective)
    path = tmp_path / "trials" / "trial_000001.json"
    record = json.loads(path.read_text())
    record["parameters"]["fixed"] = "changed"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="candidate or seeds disagree"):
        search.run_parameter_search(**config, evaluate=objective, resume=True)
