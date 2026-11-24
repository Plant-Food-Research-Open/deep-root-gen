"""Resolve one public root configuration into per-order native calculations."""

import copy
import hashlib
import json
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .canonical import RootConfig
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
)
from .simulation_data_models import RootSimulationModel

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
    row_alignment_per_cm="symmetric heading alignment toward model ±y, 1/cm",
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
    """Read a canonical root-system configuration, checking nested model mutations."""
    if isinstance(spec, (str, Path)):
        spec = load_json_config(spec)
    if isinstance(spec, RootConfig):
        spec = spec.model_dump()
    if not isinstance(spec, dict) or spec.get("schema_version") != 4:
        raise ValueError("Fresh generation requires schema_version 4. Convert older inputs with the offline migration utility.")
    return RootConfig.model_validate(spec)


def canonical_input(config):
    return config.model_dump(mode="json", exclude_unset=True)


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


def source_identity():
    """Current on-disk generator hash (not loaded-code authentication)."""
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
        """Seeded model signature only; realized identities also need run-start state."""
        if seed is None:
            raise ValueError("An unseeded model signature cannot identify a realized execution")
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


def _keyed_features(laws):
    """Active calculations that obtain an axis-keyed generator."""
    if laws.direction:
        yield "direction"
    if laws.origins is not None and laws.origins["layout"] == "disk":
        yield "primary_origins"
    if laws.origins is not None and laws.origins["layout"] == "vine_catalogue" and laws.origins["selection"]["mode"] == "sample":
        yield "primary_origins.vine_catalogue"
    if laws.maturity is not None:
        yield "cohort_maturity"
    if laws.branching:
        yield "branching"
    if any(rule["law"] == "discrete_cdf" or rule.get("sd", 0) > 0 for rule in laws.lengths.values()):
        yield "lengths"
    if any(rule[key]["sd"] > 0 for rule in laws.taper.values() for key in ("base_cm", "tip_cm")):
        yield "taper"


def _active_settings(p, irrigation, placement, transfer, floor):
    settings = {"daughters_by_parent_order": p.daughters_by_parent_order}
    if hasattr(p.root_tissue_density, "bounds_mm"):
        settings["tissue_density_by_diameter"] = p.root_tissue_density.model_dump()
    if p.max_order > 1:
        settings["min_branching_diameter_cm"] = p.min_branching_diameter_cm
    if p.allocation_controls is not None:
        settings["allocation"] = dict(root_ratio_biomass=p.root_ratio_biomass, root_ratio_length=p.root_ratio_length,
                                      controls=p.allocation_controls.model_dump())
    if irrigation is not None and irrigation.peak_multiplier > 1:
        settings["irrigation"] = irrigation.model_dump(exclude_none=True)
    if placement is not None and (placement.strength or placement.mode == "retention"):
        settings["daughter_placement"] = placement.model_dump(exclude_none=True)
    if transfer is not None and transfer.transfer_probability:
        settings["birth_depth_transfer"] = dict(transfer.model_dump(), parent_orders=sorted(transfer.parent_orders))
    if floor is not None:
        settings["minimum_realized_primary_length_cm"] = floor
    return settings


def _validate_birth_depth_transfer(parsed, resolved, settings, transfer):
    p, irrigation, placement = parsed.parameters, parsed.irrigation, parsed.daughter_placement
    if parsed.random_seed is None:
        raise ValueError("Birth depth transfer requires an explicit random_seed")
    for order in transfer.parent_orders:
        parent = resolved.laws.direction.get(order, {})
        daughter = resolved.laws.direction.get(order + 1, {})
        if (order >= p.max_order or order not in resolved.laws.branching
                or parent.get("law") != "correlated_curvature"
                or daughter.get("initial_heading") != "insertion_angle"
                or daughter.get("law") != "correlated_curvature"):
            raise ValueError("Birth depth transfer requires ordinary branching, a realized curved parent "
                             "and an insertion-angle daughter at each selected order")
        if ((order == 1 and resolved.laws.relocation is not None)
                or ("irrigation" in settings and order == irrigation.parent_order)
                or ("daughter_placement" in settings and placement.mode != "surface_bearing"
                    and order == placement.parent_order)):
            raise ValueError("Conflicting attachment controls on the birth depth transfer parent order")
    resolved.description["birth_depth_transfer"] = settings["birth_depth_transfer"]


