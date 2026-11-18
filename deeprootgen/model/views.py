"""Result views: one ``SimulationResult`` class whose contents follow capabilities.

Engine receipts (lifecycle trace, RNG fingerprint, keyed streams, law
receipts) always go to ``result.engine``. A historical adapter declares the
serialized result format of its contract (``EngineLaws.view``) so its frozen
tables and diagnostics stay byte-identical; the view never selects execution.
"""

import pandas as pd


def _identity(state, seed):
    resolved = state.resolved
    return dict(resolved.hashes, run_identity_sha256=resolved.run_identity(seed))


def _engine(state):
    return dict(
        lifecycle=list(state.trace) + ["publish"],
        native_rng_before_directions_sha256=state.diagnostics.get("native_rng_before_directions_sha256"),
        keyed_streams=list(state.streams.issued),
        law_receipts={k: v for k, v in state.diagnostics.items() if k != "native_rng_before_directions_sha256"},
    )


def tree_labels(organs):
    """Primary tree ID and group label of every organ; daughters inherit both."""
    labels = {}
    for organ in organs:
        oid = int(organ.segments[0].node_data.organ_id)
        plan = getattr(organ, "plan", None) or {}
        parent = getattr(organ.parent_node, "organ", None)
        if parent is None or int(organ.segments[0].node_data.order) == 1:
            labels[oid] = (plan.get("tree", oid), plan.get("label") or getattr(organ, "group_label", None) or "")
        else:
            labels[oid] = labels[int(parent.segments[0].node_data.organ_id)]
    return labels


def _tree_sidecar(sim, organs):
    """Primary-tree and group label for every published node, in node order."""
    labels = tree_labels(organs)
    primaries = list(sim.organs.get(1, []))
    base_owner = {
        base.node_data.node_id: int(primaries[index].segments[0].node_data.organ_id)
        for index, base in enumerate(sim.G.bases)
        if index < len(primaries)
    }
    rows = []
    for node in sim.G.nodes:
        if node.node_data.order == 0:
            owner = base_owner.get(node.node_data.node_id)
            tree, label = labels[owner] if owner is not None else (0, "")
        else:
            tree, label = labels[int(node.node_data.organ_id)]
        rows.append(dict(node_id=node.node_data.node_id, primary_tree_id=tree, cohort=label))
    return pd.DataFrame(rows)


def native_view(state):
    from .execution import SimulationResult

    sim, resolved, p = state.simulation, state.resolved, state.parameters
    seed = resolved.seed if resolved.seed is not None else getattr(sim, "random_seed", None)
    organs = state.organs_in_birth_order()
    labels = tree_labels(organs)
    rows = []
    for organ in organs:
        oid = int(organ.segments[0].node_data.organ_id)
        plan = getattr(organ, "plan", None) or {}
        tree, group = labels[oid]
        rows.append(dict(
            organ_id=oid,
            order=int(organ.segments[0].node_data.order),
            parent_node_id=int(organ.parent_node.node_data.node_id),
            parent_organ_id=int(organ.parent_node.node_data.organ_id),
            length_cm=float(organ.get_lengths().sum()),
            segment_count=len(organ.segments),
            direction_law=state.curves[oid].law["law"] if oid in state.curves else "native",
            material_law=state.material_laws.get(oid, "native_cylinder"),
            invalid_root=bool(organ.invalid_root),
            mass_g=float(organ.mass),
            maturity=plan.get("maturity", getattr(organ, "maturity", 1.0)),
            primary_tree_id=tree,
            group=group,
        ))
    multiple = len(sim.G.bases) > 1
    tree_map = multiple or any(getattr(o, "plan", None) for o in organs)
    metadata = dict(
        schema_version={"flat": 1, "2": 2, "3": 3}[resolved.source_schema],
        execution="native",
        seed=seed,
        requested_simulation_tag=(
            resolved.requested_simulation_tag
            if resolved.requested_simulation_tag is not None
            else sim.simulation_tag
        ),
        tropism_mode=getattr(p, "tropism_mode", "legacy"),
        biological_validation=False,
        lifecycle_version=state.lifecycle_version,
        capabilities=dict(multiple_bases=multiple, tree_to_vine_map=bool(tree_map), crown_support_view=False),
        **_identity(state, seed),
    )
    diagnostics = {k: v for k, v in state.diagnostics.items() if k != "native_rng_before_directions_sha256"}
    return SimulationResult(
        metadata=metadata,
        organ_table=pd.DataFrame(rows),
        diagnostics=diagnostics,
        node_metadata=_tree_sidecar(sim, organs) if tree_map else pd.DataFrame(),
        resolved=dict(resolved.description, hashes=_identity(state, seed)),
        engine=_engine(state),
    )


def cohort_v5_view(state):
    """Historical cohort serialization: organ table, diagnostics, sidecar, crown."""
    from ..research.core_observation import qualify_root_segments
    from .execution import SimulationResult

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
    from .execution import SimulationResult

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
