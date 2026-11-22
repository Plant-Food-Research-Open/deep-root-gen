"""Canonical owners for existing SO4 leaf kernels; old aliases stay at the boundary."""

from typing import ClassVar

from .consumers import fichtl_direction_orders
from .simulation_data_models import CurrentLengthCDF, RootSimulationModel

OWNERS = {
    "primary_placement": dict(yaw_mean_deg="research_primary_yaw_mean_deg", yaw_kappa="research_primary_yaw_kappa",
                              yaw_reverse_probability="research_primary_yaw_reverse_probability",
                              inclination_bias="research_primary_inclination_bias", explicit_design="research_primary_design"),
    "branch_sites": dict(placement="research_branch_placement", counts_by_order="research_root_counts_by_order",
                         primary_zone_cm="research_primary_branch_zone_cm", primary_fractions="research_primary_branch_fractions",
                         parent2_zone_cm="research_parent2_branch_zone_cm"),
    "sibling_lengths": dict(tertiary_rank_strength="research_tertiary_length_rank_strength"),
    "insertion": dict(row_axial_kappa_by_order="research_insertion_row_axial_kappa"),
    "direction": dict(sigma_by_order="research_fichtl_sigma_by_order", higher_order_tropism="research_higher_order_tropism"),
}


class _CanonicalKernelAliases(RootSimulationModel):
    # Fichtl ownership was already checked against the canonical law table.
    canonical_generation: ClassVar[bool] = True


def _collect(features):
    updates = {}
    for owner, fields in OWNERS.items():
        block = getattr(features, owner)
        if not block.enabled:
            continue
        values = block.settings.model_dump(exclude_none=True)
        if not values:
            raise ValueError(f"Enabled {owner} needs at least one setting")
        updates.update({internal: values[public] for public, internal in fields.items() if public in values})
    return updates


def _resolve_direction(features, p, laws, updates):
    if not features.direction.enabled:
        return
    settings = features.direction.settings
    if (settings.boundary is not None or settings.first_interval is not None) and settings.stationing is None:
        raise ValueError("direction.boundary/first_interval requires an explicit stationing law")
    if settings.stationing is not None:
        updates["research_current_length_grid"] = settings.stationing
        for order in range(2, p.max_order + 1):
            if order in laws.direction:
                raise ValueError(f"Two direction owners for order {order}: curvature and construction steps")
            laws.direction[order] = dict(
                law="construction_step_intervals", version=settings.stationing,
                boundary=settings.boundary or "minimum_angle_projection", first_interval="assigned_insertion",
                surface_z_cm=float(p.soil_surface_z_cm),
            )
    if settings.post_correction == "pure_surface_check":
        laws.post = "workspace_pure_checks_v1"
    if settings.primary_correction == "frozen_surface_check":
        laws.pre = "frozen_scaffold_surface_check_v1"


def _check_placement(features, laws):
    if not features.primary_placement.enabled:
        return
    settings = features.primary_placement.settings
    origin = laws.origins or {}
    if origin.get("measured_headings") and any(
        getattr(settings, name) is not None
        for name in ("yaw_mean_deg", "yaw_kappa", "yaw_reverse_probability", "inclination_bias")
    ):
        raise ValueError("Measured vine-origin headings conflict with primary yaw or inclination controls")
    if settings.explicit_design is None:
        return
    if 1 in laws.lengths or 1 in laws.taper:
        raise ValueError("Explicit primary design owns primary dimensions/material; conflicts with lengths/taper order 1")
    if origin.get("layout") == "disk" or any(entry["layout"] == "primary_layout" for entry in origin.get("entries", ())):
        raise ValueError("Explicit primary design currently requires common origins")


def _check_sites(features, laws):
    if not features.branch_sites.enabled:
        return
    b = features.branch_sites.settings
    if b.primary_zone_cm is not None and b.primary_fractions is not None:
        raise ValueError("Primary branch zone and supplied fractions have the same site owner")
    if ((b.primary_zone_cm is not None or b.primary_fractions is not None) and 1 in laws.branching
            or b.parent2_zone_cm is not None and 2 in laws.branching
            or b.counts_by_order is not None and laws.branching
            or b.placement is not None and laws.branching):
        raise ValueError("Branch-site/count conditioning conflicts with replacement branching on its orders")


