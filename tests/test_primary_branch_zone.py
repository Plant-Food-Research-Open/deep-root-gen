"""Invented primary-only physical branch zones; no observations or fitting."""

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import RootSimulationModel
from deeprootgen.archive.simulation import RootSystemSimulation
from deeprootgen.research.so4_controlled import construct_skeleton, validate_geometry
from deeprootgen.utils.primary_branch_zone import (
    FIELD,
    primary_branch_zone_sites,
    validate_primary_branch_zone,
)
from tests.test_primary_design import settings, initial

ZONE = dict(start_cm=1.0, end_cm=4.0)


def parameters(maximum=5, zone=None, **updates):
    counts = {1: 5, 2: 7, 3: 6, 4: 4, 5: 2}
    extra = dict(
        max_order=maximum,
        research_root_counts_by_order={
            order: count for order, count in counts.items() if order <= maximum
        },
        research_higher_order_tropism={
            order: dict(
                theta_deg=25.0, theta_sd_deg=0.0, probability_down=1.0, trials=0.5
            )
            for order in range(4, maximum + 1)
        }
        or None,
        research_current_length_cdfs_cm={
            order: dict(lengths_cm=[2.0, 3.0], cumulative_probabilities=[0.5, 1.0])
            for order in range(2, maximum + 1)
        },
        research_primary_branch_zone_cm=zone,
    )
    extra.update(updates)
    return settings(**extra)


def organ_arcs(simulation):
    result = {}
    for order in range(1, max(simulation.organs) + 1):
        for organ in simulation.organs[order]:
            oid = int(organ.segments[0].node_data.organ_id)
            cumulative = np.cumsum(organ.get_lengths())
            child_arcs = []
            ids = [node.node_data.node_id for node in organ.segments]
            for child in organ.child_organs:
                child_arcs.append(
                    float(cumulative[ids.index(child.parent_node.node_data.node_id)])
                )
            result[oid] = child_arcs
    return result


def test_midpoint_api_is_exact_deterministic_and_handles_zero_quota():
    assert primary_branch_zone_sites(100.0, 3, dict(start_cm=15.0, end_cm=90.0)) == [
        27.5,
        52.5,
        77.5,
    ]
    assert primary_branch_zone_sites(100.0, 0, dict(start_cm=15.0, end_cm=90.0)) == []
    assert validate_primary_branch_zone(None) is None
    for length in (90.0, 89.0):
        with pytest.raises(ValueError, match="exceed"):
            primary_branch_zone_sites(length, 3, dict(start_cm=15.0, end_cm=90.0))


@pytest.mark.parametrize("maximum", [3, 4, 5])
def test_native_primary_zone_keeps_counts_and_cdf_lengths_through_maximum(maximum):
    p = parameters(maximum, ZONE)
    one, two = RootSystemSimulation(random_seed=42), RootSystemSimulation(
        random_seed=42
    )
    one.run(p)
    two.run(p)
    nodes, edges = one.G.as_df()
    validate_geometry(nodes, edges, 0.0)
    assert (
        nodes.loc[nodes.order.gt(0)].groupby("order").organ_id.nunique().to_dict()
        == p.research_root_counts_by_order
    )
    for a, b in zip(one.G.as_df(), two.G.as_df()):
        pd.testing.assert_frame_equal(a, b, check_exact=True)
    for primary in one.organs[1]:
        report = primary.primary_branch_zone_diagnostics
        expected = primary_branch_zone_sites(
            primary.get_lengths().sum(), len(primary.child_organs), ZONE
        )
        np.testing.assert_allclose(report["sites_cm"], expected, rtol=0, atol=1e-14)
    for order in range(2, maximum + 1):
        for organ in one.organs[order]:
            assert organ.get_lengths().sum() == pytest.approx(
                organ.current_length_diagnostics["sampled_current_length_cm"], abs=1e-12
            )
            assert organ.get_lengths().sum() == pytest.approx(
                organ.current_length_diagnostics["pre_subdivision_length_cm"], abs=1e-12
            )


