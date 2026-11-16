"""Invented direction coefficients only; no observed configurations or trials."""

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import RootSimulationModel
from deeprootgen.model import RootSystemSimulation
from deeprootgen.model import root as root_module
from deeprootgen.research import construction_step_replay as canonical
from deeprootgen.research import so4_controlled as controlled
from deeprootgen.utils import tropism
from tests.test_construction_step_replay import parameters as grid_parameters, refine_graph, resign
from tests.test_parent2_branch_zone import parameters as zone_parameters, ZONE

POLICY = "minimum_angle_projection"


def parameters(mapping=None, grid=True, **updates):
    return grid_parameters(active=grid, research_fichtl_sigma_by_order=mapping, **updates)


def settings(mapping=None):
    return parameters(mapping).model_dump()


def test_alpha_length_scaling_zero_draws_and_per_order_resolution():
    first, second = np.random.default_rng(42), np.random.default_rng(42)
    alpha1 = tropism.sample_fichtl_alpha(1., .2, 7, first)
    alpha4 = tropism.sample_fichtl_alpha(4., .2, 7, second)
    np.testing.assert_array_equal(alpha4, 2. * alpha1)
    assert first.bit_generator.state == second.bit_generator.state
    zero, nonzero = np.random.default_rng(42), np.random.default_rng(42)
    np.testing.assert_array_equal(tropism.sample_fichtl_alpha(4., 0., 7, zero), np.zeros(7))
    tropism.sample_fichtl_alpha(4., .2, 7, nonzero)
    assert zero.bit_generator.state == nonzero.bit_generator.state
    assert tropism.resolve_fichtl_sigma(.2, 2, {3: .4})[0] == .2
    assert tropism.resolve_fichtl_sigma(.2, 3, {"3": .4})[0] == .4
    assert tropism.resolve_fichtl_sigma(.2, 2, {3: .4})[1]["sigma_source"] == "global_fallback"


def test_controlled_actual_alpha_uses_resolved_coefficient_and_has_same_draw_schedule():
    baseline = settings()
    changed = settings({2: .4})
    first, second = np.random.default_rng(42), np.random.default_rng(42)
    _, old = controlled.fichtl_proposal(np.eye(3), 4., 2, baseline, first)
    heading, new = controlled.fichtl_proposal(np.eye(3), 4., 2, changed, second)
    np.testing.assert_array_equal(new["alpha"], np.array(old["alpha"]) * 4.)
    assert new["beta"] == old["beta"] and new["downward"] == old["downward"]
    assert first.bit_generator.state == second.bit_generator.state
    assert np.linalg.norm(heading) == pytest.approx(1., abs=1e-12)
    assert new["effective_sigma_rad_per_sqrt_cm"] == .4
    assert new["sigma_operator_version"] == tropism.SIGMA_OPERATOR_VERSION
    for order in (2, 3):
        a, b = np.random.default_rng(42), np.random.default_rng(42)
        first, old = controlled.fichtl_proposal(np.eye(3), 4., order, baseline, a)
        second, same = controlled.fichtl_proposal(np.eye(3), 4., order, settings({2: .1, 3: .1}), b)
        np.testing.assert_array_equal(first, second)
        assert old["innovations_sha256"] == same["innovations_sha256"]
        assert a.bit_generator.state == b.bit_generator.state
    # Equal upstream frame/draws: a sigma2-only override cannot affect order3.
    first, a = controlled.fichtl_proposal(np.eye(3), 4., 3, baseline, np.random.default_rng(42))
    second, b = controlled.fichtl_proposal(np.eye(3), 4., 3, changed, np.random.default_rng(42))
    np.testing.assert_array_equal(first, second)
    assert a["innovations_sha256"] == b["innovations_sha256"]


def test_equal_global_zero_preserves_even_signed_zero_innovations():
    base = {**settings(), "fichtl_sigma": 0.}
    active = {**base, "research_fichtl_sigma_by_order": {2: -0., 3: 0.}}
    for order in (2, 3):
        _, old = controlled.fichtl_proposal(np.eye(3), 4., order, base, np.random.default_rng(42))
        _, new = controlled.fichtl_proposal(np.eye(3), 4., order, active, np.random.default_rng(42))
        assert old["innovations_sha256"] == new["innovations_sha256"]


@pytest.mark.parametrize("mapping", [{}, {1: .1}, {4: .1}, {2.: .1}, {True: .1},
                                     {2: True}, {2: np.bool_(True)}, {2: -.1}, {2: np.nan}, {3: np.inf},
                                     {2: ".1"}, {2: [0.1]}, {2: .1, "2": .2}])
def test_invalid_maps_rejected_before_schema_coercion(mapping):
    with pytest.raises(ValueError):
        tropism.validate_fichtl_sigma_by_order(mapping)
    with pytest.raises(ValueError):
        parameters(mapping)


