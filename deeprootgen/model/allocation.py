"""Deterministic bounded allocation of lengths and diameters to root-class targets."""

import numpy as np
from scipy.optimize import least_squares
from scipy.stats import qmc


TOLERANCE = 0.01
MAX_EVALUATIONS = 96
ALGORITHM = "bounded-root-allocation-v1"


class AllocationFailure(ValueError):
    """A target or a bounded search failed, with the best attained fractions."""

    def __init__(self, reason, receipt):
        self.receipt = receipt
        super().__init__(f"Root allocation {reason}: {receipt}")


class _Finished(Exception):
    """Stop the numerical optimizer once the published-material test passes."""

    def __init__(self, candidate, point):
        self.candidate = candidate
        self.point = point


def _controls(settings):
    """Collect adjustable bounds in stable length, diameter, numeric order."""
    controls = []
    for kind in ("length", "diameter"):
        table = settings.get(f"{kind}_scale_by_order", {})
        for order, interval in sorted(table.items(), key=lambda item: int(item[0])):
            lo, hi = interval
            if not np.isfinite((lo, hi)).all() or not 0 < lo <= 1 <= hi:
                raise ValueError(
                    "Allocation scale bounds must be finite, positive and include 1"
                )
            if hi > lo:
                controls.append((kind, int(order), np.log((lo, hi))))
    return controls


def allocation_diameter_supports(resolved):
    """Conservative final point-diameter ranges when every order has a taper law.

    Native cylinder inheritance and explicit primary designs have different
    supports. Where this proof does not apply, measure complete candidate forests.
    """
    p, laws = resolved.config.parameters, resolved.laws
    if len(laws.taper) != p.max_order:
        return None
    scales = p.allocation_controls.diameter_scale_by_order
    maturity = laws.maturity
    minimum_maturity = (
        min(g["maturity_range"][0] for g in maturity["groups"]) if maturity else 1.0
    )
    maturity_factor = (
        minimum_maturity ** maturity["diameter_power"] if maturity else 1.0
    )
    supports = []
    for order in range(1, p.max_order + 1):
        law = laws.taper[order]
        base, tip = law["base_cm"], law["tip_cm"]
        low_scale, high_scale = scales.get(str(order), (1.0, 1.0))
        base_min = low_scale * base["min"] * maturity_factor
        base_max = high_scale * base["max"]
        if order > 1 and laws.cap is not None:
            cap = laws.cap["fraction_max"]
            base_min = min(base_min, supports[-1][0] * cap)
            base_max = min(base_max, supports[-1][1] * cap)
        supports.append((min(base_min, low_scale * tip["min"]), base_max))
    threshold = p.threshold_root_diameter_cm
    fine = [(a, min(b, threshold)) for a, b in supports if a <= threshold]
    coarse = [(max(a, threshold), b) for a, b in supports if b > threshold]
    return {
        k: [min(a for a, _ in entries), max(b for _, b in entries)] if entries else None
        for k, entries in [("at_or_below", fine), ("above", coarse)]
    }


def _mass_per_length_bounds(interval, density):
    """Conservative extrema of rho*d² over the attainable diameter interval."""
    lo, hi = interval
    if density is None:
        return lo**2, hi**2
    edges = [0., *(mm / 10 for mm in density.bounds_mm), float("inf")]
    ranges = [(rho * max(lo, start)**2, rho * min(hi, end)**2)
              for start, end, rho in zip(edges, edges[1:], density.density_g_cm3)
              if max(lo, start) <= min(hi, end)]
    return min(a for a, _ in ranges), max(b for _, b in ranges)


def _check_material_support(targets, supports, receipt, density=None):
    if supports is None:
        return
    fine, coarse = supports["at_or_below"], supports["above"]
    receipt["diameter_support_cm"] = supports
    if fine is None or coarse is None:
        value = 1.0 if coarse is None else 0.0
        if any(abs(target - value) > TOLERANCE for target in targets.values()):
            receipt["status"] = "infeasible_diameter_support"
            raise AllocationFailure(
                "infeasible under supplied diameter support", receipt
            )
        return
    if len(targets) != 2:
        return

    def mass_share(length, linear_mass_ratio):
        if length == 1.0:  # Handles an arbitrarily small lower-class diameter.
            return 1.0
        weighted = length * linear_mass_ratio
        return weighted / (weighted + (1.0 - length))

    length, mass = targets["root_ratio_length"], targets["root_ratio_biomass"]
    fine_min, fine_max = _mass_per_length_bounds(fine, density)
    coarse_min, coarse_max = _mass_per_length_bounds(coarse, density)
    lower = mass_share(max(length - TOLERANCE, 0.0), fine_min / coarse_max)
    upper = mass_share(min(length + TOLERANCE, 1.0), fine_max / coarse_min)
    receipt["possible_biomass_fraction_at_target_length"] = [lower, upper]
    if mass < np.nextafter(lower - TOLERANCE, -np.inf) or mass > np.nextafter(
        upper + TOLERANCE, np.inf
    ):
        receipt["status"] = "infeasible_diameter_support"
        raise AllocationFailure("infeasible under supplied diameter support", receipt)


