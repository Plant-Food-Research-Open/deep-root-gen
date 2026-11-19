from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deeprootgen.model import RootSystemSimulation
from deeprootgen.research.core_observation import (
    qualify_root_segments,
    predict_core_observations,
)
from deeprootgen.research.neighbourhood import (
    generate_neighbourhood,
    neighbourhood_plan,
)


ORIGINS = [(x, y) for x in (-1, 0, 1) for y in (-2, 0, 2)]


def test_seed_assignment_is_reproducible_and_invariant_to_input_order():
    sites = neighbourhood_plan(ORIGINS, 42, "independent")
    assert len(set(s.seed for s in sites)) == 9
    assert sites[4].seed == 42
    assert tuple(reversed(sites)) == neighbourhood_plan(
        ORIGINS[::-1], 42, "independent"
    )
    assert {s.seed for s in neighbourhood_plan(ORIGINS, 42)} == {42}


@pytest.mark.parametrize(
    "origins,seed,mode",
    [
        ([(1, 2)], 1, "translated"),
        ([(0, 0), (0, 0)], 1, "translated"),
        ([(0, 0), (0, np.inf)], 1, "independent"),
        ([(0, 0)], None, "independent"),
        ([(0, 0)], -1, "independent"),
        ([(0, 0)], 1, "rotated"),
    ],
)
def test_invalid_plan(origins, seed, mode):
    with pytest.raises(ValueError):
        neighbourhood_plan(origins, seed, mode)


def test_native_graph_identity_translation_and_core_additivity():
    example = Path(__file__).resolve().parents[1] / "examples/synthetic_minimal.json"
    spec = json.loads(example.read_text())
    original = deepcopy(spec)
    clone = generate_neighbourhood(spec, ORIGINS)
    independent = generate_neighbourhood(spec, ORIGINS, "independent")
    assert spec == original
    assert clone.plants.run_identity_sha256.nunique() == 1
    assert independent.plants.run_identity_sha256.nunique() == 9
    for graph in (clone, independent):
        assert graph.nodes.node_id.is_unique
        lookup = graph.nodes.set_index("node_id").plant_id
        np.testing.assert_array_equal(
            lookup[graph.edges.parent_id], lookup[graph.edges.child_id]
        )
        assert graph.nodes.query("parent_id == -1").plant_id.nunique() == len(ORIGINS)
        for site in graph.plants.itertuples():
            direct = RootSystemSimulation(
                random_seed=site.seed, simulation_tag=spec["simulation_tag"]
            )
            direct.run(dict(spec, random_seed=site.seed))
            nodes, _ = direct.G.as_df()
            actual = graph.nodes[graph.nodes.plant_id == site.plant_id]
            np.testing.assert_allclose(
                actual[["x", "y", "z"]],
                nodes[["x", "y", "z"]] + [site.x_cm, site.y_cm, 0],
            )
            assert (
                site.run_identity_sha256
                == direct.result.metadata["run_identity_sha256"]
            )
        support = qualify_root_segments(
            graph.nodes,
            graph.edges,
            coordinate_frame="soil-cm",
            fine_diameter_max_mm=2,
            dry_density_g_cm3=0.4,
        )
        cores = pd.DataFrame(
            [
                dict(
                    core_id="synthetic",
                    x_cm=0.0,
                    y_cm=0.0,
                    z_lower_cm=-50.0,
                    z_upper_cm=0.0,
                    radius_cm=10.0,
                    sampled=True,
                )
            ]
        )
        result = predict_core_observations(support, cores, by_plant=True)
        assert result.cores.total_rld_cm_cm3.iloc[0] > 0
        assert result.by_plant.total_rld_cm_cm3.sum() == pytest.approx(
            result.cores.total_rld_cm_cm3.iloc[0]
        )


def test_cli_exports_replay_inputs_to_new_directory(tmp_path):
    from deeprootgen.cli import main

    config = Path(__file__).resolve().parents[1] / "examples/synthetic_minimal.json"
    origins = tmp_path / "offsets.json"
    origins.write_text(json.dumps(ORIGINS))
    out = tmp_path / "garden"
    args = [
        "neighbourhood",
        "--config",
        str(config),
        "--origins",
        str(origins),
        "--outdir",
        str(out),
        "--mode",
        "independent",
    ]
    assert main(args) == 0
    assert json.loads((out / "manifest.json").read_text())["plant_count"] == 9
    assert json.loads((out / "origins.json").read_text()) == json.loads(
        origins.read_text()
    )
    assert json.loads((out / "config.json").read_text()) == json.loads(
        config.read_text()
    )
    assert len(pd.read_csv(out / "plants.csv").seed.unique()) == 9
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 1
