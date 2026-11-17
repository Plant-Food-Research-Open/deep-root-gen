"""Invented authenticated straight INITIALs; no simulation or observations."""

import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import RootSimulationModel
from deeprootgen.research import construction_step_replay as legacy
from deeprootgen.research import physical_step_replay as physical
from deeprootgen.research.so4_controlled import Skeleton, digest, validate_geometry
from deeprootgen.utils.current_length import sample_current_lengths


def invented_initial(max_order=3, seed=42):
    values = json.loads(
        (Path(__file__).parents[1] / "examples/synthetic_minimal.json").read_text()
    )
    values.update(
        random_seed=seed,
        max_order=max_order,
        segments_per_root=2,
        tropism_mode="fichtl2024",
        gravitropism=0.0,
        soil_surface_z_cm=20.0,
        research_current_length_grid=legacy.GRID,
        research_current_length_cdfs_cm={
            order: dict(
                lengths_cm=[{2: 10.0, 3: 4.0, 4: 3.0, 5: 2.0}[order]],
                cumulative_probabilities=[1.0],
            )
            for order in range(2, max_order + 1)
        },
        fichtl_probability_down=0.5,
        fichtl_sigma=0.25,
        fichtl_trials_type2=2.0,
        fichtl_trials_type3=1.0,
        fichtl_theta2_deg=60.0,
        fichtl_theta2_sd_deg=10.0,
        fichtl_theta3_deg=50.0,
        fichtl_theta3_sd_deg=10.0,
    )
    if max_order > 3:
        values["research_higher_order_tropism"] = {
            order: dict(
                theta_deg=40.0, theta_sd_deg=5.0, probability_down=0.5, trials=1.0
            )
            for order in range(4, max_order + 1)
        }
    settings = RootSimulationModel(**values).model_dump()
    nodes = [
        dict(
            node_id=0,
            parent_id=-1,
            organ_id=0,
            order=0,
            segment_rank=0,
            x=0.0,
            y=0.0,
            z=20.0,
            length=0.0,
            diameter=0.0,
            root_tissue_density=0.04,
            invalid_root=False,
        ),
        dict(
            node_id=1,
            parent_id=0,
            organ_id=1,
            order=1,
            segment_rank=1,
            x=0.0,
            y=0.0,
            z=18.0,
            length=2.0,
            diameter=0.3,
            root_tissue_density=0.05,
            invalid_root=False,
        ),
    ]
    metadata, parent_id, next_id = {}, 1, 2
    for order in range(2, max_order + 1):
        oid = order
        lengths, sampler = sample_current_lengths(
            settings["research_current_length_cdfs_cm"][order], 2, seed, oid, order
        )
        sampler.update(
            allocated_organ_id=oid, post_subdivision_length_cm=float(lengths.sum())
        )
        # Deliberate attachment and diameter breaks inside original intervals.
        cuts = [
            0.35 * lengths[0],
            0.6 * lengths[0],
            lengths[0],
            lengths[0] + 0.5 * lengths[1],
            lengths.sum(),
        ]
        origin = np.array([nodes[parent_id][axis] for axis in physical.XYZ])
        heading = (
            np.array([1.0, 0.0, 0.0]) if order % 2 == 0 else np.array([0.0, 1.0, 0.0])
        )
        ids, previous_arc, previous_id = [], 0.0, parent_id
        for rank, arc in enumerate(cuts, 1):
            point = origin + arc * heading
            nodes.append(
                dict(
                    node_id=next_id,
                    parent_id=previous_id,
                    organ_id=oid,
                    order=order,
                    segment_rank=rank,
                    x=point[0],
                    y=point[1],
                    z=point[2],
                    length=float(arc - previous_arc),
                    diameter=0.12 if rank <= 2 else 0.07,
                    root_tissue_density=0.03 + 0.01 * rank,
                    invalid_root=False,
                )
            )
            ids.append(next_id)
            previous_id, previous_arc, next_id = next_id, arc, next_id + 1
        metadata[oid] = dict(
            version=legacy.VERSION,
            lengths_cm=lengths.tolist(),
            boundary_node_ids=[ids[2], ids[-1]],
            positioned_boundary_xyz=[
                origin.tolist(),
                (origin + lengths[0] * heading).tolist(),
                (origin + lengths.sum() * heading).tolist(),
            ],
            sampler=sampler,
        )
        parent_id = ids[0]  # Interior of first original construction interval.
    table = pd.DataFrame(nodes)
    saved = Skeleton.from_tables(
        table, legacy.derived_edges(table), seed, copy.deepcopy(settings)
    )
    for organ in saved.payload["organs"]:
        if organ["order"] > 1:
            organ["construction_steps"] = metadata[organ["organ_id"]]
    saved.sha256 = digest(saved.payload)
    legacy.validate_construction_metadata(saved)
    return saved, settings


