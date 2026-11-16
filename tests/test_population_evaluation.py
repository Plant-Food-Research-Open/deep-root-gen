"""Invented population means/profiles only; no observations or fitted values."""

from dataclasses import replace

import numpy as np
import pytest

from deeprootgen.research.population_evaluation import (
    AGGREGATION, TRAIT_UNITS, Architecture10PercentContract,
    ArchitectureComparisonSupport, PopulationArchitecture,
    evaluate_population_architecture,
)


def support(**updates):
    values = dict(coordinate_frame="invented-soil-frame-v1", operator="invented-root-operator-v1",
                  support="invented-valid-represented-roots-v1",
                  bin_edges_cm={"across": [-10., 0., 10.], "along": [-10., 0., 10.], "depth": [0., 10., 20.]})
    values.update(updates)
    return ArchitectureComparisonSupport(**values)


def population(identity="reference", count=2, comparison=None, **updates):
    values = dict(population_id=identity, n_architectures=count,
                  trait_means={name: 10. for name in TRAIT_UNITS},
                  profiles={axis: [.5, .5] for axis in ("across", "along", "depth")},
                  comparison=comparison or support())
    values.update(updates)
    return PopulationArchitecture(**values)


def evaluate(reference=None, candidate=None, comparison=None):
    return evaluate_population_architecture(reference or population(), candidate or population("candidate", 7),
                                            Architecture10PercentContract(comparison or support()))


def test_identical_means_profiles_different_populations_and_sizes_are_compatible():
    result = evaluate()
    assert result["reference"] == dict(population_id="reference", n_architectures=2)
    assert result["candidate"] == dict(population_id="candidate", n_architectures=7)
    assert result["version"] == "architecture-population-eps0.10-v1"
    assert result["epsilon"] == .10 and result["J"] == 0. and result["passed"]
    assert len(result["error_vector"]) == 16
    assert len(result["worst_criteria"]) == 16
    assert all(result["criterion_passes"].values())
    assert result == evaluate()


def test_exact_trait_threshold_ties_full_vector_and_signed_residuals():
    candidate = population("candidate", trait_means={name: 11. for name in TRAIT_UNITS})
    result = evaluate(candidate=candidate)
    assert result["J"] == 1. and result["passed"]
    assert len(result["worst_criteria"]) == 13
    assert all(value == .1 for name, value in result["error_vector"].items() if name.startswith("trait/"))
    assert result["traits"]["soil_length_cm"]["signed_residual"] == 1.
    means = dict(candidate.trait_means, soil_length_cm=9.)
    result = evaluate(candidate=replace(candidate, trait_means=means))
    assert result["traits"]["soil_length_cm"]["signed_residual"] == -1.
    assert result["traits"]["soil_length_cm"]["relative_error"] == .1


def test_one_failed_criterion_cannot_be_hidden_by_favourable_average_or_rounding():
    candidate = population("candidate", trait_means=dict(population().trait_means, soil_length_cm=11.00000001))
    result = evaluate(candidate=candidate)
    assert not result["passed"] and result["J"] > 1.
    assert result["worst_criteria"] == ["trait/soil_length_cm"]
    assert sum(result["criterion_passes"].values()) == 15
    assert result["normalized_error_vector"]["trait/soil_length_cm"] == result["J"]


def test_disjoint_profiles_have_tv_one_and_all_failed_axes_are_retained():
    reference = population(profiles={axis: [1., 0.] for axis in ("across", "along", "depth")})
    candidate = population("candidate", profiles={axis: [0., 1.] for axis in ("across", "along", "depth")})
    result = evaluate(reference, candidate)
    assert result["J"] == 10. and not result["passed"]
    assert result["worst_criteria"] == ["profile/across", "profile/along", "profile/depth"]
    assert result["profiles"]["depth"]["signed_residuals"] == [-1., 1.]


def test_profile_threshold_no_silent_normalization_or_length_pooling():
    reference = population(profiles={axis: [.25, .75] for axis in ("across", "along", "depth")})
    candidate = population("candidate", profiles={axis: [.35, .65] for axis in ("across", "along", "depth")})
    result = evaluate(reference, candidate)
    assert result["passed"] and result["J"] == pytest.approx(1.)
    # A numeric sum tolerance validates inputs; it must not renormalize values.
    adjusted = replace(candidate, profiles=dict(candidate.profiles, depth=[.350000001, .65]))
    result = evaluate(reference, adjusted)
    assert result["profiles"]["depth"]["candidate"] == [.350000001, .65]
    assert result["profiles"]["depth"]["total_variation"] > .10
    assert not result["passed"]
    with pytest.raises(ValueError, match="aggregation"):
        evaluate(candidate=population(comparison=support(aggregation="normalize_pooled_lengths")))
    assert AGGREGATION == result["comparison"]["aggregation"]


@pytest.mark.parametrize("field,value", [("coordinate_frame", "different-frame"), ("operator", "different-operator"),
                                         ("support", "different-root-support")])
def test_support_operator_frame_mismatch_rejected(field, value):
    with pytest.raises(ValueError, match="incompatible"):
        evaluate(candidate=population(comparison=support(**{field: value})))


