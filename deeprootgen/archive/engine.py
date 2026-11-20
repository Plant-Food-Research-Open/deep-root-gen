"""Execution schedules used only for replay of pre-cutover artifacts."""
from collections import deque

import numpy as np

from ..model import engine
from ..model.engine import organ_id
from ..model.materialize import planned_axis
from .views import VIEWS


def _prepare_planned(state):
    """Every construction law replaced: breadth-first planned organs, no native draws."""
    from ..data_model import RootNodeModel, RootTypeModel
    from ..model.hgraph import RootSystemGraph
    from ..model.laws import law_stream, primary_maturity, sample_planned_organ, site_diameter
    from ..model.root import RootOrgan

    state.planned_records = {}
    state.deferred_failure = None
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
    engine.bind_axis_states(state)


def _place_planned(state):
    sim, laws = state.simulation, state.laws
    from ..model.laws import disk_origin, law_stream, radial_inclination

    for index, primary in enumerate(sim.organs.get(1, [])):
        oid = organ_id(primary)
        start, phi = disk_origin(laws.origins, law_stream(state.streams, laws.streams, "origin", oid))
        anchor = sim.G.bases[index].node_data
        anchor.x, anchor.y, anchor.z = (float(v) for v in start)
        primary.plan["initial_heading"] = radial_inclination(
            laws.origins["heading"], phi, law_stream(state.streams, laws.streams, "heading", oid)
        )


def _realize_planned(state):
    from ..utils.tropism import insertion_heading
    from ..model.axis_laws import realize_correlated_curvature
    from ..model.laws import law_stream

    engine.begin_directions(state)
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
            reserve_stations=state.budget.reserve,
        )
        state.law_counters["surface_reflections"] += curve.receipt["surface_reflections"]
        engine._place_construction_points(organ, curve)
        state.curves[oid] = curve
        organ.axis_state.curve = curve
        organ.axis_state.material = {k: organ.plan[k] for k in ("length", "base", "tip", "midpoint")}
        receipts.append(curve.receipt)
    state.diagnostics["curvature"] = receipts


def _realize_intervals(state):
    """Record-based construction-step interval law for every daughter order."""
    from ..utils.tropism import validate_row_axial_kappas
    from ..model.execution import _partition
    from ..model.interval_geometry import realize_intervals

    engine.begin_directions(state)
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


def _materialize_planned(state):
    laws = state.laws
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


def _raise_deferred_budget_failure(state):
    """Insertion headings of daughters allocated before exhaustion, then the error."""
    from ..utils.tropism import insertion_heading
    from ..model.laws import law_stream

    failure, laws = state.deferred_failure, state.laws
    parent = next(o for o in state.organs_in_birth_order() if organ_id(o) == failure["organ_id"])
    curve, order = state.curves[failure["organ_id"]], parent.plan["order"] + 1
    for child, site in failure["allocated"]:
        law = laws.direction[order]
        insertion_heading(curve.tangent(site, coincidence_cm=laws.materialization["corner_coincidence_cm"]),
                          law["insertion_mean_deg"], law["insertion_sd_deg"],
                          law_stream(state.streams, laws.streams, "insertion", child))
    raise ValueError(failure["message"])


def _record_attachments(state):
    from ..model.execution import _organ_records, _records, _relocate

    sim = state.simulation
    state.records, state.organ_records = _records(sim), _organ_records(sim)
    if state.laws.relocation is not None:
        _relocate(state.records, state.organ_records, state.laws.relocation['distal_fraction'])


def _emit_records(state):
    from ..model.hgraph import publish_graph

    sim = state.simulation
    sim.G = publish_graph(sim.G, state.organs_in_birth_order(), records=state.records, organ_records=state.organ_records)


def _publish_replay(state):
    state.simulation.result = VIEWS[state.laws.view](state)


def execute(simulation, resolved, *, initial_recorder=None):
    phases = dict(engine.PHASES, publish=_publish_replay)
    if resolved.laws.construction == 'planned':
        phases.update(prepare_forest=_prepare_planned, place_scaffold=_place_planned,
                      realize_directions=_realize_planned, materialize=_materialize_planned,
                      check=engine.check_graph)
    elif resolved.laws.writer.get('records'):
        phases.update(attachments=_record_attachments, realize_directions=_realize_intervals,
                      post_direction=_check_interval_rows, materialize=lambda state: None, emit=_emit_records)
    return engine._execute_phases(simulation, resolved, phases, initial_recorder=initial_recorder)