def test_json_keys_zero_selected_orders_and_unsupported_scope():
    assert parameters({"2": 0., "3": .3}).research_fichtl_sigma_by_order == {2: 0., 3: .3}
    with pytest.raises(ValueError, match="fichtl2024"):
        parameters({2: .1}, grid=False, tropism_mode="legacy", research_base_origin_x_cm=None,
                   research_base_origin_y_cm=None, research_base_depth_cm=None)
    with pytest.raises(ValueError, match="unsupported"):
        tropism.validate_fichtl_sigma_by_order({3: .1}, max_order=2)


@pytest.mark.parametrize("arm", ["C", "D"])
def test_graph_segment_replay_maps_and_equal_global_geometry_innovations(arm):
    p = parameters(grid=False)
    initial = controlled.construct_skeleton(p, 42)
    baseline = controlled.replay_arm(initial, arm, p.model_dump(), POLICY)
    same = controlled.replay_arm(initial, arm, settings({2: .1, 3: .1}) | {"research_current_length_grid": None}, POLICY)
    for key in ("nodes", "edges", "proposals"):
        pd.testing.assert_frame_equal(baseline[key], same[key], check_exact=True)
    assert [s.get("innovations_sha256") for s in baseline["diagnostics"]["segments"]] == [
        s.get("innovations_sha256") for s in same["diagnostics"]["segments"]]
    for unsupported in ("A", "B"):
        with pytest.raises(ValueError, match="Fichtl continuation"):
            controlled.replay_arm(initial, unsupported, {**p.model_dump(), "research_fichtl_sigma_by_order": {3: .2}}, POLICY)


def test_canonical_sigma3_leaves_order2_exact_and_first_steps_bypass_sigma():
    p = parameters()
    initial = controlled.construct_skeleton(p, 42)
    baseline = canonical.replay_construction_steps(initial, "D", p.model_dump(), POLICY)
    changed = canonical.replay_construction_steps(initial, "D", settings({3: .4}), POLICY)
    again = canonical.replay_construction_steps(initial, "D", settings({"3": .4}), POLICY)
    old = [s for s in baseline["diagnostics"]["construction_steps"] if s["order"] == 2]
    new = [s for s in changed["diagnostics"]["construction_steps"] if s["order"] == 2]
    for a, b in zip(old, new):
        for key in a:
            assert a[key] == b[key]
    pd.testing.assert_frame_equal(changed["nodes"], again["nodes"], check_exact=True)
    assert changed["diagnostics"]["invariant_hashes"] == baseline["diagnostics"]["invariant_hashes"]
    assert any(a["accepted_heading"] != b["accepted_heading"] for a, b in zip(
        baseline["diagnostics"]["construction_steps"], changed["diagnostics"]["construction_steps"]) if a["order"] == 3)
    for a, b in zip(baseline["diagnostics"]["construction_steps"], changed["diagnostics"]["construction_steps"]):
        if a["step_index"] == 0:
            assert a == b and "effective_sigma_rad_per_sqrt_cm" not in b
    single = parameters(segments_per_root=1)
    skeleton = controlled.construct_skeleton(single, 42)
    a = canonical.replay_construction_steps(skeleton, "D", single.model_dump(), POLICY)
    b = canonical.replay_construction_steps(skeleton, "D", {**single.model_dump(), "research_fichtl_sigma_by_order": {2: 0., 3: .8}}, POLICY)
    pd.testing.assert_frame_equal(a["nodes"], b["nodes"], check_exact=True)


def test_native_uses_same_resolver_and_alpha_and_preserves_rng(monkeypatch):
    outputs, states, diagnostics, calls = [], [], [], []
    original = root_module.sample_heading

    def observed(*args, **kwargs):
        calls.append(args[3])
        return original(*args, **kwargs)

    monkeypatch.setattr(root_module, "sample_heading", observed)
    for mapping in (None, {2: .1, 3: .1}, {3: .4}):
        calls.clear()
        sim = RootSystemSimulation(random_seed=42)
        sim.run(parameters(mapping, grid=False))
        outputs.append(sim.G.as_df())
        states.append(copy.deepcopy(sim.rng.bit_generator.state))
        diagnostics.append(copy.deepcopy(sim.tropism_diagnostics))
        nodes = outputs[-1][0]
        n2 = int(nodes.order.eq(2).sum())
        assert calls[:n2] == [.1] * n2
        assert calls[n2:] == [(.4 if mapping == {3: .4} else .1)] * int(nodes.order.eq(3).sum())
        controlled.validate_geometry(*outputs[-1], 20.)
    for a, b in zip(outputs[0], outputs[1]):
        pd.testing.assert_frame_equal(a, b, check_exact=True)
    assert states[0] == states[1] == states[2]
    primary2 = outputs[0][0].order.le(2)
    pd.testing.assert_frame_equal(outputs[0][0].loc[primary2], outputs[2][0].loc[primary2], check_exact=True)
    assert "sigma_source" not in diagnostics[0]["by_order"]["2"]
    assert diagnostics[2]["by_order"]["3"]["effective_sigma_rad_per_sqrt_cm"] == .4


