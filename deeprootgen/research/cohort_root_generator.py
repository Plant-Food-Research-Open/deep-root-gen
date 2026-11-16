"""Opt-in cohort research constructor; caller owns all biological parameters.

See docs/research/COHORT_ROOT_CONSTRUCTION.md. Native defaults are untouched.
"""

from __future__ import annotations

import math
import copy
from collections import deque
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..utils.tropism import _basis, insertion_heading
from ..utils.primary_orientation import proper_rotation
from .curvature_process import ou_joint_step, spherical_exp_heading
from .core_observation import qualify_root_segments

VERSION = "cohort-root-research-v5"


def bounded_draw(spec, rng):
    """Rejection-bounded lognormal; moments refer to pre-truncation law."""
    mean, sd, lo, hi = (float(spec[k]) for k in ("mean", "sd", "min", "max"))
    if not all(np.isfinite([mean, sd, lo, hi])) or not (
        0 < lo <= mean <= hi and sd >= 0
    ):
        raise ValueError("Invalid positive distribution")
    if sd == 0:
        return mean
    if lo == hi:
        raise ValueError("Nonzero SD needs a nonzero admissible interval")
    variance = math.log1p((sd / mean) ** 2)
    mu = math.log(mean) - variance / 2
    cdf = lambda x: 0.5 * math.erfc(-(math.log(x) - mu) / math.sqrt(2 * variance))  # noqa: E731 - local scalar CDF expression
    if cdf(hi) - cdf(lo) < 0.01:
        raise ValueError("Bounded distribution accepts less than one percent")
    for _ in range(10000):
        v = rng.lognormal(math.log(mean) - variance / 2, math.sqrt(variance))
        if lo <= v <= hi:
            return float(v)
    raise ValueError("Bounded distribution exhausted rejection budget")


def taper_diameter(s, length, base, tip, midpoint_fraction=0.5):
    mid = tip + (base - tip) * midpoint_fraction
    return np.interp(np.asarray(s), [0.0, length / 2, length], [base, mid, tip])


def material_cuts(
    length, stations, attachments, base, tip, cutoff, midpoint_fraction=0.5
):
    cuts = [0.0, length, *stations, *attachments]
    if midpoint_fraction != 0.5:
        cuts.append(length / 2)
    mid = tip + (base - tip) * midpoint_fraction
    for a, b, da, db in [(0.0, length / 2, base, mid), (length / 2, length, mid, tip)]:
        if db < cutoff < da:
            cuts.append(a + (b - a) * (da - cutoff) / (da - db))
        elif cutoff == mid and tip < mid < base:
            cuts.append(length / 2)
    cuts = np.unique(np.asarray(cuts, float))
    if (
        not np.isfinite(cuts).all()
        or cuts[0] != 0
        or cuts[-1] != length
        or np.any(np.diff(cuts) <= 1e-12)
    ):
        raise ValueError("Unrepresentable or out-of-range material cuts")
    return cuts


def equivalent_diameter(a, b):
    return np.sqrt((a * a + a * b + b * b) / 3.0)


def integrate_curve(length, start, heading, step, q, ell, downward, rng):
    """Integrate before inserting material/attachment nodes; z-positive up."""
    if not (np.isfinite(length) and length > 0 and np.isfinite(step) and step > 0):
        raise ValueError("Positive finite length/step required")
    start = np.array(start, dtype=float, copy=True)
    heading = np.array(heading, dtype=float, copy=True)
    if (
        start.shape != (3,)
        or heading.shape != (3,)
        or not np.isfinite(start).all()
        or not np.isfinite(heading).all()
        or start[2] > 0
        or np.linalg.norm(heading) <= 1e-12
    ):
        raise ValueError("Finite soil start and nonzero heading required")
    if not np.isfinite(downward) or downward < 0 or step * downward >= 1:
        raise ValueError("Require finite nonnegative drift with step*drift < 1")
    stations = np.arange(0.0, length, step)
    if len(stations) > 1 and length - stations[-1] <= 64 * np.finfo(float).eps * max(
        length, step
    ):
        stations = stations[:-1]
    stations = np.r_[stations, length]
    points = [np.asarray(start, float)]
    heading /= np.linalg.norm(heading)
    frame = np.column_stack(_basis(heading))
    state = np.zeros(2)
    reflections = 0
    for h in np.diff(stations):
        state, turn = ou_joint_step(state, h, q, ell, rng)
        previous_heading = heading.copy()
        heading = spherical_exp_heading(frame, turn)
        heading = heading + h * downward * np.array([0.0, 0.0, -1.0])
        heading /= np.linalg.norm(heading)
        if points[-1][2] + h * heading[2] > 0:
            heading[2] = -abs(heading[2])
            reflections += 1
            state = np.zeros(2)
        frame = proper_rotation(previous_heading, heading) @ frame
        points.append(points[-1] + h * heading)
    return stations, np.asarray(points), reflections


