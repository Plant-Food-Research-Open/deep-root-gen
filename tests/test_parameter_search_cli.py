"""Local CLI and worker controls using invented inputs only."""

import copy
import fcntl
import json
from pathlib import Path
import subprocess
import time

import pytest

from scripts.research import parameter_search as cli

EXAMPLES = Path(__file__).parents[1] / "examples/research"


def setup_files(tmp_path):
    for name in (
        "search_synthetic.json",
        "search_synthetic_parameters.json",
        "search_synthetic_reference.json",
    ):
        (tmp_path / name).write_bytes((EXAMPLES / name).read_bytes())
    return tmp_path / "search_synthetic.json"


def change(path, mutate):
    data = json.loads(path.read_text())
    mutate(data)
    path.write_text(json.dumps(data))


def test_dry_run_validates_without_creating_output_or_running_model(
    tmp_path, monkeypatch, capsys
):
    config = setup_files(tmp_path)
    from deeprootgen.research import search_evaluation

    monkeypatch.setattr(
        search_evaluation,
        "simulate_sample",
        lambda *a, **k: pytest.fail("Unexpected simulation"),
    )
    out = tmp_path / "out"
    assert cli.main(["--config", str(config), "--outdir", str(out)]) == 0
    assert "VALIDATED_NOT_EXECUTED" in capsys.readouterr().out
    assert not out.exists()


@pytest.mark.parametrize(
    "change_kind", ["seeds", "startup", "range", "legacy", "unknown", "higher_orders"]
)
def test_invalid_contract_rejected_before_any_output(tmp_path, change_kind):
    config = setup_files(tmp_path)
    if change_kind == "seeds":
        change(config, lambda d: d.update(qualification_seeds=d["seeds"]))
    elif change_kind == "startup":
        change(config, lambda d: d["budget"].update(n_trials=1))
    elif change_kind == "range":
        change(config, lambda d: d["search_space"]["fichtl_sigma"].update(high=-1))
    elif change_kind == "legacy":
        change(
            tmp_path / "search_synthetic_parameters.json",
            lambda d: d.update(tropism_mode="legacy"),
        )
    elif change_kind == "unknown":
        change(
            tmp_path / "search_synthetic_parameters.json",
            lambda d: d.update(unknown_parameter=42),
        )
    else:
        change(
            tmp_path / "search_synthetic_reference.json",
            lambda d: d.update(root_orders=[1, 2, 3, 4]),
        )
    out = tmp_path / "out"
    with pytest.raises((ValueError, TypeError)):
        cli.main(["--config", str(config), "--outdir", str(out)])
    assert not out.exists()


def test_reject_duplicate_and_nonfinite_json(tmp_path):
    path = tmp_path / "input.json"
    for data in ('{"a":1,"a":2}', '{"a":NaN}'):
        path.write_text(data)
        with pytest.raises(ValueError):
            cli.read_json(path)


def test_each_worker_gets_requested_seed_without_mutating_candidate(
    tmp_path, monkeypatch
):
    parameters = {"random_seed": 42, "x": 3.0}
    original = copy.deepcopy(parameters)
    seen = []

    def fake_run(argv, **kwargs):
        payload = cli.read_json(argv[argv.index("--worker-input") + 1])
        seen.append(payload["parameters"]["random_seed"])
        assert payload["seed"] == payload["parameters"]["random_seed"]
        Path(argv[argv.index("--worker-output") + 1]).write_text(
            json.dumps({"seed": payload["seed"]})
        )
        assert kwargs["env"]["OMP_NUM_THREADS"] == "2"
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    budget = dict(output_stop_bytes=1_000_000, per_seed_timeout_seconds=5)
    for seed in (101, 102, 201):
        result = cli.run_one(
            parameters,
            seed,
            route="construction_steps_v1",
            outdir=tmp_path,
            identity={"files": {}},
            budget=budget,
            deadline=time.monotonic() + 10,
            phase="search" if seed < 200 else "qualify",
        )
        assert result["seed"] == seed
    assert parameters == original and seen == [101, 102, 201]
    assert all(
        cli.read_json(p)["status"] == "complete"
        for p in tmp_path.glob("calls/*/receipt.json")
    )


