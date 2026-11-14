"""Versioned research-only population architecture comparison.

Inputs are already equal-architecture means. In particular, callers normalize
each architecture's profile before averaging and explicitly pad common bins.
This module neither extracts geometry nor changes the historical 20% protocol.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from collections.abc import Mapping
from types import MappingProxyType

import numpy as np

VERSION = "architecture-population-eps0.10-v1"
EPSILON = 0.10
PROFILE_SUM_TOLERANCE = 1e-8
AGGREGATION = "equal_architecture_mean_of_per_architecture_traits_and_normalized_profiles"
TRAIT_UNITS = {
    "soil_length_cm": "cm",
    "mean_depth_cm": "cm",
    "max_depth_cm": "cm",
    "across_row_span_cm": "cm",
    "along_row_span_cm": "cm",
    "primary_mean_length_cm": "cm",
    "secondary_mean_length_cm": "cm",
    "tertiary_mean_length_cm": "cm",
    "primary_count": "count",
    "secondary_count": "count",
    "tertiary_count": "count",
    "row_across_span_ratio": "dimensionless",
    "verticality": "dimensionless",
}
PROFILE_AXES = ("across", "along", "depth")


def _snapshot(value):
    """Reject hidden missing/complex values and detach nested caller containers."""
    if np.ma.isMaskedArray(value) or np.iscomplexobj(value):
        raise ValueError("Masked arrays and complex values are unsupported")
    if isinstance(value, Mapping):
        return MappingProxyType({key: _snapshot(item) for key, item in value.items()})
    if isinstance(value, np.ndarray):
        return _snapshot(value.tolist())
    if isinstance(value, (tuple, list)):
        return tuple(_snapshot(item) for item in value)
    return value


@dataclass(frozen=True)
class ArchitectureComparisonSupport:
    """Versioned IDs identify caller-qualified frame, operator and root support."""

    coordinate_frame: str
    operator: str
    support: str
    bin_edges_cm: Mapping[str, list[float]]
    aggregation: str = AGGREGATION
    trait_units: Mapping[str, str] = field(default_factory=lambda: dict(TRAIT_UNITS))

    def __post_init__(self):
        object.__setattr__(self, "bin_edges_cm", _snapshot(self.bin_edges_cm))
        object.__setattr__(self, "trait_units", _snapshot(self.trait_units))


@dataclass(frozen=True)
class PopulationArchitecture:
    population_id: str
    n_architectures: int
    trait_means: Mapping[str, float]
    profiles: Mapping[str, list[float]]
    comparison: ArchitectureComparisonSupport

    def __post_init__(self):
        object.__setattr__(self, "trait_means", _snapshot(self.trait_means))
        object.__setattr__(self, "profiles", _snapshot(self.profiles))


@dataclass(frozen=True)
class Architecture10PercentContract:
    comparison: ArchitectureComparisonSupport
    version: str = VERSION
    epsilon: float = EPSILON


def _nonempty_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be an explicit nonempty identifier")
    return value


def _exact_keys(value, keys, name):
    if not isinstance(value, Mapping) or set(value) != set(keys):
        raise ValueError(f"{name} requires exactly {list(keys)}")


def _comparison_record(comparison):
    if not isinstance(comparison, ArchitectureComparisonSupport):
        raise ValueError("An explicit ArchitectureComparisonSupport is required")
    if comparison.aggregation != AGGREGATION:
        raise ValueError("Incompatible aggregation: normalize each architecture before averaging")
    if not isinstance(comparison.trait_units, Mapping) or dict(comparison.trait_units) != TRAIT_UNITS:
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
        trait_units=dict(TRAIT_UNITS),
    )


def _population_record(population, comparison):
    if not isinstance(population, PopulationArchitecture):
        raise ValueError("An explicit PopulationArchitecture is required")
    _nonempty_text(population.population_id, "population_id")
    if (isinstance(population.n_architectures, (bool, np.bool_))
            or not isinstance(population.n_architectures, (int, np.integer))
            or population.n_architectures <= 0):
        raise ValueError("Population size must be a positive integer")
    if _comparison_record(population.comparison) != comparison:
        raise ValueError("Population operator/frame/support/bins/aggregation are incompatible")
    _exact_keys(population.trait_means, TRAIT_UNITS, "Trait means")
    _exact_keys(population.profiles, PROFILE_AXES, "Profiles")
    traits = {}
    for name in TRAIT_UNITS:
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
    """Return all 16 unrounded criteria; J <= 1 iff every criterion passes."""
    if (not isinstance(contract, Architecture10PercentContract)
            or contract.version != VERSION or contract.epsilon != EPSILON):
        raise ValueError("Use the separately versioned epsilon=0.10 research contract")
    comparison = _comparison_record(contract.comparison)
    ref, cand = (_population_record(p, comparison) for p in (reference, candidate))
    traits, profiles, errors = {}, {}, {}
    for name, unit in TRAIT_UNITS.items():
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
        version=VERSION, epsilon=EPSILON, comparison=comparison,
        comparison_sha256=hashlib.sha256(json.dumps(comparison, sort_keys=True, allow_nan=False).encode()).hexdigest(),
        reference=dict(population_id=ref["population_id"], n_architectures=ref["n_architectures"]),
        candidate=dict(population_id=cand["population_id"], n_architectures=cand["n_architectures"]),
        traits=traits, profiles=profiles, error_vector=errors,
        normalized_error_vector={name: value / EPSILON for name, value in errors.items()},
        criterion_passes={name: value <= EPSILON for name, value in errors.items()},
        worst_criteria=[name for name, value in errors.items() if value == worst],
        worst_error=worst, J=worst / EPSILON, passed=all(value <= EPSILON for value in errors.values()),
    )
