"""Native parity against independent pre-migration source, using invented inputs."""

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import RootSimulationModel, RootSimulationConfig
from deeprootgen.archive.simulation import RootSystemSimulation
from deeprootgen.research.cohort_root_generator import CohortRootGenerator
from deeprootgen.research.so4_controlled import capture_initial

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/native_execution_contracts.json").read_text()
)


def table_hash(frame):
    return hashlib.sha256(
        frame.to_csv(index=False, float_format="%.17g").encode()
    ).hexdigest()


def json_hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def configuration(record):
    cohort = record["contract"] == "cohort_v5"
    construction = dict(
        kind="cohort" if cohort else "native", parameters=record["parameters"]
    )
    if cohort:
        construction.update(
            older_count=record["older_count"], later_count=record["later_count"]
        )
    return RootSimulationConfig(
        random_seed=record["seed"],
        construction=construction,
        simulation_tag=record["parameters"].get("simulation_tag", "default"),
        trajectory=(
            record["contract"]
            if cohort or record["contract"] == "construction_steps_v1"
            else "native"
        ),
    )


@pytest.mark.parametrize("record", FIXTURE["records"])
def test_frozen_reference_parity_and_native_ownership(record, monkeypatch):
    config = configuration(record)
    before = config.model_dump()
    sim = RootSystemSimulation(
        random_seed=config.random_seed, simulation_tag=config.simulation_tag
    )
    snapshots = []

    def forbidden(*args, **kwargs):
        pytest.fail("Fresh native run called an independent generator/replay")

    monkeypatch.setattr(CohortRootGenerator, "generate", forbidden)
    from deeprootgen.research import so4_controlled, construction_step_replay

    monkeypatch.setattr(so4_controlled, "construct_skeleton", forbidden)
    monkeypatch.setattr(
        construction_step_replay, "replay_construction_steps", forbidden
    )
    recorder = (
        (lambda sim, p: snapshots.append(capture_initial(sim, p)))
        if config.trajectory == "construction_steps_v1"
        else None
    )
    assert sim.run(config, initial_recorder=recorder) is None
    assert config.model_dump() == before
    nodes, edges = sim.G.as_df()
    assert len(nodes.node_id.unique()) == len(nodes)
    assert set(edges.parent_id) <= set(nodes.node_id)
    assert sum(len(o.segments) for group in sim.organs.values() for o in group) == int(
        nodes.order.gt(0).sum()
    )
    for group in sim.organs.values():
        for organ in group:
            assert (
                organ.segments[0].node_data.parent_id
                == organ.parent_node.node_data.node_id
            )
            assert all(n.organ is organ for n in organ.segments)
            assert organ.mass == pytest.approx(organ.calculate_mass(), rel=1e-12)
            for child in organ.child_organs:
                assert child.parent_node in organ.segments
    if record["contract"] == "cohort_v5":
        full_nodes, full_edges = sim.result.cohort_tables(sim.G)
        projected = full_nodes.loc[full_nodes.node_id.ne(0)].copy()
        projected["plant_id"] = projected.primary_tree_id
        projected.loc[projected.order.eq(0), "parent_id"] = -1
        view = dict(
            nodes=full_nodes,
            edges=full_edges,
            organs=sim.result.organ_table,
            observation_nodes=projected,
            observation_edges=full_edges.loc[full_edges.parent_id.ne(0)].copy(),
        )
        assert {k: table_hash(v) for k, v in view.items()} == record["tables"]
        assert sim.result.diagnostics == record["diagnostics"]
        assert nodes.plant_id.nunique() == 1  # Actual vine identity survives.
        assert len(sim.G.bases) == record["older_count"] + record["later_count"]
        assert len(edges) == len(nodes) - len(sim.G.bases)
    else:
        assert table_hash(nodes) == record["nodes"]
        assert table_hash(edges) == record["edges"]
        if record["contract"] == "construction_steps_v1":
            assert snapshots[0].sha256 == record["initial_sha256"]
            assert (
                json_hash(sim.result.diagnostics["construction_steps"])
                == record["steps_sha256"]
            )
            assert (
                json_hash(sim.result.diagnostics["graph_fragments"])
                == record["fragments_sha256"]
            )
        else:
            assert sim.rng.bit_generator.state == record["rng"]


def test_extended_rejects_conflicting_unused_and_unknown_options_before_execution():
    record = next(r for r in FIXTURE["records"] if r["contract"] == "cohort_v5")
    config = configuration(record).model_dump()
    mutations = [
        lambda c: c.update(trajectory="native"),
        lambda c: c.update(random_seed=True),
        lambda c: c.update(unknown_parameter=3),
        lambda c: c["construction"]["parameters"].update(gravitropism=0.1),
        lambda c: c["construction"].update(older_count=100000),
        lambda c: c["construction"]["parameters"]["orders"]["2"].update(unknown=1),
    ]
    for mutate in mutations:
        candidate = copy.deepcopy(config)
        mutate(candidate)
        with pytest.raises(ValueError):
            RootSimulationConfig(**candidate)