def subdivide_same_interval(saved, node_id):
    """Keep IDs/boundaries/attachment arcs while splitting one constant segment."""
    payload = copy.deepcopy(saved.payload)
    by_id = {row["node_id"]: row for row in payload["nodes"]}
    end = by_id[node_id]
    start = by_id[end["parent_id"]]
    inserted = copy.deepcopy(end)
    inserted["node_id"] = max(by_id) + 1
    inserted["length"] = end["length"] / 2.0
    for axis in physical.XYZ:
        inserted[axis] = (end[axis] + start[axis]) / 2.0
    end["length"] /= 2.0
    end["parent_id"] = inserted["node_id"]
    for row in payload["nodes"]:
        if (
            row["organ_id"] == end["organ_id"]
            and row["segment_rank"] >= end["segment_rank"]
        ):
            row["segment_rank"] += 1
    inserted["segment_rank"] = end["segment_rank"] - 1
    payload["nodes"].append(inserted)
    for organ in payload["organs"]:
        if node_id in organ["node_ids"]:
            organ["node_ids"].insert(
                organ["node_ids"].index(node_id), inserted["node_id"]
            )
    payload["edges"] = legacy.derived_edges(pd.DataFrame(payload["nodes"])).to_dict(
        "records"
    )
    return Skeleton(payload, digest(payload))


def measured_traits(nodes):
    lookup = nodes.set_index("node_id")
    result = {}
    for oid, chain in nodes.loc[nodes.order.gt(0)].groupby("organ_id"):
        lengths = np.linalg.norm(
            chain[physical.XYZ].to_numpy(float)
            - lookup.loc[chain.parent_id, physical.XYZ].to_numpy(float),
            axis=1,
        )
        result[oid] = np.array(
            [
                lengths.sum(),
                np.sum(chain.diameter.to_numpy() ** 2 * lengths),
                np.sum(
                    chain.root_tissue_density.to_numpy()
                    * chain.diameter.to_numpy() ** 2
                    * lengths
                ),
            ]
        )
    return result


def test_empty_orders_is_exact_legacy_delegation():
    saved, settings = invented_initial()
    expected = legacy.replay_construction_steps(
        saved, "D", settings, "minimum_angle_projection"
    )
    actual = physical.replay_physical_steps(saved, settings, orders=())
    for key in ("nodes", "edges", "proposals"):
        pd.testing.assert_frame_equal(actual[key], expected[key], check_exact=True)
    assert actual["diagnostics"] == expected["diagnostics"]


