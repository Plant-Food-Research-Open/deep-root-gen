"""One lifecycle for canonical static root configurations.

Each axis uses the selected dimension, attachment, material and direction laws.
The graph writer consumes the final axes once after geometry and material stabilize.
Archived simulations share numerical kernels and the ordered lifecycle executor.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from ..data_model.resolution import ENGINE_LIFECYCLE_VERSION, ENGINE_PHASES, sha256_json
from .materialize import check_curve_postconditions, materialize_forest
from .streams import streams_for


def _counters():
    return dict(surface_reflections=0, diameter_constrained=0, tip_constrained=0, branch_beyond_tip=0,
                length_metadata_reconciliations=[])


@dataclass
class ForestState:
    simulation: Any
    resolved: Any
    parameters: Any
    streams: Any
    initial_recorder: Optional[Any] = None
    trace: list = field(default_factory=list)
    scaffold: dict = field(default_factory=dict)
    direction_nodes: dict = field(default_factory=dict)
    curves: dict = field(default_factory=dict)
    axes: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)
    material_laws: dict = field(default_factory=dict)
    law_counters: dict = field(default_factory=_counters)
    records: Optional[dict] = None
    organ_records: Optional[list] = None
    interval_steps: list = field(default_factory=list)
    interval_fragments: list = field(default_factory=list)
    interval_receipts: list = field(default_factory=list)
    budget: Any = None
    provenance: dict = field(default_factory=dict)
    vine_origin: Optional[tuple] = None
    lifecycle_version: str = ENGINE_LIFECYCLE_VERSION

    @property
    def laws(self):
        return self.resolved.laws

    def organs_in_birth_order(self):
        organs = [o for group in self.simulation.organs.values() for o in group]
        organs.sort(key=organ_id)
        return organs

    def replaced_organs(self):
        """Organs whose direction law is replaced by a curvature law."""
        overrides = self.laws.direction
        return [
            o for order in sorted(overrides)
            if overrides[order]["law"] in ("correlated_curvature", "construction_step_intervals")
            for o in self.simulation.organs.get(order, [])
        ]


def organ_id(organ):
    return int(organ.segments[0].node_data.organ_id)


def execute_canonical(simulation, resolved, *, initial_recorder=None):
    """Evaluate target controls on private forests, then execute the chosen scales."""
    import copy
    from dataclasses import replace

    from .allocation import allocate, allocation_diameter_supports
    from .provenance import run_start
    from .root import RootSystemSimulation

    params = resolved.config.parameters
    if params.allocation_controls is None:
        return execute(simulation, resolved, initial_recorder=initial_recorder)

    provenance = run_start(simulation)
    initial_state = copy.deepcopy(simulation.rng.bit_generator.state)

    def scaled(length, diameter):
        parameters = resolved.parameters.model_copy(update={
            "allocation_length_scales": length, "allocation_diameter_scales": diameter,
        })
        return replace(resolved, parameters=parameters)

    def evaluate(length, diameter):
        trial = RootSystemSimulation(simulation_tag=simulation.simulation_tag, random_seed=resolved.seed)
        trial.rng.bit_generator.state = copy.deepcopy(initial_state)
        settings = scaled(length, diameter)
        execute(trial, settings, provenance=provenance)
        return trial.result.metadata["root_summary"], (length, diameter)

    scales, receipt = allocate(params.root_ratio_biomass, params.root_ratio_length,
                               params.allocation_controls.model_dump(), evaluate,
                               diameter_supports=allocation_diameter_supports(resolved),
                               density_profile=getattr(params.root_tissue_density, "profile", lambda: None)())
    state = execute(simulation, scaled(*scales), initial_recorder=initial_recorder)
    summary = simulation.result.metadata["root_summary"]
    for name, target in receipt["targets"].items():
        actual = summary[f"achieved_{name}"]
        if actual is None or abs(actual - target) > receipt["tolerance"]:
            simulation.result = None
            raise ValueError("Accepted root ratio targets could not be reproduced")
    simulation.result.metadata["allocation"] = receipt
    return state


def execute(simulation, resolved, *, initial_recorder=None, provenance=None):
    return _execute_phases(simulation, resolved, PHASES, initial_recorder=initial_recorder, provenance=provenance)


def _execute_phases(simulation, resolved, phases, *, initial_recorder=None, provenance=None):
    """Run each phase in lifecycle order and publish only a complete result."""
    parameters = resolved.parameters
    if resolved.laws.construction == "native":
        # Input checks first: they draw nothing and mutate nothing.
        simulation._validate_primary_yaw_seed(parameters)
    if len(simulation.G.nodes) != 1 or simulation.organs:
        raise ValueError("Use a fresh simulator for each run")
    state = ForestState(simulation, resolved, parameters, streams_for(simulation), initial_recorder)
    from .provenance import run_start

    from .budget import AllocationBudget

    state.provenance = provenance if provenance is not None else run_start(simulation)
    state.budget = AllocationBudget(resolved.limits)
    if resolved.source_schema in ("3", "4"):
        simulation.G.allocation_budget = state.budget
    simulation.result = None
    try:
        for name in ENGINE_PHASES:
            phases[name](state)
            state.trace.append(name)
    except Exception:
        simulation.result = None
        raise
    return state


# ---------------------------------------------------------------------------
# Prepare forest
# ---------------------------------------------------------------------------


def prepare_forest(state):
    """Sample the biological forest, construction intervals and birth sites."""
    primary_count = int(state.parameters.outer_root_num) + int(state.parameters.inner_root_num)
    organ_limit = state.resolved.limits.get("max_organs")
    if state.resolved.source_schema in ("3", "4") and organ_limit is not None:
        counts = getattr(state.parameters, "research_root_counts_by_order", None)
        minimum_count = primary_count if counts is None else sum(counts.values())
        if minimum_count > organ_limit:
            raise ValueError("Organ limit exceeded before forest allocation; organs are never truncated")
    sim, p = state.simulation, state.parameters
    sim._validate_primary_yaw_seed(p)
    replacements = _native_replacements(state)
    if replacements is None:
        sim.init_organs(p)
    else:
        origin_law = state.laws.origins or {}
        layout = origin_law.get("layout")
        if layout == "vine_catalogue":
            from .vine_origins import select_vine_origin

            state.vine_origin = select_vine_origin(origin_law, state.streams)
            layout = state.vine_origin[0]["layout"]
        if layout in ("disk", "primary_layout"):
            state.budget.check_nodes(primary_count)
            _per_primary_workspace(state)
        sim.init_organs(p, laws=replacements)
    bind_axis_states(state)


def bind_axis_states(state):
    from .axis_state import AxisState, BirthContext

    # Every input shares the same axis facade, including compatibility
    # schedules. Immutable sampled values are captured once; mutable geometry
    # and final attachments remain owned by the workspace/curve.
    for organ in state.organs_in_birth_order():
        if not hasattr(organ, "axis_state"):
            contexts = tuple(
                BirthContext(n.node_data.diameter, n.node_data.length, n.node_data.order, n.node_data.root_tissue_density)
                for n in organ.segments
            )
            organ.axis_state = AxisState(organ, organ_id(organ), contexts)
        organ.axis_state.birth_parent_biological_id = int(organ.parent_node.node_data.organ_id)
        organ.axis_state.sampled_lengths_cm = tuple(float(v) for v in organ.get_lengths())
    limit = state.resolved.limits.get("max_organs")
    count = sum(len(group) for group in state.simulation.organs.values())
    if limit is not None and count > limit:
        raise ValueError(f"Organ limit exceeded ({count} > {limit}); organs are never truncated")


def _native_replacements(state):
    """Leaf replacements inside native construction, or None when all native."""
    laws = state.laws
    if state.resolved.source_schema not in ("3", "4") and not (laws.taper or laws.lengths or laws.branching or laws.maturity or laws.cap or laws.origins):
        return None
    from .native_features import NativeFeatureLaws

    return NativeFeatureLaws(state)


def _per_primary_workspace(state):
    """Workspace with one provisional zero-material base per primary."""
    from ..data_model import RootNodeModel
    from .hgraph import RootSystemGraph

    sim, p = state.simulation, state.parameters
    graph = RootSystemGraph(create_base=False)
    graph.organ_id = 1  # organ 0 is reserved for bases
    graph.allocation_budget = state.budget
    for index in range(int(p.outer_root_num) + int(p.inner_root_num)):
        graph.bases.append(graph.add_node(RootNodeModel(
            parent_id=-1, plant_id=1, organ_id=0, order=0, segment_rank=index + 1, x=0.0, y=0.0, z=0.0,
            diameter=0.0, length=0.0, root_tissue_density=p.root_tissue_density, invalid_root=False,
            simulation_tag=sim.simulation_tag, root_type="base", order_type="base",
        )))
    graph.base_node = graph.bases[0] if graph.bases else None
    sim.G = graph
    state.anchors = list(graph.bases)


# ---------------------------------------------------------------------------
# Place scaffold, INITIAL view, corrections and attachments
# ---------------------------------------------------------------------------


def place_scaffold(state):
    """Native placement arithmetic and order, or origin/heading laws."""
    sim, p, laws = state.simulation, state.parameters, state.laws
    sim.position_secondary_roots(p)
    sim.position_primary_roots(p)
    if laws.origins is not None:
        from .native_features import place_origins

        place_origins(state)


def record_initial(state):
    """Optional read-only INITIAL view; it never mutates the workspace."""
    if state.initial_recorder is not None:
        from .initial_view import initial_view

        state.initial_recorder(*initial_view(state.simulation, state.parameters))


def pre_direction(state):
    """Declared pre-direction law: native Fichtl primary repair or a pure check."""
    sim, p, law = state.simulation, state.parameters, state.laws.pre
    if law == "fichtl_primary_validation_repair_v1":
        sim.validate(p, pitch=60, orders=(1,))
        sim._check_optional_primary_validation(p)
    elif law == "frozen_scaffold_surface_check_v1":
        surface = state.laws.surface_z_cm
        if any(n.node_data.z > surface for n in sim.G.nodes if n.node_data.order <= 1):
            raise ValueError("Frozen primary scaffold exceeds common physical surface")
    elif law is not None:
        raise ValueError(f"Unknown pre-direction law {law!r}")


def attachments(state):
    """Final attachment arcs; birth context and sampled dimensions are retained."""
    if state.laws.relocation is not None:
        _relocate_in_workspace(state)


def _relocate_in_workspace(state):
    """Distal relocation with the one historical kernel, committed to the workspace.

    The records view goes through the construction-step relocation law
    (new_arc = fraction * L + (1 - fraction) * old_arc, interval split without
    changing material, minimal-rotation transport of each daughter subtree).
    Inserted construction points keep their reserved IDs in the workspace; the
    writer later allocates published IDs in birth order. Sampled daughter
    dimensions are preserved.
    """
    from ..data_model import RootNodeModel
    from .execution import _organ_records, _records, _relocate
    from .hgraph import RootNode

    sim = state.simulation
    rows, records = _records(sim), _organ_records(sim)
    inserted = _relocate(rows, records, state.laws.relocation["distal_fraction"])
    graph = sim.G
    live = {node.node_data.node_id: node for node in graph.nodes}
    for nid in sorted(rows):
        data = RootNodeModel(**rows[nid])
        if nid in live:
            live[nid].node_data = data
        else:
            live[nid] = RootNode(graph, data)
    graph.node_id = max(live) + 1
    objects = {organ_id(o): o for group in sim.organs.values() for o in group}
    for record in records:
        organ = objects[record["organ_id"]]
        organ.segments = [live[n] for n in record["node_ids"]]
        organ.parent_node = live[record["parent_id"]]
        organ.base_node = organ.segments[0]
        for node in organ.segments:
            node.organ = organ
    # Canonical parent-before-child workspace order: bases, then organs by birth.
    ordered = [n for n in graph.nodes if n.node_data.order == 0]
    for organ in sorted(objects.values(), key=organ_id):
        ordered.extend(organ.segments)
    graph.nodes = ordered
    state.diagnostics["attachment_relocation"] = dict(
        moved=[dict(organ_id=r["organ_id"], original_arc_cm=r.get("attachment_arc_cm")) for r in records
               if r["order"] == 2],
        inserted_construction_point_ids=list(inserted),
    )


# ---------------------------------------------------------------------------
# Direction realization
# ---------------------------------------------------------------------------


def realize_directions(state):
    """Parent-first direction laws; every axis starts from its realized parent."""
    begin_directions(state)
    _realize_native(state)


def begin_directions(state):
    state.budget.minimum_curve_nodes = len(state.simulation.G.bases) + sum(
        len(o.segments) for order, group in state.simulation.organs.items() if order not in state.laws.direction
        for o in group
    )
    # Fingerprint of every biology/placement draw: invariant under replaced laws.
    state.diagnostics["native_rng_before_directions_sha256"] = sha256_json(
        state.streams.native.bit_generator.state
    )


def _place_construction_points(organ, curve):
    for node, xyz in zip(organ.segments, curve.position(curve.construction_arcs)):
        node.node_data.x, node.node_data.y, node.node_data.z = (float(v) for v in xyz)


def _irrigated_directions(state, order, organs, law, transverse):
    zone = getattr(state.resolved.config, "irrigation", None)
    if zone is None or zone.peak_multiplier == 1 or order != zone.parent_order + 1:
        return transverse
    from .irrigation_branching import recruit_terminals
    from .sibling_placement import sibling_directions

    before = len(organs)
    recruit_terminals(state, zone)
    if "sibling_sectors" in law:
        if zone.response == "redistribute":
            return sibling_directions(state, organs, law["sibling_sectors"])
        transverse.update(sibling_directions(state, organs[before:], law["sibling_sectors"]))
    return transverse


def _realize_replaced_order(state, order, tangent_at, placement, transfer, bearing, receipts, skipped):
    organs = state.simulation.organs.get(order, [])
    transverse = {}
    law = state.laws.direction[order]
    if transfer is not None and transfer.transfer_probability and order - 1 in transfer.parent_orders:
        from .birth_depth import transfer_birth_sites

        transfer_birth_sites(state, order - 1, transfer)
    if (placement is not None and placement.mode != "surface_bearing"
            and (placement.strength or placement.mode == "retention")
            and order == placement.parent_order + 1):
        from .daughter_placement import apply_terminal_preference

        apply_terminal_preference(state, placement)
    if "sibling_sectors" in law:
        from .sibling_placement import sibling_directions

        transverse = sibling_directions(state, organs, law["sibling_sectors"])
    transverse = _irrigated_directions(state, order, organs, law, transverse)
    order_bearing = bearing if bearing is not None and order in bearing.bearing_orders else None
    for organ in organs:
        if organ.invalid_root:
            # A scaffold invalidated by a native pre-direction correction
            # stays native and invalid, exactly as the native laws treat it.
            skipped.append(organ_id(organ))
            continue
        if law["law"] == "construction_step_intervals":
            curve = _realize_construction_curve(state, organ, law)
        else:
            curve = _realize_native_curve(state, organ, law, tangent_at,
                                          transverse.get(organ_id(organ)), order_bearing)
        if law["law"] != "construction_step_intervals":
            _place_construction_points(organ, curve)
        state.curves[organ_id(organ)] = curve
        if hasattr(organ, "axis_state"):
            organ.axis_state.curve = curve
        receipts.append(curve.receipt)


def _realize_native(state):
    sim, p, laws = state.simulation, state.parameters, state.laws
    replaced = state.replaced_organs()
    fichtl = laws.native_direction == "fichtl_search_v1"
    # Archived output includes diagnostics for configured but empty orders.
    lateral_orders = None if state.resolved.source_schema != "4" else [
        order for order, organs in sim.organs.items() if order >= 2 and organs
    ]
    if not replaced:
        if fichtl and lateral_orders is None:
            sim.apply_fichtl_tropism(p)
        elif fichtl and lateral_orders:
            sim.apply_fichtl_tropism(p, orders=lateral_orders)
        elif laws.native_direction == "legacy_gravitropism_blend_v1":
            sim.apply_gravitropism(p.gravitropism)
        return
    state.scaffold = {
        n.node_data.node_id: np.array([n.node_data.x, n.node_data.y, n.node_data.z]) for n in sim.G.nodes
    }
    state.direction_nodes = {node.node_data.node_id: node for node in sim.G.nodes}
    receipts, skipped = [], []
    state.diagnostics["curvature"] = receipts

    def tangent_at(node, chord):
        return _tangent(state, node, chord)

    placement = getattr(state.resolved.config, "daughter_placement", None)
    transfer = getattr(state.resolved.config, "birth_depth_transfer", None)
    bearing = placement if placement and placement.mode == "surface_bearing" and placement.strength else None
    if bearing is not None:
        from .daughter_placement import BEARING_GAIN, BEARING_PROBE_CM

        state.diagnostics["daughter_placement"] = dict(settings=bearing.model_dump(exclude_none=True),
                                                       max_probe_cm=BEARING_PROBE_CM, softmax_gain=BEARING_GAIN)
    first_native_lateral = True
    for order in range(1, int(p.max_order) + 1):
        if order in laws.direction:
            _realize_replaced_order(state, order, tangent_at, placement, transfer, bearing, receipts, skipped)
        elif fichtl and order >= 2 and (lateral_orders is None or order in lateral_orders):
            sim.apply_fichtl_tropism(p, scaffold=state.scaffold, tangent_at=tangent_at, orders=[order],
                                     reset_diagnostics=first_native_lateral)
            first_native_lateral = False
    if skipped:
        state.diagnostics["curvature_not_realized_invalid_scaffolds"] = skipped
    if not fichtl:
        _translate_native_daughters(state)
        fallback_orders = set(sim.organs) - set(laws.direction)
        if laws.native_direction == "legacy_gravitropism_blend_v1" and any(sim.organs[k] for k in fallback_orders):
            fixed = {n.node_data.node_id for o in replaced for n in o.segments}
            sim.apply_gravitropism(p.gravitropism, fixed=fixed)


def _realize_construction_curve(state, organ, law):
    """The existing interval kernel as a per-axis calculation, with no writer.

    Rows are a detached leaf input. The authoritative workspace is updated by
    the common direction phase and the common materializer emits all cuts.
    """
    from ..utils.tropism import validate_row_axial_kappas
    from .execution import _organ_records, _partition, _records
    from .interval_geometry import realize_intervals
    from .materialize import AxisCurve

    state.budget.reserve("stations", len(organ._construction_step_lengths_cm) + 1)
    rows = _records(state.simulation)
    record = next(r for r in _organ_records(state.simulation) if r["organ_id"] == organ_id(organ))
    partition = _partition(record, rows, organ)
    parent = organ.parent_node
    row = rows[parent.node_data.node_id]
    chord = np.array([row[k] - rows[row["parent_id"]][k] for k in ("x", "y", "z")])
    tangent = _tangent(state, parent, chord)
    p = state.parameters
    records, mapping, receipt = realize_intervals(
        record, partition, rows, p.model_dump(), state.resolved.seed, law["boundary"], law["surface_z_cm"],
        validate_row_axial_kappas(p.research_insertion_row_axial_kappa, p.max_order), tangent,
    )
    boundaries = organ.construction_step_boundary_node_ids
    stations = np.r_[0., np.cumsum(organ._construction_step_lengths_cm)]
    points = np.array([[rows[n][k] for k in ("x", "y", "z")]
                       for n in [parent.node_data.node_id, *boundaries]])
    state.interval_steps.extend(records)
    state.interval_fragments.extend(mapping)
    state.interval_receipts.append(receipt)
    for node in organ.segments:
        node.node_data.x, node.node_data.y, node.node_data.z = (float(rows[node.node_data.node_id][k]) for k in ("x", "y", "z"))
    arcs = np.cumsum(organ.get_lengths())
    # The captured boundary ID proves these are the same construction events;
    # canonical arclength labels come from their actual fragment partition.
    indices = {n.node_data.node_id: i for i, n in enumerate(organ.segments)}
    stations = np.r_[0., [arcs[indices[nid]] for nid in boundaries]]
    return AxisCurve(organ_id(organ), stations, points, arcs, dict(law), receipt)


def _realize_native_curve(state, organ, law, tangent_at, transverse=None, bearing=None):
    """Curvature on a natively constructed axis, from its realized attachment."""
    from ..utils.tropism import insertion_heading, row_axial_insertion_heading
    from .axis_laws import realize_correlated_curvature
    from .laws import law_stream

    if law["initial_heading"] == "insertion_angle":
        parent = organ.parent_node
        grandparent = state.direction_nodes.get(parent.node_data.parent_id, state.simulation.G.nodes[0])
        position = np.array([parent.node_data.x, parent.node_data.y, parent.node_data.z])
        chord = position - np.array([grandparent.node_data.x, grandparent.node_data.y, grandparent.node_data.z])
        tangent = tangent_at(parent, chord)
        oid = organ_id(organ)
        heading = insertion_heading(tangent, law["insertion_mean_deg"], law["insertion_sd_deg"],
                                    law_stream(state.streams, state.laws.streams, "insertion", oid))
        if transverse is not None:
            axis = tangent / np.linalg.norm(tangent)
            cosine = np.clip(heading @ axis, -1., 1.)
            heading = cosine * axis + np.sqrt(max(0., 1. - cosine**2)) * transverse
        axial_receipt = None
        bearing_receipt = None
        if "row_axial_kappa" in law:
            order = int(parent.node_data.order) + 1
            heading, axial_receipt = row_axial_insertion_heading(
                tangent, heading, law["row_axial_kappa"], state.resolved.seed, oid, order,
            )
        if bearing is not None:
            from .daughter_placement import surface_bearing_heading

            order = int(organ.segments[0].node_data.order)
            length_cm = float(organ.get_lengths().sum())
            heading, bearing_receipt = surface_bearing_heading(
                state, bearing, tangent, heading, position, length_cm, order, oid,
            )
        curve = realize_correlated_curvature(organ, law, state.streams, start=position, heading=heading,
                                             reserve_stations=state.budget.reserve)
        if transverse is not None:
            curve.receipt["sibling_sector_applied"] = True
        if axial_receipt is not None:
            curve.receipt["row_axial_insertion"] = axial_receipt
        if bearing_receipt is not None:
            curve.receipt["surface_bearing"] = bearing_receipt
        return curve
    if law["initial_heading"] == "origin_heading":
        return realize_correlated_curvature(organ, law, state.streams, heading=organ.plan["initial_heading"],
                                            reserve_stations=state.budget.reserve)
    return realize_correlated_curvature(organ, law, state.streams, reserve_stations=state.budget.reserve)


def _tangent(state, node, chord):
    """Realized parent tangent at an attachment node, by the parent's law."""
    organ = getattr(node, "organ", None)
    curve = None if organ is None else state.curves.get(organ_id(organ))
    if curve is None:
        return chord
    index = next(i for i, n in enumerate(organ.segments) if n is node)
    return curve.tangent(
        curve.construction_arcs[index], coincidence_cm=state.laws.materialization["corner_coincidence_cm"]
    )


