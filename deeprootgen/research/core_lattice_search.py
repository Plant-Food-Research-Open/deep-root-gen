"""Opt-in search over the lattice core score (``core_lattice_scoring``).

Four stages, all driven by one JSON spec (see docs/research/CORE_LATTICE_SEARCH.md):

* ``arms``    matched comparisons of named parameter settings on common seeds;
* ``space``   a scrambled-Sobol design over the declared parameters, batch-parallel;
* ``tpe``     sequential TPE through ``parameter_search.run_parameter_search``
              (durable, identity-bound trials); its bounds can be narrowed from
              the ``space`` results and weak parameters fixed at the best design;
* ``confirm`` the best TPE candidates and a baseline on more seeds, with paired
              changes, guards and a frozen candidate.

Every simulation runs in-process in a worker with memory and time limits. Each
record carries the canonical configuration SHA-256, seed, imported source
fingerprint, scorer version and cores digest; a cached record is reused only
when all match. A failed run stops the stage; runs over the declared organ,
memory or time limits are recorded as infeasible and penalised. Outputs keep
only per-core contributions and diagnostics, and must stay local when the cores
are private. Parameters are applied as declared edits to a base configuration:
``set`` a value at one or more dot paths, ``scale`` fields of an object against
reference values, or replace an object by a named ``choice``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import resource
import signal
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

from . import core_lattice_scoring as scoring

VERSION = "core-lattice-search-v1"
PREFIX = "search__"
_THREADS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def sha(obj):
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


# --------------------------------------------------------------------------- spec and edits

def load_search_spec(path):
    path = Path(path).resolve()
    spec = json.loads(path.read_text())
    root = path.parent
    base = json.loads((root / spec["base_config"]).read_text())
    cores, cores_sha = scoring.load_cores(spec, root)
    for name, d in spec["parameters"].items():
        if any(c in name for c in ".[]") or d.get("kind") not in ("float", "int", "categorical") or not d.get("edits"):
            raise ValueError(f"Parameter {name!r} needs a plain name, a kind and edits")
    return dict(spec=spec, root=root, base=base, cores=cores, offsets=scoring.lattice_offsets(spec["lattice"]),
                identity=dict(version=VERSION, scorer=scoring.VERSION, spec_sha256=sha(spec),
                              cores_sha256=cores_sha, base_config_sha256=sha(base)))


def _container(obj, tokens, create):
    for t in tokens[:-1]:
        if isinstance(obj, list):
            obj = obj[int(t)]
        else:
            if t not in obj or obj[t] is None:
                if not create:
                    raise KeyError(".".join(map(str, tokens)))
                obj[t] = {}
            obj = obj[t]
    return obj


def _set(config, path, value):
    tokens = path.split(".")
    holder = _container(config, tokens, True)
    key = tokens[-1]
    if isinstance(holder, list):
        holder[int(key)] = value
    else:
        holder[key] = value


def _get(config, path):
    tokens = path.split(".")
    holder = _container(config, tokens, False)
    return holder[int(tokens[-1])] if isinstance(holder, list) else holder[tokens[-1]]


def apply_parameters(config, definitions, values):
    """Apply declared edits; dict keys that are digits stay strings (order keys), list positions are ints.

    ``choice`` edits replace whole objects, so they run first; ``set`` and ``scale`` then refine them,
    whatever order the values arrive in.
    """
    c = copy.deepcopy(config)
    ordered = [(name, value, edit) for phase in ("choice", "other") for name, value in values.items()
               for edit in definitions[name]["edits"] if (edit.get("op", "set") == "choice") == (phase == "choice")]
    for name, value, edit in ordered:
        op = edit.get("op", "set")
        if op == "set":
            for path in edit.get("paths", [edit.get("path")]):
                _set(c, path, value)
        elif op == "scale":
            target = _get(c, edit["path"])
            for field in edit["fields"]:
                target[field] = edit["reference"][field] * value
        elif op == "choice":
            _set(c, edit["path"], copy.deepcopy(edit["values"][str(value)]))
        else:
            raise ValueError(f"Unknown edit op {op!r}")
    return c


# --------------------------------------------------------------------------- execution

def worker_init(memory_gb):
    for key in _THREADS:
        os.environ.setdefault(key, "1")
    if memory_gb:
        limit = int(memory_gb * 2**30)
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def _alarm(signum, frame):
    raise TimeoutError("Run time limit exceeded")


def _simulate(job, record):
    """Heavy part of one run; returns the per-core contributions and diagnostics to merge."""
    from ..model import RootSystemSimulation

    cfg = copy.deepcopy(job["config"])
    cfg["random_seed"] = job["seed"]
    sim = RootSystemSimulation(random_seed=job["seed"])
    sim.run(cfg)
    meta, diag = sim.result.metadata, sim.result.diagnostics
    nodes, edges = sim.G.as_df()
    support = scoring.band_support(nodes, edges, job["band_mm"], job["density"])
    contrib = scoring.lattice_contributions(support, job["cores"], job["offsets"])
    irr = diag.get("irrigation", {})
    out = dict(
        status="ok", invalid=int(meta["root_summary"]["excluded_invalid_root_count"]),
        contributions=contrib.round(10).tolist(),
        root_kg=sum(v["dry_biomass_g"] for v in meta["root_summary"]["diameter_classes"].values()) / 1000,
        organs={str(k): len(v) for k, v in sim.organs.items()},
        terminal_extra=sum(p.get("accepted_extra", 0) for p in irr.get("parents", [])),
        upstream_extra={k: sum(p.get("accepted_extra", 0) for p in u["parents"]) for k, u in irr.get("upstream", {}).items()},
        budget_scale={"terminal": irr.get("budget", {}).get("scale"),
                      **{k: u.get("budget", {}).get("scale") for k, u in irr.get("upstream", {}).items()}},
    )
    if job.get("probes"):
        out["probes"] = scoring.probe_attribution(support, job["cores"], job["offsets"], job["probes"])
    return out


def evaluate_seed(job):
    """Simulate one (configuration, seed) in-process and return per-core lattice contributions.

    The record is built only after any exception has been released, so a run that
    exhausts the worker memory cap is reported as infeasible instead of escaping.
    """
    from ..model.provenance import IMPORT_SOURCE_SHA256

    record = dict(config_sha=job["config_sha"], seed=job["seed"], label=job["label"], source_sha=IMPORT_SOURCE_SHA256,
                  scorer=scoring.VERSION, cores_sha=job["cores_sha"])
    start = time.time()
    outcome, reason, trace = None, None, None
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(int(job["seconds"]))
    try:
        outcome = _simulate(job, record)
    except (MemoryError, TimeoutError) as exc:
        reason = ("infeasible", type(exc).__name__)
    except ValueError as exc:
        text = str(exc)
        reason = ("infeasible" if "limit" in text.lower() else "error", text[:300])
        trace = None if reason[0] == "infeasible" else traceback.format_exc()[-4000:]
    except Exception as exc:
        reason = ("error", repr(exc)[:300])
        trace = traceback.format_exc()[-4000:]
    finally:
        signal.alarm(0)
    if outcome is not None:
        record.update(outcome)
        if record["invalid"]:
            record.update(status="infeasible", reason=f"{record['invalid']} invalid roots")
    else:
        record.update(status=reason[0], reason=reason[1])
        if trace:
            record["traceback"] = trace
    record["seconds"] = time.time() - start
    return record


class Runner:
    """Process pool plus the identity-checked result cache of one output directory."""

    def __init__(self, ctx, outdir, log=print):
        from concurrent.futures import ProcessPoolExecutor
        from ..model.provenance import IMPORT_SOURCE_SHA256

        self.ctx, self.outdir, self.log = ctx, Path(outdir), log
        self.source_sha = IMPORT_SOURCE_SHA256
        limits = ctx["spec"].get("limits", {})
        self.workers, self.seconds = int(limits.get("workers", 4)), float(limits.get("seconds", 1800))
        self.pool = ProcessPoolExecutor(self.workers, initializer=worker_init, initargs=(limits.get("memory_gb"),))

    def close(self):
        self.pool.shutdown(cancel_futures=True)

    def run(self, stage, configs, seeds, probes=False):
        from concurrent.futures import as_completed

        spec, cores_sha = self.ctx["spec"], self.ctx["identity"]["cores_sha256"]
        (self.outdir / "configs").mkdir(parents=True, exist_ok=True)
        jobs, have = [], {}
        for label, cfg in configs.items():
            cs = sha(cfg)
            (self.outdir / "configs" / f"{cs}.json").write_text(json.dumps(cfg, indent=1))
            for seed in seeds:
                path = self.outdir / stage / "results" / cs / f"{seed}.json"
                if path.exists():
                    rec = json.loads(path.read_text())
                    if (rec.get("source_sha") == self.source_sha and rec.get("config_sha") == cs and rec.get("seed") == seed
                            and rec.get("scorer") == scoring.VERSION and rec.get("cores_sha") == cores_sha
                            and rec.get("status") in ("ok", "infeasible") and (not probes or "probes" in rec or rec["status"] != "ok")):
                        have[(label, seed)] = dict(rec, label=label)
                        continue
                jobs.append(dict(config=cfg, config_sha=cs, seed=seed, label=label, cores=self.ctx["cores"],
                                 cores_sha=cores_sha, offsets=self.ctx["offsets"], band_mm=spec["band_mm"],
                                 density=spec.get("dry_density_g_cm3", 0.45), seconds=self.seconds,
                                 probes=spec.get("probes") if probes else None))
        self.log(f"[{stage}] {len(have)} cached, {len(jobs)} to run on {self.workers} workers")
        futures = {self.pool.submit(evaluate_seed, j): j for j in jobs}
        for n, fut in enumerate(as_completed(futures), 1):
            try:
                rec = fut.result()
            except MemoryError:               # the worker could not even report: count it infeasible
                j = futures[fut]
                rec = dict(config_sha=j["config_sha"], seed=j["seed"], label=j["label"], source_sha=self.source_sha,
                           scorer=scoring.VERSION, cores_sha=cores_sha, status="infeasible",
                           reason="MemoryError in worker", seconds=0.0)
            if rec["source_sha"] != self.source_sha:
                raise RuntimeError("Worker source fingerprint differs from the controller")
            path = self.outdir / stage / "results" / rec["config_sha"] / f"{rec['seed']}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(rec))
            have[(rec["label"], rec["seed"])] = rec
            if rec["status"] == "error":
                for f in futures:
                    f.cancel()
                raise RuntimeError(f"Run failed: {rec['label']} seed {rec['seed']}: {rec['reason']}\n"
                                   f"{rec.get('traceback', '')}")
            if n % 10 == 0 or n == len(jobs):
                self.log(f"[{stage}] {n}/{len(jobs)} runs; last {rec['label']} {rec['seed']} {rec['status']} "
                         f"{rec['seconds']:.0f}s")
        return {label: [have[(label, s)] for s in seeds] for label in configs}


# --------------------------------------------------------------------------- summaries

def summarise(ctx, outdir, stage, values, records, baseline=None):
    rows, per_seed, probes = [], [], []
    for label, recs in records.items():
        s = scoring.score_records(recs, ctx["cores"], ctx["spec"])
        rows.append(dict(label=label, **{k: v for k, v in s.items() if k not in ("per_seed", "guards")},
                         **{f"guard_{k}": v for k, v in (s.get("guards") or {}).items()},
                         **{f"p_{k}": v for k, v in values[label].items()}))
        for ps in s.get("per_seed", []):
            per_seed.append(dict(label=label, **{k: v for k, v in ps.items() if k != "fold_losses"},
                                 **{f"fold{i}": v for i, v in enumerate(ps["fold_losses"])}))
        for r in recs:
            for key, e in (r.get("probes") or {}).items():
                focal = int(np.argmin([abs(dx) + abs(dy) for dx, dy in ctx["offsets"]]))
                probes.append(dict(label=label, seed=r["seed"], probe=key, focal=e["by_offset"][focal],
                                   neighbours=sum(e["by_offset"]) - e["by_offset"][focal],
                                   **{k: v for k, v in e.items() if k != "by_offset"}))
    t = pd.DataFrame(rows).set_index("label")
    ps = pd.DataFrame(per_seed)
    if baseline is not None and baseline in t.index and not ps.empty:
        base = ps[ps.label.eq(baseline)].set_index("seed")
        for label in t.index:
            mine = ps[ps.label.eq(label)].set_index("seed")
            if mine.empty:
                continue
            d = (mine.loss - base.loss).dropna()
            t.loc[label, "paired_dloss"] = d.mean()
            t.loc[label, "paired_sd"] = d.std(ddof=1) if len(d) > 1 else 0.0
            t.loc[label, "seeds_better"] = int((d < 0).sum())
            for c in ["c_mae", "c_joint", "c_depth"] + [f"fold{i}" for i in range(4)]:
                if c in mine and c in base:
                    t.loc[label, f"d_{c}"] = (mine[c] - base[c]).dropna().mean()
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    t.to_csv(out / f"{stage}_summary.csv")
    ps.to_csv(out / f"{stage}_per_seed.csv", index=False)
    if probes:
        pd.DataFrame(probes).to_csv(out / f"{stage}_probes.csv", index=False)
    return t, ps


# --------------------------------------------------------------------------- stages

def run_arms(ctx, outdir, name, log=print):
    arms = ctx["spec"]["arms"][name]
    values = {label: dict(v) for label, v in arms["arms"].items()}
    configs = {label: apply_parameters(ctx["base"], ctx["spec"]["parameters"], v) for label, v in values.items()}
    runner = Runner(ctx, outdir, log)
    try:
        records = runner.run(f"arms_{name}", configs, arms["seeds"], probes=arms.get("probes", False))
    finally:
        runner.close()
    return summarise(ctx, outdir, f"arms_{name}", values, records, baseline=arms.get("baseline"))


def space_design(ctx, names=None, log2_n=7, seed=0):
    from scipy.stats import qmc

    defs = ctx["spec"]["parameters"]
    names = list(names or defs)
    u = qmc.Sobol(d=len(names), scramble=True, seed=seed).random_base2(m=log2_n)
    design = {}
    for i, row in enumerate(u):
        values = {}
        for name, x in zip(names, row):
            d = defs[name]
            if d["kind"] == "categorical":
                values[name] = d["choices"][min(int(x * len(d["choices"])), len(d["choices"]) - 1)]
            elif d.get("log"):
                values[name] = round(math.exp(math.log(d["low"]) + (math.log(d["high"]) - math.log(d["low"])) * x), 6)
            else:
                values[name] = round(d["low"] + (d["high"] - d["low"]) * x, 6)
                if d["kind"] == "int":
                    values[name] = int(round(values[name]))
        design[f"space_{i:04d}"] = values
    return design


def run_space(ctx, outdir, log=print):
    st = ctx["spec"]["stages"]["space"]
    design = space_design(ctx, st.get("parameters"), st.get("log2_n", 7), st.get("seed", 0))
    configs = {label: apply_parameters(ctx["base"], ctx["spec"]["parameters"], v) for label, v in design.items()}
    runner = Runner(ctx, outdir, log)
    try:
        records = runner.run("space", configs, st["seeds"])
    finally:
        runner.close()
    return summarise(ctx, outdir, "space", design, records)


def narrowed_space(ctx, outdir):
    """TPE space from the space stage: top-quantile bounds; weakly ranked parameters fixed at the best design."""
    st = ctx["spec"]["stages"]["tpe"]
    defs = ctx["spec"]["parameters"]
    t = pd.read_csv(Path(outdir) / "space_summary.csv", index_col="label")
    feas = t[t.feasible.astype(bool)].sort_values("J")
    if len(feas) < 8:
        raise ValueError("Too few feasible space designs to narrow the TPE space")
    top = feas.head(max(4, int(len(feas) * st.get("top_fraction", 0.2))))
    best = feas.iloc[0]
    space, fixed, strength = {}, {}, {}
    for name, d in defs.items():
        col = feas[f"p_{name}"]
        numeric = col.map(lambda v: d["choices"].index(_restore(v, d)) if d["kind"] == "categorical" else float(v))
        strength[name] = abs(numeric.astype(float).corr(feas.J, method="spearman")) if numeric.nunique() > 1 else 0.0
    keep = [n for n, v in sorted(strength.items(), key=lambda kv: -kv[1]) if v >= st.get("min_rank_correlation", 0.15)]
    keep = keep[: st.get("max_parameters", 10)]
    for name, d in defs.items():
        if name not in keep:
            fixed[name] = _restore(best[f"p_{name}"], d)
        elif d["kind"] == "categorical":
            space[name] = dict(kind="categorical", choices=d["choices"])
        else:
            vals = top[f"p_{name}"].astype(float)
            pad = 0.1 * (d["high"] - d["low"])
            low, high = max(d["low"], vals.min() - pad), min(d["high"], vals.max() + pad)
            if high - low < 0.05 * (d["high"] - d["low"]):
                low, high = max(d["low"], low - pad), min(d["high"], high + pad)
            space[name] = dict(kind=d["kind"], low=float(low), high=float(high), log=bool(d.get("log", False)))
    return space, fixed, strength


def _restore(value, d):
    if d["kind"] != "categorical":
        return float(value) if d["kind"] == "float" else int(value)
    for choice in d["choices"]:
        if str(choice) == str(value):
            return choice
    raise ValueError(f"Unknown categorical value {value!r}")


def run_tpe(ctx, outdir, log=print):
    from .parameter_search import SearchStopped, run_parameter_search

    st = ctx["spec"]["stages"]["tpe"]
    outdir = Path(outdir)
    space, fixed, strength = narrowed_space(ctx, outdir) if st.get("narrow_from_space", True) else (
        {n: {k: v for k, v in d.items() if k in ("kind", "low", "high", "log", "choices")}
         for n, d in ctx["spec"]["parameters"].items()}, {}, {})
    (outdir / "tpe_design.json").write_text(json.dumps(dict(space=space, fixed=fixed, rank_strength=strength), indent=1, default=str))
    log(f"[tpe] searching {sorted(space)}; fixed {fixed}")
    runner = Runner(ctx, outdir, log)
    base = ctx["base"]

    def evaluate(candidate, seeds):
        params = candidate.get("parameters", {})
        values = {k[len(PREFIX):]: params.pop(k) for k in list(params) if k.startswith(PREFIX)}
        if candidate != base:
            raise SearchStopped("Candidate differs from the base outside the declared search keys")
        values = dict(fixed, **values)
        config = apply_parameters(base, ctx["spec"]["parameters"], values)
        label = f"tpe_{sha(values)[:12]}"
        try:
            recs = runner.run("tpe_runs", {label: config}, list(seeds))[label]
        except RuntimeError as exc:
            raise SearchStopped("simulation_error", dict(message=str(exc)[:2000])) from exc
        s = scoring.score_records(recs, ctx["cores"], ctx["spec"])
        keep = ("loss_sd", "c_mae", "c_joint", "c_depth", "ensemble_loss", "independent_loss", "mass_mean",
                "mass_in_band", "ens_mean_ratio", "locality_excess", "feasible", "all_guards")
        # ``loss`` is the penalised objective TPE minimises; the RLD fold loss is ``rld_loss``.
        return dict(loss=float(s["J"]), rld_loss=s.get("loss"), values=values, config_sha=sha(config),
                    **{k: s[k] for k in keep if k in s}, guards=s.get("guards", {}))

    identity = dict(ctx["identity"], source_sha256=runner.source_sha, stage="tpe", fixed=fixed,
                    limits=ctx["spec"].get("limits", {}), objective=ctx["spec"].get("objective", {}))
    try:
        result = run_parameter_search(
            base_parameters=base, search_space={PREFIX + k: v for k, v in space.items()},
            seeds=list(st["seeds"]), outdir=outdir / "tpe", n_trials=int(st["n_trials"]),
            n_startup_trials=int(st["n_startup_trials"]), sampler_seed=int(st.get("sampler_seed", 0)),
            timeout_seconds=float(st.get("timeout_seconds", 86400)), identity=identity, evaluate=evaluate,
            resume=(outdir / "tpe" / "manifest.json").is_file(),
        )
    finally:
        runner.close()
    rows = []
    for path in sorted((outdir / "tpe" / "trials").glob("trial_*.json")):
        rec = json.loads(path.read_text())
        if rec.get("state") == "COMPLETE":
            res = rec["result"]
            rows.append(dict(trial=rec["trial_number"], J=res["loss"], **{k: v for k, v in res.items() if k not in ("loss", "values", "guards")},
                             **{f"guard_{k}": v for k, v in res.get("guards", {}).items()},
                             **{f"p_{k}": v for k, v in res["values"].items()}))
    pd.DataFrame(rows).to_csv(outdir / "tpe_summary.csv", index=False)
    return result


def run_confirm(ctx, outdir, log=print):
    st = ctx["spec"]["stages"]["confirm"]
    outdir = Path(outdir)
    tpe = pd.read_csv(outdir / "tpe_summary.csv").sort_values("J")
    defs = ctx["spec"]["parameters"]
    values = {st.get("baseline_label", "baseline"): dict(st.get("baseline", {}))}
    # Shortlist the best by J and, separately, the best by J among trials that pass the
    # locality guards, so a better spatial fit is not discarded by J alone.
    passing = tpe
    for column in [c for c in tpe.columns if c.startswith("guard_") and c not in ("guard_mass_share", "guard_mean_ratio")]:
        passing = passing[passing[column].astype(str).eq("True")]
    chosen = list(tpe.head(int(st.get("top", 4))).trial) + list(passing.head(int(st.get("top_locality", 0))).trial)
    for trial in dict.fromkeys(chosen):
        row = tpe[tpe.trial.eq(trial)].iloc[0]
        values[f"tpe_trial_{int(trial):04d}"] = {n: _restore(row[f"p_{n}"], defs[n]) for n in defs if f"p_{n}" in row}
    configs = {label: apply_parameters(ctx["base"], defs, v) for label, v in values.items()}
    runner = Runner(ctx, outdir, log)
    try:
        records = runner.run("confirm", configs, st["seeds"], probes=st.get("probes", False))
    finally:
        runner.close()
    t, ps = summarise(ctx, outdir, "confirm", values, records, baseline=st.get("baseline_label", "baseline"))
    candidates = t.drop(index=st.get("baseline_label", "baseline"))
    locality = [c for c in candidates.columns if c.startswith("guard_") and c not in ("guard_mass_share", "guard_mean_ratio")]
    passing = candidates[candidates.all_guards.astype(bool)] if "all_guards" in candidates else candidates.iloc[:0]
    pick = (passing if len(passing) else candidates).sort_values("loss" if len(passing) else "J").index[0]
    frozen = dict(version=VERSION, label=pick, all_guards_pass=bool(len(passing)), values=values[pick],
                  config=configs[pick], config_sha=sha(configs[pick]), seeds=list(st["seeds"]),
                  identity=dict(ctx["identity"], source_sha256=runner.source_sha))
    (outdir / "frozen_candidate.json").write_text(json.dumps(frozen, indent=1, default=str))
    log(f"[confirm] frozen candidate {pick}; all guards pass: {bool(len(passing))}")
    return t, frozen


def main(args, log=print):
    """CLI entry: ``python -m deeprootgen core-search --spec S --stage arms|space|tpe|confirm --outdir D``."""
    ctx = load_search_spec(args.spec)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    def logger(msg):
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        log(line)
        with open(outdir / "search.log", "a") as fh:
            fh.write(line + "\n")

    if args.stage == "arms":
        if not args.name:
            raise ValueError("--name selects an arm set for --stage arms")
        table, _ = run_arms(ctx, outdir, args.name, logger)
    elif args.stage == "space":
        table, _ = run_space(ctx, outdir, logger)
    elif args.stage == "tpe":
        return run_tpe(ctx, outdir, logger)
    else:
        table, frozen = run_confirm(ctx, outdir, logger)
        return dict(frozen_label=frozen["label"], all_guards_pass=frozen["all_guards_pass"])
    return dict(rows=len(table), summary=str(outdir))
