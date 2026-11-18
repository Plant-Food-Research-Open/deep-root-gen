"""Feature leaf laws applied inside native construction.

Native kernels still sample what they own (local coordinates, placement and
any dimension, material or branching law that is not replaced). A replaced
law here receives one organ's state and a keyed stream; it never constructs a
simulator, allocates published identities or writes files.

Declared semantics (also recorded in the resolved description):

* lengths: ``bounded_lognormal`` replaces the organ length and keeps the
  native segment proportions; the inherited parent-length term is not added
  (as for the historical current-length CDF, ``discrete_cdf`` reuses that law).
* maturity: one dimensionless value per primary, inherited by its tree; it
  scales whole organ length, the point-taper base and (when declared) branch
  probability. It is never chronological age.
* taper: point diameters on physical arclength (base, mid = tip + fraction *
  (base - tip), tip). Sampling -> maturity -> parent cap -> tip limit. Native
  daughters inherit the equivalent diameter of their birth construction
  interval. Each published segment carries the volume-conserving equivalent
  diameter and is classified fine/structural by it.
* branching: first-branch draw, probability (optionally maturity-scaled),
  daughter count and uniform sites replace native count/spacing; terminal
  order is ``max_order``.
* origins: ``point`` translates the common base; ``disk`` gives every primary
  its own zero-material base, translated after native placement.
"""

import numpy as np

from .cohort_geometry import bounded_draw, equivalent_diameter, taper_diameter
from .laws import disk_origin, first_branch_sites, law_stream, point_taper_dimensions, primary_maturity, radial_inclination
from .materialize import EmittedInterval, fine_by_equivalent_diameter


def _organ_order(organ):
    return int(organ.parent_node.node_data.order) + 1


class NativeFeatureLaws:
    """Per-organ hooks used by the native ``init_organs`` traversal."""

    def __init__(self, state):
        self.state = state
        self.laws = state.laws
        self.parameters = state.parameters
        self.max_order = int(state.parameters.max_order)
        self.anchors = None
        state.tapers = {}

    def stream(self, purpose, organ_id):
        return law_stream(self.state.streams, self.laws.streams, purpose, organ_id)

    # -- forest setup ------------------------------------------------------

    def begin(self, simulation):
        """Distributed origins use the per-primary bases the engine prepared."""
        self.anchors = getattr(self.state, "anchors", None)

    def primary_parent(self, simulation, index):
        return simulation.G.base_node if self.anchors is None else self.anchors[index]

    def assign_primary(self, organ, index, expected_id):
        maturity, label = 1.0, None
        if self.laws.maturity is not None:
            maturity, label = primary_maturity(self.laws.maturity, index, self.stream("maturity", expected_id))
        organ.feature_laws = self
        organ.plan = dict(order=1, maturity=maturity, label=label, tree=expected_id, index=index)

    def assign_daughter(self, organ, parent_organ):
        organ.feature_laws = self
        organ.plan = dict(order=_organ_order(organ), maturity=parent_organ.plan["maturity"],
                          label=parent_organ.plan["label"], tree=parent_organ.plan["tree"])

    # -- dimensions --------------------------------------------------------

    def replace_lengths(self, organ, lengths):
        """Feature length law for this order, or None for the native law."""
        order = _organ_order(organ)
        law = self.laws.lengths.get(order)
        if law is None or law["law"] != "bounded_lognormal":
            return None
        expected = int(organ.parent_node.G.organ_id)
        total = bounded_draw(law, self.stream("length", expected))
        proportions = np.asarray(lengths, float) / float(np.sum(lengths))
        return proportions * total

    def scale_lengths(self, organ, lengths):
        if self.laws.maturity is None:
            return lengths
        return np.asarray(lengths, float) * organ.plan["maturity"] ** self.laws.maturity["length_power"]

    # -- branching ---------------------------------------------------------

    def replaces_branching(self, organ):
        return _organ_order(organ) in self.laws.branching

    def branch_sites(self, organ, total_length):
        order = _organ_order(organ)
        expected = int(organ.parent_node.G.organ_id)
        scale = self.laws.maturity is not None and self.laws.maturity["scale_branch_probability"]
        first, sites = first_branch_sites(
            self.laws.branching[order], order, self.max_order, total_length, organ.plan["maturity"], scale,
            self.stream("branching", expected), self.state.law_counters,
        )
        organ.plan.update(first_draw=first, sites=list(sites))
        return sites

    # -- material ----------------------------------------------------------

    def after_construction(self, organ):
        """Point taper replaces the cylinder material; daughters see the new birth material."""
        order = _organ_order(organ)
        law = self.laws.taper.get(order)
        oid = int(organ.segments[0].node_data.organ_id)
        if law is None:
            return
        lengths = organ.get_lengths()
        total = float(lengths.sum())
        parent_diameter = None
        parent = getattr(organ.parent_node, "organ", None)
        if parent is not None and self.laws.cap is not None:
            ptaper = self.state.tapers[int(parent.segments[0].node_data.organ_id)]
            site = float(np.cumsum(parent.get_lengths())[parent.segments.index(organ.parent_node)])
            parent_diameter = float(taper_diameter(site, ptaper["length"], ptaper["base"], ptaper["tip"], ptaper["midpoint"]))
        maturity_law = self.laws.maturity
        base, tip = point_taper_dimensions(
            law, organ.plan["maturity"], None if maturity_law is None else maturity_law["diameter_power"],
            parent_diameter, self.laws.cap, self.stream("taper", oid), self.state.law_counters,
        )
        taper = dict(length=total, base=base, tip=tip, midpoint=law["midpoint_diameter_fraction"])
        self.state.tapers[oid] = taper
        arcs = np.r_[0.0, np.cumsum(lengths)]
        points = taper_diameter(arcs, total, base, tip, taper["midpoint"])
        for node, diameter in zip(organ.segments, equivalent_diameter(points[:-1], points[1:])):
            node.node_data.diameter = float(diameter)
        organ.plan.update(base=base, tip=tip, midpoint=taper["midpoint"], length=total)