def _apply_primary_length_floor(p, resolved, floor):
    primary = resolved.laws.lengths.get(1, {})
    if primary.get("law") != "bounded_lognormal" or not primary.get("sd") or p.allocation_controls is not None:
        raise ValueError("A realized primary floor requires a stochastic lognormal length law without allocation")
    primary["realized_floor_cm"] = floor
    resolved.description["minimum_realized_primary_length_cm"] = floor


def _validate_daughter_placement(parsed, resolved, settings, placement):
    p = parsed.parameters
    if placement.mode == "surface_bearing":
        if parsed.random_seed is None:
            raise ValueError("Surface bearing requires an explicit random_seed")
        for order in placement.bearing_orders:
            law = resolved.laws.direction.get(order, {})
            if law.get("law") != "correlated_curvature" or law.get("initial_heading") != "insertion_angle":
                raise ValueError(f"Surface bearing requires correlated curvature with insertion_angle on order {order}")
            if "sibling_sectors" in law or law.get("row_axial_kappa", 0.) > 0:
                raise ValueError(f"Surface bearing conflicts with sibling sectors or row-axial insertion on order {order}")
        resolved.description["daughter_placement"] = settings["daughter_placement"]
    else:
        order = placement.parent_order
        parent = resolved.laws.direction.get(order, {})
        daughter = resolved.laws.direction.get(order + 1, {})
        if (order + 1 != p.max_order or parsed.random_seed is None
                or order not in resolved.laws.branching
                or parent.get("law") != "correlated_curvature"
                or daughter.get("law") != "correlated_curvature"
                or daughter.get("initial_heading") != "insertion_angle"):
            raise ValueError("Daughter placement requires seeded curved terminal parents and insertion-angle daughters")
        if "irrigation" in settings:
            raise ValueError("Rainfed daughter placement and active irrigation cannot be combined")
        if p.min_branching_diameter_cm < 0.093 or order + 1 not in resolved.laws.taper:
            raise ValueError("Daughter placement requires a parent diameter gate of at least 0.093 cm and terminal point taper")
        if ((placement.mode.startswith("branch_probability") or placement.mode.startswith("sparse_"))
                and resolved.laws.branching[order]["law"] != "first_branch_and_daughter_count"):
            raise ValueError("A branching probability preference requires the first-site daughter-count law")
        if placement.mode.startswith("sparse_") and resolved.laws.branching[order]["branch_probability"] != 0:
            raise ValueError("Sparse recruitment requires an inactive ordinary terminal branch law")
        resolved.description["daughter_placement"] = settings["daughter_placement"]


def _validate_irrigation(parsed, resolved, settings, irrigation):
    p = parsed.parameters
    order = irrigation.parent_order
    if order + 1 != p.max_order or parsed.random_seed is None:
        raise ValueError("Irrigation requires a seeded terminal daughter order")
    if order not in resolved.laws.branching or p.daughters_by_parent_order.get(str(order)) is not None or getattr(resolved.parameters, "research_root_counts_by_order", None):
        raise ValueError("Irrigation requires a stochastic branching law without an exact daughter quota")
    parent = resolved.laws.direction.get(order, {})
    daughter = resolved.laws.direction.get(order + 1, {})
    if parent.get("law") != "correlated_curvature" or daughter.get("initial_heading") != "insertion_angle":
        raise ValueError("Irrigation requires realized parent curvature and terminal insertion-angle curvature")
    if order == 1 and resolved.laws.relocation is not None:
        raise ValueError("Irrigation of relocated primary sites is outside the terminal-order pilot")
    resolved.description["irrigation"] = settings["irrigation"]


