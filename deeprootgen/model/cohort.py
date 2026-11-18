"""Historical cohort configuration validation.

Cohort construction runs in the shared engine: sampling and origin/heading
laws in ``model/laws.py``, curvature in ``model/axis_laws.py``, material cuts
and classification in ``model/materialize.py`` and the historical result
serialization in ``model/views.py``. No complete cohort runner remains.
"""

import copy
import math

import numpy as np

from .cohort_geometry import bounded_draw

VERSION = "cohort-root-research-v5"


def _validate_order(rule, config):
    for key in ("curvature_sd_rad_cm", "downward_drift_per_cm"):
        _finite(rule[key], key)
    _finite(rule["correlation_cm"], "correlation length", 1e-12)
    if config["step_cm"] * rule["downward_drift_per_cm"] >= 1:
        raise ValueError("step*drift must be less than one")
    if not 0 < rule.get("midpoint_fraction", 0.5) < 1:
        raise ValueError("Midpoint fraction must be in (0,1)")
    for key in ("length_cm", "base_diameter_cm", "tip_diameter_cm", "first_branch_cm"):
        bounded_draw(rule[key], np.random.default_rng(0))
    if not 0 <= rule["branch_probability"] <= 1:
        raise ValueError("Invalid branch probability")
    probabilities = np.asarray(rule["daughter_probabilities"], float)
    if (
        not np.isfinite(probabilities).all()
        or np.any(probabilities < 0)
        or not np.isclose(sum(probabilities), 1.0, rtol=0, atol=1e-12)
        or not len(probabilities)
    ):
        raise ValueError("Invalid daughter probabilities for counts 1..N")


def _finite(value, name, low=0.0, high=float("inf")):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float, np.number))
        or not np.isfinite(value)
        or not low <= value <= high
    ):
        raise ValueError(f"Invalid {name}")


def validate_cohort_config(config):
    config = copy.deepcopy(config)
    finite = _finite

    for key in (
        "crown_mass_g",
        "unrepresented_fine_mass_g",
        "crown_radius_cm",
        "maturity_length_power",
        "maturity_diameter_power",
        "inclination_sd_deg",
    ):
        if key not in config and key != "unrepresented_fine_mass_g":
            raise ValueError(f"Missing required {key}")
        finite(config.get(key, 0.0), key)
    for key, low, high in [
        ("crown_depth_cm", 0.0, float("inf")),
        ("later_maturity", 0.000001, 1.0),
        ("inclination_bounds_deg", -90.0, 90.0),
    ]:
        values = config[key]
        if len(values) != 2 or values[0] > values[1]:
            raise ValueError(f"Invalid {key}")
        for x in values:
            finite(x, key, low, high)
    finite(
        config["inclination_mean_deg"],
        "inclination mean",
        *config["inclination_bounds_deg"],
    )
    sd = config["inclination_sd_deg"]
    if sd > 0:
        mean = config["inclination_mean_deg"]
        lo, hi = config["inclination_bounds_deg"]

        def cdf(x):
            return 0.5 * math.erfc(-(x - mean) / (sd * math.sqrt(2)))

        if cdf(hi) - cdf(lo) < 0.01:
            raise ValueError("Inclination law accepts less than one percent")
    finite(config["insertion_mean_deg"], "insertion mean", 0.0, 90.0)
    finite(config["insertion_sd_deg"], "insertion SD")
    if type(config.get("reconcile_length_metadata", False)) is not bool:
        raise ValueError("reconcile_length_metadata must be boolean")
    if type(config["max_organs"]) is not int:
        raise ValueError("max_organs must be an integer")
    for key in ("step_cm", "dry_density_g_cm3", "fine_cutoff_mm", "max_organs"):
        if not np.isfinite(config[key]) or config[key] <= 0:
            raise ValueError(f"Invalid {key}")
    if set(config["orders"]) != {"1", "2", "3", "4", "5"}:
        raise ValueError("Explicit order 1..5 rules required")
    if config["crown_mass_g"] < 0 or config.get("unrepresented_fine_mass_g", 0) < 0:
        raise ValueError("Separate mass components must be nonnegative")
    for rule in config["orders"].values():
        _validate_order(rule, config)
    if not 0 < config["child_diameter_fraction_max"] <= 1:
        raise ValueError("Child diameter fraction must be in (0,1]")
    return config
