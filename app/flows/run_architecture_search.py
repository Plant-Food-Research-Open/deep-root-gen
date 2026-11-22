"""Queue a canonical whole-root fit in the existing Prefect worker."""
from pathlib import Path
from uuid import UUID

from prefect import flow

from deeprootgen.pipeline import get_outdir
from deeprootgen.research.architecture_search import run_architecture_search


@flow(name="architecture_search")
def run_architecture_search_flow(input_parameters: dict, simulation_uuid: str):
    job_id = str(UUID(simulation_uuid))
    summary = run_architecture_search(input_parameters, Path(get_outdir()) / "architecture-search" / job_id)
    if summary["completed_trials"] == 0:
        raise ValueError("No feasible trial completed. Review the trial table.")
    return summary
