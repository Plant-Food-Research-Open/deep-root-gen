"""Synthetic verification of conservative distal joins and stepped-density dry mass."""

import copy

import numpy as np
import pytest
from scipy.integrate import quad

from deeprootgen.model.point_taper import point_diameter, thick_end
from deeprootgen.research.proximal_thickening import thicken_proximal_axes


def woody(base, rate, transition):
    return dict(base=base, tip=0.07, midpoint=0.55, rate_per_cm=rate, thick_min_cm=transition)


def inputs():
    source = [woody(1.8, 0.035, 0.5), woody(0.96, 0.018, 0.52),
              woody(1.15, 0.03, 0.5), woody(0.38, 0.02, 0.20),
              woody(0.85, 0.02, 0.28), woody(1.1, 0., 0.55),
              dict(base=0.90, tip=0.11, midpoint=0.44)]
    return dict(profiles=source, length_cm=[83., 14., 52., 18., 21., 25., 29.],
                root_order=[1, 2, 3, 1, 1, 1, 2],
                maximum_base_cm=[2.08, 2.6, 1.8, 0.7, 1.2, 1.6, 1.4],
                parent_site_cm=[np.nan, 1.20, 1.4, np.nan, np.nan, np.nan, 1.3],
                parent_cap_fraction=0.9, coarse_min_cm=.45, max_order=2,
                starting_mass_kg=.7, target_mass_kg=10.,
                density_bounds_cm=[.3, .8, 1.6], density_g_cm3=[.20, .32, .48, .61])


def test_eligibility_original_parent_cap_and_exact_distal_rejoin():
    kw = inputs()
    source = copy.deepcopy(kw["profiles"])
    result = thicken_proximal_axes(**kw)
    assert result.profiles[0]["base"] == pytest.approx(2.08)
    assert result.profiles[1]["base"] == pytest.approx(1.2 * .9)
    assert kw["profiles"] == source
    assert all(out is not old for out, old in zip(result.profiles, source))
    assert result.profiles[2:] == source[2:]
    assert np.all(result.added_mass_kg[:2] > 0)
    np.testing.assert_array_equal(result.added_mass_kg[2:], 0.)
    for old, new, length in zip(source[:2], result.profiles[:2], kw["length_cm"]):
        span = thick_end(old, length)
        assert thick_end(new, length) == pytest.approx(span, abs=1e-13)
        assert new["rate_per_cm"] <= 2 * old["rate_per_cm"]
        stationary = np.linspace(span, length, 53)
        np.testing.assert_allclose(point_diameter(stationary, length, new),
                                   point_diameter(stationary, length, old), atol=2e-14, rtol=0)
        before = np.linspace(0, span, 51, endpoint=False)
        assert np.all(point_diameter(before, length, new) >= point_diameter(before, length, old))
    assert thick_end(source[0], kw["length_cm"][0]) < kw["length_cm"][0]
    assert thick_end(source[1], kw["length_cm"][1]) == kw["length_cm"][1]


def independent_entire_axis_kg(profile, length, breaks, density):
    span = thick_end(profile, length)
    end = profile["base"] * np.exp(-profile["rate_per_cm"] * span)
    transitions = [np.log(profile["base"] / d) / profile["rate_per_cm"]
                   for d in breaks if end < d < profile["base"]]
    # These tests use one exponential and two linear distal pieces. Locate any
    # remaining density crossings by bisection on the measured point diameter.
    from scipy.optimize import brentq
    for d in breaks:
        if point_diameter(length, length, profile) < d < end:
            transitions.append(brentq(lambda x: point_diameter(x, length, profile) - d, span, length))

    def mass_per_cm(s):
        d = point_diameter(s, length, profile)
        return np.pi / 4 * d**2 * density[np.searchsorted(breaks, d)] / 1000
    cuts = np.unique([0., span, (span + length) / 2, length, *transitions])
    return sum(quad(mass_per_cm, a, b, epsabs=1e-13)[0] for a, b in zip(cuts[:-1], cuts[1:]))


