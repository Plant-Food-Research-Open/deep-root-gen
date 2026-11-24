"""Invented supplied primary fractions; no observations or fitted parameters."""

from types import SimpleNamespace

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import RootSimulationModel
from deeprootgen.archive.simulation import RootSystemSimulation
from deeprootgen.model import root as root_module
from deeprootgen.research.so4_controlled import (
    Skeleton,
    _initial_saved_parameters,
    validate_geometry,
    validate_saved_order_controls,
)
from deeprootgen.utils.primary_branch_fractions import (
    FIELD,
    primary_fraction_sites,
    validate_primary_branch_fractions,
)
from tests.test_primary_design import settings, invented_entries


def parameters(fractions=None, maximum=5, **updates):
    values = settings(
        outer_root_num=1,
        inner_root_num=1,
        research_primary_design=invented_entries()[:2],
    ).model_dump()
    values["random_seed"] = 17
    quota = (
        3 if fractions is None else len(fractions) if isinstance(fractions, list) else 3
    )
    counts = {1: 2, 2: 2 * quota, 3: 4, 4: 3, 5: 2}
    values.update(
        research_primary_branch_zone_cm=None,
        research_primary_branch_fractions=fractions,
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
    )
    values.update(updates)
    return RootSimulationModel(**values)


def fake_organ(fractions, quota):
    class NoRng:
        def __getattr__(self, name):
            raise AssertionError("Fraction site placement must not access RNG")

    return SimpleNamespace(
        input_parameters=SimpleNamespace(
            research_root_counts_by_order={1: 1, 2: len(fractions), 3: 1},
            research_parent2_branch_zone_cm=None,
            research_primary_branch_zone_cm=None,
            research_primary_branch_fractions=fractions,
            floor_threshold=0.4,
            ceiling_threshold=0.9,
        ),
        _conditioned_child_quota=quota,
        parent_node=SimpleNamespace(node_data=SimpleNamespace(order=0)),
        rng=NoRng(),
    )


def test_analytic_fraction_sites_and_nonrandom_material_subdivision(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Fraction placement must not call the stochastic site sampler"
        )

    monkeypatch.setattr(root_module, "sample_branch_sites", forbidden)
    assert primary_fraction_sites(10.0, 3, [0.2, 0.5, 0.8]) == [2.0, 5.0, 8.0]
    organ = fake_organ([0.2, 0.5, 0.8], 3)
    diameter, lengths, points, attachments = (
        root_module.RootOrgan._prepare_branch_nodes(
            organ,
            np.array([0.4, 0.2]),
            np.array([4.0, 6.0]),
            np.array([[4.0, 0.0, 0.0], [10.0, 0.0, 0.0]]),
        )
    )
    np.testing.assert_array_equal(lengths, [2.0, 2.0, 1.0, 3.0, 2.0])
    np.testing.assert_array_equal(diameter, [0.4, 0.4, 0.2, 0.2, 0.2])
    np.testing.assert_array_equal(points[:, 0], [2.0, 4.0, 5.0, 8.0, 10.0])
    assert attachments == [0, 2, 3]
    assert lengths.sum() == 10.0
    assert lengths @ diameter**2 == pytest.approx(4 * 0.4**2 + 6 * 0.2**2, abs=1e-15)
    assert organ.primary_branch_fractions_diagnostics["sites_cm"] == [2.0, 5.0, 8.0]


def test_existing_corner_is_one_cut_and_wrong_primary_quota_rejected_before_sampling():
    organ = fake_organ([0.2, 0.4, 0.8], 3)
    _, lengths, points, attachments = root_module.RootOrgan._prepare_branch_nodes(
        organ,
        np.array([0.4, 0.2]),
        np.array([4.0, 6.0]),
        np.array([[4.0, 0.0, 0.0], [10.0, 0.0, 0.0]]),
    )
    np.testing.assert_array_equal(points[:, 0], [2.0, 4.0, 8.0, 10.0])
    assert attachments == [0, 1, 2]
    assert np.all(lengths > 0)
    for quota in (0, 2, 4):
        with pytest.raises(ValueError, match="quota"):
            root_module.RootOrgan._prepare_branch_nodes(
                fake_organ([0.2, 0.4, 0.8], quota),
                np.array([0.4, 0.2]),
                np.array([4.0, 6.0]),
                np.array([[4.0, 0.0, 0.0], [10.0, 0.0, 0.0]]),
            )