@pytest.mark.parametrize("maximum,orders", [(3, (2,)), (3, (2, 3)), (5, (2, 5))])
def test_finite_connected_conserved_graph_deterministic_and_capped(maximum, orders):
    saved, settings = invented_initial(maximum)
    original = pd.DataFrame(saved.payload["nodes"])
    result = physical.replay_physical_steps(
        saved, settings, orders=orders, max_step_cm=0.75
    )
    repeat = physical.replay_physical_steps(
        saved, settings, orders=orders, max_step_cm=0.75
    )
    for key in ("nodes", "edges", "proposals"):
        pd.testing.assert_frame_equal(result[key], repeat[key], check_exact=True)
    assert result["diagnostics"] == repeat["diagnostics"]
    assert (
        result["diagnostics"]["source_sampler_seed"]
        == result["diagnostics"]["direction_seed"]
        == 42
    )
    assert len(result["nodes"]) > len(original)
    validate_geometry(result["nodes"], result["edges"], 20.0)
    assert result["nodes"].order.eq(0).sum() == 1
    assert (
        result["nodes"].groupby("order").organ_id.nunique().to_dict()
        == original.groupby("order").organ_id.nunique().to_dict()
    )
    assert set(original.node_id) <= set(result["nodes"].node_id)
    pd.testing.assert_frame_equal(
        original.loc[original.order.le(1)].reset_index(drop=True),
        result["nodes"].loc[result["nodes"].order.le(1)].reset_index(drop=True),
        check_exact=True,
    )
    for oid, expected in measured_traits(original).items():
        np.testing.assert_allclose(
            measured_traits(result["nodes"])[oid], expected, rtol=1e-9, atol=1e-12
        )
    assert all(
        0 < step["length_cm"] <= 0.75 + 1e-14
        for step in result["diagnostics"]["physical_steps"]
    )
    # Original landmarks (including diameter/density breaks) retain their arcs.
    new = result["nodes"]
    for organ in saved.payload["organs"]:
        old_chain = original.loc[original.organ_id.eq(organ["organ_id"])].sort_values(
            "segment_rank"
        )
        new_chain = new.loc[new.organ_id.eq(organ["organ_id"])].sort_values(
            "segment_rank"
        )
        arc = dict(zip(new_chain.node_id, new_chain.length.cumsum()))
        for nid, old_arc in zip(old_chain.node_id, old_chain.length.cumsum()):
            assert arc[nid] == pytest.approx(old_arc, rel=1e-12, abs=1e-12)
            for field in ("diameter", "root_tissue_density"):
                assert (
                    new.set_index("node_id").loc[nid, field]
                    == original.set_index("node_id").loc[nid, field]
                )


def test_fragment_subdivision_does_not_change_physical_innovations_or_old_geometry():
    saved, settings = invented_initial()
    parent = next(o for o in saved.payload["organs"] if o["order"] == 2)
    changed = subdivide_same_interval(saved, parent["node_ids"][1])
    first = physical.replay_physical_steps(saved, settings)
    second = physical.replay_physical_steps(changed, settings)
    assert (
        first["diagnostics"]["physical_steps"]
        == second["diagnostics"]["physical_steps"]
    )
    pd.testing.assert_frame_equal(
        first["proposals"], second["proposals"], check_exact=True
    )
    lookup = second["nodes"].set_index("node_id")
    for row in first["nodes"].itertuples():
        if row.node_id in {r["node_id"] for r in saved.payload["nodes"]}:
            np.testing.assert_allclose(
                [row.x, row.y, row.z],
                lookup.loc[row.node_id, physical.XYZ].to_numpy(float),
                atol=1e-12,
                rtol=0,
            )


def test_daughters_keep_exact_attachment_id_and_incoming_physical_tangent():
    saved, settings = invented_initial(5)
    result = physical.replay_physical_steps(saved, settings)
    nodes = result["nodes"].set_index("node_id")
    organs = {o["organ_id"]: o for o in result["diagnostics"]["organs"]}
    for organ in saved.payload["organs"]:
        if organ["order"] <= 1:
            continue
        chain = nodes.loc[nodes.organ_id.eq(organ["organ_id"])].sort_values(
            "segment_rank"
        )
        assert chain.iloc[0].parent_id == organ["parent_id"]
        receipt = organs[organ["organ_id"]]
        parent = nodes.loc[organ["parent_id"]]
        incoming = physical.unit(
            parent[physical.XYZ].to_numpy(float)
            - nodes.loc[int(parent.parent_id), physical.XYZ].to_numpy(float)
        )
        np.testing.assert_allclose(
            receipt["parent_tangent"], incoming, rtol=0, atol=1e-12
        )
        steps = [
            s
            for s in result["diagnostics"]["construction_steps"]
            if s["organ_id"] == organ["organ_id"]
        ]
        np.testing.assert_array_equal(steps[0]["start_xyz"], parent[physical.XYZ])


