"""Synthetic algorithm qualification only; no SO4 ensemble or observed data."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deeprootgen.research.so4_controlled import (
    ARMS,
    Skeleton,
    apply_boundary,
    construct_skeleton,
    digest,
    fichtl_proposal,
    frame,
    keyed_rng,
    minimal_rotation,
    replay_arm,
    validate_geometry,
)

POLICY = "minimum_angle_projection"
SETTINGS = dict(
    fichtl_theta2_deg=51.8,
    fichtl_theta2_sd_deg=22.5,
    fichtl_theta3_deg=50.4,
    fichtl_theta3_sd_deg=22.5,
    fichtl_probability_down=0.65,
    fichtl_sigma=0.2,
    fichtl_trials_type2=2.0,
    fichtl_trials_type3=1.0,
)


def skeleton(nodes, seed=42):
    edges = nodes.loc[nodes.order.gt(0), ["parent_id", "node_id"]].rename(
        columns={"node_id": "child_id"}
    )
    return Skeleton.from_tables(nodes, edges, seed=seed)


def test_legacy_identity_and_paired_frozen_attributes(rsa_nodes):
    initial = skeleton(rsa_nodes)
    results = [replay_arm(initial, arm, SETTINGS, POLICY) for arm in ARMS]
    pd.testing.assert_frame_equal(results[0]["nodes"], rsa_nodes, check_dtype=False)
    assert all(
        r["diagnostics"]["invariant_hashes"]
        == results[0]["diagnostics"]["invariant_hashes"]
        for r in results
    )
    for result in results:
        for receipt in result["diagnostics"]["organs"]:
            if not next(
                s
                for s in result["diagnostics"]["segments"]
                if s["organ_id"] == receipt["organ_id"]
            )["boundary_intervention"]:
                np.testing.assert_allclose(
                    receipt["assigned_heading"], receipt["realised_heading"], atol=1e-12
                )
        validate_geometry(result["nodes"], result["edges"], 20)


def test_legacy_turns_and_torsion_under_insertion_change(rsa_nodes):
    # Longer 3-D lateral chain: dot products and signed triple products survive.
    nodes = rsa_nodes.loc[rsa_nodes.order.le(2)].copy()
    nodes.loc[nodes.node_id.eq(4), ["x", "y", "z", "length"]] = [4, 1, -3, np.sqrt(3)]
    extra = nodes.iloc[-1].copy()
    extra[["node_id", "parent_id", "segment_rank", "x", "y", "z", "length"]] = [
        6,
        4,
        3,
        4,
        3,
        -3,
        2,
    ]
    nodes = pd.concat([nodes, extra.to_frame().T], ignore_index=True).astype(
        {
            "node_id": int,
            "parent_id": int,
            "order": int,
            "organ_id": int,
            "segment_rank": int,
        }
    )
    initial = skeleton(nodes)
    a = replay_arm(initial, "A", SETTINGS, POLICY)["nodes"].set_index("node_id")
    b = replay_arm(initial, "B", SETTINGS, POLICY)["nodes"].set_index("node_id")
    headings = []
    for table in (a, b):
        chain = table.loc[table.organ_id.eq(2)].sort_values("segment_rank")
        xyz = np.vstack(
            [
                table.loc[1, ["x", "y", "z"]].to_numpy(float),
                chain[["x", "y", "z"]].to_numpy(float),
            ]
        )
        v = np.diff(xyz, axis=0)
        headings.append(v / np.linalg.norm(v, axis=1)[:, None])
    np.testing.assert_allclose(
        headings[0] @ headings[0].T, headings[1] @ headings[1].T, atol=1e-12
    )
    assert np.linalg.det(headings[0]) == pytest.approx(
        np.linalg.det(headings[1]), abs=1e-12
    )


def test_keyed_rng_and_paired_fichtl_innovations(rsa_nodes):
    initial = skeleton(rsa_nodes)
    c = replay_arm(initial, "C", SETTINGS, POLICY)
    keyed_rng(42, 50, 4, "unrelated").random(1000)
    d = replay_arm(initial, "D", SETTINGS, POLICY)
    assert [
        x["innovations_sha256"]
        for x in c["diagnostics"]["segments"]
        if "innovations_sha256" in x
    ] == [
        x["innovations_sha256"]
        for x in d["diagnostics"]["segments"]
        if "innovations_sha256" in x
    ]
    np.testing.assert_array_equal(
        keyed_rng(42, 2, 1, "continuation").random(10),
        keyed_rng(42, 2, 1, "continuation").random(10),
    )


@pytest.mark.parametrize(
    "target",
    [
        [1, 0, 0],
        [-1, 0, 0],
        [1, 1e-15, 0],
        [-1, 1e-15, 0],
        [-1, 1e-10, 0],
        [-1, 1e-7, 1e-9],
    ],
)
def test_rotation_degenerate_parallel_antiparallel(target):
    rotation = minimal_rotation([1, 0, 0], target)
    np.testing.assert_allclose(rotation.T @ rotation, np.eye(3), atol=1e-12)
    np.testing.assert_allclose(
        rotation @ [1, 0, 0], np.asarray(target) / np.linalg.norm(target), atol=1e-12
    )
    assert np.linalg.det(rotation) == pytest.approx(1)
    with pytest.raises(ValueError, match="Degenerate"):
        minimal_rotation([0, 0, 0], target)


def test_boundary_projection_feasible_oblique_and_surface():
    feasible = np.array([1, 0, 0.0])
    accepted, _, changed = apply_boundary([0, 0, 19], feasible, 4, 20, POLICY)
    np.testing.assert_array_equal(accepted, feasible)
    assert not changed
    heading = np.array([0.6, 0, 0.8])
    accepted, proposal, changed = apply_boundary([0, 0, 19], heading, 4, 20, POLICY)
    assert changed and proposal[2] > 20
    np.testing.assert_allclose(accepted, [np.sqrt(1 - 0.25**2), 0, 0.25])
    assert np.linalg.norm(accepted) == pytest.approx(1)
    accepted, _, changed = apply_boundary([0, 0, 20], heading, 4, 20, POLICY)
    np.testing.assert_allclose(accepted, [1, 0, 0])
    assert changed
    accepted, _, changed = apply_boundary([0, 0, 20], [0, 0, -1], 4, 20, POLICY)
    assert not changed and accepted[2] == -1


def test_boundary_pure_up_keyed_and_invalid_inputs():
    outputs = [
        apply_boundary(
            [0, 0, 19], [0, 0, 1], 4, 20, POLICY, keyed_rng(4, 2, 3, "boundary")
        )[0]
        for _ in range(2)
    ]
    np.testing.assert_array_equal(*outputs)
    assert outputs[0][2] == 0.25
    for start, heading, length in [
        ([0, 0, 21], [0, 0, 1], 1),
        ([0, 0, 0], [0, 0, 0], 1),
        ([0, 0, 0], [0, 0, 2], 1),
        ([0, 0, 0], [0, 0, 1], 0),
        ([0, 0, np.nan], [0, 0, 1], 1),
    ]:
        with pytest.raises(ValueError):
            apply_boundary(start, heading, length, 20, POLICY)


def test_corrected_first_heading_and_daughter_attachment(rsa_nodes):
    rsa_nodes.loc[:, "z"] += 23
    rsa_nodes.loc[rsa_nodes.order.le(1), "z"] -= 10
    # Restore connected lateral lengths with upward first edge crossing S.
    rsa_nodes.loc[rsa_nodes.node_id.eq(3), ["x", "y", "z", "length"]] = [0, 0, 24, 15]
    rsa_nodes.loc[rsa_nodes.node_id.eq(4), ["x", "y", "z", "length"]] = [2, 0, 24, 2]
    rsa_nodes.loc[rsa_nodes.node_id.eq(5), ["x", "y", "z", "length"]] = [0, 2, 24, 2]
    rsa_nodes.loc[rsa_nodes.node_id.eq(0), "z"] = 13
    # Primary coordinates are now base13 ->9 ->3, preserving lengths.
    result = replay_arm(skeleton(rsa_nodes), "A", SETTINGS, POLICY)
    assert result["diagnostics"]["segments"][0]["boundary_intervention"]
    assert result["nodes"].z.max() <= 20 + 1e-8
    assert result["proposals"].proposed_z.max() > 20
    assert result["diagnostics"]["replays"] == {"physical": 1, "counterfactual": 0}
    validate_geometry(result["nodes"], result["edges"], 20)


def test_skeleton_save_load_and_mutation_detection(rsa_nodes, tmp_path):
    initial = skeleton(rsa_nodes)
    initial.save(tmp_path / "initial.json")
    assert Skeleton.load(tmp_path / "initial.json").sha256 == initial.sha256
    initial.payload["seed"] += 1
    with pytest.raises(ValueError, match="identity"):
        initial.verify()


def test_small_public_initial_construction():
    values = json.loads(
        (Path(__file__).parents[1] / "tests/fixtures/migration_inputs/synthetic_minimal.json").read_text()
    )
    values.update(
        max_order=3,
        min_sec_root_num=1,
        max_sec_root_num=2,
        min_sec_root_length=2,
        max_sec_root_length=3,
        interbranch_distance=2,
    )
    initial = construct_skeleton(values, 42)
    result = replay_arm(initial, "A", SETTINGS, POLICY)
    expected = pd.DataFrame(initial.payload["nodes"])
    np.testing.assert_allclose(
        result["nodes"][["x", "y", "z"]], expected[["x", "y", "z"]], atol=1e-10
    )


def runner_module():
    import importlib.util

    location = (
        Path(__file__).parents[1] / "scripts/research/so4_controlled_experiment.py"
    )
    spec = importlib.util.spec_from_file_location("so4_runner_public_test", location)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_attempt_reservations_consume_failures_and_enforce_cap(tmp_path, rsa_nodes):
    runner = runner_module()
    identity = {"sha256": "synthetic-only"}
    path = runner.reserve_attempt(tmp_path, 1, "A", identity)
    record = json.loads(path.read_text())
    assert record["status"] == "reserved" and record["scaffold_constructions"] == 0
    assert runner.reserve_attempt(tmp_path, 1, "A", identity) is None
    initial = skeleton(rsa_nodes, seed=1)
    (tmp_path / "initial").mkdir()
    initial.save(tmp_path / "initial" / "seed-1.json")
    record.update(status="complete", skeleton_sha256=initial.sha256, artifact_sha256={})
    runner.dump(path, record, tmp_path)
    assert runner.reserve_attempt(tmp_path, 1, "A", identity) is None
    for index in range(2, 41):
        runner.reserve_attempt(tmp_path, index, "A", identity)
    with pytest.raises(RuntimeError, match="40-attempt"):
        runner.reserve_attempt(tmp_path, 41, "A", identity)


def test_prepare_snapshots_without_ensemble(tmp_path, monkeypatch):
    runner = runner_module()
    root = Path(__file__).parents[1]
    monkeypatch.setattr(
        runner,
        "construct_skeleton",
        lambda *a: pytest.fail("prepare constructed scaffold"),
    )
    monkeypatch.setattr(
        runner, "replay_arm", lambda *a: pytest.fail("prepare ran an arm")
    )
    runner.main(
        [
            "--config",
            str(root / "configs/research/so4_t2_controlled.json"),
            "--parameters",
            str(root / "examples/research/so4_t2_fichtl2024.json"),
            "--outdir",
            str(tmp_path),
            "--prepare",
        ]
    )
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert "generation_started_unix" not in manifest
    assert len(list((tmp_path / "frozen_inputs").iterdir())) > 10
    assert not (tmp_path / "ledger").exists()
    manifest["identity"]["sha256"] = "bad"
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match="Resume refused"):
        runner.main(
            [
                "--config",
                str(root / "configs/research/so4_t2_controlled.json"),
                "--parameters",
                str(root / "examples/research/so4_t2_fichtl2024.json"),
                "--outdir",
                str(tmp_path),
                "--prepare",
            ]
        )


def test_storage_limit(tmp_path, monkeypatch):
    runner = runner_module()
    monkeypatch.setattr(runner, "LIMIT", 4)
    with pytest.raises(RuntimeError, match="storage budget"):
        runner.write_output(tmp_path / "large", "12345", tmp_path)
    assert not (tmp_path / "large").exists()


def test_worker_uses_one_saved_skeleton_and_rejects_reinvocation(
    tmp_path, rsa_nodes, monkeypatch
):
    from types import SimpleNamespace

    runner = runner_module()
    identity = {"sha256": "synthetic-worker-only"}
    runner.dump(
        tmp_path / "manifest.json", {"identity": identity, "synthetic": True}, tmp_path
    )
    parameter_path = tmp_path / "public_parameters.json"
    parameter_path.write_text(json.dumps(SETTINGS))
    monkeypatch.setattr(runner, "frozen_identity", lambda *a: identity)
    initial = skeleton(rsa_nodes)
    calls = []
    monkeypatch.setattr(
        runner, "construct_skeleton", lambda *a: (calls.append(a), initial)[1]
    )
    for arm in ("A", "B"):
        reservation = runner.reserve_attempt(tmp_path, 42, arm, identity)
        args = SimpleNamespace(
            outdir=str(tmp_path),
            worker_attempt=str(reservation),
            parameters=str(parameter_path),
            config="public-synthetic",
            reference=[],
        )
        runner.worker(args)
        completed = json.loads(reservation.read_text())
        assert completed["status"] == "complete"
        assert completed["scaffold_constructions"] == int(arm == "A")
        assert len(completed["artifact_sha256"]) == 4
        assert runner.reserve_attempt(tmp_path, 42, arm, identity) is None
        with pytest.raises(RuntimeError, match="unused reservation"):
            runner.worker(args)
    assert len(calls) == 1
    (tmp_path / "seed-42" / "A" / "nodes.csv").write_text("changed")
    with pytest.raises(RuntimeError, match="artifact changed"):
        runner.reserve_attempt(tmp_path, 42, "A", identity)


def test_exact_assigned_insertion_no_search_on_first_segment(rsa_nodes):
    settings = {**SETTINGS, "fichtl_theta2_sd_deg": 0.0, "fichtl_theta3_sd_deg": 0.0}
    result = replay_arm(skeleton(rsa_nodes), "D", settings, POLICY)
    for receipt in result["diagnostics"]["organs"]:
        assert receipt["assigned_angle_deg"] == pytest.approx(
            settings[f"fichtl_theta{receipt['order']}_deg"]
        )
    for segment in result["diagnostics"]["segments"]:
        assert ("candidates" in segment) == (segment["segment_index"] > 1)


def test_boundary_numerical_feasibility():
    rng = np.random.default_rng(123)
    for _ in range(1000):
        length = rng.uniform(0.001, 100)
        cap = rng.uniform(0, 0.999)
        start = np.array([0.0, 0.0, 20 - length * cap])
        heading = np.array([0.0, 0.0, 1.0])
        accepted, _, _ = apply_boundary(
            start, heading, length, 20, POLICY, keyed_rng(42, 1, 1, "boundary")
        )
        assert (start + length * accepted)[2] <= 20


def test_initial_constructor_mode_and_surface_invariance(monkeypatch):
    from deeprootgen.model import RootSystemSimulation

    values = json.loads(
        (Path(__file__).parents[1] / "tests/fixtures/migration_inputs/synthetic_minimal.json").read_text()
    )
    values.update(
        max_order=3,
        min_sec_root_num=1,
        max_sec_root_num=2,
        min_sec_root_length=2,
        max_sec_root_length=3,
        interbranch_distance=2,
        gravitropism=0.0,
        **SETTINGS,
    )

    def forbidden(*args, **kwargs):
        pytest.fail("Construction invoked treatment/run/validation/gravity")

    for name in ("run", "apply_gravitropism", "apply_fichtl_tropism", "validate"):
        monkeypatch.setattr(RootSystemSimulation, name, forbidden)
    constructions = [
        construct_skeleton(
            {**values, "tropism_mode": mode, "soil_surface_z_cm": surface}, 99
        )
        for mode, surface in [
            ("legacy", 0.0),
            ("legacy", 20.0),
            ("fichtl2024", 0.0),
            ("fichtl2024", 20.0),
        ]
    ]
    for candidate in constructions[1:]:
        assert candidate.payload["nodes"] == constructions[0].payload["nodes"]
        assert candidate.payload["edges"] == constructions[0].payload["edges"]
        assert candidate.payload["organs"] == constructions[0].payload["organs"]


def test_long_crossings_ulp_nudges_and_daughter_starts():
    rng = np.random.default_rng(0)
    hits = 0
    for _ in range(15000):
        start = np.array([0.0, 0.0, rng.uniform(-10, 12)])
        length = rng.uniform(8, 30)
        heading = rng.normal(size=3)
        heading[2] = abs(heading[2])
        heading /= np.linalg.norm(heading)
        if start[2] + length * heading[2] <= 20:
            continue
        receipt = {}
        accepted, _, _ = apply_boundary(
            start, heading, length, 20, POLICY, keyed_rng(8, 1, 1, "boundary"), receipt
        )
        hits += receipt["boundary_ulp_nudges"]
        endpoint = start + length * accepted
        assert endpoint[2] <= 20
        assert np.linalg.norm(endpoint - start) == pytest.approx(
            length, rel=1e-12, abs=1e-12
        )
        # Both a continuation and a daughter's first segment must accept this origin.
        for outward in ([0.6, 0, 0.8], [0, 0, 1.0]):
            next_heading, _, _ = apply_boundary(
                endpoint, outward, 12, 20, POLICY, keyed_rng(8, 2, 2, "boundary")
            )
            assert (endpoint + 12 * next_heading)[2] <= 20
    # Cancellation at deep synthetic origins explicitly exercises the nudge path.
    starts = rng.uniform(-10000, 0, 100000)
    lengths = rng.uniform(10001, 20000, 100000)
    caps = (20 - starts) / lengths
    candidates = np.flatnonzero(starts + lengths * caps > 20)
    assert len(candidates) > 0
    index = int(candidates[0])
    start = np.array([0.0, 0.0, starts[index]])
    receipt = {}
    accepted, _, _ = apply_boundary(
        start,
        [0.0, 0.0, 1.0],
        lengths[index],
        20,
        POLICY,
        keyed_rng(8, 3, 3, "boundary"),
        receipt,
    )
    assert receipt["boundary_ulp_nudges"] > 0
    assert (start + lengths[index] * accepted)[2] <= 20
    # Repeated crossings, each accepted endpoint becoming the next origin.
    for _ in range(1000):
        next_heading, _, _ = apply_boundary(
            start, [0.6, 0.0, 0.8], 30.0, 20.0, POLICY, keyed_rng(8, 4, 4, "boundary")
        )
        start = start + 30.0 * next_heading
        assert start[2] <= 20


def test_atomic_writes_ignore_stale_temps_and_never_expose_partial_final(
    tmp_path, monkeypatch
):
    runner = runner_module()
    destination = tmp_path / "output.json"
    destination.with_suffix(".json.tmp").write_text("stale")
    runner.dump(destination, {"old": 1}, tmp_path, exclusive=True)
    runner.dump(destination, {"new": 2}, tmp_path)
    assert json.loads(destination.read_text()) == {"new": 2}
    with pytest.raises(FileExistsError):
        runner.dump(destination, {"replace": False}, tmp_path, exclusive=True)
    assert json.loads(destination.read_text()) == {"new": 2}

    def interrupted_link(*args):
        raise OSError("synthetic interruption before publish")

    monkeypatch.setattr(runner.os, "link", interrupted_link)
    with pytest.raises(OSError, match="synthetic interruption"):
        runner.dump(
            tmp_path / "absent", {"complete": "bytes"}, tmp_path, exclusive=True
        )
    assert not (tmp_path / "absent").exists()


def test_corrupt_ledger_retains_consumed_slot_and_final_receipt(tmp_path):
    runner = runner_module()
    identity = {"sha256": "synthetic-only"}
    reservation = runner.reserve_attempt(tmp_path, 42, "A", identity)
    reservation.write_text('{"truncated":')
    with pytest.raises(RuntimeError, match="consumed ledger slot"):
        runner.reserve_attempt(tmp_path, 42, "B", identity)
    assert len(list((tmp_path / "ledger").glob("attempt-*.json"))) == 1
    runner.persist_receipt(tmp_path, {"identity": identity}, "synthetic interruption")
    receipt = json.loads((tmp_path / "generation_receipt.json").read_text())
    assert receipt["attempts"] == 1 and receipt["unreadable_consumed_slots"] == [
        reservation.name
    ]


def test_resume_skips_failed_abandoned_and_executes_unattempted_pairs(
    tmp_path, rsa_nodes, monkeypatch
):
    from types import SimpleNamespace
    import time

    runner = runner_module()
    identity = {"sha256": "synthetic-resume-only", "source_hashes": {}}
    monkeypatch.setattr(runner, "frozen_identity", lambda *args: identity)
    monkeypatch.setattr(runner, "validate_design", lambda *args: None)
    parameters = tmp_path / "synthetic-parameters.json"
    parameters.write_text(json.dumps(SETTINGS))
    config = tmp_path / "synthetic-design.json"
    config.write_text(json.dumps({"seeds": [42], "arms": list(ARMS)}))
    manifest = {
        "identity": identity,
        "synthetic": True,
        "generation_started_unix": time.time(),
    }
    runner.dump(tmp_path / "manifest.json", manifest, tmp_path)
    initial = skeleton(rsa_nodes)
    (tmp_path / "initial").mkdir()
    initial.save(tmp_path / "initial" / "seed-42.json")
    failed_path = runner.reserve_attempt(tmp_path, 42, "A", identity)
    failed = json.loads(failed_path.read_text())
    failed.update(
        status="failed", scaffold_constructions=1, skeleton_sha256=initial.sha256
    )
    runner.dump(failed_path, failed, tmp_path)
    runner.reserve_attempt(tmp_path, 42, "B", identity)  # interrupted before starting
    executed = []

    def synthetic_subprocess(command, **kwargs):
        reservation = command[command.index("--worker-attempt") + 1]
        executed.append(json.loads(Path(reservation).read_text())["arm"])
        runner.worker(
            SimpleNamespace(
                outdir=str(tmp_path),
                worker_attempt=reservation,
                parameters=str(parameters),
                config=str(config),
                reference=[],
            )
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", synthetic_subprocess)
    runner.main(
        [
            "--config",
            str(config),
            "--parameters",
            str(parameters),
            "--outdir",
            str(tmp_path),
            "--execute",
        ]
    )
    assert executed == ["C", "D"]
    receipt = json.loads((tmp_path / "generation_receipt.json").read_text())
    assert receipt["attempts"] == 4 and receipt["complete"] == 2
    assert {r["status"] for r in receipt["failures"]} == {"failed", "abandoned"}
    assert receipt["counterfactual_replays"] == 0
    runner.main(
        [
            "--config",
            str(config),
            "--parameters",
            str(parameters),
            "--outdir",
            str(tmp_path),
            "--execute",
        ]
    )
    assert executed == ["C", "D"]


def test_truncated_initial_stops_before_other_arm_reservation(tmp_path):
    runner = runner_module()
    identity = {"sha256": "synthetic-only"}
    runner.reserve_attempt(tmp_path, 42, "A", identity)
    (tmp_path / "initial").mkdir()
    (tmp_path / "initial" / "seed-42.json").write_text('{"truncated":')
    with pytest.raises(RuntimeError, match="Invalid/truncated INITIAL"):
        runner.verified_initial(tmp_path, 42, required=True)
    assert len(list((tmp_path / "ledger").glob("attempt-*.json"))) == 1


def test_frozen_design_path_budgets_and_settings(tmp_path):
    runner = runner_module()
    root = Path(__file__).parents[1]
    config = json.loads((root / "configs/research/so4_t2_controlled.json").read_text())
    parameters = root / config["parameters"]
    runner.validate_design(config, parameters)
    wrong = tmp_path / "same-bytes-wrong-path.json"
    wrong.write_bytes(parameters.read_bytes())
    with pytest.raises(ValueError, match="parameter path"):
        runner.validate_design(config, wrong)
    config["budget"]["new_ensemble_attempts"] = 41
    with pytest.raises(ValueError, match="budgets"):
        runner.validate_design(config, parameters)


def test_fichtl_proposal_rejects_invalid_inputs():
    for length, updates in [
        (0, {}),
        (1, {"fichtl_sigma": -1}),
        (1, {"fichtl_trials_type2": np.inf}),
        (1, {"fichtl_probability_down": 2}),
    ]:
        with pytest.raises(ValueError, match="Invalid Fichtl"):
            fichtl_proposal(
                frame([0, 0, -1]),
                length,
                2,
                {**SETTINGS, **updates},
                np.random.default_rng(1),
            )


def test_large_synthetic_four_arm_stress():
    """Public engineering stress only; seed 314159 is outside ensemble seeds."""
    values = json.loads(
        (Path(__file__).parents[1] / "tests/fixtures/migration_inputs/synthetic_minimal.json").read_text()
    )
    values.update(
        max_order=3,
        outer_root_num=1,
        inner_root_num=1,
        min_primary_length=40,
        max_primary_length=50,
        min_sec_root_num=4,
        max_sec_root_num=5,
        growth_sec_root=0.3,
        min_sec_root_length=20,
        max_sec_root_length=30,
        length_reduction=0.8,
        interbranch_distance=0.5,
        floor_threshold=0.1,
        ceiling_threshold=0.9,
        segments_per_root=20,
        gravitropism=0.0,
        root_vary=20,
    )
    initial = construct_skeleton(values, 314159)
    assert len(initial.payload["edges"]) >= 1000
    hashes = []
    for arm in ARMS:
        result = replay_arm(initial, arm, SETTINGS, POLICY)
        hashes.append(result["diagnostics"]["invariant_hashes"])
        assert result["nodes"].z.max() <= 20
        assert result["diagnostics"]["replays"] == {"physical": 1, "counterfactual": 0}
        validate_geometry(result["nodes"], result["edges"], 20)
    assert all(value == hashes[0] for value in hashes)


def test_geometry_rejects_disconnected_cycle_with_isolated_base(rsa_nodes):
    # Every edge has positive geometric length, all IDs exist, edges=N-1,
    # and the stored total is exact. Those numerical checks alone passed before.
    nodes = rsa_nodes.iloc[:3].copy()
    nodes.loc[nodes.node_id.eq(1), ["parent_id", "x", "y", "z", "length"]] = [2, 0., 0., -1., 1.]
    nodes.loc[nodes.node_id.eq(2), ["parent_id", "x", "y", "z", "length"]] = [1, 0., 0., -2., 1.]
    edges = pd.DataFrame({"parent_id": [2, 1], "child_id": [1, 2]})
    assert len(edges) == len(nodes) - 1
    assert nodes.length.sum() == 2.
    with pytest.raises(ValueError, match="directed cycle"):
        validate_geometry(nodes, edges, 20.)


@pytest.mark.parametrize("case", ["multiple_bases", "missing_base", "extra_root_parent", "missing_parent"])
def test_geometry_rejects_invalid_root_and_parent_structure(rsa_nodes, case):
    nodes = rsa_nodes.copy()
    if case == "multiple_bases":
        nodes.loc[nodes.node_id.eq(2), ["order", "parent_id"]] = [0, -1]
    elif case == "missing_base":
        nodes.loc[nodes.node_id.eq(0), "order"] = 1
    elif case == "extra_root_parent":
        nodes.loc[nodes.node_id.eq(2), "parent_id"] = -1
    else:
        nodes.loc[nodes.node_id.eq(2), "parent_id"] = 999
    edges = nodes.loc[nodes.order.gt(0), ["parent_id", "node_id"]].rename(columns={"node_id": "child_id"})
    expected_error = "missing parent" if case == "missing_parent" else "exactly one base/root"
    with pytest.raises(ValueError, match=expected_error):
        validate_geometry(nodes, edges, 20.)


def test_geometry_accepts_rooted_tree_with_nonzero_base_id(rsa_nodes):
    nodes = rsa_nodes.copy()
    nodes.loc[:, "node_id"] += 10
    nodes.loc[nodes.order.gt(0), "parent_id"] += 10
    edges = nodes.loc[nodes.order.gt(0), ["parent_id", "node_id"]].rename(columns={"node_id": "child_id"})
    validate_geometry(nodes, edges, 20.)


def test_replay_rejects_saved_origin_surface_mismatch(rsa_nodes):
    initial = skeleton(rsa_nodes)
    initial.payload["parameters"] = dict(research_base_depth_cm=7., soil_surface_z_cm=25.)
    initial = Skeleton(initial.payload, digest(initial.payload))
    with pytest.raises(ValueError, match="Saved origin surface disagrees"):
        replay_arm(initial, "D", SETTINGS, POLICY)
