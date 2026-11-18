"""One native engine with independently enabled features (invented inputs only).

The first delivered proof: native generation with primary correlated
curvature switched off -> on -> off in the same JSON file, with exact baseline
recovery and unchanged sampled biology/material while the curve changes.
"""

import ast
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deeprootgen.archive.export import main, simulate
from deeprootgen.data_model import RootSimulationModel
from deeprootgen.archive.resolution import explain_config, resolve_config
from deeprootgen.data_model.resolution import ENGINE_PHASES
from deeprootgen.model import engine as engine_module
from deeprootgen.archive.simulation import RootSystemSimulation

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "tests/fixtures/migration_inputs/design/native_feature_options.proposed.json"
FIXTURE = json.loads((ROOT / "tests/fixtures/native_execution_contracts.json").read_text())
MODES = ["legacy", "fichtl2024"]


def table_hash(frame):
    return hashlib.sha256(frame.to_csv(index=False, float_format="%.17g").encode()).hexdigest()


def v3(mode="legacy", curvature=False, sd=0.08, **updates):
    spec = json.loads(EXAMPLE.read_text())
    spec["parameters"]["tropism_mode"] = mode
    if mode == "fichtl2024":
        spec["parameters"]["gravitropism"] = 0.0
    spec["parameters"].update(updates)
    law = spec["features"]["curvature"]["settings"]["by_order"]["1"]
    law["curvature_sd_rad_cm"] = sd
    law["step_cm"] = 0.7
    spec["features"]["curvature"]["enabled"] = curvature
    return spec


def flat_equivalent(spec):
    return RootSimulationModel(
        **spec["parameters"],
        random_seed=spec["random_seed"],
        simulation_tag=spec["simulation_tag"],
        root_ratio=0.5,
        mechanical_constraints=0.5,
        t=0,
    )


def run(source, seed=42, tag=None):
    tag = tag if tag is not None else json.loads(EXAMPLE.read_text())["simulation_tag"]
    sim = RootSystemSimulation(random_seed=seed, simulation_tag=tag)
    sim.run(copy.deepcopy(source) if isinstance(source, dict) else source)
    return sim


def tables(sim):
    nodes, edges = sim.G.as_df()
    return table_hash(nodes), table_hash(edges)


def node_frame(sim):
    return sim.G.as_df()[0].set_index("node_id")


@pytest.mark.parametrize("mode", MODES)
def test_every_input_reaches_the_same_engine_and_lifecycle(mode, monkeypatch):
    calls = []
    original = engine_module._execute_phases

    def spy(simulation, resolved, phases, **kwargs):
        calls.append((resolved.source_schema, resolved.laws.view))
        return original(simulation, resolved, phases, **kwargs)

    monkeypatch.setattr(engine_module, "_execute_phases", spy)
    from deeprootgen.model import cohort, execution

    # The separate complete runners are gone, not merely bypassed.
    assert not hasattr(cohort, "run_cohort") and not hasattr(execution, "run_construction_steps")
    from deeprootgen.model.root import RootSystemSimulation as Simulation

    assert not hasattr(Simulation, "_run_native") and not hasattr(Simulation, "_realize_organs")
    spec = v3(mode)
    v2 = dict(
        schema_version=2,
        random_seed=spec["random_seed"],
        simulation_tag=spec["simulation_tag"],
        construction=dict(kind="native", parameters=flat_equivalent(spec).model_dump()),
    )
    steps = next(r for r in FIXTURE["records"] if r["contract"] == "construction_steps_v1")
    cohort_record = next(r for r in FIXTURE["records"] if r["contract"] == "cohort_v5")
    historical = [
        (dict(schema_version=2, random_seed=steps["seed"], trajectory="construction_steps_v1",
              construction=dict(kind="native", parameters=steps["parameters"])), steps["seed"]),
        (dict(schema_version=2, random_seed=cohort_record["seed"], trajectory="cohort_v5",
              construction=dict(kind="cohort", parameters=cohort_record["parameters"],
                                older_count=cohort_record["older_count"], later_count=cohort_record["later_count"])),
         cohort_record["seed"]),
    ]
    traces = []
    for source in (flat_equivalent(spec), v2, spec, v3(mode, curvature=True)):
        traces.append(run(source).result.engine["lifecycle"])
    for source, seed in historical:
        traces.append(run(source, seed=seed).result.engine["lifecycle"])
    assert calls == [("flat", "native"), ("2", "native"), ("3", "native"), ("3", "native"),
                     ("2", "construction_steps_v1"), ("2", "cohort_v5")]
    assert all(trace == list(ENGINE_PHASES) for trace in traces)


