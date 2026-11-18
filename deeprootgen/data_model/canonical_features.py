"""Canonical value forms for optional length and material calculations."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from .features import (
    Distribution,
    Features,
    LengthsFeature,
    LengthsOrder,
    LengthsSettings,
    TaperFeature,
    TaperOrder,
    TaperSettings,
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


class CanonicalFeatures(Features):
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
