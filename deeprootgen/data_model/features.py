"""Schema-version-3 input: one native parameter set plus independent feature toggles.

The JSON shape is the same whether a feature is enabled or disabled. Disabled
blocks keep their settings; known keys, types, shapes and finite numbers are
always validated. Completeness, ranges, engine support and cross-feature
dependencies are enforced only for enabled blocks by
``deeprootgen.data_model.resolution.resolve_config``.

There is deliberately no construction kind, complete-generator trajectory or
dataset selector here. A named mathematical law inside a feature is permitted.
"""

import re
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .simulation_data_models import FEATURE_NAMES, RootSimulationModel, ResearchPrimaryDesignEntry, Parent2BranchZone  # noqa: F401

SCHEMA_VERSION = 3
CURVATURE_LAW = "correlated_curvature"
CURVATURE_LAW_VERSION = "native-correlated-curvature-v1"
CURVATURE_STREAM_NAMESPACE = "feature.curvature.ou"
FEATURE_STREAM_VERSION = "native-feature-streams-v1"
# A geometric corner this close (cm) to a construction cut coincides with it.
CORNER_COINCIDENCE_CM = 1e-9


# Recognized features whose engine stage is not implemented yet. Enabling one
# fails before any simulation state or randomness is used; nothing is ignored.
PLANNED_FEATURE_DELIVERY = {}

# Numerical representability bounds for enabled correlated curvature. They keep
# OU coefficients finite and station counts bounded; they are not biology.
CURVATURE_BOUNDS = dict(
    step_cm=(1e-3, 1e3),
    correlation_length_cm=(1e-3, 1e6),
    curvature_sd_rad_cm=(0.0, 1e2),
)

STRICT = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
_ORDER_KEY = re.compile(r"[1-9][0-9]*")

# Flat-schema fields that schema 3 does not accept in ``parameters``. Old-input
# adapters still parse and serialize them; schema 3 gives each value one owner.
TOP_LEVEL_OWNED = ("random_seed", "simulation_tag")
NOT_CONSUMED_BY_STATIC_RUN = ("root_ratio", "mechanical_constraints", "origin_min", "origin_max", "t")
OBSERVATION_SETTINGS = ("enable_soil", "soil_layer_height", "soil_layer_width", "soil_n_layers", "soil_n_cols")
RESEARCH_ALIASES = tuple(name for name in RootSimulationModel.model_fields if name.startswith("research_"))


class _Strict(BaseModel):
    model_config = STRICT


def _order_keys(mapping):
    for key in mapping:
        if not isinstance(key, str) or not _ORDER_KEY.fullmatch(key):
            raise ValueError(f"by_order keys must be canonical positive order strings, got {key!r}")
    return mapping