def test_axis_laws_cannot_reach_simulator_graph_or_services():
    source = (ROOT / "deeprootgen/model/axis_laws.py").read_text()
    imported = {
        node.module or ""
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }
    assert not any(name.endswith(("root", "hgraph", "engine", "cohort", "execution")) for name in imported)
    for forbidden in ("RootSystemSimulation", "RootSystemGraph", "add_node", "add_edge", "open(", "write_"):
        assert forbidden not in source


@pytest.mark.parametrize("mode", MODES)
def test_all_off_matches_flat_baseline_exactly(mode):
    spec = v3(mode)
    native = run(flat_equivalent(spec))
    off = run(spec)
    assert tables(off) == tables(native)
    assert off.rng.bit_generator.state == native.rng.bit_generator.state
    assert off.result.metadata["effective_model_sha256"] == native.result.metadata["effective_model_sha256"]
    assert off.result.metadata["supplied_input_sha256"] != native.result.metadata["supplied_input_sha256"]


@pytest.mark.parametrize("record", [r for r in FIXTURE["records"] if r["contract"] in MODES])
def test_frozen_native_references_unchanged_through_engine(record):
    params = RootSimulationModel(**record["parameters"])
    sim = run(params, seed=record["seed"], tag=params.simulation_tag)
    nodes, edges = sim.G.as_df()
    assert table_hash(nodes) == record["nodes"] and table_hash(edges) == record["edges"]
    assert sim.rng.bit_generator.state == record["rng"]


@pytest.mark.parametrize("mode", MODES)
def test_curvature_off_on_off_in_same_file_recovers_baseline_exactly(mode, tmp_path):
    path = tmp_path / "native_features.json"
    path.write_text(json.dumps(v3(mode), indent=2))
    results = []
    for enabled in (False, True, False):
        spec = json.loads(path.read_text())
        spec["features"]["curvature"]["enabled"] = enabled
        path.write_text(json.dumps(spec, indent=2))
        results.append(run(path))
    off1, on, off2 = results
    assert tables(off1) == tables(off2)
    assert off1.result.metadata == off2.result.metadata
    assert tables(on) != tables(off1)
    assert len(on.G.nodes) > len(off1.G.nodes)
    # Every biology and placement draw is untouched by the replaced law.
    key = "native_rng_before_directions_sha256"
    assert on.result.engine[key] == off1.result.engine[key]
    assert on.result.metadata["effective_model_sha256"] != off1.result.metadata["effective_model_sha256"]
    assert tables(off1) == tables(run(flat_equivalent(v3(mode))))


@pytest.mark.parametrize("mode", MODES)
def test_curvature_keeps_sampled_biology_and_material(mode):
    off, on = run(v3(mode)), run(v3(mode, curvature=True))
    a, b = off.result.organ_table, on.result.organ_table
    keys = ["organ_id", "order", "parent_organ_id"]
    pd.testing.assert_frame_equal(a[keys], b[keys])
    np.testing.assert_allclose(b.length_cm, a.length_cm, rtol=1e-12, atol=0)
    np.testing.assert_allclose(b.mass_g, a.mass_g, rtol=1e-12, atol=0)
    assert set(b.loc[b.order.eq(1), "direction_law"]) == {"correlated_curvature"}
    assert set(b.loc[b.order.gt(1), "direction_law"]) == {"native"}
    # Native daughters keep their sampled intervals, diameters and classes.
    columns = ["organ_id", "order", "segment_rank", "diameter", "length", "root_type"]
    lateral_off = off.G.as_df()[0].query("order > 1")[columns].reset_index(drop=True)
    lateral_on = on.G.as_df()[0].query("order > 1")[columns].reset_index(drop=True)
    pd.testing.assert_frame_equal(lateral_off, lateral_on, check_exact=True)
    # Primary construction intervals survive as exact cuts with their diameter.
    for organ_off, organ_on in zip(off.organs[1], on.organs[1]):
        arcs_off = np.cumsum(organ_off.get_lengths())
        arcs_on = np.cumsum(organ_on.get_lengths())
        for arc, diameter in zip(arcs_off, organ_off.get_diameters()):
            index = int(np.argmin(np.abs(arcs_on - arc)))
            assert abs(arcs_on[index] - arc) < 1e-12
            assert organ_on.get_diameters()[index] == diameter


