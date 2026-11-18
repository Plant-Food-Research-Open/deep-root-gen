"""Replay the original native contracts under the current test runtime."""

import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from tests.public_checkpoint_reference import (
    _module_path,
    _verify_modules,
    comparison_command,
    subprocess_environment,
)

FIXTURES = Path(__file__).parent / "fixtures"
CONTRACTS = json.loads((FIXTURES / "native_execution_contracts.json").read_text())


def table_hash(frame):
    csv = frame.to_csv(index=False, float_format="%.17g", lineterminator="\n")
    return hashlib.sha256(csv.encode()).hexdigest()


def json_hash(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode()).hexdigest()


def capture_contract(record, simulation_class):
    """Use the original entrypoints in the reference subprocess."""
    from deeprootgen.data_model import RootSimulationModel
    from deeprootgen.research.cohort_root_generator import CohortRootGenerator
    from deeprootgen.research.construction_step_replay import replay_construction_steps
    from deeprootgen.research.so4_controlled import construct_skeleton

    contract = record["contract"]
    seed = record["seed"]
    if contract == "cohort_v5":
        result = CohortRootGenerator(record["parameters"]).generate(
            seed, record["older_count"], record["later_count"]
        )
        tables = ("nodes", "edges", "organs", "observation_nodes", "observation_edges")
        return dict(
            tables={name: table_hash(getattr(result, name)) for name in tables},
            diagnostics=result.diagnostics,
        )

    parameters = RootSimulationModel.model_validate(record["parameters"])
    if contract == "construction_steps_v1":
        initial = construct_skeleton(parameters, seed)
        result = replay_construction_steps(
            initial, "D", parameters.model_dump(), "minimum_angle_projection"
        )
        diagnostics = result["diagnostics"]
        return dict(
            nodes=table_hash(result["nodes"]),
            edges=table_hash(result["edges"]),
            initial_sha256=initial.sha256,
            steps_sha256=json_hash(diagnostics["construction_steps"]),
            fragments_sha256=json_hash(diagnostics["graph_fragments"]),
        )

    assert contract in {"legacy", "fichtl2024"}, contract
    simulation = simulation_class(random_seed=seed, simulation_tag=parameters.simulation_tag)
    simulation.run(parameters)
    nodes, edges = simulation.G.as_df()
    return dict(nodes=table_hash(nodes), edges=table_hash(edges), rng=simulation.rng.bit_generator.state)


def replay_native_contracts(target):
    """Authenticate and execute independent historical source once for the suite."""
    archive = (FIXTURES / "native_execution_reference_source.json.gz").read_bytes()
    assert hashlib.sha256(archive).hexdigest() == CONTRACTS["reference_archive_sha256"]
    for name, source in json.loads(gzip.decompress(archive)).items():
        path = _module_path(target, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source.encode())
    _verify_modules(target, CONTRACTS["reference_source_sha256"])

    script = """
import json
import sys
from pathlib import Path

from tests.native_execution_reference import CONTRACTS, capture_contract

results = [capture_contract(record, ComparisonSimulation) for record in CONTRACTS["records"]]
Path(sys.argv[1]).write_text(json.dumps(results, allow_nan=False))
"""
    output = target / "reference_outputs.json"
    result = subprocess.run(
        [*comparison_command(script, current=False), str(output)],
        cwd=target, env=subprocess_environment(target), text=True, capture_output=True, timeout=120,
    )
    assert result.returncode == 0, f"Historical native contract replay failed\n{result.stderr}"
    records = json.loads(output.read_text())
    assert len(records) == len(CONTRACTS["records"])
    return records