def test_full_vine_mass_and_partial_target_against_independent_numerical_integral():
    kw = inputs()
    full = thicken_proximal_axes(**kw)
    cap = full.capacity_kg
    assert 0. < cap < .10
    for f in [0., .17, .68, 1., 1.3]:
        kw["target_mass_kg"] = kw["starting_mass_kg"] + f * cap
        out = thicken_proximal_axes(**kw)
        assert out.final_mass_kg == pytest.approx(kw["starting_mass_kg"] + min(1., f) * cap, abs=1e-13)
        assert out.shortfall_kg == pytest.approx(max(0., f - 1.) * cap, abs=1e-13)
        assert out.capacity_kg == pytest.approx(cap)
        for i in (0, 1):
            params = kw["length_cm"][i], kw["density_bounds_cm"], kw["density_g_cm3"]
            kg1 = independent_entire_axis_kg(out.profiles[i], *params)
            kg0 = independent_entire_axis_kg(kw["profiles"][i], *params)
            assert kg1 - kg0 == pytest.approx(out.added_mass_kg[i], abs=1e-13)
        assert np.all(out.added_mass_kg >= 0)


def test_increase_is_monotone_and_shared_as_a_fraction_of_logarithmic_headroom():
    kw = inputs()
    cap = thicken_proximal_axes(**kw)
    prev = np.zeros(2)
    base = np.array([p["base"] for p in kw["profiles"][:2]])
    full = np.array([p["base"] for p in cap.profiles[:2]])
    for f in np.linspace(.05, .95, 11):
        kw["target_mass_kg"] = kw["starting_mass_kg"] + cap.capacity_kg * f
        step = thicken_proximal_axes(**kw)
        assert np.all(step.added_mass_kg[:2] > prev)
        prev = step.added_mass_kg[:2]
        ends = [p["base"] for p in step.profiles[:2]]
        np.testing.assert_allclose(np.log(ends / base) / np.log(full / base), step.fraction_of_headroom)


@pytest.mark.parametrize("change", [dict(target_mass_kg=.25), dict(max_order=0),
                                    dict(max_base_factor=1), dict(max_rate_factor=1)])
def test_control_and_lower_target_preserve_original_inputs(change):
    kw = {**inputs(), **change}
    out = thicken_proximal_axes(**kw)
    assert out.profiles == kw["profiles"]
    assert out.final_mass_kg == kw["starting_mass_kg"]
    np.testing.assert_array_equal(out.added_mass_kg, 0)


def test_engineering_rate_limit_and_primary_only_control():
    kw = {**inputs(), "max_order": 1, "max_base_factor": 4., "max_rate_factor": 1.04,
          "maximum_base_cm": 5., "density_bounds_cm": [], "density_g_cm3": [.38]}
    out = thicken_proximal_axes(**kw)
    assert out.profiles[0]["rate_per_cm"] == pytest.approx(1.04 * kw["profiles"][0]["rate_per_cm"])
    assert out.profiles[1:] == kw["profiles"][1:]


@pytest.mark.parametrize("change", [
    dict(parent_site_cm=1.), dict(parent_site_cm=np.nan), dict(maximum_base_cm=.1),
    dict(coarse_min_cm=0), dict(density_bounds_cm=[.8, .4, 1.4]),
    dict(density_g_cm3=[.5, .4, .3, .2]), dict(starting_mass_kg=np.nan),
    dict(max_order=3), dict(length_cm=[3.]), dict(root_order=[1.2] * 7),
])
def test_invalid_caps_densities_and_axis_inputs(change):
    with pytest.raises(ValueError):
        thicken_proximal_axes(**{**inputs(), **change})


def test_zero_length_exponential_section_and_empty_cohort():
    kw = inputs()
    kw["profiles"][0] = woody(.60, .04, .60)
    r = thicken_proximal_axes(**{**kw, "max_order": 1})
    assert r.capacity_kg == 0 and r.profiles == kw["profiles"]
    empty = {**kw, "profiles": [], "length_cm": [], "root_order": [], "maximum_base_cm": [], "parent_site_cm": []}
    out = thicken_proximal_axes(**empty)
    assert out.profiles == [] and out.capacity_kg == 0 and out.final_mass_kg == .7


@pytest.mark.parametrize("end_at_join", [True, False])
def test_endpoint_classification_at_machine_precision(end_at_join):
    from math import log
    old = woody(1.4, .04, .65)
    join = (log(old["base"]) - log(old["thick_min_cm"])) / old["rate_per_cm"]
    length = join if end_at_join else np.nextafter(join, np.inf)
    kw = {**inputs(), "profiles": [old], "length_cm": [length], "root_order": [1],
          "maximum_base_cm": 2.5, "parent_site_cm": np.nan}
    new = thicken_proximal_axes(**kw).profiles[0]
    assert (thick_end(new, length) == length) == end_at_join
    assert point_diameter(length, length, new) == pytest.approx(point_diameter(length, length, old))
