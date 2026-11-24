"""Independent analytic root-material and bounded-allocation checks."""

from types import SimpleNamespace

import numpy as np
import pytest

from deeprootgen.model.allocation import (
    AllocationFailure,
    MAX_EVALUATIONS,
    TOLERANCE,
    allocate,
)
from deeprootgen.model.material_summary import summarize_root_material


def organ(oid, coords, diameter, *, invalid=False):
    def node(x, d=0.0):
        data = SimpleNamespace(
            x=x,
            y=0.0,
            z=0.0,
            diameter=d,
            organ_id=oid,
            root_tissue_density=0.2,
            invalid_root=invalid,
        )
        return SimpleNamespace(node_data=data)

    return SimpleNamespace(
        parent_node=node(0.0),
        segments=[node(x, diameter) for x in coords],
        invalid_root=invalid,
    )


def test_physical_material_summary_boundaries_and_counts():
    higher = np.nextafter(0.25, np.inf)
    sim = SimpleNamespace(
        organs={
            1: [organ(1, [1.0, 2.0], 0.25), organ(2, [3.0], 0.15, invalid=True)],
            2: [organ(3, [6.0], higher)],
        }
    )
    summary = summarize_root_material(sim, 3, 0.25)
    assert summary["by_order"] == [
        dict(order=1, root_count=1, length_cm=2.0),
        dict(order=2, root_count=1, length_cm=6.0),
        dict(order=3, root_count=0, length_cm=0.0),
    ]
    assert summary["excluded_invalid_root_count"] == 1
    assert summary["diameter_classes"]["at_or_below"]["length_cm"] == 2.0
    assert summary["diameter_classes"]["above"]["length_cm"] == 6.0
    assert summary["achieved_root_ratio_length"] == 0.25
    assert summary["achieved_root_ratio_biomass"] == pytest.approx(0.25)
    empty = summarize_root_material(SimpleNamespace(organs={}), 2, 0.25)
    assert (
        empty["achieved_root_ratio_length"] is None
        and empty["achieved_root_ratio_biomass"] is None
    )


@pytest.mark.parametrize("points", [[6.0], [0.8, 2.4, 3.1, 4.7, 6.0]])
def test_taper_crossing_conserves_class_mass_after_subdivision(points):
    sim = SimpleNamespace(organs={1: [organ(1, points, 0.32)]})
    profile = {1: dict(base=0.4, tip=0.1, midpoint=0.5)}
    summary = summarize_root_material(sim, 1, 0.25, profile)
    classes = summary["diameter_classes"]
    for label, begin, end in [("at_or_below", 0.25, 0.1), ("above", 0.4, 0.25)]:
        assert classes[label]["length_cm"] == pytest.approx(3.0)
        assert classes[label]["dry_biomass_g"] == pytest.approx(
            0.2 * np.pi / 12 * 3 * (begin**2 + begin * end + end**2)
        )


def allocated_stems(length, diameter):
    sim = SimpleNamespace(
        organs={
            1: [organ(1, [200.0], 0.4)],
            2: [organ(2, [400.0 * length[2]], 0.1 * diameter[2])],
        }
    )
    return summarize_root_material(sim, 2, 0.25), sim


CONTROLS = dict(
    length_scale_by_order={"2": [0.5, 3.0]}, diameter_scale_by_order={"2": [0.5, 2.0]}
)


@pytest.mark.parametrize("mass, length", [(None, 0.8), (0.2, None), (0.32, 0.8)])
def test_allocation_meets_targets_with_real_lengths_and_diameters(mass, length):
    chosen, receipt = allocate(mass, length, CONTROLS, allocated_stems)
    check = summarize_root_material(chosen, 2, 0.25)
    assert (
        receipt["status"] == "satisfied"
        and 1 < receipt["evaluations"] <= MAX_EVALUATIONS
    )
    for name, target in receipt["targets"].items():
        assert check[f"achieved_{name}"] == pytest.approx(target, abs=TOLERANCE)
    _, again = allocate(mass, length, CONTROLS, allocated_stems)
    assert again == receipt


