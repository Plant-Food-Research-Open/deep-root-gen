import json
from pathlib import Path

import pytest

from deeprootgen.research.architecture_search import describe_controls, run_architecture_search, validate_architecture_search


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def request_data():
    base = json.loads((ROOT / "examples/synthetic_minimal.json").read_text())
    return dict(
        base=base, ranges=[dict(control="primary_root_count", lower=2, upper=4)],
        targets=[dict(statistic_name="root_number", statistic_value=3)],
        metric="mae", trials=5, startup=2, seeds=[0, 1],
    )


@pytest.mark.parametrize("method", ["tpe", "latin_hypercube"])
def test_seeded_native_fit_and_export(tmp_path, request_data, method):
    outdir = tmp_path / "fit"
    result = run_architecture_search(dict(request_data, method=method), outdir)
    assert result["completed_trials"] == 5
    assert result["best_loss"] == 0.0
    best = json.loads((outdir / "best-configuration.json").read_text())
    assert best["parameters"]["primary_root_count"] == 3
    assert best["random_seed"] == 0
    assert (outdir / "trials.csv").read_text().count("\n") == 6


def test_inactive_and_noninteger_ranges_are_rejected(request_data):
    request_data["ranges"][0]["lower"] = 2.5
    with pytest.raises(ValueError, match="integer"):
        validate_architecture_search(request_data)
    request_data["ranges"] = [dict(control="min_lateral_length", lower=8, upper=12)]
    with pytest.raises(ValueError, match="active control"):
        validate_architecture_search(request_data)


def test_available_native_controls_follow_the_effective_model(request_data):
    base = request_data["base"]
    _, controls, _ = describe_controls(base)
    assert "gravitropism" in controls
    assert "min_lateral_length" not in controls
    assert "threshold_root_diameter_cm" not in controls


def test_current_structured_features_resolve_without_offering_fixed_or_terminal_controls():
    def config(name):
        return json.loads((ROOT / "examples" / name).read_text())

    base = config("synthetic_minimal.json")
    base["features"]["lengths"] = dict(enabled=True, settings={"by_order": {"1": 21.0}})
    _, simple, _ = describe_controls(base)
    assert "lengths_1_mean" not in simple
    _, cohort, _ = describe_controls(config("research/native_cohort_synthetic.json"))
    assert "curvature_2_downward_drift_per_cm" in cohort
    assert "branching_5_branch_probability" not in cohort


def test_native_lateral_ranges_use_the_canonical_field_names(request_data):
    base = request_data["base"]
    base["parameters"]["max_order"] = 2
    _, controls, _ = describe_controls(base)
    assert controls["min_lateral_length"]["path"] == ("parameters", "min_lateral_length")
