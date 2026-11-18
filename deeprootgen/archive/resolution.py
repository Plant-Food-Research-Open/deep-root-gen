"""Replay-only resolvers for historical records and migration tests."""
from pathlib import Path

from ..data_model.execution import RootSimulationConfig
from ..data_model.features import NativeParameters, RootSimulationConfigV3
from ..data_model.simulation_data_models import RootSimulationModel, reserved_key_conflicts
from ..data_model.resolution import (
    CONSTRUCTION_STEP_GUARD, CURVATURE_LAW, EngineLaws, ResolvedConfig, RESEARCH_ALIASES,
    NOT_CONSUMED_BY_STATIC_RUN, TOP_LEVEL_OWNED, OBSERVATION_SETTINGS, _describe,
    _construction_step_controls, _native_laws, _resolve_features, _supplied_payload,
    load_json_config, sha256_json,
)


def parse_config(spec):
    """Return one validated input model; never discard a versioned key."""
    if isinstance(spec, (str, Path)):
        spec = load_json_config(spec)
    if isinstance(spec, RootSimulationConfigV3):
        # Detach and revalidate: callers can mutate nested Pydantic objects.
        return RootSimulationConfigV3.model_validate(_v3_dump(spec))
    if isinstance(spec, RootSimulationConfig):
        return RootSimulationConfig.model_validate(spec.model_dump())
    if isinstance(spec, NativeParameters):
        raise TypeError("Schema-3 parameters run only inside a RootSimulationConfigV3")
    if isinstance(spec, RootSimulationModel):
        return spec
    if not isinstance(spec, dict):
        raise TypeError(
            "Simulation input must be a JSON object, JSON text/path or a validated simulation model"
        )
    if "schema_version" not in spec:
        reserved = reserved_key_conflicts(spec, RootSimulationModel.model_fields)
        if reserved:
            raise ValueError(
                f"Keys {reserved} require an explicit schema_version (2 or 3); "
                "legacy flat parsing would discard them"
            )
        return RootSimulationModel(**spec)
    version = spec["schema_version"]
    if type(version) is not int:
        raise ValueError("schema_version must be the integer 2 or 3")
    if version == 2:
        return RootSimulationConfig(**spec)
    if version == 3:
        return RootSimulationConfigV3(**spec)
    raise ValueError(f"Unsupported schema_version {version}; expected 2 or 3")


def _v3_dump(config):
    """Round-trip dump; drop only defaulted non-canonical parameter fields.

    A non-default value in such a field (for example a caller mutation after
    validation) is kept, so revalidation rejects it instead of discarding it.
    """
    values = config.model_dump()
    # Only the parameters the input set; omitted fallbacks keep their defaults.
    parameters = config.parameters.model_dump(exclude_unset=True)
    for name in TOP_LEVEL_OWNED + NOT_CONSUMED_BY_STATIC_RUN + OBSERVATION_SETTINGS + RESEARCH_ALIASES:
        if name in parameters and parameters[name] == NativeParameters.model_fields[name].default:
            del parameters[name]
    values["parameters"] = parameters
    return values


def canonical_input(config):
    """Reloadable serialization of a validated input (schema-3 keeps one owner)."""
    if isinstance(config, RootSimulationConfigV3):
        return _v3_dump(config)
    return config.model_dump()


def resolve_config(spec):
    """Parse if needed, choose laws, check dependencies, describe and hash."""
    supplied = _supplied_payload(spec)
    parsed = parse_config(spec)
    if isinstance(parsed, RootSimulationConfigV3):
        resolved = _resolve_features(parsed, parsed.parameters, "3")
    elif isinstance(parsed, RootSimulationConfig):
        resolved = _resolve_v2(parsed)
    else:
        resolved = _resolve_flat(parsed)
    resolved.hashes["supplied_input_sha256"] = sha256_json(supplied)
    resolved.description["hashes"] = dict(resolved.hashes)
    return resolved


def _resolve_flat(p):
    if _construction_step_controls(p):
        raise ValueError(CONSTRUCTION_STEP_GUARD)
    laws = _native_laws(p)
    description, hashes = _describe("flat", p, getattr(p, "random_seed", None), None, laws, {}, {}, {})
    return ResolvedConfig("flat", p, p, None, None, laws, {}, description, hashes)


def _resolve_v2(config):
    if config.construction.kind == "cohort":
        return _resolve_cohort_v5(config)
    if config.trajectory == "construction_steps_v1":
        return _resolve_construction_steps(config)
    p = config.construction.parameters
    if _construction_step_controls(p):
        raise ValueError(CONSTRUCTION_STEP_GUARD)
    laws = _native_laws(p)
    description, hashes = _describe("2", p, config.random_seed, config.simulation_tag, laws, {}, {}, {})
    return ResolvedConfig("2", config, p, config.random_seed, config.simulation_tag, laws, {}, description,
                          hashes, requested_simulation_tag=config.simulation_tag,
                          simulator_tag=config.simulation_tag)


SO4_INTERNAL_TAG = "SO4-T2-controlled-INITIAL"
SO4_SURFACE_Z_CM = 20.0