def reconcile_interval_lengths(coords, stored, enabled=False):
    """Bounded metadata reconciliation; never moves geometry or cuts.

    Reject intervals below a 64-epsilon coordinate-scale resolution floor.
    Remaining strict failures are ValueError, not a caller-visible assertion.
    """
    coords = np.asarray(coords, float)
    result = np.asarray(stored, float).copy()
    if (
        type(enabled) is not bool
        or coords.shape != (len(result) + 1, 3)
        or not np.isfinite(coords).all()
        or not np.isfinite(result).all()
        or np.any(result <= 0)
    ):
        raise ValueError("Invalid interval geometry/metadata")
    actual = np.linalg.norm(np.diff(coords, axis=0), axis=1)
    eps = np.finfo(float).eps
    scale = np.linalg.norm(coords[:-1], axis=1) + np.linalg.norm(coords[1:], axis=1)
    floor = 64 * eps * scale
    if np.any(actual <= floor) or np.any(result <= floor):
        raise ValueError("Interval below coordinate-scale resolution floor")
    records = []
    for k in np.flatnonzero(~np.isclose(actual, result, rtol=1e-9, atol=0)):
        if not enabled:
            raise ValueError(
                f"Interval {k} fails strict geometric length; reconciliation disabled"
            )
        error = abs(actual[k] - result[k])
        guard = 64 * eps * (scale[k] + result[k])
        relative = error / min(actual[k], result[k])
        if error > guard:
            raise ValueError(f"Interval {k} exceeds absolute roundoff agreement guard")
        if relative > np.sqrt(eps):
            raise ValueError(f"Interval {k} exceeds relative roundoff agreement guard")
        records.append(
            dict(
                interval=int(k),
                before_cm=float(result[k]),
                after_cm=float(actual[k]),
                absolute_error_cm=float(error),
                relative_error=float(relative),
            )
        )
        result[k] = actual[k]
    np.testing.assert_allclose(actual, result, rtol=1e-9, atol=0)
    return result, records


@dataclass
class CohortArchitecture:
    nodes: pd.DataFrame
    edges: pd.DataFrame
    organs: pd.DataFrame
    observation_nodes: pd.DataFrame
    observation_edges: pd.DataFrame
    diagnostics: dict