def _translate_native_daughters(state):
    """Native legacy daughters are rigid relative to their attachment point."""
    for organ in state.organs_in_birth_order():
        if organ_id(organ) in state.curves:
            continue
        parent_organ = getattr(organ.parent_node, "organ", None)
        if parent_organ is None or organ_id(parent_organ) not in state.curves:
            continue
        attachment = organ.parent_node.node_data
        delta = np.array([attachment.x, attachment.y, attachment.z]) - state.scaffold[attachment.node_id]
        subtree = [organ]
        while subtree:
            current = subtree.pop()
            current.set_coordinates(current.get_coordinates() + delta)
            subtree.extend(current.child_organs)


# ---------------------------------------------------------------------------
# Post-direction corrections, materialization, emission, checks, publication
# ---------------------------------------------------------------------------


def post_direction(state):
    """Declared post-direction law; replaced axes are checked, never repaired."""
    sim, p, law = state.simulation, state.parameters, state.laws.post
    if law == "fichtl_lateral_validation_check_v1":
        sim.validate(p, pitch=60, orders=range(2, p.max_order + 1), allow_reorient=False)
    elif law == "legacy_validation_repair_v1":
        replaced = state.replaced_organs()
        if replaced:
            sim.validate(p, pitch=60, check_only={organ_id(o) for o in replaced})
        else:
            sim.validate(p, pitch=60)
        sim._check_optional_primary_validation(p)
    elif law == "workspace_pure_checks_v1":
        if any(n.node_data.z > state.laws.surface_z_cm for n in sim.G.nodes):
            raise ValueError("Realized forest exceeds the declared soil surface")
    elif law is not None:
        raise ValueError(f"Unknown post-direction law {law!r}")


