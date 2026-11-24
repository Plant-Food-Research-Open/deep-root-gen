"""Transfer existing ordinary buds along the realized contour of the same parent."""

from collections import Counter

import numpy as np

from .daughter_placement import _deep_intervals, eligible_contour
from .irrigation_branching import _insert, _support


def _free_contour(curve, starts, stops):
    """Leave a numerical gap around existing construction and direction events."""
    occupied = np.unique(np.r_[curve.stations, curve.construction_arcs])
    boundaries = np.unique(np.r_[starts, stops, occupied])
    left, right = boundaries[:-1], boundaries[1:]
    middle = (left + right) / 2.
    index = np.searchsorted(starts, middle, side="right") - 1
    keep = (index >= 0) & (middle < stops[index])
    left, right = left[keep], right[keep]
    # A translated polyline can resolve less detail than its local arclength.
    # Leave twice the writer's 64-epsilon endpoint-pair resolution floor.
    scale = np.linalg.norm(curve.points, axis=1).max()
    gap = max(1.e-9, 256 * np.finfo(float).eps * scale)
    left = left + gap
    right = right - gap
    keep = right > left
    return left[keep], right[keep]


def _destination(state, parent, curve, child, settings, lower, upper, rng):
    threshold = state.parameters.min_branching_diameter_cm
    if state.laws.cap is not None:
        # Moving a nonterminal daughter must also preserve the material that
        # its existing descendants sampled. Restrict its destination accordingly.
        fraction = state.laws.cap["fraction_max"]
        base = child.axis_state.material["base"]
        required = base / fraction
        # Eligibility uses the original forward multiplication. Its inverse can
        # round one parent-diameter ULP above an exactly admissible plateau.
        previous = np.nextafter(required, 0.)
        if previous * fraction >= base:
            required = previous
        elif required * fraction < base:
            required = np.nextafter(required, np.inf)
        threshold = max(threshold, required)
    starts, stops = eligible_contour(parent, curve, threshold, lower, upper)
    starts, stops = _deep_intervals(curve, starts, stops, state.laws.surface_z_cm - settings.deep_depth_cm)
    if not len(starts):
        return None, 0.
    starts, stops = _free_contour(curve, starts, stops)
    if not len(starts):
        return None, 0.
    cumulative = np.cumsum(stops - starts)
    width = float(cumulative[-1])
    draw = rng.random() * width
    index = min(np.searchsorted(cumulative, draw, side="right"), len(cumulative) - 1)
    return float(stops[index] - (cumulative[index] - draw)), width


def transfer_birth_sites(state, order, settings):
    """Depth is positive below soil. Protect the first accepted count-law anchor.

    Original buds and downstream organs already exist. Before realizing daughter
    directions, move selected shallow buds to eligible deeper contour or retain
    them in place if such contour is unavailable. A transfer consumes no organ or
    branch proposal. The ordinary node budget still covers each new parent cut.
    """
    report = state.diagnostics.setdefault("birth_depth_transfer", dict(
        settings=state.resolved.description["birth_depth_transfer"], by_parent_order={},
    ))
    totals = Counter(dict(daughters=0, shallow_before=0, shallow_after=0, deep_before=0,
                          deep_after=0, anchored_shallow=0, eligible_shallow=0,
                          selected=0, moved=0, shortfall=0, skipped_parents=0))
    rows = []
    surface = state.laws.surface_z_cm
    for parent in state.simulation.organs.get(order, []):
        parent_id = parent.axis_state.biological_id
        curve = state.curves.get(parent_id)
        if curve is None or parent.invalid_root:
            totals["skipped_parents"] += 1
            continue
        children = parent.child_organs
        if not children:
            continue
        original_arcs = {id(node): arc for node, arc in zip(parent.segments, curve.construction_arcs)}
        lower, upper, _, _, _ = _support(parent, curve)
        anchor = None if "length_poisson" in parent.plan else children[0]
        if anchor is not None:
            lower = max(lower, original_arcs[id(anchor.parent_node)])
        for child in children:
            arc = float(original_arcs[id(child.parent_node)])
            depth = float(surface - curve.position([arc])[0, 2])
            shallow = depth < settings.shallow_depth_cm
            totals.update(daughters=1, shallow_before=int(shallow), deep_before=int(depth > settings.deep_depth_cm))
            final_arc, final_depth = arc, depth
            row = dict(parent_id=parent_id, daughter_id=child.axis_state.biological_id,
                       original_arc_cm=arc, original_depth_cm=depth)
            if not shallow:
                decision = "outside_shallow_layer"
            elif child is anchor:
                decision = "first_accepted_anchor"
                totals["anchored_shallow"] += 1
            else:
                totals["eligible_shallow"] += 1
                rng = state.streams.keyed("birth_depth_transfer", "1", order, parent_id, child.axis_state.biological_id)
                if rng.random() < settings.transfer_probability:
                    totals["selected"] += 1
                    destination, width = _destination(state, parent, curve, child, settings, lower, upper, rng)
                    row["eligible_deep_cm"] = width
                    if destination is None:
                        decision = "no_eligible_deep_contour"
                        totals["shortfall"] += 1
                    else:
                        node = _insert(parent, curve, state, destination)
                        child.parent_node = node
                        child.segments[0].node_data.parent_id = node.node_data.node_id
                        final_arc, final_depth = destination, float(surface - node.node_data.z)
                        decision = "transferred"
                        totals["moved"] += 1
                else:
                    decision = "not_selected"
            totals.update(shallow_after=int(final_depth < settings.shallow_depth_cm),
                          deep_after=int(final_depth > settings.deep_depth_cm))
            rows.append(dict(row, decision=decision, final_arc_cm=final_arc, final_depth_cm=final_depth))
    report["by_parent_order"][str(order)] = dict(
        totals, expected_selected=totals["eligible_shallow"] * settings.transfer_probability, births=rows,
    )
