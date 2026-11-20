"""Bounded whole-root search on one canonical architecture and shared seeds."""
import copy
import csv
import hashlib
import json
from pathlib import Path
from time import monotonic
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from scipy.stats import qmc

from ..data_model.canonical import RootConfig
from ..data_model.resolution import canonical_input, resolve_config
from ..form.optimisation import SCALAR_STATISTICS
from ..model import RootSystemSimulation
from ..statistics import get_summary_statistic_func
from .parameter_search import _atomic_json, run_parameter_search


_COMMON = {
    "primary_root_count": ("Primary root count", "roots", "int"),
    "outer_primary_fraction": ("Outer primary fraction", "fraction", "float"),
}
_FALLBACK = {
    "min_primary_length": ("Primary length minimum", "cm"),
    "max_primary_length": ("Primary length maximum", "cm"),
    "min_lateral_length": ("Lateral length minimum", "cm"),
    "max_lateral_length": ("Lateral length maximum", "cm"),
    "gravitropism": ("Legacy downward bias", "fraction"),
    "length_reduction": ("Lateral length reduction", "fraction"),
    "interbranch_distance": ("Native attachment spacing", "cm"),
    "min_branching_diameter_cm": ("Minimum diameter at attachment", "cm"),
    "base_diameter": ("Native base diameter", "cm"),
    "apex_diameter": ("Native endpoint diameter", "cm"),
    "diameter_reduction": ("Native diameter reduction", "fraction"),
}
_NATIVE_NAMES = {"min_lateral_length": "min_sec_root_length", "max_lateral_length": "max_sec_root_length"}
_REPLACEMENTS = {
    "curvature": {"downward_drift_per_cm": ("Downward drift", "per cm"),
                  "row_alignment_per_cm": ("Row alignment", "per cm"),
                  "curvature_sd_rad_cm": ("Curvature variability", "rad per cm"),
                  "correlation_length_cm": ("Curvature correlation length", "cm")},
    "lengths": {"mean": ("Length distribution mean", "cm")},
    "branching": {"branch_probability": ("Parent branching probability", "fraction"),
                  "mean_spacing_cm": ("Mean Poisson attachment spacing", "cm")},
}


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    statistic_name: str
    statistic_value: float = Field(ge=0)
    scale: float | None = Field(default=None, gt=0)