@pytest.mark.parametrize("mode", MODES)
def test_realized_axes_keep_corners_lengths_and_surface(mode):
    on = run(v3(mode, curvature=True))
    receipts = on.result.diagnostics["curvature"]
    assert [r["organ_id"] for r in receipts] == [int(o.segments[0].node_data.organ_id) for o in on.organs[1]]
    nodes = node_frame(on)
    for organ in on.organs[1]:
        xyz = organ.get_coordinates()
        parent = organ.parent_node.node_data
        previous = np.vstack([[parent.x, parent.y, parent.z], xyz[:-1]])
        np.testing.assert_allclose(np.linalg.norm(xyz - previous, axis=1), organ.get_lengths(), rtol=1e-9)
        assert xyz[:, 2].max() <= on.G.base_node.node_data.z + 1e-12
        stations = np.arange(0.0, organ.get_lengths().sum(), 0.7)[1:]
        arcs = np.cumsum(organ.get_lengths())
        assert all(np.min(np.abs(arcs - s)) <= 1e-9 for s in stations)
    # Daughters attach at retained construction cuts of the realized primary.
    for child in (o for group in list(on.organs.values())[1:] for o in group):
        assert child.parent_node in child.parent_node.organ.segments
        assert nodes.loc[child.segments[0].node_data.node_id, "parent_id"] == child.parent_node.node_data.node_id


def test_legacy_daughters_stay_rigid_relative_to_their_attachment():
    off, on = run(v3("legacy")), run(v3("legacy", curvature=True))
    checked = 0
    for a, b in zip(
        (o for order in sorted(off.organs) if order > 1 for o in off.organs[order]),
        (o for order in sorted(on.organs) if order > 1 for o in on.organs[order]),
    ):
        if a.validation_reorientations or b.validation_reorientations or a.invalid_root or b.invalid_root:
            continue
        rel_a = a.get_coordinates() - a.get_parent_origin()
        rel_b = b.get_coordinates() - b.get_parent_origin()
        np.testing.assert_allclose(rel_b, rel_a, rtol=0, atol=1e-9)
        checked += 1
    assert checked


def test_fichtl_daughters_use_the_realized_parent_tangent(monkeypatch):
    import deeprootgen.model.root as root_module

    recorded = []
    original = root_module.insertion_heading

    def spy(tangent, *args, **kwargs):
        recorded.append(np.asarray(tangent, float))
        return original(tangent, *args, **kwargs)

    monkeypatch.setattr(root_module, "insertion_heading", spy)
    on = run(v3("fichtl2024", curvature=True))
    nodes = node_frame(on)
    children = [o for o in on.organs[2] if not o.invalid_root]
    assert len(recorded) == len(children) + sum(not o.invalid_root for o in on.organs.get(3, []))
    for tangent, child in zip(recorded, children):
        attachment = child.parent_node.node_data
        incoming = nodes.loc[attachment.parent_id, ["x", "y", "z"]].to_numpy(float)
        edge = np.array([attachment.x, attachment.y, attachment.z]) - incoming
        np.testing.assert_allclose(tangent / np.linalg.norm(tangent), edge / np.linalg.norm(edge), atol=1e-9)
        first = child.get_coordinates()[0] - np.array([attachment.x, attachment.y, attachment.z])
        assert np.isclose(np.linalg.norm(first), child.segments[0].node_data.length, rtol=1e-9)


