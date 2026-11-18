"""Historical controlled-search replay and validation."""
import copy
from collections.abc import Mapping

from ..research.search_evaluation import ROUTES, _integer, _number, summarize_sample


def validate_simulation_parameters(parameters, *, route: str):
    """Validate the same route/model scope as execution without constructing.

    Returns detached JSON-compatible model parameters. This is a schema/route
    preflight, not a claim that construction or the declared positive traits pass.
    """
    if route not in ROUTES:
        raise ValueError(f"route must explicitly select one of {ROUTES}")
    if hasattr(parameters, "model_dump"):
        values = parameters.model_dump()
    elif isinstance(parameters, Mapping):
        values = copy.deepcopy(dict(parameters))
    else:
        raise ValueError("parameters must be a mapping or RootSimulationModel")
    _integer(values.get("random_seed"), "parameters.random_seed")
    if _number(values.get("soil_surface_z_cm"), "soil_surface_z_cm") != 20.:
        raise ValueError("Controlled search requires an explicit fixed soil surface at 20 cm")
    maximum = _integer(values.get("max_order"), "parameters.max_order", 3)
    if maximum > 5 or values.get("tropism_mode") != "fichtl2024":
        raise ValueError("The positive-trait bridge requires Fichtl mode and max_order 3, 4 or 5")
    grid = values.get("research_current_length_grid")
    if route == "construction_steps_v1" and grid != "construction_steps_v1":
        raise ValueError("Construction-step route requires matching construction_steps_v1 parameters")
    if route == "graph_segments_v1" and (
        grid is not None or values.get("research_parent2_branch_zone_cm") is not None
        or values.get("research_tertiary_length_rank_strength")
        or values.get("research_primary_attachment_distal_fraction")
    ):
        raise ValueError("Graph-segment route cannot use construction-step-only parameters")
    from ..data_model import RootSimulationModel
    unknown = set(values).difference(RootSimulationModel.model_fields)
    if unknown:
        raise ValueError(f"Unknown simulation parameters would be ignored: {sorted(unknown)}")
    return RootSimulationModel(**values).model_dump()


def simulate_sample(parameters, seed: int, *, route: str):
    """Construct a fresh INITIAL and explicitly replay existing controlled arm D.

    Caller-supplied seeds must match. No skeleton is reused when parameters
    change. The existing constructor's internal simulation tag is preserved;
    the requested tag and a separate run identity are reported in diagnostics.
    """
    seed = _integer(seed, "seed")
    if hasattr(parameters, "model_dump"):
        values = parameters.model_dump()
    elif isinstance(parameters, Mapping):
        values = copy.deepcopy(dict(parameters))
    else:
        raise ValueError("parameters must be a mapping or RootSimulationModel")
    if "random_seed" in values and _integer(values["random_seed"], "parameters.random_seed") != seed:
        raise ValueError("parameters.random_seed must match the requested seed")
    values["random_seed"] = seed
    validated = validate_simulation_parameters(values, route=route)
    from ..research.so4_controlled import construct_skeleton, digest, replay_arm

    if route == "construction_steps_v1":
        from ..data_model import RootSimulationConfig
        from .simulation import RootSystemSimulation
        from ..research.so4_controlled import capture_initial
        snapshots = []
        config = RootSimulationConfig(random_seed=seed, simulation_tag=validated['simulation_tag'],
                                      construction=dict(kind='native', parameters=validated), trajectory='construction_steps_v1')
        simulation = RootSystemSimulation(random_seed=seed)
        simulation.run(config, initial_recorder=lambda sim, p: snapshots.append(capture_initial(sim, p)))
        initial = snapshots[0]
        nodes, edges = simulation.G.as_df()
        result = dict(nodes=nodes, edges=edges)
    else:
        # Archived graph-segment experiment; not a supported extended contract.
        initial = construct_skeleton(validated, seed)
        result = replay_arm(initial, "D", validated, "minimum_angle_projection", surface_z=20.)
    sample = summarize_sample(result["nodes"], result["edges"], seed=seed, surface_z_cm=20.,
                              root_orders=list(range(1, validated["max_order"] + 1)))
    identity = dict(route=route, seed=seed, parameters=validated, initial_sha256=initial.sha256)
    sample["diagnostics"].update(
        simulation_route=route, arm="D", boundary_policy="minimum_angle_projection",
        initial_sha256=initial.sha256, fresh_initial_construction=True,
        requested_simulation_tag=validated["simulation_tag"],
        constructor_simulation_tag=initial.payload["parameters"]["simulation_tag"],
        run_identity_sha256=digest(identity),
    )
    return sample