def test_infeasible_and_exhausted_are_distinct():
    with pytest.raises(AllocationFailure) as failure:
        allocate(
            0.8,
            0.2,
            CONTROLS,
            lambda *_: pytest.fail("cannot construct an infeasible pair"),
        )
    assert failure.value.receipt["status"] == "infeasible_uniform_density"
    assert failure.value.receipt["evaluations"] == 0
    with pytest.raises(AllocationFailure) as exhausted:
        allocate(None, 1.0, CONTROLS, allocated_stems)
    assert exhausted.value.receipt["status"] == "search_exhausted"
    assert (
        exhausted.value.receipt["best"]["residuals"]["root_ratio_length"] < -TOLERANCE
    )
    assert exhausted.value.receipt["evaluations"] <= MAX_EVALUATIONS


def test_canonical_joint_targets_change_measured_architecture():
    """A real native forest with coarse primaries and fine laterals as two compartments."""
    from copy import deepcopy

    from deeprootgen.model import RootSystemSimulation

    def taper(diameter):
        law = dict(
            mean=diameter, sd=diameter * 0.01, min=diameter * 0.5, max=diameter * 1.5
        )
        return dict(
            law="piecewise_linear_arclength",
            midpoint_diameter_fraction=0.5,
            base_cm=law,
            tip_cm=law,
        )

    def run(config, recorder=None):
        sim = RootSystemSimulation(random_seed=42, simulation_tag="allocation")
        sim.run(config, initial_recorder=recorder)
        return sim

    p = dict(
        max_order=2,
        primary_root_count=2,
        daughters_per_parent=2,
        min_branching_diameter_cm=0.05,
        min_primary_length=6.0,
        max_primary_length=7.0,
        min_lateral_length=2.0,
        max_lateral_length=10.0,
        length_reduction=0.5,
        segments_per_root=3,
        root_vary=1.0,
        interbranch_distance=0.5,
        root_tissue_density=0.2,
        gravitropism=0.5,
        threshold_root_diameter_cm=0.25,
    )
    config = dict(
        schema_version=4,
        random_seed=42,
        simulation_tag="allocation",
        parameters=p,
        features={
            "primary_origins": dict(
                enabled=True,
                settings=dict(layout="point", x_cm=0.0, y_cm=0.0, depth_cm=20.0),
            ),
            "taper": dict(
                enabled=True, settings=dict(by_order={"1": taper(0.4), "2": taper(0.1)})
            ),
        },
    )
    baseline = run(config)
    summary = baseline.result.metadata["root_summary"]
    fine, coarse = (summary["diameter_classes"][k] for k in ("at_or_below", "above"))
    target_config = deepcopy(config)
    target_p = target_config["parameters"]
    for key, scale, field in [
        ("length", 1.5, "length_cm"),
        ("biomass", 1.5 * 1.15**2, "dry_biomass_g"),
    ]:
        expected = scale * fine[field] / (scale * fine[field] + coarse[field])
        assert abs(summary[f"achieved_root_ratio_{key}"] - expected) > TOLERANCE
        target_p[f"root_ratio_{key}"] = expected
    target_p["allocation_controls"] = dict(
        length_scale_by_order={"2": [0.75, 2.0]},
        diameter_scale_by_order={"2": [0.85, 1.3]},
    )
    captures = []
    fitted = run(target_config, lambda *_: captures.append(True))
    assert captures == [True]
    receipt = fitted.result.metadata["allocation"]
    fresh = summarize_root_material(fitted, 2, 0.25)
    for key, target in receipt["targets"].items():
        assert fresh[f"achieved_{key}"] == pytest.approx(target, abs=TOLERANCE)
    assert fresh["by_order"][1]["length_cm"] > summary["by_order"][1]["length_cm"]
    assert receipt["best"]["diameter_scale_by_order"][2] > 1


def test_allocation_rejects_proven_class_support_conflict_before_sampling():
    supports = dict(at_or_below=[0.08, 0.12], above=[0.36, 0.44])
    with pytest.raises(AllocationFailure) as failure:
        allocate(
            0.5,
            0.65,
            CONTROLS,
            lambda *_: pytest.fail("preflight proof"),
            diameter_supports=supports,
        )
    assert failure.value.receipt["status"] == "infeasible_diameter_support"
    assert failure.value.receipt["possible_biomass_fraction_at_target_length"][1] < 0.2
    assert failure.value.receipt["evaluations"] == 0
