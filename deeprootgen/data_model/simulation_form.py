"""Pure mapping between Dash controls and the canonical generation document."""

import json

from pydantic import BaseModel, ConfigDict, Field

from .canonical import RootConfig
from .features import OBSERVATION_SETTINGS


class SoilDisplay(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    enable_soil: bool = False
    soil_layer_height: float = Field(default=0, ge=0)
    soil_layer_width: float = Field(default=0, ge=0)
    soil_n_layers: int = Field(default=0, ge=0)
    soil_n_cols: int = Field(default=0, ge=0)


def simulation_document(values):
    fields = dict(values)
    for name in OBSERVATION_SETTINGS:
        fields.pop(name, None)
    advanced = json.loads(fields.pop("advanced_settings", None) or "{}")
    parameters = advanced.pop("parameters", {})
    seed = fields.pop("random_seed")
    tag = fields.pop("simulation_tag", None) or "default"
    for name, value in fields.items():
        if value is not None:
            if name in parameters:
                raise ValueError(f"{name} was supplied twice")
            parameters[name] = value
    return RootConfig(schema_version=4, random_seed=seed, simulation_tag=tag,
                      parameters=parameters, **advanced).model_dump(mode="json", exclude_unset=True)


def simulation_controls(document, form_fields, current_soil=None):
    """Preserve features, limits and advanced parameters across edit/save/upload."""
    config = RootConfig.model_validate(document)
    spec = config.model_dump(mode="json", exclude_unset=True)
    params = spec.pop("parameters")
    fields = dict(random_seed=config.random_seed, simulation_tag=config.simulation_tag)
    for key in form_fields:
        if key in params and not isinstance(params[key], (list, dict)):
            fields[key] = params.pop(key)
    extra = {k: v for k, v in spec.items() if k not in ("schema_version", "random_seed", "simulation_tag")}
    if params:
        extra["parameters"] = params
    fields["advanced_settings"] = json.dumps(extra, indent=2)
    fields.update(current_soil or {})
    return [fields.get(k) for k in form_fields]
