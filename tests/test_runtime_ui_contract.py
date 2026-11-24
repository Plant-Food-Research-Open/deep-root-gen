"""Local simulation inputs follow the upstream 1.0 runtime domain."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("form", ["simulation_form", "deployments_form"])
def test_gravitropism_input_matches_runtime_domain(form):
    config = yaml.safe_load((ROOT / "app/conf" / form / "common.yaml").read_text())

    def find(value):
        if isinstance(value, dict):
            if value.get("id") == "gravitropism-input":
                return value
            for child in value.values():
                result = find(child)
                if result is not None:
                    return result
        elif isinstance(value, list):
            for child in value:
                result = find(child)
                if result is not None:
                    return result
        return None

    field = find(config)["kwargs"]
    assert field["min"] == 0 and field["max"] == 1
    assert 0 <= field["value"] <= 1
    assert 0 < field["step"] < 1
