"""Algorithm checks for the optional research kernel, not biological validation."""

import json
import hashlib
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import RootSimulationModel
from deeprootgen.model import RootSystemSimulation
from deeprootgen.utils.tropism import insertion_heading, sample_heading
from tests.public_checkpoint_reference import materialize_reference, subprocess_environment


def parameters(mode="legacy"):
    values = json.loads(
        (Path(__file__).parents[1] / "examples/synthetic_minimal.json").read_text()
    )
    values.update(
        max_order=3,
        min_sec_root_num=1,
        max_sec_root_num=2,
        min_sec_root_length=2,
        max_sec_root_length=3,
        interbranch_distance=2,
        tropism_mode=mode,
        soil_surface_z_cm=20,
    )
    if mode == "fichtl2024":
        values.update(
            gravitropism=0.0,
            fichtl_probability_down=0.65,
            fichtl_sigma=0.2,
            fichtl_trials_type2=2,
            fichtl_trials_type3=1,
            fichtl_theta2_deg=51.8,
            fichtl_theta2_sd_deg=22.5,
            fichtl_theta3_deg=50.4,
            fichtl_theta3_sd_deg=22.5,
        )
    return RootSimulationModel(**values)


def test_insertion_angle_and_step_scaling():
    rng = np.random.default_rng(3)
    heading = insertion_heading([0, 0, -1], 60, 0, rng)
    assert np.dot(heading, [0, 0, -1]) == pytest.approx(0.5)
    chosen, receipt = sample_heading(heading, 4, 1, 0.2, 2, rng)
    assert receipt["candidates"] == 5  # initial + N*sqrt(ds)
    assert np.linalg.norm(chosen) == pytest.approx(1)


def test_probability_changes_objective_and_surface_is_respected():
    selections = []
    for probability in (0, 1):
        rng = np.random.default_rng(123)
        samples = [
            sample_heading([1, 0, 0], 1, probability, 0.3, 8, rng)[0]
            for _ in range(200)
        ]
        selections.append(np.array(samples))
    assert np.abs(selections[0][:, 2]).mean() < np.abs(selections[1][:, 2]).mean() / 2
    assert selections[1][:, 2].mean() < -0.2
    direction, receipt = sample_heading(
        [0, 0, 1], 2, 0, 0, 2, np.random.default_rng(1), start_z=19, surface_z=20
    )
    assert receipt["surface_fallback"]
    assert 19 + 2 * direction[2] <= 20
    assert np.linalg.norm(direction) == pytest.approx(1)


def test_explicit_parameters_required():
    p = parameters().model_dump()
    p["tropism_mode"] = "fichtl2024"
    p["gravitropism"] = 0.0
    with pytest.raises(ValueError, match="explicit"):
        RootSimulationModel(**p)


def test_graph_attachments_lengths_scaffold_and_seed():
    p = parameters("fichtl2024")
    sim = RootSystemSimulation(random_seed=p.random_seed)
    sim.init_organs(p)
    sim.position_secondary_roots(p)
    sim.position_primary_roots(p)
    original, edges = sim.G.as_df()
    sim.apply_fichtl_tropism(p)
    actual, actual_edges = sim.G.as_df()
    pd.testing.assert_frame_equal(edges, actual_edges)
    pd.testing.assert_frame_equal(
        original.loc[original.order <= 1], actual.loc[actual.order <= 1]
    )
    by_id = actual.set_index("node_id")
    for row in actual.itertuples():
        if row.order:
            start = by_id.loc[row.parent_id, ["x", "y", "z"]].to_numpy(float)
            assert np.linalg.norm(
                np.array([row.x, row.y, row.z]) - start
            ) == pytest.approx(row.length, rel=1e-5, abs=1e-6)
    tables = []
    for _ in range(2):
        model = RootSystemSimulation(random_seed=p.random_seed)
        model.run(p)
        tables.append(model.G.as_df())
    for i in range(2):
        pd.testing.assert_frame_equal(tables[0][i], tables[1][i])
    assert not tables[0][0].invalid_root.any()
    assert tables[0][0].z.max() <= p.soil_surface_z_cm + p.no_root_zone


def test_below_surface_upward_lateral_does_not_need_downward_apex():
    p = parameters("fichtl2024")
    sim = RootSystemSimulation(random_seed=p.random_seed)
    sim.init_organs(p)
    sim.position_secondary_roots(p)
    sim.position_primary_roots(p)
    organ = sim.organs[2][0]
    origin = organ.get_local_origin()
    distance = 0.0
    for node in organ.segments:
        distance += node.node_data.length
        node.node_data.x, node.node_data.y, node.node_data.z = origin + [0, 0, distance]
    before = organ.get_coordinates().copy()
    organ.validate(20, max_attempts=0, enforce_downward_apex=False)
    assert not organ.invalid_root
    np.testing.assert_array_equal(organ.get_coordinates(), before)


def test_legacy_implicit_and_explicit_mode_match():
    values = parameters().model_dump()
    values.pop("tropism_mode")
    tables = []
    for settings in (values, {**values, "tropism_mode": "legacy"}):
        p = RootSimulationModel(**settings)
        sim = RootSystemSimulation(random_seed=p.random_seed)
        sim.run(p)
        tables.append(sim.G.as_df())
    for i in range(2):
        pd.testing.assert_frame_equal(tables[0][i], tables[1][i])


