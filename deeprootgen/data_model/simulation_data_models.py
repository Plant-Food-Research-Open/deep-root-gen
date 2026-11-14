"""Contains Pydantic data models for the simulation

Several Pydantic data models are defined for different
root system architecture simulation procedures.

"""

import math
from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from ..utils.current_length import validate_current_length_cdf
from ..utils.tropism import row_axial_controls_active, validate_row_axial_kappas


class Config:
    arbitrary_types_allowed = True


class RootType(Enum):
    STRUCTURAL = "structural"
    FINE = "fine"
    PRIMARY = "primary"
    SECONDARY = "secondary"
    OUTER = "outer"
    INNER = "inner"


class RootTypeModel(BaseModel):
    """The root type data model for classifying roots.

    Args:
        BaseModel (BaseModel):
            The Pydantic Base model class.
    """

    root_type: str
    order_type: str
    position_type: str


class RootNodeModel(BaseModel):
    """The node data model for the hierarchical graph representation of the root system.

    Args:
        BaseModel (BaseModel):
            The Pydantic Base model class.
    """

    node_id: Optional[int] = 0
    plant_id: Optional[int] = 1
    parent_id: Optional[int] = -1
    organ_id: Optional[int] = 0
    x: Optional[float] = 0.0
    y: Optional[float] = 0.0
    z: Optional[float] = 0.0
    order: Optional[int] = 0
    segment_rank: Optional[int] = 0
    diameter: Optional[float] = 0.0
    length: Optional[float] = 0.0
    root_tissue_density: Optional[float] = 0.0
    root_type: Optional[str] = "base"
    order_type: Optional[str] = "base"
    position_type: Optional[str] = "base"
    simulation_tag: Optional[str] = "default"
    invalid_root: Optional[bool] = False


class RootEdgeModel(BaseModel):
    """The edge data model for the hierarchical graph representation of the root system.

    Args:
        BaseModel (BaseModel):
            The Pydantic Base model class.
    """

    parent_id: int
    child_id: int


class CurrentLengthCDF(BaseModel):
    """Explicit discrete current organ-length CDF; support is in cm."""

    lengths_cm: List[float]
    cumulative_probabilities: List[float]

    @model_validator(mode="after")
    def validate_discrete_cdf(self):
        validate_current_length_cdf(self.lengths_cm, self.cumulative_probabilities)
        return self