@pytest.mark.parametrize("curvature", [False, True])
def test_dormant_settings_never_change_model_output_or_draws(curvature):
    spec = v3("legacy", curvature=curvature)
    edited = copy.deepcopy(spec)
    edited["features"]["taper"]["settings"]["by_order"]["1"]["midpoint_diameter_fraction"] = 0.3
    edited["features"]["primary_origins"]["settings"]["radius_cm"] = 9.0
    edited["features"]["lengths"]["settings"]["by_order"]["3"]["mean"] = 2.5
    if not curvature:
        edited["features"]["curvature"]["settings"]["by_order"]["1"]["step_cm"] = 0.2
    a, b = run(spec), run(edited)
    assert tables(a) == tables(b)
    assert a.rng.bit_generator.state == b.rng.bit_generator.state
    assert a.result.metadata["effective_model_sha256"] == b.result.metadata["effective_model_sha256"]
    assert a.result.metadata["supplied_input_sha256"] != b.result.metadata["supplied_input_sha256"]
    assert b.result.resolved["features"]["inactive"]["primary_origins"]["radius_cm"] == 9.0


def test_simulation_tag_and_limits_do_not_change_model_identity():
    spec = v3("legacy", curvature=True)
    other = copy.deepcopy(spec)
    other["simulation_tag"] = "another-label"
    other["limits"] = {"max_organs": 500}
    a, b = run(spec), run(other, tag="another-label")
    assert a.result.metadata["effective_model_sha256"] == b.result.metadata["effective_model_sha256"]
    nodes_a, nodes_b = a.G.as_df()[0], b.G.as_df()[0]
    pd.testing.assert_frame_equal(nodes_a.drop(columns="simulation_tag"), nodes_b.drop(columns="simulation_tag"))


def mutated(path, value, *, curvature=True, mode="legacy"):
    spec = v3(mode, curvature=curvature)
    target = spec
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return spec


CURVE = ("features", "curvature", "settings", "by_order")


@pytest.mark.parametrize(
    "spec,match",
    [
        (mutated(("features", "cohort_maturity", "enabled"), True), "requires point taper"),
        (mutated(("features", "parent_diameter_cap", "enabled"), True), "requires point taper"),
        (mutated(CURVE + ("2",), dict(v3()["features"]["curvature"]["settings"]["by_order"]["1"])), "insertion_angle"),
        (mutated(CURVE + ("4",), dict(v3()["features"]["curvature"]["settings"]["by_order"]["1"])), "max_order"),
        (mutated(CURVE + ("1", "boundary"), None), "incomplete"),
        (mutated(CURVE + ("1", "correlation_length_cm"), 0.0), "correlation_length_cm"),
        (mutated(CURVE + ("1", "downward_drift_per_cm"), 2.0), "step_cm\\*downward_drift_per_cm"),
        (mutated(CURVE, {}), "at least one"),
        (mutated(("parameters", "no_root_zone"), -0.5), "no_root_zone"),
        (mutated(("features", "attachment_relocation", "enabled"), True, curvature=False), "attachment_relocation requires"),
        (mutated(CURVE + ("1", "initial_heading"), "origin_heading"), "origin_heading"),
    ],
)
def test_unsupported_or_incomplete_requests_fail_before_state_or_randomness(spec, match):
    sim = RootSystemSimulation(random_seed=spec["random_seed"])
    state = copy.deepcopy(sim.rng.bit_generator.state)
    with pytest.raises(ValueError, match=match):
        sim.run(spec)
    assert len(sim.G.nodes) == 1 and not sim.organs
    assert sim.rng.bit_generator.state == state
    assert sim.streams.issued == []


def test_failure_after_construction_publishes_no_result():
    spec = v3("legacy", curvature=True)
    spec["limits"] = {"max_nodes": 5}
    sim = RootSystemSimulation(random_seed=spec["random_seed"])
    with pytest.raises(ValueError, match="Node limit"):
        sim.run(spec)
    assert sim.result is None
    spec["limits"] = {"max_organs": 1}
    sim = RootSystemSimulation(random_seed=spec["random_seed"])
    with pytest.raises(ValueError, match="Organ limit"):
        sim.run(spec)
    assert sim.result is None


