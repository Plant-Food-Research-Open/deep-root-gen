"""Invented matched-reference isolation; no observations or empirical seeds."""

import copy
import json

import numpy as np
import pandas as pd
import pytest

from deeprootgen.research.primary_scaffold import freeze_primary_scaffold
from deeprootgen.research.construction_step_replay import replay_construction_steps, validate_construction_metadata
from deeprootgen.research.so4_controlled import Skeleton, construct_skeleton, digest, validate_geometry
from tests.test_parent2_branch_zone import ZONE, parameters


@pytest.fixture
def pair():
    return construct_skeleton(parameters(ZONE), 42), construct_skeleton(parameters(), 42)


def test_pure_reference_transport_preserves_dimensions_lengths_and_canonical_parent_paths(pair, monkeypatch):
    source, reference = pair
    source_snapshot, reference_snapshot = copy.deepcopy(source.payload), copy.deepcopy(reference.payload)
    original = pd.DataFrame(source.payload["nodes"])
    target = pd.DataFrame(reference.payload["nodes"])
    assert not original.loc[original.order.le(1), ["x", "y", "z"]].equals(target.loc[target.order.le(1), ["x", "y", "z"]])

    def forbidden(*args, **kwargs):
        pytest.fail("Reference transport consumed a random stream")

    with monkeypatch.context() as context:
        context.setattr(np.random, "default_rng", forbidden)
        frozen = freeze_primary_scaffold(source, reference)
    repeated = freeze_primary_scaffold(source, reference)
    assert frozen.payload == repeated.payload and frozen.sha256 == repeated.sha256
    assert source.payload == source_snapshot and reference.payload == reference_snapshot
    nodes, edges = pd.DataFrame(frozen.payload["nodes"]), pd.DataFrame(frozen.payload["edges"])
    pd.testing.assert_frame_equal(nodes.drop(columns=["x", "y", "z"]), original.drop(columns=["x", "y", "z"]), check_exact=True)
    pd.testing.assert_frame_equal(nodes.loc[nodes.order.le(1)].reset_index(drop=True),
                                  target.loc[target.order.le(1)].reset_index(drop=True), check_exact=True)
    assert frozen.payload["edges"] == source.payload["edges"]
    validate_geometry(nodes, edges)
    validate_construction_metadata(frozen)
    lookup, before = nodes.set_index("node_id"), original.set_index("node_id")
    for report in frozen.payload["primary_scaffold_reference"]["transforms"]:
        ids, rotation = report["node_ids"], np.array(report["rotation"])
        expected = np.array(report["reference_anchor_cm"]) + (
            before.loc[ids, ["x", "y", "z"]].to_numpy(float) - report["old_anchor_cm"]) @ rotation.T
        np.testing.assert_allclose(lookup.loc[ids, ["x", "y", "z"]].to_numpy(float), expected, rtol=0, atol=1e-12)
        np.testing.assert_allclose(rotation.T @ rotation, np.eye(3), rtol=0, atol=1e-12)
        assert np.linalg.det(rotation) == pytest.approx(1., abs=1e-12)
    old_organs = {o["organ_id"]: o for o in source.payload["organs"]}
    for organ in frozen.payload["organs"]:
        if organ["order"] == 1:
            continue
        old_meta, new_meta = old_organs[organ["organ_id"]]["construction_steps"], organ["construction_steps"]
        assert old_meta["sampler"] == new_meta["sampler"]
        assert old_meta["boundary_node_ids"] == new_meta["boundary_node_ids"]
        ids = [organ["parent_id"], *new_meta["boundary_node_ids"]]
        np.testing.assert_array_equal(new_meta["positioned_boundary_xyz"], lookup.loc[ids, ["x", "y", "z"]])
    baseline = replay_construction_steps(reference, "D", parameters().model_dump(), "minimum_angle_projection")
    result = replay_construction_steps(frozen, "D", parameters(ZONE).model_dump(), "minimum_angle_projection")

    def parents(replay):
        return [record for record in replay["diagnostics"]["construction_steps"] if record["order"] == 2]

    assert parents(result) == parents(baseline)
    assert len([o for o in source.payload["organs"] if o["order"] == 3]) > len([o for o in reference.payload["organs"] if o["order"] == 3])
    assert frozen.payload["primary_scaffold_reference"]["reference_sha256"] == reference.sha256
    validate_geometry(result["nodes"], result["edges"], 20.)


@pytest.mark.parametrize("defect", ["seed", "base", "primary_dimension", "primary_identity", "attachment", "parent2_steps"])
def test_mismatched_reference_rejected_without_mutating_either_input(pair, defect):
    source, reference = pair
    if defect == "seed":
        reference = construct_skeleton(parameters(random_seed=43), 43)
    elif defect == "base":
        for row in reference.payload["nodes"]:
            row["x"] += 1.
        for organ in reference.payload["organs"]:
            if "construction_steps" in organ:
                for point in organ["construction_steps"]["positioned_boundary_xyz"]:
                    point[0] += 1.
    elif defect == "primary_dimension":
        reference.payload["nodes"][1]["diameter"] *= 2.
    elif defect == "primary_identity":
        reference.payload["nodes"][1]["position_type"] = "different-position"
    elif defect == "attachment":
        next(o for o in reference.payload["organs"] if o["order"] == 2)["attachment_arc_cm"] += .1
    elif defect == "parent2_steps":
        next(o for o in reference.payload["organs"] if o["order"] == 2)["construction_steps"]["lengths_cm"][0] += .1
    reference = Skeleton(reference.payload, digest(reference.payload))
    snapshots = copy.deepcopy(source.payload), copy.deepcopy(reference.payload)
    with pytest.raises(ValueError):
        freeze_primary_scaffold(source, reference)
    assert source.payload == snapshots[0] and reference.payload == snapshots[1]


def test_identical_reference_keeps_coordinates_exact(pair):
    source, _ = pair
    frozen = freeze_primary_scaffold(source, source)
    assert frozen.payload["nodes"] == source.payload["nodes"]
    assert frozen.payload["edges"] == source.payload["edges"]


def test_sorted_json_reference_roundtrip_does_not_change_identity_or_result(pair):
    source, reference = pair
    roundtrip = Skeleton(json.loads(json.dumps(reference.payload, sort_keys=True)), reference.sha256)
    expected = freeze_primary_scaffold(source, reference)
    actual = freeze_primary_scaffold(source, roundtrip)
    assert actual.payload == expected.payload and actual.sha256 == expected.sha256


def test_short_parent_zone_removes_all_tertiaries_but_retains_exact_parent_paths():
    cdfs = {2: dict(lengths_cm=[10.], cumulative_probabilities=[1.]),
            3: dict(lengths_cm=[2.], cumulative_probabilities=[1.])}
    control = parameters(research_current_length_cdfs_cm=cdfs)
    zone = parameters(ZONE, research_current_length_cdfs_cm=cdfs)
    reference, source = construct_skeleton(control, 42), construct_skeleton(zone, 42)
    assert any(organ["order"] == 3 for organ in reference.payload["organs"])
    assert not any(organ["order"] == 3 for organ in source.payload["organs"])
    frozen = freeze_primary_scaffold(source, reference)
    baseline = replay_construction_steps(reference, "D", control.model_dump(), "minimum_angle_projection")
    result = replay_construction_steps(frozen, "D", zone.model_dump(), "minimum_angle_projection")
    assert [r for r in baseline["diagnostics"]["construction_steps"] if r["order"] == 2] == result["diagnostics"]["construction_steps"]
