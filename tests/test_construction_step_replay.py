"""Invented operator partitions and separately captured keyed live constructions."""

import copy

import numpy as np
import pandas as pd
import pytest

from deeprootgen.archive.simulation import RootSystemSimulation
from deeprootgen.research import construction_step_replay as step
from deeprootgen.research.so4_controlled import Skeleton, construct_skeleton, digest, replay_arm, validate_geometry
from tests.test_primary_inclination import parameters as inclination_parameters

POLICY = "minimum_angle_projection"


def parameters(active=True, **updates):
    values = dict(segments_per_root=2, research_current_length_grid=step.GRID if active else None,
                  research_current_length_cdfs_cm={
                      2: dict(lengths_cm=[10.], cumulative_probabilities=[1.]),
                      3: dict(lengths_cm=[2.], cumulative_probabilities=[1.]),
                  },
                  research_primary_yaw_mean_deg=35., research_primary_yaw_kappa=2.,
                  research_primary_inclination_bias=.3, research_base_origin_x_cm=1.,
                  research_base_origin_y_cm=-2., research_base_depth_cm=8.,
                  research_branch_placement="redistribute_capped")
    values.update(updates)
    return inclination_parameters(**values)


def resign(skeleton):
    return Skeleton(skeleton.payload, digest(skeleton.payload))


def operator_graph(cuts, surface=False):
    # This [4,6] unit fixture is NOT claimed to be drawn by the sorted-weight
    # sampler. Live captured provenance is exercised in separate API tests.
    entries = [dict(node_id=0, parent_id=-1, organ_id=0, order=0, segment_rank=0,
                    x=0., y=0., z=20., length=0., diameter=0., invalid_root=False),
               dict(node_id=1, parent_id=0, organ_id=1, order=1, segment_rank=1,
                    x=0., y=0., z=18., length=2., diameter=.2, invalid_root=False)]
    previous = 0.
    for rank, arc in enumerate(cuts, 1):
        entries.append(dict(node_id=rank + 1, parent_id=rank, organ_id=2, order=2, segment_rank=rank,
                            x=arc, y=0., z=18., length=arc - previous, diameter=.1, invalid_root=False))
        previous = arc
    nodes = pd.DataFrame(entries).set_index("node_id", drop=False)
    groups, start = [], 0.
    for index, end in enumerate([4., 10.]):
        fragment_ids = [rank + 2 for rank, arc in enumerate(cuts) if start < arc <= end]
        groups.append(dict(step_index=index, length_cm=end - start,
                           node_ids=fragment_ids, fractions=[(cuts[nid - 2] - start) / (end - start) for nid in fragment_ids]))
        start = end
    organ = dict(organ_id=2, order=2, parent_id=1, construction_steps=dict(synthetic_unit_fixture=True))
    return nodes, organ, groups


