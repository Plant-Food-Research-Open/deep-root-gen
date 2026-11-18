"""Public entry points and migration boundary for the one supported configuration."""
import json
from pathlib import Path

import pandas as pd
import pytest

from deeprootgen.cli import simulate
from deeprootgen.data_model import RootConfig, explain_config, resolve_config
from deeprootgen.data_model.migration import convert_input
from deeprootgen.model import RootSystemSimulation
from deeprootgen.run_records import tracked_run


ROOT = Path(__file__).resolve().parents[1]


def simple():
    return json.loads((ROOT / "examples/synthetic_minimal.json").read_text())


def test_archive_files_require_explicit_conversion(tmp_path):
    archived = json.loads((ROOT / "tests/fixtures/migration_inputs/synthetic_minimal.json").read_text())
    with pytest.raises(ValueError, match="schema_version 4"):
        simulate(archived, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()
    original = dict(archived)
    parsed = RootConfig.model_validate(convert_input(archived))
    assert archived == original
    assert parsed.parameters.threshold_root_diameter_cm == original["fine_root_threshold"]
    assert parsed.parameters.min_branching_diameter_cm == 0
    assert parsed.parameters.primary_root_count == original["outer_root_num"] + original["inner_root_num"]


@pytest.mark.parametrize("value", [True, 2.0, "2", {"mean": 2, "sd": 1}])
def test_maximum_order_is_one_strict_integer(value):
    config = simple()
    config["parameters"]["max_order"] = value
    with pytest.raises(ValueError, match="max_order"):
        resolve_config(config)


def test_terminal_order_does_not_consume_branch_minimum():
    source = simple()
    source["parameters"]["max_order"] = 1
    old = explain_config(source)["hashes"]["effective_model_sha256"]
    source["parameters"]["min_branching_diameter_cm"] = 0.93
    assert explain_config(source)["hashes"]["effective_model_sha256"] == old


def test_curved_lateral_uses_row_axial_insertion():
    source = simple()
    source["parameters"].update(max_order=2, soil_surface_z_cm=0., floor_threshold=.3, ceiling_threshold=.8)
    source["features"]["curvature"] = {
        "enabled": True, "settings": {"by_order": {"2": dict(
            law="correlated_curvature", step_cm=1., curvature_sd_rad_cm=.005,
            correlation_length_cm=8., downward_drift_per_cm=.02,
            boundary="reflect_downward", first_interval="integrate",
            initial_heading="insertion_angle", insertion_mean_deg=45., insertion_sd_deg=8.,
        )}},
    }
    by_order = source["features"]["curvature"]["settings"]["by_order"]
    by_order["1"] = {key: value for key, value in by_order["2"].items() if not key.startswith("insertion_")}
    by_order["1"]["initial_heading"] = "scaffold_chord"
    source["features"]["direction"] = {"enabled": True, "settings": {"post_correction": "pure_surface_check"}}
    source["features"]["insertion"] = {"enabled": True, "settings": {"row_axial_kappa_by_order": {"2": 8.}}}
    resolved = resolve_config(source)
    assert resolved.laws.direction[2]["row_axial_kappa"] == 8.
    model = RootSystemSimulation(random_seed=source["random_seed"])
    model.run(source)
    reports = [root.axis_state.curve.receipt["row_axial_insertion"] for root in model.organs[2]
               if root.axis_state.curve is not None]
    assert reports
    for report in reports:
        assert report["new_polar_angle_deg"] == pytest.approx(report["old_polar_angle_deg"])
    assert any(report["new_heading"] != report["old_heading"] for report in reports)


def test_tracked_summary_and_reload_agree_with_direct_api(tmp_path):
    config = simple()
    # Exercise the structural defaults, including exact equality in the reporting bin.
    p = config["parameters"]
    p.pop("min_branching_diameter_cm", None)
    p.pop("threshold_root_diameter_cm", None)
    p.update(base_diameter=.25, apex_diameter=.25, diameter_reduction=0.)
    sim = RootSystemSimulation(random_seed=config["random_seed"])
    sim.run(config)
    expected = sim.result.metadata["root_summary"]
    assert expected["achieved_root_ratio_biomass"] == expected["achieved_root_ratio_length"] == 1.
    assert expected["diameter_classes"]["above"] == dict(length_cm=0., dry_biomass_g=0.)
    assert expected["by_order"][0]["root_count"] == p["primary_root_count"]
    source, replay = tmp_path / "seeded", tmp_path / "replay"
    first = tracked_run(config, source, label="canonical-direct")
    second = tracked_run(source / "parameters.json", replay, label="canonical-replay")
    assert json.loads((source / "root_summary.json").read_text()) == expected
    for key in ("effective_model_sha256", "run_identity_sha256"):
        assert first["model_identity"][key] == second["model_identity"][key]
    for name in ("root_summary.json", "nodes.csv", "edges.csv"):
        assert (source / name).read_bytes() == (replay / name).read_bytes()
    nodes, _ = sim.G.as_df()
    assert list(pd.read_csv(source / "nodes.csv")["node_id"]) == list(nodes.node_id)