def allocate(
    root_ratio_biomass,
    root_ratio_length,
    allocation_controls,
    evaluate,
    *,
    diameter_supports=None,
    density_profile=None,
):
    """Evaluate full, seeded candidate forests and return (accepted candidate, receipt).

    ``evaluate(length_scales, diameter_scales)`` must start from identical random
    state for each evaluation and return (physical material summary, candidate).
    Only optimizer failures are handled here. Model integrity errors propagate.
    """
    targets = {
        key: value
        for key, value in (
            ("root_ratio_biomass", root_ratio_biomass),
            ("root_ratio_length", root_ratio_length),
        )
        if value is not None
    }
    if not targets or any(
        not np.isfinite(v) or not 0 <= v <= 1 for v in targets.values()
    ):
        raise ValueError("Allocation requires a supplied finite ratio in [0,1]")
    receipt = dict(
        algorithm=ALGORITHM,
        tolerance=TOLERANCE,
        targets=targets,
        evaluations=0,
        max_evaluations=MAX_EVALUATIONS,
        status="search_exhausted",
        best=None,
    )
    if density_profile is None and root_ratio_biomass is not None and root_ratio_length is not None:
        if root_ratio_biomass - root_ratio_length > 2 * TOLERANCE:
            receipt["status"] = "infeasible_uniform_density"
            raise AllocationFailure("infeasible for uniform tissue density", receipt)
    _check_material_support(targets, diameter_supports, receipt, density_profile)
    controls = _controls(allocation_controls)
    if not controls:
        raise ValueError(
            "Supply a nondegenerate allocation scale range with the ratio target"
        )
    lower, upper = np.array([c[2] for c in controls]).T
    original = np.clip((0.0 - lower) / (upper - lower), 0.0, 1.0)
    scores = {}
    best_key = (float("inf"), float("inf"))

    def objective(point):
        nonlocal best_key
        key = tuple(point)
        if key in scores:
            return scores[key]
        if len(scores) >= MAX_EVALUATIONS:
            raise AllocationFailure("search exhausted within scale bounds", receipt)
        length, diameter = {}, {}
        for (kind, order, _), scale in zip(
            controls, np.exp(lower + point * (upper - lower))
        ):
            (length if kind == "length" else diameter)[order] = float(scale)
        if np.array_equal(point, original):
            length, diameter = dict.fromkeys(length, 1.0), dict.fromkeys(diameter, 1.0)
        summary, candidate = evaluate(length, diameter)
        achieved = {name: summary[f"achieved_{name}"] for name in targets}
        residuals = {
            k: None if actual is None else float(actual - targets[k])
            for k, actual in achieved.items()
        }
        # Undefined class fractions are unusable. A finite search penalty allows
        # the deterministic global probes to try a different architecture.
        residual = np.array(
            [2.0 if value is None else value for value in residuals.values()]
        )
        scores[key] = residual
        receipt["evaluations"] = len(scores)
        loss = (
            float(np.max(np.abs(residual))),
            float(np.linalg.norm(point - original)),
        )
        if loss[0] <= TOLERANCE or loss < best_key:
            best_key = loss
            receipt["best"] = dict(
                achieved=achieved,
                residuals=residuals,
                length_scale_by_order=length,
                diameter_scale_by_order=diameter,
                normalized_log_scale_distance=loss[1],
            )
        if loss[0] <= TOLERANCE:
            receipt["status"] = "satisfied"
            raise _Finished(candidate, point.copy())
        return residual

    try:
        objective(original)
        # Try bounds explicitly (important for empty/single-class endpoints),
        # then use bounded least squares on the two measured physical fractions.
        dimension = len(controls)
        probes = [np.zeros(dimension), np.ones(dimension)]
        probes += list(qmc.Halton(dimension, scramble=False).random(8)[1:])
        for point in probes:
            objective(point)
        # A few dispersed restarts handle jumps as a branch or class disappears.
        starts = sorted(scores, key=lambda key: np.linalg.norm(scores[key]))[:4]
        for start in starts:
            least_squares(
                objective,
                np.array(start),
                bounds=(0.0, 1.0),
                diff_step=0.01,
                max_nfev=12,
                xtol=1e-7,
                ftol=1e-7,
                gtol=1e-7,
            )
        raise AllocationFailure("search exhausted within scale bounds", receipt)
    except _Finished as found:
        candidate, good = found.candidate, found.point
    candidate = _contract_toward_baseline(
        objective, candidate, good, original, MAX_EVALUATIONS - len(scores)
    )
    return candidate, receipt


def _contract_toward_baseline(objective, candidate, good, original, evaluations_left):
    # Seek a smaller change along the accepted log-scale direction. Every
    # contraction must satisfy the measured fractions, even if the topology
    # jumps. This is a local preference, with no global-minimum guarantee.
    if not np.array_equal(good, original):
        bad = original
        for _ in range(min(8, evaluations_left)):
            probe = 0.5 * (bad + good)
            try:
                objective(probe)
            except _Finished as found:
                candidate, good = found.candidate, found.point
            else:
                bad = probe
    return candidate
