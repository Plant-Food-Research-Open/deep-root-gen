"""Invented zone/count and RNG fixtures; paper means used only analytically."""

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from tests.public_checkpoint_reference import comparison_command, materialize_reference, subprocess_environment

from deeprootgen.archive.simulation import RootSystemSimulation
from deeprootgen.model import root as root_module
from deeprootgen.utils.branching import MAX_PARENT2_BRANCH_SITES, parent2_zone_sites
from deeprootgen.research.so4_controlled import construct_skeleton, replay_arm, validate_geometry
from deeprootgen.research.construction_step_replay import replay_construction_steps
from tests.test_construction_step_replay import parameters as step_parameters

ZONE = dict(basal_cm=7.8, apical_cm=16.4, spacing_cm=4.8)


def parameters(zone=None, **updates):
    values = dict(research_parent2_branch_zone_cm=zone, interbranch_distance=1., growth_sec_root=0.,
                  min_sec_root_num=2, max_sec_root_num=3,
                  research_current_length_cdfs_cm={
                      2: dict(lengths_cm=[80.], cumulative_probabilities=[1.]),
                      3: dict(lengths_cm=[2., 3.], cumulative_probabilities=[.4, 1.]),
                  })
    values.update(updates)
    return step_parameters(**values)


def branch_fixture(settings, order=2):
    organ = object.__new__(root_module.RootOrgan)
    organ.input_parameters = settings
    organ.parent_node = SimpleNamespace(node_data=SimpleNamespace(order=order - 1))
    organ.rng = np.random.default_rng(42)
    organ.current_length_diagnostics = dict(sampled_current_length_cm=80.)
    return organ


def prepare(organ):
    return organ._prepare_branch_nodes(np.array([.2]), np.array([80.]), np.array([[80., 0., 0.]]))


def test_short_equality_spacing_and_public_illustrative_counts():
    assert parent2_zone_sites(10., **ZONE) == []
    assert parent2_zone_sites(24.2, **ZONE) == [7.8]
    assert parent2_zone_sites(29., **ZONE) == [7.8, 12.6]
    sites = parent2_zone_sites(80., **ZONE)
    assert len(sites) == 12 and sites[0] == 7.8 and sites[-1] == 60.6
    assert len(parent2_zone_sites(np.nextafter(24.2, -np.inf), **ZONE)) == 0
    assert len(parent2_zone_sites(np.nextafter(24.2, np.inf), **ZONE)) == 1
    assert len(parent2_zone_sites(np.nextafter(29., -np.inf), **ZONE)) == 1
    assert len(parent2_zone_sites(np.nextafter(29., np.inf), **ZONE)) == 2
    assert parent2_zone_sites(.6, .1, .2, .1) == [.1, .2, .3, .4]
    assert len(parent2_zone_sites(np.nextafter(.6, -np.inf), .1, .2, .1)) == 3


@pytest.mark.parametrize("key", ["basal_cm", "apical_cm", "spacing_cm"])
@pytest.mark.parametrize("value", [True, np.bool_(True), 0., -1., np.nan, np.inf, "4.8"])
def test_invalid_zone_scalars_rejected_by_helper_and_schema(key, value):
    zone = dict(ZONE, **{key: value})
    with pytest.raises(ValueError):
        parent2_zone_sites(80., **zone)
    with pytest.raises(ValueError):
        parameters(zone)


@pytest.mark.parametrize("length", [True, 0., -1., np.nan, np.inf, "80"])
def test_invalid_current_lengths_rejected(length):
    with pytest.raises(ValueError):
        parent2_zone_sites(length, **ZONE)


def test_allocation_limit_and_unrepresentable_sites_reject_without_truncation():
    assert len(parent2_zone_sites(10001., 1., 1., 1.)) == MAX_PARENT2_BRANCH_SITES
    with pytest.raises(ValueError, match="allocation limit"):
        parent2_zone_sites(10002., 1., 1., 1.)
    with pytest.raises(ValueError, match="representable"):
        parent2_zone_sites(2., 1., .9999999999999999, 1e-16)


