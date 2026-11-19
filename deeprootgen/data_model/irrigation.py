"""Surveyed irrigation geometry in the vineyard frame (centimetres)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Positive = Annotated[float, Field(gt=0)]


class Irrigation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    treatment: Literal["buried_drip", "surface_drip", "broad_surface"]
    irrigation_depth_cm: Annotated[float, Field(ge=0)]
    peak_multiplier: Annotated[float, Field(ge=1)] = 1.0
    response: Literal["add", "redistribute", "uniform_extra"] = "add"
    parent_order: Annotated[int, Field(ge=1)] = 4
    line_offsets_cm: list[float] | None = None
    row_period_cm: Positive | None = None
    across_radius_cm: Positive | None = None
    emitter_spacing_cm: Positive | None = None
    emitter_origin_y_cm: float | None = None
    along_radius_cm: Positive | None = None
    upper_radius_cm: Positive | None = None
    lower_radius_cm: Positive | None = None
    surface_profile: Literal["plateau", "deep_peak"] = "plateau"
    origin_x_cm: float = 0.0
    origin_y_cm: float = 0.0
    reflect_x: Literal[-1, 1] = 1
    reflect_y: Literal[-1, 1] = 1

    @model_validator(mode="after")
    def footprint(self):
        drip = self.treatment != "broad_surface"
        if drip:
            if not self.line_offsets_cm or self.across_radius_cm is None:
                raise ValueError("Drip requires line_offsets_cm and across_radius_cm")
            if len(set(self.line_offsets_cm)) != len(self.line_offsets_cm):
                raise ValueError("Repeated irrigation line offset")
        elif self.line_offsets_cm is not None or self.across_radius_cm is not None:
            raise ValueError("Broad surface irrigation covers the horizontal domain")
        if self.row_period_cm is not None and (
            not drip or len(self.line_offsets_cm) != 1
        ):
            raise ValueError("Periodic rows require one explicit reference line")
        emitter = (
            self.emitter_spacing_cm,
            self.emitter_origin_y_cm,
            self.along_radius_cm,
        )
        if any(v is not None for v in emitter) and (
            not drip or any(v is None for v in emitter)
        ):
            raise ValueError(
                "Discrete drip outlets require spacing, origin and along-row radius"
            )
        if self.treatment == "buried_drip":
            if (
                self.irrigation_depth_cm <= 0
                or self.upper_radius_cm is None
                or self.lower_radius_cm is None
            ):
                raise ValueError(
                    "Buried drip requires positive outlet depth and both vertical radii"
                )
            if (
                "surface_profile" in self.model_fields_set
                and self.surface_profile != "plateau"
            ):
                raise ValueError(
                    "A surface depth profile applies only to surface irrigation"
                )
        elif self.irrigation_depth_cm != 0 or any(
            v is not None for v in (self.upper_radius_cm, self.lower_radius_cm)
        ):
            raise ValueError(
                "Surface irrigation uses zero outlet depth and its declared 0–50 cm profile"
            )
        return self