@pytest.mark.parametrize(
    "values",
    [
        [],
        (),
        "0.2",
        [0.0, 0.5],
        [0.2, 1.0],
        [-0.1, 0.5],
        [0.2, 0.2],
        [0.5, 0.2],
        [True, 0.5],
        [".2", 0.5],
        [np.nan],
        [np.inf],
        [10**400],
    ],
)
def test_invalid_lists_fail_helper_schema_and_preinit_scope(values):
    with pytest.raises(ValueError):
        validate_primary_branch_fractions(values)
    with pytest.raises(ValueError):
        parameters(values)
    p = parameters().model_copy(update={FIELD: values})
    simulation = RootSystemSimulation(random_seed=p.random_seed)
    before = simulation.G.as_df()
    with pytest.raises(ValueError):
        simulation.init_organs(p)
    for left, right in zip(before, simulation.G.as_df()):
        pd.testing.assert_frame_equal(left, right, check_exact=True)


@pytest.mark.parametrize(
    "updates",
    [
        dict(research_root_counts_by_order={1: 2, 2: 5, 3: 4, 4: 3, 5: 2}),
        dict(research_primary_branch_zone_cm=dict(start_cm=1.0, end_cm=5.0)),
        dict(research_primary_design=None),
        dict(research_root_counts_by_order=None),
        dict(research_current_length_cdfs_cm=None),
        dict(research_current_length_grid="construction_steps_v1"),
        dict(tropism_mode="legacy"),
        dict(soil_surface_z_cm=20.0),
        dict(t=1),
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
def test_unsupported_compositions_and_mismatched_quota_fail_schema(updates):
    with pytest.raises(ValueError):
        parameters([0.2, 0.5, 0.8], **updates)


def test_default_none_omitted_from_both_serialization_sites_and_active_replay_rejected():
    inactive = parameters()
    assert FIELD not in _initial_saved_parameters(inactive)
    nodes = pd.DataFrame(
        [
            dict(
                node_id=0,
                parent_id=-1,
                organ_id=0,
                order=0,
                segment_rank=0,
                x=0.0,
                y=0.0,
                z=0.0,
                length=0.0,
                diameter=0.0,
            ),
            dict(
                node_id=1,
                parent_id=0,
                organ_id=1,
                order=1,
                segment_rank=1,
                x=1.0,
                y=0.0,
                z=0.0,
                length=1.0,
                diameter=0.2,
            ),
        ]
    )
    edges = pd.DataFrame([dict(parent_id=0, child_id=1)])
    values = inactive.model_dump()
    with_none = Skeleton.from_tables(nodes, edges, 17, values)
    values.pop(FIELD)
    omitted = Skeleton.from_tables(nodes, edges, 17, values)
    assert with_none.sha256 == omitted.sha256
    assert FIELD not in with_none.payload["parameters"]
    active = parameters([0.2, 0.5, 0.8]).model_dump()
    skeleton = Skeleton.from_tables(nodes, edges, 17, active)
    with pytest.raises(ValueError, match="controlled replay is unsupported"):
        validate_saved_order_controls(skeleton, active)
    changed = dict(active, research_primary_branch_fractions=[0.1, 0.6, 0.9])
    with pytest.raises(ValueError, match="controlled replay is unsupported"):
        validate_saved_order_controls(skeleton, changed)


@pytest.mark.parametrize(
    "maximum,fractions",
    [(3, [0.2, 0.5, 0.8]), (4, [0.1, 0.6]), (5, [0.2, 0.5, 0.8]), (5, [0.1, 0.6])],
)
def test_native_exact_fractions_counts_lengths_tree_and_determinism(maximum, fractions):
    p = parameters(fractions, maximum)
    first, second = RootSystemSimulation(random_seed=17), RootSystemSimulation(
        random_seed=17
    )
    first.run(p)
    second.run(p)
    for left, right in zip(first.G.as_df(), second.G.as_df()):
        pd.testing.assert_frame_equal(left, right, check_exact=True)
    nodes, edges = first.G.as_df()
    validate_geometry(nodes, edges, 0.0)
    assert nx.is_arborescence(nx.DiGraph(zip(edges.parent_id, edges.child_id)))
    assert (
        nodes.loc[nodes.order.gt(0)].groupby("order").organ_id.nunique().to_dict()
        == p.research_root_counts_by_order
    )
    for primary in first.organs[1]:
        cumulative = np.cumsum(primary.get_lengths())
        ids = [node.node_data.node_id for node in primary.segments]
        actual = [
            cumulative[ids.index(child.parent_node.node_data.node_id)]
            for child in primary.child_organs
        ]
        np.testing.assert_allclose(
            actual,
            np.array(fractions) * primary.get_lengths().sum(),
            rtol=0,
            atol=1e-12,
        )
        assert len(primary.child_organs) == len(fractions)
    for order in range(2, maximum + 1):
        for organ in first.organs[order]:
            assert organ.get_lengths().sum() == pytest.approx(
                organ.current_length_diagnostics["sampled_current_length_cm"], abs=1e-12
            )
            if order < maximum:
                cumulative = np.cumsum(organ.get_lengths())
                ids = [node.node_data.node_id for node in organ.segments]
                sites = [
                    cumulative[ids.index(child.parent_node.node_data.node_id)]
                    for child in organ.child_organs
                ]
                quota = len(sites)
                expected = [
                    (
                        p.floor_threshold
                        + (index + 0.5)
                        * (p.ceiling_threshold - p.floor_threshold)
                        / quota
                    )
                    * cumulative[-1]
                    for index in range(quota)
                ]
                np.testing.assert_allclose(sites, expected, rtol=0, atol=1e-12)


def test_native_initial_rng_daughter_lengths_and_primary_material_intervals_preserved(
    monkeypatch,
):
    from tests.test_primary_design import initial

    captured = []
    original = root_module.RootOrgan._prepare_branch_nodes

    def observe(organ, diameter, length, points):
        if organ.parent_node.node_data.order == 0:
            captured.append((diameter.copy(), length.copy(), points.copy()))
        return original(organ, diameter, length, points)

    monkeypatch.setattr(root_module.RootOrgan, "_prepare_branch_nodes", observe)
    before, after = initial(parameters()), initial(parameters([0.2, 0.5, 0.8]))
    assert before.rng.bit_generator.state == after.rng.bit_generator.state
    for left, right in zip(captured[:2], captured[2:]):
        for a, b in zip(left, right):
            np.testing.assert_array_equal(a, b)
    for primary, (diameter, length, points) in zip(after.organs[1], captured[2:]):
        actual_length = primary.get_lengths()
        arc = np.cumsum(actual_length)
        old_arc = np.cumsum(length)
        assert all(np.min(abs(arc - end)) < 1e-12 for end in old_arc)
        expected_diameter = diameter[np.searchsorted(old_arc, arc - actual_length / 2)]
        np.testing.assert_array_equal(primary.get_diameters(), expected_diameter)
        assert actual_length @ primary.get_diameters() ** 2 == pytest.approx(
            length @ diameter**2, abs=1e-12
        )
    for order in range(2, 6):
        for a, b in zip(before.organs[order], after.organs[order]):
            np.testing.assert_allclose(
                a.get_lengths(), b.get_lengths(), rtol=0, atol=1e-12
            )


def test_native_inactive_historical_initial_hash_remains_exact(tmp_path):
    from tests.test_primary_design import (
        test_inactive_field_retains_preimplementation_initial_identity,
    )

    test_inactive_field_retains_preimplementation_initial_identity(tmp_path)


def test_active_primary_fractions_bypass_unused_global_window_distribution(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Primary fractions must bypass the unused global window")

    monkeypatch.setattr(root_module, "redistribute_capped_sites", forbidden)
    organ = fake_organ([0.2, 0.5, 0.8], 3)
    organ.input_parameters.floor_threshold = 0.4
    organ.input_parameters.ceiling_threshold = np.nextafter(np.nextafter(0.4, 1.0), 1.0)
    _, _, _, attachments = root_module.RootOrgan._prepare_branch_nodes(
        organ,
        np.array([0.4, 0.2]),
        np.array([4.0, 6.0]),
        np.array([[4.0, 0.0, 0.0], [10.0, 0.0, 0.0]]),
    )
    assert len(attachments) == 3
    assert organ.primary_branch_fractions_diagnostics["sites_cm"] == [2.0, 5.0, 8.0]


def test_later_parent_orders_keep_global_window_distribution_with_primary_fractions(
    monkeypatch,
):
    original = root_module.redistribute_capped_sites
    calls = []

    def recorded(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(root_module, "redistribute_capped_sites", recorded)
    organ = fake_organ([0.2, 0.5, 0.8], 2)
    organ.parent_node.node_data.order = 1
    _, lengths, _, attachments = root_module.RootOrgan._prepare_branch_nodes(
        organ,
        np.array([0.4, 0.2]),
        np.array([4.0, 6.0]),
        np.array([[4.0, 0.0, 0.0], [10.0, 0.0, 0.0]]),
    )
    assert len(calls) == 1
    assert calls[0]["floor_threshold"] == 0.4 and calls[0]["ceiling_threshold"] == 0.9
    np.testing.assert_allclose(
        np.cumsum(lengths)[attachments], [5.25, 7.75], rtol=0, atol=1e-14
    )
    assert not hasattr(organ, "primary_branch_fractions_diagnostics")