def test_inactive_orders_use_legacy_rng_and_directional_operator(monkeypatch):
    saved, settings = invented_initial(5)
    calls = []
    original = legacy.step_rng

    def observed(seed, organ, index, purpose):
        calls.append((seed, organ, index, purpose))
        return original(seed, organ, index, purpose)

    monkeypatch.setattr(legacy, "step_rng", observed)
    result = physical.replay_physical_steps(saved, settings, direction_seed=123)
    assert {call[1] for call in calls} == {3, 4, 5}
    assert {call[0] for call in calls} == {123}
    for receipt in result["diagnostics"]["organs"]:
        if receipt["order"] != 2:
            assert receipt["integration_route"] == legacy.VERSION
            assert (
                sum(
                    r["organ_id"] == receipt["organ_id"]
                    for r in result["diagnostics"]["construction_steps"]
                )
                == 2
            )


def test_surface_projection_receipts_and_first_insertion_only_one_microstep(
    monkeypatch,
):
    saved, settings = invented_initial()
    monkeypatch.setattr(
        physical, "insertion_heading", lambda *args: np.array([0.0, 0.0, 1.0])
    )
    monkeypatch.setattr(
        physical, "fichtl_proposal", lambda *args: (np.array([0.0, 0.0, 1.0]), {})
    )
    result = physical.replay_physical_steps(saved, settings, max_step_cm=1.0)
    records = result["diagnostics"]["physical_steps"]
    assert any(r["boundary_intervention"] for r in records)
    assert all(r["accepted_endpoint"][2] <= 20.0 for r in records)
    assert all("boundary_ulp_nudges" in r for r in records)
    assert len(records) > len(
        next(o for o in saved.payload["organs"] if o["order"] == 2)[
            "construction_steps"
        ]["lengths_cm"]
    )
    assert all(
        r["corrected_segment_length_cm"]
        == (r["length_cm"] if r["boundary_intervention"] else 0.0)
        for r in records
    )


def test_direction_seed_changes_only_geometry_and_is_reproducible():
    saved, settings = invented_initial()
    original_identity = digest(saved.payload)
    first = physical.replay_physical_steps(saved, settings, direction_seed=7)
    second = physical.replay_physical_steps(saved, settings, direction_seed=8)
    again = physical.replay_physical_steps(saved, settings, direction_seed=7)
    pd.testing.assert_frame_equal(first["nodes"], again["nodes"], check_exact=True)
    pd.testing.assert_frame_equal(
        first["nodes"].drop(columns=physical.XYZ),
        second["nodes"].drop(columns=physical.XYZ),
        check_exact=True,
    )
    assert not first["nodes"][physical.XYZ].equals(second["nodes"][physical.XYZ])
    assert first["diagnostics"]["source_sampler_seed"] == 42
    assert first["diagnostics"]["direction_seed"] == 7
    assert digest(saved.payload) == original_identity


def test_explicit_direction_seed_empty_orders_matches_legacy_helper(monkeypatch):
    saved, settings = invented_initial()
    calls = []
    original = legacy._replay_organ

    def observed(*args, **kwargs):
        calls.append(args[4])
        return original(*args, **kwargs)

    monkeypatch.setattr(physical, "_replay_organ", observed)
    result = physical.replay_physical_steps(
        saved, settings, orders=(), direction_seed=19
    )
    assert calls == [19, 19]
    assert not result["diagnostics"]["physical_steps"]
    assert len(result["nodes"]) == len(saved.payload["nodes"])


@pytest.mark.parametrize(
    "updates",
    [
        dict(max_step_cm=0),
        dict(max_step_cm=True),
        dict(max_step_cm=float("inf")),
        dict(orders=(1,)),
        dict(orders=(2, 2)),
        dict(orders=(True,)),
        dict(orders=(4,)),
        dict(direction_seed=-1),
        dict(direction_seed=True),
        dict(direction_seed=3.5),
        dict(surface_z=0.0),
        dict(boundary_policy="clip"),
    ],
)
def test_invalid_physical_arguments_fail_closed(updates):
    saved, settings = invented_initial()
    with pytest.raises(ValueError):
        physical.replay_physical_steps(saved, settings, **updates)


