"""Exercise the real native search callback on the distributed synthetic configuration."""
import json
from pathlib import Path

from deeprootgen.research.search_evaluation import simulate_sample


def test_canonical_construction_steps_accept_absent_retired_parameters():
    example = Path(__file__).resolve().parents[1] / "examples/research/search_synthetic_parameters.json"
    config = json.loads(example.read_text())
    config["random_seed"] = 101
    result = simulate_sample(config, 101, route="construction_steps_v1")
    assert result["diagnostics"]["fresh_initial_construction"]
    assert result["diagnostics"]["initial_sha256"]
    assert len(result["traits"]) == 13