def materialize(state):
    if state.resolved.source_schema == "4" and (state.parameters.min_branching_diameter_cm or state.laws.cap):
        from .branch_eligibility import validate_branching_diameters

        validate_branching_diameters(state)
    state.axes = materialize_forest(state.organs_in_birth_order(), state.curves, state)


def emit(state):
    """Sole writer: published graph and organ registry are published together."""
    from .hgraph import publish_graph

    sim, laws = state.simulation, state.laws
    organs = state.organs_in_birth_order()
    state.budget.check_nodes(len(sim.G.bases) + sum(len(v) for v in state.axes.values()))
    sim.G = publish_graph(sim.G, organs, axes=state.axes, first_node_id=laws.writer.get("first_node_id", 0))
    if state.resolved.source_schema == "4":
        settings = state.resolved.config.parameters.root_tissue_density
        if hasattr(settings, "bounds_mm"):
            from .segment_density import apply_diameter_density

            sim.diameter_density = settings.profile()
            for organ in organs:
                apply_diameter_density(organ, sim.diameter_density)
            return
    for organ in organs:
        if organ_id(organ) in state.curves or organ_id(organ) in state.material_laws:
            organ.mass = organ.calculate_mass()


def check(state):
    """Pure integrity and law postconditions; draw nothing, repair nothing."""
    check_graph(state)
    for organ in state.organs_in_birth_order():
        curve = state.curves.get(organ_id(organ))
        if curve is not None:
            check_curve_postconditions(organ, curve, curve.law["surface_z_cm"])


