"""Input boundary: one parser; no requested option can silently disappear."""

import copy
import json
from pathlib import Path

import pytest

from deeprootgen.archive.export import main, simulate
from deeprootgen.data_model import (
    RootSimulationConfig,
    RootSimulationConfigV3,
    RootSimulationModel,
    load_json_config,
)
from deeprootgen.archive.resolution import parse_config

ROOT = Path(__file__).resolve().parents[1]
FLAT = json.loads((ROOT / "tests/fixtures/migration_inputs/synthetic_minimal.json").read_text())
V3 = json.loads((ROOT / "tests/fixtures/migration_inputs/design/native_feature_options.proposed.json").read_text())


def test_duplicate_json_keys_fail_at_every_level():
    for text in (
        '{"random_seed": 1, "random_seed": 2}',
        '{"schema_version": 3, "features": {"curvature": {"enabled": false, "enabled": true}}}',
        '{"a": [{"b": 1, "b": 1}]}',
    ):
        with pytest.raises(ValueError, match="Duplicate JSON key"):
            load_json_config(text)


def test_cli_rejects_duplicate_keys_before_creating_output(tmp_path, capsys):
    text = (ROOT / "tests/fixtures/migration_inputs/synthetic_minimal.json").read_text().replace(
        '"random_seed": 42,', '"random_seed": 42, "random_seed": 43,'
    )
    config = tmp_path / "dup.json"
    config.write_text(text)
    with pytest.raises(SystemExit) as exit_info:
        main(["simulate", "--config", str(config), "--outdir", str(tmp_path / "out")])
    assert exit_info.value.code == 1
    assert "Duplicate JSON key" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("key", ["features", "parameters", "limits", "construction", "trajectory"])
def test_flat_input_cannot_silently_discard_versioned_keys(key, tmp_path):
    spec = dict(FLAT, **{key: {"curvature": {"enabled": True}}})
    with pytest.raises(ValueError, match="schema_version"):
        parse_config(spec)
    # Direct API construction is protected too, not only raw parsing.
    with pytest.raises(ValueError, match="schema_version"):
        RootSimulationModel(**spec)
    with pytest.raises(ValueError, match="schema_version"):
        simulate(spec, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_flat_unknown_nonreserved_keys_keep_historical_behaviour():
    parsed = parse_config(dict(FLAT, historical_extra=1))
    assert isinstance(parsed, RootSimulationModel)
    assert not hasattr(parsed, "historical_extra")


@pytest.mark.parametrize("version", [True, "3", 3.0, 1, 4])
def test_schema_version_must_be_a_supported_integer(version):
    with pytest.raises(ValueError, match="schema_version"):
        parse_config(dict(V3, schema_version=version))


def test_schema_versions_route_to_one_validated_model_each():
    assert isinstance(parse_config(copy.deepcopy(V3)), RootSimulationConfigV3)
    fixture = json.loads((ROOT / "tests/fixtures/native_execution_contracts.json").read_text())
    record = next(r for r in fixture["records"] if r["contract"] == "legacy")
    v2 = dict(
        schema_version=2,
        random_seed=record["seed"],
        construction=dict(kind="native", parameters=record["parameters"]),
    )
    assert isinstance(parse_config(v2), RootSimulationConfig)
    assert isinstance(parse_config(json.dumps(V3)), RootSimulationConfigV3)


def mutate(path, value):
    spec = copy.deepcopy(V3)
    target = spec
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return spec


@pytest.mark.parametrize(
    "spec",
    [
        mutate(("features", "curvature", "enabled"), "true"),
        mutate(("features", "curvature", "enabled"), 1),
        mutate(("features", "curvature", "enable"), True),
        mutate(("features", "curvatures"), {"enabled": False}),
        mutate(("features", "curvature", "settings", "by_order", "1", "step"), 2.0),
        mutate(("features", "curvature", "settings", "by_order", "01"), {}),
        mutate(("features", "curvature", "settings", "by_order", "1", "step_cm"), float("nan")),
        mutate(("features", "taper", "settings", "by_order", "1", "base_cm", "mean"), True),
        mutate(("features", "lengths", "settings", "by_order", "2", "mean"), 2.0),
        mutate(("parameters", "random_seed"), 42),
        mutate(("parameters", "simulation_tag"), "x"),
        mutate(("parameters", "root_ratio"), 0.5),
        mutate(("parameters", "research_primary_yaw_mean_deg"), 10.0),
        mutate(("parameters", "enable_soil"), False),
        mutate(("parameters", "max_order"), 3.0),
        mutate(("parameters", "base_diameter"), float("inf")),
        mutate(("parameters", "unknown_parameter"), 1),
        mutate(("unknown_top_level",), 1),
        mutate(("random_seed",), True),
        mutate(("limits", "max_organs"), 0),
    ],
)
def test_schema3_rejects_unknown_misspelled_nonfinite_and_noncanonical(spec):
    with pytest.raises(ValueError):
        parse_config(spec)


def test_schema3_disabled_blocks_validate_shape_but_not_completeness():
    spec = copy.deepcopy(V3)
    # Partial settings are allowed while disabled; they are retained, not run.
    spec["features"]["curvature"]["settings"]["by_order"]["1"] = {"step_cm": 3.0}
    spec["features"]["taper"]["settings"] = {"by_order": {"2": {"midpoint_diameter_fraction": 7.0}}}
    parsed = parse_config(spec)
    assert parsed.features.curvature.settings.by_order["1"].step_cm == 3.0
    del spec["features"]["branching"]
    assert parse_config(spec).features.branching.enabled is False


@pytest.mark.parametrize("key", ["curvature", "taper", "feature", "Features", "FEATURES", "limit", "Parameters"])
def test_flat_input_rejects_feature_blocks_and_close_misspellings(key):
    spec = dict(FLAT, **{key: {"enabled": True}})
    with pytest.raises(ValueError, match="schema_version"):
        parse_config(spec)
    with pytest.raises(ValueError, match="schema_version"):
        RootSimulationModel(**spec)