def place_origins(state):
    """Translate native scaffolds to their origins after native placement."""
    sim, laws = state.simulation, state.laws
    law = laws.origins
    if law["layout"] == "point":
        receipt = sim.translate_common_base(law["x_cm"], law["y_cm"], law["depth_cm"], law["surface_z_cm"])
        state.diagnostics["primary_origins"] = dict(layout="point", **receipt)
        return
    receipts = []
    for index, primary in enumerate(sim.organs.get(1, [])):
        oid = int(primary.segments[0].node_data.organ_id)
        start, phi = disk_origin(law, law_stream(state.streams, laws.streams, "origin", oid))
        anchor = sim.G.bases[index].node_data
        delta = start - np.array([anchor.x, anchor.y, anchor.z])
        anchor.x, anchor.y, anchor.z = (float(v) for v in start)
        subtree = [primary]
        while subtree:
            organ = subtree.pop()
            organ.set_coordinates(organ.get_coordinates() + delta)
            subtree.extend(organ.child_organs)
        if "heading" in law:
            primary.plan["initial_heading"] = radial_inclination(
                law["heading"], phi, law_stream(state.streams, laws.streams, "heading", oid)
            )
        receipts.append(dict(organ_id=oid, origin_cm=start.tolist(), polar_angle_rad=float(phi)))
    state.diagnostics["primary_origins"] = dict(layout="disk", primaries=receipts)


def tapered_axis(organ, curve, taper, state):
    """Point-taper material over native construction intervals (and curve corners)."""
    from .materialize import interior_material_cuts, merge_cuts

    cutoff_mm = float(state.parameters.fine_root_threshold) * 10.0
    arcs = np.cumsum(organ.get_lengths())
    total = float(arcs[-1])
    stations = [] if curve is None else curve.stations[1:-1]
    material = interior_material_cuts(total, taper["base"], taper["tip"], cutoff_mm / 10.0, taper["midpoint"])
    tolerance = state.laws.materialization["corner_coincidence_cm"]
    cuts = merge_cuts(np.r_[0.0, arcs], [stations, material], tolerance)[1:]
    if np.any(np.diff(np.r_[0.0, cuts]) <= 1e-12):
        raise ValueError("Unrepresentable material cut on a tapered axis")
    if curve is not None:
        positions = curve.position(cuts)
    else:
        parent = organ.parent_node.node_data
        polyline = np.vstack([[parent.x, parent.y, parent.z], organ.get_coordinates()])
        positions = np.column_stack([np.interp(cuts, np.r_[0.0, arcs], polyline[:, k]) for k in range(3)])
    points = taper_diameter(np.r_[0.0, cuts], total, taper["base"], taper["tip"], taper["midpoint"])
    equivalents = equivalent_diameter(points[:-1], points[1:])
    intervals = []
    previous = 0.0
    for cut, xyz, diameter in zip(cuts, positions, equivalents):
        k = int(np.searchsorted(arcs, cut, side="left"))
        node = organ.segments[k]
        retained = arcs[k] == cut
        data = node.node_data.model_copy()
        data.x, data.y, data.z = (float(v) for v in xyz)
        data.length, data.diameter = float(cut - previous), float(diameter)
        data.root_type = fine_by_equivalent_diameter(diameter, cutoff_mm)
        intervals.append(EmittedInterval(None, node if retained else None, data=data))
        previous = cut
    return intervals