def check_graph(state):
    from .integrity import validate_result

    sim = state.simulation
    validate_result(sim)
    limit = state.resolved.limits.get("max_nodes")
    if limit is not None and len(sim.G.nodes) > limit:
        raise ValueError(f"Node limit exceeded ({len(sim.G.nodes)} > {limit})")


def publish(state):
    from .views import native_view
    from .material_summary import summarize_root_material

    result = native_view(state)
    result.metadata["root_summary"] = summarize_root_material(
        state.simulation, state.parameters.max_order, state.parameters.fine_root_threshold,
        getattr(state, "tapers", None),
    )
    if hasattr(state.simulation, "diameter_density"):
        result.metadata["tissue_density_by_diameter"] = state.resolved.config.parameters.root_tissue_density.model_dump()
    state.simulation.result = result


PHASES = dict(
    prepare_forest=prepare_forest,
    place_scaffold=place_scaffold,
    record_initial=record_initial,
    pre_direction=pre_direction,
    attachments=attachments,
    realize_directions=realize_directions,
    post_direction=post_direction,
    materialize=materialize,
    emit=emit,
    check=check,
    publish=publish,
)
if tuple(PHASES) != ENGINE_PHASES:
    raise RuntimeError("Engine phase table disagrees with the declared lifecycle")
