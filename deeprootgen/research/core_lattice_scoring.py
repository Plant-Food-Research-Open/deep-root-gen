"""Opt-in lattice core score: simulated vines against soil-core root length density.

A research operator, not a qualification. Observed increments and the simulated
graph are compared in one root-diameter band on both sides: simulated length
counts only on graph segments whose constant child diameter d satisfies
``band_mm[0] < 10 d <= band_mm[1]`` (exact straight-segment / finite-cylinder
intersection, ``core_observation``). Each simulated vine is summed over a
translated lattice of planting positions, so one seed represents a periodic
planting; per-offset contributions are retained so that neighbours can instead
be taken from other seeds (``independent_loss``).

The loss is ``score_core_placement`` on caller-defined whole-core folds, using
each fold's training cores for normalisation, averaged over folds and then
seeds. A penalised objective adds kilograms outside a dry-mass band and
mean-RLD ratio units outside a band; guards are reported, never imposed here.
Core coordinates are mapped into the model frame by a declared column/sign
mapping; no other coordinate conversion is inferred. Cores listed as excluded
(for example a frozen hold-out) are rejected if they appear in the table.
"""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

VERSION = "core-lattice-score-v1"


def assign_folds(core_ids, strata, k, seed):
    """Deal whole cores to k folds: seeded order within each stratum, round-robin across strata."""
    present = set(core_ids)
    listed = [c for group in strata for c in group]
    if len(listed) != len(set(listed)) or set(listed) != present:
        raise ValueError("Fold strata must list every scored core exactly once")
    rng = np.random.default_rng(seed)
    fold, n = {}, 0
    for group in strata:
        for core in rng.permutation(list(group)):
            fold[str(core)] = n % k
            n += 1
    return fold


def load_cores(spec, root):
    """Scored increments with model-frame coordinates, folds and ``rld_est``."""
    c = spec["cores"]
    path = Path(root) / c["path"]
    table = pd.read_csv(path)
    for column, value in (c.get("filter") or {}).items():
        table = table[table[column].eq(value)]
    table = table.reset_index(drop=True)
    columns = dict(core_id="core_id", rld="rld_cm_per_cm3", z_lower="z_lower_cm", z_upper="z_upper_cm",
                   radius="radius_cm", **(c.get("columns") or {}))
    excluded = set(c.get("exclude_cores") or [])
    if table[columns["core_id"]].isin(excluded).any():
        raise ValueError("An excluded core appears in the scored table")
    frame = c["frame"]
    cores = pd.DataFrame(dict(
        core_id=table[columns["core_id"]].astype(str),
        model_x=frame["model_x"]["sign"] * table[frame["model_x"]["column"]].astype(float),
        model_y=frame["model_y"]["sign"] * table[frame["model_y"]["column"]].astype(float),
        z_lower_cm=table[columns["z_lower"]].astype(float), z_upper_cm=table[columns["z_upper"]].astype(float),
        radius_cm=table[columns["radius"]].astype(float), rld_est=table[columns["rld"]].astype(float),
    ))
    if not np.isfinite(cores.drop(columns="core_id").to_numpy()).all() or (cores.rld_est < 0).any():
        raise ValueError("Scored increments need finite coordinates and nonnegative RLD")
    folds = c["folds"]
    fold = assign_folds(cores.core_id.unique(), folds["strata"], folds["k"], folds["seed"])
    cores["fold"] = cores.core_id.map(fold)
    cores["core_volume_cm3"] = np.pi * cores.radius_cm**2 * (cores.z_upper_cm - cores.z_lower_cm)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return cores, digest


def lattice_offsets(lattice):
    extent = int(lattice.get("extent", 1))
    steps = range(-extent, extent + 1)
    return [(i * float(lattice["x_spacing_cm"]), j * float(lattice["y_spacing_cm"])) for i in steps for j in steps]


def band_support(nodes, edges, band_mm, dry_density_g_cm3=0.45):
    """Qualified segments with ``is_fine`` set to the band, plus order and primary subtree index."""
    from .core_observation import qualify_root_segments

    nodes = nodes.copy()
    nodes["invalid_root"] = nodes.invalid_root.astype(bool)
    ids = nodes.node_id.to_numpy()
    position = {v: i for i, v in enumerate(ids)}
    parent = np.array([position.get(p, -1) for p in nodes.parent_id.to_numpy()])
    root = np.where(parent < 0, np.arange(len(ids)), parent)
    while True:                                   # pointer jumping: each node's own base
        nxt = root[root]
        if np.array_equal(nxt, root):
            break
        root = nxt
    # Distributed origins give one base per primary; each primary subtree is its own plant here.
    nodes["plant_id"] = ids[root]
    lo, hi = band_mm
    support = qualify_root_segments(nodes, edges, coordinate_frame="model", fine_diameter_max_mm=hi,
                                    dry_density_g_cm3=dry_density_g_cm3)
    seg = support.segments.copy()
    seg["is_fine"] = (seg.diameter_cm * 10 > lo) & seg.is_fine
    seg["order"] = seg.child_id.map(dict(zip(nodes.node_id, nodes.order)))
    bases = nodes.order.eq(0)
    seg["primary_index"] = seg.plant_id.map(dict(zip(nodes.node_id[bases], nodes.segment_rank[bases]))) - 1
    return dataclasses.replace(support, segments=seg)


