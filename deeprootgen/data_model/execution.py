"""Versioned, explicit options for the native simulator's extended execution."""

from typing import Dict, List, Literal, Union
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .simulation_data_models import RootSimulationModel


class NativeConstruction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["native"] = "native"
    parameters: RootSimulationModel

    @model_validator(mode="before")
    @classmethod
    def reject_unknown_parameters(cls, values):
        if isinstance(values, dict) and isinstance(values.get("parameters"), dict):
            unknown = set(values["parameters"]) - set(RootSimulationModel.model_fields)
            if unknown:
                raise ValueError(f"Unknown native parameters: {sorted(unknown)}")
        return values

    @model_validator(mode="after")
    def require_finite_parameters(self):
        # Legacy flat parsing stays unchanged; extended inputs are explicit.
        try:
            json.dumps(self.parameters.model_dump(), allow_nan=False)
        except ValueError as error:
            raise ValueError("Extended native parameters must be finite") from error
        return self


class Distribution(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    mean: float
    sd: float
    min: float
    max: float


class CohortOrder(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    length_cm: Distribution
    base_diameter_cm: Distribution
    tip_diameter_cm: Distribution
    first_branch_cm: Distribution
    branch_probability: float
    daughter_probabilities: List[float]
    curvature_sd_rad_cm: float
    correlation_cm: float
    downward_drift_per_cm: float
    midpoint_fraction: float = 0.5


class CohortParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    step_cm: float
    dry_density_g_cm3: float
    fine_cutoff_mm: float
    max_organs: int = Field(strict=True, gt=0)
    crown_mass_g: float
    crown_depth_cm: List[float]
    crown_radius_cm: float
    later_maturity: List[float]
    maturity_length_power: float
    maturity_diameter_power: float
    child_diameter_fraction_max: float
    inclination_mean_deg: float
    inclination_sd_deg: float
    inclination_bounds_deg: List[float]
    insertion_mean_deg: float
    insertion_sd_deg: float
    orders: Dict[str, CohortOrder]
    reconcile_length_metadata: bool = Field(default=False, strict=True)
    unrepresented_fine_mass_g: float = 0.0

    @model_validator(mode="after")
    def validate_laws(self):
        from ..model.cohort import validate_cohort_config

        validate_cohort_config(self.model_dump())
        return self


class CohortConstruction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["cohort"]
    parameters: CohortParameters
    older_count: int = Field(strict=True, ge=1)
    later_count: int = Field(strict=True, ge=0)


class RootSimulationConfig(BaseModel):
    """New options share run(); flat RootSimulationModel remains compatible."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[2] = 2
    random_seed: int = Field(strict=True, ge=0)
    simulation_tag: str = "default"
    construction: Union[NativeConstruction, CohortConstruction] = Field(
        discriminator="kind"
    )
    trajectory: Literal["native", "construction_steps_v1", "cohort_v5"] = "native"

    @model_validator(mode="after")
    def require_supported_contract(self):
        if self.construction.kind == "cohort":
            if self.trajectory != "cohort_v5":
                raise ValueError("Cohort construction requires cohort_v5 trajectory")
            if (
                self.construction.older_count + self.construction.later_count
                > self.construction.parameters.max_organs
            ):
                raise ValueError("Initial primary organ budget exhausted")
            return self
        if self.trajectory == "cohort_v5":
            raise ValueError("cohort_v5 requires cohort construction")
        p = self.construction.parameters
        if p.random_seed != self.random_seed:
            raise ValueError("Native parameters and execution random_seed must match")
        if self.trajectory == "construction_steps_v1":
            if (
                p.research_current_length_grid != "construction_steps_v1"
                or p.tropism_mode != "fichtl2024"
                or p.soil_surface_z_cm != 20.0
                or p.max_order not in (3, 4, 5)
                or p.research_primary_design is not None
            ):
                raise ValueError(
                    "Construction steps require grid/Fichtl/surface20/order3..5 without explicit primary design"
                )
        elif (
            p.research_current_length_grid is not None
            or p.research_parent2_branch_zone_cm is not None
            or p.research_tertiary_length_rank_strength
            or p.research_primary_attachment_distal_fraction
        ):
            raise ValueError(
                "Construction-step controls require construction_steps_v1 trajectory"
            )
        return self


def require_native_service_request(parameters):
    """Reject offline-only contracts before a service creates any artifacts."""
    if not isinstance(parameters, RootSimulationModel):
        raise ValueError(
            "Extended construction is supported by the offline API/CLI only"
        )
    if (
        parameters.research_current_length_grid is not None
        or parameters.research_parent2_branch_zone_cm is not None
        or parameters.research_tertiary_length_rank_strength
        or parameters.research_primary_attachment_distal_fraction
    ):
        raise ValueError("Construction-step controls require the offline extended API")
