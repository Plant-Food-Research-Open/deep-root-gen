"""Algorithm checks for the optional research kernel, not biological validation."""

import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import RootSimulationModel
from deeprootgen.model import RootSystemSimulation
from deeprootgen.utils.tropism import insertion_heading, sample_heading


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


def test_prechange_legacy_golden():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/fichtl_legacy_golden.json").read_text()
    )
    for case in fixture["cases"]:
        p = RootSimulationModel(**case["parameters"])
        sim = RootSystemSimulation(random_seed=p.random_seed)
        sim.run(p)
        for table, expected in zip(sim.G.as_df(), case["csv_sha256"]):
            assert (
                hashlib.sha256(table.to_csv(index=False).encode()).hexdigest()
                == expected
            )
