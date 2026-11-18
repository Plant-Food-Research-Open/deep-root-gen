"""One parser and one resolver for every fresh-generation input.

``parse_config`` turns raw input into exactly one validated input model:
legacy flat ``RootSimulationModel``, schema-2 ``RootSimulationConfig`` or
schema-3 ``RootSimulationConfigV3``. Versioned keys are reserved before legacy
flat parsing, so a requested option block can never be silently discarded, and
the JSON reader rejects duplicate keys at every nesting level.

``resolve_config`` chooses one active law per stage and order, checks
dependencies before any simulation state or randomness is used, and produces
the resolved description saved with every result (``--explain-config``).
Already-parsed legacy objects cannot recover keys discarded earlier; callers
must pass raw input through this module.
"""

import copy
import functools
import hashlib
import json
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .execution import RootSimulationConfig
from .features import (
    CORNER_COINCIDENCE_CM,
    CURVATURE_BOUNDS,
    CURVATURE_LAW,
    CURVATURE_LAW_VERSION,
    CURVATURE_STREAM_NAMESPACE,
    FEATURE_NAMES,
    NOT_CONSUMED_BY_STATIC_RUN,
    OBSERVATION_SETTINGS,
    RESEARCH_ALIASES,
    TOP_LEVEL_OWNED,
    NativeParameters,
    RootSimulationConfigV3,
)
from .simulation_data_models import RootSimulationModel, reserved_key_conflicts

ENGINE_LIFECYCLE_VERSION = "native-engine-lifecycle-v1"
ENGINE_PHASES = (
    "prepare_forest",
    "place_scaffold",
    "record_initial",
    "pre_direction",
    "attachments",
    "realize_directions",
    "post_direction",
    "materialize",
    "emit",
    "check",
    "publish",
)
CONSTRUCTION_STEP_GUARD = (
    "Construction-step grid/tertiary rank requires named controlled replay; native run is unsupported"
)
EFFECTIVE_NATIVE_FIELDS = tuple(
    name
    for name in RootSimulationModel.model_fields
    if name not in TOP_LEVEL_OWNED + NOT_CONSUMED_BY_STATIC_RUN + OBSERVATION_SETTINGS + RESEARCH_ALIASES
)
CURVATURE_REQUIRED = (
    "law",
    "step_cm",
    "curvature_sd_rad_cm",
    "correlation_length_cm",
    "downward_drift_per_cm",
    "boundary",
    "first_interval",
)
UNITS = dict(
    length="cm",
    diameter="cm",
    density="g/cm3",
    angles="degrees unless a field name states rad",
    fichtl_sigma="rad/sqrt(cm)",
    curvature_sd_rad_cm="stationary per-component curvature SD, rad/cm",
    correlation_length_cm="cm",
    downward_drift_per_cm="heading drift toward -z per cm of arclength (dimensionless/cm)",
    step_cm="physical direction-integration step, cm",
)


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(
                f"Duplicate JSON key {key!r}: a later value would silently replace an earlier one"
            )
        result[key] = value
    return result


def load_json_config(source):
    """Load JSON text or a path; duplicate keys fail at every nesting level."""
    text = Path(source).read_text() if isinstance(source, Path) else source
    if not isinstance(text, str):
        raise TypeError("Expected JSON text or a pathlib.Path")
    return json.loads(text, object_pairs_hook=_reject_duplicate_keys)


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


def canonical_json(value):
    """Deterministic encoding for identity hashes; total over legacy objects.

    Schema-2/3 inputs are already finite. Legacy flat objects may carry
    unvalidated values; hashing them must never replace a native guard's error.
    """
    return json.dumps(_dump(value), sort_keys=True, separators=(",", ":"), allow_nan=True, default=_json_default)


