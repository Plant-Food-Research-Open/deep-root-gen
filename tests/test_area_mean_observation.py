"""Invented analytic support only; no observations, simulations or objectives."""

import math

import numpy as np
import pandas as pd
import pytest

from deeprootgen.research.area_mean_observation import (
    MATCHED,
    VIRTUAL,
    make_virtual_cores,
    pool_area_mean_observations,
)
from deeprootgen.research.core_observation import (
    predict_core_observations,
    qualify_root_segments,
)


def cores():
    return pd.DataFrame(
        [
            dict(
                core_id="a",
                x_cm=0.0,
                y_cm=0.0,
                z_lower_cm=0.0,
                z_upper_cm=1.0,
                radius_cm=1.0,
                sampled=True,
                known_volume_cm3=np.pi,
            ),
            dict(
                core_id="b",
                x_cm=4.0,
                y_cm=0.0,
                z_lower_cm=0.0,
                z_upper_cm=3.0,
                radius_cm=1.0,
                sampled=True,
                known_volume_cm3=3 * np.pi,
            ),
        ]
    )


def quantities(table, densities=(2.0, 6.0)):
    result = table.copy(deep=True)
    result["length_cm"] = np.asarray(densities) * result.known_volume_cm3.to_numpy(
        float
    )
    result["mass_g"] = result.length_cm * 0.2
    return result


def pool(observed, predicted, groups=None, **changes):
    return pool_area_mean_observations(
        observed,
        predicted,
        {"all": ["a", "b"]} if groups is None else groups,
        quantity_columns=changes.pop("quantity_columns", ["length_cm", "mass_g"]),
        **changes
    )


def test_virtual_geometry_mapping_and_simulation_volume_do_not_modify_observations():
    raw = quantities(cores())
    raw.loc[1, "sampled"] = False
    snapshot = raw.copy(deep=True)
    virtual, mapping, report = make_virtual_cores(raw, 3.0, (0.0, 2.0))
    pd.testing.assert_frame_equal(raw, snapshot, check_exact=True)
    assert virtual.core_id.tolist() == ["a", "b"]
    assert virtual.sampled.tolist() == [True, False]
    np.testing.assert_allclose(virtual.known_volume_cm3, 18 * np.pi, rtol=1e-15)
    np.testing.assert_array_equal(
        mapping.original_known_volume_cm3, raw.known_volume_cm3
    )
    assert mapping.original_z_upper_cm.tolist() == [1.0, 3.0]
    assert mapping.virtual_z_upper_cm.tolist() == [2.0, 2.0]
    assert "length_cm" not in virtual and "mass_g" not in virtual
    assert report["measured_geometry_modified"] is False
    assert report["observed_values_transferred"] is False
    assert report["virtual_overlap_pairs"] == [("a", "b")]
    preserved, _, receipt = make_virtual_cores(raw, 2.0)
    np.testing.assert_array_equal(preserved.z_upper_cm, raw.z_upper_cm)
    assert receipt["depth_band_policy"] == "preserve_original_intervals"


def test_matched_pool_is_sum_additives_over_sum_actual_volumes_not_average_densities():
    observed, predicted = quantities(cores()), quantities(cores(), [4.0, 8.0])
    before = (observed.copy(deep=True), predicted.copy(deep=True))
    result, report = pool(observed, predicted.iloc[::-1].reset_index(drop=True))
    length = result.loc[result.quantity.eq("length_cm")].iloc[0]
    assert length.observed_sampled_volume_cm3 == pytest.approx(4 * np.pi)
    assert length.observed_additive_total == pytest.approx(20 * np.pi)
    assert length.observed_density_per_cm3 == pytest.approx(5.0)
    assert length.predicted_density_per_cm3 == pytest.approx(7.0)
    assert length.predicted_additive_total == pytest.approx(28 * np.pi)
    assert report["same_core_ids_and_sample_masks"]
    assert report["prediction_mode"] == MATCHED
    for actual, expected in zip((observed, predicted), before):
        pd.testing.assert_frame_equal(actual, expected, check_exact=True)