def test_worker_timeout_keeps_consumed_failed_receipt(tmp_path, monkeypatch):
    def timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(cli.subprocess, "run", timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        cli.run_one(
            {"random_seed": 1},
            2,
            route="graph_segments_v1",
            outdir=tmp_path,
            identity={"files": {}},
            budget=dict(output_stop_bytes=1_000_000, per_seed_timeout_seconds=5),
            deadline=time.monotonic() + 10,
            phase="search",
        )
    record = cli.read_json(next(tmp_path.glob("calls/*/receipt.json")))
    assert record["status"] == "failed" and "TimeoutExpired" in record["error"]


def test_resume_refuses_live_worker_then_retires_interrupted_call(tmp_path):
    folder = tmp_path / "calls/000001"
    folder.mkdir(parents=True)
    receipt = folder / "receipt.json"
    receipt.write_text(json.dumps(dict(status="running", seed=7, phase="search")))
    with (folder / "worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="orphan"):
            cli.recover_call_workers(tmp_path, 1_000_000)
    cli.recover_call_workers(tmp_path, 1_000_000)
    assert cli.read_json(receipt)["status"] == "abandoned"


def test_worker_refuses_expired_reservation_before_simulation(tmp_path, monkeypatch):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(dict(deadline_unix=time.time() - 1)))
    (tmp_path / "receipt.json").write_text(
        json.dumps(dict(status="running", input_sha256=cli.sha(source)))
    )
    from deeprootgen.research import search_evaluation

    monkeypatch.setattr(
        search_evaluation,
        "simulate_sample",
        lambda *a, **k: pytest.fail("Expired worker ran"),
    )
    with pytest.raises(TimeoutError, match="expired"):
        cli.worker(source, tmp_path / "sample.json")
    assert not (tmp_path / "sample.json").exists()


def test_worker_rejects_oversized_sample_before_writing(tmp_path, monkeypatch):
    source = tmp_path / "input.json"
    source.write_text(
        json.dumps(
            dict(
                deadline_unix=time.time() + 10,
                max_sample_bytes=16,
                identity={"files": {}},
                parameters={},
                seed=1,
                route="graph_segments_v1",
            )
        )
    )
    (tmp_path / "receipt.json").write_text(
        json.dumps(dict(status="running", input_sha256=cli.sha(source)))
    )
    from deeprootgen.research import search_evaluation

    monkeypatch.setattr(
        search_evaluation, "simulate_sample", lambda *a, **k: {"result": "x" * 100}
    )
    with pytest.raises(RuntimeError, match="reserved output"):
        cli.worker(source, tmp_path / "sample.json")
    assert not (tmp_path / "sample.json").exists()


def test_output_admission_stops_before_a_model_call(tmp_path, monkeypatch):
    config = setup_files(tmp_path)
    change(config, lambda d: d["budget"].update(output_stop_bytes=262144))
    monkeypatch.setattr(
        cli, "run_one", lambda *a, **k: pytest.fail("Output guard admitted work")
    )
    out = tmp_path / "out"
    cli.main(["--config", str(config), "--outdir", str(out), "--execute"])
    summary = cli.read_json(out / "search/summary.json")
    assert summary["attempted_trials"] == 0
    assert "Output admission" in str(summary)
    assert not (out / "calls").exists()
    assert cli.size(out) < 262144


def test_qualification_rejects_tampered_best_parameters_before_workers(
    tmp_path, monkeypatch
):
    from deeprootgen.research.parameter_search import (
        run_parameter_search,
        validate_search_inputs,
    )

    config_path = setup_files(tmp_path)
    config, parameters, reference, files = cli.load_config(config_path)
    identity = cli.source_identity(config_path, files)
    budget = config["budget"]
    inputs = dict(
        base_parameters=parameters,
        search_space=config["search_space"],
        seeds=config["seeds"],
        n_trials=budget["n_trials"],
        n_startup_trials=budget["n_startup_trials"],
        sampler_seed=config["sampler_seed"],
        timeout_seconds=budget["timeout_seconds"],
        identity=identity,
    )
    out = tmp_path / "out"
    run_parameter_search(
        **inputs, outdir=out / "search", evaluate=lambda *a: {"loss": 1.0}
    )
    change(
        out / "search/summary.json",
        lambda d: d["best_parameters"].update(fichtl_sigma=999.0),
    )
    monkeypatch.setattr(
        cli, "run_one", lambda *a, **k: pytest.fail("Tampered candidate ran")
    )
    with pytest.raises(ValueError, match="summary"):
        cli.qualification(
            config,
            reference,
            out,
            identity,
            time.monotonic() + 10,
            validate_search_inputs(**inputs),
        )
    assert not (out / "qualification_plan.json").exists()


def test_notebook_cells_are_python_and_execution_is_opt_in():
    path = (
        Path(__file__).parents[1]
        / "notebooks/grapevine_fichtl_2024/5_controlled_research_search.ipynb"
    )
    notebook = json.loads(path.read_text())
    source = "\n".join(
        "".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"
    )
    compile(source, str(path), "exec")
    assert "RUN_SEARCH = False" in source and "RUN_QUALIFICATION = False" in source
