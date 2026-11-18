"""Per-organ cohort planning executed by the native simulation owner."""

import copy
import math
from collections import deque
from types import SimpleNamespace
import numpy as np
import pandas as pd
from ..data_model import RootNodeModel, RootEdgeModel, RootTypeModel
from ..utils.tropism import insertion_heading
from ..research.core_observation import qualify_root_segments
from .hgraph import RootSystemGraph
from .execution import SimulationResult
from .cohort_geometry import (
    bounded_draw,
    integrate_curve,
    material_cuts,
    reconcile_interval_lengths,
    taper_diameter,
    equivalent_diameter,
)

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


def _sample_organ(t, c, rng, diagnostics):
    order = t["order"]
    rule = c["orders"][str(order)]
    maturity = t["maturity"]
    length = (
        bounded_draw(rule["length_cm"], rng) * maturity ** c["maturity_length_power"]
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
    return length, base, tip, first_draw, sites


def run_cohort(simulation, config):
    from .root import RootOrgan

    seed = config.random_seed
    older_count, later_count = (
        config.construction.older_count,
        config.construction.later_count,
    )
    if (
        any(type(x) is not int or x < 0 for x in (seed, older_count, later_count))
        or older_count < 1
    ):
        raise ValueError("Integer seed/counts and at least one older primary required")
    c = config.construction.parameters.model_dump()
    if older_count + later_count > c["max_organs"]:
        raise ValueError("Initial primary organ budget exhausted")
    organs, tasks = [], deque()
    simulation._organ_queue = tasks
    simulation.G = RootSystemGraph(create_base=False)
    simulation.G.node_id = 1  # Reserve historical crown ID 0 for the support view.
    simulation.organs = {order: [] for order in range(1, 6)}
    sidecars, live = [], {}
    graph = simulation.G
    objects = {}
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
        data = RootNodeModel(
            parent_id=parent,
            plant_id=1,
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
            simulation_tag=config.simulation_tag,
            root_type=(
                "base"
                if order == 0
                else (
                    "fine"
                    if diameter * 10 <= np.nextafter(c["fine_cutoff_mm"], np.inf)
                    else "structural"
                )
            ),
            order_type=(
                "base" if order == 0 else ("primary" if order == 1 else "secondary")
            ),
        )
        result = graph.add_node(data)
        nid = result.node_data.node_id
        live[nid] = result
        sidecars.append(dict(node_id=nid, primary_tree_id=tree, cohort=cohort))
        if parent >= 0:
            graph.add_edge(RootEdgeModel(parent_id=parent, child_id=nid))
        return nid

    oid = 0
    for index in range(older_count + later_count):
        oid += 1
        rng = stream(oid, 0)
        cohort = "A" if index < older_count else "B"
        maturity = 1.0 if cohort == "A" else float(rng.uniform(*c["later_maturity"]))
        phi = rng.uniform(-np.pi, np.pi)
        radius = c["crown_radius_cm"] * np.sqrt(rng.uniform())
        start = np.array(
            [
                radius * np.cos(phi),
                radius * np.sin(phi),
                -rng.uniform(*c["crown_depth_cm"]),
            ]
        )
        anchor = node(-1, 0, 0, index + 1, start, tree=oid, cohort=cohort)
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

    def realize(t):
        nonlocal oid
        order, organ = t["order"], t["oid"]
        rule, rng = c["orders"][str(order)], stream(organ, 1)
        maturity = t["maturity"]
        length, base, tip, first_draw, sites = _sample_organ(t, c, rng, diagnostics)
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
            length, arc, sites, base, tip, c["fine_cutoff_mm"] / 10, midpoint_fraction
        )
        coords = np.column_stack([np.interp(cuts, arc, points[:, k]) for k in range(3)])
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
        context = SimpleNamespace(
            root_tissue_density=c["dry_density_g_cm3"],
            fine_root_threshold=c["fine_cutoff_mm"] / 10.0,
        )
        native = RootOrgan(
            live[t["parent_node"]],
            context,
            RootTypeModel(
                root_type="structural",
                order_type="primary" if order == 1 else "secondary",
                position_type="cohort",
            ),
            config.simulation_tag,
            rng,
            planned=True,
        )
        native.segments = [live[n] for n in cut_ids[1:]]
        native.base_node = native.segments[0]
        for segment in native.segments:
            segment.organ = native
        native.mass = native.calculate_mass()
        native.cohort = t["cohort"]
        native.maturity = maturity
        if t["parent_organ"]:
            objects[t["parent_organ"]].child_organs.append(native)
        objects[organ] = native
        simulation.organs[order].append(native)
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
                max(int(np.searchsorted(arc, site, side="left")) - 1, 0), len(arc) - 2
            )
            tangent = points[j + 1] - points[j]
            heading = insertion_heading(
                tangent, c["insertion_mean_deg"], c["insertion_sd_deg"], stream(oid, 3)
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

    simulation._realize_organs(tasks, realize)
    graph.bases = [live[n] for n in live if live[n].node_data.order == 0]
    graph.base_node = graph.bases[0]
    graph.organ_id = oid + 1
    nodes, edges = graph.as_df()
    sidecar = pd.DataFrame(sidecars)
    projection = nodes.merge(sidecar, on="node_id", validate="one_to_one")
    projection["plant_id"] = projection.primary_tree_id
    support = qualify_root_segments(
        projection,
        edges,
        coordinate_frame="local-crown-soil0-z-up-cm",
        fine_diameter_max_mm=c["fine_cutoff_mm"],
        dry_density_g_cm3=c["dry_density_g_cm3"],
    )
    diagnostics["root_totals"] = support.whole_system_totals["included"]
    diagnostics["unrepresented_fine_mass_g"] = c.get("unrepresented_fine_mass_g", 0.0)
    diagnostics["combined_with_crown_mass_g"] = (
        sum(o["dry_mass_g"] for o in organs)
        + c["crown_mass_g"]
        + c.get("unrepresented_fine_mass_g", 0.0)
    )
    diagnostics["max_depth_cm"] = float(-nodes.z.min())
    diagnostics["root_below_150cm"] = bool(
        nodes.loc[nodes.order.gt(0), "z"].lt(-150).any()
    )
    simulation.result = SimulationResult(
        metadata=dict(
            schema_version=2,
            execution="cohort_v5",
            seed=seed,
            coordinate_frame="local-crown-soil0-z-up-cm",
            biological_validation=False,
            requested_simulation_tag=config.simulation_tag,
        ),
        organ_table=pd.DataFrame(organs),
        diagnostics=diagnostics,
        node_metadata=sidecar,
        crown_support=dict(
            center_cm=[0.0, 0.0, -c["crown_depth_cm"][0]],
            anchor_ids=[n.node_data.node_id for n in graph.bases],
            dry_mass_g=c["crown_mass_g"],
        ),
    )