def test_virtual_density_uses_actual_observed_weights_reports_overlap_and_never_union_totals():
    observed = quantities(cores())
    virtual, _, _ = make_virtual_cores(cores(), 3.0, (0.0, 2.0))
    predicted = quantities(virtual, [1.0, 9.0])
    result, report = pool(observed, predicted, prediction_mode=VIRTUAL)
    length = result.loc[result.quantity.eq("length_cm")].iloc[0]
    assert length.observed_density_per_cm3 == pytest.approx(5.0)
    assert length.predicted_density_per_cm3 == pytest.approx(7.0)  # observed weights1:3
    assert length.predicted_equivalent_on_observed_volume == pytest.approx(28 * np.pi)
    assert math.isnan(length.predicted_additive_total)
    assert length.observed_sampled_volume_cm3 == pytest.approx(4 * np.pi)
    assert length.summed_prediction_window_volume_cm3 == pytest.approx(36 * np.pi)
    assert report["predicted_window_overlap_pairs"] == [("a", "b")]
    assert not report["virtual_union_volume_supported"]
    assert not report["virtual_union_additive_totals_supported"]
    assert report["groups"][0]["observed_known_volumes_cm3"] == pytest.approx(
        [np.pi, 3 * np.pi]
    )
    assert report["groups"][0]["predicted_physical_volumes_cm3"] == pytest.approx(
        [18 * np.pi, 18 * np.pi]
    )
    with pytest.raises(ValueError, match="identical geometry"):
        pool(observed, predicted)
    with pytest.raises(ValueError, match="Virtual simulation volumes"):
        pool(predicted, predicted, prediction_mode=VIRTUAL)


def line_support(xy):
    rows = []
    for plant, (x, y) in enumerate(xy):
        base = 2 * plant
        for nid, parent, z, order, label in [
            (base, -1, 0.0, 0, "base"),
            (base + 1, base, -10.0, 1, "fine"),
        ]:
            rows.append(
                dict(
                    node_id=nid,
                    parent_id=parent,
                    plant_id=plant,
                    order=order,
                    x=float(x),
                    y=float(y),
                    z=z,
                    diameter=0.1,
                    root_type=label,
                    invalid_root=False,
                )
            )
    nodes = pd.DataFrame(rows)
    edges = nodes.loc[nodes.order.gt(0), ["parent_id", "node_id"]].rename(
        columns={"node_id": "child_id"}
    )
    return qualify_root_segments(
        nodes,
        edges,
        coordinate_frame="invented-common-frame",
        fine_diameter_max_mm=2.0,
        dry_density_g_cm3=0.1,
    )


def test_uniform_analytic_line_rld_is_invariant_under_expanded_support():
    # Four inner lines and12 annular lines: both chosen cylinders have exactly
    # four lines per pi cm². This is an analytic numerical field, not root data.
    inner = [(x, y) for x in (-0.25, 0.25) for y in (-0.25, 0.25)]
    outer = [
        (1.5 * np.cos(phi), 1.5 * np.sin(phi))
        for phi in np.linspace(0.0, 2 * np.pi, 12, endpoint=False)
    ]
    support = line_support(inner + outer)
    raw = pd.DataFrame(
        [
            dict(
                core_id="uniform",
                x_cm=0.0,
                y_cm=0.0,
                z_lower_cm=-10.0,
                z_upper_cm=0.0,
                radius_cm=1.0,
                sampled=True,
                known_volume_cm3=10 * np.pi,
            )
        ]
    )
    virtual, _, _ = make_virtual_cores(raw, 2.0)
    observed = predict_core_observations(support, raw).cores
    predicted = predict_core_observations(support, virtual).cores
    assert observed.total_length_cm.iloc[0] == pytest.approx(40.0)
    assert predicted.total_length_cm.iloc[0] == pytest.approx(160.0)
    result, _ = pool_area_mean_observations(
        observed,
        predicted,
        {"uniform": ["uniform"]},
        quantity_columns=["total_length_cm"],
        prediction_mode=VIRTUAL,
    )
    assert result.observed_density_per_cm3.iloc[0] == pytest.approx(4 / np.pi)
    assert result.predicted_density_per_cm3.iloc[0] == pytest.approx(4 / np.pi)
    assert result.observed_additive_total.iloc[0] == pytest.approx(40.0)


