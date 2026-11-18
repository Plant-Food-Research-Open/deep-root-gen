"""Explicit offline search bridge with separately versioned order-1--3/4/5 diagnostics.

The geometric operator and epsilon=.10 criteria are unchanged. A seed ensemble
can represent a population mean or repeated reconstructions of one reference;
neither mode supplies independent biological validation. No observations are
loaded here and no services, files, retries, or seed selection are performed.
"""

from __future__ import annotations

import importlib.util
import math
import re
import sys
from collections import defaultdict
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .population_evaluation import (
    AGGREGATION, PROFILE_AXES, PROFILE_SUM_TOLERANCE, TRAIT_UNITS,
    Architecture10PercentContract, ArchitectureComparisonSupport,
    PopulationArchitecture, evaluate_population_architecture,
)

from .order5_population_evaluation import (
    VERSIONS as HIGHER_CONTRACT_VERSIONS, HigherOrder10PercentContract,
    evaluate_population_architecture as evaluate_higher_order_population,
    trait_units_for_orders, validate_root_orders,
)

VERSION = "research-search-evaluation-v1"
HIGHER_ORDER_VERSIONS = {order: f"research-search-evaluation-order{order}-v1" for order in (4, 5)}
ROUTES = ("graph_segments_v1", "construction_steps_v1")
OBJECTIVE_MODES = ("population_mean", "per_seed_mean")
ROOT_ORDERS = [1, 2, 3]
# A capacity guard rejects oversized dense requests; it never clips support.
MAX_PROFILE_BINS = 100_000


def _integer(value, name, minimum=0):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, np.integer)) or value < minimum):
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _number(value, name, positive=False):
    if (isinstance(value, (bool, np.bool_)) or np.ma.isMaskedArray(value)
            or not isinstance(value, (int, float, np.integer, np.floating))):
        raise ValueError(f"{name} must be a finite real number")
    try:
        value = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{name} must be finite") from error
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f"{name} must be {'positive and ' if positive else ''}finite")
    return value


def _traits(values, root_orders=None):
    units = trait_units_for_orders(ROOT_ORDERS if root_orders is None else root_orders)
    count = len(units)
    if not isinstance(values, Mapping) or set(values) != set(units):
        raise ValueError(f"Exactly the {count} existing positive traits are required")
    result = {}
    for name, value in values.items():
        try:
            result[name] = _number(value, name, positive=True)
        except ValueError as error:
            raise ValueError(
                f"The {count}-positive-trait contract rejects zero/undefined {name}"
            ) from error
    return result