class NativeParameters(RootSimulationModel):
    """Native fallback laws. Meaningful values remain; aliases stay in adapters.

    ``random_seed`` and ``simulation_tag`` are owned by the top level and are
    injected by the resolver. Fields without a static-run consumer are absent.
    """

    model_config = STRICT
    random_seed: Optional[int] = None
    root_ratio: Optional[float] = None
    mechanical_constraints: Optional[float] = None
    t: Optional[int] = None
    # Native construction fallbacks: required by the resolver only while a
    # native construction kernel still consumes them (no dummy values).
    min_primary_length: Optional[float] = None
    max_primary_length: Optional[float] = None
    base_diameter: Optional[float] = None
    diameter_reduction: Optional[float] = None
    apex_diameter: Optional[float] = None
    min_sec_root_num: Optional[int] = None
    max_sec_root_num: Optional[int] = None
    growth_sec_root: Optional[float] = None
    min_sec_root_length: Optional[float] = None
    max_sec_root_length: Optional[float] = None
    segments_per_root: Optional[int] = None
    length_reduction: Optional[float] = None
    root_vary: Optional[float] = None
    interbranch_distance: Optional[float] = None
    gravitropism: Optional[float] = None

    @model_validator(mode="after")
    def require_explicit_fichtl_parameters(self):
        """Inherited check, with an absent legacy gravitropism treated as zero."""
        if self.tropism_mode == "fichtl2024" and self.gravitropism not in (None, 0, 0.0):
            raise ValueError("Set legacy gravitropism to zero in fichtl2024 mode")
        # Consumer-specific completeness is enforced after feature resolution.
        return self

    @model_validator(mode="after")
    def validate_optional_order_scope(self):
        # Higher-order laws belong to feature blocks and are checked after
        # resolution; aliases are still forbidden at this input boundary.
        return self

    @model_validator(mode="before")
    @classmethod
    def reject_non_canonical_keys(cls, values):
        if not isinstance(values, dict):
            return values
        errors = []
        for key in values:
            if key in TOP_LEVEL_OWNED:
                errors.append(f"{key} is owned by the top-level {key}")
            elif key in NOT_CONSUMED_BY_STATIC_RUN:
                errors.append(f"{key} has no static-generation consumer; only old-input adapters keep it")
            elif key in OBSERVATION_SETTINGS:
                errors.append(f"{key} is an observation/visualization setting, not a generation parameter")
            elif key in RESEARCH_ALIASES:
                errors.append(f"{key} is an old-input alias; schema 3 expresses each control once in features")
        if errors:
            raise ValueError("Schema-3 parameters reject non-canonical keys: " + "; ".join(errors))
        return values


class Distribution(_Strict):
    """Bounded positive law; mean/SD describe the pre-truncation distribution."""

    mean: Optional[float] = None
    sd: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None


class CurvatureOrder(_Strict):
    """Correlated (OU) curvature on physical arclength; units are explicit."""

    law: Optional[Literal["correlated_curvature"]] = None
    step_cm: Optional[float] = None
    curvature_sd_rad_cm: Optional[float] = None
    correlation_length_cm: Optional[float] = None
    downward_drift_per_cm: Optional[float] = None
    boundary: Optional[Literal["reflect_downward"]] = None
    first_interval: Optional[Literal["integrate"]] = None
    # scaffold_chord: placed native scaffold; origin_heading: primary_origins
    # heading law; insertion_angle: keyed angle about the realized parent tangent.
    initial_heading: Optional[Literal["scaffold_chord", "origin_heading", "insertion_angle"]] = None
    insertion_mean_deg: Optional[float] = None
    insertion_sd_deg: Optional[float] = None


class CurvatureSettings(_Strict):
    by_order: Dict[str, CurvatureOrder] = Field(default_factory=dict)

    @field_validator("by_order")
    @classmethod
    def validate_order_keys(cls, value):
        return _order_keys(value)


class TaperOrder(_Strict):
    law: Optional[Literal["piecewise_linear_arclength"]] = None
    midpoint_diameter_fraction: Optional[float] = None
    base_cm: Optional[Distribution] = None
    tip_cm: Optional[Distribution] = None


class TaperSettings(_Strict):
    by_order: Dict[str, TaperOrder] = Field(default_factory=dict)

    @field_validator("by_order")
    @classmethod
    def validate_order_keys(cls, value):
        return _order_keys(value)


class PrimaryHeading(_Strict):
    """Initial primary heading: radial azimuth from the disk origin, drawn inclination."""

    law: Optional[Literal["radial_inclination"]] = None
    inclination_mean_deg: Optional[float] = None
    inclination_sd_deg: Optional[float] = None
    inclination_bounds_deg: Optional[List[float]] = None


class PrimaryOriginsSettings(_Strict):
    """disk: sampled origin per primary; point: one translated common base."""

    layout: Optional[Literal["disk", "point"]] = None
    radius_cm: Optional[float] = None
    depth_range_cm: Optional[List[float]] = None
    x_cm: Optional[float] = None
    y_cm: Optional[float] = None
    depth_cm: Optional[float] = None
    heading: Optional[PrimaryHeading] = None


