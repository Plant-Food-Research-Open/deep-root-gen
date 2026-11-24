"""Invented discrete CDFs and actual-graph subdivision checks; no observations."""

import copy
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import RootSimulationModel
from deeprootgen.data_model.simulation_data_models import CurrentLengthCDF
from deeprootgen.archive.simulation import RootSystemSimulation
from deeprootgen.model.hgraph import RootSystemGraph
from deeprootgen.model.root import RootOrgan
from deeprootgen.research.so4_controlled import construct_skeleton, validate_geometry
from deeprootgen.utils.current_length import (
    sample_current_lengths,
    select_current_length,
)
from tests import test_subdivision_characterization as characterization

CDF = dict(lengths_cm=[4.0, 6.0, 8.0], cumulative_probabilities=[0.25, 0.75, 1.0])
LEGACY_PARAMETERS = characterization.parameters


def parameters(cdfs=None, **updates):
    spec = LEGACY_PARAMETERS().model_dump()
    spec.update(research_current_length_cdfs_cm=cdfs)
    spec.update(updates)
    return RootSimulationModel(**spec)


@pytest.mark.parametrize(
    "quantile,expected,index",
    [
        (0.0, 4.0, 0),
        (0.249, 4.0, 0),
        (0.25, 6.0, 1),
        (0.749, 6.0, 1),
        (0.75, 8.0, 2),
        (np.nextafter(1.0, 0.0), 8.0, 2),
    ],
)
def test_discrete_step_boundaries_no_interpolation(quantile, expected, index):
    assert select_current_length(CDF, quantile) == (expected, index)


def test_singleton_and_keyed_weights_preserve_normalized_current_total():
    singleton = CurrentLengthCDF(lengths_cm=[6.0], cumulative_probabilities=[1.0])
    lengths, report = sample_current_lengths(singleton, 10, 42, 3, 3)
    assert np.isfinite(lengths).all() and (lengths > 0).all()
    assert np.all(np.diff(lengths) <= 0)
    assert lengths.sum() == pytest.approx(6.0, rel=0, abs=1e-8)
    assert sum(report["normalized_weights"]) == pytest.approx(1.0)
    assert report["support_index"] == 0 and report["sampled_current_length_cm"] == 6.0
    assert report["stream_version"] == "drg-current-length-v1"
    repeated, repeated_report = sample_current_lengths(singleton, 10, 42, 3, 3)
    np.testing.assert_array_equal(lengths, repeated)
    assert report == repeated_report


def test_cdf_identity_changes_provenance_but_not_quantile_or_weight_keys():
    first, a = sample_current_lengths(CDF, 10, 42, 3, 3)
    scaled = dict(
        lengths_cm=[40.0, 60.0, 80.0], cumulative_probabilities=[0.25, 0.75, 1.0]
    )
    second, b = sample_current_lengths(scaled, 10, 42, 3, 3)
    assert a["cdf_sha256"] != b["cdf_sha256"]
    assert a["quantile"] == b["quantile"] and a["support_index"] == b["support_index"]
    assert a["normalized_weights"] == b["normalized_weights"]
    np.testing.assert_allclose(second, first * 10.0, rtol=0, atol=1e-12)
    _, different_organ = sample_current_lengths(CDF, 10, 42, 4, 3)
    assert a["normalized_weights"] != different_organ["normalized_weights"]


def length_only_organ(settings, *, capture=True):
    organ = object.__new__(RootOrgan)
    organ.input_parameters = settings
    organ.parent_node = SimpleNamespace(node_data=SimpleNamespace(order=2))
    organ.length_reduction = settings.length_reduction
    organ.sroot_length_interval = np.array(
        [settings.min_sec_root_length, settings.max_sec_root_length]
    )
    organ.rng = np.random.default_rng(42)
    if capture:
        organ._current_length_expected_organ_id = 3
    return organ