def _core_rows(cores, offsets, radius=None):
    out = []
    for i, r in cores.iterrows():
        for j, (dx, dy) in enumerate(offsets):
            out.append(dict(core_id=f"{i}:{j}", x_cm=r.model_x - dx, y_cm=r.model_y - dy, z_lower_cm=r.z_lower_cm,
                            z_upper_cm=r.z_upper_cm, radius_cm=r.radius_cm if radius is None else radius,
                            sampled=True))
    return pd.DataFrame(out)


def _lengths(support, rows, mask=None):
    from .core_observation import predict_core_observations

    s = support if mask is None else dataclasses.replace(support, segments=support.segments.loc[mask])
    return predict_core_observations(s, rows).cores


def lattice_contributions(support, cores, offsets):
    """Band RLD contributed to each increment by each lattice copy: shape (cores, offsets)."""
    got = _lengths(support, _core_rows(cores, offsets))
    length = got.fine_length_cm.to_numpy().reshape(len(cores), len(offsets))
    return length / cores.core_volume_cm3.to_numpy()[:, None]


def probe_attribution(support, cores, offsets, probes):
    """Band RLD in selected supports by lattice copy, crown group and order, plus nearby carriers."""
    seg = support.segments
    group = np.full(len(seg), "other", dtype=object)
    for label, indices in (probes.get("groups") or {}).items():
        group[seg.primary_index.isin(indices).to_numpy()] = label
    out = {}
    for p in probes.get("supports", []):
        rows = cores[cores.core_id.eq(p["core"]) & (-cores.z_upper_cm >= p["top_cm"])
                     & (-cores.z_lower_cm <= p["bottom_cm"])]
        if rows.empty:
            continue
        volume = float(rows.core_volume_cm3.sum())
        cr = _core_rows(rows, offsets)
        entry = dict(by_offset=(_lengths(support, cr).fine_length_cm.to_numpy()
                                .reshape(len(rows), len(offsets)).sum(0) / volume).tolist())
        for o in sorted(seg.order.dropna().unique()):
            entry[f"order{int(o)}"] = float(_lengths(support, cr, (seg.order == o).to_numpy()).fine_length_cm.sum() / volume)
        for label in set(group):
            entry[f"group_{label}"] = float(_lengths(support, cr, group == label).fine_length_cm.sum() / volume)
        radius = float(probes.get("carrier_radius_cm", 10.0))
        wide = _lengths(support, _core_rows(rows, offsets, radius), (seg.order <= probes.get("carrier_max_order", 3)).to_numpy())
        entry["carrier_total_length_cm"] = float(wide.total_length_cm.sum())
        out[f"{p['core']}_{p['top_cm']}_{p['bottom_cm']}"] = entry
    return out


def fold_scores(pred, cores, objective):
    from .core_placement_cost import score_core_placement

    folds = []
    for k in sorted(cores.fold.unique()):
        held, training = cores[cores.fold.eq(k)], cores[~cores.fold.eq(k)]
        folds.append(score_core_placement(training, held, pd.Series(pred[held.index], index=held.index),
                                          top30_weight=objective.get("top30_weight", 1.0),
                                          cap_multiple=objective.get("cap_multiple")))
    return dict(loss=float(np.mean([f["loss"] for f in folds])),
                c_mae=float(np.mean([0.5 * f["normalized_mae"] for f in folds])),
                c_joint=float(np.mean([0.25 * f["joint_tv"] for f in folds])),
                c_depth=float(np.mean([0.25 * f["depth_tv"] for f in folds])),
                fold_losses=[float(f["loss"]) for f in folds])


def diagnostics(pred, cores, spec):
    obs = cores.rld_est.to_numpy()
    out = dict(mean_ratio=float(pred.mean() / obs.mean()))
    for name, s in (spec.get("supports") or {}).items():
        m = (cores.core_id.isin(s["cores"]) & (-cores.z_upper_cm >= s["top_cm"]) & (-cores.z_lower_cm <= s["bottom_cm"]))
        out[name] = float(pred[m.to_numpy()].mean())
    for name, (num, den) in (spec.get("ratios") or {}).items():
        out[name] = out[num] / max(out[den], 1e-9)
    deep = (-cores.z_upper_cm >= spec.get("deep_top_cm", 90)).to_numpy()
    if (deep & (obs > 0)).any():
        out["deep_recovery"] = float((pred[deep & (obs > 0)] > 0).mean())
    if (deep & (obs == 0)).any():
        out["deep_false_hits"] = float((pred[deep & (obs == 0)] > 0).mean())
    return out


