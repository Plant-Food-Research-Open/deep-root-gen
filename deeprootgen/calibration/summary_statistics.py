"""Contains utilities for calibrating models from summary statistics.

This module defines utility functions for calibrating simulation models from summary statistics.
"""

from deeprootgen.statistics.summary_statistics import RootLengthDensity
import numpy as np
import pandas as pd

from ..data_model import (
    RootCalibrationModel,
    RootSimulationModel,
    SummaryStatisticsModel,
)
from ..model import RootSystemSimulation
from ..statistics import (
    DistanceMetricBase,
    get_distance_metric_func,
    get_summary_statistic_func,
)
from ..statistics.spatial_rld import calculate_core_rld

def get_calibration_summary_stats(input_parameters: RootCalibrationModel) -> tuple:
    """Extract summary statistics needed for model calibration.

    Args:
        input_parameters (RootCalibrationModel):
            The root calibration data model.
    Raises:
        ValueError:
            Error thrown when the summary statistic list is empty.

    Returns:
        tuple:
            The calibration distance metric and summary statistics.
    """
    statistics_comparison = input_parameters.statistics_comparison

    distance_metrics = []
    if isinstance(statistics_comparison.distance_metrics, list):  # type: ignore[union-attr]
        for distance_metric in statistics_comparison.distance_metrics:  # type: ignore[union-attr]
            distance_func = get_distance_metric_func(distance_metric)
            distance = distance_func()
            distance_metrics.append(distance)

    statistics_list: list[SummaryStatisticsModel] = []
    if input_parameters.summary_statistics is None:
        return distance_metrics, statistics_list

    input_statistics = []
    for summary_statistic in input_parameters.summary_statistics:
        statistics_list.append(summary_statistic.dict())
        input_statistics.append(summary_statistic.statistic_name)

    summary_statistics = set(  # noqa: F841
        statistics_comparison.summary_statistics  # type: ignore
    ).intersection(input_statistics)

    statistics_records = (
        pd.DataFrame(statistics_list)
        .query("statistic_name in @summary_statistics")
        .to_dict("records")
    )
    if len(statistics_records) == 0:
        raise ValueError("Summary statistics list cannot be empty.")

    statistics_list = [
        SummaryStatisticsModel.parse_obj(statistic) for statistic in statistics_records
    ]

    return distance_metrics, statistics_list


def run_calibration_simulation(
    parameter_specs: dict,
    input_parameters: RootCalibrationModel,
) -> tuple:
    """Run a simulation for model calibration purposes.

    Args:
        parameter_specs (dict):
            The simulation parameter specification.
        input_parameters (RootCalibrationModel):
            The root calibration data model.

    Returns:
        tuple:
            The simulation and its parameters.
    """
    parameter_specs["random_seed"] = input_parameters.random_seed
    simulation_parameters = RootSimulationModel.parse_obj(parameter_specs)
    simulation = RootSystemSimulation(
        simulation_tag=input_parameters.simulation_tag,  # type: ignore
        random_seed=input_parameters.random_seed,  # type: ignore
    )

    simulation.run(simulation_parameters)
    return simulation, simulation_parameters


def calculate_summary_statistics(
    parameter_specs: dict,
    input_parameters: RootCalibrationModel,
    statistics_list: list[SummaryStatisticsModel],
) -> tuple:
    """Calculate summary statistics for observed and simulated data.

    Args:
        parameter_specs (dict):
            The simulation parameter specification.
        input_parameters (RootCalibrationModel):
            The root calibration data model.
        statistics_list (list[SummaryStatisticsModel]):
            The list of summary statistics.

    Returns:
        tuple:
            The simulated and observed data.
    """
    simulation, simulation_parameters = run_calibration_simulation(
        parameter_specs, input_parameters
    )

    node_df, _ = simulation.G.as_df()
    # Build a soil grid if RLD is being calibrated.
    rld_requested = any(
        s.statistic_name == "root_length_density"
        for s in statistics_list
    )

    soil_df = None

    if rld_requested:
        dimensions = [
            input_parameters.soil_layer_height,
            input_parameters.soil_layer_width,
            input_parameters.soil_n_layers,
            input_parameters.soil_n_cols,
        ]

        if any(v is None or v <= 0 for v in dimensions):
            raise ValueError(
                "RLD calibration requires valid soil dimensions."
            )

        soil_df = simulation.soil.create_soil_grid(
            input_parameters.soil_layer_height,
            input_parameters.soil_n_layers,
            input_parameters.soil_layer_width,
            input_parameters.soil_n_cols,
        )

        # Only for the original Soil implementation.
        soil_df = soil_df.rename(
            columns={"y": "z", "z": "y"}
        )


    observed_values = []
    simulated_values = []
    kwargs = dict(root_tissue_density=simulation_parameters.root_tissue_density)


    for statistic in statistics_list:
        statistic_name = statistic.statistic_name

        if statistic_name == "root_length_density":
            is_spatial = any(
                value is not None
                for value in (
                    statistic.x,
                    statistic.y,
                    statistic.core_radius,
                )
            )

            if is_spatial:
                if any(
                    value is None
                    for value in (
                        statistic.x,
                        statistic.y,
                        statistic.core_radius,
                    )
                ):
                    raise ValueError(
                        "Spatial RLD requires x, y and core_radius."
                    )

                statistic_value = calculate_core_rld(
                    node_df,
                    x=statistic.x,
                    y=statistic.y,
                    z_lower_bound=statistic.z_lower_bound,
                    z_upper_bound=statistic.z_upper_bound,
                    core_radius=statistic.core_radius,
                    diameter_max_mm=statistic.diameter_max_mm,
                    plant_id=statistic.plant_id,
                )

            else:
                # Existing whole-grid RLD calculation.
                # soil_df must be generated beforehand.
                statistic_value = RootLengthDensity(
                    soil_df=soil_df
                ).calculate(node_df)

        else:
            statistic_func = get_summary_statistic_func(
                statistic_name
            )

            statistic_instance = statistic_func(
                root_tissue_density=(
                    simulation_parameters.root_tissue_density
                )
            )

            statistic_value = statistic_instance.calculate(
                node_df
            )

        if not np.isscalar(statistic_value):
            continue

        observed_values.append(statistic.statistic_value)
        simulated_values.append(float(statistic_value))

    observed = np.array(observed_values).flatten()
    simulated = np.array(simulated_values).flatten()

    return simulated, observed


def calculate_summary_statistic_discrepancy(
    parameter_specs: dict,
    input_parameters: RootCalibrationModel,
    statistics_list: list[SummaryStatisticsModel],
    distances: list[DistanceMetricBase],
) -> float:
    """Calculate the discrepancy between simulated and observed data.

    Args:
        parameter_specs (dict):
            The simulation parameter specification.
        input_parameters (RootCalibrationModel):
            The root calibration data model.
        statistics_list (list[SummaryStatisticsModel]):
            The list of summary statistics.
        distances (list[DistanceMetricBase]):
            The distance metric object.

    Returns:
        float:
            The discrepancy between simulated and observed data.
    """
    simulated, observed = calculate_summary_statistics(
        parameter_specs, input_parameters, statistics_list
    )

    discrepancy_list = []
    for distance in distances:
        discrepancy = distance.calculate(observed, simulated)
        discrepancy_list.append(discrepancy)

    discrepancies: float = np.array(discrepancy_list).flatten().sum()
    return discrepancies
