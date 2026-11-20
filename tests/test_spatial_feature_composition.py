"""The eight independent feature choices share the canonical caller contract."""

import json

import numpy as np
import pytest

from deeprootgen.cli import simulate
from deeprootgen.data_model import RootConfig, explain_config
from deeprootgen.data_model.simulation_form import simulation_controls, simulation_document
from deeprootgen.model import RootSystemSimulation
from scripts.validation.native_engine_matrix import spatial_cases


@pytest.mark.parametrize("label,config", list(spatial_cases()), ids=[label for label, _ in spatial_cases()])
def test_spatial_feature_matrix_cli_api_and_advanced_form(label, config, tmp_path):
    parameters = RootConfig.model_validate(config)  # same loader used from a notebook
    api = RootSystemSimulation(random_seed=parameters.random_seed)
    api.run(parameters)
    nodes, edges = api.G.as_df()
    assert np.isfinite(nodes[["x", "y", "z", "diameter", "length"]]).all().all()
    assert nodes.plant_id.unique().tolist() == [1]
    assert not nodes.invalid_root.any()
    assert set(edges.parent_id).issubset(nodes.node_id) and set(edges.child_id).issubset(nodes.node_id)
    assert list(api.result.organ_table.groupby("order").size().index) == [1, 2, 3, 4, 5]
    assert api.result.organ_table.mass_g.gt(0).all()

    fields = ["random_seed", "simulation_tag", "primary_root_count", "advanced_settings"]
    converted = simulation_document(dict(zip(fields, simulation_controls(config, fields))))
    assert RootConfig.model_validate(converted) == parameters
    original, replay = tmp_path / "first", tmp_path / "replay"
    first = simulate(converted, original)
    second = simulate(original / "parameters.json", replay)
    for key in ("effective_model_sha256", "run_identity_sha256"):
        assert first["model_identity"][key] == second["model_identity"][key] == api.result.metadata[key]
    assert (original / "nodes.csv").read_text() == nodes.to_csv(index=False)
    assert (original / "edges.csv").read_text() == edges.to_csv(index=False)
    for name in ("nodes.csv", "edges.csv", "organs.csv", "root_summary.json", "branching.json"):
        assert (original / name).read_bytes() == (replay / name).read_bytes()

    resolved = explain_config(config)
    files = (("row_alignment.json", "row_alignment_per_cm", "-R1", [2]),
             ("vine_origin_catalogue.json", "vine_origin_catalogue", "-O1", [1]))
    for file, field, flag, orders in files:
        expected = flag in label
        assert (original / file).exists() == expected == (replay / file).exists()
        assert resolved["consumers"][field]["orders"] == (orders if expected else [])
        if expected:
            assert (original / file).read_bytes() == (replay / file).read_bytes()
    archived = json.loads((original / "parameters.json").read_text())
    assert archived["features"]["primary_origins"]["settings"] == config["features"]["primary_origins"]["settings"]
    branching = json.loads((replay / "branching.json").read_text())["by_parent_order"]["2"]
    assert ("length_poisson_sites" in branching) == ("-B1" in label)
    assert resolved["consumers"]["mean_spacing_cm"]["orders"] == ([2] if "-B1" in label else [])


def test_poisson_and_relocation_can_own_distinct_parent_orders():
    config = dict(spatial_cases())["spatial-R1-O1-B1"]
    config["features"]["attachment_relocation"] = dict(enabled=True, settings=dict(orders=[2], distal_fraction=.23))
    simulation = RootSystemSimulation(random_seed=config["random_seed"])
    simulation.run(config)
    assert simulation.result.organ_table.invalid_root.sum() == 0
    assert "length_poisson_sites" in simulation.result.diagnostics["branching"]["by_parent_order"]["2"]
