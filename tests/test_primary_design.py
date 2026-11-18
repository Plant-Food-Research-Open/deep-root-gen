"""Explicit construction checks using invented dimensions and labels only."""

import copy

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import RootSimulationModel
from deeprootgen.archive.simulation import RootSystemSimulation
from deeprootgen.research.so4_controlled import (
    construct_skeleton,
    replay_arm,
    validate_geometry,
)
from deeprootgen.utils.primary_design import primary_dimensions, target_direction
from deeprootgen.utils.primary_orientation import proper_rotation
from tests.test_root_origin_initialization import values


def invented_entries():
    """Three horizontal labels, one vertical and one unknown; all angles assumed."""
    return [
        dict(
            primary_id=f"invented-{i}",
            category=category,
            length_cm=float(6 + i),
            diameter_base_cm=0.6 + 0.1 * i,
            diameter_apex_cm=0.1 + 0.01 * i,
            inclination_deg=angle,
            azimuth_deg=azimuth,
        )
        for i, (category, angle, azimuth) in enumerate(
            [
                ("horizontal", 0.0, 0.0),
                ("horizontal", 0.0, 120.0),
                ("horizontal", 0.0, -120.0),
                ("vertical", 90.0, 0.0),
                ("unknown", 45.0, 20.0),
            ]
        )
    ]


def settings(**updates):
    spec = values(
        outer_root_num=3,
        inner_root_num=2,
        segments_per_root=4,
        min_primary_length=5.0,
        max_primary_length=6.0,
        root_vary=2.0,
        min_sec_root_num=1,
        max_sec_root_num=2,
        growth_sec_root=0.0,
        interbranch_distance=0.5,
        floor_threshold=0.25,
        ceiling_threshold=0.75,
        soil_surface_z_cm=0.0,
        research_base_origin_x_cm=2.0,
        research_base_origin_y_cm=-3.0,
        research_base_depth_cm=25.0,
        research_primary_design=invented_entries(),
    )
    spec.update(updates)
    return RootSimulationModel(**spec)


def initial(parameters):
    sim = RootSystemSimulation(random_seed=parameters.random_seed)
    sim.init_organs(parameters)
    sim.position_secondary_roots(parameters)
    sim.position_primary_roots(parameters)
    return sim


def test_five_primaries_lengths_taper_and_shared_origin_before_and_after_native_tropism():
    p = settings()
    sim = initial(p)
    nodes, edges = sim.G.as_df()
    assert len(sim.organs[1]) == 5
    assert [organ.root_type.position_type for organ in sim.organs[1]] == [
        "outer"
    ] * 3 + ["inner"] * 2
    assert [organ.primary_design["category"] for organ in sim.organs[1]] == [
        "horizontal"
    ] * 3 + ["vertical", "unknown"]
    base = np.array([2.0, -3.0, -25.0])
    for organ, entry in zip(sim.organs[1], invented_entries()):
        assert organ.parent_node is sim.G.base_node
        assert organ.get_lengths().sum() == pytest.approx(entry["length_cm"], abs=1e-12)
        diameter = organ.get_diameters()
        assert diameter[0] == entry["diameter_base_cm"]
        assert diameter[-1] == entry["diameter_apex_cm"]
        assert np.all(np.diff(diameter) <= 0)
        assert set(diameter).issubset(
            set(np.linspace(entry["diameter_base_cm"], entry["diameter_apex_cm"], 4))
        )
        chord = organ.get_apex_coordinates() - base
        np.testing.assert_allclose(
            chord / np.linalg.norm(chord), target_direction(entry), atol=1e-12
        )
    native = RootSystemSimulation(random_seed=p.random_seed)
    native.run(p)
    native_nodes, native_edges = native.G.as_df()
    pd.testing.assert_frame_equal(
        nodes.loc[nodes.order.le(1)].reset_index(drop=True),
        native_nodes.loc[native_nodes.order.le(1)].reset_index(drop=True),
    )
    pd.testing.assert_frame_equal(edges, native_edges)
    assert all(
        not organ.invalid_root and organ.validation_reorientations == 0
        for organ in native.organs[1]
    )
    validate_geometry(native_nodes, native_edges, 0.0)
    graph = nx.DiGraph(zip(native_edges.parent_id, native_edges.child_id))
    assert nx.is_arborescence(graph) and nx.is_weakly_connected(graph)
    assert set(native_nodes.node_id) == set(graph.nodes)


