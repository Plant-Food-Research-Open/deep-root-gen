"""Historical cohort API; fresh generation is owned by native run()."""

from dataclasses import dataclass
import pandas as pd
from ..model.cohort_geometry import (
    bounded_draw,
    taper_diameter,
    material_cuts,
    equivalent_diameter,
    integrate_curve,
    reconcile_interval_lengths,
)
from ..model.cohort import VERSION, validate_cohort_config


@dataclass
class CohortArchitecture:
    nodes: pd.DataFrame
    edges: pd.DataFrame
    organs: pd.DataFrame
    observation_nodes: pd.DataFrame
    observation_edges: pd.DataFrame
    diagnostics: dict


class CohortRootGenerator:
    """Compatibility configuration/export adapter to RootSystemSimulation.run."""

    def __init__(self, config):
        self.config = validate_cohort_config(config)

    def generate(self, seed, older_count, later_count):
        from ..data_model.execution import RootSimulationConfig
        from ..model import RootSystemSimulation

        config = RootSimulationConfig(
            random_seed=seed,
            trajectory="cohort_v5",
            construction=dict(
                kind="cohort",
                parameters=self.config,
                older_count=older_count,
                later_count=later_count,
            ),
        )
        simulation = RootSystemSimulation(random_seed=seed)
        simulation.run(config)
        result = simulation.result
        nodes, edges = result.cohort_tables(simulation.G)
        projected = nodes.loc[nodes.node_id.ne(0)].copy()
        projected["plant_id"] = projected.primary_tree_id
        projected.loc[projected.order.eq(0), "parent_id"] = -1
        projected_edges = edges.loc[edges.parent_id.ne(0)].copy()
        return CohortArchitecture(
            nodes,
            edges,
            result.organ_table,
            projected,
            projected_edges,
            result.diagnostics,
        )