class MaturityGroup(_Strict):
    """Primaries by zero-based birth index (outer then inner); descendants inherit."""

    label: Optional[str] = None
    primary_indices: Optional[List[int]] = None
    maturity_range: Optional[List[float]] = None


class CohortMaturitySettings(_Strict):
    groups: Optional[List[MaturityGroup]] = None
    length_power: Optional[float] = None
    diameter_power: Optional[float] = None
    scale_branch_probability: Optional[bool] = None
    diameter_target: Optional[Literal["base_anchor"]] = None


class LengthsOrder(_Strict):
    law: Optional[Literal["discrete_cdf", "bounded_lognormal"]] = None
    lengths_cm: Optional[List[float]] = None
    cumulative_probabilities: Optional[List[float]] = None
    mean: Optional[float] = None
    sd: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None

    @model_validator(mode="after")
    def reject_fields_of_another_law(self):
        cdf = {"lengths_cm", "cumulative_probabilities"}
        bounded = {"mean", "sd", "min", "max"}
        supplied = {name for name in cdf | bounded if getattr(self, name) is not None}
        foreign = {"discrete_cdf": supplied & bounded, "bounded_lognormal": supplied & cdf}.get(self.law)
        if foreign:
            raise ValueError(f"Length law {self.law} does not accept {sorted(foreign)}")
        return self


class LengthsSettings(_Strict):
    by_order: Dict[str, LengthsOrder] = Field(default_factory=dict)

    @field_validator("by_order")
    @classmethod
    def validate_order_keys(cls, value):
        return _order_keys(value)


class BranchingOrder(_Strict):
    law: Optional[Literal["first_branch_and_daughter_count"]] = None
    first_branch_cm: Optional[Distribution] = None
    branch_probability: Optional[float] = None
    daughter_probabilities: Optional[List[float]] = None


class BranchingSettings(_Strict):
    by_order: Dict[str, BranchingOrder] = Field(default_factory=dict)

    @field_validator("by_order")
    @classmethod
    def validate_order_keys(cls, value):
        return _order_keys(value)


class ParentDiameterCapSettings(_Strict):
    fraction_max: Optional[float] = None


class AttachmentRelocationSettings(_Strict):
    orders: Optional[List[int]] = None
    distal_fraction: Optional[float] = None
    preserve_sampled_daughter_dimensions: Optional[bool] = None


class CurvatureFeature(_Strict):
    enabled: bool = False
    settings: CurvatureSettings = Field(default_factory=CurvatureSettings)


class TaperFeature(_Strict):
    enabled: bool = False
    settings: TaperSettings = Field(default_factory=TaperSettings)


class PrimaryOriginsFeature(_Strict):
    enabled: bool = False
    settings: PrimaryOriginsSettings = Field(default_factory=PrimaryOriginsSettings)


class CohortMaturityFeature(_Strict):
    enabled: bool = False
    settings: CohortMaturitySettings = Field(default_factory=CohortMaturitySettings)


class LengthsFeature(_Strict):
    enabled: bool = False
    settings: LengthsSettings = Field(default_factory=LengthsSettings)


class BranchingFeature(_Strict):
    enabled: bool = False
    settings: BranchingSettings = Field(default_factory=BranchingSettings)


class ParentDiameterCapFeature(_Strict):
    enabled: bool = False
    settings: ParentDiameterCapSettings = Field(default_factory=ParentDiameterCapSettings)


class AttachmentRelocationFeature(_Strict):
    enabled: bool = False
    settings: AttachmentRelocationSettings = Field(default_factory=AttachmentRelocationSettings)


class PrimaryPlacementSettings(_Strict):
    yaw_mean_deg: Optional[float] = None
    yaw_kappa: Optional[float] = None
    yaw_reverse_probability: Optional[float] = None
    inclination_bias: Optional[float] = None
    explicit_design: Optional[List[ResearchPrimaryDesignEntry]] = None