def _json_default(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    return f"<{type(value).__module__}.{type(value).__qualname__}>{value!r}"


def sha256_json(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


@functools.lru_cache(maxsize=1)
def source_identity():
    """Hash of the installed generator source; binds run identity to code."""
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def environment_identity():
    import numpy

    return dict(python=platform.python_version(), numpy=numpy.__version__)


NATIVE_CONSTRUCTION_FIELDS = (
    "min_primary_length",
    "max_primary_length",
    "base_diameter",
    "diameter_reduction",
    "apex_diameter",
    "min_sec_root_num",
    "max_sec_root_num",
    "growth_sec_root",
    "min_sec_root_length",
    "max_sec_root_length",
    "segments_per_root",
    "length_reduction",
    "root_vary",
    "interbranch_distance",
)


@dataclass
class EngineLaws:
    """One active law per stage and order; ``None``/missing means native fallback.

    ``construction`` is ``native`` (native kernels with optional leaf
    replacements) or ``planned`` (every native construction law is replaced, so
    no native kernel or native draw remains). ``streams`` names the keyed
    stream policy; ``writer`` and ``view`` declare the identity allocation and
    the serialized result format of the input's contract.
    """

    construction: str = "native"
    pre: Optional[str] = None
    post: Optional[str] = None
    native_direction: Optional[str] = None
    direction: dict = field(default_factory=dict)
    lengths: dict = field(default_factory=dict)
    taper: dict = field(default_factory=dict)
    branching: dict = field(default_factory=dict)
    maturity: Optional[dict] = None
    cap: Optional[dict] = None
    origins: Optional[dict] = None
    relocation: Optional[dict] = None
    streams: str = "feature_keyed_v1"
    surface_z_cm: float = 0.0
    materialization: dict = field(
        default_factory=lambda: dict(rule="native_union_v1", corner_coincidence_cm=CORNER_COINCIDENCE_CM,
                                     reconcile_length_metadata=False)
    )
    writer: dict = field(default_factory=lambda: dict(first_node_id=0, records=False))
    view: str = "native"
    view_options: dict = field(default_factory=dict)

    def describe(self):
        return _dump(dict(self.__dict__))


@dataclass
class ResolvedConfig:
    """Engine input: one native parameter set plus one active law per stage/order."""

    source_schema: str
    config: Any
    parameters: Any
    seed: Optional[int]
    simulation_tag: Optional[str]
    laws: EngineLaws = field(default_factory=EngineLaws)
    limits: dict = field(default_factory=dict)
    description: dict = field(default_factory=dict)
    hashes: dict = field(default_factory=dict)
    requested_simulation_tag: Optional[str] = None
    # Tag the simulator adopts; None keeps the constructor's (historical cohort).
    simulator_tag: Optional[str] = None

    @property
    def direction_overrides(self):
        return self.laws.direction

    def run_identity(self, seed):
        """Effective model plus seed, generator source and numeric environment."""
        return sha256_json(
            dict(
                effective_model_sha256=self.hashes["effective_model_sha256"],
                seed=seed,
                source_sha256=source_identity(),
                environment=environment_identity(),
            )
        )


def _supplied_payload(spec):
    if isinstance(spec, (str, Path)):
        return load_json_config(spec)
    if isinstance(spec, dict):
        return copy.deepcopy(spec)
    if hasattr(spec, "model_dump"):
        return spec.model_dump()
    return None


def resolve_config(spec):
    """Parse if needed, choose laws, check dependencies, describe and hash."""
    supplied = _supplied_payload(spec)
    parsed = parse_config(spec)
    if isinstance(parsed, RootSimulationConfigV3):
        resolved = _resolve_v3(parsed)
    elif isinstance(parsed, RootSimulationConfig):
        resolved = _resolve_v2(parsed)
    else:
        resolved = _resolve_flat(parsed)
    resolved.hashes["supplied_input_sha256"] = sha256_json(supplied)
    resolved.description["hashes"] = dict(resolved.hashes)
    return resolved


def explain_config(spec):
    """Resolved description: active laws, inactive values, replaced fallbacks."""
    return resolve_config(spec).description


def _construction_step_controls(p):
    from ..utils.primary_attachment import FIELD as ATTACH_FIELD, validate_distal_fraction
    from ..utils.tertiary_length_rank import validate_rank_strength

    return (
        getattr(p, "research_current_length_grid", None) is not None
        or getattr(p, "research_parent2_branch_zone_cm", None) is not None
        or validate_rank_strength(getattr(p, "research_tertiary_length_rank_strength", None))
        or validate_distal_fraction(getattr(p, ATTACH_FIELD, None))
    )


LEGACY_ONLY_FIELDS = ("gravitropism", "no_root_zone")
FICHTL_ONLY_FIELDS = (
    "fichtl_probability_down",
    "fichtl_sigma",
    "fichtl_trials_type2",
    "fichtl_trials_type3",
    "fichtl_theta2_deg",
    "fichtl_theta2_sd_deg",
    "fichtl_theta3_deg",
    "fichtl_theta3_sd_deg",
)


def _research_active(name, value):
    """Whether a historical research control changes the run; no-ops are dormant."""
    from ..utils.primary_attachment import validate_distal_fraction
    from ..utils.tertiary_length_rank import validate_rank_strength
    from ..utils.tropism import row_axial_controls_active, validate_primary_yaw_reverse_probability

    if value is None:
        return False
    predicates = dict(
        research_branch_placement=lambda v: v != "legacy_spacing",
        research_tertiary_length_rank_strength=validate_rank_strength,
        research_primary_attachment_distal_fraction=validate_distal_fraction,
        research_primary_yaw_reverse_probability=validate_primary_yaw_reverse_probability,
        research_primary_inclination_bias=bool,
        research_insertion_row_axial_kappa=row_axial_controls_active,
    )
    try:
        return bool(predicates.get(name, lambda v: True)(value))
    except Exception:
        # Unvalidated legacy objects: keep the raw value; native guards reject it.
        return True


def _effective_native_parameters(p, laws):
    """Native values that can affect this run: active fallbacks and controls."""
    mode = getattr(p, "tropism_mode", "legacy")
    inactive = set(FICHTL_ONLY_FIELDS if mode == "legacy" else LEGACY_ONLY_FIELDS)
    if laws.construction == "planned":
        inactive |= set(NATIVE_CONSTRUCTION_FIELDS) | set(FICHTL_ONLY_FIELDS) | set(LEGACY_ONLY_FIELDS)
        inactive |= {"tropism_mode", "max_val_attempts", "floor_threshold", "ceiling_threshold"}
    values = {name: getattr(p, name, None) for name in EFFECTIVE_NATIVE_FIELDS if name not in inactive}
    for name in RESEARCH_ALIASES:
        value = getattr(p, name, None)
        if _research_active(name, value):
            values[name] = value.model_dump() if hasattr(value, "model_dump") else value
    return json.loads(canonical_json(values))


def _dump(value):
    if hasattr(value, "model_dump"):
        return _dump(value.model_dump())
    if isinstance(value, dict):
        return {str(k): _dump(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_dump(v) for v in value]
    return value


def _native_laws(p, **overrides):
    """Native fallbacks: the historical correction and direction laws by mode."""
    fichtl = getattr(p, "tropism_mode", "legacy") == "fichtl2024"
    laws = EngineLaws(
        pre="fichtl_primary_validation_repair_v1" if fichtl else None,
        post="fichtl_lateral_validation_check_v1" if fichtl else "legacy_validation_repair_v1",
        native_direction="fichtl_search_v1" if fichtl else "legacy_gravitropism_blend_v1",
        surface_z_cm=float(getattr(p, "soil_surface_z_cm", 0.0) or 0.0),
    )
    for key, value in overrides.items():
        setattr(laws, key, value)
    return laws


def _law_table(p, laws):
    """Per-order description of the active law for each stage."""
    cdfs = getattr(p, "research_current_length_cdfs_cm", None) or {}
    design = getattr(p, "research_primary_design", None) is not None
    planned = laws.construction == "planned"
    table = {}
    for order in range(1, int(p.max_order) + 1):
        if planned:
            dimensions = "replaced"
        elif order == 1:
            dimensions = "explicit_primary_design_v1" if design else "native_uniform_rank_sorted_v1"
        else:
            dimensions = "keyed_current_length_cdf_v1" if order in cdfs else "native_uniform_rank_sorted_inherited_v1"
        if order == 1:
            native_direction = "native_scaffold_v1"
        else:
            native_direction = (
                "native_fichtl_search_v1" if laws.native_direction == "fichtl_search_v1" else "native_scaffold_v1"
            )
        entry = dict(
            construction=laws.construction,
            dimensions=laws.lengths[order] if order in laws.lengths else dimensions,
            material=laws.taper[order] if order in laws.taper else "native_cylinder_per_construction_interval_v1",
            classification=(
                "per_segment_equivalent_diameter_v1"
                if order in laws.taper
                else ("primary_structural_v1" if order == 1 else "native_mean_cylinder_threshold_v1")
            ),
            branching=laws.branching[order] if order in laws.branching else ("none" if planned else "native"),
            direction=(
                dict(laws.direction[order], replaces=None if planned else native_direction)
                if order in laws.direction
                else native_direction
            ),
        )
        table[str(order)] = entry
    return dict(
        by_order=table,
        construction=laws.construction,
        corrections=dict(pre_direction=laws.pre, global_direction=laws.native_direction, post_direction=laws.post),
        maturity=laws.maturity,
        parent_diameter_cap=laws.cap,
        primary_origins=laws.origins,
        attachment_relocation=laws.relocation,
        streams=laws.streams,
        materialization=laws.materialization,
        writer=laws.writer,
        result_view=laws.view,
    )


def _describe(source_schema, p, seed, tag, laws, active, dormant, limits, contract=None):
    law_table = _law_table(p, laws)
    effective = _dump(
        dict(
            lifecycle_version=ENGINE_LIFECYCLE_VERSION,
            parameters=_effective_native_parameters(p, laws),
            laws=law_table,
            active_features=active,
            contract=contract,
        )
    )
    # Limits, labels and output locations never change a successful output, so
    # they are recorded in the description but excluded from model identity.
    description = _dump(
        dict(
            engine=dict(lifecycle_version=ENGINE_LIFECYCLE_VERSION, phases=list(ENGINE_PHASES)),
            source_schema=source_schema,
            seed=seed,
            simulation_tag=tag,
            parameters=effective["parameters"],
            laws=law_table,
            features=dict(active=active, inactive=dormant),
            contract=contract,
            units=UNITS,
            rng=dict(
                native="numpy default_rng(seed) sequential stream; historical draw order",
                native_schedule=(
                    "biology and placement draws are unchanged by direction-law replacements; a replaced "
                    "axis takes its historical correction draw but is only checked; later correction draws "
                    "can differ when a replaced axis changes which native axes stay valid (an invalid axis "
                    "draws nothing); a replaced construction law draws nothing natively"
                ),
                keyed_policy=laws.streams,
            ),
            limits=limits,
        )
    )
    return description, dict(effective_model_sha256=sha256_json(effective))


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
        contract=dict(cohort_v5=construction.model_dump(mode="json")),
    )
    return ResolvedConfig("2", config, p, config.random_seed, config.simulation_tag, laws, limits, description,
                          hashes, requested_simulation_tag=config.simulation_tag)


# ---------------------------------------------------------------------------
# Schema 3: features as leaf laws
# ---------------------------------------------------------------------------


def _number(value, name, low=None, high=None, low_open=False):
    if value is None:
        raise ValueError(f"{name} is required by the enabled feature")
    if low is not None and (value < low or (low_open and value == low)):
        raise ValueError(f"{name}={value} must be {'>' if low_open else '>='} {low}")
    if high is not None and value > high:
        raise ValueError(f"{name}={value} must be <= {high}")
    return float(value)


def _require_acceptance(mean, sd, low, high, minimum, name):
    """A truncated-normal rejection sampler must accept often enough to finish."""
    if sd == 0:
        return
    import math

    def cdf(x):
        return 0.5 * math.erfc(-(x - mean) / (sd * math.sqrt(2)))

    if cdf(high) - cdf(low) < minimum:
        raise ValueError(f"{name} accepts less than {minimum:.0%} of draws within [{low}, {high}]")


def _distribution(spec, name):
    from ..model.cohort_geometry import bounded_draw

    if spec is None:
        raise ValueError(f"{name} distribution is required by the enabled feature")
    values = {k: _number(getattr(spec, k), f"{name}.{k}") for k in ("mean", "sd", "min", "max")}
    import numpy as np

    bounded_draw(values, np.random.default_rng(0))  # validates support/acceptance
    return values


def _orders(settings, feature, max_order):
    keys = sorted(settings.by_order, key=int)
    if not keys:
        raise ValueError(f"Enabled {feature} requires at least one by_order entry")
    for key in keys:
        if int(key) > int(max_order):
            raise ValueError(f"{feature}.by_order[{key!r}] exceeds max_order {max_order}")
    return [(int(k), settings.by_order[k]) for k in keys]


def _resolve_curvature(settings, p):
    laws = {}
    for order, law in _orders(settings, "curvature", p.max_order):
        key = str(order)
        missing = [name for name in CURVATURE_REQUIRED if getattr(law, name) is None]
        if missing:
            raise ValueError(f"Enabled curvature.by_order[{key!r}] is incomplete; missing {missing}")
        step, q, ell, drift = (
            law.step_cm, law.curvature_sd_rad_cm, law.correlation_length_cm, law.downward_drift_per_cm
        )
        for name, value in (("step_cm", step), ("correlation_length_cm", ell), ("curvature_sd_rad_cm", q)):
            low, high = CURVATURE_BOUNDS[name]
            if not low <= value <= high:
                raise ValueError(
                    f"curvature.by_order[{key!r}].{name}={value} is outside the representable range "
                    f"[{low}, {high}]"
                )
        if drift < 0:
            raise ValueError(f"curvature.by_order[{key!r}] requires downward_drift_per_cm>=0")
        if step * drift >= 1:
            raise ValueError(f"curvature.by_order[{key!r}] requires step_cm*downward_drift_per_cm < 1")
        from ..model.curvature import ou_transition_coefficients

        ou_transition_coefficients(step, q, ell)  # finite at the largest interval
        heading = law.initial_heading or ("scaffold_chord" if order == 1 else None)
        if order > 1 and heading != "insertion_angle":
            raise ValueError(
                f"curvature.by_order[{key!r}] on a daughter order requires initial_heading='insertion_angle' "
                "with insertion_mean_deg and insertion_sd_deg"
            )
        if order == 1 and heading == "insertion_angle":
            raise ValueError("Primary curvature uses initial_heading 'scaffold_chord' or 'origin_heading'")
        entry = dict(
            law=CURVATURE_LAW, version=CURVATURE_LAW_VERSION, step_cm=float(step), curvature_sd_rad_cm=float(q),
            correlation_length_cm=float(ell), downward_drift_per_cm=float(drift), boundary=law.boundary,
            first_interval=law.first_interval, initial_heading=heading,
            surface_z_cm=float(p.soil_surface_z_cm), stream_namespace=CURVATURE_STREAM_NAMESPACE,
        )
        if heading == "insertion_angle":
            entry["insertion_mean_deg"] = _number(law.insertion_mean_deg, f"curvature[{key}].insertion_mean_deg", 0, 90)
            entry["insertion_sd_deg"] = _number(law.insertion_sd_deg, f"curvature[{key}].insertion_sd_deg", 0)
            # The insertion sampler has 1000 tries; 5% acceptance keeps exhaustion implausible.
            _require_acceptance(entry["insertion_mean_deg"], entry["insertion_sd_deg"], 0.0, 90.0, 0.05,
                                f"curvature[{key}] insertion law")
        laws[order] = entry
    return laws


def _resolve_taper(settings, p):
    laws = {}
    for order, law in _orders(settings, "taper", p.max_order):
        if law.law is None:
            raise ValueError(f"Enabled taper.by_order['{order}'] requires law")
        fraction = _number(law.midpoint_diameter_fraction, f"taper[{order}].midpoint_diameter_fraction", 0, 1, True)
        if fraction >= 1:
            raise ValueError("midpoint_diameter_fraction must lie in (0, 1)")
        laws[order] = dict(
            law=law.law, midpoint_diameter_fraction=fraction,
            base_cm=_distribution(law.base_cm, f"taper[{order}].base_cm"),
            tip_cm=_distribution(law.tip_cm, f"taper[{order}].tip_cm"),
        )
    return laws


def _resolve_lengths(settings, p):
    from ..utils.current_length import validate_current_length_cdf

    laws = {}
    for order, law in _orders(settings, "lengths", p.max_order):
        if law.law == "discrete_cdf":
            if law.lengths_cm is None or law.cumulative_probabilities is None:
                raise ValueError(f"lengths[{order}] discrete_cdf requires lengths_cm and cumulative_probabilities")
            validate_current_length_cdf(law.lengths_cm, law.cumulative_probabilities)
            laws[order] = dict(law="discrete_cdf", lengths_cm=list(law.lengths_cm),
                               cumulative_probabilities=list(law.cumulative_probabilities))
        elif law.law == "bounded_lognormal":
            values = {k: getattr(law, k) for k in ("mean", "sd", "min", "max")}
            laws[order] = dict(law="bounded_lognormal", **_distribution(_Spec(values), f"lengths[{order}]"))
        else:
            raise ValueError(f"Enabled lengths.by_order['{order}'] requires law")
    return laws


class _Spec:
    def __init__(self, values):
        self.__dict__.update(values)


def _resolve_branching(settings, p):
    import numpy as np

    laws = {}
    for order, law in _orders(settings, "branching", p.max_order):
        if law.law is None:
            raise ValueError(f"Enabled branching.by_order['{order}'] requires law")
        probability = _number(law.branch_probability, f"branching[{order}].branch_probability", 0, 1)
        weights = law.daughter_probabilities
        if not weights or any(w < 0 for w in weights) or not np.isclose(sum(weights), 1.0, rtol=0, atol=1e-12):
            raise ValueError(f"branching[{order}].daughter_probabilities must be nonnegative and sum to 1")
        laws[order] = dict(
            law=law.law, first_branch_cm=_distribution(law.first_branch_cm, f"branching[{order}].first_branch_cm"),
            branch_probability=probability, daughter_probabilities=list(weights),
        )
    return laws


def _resolve_origins(settings, p):
    surface = float(p.soil_surface_z_cm)
    if settings.layout == "disk":
        radius = _number(settings.radius_cm, "primary_origins.radius_cm", 0)
        depth = settings.depth_range_cm
        if not depth or len(depth) != 2 or not 0 <= depth[0] <= depth[1]:
            raise ValueError("primary_origins.depth_range_cm must be [min, max] with 0 <= min <= max")
        law = dict(layout="disk", radius_cm=radius, depth_range_cm=[float(depth[0]), float(depth[1])])
    elif settings.layout == "point":
        law = dict(layout="point", x_cm=_number(settings.x_cm, "primary_origins.x_cm"),
                   y_cm=_number(settings.y_cm, "primary_origins.y_cm"),
                   depth_cm=_number(settings.depth_cm, "primary_origins.depth_cm", 0))
    else:
        raise ValueError("Enabled primary_origins requires layout 'disk' or 'point'")
    if settings.heading is not None:
        heading = settings.heading
        if settings.layout != "disk" or heading.law != "radial_inclination":
            raise ValueError("primary_origins.heading 'radial_inclination' requires the disk layout")
        bounds = heading.inclination_bounds_deg
        if not bounds or len(bounds) != 2 or not -90 <= bounds[0] <= bounds[1] <= 90:
            raise ValueError("inclination_bounds_deg must be [low, high] within [-90, 90]")
        law["heading"] = dict(
            law="radial_inclination",
            inclination_mean_deg=_number(heading.inclination_mean_deg, "inclination_mean_deg", bounds[0], bounds[1]),
            inclination_sd_deg=_number(heading.inclination_sd_deg, "inclination_sd_deg", 0),
            inclination_bounds_deg=[float(bounds[0]), float(bounds[1])],
        )
        _require_acceptance(law["heading"]["inclination_mean_deg"], law["heading"]["inclination_sd_deg"],
                            bounds[0], bounds[1], 0.01, "Inclination law")
    law["surface_z_cm"] = surface
    return law


def _resolve_maturity(settings, p):
    primaries = int(p.outer_root_num) + int(p.inner_root_num)
    groups, seen = [], []
    for group in settings.groups or []:
        if not group.label or not group.primary_indices or not group.maturity_range:
            raise ValueError("Each maturity group requires label, primary_indices and maturity_range")
        low, high = group.maturity_range
        if not 0 < low <= high <= 1:
            raise ValueError("maturity_range must satisfy 0 < low <= high <= 1")
        seen.extend(group.primary_indices)
        groups.append(dict(label=group.label, primary_indices=list(group.primary_indices),
                           maturity_range=[float(low), float(high)], draw="fixed" if low == high else "uniform"))
    if sorted(seen) != list(range(primaries)):
        raise ValueError(f"Maturity groups must cover primary indices 0..{primaries - 1} exactly once")
    if settings.diameter_target not in (None, "base_anchor"):
        raise ValueError("Only diameter_target 'base_anchor' is supported")
    return dict(
        groups=groups, length_power=_number(settings.length_power, "cohort_maturity.length_power", 0),
        diameter_power=_number(settings.diameter_power, "cohort_maturity.diameter_power", 0),
        scale_branch_probability=bool(settings.scale_branch_probability),
        diameter_target="base_anchor",
    )


def _resolve_v3(config):
    p = config.parameters.model_copy(
        update=dict(random_seed=config.random_seed, simulation_tag=config.simulation_tag)
    )
    f = config.features
    active, dormant = {}, {}
    for name in FEATURE_NAMES:
        block = getattr(f, name)
        (active if block.enabled else dormant)[name] = block.settings.model_dump(exclude_none=True)
    laws = _native_laws(p)
    if f.curvature.enabled:
        laws.direction = _resolve_curvature(f.curvature.settings, p)
    if f.taper.enabled:
        laws.taper = _resolve_taper(f.taper.settings, p)
    if f.lengths.enabled:
        laws.lengths = _resolve_lengths(f.lengths.settings, p)
    if f.branching.enabled:
        laws.branching = _resolve_branching(f.branching.settings, p)
    if f.primary_origins.enabled:
        laws.origins = _resolve_origins(f.primary_origins.settings, p)
    if f.cohort_maturity.enabled:
        laws.maturity = _resolve_maturity(f.cohort_maturity.settings, p)
    if f.parent_diameter_cap.enabled:
        laws.cap = dict(fraction_max=_number(f.parent_diameter_cap.settings.fraction_max,
                                             "parent_diameter_cap.fraction_max", 0, 1, True))
    if f.attachment_relocation.enabled:
        s = f.attachment_relocation.settings
        if s.orders != [2] or s.preserve_sampled_daughter_dimensions is False:
            raise ValueError("attachment_relocation supports orders [2] with preserved sampled daughter dimensions")
        laws.relocation = dict(law="distal_fraction", distal_fraction=_number(s.distal_fraction, "distal_fraction", 0, 1, True))
    _check_supported_combinations(p, laws)
    cdfs = {order: law for order, law in laws.lengths.items() if law["law"] == "discrete_cdf"}
    if cdfs and laws.construction == "native":
        # One law, one implementation: the keyed current-length CDF kernel.
        from .simulation_data_models import CurrentLengthCDF

        p = p.model_copy(update=dict(research_current_length_cdfs_cm={
            order: CurrentLengthCDF(lengths_cm=law["lengths_cm"], cumulative_probabilities=law["cumulative_probabilities"])
            for order, law in cdfs.items()
        }))
    for name, law in (("curvature", laws.direction), ("taper", laws.taper), ("lengths", laws.lengths),
                      ("branching", laws.branching)):
        if law:
            active[name] = {"by_order": {str(k): v for k, v in law.items()}}
    for name, law in (("primary_origins", laws.origins), ("cohort_maturity", laws.maturity),
                      ("parent_diameter_cap", laws.cap), ("attachment_relocation", laws.relocation)):
        if law:
            active[name] = law
    limits = config.limits.model_dump(exclude_none=True)
    description, hashes = _describe("3", p, config.random_seed, config.simulation_tag, laws, active, dormant, limits)
    return ResolvedConfig("3", config, p, config.random_seed, config.simulation_tag, laws, limits,
                          description, hashes, requested_simulation_tag=config.simulation_tag,
                          simulator_tag=config.simulation_tag)


def _check_supported_combinations(p, laws):
    """Declared supported combinations; every other one fails before execution."""
    orders = set(range(1, int(p.max_order) + 1))
    if _fully_replaced(laws, orders):
        _configure_planned(p, laws)
        return
    _check_native_parameters(p, laws)
    _check_headings(laws)
    _check_direction_rules(p, laws)
    _check_material_rules(p, laws, orders)
    _check_relocation(p, laws)


def _fully_replaced(laws, orders):
    """Nothing native remains when every construction law is replaced."""
    return (
        set(laws.direction) == orders
        and set(laws.taper) == orders
        and set(laws.lengths) == orders
        and all(law["law"] == "bounded_lognormal" for law in laws.lengths.values())
        and orders - {max(orders)} <= set(laws.branching)
    )


def _configure_planned(p, laws):
    if int(p.outer_root_num) + int(p.inner_root_num) < 1:
        raise ValueError("Fully replaced construction requires at least one primary")
    laws.construction = "planned"
    laws.pre = laws.post = laws.native_direction = None
    laws.materialization = dict(rule="merged_material_cuts_v1", corner_coincidence_cm=CORNER_COINCIDENCE_CM,
                                reconcile_length_metadata=False,
                                cutoff_mm=float(p.fine_root_threshold) * 10.0, position_type="native_birth_group")
    if laws.origins is None or laws.origins["layout"] != "disk" or "heading" not in laws.origins:
        raise ValueError("Fully replaced construction requires disk primary_origins with a radial_inclination heading")
    if laws.direction[1]["initial_heading"] != "origin_heading":
        raise ValueError("Fully replaced construction requires primary curvature initial_heading 'origin_heading'")
    if laws.relocation is not None:
        raise ValueError("attachment_relocation requires native primary construction")


def _check_native_parameters(p, laws):
    if int(p.outer_root_num) < 1 or int(p.inner_root_num) < 1:
        raise ValueError("Native primary placement spaces each group around the base; "
                         "outer_root_num and inner_root_num must both be at least 1")
    missing = [name for name in NATIVE_CONSTRUCTION_FIELDS if getattr(p, name, None) is None]
    if laws.native_direction == "legacy_gravitropism_blend_v1" and getattr(p, "gravitropism", None) is None:
        missing.append("gravitropism")
    if missing:
        raise ValueError(f"Native construction laws still active; missing native parameters {missing}")


def _check_headings(laws):
    origin_heading = laws.origins is not None and "heading" in laws.origins
    if any(law["initial_heading"] == "origin_heading" for law in laws.direction.values()) and not origin_heading:
        raise ValueError("initial_heading 'origin_heading' requires primary_origins with a heading law")
    if origin_heading and 1 not in laws.direction:
        raise ValueError("A primary_origins heading law requires primary curvature to use it")


def _check_direction_rules(p, laws):
    if p.tropism_mode == "fichtl2024" or not laws.direction:
        return
    if set(laws.direction) != set(range(1, max(laws.direction) + 1)):
        raise ValueError(
            "Legacy fallback repairs native ancestors after realization; curvature orders must be a prefix 1..k"
        )
    if (p.no_root_zone or 0.0) < 0:
        raise ValueError(
            "Legacy validation with negative no_root_zone would rotate a correlated-curvature "
            "axis after realization; unsupported combination"
        )


def _check_material_rules(p, laws, orders):
    cdf_orders = [order for order, law in laws.lengths.items() if law["law"] == "discrete_cdf"]
    if 1 in cdf_orders or (cdf_orders and int(p.max_order) > 5):
        raise ValueError("Native discrete_cdf lengths support daughter orders 2..5 with max_order <= 5")
    maturity = laws.maturity
    if maturity is not None:
        if maturity["diameter_power"] and set(laws.taper) != orders:
            raise ValueError("Maturity diameter scaling requires point taper on every order (base anchor)")
        if maturity["scale_branch_probability"] and not orders - {max(orders)} <= set(laws.branching):
            raise ValueError("Maturity branch-probability scaling requires the probability branching law")
        if cdf_orders:
            raise ValueError("Maturity length scaling is not defined for discrete_cdf lengths")
    if laws.cap is not None:
        if set(laws.taper) != orders:
            raise ValueError("parent_diameter_cap requires point taper on every order")
        if laws.relocation is not None:
            raise ValueError("parent_diameter_cap with attachment_relocation is unsupported (cap site may move)")


def _check_relocation(p, laws):
    if laws.relocation is None:
        return
    if int(p.max_order) < 2:
        raise ValueError("attachment_relocation requires max_order >= 2")
    if p.tropism_mode != "fichtl2024" and 2 not in laws.direction:
        raise ValueError("attachment_relocation requires daughters realized from the final attachment "
                         "(fichtl2024 fallback or curvature on order 2)")
