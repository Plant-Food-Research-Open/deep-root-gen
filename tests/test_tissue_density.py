from math import exp, log, pi

import numpy as np
import pytest

from deeprootgen.model import RootSystemSimulation
from deeprootgen.model.tissue_density import (
    DiameterDensity,
    GRAPEVINE_STEPPED,
    TaperedAxes,
)
from tests.test_exponential_taper import config


def test_cylinders_exactly_on_each_boundary():
    d = np.array([0.09, 0.1, 0.2, 0.25, 1.2, 3.0, 3.1])
    axes = TaperedAxes(np.ones_like(d), d, d, 0.5, -1.0, 0.0)
    lengths, volumes, masses = axes.band_material(GRAPEVINE_STEPPED)
    np.testing.assert_equal(lengths.sum(axis=1), 1.0)
    np.testing.assert_equal(lengths.argmax(axis=1), [0, 1, 1, 2, 3, 4, 5])
    np.testing.assert_allclose(volumes.sum(axis=1), pi / 4 * d**2)
    np.testing.assert_allclose(
        masses.sum(axis=1), pi / 4 * d**2 * [0.25, 0.30, 0.30, 0.40, 0.45, 0.50, 0.50]
    )


def test_linear_cone_crosses_three_bands_and_has_clippable_volume():
    axes = TaperedAxes([30.0], [0.3], [0.0], [0.5], [-1.0], [0.0])
    lengths, volumes, _ = axes.band_material(GRAPEVINE_STEPPED)
    np.testing.assert_allclose(lengths[0], [10.0, 10.0, 5.0, 5.0, 0.0, 0.0])
    bounds = np.array([0.0, 0.1, 0.2, 0.25, 0.3])
    np.testing.assert_allclose(volumes[0, :4], pi / 4 * 100 / 3 * np.diff(bounds**3))
    # A 4 cm piece of this axis lies wholly inside the 1–2 mm band.
    np.testing.assert_allclose(
        axes.prefix_volume(18.0) - axes.prefix_volume(14.0),
        pi / 4 * 4 * (0.16**2 + 0.16 * 0.12 + 0.12**2) / 3,
    )


def test_exponential_crossings_and_constant_thick_piece():
    axes = TaperedAxes(
        [100.0, 10.0], [1.0, 0.4], [0.08, 0.08], [0.6, 0.5], [0.01, 0.0], [0.4, 0.4]
    )
    np.testing.assert_allclose(axes.prefix_length(0.6), [log(1 / 0.6) / 0.01, 0.0])
    stop = 20.0
    expected = pi / 4 * (1 - exp(-0.02 * stop)) / 0.02
    np.testing.assert_allclose(
        axes.prefix_volume(stop), [expected, pi / 4 * 0.4**2 * 10]
    )
    assert axes.prefix_length(0.4)[1] == 0
    assert axes.prefix_length(0.4, inclusive=True)[1] == 10


def test_measuring_a_real_simulation_preserves_geometry_and_scalar_mass():
    cfg = config()
    sim = RootSystemSimulation(random_seed=cfg["random_seed"])
    with pytest.raises(ValueError, match="Run the simulation"):
        sim.diameter_material()
    sim.run(cfg)
    organ = sim.organs[1][0]
    old = organ.get_coordinates().copy()
    uniform = DiameterDensity((1.0, 2.0, 2.5), (0.4,) * 4, (False, True, True))
    row = sim.diameter_material(uniform)["by_order"][0]
    expected = sim.result.metadata["root_summary"]["diameter_classes"]
    assert sum(row["dry_mass_g"]) == pytest.approx(
        sum(v["dry_biomass_g"] for v in expected.values())
    )
    assert sum(
        sim.diameter_material()["by_order"][0]["fresh_volume_cm3"]
    ) == pytest.approx(sum(row["fresh_volume_cm3"]))
    np.testing.assert_array_equal(old, organ.get_coordinates())


@pytest.mark.parametrize(
    "bounds,densities,flags",
    [
        ((1.0, 1.0), (0.3, 0.4, 0.5), (True, True)),
        ((1.0,), (0.3, np.nan), (True,)),
        ((1.0,), (0.3, 0.4), ()),
    ],
)
def test_invalid_profiles(bounds, densities, flags):
    with pytest.raises(ValueError):
        DiameterDensity(bounds, densities, flags)


