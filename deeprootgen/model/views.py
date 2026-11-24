"""Canonical result tables, metadata and execution diagnostics."""

import pandas as pd


def _identity(state, seed):
    resolved = state.resolved
    from ..data_model.resolution import sha256_json

    return dict(resolved.hashes, run_identity_sha256=sha256_json(dict(
        effective_model_sha256=resolved.hashes["effective_model_sha256"], seed=seed,
        execution=state.provenance,
    )))


def _engine(state):
    return dict(
        lifecycle=list(state.trace) + ["publish"],
        provenance=state.provenance,
        materialization=state.law_counters,
        construction_steps=state.interval_steps,
        interval_fragments=state.interval_fragments,
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
    tree_map = multiple or state.laws.maturity is not None
    metadata = dict(
        schema_version={"flat": 1, "2": 2, "3": 3, "4": 4}[resolved.source_schema],
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
    if resolved.source_schema == "4":
        from .branch_eligibility import branching_receipt

        metadata["resolved_primary_counts"] = dict(total=p.outer_root_num + p.inner_root_num,
                                                   outer=p.outer_root_num, inner=p.inner_root_num)
        state.diagnostics["branching"] = branching_receipt(sim, p)
    diagnostics = {k: v for k, v in state.diagnostics.items() if k != "native_rng_before_directions_sha256"}
    return SimulationResult(
        metadata=metadata,
        organ_table=pd.DataFrame(rows),
        diagnostics=diagnostics,
        node_metadata=_tree_sidecar(sim, organs) if tree_map else pd.DataFrame(),
        resolved=dict(resolved.description, hashes=_identity(state, seed)),
        engine=_engine(state),
    )
