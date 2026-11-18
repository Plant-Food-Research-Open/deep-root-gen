"""Serialized result formats for explicitly archived simulations."""
import pandas as pd

from ..model.views import native_view, _engine, _tree_sidecar, _identity


def cohort_v5_view(state):
    """Historical cohort serialization: organ table, diagnostics, sidecar, crown."""
    from ..research.core_observation import qualify_root_segments
    from ..model.execution import SimulationResult

    sim, resolved = state.simulation, state.resolved
    options = resolved.laws.view_options
    seed = resolved.seed
    graph = sim.G
    nodes, edges = graph.as_df()
    sidecar = _tree_sidecar(sim, state.organs_in_birth_order())
    projection = nodes.merge(sidecar, on="node_id", validate="one_to_one")
    projection["plant_id"] = projection.primary_tree_id
    support = qualify_root_segments(
        projection,
        edges,
        coordinate_frame=options["coordinate_frame"],
        fine_diameter_max_mm=options["fine_cutoff_mm"],
        dry_density_g_cm3=options["dry_density_g_cm3"],
    )
    records = [state.planned_records[int(o.segments[0].node_data.organ_id)] for o in state.organs_in_birth_order()]
    counters = state.law_counters
    diagnostics = dict(
        version=options["version"],
        seed=seed,
        surface_reflections=counters["surface_reflections"],
        diameter_constrained=counters["diameter_constrained"],
        tip_constrained=counters["tip_constrained"],
        branch_beyond_tip=counters["branch_beyond_tip"],
        length_metadata_reconciliations=counters["length_metadata_reconciliations"],
        crown_mass_g=options["crown_mass_g"],
        maturity_is_age_years=False,
    )
    diagnostics["root_totals"] = support.whole_system_totals["included"]
    diagnostics["unrepresented_fine_mass_g"] = options["unrepresented_fine_mass_g"]
    diagnostics["combined_with_crown_mass_g"] = (
        sum(o["dry_mass_g"] for o in records) + options["crown_mass_g"] + options["unrepresented_fine_mass_g"]
    )
    diagnostics["max_depth_cm"] = float(-nodes.z.min())
    diagnostics["root_below_150cm"] = bool(nodes.loc[nodes.order.gt(0), "z"].lt(-150).any())
    identity = _identity(state, seed)
    return SimulationResult(
        metadata=dict(
            schema_version=2,
            execution="cohort_v5",
            seed=seed,
            coordinate_frame=options["coordinate_frame"],
            biological_validation=False,
            requested_simulation_tag=resolved.requested_simulation_tag,
            capabilities=dict(multiple_bases=True, tree_to_vine_map=True, crown_support_view=True),
            lifecycle_version=state.lifecycle_version,
            **identity,
        ),
        organ_table=pd.DataFrame(records),
        diagnostics=diagnostics,
        node_metadata=sidecar,
        crown_support=dict(
            center_cm=[0.0, 0.0, -options["crown_depth_cm"][0]],
            anchor_ids=[n.node_data.node_id for n in graph.bases],
            dry_mass_g=options["crown_mass_g"],
        ),
        resolved=dict(resolved.description, hashes=identity),
        engine=_engine(state),
    )


def construction_steps_view(state):
    """Historical construction-step serialization: intervals, fragments, receipts."""
    from ..model.execution import SimulationResult

    resolved = state.resolved
    options = resolved.laws.view_options
    identity = _identity(state, resolved.seed)
    return SimulationResult(
        metadata=dict(
            schema_version=2,
            execution="construction_steps_v1",
            seed=resolved.seed,
            requested_simulation_tag=resolved.requested_simulation_tag,
            internal_simulation_tag=options["internal_simulation_tag"],
            coordinate_frame=options["coordinate_frame"],
            biological_validation=False,
            capabilities=dict(multiple_bases=False, tree_to_vine_map=False, crown_support_view=False),
            lifecycle_version=state.lifecycle_version,
            **identity,
        ),
        organ_table=pd.DataFrame(
            [{k: v for k, v in o.items() if k != "construction_steps"} for o in state.organ_records]
        ),
        diagnostics=dict(
            construction_steps=state.interval_steps,
            graph_fragments=state.interval_fragments,
            organs=state.interval_receipts,
        ),
        resolved=dict(resolved.description, hashes=identity),
        engine=_engine(state),
    )


VIEWS = dict(native=native_view, cohort_v5=cohort_v5_view, construction_steps_v1=construction_steps_view)
