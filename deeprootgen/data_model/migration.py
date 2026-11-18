"""Explicit, offline conversion of inventoried generation inputs to schema 4."""

from copy import deepcopy

from .execution import RootSimulationConfig
from .features import NOT_CONSUMED_BY_STATIC_RUN, OBSERVATION_SETTINGS, RootSimulationConfigV3
from .native_options import OWNERS
from .simulation_data_models import RootSimulationModel


def _block(features, feature, **settings):
    features.setdefault(feature, {"enabled": True, "settings": {}})["settings"].update(settings)


def _native_features(p):
    features = {}
    for owner, names in OWNERS.items():
        for target, source in names.items():
            value = p.pop(source, None)
            if value is not None:
                _block(features, owner, **{target: value})
    lengths = p.pop("research_current_length_cdfs_cm", None)
    if lengths:
        _block(features, "lengths", by_order={
            str(k): {"law": "discrete_cdf", **v} for k, v in lengths.items()
        })
    grid = p.pop("research_current_length_grid", None)
    if grid:
        _block(features, "direction", stationing=grid, primary_correction="frozen_surface_check",
               post_correction="pure_surface_check")
    distal = p.pop("research_primary_attachment_distal_fraction", None)
    if distal:
        _block(features, "attachment_relocation", orders=[2], distal_fraction=distal,
               preserve_sampled_daughter_dimensions=True)
    x = p.pop("research_base_origin_x_cm", None)
    y = p.pop("research_base_origin_y_cm", None)
    depth = p.pop("research_base_depth_cm", None)
    if depth is not None:
        _block(features, "primary_origins", layout="point", x_cm=x, y_cm=y, depth_cm=depth)
    return features


def _parameters(p):
    for field in (*NOT_CONSUMED_BY_STATIC_RUN, *OBSERVATION_SETTINGS, "random_seed", "simulation_tag"):
        p.pop(field, None)
    outer, inner = p.pop("outer_root_num"), p.pop("inner_root_num")
    count = outer + inner
    if count <= 0:
        raise ValueError("A primary population requires a positive total")
    p.update(primary_root_count=count, outer_primary_fraction=outer / count, min_branching_diameter_cm=0.0)
    for source, target in [
        ("fine_root_threshold", "threshold_root_diameter_cm"),
        ("growth_sec_root", "daughter_count_order_gain"),
        ("min_sec_root_length", "min_lateral_length"),
        ("max_sec_root_length", "max_lateral_length"),
    ]:
        if source in p:
            p[target] = p.pop(source)
    if "min_sec_root_num" in p or "max_sec_root_num" in p:
        if "min_sec_root_num" not in p or "max_sec_root_num" not in p:
            raise ValueError("Migration requires both bounds for requested daughters")
        lo, hi = sorted((p.pop("min_sec_root_num"), p.pop("max_sec_root_num")))
        p["daughters_per_parent"] = lo if lo == hi else {"min": lo, "max_exclusive": hi}
    return p


def _cohort(spec):
    """Use the historical validated leaf mappings, then enter ordinary schema 4."""
    from ..archive.resolution import _resolve_cohort_v5

    c = spec.construction.parameters
    if c.crown_mass_g or c.unrepresented_fine_mass_g:
        raise ValueError("Preserve crown and unrepresented fine mass as separate observation compartments")
    resolved = _resolve_cohort_v5(spec)
    laws = resolved.laws
    features = {}
    for feature in ("lengths", "taper", "branching"):
        _block(features, feature, by_order={str(k): v for k, v in getattr(laws, feature).items()})
    curves = {}
    for k, rule in laws.direction.items():
        curves[str(k)] = {n: v for n, v in rule.items() if n not in {"version", "surface_z_cm"}
                          and (k != 1 or n not in {"insertion_mean_deg", "insertion_sd_deg"})}
    _block(features, "curvature", by_order=curves)
    _block(features, "direction", post_correction="pure_surface_check")
    _block(features, "primary_origins", **{k: v for k, v in laws.origins.items() if k != "surface_z_cm"})
    maturity = deepcopy(laws.maturity)
    maturity["groups"] = [g for g in maturity["groups"] if g["primary_indices"]]
    for g in maturity["groups"]:
        del g["draw"]
    _block(features, "cohort_maturity", **maturity)
    _block(features, "parent_diameter_cap", **laws.cap)
    if c.reconcile_length_metadata:
        _block(features, "materialization", reconcile_length_metadata=True)
    p = resolved.parameters.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    return dict(schema_version=4, random_seed=spec.random_seed, simulation_tag=spec.simulation_tag,
                parameters=_parameters(p), features=features, limits={"max_organs": c.max_organs})


def convert_input(spec):
    """Convert a generation document. Returns new data and never changes the input.

    Observation values belong with the observation request. Callers converting
    an enabled soil display must extract those values separately first.
    """
    from .canonical import RootConfig

    d = deepcopy(spec)
    if not isinstance(d, dict):
        raise TypeError("Expected a generation document")
    version = d.get("schema_version")
    if "schema_version" in d and type(version) is not int:
        raise ValueError("schema_version must be an integer")
    limits = {}
    if version == 4:
        result = d
    elif version == 2 and d.get("construction", {}).get("kind") == "cohort":
        result = _cohort(RootSimulationConfig.model_validate(d))
    else:
        if version == 3:
            RootSimulationConfigV3.model_validate(d)
            params, features = d["parameters"], d.get("features", {})
            seed, tag, limits = d["random_seed"], d.get("simulation_tag", "default"), d.get("limits", {})
        elif version in (None, 2):
            if version == 2:
                old = RootSimulationConfig.model_validate(d)
                params = old.construction.parameters.model_dump(mode="json", exclude_unset=True, exclude_none=True)
                seed, tag = old.random_seed, old.simulation_tag
            else:
                unknown = d.keys() - RootSimulationModel.model_fields.keys()
                if unknown:
                    raise ValueError(f"Unmapped generation fields: {sorted(unknown)}")
                old = RootSimulationModel.model_validate(d)
                params = old.model_dump(mode="json", exclude_unset=True, exclude_none=True)
                seed, tag = old.random_seed, old.simulation_tag
            if params.get("enable_soil") or all(
                params.get(k, 0) for k in OBSERVATION_SETTINGS if k != "enable_soil"
            ):
                raise ValueError("Move enabled soil settings to the observation request before conversion")
            features = _native_features(params)
        else:
            raise ValueError(f"Unsupported source schema version {version}")
        result = dict(schema_version=4, random_seed=seed, simulation_tag=tag,
                      parameters=_parameters(params), features=features, limits=limits)
    RootConfig.model_validate(result)
    return result
