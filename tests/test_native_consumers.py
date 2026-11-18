"""Canonical law consumers and flexibility; invented inputs, no observations."""

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from deeprootgen.archive.resolution import resolve_config
from deeprootgen.archive.simulation import RootSystemSimulation
from tests.test_native_features import BASE, CURVE_1, PLANNED, run, spec, tables


def test_replaced_branch_parameters_are_optional_and_identity_inactive():
    value = spec(branching=None)
    first = run(value)
    for name in ("min_sec_root_num", "max_sec_root_num", "growth_sec_root", "interbranch_distance"):
        value["parameters"].pop(name)
    second = run(value)
    assert tables(first) == tables(second)
    assert first.rng.bit_generator.state == second.rng.bit_generator.state
    assert first.result.metadata["effective_model_sha256"] == second.result.metadata["effective_model_sha256"]
    assert first.result.metadata["supplied_input_sha256"] != second.result.metadata["supplied_input_sha256"]
    assert resolve_config(value).description["consumers"]["min_sec_root_num"]["status"] == "replaced"


def test_last_dimension_toggle_keeps_common_origin_and_corrections():
    value = spec(curvature=dict(by_order={"1": CURVE_1}), taper=dict(by_order={"1": BASE["features"]["taper"]["settings"]["by_order"]["1"]}))
    value["parameters"]["max_order"] = 1
    off = run(value)
    value["features"]["lengths"] = dict(enabled=True, settings=dict(by_order={"1": dict(law="bounded_lognormal", mean=2., sd=0., min=2., max=2.)}))
    on = run(value)
    assert len(on.G.bases) == len(off.G.bases) == 1
    assert on.result.resolved["laws"]["construction"] == "native"
    assert on.result.resolved["laws"]["corrections"] == off.result.resolved["laws"]["corrections"]
    assert on.result.resolved["laws"]["primary_origins"] is None
    for organ in on.organs[1]:
        assert organ.get_lengths().sum() == pytest.approx(2., rel=1e-12)


@pytest.mark.parametrize("field,value", [("radius_cm", 1.), ("depth_range_cm", [0., 20.])])
def test_point_origins_reject_disk_only_fields(field, value):
    with pytest.raises(ValueError, match="does not consume"):
        resolve_config(spec(primary_origins=dict(layout="point", x_cm=0., y_cm=0., depth_cm=1., **{field: value})))


def test_disk_heading_requires_its_actual_primary_consumer():
    from tests.test_native_features import DISK, HEADING
    with pytest.raises(ValueError, match="requires primary curvature"):
        resolve_config(spec(primary_origins=dict(DISK, heading=HEADING), curvature=dict(by_order={"1": CURVE_1})))


def test_cohort_resource_limit_excluded_from_model_identity():
    from tests.test_native_engine import _cohort_config
    config, _ = _cohort_config()
    first = resolve_config(config)
    config["construction"]["parameters"]["max_organs"] *= 2
    second = resolve_config(config)
    assert first.hashes["effective_model_sha256"] == second.hashes["effective_model_sha256"]
    assert first.hashes["supplied_input_sha256"] != second.hashes["supplied_input_sha256"]


def test_optional_native_dimensions_when_every_actual_consumer_is_replaced():
    value = json.loads(Path("tests/fixtures/migration_inputs/design/native_features_fully_replaced.json").read_text())
    sim = run(value)
    assert len(sim.G.bases) == 2
    assert np.isfinite(sim.G.as_df()[0][["x", "y", "z", "diameter", "length"]]).all().all()
    assert all(o.axis_state.birth_contexts for group in sim.organs.values() for o in group)


def test_crown_origins_span_the_buried_trunk_and_keep_default_origin():
    value = spec(primary_origins=dict(layout="disk", radius_cm=0., depth_range_cm=[0., 20.]))
    depths = []
    for seed in range(8):
        value["random_seed"] = seed
        sim = run(value)
        for primary in sim.organs[1]:
            base = primary.parent_node.node_data
            assert base.x == base.y == 0.
            assert 0. <= -base.z <= 20.
            depths.append(-base.z)
    assert min(depths) < 5. and max(depths) > 15.
    baseline = run(spec())
    assert len(baseline.G.bases) == 1 and baseline.G.base_node.node_data.z == 0.


def test_crown_depths_use_the_declared_soil_surface():
    value = spec(primary_origins=dict(layout="disk", radius_cm=0., depth_range_cm=[0., 20.]))
    value["parameters"]["soil_surface_z_cm"] = 20.
    sim = run(value)
    assert all(0. <= b.node_data.z <= 20. for b in sim.G.bases)


