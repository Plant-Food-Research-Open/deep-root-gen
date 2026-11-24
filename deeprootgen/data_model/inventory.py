"""Checked migration inventory of every historical input field.

Each entry names the canonical schema-3 destination, the historical alias,
units, when it is active, its consumer and its disposition. The test suite
verifies that every field of the flat, schema-2 and cohort schemas is listed
and that every canonical destination exists in the schema-3 models.

Dispositions:
  canonical        expressed once in schema 3 and executed by the engine
  adapter_law      a native law variant the one engine executes for old
                   (flat/schema-2) inputs; no schema-3 key yet
  adapter_only     no static-generation consumer; old adapters still parse it
  observation      observation/visualization setting outside generation
  selector         historical complete-route selector; schema 3 has none
  support          crown/support accounting, never root material
"""

FLAT = "RootSimulationModel"
V2 = "RootSimulationConfig"
NATIVE_V2 = "NativeConstruction"
COHORT_V2 = "CohortConstruction"
COHORT = "CohortParameters"
COHORT_ORDER = "CohortOrder"

_ORDER = "features.{feature}.settings.by_order.<order>.{key}"

# Schema-4-only settings have no historical input alias.
SPATIAL_CONSTRUCTION_FIELDS = {
    "row_alignment_per_cm": dict(
        path=_ORDER.format(feature="curvature", key="row_alignment_per_cm"),
        units="1/cm", operation="symmetric alignment at physical curvature stations", rng="no draws",
    ),
    "basal_exclusion_cm": dict(
        path=_ORDER.format(feature="branching", key="basal_exclusion_cm"),
        units="cm", operation="exclude basal arclength from Poisson sites", rng="feature.branching_length_poisson",
    ),
    "apical_exclusion_cm": dict(
        path=_ORDER.format(feature="branching", key="apical_exclusion_cm"),
        units="cm", operation="exclude tip arclength from Poisson sites", rng="feature.branching_length_poisson",
    ),
    "mean_spacing_cm": dict(
        path=_ORDER.format(feature="branching", key="mean_spacing_cm"),
        units="cm", operation="mean contour spacing of unfiltered Poisson sites", rng="feature.branching_length_poisson",
    ),
    "length_poisson_branch_probability": dict(
        path=_ORDER.format(feature="branching", key="branch_probability"),
        units="probability", operation="parent activation before Poisson site draws", rng="feature.branching_length_poisson",
    ),
    "max_branch_proposals": dict(
        path="limits.max_branch_proposals", units="count", operation="execution budget for all Poisson proposals",
        rng="no draws",
    ),
    "vine_origin_catalogue": dict(
        path="features.primary_origins.settings", units="model-soil-frame cm and unit headings",
        operation="one whole-vine origin record", rng="feature.vine_origin_catalogue for sample selection",
    ),
}


def _e(schema, field, destination, units, activation, consumer, disposition, delivery=None, alias=None):
    return dict(
        schema=schema,
        field=field,
        destination=destination,
        alias=alias or field,
        units=units,
        activation=activation,
        consumer=consumer,
        disposition=disposition,
        delivery=delivery,
    )


def _native(field, units, consumer, activation="always"):
    return _e(FLAT, field, f"parameters.{field}", units, activation, consumer, "canonical")