class Range(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    control: str
    lower: float
    upper: float


class ArchitectureSearch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base: RootConfig
    ranges: list[Range] = Field(min_length=1, max_length=6)
    targets: list[Target] = Field(min_length=1, max_length=13)
    metric: str = Field(pattern="^(mae|rmse)$")
    method: Literal["tpe", "latin_hypercube"] = "tpe"
    trials: int = Field(ge=2, le=60)
    startup: int = Field(ge=1, le=30)
    seeds: list[int] = Field(min_length=1, max_length=4)


def _replacement_controls(supplied, max_order):
    """Extract scalar values owned by a configured per-order replacement law."""
    controls = {}
    for feature, names in _REPLACEMENTS.items():
        section = supplied.get("features", {}).get(feature, {})
        if not section.get("enabled"):
            continue
        orders = section["settings"].get("by_order", {})
        for order, settings in orders.items():
            if not isinstance(settings, dict):
                continue  # Fixed numeric dimensions have no search distribution.
            if feature == "branching" and int(order) >= max_order:
                continue
            for field, (label, unit) in names.items():
                value = settings.get(field)
                if type(value) in (int, float):
                    name = f"{feature}_{order}_{field}"
                    controls[name] = dict(label=f"{label} · order {order}", unit=unit, kind="float",
                                          path=("features", feature, "settings", "by_order", order, field),
                                          value=value)
    return controls


def describe_controls(base):
    resolved = resolve_config(base)
    supplied = canonical_input(resolved.config)
    parameters = supplied["parameters"]
    description = resolved.description
    controls = {}
    for name, (label, unit, kind) in _COMMON.items():
        origins = description["laws"].get("primary_origins") or {}
        plac = supplied.get("features", {}).get("primary_placement", {})
        if origins.get("layout") == "vine_catalogue" or (
                plac.get("enabled") and plac.get("settings", {}).get("explicit_design")):
            continue
        controls[name] = dict(label=label, unit=unit, kind=kind, path=("parameters", name),
                              value=parameters.get(name, getattr(resolved.config.parameters, name)))
    for name, (label, unit) in _FALLBACK.items():
        consumer = description["consumers"].get(_NATIVE_NAMES.get(name, name), {})
        if consumer.get("status") == "active" and parameters.get(name) is not None:
            suffix = ", ".join(str(o) for o in consumer["orders"])
            controls[name] = dict(label=f"{label} · order {suffix}", unit=unit, kind="float",
                                  path=("parameters", name), value=parameters[name])
    controls.update(_replacement_controls(supplied, parameters["max_order"]))
    taper = supplied.get("features", {}).get("taper", {})
    if taper.get("enabled"):
        for order, settings in taper["settings"].get("by_order", {}).items():
            for field, text in (("base_cm", "Basal"), ("tip_cm", "Tip")):
                distribution = settings.get(field)
                if isinstance(distribution, dict) and type(distribution.get("mean")) in (int, float):
                    controls[f"taper_{order}_{field}_mean"] = dict(
                        label=f"{text} diameter mean · order {order}", unit="cm", kind="float",
                        path=("features", "taper", "settings", "by_order", order, field, "mean"),
                        value=distribution["mean"],
                    )
    for group, field, label, unit in (
        ("daughter_placement", "strength", "Daughter placement strength", "fraction"),
        ("irrigation", "peak_multiplier", "Irrigation multiplier", "ratio"),
        ("birth_depth_transfer", "transfer_probability", "Birth depth transfer", "fraction"),
    ):
        if group not in description:
            continue
        value = (supplied.get(group) or {}).get(field)
        if type(value) in (int, float):
            controls[f"{group}_{field}"] = dict(label=label, unit=unit, kind="float", path=(group, field), value=value)
    return supplied, controls, description


def _candidate(base, controls, values):
    result = copy.deepcopy(base)
    for name, value in values.items():
        *path, key = controls[name]["path"]
        section = result
        for element in path:
            section = section[element]
        section[key] = value
    return result


def validate_architecture_search(request):
    job = ArchitectureSearch.model_validate(request)
    base, controls, description = describe_controls(job.base)
    if job.method == "tpe" and job.startup >= job.trials:
        raise ValueError("Use fewer startup trials than total trials.")
    if len(set(job.seeds)) != len(job.seeds) or min(job.seeds) < 0:
        raise ValueError("Use distinct nonnegative simulation seeds.")
    if set(target.statistic_name for target in job.targets) - SCALAR_STATISTICS:
        raise ValueError("Select supported whole-root statistics.")
    if len({target.statistic_name for target in job.targets}) != len(job.targets):
        raise ValueError("List each whole-root statistic once.")
    space = {}
    for item in job.ranges:
        name = item.control
        if name in space or name not in controls or item.lower >= item.upper:
            raise ValueError(f"Check the active control and increasing bounds for {name}.")
        integer = controls[name]["kind"] == "int"
        if integer and not (item.lower.is_integer() and item.upper.is_integer()):
            raise ValueError(f"Use integer bounds for {name}.")
        if name == "gravitropism" and not 0 <= item.lower <= item.upper <= 1:
            raise ValueError("Use legacy downward bias between 0 and 1.")
        cast = int if integer else float
        space[name] = dict(kind=controls[name]["kind"], low=cast(item.lower), high=cast(item.upper))
    parameters = base["parameters"]
    for part in ("primary", "lateral"):
        low, high = f"min_{part}_length", f"max_{part}_length"
        if low in space or high in space:
            if space.get(low, {}).get("high", parameters.get(low)) > space.get(high, {}).get("low", parameters.get(high)):
                raise ValueError(f"Keep the entire {part} minimum-length range below the maximum-length range.")
    # Respect stricter configured limits and bound each shared worker's geometry.
    limits = base.setdefault("limits", {})
    for name, maximum in (("max_organs", 20000), ("max_nodes", 150000), ("max_stations", 150000),
                          ("max_branch_proposals", 250000)):
        limits[name] = min(limits.get(name) or maximum, maximum)
    for side in ("low", "high"):
        point = _candidate(base, controls, {name: limits[side] for name, limits in space.items()})
        resolve_config(point)
    return job, base, controls, space, description


def _predict(spec, targets, seeds):
    predictions = []
    for seed in seeds:
        config = dict(spec, random_seed=seed)
        simulator = RootSystemSimulation(random_seed=seed)
        simulator.run(config)
        nodes, _ = simulator.G.as_df()
        density = spec["parameters"]["root_tissue_density"]
        values = []
        for target in targets:
            cls = get_summary_statistic_func(target.statistic_name)
            value = cls(root_tissue_density=None if isinstance(density, dict) else density).calculate(nodes)
            if not np.isscalar(value) or not np.isfinite(value):
                raise ValueError(f"Simulation produced a nonfinite scalar for {target.statistic_name}")
            values.append(float(value))
        predictions.append(values)
    return np.mean(predictions, axis=0)


def _screen(job, space, study, evaluate, identity):
    """Evaluate a seeded stratified design through the same native objective."""
    design = qmc.LatinHypercube(len(space), seed=job.seeds[0]).random(job.trials)
    receipts = study / "trials"
    receipts.mkdir(parents=True)
    _atomic_json(study / "manifest.json", dict(identity=identity, method=job.method, design=design.tolist()))
    started = monotonic()
    completed, failed, best, value, best_index = 0, 0, None, None, None
    for trial, unit in enumerate(design):
        if monotonic() - started >= 600:
            break
        offer = {}
        for (name, spec), x in zip(space.items(), unit):
            low, high = spec["low"], spec["high"]
            if spec["kind"] == "int":
                offer[name] = low + int(x * (high - low + 1))
            else:
                offer[name] = float(low + x * (high - low))
        record = dict(trial_number=trial, suggested_parameters=offer)
        try:
            result = evaluate(offer, job.seeds)
        except (ValueError, RuntimeError) as error:
            record.update(state="FAIL", error=str(error))
            failed += 1
        else:
            record.update(state="COMPLETE", result=result)
            if value is None or result["loss"] < value:
                best, value, best_index = offer, result["loss"], trial
            completed += 1
        _atomic_json(receipts / f"trial_{trial:06d}.json", record)
    return dict(completed_trials=completed, failed_trials=failed, best_parameters=best,
                best_loss=value, best_trial_number=best_index,
                stop_reason="trial_budget_exhausted" if completed + failed == job.trials else "invocation_timeout")


def run_architecture_search(request, outdir):
    """Run a bounded search and export the replayable best input and trial table."""
    job, base, controls, space, description = validate_architecture_search(request)
    targets = job.targets
    observed = np.array([target.statistic_value for target in targets])
    scales = np.array([target.scale or abs(target.statistic_value) or 1. for target in targets])
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=False)

    def evaluate(settings, seeds):
        spec = _candidate(base, controls, {name: settings[name] for name in space})
        predicted = _predict(spec, targets, seeds)
        residual = (predicted - observed) / scales
        loss = np.abs(residual).mean() if job.metric == "mae" else np.sqrt(np.mean(residual ** 2))
        return dict(loss=float(loss), means=predicted.tolist())

    identity = dict(workflow="canonical-whole-root-v1", request=job.model_dump(mode="json"),
                    resolved=description["hashes"], capped_base=base,
                    evaluator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    study = outdir / "study"
    if job.method == "tpe":
        summary = run_parameter_search(
            base_parameters={}, search_space=space, seeds=job.seeds, outdir=study,
            n_trials=job.trials, n_startup_trials=job.startup, sampler_seed=job.seeds[0],
            timeout_seconds=600, evaluate=evaluate, identity=identity,
        )
    else:
        summary = _screen(job, space, study, evaluate, identity)
    summary["method"] = job.method
    paths = sorted((outdir / "study" / "trials").glob("trial_*.json"))
    with (outdir / "trials.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["trial", "state", "loss", *space])
        for path in paths:
            row = json.loads(path.read_text())
            values = row.get("suggested_parameters", {})
            writer.writerow([row["trial_number"], row["state"], row.get("result", {}).get("loss"),
                             *(values.get(name) for name in space)])
    if summary["best_parameters"] is not None:
        spec = _candidate(base, controls, summary["best_parameters"])
        _atomic_json(outdir / "best-configuration.json", dict(spec, random_seed=job.seeds[0]))
    _atomic_json(outdir / "summary.json", summary)
    return summary
