"""Every historical input field has a declared destination and disposition."""

import re

import pytest

from deeprootgen.data_model.execution import (
    CohortConstruction,
    CohortOrder,
    CohortParameters,
    NativeConstruction,
    RootSimulationConfig,
)
from deeprootgen.data_model.features import Features, NativeParameters, RootSimulationConfigV3
from deeprootgen.data_model.inventory import FIELD_INVENTORY
from deeprootgen.data_model.resolution import EFFECTIVE_NATIVE_FIELDS
from deeprootgen.data_model.simulation_data_models import RootSimulationModel

SCHEMAS = {
    "RootSimulationModel": RootSimulationModel,
    "RootSimulationConfig": RootSimulationConfig,
    "NativeConstruction": NativeConstruction,
    "CohortConstruction": CohortConstruction,
    "CohortParameters": CohortParameters,
    "CohortOrder": CohortOrder,
}
DISPOSITIONS = {"canonical", "adapter_law", "adapter_only", "observation", "selector", "support"}


def test_inventory_covers_every_field_exactly_once():
    listed = [(e["schema"], e["field"]) for e in FIELD_INVENTORY]
    assert len(listed) == len(set(listed))
    expected = {(name, field) for name, model in SCHEMAS.items() for field in model.model_fields}
    assert set(listed) == expected


def _resolves(path):
    """Walk a schema-3 destination path through the pydantic models."""
    import typing

    model, parts = RootSimulationConfigV3, path.split(".")
    for index, part in enumerate(parts):
        if model is None:
            return False
        if part == "<order>":
            continue
        if part not in model.model_fields:
            return False
        annotation = model.model_fields[part].annotation
        while True:
            args = [a for a in typing.get_args(annotation) if a is not type(None)]
            origin = typing.get_origin(annotation)
            if origin in (dict, typing.Dict) or (origin is not None and str(origin).endswith("Dict")):
                annotation = args[-1]
            elif args and origin is not None and origin is not list:
                annotation = args[0]
            else:
                break
        model = annotation if isinstance(annotation, type) and hasattr(annotation, "model_fields") else None
    return True


@pytest.mark.parametrize("entry", FIELD_INVENTORY, ids=lambda e: f"{e['schema']}.{e['field']}")
def test_inventory_entries_have_owner_units_and_valid_destination(entry):
    assert entry["disposition"] in DISPOSITIONS
    assert entry["units"] and entry["consumer"] and entry["activation"]
    if entry["disposition"] in ("adapter_only", "observation", "selector", "support"):
        assert entry["destination"] is None
    if entry["disposition"] == "adapter_law":
        assert entry["destination"]  # names the engine stage that executes it
    if entry["disposition"] != "canonical":
        return
    destination = entry["destination"]
    if destination.startswith("parameters."):
        name = destination.split(".", 1)[1]
        assert name in NativeParameters.model_fields and name in EFFECTIVE_NATIVE_FIELDS
    else:
        assert _resolves(destination), destination


def test_every_schema3_feature_has_a_documented_source_or_is_new():
    destinations = " ".join(str(e["destination"]) for e in FIELD_INVENTORY)
    for feature in Features.model_fields:
        assert re.search(rf"features\.{feature}\b", destinations), feature