def test_legacy_scalar_and_weight_draw_consumption_retained_exactly_once():
    legacy = length_only_organ(parameters())
    selected = length_only_organ(parameters({3: CDF}))
    legacy.init_lengths(10)
    assigned = selected.init_lengths(10)
    assert legacy.rng.bit_generator.state == selected.rng.bit_generator.state
    assert selected.current_length_diagnostics["legacy_compatibility_draw_count"] == 11
    assert assigned.sum() == pytest.approx(
        selected.current_length_diagnostics["sampled_current_length_cm"], abs=1e-8
    )
    # A changed legacy reduction cannot change selected current length or weights.
    different_reduction = length_only_organ(parameters({3: CDF}, length_reduction=0.2))
    np.testing.assert_array_equal(assigned, different_reduction.init_lengths(10))
    assert (
        selected.rng.bit_generator.state == different_reduction.rng.bit_generator.state
    )


def test_unselected_order_retains_legacy_values_and_shared_rng():
    original = length_only_organ(parameters())
    unselected = length_only_organ(parameters({2: CDF}))
    np.testing.assert_array_equal(
        original.init_lengths(10), unselected.init_lengths(10)
    )
    assert original.rng.bit_generator.state == unselected.rng.bit_generator.state
    assert not hasattr(unselected, "current_length_diagnostics")


def test_selected_sampling_rejects_missing_captured_id_before_rng_draws():
    organ = length_only_organ(parameters({3: CDF}), capture=False)
    before = copy.deepcopy(organ.rng.bit_generator.state)
    with pytest.raises(ValueError, match="captured next organ ID"):
        organ.init_lengths(10)
    assert organ.rng.bit_generator.state == before


def test_actual_order3_graph_is_independent_of_parent_subdivision_with_matched_branch_rng(
    monkeypatch,
):
    selected = parameters({3: CDF})
    monkeypatch.setattr(characterization, "parameters", lambda: selected)
    coarse = characterization.construct_refined_fixture(False)
    fine = characterization.construct_refined_fixture(True)
    a, b = coarse["daughter"], fine["daughter"]
    assert a.parent_node.node_data.node_id != b.parent_node.node_data.node_id
    assert (
        a.parent_node.node_data.length == 5.0 and b.parent_node.node_data.length == 1.0
    )
    assert coarse["attachment_arc_cm"] == fine["attachment_arc_cm"] == 5.0
    assert coarse["state_before"] == fine["state_before"]
    np.testing.assert_array_equal(coarse["nominal"], fine["nominal"])
    np.testing.assert_array_equal(coarse["nominal"], coarse["before_subdivision"])
    np.testing.assert_array_equal(fine["nominal"], fine["before_subdivision"])
    np.testing.assert_allclose(
        a.get_coordinates(), b.get_coordinates(), rtol=0, atol=1e-10
    )
    np.testing.assert_allclose(a.get_lengths(), b.get_lengths(), rtol=0, atol=1e-10)
    np.testing.assert_array_equal(a.get_diameters(), b.get_diameters())
    assert coarse["insertion_count"] == fine["insertion_count"]
    assert len(a.child_organs) == len(b.child_organs) == coarse["insertion_count"]
    assert a.rng.bit_generator.state == b.rng.bit_generator.state
    for fixture in (coarse, fine):
        report = fixture["daughter"].current_length_diagnostics
        assert report["expected_organ_id"] == report["allocated_organ_id"] == 3
        assert report["sampled_current_length_cm"] in CDF["lengths_cm"]
        assert report["post_subdivision_length_cm"] == pytest.approx(
            report["sampled_current_length_cm"], rel=0, abs=1e-8
        )
        assert report["pre_subdivision_length_cm"] == pytest.approx(
            report["post_subdivision_length_cm"], rel=0, abs=1e-8
        )
        validate_geometry(fixture["nodes"], fixture["edges"])
    assert a.current_length_diagnostics == b.current_length_diagnostics


def test_actual_first_allocated_organ_id_is_checked(monkeypatch):
    selected = parameters({3: CDF})
    monkeypatch.setattr(characterization, "parameters", lambda: selected)
    increment = RootSystemGraph.increment_organ_id

    def wrong_allocation(graph):
        allocated = increment(graph)
        return allocated + 100 if allocated == 3 else allocated

    monkeypatch.setattr(RootSystemGraph, "increment_organ_id", wrong_allocation)
    with pytest.raises(ValueError, match="Allocated biological organ ID disagrees"):
        characterization.construct_refined_fixture(False)