@pytest.mark.parametrize("zero_cap", [False, True])
def test_original_count_spacing_rng_schedule_preserved_before_zone_override(monkeypatch, zero_cap):
    overrides = dict(min_sec_root_num=0, max_sec_root_num=0) if zero_cap else {}
    old, new = branch_fixture(parameters(**overrides)), branch_fixture(parameters(ZONE, **overrides))
    sampler, calls = root_module.sample_branch_sites, []

    def observe(**kwargs):
        sites = sampler(**kwargs)
        calls.append((kwargs["max_branches"], sites.copy(), copy.deepcopy(kwargs["rng"].bit_generator.state)))
        return sites

    monkeypatch.setattr(root_module, "sample_branch_sites", observe)
    prepare(old)
    old_calls = copy.deepcopy(calls)
    calls.clear()
    diameters, lengths, coordinates, indices = prepare(new)
    assert calls == old_calls
    assert old.rng.bit_generator.state == new.rng.bit_generator.state
    assert len(calls) == (0 if zero_cap else 1)
    receipt = new.parent2_zone_diagnostics
    assert receipt["original_requested_count"] == (0 if zero_cap else 2)
    assert receipt["original_retained_count"] == (0 if zero_cap else 2)
    assert receipt["count"] == len(indices) == 12
    np.testing.assert_allclose(coordinates[indices, 0], receipt["sites_cm"], rtol=0, atol=1e-8)
    assert lengths.sum() == pytest.approx(80., rel=0, abs=1e-8)
    assert np.all(diameters == .2)


def test_zone_does_not_override_other_orders():
    original, active = branch_fixture(parameters(), order=1), branch_fixture(parameters(ZONE), order=1)
    for first, second in zip(prepare(original), prepare(active)):
        np.testing.assert_array_equal(first, second)
    assert original.rng.bit_generator.state == active.rng.bit_generator.state
    assert not hasattr(active, "parent2_zone_diagnostics")


def test_realized_graph_birth_counts_arc_sites_and_repeatability():
    p = parameters(ZONE)
    first, second = construct_skeleton(p, 42), construct_skeleton(p, 42)
    assert first.payload == second.payload and first.sha256 == second.sha256
    nodes, edges = pd.DataFrame(first.payload["nodes"]), pd.DataFrame(first.payload["edges"])
    validate_geometry(nodes, edges)
    for organ in first.payload["organs"]:
        if organ["order"] != 2:
            continue
        report = organ["parent2_branch_zone"]
        assert report["sites_cm"] == parent2_zone_sites(80., **ZONE)
        children = [child for child in first.payload["organs"] if child["order"] == 3 and child["parent_id"] in organ["node_ids"]]
        assert len(children) == report["count"] == 12
        np.testing.assert_allclose([child["attachment_arc_cm"] for child in children], report["sites_cm"], rtol=0, atol=1e-8)


@pytest.mark.parametrize("updates", [{"research_current_length_grid": None}, {"max_order": 2},
                                     {"random_seed": None}, {"research_current_length_cdfs_cm": None}, {"tropism_mode": "legacy"}])
def test_zone_scope_rejected(updates):
    with pytest.raises(ValueError):
        parameters(ZONE, **updates)


def test_none_serialization_canonical_and_native_legacy_regressions():
    p = parameters()
    implicit = p.model_dump()
    implicit.pop("research_parent2_branch_zone_cm")
    first, second = construct_skeleton(implicit, 42), construct_skeleton(p, 42)
    assert first.payload == second.payload and first.sha256 == second.sha256
    assert "research_parent2_branch_zone_cm" not in first.payload["parameters"]
    assert not any("parent2_branch_zone" in organ for organ in first.payload["organs"])
    one, two = replay_construction_steps(first, "D", implicit, "minimum_angle_projection"), replay_construction_steps(second, "D", p.model_dump(), "minimum_angle_projection")
    for key in ("nodes", "edges", "proposals"):
        pd.testing.assert_frame_equal(one[key], two[key], check_exact=True)
    assert one["diagnostics"] == two["diagnostics"]
    legacy = parameters(research_current_length_grid=None)
    raw = legacy.model_dump()
    raw.pop("research_parent2_branch_zone_cm")
    a, b = construct_skeleton(raw, 42), construct_skeleton(legacy, 42)
    for arm in "ABCD":
        for key in ("nodes", "edges", "proposals"):
            pd.testing.assert_frame_equal(replay_arm(a, arm, raw, "minimum_angle_projection")[key],
                                          replay_arm(b, arm, legacy.model_dump(), "minimum_angle_projection")[key], check_exact=True)


NATIVE_PARITY_SCRIPT = '''
import json,sys
import deeprootgen.model.root as module
from deeprootgen.data_model import RootSimulationModel
values=json.loads(sys.stdin.read());outputs={};fields={}
for label,extra in [('omitted',{}),('explicit_none',{'research_parent2_branch_zone_cm':None})]:
    config={**values,**extra};p=RootSimulationModel(**config)
    if 'research_parent2_branch_zone_cm' in RootSimulationModel.model_fields:
        fields[label]='research_parent2_branch_zone_cm' in p.model_fields_set
    sim=ComparisonSimulation(random_seed=p.random_seed);sim.run(p)
    nodes,edges=sim.G.as_df()
    outputs[label]={'nodes':nodes.to_dict('records'),'edges':edges.to_dict('records'),'rng':sim.rng.bit_generator.state}
print(json.dumps({'loaded_root_module':module.__file__,'outputs':outputs,'explicit_field_presence':fields},sort_keys=True,allow_nan=False))
'''


