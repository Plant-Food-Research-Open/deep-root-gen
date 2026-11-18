"""Fixed execution lifecycle shared by every input.

prepare forest -> place scaffold -> optional read-only INITIAL view ->
pre-direction corrections -> attachment mapping -> direction realization ->
post-direction corrections -> materialize -> emit (sole writer) -> pure checks
-> publish. Phases always run in this order; an unused operation is a no-op.
The executor owns traversal and phase transitions. The resolved law table
(``ResolvedConfig.laws``) selects leaf laws per stage and order; it never
selects a phase list or a complete runner, and route labels select nothing.

Construction state is the workspace: provisional construction points plus the
``RootOrgan`` axis records (biological identity, construction intervals,
scaffold coordinates, sampled plans). Record-based interval laws operate on a
records view of the same workspace from attachment mapping onward. The
published graph is written once, after geometry is stable.

Native sequential draws keep their historical order. A replaced direction law
draws only from its keyed stream, and native corrections visiting a replaced
axis consume their usual draw but only check. Every biology and placement draw
is therefore unchanged by a replaced direction law; later correction draws can
differ when validity outcomes differ. A replaced construction law draws
nothing natively.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from ..data_model.resolution import ENGINE_LIFECYCLE_VERSION, ENGINE_PHASES, sha256_json
from .materialize import check_curve_postconditions, materialize_forest, planned_axis
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
    curves: dict = field(default_factory=dict)
    axes: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)
    material_laws: dict = field(default_factory=dict)
    law_counters: dict = field(default_factory=_counters)
    planned_records: dict = field(default_factory=dict)
    records: Optional[dict] = None
    organ_records: Optional[list] = None
    interval_steps: list = field(default_factory=list)
    interval_fragments: list = field(default_factory=list)
    interval_receipts: list = field(default_factory=list)
    deferred_failure: Optional[dict] = None
    lifecycle_version: str = ENGINE_LIFECYCLE_VERSION

    @property
    def laws(self):
        return self.resolved.laws

    @property
    def planned(self):
        return self.laws.construction == "planned"

    def organs_in_birth_order(self):
        organs = [o for group in self.simulation.organs.values() for o in group]
        organs.sort(key=organ_id)
        return organs

    def replaced_organs(self):
        """Organs whose direction law is replaced by a curvature law."""
        overrides = self.laws.direction
        return [
            o for order in sorted(overrides)
            if overrides[order]["law"] == "correlated_curvature"
            for o in self.simulation.organs.get(order, [])
        ]


def organ_id(organ):
    return int(organ.segments[0].node_data.organ_id)


def execute(simulation, resolved, *, initial_recorder=None):
    """Run every phase in the fixed order; no successful result after failure."""
    parameters = resolved.parameters
    if resolved.laws.construction == "native":
        # Input checks first: they draw nothing and mutate nothing.
        simulation._validate_primary_yaw_seed(parameters)
    if len(simulation.G.nodes) != 1 or simulation.organs:
        raise ValueError("Use a fresh simulator for each run")
    state = ForestState(simulation, resolved, parameters, streams_for(simulation), initial_recorder)
    simulation.result = None
    try:
        for name in ENGINE_PHASES:
            PHASES[name](state)
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
    if state.planned:
        _prepare_planned(state)
    else:
        sim, p = state.simulation, state.parameters
        sim._validate_primary_yaw_seed(p)
        replacements = _native_replacements(state)
        if replacements is None:
            sim.init_organs(p)
        else:
            if state.laws.origins is not None and state.laws.origins["layout"] == "disk":
                _per_primary_workspace(state)
            sim.init_organs(p, laws=replacements)
    limit = state.resolved.limits.get("max_organs")
    count = sum(len(group) for group in state.simulation.organs.values())
    if limit is not None and count > limit:
        raise ValueError(f"Organ limit exceeded ({count} > {limit}); organs are never truncated")


def _native_replacements(state):
    """Leaf replacements inside native construction, or None when all native."""
    laws = state.laws
    if not (laws.taper or laws.lengths or laws.branching or laws.maturity or laws.cap or laws.origins):
        return None
    from .native_features import NativeFeatureLaws

    return NativeFeatureLaws(state)


def _per_primary_workspace(state):
    """Workspace with one provisional zero-material base per primary (disk origins)."""
    from ..data_model import RootNodeModel
    from .hgraph import RootSystemGraph

    sim, p = state.simulation, state.parameters
    graph = RootSystemGraph(create_base=False)
    graph.organ_id = 1  # organ 0 is reserved for bases
    for index in range(int(p.outer_root_num) + int(p.inner_root_num)):
        graph.bases.append(graph.add_node(RootNodeModel(
            parent_id=-1, plant_id=1, organ_id=0, order=0, segment_rank=index + 1, x=0.0, y=0.0, z=0.0,
            diameter=0.0, length=0.0, root_tissue_density=p.root_tissue_density, invalid_root=False,
            simulation_tag=sim.simulation_tag, root_type="base", order_type="base",
        )))
    graph.base_node = graph.bases[0] if graph.bases else None
    sim.G = graph
    state.anchors = list(graph.bases)


def _prepare_planned(state):
    """Every construction law replaced: breadth-first planned organs, no native draws."""
    from ..data_model import RootNodeModel, RootTypeModel
    from .hgraph import RootSystemGraph
    from .laws import law_stream, primary_maturity, sample_planned_organ, site_diameter
    from .root import RootOrgan

    sim, p, laws = state.simulation, state.parameters, state.laws
    max_order = int(p.max_order)
    outer = int(p.outer_root_num)
    primaries = outer + int(p.inner_root_num)
    limits = state.resolved.limits
    limit = limits.get("max_organs")
    message = limits.get("organ_limit_message", "Organ limit exceeded; organs are never truncated")
    if limit is not None and primaries > limit:
        raise ValueError("Initial primary organ budget exhausted")
    graph = RootSystemGraph(create_base=False)
    graph.organ_id = 1  # organ 0 is reserved for bases
    sim.G = graph
    sim.organs = {order: [] for order in range(1, max_order + 1)}
    tag, density = state.resolved.simulation_tag, p.root_tissue_density
    historical_labels = laws.materialization.get("position_type") == "base"
    queue = deque()
    for index in range(primaries):
        anchor = graph.add_node(RootNodeModel(
            parent_id=-1, plant_id=1, organ_id=0, order=0, segment_rank=index + 1, x=np.nan, y=np.nan, z=np.nan,
            diameter=0.0, length=0.0, root_tissue_density=density, invalid_root=False, simulation_tag=tag,
            root_type="base", order_type="base",
        ))
        graph.bases.append(anchor)
        oid = graph.increment_organ_id()
        maturity, label = 1.0, None
        if laws.maturity is not None:
            maturity, label = primary_maturity(
                laws.maturity, index, law_stream(state.streams, laws.streams, "maturity", oid)
            )
        queue.append(dict(oid=oid, order=1, parent=anchor, parent_organ=None, maturity=maturity, label=label,
                          tree=oid, attachment_cm=0.0, parent_diameter=None, index=index,
                          position_type="outer" if index < outer else "inner"))
    graph.base_node = graph.bases[0] if graph.bases else None
    counters = state.law_counters
    while queue:
        task = queue.popleft()
        oid, order = task["oid"], task["order"]
        rngs = {
            purpose: law_stream(state.streams, laws.streams, purpose, oid)
            for purpose in ("length", "taper", "branching")
        }
        sample = sample_planned_organ(order, max_order, task["maturity"], task["parent_diameter"], laws, rngs, counters)
        organ = RootOrgan(
            task["parent"], input_parameters=p,
            root_type=RootTypeModel(root_type="structural", order_type="primary" if order == 1 else "secondary",
                                    position_type="cohort" if historical_labels else task["position_type"]),
            simulation_tag=tag, rng=sim.rng, planned=True,
        )
        arcs = [*sample["sites"], sample["length"]]
        previous, segments, start = task["parent"], [], 0.0
        for rank, arc in enumerate(arcs, 1):
            node = graph.add_node(RootNodeModel(
                parent_id=previous.node_data.node_id, plant_id=1, organ_id=oid, order=order, segment_rank=rank,
                x=np.nan, y=np.nan, z=np.nan, length=arc - start, root_tissue_density=density, simulation_tag=tag,
            ))
            node.organ = organ
            segments.append(node)
            previous, start = node, arc
        organ.segments, organ.base_node = segments, segments[0]
        organ.lateral_attachment_nodes = segments[:-1]
        organ.plan = dict(
            sample, order=order, maturity=task["maturity"], label=task["label"], tree=task["tree"],
            attachment_cm=task["attachment_cm"],
            parent_organ_id=0 if task["parent_organ"] is None else organ_id(task["parent_organ"]),
            position_type=task["position_type"], index=task.get("index"),
        )
        organ.cohort, organ.maturity = task["label"], task["maturity"]
        if task["parent_organ"] is not None:
            task["parent_organ"].child_organs.append(organ)
        sim.organs[order].append(organ)
        allocated = []
        for k, site in enumerate(sample["sites"]):
            child = graph.increment_organ_id()
            if limit is not None and child > limit:
                # Historical precedence: the budget fails while this organ's
                # daughters are allocated, after its own curve and material.
                # Later organs are never sampled; the failure is raised in
                # materialize once this organ has been realized.
                state.deferred_failure = dict(message=message, organ_id=oid, allocated=allocated)
                break
            allocated.append((child, site))
            queue.append(dict(oid=child, order=order + 1, parent=segments[k], parent_organ=organ,
                              maturity=task["maturity"], label=task["label"], tree=task["tree"], attachment_cm=site,
                              parent_diameter=site_diameter(organ.plan, site), position_type=task["position_type"]))
        organ.lateral_attachment_nodes = []  # birth sites are consumed by their daughters
        if state.deferred_failure is not None:
            break


# ---------------------------------------------------------------------------
# Place scaffold, INITIAL view, corrections and attachments
# ---------------------------------------------------------------------------


def place_scaffold(state):
    """Native placement arithmetic and order, or origin/heading laws."""
    sim, p, laws = state.simulation, state.parameters, state.laws
    if state.planned:
        from .laws import disk_origin, law_stream, radial_inclination

        for index, primary in enumerate(sim.organs.get(1, [])):
            oid = organ_id(primary)
            start, phi = disk_origin(laws.origins, law_stream(state.streams, laws.streams, "origin", oid))
            anchor = sim.G.bases[index].node_data
            anchor.x, anchor.y, anchor.z = (float(v) for v in start)
            primary.plan["initial_heading"] = radial_inclination(
                laws.origins["heading"], phi, law_stream(state.streams, laws.streams, "heading", oid)
            )
        return
    sim.position_secondary_roots(p)
    sim.position_primary_roots(p)
    if laws.origins is not None:
        from .native_features import place_origins

        place_origins(state)


def record_initial(state):
    """Optional read-only INITIAL view; it never mutates the workspace."""
    if state.initial_recorder is not None:
        state.initial_recorder(state.simulation, state.parameters)


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
    sim, laws = state.simulation, state.laws
    if laws.writer.get("records"):
        from .execution import _organ_records, _records, _relocate

        state.records, state.organ_records = _records(sim), _organ_records(sim)
        if laws.relocation is not None:
            _relocate(state.records, state.organ_records, laws.relocation["distal_fraction"])
    elif laws.relocation is not None:
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
    # Fingerprint of every biology/placement draw: invariant under replaced laws.
    state.diagnostics["native_rng_before_directions_sha256"] = sha256_json(
        state.streams.native.bit_generator.state
    )
    if state.planned:
        _realize_planned(state)
    elif state.laws.writer.get("records"):
        _realize_intervals(state)
    else:
        _realize_native(state)


def _realize_planned(state):
    from ..utils.tropism import insertion_heading
    from .axis_laws import realize_correlated_curvature
    from .laws import law_stream

    laws = state.laws
    coincidence = laws.materialization["corner_coincidence_cm"]
    receipts = []
    for organ in state.organs_in_birth_order():
        plan, oid = organ.plan, organ_id(organ)
        law = laws.direction[plan["order"]]
        if plan["order"] == 1:
            anchor = organ.parent_node.node_data
            start, heading = np.array([anchor.x, anchor.y, anchor.z]), plan["initial_heading"]
        else:
            parent = state.curves[organ_id(organ.parent_node.organ)]
            site = plan["attachment_cm"]
            start = parent.position([site])[0]
            tangent = parent.tangent(site, coincidence_cm=coincidence)
            heading = insertion_heading(tangent, law["insertion_mean_deg"], law["insertion_sd_deg"],
                                        law_stream(state.streams, laws.streams, "insertion", oid))
        curve = realize_correlated_curvature(
            organ, law, state.streams, start=start, heading=heading, length=plan["length"],
            arcs=np.asarray([*plan["sites"], plan["length"]], dtype=float),
            rng=law_stream(state.streams, laws.streams, "curvature", oid),
        )
        state.law_counters["surface_reflections"] += curve.receipt["surface_reflections"]
        _place_construction_points(organ, curve)
        state.curves[oid] = curve
        receipts.append(curve.receipt)
    state.diagnostics["curvature"] = receipts


def _place_construction_points(organ, curve):
    for node, xyz in zip(organ.segments, curve.position(curve.construction_arcs)):
        node.node_data.x, node.node_data.y, node.node_data.z = (float(v) for v in xyz)


def _realize_intervals(state):
    """Record-based construction-step interval law for every daughter order."""
    from ..utils.tropism import validate_row_axial_kappas
    from .execution import _partition
    from .interval_geometry import realize_intervals

    sim, p, laws = state.simulation, state.parameters, state.laws
    rows, organs = state.records, state.organ_records
    objects = {organ_id(o): o for group in sim.organs.values() for o in group}
    kappas = validate_row_axial_kappas(p.research_insertion_row_axial_kappa, p.max_order)
    partitions = {o["organ_id"]: _partition(o, rows, objects[o["organ_id"]]) for o in organs if o["order"] > 1}
    settings, incoming = p.model_dump(), {}
    for organ in sorted((o for o in organs if o["order"] > 1), key=lambda o: (o["order"], o["organ_id"])):
        law = laws.direction[organ["order"]]
        records, mapping, receipt = realize_intervals(
            organ, partitions[organ["organ_id"]], rows, settings, state.resolved.seed, law["boundary"],
            law["surface_z_cm"], kappas, incoming.get(organ["parent_id"]),
        )
        for item in mapping:
            incoming[item["node_id"]] = records[item["step_index"]]["accepted_heading"]
        state.interval_steps.extend(records)
        state.interval_fragments.extend(mapping)
        state.interval_receipts.append(receipt)


def _realize_native(state):
    sim, p, laws = state.simulation, state.parameters, state.laws
    replaced = state.replaced_organs()
    fichtl = laws.native_direction == "fichtl_search_v1"
    if not replaced:
        if fichtl:
            sim.apply_fichtl_tropism(p)
        elif laws.native_direction == "legacy_gravitropism_blend_v1":
            sim.apply_gravitropism(p.gravitropism)
        return
    state.scaffold = {
        n.node_data.node_id: np.array([n.node_data.x, n.node_data.y, n.node_data.z]) for n in sim.G.nodes
    }
    receipts, skipped = [], []
    state.diagnostics["curvature"] = receipts

    def tangent_at(node, chord):
        return _tangent(state, node, chord)

    first_native_lateral = True
    for order in range(1, int(p.max_order) + 1):
        if order in laws.direction:
            for organ in sim.organs.get(order, []):
                if organ.invalid_root:
                    # A scaffold invalidated by a native pre-direction correction
                    # stays native and invalid, exactly as the native laws treat it.
                    skipped.append(organ_id(organ))
                    continue
                curve = _realize_native_curve(state, organ, laws.direction[order], tangent_at)
                _place_construction_points(organ, curve)
                state.curves[organ_id(organ)] = curve
                receipts.append(curve.receipt)
        elif fichtl and order >= 2:
            sim.apply_fichtl_tropism(p, scaffold=state.scaffold, tangent_at=tangent_at, orders=[order],
                                     reset_diagnostics=first_native_lateral)
            first_native_lateral = False
    if skipped:
        state.diagnostics["curvature_not_realized_invalid_scaffolds"] = skipped
    if not fichtl:
        _translate_native_daughters(state)
        if laws.native_direction == "legacy_gravitropism_blend_v1":
            fixed = {n.node_data.node_id for o in replaced for n in o.segments}
            sim.apply_gravitropism(p.gravitropism, fixed=fixed)


def _realize_native_curve(state, organ, law, tangent_at):
    """Curvature on a natively constructed axis, from its realized attachment."""
    from ..utils.tropism import insertion_heading
    from .axis_laws import realize_correlated_curvature
    from .laws import law_stream

    if law["initial_heading"] == "insertion_angle":
        parent = organ.parent_node
        grandparent = state.simulation.G.nodes[0]
        for node in state.simulation.G.nodes:
            if node.node_data.node_id == parent.node_data.parent_id:
                grandparent = node
                break
        position = np.array([parent.node_data.x, parent.node_data.y, parent.node_data.z])
        chord = position - np.array([grandparent.node_data.x, grandparent.node_data.y, grandparent.node_data.z])
        heading = insertion_heading(tangent_at(parent, chord), law["insertion_mean_deg"], law["insertion_sd_deg"],
                                    law_stream(state.streams, state.laws.streams, "insertion", organ_id(organ)))
        return realize_correlated_curvature(organ, law, state.streams, start=position, heading=heading)
    if law["initial_heading"] == "origin_heading":
        return realize_correlated_curvature(organ, law, state.streams, heading=organ.plan["initial_heading"])
    return realize_correlated_curvature(organ, law, state.streams)


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
    elif law == "interval_pure_checks_v1":
        _check_interval_rows(state)
    elif law is not None:
        raise ValueError(f"Unknown post-direction law {law!r}")


def _check_interval_rows(state):
    """Pure final checks; never invoke native reorientation or consume shared RNG."""
    rows, surface = state.records, state.laws.surface_z_cm
    for row in rows.values():
        if row["order"] == 0:
            continue
        parent = rows[row["parent_id"]]
        actual = np.linalg.norm(
            np.array([row[k] for k in ("x", "y", "z")]) - np.array([parent[k] for k in ("x", "y", "z")])
        )
        if row["z"] > surface or not np.isclose(actual, row["length"], rtol=1e-5, atol=1e-6):
            raise ValueError("Native construction-step geometry failed integrity checks")


def materialize(state):
    laws = state.laws
    if laws.writer.get("records"):
        return  # Record-based intervals are final construction cuts.
    if state.planned:
        p = state.parameters
        for organ in state.organs_in_birth_order():
            oid = organ_id(organ)
            intervals, record = planned_axis(organ, state.curves[oid], laws.materialization,
                                             state.resolved.simulation_tag, p.root_tissue_density, state.law_counters)
            state.axes[oid] = intervals
            state.planned_records[oid] = record
            state.material_laws[oid] = "point_taper"
        if state.deferred_failure is not None:
            _raise_deferred_budget_failure(state)
        return
    state.axes = materialize_forest(state.organs_in_birth_order(), state.curves, state)


def _raise_deferred_budget_failure(state):
    """Insertion headings of daughters allocated before exhaustion, then the error."""
    from ..utils.tropism import insertion_heading
    from .laws import law_stream

    failure, laws = state.deferred_failure, state.laws
    parent = next(o for o in state.organs_in_birth_order() if organ_id(o) == failure["organ_id"])
    curve, order = state.curves[failure["organ_id"]], parent.plan["order"] + 1
    for child, site in failure["allocated"]:
        law = laws.direction[order]
        insertion_heading(curve.tangent(site, coincidence_cm=laws.materialization["corner_coincidence_cm"]),
                          law["insertion_mean_deg"], law["insertion_sd_deg"],
                          law_stream(state.streams, laws.streams, "insertion", child))
    raise ValueError(failure["message"])


def emit(state):
    """Sole writer: published graph and organ registry are published together."""
    from .hgraph import publish_graph

    sim, laws = state.simulation, state.laws
    organs = state.organs_in_birth_order()
    if laws.writer.get("records"):
        sim.G = publish_graph(sim.G, organs, records=state.records, organ_records=state.organ_records)
        return
    sim.G = publish_graph(sim.G, organs, axes=state.axes, first_node_id=laws.writer.get("first_node_id", 0))
    for organ in organs:
        if organ_id(organ) in state.curves or organ_id(organ) in state.material_laws:
            organ.mass = organ.calculate_mass()


def check(state):
    """Pure integrity and law postconditions; draw nothing, repair nothing."""
    from .integrity import validate_result

    sim = state.simulation
    validate_result(sim)
    limit = state.resolved.limits.get("max_nodes")
    if limit is not None and len(sim.G.nodes) > limit:
        raise ValueError(f"Node limit exceeded ({len(sim.G.nodes)} > {limit})")
    if state.planned:
        return  # The planned materializer enforces its own strict interval checks.
    for organ in state.organs_in_birth_order():
        curve = state.curves.get(organ_id(organ))
        if curve is not None:
            check_curve_postconditions(organ, curve, curve.law["surface_z_cm"])


def publish(state):
    from .views import VIEWS

    state.simulation.result = VIEWS[state.laws.view](state)


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