def test_default_surface_has_no_post_tropism_rotation():
    p = parameters("fichtl2024").model_copy(update={"soil_surface_z_cm": 0.0})
    sim = RootSystemSimulation(random_seed=p.random_seed)
    apply = sim.apply_fichtl_tropism
    snapshots = []

    def record(settings):
        apply(settings)
        snapshots.append(sim.G.as_df()[0][["x", "y", "z"]].copy())

    sim.apply_fichtl_tropism = record
    sim.run(p)
    nodes = sim.G.as_df()[0]
    pd.testing.assert_frame_equal(nodes[["x", "y", "z"]], snapshots[0])
    assert nodes.loc[~nodes.invalid_root, "z"].max() <= 0
    assert all(
        v["reorientations"] == 0 for v in sim.validation_diagnostics if v["order"] > 1
    )


def test_boundary_and_schema_negative_cases():
    with pytest.raises(ValueError, match="start"):
        sample_heading(
            [0, 0, -1],
            1,
            0.65,
            0.2,
            2,
            np.random.default_rng(1),
            start_z=21,
            surface_z=20,
        )
    base = parameters("fichtl2024").model_dump()
    for update in (
        {"fichtl_sigma": float("inf")},
        {"soil_surface_z_cm": float("inf")},
        {"max_order": 4},
        {"enable_soil": True},
        {"gravitropism": 0.1},
    ):
        with pytest.raises(ValueError):
            RootSimulationModel(**{**base, **update})


LEGACY_PARITY_SCRIPT = r"""
import json
from pathlib import Path
import sys
import deeprootgen.model.root as root_module
import deeprootgen.data_model.simulation_data_models as schema_module
import deeprootgen.utils.branching as branching_module

outputs = []
for values in json.loads(sys.stdin.read()):
    parameters = schema_module.RootSimulationModel(**values)
    simulation = root_module.RootSystemSimulation(random_seed=parameters.random_seed)
    simulation.run(parameters)
    nodes, edges = simulation.G.as_df()
    outputs.append({
        "csv": [table.to_csv(index=False) for table in (nodes, edges)],
        "dtypes": [[[str(name), str(dtype)] for name, dtype in table.dtypes.items()]
                   for table in (nodes, edges)],
        "geometry": nodes[["node_id", "parent_id", "x", "y", "z", "length", "diameter"]].values.tolist(),
        "rng": simulation.rng.bit_generator.state,
    })
print(json.dumps({"loaded_modules": {
    "deeprootgen/model/root.py": str(Path(root_module.__file__).resolve()),
    "deeprootgen/data_model/simulation_data_models.py": str(Path(schema_module.__file__).resolve()),
    "deeprootgen/utils/branching.py": str(Path(branching_module.__file__).resolve()),
}, "outputs": outputs}, sort_keys=True, allow_nan=False))
"""


def test_prechange_legacy_golden(tmp_path):
    # Historical fixed digests remain an unchanged receipt of their original
    # runtime. Acceptance compares both public sources on this SAME runtime.
    fixture_path = Path(__file__).parent / "fixtures/fichtl_legacy_golden.json"
    fixture = json.loads(fixture_path.read_text())
    current = Path(__file__).parents[1]
    reference = materialize_reference(current, tmp_path, "pre_research_legacy")
    parameters = [case["parameters"] for case in fixture["cases"]]
    results, source_hashes = {}, {}
    for name, source in (("reference", reference), ("current", current)):
        run = subprocess.run(
            [sys.executable, "-c", LEGACY_PARITY_SCRIPT],
            input=json.dumps(parameters), text=True, capture_output=True,
            check=True, timeout=90, cwd=source,
            env=subprocess_environment(source),
        )
        result = json.loads(run.stdout)
        source_hashes[name] = {}
        for module, loaded in result["loaded_modules"].items():
            assert Path(loaded).resolve() == (source / module).resolve()
            source_hashes[name][module] = hashlib.sha256((source / module).read_bytes()).hexdigest()
        results[name] = result["outputs"]
    for old, new in zip(results["reference"], results["current"]):
        assert [value.encode("utf-8") for value in old["csv"]] == [value.encode("utf-8") for value in new["csv"]]
        assert old["dtypes"] == new["dtypes"]
        assert old["geometry"] == new["geometry"]
        assert old["rng"] == new["rng"]
    assert len(results["reference"]) == len(results["current"]) == len(parameters) == 2
    receipt = {
        "source_hashes": source_hashes,
        "historical_fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        "historical_csv_sha256": [case["csv_sha256"] for case in fixture["cases"]],
        "paired_csv_sha256": {
            name: [[hashlib.sha256(value.encode("utf-8")).hexdigest() for value in case["csv"]]
                   for case in outputs] for name, outputs in results.items()
        },
        "exact_csv_dtypes_geometry_rng": True,
        "parameters": parameters,
    }
    (tmp_path / "legacy_parity.json").write_text(json.dumps(receipt, indent=2) + "\n")