def _check_direction_consumers(updates, laws):
    for field in ("research_insertion_row_axial_kappa", "research_fichtl_sigma_by_order", "research_higher_order_tropism"):
        for order in updates.get(field, {}) or {}:
            if int(order) in laws.direction and laws.direction[int(order)]["law"] != "construction_step_intervals":
                raise ValueError(f"{field} has no Fichtl/insertion consumer on replaced order {order}")


def _check_canonical_fichtl_orders(p, laws, updates):
    if p.tropism_mode == "fichtl2024" and p.max_order > 5:
        raise ValueError("fichtl2024 mode currently supports max_order <= 5")
    required = {str(order) for order in fichtl_direction_orders(p, laws) if order >= 4}
    supplied = {str(order) for order in updates.get("research_higher_order_tropism", {})}
    if required != supplied:
        raise ValueError(
            "direction.higher_order_tropism requires entries for active Fichtl orders "
            f"{sorted(required)}, got {sorted(supplied)}"
        )


def _assign_curved_insertion(updates, laws, max_order):
    from ..utils.tropism import validate_row_axial_kappas

    field = "research_insertion_row_axial_kappa"
    if field not in updates:
        return
    native = {}
    for order, kappa in validate_row_axial_kappas(updates[field], max_order).items():
        direction = laws.direction.get(order, {})
        if direction.get("law") != "correlated_curvature":
            native[order] = kappa
        elif direction["initial_heading"] != "insertion_angle":
            raise ValueError(f"Row-axial insertion requires an insertion heading on curved order {order}")
        elif kappa > 0:
            if "sibling_sectors" in direction:
                raise ValueError(f"Sibling sectors and row-axial insertion both set the bearing on order {order}")
            direction["row_axial_kappa"] = kappa
    if native:
        updates[field] = native
    else:
        updates.pop(field)


def _validated_aliases(p, updates):
    """Validate aliases without filling absent canonical numerical fallbacks.

    The v1 kernels retain their declared historical scope/RNG policy. Values
    below fill validator scaffolding only, and are discarded after validation.
    """
    payload = p.model_dump()
    payload.update(updates)
    payload.update(root_ratio=.5, mechanical_constraints=0., t=0)
    defaults = dict(
        min_primary_length=1., max_primary_length=1., base_diameter=.1, diameter_reduction=0., apex_diameter=.01,
        min_sec_root_num=0, max_sec_root_num=0, growth_sec_root=0., min_sec_root_length=1., max_sec_root_length=1.,
        segments_per_root=1, length_reduction=1., root_vary=0., interbranch_distance=1., gravitropism=0.,
        fichtl_probability_down=.5, fichtl_sigma=0., fichtl_trials_type2=0., fichtl_trials_type3=0.,
        fichtl_theta2_deg=0., fichtl_theta2_sd_deg=0., fichtl_theta3_deg=0., fichtl_theta3_sd_deg=0.,
    )
    for field, value in defaults.items():
        if payload.get(field) is None:
            payload[field] = value
    validator = _CanonicalKernelAliases if getattr(p, "canonical_generation", False) else RootSimulationModel
    validated = validator(**payload)
    result = {field: getattr(validated, field) for field in updates}
    if "research_primary_design" in result:
        result["t"] = 0
    return p.model_copy(update=result)


def resolve_native_options(features, p, laws):
    updates = _collect(features)
    _resolve_direction(features, p, laws, updates)
    _assign_curved_insertion(updates, laws, p.max_order)
    _check_placement(features, laws)
    _check_sites(features, laws)
    _check_direction_consumers(updates, laws)
    if getattr(p, "canonical_generation", False):
        _check_canonical_fichtl_orders(p, laws, updates)
    if laws.lengths:
        updates["research_current_length_cdfs_cm"] = {
            order: CurrentLengthCDF(lengths_cm=law["lengths_cm"], cumulative_probabilities=law["cumulative_probabilities"])
            for order, law in laws.lengths.items() if law["law"] == "discrete_cdf"
        } or None
    if features.materialization.enabled:
        value = features.materialization.settings.reconcile_length_metadata
        if value is None or not laws.taper:
            raise ValueError("Materialization reconciliation needs a Boolean and at least one point-taper axis")
        laws.materialization["reconcile_length_metadata"] = value
    return _validated_aliases(p, updates) if updates else p