def test_explanation_matches_executed_laws(capsys, tmp_path):
    spec = v3("fichtl2024", curvature=True)
    description = explain_config(copy.deepcopy(spec))
    primary = description["laws"]["by_order"]["1"]["direction"]
    assert primary["law"] == "correlated_curvature" and primary["replaces"] == "native_scaffold_v1"
    assert primary["curvature_sd_rad_cm"] == 0.08 and primary["surface_z_cm"] == 0.0
    assert description["laws"]["by_order"]["2"]["direction"] == "native_fichtl_search_v1"
    assert "taper" in description["features"]["inactive"]
    assert description["features"]["active"]["curvature"]["by_order"]["1"]["initial_heading"] == "scaffold_chord"
    sim = run(spec)
    executed = dict(sim.result.resolved)
    assert executed.pop("hashes")["run_identity_sha256"] == sim.result.metadata["run_identity_sha256"]
    expected = dict(description)
    expected.pop("hashes")
    assert executed == expected
    config = tmp_path / "config.json"
    config.write_text(json.dumps(spec))
    assert main(["simulate", "--config", str(config), "--explain-config"]) == 0
    assert json.loads(capsys.readouterr().out) == dict(valid=True, **description)
    spec["features"]["parent_diameter_cap"]["enabled"] = True
    config.write_text(json.dumps(spec))
    with pytest.raises(SystemExit) as exit_info:
        main(["simulate", "--config", str(config), "--explain-config"])
    assert exit_info.value.code == 1
    verdict = json.loads(capsys.readouterr().out)
    assert verdict["valid"] is False and "point taper" in verdict["error"]


def test_api_and_cli_give_identical_canonical_results(tmp_path):
    spec = v3("legacy", curvature=True)
    sim = run(spec)
    manifest = simulate(copy.deepcopy(spec), tmp_path / "cli")
    nodes, edges = sim.G.as_df()
    pd.testing.assert_frame_equal(pd.read_csv(tmp_path / "cli/nodes.csv"), nodes, check_exact=False, rtol=1e-15)
    pd.testing.assert_frame_equal(pd.read_csv(tmp_path / "cli/edges.csv"), edges)
    for key, value in manifest["model_identity"].items():
        assert sim.result.metadata[key] == value
    resolved = json.loads((tmp_path / "cli/resolved_config.json").read_text())
    assert resolved["hashes"]["run_identity_sha256"] == sim.result.metadata["run_identity_sha256"]


def test_curvature_streams_are_keyed_by_seed_and_biological_identity():
    spec = v3("legacy", curvature=True)
    a, b = run(spec), run(spec)
    assert tables(a) == tables(b)
    assert a.streams.issued == [
        dict(namespace="feature.curvature.ou", version="native-correlated-curvature-v1", ids=[int(o.segments[0].node_data.organ_id)])
        for o in a.organs[1]
    ]
    reseeded = copy.deepcopy(spec)
    reseeded["random_seed"] = 7
    assert tables(run(reseeded, seed=7)) != tables(a)


def test_result_views_follow_capabilities_not_route_labels():
    sim = run(v3("legacy", curvature=True))
    assert sim.result.metadata["capabilities"] == dict(
        multiple_bases=False, tree_to_vine_map=False, crown_support_view=False
    )
    with pytest.raises(ValueError, match="crown support"):
        sim.result.cohort_tables(sim.G)
    nodes, _ = sim.result.observation_tables(sim.G)
    assert "vine_id" not in nodes
    relabelled = copy.deepcopy(sim.result)
    relabelled.metadata["execution"] = "cohort_v5"
    with pytest.raises(ValueError, match="crown support"):
        relabelled.cohort_tables(sim.G)


def test_materializer_keeps_construction_cuts_at_coinciding_corners():
    """A corner on a construction cut (attachment site) is one node, not two."""
    from types import SimpleNamespace as NS

    from deeprootgen.data_model import RootNodeModel
    from deeprootgen.model.materialize import AxisCurve, curved_axis

    stations = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    points = np.column_stack([stations, np.zeros(5), -np.abs(np.sin(stations))])
    arcs_points = np.cumsum(np.r_[0.0, np.linalg.norm(np.diff(points, axis=0), axis=1)])
    curve = AxisCurve(1, arcs_points, points, np.array([arcs_points[1], 2.5, arcs_points[4]]), {})
    nodes = []
    for arc, diameter in zip(curve.construction_arcs, (0.3, 0.2, 0.1)):
        xyz = curve.position([arc])[0]
        nodes.append(NS(node_data=RootNodeModel(x=xyz[0], y=xyz[1], z=xyz[2], diameter=diameter)))
    intervals = curved_axis(NS(segments=nodes), curve)
    cuts = np.cumsum([i.length for i in intervals])
    np.testing.assert_allclose(cuts, [arcs_points[1], arcs_points[2], 2.5, arcs_points[3], arcs_points[4]])
    assert [i.source is not None for i in intervals] == [True, False, True, False, True]
    assert [i.diameter for i in intervals] == [0.3, 0.2, 0.2, 0.1, 0.1]
    volume = sum(np.pi / 4 * i.diameter**2 * i.length for i in intervals)
    expected = np.pi / 4 * np.dot([0.3**2, 0.2**2, 0.1**2], np.diff(np.r_[0.0, curve.construction_arcs]))
    assert np.isclose(volume, expected, rtol=1e-14)