class CohortRootGenerator:
    """Static research extension using existing curvature and observation APIs."""

    def __init__(self, config):  # noqa: C901 - explicit research guard and construction branches
        self.config = copy.deepcopy(config)
        config = self.config

        def finite(value, name, low=0.0, high=float("inf")):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float, np.number))
                or not np.isfinite(value)
                or not low <= value <= high
            ):
                raise ValueError(f"Invalid {name}")

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
            cdf = lambda x: 0.5 * math.erfc(-(x - mean) / (sd * math.sqrt(2)))  # noqa: E731 - local scalar CDF expression
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
            for key in ("curvature_sd_rad_cm", "downward_drift_per_cm"):
                finite(rule[key], key)
            finite(rule["correlation_cm"], "correlation length", 1e-12)
            if config["step_cm"] * rule["downward_drift_per_cm"] >= 1:
                raise ValueError("step*drift must be less than one")
            if not 0 < rule.get("midpoint_fraction", 0.5) < 1:
                raise ValueError("Midpoint fraction must be in (0,1)")
            for key in (
                "length_cm",
                "base_diameter_cm",
                "tip_diameter_cm",
                "first_branch_cm",
            ):
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
        if not 0 < config["child_diameter_fraction_max"] <= 1:
            raise ValueError("Child diameter fraction must be in (0,1]")

    def generate(self, seed, older_count, later_count):  # noqa: C901 - explicit research guard and construction branches
        if (
            any(type(x) is not int or x < 0 for x in (seed, older_count, later_count))
            or older_count < 1
        ):
            raise ValueError(
                "Integer seed/counts and at least one older primary required"
            )
        c = self.config
        if older_count + later_count > c["max_organs"]:
            raise ValueError("Initial primary organ budget exhausted")
        rows, edges, organs, tasks = [], [], [], deque()
        diagnostics = dict(
            version=VERSION,
            seed=seed,
            surface_reflections=0,
            diameter_constrained=0,
            tip_constrained=0,
            branch_beyond_tip=0,
            length_metadata_reconciliations=[],
            crown_mass_g=c["crown_mass_g"],
            maturity_is_age_years=False,
        )

        def stream(oid, purpose):
            return np.random.default_rng(np.random.SeedSequence([seed, oid, purpose]))

        def node(
            parent,
            oid,
            order,
            rank,
            point,
            diameter=0.0,
            length=0.0,
            tree=0,
            cohort="crown",
        ):
            nid = len(rows)
            rows.append(
                dict(
                    node_id=nid,
                    parent_id=parent,
                    plant_id=1,
                    primary_tree_id=tree,
                    organ_id=oid,
                    order=order,
                    segment_rank=rank,
                    x=float(point[0]),
                    y=float(point[1]),
                    z=float(point[2]),
                    diameter=float(diameter),
                    length=float(length),
                    root_tissue_density=c["dry_density_g_cm3"],
                    invalid_root=False,
                    root_type=(
                        "base"
                        if order == 0
                        else (
                            "fine"
                            if diameter * 10
                            <= np.nextafter(c["fine_cutoff_mm"], np.inf)
                            else "structural"
                        )
                    ),
                    cohort=cohort,
                )
            )
            if parent >= 0:
                edges.append(dict(parent_id=parent, child_id=nid))
            return nid

        node(-1, 0, 0, 0, [0, 0, -c["crown_depth_cm"][0]])
        oid = 0
        for index in range(older_count + later_count):
            oid += 1
            rng = stream(oid, 0)
            cohort = "A" if index < older_count else "B"
            maturity = (
                1.0 if cohort == "A" else float(rng.uniform(*c["later_maturity"]))
            )
            phi = rng.uniform(-np.pi, np.pi)
            radius = c["crown_radius_cm"] * np.sqrt(rng.uniform())
            start = np.array(
                [
                    radius * np.cos(phi),
                    radius * np.sin(phi),
                    -rng.uniform(*c["crown_depth_cm"]),
                ]
            )
            anchor = node(0, 0, 0, index + 1, start, tree=oid, cohort=cohort)
            # Caller supplies degrees below horizontal; no age inference.
            for _ in range(10000):
                angle = rng.normal(c["inclination_mean_deg"], c["inclination_sd_deg"])
                if (
                    c["inclination_bounds_deg"][0]
                    <= angle
                    <= c["inclination_bounds_deg"][1]
                ):
                    break
            else:
                raise ValueError("Inclination rejection budget exhausted")
            a = np.deg2rad(angle)
            heading = [np.cos(a) * np.cos(phi), np.cos(a) * np.sin(phi), -np.sin(a)]
            tasks.append(
                dict(
                    oid=oid,
                    order=1,
                    parent_node=anchor,
                    parent_organ=0,
                    start=start,
                    heading=heading,
                    maturity=maturity,
                    cohort=cohort,
                    tree=oid,
                    attachment_cm=0.0,
                    parent_diameter=None,
                )
            )
        while tasks:
            t = tasks.popleft()
            order, organ = t["order"], t["oid"]
            rule, rng = c["orders"][str(order)], stream(organ, 1)
            maturity = t["maturity"]
            length = (
                bounded_draw(rule["length_cm"], rng)
                * maturity ** c["maturity_length_power"]
            )
            base = (
                bounded_draw(rule["base_diameter_cm"], rng)
                * maturity ** c["maturity_diameter_power"]
            )
            if t["parent_diameter"] is not None:
                limit = t["parent_diameter"] * c["child_diameter_fraction_max"]
                if base > limit:
                    diagnostics["diameter_constrained"] += 1
                    base = limit
            tip_draw = bounded_draw(rule["tip_diameter_cm"], rng)
            diagnostics["tip_constrained"] += int(tip_draw > base)
            tip = min(tip_draw, base)
            first_draw = bounded_draw(rule["first_branch_cm"], rng)
            sites = []
            if order < 5 and rng.uniform() < rule["branch_probability"] * maturity:
                if first_draw < length:
                    n = int(
                        rng.choice(
                            np.arange(1, len(rule["daughter_probabilities"]) + 1),
                            p=rule["daughter_probabilities"],
                        )
                    )
                    sites = [first_draw]
                    if n > 1:
                        sites += sorted(rng.uniform(first_draw, length, n - 1).tolist())
                else:
                    diagnostics["branch_beyond_tip"] += 1
            arc, points, reflections = integrate_curve(
                length,
                t["start"],
                t["heading"],
                c["step_cm"],
                rule["curvature_sd_rad_cm"],
                rule["correlation_cm"],
                rule["downward_drift_per_cm"],
                stream(organ, 2),
            )
            diagnostics["surface_reflections"] += reflections
            midpoint_fraction = rule.get("midpoint_fraction", 0.5)
            cuts = material_cuts(
                length,
                arc,
                sites,
                base,
                tip,
                c["fine_cutoff_mm"] / 10,
                midpoint_fraction,
            )
            coords = np.column_stack(
                [np.interp(cuts, arc, points[:, k]) for k in range(3)]
            )
            ds = np.diff(cuts)
            try:
                ds, changes = reconcile_interval_lengths(
                    coords, ds, c.get("reconcile_length_metadata", False)
                )
            except ValueError as exc:
                raise ValueError(f"Organ {organ}: {exc}") from exc
            diagnostics["length_metadata_reconciliations"].extend(
                dict(organ_id=organ, **x) for x in changes
            )
            np.testing.assert_allclose(ds.sum(), length, rtol=1e-9, atol=0)
            point_d = taper_diameter(cuts, length, base, tip, midpoint_fraction)
            equiv = equivalent_diameter(point_d[:-1], point_d[1:])
            parent = t["parent_node"]
            cut_ids = [parent]
            for rank, (p, diameter, h) in enumerate(zip(coords[1:], equiv, ds), 1):
                parent = node(
                    parent, organ, order, rank, p, diameter, h, t["tree"], t["cohort"]
                )
                cut_ids.append(parent)
            volume = np.pi / 4 * float(np.dot(ds, equiv**2))
            organs.append(
                dict(
                    organ_id=organ,
                    parent_organ_id=t["parent_organ"],
                    order=order,
                    cohort=t["cohort"],
                    maturity=maturity,
                    primary_tree_id=t["tree"],
                    length_cm=length,
                    base_diameter_cm=base,
                    mid_diameter_cm=float(
                        taper_diameter(length / 2, length, base, tip, midpoint_fraction)
                    ),
                    tip_diameter_cm=tip,
                    first_branch_draw_cm=first_draw,
                    first_branch_cm=sites[0] if sites else np.nan,
                    daughter_count=len(sites),
                    attachment_cm=t["attachment_cm"],
                    volume_cm3=volume,
                    dry_mass_g=volume * c["dry_density_g_cm3"],
                )
            )
            for site in sites:
                oid += 1
                if oid > c["max_organs"]:
                    raise ValueError(
                        "Explicit organ budget exhausted; no silent truncation"
                    )
                i = int(np.searchsorted(cuts, site))
                j = min(
                    max(int(np.searchsorted(arc, site, side="left")) - 1, 0),
                    len(arc) - 2,
                )
                tangent = points[j + 1] - points[j]
                heading = insertion_heading(
                    tangent,
                    c["insertion_mean_deg"],
                    c["insertion_sd_deg"],
                    stream(oid, 3),
                )
                tasks.append(
                    dict(
                        oid=oid,
                        order=order + 1,
                        parent_node=cut_ids[i],
                        parent_organ=organ,
                        start=coords[i],
                        heading=heading,
                        maturity=maturity,
                        cohort=t["cohort"],
                        tree=t["tree"],
                        attachment_cm=site,
                        parent_diameter=float(
                            taper_diameter(site, length, base, tip, midpoint_fraction)
                        ),
                    )
                )
        nodes, edge_table = pd.DataFrame(rows), pd.DataFrame(edges)
        # Each primary tree gets its actual crown anchor as an order-0 base.
        projected = nodes.loc[nodes.node_id.ne(0)].copy()
        projected["plant_id"] = projected.primary_tree_id
        projected.loc[projected.order.eq(0), "parent_id"] = -1
        projected_edges = edge_table.loc[edge_table.parent_id.ne(0)].copy()
        support = qualify_root_segments(
            projected,
            projected_edges,
            coordinate_frame="local-crown-soil0-z-up-cm",
            fine_diameter_max_mm=c["fine_cutoff_mm"],
            dry_density_g_cm3=c["dry_density_g_cm3"],
        )
        diagnostics["root_totals"] = support.whole_system_totals["included"]
        diagnostics["unrepresented_fine_mass_g"] = c.get(
            "unrepresented_fine_mass_g", 0.0
        )
        diagnostics["combined_with_crown_mass_g"] = (
            sum(o["dry_mass_g"] for o in organs)
            + c["crown_mass_g"]
            + c.get("unrepresented_fine_mass_g", 0.0)
        )
        diagnostics["max_depth_cm"] = float(-nodes.z.min())
        diagnostics["root_below_150cm"] = bool(
            nodes.loc[nodes.order.gt(0), "z"].lt(-150).any()
        )
        return CohortArchitecture(
            nodes,
            edge_table,
            pd.DataFrame(organs),
            projected,
            projected_edges,
            diagnostics,
        )
