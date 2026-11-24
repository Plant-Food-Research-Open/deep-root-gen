"""One parameter-consumer map for canonical requirements and model identity.

Compatibility draws depend on draw count, not on the unused uniform bounds.
Values with no numerical consumer remain only in supplied-input provenance.
"""


def fichtl_direction_orders(p, laws):
    """Orders that use Fichtl controls, including construction-step directions."""
    if p.tropism_mode != "fichtl2024":
        return set()
    return {
        order for order in range(2, p.max_order + 1)
        if order not in laws.direction or laws.direction[order]["law"] == "construction_step_intervals"
    }


def spatial_feature_consumers(laws):
    from .inventory import SPATIAL_CONSTRUCTION_FIELDS
    from ..model.branching_laws import LENGTH_POISSON_LAW

    aligned = sorted(order for order, law in laws.direction.items() if "row_alignment" in law)
    poisson = sorted(order for order, law in laws.branching.items() if law["law"] == LENGTH_POISSON_LAW)
    catalogue = laws.origins is not None and laws.origins["layout"] == "vine_catalogue"
    owners = dict.fromkeys(SPATIAL_CONSTRUCTION_FIELDS, poisson)
    owners.update(row_alignment_per_cm=aligned, vine_origin_catalogue=[1] if catalogue else [])
    return {
        field: dict(record, orders=owners[field], status="active" if owners[field] else "inactive")
        for field, record in SPATIAL_CONSTRUCTION_FIELDS.items()
    }


def parameter_consumers(p, laws):
    orders = set(range(1, int(p.max_order) + 1))
    planned = laws.construction == "planned"  # historical adapter policy only
    native_lengths = {k for k in orders if k not in laws.lengths and k not in (getattr(p, "research_current_length_cdfs_cm", None) or {})}
    native_material = orders - set(laws.taper)
    birth_material = {k for k in orders if any(j >= k for j in native_material)}
    branches = {k for k in orders if k < max(orders) and k not in laws.branching}
    counts_conditioned = getattr(p, "research_root_counts_by_order", None) is not None
    fallback_directions = fichtl_direction_orders(p, laws)
    geometry_needed = {k for k in orders if k not in laws.direction or laws.direction[k].get("initial_heading") == "scaffold_chord"}
    result = {}

    def add(names, operation, owners, units, compatibility_draws=None, required=True):
        for name in names:
            result[name] = dict(operation=operation, orders=sorted(owners), units=units,
                                status="active" if owners and not planned else "replaced",
                                required=bool(owners and not planned and required),
                                rng=compatibility_draws or "native sequential; historical schedule")

    add(("min_primary_length", "max_primary_length"), "length", native_lengths & {1}, "cm")
    add(("min_sec_root_length", "max_sec_root_length"), "length", native_lengths - {1}, "cm")
    add(("length_reduction",), "length", native_lengths - {1}, "dimensionless")
    add(("base_diameter", "diameter_reduction", "apex_diameter"), "birth_material", birth_material, "cm or fraction")
    add(("min_sec_root_num", "max_sec_root_num", "growth_sec_root"), "branch_count", set() if counts_conditioned else branches - set(getattr(p, "daughters_by_parent_order", {})), "count or fraction")
    add(("interbranch_distance", "floor_threshold", "ceiling_threshold"), "attachment_sites", branches, "cm or fraction")
    # Segment count remains a real consumer for proportions, draw count and
    # construction-cylinder inheritance, even when total length is replaced.
    add(("segments_per_root",), "construction_partition", orders, "count", required=False)
    add(("root_vary",), "scaffold_heading", orders if p.root_vary is not None else geometry_needed,
        "degrees", required=bool(geometry_needed))
    if planned:
        for name in ("gravitropism", "no_root_zone", "max_val_attempts", "tropism_mode"):
            add((name,), "native_direction", set(), "native")
    elif p.tropism_mode == "legacy":
        add(("gravitropism",), "native_direction", orders - set(laws.direction), "fraction")
    else:
        add(("gravitropism", "no_root_zone"), "native_direction", set(), "native")
    for name in ("fichtl_probability_down", "fichtl_trials_type2", "fichtl_theta2_deg", "fichtl_theta2_sd_deg"):
        add((name,), "fichtl_direction", fallback_directions & {2}, "native")
    for name in ("fichtl_trials_type3", "fichtl_theta3_deg", "fichtl_theta3_sd_deg"):
        add((name,), "fichtl_direction", fallback_directions & {3}, "native")
    sigma_orders = fallback_directions - set(getattr(p, "research_fichtl_sigma_by_order", None) or {})
    add(("fichtl_sigma",), "fichtl_direction", sigma_orders, "rad/sqrt(cm)")
    return result