def test_replaced_law_keeps_biology_even_when_correction_draws_differ():
    """Review case: a curved primary passes where its scaffold failed.

    Its daughters then take validation draws they skipped when invalid, so the
    final native RNG state may differ; biology and placement draws may not.
    """
    spec = v3("legacy", curvature=True, sd=0.05)
    spec["random_seed"] = 33612
    spec["parameters"].update(
        max_order=2, outer_root_num=1, inner_root_num=2, min_primary_length=8.120105823629256,
        max_primary_length=11.587960468190118, min_sec_root_num=2, max_sec_root_num=5,
        growth_sec_root=0.1, min_sec_root_length=3.5613051453727023, max_sec_root_length=5.574852098636926,
        segments_per_root=6, length_reduction=0.7, root_vary=22.946285646680167, interbranch_distance=0.0078,
        gravitropism=0.0, no_root_zone=1.0, max_val_attempts=1,
    )
    law = spec["features"]["curvature"]["settings"]["by_order"]["1"]
    law.update(correlation_length_cm=1.0, downward_drift_per_cm=0.05)
    off_spec = copy.deepcopy(spec)
    off_spec["features"]["curvature"]["enabled"] = False
    off, on = run(off_spec, seed=33612), run(spec, seed=33612)
    assert [o.invalid_root for o in off.organs[1]] != [o.invalid_root for o in on.organs[1]]
    assert off.rng.bit_generator.state != on.rng.bit_generator.state
    key = "native_rng_before_directions_sha256"
    assert on.result.engine[key] == off.result.engine[key]
    a, b = off.result.organ_table, on.result.organ_table
    pd.testing.assert_frame_equal(a[["organ_id", "order", "parent_organ_id"]], b[["organ_id", "order", "parent_organ_id"]])
    np.testing.assert_allclose(b.length_cm, a.length_cm, rtol=1e-12, atol=0)
    assert "later correction draws can differ" in on.result.resolved["rng"]["native_schedule"]


def test_daughter_tangent_matches_the_incoming_piece_beside_a_retained_corner():
    """A nearby attachment keeps the corner and uses the tip-side tangent."""
    from types import SimpleNamespace as NS

    from deeprootgen.data_model import RootNodeModel
    from deeprootgen.model.materialize import AxisCurve, curved_axis

    stations = np.array([0.0, 1.0, 2.0])
    points = np.array([[0, 0, 0], [1, 0, 0], [1, 0, -1]], float)
    arc = 1.0 + 5e-10
    curve = AxisCurve(1, stations, points, np.array([arc, 2.0]), {})
    nodes = [
        NS(node_data=RootNodeModel(**dict(zip("xyz", curve.position([a])[0])), diameter=0.1))
        for a in curve.construction_arcs
    ]
    intervals = curved_axis(NS(segments=nodes), curve)
    assert len(intervals) == 3
    edge = np.array(intervals[1].xyz) - np.array(intervals[0].xyz)
    tangent = curve.tangent(arc)
    np.testing.assert_allclose(tangent / np.linalg.norm(tangent), edge / np.linalg.norm(edge), atol=1e-8)


