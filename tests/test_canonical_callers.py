"""Support-surface contracts without starting Dash, Prefect or inference services."""
import ast
from copy import deepcopy
import json
from pathlib import Path

import pytest
import yaml

from deeprootgen.data_model.canonical import RootConfig
from deeprootgen.data_model.migration import convert_input
from deeprootgen.data_model.resolution import resolve_config
from deeprootgen.data_model.simulation_form import simulation_controls, simulation_document
from deeprootgen.research.notebook_inputs import vineyard_trial

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
HISTORICAL = ROOT / "tests/fixtures/migration_inputs"


@pytest.mark.parametrize("source", [
    "synthetic_minimal.json", "design/native_features_fully_replaced.json",
    "research/native_steps_synthetic.json", "research/native_cohort_synthetic.json",
])
def test_offline_conversion_matches_current_examples(source):
    old = json.loads((HISTORICAL / source).read_text())
    untouched = deepcopy(old)
    generated = convert_input(old)
    assert generated == json.loads((EXAMPLES / source).read_text())
    assert old == untouched
    assert generated["parameters"]["min_branching_diameter_cm"] == 0.
    resolve_config(generated)


def test_conversion_reports_unmapped_fields():
    old = json.loads((HISTORICAL / "synthetic_minimal.json").read_text())
    with pytest.raises(ValueError, match="Unmapped"):
        convert_input(dict(old, diameter_mean=0.5))
    with pytest.raises(ValueError, match="soil"):
        convert_input(dict(old, enable_soil=True))


@pytest.mark.parametrize("example", ["research/native_steps_synthetic.json", "design/native_allocation_targets.json"])
def test_form_defaults_and_upload_roundtrip_preserve_optional_parameters(example):
    form = yaml.safe_load((ROOT / "app/conf/simulation_form/common.yaml").read_text())
    rows = form["components"]["parameters"]["children"]
    defaults = {row["param"]: row["kwargs"].get("value") for row in rows}
    resolve_config(simulation_document(defaults))
    original = json.loads((EXAMPLES / example).read_text())
    fields = list(defaults)
    values = simulation_controls(original, fields)
    loaded = simulation_document(dict(zip(fields, values)))
    assert RootConfig.model_validate(loaded) == RootConfig.model_validate(original)
    assert "enable_soil" not in loaded["parameters"]


def test_notebook_sample_builds_canonical_configuration():
    p = ROOT / "notebooks/grapevine_wong_2026/2_wong_2026_calibration_grid_search.ipynb"
    cells = json.loads(p.read_text())["cells"]
    settings = next(''.join(c['source']) for c in cells if 'BASE_PARAMETERS = dict(' in ''.join(c['source']))
    tree = ast.parse(settings)
    assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                      and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "BASE_PARAMETERS")
    parsed = {arg.arg: (42 if arg.arg == "random_seed" else ast.literal_eval(arg.value))
              for arg in assignment.value.keywords}
    config = vineyard_trial(**parsed)
    resolve_config(config)
    assert config.parameters.primary_root_count == parsed["outer_root_num"] + parsed["inner_root_num"]