@pytest.mark.parametrize("crossing", [False, True])
def test_integration_once_per_4_6_step_independent_of_extra_2_4_8_10_cuts(monkeypatch, crossing):
    streams, original_stream = [], step.step_rng

    def observed_stream(*args):
        streams.append(args)
        return original_stream(*args)

    monkeypatch.setattr(step, "step_rng", observed_stream)
    if crossing:
        monkeypatch.setattr(step, "insertion_heading", lambda *args: np.array([0., 0., 1.]))
        monkeypatch.setattr(step, "fichtl_proposal", lambda *args: (np.array([0., 0., 1.]), {}))
    outputs = []
    for cuts in ([4., 10.], [2., 4., 8., 10.]):
        nodes, organ, groups = operator_graph(cuts)
        records, mapping, receipt = step._replay_organ(organ, groups, nodes, parameters().model_dump(), 42, POLICY, 20., None)
        outputs.append((nodes, records, mapping))
        assert len(records) == 2 and len(mapping) == len(cuts)
        for record, group in zip(records, groups):
            np.testing.assert_array_equal(nodes.loc[group["node_ids"][-1], step.XYZ], record["accepted_endpoint"])
        validate_geometry(nodes.reset_index(drop=True), step.derived_edges(nodes.reset_index(drop=True)), 20.)
    coarse, fine = outputs
    assert streams[:len(streams) // 2] == streams[len(streams) // 2:]
    assert sum(key[-1] == "boundary" for key in streams) == 4
    assert coarse[1] == fine[1]
    assert sum(r["boundary_intervention"] for r in coarse[1]) == (2 if crossing else 0)
    for arc, coarse_id, fine_id in [(4., 2, 3), (10., 3, 5)]:
        np.testing.assert_array_equal(coarse[0].loc[coarse_id, step.XYZ], fine[0].loc[fine_id, step.XYZ])
    for nid, fraction in [(2, .5), (4, 2. / 3.)]:
        record = fine[1][0 if nid == 2 else 1]
        expected = np.array(record["start_xyz"]) + fraction * (np.array(record["accepted_endpoint"]) - record["start_xyz"])
        np.testing.assert_array_equal(fine[0].loc[nid, step.XYZ], expected)
    if crossing:
        assert fine[1][1]["accepted_heading"][2] <= 0.
        assert np.linalg.norm(fine[1][1]["accepted_heading"][:2]) == pytest.approx(1.)


def test_live_capture_uses_positioned_boundaries_and_preserves_original_keyed_sampler(monkeypatch):
    p = parameters()
    captured = []
    original_sampler = __import__("deeprootgen.model.root", fromlist=["sample_current_lengths"]).sample_current_lengths

    def observe(*args):
        lengths, report = original_sampler(*args)
        captured.append((lengths.copy(), copy.deepcopy(report)))
        return lengths, report

    monkeypatch.setattr("deeprootgen.model.root.sample_current_lengths", observe)
    saved = construct_skeleton(p, 42)
    lookup = pd.DataFrame(saved.payload["nodes"]).set_index("node_id")
    organs = [o for o in saved.payload["organs"] if o["order"] > 1]
    assert len(captured) == len(organs)
    observed = {report["expected_organ_id"]: (lengths, report) for lengths, report in captured}
    for organ in organs:
        metadata = organ["construction_steps"]
        lengths, report = observed[organ["organ_id"]]
        np.testing.assert_array_equal(metadata["lengths_cm"], lengths)
        assert metadata["sampler"]["quantile"] == report["quantile"]
        ids = [organ["parent_id"], *metadata["boundary_node_ids"]]
        np.testing.assert_array_equal(metadata["positioned_boundary_xyz"], lookup.loc[ids, step.XYZ])
    partitions = step.validate_construction_metadata(saved)
    result = step.replay_construction_steps(saved, "D", p.model_dump(), POLICY)
    repeat = step.replay_construction_steps(saved, "D", p.model_dump(), POLICY)
    for key in ("nodes", "edges", "proposals"):
        pd.testing.assert_frame_equal(result[key], repeat[key], check_exact=True)
    assert result["diagnostics"] == repeat["diagnostics"]
    assert len(result["diagnostics"]["construction_steps"]) == sum(len(parts) for parts in partitions.values())
    assert result["diagnostics"]["invariant_hashes"] == step.invariant_hashes(pd.DataFrame(saved.payload["nodes"]))
    validate_geometry(result["nodes"], result["edges"], 20.)


def renumber(saved):
    payload = copy.deepcopy(saved.payload)
    remap = {row["node_id"]: 1000 + 3 * row["node_id"] for row in payload["nodes"]}
    for row in payload["nodes"]:
        row["node_id"] = remap[row["node_id"]]
        row["parent_id"] = remap.get(row["parent_id"], -1)
    for row in payload["edges"]:
        row["parent_id"], row["child_id"] = remap[row["parent_id"]], remap[row["child_id"]]
    for organ in payload["organs"]:
        organ["parent_id"] = remap[organ["parent_id"]]
        organ["node_ids"] = [remap[nid] for nid in organ["node_ids"]]
        if "construction_steps" in organ:
            organ["construction_steps"]["boundary_node_ids"] = [remap[nid] for nid in organ["construction_steps"]["boundary_node_ids"]]
    return Skeleton(payload, digest(payload)), remap


def test_node_renumbering_preserves_proposals_and_every_realised_coordinate():
    p = parameters()
    saved = construct_skeleton(p, 42)
    changed, mapping = renumber(saved)
    first = step.replay_construction_steps(saved, "D", p.model_dump(), POLICY)
    second = step.replay_construction_steps(changed, "D", p.model_dump(), POLICY)
    pd.testing.assert_frame_equal(first["proposals"], second["proposals"], check_exact=True)
    assert first["diagnostics"]["construction_steps"] == second["diagnostics"]["construction_steps"]
    actual = second["nodes"].set_index("node_id")
    for row in first["nodes"].itertuples():
        np.testing.assert_array_equal([row.x, row.y, row.z], actual.loc[mapping[row.node_id], step.XYZ])


@pytest.mark.parametrize("corner", [False, True])
def test_daughter_origins_follow_interpolated_parent_and_incoming_corner_tangent(corner):
    p = parameters()
    saved = construct_skeleton(p, 42)
    daughter = next(o for o in saved.payload["organs"] if o["order"] == 3)
    lookup = pd.DataFrame(saved.payload["nodes"]).set_index("node_id")
    parent_organ_id = int(lookup.loc[daughter["parent_id"], "organ_id"])
    parent_organ = next(o for o in saved.payload["organs"] if o["organ_id"] == parent_organ_id)
    boundaries = parent_organ["construction_steps"]["boundary_node_ids"]
    if corner:
        old_parent, new_parent = daughter["parent_id"], boundaries[0]
        translation = lookup.loc[new_parent, step.XYZ].to_numpy(float) - lookup.loc[old_parent, step.XYZ].to_numpy(float)
        for row in saved.payload["nodes"]:
            if row["node_id"] in daughter["node_ids"]:
                for axis, delta in zip(step.XYZ, translation):
                    row[axis] += float(delta)
            if row["node_id"] == daughter["node_ids"][0]:
                row["parent_id"] = new_parent
        for edge in saved.payload["edges"]:
            if edge["child_id"] == daughter["node_ids"][0]:
                edge["parent_id"] = new_parent
        daughter["parent_id"] = new_parent
        coords = np.array(daughter["construction_steps"]["positioned_boundary_xyz"])
        daughter["construction_steps"]["positioned_boundary_xyz"] = (coords + translation).tolist()
        saved = resign(saved)
    else:
        assert daughter["parent_id"] not in boundaries
    result = step.replay_construction_steps(saved, "D", p.model_dump(), POLICY)
    records = result["diagnostics"]["construction_steps"]
    first = next(record for record in records if record["organ_id"] == daughter["organ_id"])
    nodes = result["nodes"].set_index("node_id")
    parent = nodes.loc[daughter["parent_id"]]
    np.testing.assert_array_equal(first["start_xyz"], parent[step.XYZ])
    receipt = next(report for report in result["diagnostics"]["organs"] if report["organ_id"] == daughter["organ_id"])
    incoming = step.unit(parent[step.XYZ].to_numpy(float) - nodes.loc[int(parent.parent_id), step.XYZ].to_numpy(float))
    np.testing.assert_allclose(receipt["parent_tangent"], incoming, rtol=0, atol=1e-12)
    assert receipt["parent_tangent_source"] == "incoming_construction_step"
    if corner:
        first_parent_step = next(record for record in records if record["organ_id"] == parent_organ_id)
        np.testing.assert_allclose(incoming, first_parent_step["accepted_heading"], rtol=0, atol=1e-12)


@pytest.mark.parametrize("defect", ["missing", "duplicate", "wrong_seed", "wrong_sampler", "wrong_cdf", "wrong_length", "stale_xyz", "wrong_member"])
def test_missing_ambiguous_and_inconsistent_partition_rejected(defect):
    p = parameters()
    saved = construct_skeleton(p, 42)
    organ = next(o for o in saved.payload["organs"] if o["order"] == 2)
    metadata = organ["construction_steps"]
    if defect == "missing":
        organ.pop("construction_steps")
    elif defect == "duplicate":
        metadata["boundary_node_ids"][1] = metadata["boundary_node_ids"][0]
    elif defect == "wrong_seed":
        metadata["sampler"]["seed"] = 43
    elif defect == "wrong_sampler":
        metadata["sampler"]["stream_version"] = "unknown"
    elif defect == "wrong_cdf":
        metadata["sampler"]["cdf_sha256"] = "wrong"
    elif defect == "wrong_length":
        metadata["lengths_cm"][0] += .1
    elif defect == "stale_xyz":
        metadata["positioned_boundary_xyz"][0][0] += 1.
    elif defect == "wrong_member":
        metadata["boundary_node_ids"][0] = organ["parent_id"]
    with pytest.raises(ValueError):
        step.replay_construction_steps(resign(saved), "D", p.model_dump(), POLICY)


def refine_graph(saved, boundary, tail_length):
    organ = next(o for o in saved.payload["organs"] if boundary in o["node_ids"])
    nodes = pd.DataFrame(saved.payload["nodes"])
    lookup = nodes.set_index("node_id")
    end = lookup.loc[boundary]
    parent = lookup.loc[int(end.parent_id)]
    new_id = int(nodes.node_id.max()) + 1
    inserted = end.to_dict()
    inserted["node_id"], inserted["parent_id"] = new_id, int(end.parent_id)
    fraction = 1. - tail_length / end.length
    point = parent[step.XYZ].to_numpy(float) + fraction * (end[step.XYZ].to_numpy(float) - parent[step.XYZ].to_numpy(float))
    inserted.update(dict(zip(step.XYZ, point)))
    inserted["length"] = float(end.length - tail_length)
    selected = nodes.organ_id.eq(organ["organ_id"]) & nodes.segment_rank.ge(int(end.segment_rank))
    nodes.loc[selected, "segment_rank"] += 1
    nodes.loc[nodes.node_id.eq(boundary), "parent_id"] = new_id
    nodes.loc[nodes.node_id.eq(boundary), "length"] = tail_length
    nodes = pd.concat([nodes, pd.DataFrame([inserted])], ignore_index=True)
    for key in ("node_id", "parent_id", "organ_id", "order", "segment_rank"):
        nodes[key] = nodes[key].astype(int)
    changed = Skeleton.from_tables(nodes, step.derived_edges(nodes), 42, saved.payload["parameters"])
    metadata = {o["organ_id"]: o.get("construction_steps") for o in saved.payload["organs"]}
    for current in changed.payload["organs"]:
        if metadata[current["organ_id"]] is not None:
            current["construction_steps"] = metadata[current["organ_id"]]
    return resign(changed)


def test_ambiguous_corner_nearby_graph_cut_is_rejected_without_merging_or_rescaling():
    p = parameters()
    saved = construct_skeleton(p, 42)
    organ = next(o for o in saved.payload["organs"] if o["order"] == 2)
    boundary = organ["construction_steps"]["boundary_node_ids"][0]
    changed = refine_graph(saved, boundary, 1e-9)
    with pytest.raises(ValueError, match="ambiguous"):
        step.validate_construction_metadata(changed)


def test_live_additional_cut_preserves_parent_and_daughter_step_directions_and_coordinates():
    p = parameters()
    saved = construct_skeleton(p, 42)
    daughter = next(o for o in saved.payload["organs"] if o["order"] == 3)
    parent_id = daughter["parent_id"]
    old = pd.DataFrame(saved.payload["nodes"]).set_index("node_id")
    refined = refine_graph(saved, parent_id, float(old.loc[parent_id, "length"]) / 4.)
    baseline = step.replay_construction_steps(saved, "D", p.model_dump(), POLICY)
    result = step.replay_construction_steps(refined, "D", p.model_dump(), POLICY)
    for first, second in zip(baseline["diagnostics"]["construction_steps"], result["diagnostics"]["construction_steps"]):
        assert first.get("innovations_sha256") == second.get("innovations_sha256")
        np.testing.assert_array_equal(first["proposed_heading"], second["proposed_heading"])
        np.testing.assert_array_equal(first["accepted_heading"], second["accepted_heading"])
    actual = result["nodes"].set_index("node_id")
    for row in baseline["nodes"].itertuples():
        np.testing.assert_allclose([row.x, row.y, row.z], actual.loc[row.node_id, step.XYZ].to_numpy(float), rtol=0, atol=1e-8)


@pytest.mark.parametrize("method", ["run", "apply_fichtl_tropism"])
def test_native_routes_reject_before_mutation(method):
    p = parameters()
    sim = RootSystemSimulation(random_seed=42)
    before, state = sim.G.as_df(), copy.deepcopy(sim.rng.bit_generator.state)
    with pytest.raises(ValueError, match="named controlled replay"):
        getattr(sim, method)(p)
    for expected, actual in zip(before, sim.G.as_df()):
        pd.testing.assert_frame_equal(expected, actual)
    assert state == sim.rng.bit_generator.state


def test_wrong_entrypoint_arms_seed_and_construction_config_rejected():
    p = parameters()
    saved = construct_skeleton(p, 42)
    with pytest.raises(ValueError, match="not legacy replay_arm"):
        replay_arm(saved, "D", p.model_dump(), POLICY)
    for arm in ("A", "B", "C"):
        with pytest.raises(ValueError, match="only supports D"):
            step.replay_construction_steps(saved, arm, p.model_dump(), POLICY)
    for updates in ({"random_seed": 43}, {"research_current_length_grid": None}, {"root_vary": 99.}):
        with pytest.raises(ValueError):
            step.replay_construction_steps(saved, "D", {**p.model_dump(), **updates}, POLICY)
    with pytest.raises(ValueError, match="matching explicit seeds"):
        construct_skeleton(p, 43)


@pytest.mark.parametrize("updates", [{"tropism_mode": "legacy"}, {"max_order": 2}, {"random_seed": None},
                                     {"research_current_length_cdfs_cm": None},
                                     {"research_current_length_cdfs_cm": {2: dict(lengths_cm=[10.], cumulative_probabilities=[1.])}}])
def test_schema_restricts_initial_scope(updates):
    with pytest.raises(ValueError):
        parameters(**updates)


def test_none_grid_preserves_initial_serialization_native_replay_and_rng():
    p = parameters(active=False)
    implicit_values = p.model_dump()
    implicit_values.pop("research_current_length_grid")
    implicit, explicit = construct_skeleton(implicit_values, 42), construct_skeleton(p, 42)
    assert implicit.payload == explicit.payload and implicit.sha256 == explicit.sha256
    assert "research_current_length_grid" not in implicit.payload["parameters"]
    assert not any("construction_steps" in organ for organ in implicit.payload["organs"])
    for arm in "ABCD":
        first, second = replay_arm(implicit, arm, implicit_values, POLICY), replay_arm(explicit, arm, p.model_dump(), POLICY)
        for key in ("nodes", "edges", "proposals"):
            pd.testing.assert_frame_equal(first[key], second[key], check_exact=True)
        assert first["diagnostics"] == second["diagnostics"]
    first, second = RootSystemSimulation(random_seed=42), RootSystemSimulation(random_seed=42)
    first.run(p)
    second.run(p.model_copy(update={"research_current_length_grid": None}))
    for expected, actual in zip(first.G.as_df(), second.G.as_df()):
        pd.testing.assert_frame_equal(expected, actual, check_exact=True)
    assert first.rng.bit_generator.state == second.rng.bit_generator.state