FIELD_INVENTORY = [
    _e(FLAT, "random_seed", "random_seed", "-", "always", "RandomStreams (native sequence, keyed streams)", "canonical"),
    _e(FLAT, "simulation_tag", "simulation_tag", "label", "always", "graph node label; never model identity", "canonical"),
    _native("max_order", "count", "init_organs"),
    _native("fine_root_threshold", "cm", "native mean-cylinder classification"),
    _native("outer_root_num", "count", "init_organs"),
    _native("inner_root_num", "count", "init_organs"),
    _native("min_primary_length", "cm", "RootOrgan.init_lengths"),
    _native("max_primary_length", "cm", "RootOrgan.init_lengths"),
    _native("base_diameter", "cm", "RootOrgan.init_diameters"),
    _native("diameter_reduction", "fraction per order", "RootOrgan.init_diameters"),
    _native("apex_diameter", "cm", "RootOrgan.init_diameters"),
    _native("min_sec_root_num", "count", "RootOrgan._draw_lateral_count"),
    _native("max_sec_root_num", "count (exclusive upper bound)", "RootOrgan._draw_lateral_count"),
    _native("growth_sec_root", "fraction in [0,1)", "RootOrgan._draw_lateral_count"),
    _native("min_sec_root_length", "cm", "RootOrgan.init_lengths"),
    _native("max_sec_root_length", "cm", "RootOrgan.init_lengths"),
    _native("segments_per_root", "count", "construction intervals"),
    _native("length_reduction", "fraction per order", "RootOrgan.init_lengths"),
    _native("root_vary", "degrees", "RootOrgan.init_segment_coordinates"),
    _native("interbranch_distance", "cm", "sample_branch_sites"),
    _native("root_tissue_density", "g/cm3", "RootOrgan.calculate_mass"),
    _native("gravitropism", "blend fraction [0,1]", "apply_gravitropism", "tropism_mode=legacy"),
    _native("max_val_attempts", "count", "RootOrgan.validate"),
    _native("no_root_zone", "cm above surface", "legacy validation", "tropism_mode=legacy"),
    _native("floor_threshold", "fraction of parent length", "branch window"),
    _native("ceiling_threshold", "fraction of parent length", "branch window"),
    _native("tropism_mode", "law name", "native fallback direction law"),
    _native("soil_surface_z_cm", "cm", "one soil frame; validation and curvature boundary"),
    _native("fichtl_probability_down", "probability", "sample_heading", "tropism_mode=fichtl2024"),
    _native("fichtl_sigma", "rad/sqrt(cm)", "sample_fichtl_alpha", "tropism_mode=fichtl2024"),
    _native("fichtl_trials_type2", "trials per sqrt(cm)", "sample_heading", "tropism_mode=fichtl2024"),
    _native("fichtl_trials_type3", "trials per sqrt(cm)", "sample_heading", "tropism_mode=fichtl2024"),
    _native("fichtl_theta2_deg", "degrees", "insertion_heading", "tropism_mode=fichtl2024"),
    _native("fichtl_theta2_sd_deg", "degrees", "insertion_heading", "tropism_mode=fichtl2024"),
    _native("fichtl_theta3_deg", "degrees", "insertion_heading", "tropism_mode=fichtl2024"),
    _native("fichtl_theta3_sd_deg", "degrees", "insertion_heading", "tropism_mode=fichtl2024"),
    _e(FLAT, "root_ratio", None, "fraction", "never", "no static-generation consumer", "adapter_only"),
    _e(FLAT, "mechanical_constraints", None, "-", "never", "no static-generation consumer", "adapter_only"),
    _e(FLAT, "origin_min", None, "cm", "never", "no static-generation consumer", "adapter_only"),
    _e(FLAT, "origin_max", None, "cm", "never", "no static-generation consumer", "adapter_only"),
    _e(FLAT, "t", None, "steps", "legacy grow(); explicit-primary scope check", "RootOrgan.grow (not called by run)", "adapter_only"),
    *[
        _e(FLAT, name, None, units, "observation/plot", "Soil grid; init_fig; calibration statistics", "observation")
        for name, units in (
            ("enable_soil", "flag"),
            ("soil_layer_height", "cm"),
            ("soil_layer_width", "cm"),
            ("soil_n_layers", "count"),
            ("soil_n_cols", "count"),
        )
    ],
    _e(FLAT, "research_branch_placement", "features.branch_sites.settings.placement", "law name", "when set", "_prepare_branch_nodes", "canonical"),
    _e(FLAT, "research_current_length_cdfs_cm", "features.lengths.settings.by_order.<order>.lengths_cm", "cm", "orders listed", "sample_current_lengths", "canonical"),
    _e(FLAT, "research_current_length_grid", "features.direction.settings.stationing", "law name", "construction steps", "realize_intervals", "canonical"),
    _e(FLAT, "research_tertiary_length_rank_strength", "features.sibling_lengths.settings.tertiary_rank_strength", "strength", "order 3 families", "plan_tertiary_length_family", "canonical"),
    _e(FLAT, "research_parent2_branch_zone_cm", "features.branch_sites.settings.parent2_zone_cm", "cm", "order-2 parents", "parent2_zone_sites", "canonical"),
    _e(FLAT, "research_insertion_row_axial_kappa", "features.insertion.settings.row_axial_kappa_by_order", "concentration", "selected orders", "row_axial_insertion_heading", "canonical"),
    _e(FLAT, "research_primary_yaw_mean_deg", "features.primary_placement.settings.yaw_mean_deg", "degrees", "primaries", "apply_primary_yaw_initialization", "canonical"),
    _e(FLAT, "research_primary_yaw_reverse_probability", "features.primary_placement.settings.yaw_reverse_probability", "probability", "primaries", "reverse_primary_yaw", "canonical"),
    _e(FLAT, "research_primary_yaw_kappa", "features.primary_placement.settings.yaw_kappa", "concentration", "primaries", "sample_primary_yaw", "canonical"),
    _e(FLAT, "research_primary_attachment_distal_fraction", "features.attachment_relocation.settings.distal_fraction", "fraction", "construction steps", "attachment relocation", "canonical"),
    _e(FLAT, "research_primary_inclination_bias", "features.primary_placement.settings.inclination_bias", "fraction", "primaries", "apply_primary_inclination_initialization", "canonical"),
    _e(FLAT, "research_primary_design", "features.primary_placement.settings.explicit_design", "cm, degrees", "primaries", "primary_dimensions; design_rotation", "canonical"),
    _e(FLAT, "research_primary_branch_zone_cm", "features.branch_sites.settings.primary_zone_cm", "cm", "primaries", "primary_branch_zone_sites", "canonical"),
    _e(FLAT, "research_primary_branch_fractions", "features.branch_sites.settings.primary_fractions", "fraction of length", "primaries", "primary_fraction_sites", "canonical"),
    _e(FLAT, "research_base_origin_x_cm", "features.primary_origins.settings.x_cm", "cm", "with depth", "apply_root_origin_initialization", "canonical"),
    _e(FLAT, "research_base_origin_y_cm", "features.primary_origins.settings.y_cm", "cm", "with depth", "apply_root_origin_initialization", "canonical"),
    _e(FLAT, "research_base_depth_cm", "features.primary_origins.settings.depth_cm", "cm below surface", "with x/y", "apply_root_origin_initialization", "canonical"),
    _e(FLAT, "research_fichtl_sigma_by_order", "features.direction.settings.sigma_by_order", "rad/sqrt(cm)", "orders listed", "resolve_fichtl_sigma", "canonical"),
    _e(FLAT, "research_higher_order_tropism", "features.direction.settings.higher_order_tropism", "degrees, probability", "orders 4..5", "direction_controls", "canonical"),
    _e(FLAT, "research_root_counts_by_order", "features.branch_sites.settings.counts_by_order", "count", "when set", "plan_child_quotas", "canonical"),
    _e(V2, "schema_version", "schema_version", "-", "always", "parse_config", "canonical"),
    _e(V2, "random_seed", "random_seed", "-", "always", "RandomStreams", "canonical"),
    _e(V2, "simulation_tag", "simulation_tag", "label", "always", "graph node label", "canonical"),
    _e(V2, "construction", None, "-", "always", "historical route selector", "selector"),
    _e(V2, "trajectory", None, "-", "always", "historical route selector", "selector"),
    _e(NATIVE_V2, "kind", None, "-", "always", "historical route selector", "selector"),
    _e(NATIVE_V2, "parameters", "parameters", "-", "always", "native parameters", "canonical"),
    _e(COHORT_V2, "kind", None, "-", "always", "historical route selector", "selector"),
    _e(COHORT_V2, "parameters", "features", "-", "always", "cohort adapter -> planned construction laws", "canonical"),
    _e(COHORT_V2, "older_count", "features.cohort_maturity.settings.groups", "count", "always", "outer/inner primary counts and maturity groups", "canonical"),
    _e(COHORT_V2, "later_count", "features.cohort_maturity.settings.groups", "count", "always", "outer/inner primary counts and maturity groups", "canonical"),
    _e(COHORT, "step_cm", _ORDER.format(feature="curvature", key="step_cm"), "cm", "curvature active", "integrate_curve", "canonical"),
    _e(COHORT, "dry_density_g_cm3", "parameters.root_tissue_density", "g/cm3", "always", "material accounting", "canonical"),
    _e(COHORT, "fine_cutoff_mm", "parameters.fine_root_threshold", "mm", "always", "segment classification", "canonical"),
    _e(COHORT, "max_organs", "limits.max_organs", "count", "always", "engine resource limit", "canonical"),
    _e(COHORT, "crown_mass_g", None, "g", "always", "crown support accounting", "support"),
    _e(COHORT, "crown_depth_cm", "features.primary_origins.settings.depth_range_cm", "cm", "origins active", "origin layout", "canonical"),
    _e(COHORT, "crown_radius_cm", "features.primary_origins.settings.radius_cm", "cm", "origins active", "origin layout", "canonical"),
    _e(COHORT, "later_maturity", "features.cohort_maturity.settings.groups", "dimensionless", "maturity active", "maturity scaling", "canonical"),
    _e(COHORT, "maturity_length_power", "features.cohort_maturity.settings.length_power", "exponent", "maturity active", "maturity scaling", "canonical"),
    _e(COHORT, "maturity_diameter_power", "features.cohort_maturity.settings.diameter_power", "exponent", "maturity active", "maturity scaling", "canonical"),
    _e(COHORT, "child_diameter_fraction_max", "features.parent_diameter_cap.settings.fraction_max", "fraction", "cap active", "parent basal cap", "canonical"),
    _e(COHORT, "inclination_mean_deg", "features.primary_origins.settings.heading.inclination_mean_deg", "degrees below horizontal", "primaries", "laws.radial_inclination", "canonical"),
    _e(COHORT, "inclination_sd_deg", "features.primary_origins.settings.heading.inclination_sd_deg", "degrees", "primaries", "laws.radial_inclination", "canonical"),
    _e(COHORT, "inclination_bounds_deg", "features.primary_origins.settings.heading.inclination_bounds_deg", "degrees", "primaries", "laws.radial_inclination", "canonical"),
    _e(COHORT, "insertion_mean_deg", "features.curvature.settings.by_order.<order>.insertion_mean_deg", "degrees", "daughters", "insertion_heading", "canonical"),
    _e(COHORT, "insertion_sd_deg", "features.curvature.settings.by_order.<order>.insertion_sd_deg", "degrees", "daughters", "insertion_heading", "canonical"),
    _e(COHORT, "orders", "features", "-", "always", "per-order laws", "canonical"),
    _e(COHORT, "reconcile_length_metadata", "features.materialization.settings.reconcile_length_metadata", "flag", "when set", "reconcile_interval_lengths", "canonical"),
    _e(COHORT, "unrepresented_fine_mass_g", None, "g", "always", "separate traceable diagnostic", "support"),
    _e(COHORT_ORDER, "length_cm", "features.lengths.settings.by_order.<order>.mean", "cm", "lengths active", "bounded_draw", "canonical"),
    _e(COHORT_ORDER, "base_diameter_cm", "features.taper.settings.by_order.<order>.base_cm", "cm", "taper active", "point taper", "canonical"),
    _e(COHORT_ORDER, "tip_diameter_cm", "features.taper.settings.by_order.<order>.tip_cm", "cm", "taper active", "point taper", "canonical"),
    _e(COHORT_ORDER, "first_branch_cm", "features.branching.settings.by_order.<order>.first_branch_cm", "cm", "branching active", "laws.first_branch_sites", "canonical"),
    _e(COHORT_ORDER, "branch_probability", "features.branching.settings.by_order.<order>.branch_probability", "probability", "branching active", "laws.first_branch_sites", "canonical"),
    _e(COHORT_ORDER, "daughter_probabilities", "features.branching.settings.by_order.<order>.daughter_probabilities", "probabilities", "branching active", "laws.first_branch_sites", "canonical"),
    _e(COHORT_ORDER, "curvature_sd_rad_cm", _ORDER.format(feature="curvature", key="curvature_sd_rad_cm"), "rad/cm", "curvature active", "ou_joint_step", "canonical"),
    _e(COHORT_ORDER, "correlation_cm", _ORDER.format(feature="curvature", key="correlation_length_cm"), "cm", "curvature active", "ou_joint_step", "canonical", alias="correlation_cm"),
    _e(COHORT_ORDER, "downward_drift_per_cm", _ORDER.format(feature="curvature", key="downward_drift_per_cm"), "1/cm", "curvature active", "integrate_curve", "canonical"),
    _e(COHORT_ORDER, "midpoint_fraction", "features.taper.settings.by_order.<order>.midpoint_diameter_fraction", "fraction: d(L/2)=d_tip+f*(d_base-d_tip)", "taper active", "taper_diameter", "canonical", alias="midpoint_fraction"),
]
