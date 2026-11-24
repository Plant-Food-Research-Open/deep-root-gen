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

from .branching_laws import LENGTH_POISSON_LAW, length_poisson_sites
from .cohort_geometry import bounded_draw
from .laws import disk_origin, first_branch_sites, law_stream, point_taper_dimensions, primary_maturity, radial_inclination
from .materialize import EmittedInterval, fine_by_equivalent_diameter
from .point_taper import exponential_profile_integral, profile_cuts


def _organ_order(organ):
    return int(organ.parent_node.node_data.order) + 1


class NativeFeatureLaws:
    """Per-organ hooks used by the native ``init_organs`` traversal."""

    def __init__(self, state):
        self.state = state
        self.laws = state.laws
        self.parameters = state.parameters
        self.max_order = int(state.parameters.max_order)
        self.consumers = state.resolved.description["consumers"]
        self.anchors = None
        state.tapers = {}
        self.birth_contexts = {}

    def stream(self, purpose, organ_id):
        return law_stream(self.state.streams, self.laws.streams, purpose, organ_id)

    def dimension_stream(self, purpose, organ_id, *distributions):
        if getattr(self.parameters, "canonical_generation", False) and all(d["sd"] == 0 for d in distributions):
            return None
        return self.stream(purpose, organ_id)

    # -- forest setup ------------------------------------------------------

    def begin(self, simulation):
        """Distributed origins use the per-primary bases the engine prepared."""
        self.anchors = getattr(self.state, "anchors", None)

    def reserve_construction(self, count, graph):
        self.state.budget.check_nodes(len(graph.nodes) + count)

    def reserve_organ(self):
        self.state.budget.reserve("organs", 1)

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

    def uses_birth_diameter(self, order):
        # Untapered descendants inherit native cylinders recursively.
        return order in self.consumers["base_diameter"]["orders"]

    def birth_context(self, node):
        return self.birth_contexts[id(node)]

    # -- dimensions --------------------------------------------------------

    def replace_lengths(self, organ, lengths):
        """Feature length law for this order, or None for the native law."""
        order = _organ_order(organ)
        law = self.laws.lengths.get(order)
        if law is None or law["law"] != "bounded_lognormal":
            return None
        expected = int(organ.parent_node.G.organ_id)
        rng = self.dimension_stream("length", expected, law)
        floor = law.get("realized_floor_cm")
        if floor is None:
            total = bounded_draw(law, rng)
        else:
            from scipy.stats import truncnorm

            maturity = 1. if self.laws.maturity is None else organ.plan["maturity"] ** self.laws.maturity["length_power"]
            minimum = max(law["min"], floor / maturity)
            if minimum >= law["max"]:
                raise ValueError("Realized primary length floor leaves no probability mass after maturity scaling")
            variance = np.log1p((law["sd"] / law["mean"]) ** 2)
            sigma = np.sqrt(variance)
            mu = np.log(law["mean"]) - 0.5 * variance
            a, b = (np.log([minimum, law["max"]]) - mu) / sigma
            total = float(np.exp(mu + sigma * truncnorm.ppf(rng.random(), a, b)))
        proportions = np.asarray(lengths, float) / float(np.sum(lengths))
        return proportions * total

    def scale_lengths(self, organ, lengths):
        if self.laws.maturity is not None:
            lengths = np.asarray(lengths, float) * organ.plan["maturity"] ** self.laws.maturity["length_power"]
        factor = getattr(self.parameters, "allocation_length_scales", {}).get(_organ_order(organ), 1.)
        if factor != 1.:
            lengths = lengths * factor
            if hasattr(organ, "current_length_diagnostics"):
                organ.current_length_diagnostics["allocated_length_cm"] = float(np.sum(lengths))
        return lengths

    def scale_diameters(self, organ, diameters):
        factor = self.diameter_factor(organ)
        return diameters if factor == 1. else diameters * factor

    def diameter_factor(self, organ):
        return getattr(self.parameters, "allocation_diameter_scales", {}).get(_organ_order(organ), 1.)

    # -- branching ---------------------------------------------------------

    def replaces_branching(self, organ):
        return _organ_order(organ) in self.laws.branching

    def filter_branch_sites(self, organ):
        from .branch_eligibility import filter_branch_sites

        candidates = len(organ.lateral_attachment_nodes)
        filter_branch_sites(self.state, organ)
        if self.state.resolved.source_schema == "4":
            organ.plan["placed_sites"] = candidates
            organ.plan["diameter_rejections"] = candidates - len(organ.lateral_attachment_nodes)
            if "length_poisson" in organ.plan:
                first = None
                if organ.lateral_attachment_nodes:
                    index = organ.segments.index(organ.lateral_attachment_nodes[0])
                    first = float(np.cumsum(organ.get_lengths())[index])
                organ.plan["length_poisson"]["first_accepted_site_cm"] = first

    def branch_sites(self, organ, total_length, intervals):
        order = _organ_order(organ)
        expected = int(organ.parent_node.G.organ_id)
        law = self.laws.branching[order]
        if law["law"] == LENGTH_POISSON_LAW:
            graph = organ.parent_node.G
            sites, receipt = length_poisson_sites(
                law, total_length,
                lambda: self.state.streams.keyed(law["stream_namespace"], law["version"], expected),
                lambda count: self.state.budget.reserve_branch_proposals(count, len(graph.nodes), intervals, expected),
            )
            organ.plan["length_poisson"] = receipt
            return sites
        scale = self.laws.maturity is not None and self.laws.maturity["scale_branch_probability"]
        beyond_tip = self.state.law_counters["branch_beyond_tip"]
        first, sites = first_branch_sites(
            law, order, self.max_order, total_length, organ.plan["maturity"], scale,
            self.stream("branching", expected), self.state.law_counters,
        )
        organ.plan.update(first_draw=first, sites=list(sites))
        if self.state.resolved.source_schema == "4":
            if sites:
                decision = "proposed"
            elif self.state.law_counters["branch_beyond_tip"] > beyond_tip:
                decision = "first_site_at_or_beyond_tip"
            else:
                decision = "bernoulli_rejected"
            organ.plan["branch_decision"] = decision
        return sites

    # -- material ----------------------------------------------------------

    def after_construction(self, organ):
        """Keep native birth cylinders immutable; taper is a separate profile.

        Native daughter sampling reads these construction cylinders. Active
        taper is consumed only by explicit parent capping and materialization.
        """
        order = _organ_order(organ)
        from .axis_state import AxisState, BirthContext

        contexts = tuple(
            BirthContext(n.node_data.diameter, n.node_data.length, n.node_data.order, n.node_data.root_tissue_density)
            for n in organ.segments
        )
        self.birth_contexts.update((id(n), c) for n, c in zip(organ.segments, contexts))
        organ.axis_state = AxisState(organ, int(organ.segments[0].node_data.organ_id), contexts)
        law = self.laws.taper.get(order)
        oid = int(organ.segments[0].node_data.organ_id)
        if law is None:
            return
        lengths = organ.get_lengths()
        total = float(lengths.sum())
        parent_diameter = None
        parent = getattr(organ.parent_node, "organ", None)
        if parent is not None and self.laws.cap is not None:
            from .branch_eligibility import attachment_diameters
            parent_diameter = float(attachment_diameters(parent, [organ.parent_node], self.laws.relocation)[0])
        maturity_law = self.laws.maturity
        base, tip = point_taper_dimensions(
            law, organ.plan["maturity"], None if maturity_law is None else maturity_law["diameter_power"],
            parent_diameter, self.laws.cap, self.dimension_stream("taper", oid, law["base_cm"], law["tip_cm"]),
            self.state.law_counters,
            diameter_scale=self.diameter_factor(organ),
        )
        taper = dict(length=total, base=base, tip=tip, midpoint=law["midpoint_diameter_fraction"])
        if "rate_per_cm" in law and base >= law["thick_min_cm"]:
            taper.update(rate_per_cm=law["rate_per_cm"], thick_min_cm=law["thick_min_cm"])
        self.state.tapers[oid] = taper
        organ.axis_state.material = taper
        organ.plan.update(base=base, tip=tip, midpoint=taper["midpoint"], length=total)