def test_single_line_expansion_changes_simulation_density_without_diluting_raw_observation():
    support = line_support([(0.0, 0.0)])
    raw = pd.DataFrame(
        [
            dict(
                core_id="line",
                x_cm=0.0,
                y_cm=0.0,
                z_lower_cm=-10.0,
                z_upper_cm=0.0,
                radius_cm=1.0,
                sampled=True,
                known_volume_cm3=10 * np.pi,
            )
        ]
    )
    expanded, _, _ = make_virtual_cores(raw, 2.0)
    observed = predict_core_observations(support, raw).cores
    predicted = predict_core_observations(support, expanded).cores
    result, _ = pool_area_mean_observations(
        observed,
        predicted,
        {"line": ["line"]},
        quantity_columns=["total_length_cm"],
        prediction_mode=VIRTUAL,
    )
    assert result.observed_density_per_cm3.iloc[0] == pytest.approx(1 / np.pi)
    assert result.predicted_density_per_cm3.iloc[0] == pytest.approx(1 / (4 * np.pi))
    assert result.observed_additive_total.iloc[0] == pytest.approx(10.0)


def test_shared_missing_masks_never_impute_zero_and_all_missing_pool_is_missing():
    observed = quantities(cores())
    observed.loc[1, ["sampled", "length_cm", "mass_g"]] = [False, np.nan, np.nan]
    predicted = quantities(cores(), [4.0, 999999.0])
    predicted.loc[1, "sampled"] = False
    # Even caller-stored numeric missing entries are ignored with zero weight.
    result, report = pool(observed, predicted, {"valid": ["a"], "missing": ["b"]})
    valid = result.loc[
        (result.group_id == "valid") & (result.quantity == "length_cm")
    ].iloc[0]
    missing = result.loc[
        (result.group_id == "missing") & (result.quantity == "length_cm")
    ].iloc[0]
    assert valid.observed_density_per_cm3 == pytest.approx(2.0)
    assert valid.predicted_density_per_cm3 == pytest.approx(4.0)
    assert not missing.sampled and missing.sampled_core_count == 0
    assert missing.observed_sampled_volume_cm3 == 0.0
    assert math.isnan(missing.observed_additive_total)
    assert math.isnan(missing.observed_density_per_cm3)
    assert math.isnan(missing.predicted_density_per_cm3)
    assert report["groups"][1]["excluded_missing_core_ids"] == ["b"]
    predicted.loc[1, "sampled"] = True
    with pytest.raises(ValueError, match="sampled masks"):
        pool(observed, predicted)


def test_sampled_empty_core_is_zero_not_missing_and_group_subset_is_explicit():
    observed = quantities(cores(), [0.0, 6.0])
    predicted = quantities(cores(), [0.0, 8.0])
    result, report = pool(observed, predicted, {"empty": ["a"]})
    assert result.sampled.all() and result.sampled_core_count.eq(1).all()
    assert result.observed_density_per_cm3.eq(0).all()
    assert report["ungrouped_core_ids"] == ["b"]


@pytest.mark.parametrize(
    "groups",
    [{"x": ["a"], "y": ["a"]}, {"x": ["a", "a"]}, {"x": ["unknown"]}, {"x": []}, {}],
)
def test_duplicate_overlapping_or_unknown_group_membership_rejected(groups):
    observed = quantities(cores())
    with pytest.raises(ValueError):
        pool(observed, observed, groups)


def test_overlapping_actual_supports_rejected_but_shared_faces_and_tangencies_allowed():
    observed = quantities(cores())
    observed.loc[1, "x_cm"] = 1.0
    with pytest.raises(ValueError, match="Overlapping observed"):
        pool(observed, observed)
    observed.loc[1, "x_cm"] = 2.0
    pool(observed, observed)  # tangent radial boundaries have no overlapping volume
    observed.loc[1, ["x_cm", "z_lower_cm", "z_upper_cm"]] = [0.0, 1.0, 4.0]
    pool(observed, observed)  # adjacent z faces


@pytest.mark.parametrize(
    "radius,band",
    [
        (True, None),
        ("2", None),
        (0.0, None),
        (-1.0, None),
        (np.inf, None),
        (np.nan, None),
        (2.0, 3.0),
        (2.0, (0.0, True)),
        (2.0, (1.0, 1.0)),
        (2.0, (2.0, 1.0)),
        (2.0, (0.0, np.inf)),
    ],
)
def test_virtual_controls_reject_nonfinite_bool_and_inferred_depths(radius, band):
    with pytest.raises(ValueError):
        make_virtual_cores(cores(), radius, band)


