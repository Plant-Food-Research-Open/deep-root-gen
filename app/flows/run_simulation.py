#!/usr/bin/env python

######################################
# Imports
######################################

import mlflow
from prefect import flow, task
from prefect.task_runners import ConcurrentTaskRunner

from deeprootgen.data_model.canonical import RootConfig
from deeprootgen.data_model.simulation_form import SoilDisplay
from deeprootgen.data_model.resolution import resolve_config
from deeprootgen.io import save_graph_to_db
from deeprootgen.model import RootSystemSimulation
from deeprootgen.pipeline import (
    begin_experiment,
    log_config,
    log_experiment_details,
    log_simulation,
)

######################################
# Constants
######################################

TASK = "simulation"

######################################
# Main
######################################


@task
def execute_simulation(input_parameters: RootConfig) -> RootSystemSimulation:
    """Execute the root simulation.

    Args:
        input_parameters (RootConfig):
            The root simulation data model.

    Returns:
        RootSystemSimulation:
            The root simulation.
    """
    resolve_config(input_parameters)
    simulation = RootSystemSimulation(
        simulation_tag=input_parameters.simulation_tag,  # type: ignore
        random_seed=input_parameters.random_seed,  # type: ignore
    )
    simulation.run(input_parameters)
    return simulation


@task
def run_simulation(input_parameters: RootConfig, simulation_uuid: str, soil_display: SoilDisplay | None = None) -> None:
    """Running a single root simulation.

    Args:
        input_parameters (RootConfig):
            The root simulation data model.
        simulation_uuid (str):
            The simulation uuid.
    """
    resolve_config(input_parameters)
    begin_experiment(TASK, simulation_uuid, input_parameters.simulation_tag)
    log_experiment_details(simulation_uuid)
    simulation = execute_simulation(input_parameters)
    config = input_parameters.model_dump(mode="json", exclude_unset=True)

    log_config(config, TASK)
    log_simulation(input_parameters, simulation, TASK, soil_display)
    save_graph_to_db(simulation, TASK, simulation_uuid)
    mlflow.end_run()


@flow(
    name="simulation",
    description="Run a single simulation for the root model.",
    task_runner=ConcurrentTaskRunner(),
)
def run_simulation_flow(
    input_parameters: RootConfig, simulation_uuid: str, soil_display: SoilDisplay | None = None
) -> None:
    """Flow for running a single root simulation.

    Args:
        input_parameters (RootConfig):
            The root simulation data model.
        simulation_uuid (str):
            The simulation uuid.
    """
    resolve_config(input_parameters)
    run_simulation.submit(input_parameters, simulation_uuid, soil_display).result()
