"""Synthetic interface checks; no observation data or scientific calibration."""

import json
from pathlib import Path
import socket
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from deeprootgen.archive.export import simulate
from deeprootgen.data_model import RootSimulationModel
from deeprootgen.archive.simulation import RootSystemSimulation

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "tests/fixtures/migration_inputs/synthetic_minimal.json"


def test_seeded_api_cli_parity_without_services(tmp_path, monkeypatch):
    def deny_network(*args, **kwargs):
        raise AssertionError("Offline simulation attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    spec = json.loads(CONFIG.read_text())
    parameters = RootSimulationModel(**spec)
    model = RootSystemSimulation(random_seed=42, simulation_tag=spec["simulation_tag"])
    model.run(parameters)
    expected_nodes, expected_edges = model.G.as_df()
    first = simulate(spec, tmp_path / "first")
    simulate(spec, tmp_path / "second")
    assert (first["node_count"], first["edge_count"]) == (11, 10)
    assert expected_nodes.node_id.is_unique
    assert expected_nodes.query("order == 0").parent_id.tolist() == [-1]
    assert set(expected_edges.parent_id) <= set(expected_nodes.node_id)
    assert set(expected_edges.child_id) <= set(expected_nodes.node_id)
    assert (
        np.isfinite(expected_nodes[["x", "y", "z", "length", "diameter"]]).all().all()
    )
    assert (expected_nodes[["length", "diameter"]] >= 0).all().all()
    for group in expected_nodes.query("order == 1").groupby("organ_id"):
        assert group[1].segment_rank.tolist() == [1, 2, 3, 4, 5]
    for name, expected in [
        ("nodes.csv", expected_nodes),
        ("edges.csv", expected_edges),
    ]:
        a = pd.read_csv(tmp_path / "first" / name)
        b = pd.read_csv(tmp_path / "second" / name)
        pd.testing.assert_frame_equal(a, b)
        pd.testing.assert_frame_equal(a, expected, check_exact=False)
    assert (tmp_path / "first/roots.html").stat().st_size > 1000
    with pytest.raises(FileExistsError):
        simulate(spec, tmp_path / "first")


def test_cli_from_unrelated_directory(tmp_path):
    command = [sys.executable, "-m", "deeprootgen"]
    help_result = subprocess.run(
        command + ["--help"], cwd=tmp_path, capture_output=True, timeout=15
    )
    assert help_result.returncode == 0
    result = subprocess.run(
        command
        + ["simulate", "--config", str(ROOT / "examples/synthetic_minimal.json"), "--outdir", str(tmp_path / "cli")],
        cwd=tmp_path,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr.decode()
    receipt = json.loads(result.stdout)
    assert receipt["node_count"] == 11 and receipt["edge_count"] == 10
    assert pd.read_csv(tmp_path / "cli/edges.csv").columns.tolist() == [
        "parent_id",
        "child_id",
    ]
    missing = subprocess.run(
        command
        + ["simulate", "--config", "absent.json", "--outdir", str(tmp_path / "bad")],
        cwd=tmp_path,
        capture_output=True,
        timeout=15,
    )
    assert missing.returncode != 0
    assert not (tmp_path / "bad").exists()