@pytest.mark.parametrize("defect", ["seed", "sampler", "boundary", "hash", "settings"])
def test_initial_authentication_cannot_be_bypassed_by_direction_seed(defect):
    saved, settings = invented_initial()
    if defect == "seed":
        saved.payload["parameters"]["random_seed"] = 100
    elif defect == "sampler":
        saved.payload["organs"][1]["construction_steps"]["sampler"]["seed"] = 100
    elif defect == "boundary":
        saved.payload["organs"][1]["construction_steps"]["positioned_boundary_xyz"][1][
            0
        ] += 0.1
    elif defect == "settings":
        settings["base_diameter"] += 0.1
    elif defect == "hash":
        saved.payload["nodes"][0]["x"] += 1.0
    if defect != "hash":
        saved.sha256 = digest(saved.payload)
    with pytest.raises(ValueError):
        physical.replay_physical_steps(saved, settings, direction_seed=100)


def test_active_insertion_exactly_preserves_legacy_assigned_heading():
    saved, settings = invented_initial()
    baseline = legacy.replay_construction_steps(
        saved, "D", settings, "minimum_angle_projection"
    )
    result = physical.replay_physical_steps(saved, settings)
    old = next(r for r in baseline["diagnostics"]["organs"] if r["order"] == 2)
    new = next(r for r in result["diagnostics"]["organs"] if r["order"] == 2)
    assert old["assigned_heading"] == new["assigned_heading"]
    steps = result["diagnostics"]["physical_steps"]
    assert steps[0]["proposed_heading"] == new["assigned_heading"]
    # Continuation begins at the next capped microstep, inside the first old interval.
    assert steps[1]["construction_step_index"] == 0
    assert "innovations_sha256" in steps[1]


def test_all_physical_vertices_are_exported_with_no_chord_shortcuts():
    saved, settings = invented_initial()
    result = physical.replay_physical_steps(saved, settings, max_step_cm=0.6)
    for record in result["diagnostics"]["physical_steps"]:
        chain = (
            result["nodes"]
            .loc[result["nodes"].organ_id.eq(record["organ_id"])]
            .sort_values("segment_rank")
        )
        endpoint = np.asarray(record["accepted_endpoint"])
        assert (
            np.min(
                np.linalg.norm(chain[physical.XYZ].to_numpy(float) - endpoint, axis=1)
            )
            < 1e-12
        )
        arcs = chain.length.cumsum().to_numpy()
        assert np.min(np.abs(arcs - record["arc_end_cm"])) < 1e-12
    fragments = [
        f for f in result["diagnostics"]["graph_fragments"] if f["organ_id"] == 2
    ]
    assert all(
        -1e-12 <= f["start_fraction"] <= f["end_fraction"] <= 1.0 + 1e-12
        for f in fragments
    )


@pytest.mark.parametrize(
    "maximum,orders,cap,seed,expected",
    [
        (
            3,
            (2,),
            2.0,
            None,
            "75d28a08605a7d5bab1956f50c5412d3f21c90d104e1e01b0d3b04f6226ba5a5",
        ),
        (
            5,
            (2, 5),
            0.75,
            19,
            "45e012549d3c985f1177815642b1ff986a52d22cd03d205cac1bdd00c6e0bcc4",
        ),
        (
            3,
            (),
            2.0,
            None,
            "5c4e72be13f2bb1f0cebfc66eba71ded2a700caef706d647862a3eb3039b0838",
        ),
    ],
)
def test_cap_default_output_bytes_match_pre_ou_source_epoch(
    maximum, orders, cap, seed, expected, tmp_path
):
    # Recorded from public cap module SHA256 e4e7e4b545476e5e9944b1e094809b51780cfb232b8bfe2d78a7521f7434a16a,
    # before OU implementation. Includes nodes, edges, proposals and diagnostics.
    saved, settings = invented_initial(maximum)
    result = physical.replay_physical_steps(
        saved, settings, orders=orders, max_step_cm=cap, direction_seed=seed
    )
    encoded = {
        key: value.to_dict("records") if hasattr(value, "to_dict") else value
        for key, value in result.items()
    }
    from tests.portable_hash_cases import historical_payload
    from tests.hash_failure_diagnostics import canonical_bytes

    reference = historical_payload(
        tmp_path, "pre_ou_physical", ["physical", maximum, orders, cap, seed]
    )
    # expected retains the original cross-runtime digest as provenance only.
    # Exact same-runtime bytes remain the acceptance contract, with no tolerance.
    try:
        assert canonical_bytes(encoded) == canonical_bytes(reference)
    except AssertionError:
        from tests.hash_failure_diagnostics import record_failure

        record_failure(
            "physical-cap", {"actual": encoded, "reference": reference}, expected
        )
        raise