@pytest.mark.parametrize("mode", ["legacy", "fichtl2024"])
def test_native_omitted_and_none_exact_prechange_subprocess_parity(mode, tmp_path):
    """Always compare exact native output against self-contained public source."""
    current = Path(__file__).parents[1]
    old = materialize_reference(current, tmp_path, 'parent2_branch_zone')
    config = json.loads((current / "tests/fixtures/migration_inputs/synthetic_minimal.json").read_text())
    config.update(max_order=2, min_sec_root_num=1, max_sec_root_num=2,
                  min_sec_root_length=2., max_sec_root_length=3., interbranch_distance=2.,
                  gravitropism=0., tropism_mode=mode, soil_surface_z_cm=20.)
    if mode == "fichtl2024":
        config.update(fichtl_probability_down=.5, fichtl_sigma=.1,
                      fichtl_trials_type2=1., fichtl_trials_type3=1.,
                      fichtl_theta2_deg=50., fichtl_theta2_sd_deg=5.,
                      fichtl_theta3_deg=50., fichtl_theta3_sd_deg=5.)
    assert "research_parent2_branch_zone_cm" not in config
    results, hashes = {}, {}
    for label, source in (("prechange", old), ("current", current)):
        environment = subprocess_environment(source)
        completed = subprocess.run(comparison_command(NATIVE_PARITY_SCRIPT, current=label == "current"), input=json.dumps(config),
                                   text=True, capture_output=True, check=True, timeout=45, env=environment, cwd=source)
        results[label] = json.loads(completed.stdout)
        assert Path(results[label]["loaded_root_module"]).resolve() == (source / "deeprootgen/model/root.py").resolve()
        outputs = results[label]["outputs"]
        assert outputs["omitted"] == outputs["explicit_none"]
        hashes[label] = {path: hashlib.sha256((source / path).read_bytes()).hexdigest() for path in (
            "deeprootgen/model/root.py", "deeprootgen/data_model/simulation_data_models.py", "deeprootgen/utils/branching.py",
            "deeprootgen/model/hgraph.py", "deeprootgen/utils/current_length.py", "deeprootgen/utils/tropism.py", "deeprootgen/utils/primary_orientation.py",
        )}
    assert results["current"]["explicit_field_presence"] == {"omitted": False, "explicit_none": True}
    assert results["prechange"]["outputs"] == results["current"]["outputs"]

    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

    digests = {label: hashlib.sha256(canonical(result["outputs"])).hexdigest() for label, result in results.items()}
    assert digests["prechange"] == digests["current"]
    destination = Path(os.environ.get("DRG_PUBLIC_NATIVE_PARITY_DIR", str(tmp_path)))
    destination.mkdir(parents=True, exist_ok=True)
    (destination / f"native_parity_{mode}.json").write_text(json.dumps(dict(
        kind="invented_native_exact_prechange_parity", mode=mode, source_sha256=hashes, output_sha256=digests,
        source_roots=dict(prechange=str(old), current=str(current)),
        config=config, explicit_field_presence=results["current"]["explicit_field_presence"], exact_nodes_edges_rng=True,
    ), indent=2) + "\n")


@pytest.mark.parametrize("method", ["run", "apply_fichtl_tropism"])
def test_unvalidated_active_zone_cannot_bypass_native_routing_by_dropping_grid(method):
    invalid = parameters(ZONE).model_copy(update={"research_current_length_grid": None})
    sim = RootSystemSimulation(random_seed=42)
    before, state = sim.G.as_df(), copy.deepcopy(sim.rng.bit_generator.state)
    with pytest.raises(ValueError, match="named controlled replay"):
        getattr(sim, method)(invalid)
    for expected, actual in zip(before, sim.G.as_df()):
        pd.testing.assert_frame_equal(expected, actual, check_exact=True)
    assert state == sim.rng.bit_generator.state


def test_active_zone_cannot_be_ignored_by_legacy_replay_without_grid_flag():
    p = parameters(research_current_length_grid=None)
    initial = construct_skeleton(p, 42)
    invalid = {**p.model_dump(), "research_parent2_branch_zone_cm": ZONE}
    with pytest.raises(ValueError, match="not legacy replay_arm"):
        replay_arm(initial, "D", invalid, "minimum_angle_projection")
