"""Optional contour preference for terminal daughter placement."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, field_validator, model_validator


class OccurrenceProfile(BaseModel):
    """Frozen training-core regression, evaluated in vineyard coordinates."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    version: Literal["occurrence_v1"] = "occurrence_v1"
    # Intercept, scaled depth, two hinges, and normalized cross-row distance.
    coefficients: tuple[float, float, float, float, float]
    row_depth_slope: float | None = None
    training_mean: float
    depth_range_cm: tuple[float, float]
    fade_cm: Annotated[float, Field(gt=0)]
    row_period_cm: Annotated[float, Field(gt=0)]
    # Full support requires at least two tubes in a management zone.
    zone_boundaries: tuple[float, float]
    zone_tube_counts: tuple[int, int, int]

    @field_validator("coefficients", "depth_range_cm", "zone_boundaries", "zone_tube_counts", mode="before")
    @classmethod
    def json_arrays(cls, value):
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def check_support(self):
        lo, hi = self.depth_range_cm
        a, b = self.zone_boundaries
        if not 0 <= lo < hi or not 0 < a < b < 1 or min(self.zone_tube_counts) < 0:
            raise ValueError("Invalid occurrence profile support")
        return self


class Vineyard3DProfile(BaseModel):
    """Depth-varying cosine field in crown-centred horizontal coordinates (cm).

    Indexed primary origins use model x/y with the vine crown at (0, 0).
    A common-point crown can be translated; the native evaluator subtracts its x/y.
    """

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, frozen=True)
    version: Literal["vineyard_3d_v1"]
    depth_knots_cm: Annotated[tuple[float, ...], Field(min_length=2)]
    # Per-knot coefficients of [1, cos(across), cos(along), cos(across)*cos(along)].
    coefficients: tuple[tuple[float, float, float, float], ...]
    across_period_cm: Annotated[float, Field(gt=0)]
    along_period_cm: Annotated[float, Field(gt=0)]
    fade_cm: Annotated[float, Field(gt=0)]

    @field_validator("depth_knots_cm", mode="before")
    @classmethod
    def json_knots(cls, value):
        return tuple(value) if isinstance(value, list) else value

    @field_validator("coefficients", mode="before")
    @classmethod
    def json_coefficients(cls, value):
        if isinstance(value, (list, tuple)):
            return tuple(tuple(row) if isinstance(row, list) else row for row in value)
        return value

    @model_validator(mode="after")
    def check_knots(self):
        knots = self.depth_knots_cm
        if knots[0] < 0 or any(b <= a for a, b in zip(knots, knots[1:])):
            raise ValueError("Depth knots must be nonnegative and strictly increasing")
        if len(self.coefficients) != len(knots):
            raise ValueError("Each depth knot requires one row of coefficients")
        return self


def _profile_version(value):
    # Original occurrence profiles can omit their default version on input and export.
    if isinstance(value, dict):
        return value.get("version", "occurrence_v1")
    return getattr(value, "version", None)


class DaughterPlacement(BaseModel):
    """Rainfed preferences evaluated only after a terminal parent takes shape."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    parent_order: Annotated[int, Field(ge=2)] = 4
    strength: Annotated[float, Field(ge=0, le=1)] = 0.0
    profile: Annotated[
        Annotated[OccurrenceProfile, Tag("occurrence_v1")] | Annotated[Vineyard3DProfile, Tag("vineyard_3d_v1")],
        Discriminator(_profile_version),
    ] | None = None
    layer_depths_cm: tuple[float, float, float, float] | None = None
    layer_peak_multiplier: Annotated[float, Field(gt=1, le=5)] | None = None
    mode: Literal[
        "redistribute", "branch_probability", "branch_probability_uniform", "retention",
        "add", "uniform_extra", "sparse_depth", "sparse_uniform", "sparse_depth_balanced", "surface_bearing",
    ] = "redistribute"
    spatial_cell_width_cm: Annotated[float, Field(gt=0)] | None = None
    bearing_orders: Annotated[tuple[Annotated[int, Field(ge=2)], ...], Field(min_length=1)] | None = None

    @field_validator("layer_depths_cm", "bearing_orders", mode="before")
    @classmethod
    def json_arrays(cls, value):
        return tuple(value) if isinstance(value, list) else value

    @field_validator("bearing_orders")
    @classmethod
    def unique_bearing_orders(cls, value):
        if value is not None:
            if len(set(value)) != len(value):
                raise ValueError("bearing_orders must list distinct daughter orders")
            return tuple(sorted(value))
        return value

    @model_validator(mode="after")
    def check_mode(self):
        if (self.mode == "surface_bearing") != (self.bearing_orders is not None):
            raise ValueError("bearing_orders is required exclusively for surface_bearing")
        if self.mode == "surface_bearing" and not isinstance(self.profile, Vineyard3DProfile):
            raise ValueError("surface_bearing requires a vineyard_3d_v1 profile")
        if self.mode.startswith("branch_probability") and self.strength and self.profile is None:
            raise ValueError("Changing branch probability requires an occurrence profile")
        if (self.mode == "sparse_depth_balanced") != (self.spatial_cell_width_cm is not None):
            raise ValueError("spatial_cell_width_cm is required exclusively for sparse_depth_balanced")
        if (self.mode in ("add", "uniform_extra") or self.mode.startswith("sparse_")) and self.profile is not None:
            raise ValueError("Extra recruitment uses the depth-layer preference")
        if self.layer_depths_cm is not None or self.layer_peak_multiplier is not None:
            if self.profile is not None or self.mode not in ("redistribute", "add", "uniform_extra"):
                raise ValueError("Depth-layer controls require a contour placement or recruitment arm")
            if self.layer_depths_cm is not None:
                a, b, c, d = self.layer_depths_cm
                if not 0 <= a < b <= c < d:
                    raise ValueError("Layer requires nonnegative, ordered ramp and plateau depths")
        return self