@pytest.mark.parametrize("cap", [2.0, 1.0, 0.5])
def test_ou_finite_geometry_conservation_and_deterministic_at_three_caps(cap):
    saved, settings = invented_initial(5)
    kwargs = dict(
        max_step_cm=cap,
        curvature_sd_rad_cm=0.12,
        correlation_length_cm=4.0,
        tropism_drift_rad_cm=0.08,
        row_drift_rad_cm=0.03,
        orders=(2, 5),
        direction_seed=12,
    )
    first = physical.replay_physical_steps(saved, settings, **kwargs)
    again = physical.replay_physical_steps(saved, settings, **kwargs)
    assert first["diagnostics"] == again["diagnostics"]
    for key in ("nodes", "edges", "proposals"):
        pd.testing.assert_frame_equal(first[key], again[key], check_exact=True)
    assert first["diagnostics"]["route"] == physical.OU_VERSION
    validate_geometry(first["nodes"], first["edges"], 20.0)
    old_traits = measured_traits(pd.DataFrame(saved.payload["nodes"]))
    for oid, traits in measured_traits(first["nodes"]).items():
        np.testing.assert_allclose(traits, old_traits[oid], rtol=1e-9, atol=0)
    steps = first["diagnostics"]["physical_steps"]
    assert set(step["order"] for step in steps) == {2, 5}
    assert all(step["candidate_selection"] == "none_unselected_ou" for step in steps)
    assert all(step["length_cm"] <= cap + 1e-14 for step in steps)
    assert (
        first["diagnostics"]["curvature_process"]["boundary_latent_state"]
        == "retained_after_projection"
    )
    for organ in first["diagnostics"]["organs"]:
        if organ["order"] in (2, 5):
            organ_steps = [
                step for step in steps if step["organ_id"] == organ["organ_id"]
            ]
            assert organ_steps[0]["proposed_heading"] == organ["assigned_heading"]
            assert not organ_steps[0]["integrated_turn_applied"]
            assert organ_steps[1]["integrated_turn_applied"]
            assert (
                organ_steps[0]["curvature_end_rad_cm"]
                != organ_steps[0]["curvature_start_rad_cm"]
            )
        else:
            assert organ["integration_route"] == legacy.VERSION


def test_ou_fragment_subdivision_changes_no_physical_proposal_or_old_coordinates():
    saved, settings = invented_initial()
    parent = next(o for o in saved.payload["organs"] if o["order"] == 2)
    changed = subdivide_same_interval(saved, parent["node_ids"][1])
    kwargs = dict(
        curvature_sd_rad_cm=0.14, correlation_length_cm=3.0, tropism_drift_rad_cm=0.05
    )
    baseline = physical.replay_physical_steps(saved, settings, **kwargs)
    result = physical.replay_physical_steps(changed, settings, **kwargs)
    assert (
        baseline["diagnostics"]["physical_steps"]
        == result["diagnostics"]["physical_steps"]
    )
    pd.testing.assert_frame_equal(
        baseline["proposals"], result["proposals"], check_exact=True
    )
    original_ids = [row["node_id"] for row in saved.payload["nodes"]]
    np.testing.assert_array_equal(
        baseline["nodes"].set_index("node_id").loc[original_ids, physical.XYZ],
        result["nodes"].set_index("node_id").loc[original_ids, physical.XYZ],
    )