@pytest.mark.parametrize(
    "name,value",
    [("correlation_length_cm", 1e-310), ("curvature_sd_rad_cm", 1e308), ("step_cm", 1e-300), ("step_cm", 1e9)],
)
def test_unrepresentable_curvature_settings_fail_before_any_state(name, value):
    spec = v3("legacy", curvature=True)
    spec["features"]["curvature"]["settings"]["by_order"]["1"][name] = value
    sim = RootSystemSimulation(random_seed=spec["random_seed"])
    state = copy.deepcopy(sim.rng.bit_generator.state)
    with pytest.raises(ValueError, match="representable"):
        sim.run(spec)
    assert len(sim.G.nodes) == 1 and not sim.organs and sim.rng.bit_generator.state == state


def test_cli_parameters_export_reloads_to_the_same_model(tmp_path):
    spec = v3("fichtl2024", curvature=True)
    manifest = simulate(copy.deepcopy(spec), tmp_path / "out")
    exported = json.loads((tmp_path / "out/parameters.json").read_text())
    resolved = resolve_config(exported)
    assert resolved.hashes["effective_model_sha256"] == manifest["model_identity"]["effective_model_sha256"]
    assert exported["simulation_tag"] == spec["simulation_tag"]
    assert "random_seed" not in exported["parameters"]


def test_effective_identity_ignores_inactive_mode_parameters_and_noop_controls():
    legacy = v3("legacy")
    edited = copy.deepcopy(legacy)
    edited["parameters"].update(fichtl_sigma=0.37, fichtl_theta2_deg=20.0)
    assert (
        resolve_config(legacy).hashes["effective_model_sha256"]
        == resolve_config(edited).hashes["effective_model_sha256"]
    )
    flat = flat_equivalent(legacy).model_dump()
    noop = dict(flat, research_primary_inclination_bias=0.0, research_primary_yaw_reverse_probability=0.0)
    assert (
        resolve_config(RootSimulationModel(**flat)).hashes["effective_model_sha256"]
        == resolve_config(RootSimulationModel(**noop)).hashes["effective_model_sha256"]
    )
    changed = copy.deepcopy(legacy)
    changed["parameters"]["gravitropism"] = 0.2
    assert (
        resolve_config(legacy).hashes["effective_model_sha256"]
        != resolve_config(changed).hashes["effective_model_sha256"]
    )


def test_flat_runs_require_a_fresh_simulator_and_physical_material():
    spec = json.loads((ROOT / "tests/fixtures/migration_inputs/synthetic_minimal.json").read_text())
    sim = RootSystemSimulation(random_seed=42)
    sim.run(RootSimulationModel(**spec))
    with pytest.raises(ValueError, match="fresh simulator"):
        sim.run(RootSimulationModel(**spec))
    negative = RootSimulationModel(**dict(spec, root_tissue_density=-0.05))
    fresh = RootSystemSimulation(random_seed=42)
    with pytest.raises(ValueError, match="Negative root material"):
        fresh.run(negative)
    assert fresh.result is None


@pytest.mark.parametrize("kind", ["flat", "v3-on", "construction_steps_v1", "cohort_v5", "fully-replaced"])
def test_one_writer_publishes_every_graph_once(kind, monkeypatch):
    from deeprootgen.model import hgraph

    published = []
    original = hgraph.publish_graph

    def spy(*args, **kwargs):
        graph = original(*args, **kwargs)
        published.append(graph)
        return graph

    monkeypatch.setattr(hgraph, "publish_graph", spy)
    if kind == "flat":
        sim = run(flat_equivalent(v3()))
    elif kind == "v3-on":
        sim = run(v3("fichtl2024", curvature=True))
    elif kind == "fully-replaced":
        from tests.test_native_features import PLANNED, spec as feature_spec

        sim = run(feature_spec(**PLANNED))
    else:
        record = next(r for r in FIXTURE["records"] if r["contract"] == kind)
        construction = (
            dict(kind="cohort", parameters=record["parameters"], older_count=record["older_count"],
                 later_count=record["later_count"])
            if kind == "cohort_v5" else dict(kind="native", parameters=record["parameters"])
        )
        sim = run(dict(schema_version=2, random_seed=record["seed"], trajectory=kind, construction=construction),
                  seed=record["seed"])
    assert len(published) == 1 and sim.G is published[0]
    assert all(node.G is sim.G for node in sim.G.nodes)
    registered = {id(n) for group in sim.organs.values() for o in group for n in o.segments}
    assert registered == {id(n) for n in sim.G.nodes if n.node_data.order > 0}