class RootSimulationModel(BaseModel):
    """
    The root system architecture simulation data model.

    Args:
        BaseModel (BaseModel):
            The Pydantic Base model class.
    """

    random_seed: int | None
    max_order: int
    root_ratio: float
    fine_root_threshold: float
    outer_root_num: int
    inner_root_num: int
    min_primary_length: float
    max_primary_length: float
    base_diameter: float
    diameter_reduction: float
    apex_diameter: float
    min_sec_root_num: int
    max_sec_root_num: int
    growth_sec_root: float
    min_sec_root_length: float
    max_sec_root_length: float
    segments_per_root: int
    length_reduction: float
    root_vary: float
    interbranch_distance: float
    mechanical_constraints: float
    root_tissue_density: float
    gravitropism: float
    t: int
    origin_min: Optional[float] = 1e-3
    origin_max: Optional[float] = 1e-2
    enable_soil: Optional[bool] = False
    soil_layer_height: Optional[float] = 0
    soil_layer_width: Optional[float] = 0
    soil_n_layers: Optional[int] = 0
    soil_n_cols: Optional[int] = 0
    max_val_attempts: Optional[int] = 50
    simulation_tag: Optional[str] = "default"
    no_root_zone: Optional[float] = 1e-4
    floor_threshold: Optional[float] = 0.4
    ceiling_threshold: Optional[float] = 0.9
    research_branch_placement: Literal["legacy_spacing", "redistribute_capped"] = "legacy_spacing"
    research_current_length_cdfs_cm: Optional[Dict[int, CurrentLengthCDF]] = None
    research_insertion_row_axial_kappa: Optional[Dict[int, float]] = None
    research_primary_yaw_mean_deg: Optional[float] = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    research_primary_yaw_kappa: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    research_base_origin_x_cm: Optional[float] = Field(default=None, allow_inf_nan=False)
    research_base_origin_y_cm: Optional[float] = Field(default=None, allow_inf_nan=False)
    research_base_depth_cm: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    tropism_mode: Literal["legacy", "fichtl2024"] = "legacy"
    soil_surface_z_cm: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    fichtl_probability_down: Optional[float] = Field(default=None, ge=0, le=1)
    fichtl_sigma: Optional[float] = Field(default=None, ge=0)
    fichtl_trials_type2: Optional[float] = Field(default=None, ge=0, le=100)
    fichtl_trials_type3: Optional[float] = Field(default=None, ge=0, le=100)
    fichtl_theta2_deg: Optional[float] = Field(default=None, ge=0, le=90)
    fichtl_theta2_sd_deg: Optional[float] = Field(default=None, ge=0)
    fichtl_theta3_deg: Optional[float] = Field(default=None, ge=0, le=90)
    fichtl_theta3_sd_deg: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_insertion_row_axial(self):
        self.research_insertion_row_axial_kappa = validate_row_axial_kappas(
            self.research_insertion_row_axial_kappa, self.max_order,
        )
        if row_axial_controls_active(self.research_insertion_row_axial_kappa):
            if self.tropism_mode != "fichtl2024" or self.random_seed is None:
                raise ValueError("Active row-axial insertion requires Fichtl mode and explicit random_seed")
        return self

    @model_validator(mode="after")
    def validate_current_length_orders(self):
        cdfs = self.research_current_length_cdfs_cm
        if cdfs is not None:
            if not cdfs or any(order not in (2, 3) or order > self.max_order for order in cdfs):
                raise ValueError("Current-length CDFs require a nonempty selection of supported orders 2/3")
            if self.random_seed is None or self.segments_per_root <= 0:
                raise ValueError("Current-length CDFs require an explicit random_seed and positive segments_per_root")
        return self

    @model_validator(mode="after")
    def require_explicit_root_origin(self):
        values = (self.research_base_origin_x_cm, self.research_base_origin_y_cm, self.research_base_depth_cm)
        if any(value is not None for value in values):
            if any(value is None for value in values):
                raise ValueError("Research base origin x/y/depth must be supplied together")
            if "soil_surface_z_cm" not in self.model_fields_set:
                raise ValueError("Research base origin requires an explicit soil_surface_z_cm")
            if self.tropism_mode != "fichtl2024":
                raise ValueError("Research base origin currently requires fichtl2024 mode")
        return self

    @model_validator(mode="after")
    def require_paired_primary_yaw_parameters(self):
        if (self.research_primary_yaw_mean_deg is None) != (self.research_primary_yaw_kappa is None):
            raise ValueError("Research primary yaw mean and kappa must be supplied together")
        if self.research_primary_yaw_mean_deg is not None and self.random_seed is None:
            raise ValueError("Research primary yaw requires an explicit random_seed")
        return self

    @model_validator(mode="after")
    def require_explicit_fichtl_parameters(self):
        if self.soil_surface_z_cm and self.enable_soil:
            raise ValueError(
                "Offset soil surface requires the offline aligned observation route"
            )
        if self.tropism_mode == "fichtl2024":
            if self.gravitropism != 0:
                raise ValueError("Set legacy gravitropism to zero in fichtl2024 mode")
            if self.max_order > 3:
                raise ValueError(
                    "fichtl2024 mode currently supports orders 1 through 3"
                )
            names = (
                "fichtl_probability_down",
                "fichtl_sigma",
                "fichtl_trials_type2",
                "fichtl_trials_type3",
                "fichtl_theta2_deg",
                "fichtl_theta2_sd_deg",
                "fichtl_theta3_deg",
                "fichtl_theta3_sd_deg",
            )
            if any(getattr(self, name) is None for name in names):
                raise ValueError(
                    "fichtl2024 mode requires explicit tropism/angle parameters"
                )
            if any(not math.isfinite(getattr(self, name)) for name in names):
                raise ValueError("fichtl2024 parameters must be finite")
        return self