def test_zero_native_fallback_and_canonical_common_projection_keep_draws(monkeypatch):
    first, second = np.random.default_rng(42), np.random.default_rng(42)
    sigma, _ = tropism.resolve_fichtl_sigma(.1, 2, {2: 0.})
    actual, receipt = tropism.sample_heading([0., 0., 1.], 1., .5, sigma, 1., first, start_z=20., surface_z=20.)
    tropism.sample_heading([0., 0., 1.], 1., .5, 0., 1., second, start_z=20., surface_z=20.)
    np.testing.assert_array_equal(actual, [0., 0., -1.])
    assert receipt["surface_fallback"] and first.bit_generator.state == second.bit_generator.state
    from tests.test_construction_step_replay import operator_graph
    monkeypatch.setattr(canonical, "insertion_heading", lambda *args: np.array([0., 0., 1.]))
    nodes, organ, partition = operator_graph([2., 4., 8., 10.])
    records, _, _ = canonical._replay_organ(organ, partition, nodes, settings({2: 0.}), 42, POLICY, 20., None)
    assert len(records) == 2 and all(r["boundary_intervention"] for r in records)
    assert records[1]["effective_sigma_rad_per_sqrt_cm"] == 0.
    assert nodes.z.max() <= 20.
    controlled.validate_geometry(nodes.reset_index(drop=True), controlled.derived_edges(nodes.reset_index(drop=True)), 20.)


def test_combined_zone_grid_sigma_graph_and_added_cut_invariance():
    p = zone_parameters(ZONE)
    initial = controlled.construct_skeleton(p, 42)
    active = {**p.model_dump(), "research_fichtl_sigma_by_order": {2: .04, 3: .3}}
    old = pd.DataFrame(initial.payload["nodes"]).set_index("node_id")
    daughter = next(o for o in initial.payload["organs"] if o["order"] == 3)
    refined = refine_graph(initial, daughter["parent_id"], float(old.loc[daughter["parent_id"], "length"]) / 4.)
    # Preserve zone provenance alongside the unchanged construction partitions.
    zones = {o["organ_id"]: o.get("parent2_branch_zone") for o in initial.payload["organs"]}
    for organ in refined.payload["organs"]:
        if zones[organ["organ_id"]] is not None:
            organ["parent2_branch_zone"] = copy.deepcopy(zones[organ["organ_id"]])
    refined = resign(refined)
    first = canonical.replay_construction_steps(initial, "D", active, POLICY)
    second = canonical.replay_construction_steps(refined, "D", active, POLICY)
    for a, b in zip(first["diagnostics"]["construction_steps"], second["diagnostics"]["construction_steps"]):
        assert a.get("innovations_sha256") == b.get("innovations_sha256")
        np.testing.assert_allclose(a["accepted_heading"], b["accepted_heading"], rtol=0, atol=1e-8)
        np.testing.assert_allclose(a["accepted_endpoint"], b["accepted_endpoint"], rtol=0, atol=1e-8)
    for result in (first, second):
        controlled.validate_geometry(result["nodes"], result["edges"], 20.)
    assert first["diagnostics"]["invariant_hashes"] == controlled.invariant_hashes(pd.DataFrame(initial.payload["nodes"]))


def test_legacy_mode_unvalidated_active_map_rejected_before_mutation():
    invalid = parameters({2: .1}, grid=False).model_copy(update={"tropism_mode": "legacy"})
    sim = RootSystemSimulation(random_seed=42)
    before, state = sim.G.as_df(), copy.deepcopy(sim.rng.bit_generator.state)
    with pytest.raises(ValueError, match="fichtl2024"):
        sim.run(invalid)
    for a, b in zip(before, sim.G.as_df()):
        pd.testing.assert_frame_equal(a, b, check_exact=True)
    assert state == sim.rng.bit_generator.state