@pytest.mark.parametrize("edges", [
    {"across": [-10., 0., 10.], "along": [0., 10.], "depth": [0., 10., 20.]},
    {"across": [-5., 5., 15.], "along": [-10., 0., 10.], "depth": [0., 10., 20.]},
    {"across": [-10., 0., 11.], "along": [-10., 0., 10.], "depth": [0., 10., 20.]},
    {"across": [-10., 0., np.inf], "along": [-10., 0., 10.], "depth": [0., 10., 20.]},
])
def test_mismatched_or_invalid_bins_rejected(edges):
    with pytest.raises(ValueError):
        evaluate(candidate=population(comparison=support(bin_edges_cm=edges)))


@pytest.mark.parametrize("value", [0., -1., np.nan, np.inf, True, None, "not-a-number"])
def test_invalid_positive_trait_mean_rejected(value):
    with pytest.raises(ValueError, match="positive finite"):
        evaluate(candidate=population(trait_means=dict(population().trait_means, soil_length_cm=value)))


@pytest.mark.parametrize("values", [[.2, .2], [0., 0.], [-.1, 1.1], [np.nan, 1.], [np.inf, 0.], [1.], [[.5, .5]]])
def test_invalid_profiles_rejected(values):
    with pytest.raises(ValueError, match="Profiles"):
        evaluate(candidate=population(profiles=dict(population().profiles, depth=values)))


@pytest.mark.parametrize("field", ["trait_means", "profiles"])
@pytest.mark.parametrize("operation", ["missing", "extra"])
def test_missing_extra_criteria_rejected(field, operation):
    values = dict(getattr(population(), field))
    if operation == "missing":
        values.pop(next(iter(values)))
    else:
        values["unexpected"] = 1.
    with pytest.raises(ValueError, match="exactly"):
        evaluate(candidate=population(**{field: values}))


@pytest.mark.parametrize("count", [0, -1, 2.5, True])
def test_invalid_population_size_rejected(count):
    with pytest.raises(ValueError, match="positive integer"):
        evaluate(candidate=population(count=count))


def test_wrong_units_empty_ids_and_old_epsilon_cannot_enter_new_contract():
    with pytest.raises(ValueError, match="units"):
        evaluate(candidate=population(comparison=support(trait_units=dict(TRAIT_UNITS, soil_length_cm="m"))))
    with pytest.raises(ValueError, match="identifier"):
        evaluate(candidate=population(identity=""))
    with pytest.raises(ValueError, match="epsilon=0.10"):
        evaluate_population_architecture(population(), population(), Architecture10PercentContract(support(), epsilon=.20))


def test_finite_inputs_cannot_return_infinite_relative_error():
    with pytest.raises(ValueError, match="overflow"):
        evaluate(reference=population(trait_means=dict(population().trait_means, soil_length_cm=1e-300)),
                 candidate=population(trait_means=dict(population().trait_means, soil_length_cm=1e300)))


def test_support_and_population_snapshot_nested_mappings_lists_and_arrays():
    edges = {"across": [-10., 0., 10.], "along": [-10., 0., 10.], "depth": np.array([0., 10., 20.])}
    units = dict(TRAIT_UNITS)
    declared = support(bin_edges_cm=edges, trait_units=units)
    traits = {name: 10. for name in TRAIT_UNITS}
    profiles = {axis: [.5, .5] for axis in ("across", "along", "depth")}
    reference = population(comparison=declared, trait_means=traits, profiles=profiles)
    candidate = population("candidate", comparison=declared, trait_means=traits, profiles=profiles)
    contract = Architecture10PercentContract(declared)
    before = evaluate_population_architecture(reference, candidate, contract)
    edges["depth"][:] = [10., 20., 30.]
    edges["along"][0] = -20.
    units["soil_length_cm"] = "m"
    traits["soil_length_cm"] = 100.
    profiles["depth"][:] = [1., 0.]
    assert evaluate_population_architecture(reference, candidate, contract) == before
    assert declared.bin_edges_cm["depth"] == (0., 10., 20.)
    with pytest.raises(TypeError):
        declared.bin_edges_cm["depth"][0] = 10.
    with pytest.raises(TypeError):
        declared.trait_units["soil_length_cm"] = "m"
    with pytest.raises(TypeError):
        candidate.profiles["depth"] = (1., 0.)


@pytest.mark.parametrize("value", [
    np.ma.array([.5, .5], mask=[False, True]), np.ma.array([.5, .5], mask=False),
    np.array([.5 + 3j, .5 - 3j]), np.array([.5 + 3j, .5 - 3j], dtype=object),
])
def test_profiles_reject_masks_and_complex_values_before_conversion(value):
    with pytest.raises(ValueError, match="Masked arrays and complex"):
        population(profiles=dict(population().profiles, depth=value))


@pytest.mark.parametrize("value", [
    np.ma.array([0., 10., 20.], mask=[False, True, False]), np.array([0., 10. + 1j, 20.]),
])
def test_edges_reject_masks_and_complex_values_before_conversion(value):
    edges = dict(support().bin_edges_cm, depth=value)
    with pytest.raises(ValueError, match="Masked arrays and complex"):
        support(bin_edges_cm=edges)


@pytest.mark.parametrize("value", [np.ma.array(10., mask=True), np.complex128(10. + 2j)])
def test_traits_reject_masks_and_complex_values_before_conversion(value):
    with pytest.raises(ValueError, match="Masked arrays and complex"):
        population(trait_means=dict(population().trait_means, soil_length_cm=value))