def test_extended_seed_reuse_and_failure_do_not_report_success():
    config = configuration(
        next(r for r in FIXTURE["records"] if r["contract"] == "cohort_v5")
    )
    wrong = RootSystemSimulation(random_seed=99)
    with pytest.raises(ValueError, match="seed"):
        wrong.run(config)
    assert len(wrong.G.nodes) == 1 and not wrong.organs
    sim = RootSystemSimulation(random_seed=config.random_seed)
    sim.run(config)
    with pytest.raises(ValueError, match="fresh"):
        sim.run(config)


def test_observer_projection_preserves_true_vine_and_root_material():
    config = configuration(
        next(r for r in FIXTURE["records"] if r["contract"] == "cohort_v5")
    )
    sim = RootSystemSimulation(random_seed=config.random_seed)
    sim.run(config)
    nodes, edges = sim.result.observation_tables(sim.G)
    assert nodes.vine_id.nunique() == 1
    assert (
        nodes.plant_id.nunique()
        == config.construction.older_count + config.construction.later_count
    )
    from deeprootgen.research.core_observation import qualify_root_segments

    support = qualify_root_segments(
        nodes,
        edges,
        coordinate_frame=sim.result.metadata["coordinate_frame"],
        fine_diameter_max_mm=config.construction.parameters.fine_cutoff_mm,
        dry_density_g_cm3=config.construction.parameters.dry_density_g_cm3,
    )
    np.testing.assert_allclose(
        support.whole_system_totals["included"]["dry_mass_g"],
        sim.result.organ_table.dry_mass_g.sum(),
        rtol=1e-12,
    )


def test_networkx_retains_an_isolated_root_base():
    from deeprootgen.model.hgraph import RootSystemGraph

    graph = RootSystemGraph()
    nodes, edges = graph.as_df()
    # An explicit empty edge schema also describes a material-free forest.
    graph_view = graph.as_networkx()
    assert set(graph_view.nodes) == set(nodes.node_id)
    base = graph.base_node.node_data.node_id
    assert graph_view.nodes[base]['organ_coordinates']['x'] == 0.


def test_partial_cohort_failure_has_no_success_result():
    config = configuration(
        next(r for r in FIXTURE["records"] if r["contract"] == "cohort_v5")
    ).model_dump()
    config["construction"]["parameters"]["max_organs"] = 3
    config = RootSimulationConfig(**config)
    sim = RootSystemSimulation(random_seed=config.random_seed)
    with pytest.raises(ValueError, match="budget"):
        sim.run(config)
    assert sim.result is None


def test_mutated_extended_config_is_revalidated_before_construction():
    config = configuration(
        next(r for r in FIXTURE["records"] if r["contract"] == "construction_steps_v1")
    )
    config.construction.parameters.soil_surface_z_cm = 0.0
    sim = RootSystemSimulation(random_seed=config.random_seed)
    with pytest.raises(ValueError):
        sim.run(config)
    assert len(sim.G.nodes) == 1 and not sim.organs


def test_extended_native_rejects_nonfinite_inputs_and_flat_reuse():
    config = configuration(
        next(r for r in FIXTURE["records"] if r["contract"] == "legacy")
    )
    values = config.model_dump()
    values["construction"]["parameters"]["root_ratio"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        RootSimulationConfig(**values)
    sim = RootSystemSimulation(random_seed=config.random_seed)
    sim.run(config)
    with pytest.raises(ValueError, match="fresh"):
        sim.run(config.construction.parameters)


def test_service_guard_rejects_extended_contracts_before_side_effects():
    import ast
    from deeprootgen.data_model.execution import require_native_service_request

    flat = RootSimulationModel(
        **next(r["parameters"] for r in FIXTURE["records"] if r["contract"] == "legacy")
    )
    assert require_native_service_request(flat) is None
    for contract in ("construction_steps_v1", "cohort_v5"):
        config = configuration(
            next(r for r in FIXTURE["records"] if r["contract"] == contract)
        )
        with pytest.raises(ValueError, match="offline"):
            require_native_service_request(config)
    # Inspect the service boundary without importing or starting Prefect/MLflow.
    source = Path(__file__).parents[1] / "app/flows/run_simulation.py"
    tree = ast.parse(source.read_text())
    for name in ("execute_simulation", "run_simulation", "run_simulation_flow"):
        function = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name
        )
        first_action = function.body[1]  # After the docstring, before any service call.
        assert isinstance(first_action, ast.Expr)
        assert isinstance(first_action.value, ast.Call)
        assert first_action.value.func.id == "resolve_config"
