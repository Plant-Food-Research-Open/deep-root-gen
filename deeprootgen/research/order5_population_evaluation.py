"""Separately versioned order-4/5 research diagnostic contracts.

The original order-1--3 contract and constants remain in population_evaluation.
No individual-vine, mass or biological acceptance policy is established here.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from collections.abc import Mapping

import numpy as np

from .population_evaluation import (
    AGGREGATION, EPSILON, PROFILE_AXES, PROFILE_SUM_TOLERANCE,
    TRAIT_UNITS as LEGACY_TRAIT_UNITS, ArchitectureComparisonSupport, PopulationArchitecture,
)

ORDER_NAMES = ("primary", "secondary", "tertiary", "quaternary", "quinary")
VERSIONS = {order: f"architecture-population-order{order}-eps0.10-v1" for order in (4, 5)}


def validate_root_orders(root_orders):
    """Require an explicit, contiguous order-1 through order-3/4/5 list."""
    if (not isinstance(root_orders, list) or len(root_orders) not in (3, 4, 5)
            or any(isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, np.integer))
                   for v in root_orders)
            or root_orders != list(range(1, len(root_orders) + 1))):
        raise ValueError("root_orders must declare contiguous [1, ..., max_order] with max_order 3, 4 or 5")
    return [int(v) for v in root_orders]


def trait_units_for_orders(root_orders):
    """Return detached units; never extend the legacy TRAIT_UNITS mapping."""
    orders = validate_root_orders(root_orders)
    units = dict(LEGACY_TRAIT_UNITS)
    for order in orders[3:]:
        name = ORDER_NAMES[order - 1]
        units[f"{name}_count"] = "count"
        units[f"{name}_mean_length_cm"] = "cm"
    return units


@dataclass(frozen=True)
class HigherOrder10PercentContract:
    comparison: ArchitectureComparisonSupport
    root_orders: list[int]
    version: str
    epsilon: float = EPSILON

    def __post_init__(self):
        orders = validate_root_orders(self.root_orders)
        if len(orders) not in VERSIONS or self.version != VERSIONS[len(orders)]:
            raise ValueError("Use the separately versioned order-4/5 contract")
        object.__setattr__(self, "root_orders", tuple(orders))


def _nonempty_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be an explicit nonempty identifier")
    return value


def _exact_keys(value, keys, name):
    if not isinstance(value, Mapping) or set(value) != set(keys):
        raise ValueError(f"{name} requires exactly {list(keys)}")


def _comparison_record(comparison, trait_units, root_orders):
    if not isinstance(comparison, ArchitectureComparisonSupport):
        raise ValueError("An explicit ArchitectureComparisonSupport is required")
    if comparison.aggregation != AGGREGATION:
        raise ValueError("Incompatible aggregation: normalize each architecture before averaging")
    if not isinstance(comparison.trait_units, Mapping) or dict(comparison.trait_units) != trait_units:
        raise ValueError("Trait units disagree with the versioned contract")
    _exact_keys(comparison.bin_edges_cm, PROFILE_AXES, "Profile edges")
    edges = {}
    for axis in PROFILE_AXES:
        values = np.asarray(comparison.bin_edges_cm[axis], dtype=float)
        if (values.ndim != 1 or len(values) < 2 or not np.isfinite(values).all()
                or not np.allclose(np.diff(values), 10., rtol=0, atol=1e-8)
                or not np.allclose(values / 10., np.rint(values / 10.), rtol=0, atol=1e-10)):
            raise ValueError("Profile edges must lie on a finite common 10 cm lattice")
        edges[axis] = values.tolist()
    return dict(
        coordinate_frame=_nonempty_text(comparison.coordinate_frame, "coordinate_frame"),
        operator=_nonempty_text(comparison.operator, "operator"),
        support=_nonempty_text(comparison.support, "support"),
        bin_edges_cm=edges, aggregation=comparison.aggregation,
        trait_units=dict(trait_units), root_orders=list(root_orders),
    )


def _population_record(population, comparison, trait_units, root_orders):
    if not isinstance(population, PopulationArchitecture):
        raise ValueError("An explicit PopulationArchitecture is required")
    _nonempty_text(population.population_id, "population_id")
    if (isinstance(population.n_architectures, (bool, np.bool_))
            or not isinstance(population.n_architectures, (int, np.integer))
            or population.n_architectures <= 0):
        raise ValueError("Population size must be a positive integer")
    if _comparison_record(population.comparison, trait_units, root_orders) != comparison:
        raise ValueError("Population operator/frame/support/bins/aggregation are incompatible")
    _exact_keys(population.trait_means, trait_units, "Trait means")
    _exact_keys(population.profiles, PROFILE_AXES, "Profiles")
    traits = {}
    for name in trait_units:
        value = population.trait_means[name]
        if isinstance(value, (bool, np.bool_)):
            raise ValueError("Trait means must be positive finite numbers")
        try:
            value = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError("Trait means must be positive finite numbers") from error
        if not np.isfinite(value) or value <= 0:
            raise ValueError("Trait means must be positive finite numbers")
        traits[name] = value
    profiles = {}
    for axis in PROFILE_AXES:
        values = np.asarray(population.profiles[axis], dtype=float)
        if (values.ndim != 1 or len(values) != len(comparison["bin_edges_cm"][axis]) - 1
                or not np.isfinite(values).all() or (values < 0).any()
                or not np.isclose(values.sum(), 1., rtol=0, atol=PROFILE_SUM_TOLERANCE)):
            raise ValueError("Profiles need explicit common bins and nonnegative normalized fractions")
        profiles[axis] = values
    return dict(population_id=population.population_id, n_architectures=int(population.n_architectures),
                trait_means=traits, profiles=profiles)


def evaluate_population_architecture(reference, candidate, contract):
    """Return 18/20 unrounded research criteria using unchanged epsilon=.10."""
    if (not isinstance(contract, HigherOrder10PercentContract)
            or contract.version != VERSIONS.get(len(contract.root_orders)) or contract.epsilon != EPSILON):
        raise ValueError("Use the separately versioned epsilon=0.10 research contract")
    orders = validate_root_orders(list(contract.root_orders))
    trait_units = trait_units_for_orders(orders)
    comparison = _comparison_record(contract.comparison, trait_units, orders)
    ref, cand = (_population_record(p, comparison, trait_units, orders) for p in (reference, candidate))
    traits, profiles, errors = {}, {}, {}
    for name, unit in trait_units.items():
        observed, proposed = ref["trait_means"][name], cand["trait_means"][name]
        signed = proposed - observed
        error = abs(signed) / observed
        if not np.isfinite(error):
            raise ValueError("Relative error overflow")
        traits[name] = dict(unit=unit, reference=observed, candidate=proposed,
                            signed_residual=signed, relative_error=error, passed=error <= EPSILON)
        errors[f"trait/{name}"] = error
    for axis in PROFILE_AXES:
        signed = cand["profiles"][axis] - ref["profiles"][axis]
        error = float(np.abs(signed).sum() / 2.)
        profiles[axis] = dict(bin_edges_cm=comparison["bin_edges_cm"][axis],
                              reference=ref["profiles"][axis].tolist(), candidate=cand["profiles"][axis].tolist(),
                              signed_residuals=signed.tolist(), total_variation=error, passed=error <= EPSILON)
        errors[f"profile/{axis}"] = error
    worst = max(errors.values())
    return dict(
        version=contract.version, epsilon=EPSILON, comparison=comparison,
        comparison_sha256=hashlib.sha256(json.dumps(comparison, sort_keys=True, allow_nan=False).encode()).hexdigest(),
        reference=dict(population_id=ref["population_id"], n_architectures=ref["n_architectures"]),
        candidate=dict(population_id=cand["population_id"], n_architectures=cand["n_architectures"]),
        traits=traits, profiles=profiles, error_vector=errors,
        normalized_error_vector={name: value / EPSILON for name, value in errors.items()},
        criterion_passes={name: value <= EPSILON for name, value in errors.items()},
        worst_criteria=[name for name, value in errors.items() if value == worst],
        worst_error=worst, J=worst / EPSILON, passed=all(value <= EPSILON for value in errors.values()),
    )