def _resolve_construction_steps(config):
    """Schema-2 SO4 construction steps: native construction, interval direction law."""
    from ..utils.primary_attachment import validate_distal_fraction

    p = config.construction.parameters.model_copy(update={"simulation_tag": SO4_INTERNAL_TAG})
    fraction = validate_distal_fraction(p.research_primary_attachment_distal_fraction)
    laws = EngineLaws(
        pre="frozen_scaffold_surface_check_v1",
        post="interval_pure_checks_v1",
        native_direction=None,
        direction={
            order: dict(law="construction_step_intervals", version="so4-construction-steps-v1",
                        boundary="minimum_angle_projection", surface_z_cm=SO4_SURFACE_Z_CM)
            for order in range(2, int(p.max_order) + 1)
        },
        relocation=(dict(law="distal_fraction", distal_fraction=float(fraction)) if fraction else None),
        surface_z_cm=SO4_SURFACE_Z_CM,
        writer=dict(first_node_id=0, records=True),
        view="construction_steps_v1",
        view_options=dict(
            coordinate_frame="model-x-across-y-along-depth20-minus-z-cm",
            internal_simulation_tag=SO4_INTERNAL_TAG,
        ),
    )
    description, hashes = _describe(
        "2", p, config.random_seed, config.simulation_tag, laws, {}, {}, {}, contract="construction_steps_v1"
    )
    return ResolvedConfig("2", config, p, config.random_seed, SO4_INTERNAL_TAG, laws, {}, description, hashes,
                          requested_simulation_tag=config.simulation_tag, simulator_tag=SO4_INTERNAL_TAG)


def _resolve_cohort_v5(config):
    """Schema-2 cohort: every construction law replaced; historical streams/IDs/output."""
    construction = config.construction
    c = construction.parameters.model_dump()
    older, later = construction.older_count, construction.later_count
    orders = {int(k): v for k, v in c["orders"].items()}
    p = NativeParameters.model_construct(
        random_seed=config.random_seed,
        simulation_tag=config.simulation_tag,
        max_order=5,
        outer_root_num=older,
        inner_root_num=later,
        root_tissue_density=c["dry_density_g_cm3"],
        fine_root_threshold=c["fine_cutoff_mm"] / 10.0,
        soil_surface_z_cm=0.0,
        tropism_mode="legacy",
    )
    laws = EngineLaws(
        construction="planned",
        lengths={k: dict(law="bounded_lognormal", **rule["length_cm"]) for k, rule in orders.items()},
        taper={
            k: dict(law="piecewise_linear_arclength", base_cm=rule["base_diameter_cm"],
                    tip_cm=rule["tip_diameter_cm"], midpoint_diameter_fraction=rule.get("midpoint_fraction", 0.5))
            for k, rule in orders.items()
        },
        branching={
            k: dict(law="first_branch_and_daughter_count", first_branch_cm=rule["first_branch_cm"],
                    branch_probability=rule["branch_probability"],
                    daughter_probabilities=rule["daughter_probabilities"])
            for k, rule in orders.items()
        },
        maturity=dict(
            groups=[
                dict(label="A", primary_indices=list(range(older)), maturity_range=[1.0, 1.0], draw="fixed"),
                dict(label="B", primary_indices=list(range(older, older + later)),
                     maturity_range=list(c["later_maturity"]), draw="uniform"),
            ],
            length_power=c["maturity_length_power"],
            diameter_power=c["maturity_diameter_power"],
            scale_branch_probability=True,
            diameter_target="base_anchor",
        ),
        cap=dict(fraction_max=c["child_diameter_fraction_max"]),
        origins=dict(
            layout="disk", radius_cm=c["crown_radius_cm"], depth_range_cm=list(c["crown_depth_cm"]), surface_z_cm=0.0,
            heading=dict(law="radial_inclination", inclination_mean_deg=c["inclination_mean_deg"],
                         inclination_sd_deg=c["inclination_sd_deg"],
                         inclination_bounds_deg=list(c["inclination_bounds_deg"])),
        ),
        direction={
            k: dict(
                law=CURVATURE_LAW, version="cohort-root-research-v5", step_cm=c["step_cm"],
                curvature_sd_rad_cm=rule["curvature_sd_rad_cm"], correlation_length_cm=rule["correlation_cm"],
                downward_drift_per_cm=rule["downward_drift_per_cm"], boundary="reflect_downward",
                first_interval="integrate", initial_heading="origin_heading" if k == 1 else "insertion_angle",
                insertion_mean_deg=c["insertion_mean_deg"], insertion_sd_deg=c["insertion_sd_deg"],
                surface_z_cm=0.0,
            )
            for k, rule in orders.items()
        },
        streams="cohort_v5",
        surface_z_cm=0.0,
        materialization=dict(rule="cohort_v5_material_cuts", corner_coincidence_cm=0.0,
                             reconcile_length_metadata=c.get("reconcile_length_metadata", False),
                             cutoff_mm=c["fine_cutoff_mm"], position_type="base"),
        writer=dict(first_node_id=1, records=False),
        view="cohort_v5",
        view_options=dict(
            coordinate_frame="local-crown-soil0-z-up-cm", crown_mass_g=c["crown_mass_g"],
            crown_depth_cm=list(c["crown_depth_cm"]), unrepresented_fine_mass_g=c.get("unrepresented_fine_mass_g", 0.0),
            dry_density_g_cm3=c["dry_density_g_cm3"], fine_cutoff_mm=c["fine_cutoff_mm"], version="cohort-root-research-v5",
        ),
    )
    limits = dict(max_organs=c["max_organs"], organ_limit_message="Explicit organ budget exhausted; no silent truncation")
    description, hashes = _describe(
        "2", p, config.random_seed, config.simulation_tag, laws, {}, {}, limits,
        contract=dict(cohort_v5=construction.model_dump(mode="json", exclude={"parameters": {"max_organs"}})),
    )
    return ResolvedConfig("2", config, p, config.random_seed, config.simulation_tag, laws, limits, description,
                          hashes, requested_simulation_tag=config.simulation_tag)


def explain_config(spec):
    return resolve_config(spec).description
