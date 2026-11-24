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
    # Optional wet-zone recruitment of non-terminal daughters, keyed by daughter
    # order k (2 <= k <= parent_order): extra order-k births on order k-1 parents
    # at local rate multiplier 1 + s_k (peak_multiplier - 1) K. Each recruited
    # daughter receives its own native branching subtree. The terminal daughter
    # order (parent_order + 1) always uses s = 1. None keeps the terminal-only law.
    order_sensitivity: dict[str, Annotated[float, Field(ge=0, le=1)]] | None = None
    # Optional moisture-directed growth, keyed by root order: at each curvature
    # step the heading gains step * gain * grad K (K the wet-zone exposure, per
    # cm). Zero outside the footprint; no random draws. None/0 keeps the old law.
    moisture_tropism: dict[str, Annotated[float, Field(ge=0, le=10)]] | None = None
    # Optional recruitment budget: the total expected extra daughters of each
    # recruited order are capped at this fraction of that order's daughters
    # present before recruitment, scaling every parent's expectation equally
    # (wet-zone allocation unchanged). None keeps the uncapped law.
    max_extra_fraction: Annotated[float, Field(gt=0)] | None = None
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

    def upstream_sensitivity(self):
        """Active non-terminal daughter orders and their sensitivities."""
        return {
            int(k): float(v)
            for k, v in (self.order_sensitivity or {}).items()
            if int(k) <= self.parent_order and v > 0
        }

    @model_validator(mode="after")
    def footprint(self):
        if self.order_sensitivity is not None:
            for key, value in self.order_sensitivity.items():
                if not key.isdigit() or key != str(int(key)) or not 2 <= int(key) <= self.parent_order + 1:
                    raise ValueError(
                        "order_sensitivity keys are daughter orders from 2 to parent_order + 1"
                    )
                if int(key) == self.parent_order + 1 and value != 1:
                    raise ValueError(
                        "The terminal daughter order always responds with sensitivity 1"
                    )
            if self.upstream_sensitivity() and self.response == "redistribute":
                raise ValueError(
                    "Non-terminal wet-zone recruitment adds daughters; it has no redistribute form"
                )
        if self.moisture_tropism is not None and any(
            not key.isdigit() or key != str(int(key)) or int(key) < 1
            for key in self.moisture_tropism
        ):
            raise ValueError("moisture_tropism keys are canonical root orders from 1")
        if self.max_extra_fraction is not None and self.response == "redistribute":
            raise ValueError("A recruitment budget caps added daughters; redistribute adds none")
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