def place_origins(state):
    """Translate native scaffolds to their origins after native placement."""
    sim, laws = state.simulation, state.laws
    law = laws.origins
    if state.vine_origin is not None:
        _place_catalogue_origins(state)
        return
    if law["layout"] == "point":
        receipt = sim.translate_common_base(law["x_cm"], law["y_cm"], law["depth_cm"], law["surface_z_cm"])
        state.diagnostics["primary_origins"] = dict(layout="point", **receipt)
        return
    receipts = []
    for index, primary in enumerate(sim.organs.get(1, [])):
        oid = int(primary.segments[0].node_data.organ_id)
        start, phi = disk_origin(law, law_stream(state.streams, laws.streams, "origin", oid))
        _translate_primary(primary, sim.G.bases[index].node_data, start)
        if "heading" in law:
            primary.plan["initial_heading"] = radial_inclination(
                law["heading"], phi, law_stream(state.streams, laws.streams, "heading", oid)
            )
        receipts.append(dict(organ_id=oid, origin_cm=start.tolist(), polar_angle_rad=float(phi)))
    state.diagnostics["primary_origins"] = dict(layout="disk", primaries=receipts)


def _translate_primary(primary, anchor, start):
    delta = start - np.array([anchor.x, anchor.y, anchor.z])
    anchor.x, anchor.y, anchor.z = (float(v) for v in start)
    subtree = [primary]
    while subtree:
        organ = subtree.pop()
        organ.set_coordinates(organ.get_coordinates() + delta)
        subtree.extend(organ.child_organs)