@pytest.mark.parametrize("constructor_seed", [None, 43, True])
@pytest.mark.parametrize("method", ["init_organs", "run"])
def test_current_mode_requires_matching_explicit_seeds_before_graph_or_rng_mutations(
    constructor_seed, method
):
    settings = parameters({3: CDF})
    sim = RootSystemSimulation(random_seed=constructor_seed)
    before = sim.G.as_df()
    state = copy.deepcopy(sim.rng.bit_generator.state)
    with pytest.raises(
        ValueError, match="equal explicit constructor and parameter seeds"
    ):
        getattr(sim, method)(settings)
    for original, actual in zip(before, sim.G.as_df()):
        pd.testing.assert_frame_equal(original, actual)
    assert state == sim.rng.bit_generator.state and sim.organs == {}


def test_matched_initial_api_is_deterministic_and_keeps_skeleton_schema():
    settings = parameters({2: CDF, 3: CDF}, max_order=3)
    first, second = construct_skeleton(settings, 42), construct_skeleton(settings, 42)
    assert first.sha256 == second.sha256
    assert set(first.payload) == {
        "format",
        "seed",
        "parameters",
        "nodes",
        "edges",
        "organs",
    }
    validate_geometry(
        pd.DataFrame(first.payload["nodes"]), pd.DataFrame(first.payload["edges"])
    )


@pytest.mark.parametrize(
    "lengths,cumulative",
    [
        ([], []),
        ([1.0], []),
        ([1.0, 2.0], [1.0]),
        ([0.0], [1.0]),
        ([-1.0], [1.0]),
        ([np.inf], [1.0]),
        ([np.nan], [1.0]),
        ([2.0, 1.0], [0.5, 1.0]),
        ([1.0, 1.0], [0.5, 1.0]),
        ([1.0, 2.0], [0.0, 1.0]),
        ([1.0, 2.0], [0.5, 0.5]),
        ([1.0, 2.0], [0.75, 0.5]),
        ([1.0], [0.999]),
        ([1.0], [1.001]),
        ([1.0], [np.inf]),
        ([1.0], [np.nan]),
    ],
)
def test_invalid_cdf_schema_is_rejected_without_sorting_or_normalization(
    lengths, cumulative
):
    with pytest.raises(ValueError):
        CurrentLengthCDF(lengths_cm=lengths, cumulative_probabilities=cumulative)


@pytest.mark.parametrize(
    "cdfs,updates",
    [
        ({}, {}),
        ({1: CDF}, {}),
        ({6: CDF}, {}),
        ({3: CDF}, {"max_order": 2}),
        ({3: CDF}, {"random_seed": None}),
        ({3: CDF}, {"segments_per_root": 0}),
    ],
)
def test_invalid_selection_or_required_sampling_configuration_rejected(cdfs, updates):
    with pytest.raises(ValueError):
        parameters(cdfs, **updates)


@pytest.mark.parametrize("quantile", [-0.1, 1.0, np.nan, np.inf])
def test_invalid_quantiles_rejected(quantile):
    with pytest.raises(ValueError):
        select_current_length(CDF, quantile)


@pytest.mark.parametrize(
    "count,seed,organ,order",
    [
        (0, 42, 3, 3),
        (True, 42, 3, 3),
        (10, None, 3, 3),
        (10, 42, 0, 3),
        (10, 42, 3, 1),
        (10, 42, 3, 3.0),
    ],
)
def test_invalid_keyed_sampling_inputs_rejected(count, seed, organ, order):
    with pytest.raises(ValueError):
        sample_current_lengths(CDF, count, seed, organ, order)


def test_boolean_input_seed_rejected_even_when_numerically_equal_to_constructor_seed():
    settings = parameters({3: CDF}, random_seed=1).model_copy(
        update={"random_seed": True}
    )
    sim = RootSystemSimulation(random_seed=1)
    before = sim.G.as_df()
    with pytest.raises(
        ValueError, match="equal explicit constructor and parameter seeds"
    ):
        sim.init_organs(settings)
    for original, actual in zip(before, sim.G.as_df()):
        pd.testing.assert_frame_equal(original, actual)
