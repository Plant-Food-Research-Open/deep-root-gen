"""Recruit wet-zone daughters after parent placement and before their curves are realized.

Terminal daughters (parent_order + 1) are the original pilot law. Optional
non-terminal recruitment adds order-k daughters on realized order k-1 parents
and gives each one the native branching subtree of an ordinary daughter.
"""

import numpy as np

from .branch_eligibility import attachment_diameters
from .irrigation import WetContour, exposure, survey_points


def _support(parent, curve):
    length = float(curve.stations[-1])
    poisson = parent.plan.get("length_poisson")
    if poisson:
        return (
            poisson["basal_exclusion_cm"],
            length - poisson["apical_exclusion_cm"],
            1 / poisson["mean_spacing_cm"],
            poisson["active"],
            poisson["decision"],
        )
    sites = parent.plan["sites"]
    first = parent.plan["first_draw"]
    if not sites:
        return first, length, 0.0, False, parent.plan.get("branch_decision", "inactive")
    rate = (len(sites) - 1) / (length - first) if length > first else 0.0
    return first, length, rate, True, "single_site" if len(sites) == 1 else "proposed"


def _insert(parent, curve, state, site):
    """Split the incoming material interval, retaining its old endpoint and all downstream IDs."""
    arcs = curve.construction_arcs
    i = int(np.searchsorted(arcs, site))
    end = parent.segments[i]
    start = 0.0 if i == 0 else arcs[i - 1]
    original = parent.feature_laws.birth_context(end)
    data = end.node_data.model_copy()
    data.parent_id = (
        parent.parent_node.node_data.node_id
        if i == 0
        else parent.segments[i - 1].node_data.node_id
    )
    data.length = float(site - start)
    data.x, data.y, data.z = map(float, curve.position([site])[0])
    node = parent.parent_node.G.add_node(data)
    node.organ = parent
    end.node_data.parent_id = node.node_data.node_id
    end.node_data.length = float(arcs[i] - site)
    parent.segments.insert(i, node)
    parent.base_node = parent.segments[0]
    curve.construction_arcs = np.insert(arcs, i, site)
    state.direction_nodes[data.node_id] = node
    parent.feature_laws.birth_contexts[id(node)] = original
    return node


def _exposure_bins(receipt, contour, zone):
    if contour is not None and contour.eligible:
        middle = contour.xyz + 0.5 * contour.steps
        bins = np.floor(middle[:, 2] / 10).astype(int)
        receipt["by_depth_cm"] = {
            str(10 * int(k)): [
                float(contour.widths[bins == k].sum()),
                float(contour.weights[bins == k].sum()),
            ]
            for k in np.unique(bins)
        }
        if zone.line_offsets_cm:
            dx = middle[:, 0, None] - np.asarray(zone.line_offsets_cm)
            if zone.row_period_cm:
                dx = (
                    dx + zone.row_period_cm / 2
                ) % zone.row_period_cm - zone.row_period_cm / 2
            distances = np.floor(np.abs(dx).min(axis=1) / 10).astype(int)
            receipt["by_line_distance_cm"] = {
                str(10 * int(k)): [
                    float(contour.widths[distances == k].sum()),
                    float(contour.weights[distances == k].sum()),
                ]
                for k in np.unique(distances)
            }


def _move_child(child, node, parent, state):
    child.parent_node = node
    child.segments[0].node_data.parent_id = node.node_data.node_id
    # Retain dimensions and enforce the same physical cap at the new insertion.
    if state.laws.cap is not None:
        cap = attachment_diameters(parent, [node])[0] * state.laws.cap["fraction_max"]
        material = child.axis_state.material
        material["base"] = min(material["base"], float(cap))
        material["tip"] = min(material["tip"], material["base"])
        if "thick_min_cm" in material and material["base"] < material["thick_min_cm"]:
            material.pop("rate_per_cm")
            material.pop("thick_min_cm")
        child.plan.update(base=material["base"], tip=material["tip"])


def _register(state, organ):
    """Direction lookups for nodes created after the direction phase began."""
    for node in organ.segments:
        state.direction_nodes[node.node_data.node_id] = node
        data = node.node_data
        state.scaffold[data.node_id] = np.array([data.x, data.y, data.z])