class BranchSitesSettings(_Strict):
    placement: Optional[Literal["legacy_spacing", "redistribute_capped"]] = None
    counts_by_order: Optional[Dict[str, int]] = None
    primary_zone_cm: Optional[Dict[str, float]] = None
    primary_fractions: Optional[List[float]] = None
    parent2_zone_cm: Optional[Parent2BranchZone] = None


class SiblingLengthsSettings(_Strict):
    tertiary_rank_strength: Optional[float] = None


class InsertionSettings(_Strict):
    row_axial_kappa_by_order: Optional[Dict[str, float]] = None


class DirectionSettings(_Strict):
    sigma_by_order: Optional[Dict[str, float]] = None
    higher_order_tropism: Optional[Dict[str, Dict[str, float]]] = None
    stationing: Optional[Literal["construction_steps_v1"]] = None
    boundary: Optional[Literal["minimum_angle_projection"]] = None
    first_interval: Optional[Literal["assigned_insertion"]] = None
    primary_correction: Optional[Literal["native", "frozen_surface_check"]] = None
    post_correction: Optional[Literal["native", "pure_surface_check"]] = None


class MaterializationSettings(_Strict):
    reconcile_length_metadata: Optional[bool] = None


class PrimaryPlacementFeature(_Strict):
    enabled: bool = False
    settings: PrimaryPlacementSettings = Field(default_factory=PrimaryPlacementSettings)


class BranchSitesFeature(_Strict):
    enabled: bool = False
    settings: BranchSitesSettings = Field(default_factory=BranchSitesSettings)


class SiblingLengthsFeature(_Strict):
    enabled: bool = False
    settings: SiblingLengthsSettings = Field(default_factory=SiblingLengthsSettings)


class InsertionFeature(_Strict):
    enabled: bool = False
    settings: InsertionSettings = Field(default_factory=InsertionSettings)


class DirectionFeature(_Strict):
    enabled: bool = False
    settings: DirectionSettings = Field(default_factory=DirectionSettings)


class MaterializationFeature(_Strict):
    enabled: bool = False
    settings: MaterializationSettings = Field(default_factory=MaterializationSettings)


class Features(_Strict):
    """Every recognized feature; an omitted block is disabled with no settings."""

    primary_placement: PrimaryPlacementFeature = Field(default_factory=PrimaryPlacementFeature)
    branch_sites: BranchSitesFeature = Field(default_factory=BranchSitesFeature)
    sibling_lengths: SiblingLengthsFeature = Field(default_factory=SiblingLengthsFeature)
    insertion: InsertionFeature = Field(default_factory=InsertionFeature)
    direction: DirectionFeature = Field(default_factory=DirectionFeature)
    materialization: MaterializationFeature = Field(default_factory=MaterializationFeature)
    curvature: CurvatureFeature = Field(default_factory=CurvatureFeature)
    taper: TaperFeature = Field(default_factory=TaperFeature)
    primary_origins: PrimaryOriginsFeature = Field(default_factory=PrimaryOriginsFeature)
    cohort_maturity: CohortMaturityFeature = Field(default_factory=CohortMaturityFeature)
    lengths: LengthsFeature = Field(default_factory=LengthsFeature)
    branching: BranchingFeature = Field(default_factory=BranchingFeature)
    parent_diameter_cap: ParentDiameterCapFeature = Field(default_factory=ParentDiameterCapFeature)
    attachment_relocation: AttachmentRelocationFeature = Field(default_factory=AttachmentRelocationFeature)


class Limits(_Strict):
    """Explicit resource limits; exceeding one fails instead of truncating organs."""

    max_organs: Optional[int] = Field(default=None, gt=0)
    max_nodes: Optional[int] = Field(default=None, gt=0)
    max_stations: Optional[int] = Field(default=None, gt=0)


class RootSimulationConfigV3(_Strict):
    """One JSON for native generation with independently enabled features."""

    schema_version: Literal[3]
    random_seed: int = Field(ge=0)
    simulation_tag: str = "default"
    parameters: NativeParameters
    features: Features = Field(default_factory=Features)
    limits: Limits = Field(default_factory=Limits)
