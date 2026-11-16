"""Opt-in cylinder mass scenarios on caller-supplied root graph tables.

Geometry and child diameters are cm; explicit uniform density is dry g/cm3.
An order share is a scenario assumption, never a measured biomass target or a
diameter-defined fine-root share. No simulator, file reader, fitting, biological
threshold or legacy statistic is changed. Invalid graphs fail closed.
"""

from __future__ import annotations

from collections.abc import Mapping
import math
from numbers import Real

import numpy as np
import pandas as pd

from .core_observation import qualify_root_segments

VERSION = "supplied-graph-order-mass-allocation-v1"


class InfeasibleMassBudget(ValueError):
    """The supplied graph, order partition or locked mass cannot meet a budget."""


def _real(value, name, *, positive=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    result = float(value)
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return result


def _orders(values, name):
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{name} must be a list or tuple of positive integers")
    result = []
    for value in values:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value <= 0:
            raise ValueError(f"{name} must contain positive integers")
        result.append(int(value))
    if len(set(result)) != len(result):
        raise ValueError(f"{name} contains duplicate orders")
    return result


def _summary(segments):
    try:
        mass = math.fsum(segments.dry_mass_g)
        length = math.fsum(segments.length_cm)
        volume = math.fsum(segments.root_volume_cm3)
    except OverflowError as error:
        raise ValueError("Nonfinite aggregate cylinder arithmetic") from error
    srl = length / mass if mass else None
    reason = "zero_mass" if mass == 0 else None
    if srl is not None and not math.isfinite(srl):
        srl, reason = None, "nonfinite_length_mass_ratio"
    return dict(segment_count=len(segments), length_cm=length,
                volume_cm3=volume, mass_g=mass,
                specific_root_length_cm_g=srl,
                specific_root_length_defined=srl is not None,
                specific_root_length_undefined_reason=reason)


def audit_root_mass(nodes, edges, *, dry_density_g_cm3, fine_diameter_max_mm=2.5):
    """Audit all represented root cylinders without silently excluding invalids.

    Order-0 bases create no cylinder, regardless of their diameter/length/density
    metadata. ``root_tissue_density``, when supplied for nonbase nodes, must
    agree with the explicit uniform density (1e-12 relative numerical tolerance).
    Otherwise the density source is labelled a caller-supplied dry assumption.
    Recorded lengths/root_type never define geometric length or fine class.

    A hierarchy violation compares a daughter organ's first incoming cylinder
    with the incoming cylinder of its parent attachment node; bases are exempt.
    Organ IDs identify boundaries when present, otherwise order changes do.
    This diagnostic does not clamp diameters or impose a biological threshold.
    """
    density = _real(dry_density_g_cm3, "dry_density_g_cm3", positive=True)
    threshold = _real(fine_diameter_max_mm, "fine_diameter_max_mm", positive=True)
    if not isinstance(nodes, pd.DataFrame) or not isinstance(edges, pd.DataFrame):
        raise ValueError("nodes and edges must be DataFrames")
    # Require strict numeric geometry before the shared operator's conversion.
    required = {"order", "x", "y", "z", "diameter", "invalid_root"}
    if not required.issubset(nodes) or nodes.columns.duplicated().any():
        raise ValueError("Missing graph columns or duplicate columns")
    if not all(isinstance(flag, (bool, np.bool_)) for flag in nodes.invalid_root):
        raise ValueError("invalid_root must contain strict booleans")
    if nodes.invalid_root.any():
        raise ValueError("Require valid graph: invalid_root flags cannot be silently excluded")
    roots = nodes.loc[nodes.order.ne(0)]
    for column in ("x", "y", "z"):
        for value in nodes[column]:
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not math.isfinite(float(value)):
                raise ValueError("Coordinates must be finite real cm values")
    for value in roots.diameter:
        _real(value, "child diameter")
    metadata_matches = "root_tissue_density" in nodes
    if metadata_matches:
        for value in roots.root_tissue_density:
            recorded = _real(value, "root_tissue_density", positive=True)
            if not math.isclose(recorded, density, rel_tol=1e-12, abs_tol=0.):
                raise ValueError("Explicit dry density disagrees with nonbase root_tissue_density metadata")
    support = qualify_root_segments(nodes, edges, coordinate_frame="caller-supplied-cm-graph",
                                    fine_diameter_max_mm=threshold, dry_density_g_cm3=density)
    segments = support.segments.copy(deep=True)
    indexed = nodes.set_index("node_id", drop=False)
    segments["order"] = segments.child_id.map(indexed.order).astype(int)
    organ_count_available = "organ_id" in nodes
    if organ_count_available:
        for value in roots.organ_id:
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < 0:
                raise ValueError("organ_id must contain nonnegative integers")
        segments["organ_id"] = segments.child_id.map(indexed.organ_id)
        identities = segments[["plant_id", "organ_id", "order"]].drop_duplicates()
        if identities.duplicated(["plant_id", "organ_id"]).any():
            raise ValueError("An organ_id must have one root order within each plant")
    by_order = {}
    for order, part in segments.groupby("order", sort=True):
        values = _summary(part)
        values["organ_count"] = len(part[["plant_id", "organ_id"]].drop_duplicates()) if organ_count_available else None
        by_order[int(order)] = values
    parent_orders = segments.parent_id.map(indexed.order)
    parent_diameters = segments.parent_id.map(indexed.diameter)
    boundary = (segments.parent_id.map(indexed.organ_id).ne(segments.organ_id) if organ_count_available
                else parent_orders.ne(segments.order))
    if organ_count_available:
        entries = boundary | parent_orders.eq(0)
        entry_counts = segments.assign(organ_entry=entries).groupby(["plant_id", "organ_id"]).organ_entry.sum()
        if not entry_counts.eq(1).all():
            raise ValueError("Each organ_id must identify one connected organ chain with one entry")
        if segments.loc[~entries].parent_id.duplicated().any():
            raise ValueError("An organ_id must identify an unbranched organ chain")
    # Compare only real parent incoming cylinders: base metadata is not geometry.
    eligible = boundary & parent_orders.ne(0)
    violation_mask = pd.Series(False, index=segments.index)
    violation_mask.loc[eligible] = segments.loc[eligible, "diameter_cm"].gt(parent_diameters.loc[eligible])
    violations = [dict(child_id=int(row.child_id), parent_id=int(row.parent_id),
                       child_order=int(row.order), parent_order=int(parent_orders.loc[row.Index]),
                       child_diameter_cm=float(row.diameter_cm),
                       parent_attachment_diameter_cm=float(parent_diameters.loc[row.Index]))
                  for row in segments.loc[violation_mask].itertuples()]
    total = _summary(segments)
    for values in by_order.values():
        values["mass_share"] = values["mass_g"] / total["mass_g"] if total["mass_g"] else None
    return dict(version=VERSION, totals=total, by_order=by_order,
                by_diameter_class={label: _summary(segments.loc[segments.is_fine.eq(fine)])
                                   for label, fine in (("fine", True), ("coarse", False))},
                per_segment=segments, diagnostics=dict(
                    qualification="ALGORITHM_ONLY_SCENARIO_ASSUMPTION",
                    invalid_policy="require_all_nodes_valid", base_node_count=support.diagnostics["base_node_count"],
                    length_source="geometric_endpoint_distance_cm", diameter_source="constant_incoming_child_diameter_cm",
                    dry_density_g_cm3=density, density_source="explicit_caller_uniform_dry_density_assumption",
                    density_metadata="matching_nonbase_metadata" if metadata_matches else "not_supplied",
                    fine_diameter_max_mm=threshold, fine_class_source="diameter_independent_of_root_type_and_order",
                    hierarchy_boundary_source="organ_id" if organ_count_available else "root_order_change",
                    hierarchy_violations=violations, hierarchy_violation_count=len(violations),
                    zero_length_segment_count=int(segments.length_cm.eq(0).sum()),
                    zero_mass_segment_count=int(segments.dry_mass_g.eq(0).sum()),
                    srl_definition="total_geometric_length_cm / total_dry_mass_g; None if zero mass or nonfinite ratio",
                    biological_thresholds_applied=False))


def allocate_order_mass(nodes, edges, *, dry_density_g_cm3, groups, target_total_g=None,
                        locked_orders=(), fine_diameter_max_mm=2.5):
    """Return ``(new_nodes, new_edges, diagnostics)`` for an explicit scenario.

    Groups are records ``{'orders': [1, 2, 3], 'share': .75}`` partitioning all
    represented orders exactly once; positive shares sum to one. For each group,
    locked mass is subtracted first and unlocked diameters share one square-root
    mass scale, preserving relative taper. No target means preserve original
    total mass. A target of zero is allowed and can produce zero diameters.
    Density, labels, topology, coordinates, lengths and seeds are unchanged.
    Primary evidence modification and fine-cutoff migration are reported;
    biological/soft limits and approval of a scenario belong to the caller.
    """
    try:
        before = audit_root_mass(nodes, edges, dry_density_g_cm3=dry_density_g_cm3,
                                 fine_diameter_max_mm=fine_diameter_max_mm)
        represented = set(before["by_order"])
        if not isinstance(groups, (list, tuple)) or not groups:
            raise ValueError("groups must be a nonempty list or tuple")
        locked = set(_orders(locked_orders, "locked_orders"))
        if not locked <= represented:
            raise ValueError("locked_orders must be represented orders")
        partition, parsed = [], []
        for group in groups:
            if not isinstance(group, Mapping) or set(group) != {"orders", "share"}:
                raise ValueError("Each group must have exactly orders and share")
            orders = _orders(group["orders"], "group orders")
            if not orders:
                raise ValueError("Group orders cannot be empty")
            share = _real(group["share"], "group share", positive=True)
            parsed.append((orders, share))
            partition.extend(orders)
        if len(partition) != len(set(partition)) or set(partition) != represented:
            raise ValueError("groups must cover represented orders exactly once")
        if not math.isclose(math.fsum(share for _, share in parsed), 1., rel_tol=0., abs_tol=1e-12):
            raise ValueError("Group shares must sum to one")
        original_total = before["totals"]["mass_g"]
        total = original_total if target_total_g is None else _real(target_total_g, "target_total_g")
        new_nodes, new_edges = nodes.copy(deep=True), edges.copy(deep=True)
        group_records, order_records = [], {}
        for group_index, (orders, share) in enumerate(parsed):
            original = math.fsum(before["by_order"][order]["mass_g"] for order in orders)
            fixed = math.fsum(before["by_order"][order]["mass_g"] for order in orders if order in locked)
            unlocked = math.fsum(before["by_order"][order]["mass_g"] for order in orders if order not in locked)
            target = total * share
            if not math.isfinite(target):
                raise ValueError("Nonfinite group target arithmetic")
            remaining = target - fixed
            # This is only a roundoff allowance, not a biological tolerance.
            tolerance = 32 * np.finfo(float).eps * max(target, fixed, np.finfo(float).tiny)
            if remaining < -tolerance:
                raise ValueError("Locked mass exceeds group allocation")
            if abs(remaining) <= tolerance:
                remaining = 0.
            if unlocked == 0:
                if remaining != 0:
                    raise ValueError("Positive group budget has zero unlocked source mass")
                scale = 1.
            else:
                scale = math.sqrt(remaining) / math.sqrt(unlocked)
                if not math.isfinite(scale):
                    raise ValueError("Nonfinite diameter scale")
            for order in orders:
                factor = 1. if order in locked else scale
                mask = new_nodes.order.eq(order)
                new_nodes.loc[mask, "diameter"] = new_nodes.loc[mask, "diameter"] * factor
                original_order = before["by_order"][order]["mass_g"]
                target_order = original_order * factor * factor
                order_records[order] = dict(group_index=group_index, locked=order in locked,
                                           original_mass_g=original_order, target_mass_g=target_order,
                                           original_share=original_order / original_total if original_total else None,
                                           target_share=target_order / total if total else None,
                                           diameter_scale_factor=factor)
            group_records.append(dict(group_index=group_index, orders=orders, target_share=share,
                                      original_share=original / original_total if original_total else None,
                                      original_mass_g=original, target_mass_g=target, locked_mass_g=fixed,
                                      original_unlocked_mass_g=unlocked, unlocked_diameter_scale_factor=scale))
        after = audit_root_mass(new_nodes, new_edges, dry_density_g_cm3=dry_density_g_cm3,
                                fine_diameter_max_mm=fine_diameter_max_mm)
        for record in group_records:
            achieved = math.fsum(after["by_order"][order]["mass_g"] for order in record["orders"])
            record.update(achieved_mass_g=achieved, achieved_share=achieved / after["totals"]["mass_g"]
                          if after["totals"]["mass_g"] else None)
            if not math.isclose(achieved, record["target_mass_g"], rel_tol=1e-12, abs_tol=0.):
                raise ValueError("Achieved group mass does not satisfy target numerically")
        for order, record in order_records.items():
            record.update(achieved_mass_g=after["by_order"][order]["mass_g"],
                          achieved_share=after["by_order"][order]["mass_share"])
        old = before["per_segment"].set_index("child_id")
        new = after["per_segment"].set_index("child_id")
        migration = old.is_fine.ne(new.is_fine)
        migrations = [dict(child_id=int(child), order=int(old.loc[child, "order"]),
                           original_diameter_cm=float(old.loc[child, "diameter_cm"]),
                           allocated_diameter_cm=float(new.loc[child, "diameter_cm"]),
                           original_class="fine" if old.loc[child, "is_fine"] else "coarse",
                           allocated_class="fine" if new.loc[child, "is_fine"] else "coarse")
                      for child in old.index[migration]]
        primary_changed = bool((new_nodes.loc[new_nodes.order.eq(1), "diameter"] !=
                                nodes.loc[nodes.order.eq(1), "diameter"]).any())
        diagnostics = dict(version=VERSION, target_kind="scenario_assumption_not_measured_biomass",
                           total_policy="preserve_original" if target_total_g is None else "explicit_scenario_total",
                           original_total_g=original_total, target_total_g=total,
                           achieved_total_g=after["totals"]["mass_g"], groups=group_records,
                           by_order=order_records, locked_orders=sorted(locked),
                           primary_evidence_would_be_modified=primary_changed,
                           fine_cutoff_migration_count=len(migrations), fine_cutoff_migrations=migrations,
                           hierarchy_violations=after["diagnostics"]["hierarchy_violations"],
                           hierarchy_violation_count=after["diagnostics"]["hierarchy_violation_count"],
                           biological_thresholds_applied=False, before=before, after=after)
        return new_nodes, new_edges, diagnostics
    except (ValueError, TypeError, OverflowError, KeyError) as error:
        raise InfeasibleMassBudget(str(error)) from error
