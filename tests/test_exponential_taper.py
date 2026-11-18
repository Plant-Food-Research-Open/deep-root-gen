"""Physical material, local branching and canonical serialization for thick roots."""

from math import exp, log, pi

import numpy as np
import pytest

from deeprootgen.data_model import RootConfig
from deeprootgen.model import RootSystemSimulation
from deeprootgen.model.point_taper import point_diameter


def config(length=100., base=1., cutoff=.6):
    return {
        "schema_version": 4,
        "random_seed": 901,
        "parameters": dict(max_order=1, primary_root_count=1, root_tissue_density=.4, root_vary=0., gravitropism=0.,
                           threshold_root_diameter_cm=cutoff),
        "features": {
            "lengths": {"enabled": True, "settings": {"by_order": {"1": length}}},
            "taper": {"enabled": True, "settings": {"by_order": {"1": dict(
                law="exponential_above_diameter", base_cm=base, tip_cm=.08,
                midpoint_diameter_fraction=.5, rate_per_cm=.01, thick_min_cm=.4,
            )}}},
        },
    }


def test_thick_exponential_and_thin_continuation_match_integrated_material():
    length = 100.
    value = RootConfig.model_validate(config(length)).model_dump(mode="json", exclude_none=True)
    model = RootSystemSimulation(random_seed=value["random_seed"])
    model.run(value)
    organ = model.organs[1][0]
    profile = organ.axis_state.material
    join = log(1. / .4) / .01
    at_cutoff = log(1. / .6) / .01
    np.testing.assert_allclose(point_diameter([0., 50., join, length], length, profile),
                               [1., exp(-.5), .4, .08])
    expected_mass = .4 * pi / 4 * (
        (1 - .4**2) / .02 + (length - join) * (.4**2 + .4 * .08 + .08**2) / 3
    )
    expected_coarse_mass = .4 * pi / 4 * (1 - .6**2) / .02
    classes = model.result.metadata["root_summary"]["diameter_classes"]
    assert classes["at_or_below"]["length_cm"] == pytest.approx(length - at_cutoff)
    assert classes["above"]["dry_biomass_g"] == pytest.approx(expected_coarse_mass)
    assert classes["at_or_below"]["dry_biomass_g"] == pytest.approx(expected_mass - expected_coarse_mass)
    nodes = [node.node_data for node in organ.segments]
    exported_mass = sum(node.length * node.diameter**2 * node.root_tissue_density * pi / 4 for node in nodes)
    assert exported_mass == pytest.approx(expected_mass)


@pytest.mark.parametrize("first_branch_cm,born", [(50., True), (99.95, False)])
def test_daughter_uses_physical_parent_diameter(first_branch_cm, born):
    value = config()
    value["parameters"].update(max_order=2, min_branching_diameter_cm=.093)
    features = value["features"]
    features["lengths"]["settings"]["by_order"]["2"] = 4.0
    features["taper"]["settings"]["by_order"]["2"] = dict(base_cm=.7, tip_cm=.07)
    features["parent_diameter_cap"] = {"enabled": True, "settings": {"fraction_max": .9}}
    features["branching"] = {"enabled": True, "settings": {"by_order": {"1": dict(
        law="first_branch_and_daughter_count",
        first_branch_cm=dict(mean=first_branch_cm, sd=0., min=first_branch_cm, max=first_branch_cm),
        branch_probability=1., daughter_probabilities=[1.],
    )}}}
    model = RootSystemSimulation(random_seed=value["random_seed"])
    model.run(value)
    assert len(model.organs[2]) == int(born)
    if born:
        assert model.organs[2][0].axis_state.material["base"] == pytest.approx(.9 * exp(-.5))


@pytest.mark.parametrize("base,rate,end", [(.39, .01, .08), (.4, 0., .4), (1., .01, exp(-.1))])
def test_thin_fallback_and_thick_root_endpoints(base, rate, end):
    value = config(length=10., base=base)
    value["features"]["taper"]["settings"]["by_order"]["1"]["rate_per_cm"] = rate
    model = RootSystemSimulation(random_seed=value["random_seed"])
    model.run(value)
    profile = model.organs[1][0].axis_state.material
    assert point_diameter(10., 10., profile) == pytest.approx(end)