def _profiles(values):
    if not isinstance(values, Mapping) or set(values) != set(PROFILE_AXES):
        raise ValueError("Profiles require exactly across, along and depth axes")
    result = {}
    for axis in PROFILE_AXES:
        if not isinstance(values[axis], Mapping) or not values[axis]:
            raise ValueError("Each profile must be a nonempty sparse bin mapping")
        bins = {}
        for key, value in values[axis].items():
            if not isinstance(key, str) or re.fullmatch(r"0|-?[1-9][0-9]*", key) is None:
                raise ValueError("Profile bins must be canonical integer strings (no aliases)")
            index = int(key)
            if abs(index) > (2**53 // 10) - 1:
                raise ValueError("Profile bin coordinates exceed exact numeric support")
            fraction = _number(value, "profile fraction")
            if fraction < 0:
                raise ValueError("Profile fractions must be nonnegative")
            bins[index] = fraction
        if not math.isclose(math.fsum(bins.values()), 1., rel_tol=0., abs_tol=PROFILE_SUM_TOLERANCE):
            raise ValueError("Profile fractions must already be normalized; no renormalization")
        result[axis] = bins
    return result


@lru_cache(maxsize=1)
def _pilot_helpers():
    """Load the public offline operator; its guarded CLI is never executed.

    Its imports are NumPy/Pandas/NetworkX and the direct model, plus the
    standard-library grid converter. It imports no Dash/Prefect/service layer.
    This bridge intentionally requires the repository's scripts directory.
    """
    path = Path(__file__).resolve().parents[2] / "scripts/research/grapevine3d_so4_pilot.py"
    spec = importlib.util.spec_from_file_location("_drg_search_pilot", path)
    if spec is None or spec.loader is None:
        raise ValueError("Public research geometry operator is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _validate_graph(nodes, edges, root_orders):
    required = {"node_id", "parent_id", "organ_id", "order", "x", "y", "z",
                "length", "diameter", "invalid_root", "root_type"}
    if (not isinstance(nodes, pd.DataFrame) or not isinstance(edges, pd.DataFrame)
            or not required.issubset(nodes) or not {"parent_id", "child_id"}.issubset(edges)):
        raise ValueError("Explicit root node/edge schema is required")
    if (nodes.empty or nodes.columns.duplicated().any() or edges.columns.duplicated().any()
            or not nodes.node_id.is_unique):
        raise ValueError("Empty graph, duplicate columns or duplicate node IDs")
    parents, orders = {}, {}
    for row in nodes.itertuples(index=False):
        node = _integer(row.node_id, "node_id")
        parents[node] = _integer(row.parent_id, "parent_id", -1)
        orders[node] = _integer(row.order, "root order")
        _integer(row.organ_id, "organ_id")
        if not isinstance(row.invalid_root, (bool, np.bool_)):
            raise ValueError("invalid_root flags must be strict booleans")
        if row.order > root_orders[-1]:
            raise ValueError("Graph root order exceeds the explicit root_orders support")
    bases = [node for node, order in orders.items() if order == 0]
    if len(bases) != 1 or parents[bases[0]] != -1 or list(parents.values()).count(-1) != 1:
        raise ValueError("Graph must contain exactly one order-0 base")
    base = bases[0]
    if "plant_id" in nodes and (nodes.plant_id.isna().any() or nodes.plant_id.nunique() != 1):
        raise ValueError("A sample must contain exactly one plant identity")
    roots = nodes.loc[nodes.node_id.ne(base)]
    if (not roots.root_type.isin(["fine", "structural"]).all()
            or nodes.loc[nodes.node_id.eq(base), "root_type"].iloc[0] != "base"):
        raise ValueError("Unknown root-only root_type mapping")
    if roots.organ_id.eq(nodes.loc[nodes.node_id.eq(base), "organ_id"].iloc[0]).any():
        raise ValueError("Root organ identity must differ from the base")
    if (roots.groupby("organ_id").order.nunique() > 1).any():
        raise ValueError("An organ cannot mix root orders")
    pairs = [(_integer(r.parent_id, "edge parent"), _integer(r.child_id, "edge child"))
             for r in edges.itertuples(index=False)]
    expected = {(parent, child) for child, parent in parents.items() if child != base}
    if len(pairs) != len(expected) or set(pairs) != expected:
        raise ValueError("Edge/parent agreement or unique incoming edge failed")
    if any(parent not in parents for child, parent in parents.items() if child != base):
        raise ValueError("Missing graph parent")
    if (roots.length.le(0).any() or roots.diameter.lt(0).any()):
        raise ValueError("Root segments require positive length and nonnegative diameter")
    _pilot_helpers().check_graph(nodes, edges)


def summarize_sample(nodes, edges, *, seed: int, surface_z_cm: float = 20.0, root_orders=None):
    """Summarize one graph using the unchanged public soil-clipped operator.

    All declared traits must be positive. Absent orders, zero spans and undefined
    ratios are rejected rather than assigned a new individual-vine policy.
    """
    seed = _integer(seed, "seed")
    surface = _number(surface_z_cm, "surface_z_cm")
    orders = validate_root_orders(ROOT_ORDERS if root_orders is None else root_orders)
    units = trait_units_for_orders(orders)
    _validate_graph(nodes, edges, orders)
    pilot = _pilot_helpers()
    records, invalid = pilot.node_segments(nodes, base_depth=surface)
    metrics, cells, _ = pilot.summarize_geometry(records)
    traits = _traits({name: metrics[name] for name in units}, orders)
    profiles = {axis: defaultdict(float) for axis in PROFILE_AXES}
    for cell, length in cells.items():
        for index, axis in enumerate(PROFILE_AXES):
            profiles[axis][str(int(cell[index]))] += length / traits["soil_length_cm"]
    profiles = {axis: dict(sorted(bins.items(), key=lambda item: int(item[0])))
                for axis, bins in profiles.items()}
    _profiles(profiles)
    invalid_metrics, _, _ = pilot.summarize_geometry(invalid)
    return dict(
        seed=seed, traits=traits, profiles=profiles,
        diagnostics=dict(
            version=HIGHER_ORDER_VERSIONS.get(orders[-1], VERSION), geometry_operator="grapevine3d_so4_pilot.summarize_geometry",
            root_orders=orders.copy(), surface_z_cm=surface, length_source="geometric",
            profile_bin_width_cm=10., profile_normalization="per_architecture_soil_length",
            node_count=len(nodes), edge_count=len(edges), invalid_child_count=len(invalid),
            invalid_soil_length_cm=float(invalid_metrics["soil_length_cm"]),
            above_surface_length_cm=float(metrics["above_surface_length_cm"]),
            shallow_fraction=float(metrics["shallow_fraction"]),
            qualification="RECONSTRUCTION_DIAGNOSTIC", biological_validation=False,
        ),
    )


def evaluate_samples(reference: dict, samples: list, *, objective_mode: str):
    """Compare seed summaries on common full-support bins without pooling length.

    population_mean uses the existing J of equal-architecture means.
    per_seed_mean averages each seed's existing J against the same reference;
    it is a reconstruction diagnostic, not a newly qualified acceptance rule.
    """
    if objective_mode not in OBJECTIVE_MODES:
        raise ValueError(f"objective_mode must explicitly select one of {OBJECTIVE_MODES}")
    if not isinstance(reference, Mapping):
        raise ValueError("An explicit reference mapping is required")
    orders = validate_root_orders(reference.get("root_orders"))
    units = trait_units_for_orders(orders)
    identity = reference.get("population_id")
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError("reference.population_id must be explicit nonempty text")
    count = _integer(reference.get("n_architectures"), "reference.n_architectures", 1)
    ref_traits, ref_profiles = _traits(reference.get("trait_means"), orders), _profiles(reference.get("profiles"))
    comparison = reference.get("comparison")
    if (not isinstance(comparison, Mapping)
            or set(comparison) != {"coordinate_frame", "operator", "support"}
            or any(not isinstance(v, str) or not v.strip() for v in comparison.values())):
        raise ValueError("comparison requires explicit coordinate_frame, operator and support")
    if not isinstance(samples, list) or not samples:
        raise ValueError("A nonempty list of seed samples is required")
    parsed, seen = [], set()
    for sample in samples:
        if not isinstance(sample, Mapping):
            raise ValueError("Each sample must be a mapping")
        seed = _integer(sample.get("seed"), "sample.seed")
        if seed in seen:
            raise ValueError("Duplicate sample seeds cannot receive additional weight")
        seen.add(seed)
        diagnostics = sample.get("diagnostics", {})
        if not isinstance(diagnostics, Mapping):
            raise ValueError("sample.diagnostics must be a mapping")
        if "root_orders" in diagnostics and validate_root_orders(diagnostics["root_orders"]) != orders:
            raise ValueError("sample diagnostics root_orders disagree with reference.root_orders")
        if orders[-1] > 3 and "root_orders" not in diagnostics:
            raise ValueError("Higher-order samples require explicit diagnostics.root_orders")
        parsed.append((seed, _traits(sample.get("traits"), orders), _profiles(sample.get("profiles"))))
    bins, edges = {}, {}
    for axis in PROFILE_AXES:
        union = set(ref_profiles[axis]).union(*(set(p[axis]) for _, _, p in parsed))
        lo, hi = min(union), max(union)
        if hi - lo + 1 > MAX_PROFILE_BINS:
            raise ValueError("Common profile support exceeds dense capacity; no bins were truncated")
        bins[axis] = range(lo, hi + 1)
        edges[axis] = [float(10 * index) for index in range(lo, hi + 2)]
    support = ArchitectureComparisonSupport(**dict(comparison), bin_edges_cm=edges, trait_units=units)
    if orders[-1] == 3:
        contract = Architecture10PercentContract(support)
        evaluate_population = evaluate_population_architecture
    else:
        contract = HigherOrder10PercentContract(support, orders, HIGHER_CONTRACT_VERSIONS[orders[-1]])
        evaluate_population = evaluate_higher_order_population

    def dense(profiles):
        return {axis: [profiles[axis].get(index, 0.) for index in bins[axis]] for axis in PROFILE_AXES}

    observed = PopulationArchitecture(identity, count, ref_traits, dense(ref_profiles), support)
    per_seed = []
    for seed, traits, profiles in parsed:
        candidate = PopulationArchitecture(f"generated-seed-{seed}", 1, traits, dense(profiles), support)
        per_seed.append(dict(seed=seed, **evaluate_population(observed, candidate, contract)))
    n = len(parsed)
    means = {name: math.fsum(t[name] / n for _, t, _ in parsed) for name in units}
    mean_profiles = {axis: [math.fsum(p[axis].get(index, 0.) / n for _, _, p in parsed)
                            for index in bins[axis]] for axis in PROFILE_AXES}
    candidate = PopulationArchitecture("generated-seed-ensemble", n, means, mean_profiles, support)
    population = evaluate_population(observed, candidate, contract)
    loss = population["J"] if objective_mode == "population_mean" else math.fsum(r["J"] / n for r in per_seed)
    return dict(
        version=HIGHER_ORDER_VERSIONS.get(orders[-1], VERSION), objective_mode=objective_mode, loss=float(loss),
        population_report=population, per_seed_reports=per_seed,
        per_seed_pass_fraction=sum(r["passed"] for r in per_seed) / n,
        per_seed_criterion_pass_fractions={key: sum(r["criterion_passes"][key] for r in per_seed) / n
                                           for key in population["criterion_passes"]},
        seeds=[seed for seed, _, _ in parsed], root_orders=orders.copy(),
        aggregation=AGGREGATION, qualification="RECONSTRUCTION_DIAGNOSTIC",
        biological_validation=False, mass_constraint_included=False,
        reference_scope="caller_declared_reference; no held-out-vine claim",
        objective_semantics=("J_of_equal_architecture_means" if objective_mode == "population_mean"
                             else "arithmetic_mean_of_per_seed_J_against_same_reference"),
    )


def validate_simulation_parameters(parameters, *, route: str):
    """Validate a canonical configuration against the chosen sampling protocol."""
    from ..data_model.resolution import parse_config, resolve_config

    config = parse_config(parameters)
    resolve_config(config)
    if route not in ROUTES:
        raise ValueError(f"Unsupported route {route}")
    p = config.parameters
    if p.tropism_mode != "fichtl2024" or not 3 <= p.max_order <= 5 or p.soil_surface_z_cm != 20:
        raise ValueError("Population summaries require Fichtl geometry, orders 3 to 5 and soil surface 20 cm")
    direction = config.features.direction
    steps = direction.enabled and direction.settings.stationing == "construction_steps_v1"
    if steps != (route == "construction_steps_v1"):
        raise ValueError("Search protocol and configured construction stationing disagree")
    return config


def simulate_sample(parameters, seed: int, *, route: str):
    """Generate one canonical architecture and measure its population traits."""
    from ..model import RootSystemSimulation
    from .so4_controlled import capture_initial

    config = validate_simulation_parameters(parameters, route=route)
    if config.random_seed != _integer(seed, "seed"):
        raise ValueError("parameters.random_seed must match the requested seed")
    snapshots = []
    simulation = RootSystemSimulation(random_seed=seed)
    simulation.run(config, initial_recorder=lambda sim, p: snapshots.append(capture_initial(sim, p)))
    nodes, edges = simulation.G.as_df()
    sample = summarize_sample(nodes, edges, seed=seed, surface_z_cm=config.parameters.soil_surface_z_cm,
                              root_orders=list(range(1, config.parameters.max_order + 1)))
    sample["diagnostics"].update(simulation_route=route, initial_sha256=snapshots[0].sha256,
                                 fresh_initial_construction=True, requested_simulation_tag=config.simulation_tag,
                                 constructor_simulation_tag=snapshots[0].payload["parameters"]["simulation_tag"],
                                 run_identity_sha256=simulation.result.metadata["run_identity_sha256"])
    return sample