def test_configured_bands_drive_node_organ_and_class_mass_without_moving_geometry():
    from dataclasses import asdict

    cfg = config(cutoff=0.25)
    baseline = RootSystemSimulation(random_seed=cfg["random_seed"])
    baseline.run(cfg)
    cfg["parameters"]["root_tissue_density"] = {
        k: list(v) for k, v in asdict(GRAPEVINE_STEPPED).items()
    }
    sim = RootSystemSimulation(random_seed=cfg["random_seed"])
    sim.run(cfg)
    np.testing.assert_array_equal(
        sim.organs[1][0].get_coordinates(), baseline.organs[1][0].get_coordinates()
    )
    row = sim.diameter_material()["by_order"][0]
    mass = sum(row["dry_mass_g"])
    assert sim.organs[1][0].calculate_mass() == pytest.approx(mass)
    assert sim.result.organ_table.mass_g.sum() == pytest.approx(mass)
    classes = sim.result.metadata["root_summary"]["diameter_classes"]
    assert classes["at_or_below"]["dry_biomass_g"] == pytest.approx(
        sum(row["dry_mass_g"][:3])
    )
    assert classes["above"]["dry_biomass_g"] == pytest.approx(
        sum(row["dry_mass_g"][3:])
    )
    nodes = [n.node_data for n in sim.organs[1][0].segments]
    assert sum(
        n.root_tissue_density * n.diameter**2 * pi / 4 * n.length for n in nodes
    ) == pytest.approx(mass)
    assert (
        sim.result.metadata["effective_model_sha256"]
        != baseline.result.metadata["effective_model_sha256"]
    )


def test_allocation_mass_support_accounts_for_heavier_fine_tissue():
    from deeprootgen.model.allocation import _check_material_support

    profile = DiameterDensity((2.5,), (1.0, 0.1), (True,))
    targets = dict(root_ratio_length=0.5, root_ratio_biomass=0.85)
    receipt = {}
    _check_material_support(
        targets, {"at_or_below": [0.2, 0.24], "above": [0.26, 0.3]}, receipt, profile
    )
    low, high = receipt["possible_biomass_fraction_at_target_length"]
    assert low <= 0.85 < high


def test_configured_cylinders_use_point_diameter_boundary_convention():
    from tests.test_canonical_execution import simple

    cfg = simple()
    cfg["parameters"].update(
        base_diameter=0.1,
        apex_diameter=0.1,
        diameter_reduction=0.0,
        root_tissue_density=dict(
            bounds_mm=[1.0], density_g_cm3=[0.2, 0.4], equality_to_finer=[False]
        ),
    )
    sim = RootSystemSimulation(random_seed=cfg["random_seed"])
    sim.run(cfg)
    by_order = sim.diameter_material()["by_order"]
    for row in by_order:
        assert row["dry_mass_g"][0] == 0
        assert row["dry_mass_g"][1] == pytest.approx(
            0.4 * pi / 4 * 0.1**2 * sum(row["length_cm"])
        )
    assert all(
        n.node_data.root_tissue_density == 0.4
        for group in sim.organs.values()
        for organ in group
        for n in organ.segments
    )


def test_target_allocation_evaluates_the_configured_density():
    cfg = config(cutoff=0.6)
    taper = cfg["features"]["taper"]["settings"]["by_order"]["1"]
    for field in ("base_cm", "tip_cm"):
        taper[field] = {"nominal_cm": taper[field]}
    cfg["parameters"]["root_tissue_density"] = dict(
        bounds_mm=[6.0], density_g_cm3=[0.25, 0.5], equality_to_finer=[True]
    )
    original = RootSystemSimulation(random_seed=cfg["random_seed"])
    original.run(cfg)
    initial = original.result.metadata["root_summary"]["achieved_root_ratio_biomass"]
    target = initial + 0.03
    cfg["parameters"].update(
        root_ratio_biomass=target,
        allocation_controls=dict(diameter_scale_by_order={"1": [0.8, 1.2]}),
    )
    fitted = RootSystemSimulation(random_seed=cfg["random_seed"])
    fitted.run(cfg)
    masses = fitted.diameter_material()["by_order"][0]["dry_mass_g"]
    assert masses[0] / sum(masses) == pytest.approx(target, abs=0.01)
    assert fitted.result.metadata["allocation"]["status"] == "satisfied"
