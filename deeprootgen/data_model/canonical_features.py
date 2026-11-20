"""Canonical value forms for optional length and material calculations."""

from math import hypot, isclose
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, RootModel, Tag, field_validator, model_validator

from .features import (
    BranchingFeature,
    BranchingOrder,
    BranchingSettings,
    CurvatureFeature,
    CurvatureOrder,
    CurvatureSettings,
    Distribution,
    Features,
    Limits,
    LengthsFeature,
    LengthsOrder,
    LengthsSettings,
    PrimaryOriginsFeature,
    PrimaryOriginsSettings,
    TaperFeature,
    TaperOrder,
    TaperSettings,
    STRICT,
)


PositiveCm = Annotated[float, Field(gt=0, strict=True, allow_inf_nan=False)]


class _ConstantDimension:
    """Deterministic initial dimension, in the existing length/material sampler."""

    @property
    def law(self):
        return "bounded_lognormal"

    @property
    def mean(self):
        return self.value

    @property
    def sd(self):
        return 0.0

    @property
    def min(self):
        return self.value

    @property
    def max(self):
        return self.value


class FixedLength(_ConstantDimension, RootModel[PositiveCm]):
    @property
    def value(self):
        return self.root


class NominalDimension(_ConstantDimension, BaseModel):
    """Initial constant whose final dimension may vary within the explicit scale bounds."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    nominal_cm: PositiveCm

    @property
    def value(self):
        return self.nominal_cm


class PointDiameterLaw(BaseModel):
    """Point diameter in cm, with moments on the untruncated distribution."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    law: Literal["truncated_normal", "bounded_lognormal"]
    mean: float
    sd: Annotated[float, Field(ge=0)]
    min: PositiveCm
    max: PositiveCm


class PointTaper(TaperOrder):
    law: Literal["piecewise_linear_arclength"] = "piecewise_linear_arclength"
    midpoint_diameter_fraction: float = 0.5
    base_cm: PositiveCm | NominalDimension | PointDiameterLaw | Distribution | None = (
        None
    )
    tip_cm: PositiveCm | NominalDimension | PointDiameterLaw | Distribution | None = (
        None
    )


class ThickRootTaper(PointTaper):
    """Exponential change through the thick part, with a continuous thin taper."""

    law: Literal["exponential_above_diameter"]
    rate_per_cm: Annotated[float, Field(ge=0, strict=True, allow_inf_nan=False)]
    thick_min_cm: PositiveCm


class PointTaperSettings(TaperSettings):
    by_order: dict[str, PointTaper | ThickRootTaper] = Field(default_factory=dict)


class PointTaperFeature(TaperFeature):
    settings: PointTaperSettings = Field(default_factory=PointTaperSettings)


class CanonicalLengthsSettings(LengthsSettings):
    by_order: dict[str, FixedLength | NominalDimension | LengthsOrder] = Field(
        default_factory=dict
    )


class CanonicalLengths(LengthsFeature):
    settings: CanonicalLengthsSettings = Field(default_factory=CanonicalLengthsSettings)


class CanonicalCurvatureOrder(CurvatureOrder):
    row_alignment_per_cm: Annotated[float, Field(ge=0)] = 0.0


class CanonicalCurvatureSettings(CurvatureSettings):
    by_order: dict[str, CanonicalCurvatureOrder] = Field(default_factory=dict)


class CanonicalCurvature(CurvatureFeature):
    settings: CanonicalCurvatureSettings = Field(default_factory=CanonicalCurvatureSettings)


class LengthPoissonSites(BaseModel):
    model_config = STRICT

    law: Literal["length_poisson_sites_v1"]
    basal_exclusion_cm: PositiveCm
    apical_exclusion_cm: PositiveCm
    mean_spacing_cm: PositiveCm
    branch_probability: Annotated[float, Field(ge=0, le=1)]


def _branching_law(value):
    law = value.get("law") if isinstance(value, dict) else getattr(value, "law", None)
    # Existing dormant blocks can preserve an incomplete first-site law.
    if law is None:
        return "first_branch_and_daughter_count"
    return law if isinstance(law, str) else "invalid"


CanonicalBranchingOrder = Annotated[
    Annotated[BranchingOrder, Tag("first_branch_and_daughter_count")]
    | Annotated[LengthPoissonSites, Tag("length_poisson_sites_v1")],
    Discriminator(_branching_law),
]


class CanonicalBranchingSettings(BranchingSettings):
    by_order: dict[str, CanonicalBranchingOrder] = Field(default_factory=dict)


class CanonicalBranching(BranchingFeature):
    settings: CanonicalBranchingSettings = Field(default_factory=CanonicalBranchingSettings)


class CanonicalLimits(Limits):
    max_branch_proposals: Annotated[int, Field(gt=0)] | None = None


class OriginCoordinates(BaseModel):
    model_config = STRICT

    x_cm: float
    y_cm: float
    depth_cm: Annotated[float, Field(ge=0)]


class IndexedPrimaryOrigin(OriginCoordinates):
    index: Annotated[int, Field(ge=0)]
    heading_unit: Annotated[list[float], Field(min_length=3, max_length=3)] | None = None

    @field_validator("heading_unit")
    @classmethod
    def unit_heading(cls, heading):
        if heading is not None and not isclose(hypot(*heading), 1.0, abs_tol=1e-12, rel_tol=0):
            raise ValueError("heading_unit must be a unit vector in the model frame")
        return heading


