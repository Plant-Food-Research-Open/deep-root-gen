"""Public configuration for a static root system, in centimetres and grams."""
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .canonical_features import CanonicalFeatures as Features, CanonicalLimits, check_allocation_ownership
from .features import NativeParameters, _order_keys
from .daughter_placement import DaughterPlacement
from .irrigation import Irrigation


Positive = Annotated[float, Field(gt=0)]
Fraction = Annotated[float, Field(ge=0, le=1)]
Count = Annotated[int, Field(ge=0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class BirthDepthTransfer(StrictModel):
    """Move eligible ordinary daughters along their own parent's contour."""

    parent_orders: Annotated[list[Annotated[int, Field(ge=1)]], Field(min_length=1)]
    shallow_depth_cm: Positive
    deep_depth_cm: Positive
    transfer_probability: Fraction

    @model_validator(mode="after")
    def check_support(self):
        if self.deep_depth_cm < self.shallow_depth_cm:
            raise ValueError("deep_depth_cm must be at least shallow_depth_cm")
        if len(set(self.parent_orders)) != len(self.parent_orders):
            raise ValueError("parent_orders must contain distinct orders")
        return self


class DaughterRange(StrictModel):
    min: Count
    max_exclusive: Count

    @model_validator(mode="after")
    def check_interval(self):
        if self.max_exclusive <= self.min:
            raise ValueError("max_exclusive must exceed min")
        return self


class TissueDensityBands(StrictModel):
    """Piecewise-constant dry mass per unit fresh root volume."""

    bounds_mm: list[Positive]
    density_g_cm3: list[Positive]
    equality_to_finer: list[bool]

    @model_validator(mode="after")
    def validate_bands(self):
        if any(b <= a for a, b in zip(self.bounds_mm, self.bounds_mm[1:])):
            raise ValueError("Diameter bounds must increase")
        if len(self.density_g_cm3) != len(self.bounds_mm) + 1 or len(self.equality_to_finer) != len(self.bounds_mm):
            raise ValueError("Supply one density per band and one equality convention per boundary")
        return self

    def profile(self):
        from ..model.tissue_density import DiameterDensity

        return DiameterDensity(tuple(self.bounds_mm), tuple(self.density_g_cm3), tuple(self.equality_to_finer))


class AllocationControls(StrictModel):
    length_scale_by_order: dict[str, list[Positive]] = Field(default_factory=dict)
    diameter_scale_by_order: dict[str, list[Positive]] = Field(default_factory=dict)

    @field_validator("length_scale_by_order", "diameter_scale_by_order")
    @classmethod
    def scales(cls, values):
        _order_keys(values)
        for interval in values.values():
            if len(interval) != 2 or not interval[0] <= 1 <= interval[1] or interval[0] == interval[1]:
                raise ValueError("Supply an adjustable [min, max] scale interval containing 1")
        return values


class RootParameters(StrictModel):
    max_order: Annotated[int, Field(gt=0)]
    primary_root_count: Annotated[int, Field(gt=0)]
    outer_primary_fraction: Fraction = 0.5
    threshold_root_diameter_cm: Positive = 0.25
    min_branching_diameter_cm: Annotated[float, Field(ge=0)] = 0.093
    root_ratio_biomass: Fraction | None = None
    root_ratio_length: Fraction | None = None
    allocation_controls: AllocationControls | None = None
    root_tissue_density: Positive | TissueDensityBands
    daughters_per_parent: Count | DaughterRange | None = None
    daughters_by_parent_order: dict[str, Count] = Field(default_factory=dict)
    daughter_count_order_gain: Annotated[float, Field(ge=0, lt=1)] = 0.0
    min_primary_length: Positive | None = None
    max_primary_length: Positive | None = None
    min_lateral_length: Positive | None = None
    max_lateral_length: Positive | None = None
    base_diameter: Positive | None = None
    apex_diameter: Positive | None = None
    diameter_reduction: Fraction | None = None
    segments_per_root: Annotated[int, Field(gt=0)] | None = None
    length_reduction: Annotated[float, Field(ge=0)] | None = None
    root_vary: Annotated[float, Field(ge=0)] | None = None
    interbranch_distance: Positive | None = None
    gravitropism: float | None = None
    floor_threshold: Fraction = 0.4
    ceiling_threshold: Fraction = 0.9
    max_val_attempts: Count = 50
    no_root_zone: float = 1e-4
    tropism_mode: Literal["legacy", "fichtl2024"] = "legacy"
    soil_surface_z_cm: Annotated[float, Field(ge=0)] = 0
    fichtl_probability_down: Fraction | None = None
    fichtl_sigma: float | None = None
    fichtl_trials_type2: float | None = None
    fichtl_trials_type3: float | None = None
    fichtl_theta2_deg: float | None = None
    fichtl_theta2_sd_deg: float | None = None
    fichtl_theta3_deg: float | None = None
    fichtl_theta3_sd_deg: float | None = None

    @model_validator(mode="after")
    def check_orders_and_targets(self):
        _order_keys(self.daughters_by_parent_order)
        if any(int(k) >= self.max_order for k in self.daughters_by_parent_order):
            raise ValueError("Daughter overrides require a nonterminal parent order")
        controls = self.allocation_controls
        has_target = self.root_ratio_biomass is not None or self.root_ratio_length is not None
        if has_target != (controls is not None):
            raise ValueError("Root ratio targets and their allocation_controls must be supplied together")
        if controls is not None:
            orders = set(controls.length_scale_by_order) | set(controls.diameter_scale_by_order)
            if not orders or any(int(k) > self.max_order for k in orders):
                raise ValueError("Allocation controls require adjustable orders within max_order")
        for lo, hi in ((self.min_primary_length, self.max_primary_length),
                       (self.min_lateral_length, self.max_lateral_length)):
            if lo is not None and hi is not None and lo > hi:
                raise ValueError("Length minimum exceeds maximum")
        return self

    def kernel_parameters(self):
        """Bind user settings to the existing numerical kernels."""
        outer = int((Decimal(str(self.outer_primary_fraction)) * self.primary_root_count)
                    .to_integral_value(rounding=ROUND_HALF_UP))
        count = self.daughters_per_parent
        lower = count.min if isinstance(count, DaughterRange) else count
        upper = count.max_exclusive if isinstance(count, DaughterRange) else count
        shared_fields = RootParameters.model_fields.keys() & NativeParameters.model_fields.keys()
        values = self.model_dump(include=shared_fields)
        if isinstance(self.root_tissue_density, TissueDensityBands):
            # Construction creates provisional cylinders; final material uses physical point diameters.
            values["root_tissue_density"] = self.root_tissue_density.density_g_cm3[-1]
        values.update(outer_root_num=outer, inner_root_num=self.primary_root_count - outer,
                      fine_root_threshold=self.threshold_root_diameter_cm,
                      min_sec_root_num=lower, max_sec_root_num=upper,
                      growth_sec_root=self.daughter_count_order_gain,
                      min_sec_root_length=self.min_lateral_length, max_sec_root_length=self.max_lateral_length)
        return NativeParameters.model_validate(values).model_copy(update={
            "min_branching_diameter_cm": self.min_branching_diameter_cm,
            "daughters_by_parent_order": {int(k): v for k, v in self.daughters_by_parent_order.items()},
            "canonical_generation": True,
        })


class RootConfig(StrictModel):
    irrigation: Irrigation | None = None
    daughter_placement: DaughterPlacement | None = None
    birth_depth_transfer: BirthDepthTransfer | None = None
    minimum_realized_primary_length_cm: Annotated[float, Field(gt=0)] | None = None

    @field_validator("irrigation", mode="before")
    @classmethod
    def rainfed(cls, value):
        if value == "rainfed" or (isinstance(value, dict) and (value.get("treatment") == "rainfed" or value.get("irrigation_depth_cm", "required") in (None, "rainfed"))):
            return None
        return value

    schema_version: Literal[4]
    random_seed: Annotated[int, Field(ge=0)] | None
    simulation_tag: str = "default"
    parameters: RootParameters
    features: Features = Field(default_factory=Features)
    limits: CanonicalLimits = Field(default_factory=CanonicalLimits)

    @field_validator("schema_version", mode="before")
    @classmethod
    def check_version(cls, value):
        if type(value) is not int:
            raise ValueError("schema_version must be an integer")
        return value

    @model_validator(mode="after")
    def check_feature_owners(self):
        p = self.parameters
        counts = p.daughters_by_parent_order
        branching = self.features.branching
        sites = self.features.branch_sites
        if counts and ((branching.enabled and counts.keys() & branching.settings.by_order.keys())
                       or (sites.enabled and sites.settings.counts_by_order is not None)):
            raise ValueError("Two daughter-count laws own the same parent order")
        if p.allocation_controls is not None:
            check_allocation_ownership(p, self.features)
            c = p.allocation_controls
            placement = self.features.primary_placement
            if ("1" in set(c.length_scale_by_order) | set(c.diameter_scale_by_order)
                    and placement.enabled and placement.settings.explicit_design is not None):
                raise ValueError("Explicit primary design fixes primary dimensions")
        return self