def test_dimensions_are_bound_before_primary_branch_sites_and_daughter_construction(
    monkeypatch,
):
    from deeprootgen.model.root import RootOrgan

    observed = []
    original = RootOrgan._prepare_branch_nodes

    def checked(organ, diameters, lengths, coordinates):
        if hasattr(organ, "primary_design"):
            entry = organ.primary_design
            assert lengths.sum() == pytest.approx(entry["length_cm"], abs=1e-12)
            np.testing.assert_allclose(
                diameters,
                np.linspace(entry["diameter_base_cm"], entry["diameter_apex_cm"], 4),
            )
            observed.append(entry["primary_id"])
        return original(organ, diameters, lengths, coordinates)

    monkeypatch.setattr(RootOrgan, "_prepare_branch_nodes", checked)
    sim = initial(settings())
    assert observed == [entry["primary_id"] for entry in invented_entries()]
    assert len(sim.organs[2]) == len(sim.organs[3]) == 5
    for parent in sim.organs[1]:
        assert len(parent.child_organs) == 1
        child = parent.child_organs[0]
        assert child.parent_node in parent.segments
        assert (
            child.segments[0].node_data.parent_id == child.parent_node.node_data.node_id
        )


def test_linear_rank_taper_and_constant_taper_child_cylinder_convention():
    entry = invented_entries()[0]
    diameter, length = primary_dimensions(entry, [0.2, 0.3, 0.5])
    np.testing.assert_array_equal(diameter, [0.6, 0.35, 0.1])
    np.testing.assert_allclose(length, [1.2, 1.8, 3.0])
    constant = dict(entry, diameter_apex_cm=0.6)
    np.testing.assert_array_equal(
        primary_dimensions(constant, [0.2, 0.3, 0.5])[0], [0.6, 0.6, 0.6]
    )


@pytest.mark.parametrize("outer,inner", [(5, 0), (0, 5)])
def test_zero_native_group_is_supported_only_by_opted_in_positioning(outer, inner):
    sim = initial(settings(outer_root_num=outer, inner_root_num=inner))
    assert len(sim.organs[1]) == 5
    assert all(
        organ.root_type.position_type == ("outer" if outer else "inner")
        for organ in sim.organs[1]
    )


def test_repeatability_and_rigid_subtree_rotation_keep_dimensions_and_parent_links():
    p = settings()
    one, two = initial(p), initial(p)
    for left, right in zip(one.G.as_df(), two.G.as_df()):
        pd.testing.assert_frame_equal(left, right, check_exact=True)
    assert one.rng.bit_generator.state == two.rng.bit_generator.state
    raw = RootSystemSimulation(random_seed=p.random_seed)
    raw.init_organs(p)
    raw.position_secondary_roots(p)
    before, before_edges = raw.G.as_df()
    state = copy.deepcopy(raw.rng.bit_generator.state)
    raw.apply_primary_design_initialization(p)
    after, after_edges = raw.G.as_df()
    pd.testing.assert_frame_equal(
        before.drop(columns=["x", "y", "z"]), after.drop(columns=["x", "y", "z"])
    )
    pd.testing.assert_frame_equal(before_edges, after_edges)
    assert raw.rng.bit_generator.state == state
    for report in raw.primary_design_diagnostics:
        r = np.asarray(report["rotation"])
        np.testing.assert_allclose(r.T @ r, np.eye(3), atol=1e-12)
        assert np.linalg.det(r) == pytest.approx(1.0, abs=1e-12)
        assert report["maximum_edge_length_residual_cm"] <= 1e-8


def test_antiparallel_rotation_is_proper_and_angles_include_horizontal_oblique_vertical():
    rotation = proper_rotation([1.0, 0.0, 0.0], [-1.0, 0.0, 0.0])
    np.testing.assert_allclose(rotation @ [1.0, 0.0, 0.0], [-1.0, 0.0, 0.0], atol=1e-12)
    assert np.linalg.det(rotation) == pytest.approx(1.0)
    entry = invented_entries()[0]
    for angle, expected in [
        (0.0, [1.0, 0.0, 0.0]),
        (45.0, [2**-0.5, 0.0, -(2**-0.5)]),
        (90.0, [0.0, 0.0, -1.0]),
    ]:
        np.testing.assert_allclose(
            target_direction(dict(entry, inclination_deg=angle)), expected, atol=1e-12
        )


def test_category_and_id_are_metadata_only():
    p = settings()
    edited = invented_entries()
    for i, entry in enumerate(edited):
        entry.update(primary_id=f"other-{i}", category="unmeasured label")
    a, b = initial(p), initial(settings(research_primary_design=edited))
    for left, right in zip(a.G.as_df(), b.G.as_df()):
        pd.testing.assert_frame_equal(left, right, check_exact=True)