class OriginProvenance(BaseModel):
    model_config = STRICT

    source_frame: str | None = None
    source_sha256: Annotated[str, Field(pattern=r"^[a-fA-F0-9]{64}$")] | None = None
    conversion_version: str | None = None
    comment: str | None = None


class VineOriginEntry(BaseModel):
    model_config = STRICT

    entry_id: Annotated[str, Field(min_length=1)]
    weight: Annotated[float, Field(gt=0)] = 1.0
    origins_status: Literal["complete", "inferred"] = "complete"
    crown_census_status: Literal["complete", "missing", "inferred"] = "missing"
    provenance: OriginProvenance | None = None


class CommonPointEntry(VineOriginEntry):
    layout: Literal["common_point"]
    origin: OriginCoordinates


class PrimaryLayoutEntry(VineOriginEntry):
    layout: Literal["primary_layout"]
    primaries: Annotated[list[IndexedPrimaryOrigin], Field(min_length=1)]
    headings_status: Literal["complete", "missing", "inferred"] | None = None

    @model_validator(mode="after")
    def check_layout(self):
        indices = {origin.index for origin in self.primaries}
        if len(indices) != len(self.primaries):
            raise ValueError("Vine primary layout has duplicate primary indices")
        headings = sum(origin.heading_unit is not None for origin in self.primaries)
        if headings not in (0, len(self.primaries)):
            raise ValueError("A vine primary layout must supply all headings or omit all headings")
        if self.headings_status is not None and (self.headings_status == "missing") == bool(headings):
            raise ValueError("headings_status disagrees with the supplied primary headings")
        return self


class SampleVineOrigin(BaseModel):
    model_config = STRICT
    mode: Literal["sample"] = "sample"


class FixedVineOrigin(BaseModel):
    model_config = STRICT
    mode: Literal["fixed"]
    entry_id: Annotated[str, Field(min_length=1)]


class VineCatalogueSettings(BaseModel):
    model_config = STRICT

    layout: Literal["vine_catalogue"]
    catalogue_version: Literal["vine_origins_v1"]
    coordinate_frame: Literal["model_soil_cm_v1"]
    selection: Annotated[SampleVineOrigin | FixedVineOrigin, Field(discriminator="mode")] = Field(
        default_factory=SampleVineOrigin
    )
    entries: Annotated[list[Annotated[CommonPointEntry | PrimaryLayoutEntry, Field(discriminator="layout")]],
                       Field(min_length=1)]

    @model_validator(mode="after")
    def check_entries(self):
        ids = {entry.entry_id for entry in self.entries}
        if len(ids) != len(self.entries):
            raise ValueError("Vine-origin catalogue entry_id values must be unique")
        if self.selection.mode == "fixed" and self.selection.entry_id not in ids:
            raise ValueError("Fixed vine-origin entry_id must be present in the catalogue")
        return self


def _origin_layout(value):
    layout = value.get("layout") if isinstance(value, dict) else getattr(value, "layout", None)
    return "vine_catalogue" if layout == "vine_catalogue" else "point_or_disk"


class CanonicalPrimaryOrigins(PrimaryOriginsFeature):
    settings: Annotated[
        Annotated[PrimaryOriginsSettings, Tag("point_or_disk")]
        | Annotated[VineCatalogueSettings, Tag("vine_catalogue")],
        Discriminator(_origin_layout),
    ] = Field(default_factory=PrimaryOriginsSettings)


class CanonicalFeatures(Features):
    branching: CanonicalBranching = Field(default_factory=CanonicalBranching)
    curvature: CanonicalCurvature = Field(default_factory=CanonicalCurvature)
    primary_origins: CanonicalPrimaryOrigins = Field(default_factory=CanonicalPrimaryOrigins)
    taper: PointTaperFeature = Field(default_factory=PointTaperFeature)
    lengths: CanonicalLengths = Field(default_factory=CanonicalLengths)


def check_allocation_ownership(p, features):
    """Keep fixed dimensions hard while allowing explicitly nominal constants."""
    controls = p.allocation_controls
    for key in controls.length_scale_by_order:
        law = (
            features.lengths.settings.by_order.get(key)
            if features.lengths.enabled
            else None
        )
        if law is None:
            lo, hi = (
                (p.min_primary_length, p.max_primary_length)
                if key == "1"
                else (p.min_lateral_length, p.max_lateral_length)
            )
            fixed = lo is not None and lo == hi
        elif law.law == "discrete_cdf":
            fixed = len(set(law.lengths_cm or [])) == 1
        else:
            fixed = _fixed_value(law)
        if fixed:
            raise ValueError(
                f"Fixed length for order {key} conflicts with allocation; use nominal_cm to allow scaling"
            )
    for key in controls.diameter_scale_by_order:
        taper = (
            features.taper.settings.by_order.get(key)
            if features.taper.enabled
            else None
        )
        if taper is not None:
            fixed = any(_fixed_value(value) for value in (taper.base_cm, taper.tip_cm))
        elif None not in (p.base_diameter, p.diameter_reduction, p.apex_diameter):
            fixed = (
                p.base_diameter * (1.0 - p.diameter_reduction) ** (int(key) - 1)
                == p.apex_diameter
            )
        else:
            fixed = False
        if fixed:
            raise ValueError(
                f"Fixed diameter for order {key} conflicts with allocation; use nominal_cm to allow scaling"
            )


def _fixed_value(law):
    if isinstance(law, NominalDimension):
        return False
    return isinstance(law, (float, int)) or getattr(law, "sd", None) == 0