def resolve_config(spec):
    """Resolve a schema-4 input against the shared native construction kernels."""
    from .consumers import spatial_feature_consumers

    parsed = parse_config(spec)
    p = parsed.parameters
    irrigation, placement = parsed.irrigation, parsed.daughter_placement
    transfer, floor = parsed.birth_depth_transfer, parsed.minimum_realized_primary_length_cm
    settings = _active_settings(p, irrigation, placement, transfer, floor)
    resolved = _resolve_features(parsed, p.kernel_parameters(), "4", contract=settings)
    if "birth_depth_transfer" in settings:
        _validate_birth_depth_transfer(parsed, resolved, settings, transfer)
    if floor is not None:
        _apply_primary_length_floor(p, resolved, floor)
    if "daughter_placement" in settings:
        _validate_daughter_placement(parsed, resolved, settings, placement)
    if "irrigation" in settings:
        _validate_irrigation(parsed, resolved, settings, irrigation)
    if parsed.random_seed is None:
        keyed = list(_keyed_features(resolved.laws))
        if keyed:
            raise ValueError(f"An explicit random_seed is required for keyed calculations: {keyed}")
    consumers = resolved.description["consumers"]
    consumers.update(spatial_feature_consumers(resolved.laws))
    nonterminal = list(range(1, p.max_order))
    consumers["min_branching_diameter_cm"] = dict(
        operation="daughter eligibility at the final attachment", units="cm",
        orders=nonterminal, status="active" if nonterminal and p.min_branching_diameter_cm else "inactive",
    )
    consumers["threshold_root_diameter_cm"] = dict(
        operation="diameter-class length, dry biomass and achieved fractions", units="cm",
        orders=list(range(1, p.max_order + 1)), status="active",
    )
    for name in ("root_ratio_length", "root_ratio_biomass"):
        consumers[name] = dict(operation="architecture allocation", units="fraction",
                               status="active" if getattr(p, name) is not None else "inactive")
    resolved.hashes["supplied_input_sha256"] = sha256_json(_supplied_payload(spec))
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
    from .consumers import parameter_consumers

    consumers = parameter_consumers(p, laws)
    inactive |= {name for name, item in consumers.items() if item["status"] != "active"}
    values = {name: getattr(p, name, None) for name in EFFECTIVE_NATIVE_FIELDS if name not in inactive}
    if laws.construction != "planned":
        values["segments_per_root"] = p.segments_per_root or 1
        if "root_vary" in values and values["root_vary"] is None:
            values["root_vary"] = 0.0
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
    from .consumers import parameter_consumers

    law_table = _law_table(p, laws)
    effective = _dump(
        dict(
            lifecycle_version=ENGINE_LIFECYCLE_VERSION,
            parameters=_effective_native_parameters(p, laws),
            laws=law_table,
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
            consumers=parameter_consumers(p, laws),
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
    if source_schema == "4":
        description["rng"].update(
            native="numpy default_rng(seed), sequential native kernels",
            native_schedule="schema4: draw from selected dimension laws and construction partitions",
        )
    return description, dict(effective_model_sha256=sha256_json(effective))


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
    if isinstance(spec, (int, float)):
        value = _number(spec, name, low=0, low_open=True)
        return dict(mean=value, sd=0., min=value, max=value)
    values = {k: _number(getattr(spec, k), f"{name}.{k}") for k in ("mean", "sd", "min", "max")}
    if getattr(spec, "law", None) == "truncated_normal":
        values["law"] = "truncated_normal"
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
        if order == 1 and (law.insertion_mean_deg is not None or law.insertion_sd_deg is not None):
            raise ValueError("Primary curvature has no insertion-angle consumer")
        if order == 1 and heading == "insertion_angle":
            raise ValueError("Primary curvature uses initial_heading 'scaffold_chord' or 'origin_heading'")
        entry = dict(
            law=CURVATURE_LAW, version=CURVATURE_LAW_VERSION, step_cm=float(step), curvature_sd_rad_cm=float(q),
            correlation_length_cm=float(ell), downward_drift_per_cm=float(drift), boundary=law.boundary,
            first_interval=law.first_interval, initial_heading=heading,
            surface_z_cm=float(p.soil_surface_z_cm), stream_namespace=CURVATURE_STREAM_NAMESPACE,
        )
        strength = getattr(law, "row_alignment_per_cm", 0.0)
        sectors = getattr(law, "sibling_sectors", None)
        if sectors is not None:
            if heading != "insertion_angle":
                raise ValueError("sibling_sectors requires lateral insertion_angle")
            if sectors.fraction:
                entry["sibling_sectors"] = sectors.model_dump(exclude_none=True)
        carrier = getattr(law, "deep_carrier", None)
        if carrier is not None and carrier.fraction:
            if order == 1 or step * drift * carrier.drift_multiplier >= 1:
                raise ValueError("Deep carrier requires a lateral order and step times amplified drift below one")
            entry["deep_carrier"] = carrier.model_dump()
        if strength:
            from ..model.row_alignment import ROW_AXIS, ROW_ALIGNMENT_LAW, check_alignment_step

            check_alignment_step(strength, step)
            entry["row_alignment"] = dict(law=ROW_ALIGNMENT_LAW, row_alignment_per_cm=strength, axis=list(ROW_AXIS))
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
        if law.law == "exponential_above_diameter":
            laws[order].update(rate_per_cm=law.rate_per_cm, thick_min_cm=law.thick_min_cm)
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
    from ..model.branching_laws import LENGTH_POISSON_LAW, LENGTH_POISSON_STREAM, LENGTH_POISSON_VERSION

    laws = {}
    for order, law in _orders(settings, "branching", p.max_order):
        if law.law is None:
            raise ValueError(f"Enabled branching.by_order['{order}'] requires law")
        if law.law == LENGTH_POISSON_LAW:
            laws[order] = dict(law.model_dump(), stream_namespace=LENGTH_POISSON_STREAM, version=LENGTH_POISSON_VERSION)
            continue
        probability = _number(law.branch_probability, f"branching[{order}].branch_probability", 0, 1)
        weights = law.daughter_probabilities
        if not weights or any(w < 0 for w in weights) or not np.isclose(sum(weights), 1.0, rtol=0, atol=1e-12):
            raise ValueError(f"branching[{order}].daughter_probabilities must be nonnegative and sum to 1")
        laws[order] = dict(
            law=law.law, first_branch_cm=_distribution(law.first_branch_cm, f"branching[{order}].first_branch_cm"),
            branch_probability=probability, daughter_probabilities=list(weights),
        )
        if getattr(law, "stratify_distal_sites", False):
            laws[order]["stratify_distal_sites"] = True
    return laws


def _resolve_origins(settings, p):
    surface = float(p.soil_surface_z_cm)
    if settings.layout == "vine_catalogue":
        from ..model.vine_origins import resolve_vine_origins

        return resolve_vine_origins(settings, p.outer_root_num + p.inner_root_num, surface)
    supplied = settings.model_dump(exclude_none=True)
    foreign = ({"x_cm", "y_cm", "depth_cm"} if settings.layout == "disk" else
               {"radius_cm", "depth_range_cm", "heading"}) & set(supplied)
    if foreign:
        raise ValueError(f"primary_origins layout {settings.layout} does not consume {sorted(foreign)}")
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


def _resolve_features(config, parameters, version, contract=None):
    p = parameters.model_copy(
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
        if version == "4" and p.max_order in laws.branching:
            terminal = str(p.max_order)
            laws.branching.pop(p.max_order)
            settings = active["branching"]["by_order"]
            dormant["branching"] = {"by_order": {terminal: settings.pop(terminal)}}
            if not settings:
                active.pop("branching")
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
    from .native_options import resolve_native_options

    p = resolve_native_options(f, p, laws)
    _check_supported_combinations(p, laws)
    p = p.model_copy(update=dict(root_vary=0.0 if p.root_vary is None else p.root_vary,
                                 segments_per_root=p.segments_per_root or 1))
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
    limits = _execution_limits(config, laws)
    description, hashes = _describe(version, p, config.random_seed, config.simulation_tag, laws, active, dormant, limits, contract)
    return ResolvedConfig(version, config, p, config.random_seed, config.simulation_tag, laws, limits,
                          description, hashes, requested_simulation_tag=config.simulation_tag,
                          simulator_tag=config.simulation_tag)


def _execution_limits(config, laws):
    from ..model.budget import DEFAULT_MAX_BRANCH_PROPOSALS

    limits = config.limits.model_dump(exclude_none=True)
    if _poisson_orders(laws):
        limits.setdefault("max_branch_proposals", DEFAULT_MAX_BRANCH_PROPOSALS)
    return limits


def _check_supported_combinations(p, laws):
    """Declared supported combinations; every other one fails before execution."""
    orders = set(range(1, int(p.max_order) + 1))
    _check_native_parameters(p, laws)
    _check_headings(laws)
    _check_direction_rules(p, laws)
    _check_material_rules(p, laws, orders)
    _check_relocation(p, laws)
    _check_poisson_ownership(laws)


def _poisson_orders(laws):
    from ..model.branching_laws import LENGTH_POISSON_LAW

    return {order for order, law in laws.branching.items() if law["law"] == LENGTH_POISSON_LAW}


def _check_poisson_ownership(laws):
    orders = _poisson_orders(laws)
    if orders and laws.maturity is not None and laws.maturity["scale_branch_probability"]:
        raise ValueError("length_poisson_sites_v1 conflicts with maturity-scaled branch probability")
    if 1 in orders and laws.relocation is not None:
        raise ValueError("length_poisson_sites_v1 on parent order 1 conflicts with order-2 attachment relocation")


def _check_native_parameters(p, laws):
    if not getattr(p, "canonical_generation", False) and min(p.outer_root_num, p.inner_root_num) < 1:
        raise ValueError("Native primary placement spaces each group around the base; "
                         "outer_root_num and inner_root_num must both be at least 1")
    from .consumers import parameter_consumers

    consumers = parameter_consumers(p, laws)
    missing = [name for name, consumer in consumers.items()
               if consumer["required"] and getattr(p, name, None) is None]
    needs_partition = (any(k not in laws.lengths for k in range(1, p.max_order + 1))
                       or any(k not in laws.taper for k in range(1, p.max_order + 1)))
    if p.segments_per_root is None and needs_partition:
        missing.append("segments_per_root")
    if (laws.native_direction == "legacy_gravitropism_blend_v1"
            and set(range(1, p.max_order + 1)) - set(laws.direction)
            and getattr(p, "gravitropism", None) is None):
        missing.append("gravitropism")
    if missing:
        raise ValueError(f"Native construction laws still active; missing native parameters {missing}")


def _check_headings(laws):
    origin_heading = laws.origins is not None and ("heading" in laws.origins or laws.origins.get("measured_headings", False))
    if any(law.get("initial_heading") == "origin_heading" for law in laws.direction.values()) and not origin_heading:
        raise ValueError("initial_heading 'origin_heading' requires primary_origins with a heading law")
    if origin_heading and laws.direction.get(1, {}).get("initial_heading") != "origin_heading":
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
        if laws.relocation is not None and not getattr(p, "canonical_generation", False):
            raise ValueError("parent_diameter_cap with attachment_relocation is unsupported (cap site may move)")


def _check_relocation(p, laws):
    if laws.relocation is None:
        return
    if int(p.max_order) < 2:
        raise ValueError("attachment_relocation requires max_order >= 2")
    if p.tropism_mode != "fichtl2024" and 2 not in laws.direction:
        raise ValueError("attachment_relocation requires daughters realized from the final attachment "
                         "(fichtl2024 fallback or curvature on order 2)")