def _place_catalogue_origins(state):
    from ..data_model.resolution import sha256_json

    law = state.laws.origins
    entry, weight = state.vine_origin
    sim = state.simulation
    primaries = sim.organs[1]
    surface = law["surface_z_cm"]
    if entry["layout"] == "common_point":
        sim.translate_common_base(**entry["origin"], surface_z_cm=surface)
    else:
        for point, primary in zip(entry["primaries"], primaries):
            anchor = sim.G.bases[point["index"]].node_data
            position = np.array([point["x_cm"], point["y_cm"], surface - point["depth_cm"]])
            _translate_primary(primary, anchor, position)
            if "heading_unit" in point:
                primary.plan["initial_heading"] = point["heading_unit"]
    inputs = state.resolved.config.features.primary_origins.settings
    supplied = next(item for item in inputs.entries if item.entry_id == entry["entry_id"])
    state.diagnostics["vine_origin_catalogue"] = dict(
        catalogue_version=law["catalogue_version"], coordinate_frame=law["coordinate_frame"],
        selection=law["selection"]["mode"], normalized_selection_weight=weight,
        pool_sha256=sha256_json(law), entry_sha256=sha256_json(entry), selected_entry=entry,
        soil_surface_z_cm=surface, origins_status=supplied.origins_status, crown_census_status=supplied.crown_census_status,
        headings_status=getattr(supplied, "headings_status", None) or ("complete" if law["measured_headings"] else "missing"),
        provenance=None if supplied.provenance is None else supplied.provenance.model_dump(exclude_none=True),
        primary_organ_ids={str(index): axis.axis_state.biological_id for index, axis in enumerate(primaries)},
    )


def tapered_axis(organ, curve, taper, state):
    """Point-taper material over native construction intervals (and curve corners)."""
    from .materialize import check_representable, merge_cuts, taper_interval_diameters

    cutoff_mm = float(state.parameters.fine_root_threshold) * 10.0
    arcs = np.cumsum(organ.get_lengths())
    total = float(arcs[-1])
    stations = [] if curve is None else curve.stations[1:-1]
    material = profile_cuts(total, taper, cutoff_mm / 10.0)
    tolerance = state.laws.materialization["corner_coincidence_cm"]
    cuts = merge_cuts(np.r_[0.0, arcs], [stations, material], tolerance)[1:]
    if np.any(np.diff(np.r_[0.0, cuts]) <= 0):
        raise ValueError("Unrepresentable material cut on a tapered axis")
    if curve is not None:
        positions = curve.position(cuts)
    else:
        parent = organ.parent_node.node_data
        polyline = np.vstack([[parent.x, parent.y, parent.z], organ.get_coordinates()])
        positions = np.column_stack([np.interp(cuts, np.r_[0.0, arcs], polyline[:, k]) for k in range(3)])
    check_representable(curve.points[0] if curve is not None else polyline[0],
                        positions, np.diff(np.r_[0.0, cuts]))
    boundaries = np.r_[0., cuts]
    lengths = np.diff(boundaries)
    if "rate_per_cm" in taper:
        integrals = exponential_profile_integral(boundaries[:-1], cuts, total, taper)
        equivalents = np.sqrt(integrals / lengths)
    else:
        equivalents = taper_interval_diameters(boundaries, total, taper["base"], taper["tip"], taper["midpoint"])
    if state.laws.materialization.get("reconcile_length_metadata", False):
        from .cohort_geometry import reconcile_interval_lengths

        start = curve.points[0] if curve is not None else polyline[0]
        reconciled, changes = reconcile_interval_lengths(np.vstack([start, positions]), lengths, True)
        equivalents *= np.sqrt(lengths / reconciled)  # same integrated material
        lengths = reconciled
        state.law_counters["length_metadata_reconciliations"].extend(
            dict(organ_id=int(organ.segments[0].node_data.organ_id), **x) for x in changes
        )
    intervals = []
    for cut, xyz, diameter, length in zip(cuts, positions, equivalents, lengths):
        k = int(np.searchsorted(arcs, cut, side="left"))
        node = organ.segments[k]
        retained = arcs[k] == cut
        data = node.node_data.model_copy()
        data.x, data.y, data.z = (float(v) for v in xyz)
        data.length, data.diameter = float(length), float(diameter)
        data.root_type = fine_by_equivalent_diameter(diameter, cutoff_mm)
        intervals.append(EmittedInterval(None, node if retained else None, data=data))
    return intervals