def test_surface_zero_controlled_initial_identity_and_replay():
    p = settings()
    skeleton = construct_skeleton(p, 42)
    repeated = construct_skeleton(p, 42)
    assert skeleton.sha256 == repeated.sha256
    assert (
        skeleton.payload["parameters"]["research_primary_design"]
        == p.model_dump()["research_primary_design"]
    )
    expected = initial(p).G.as_df()[0]
    actual = pd.DataFrame(skeleton.payload["nodes"])
    pd.testing.assert_frame_equal(
        expected.drop(columns="simulation_tag"), actual.drop(columns="simulation_tag")
    )
    replay = replay_arm(
        skeleton, "D", p.model_dump(), "minimum_angle_projection", surface_z=0.0
    )
    validate_geometry(replay["nodes"], replay["edges"], 0.0)
    assert not replay["nodes"].invalid_root.any()
    with pytest.raises(ValueError):
        replay_arm(skeleton, "D", p.model_dump(), "minimum_angle_projection")
    with pytest.raises(ValueError, match="matching explicit seeds"):
        construct_skeleton(p, 43)


@pytest.mark.parametrize(
    "field",
    [
        "primary_id",
        "category",
        "length_cm",
        "diameter_base_cm",
        "diameter_apex_cm",
        "inclination_deg",
        "azimuth_deg",
    ],
)
def test_replay_rejects_changed_explicit_design(field):
    p = settings()
    skeleton = construct_skeleton(p, 42)
    requested = p.model_dump()
    old = requested["research_primary_design"][0][field]
    requested["research_primary_design"][0][field] = (
        old + "-changed" if isinstance(old, str) else old + 0.01
    )
    with pytest.raises(ValueError, match="disagrees with saved INITIAL"):
        replay_arm(skeleton, "D", requested, "minimum_angle_projection", surface_z=0.0)


@pytest.mark.parametrize(
    "key,value",
    [
        ("research_primary_design", None),
        ("random_seed", 43),
        ("research_base_depth_cm", 26.0),
        ("research_base_origin_x_cm", 3.0),
    ],
)
def test_replay_rejects_omitted_design_or_changed_seed_and_common_origin(key, value):
    p = settings()
    skeleton = construct_skeleton(p, 42)
    requested = p.model_dump()
    requested[key] = value
    with pytest.raises(ValueError, match="disagrees with saved INITIAL"):
        replay_arm(skeleton, "D", requested, "minimum_angle_projection", surface_z=0.0)


def test_single_segment_constant_taper_and_negative_inclination_are_supported():
    entry = dict(
        invented_entries()[0],
        diameter_apex_cm=0.6,
        inclination_deg=-89.0,
        azimuth_deg=-180.0,
    )
    p = settings(
        max_order=1,
        outer_root_num=1,
        inner_root_num=0,
        segments_per_root=1,
        research_primary_design=[entry],
    )
    sim = RootSystemSimulation(random_seed=p.random_seed)
    sim.run(p)
    organ = sim.organs[1][0]
    np.testing.assert_allclose(organ.get_diameters(), [0.6])
    np.testing.assert_allclose(organ.get_lengths(), [6.0])
    chord = organ.get_apex_coordinates() - np.array([2.0, -3.0, -25.0])
    np.testing.assert_allclose(
        chord / np.linalg.norm(chord), target_direction(entry), atol=1e-12
    )


@pytest.mark.parametrize(
    "updates",
    [
        dict(research_primary_design=[]),
        dict(inner_root_num=1),
        dict(random_seed=None),
        dict(random_seed=True),
        dict(tropism_mode="legacy"),
        dict(max_order=6),
        dict(t=1),
        dict(soil_surface_z_cm=20.0),
        dict(research_primary_yaw_mean_deg=0.0, research_primary_yaw_kappa=0.0),
        dict(research_primary_inclination_bias=0.0),
        dict(research_primary_yaw_reverse_probability=0.0),
        dict(segments_per_root=1),
        dict(outer_root_num=-1, inner_root_num=6),
    ],
)
def test_invalid_design_compositions(updates):
    with pytest.raises(ValueError):
        settings(**updates)