def test_primary_only_window_preserves_daughter_lengths_nonprimary_attachment_arcs_and_rng():
    before, after = initial(parameters()), initial(parameters(zone=ZONE))
    assert before.rng.bit_generator.state == after.rng.bit_generator.state
    a_arcs, b_arcs = organ_arcs(before), organ_arcs(after)
    for order in range(1, 6):
        for a, b in zip(before.organs[order], after.organs[order]):
            assert a.get_lengths().sum() == pytest.approx(
                b.get_lengths().sum(), abs=1e-12
            )
            if order > 1:
                np.testing.assert_allclose(
                    a.get_lengths(), b.get_lengths(), rtol=0, atol=1e-14
                )
                oid = int(a.segments[0].node_data.organ_id)
                np.testing.assert_allclose(a_arcs[oid], b_arcs[oid], rtol=0, atol=1e-14)
                assert not hasattr(b, "primary_branch_zone_diagnostics")
            else:
                oid = int(a.segments[0].node_data.organ_id)
                assert a_arcs[oid] != b_arcs[oid]
    # Inherited diameter is intentionally coupled to the new primary cylinder.
    assert any(
        not np.array_equal(a.get_diameters(), b.get_diameters())
        for a, b in zip(before.organs[2], after.organs[2])
    )


def test_primary_curve_and_each_original_material_interval_survive_before_positioning():
    base, zoned = parameters(), parameters(zone=ZONE)
    # Original construction arrays are observed before any branch cuts.
    from deeprootgen.model.root import RootOrgan
    from unittest.mock import patch

    captured = []
    original = RootOrgan._prepare_branch_nodes

    def capture(organ, diameters, lengths, coordinates):
        if organ.parent_node.node_data.order == 0:
            captured.append((diameters.copy(), lengths.copy(), coordinates.copy()))
        return original(organ, diameters, lengths, coordinates)

    with patch.object(RootOrgan, "_prepare_branch_nodes", capture):
        initial(base)
        after = initial(zoned)
    for a, b in zip(captured[:5], captured[5:]):
        for left, right in zip(a, b):
            np.testing.assert_array_equal(left, right)
    for primary, (diameter, length, _) in zip(after.organs[1], captured[5:]):
        original_ends = np.cumsum(length)
        actual_ends = np.cumsum(primary.get_lengths())
        for end in original_ends:
            assert np.min(abs(actual_ends - end)) < 1e-12
        midpoints = actual_ends - primary.get_lengths() / 2.0
        expected_diameter = diameter[np.searchsorted(original_ends, midpoints)]
        np.testing.assert_array_equal(primary.get_diameters(), expected_diameter)
        assert (primary.get_lengths() @ primary.get_diameters() ** 2) == pytest.approx(
            length @ diameter**2, abs=1e-12
        )


def test_inactive_none_preserves_original_graph_rng_and_saved_initial_hash():
    p = parameters()
    omitted = p.model_dump()
    omitted.pop(FIELD)
    a, b = initial(RootSimulationModel(**omitted)), initial(p)
    for left, right in zip(a.G.as_df(), b.G.as_df()):
        pd.testing.assert_frame_equal(left, right, check_exact=True)
    assert a.rng.bit_generator.state == b.rng.bit_generator.state
    source = construct_skeleton(p, 42)
    assert FIELD not in source.payload["parameters"]


@pytest.mark.parametrize(
    "zone",
    [
        dict(start_cm=True, end_cm=4.0),
        dict(start_cm=1.0, end_cm="4"),
        dict(start_cm=0.0, end_cm=4.0),
        dict(start_cm=-1.0, end_cm=4.0),
        dict(start_cm=4.0, end_cm=4.0),
        dict(start_cm=5.0, end_cm=4.0),
        dict(start_cm=1.0, end_cm=np.inf),
        dict(start_cm=np.nan, end_cm=4.0),
        dict(start_cm=1.0, end_cm=4.0, extra=2.0),
        {},
        dict(start_cm=1.0, end_cm=6.0),
    ],
)
def test_invalid_zones_rejected_by_helper_schema_and_mutation(zone):
    with pytest.raises(ValueError):
        parameters(zone=zone)
    p = parameters().model_copy(update={FIELD: zone})
    simulation = RootSystemSimulation(random_seed=42)
    before = simulation.G.as_df()
    with pytest.raises(ValueError):
        simulation.init_organs(p)
    for left, right in zip(before, simulation.G.as_df()):
        pd.testing.assert_frame_equal(left, right, check_exact=True)