class ParameterIntervalModel(BaseModel):
    """The parameter specification data model.

    Args:
        BaseModel (BaseModel):
            The Pydantic Base model class.
    """

    lower_bound: float
    upper_bound: float
    data_type: str


class SummaryStatisticsModel(BaseModel):
    """The summary statistics data model.

    Args:
        BaseModel (BaseModel):
            The Pydantic Base model class.
    """

    statistic_name: str
    statistic_value: float

    z_lower_bound: Optional[float] = 0.0
    z_upper_bound: Optional[float] = 0.0

    # Spatial soil-core observations
    sample_id: Optional[str] = None
    plant_id: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None
    core_radius: Optional[float] = None

    # Optional restriction to smaller root diameters
    diameter_max_mm: Optional[float] = None


class StatisticsComparisonModel(BaseModel):
    """The data model for comparing synthetic and observed data.

    Args:
        BaseModel (BaseModel):
            The Pydantic Base model class.
    """

    summary_statistics: Optional[List[str]] = None
    distance_metrics: Optional[List[str]] = None
    include_parameters: Optional[List[str]] = None
    exclude_parameters: Optional[List[str]] = None
    input_columns: Optional[List[str]] = None
    output_columns: Optional[List[str]] = None
    stat_by_soil_layer: Optional[bool] = False
    stat_by_soil_column: Optional[bool] = False
    use_summary_statistics: Optional[bool] = True


class RootCalibrationIntervals(BaseModel):
    """
    The root system architecture calibration interval data model.

    Args:
        BaseModel (BaseModel):
            The Pydantic Base model class.
    """

    max_order: ParameterIntervalModel
    root_ratio: ParameterIntervalModel
    fine_root_threshold: ParameterIntervalModel
    outer_root_num: ParameterIntervalModel
    inner_root_num: ParameterIntervalModel
    min_primary_length: ParameterIntervalModel
    max_primary_length: ParameterIntervalModel
    base_diameter: ParameterIntervalModel
    diameter_reduction: ParameterIntervalModel
    apex_diameter: ParameterIntervalModel
    min_sec_root_num: ParameterIntervalModel
    max_sec_root_num: ParameterIntervalModel
    growth_sec_root: ParameterIntervalModel
    min_sec_root_length: ParameterIntervalModel
    max_sec_root_length: ParameterIntervalModel
    segments_per_root: ParameterIntervalModel
    length_reduction: ParameterIntervalModel
    root_vary: ParameterIntervalModel
    interbranch_distance: ParameterIntervalModel
    mechanical_constraints: ParameterIntervalModel
    root_tissue_density: ParameterIntervalModel
    gravitropism: ParameterIntervalModel
    t: ParameterIntervalModel


class RootCalibrationModel(BaseModel):
    """
    The root system architecture calibration data model.

    Args:
        BaseModel (BaseModel):
            The Pydantic Base model class.
    """

    random_seed: int | None
    parameter_intervals: RootCalibrationIntervals
    calibration_parameters: Dict[str, bool | float | int | str]
    summary_statistics: Optional[List[SummaryStatisticsModel]] = None
    observed_data: Optional[List[RootNodeModel]] = None
    observed_data_content: Optional[str] = ""
    raw_edge_content: Optional[str] = ""
    statistics_comparison: Optional[StatisticsComparisonModel] = None
    origin_min: Optional[float] = 1e-3
    origin_max: Optional[float] = 1e-2
    enable_soil: Optional[bool] = False
    soil_layer_height: Optional[float] = 0
    soil_layer_width: Optional[float] = 0
    soil_n_layers: Optional[int] = 0
    soil_n_cols: Optional[int] = 0
    max_val_attempts: Optional[int] = 50
    simulation_tag: Optional[str] = "default"
    no_root_zone: Optional[float] = 1e-4
    floor_threshold: Optional[float] = 0.4
    ceiling_threshold: Optional[float] = 0.9