@pytest.mark.parametrize("limit,maximum", [("max_organs", 1), ("max_nodes", 5), ("max_stations", 2)])
def test_small_budgets_fail_before_publishing(limit, maximum, monkeypatch):
    value = spec(curvature=dict(by_order={"1": CURVE_1}))
    value["limits"] = {limit: maximum}
    from deeprootgen.model import hgraph
    calls = []
    original = hgraph.RootSystemGraph.add_node

    def counted(graph, data):
        node = original(graph, data)
        calls.append(node)
        return node
    monkeypatch.setattr(hgraph.RootSystemGraph, "add_node", counted)
    simulation = RootSystemSimulation(random_seed=42)
    with pytest.raises(ValueError, match="limit exceeded"):
        simulation.run(value)
    assert simulation.result is None
    if limit == "max_nodes":
        assert len(calls) <= maximum
    if limit == "max_organs":
        assert sum(map(len, simulation.organs.values())) <= maximum


def test_frozen_reference_preflight(tmp_path):
    from tests.public_checkpoint_reference import FIXTURES, materialize_reference
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    for name in manifest["references"]:
        assert materialize_reference(Path.cwd(), tmp_path, name).is_dir()


def canonical_from_flat(p):
    """Boundary translation for matched invented adapter/canonical probes."""
    from deeprootgen.data_model.features import TOP_LEVEL_OWNED, NOT_CONSUMED_BY_STATIC_RUN, OBSERVATION_SETTINGS, RESEARCH_ALIASES
    from deeprootgen.data_model.native_options import OWNERS
    data = p.model_dump()
    value = dict(schema_version=3, random_seed=p.random_seed, simulation_tag=p.simulation_tag,
                 parameters={k: v for k, v in data.items() if k not in TOP_LEVEL_OWNED + NOT_CONSUMED_BY_STATIC_RUN + OBSERVATION_SETTINGS + RESEARCH_ALIASES}, features={})
    for owner, fields in OWNERS.items():
        settings = {public: data[internal] for public, internal in fields.items() if data.get(internal) is not None}
        if owner == "branch_sites" and settings.get("placement") == "legacy_spacing":
            settings.pop("placement")
        for key in ("counts_by_order", "row_axial_kappa_by_order", "sigma_by_order", "higher_order_tropism"):
            if settings.get(key) is not None:
                settings[key] = {str(k): v for k, v in settings[key].items()}
        if settings:
            value["features"][owner] = dict(enabled=True, settings=settings)
    if p.research_base_depth_cm is not None:
        value["features"]["primary_origins"] = dict(enabled=True, settings=dict(
            layout="point", x_cm=p.research_base_origin_x_cm, y_cm=p.research_base_origin_y_cm,
            depth_cm=p.research_base_depth_cm))
    if p.research_current_length_cdfs_cm is not None:
        value["features"]["lengths"] = dict(enabled=True, settings=dict(by_order={str(k): dict(law="discrete_cdf", **v.model_dump()) for k, v in p.research_current_length_cdfs_cm.items()}))
    if p.research_current_length_grid is not None:
        direction = value["features"].setdefault("direction", dict(enabled=True, settings={}))
        direction["settings"].update(stationing="construction_steps_v1", boundary="minimum_angle_projection", primary_correction="frozen_surface_check", post_correction="pure_surface_check")
    return value


@pytest.mark.parametrize("updates", [
    dict(research_primary_yaw_mean_deg=20., research_primary_yaw_kappa=3., research_primary_yaw_reverse_probability=.5),
    dict(research_primary_inclination_bias=.2),
    dict(research_insertion_row_axial_kappa={2: 2., 3: 1.}),
    dict(research_fichtl_sigma_by_order={2: .2, 3: .3}),
])
def test_canonical_leaf_controls_match_flat_adapter_tables_and_rng(updates):
    from deeprootgen.data_model import RootSimulationModel
    from tests.test_native_engine import flat_equivalent
    p = flat_equivalent(spec()).model_copy(update=updates)
    p = RootSimulationModel(**p.model_dump())
    sim = RootSystemSimulation(random_seed=p.random_seed, simulation_tag=p.simulation_tag)
    sim.run(p)
    canonical = run(canonical_from_flat(p))
    assert tables(canonical) == tables(sim)
    assert canonical.rng.bit_generator.state == sim.rng.bit_generator.state


def test_explicit_primary_design_is_available_canonically():
    from tests.test_primary_design import settings
    p = settings()
    canonical = run(canonical_from_flat(p))
    sim = RootSystemSimulation(random_seed=p.random_seed, simulation_tag=p.simulation_tag)
    sim.run(p)
    assert tables(canonical) == tables(sim)
    assert canonical.rng.bit_generator.state == sim.rng.bit_generator.state