def _build_subtree(state, root):
    """Native biology for a recruited non-terminal daughter, as in init_organs.

    Branch sites, lengths and taper use the same feature laws, keyed by the new
    organ IDs; descendants join the order lists before their orders realize.
    """
    sim, p = state.simulation, state.parameters
    _register(state, root)
    frontier, order, born = [root], int(root.segments[0].node_data.order), 0
    while frontier and order < int(p.max_order):
        nxt = []
        for parent in frontier:
            laws = parent.feature_laws
            laws.filter_branch_sites(parent)
            while parent.lateral_attachment_nodes:
                child = parent.add_child_organ(
                    floor_threshold=p.floor_threshold,
                    ceiling_threshold=p.ceiling_threshold,
                )
                laws.assign_daughter(child, parent)
                sim.organs[order + 1].append(child)
                child.construct_root_from_parent(
                    p.segments_per_root or 1, p.apex_diameter
                )
                laws.after_construction(child)
                child.axis_state.birth_parent_biological_id = int(
                    child.parent_node.node_data.organ_id
                )
                child.axis_state.sampled_lengths_cm = tuple(
                    float(v) for v in child.get_lengths()
                )
                _register(state, child)
                nxt.append(child)
        born += len(nxt)
        frontier, order = nxt, order + 1
    return born


def _add_child(parent, node, state, oid, j):
    laws = parent.feature_laws
    parent.lateral_attachment_nodes.append(node)
    child = parent.add_child_organ()
    child.rng = state.streams.keyed("irrigation.child", "1", oid, j)
    laws.assign_daughter(child, parent)
    child.construct_root_from_parent(
        state.parameters.segments_per_root or 1,
        state.parameters.apex_diameter,
    )
    laws.after_construction(child)
    child.axis_state.birth_parent_biological_id = oid
    child.axis_state.sampled_lengths_cm = tuple(child.get_lengths())
    return child


def _realize_proposals(
    state, zone, parent, curve, daughters, threshold, contour, lo, h, expected, receipt
):
    oid = parent.axis_state.biological_id
    ends = curve.construction_arcs
    sim = state.simulation
    surface = state.laws.surface_z_cm
    if not expected:
        return
    rng = state.streams.keyed("irrigation.positions", "1", oid)
    moving = zone.response == "redistribute"
    if moving:
        indices = {id(node): k for k, node in enumerate(parent.segments)}
        children = [
            child
            for child in parent.child_organs
            if (
                parent.plan.get("length_poisson")
                or ends[indices[id(child.parent_node)]] > lo + 1.0e-9
            )
            and attachment_diameters(parent, [child.parent_node])[0] >= threshold
        ]
        count = len(children)
        if not count:
            return
        prob = (
            (zone.peak_multiplier - 1)
            * h
            / (contour.eligible + (zone.peak_multiplier - 1) * h)
        )
        wet = int(rng.binomial(count, prob))
        sites = np.sort(
            np.r_[
                contour.sample(rng, wet, True),
                contour.sample(rng, count - wet, False),
            ]
        )
    else:
        count = int(state.streams.keyed("irrigation.count", "1", oid).poisson(expected))
        receipt["drawn_extra"] = count
        if not count:
            return
        state.budget.reserve_branch_proposals(count, len(sim.G.nodes), 0, oid)
        limit = state.resolved.limits.get("max_organs")
        if limit is not None and state.budget.used["organs"] + count > limit:
            raise ValueError("Organ limit exceeded before irrigation recruitment")
        sites = np.sort(contour.sample(rng, count, zone.response == "add"))
    for j, site in enumerate(sites):
        # Never produce a microscopic split at an existing material or direction event.
        if (
            min(
                np.min(abs(curve.stations - site)),
                np.min(abs(curve.construction_arcs - site)),
            )
            <= 1e-9
        ):
            receipt["coincident"] += 1
            continue
        node = _insert(parent, curve, state, site)
        if moving:
            child = children[j]
            _move_child(child, node, parent, state)
        else:
            child = _add_child(parent, node, state, oid, j)
            daughters.append(child)
            receipt["accepted_extra"] += 1
            if "subtree_organs" in receipt:
                receipt["subtree_organs"] += _build_subtree(state, child)
        xyz = survey_points(curve.position([site]), zone, surface)[0]
        receipt["births"].append(
            dict(
                daughter_id=child.axis_state.biological_id,
                arc_cm=float(site),
                x_cm=float(xyz[0]),
                y_cm=float(xyz[1]),
                depth_cm=float(xyz[2]),
                exposure=float(exposure(zone, xyz[None, :])[0]),
            )
        )
    parent.plan["irrigation_extra_proposed"] = receipt["drawn_extra"]
    parent.plan["irrigation_extra_placed"] = receipt["accepted_extra"]


