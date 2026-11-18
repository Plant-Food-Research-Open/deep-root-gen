"""Synthetic checks for positive point diameters and shared primary-subtree effects."""

from copy import deepcopy

import numpy as np
import pytest
from pydantic import ValidationError

from deeprootgen.data_model.canonical import RootConfig
from deeprootgen.model import RootSystemSimulation
from deeprootgen.model.cohort_geometry import bounded_draw


def config():
    return dict(
        schema_version=4,
        random_seed=42,
        simulation_tag="point-dimensions",
        parameters=dict(
            max_order=2,
            primary_root_count=2,
            root_tissue_density=0.2,
            segments_per_root=4,
            gravitropism=0.5,
            root_vary=1.0,
            length_reduction=0.5,
        ),
        features={
            "primary_origins": dict(
                enabled=True,
                settings=dict(layout="point", x_cm=0.0, y_cm=0.0, depth_cm=20.0),
            ),
            "lengths": dict(enabled=True, settings=dict(by_order={"1": 6.0, "2": 3.0})),
            "taper": dict(
                enabled=True,
                settings=dict(
                    by_order={
                        "1": dict(base_cm=0.4, tip_cm=0.2),
                        "2": dict(base_cm=0.1, tip_cm=0.05),
                    }
                ),
            ),
            "branching": dict(
                enabled=True,
                settings=dict(
                    by_order={
                        "1": dict(
                            law="first_branch_and_daughter_count",
                            first_branch_cm=dict(mean=0.1, sd=0.0, min=0.1, max=0.1),
                            branch_probability=1.0,
                            daughter_probabilities=[1.0],
                        )
                    }
                ),
            ),
        },
    )


def run(config):
    sim = RootSystemSimulation(random_seed=config["random_seed"])
    sim.run(config)
    return sim


def test_scalar_lengths_and_normal_basal_diameter_round_trip():
    value = config()
    normal = dict(law="truncated_normal", mean=0.35, sd=0.1, min=0.30, max=0.40)
    value["features"]["taper"]["settings"]["by_order"]["1"]["base_cm"] = normal
    decoded = RootConfig.model_validate(value).model_dump(mode="json")
    assert decoded["features"]["lengths"]["settings"]["by_order"]["1"] == 6.0
    sim = run(decoded)
    bases = [p.axis_state.material["base"] for p in sim.organs[1]]
    assert 0.3 <= min(bases) < max(bases) <= 0.4
    assert [p.axis_state.material["tip"] for p in sim.organs[1]] == [0.2, 0.2]
    assert [p.get_lengths().sum() for p in sim.organs[1]] == pytest.approx([6.0, 6.0])
    assert [p.get_lengths().sum() for p in sim.organs[2]] == pytest.approx([3.0, 3.0])
    assert sim.result.metadata["root_summary"]["by_order"][0]["root_count"] == 2
    # Match a reference sequence drawn from the named parent distribution,
    # including rejection at both ends. Rejection sampling never clips tails.
    manual = np.random.default_rng(3)
    draws = iter(manual.normal(0.35, 0.1, 1000))
    expected = [next(x for x in draws if 0.30 <= x <= 0.40) for _ in range(30)]
    rng = np.random.default_rng(3)
    assert [bounded_draw(normal, rng) for _ in expected] == expected


@pytest.mark.parametrize(
    "bad",
    [
        True,
        -0.1,
        {"law": "truncated_normal", "mean": 0.2, "sd": 0.1, "min": 0, "max": 0.3},
    ],
)
def test_invalid_diameter_support_rejected(bad):
    value = config()
    value["features"]["taper"]["settings"]["by_order"]["1"]["base_cm"] = bad
    with pytest.raises(ValidationError):
        RootConfig.model_validate(value)


def test_shared_factor_controls_subtree_length_and_branching_at_equal_basal_diameter():
    value = config()
    value["features"]["cohort_maturity"] = dict(
        enabled=True,
        settings=dict(
            groups=[
                dict(label="large", primary_indices=[0], maturity_range=[1.0, 1.0]),
                dict(label="small", primary_indices=[1], maturity_range=[0.1, 0.1]),
            ],
            length_power=1.0,
            diameter_power=0.0,
            scale_branch_probability=False,
        ),
    )
    both = run(value)
    primaries = both.organs[1]
    assert [p.plan["base"] for p in primaries] == [0.4, 0.4]
    assert [p.get_lengths().sum() for p in primaries] == pytest.approx([6.0, 0.6])
    assert [c.get_lengths().sum() for c in both.organs[2]] == pytest.approx([3.0, 0.3])
    scaled = deepcopy(value)
    scaled["features"]["cohort_maturity"]["settings"]["scale_branch_probability"] = True
    reduced = run(scaled)
    assert [p.plan["base"] for p in reduced.organs[1]] == [0.4, 0.4]
    assert [len(p.child_organs) for p in reduced.organs[1]] == [1, 0]


@pytest.mark.parametrize("field", ["length", "diameter"])
def test_allocation_requires_explicit_authority_to_adjust_a_fixed_dimension(field):
    value = config()
    p = value["parameters"]
    p.update(
        root_ratio_length=0.75,
        allocation_controls={f"{field}_scale_by_order": {"2": [0.5, 2.0]}},
    )
    with pytest.raises(ValueError, match=f"Fixed {field} for order 2"):
        RootConfig.model_validate(value)
    if field == "length":
        value["features"]["lengths"]["settings"]["by_order"]["2"] = {"nominal_cm": 3.0}
    else:
        law = value["features"]["taper"]["settings"]["by_order"]["2"]
        law["base_cm"], law["tip_cm"] = {"nominal_cm": 0.1}, {"nominal_cm": 0.05}
    RootConfig.model_validate(value)