@pytest.mark.parametrize("grid", [False, True])
def test_higher_order_counts_lengths_directions_match_historical_adapters(grid):
    from tests.test_order5_core import parameters
    from deeprootgen.data_model import RootSimulationConfig
    from deeprootgen.archive.resolution import SO4_INTERNAL_TAG
    p = parameters(grid)
    if grid:
        p = p.model_copy(update=dict(simulation_tag=SO4_INTERNAL_TAG))
    source = (dict(schema_version=2, random_seed=p.random_seed, simulation_tag=p.simulation_tag,
                   trajectory="construction_steps_v1", construction=dict(kind="native", parameters=p.model_dump()))
              if grid else p)
    sim = RootSystemSimulation(random_seed=p.random_seed, simulation_tag=p.simulation_tag)
    sim.run(source)
    canonical = run(canonical_from_flat(p))
    import pandas as pd
    a, ae = canonical.G.as_df()
    b, be = sim.G.as_df()
    # Canonical geometry uses the published parent's incoming tangent, while
    # the historical adapter carries its accepted unit vector. Binary64
    # differences stay within the established geometric tolerance.
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-12, atol=1e-12)
    pd.testing.assert_frame_equal(ae.sort_values(["parent_id", "child_id"]).reset_index(drop=True),
                                  be.sort_values(["parent_id", "child_id"]).reset_index(drop=True))
    assert canonical.rng.bit_generator.state == sim.rng.bit_generator.state
    if grid:
        old, new = sim.result.engine["construction_steps"], canonical.result.engine["construction_steps"]
        assert len(old) == len(new)
        for before, after in zip(old, new):
            assert before["organ_id"] == after["organ_id"] and before["step_index"] == after["step_index"]
            np.testing.assert_allclose(before["accepted_heading"], after["accepted_heading"], rtol=1e-12, atol=1e-12)


def test_construction_steps_compose_with_taper_in_the_common_materializer():
    from tests.test_construction_step_replay import parameters
    value = canonical_from_flat(parameters())
    value["features"]["taper"] = copy.deepcopy(BASE["features"]["taper"])
    value["features"]["taper"]["enabled"] = True
    simulation = run(value)
    assert set(simulation.result.organ_table.material_law) == {"point_taper"}
    assert set(simulation.result.organ_table.query("order > 1").direction_law) == {"construction_step_intervals"}
    assert simulation.result.engine["construction_steps"]


def test_branch_zones_and_sibling_length_rank_have_canonical_consumers():
    from tests.test_tertiary_length_rank import parameters
    p = parameters(strength=.7)
    value = canonical_from_flat(p)
    from deeprootgen.archive.resolution import SO4_INTERNAL_TAG
    p = p.model_copy(update=dict(simulation_tag=SO4_INTERNAL_TAG))
    value["simulation_tag"] = SO4_INTERNAL_TAG
    canonical = run(value)
    sim = RootSystemSimulation(random_seed=p.random_seed)
    sim.run(dict(schema_version=2, random_seed=p.random_seed, trajectory="construction_steps_v1",
                 construction=dict(kind="native", parameters=p.model_dump())))
    import pandas as pd
    pd.testing.assert_frame_equal(canonical.G.as_df()[0], sim.G.as_df()[0], check_exact=False, rtol=1e-12, atol=1e-12)
    assert canonical.rng.bit_generator.state == sim.rng.bit_generator.state


def test_construction_step_sigma_is_an_active_identity_consumer():
    from tests.test_construction_step_replay import parameters
    value = canonical_from_flat(parameters())
    first = run(value)
    value["parameters"]["fichtl_sigma"] = .7
    second = run(value)
    assert tables(first) != tables(second)
    assert first.result.metadata["effective_model_sha256"] != second.result.metadata["effective_model_sha256"]
    value["parameters"].pop("fichtl_sigma")
    with pytest.raises(ValueError, match="missing native parameters"):
        resolve_config(value)


@pytest.mark.parametrize("law", ["zone", "fractions"])
def test_supplied_primary_sites_match_the_native_adapter(law):
    if law == "zone":
        from tests.test_primary_branch_zone import parameters, ZONE
        p = parameters(zone=ZONE)
    else:
        from tests.test_primary_branch_fractions import parameters
        p = parameters(fractions=[.2, .4, .6])
    canonical = run(canonical_from_flat(p))
    historical = RootSystemSimulation(random_seed=p.random_seed, simulation_tag=p.simulation_tag)
    historical.run(p)
    assert tables(canonical) == tables(historical)
    assert canonical.rng.bit_generator.state == historical.rng.bit_generator.state