def test_ou_zero_curvature_and_zero_drift_straight_from_insertion():
    saved, settings = invented_initial()
    result = physical.replay_physical_steps(
        saved,
        settings,
        curvature_sd_rad_cm=0.0,
        correlation_length_cm=3.0,
        max_step_cm=0.5,
    )
    organ = next(o for o in result["diagnostics"]["organs"] if o["order"] == 2)
    for step in result["diagnostics"]["physical_steps"]:
        np.testing.assert_allclose(
            step["proposed_heading"], organ["assigned_heading"], rtol=0, atol=1e-14
        )
        np.testing.assert_array_equal(step["curvature_start_rad_cm"], [0.0, 0.0])
        np.testing.assert_array_equal(step["curvature_end_rad_cm"], [0.0, 0.0])
        assert not step["boundary_intervention"]


def test_ou_zero_curvature_downward_drift_turns_toward_down_and_row_sign_is_frozen(
    monkeypatch,
):
    saved, settings = invented_initial()
    monkeypatch.setattr(
        physical, "insertion_heading", lambda *args: np.array([np.sqrt(0.75), 0.5, 0.0])
    )
    result = physical.replay_physical_steps(
        saved,
        settings,
        curvature_sd_rad_cm=0.0,
        correlation_length_cm=3.0,
        tropism_drift_rad_cm=0.1,
        row_drift_rad_cm=0.03,
        max_step_cm=0.5,
    )
    steps = result["diagnostics"]["physical_steps"]
    assert all(step["row_drift_frozen_sign"] == 1.0 for step in steps)
    assert steps[0]["proposed_heading"][2] == 0.0
    assert all(step["proposed_heading"][2] < 0 for step in steps[1:])
    assert steps[-1]["proposed_heading"][2] < steps[1]["proposed_heading"][2]


def test_ou_projection_retains_latent_curvature_and_advances_first_chord(monkeypatch):
    saved, settings = invented_initial()
    monkeypatch.setattr(
        physical, "insertion_heading", lambda *args: np.array([0.0, 0.0, 1.0])
    )
    result = physical.replay_physical_steps(
        saved,
        settings,
        curvature_sd_rad_cm=0.001,
        correlation_length_cm=3.0,
        max_step_cm=0.5,
    )
    steps = result["diagnostics"]["physical_steps"]
    assert any(step["boundary_intervention"] for step in steps)
    assert steps[0]["integrated_curvature_rad"] != [0.0, 0.0]
    assert steps[0]["proposed_heading"] == [0.0, 0.0, 1.0]
    for previous, current in zip(steps, steps[1:]):
        assert current["curvature_start_rad_cm"] == previous["curvature_end_rad_cm"]
    assert all(step["accepted_endpoint"][2] <= 20.0 for step in steps)


def test_ou_direction_seed_repeats_changes_geometry_and_retains_source_sampler():
    saved, settings = invented_initial()
    kwargs = dict(curvature_sd_rad_cm=0.1, correlation_length_cm=3.0)
    a = physical.replay_physical_steps(saved, settings, direction_seed=10, **kwargs)
    b = physical.replay_physical_steps(saved, settings, direction_seed=11, **kwargs)
    repeat = physical.replay_physical_steps(
        saved, settings, direction_seed=10, **kwargs
    )
    pd.testing.assert_frame_equal(a["nodes"], repeat["nodes"], check_exact=True)
    assert not a["nodes"][physical.XYZ].equals(b["nodes"][physical.XYZ])
    pd.testing.assert_frame_equal(
        a["nodes"].drop(columns=physical.XYZ),
        b["nodes"].drop(columns=physical.XYZ),
        check_exact=True,
    )
    assert (
        a["diagnostics"]["source_sampler_seed"]
        == b["diagnostics"]["source_sampler_seed"]
        == 42
    )


@pytest.mark.parametrize(
    "updates",
    [
        dict(curvature_sd_rad_cm=0.1),
        dict(correlation_length_cm=3.0),
        dict(tropism_drift_rad_cm=0.1),
        dict(row_drift_rad_cm=0.1),
        dict(curvature_sd_rad_cm=0.1, correlation_length_cm=3.0, orders=()),
    ],
)
def test_inactive_and_incomplete_ou_arguments_fail_closed(updates):
    saved, settings = invented_initial()
    with pytest.raises(ValueError):
        physical.replay_physical_steps(saved, settings, **updates)