def _measure_parent(parent, curve, state, zone, threshold, sensitivity=None):
    """Eligible wet contour, exposure integral and expected extra count of one parent."""
    surface = state.laws.surface_z_cm
    oid = parent.axis_state.biological_id
    lo, hi, rate, active, decision = _support(parent, curve)
    ends = curve.construction_arcs
    # Measure eligible contour even for inactive parents when a usable interval exists.
    contour = (
        WetContour(
            zone,
            curve,
            surface,
            lo,
            hi,
            parent.axis_state.material,
            ends,
            parent.get_diameters(),
            threshold,
        )
        if hi > lo
        else None
    )
    h = 0.0 if contour is None else contour.H
    scale = 1.0 if sensitivity is None else sensitivity
    expected = scale * (zone.peak_multiplier - 1) * rate * h if active else 0.0
    receipt = dict(
        parent_id=oid,
        decision=decision,
        active=active,
        usable_cm=max(0.0, hi - lo),
        eligible_cm=0.0 if contour is None else contour.eligible,
        H_cm=h,
        rate_per_cm=rate,
        expected_extra=expected,
        baseline_accepted=len(parent.child_organs),
        drawn_extra=0,
        accepted_extra=0,
        coincident=0,
        births=[],
    )
    if sensitivity is not None:
        receipt["subtree_organs"] = 0
    _exposure_bins(receipt, contour, zone)
    return contour, lo, h, expected, receipt


def recruit_terminals(state, zone):
    """The terminal pilot law: order parent_order + 1 on order parent_order."""
    recruit(state, zone, zone.parent_order)


def recruit(state, zone, order, sensitivity=None):
    """Wet-zone daughters of order + 1 on realized order parents.

    ``sensitivity`` None is the terminal law; a value s scales the expected
    extra births by s and builds each recruited daughter's native subtree.
    """
    sim = state.simulation
    parents, daughters = sim.organs[order], sim.organs[order + 1]
    threshold = max(0.093, state.parameters.min_branching_diameter_cm)
    records = []
    report = state.diagnostics.setdefault(
        "irrigation",
        dict(
            settings=zone.model_dump(exclude_none=True),
            minimum_parent_diameter_cm=threshold,
        ),
    )
    if sensitivity is None:
        report["parents"] = records
    else:
        report.setdefault("upstream", {})[str(order + 1)] = dict(
            sensitivity=sensitivity, parents=records
        )
    # Measure every parent first (each uses only its own realized curve), so an
    # optional budget can scale all expectations equally before any draw.
    entries = []
    for parent in parents:
        oid = parent.axis_state.biological_id
        curve = state.curves.get(oid)
        if curve is None or parent.invalid_root:
            entries.append((None, dict(parent_id=oid, decision="invalid_parent", accepted_extra=0)))
            continue
        entries.append(((parent, curve), _measure_parent(parent, curve, state, zone, threshold, sensitivity)))
    factor = 1.0
    if zone.max_extra_fraction is not None and zone.response != "redistribute":
        total = sum(m[3] for p, m in entries if p is not None)
        budget = zone.max_extra_fraction * len(daughters)
        factor = min(1.0, budget / total) if total > 0 else 1.0
        target = report if sensitivity is None else report["upstream"][str(order + 1)]
        target["budget"] = dict(max_extra_fraction=zone.max_extra_fraction, baseline_daughters=len(daughters),
                                uncapped_expected_extra=total, scale=factor)
    for placed, measured in entries:
        if placed is None:
            records.append(measured)
            continue
        parent, curve = placed
        contour, lo, h, expected, receipt = measured
        if factor != 1.0:
            receipt["uncapped_expected_extra"] = expected
            expected *= factor
            receipt["expected_extra"] = expected
        _realize_proposals(state, zone, parent, curve, daughters, threshold, contour, lo, h, expected, receipt)
        records.append(receipt)
