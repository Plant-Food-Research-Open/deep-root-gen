"""Joint origin selection and geometry checks using invented vine records."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from deeprootgen.data_model import resolve_config
from deeprootgen.model.streams import RandomStreams
from deeprootgen.model.vine_origins import VINE_ORIGIN_STREAM, select_vine_origin
from tests.test_schema4_branching_receipts import document, five_orders, run


def catalogue(entries, mode="sample", **selection):
    return dict(enabled=True, settings=dict(
        layout="vine_catalogue", catalogue_version="vine_origins_v1",
        coordinate_frame="model_soil_cm_v1", selection=dict(mode=mode, **selection), entries=entries,
    ))


def common(entry_id, x, y, depth):
    return dict(entry_id=entry_id, layout="common_point", origin=dict(x_cm=x, y_cm=y, depth_cm=depth))


def primary_layouts(headings=False):
    result = []
    for entry_id, offset in (("field-b", 6.), ("field-a", -3.)):
        points = [dict(index=i, x_cm=offset + i, y_cm=-2 * offset - 3 * i, depth_cm=8. + offset + i)
                  for i in range(3)]
        if headings:
            for i, point in enumerate(points):
                point["heading_unit"] = [.8, 0., -.6] if i % 2 else [0., -.8, -.6]
        result.append(dict(entry_id=entry_id, layout="primary_layout", primaries=points,
                           crown_census_status="complete"))
    return result


def curved_catalogue(headings=False):
    spec = five_orders()
    spec["features"]["primary_origins"] = catalogue(primary_layouts(headings))
    if not headings:
        spec["features"]["curvature"]["settings"]["by_order"]["1"]["initial_heading"] = "scaffold_chord"
    return spec


def test_sample_selects_one_whole_layout_and_is_order_invariant():
    spec = curved_catalogue()
    settings = spec["features"]["primary_origins"]["settings"]
    settings["entries"][0].update(weight=3., provenance=dict(source_frame="invented", comment="trial"))
    initial = deepcopy(spec)
    first = run(spec)
    assert spec == initial
    reordered = deepcopy(spec)
    ordered = reordered["features"]["primary_origins"]["settings"]["entries"]
    ordered.reverse()
    for record in ordered:
        record["primaries"].reverse()
    second = run(reordered)
    for a, b in zip(first.G.as_df(), second.G.as_df()):
        pd.testing.assert_frame_equal(a, b, check_exact=True)
    for key in ("effective_model_sha256", "run_identity_sha256"):
        assert first.result.metadata[key] == second.result.metadata[key]
    assert first.result.metadata["supplied_input_sha256"] != second.result.metadata["supplied_input_sha256"]
    row = first.result.diagnostics["vine_origin_catalogue"]
    other = second.result.diagnostics["vine_origin_catalogue"]
    assert row == other
    selected = row["selected_entry"]
    original = next(record for record in settings["entries"] if record["entry_id"] == selected["entry_id"])
    assert selected["primaries"] == original["primaries"]
    assert row["crown_census_status"] == "complete"
    assert [a["ids"] for a in first.streams.issued if a["namespace"] == VINE_ORIGIN_STREAM] == [[]]
    nodes, _ = first.G.as_df()
    anchors = nodes[nodes.order.eq(0)]
    assert len(anchors) == len(selected["primaries"]) == len(first.organs[1])
    assert (anchors.length == 0).all() and (anchors.diameter == 0).all()
    assert set(nodes.plant_id) == {1}
    assert sorted(row["primary_organ_ids"].values()) == sorted(
        axis.axis_state.biological_id for axis in first.organs[1]
    )
    expected = [[p["x_cm"], p["y_cm"], -p["depth_cm"]] for p in selected["primaries"]]
    np.testing.assert_array_equal(anchors[["x", "y", "z"]].to_numpy(), expected)


def test_fixed_common_point_preserves_geometry_and_uses_no_selection_stream():
    legacy = document("synthetic_minimal")
    legacy["parameters"]["soil_surface_z_cm"] = 20.
    entry = common("point-c", 1., -3., 12.)
    legacy["features"]["primary_origins"] = dict(enabled=True, settings=dict(layout="point", **entry["origin"]))
    spec = deepcopy(legacy)
    other = common("point-d", 5., 8., 7.)
    spec["features"]["primary_origins"] = catalogue([entry, other], mode="fixed", entry_id="point-c")
    a, b = run(legacy), run(spec)
    for left, right in zip(a.G.as_df(), b.G.as_df()):
        pd.testing.assert_frame_equal(left, right, check_exact=True)
    assert a.result.metadata["root_summary"] == b.result.metadata["root_summary"]
    assert a.rng.bit_generator.state == b.rng.bit_generator.state
    assert not any(row["namespace"] == VINE_ORIGIN_STREAM for row in b.streams.issued)
    assert b.result.diagnostics["vine_origin_catalogue"]["normalized_selection_weight"] == 1.
    spec["random_seed"] = None
    assert resolve_config(spec).seed is None
    spec["features"]["primary_origins"]["settings"]["selection"] = {"mode": "sample"}
    with pytest.raises(ValueError, match="explicit random_seed"):
        resolve_config(spec)


def test_sample_weights_and_correlated_coordinates():
    spec = document("synthetic_minimal")
    spec["features"]["primary_origins"] = catalogue([common("B", 5., -6., 12.), common("A", -4., 9., 23.)])
    settings = spec["features"]["primary_origins"]["settings"]
    del settings["selection"]
    resolved = resolve_config(spec)
    assert resolved.laws.origins["weights"] == [.5, .5]
    settings["entries"][0]["weight"] = 3.
    law = resolve_config(spec).laws.origins
    assert law["weights"] == [.25, .75]
    results = [select_vine_origin(law, RandomStreams(seed))[0] for seed in range(800)]
    valid = [row["origin"] for row in settings["entries"]]
    assert all(r["origin"] in valid for r in results)
    # More than four binomial standard errors at n=800.
    assert np.mean([r["entry_id"] == "B" for r in results]) == pytest.approx(.75, abs=.07)


def test_heading_use_and_ownership():
    spec = curved_catalogue(headings=True)
    spec["features"]["curvature"]["settings"]["by_order"]["1"]["curvature_sd_rad_cm"] = 0.
    selected = run(spec)
    origins = selected.result.diagnostics["vine_origin_catalogue"]["selected_entry"]["primaries"]
    for axis, origin in zip(selected.organs[1], origins):
        receipt = axis.axis_state.curve.receipt
        np.testing.assert_allclose(receipt["initial_heading_unit"], origin["heading_unit"], atol=1e-12)
    spec["features"]["primary_placement"] = dict(enabled=True, settings=dict(yaw_mean_deg=30., yaw_kappa=3.))
    with pytest.raises(ValueError, match="headings conflict with primary yaw"):
        resolve_config(spec)


@pytest.mark.parametrize("mutator,reason", [
    (lambda s: s.update(coordinate_frame="scanner"), "coordinate_frame"),
    (lambda s: s["entries"].append(s["entries"][0]), "must be unique"),
    (lambda s: s["entries"][0].update(weight=0.), "greater than 0"),
    (lambda s: s["entries"][0]["primaries"][1].update(index=0), "duplicate primary indices"),
    (lambda s: s["entries"][0]["primaries"].pop(), "exactly primary indices"),
    (lambda s: s["entries"][0]["primaries"][0].update(depth_cm=-1.), "depth_cm"),
    (lambda s: s["entries"][0]["primaries"][0].update(heading_unit=[.8, .6, 0.]), "all headings"),
    (lambda s: s["entries"][0]["primaries"][0].update(heading_unit=[1., 1., 0.]), "unit vector"),
])
def test_incompatible_catalogues_fail_during_resolution(mutator, reason):
    spec = curved_catalogue()
    mutator(spec["features"]["primary_origins"]["settings"])
    with pytest.raises(ValueError, match=reason):
        resolve_config(spec)


def test_provenance_does_not_change_the_effective_catalogue():
    config = curved_catalogue()
    original = resolve_config(config)
    entries = config["features"]["primary_origins"]["settings"]["entries"]
    entries[0]["provenance"] = dict(source_frame="invented", conversion_version="test", comment="label")
    after = resolve_config(config)
    assert original.hashes["effective_model_sha256"] == after.hashes["effective_model_sha256"]
    assert original.hashes["supplied_input_sha256"] != after.hashes["supplied_input_sha256"]