@pytest.mark.parametrize(
    "updates",
    [
        dict(research_primary_design=None),
        dict(research_root_counts_by_order=None),
        dict(tropism_mode="legacy"),
        dict(max_order=2),
        dict(t=1),
        dict(research_current_length_grid="construction_steps_v1"),
        dict(research_current_length_cdfs_cm=None),
        dict(random_seed=None),
        dict(research_primary_attachment_distal_fraction=0.2),
        dict(
            research_parent2_branch_zone_cm=dict(
                basal_cm=0.2, apical_cm=0.2, spacing_cm=0.2
            )
        ),
        dict(research_tertiary_length_rank_strength=0.2),
    ],
)
def test_unsupported_scope_and_compositions_rejected(updates):
    with pytest.raises(ValueError):
        parameters(zone=ZONE, **updates)


def test_primitive_quota_and_unrepresentable_sites_fail_closed():
    for count in (-1, True, 1.2, "2"):
        with pytest.raises(ValueError, match="quota"):
            primary_branch_zone_sites(10.0, count, ZONE)
    zone = dict(start_cm=1.0, end_cm=np.nextafter(1.0, 2.0))
    with pytest.raises(ValueError, match="representable"):
        primary_branch_zone_sites(10.0, 2, zone)


def test_exact_existing_curve_knot_is_retained_without_rng_or_duplicate_cut():
    from types import SimpleNamespace
    from deeprootgen.model.root import RootOrgan

    class NoRng:
        def __getattr__(self, name):
            raise AssertionError("Primary quota placement must not access RNG")

    parameters = SimpleNamespace(
        research_root_counts_by_order={1: 1, 2: 1, 3: 1},
        research_parent2_branch_zone_cm=None,
        research_primary_branch_zone_cm=dict(start_cm=1.0, end_cm=3.0),
        floor_threshold=0.4,
        ceiling_threshold=0.9,
    )
    organ = SimpleNamespace(
        input_parameters=parameters,
        _conditioned_child_quota=1,
        parent_node=SimpleNamespace(node_data=SimpleNamespace(order=0)),
        rng=NoRng(),
    )
    diameter, length, coordinates, attachments = RootOrgan._prepare_branch_nodes(
        organ,
        np.array([0.6, 0.2]),
        np.array([2.0, 4.0]),
        np.array([[2.0, 0.0, 0.0], [6.0, 0.0, 0.0]]),
    )
    np.testing.assert_array_equal(length, [2.0, 4.0])
    np.testing.assert_array_equal(diameter, [0.6, 0.2])
    np.testing.assert_array_equal(coordinates, [[2.0, 0.0, 0.0], [6.0, 0.0, 0.0]])
    assert attachments == [0]
    assert organ.primary_branch_zone_diagnostics["sites_cm"] == [2.0]


def test_zero_quota_primary_emits_explicit_empty_receipt_without_array_or_rng_changes():
    from types import SimpleNamespace
    from deeprootgen.model.root import RootOrgan

    class NoRng:
        def __getattr__(self, name):
            raise AssertionError("Empty primary quota must not access RNG")

    parameters = SimpleNamespace(
        research_root_counts_by_order={1: 2, 2: 1, 3: 1},
        research_parent2_branch_zone_cm=None,
        research_primary_branch_zone_cm=ZONE,
        floor_threshold=0.4,
        ceiling_threshold=0.9,
    )
    organ = SimpleNamespace(
        input_parameters=parameters,
        _conditioned_child_quota=0,
        parent_node=SimpleNamespace(node_data=SimpleNamespace(order=0)),
        rng=NoRng(),
    )
    original = (
        np.array([0.6, 0.2]),
        np.array([2.0, 4.0]),
        np.array([[2.0, 0.0, 0.0], [6.0, 0.0, 0.0]]),
    )
    snapshots = tuple(array.copy() for array in original)
    result = RootOrgan._prepare_branch_nodes(organ, *original)
    for left, right, snapshot in zip(result[:3], original, snapshots):
        assert left is right
        np.testing.assert_array_equal(left, snapshot)
    assert result[3] == []
    assert organ.primary_branch_zone_diagnostics["retained_count"] == 0
    assert organ.primary_branch_zone_diagnostics["sites_cm"] == []
    assert organ.primary_branch_zone_diagnostics["zone_cm"] == ZONE