@pytest.mark.parametrize(
    "defect",
    [
        "nonfinite",
        "negative",
        "bool_quantity",
        "missing_known_volume",
        "wrong_known_volume",
        "missing_id",
        "sampled_type",
        "duplicate_column",
        "virtual_volume_overflow",
    ],
)
def test_nonfinite_quantities_weights_and_schema_fail_closed(defect):
    observed, predicted = quantities(cores()), quantities(cores())
    if defect == "nonfinite":
        observed.loc[0, "length_cm"] = np.inf
    elif defect == "negative":
        predicted.loc[0, "length_cm"] = -1.0
    elif defect == "bool_quantity":
        observed["length_cm"] = True
    elif defect == "missing_known_volume":
        observed.loc[0, "known_volume_cm3"] = np.nan
    elif defect == "wrong_known_volume":
        observed.loc[0, "known_volume_cm3"] = 99.0
    elif defect == "missing_id":
        predicted = predicted.iloc[:1]
    elif defect == "sampled_type":
        observed["sampled"] = 1
    elif defect == "duplicate_column":
        observed = pd.concat([observed, observed[["length_cm"]]], axis=1)
    else:
        with pytest.raises(ValueError, match="Virtual support volume"):
            make_virtual_cores(cores(), 1e200)
        return
    with pytest.raises(ValueError):
        pool(observed, predicted)


def test_nonfinite_pooled_density_is_rejected_even_when_additives_and_volumes_are_finite():
    observed = cores().iloc[:1].copy()
    observed["radius_cm"] = 1e-100
    observed["known_volume_cm3"] = np.pi * 1e-200
    observed["length_cm"] = 1e200
    predicted = observed.copy()
    predicted["length_cm"] = 0.0
    with np.errstate(over="ignore", invalid="ignore"), pytest.raises(
        ValueError, match="Nonfinite"
    ):
        pool_area_mean_observations(
            observed, predicted, {"tiny": ["a"]}, quantity_columns=["length_cm"]
        )


def test_missing_virtual_support_retains_flags_without_inventing_observed_known_volume():
    raw = cores().iloc[:1].copy()
    raw["sampled"] = False
    raw["known_volume_cm3"] = np.nan
    virtual, mapping, receipt = make_virtual_cores(raw, 2.0)
    assert virtual.sampled.tolist() == [False]
    assert virtual.known_volume_cm3.iloc[0] == pytest.approx(4 * np.pi)
    assert math.isnan(mapping.original_known_volume_cm3.iloc[0])
    assert receipt["sampled_core_count"] == 0


def test_matched_pool_avoids_unneeded_overflowing_individual_virtual_densities():
    observed = pd.DataFrame(
        [
            dict(
                core_id="tiny",
                x_cm=0.0,
                y_cm=0.0,
                z_lower_cm=0.0,
                z_upper_cm=1.0,
                radius_cm=1e-100,
                sampled=True,
                known_volume_cm3=np.pi * 1e-200,
                length_cm=1e200,
            ),
            dict(
                core_id="large",
                x_cm=1e101,
                y_cm=0.0,
                z_lower_cm=0.0,
                z_upper_cm=1.0,
                radius_cm=1e100,
                sampled=True,
                known_volume_cm3=np.pi * 1e200,
                length_cm=0.0,
            ),
        ]
    )
    result, _ = pool_area_mean_observations(
        observed,
        observed.iloc[::-1],
        {"both": ["tiny", "large"]},
        quantity_columns=["length_cm"],
    )
    assert result.observed_density_per_cm3.iloc[0] == pytest.approx(1 / np.pi)
    assert result.predicted_density_per_cm3.iloc[0] == pytest.approx(1 / np.pi)
    assert result.predicted_additive_total.iloc[0] == pytest.approx(1e200)


def test_virtual_pool_matches_ids_and_mixed_known_missing_volumes_with_reversed_rows():
    observed = cores()
    observed["length_cm"] = [2 * np.pi, np.nan]
    observed.loc[1, "sampled"] = False
    observed.loc[1, "known_volume_cm3"] = np.nan
    predicted, _, _ = make_virtual_cores(observed, 2.0)
    predicted["length_cm"] = [4 * np.pi, np.nan]
    result, receipt = pool_area_mean_observations(
        observed,
        predicted.iloc[::-1],
        {"mixed": ["a", "b"]},
        quantity_columns=["length_cm"],
        prediction_mode=VIRTUAL,
    )
    assert result.observed_density_per_cm3.iloc[0] == pytest.approx(2.0)
    assert result.predicted_density_per_cm3.iloc[0] == pytest.approx(1.0)
    assert result.observed_sampled_volume_cm3.iloc[0] == pytest.approx(np.pi)
    assert result.sampled_core_count.iloc[0] == 1
    assert receipt["groups"][0]["excluded_missing_core_ids"] == ["b"]
