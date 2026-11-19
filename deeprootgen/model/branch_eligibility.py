"""Decide daughter eligibility from local parent material in centimetres."""

from collections import Counter

import numpy as np

from .attachment import distal_arc_cm
from .point_taper import point_diameter


def attachment_diameters(parent, nodes, relocation=None):
    """Resolve local point taper or incoming-cylinder diameter at each site."""
    ends = np.cumsum(parent.get_lengths())
    indices = {id(node): index for index, node in enumerate(parent.segments)}
    arcs = ends[[indices[id(node)] for node in nodes]]
    if relocation is not None and parent.segments[0].node_data.order == 1:
        fraction = relocation["distal_fraction"]
        arcs = np.array([distal_arc_cm(arc, ends[-1], fraction) for arc in arcs])
    taper = parent.axis_state.material
    if taper is not None:
        return point_diameter(arcs, taper["length"], taper)
    return parent.get_diameters()[np.searchsorted(ends, arcs, side="left")]


def filter_branch_sites(state, parent):
    """Reject thin attachment sites before allocating daughters or their subtrees."""
    threshold = getattr(state.parameters, "min_branching_diameter_cm", 0.)
    if not threshold:
        return
    order = int(parent.segments[0].node_data.order)
    receipt = state.diagnostics.setdefault("branch_eligibility", {
        "min_branching_diameter_cm": threshold, "by_parent_order": {},
    })
    counts = receipt["by_parent_order"].setdefault(str(order), {
        "candidates": 0, "eligible": 0, "diameter_below_branch_minimum": 0,
    })
    candidates = parent.lateral_attachment_nodes
    if not candidates:
        return
    diameters = attachment_diameters(parent, candidates, state.laws.relocation)
    eligible = [node for node, diameter in zip(candidates, diameters) if diameter >= threshold]
    rejected = len(candidates) - len(eligible)
    counts["candidates"] += len(candidates)
    counts["eligible"] += len(eligible)
    counts["diameter_below_branch_minimum"] += rejected
    if rejected and getattr(state.parameters, "research_root_counts_by_order", None) is not None:
        raise ValueError(
            f"Exact daughter count infeasible on parent organ {parent.axis_state.biological_id}: "
            f"{rejected} of {len(candidates)} sites below minimum branching diameter {threshold:g} cm"
        )
    if rejected and hasattr(parent, "parent2_zone_diagnostics"):
        zone = parent.parent2_zone_diagnostics
        zone["eligible_sites_cm"] = [
            arc for arc, diameter in zip(zone["sites_cm"], diameters) if diameter >= threshold
        ]
    parent.lateral_attachment_nodes = eligible


def validate_branching_diameters(state):
    """Check the realized attachment against the final profile prior to materialization."""
    threshold = getattr(state.parameters, "min_branching_diameter_cm", 0.)
    cap = state.laws.cap
    if not threshold and cap is None:
        return
    for group in state.simulation.organs.values():
        for parent in group:
            nodes = [child.parent_node for child in parent.child_organs]
            if not nodes:
                continue
            diameters = attachment_diameters(parent, nodes)
            if np.any(diameters < threshold):
                raise ValueError(
                    f"Realized daughter site below minimum branching diameter {threshold:g} cm "
                    f"on parent organ {parent.axis_state.biological_id}"
                )
            if cap is not None:
                limits = diameters * cap["fraction_max"]
                bases = np.array([child.axis_state.material["base"] for child in parent.child_organs])
                if np.any((bases > limits) & ~np.isclose(bases, limits, rtol=1e-12, atol=0.)):
                    raise ValueError(
                        f"Daughter base exceeds the diameter cap on parent organ {parent.axis_state.biological_id}"
                    )


def branching_receipt(simulation, parameters):
    """Keep proposal, attachment and post-validation counts distinguishable."""
    by_order = {}
    for order, parents in sorted(simulation.organs.items()):
        if order >= parameters.max_order:
            continue
        totals = Counter(dict(proposed=0, placed_sites=0, accepted=0, invalid_daughters=0))
        reasons = Counter()
        first_sites = []
        poisson_sites = []
        for parent in parents:
            plan = parent.plan
            placed = plan["placed_sites"]
            poisson = plan.get("length_poisson")
            proposed = len(plan["sites"]) if "sites" in plan else placed
            if poisson is not None:
                proposed = poisson["proposed"]
            proposed += plan.get("irrigation_extra_proposed", 0)
            placed += plan.get("irrigation_extra_placed", 0)
            nonunique = proposed - placed
            reasons.update(diameter_below_branch_minimum=plan["diameter_rejections"], coincident_sites=nonunique)
            children = parent.child_organs
            invalid = sum(bool(child.invalid_root) for child in children)
            totals.update(proposed=proposed, placed_sites=placed, accepted=len(children),
                          invalid_daughters=invalid)
            if poisson is not None:
                poisson_sites.append(dict(
                    poisson, organ_id=parent.axis_state.biological_id, placed_sites=placed,
                    diameter_below_branch_minimum=plan["diameter_rejections"], accepted=len(children),
                    invalid_daughters=invalid, invalid_descendants=_invalid_descendants(children),
                ))
                if poisson["decision"] != "proposed":
                    reasons[poisson["decision"]] += 1
            if "branch_decision" in plan:
                decision = plan["branch_decision"]
                first_sites.append(dict(organ_id=parent.axis_state.biological_id, first_site_cm=plan["first_draw"],
                                        proposed=proposed, accepted=len(children), decision=decision))
                if decision != "proposed":
                    reasons[decision] += 1
        by_order[str(order)] = dict(parents=len(parents), **totals, rejections=dict(reasons),
                                    sampled_first_sites=first_sites)
        if poisson_sites:
            by_order[str(order)]["length_poisson_sites"] = poisson_sites
    return dict(by_parent_order=by_order)


def _invalid_descendants(children):
    count = 0
    remaining = list(children)
    while remaining:
        child = remaining.pop()
        count += bool(child.invalid_root)
        remaining.extend(child.child_organs)
    return count