def score_records(records, cores, spec):
    """Aggregate one configuration's per-seed records (seed order) into a trial summary."""
    objective = spec.get("objective") or {}
    ok = [r for r in records if r["status"] == "ok"]
    n = len(records)
    if len(ok) < n:
        return dict(feasible=False, n=n, n_ok=len(ok), J=2.0 + (n - len(ok)) / n,
                    reasons=[r.get("reason", r["status"]) for r in records if r["status"] != "ok"])
    contrib = np.array([np.asarray(r["contributions"], float) for r in ok])        # seeds x cores x offsets
    preds = contrib.sum(axis=2)
    crown = float(spec.get("crown_kg", 0.0))
    per_seed = []
    for r, p in zip(ok, preds):
        per_seed.append(dict(seed=r["seed"], mass_kg=r["root_kg"] + crown, **fold_scores(p, cores, objective),
                             **diagnostics(p, cores, spec)))
    centre = int(np.argmin([abs(dx) + abs(dy) for dx, dy in lattice_offsets(spec["lattice"])]))
    others = [j for j in range(contrib.shape[2]) if j != centre]
    independent = []
    for i in range(len(ok)):
        p = contrib[i, :, centre].copy()
        for k, j in enumerate(others):
            p += contrib[(i + 1 + k) % len(ok), :, j]
        independent.append(fold_scores(p, cores, objective)["loss"])
    t = pd.DataFrame(per_seed)
    mass = t.mass_kg.to_numpy()
    lo, hi = objective.get("mass_band_kg", (-np.inf, np.inf))
    kg_outside = float((np.maximum(0, lo - mass) + np.maximum(0, mass - hi)).mean())
    ens = preds.mean(axis=0)
    ens_diag = diagnostics(ens, cores, spec)
    rlo, rhi = objective.get("ratio_band", (0.0, np.inf))
    ratio_outside = float(max(0.0, rlo - ens_diag["mean_ratio"], ens_diag["mean_ratio"] - rhi))
    loss = float(t.loss.mean())
    # Optional soft locality term: relative violation of the min/max ratio guards (seed-mean prediction).
    excess = 0.0
    for name, rule in (spec.get("guards") or {}).items():
        if isinstance(rule, dict) and f"{name}" in ens_diag:
            value = ens_diag[name]
            if "min" in rule and rule["min"] > 0:
                excess += max(0.0, (rule["min"] - value) / rule["min"])
            if "max" in rule and rule["max"] > 0:
                excess += max(0.0, (value - rule["max"]) / rule["max"])
    summary = dict(
        feasible=True, n=len(ok), loss=loss, loss_sd=float(t.loss.std(ddof=1)) if len(ok) > 1 else 0.0,
        c_mae=float(t.c_mae.mean()), c_joint=float(t.c_joint.mean()), c_depth=float(t.c_depth.mean()),
        ensemble_loss=fold_scores(ens, cores, objective)["loss"], independent_loss=float(np.mean(independent)),
        mass_mean=float(mass.mean()), mass_in_band=int(((mass >= lo) & (mass <= hi)).sum()),
        kg_outside=kg_outside, ratio_outside=ratio_outside,
        locality_excess=excess,
        J=loss + objective.get("kg_weight", 0.0) * kg_outside + objective.get("ratio_weight", 0.0) * ratio_outside
        + objective.get("locality_weight", 0.0) * excess,
        organs=float(np.mean([sum(r["organs"].values()) for r in ok])),
        seconds=float(np.mean([r["seconds"] for r in ok])),
        **{f"ens_{k}": v for k, v in ens_diag.items()},
        **{f"seed_{k}": float(t[k].mean()) for k in ("deep_recovery", "deep_false_hits") if k in t},
    )
    guards = spec.get("guards") or {}
    passed = {}
    for name, rule in guards.items():
        if name == "mass_share":
            passed[name] = summary["mass_in_band"] >= rule * len(ok)
        elif name == "mean_ratio":
            passed[name] = summary["ratio_outside"] == 0
        else:
            value = summary[f"ens_{name}"]
            passed[name] = (value >= rule.get("min", -np.inf)) and (value <= rule.get("max", np.inf))
    summary["guards"] = passed
    summary["all_guards"] = bool(all(passed.values())) if passed else True
    summary["per_seed"] = per_seed
    return summary
