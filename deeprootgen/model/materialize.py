"""Single materializer: the union of construction, attachment and geometric cuts.

Biological organs keep their original construction intervals (and therefore
the birth context used by native daughter sampling). A replaced direction law
can add geometric corners; materialization inserts them as extra graph cuts
without changing contour length, interval material or any sampled dimension.
The materializer resamples nothing and allocates no IDs; the writer in
``hgraph.publish_graph`` owns graph identities.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from ..data_model.features import CORNER_COINCIDENCE_CM  # noqa: E402


@dataclass
class AxisCurve:
    """Realized centreline of one axis on physical arclength (cm)."""

    organ_id: int
    stations: np.ndarray
    points: np.ndarray
    construction_arcs: np.ndarray
    law: dict
    receipt: dict = field(default_factory=dict)

    def position(self, arc):
        arc = np.asarray(arc, dtype=float)
        return np.column_stack([np.interp(arc, self.stations, self.points[:, k]) for k in range(3)])

    def tangent(self, arc, coincidence_cm=CORNER_COINCIDENCE_CM):
        """Direction of the incoming (base-side) linear piece ending at ``arc``.

        Exact corners use the incoming piece. A nearby attachment on the tip
        side uses that side's piece; proximity does not identify physical events.
        """
        j = int(np.searchsorted(self.stations, float(arc), side="left")) - 1
        j = min(max(j, 0), len(self.stations) - 2)
        return self.points[j + 1] - self.points[j]


@dataclass(frozen=True)
class EmittedInterval:
    """One published edge: material/classification context plus geometry.

    ``data`` is a complete node record for laws that classify each segment;
    otherwise ``template`` supplies context and the optional geometry overrides.
    ``source`` is the construction point this cut retains, if any.
    ``cut_cm`` retains the original station when edge metadata may be reconciled.
    """

    template: Any
    source: Any
    xyz: Optional[tuple] = None
    length: Optional[float] = None
    diameter: Optional[float] = None
    data: Any = None
    cut_cm: Optional[float] = None


def identity_axis(organ):
    """Native intervals are already final; publish them unchanged."""
    return [EmittedInterval(node.node_data, node) for node in organ.segments]


def curved_axis(organ, curve):
    """Insert every retained corner; construction cuts keep their identity."""
    nodes = organ.segments
    arcs = np.asarray(curve.construction_arcs, dtype=float)
    total = float(arcs[-1])
    interior = curve.stations[(curve.stations > 0) & (curve.stations < total)]
    cuts = np.unique(np.r_[arcs, interior])
    lengths = np.diff(np.r_[0.0, cuts])
    if not np.isfinite(cuts).all() or np.any(lengths <= 0):
        raise ValueError("Unrepresentable material cut on a realized axis")
    positions = curve.position(cuts)
    check_representable(curve.points[0], positions, lengths)
    intervals = []
    for cut, xyz, length in zip(cuts, positions, lengths):
        k = int(np.searchsorted(arcs, cut, side="left"))
        node = nodes[k]
        retained = arcs[k] == cut
        if retained:
            current = np.array([node.node_data.x, node.node_data.y, node.node_data.z], dtype=float)
            if not np.allclose(current, xyz, rtol=0, atol=1e-12):
                raise ValueError("A realized axis moved after direction realization")
            xyz = current
        intervals.append(
            EmittedInterval(
                node.node_data,
                node if retained else None,
                tuple(float(v) for v in xyz),
                float(length),
                float(node.node_data.diameter),
            )
        )
    return intervals


def materialize_forest(organs, curves, state=None):
    """Map biological organ ID to its published intervals, in birth order.

    Native axes keep their construction intervals; a realized curve adds its
    corners; a point-taper material law adds midpoint/cutoff cuts and replaces
    each interval's diameter by the volume-conserving equivalent diameter.
    """
    axes = {}
    tapered = {} if state is None else getattr(state, "tapers", {})
    for organ in organs:
        organ_id = int(organ.segments[0].node_data.organ_id)
        curve, taper = curves.get(organ_id), tapered.get(organ_id)
        if taper is not None:
            from .native_features import tapered_axis

            axes[organ_id] = tapered_axis(organ, curve, taper, state)
            state.material_laws[organ_id] = "point_taper"
        elif curve is not None:
            axes[organ_id] = curved_axis(organ, curve)
        else:
            axes[organ_id] = identity_axis(organ)
    return axes


def check_curve_postconditions(organ, curve, surface_z, *, rtol=1e-9, retained_cuts=None):
    """Pure checks of a published realized axis; draws and repairs nothing."""
    xyz = np.array([[n.node_data.x, n.node_data.y, n.node_data.z] for n in organ.segments], float)
    parent = organ.parent_node.node_data
    previous = np.vstack([[parent.x, parent.y, parent.z], xyz[:-1]])
    lengths = np.array([n.node_data.length for n in organ.segments], float)
    actual = np.linalg.norm(xyz - previous, axis=1)
    scale = np.linalg.norm(xyz, axis=1) + np.linalg.norm(previous, axis=1)
    if np.any(np.abs(actual - lengths) > rtol * lengths + 64 * np.finfo(float).eps * scale):
        raise ValueError(f"Realized axis {curve.organ_id} edge lengths disagree with its geometry")
    if np.any(xyz[:, 2] > surface_z + 1e-9):
        raise ValueError(f"Realized axis {curve.organ_id} crosses the declared soil surface")
    total = float(curve.construction_arcs[-1])
    if not np.isclose(lengths.sum(), total, rtol=1e-12, atol=1e-12):
        raise ValueError(f"Realized axis {curve.organ_id} does not conserve contour length")
    if retained_cuts is not None:
        # Reconciled lengths are geometric chords and can shift cumulative
        # length away from the original station even when its vertex survives.
        cuts = np.asarray(retained_cuts)
        stations = curve.stations[1:-1]
        indices = np.searchsorted(cuts, stations)
        tip_tolerance = 64 * np.finfo(float).eps * total
        # Splitting an attachment interval can perturb the summed tip arc.
        # The tip still follows the curve at that cut. Interior stations are
        # retained as exact cuts and must have their original vertices.
        if (len(cuts) != len(xyz)
                or abs(cuts[-1] - curve.stations[-1]) > tip_tolerance
                or not np.array_equal(xyz[-1], curve.position(cuts[-1:])[0])
                or np.any(indices >= len(cuts) - 1) or not np.array_equal(cuts[indices], stations)
                or not np.array_equal(xyz[indices], curve.points[1:-1])):
            raise ValueError(f"Realized axis {curve.organ_id} lost a direction corner")
        return
    published_arcs = np.cumsum(lengths)
    for station in curve.stations[1:]:
        if np.min(np.abs(published_arcs - station)) > 64 * np.finfo(float).eps * max(total, abs(station)):
            raise ValueError(f"Realized axis {curve.organ_id} lost a direction corner")


def merge_cuts(identity, candidate_groups, tolerance):
    """Retain every geometric/identity event and every resolvable material cut.

    Only a material event within binary64 roundoff of an existing cut can be
    omitted from output. Its exact breakpoint still participates in the
    piecewise volume integral. ``tolerance`` remains an adapter argument, not
    permission to discard a real corner or use an absolute physical tolerance.
    """
    groups = list(candidate_groups)
    kept = np.unique(np.r_[identity, groups[0] if groups else []])
    for group in groups[1:]:
        for cut in np.asarray(group, dtype=float):
            k = int(np.searchsorted(kept, cut))
            if all(abs(cut - kept[i]) > 64 * np.finfo(float).eps * max(abs(cut), abs(kept[i]))
                   for i in (k - 1, k) if 0 <= i < len(kept)):
                kept = np.insert(kept, k, cut)
    return kept


def check_representable(start, points, lengths):
    """Reject intervals that cannot be represented at their coordinate scale."""
    previous = np.vstack([start, points[:-1]])
    floor = 64 * np.finfo(float).eps * (np.linalg.norm(previous, axis=1) + np.linalg.norm(points, axis=1))
    if np.any(lengths <= floor) or np.any(np.linalg.norm(points - previous, axis=1) <= floor):
        raise ValueError("Interval below coordinate-scale resolution floor")


def taper_interval_diameters(cuts, total, base, tip, midpoint):
    """Exact piecewise-taper volume, including breakpoints omitted as roundoff."""
    from .cohort_geometry import taper_diameter

    result = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        events = np.array([a, total / 2, b] if a < total / 2 < b else [a, b])
        diameters = taper_diameter(events, total, base, tip, midpoint)
        squares = (diameters[:-1]**2 + diameters[:-1] * diameters[1:] + diameters[1:]**2) / 3
        result.append(np.sqrt(np.dot(np.diff(events), squares) / (b - a)))
    return np.asarray(result)


def interior_material_cuts(length, base, tip, cutoff_cm, midpoint):
    """Point-taper breakpoints: midpoint (fraction != 0.5) and fine-cutoff crossings."""
    from .cohort_geometry import material_cuts

    return material_cuts(length, [], [], base, tip, cutoff_cm, midpoint, minimum_interval_cm=0.)[1:-1]


def fine_by_equivalent_diameter(diameter_cm, cutoff_mm):
    """Per-segment classification: fine when the diameter is at the cutoff or below."""
    return "fine" if diameter_cm * 10 <= np.nextafter(cutoff_mm, np.inf) else "structural"


def planned_axis(organ, curve, rule, simulation_tag, density, counters):
    """Fully replaced axis: material cuts, reconciliation and point-taper material.

    Cuts are the union of curve stations, birth sites, the midpoint when the
    midpoint fraction is not one half, and fine-cutoff crossings (exact union;
    intervals <= 1e-12 cm fail). Each edge carries the equivalent diameter that
    conserves the integrated taper volume over it.
    """
    from ..data_model import RootNodeModel
    from .cohort_geometry import equivalent_diameter, material_cuts, reconcile_interval_lengths, taper_diameter

    plan = organ.plan
    organ_id = int(organ.segments[0].node_data.organ_id)
    order = plan["order"]
    length, sites, base, tip, midpoint = plan["length"], plan["sites"], plan["base"], plan["tip"], plan["midpoint"]
    cutoff_mm = rule["cutoff_mm"]
    tolerance = rule["corner_coincidence_cm"]
    if tolerance == 0.0:
        # Historical exact union (cohort contract): near-coincident cuts fail.
        cuts = material_cuts(length, curve.stations, sites, base, tip, cutoff_mm / 10, midpoint)
    else:
        cuts = merge_cuts(
            np.r_[0.0, sites, length],
            [curve.stations[1:-1], interior_material_cuts(length, base, tip, cutoff_mm / 10, midpoint)],
            tolerance,
        )
        if np.any(np.diff(cuts) <= 1e-12):
            raise ValueError("Unrepresentable material cut on a planned axis")
    coords = curve.position(cuts)
    ds = np.diff(cuts)
    try:
        ds, changes = reconcile_interval_lengths(coords, ds, rule.get("reconcile_length_metadata", False))
    except ValueError as exc:
        raise ValueError(f"Organ {organ_id}: {exc}") from exc
    counters["length_metadata_reconciliations"].extend(dict(organ_id=organ_id, **x) for x in changes)
    np.testing.assert_allclose(ds.sum(), length, rtol=1e-9, atol=0)
    point_d = taper_diameter(cuts, length, base, tip, midpoint)
    equiv = equivalent_diameter(point_d[:-1], point_d[1:])
    position_type = "base" if rule["position_type"] == "base" else plan["position_type"]
    retained = {int(np.searchsorted(cuts, site)): organ.segments[k] for k, site in enumerate(sites)}
    retained[len(cuts) - 1] = organ.segments[-1]
    intervals = []
    for rank, (point, diameter, interval) in enumerate(zip(coords[1:], equiv, ds), 1):
        data = RootNodeModel(
            plant_id=1,
            organ_id=organ_id,
            order=order,
            segment_rank=rank,
            x=float(point[0]),
            y=float(point[1]),
            z=float(point[2]),
            diameter=float(diameter),
            length=float(interval),
            root_tissue_density=density,
            invalid_root=False,
            simulation_tag=simulation_tag,
            root_type=fine_by_equivalent_diameter(diameter, cutoff_mm),
            order_type="primary" if order == 1 else "secondary",
            position_type=position_type,
        )
        intervals.append(EmittedInterval(None, retained.get(rank), data=data))
    volume = np.pi / 4 * float(np.dot(ds, equiv**2))
    record = dict(
        organ_id=organ_id,
        parent_organ_id=plan["parent_organ_id"],
        order=order,
        cohort=plan["label"],
        maturity=plan["maturity"],
        primary_tree_id=plan["tree"],
        length_cm=length,
        base_diameter_cm=base,
        mid_diameter_cm=float(taper_diameter(length / 2, length, base, tip, midpoint)),
        tip_diameter_cm=tip,
        first_branch_draw_cm=plan["first_draw"],
        first_branch_cm=sites[0] if sites else np.nan,
        daughter_count=len(sites),
        attachment_cm=plan["attachment_cm"],
        volume_cm3=volume,
        dry_mass_g=volume * density,
    )
    return intervals, record