NONE_PARITY_SCRIPT = '''
import json,sys
import deeprootgen.model.root as module
from deeprootgen.data_model import RootSimulationModel
from deeprootgen.research.so4_controlled import construct_skeleton,replay_arm
from deeprootgen.research.construction_step_replay import replay_construction_steps
configs=json.loads(sys.stdin.read());outputs={};presence={}
for label,extra in [('omitted',{}),('explicit_none',{'research_fichtl_sigma_by_order':None})]:
    records={};presence[label]={}
    for name,values in configs.items():
        p=RootSimulationModel(**{**values,**extra})
        if 'research_fichtl_sigma_by_order' in RootSimulationModel.model_fields:
            presence[label][name]='research_fichtl_sigma_by_order' in p.model_fields_set
        if name.startswith('native'):
            sim=module.RootSystemSimulation(random_seed=p.random_seed);sim.run(p)
            nodes,edges=sim.G.as_df()
            records[name]={'nodes_csv':nodes.to_csv(index=False),'edges_csv':edges.to_csv(index=False),'rng':sim.rng.bit_generator.state,'diagnostics':getattr(sim,'tropism_diagnostics',None)}
        else:
            saved=construct_skeleton(p,p.random_seed)
            records[name]={'initial':saved.payload,'initial_sha256':saved.sha256,'arms':{}}
            for arm in ('D' if name=='canonical' else 'ABCD'):
                result=(replay_construction_steps if name=='canonical' else replay_arm)(saved,arm,p.model_dump(),'minimum_angle_projection')
                records[name]['arms'][arm]={key:result[key].to_csv(index=False) for key in ['nodes','edges','proposals']}
                records[name]['arms'][arm]['diagnostics']=result['diagnostics']
    outputs[label]=records
print(json.dumps({'loaded_root':module.__file__,'outputs':outputs,'presence':presence},sort_keys=True,allow_nan=False))
'''


def test_none_prechange_subprocess_serialization_diagnostics_geometry_rng_parity(tmp_path):
    current = Path(__file__).parents[1]
    old = Path(os.environ.get("DRG_SIGMA_PRECHANGE_SOURCE", "/tmp/drg-order-sigma-public/preimplementation/source"))
    if not (old / "deeprootgen/model/root.py").is_file():
        pytest.skip("Qualified prechange public source snapshot unavailable")
    base = json.loads((current / "examples/synthetic_minimal.json").read_text())
    base.update(max_order=3, min_sec_root_num=1, max_sec_root_num=2,
                min_sec_root_length=2., max_sec_root_length=3., interbranch_distance=2.,
                gravitropism=0., soil_surface_z_cm=20.)
    native_fichtl = {**base, "tropism_mode": "fichtl2024", "fichtl_sigma": .1,
                     "fichtl_probability_down": .5, "fichtl_trials_type2": 1., "fichtl_trials_type3": 1.,
                     "fichtl_theta2_deg": 50., "fichtl_theta3_deg": 50.,
                     "fichtl_theta2_sd_deg": 5., "fichtl_theta3_sd_deg": 5.}
    configs = dict(native_legacy={**base, "tropism_mode": "legacy"}, native_fichtl=native_fichtl,
                   graph=parameters(grid=False).model_dump(), canonical=parameters().model_dump())
    for config in configs.values():
        config.pop("research_fichtl_sigma_by_order", None)
        assert "research_fichtl_sigma_by_order" not in config
    overlay = next(path for path in sys.path if path.endswith("/locked-overlay"))
    results, hashes = {}, {}
    for name, source in (("prechange", old), ("current", current)):
        env = {**os.environ, "PYTHONPATH": overlay + os.pathsep + str(source), "PYTHONDONTWRITEBYTECODE": "1"}
        completed = subprocess.run([sys.executable, "-c", NONE_PARITY_SCRIPT], input=json.dumps(configs),
                                   text=True, capture_output=True, check=True, timeout=60, cwd=source, env=env)
        results[name] = json.loads(completed.stdout)
        assert Path(results[name]["loaded_root"]).resolve() == (source / "deeprootgen/model/root.py").resolve()
        assert results[name]["outputs"]["omitted"] == results[name]["outputs"]["explicit_none"]
        hashes[name] = {path: hashlib.sha256((source / path).read_bytes()).hexdigest() for path in (
            "deeprootgen/model/root.py", "deeprootgen/data_model/simulation_data_models.py", "deeprootgen/utils/tropism.py",
            "deeprootgen/research/so4_controlled.py", "deeprootgen/research/construction_step_replay.py")}
    assert results["prechange"]["outputs"] == results["current"]["outputs"]
    for label, present in (("omitted", False), ("explicit_none", True)):
        assert results["current"]["presence"][label] == {name: present for name in configs}

    def output_digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

    digests = {name: output_digest(result["outputs"]) for name, result in results.items()}
    assert digests["prechange"] == digests["current"]
    destination = Path(os.environ.get("DRG_SIGMA_PARITY_DIR", str(tmp_path)))
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "none_prechange_parity.json").write_text(json.dumps(dict(
        kind="invented_native_and_controlled_none_exact_prechange_parity", source_sha256=hashes,
        output_sha256=digests, exact_nodes_edges_proposals_diagnostics_initial_serialization_rng=True,
        source_roots=dict(prechange=str(old), current=str(current)),
        explicit_field_presence=results["current"]["presence"],
    ), indent=2) + "\n")