def test_leaf_law_modules_cannot_reach_simulator_writer_or_engine():
    for name in ("laws.py", "axis_laws.py", "native_features.py"):
        source = (ROOT / "deeprootgen/model" / name).read_text()
        imported = {
            node.module or ""
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom)
        }
        assert not any(m.endswith(("root", "hgraph", "engine", "views", "execution")) for m in imported), name
        for forbidden in ("RootSystemSimulation", "RootSystemGraph", "RootNode(", "publish_graph", "add_node",
                          "add_edge", "open(", ".write_"):
            assert forbidden not in source, (name, forbidden)


def _cohort_config(**updates):
    record = next(r for r in FIXTURE["records"] if r["contract"] == "cohort_v5")
    parameters = copy.deepcopy(record["parameters"])
    parameters.update(updates)
    return dict(schema_version=2, random_seed=record["seed"], trajectory="cohort_v5",
                construction=dict(kind="cohort", parameters=parameters, older_count=record["older_count"],
                                  later_count=record["later_count"])), record["seed"]


def test_initial_recorder_only_views_a_placed_native_scaffold():
    calls = []
    recorder = lambda sim, p: calls.append(all(np.isfinite([n.node_data.z for n in sim.G.nodes])))  # noqa: E731
    flat = RootSimulationModel(**json.loads((ROOT / "tests/fixtures/migration_inputs/synthetic_minimal.json").read_text()))
    with pytest.raises(ValueError, match="extended construction-step execution"):
        RootSystemSimulation(random_seed=42).run(flat, initial_recorder=recorder)
    cohort, seed = _cohort_config()
    native = dict(schema_version=2, random_seed=42, construction=dict(kind="native", parameters=flat.model_dump()))
    for config, config_seed in ((cohort, seed), (native, 42)):
        with pytest.raises(ValueError, match="requires construction-step execution"):
            RootSystemSimulation(random_seed=config_seed).run(config, initial_recorder=recorder)
    from tests.test_native_features import PLANNED, spec as feature_spec

    RootSystemSimulation(random_seed=42).run(feature_spec(**PLANNED), initial_recorder=recorder)
    run_spec = v3("fichtl2024", curvature=True)
    RootSystemSimulation(random_seed=42, simulation_tag="x").run(run_spec, initial_recorder=recorder)
    assert calls == [True, True]


@pytest.mark.parametrize(
    "reconcile,first,expected",
    # Messages observed from the pre-refactor runner for the same invented inputs.
    [
        (False, 10.000000001, "Organ 1: Interval 10 fails strict geometric length; reconciliation disabled"),
        (True, 10.000000001, "Organ 1: Interval 10 exceeds relative roundoff agreement guard"),
        (True, 10.4, "Explicit organ budget exhausted; no silent truncation"),
        (False, 10.4, "Explicit organ budget exhausted; no silent truncation"),
    ],
)
def test_cohort_error_precedence_matches_the_historical_runner(reconcile, first, expected):
    """Review case: organ 1 may fail reconciliation and its daughters exceed max_organs."""
    config, _ = _cohort_config(step_cm=1.0, max_organs=2, reconcile_length_metadata=reconcile)
    config["construction"].update(older_count=1, later_count=0)
    rule = config["construction"]["parameters"]["orders"]["1"]
    rule.update(length_cm=dict(mean=20.0, sd=0, min=20.0, max=20.0), daughter_probabilities=[0.0, 0.0, 1.0],
                curvature_sd_rad_cm=0.3, first_branch_cm=dict(mean=first, sd=0, min=first, max=first))
    config["random_seed"] = 1
    sim = RootSystemSimulation(random_seed=1)
    with pytest.raises(ValueError) as error:
        sim.run(config)
    assert str(error.value) == expected
    assert sim.result is None


def test_cohort_keeps_constructor_tag_and_consumes_birth_queues():
    config, seed = _cohort_config()
    sim = RootSystemSimulation(random_seed=seed, simulation_tag="constructor-tag")
    sim.run(config)
    assert sim.simulation_tag == "constructor-tag"
    assert all(not o.lateral_attachment_nodes for group in sim.organs.values() for o in group)