@pytest.mark.parametrize(
    "field,value",
    [
        ("primary_id", ""),
        ("category", 4),
        ("length_cm", 0.0),
        ("length_cm", float("nan")),
        ("diameter_base_cm", 0.01),
        ("diameter_apex_cm", 0.0),
        ("inclination_deg", -90.0),
        ("inclination_deg", 90.1),
        ("azimuth_deg", 181.0),
        ("azimuth_deg", True),
        ("origin_x_cm", 1.0),
    ],
)
def test_invalid_entry_values_and_unequal_origins_are_rejected(field, value):
    entries = invented_entries()
    entries[0][field] = value
    with pytest.raises(ValueError):
        settings(research_primary_design=entries)


def test_duplicate_ids_constructor_seed_and_mutated_design_are_rejected():
    entries = invented_entries()
    entries[1]["primary_id"] = entries[0]["primary_id"]
    with pytest.raises(ValueError, match="unique"):
        settings(research_primary_design=entries)
    for seed in (None, 43):
        with pytest.raises(ValueError, match="matching constructor"):
            RootSystemSimulation(random_seed=seed).init_organs(settings())
    missing_constructor_seed = RootSystemSimulation(random_seed=42)
    del missing_constructor_seed.random_seed
    with pytest.raises(ValueError, match="matching constructor"):
        missing_constructor_seed.init_organs(settings())
    p = settings()
    p.research_primary_design[0].length_cm = -1.0
    with pytest.raises(ValueError):
        RootSystemSimulation(random_seed=42).init_organs(p)


def test_inactive_field_retains_preimplementation_initial_identity(tmp_path):
    # Paired against the exact pre-edit source copy in
    # Preimplementation qualification used only invented public fixture values.
    spec = values(
        min_primary_length=5.0,
        max_primary_length=6.0,
        segments_per_root=3,
        root_vary=2.0,
        interbranch_distance=0.5,
    )
    omitted = construct_skeleton(RootSimulationModel(**spec), 42)
    explicit_none = construct_skeleton(
        RootSimulationModel(**dict(spec, research_primary_design=None)), 42
    )
    assert "research_primary_design" not in omitted.payload["parameters"]
    from tests.portable_hash_cases import historical_payload
    from tests.hash_failure_diagnostics import canonical_bytes

    reference = historical_payload(tmp_path, "pre_primary_design", ["initial"])
    try:
        assert canonical_bytes(omitted.payload) == canonical_bytes(reference), "INITIAL payload disagrees with historical reference"
        assert omitted.sha256 == explicit_none.sha256
    except AssertionError:
        from tests.hash_failure_diagnostics import record_failure

        record_failure(
            "inactive-primary-design",
            {
                "omitted": omitted.payload,
                "explicit_none": explicit_none.payload,
                "reference": reference,
            },
            "87b5eae47aff0685b192fb8a4734664d00c601ba9ca69dbbcacf29ba3edd8b90",
        )
        raise


@pytest.mark.parametrize("maximum", [4, 5])
def test_explicit_primary_design_native_higher_orders_keep_required_assumptions(
    maximum,
):
    from tests.test_order5_core import parameters

    entries = invented_entries()[:2]
    p = parameters(
        False,
        max_order=maximum,
        soil_surface_z_cm=0.0,
        research_root_counts_by_order={
            order: count
            for order, count in {1: 2, 2: 3, 3: 4, 4: 2, 5: 1}.items()
            if order <= maximum
        },
        research_higher_order_tropism={
            order: dict(
                theta_deg=25.0, theta_sd_deg=0.0, probability_down=1.0, trials=0.5
            )
            for order in range(4, maximum + 1)
        },
        research_current_length_cdfs_cm={
            order: dict(lengths_cm=[float(7 - order)], cumulative_probabilities=[1.0])
            for order in range(2, maximum + 1)
        },
        research_base_origin_x_cm=0.0,
        research_base_origin_y_cm=0.0,
        research_base_depth_cm=50.0,
        research_primary_design=entries,
        research_primary_yaw_mean_deg=None,
        research_primary_yaw_kappa=None,
        research_primary_inclination_bias=None,
    )
    simulation = RootSystemSimulation(random_seed=42)
    simulation.run(p)
    nodes, edges = simulation.G.as_df()
    validate_geometry(nodes, edges, 0.0)
    assert nodes.order.max() == maximum
    assert (
        nodes.loc[nodes.order.gt(0)].groupby("order").organ_id.nunique().to_dict()
        == p.research_root_counts_by_order
    )
    for organ, entry in zip(simulation.organs[1], entries):
        assert organ.get_lengths().sum() == pytest.approx(entry["length_cm"], abs=1e-12)
    p.research_higher_order_tropism = None
    with pytest.raises(ValueError, match="higher-order"):
        RootSystemSimulation(random_seed=42).init_organs(p)
