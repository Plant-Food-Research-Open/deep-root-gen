"""Counterexamples from the merge review, using invented data only."""

import copy
from types import SimpleNamespace as NS

import numpy as np
import pytest

from deeprootgen.data_model import RootNodeModel
from deeprootgen.archive.simulation import RootSystemSimulation
from deeprootgen.model.materialize import AxisCurve, curved_axis, merge_cuts, taper_interval_diameters
from tests.test_native_features import BASE, organs, run, spec, tables


@pytest.mark.parametrize("mode", ["legacy", "fichtl2024"])
def test_parent_only_taper_preserves_untapered_descendant_birth_material(mode):
    baseline = run(spec(mode))
    value = spec(mode, taper=dict(by_order={"1": BASE["features"]["taper"]["settings"]["by_order"]["1"]}))
    tapered = run(value)
    assert tapered.result.metadata["effective_model_sha256"] != baseline.result.metadata["effective_model_sha256"]
    checked = 0
    for a, b in zip(organs(baseline), organs(tapered)):
        if a.segments[0].node_data.order > 1:
            np.testing.assert_array_equal(a.get_lengths(), b.get_lengths())
            np.testing.assert_array_equal(a.get_diameters(), b.get_diameters())
            checked += 1
    assert checked


@pytest.mark.parametrize("delta", [0.0, 5e-10, 2e-9])
def test_near_attachment_never_discards_a_real_curve_corner(delta):
    stations = np.array([0.0, 0.001, 0.002])
    points = np.array([[0., 0., 0.], [0.001, 0., 0.], [0.001, 0., -0.001]])
    arcs = np.array([0.001 + delta, 0.002])
    curve = AxisCurve(1, stations, points, arcs, {})
    nodes = [NS(node_data=RootNodeModel(**dict(zip("xyz", curve.position([a])[0])), diameter=.1)) for a in arcs]
    emitted = curved_axis(NS(segments=nodes), curve)
    xyz = np.array([points[0], *[x.xyz for x in emitted]])
    np.testing.assert_allclose(np.linalg.norm(np.diff(xyz, axis=0), axis=1), [x.length for x in emitted], rtol=1e-9)
    assert any(x.source is nodes[0] for x in emitted)
    tangent = curve.tangent(arcs[0])
    np.testing.assert_array_equal(tangent, points[1] - points[0] if delta == 0 else points[2] - points[1])


def test_tiny_taper_preserves_midpoint_and_analytic_mass():
    length, base, tip, mid = 1e-10, .2, .01, .9
    cuts = merge_cuts([0., length], [[], [length / 2]], 1e-9)
    assert len(cuts) == 3
    diameters = taper_interval_diameters(cuts, length, base, tip, mid)
    middle = tip + mid * (base - tip)
    volume = np.pi / 4 * np.dot(np.diff(cuts), diameters**2)
    analytic = np.pi / 12 * length / 2 * (base**2 + base * middle + 2 * middle**2 + middle * tip + tip**2)
    assert volume == pytest.approx(analytic, rel=1e-14)


def test_initial_observer_has_no_live_rng_and_cannot_change_execution():
    value = spec("legacy")
    baseline = run(value)
    seen = []

    def recorder(sim, p):
        assert not hasattr(sim, "rng") and not hasattr(sim, "streams")
        with pytest.raises(AttributeError, match="read-only"):
            p.gravitropism = .9
        with pytest.raises(AttributeError, match="read-only"):
            sim.G.nodes[1].node_data.diameter = 999.
        nodes, edges = sim.G.as_df()
        nodes.loc[:, "z"] = 123.
        sim.organs.clear()
        seen.append((nodes, edges))

    sim = RootSystemSimulation(random_seed=value["random_seed"], simulation_tag=value["simulation_tag"])
    sim.run(copy.deepcopy(value), initial_recorder=recorder)
    assert seen
    assert tables(sim) == tables(baseline)
    assert sim.rng.bit_generator.state == baseline.rng.bit_generator.state
    assert sim.result.metadata == baseline.result.metadata


def test_unseeded_direct_execution_records_realized_rng_and_distinct_identities():
    from deeprootgen.data_model import RootSimulationModel
    import json
    from pathlib import Path

    parameters = json.loads(Path("tests/fixtures/migration_inputs/synthetic_minimal.json").read_text())
    parameters["random_seed"] = None
    a, b = RootSystemSimulation(random_seed=None), RootSystemSimulation(random_seed=None)
    for simulation in (a, b):
        simulation.run(RootSimulationModel(**parameters))
        record = simulation.result.engine["provenance"]
        assert record["replayable"] is False and record["replay_policy"] == "unseeded_non_replayable"
        assert record["initial_native_rng_state"]["bit_generator"] == "PCG64"
    assert a.result.metadata["run_identity_sha256"] != b.result.metadata["run_identity_sha256"]


def test_runtime_function_changes_are_distinguished_from_disk_source(monkeypatch):
    from deeprootgen.model.root import RootOrgan
    baseline = run(spec())
    original = RootOrgan.init_diameters

    def forwarding(self, *args, **kwargs):
        return original(self, *args, **kwargs)

    monkeypatch.setattr(RootOrgan, "init_diameters", forwarding)
    changed = run(spec())
    assert tables(changed) == tables(baseline)
    a, b = baseline.result.engine["provenance"], changed.result.engine["provenance"]
    assert a["source_sha256"] == b["source_sha256"]
    assert a["loaded_python_code_sha256"] != b["loaded_python_code_sha256"]
    assert changed.result.metadata["run_identity_sha256"] != baseline.result.metadata["run_identity_sha256"]


def test_source_edits_since_import_require_restart_before_allocation(monkeypatch):
    from deeprootgen.model import provenance
    monkeypatch.setattr(provenance, "source_fingerprint", lambda: "changed-on-disk")
    simulation = RootSystemSimulation(random_seed=42)
    before = copy.deepcopy(simulation.rng.bit_generator.state)
    with pytest.raises(ValueError, match="restart Python"):
        simulation.run(spec())
    assert not simulation.organs and len(simulation.G.nodes) == 1
    assert simulation.rng.bit_generator.state == before
