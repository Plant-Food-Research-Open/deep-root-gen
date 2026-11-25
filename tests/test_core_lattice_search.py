"""Synthetic checks of the opt-in lattice core score and its search driver."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deeprootgen.research import core_lattice_scoring as scoring
from deeprootgen.research import core_lattice_search as search
from deeprootgen.research.core_placement_cost import score_core_placement

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _graph(segments):
    """One base at the origin; each segment is (parent index, x, y, z, diameter_cm, order)."""
    rows = [dict(node_id=0, parent_id=-1, order=0, segment_rank=1, x=0.0, y=0.0, z=0.0, diameter=0.0,
                 root_type="base", invalid_root=False)]
    for i, (parent, x, y, z, d, order) in enumerate(segments, 1):
        rows.append(dict(node_id=i, parent_id=parent, order=order, segment_rank=1, x=x, y=y, z=z, diameter=d,
                         root_type="fine", invalid_root=False))
    nodes = pd.DataFrame(rows)
    edges = pd.DataFrame(dict(parent_id=nodes.parent_id[1:].to_numpy(), child_id=nodes.node_id[1:].to_numpy()))
    return nodes, edges


def _cores(points):
    rows = []
    for core, (x, y) in points.items():
        for top in (0, 10, 20):
            rows.append(dict(core_id=core, model_x=float(x), model_y=float(y), z_lower_cm=-top - 10.0,
                             z_upper_cm=-float(top), radius_cm=2.0, rld_est=0.1, fold=0))
    cores = pd.DataFrame(rows)
    cores["core_volume_cm3"] = np.pi * 4.0 * 10
    return cores


def test_fold_dealing_is_deterministic_and_complete():
    strata = [["a", "b"], ["c", "d", "e"], ["f"]]
    one = scoring.assign_folds(list("abcdef"), strata, 3, 7)
    assert one == scoring.assign_folds(list("abcdef"), strata, 3, 7)
    assert sorted(one) == list("abcdef") and set(one.values()) == {0, 1, 2}
    assert one["a"] != one["b"]                                  # a two-core stratum never shares a fold
    for bad in ([["a", "b"], ["c", "d", "e"]], [["a", "a"], ["b", "c", "d", "e", "f"]]):
        with pytest.raises(ValueError):
            scoring.assign_folds(list("abcdef"), bad, 3, 7)


def test_band_edges_and_lattice_offsets():
    # Vertical segments under the origin: 0.4 mm, 0.5 mm (excluded), 1 mm, 2.5 mm (included), 3 mm.
    nodes, edges = _graph([(0, 0, 0, -30, 0.04, 1), (0, 0, 0, -30, 0.05, 1), (0, 0, 0, -30, 0.1, 1),
                           (0, 0, 0, -30, 0.25, 1), (0, 0, 0, -30, 0.3, 1)])
    support = scoring.band_support(nodes, edges, (0.5, 2.5))
    assert support.segments.is_fine.tolist() == [False, False, True, True, False]
    offsets = scoring.lattice_offsets(dict(x_spacing_cm=300, y_spacing_cm=200, extent=1))
    assert len(offsets) == 9 and (0.0, 0.0) in offsets
    cores = _cores({"here": (0, 0), "next_row": (300, 0), "between": (150, 100)})
    c = scoring.lattice_contributions(support, cores, offsets)
    here = cores.core_id.eq("here").to_numpy()
    nxt = cores.core_id.eq("next_row").to_numpy()
    expected = 2 * 10 / (np.pi * 4.0 * 10)                       # two band segments cross each 10 cm increment
    np.testing.assert_allclose(c[here, offsets.index((0.0, 0.0))], expected)
    np.testing.assert_allclose(c[nxt, offsets.index((300.0, 0.0))], expected)   # periodic copy one row over
    assert c[here].sum() == pytest.approx(3 * expected) and not c[cores.core_id.eq("between").to_numpy()].any()


def test_parameter_edits():
    config = dict(irrigation=dict(upper_radius_cm=20.0), features=dict(groups=[dict(c=1.0), dict(c=2.0)],
                                                                         lengths=dict(mean=10.0, sd=2.0)))
    defs = dict(
        up=dict(kind="float", edits=[dict(op="set", path="irrigation.upper_radius_cm")]),
        gain=dict(kind="float", edits=[dict(op="set", paths=["irrigation.moisture_tropism.4", "irrigation.moisture_tropism.5"])]),
        kappa=dict(kind="float", edits=[dict(op="set", paths=["features.groups.0.c", "features.groups.1.c"])]),
        scale=dict(kind="float", edits=[dict(op="scale", path="features.lengths", fields=["mean", "sd"],
                                             reference=dict(mean=5.0, sd=1.0))]),
        law=dict(kind="categorical", choices=["a", "b"], edits=[dict(op="choice", path="features.law",
                                                                     values=dict(a=dict(x=1), b=dict(x=2)))]),
    )
    out = search.apply_parameters(config, defs, dict(up=30.0, gain=0.5, kappa=3.0, scale=2.0, law="b"))
    # A choice replacing the object that a set edits applies first, whatever the value order.
    defs["groups"] = dict(kind="categorical", choices=["one"], edits=[dict(op="choice", path="features.groups",
                                                                           values=dict(one=[dict(c=0.0), dict(c=0.0)]))])
    for order in (dict(kappa=3.0, groups="one"), dict(groups="one", kappa=3.0)):
        assert [g["c"] for g in search.apply_parameters(config, defs, order)["features"]["groups"]] == [3.0, 3.0]
    assert out["irrigation"] == dict(upper_radius_cm=30.0, moisture_tropism={"4": 0.5, "5": 0.5})
    assert [g["c"] for g in out["features"]["groups"]] == [3.0, 3.0]
    assert out["features"]["lengths"] == dict(mean=10.0, sd=2.0) and out["features"]["law"] == dict(x=2)
    assert config["irrigation"] == dict(upper_radius_cm=20.0)    # the base is never mutated


def test_score_records_matches_manual_folds_and_penalties():
    rng = np.random.default_rng(0)
    cores = _cores({"a": (0, 0), "b": (10, 0), "c": (0, 10), "d": (10, 10)})
    cores["fold"] = cores.core_id.map(dict(a=0, b=0, c=1, d=1))
    cores["rld_est"] = rng.uniform(0, 0.3, len(cores))
    spec = dict(lattice=dict(x_spacing_cm=300, y_spacing_cm=200, extent=1), crown_kg=1.0,
                objective=dict(mass_band_kg=[4.0, 5.0], ratio_band=[0.8, 1.2], kg_weight=0.25, ratio_weight=0.5),
                supports=dict(ab=dict(cores=["a", "b"], top_cm=0, bottom_cm=30)), guards=dict(mass_share=0.5))
    contributions = rng.uniform(0, 0.05, (len(cores), 9))
    rec = dict(status="ok", seed=1, contributions=contributions.tolist(), root_kg=2.0, organs={"1": 3}, seconds=1.0)
    s = scoring.score_records([rec], cores, spec)
    pred = contributions.sum(1)
    manual = np.mean([score_core_placement(cores[~cores.fold.eq(k)], cores[cores.fold.eq(k)],
                                           pd.Series(pred[cores.fold.eq(k).to_numpy()], index=cores.index[cores.fold.eq(k)]))["loss"]
                      for k in (0, 1)])
    assert s["loss"] == pytest.approx(manual)
    assert s["independent_loss"] == pytest.approx(s["loss"])          # one seed: neighbours are itself
    ratio = pred.mean() / cores.rld_est.mean()
    expected_j = manual + 0.25 * 1.0 + 0.5 * max(0.0, 0.8 - ratio, ratio - 1.2)
    assert s["J"] == pytest.approx(expected_j) and s["guards"] == dict(mass_share=False)
    # Soft locality term: relative violation of a ratio guard, off unless weighted.
    spec["ratios"] = dict(ab_cd=["ab", "cd"])
    spec["supports"]["cd"] = dict(cores=["c", "d"], top_cm=0, bottom_cm=30)
    spec["guards"] = dict(ab_cd=dict(max=0.5))
    spec["objective"]["locality_weight"] = 0.4
    s2 = scoring.score_records([rec], cores, spec)
    ratio_ab_cd = s2["ens_ab_cd"]
    assert s2["locality_excess"] == pytest.approx(max(0.0, (ratio_ab_cd - 0.5) / 0.5))
    assert s2["J"] == pytest.approx(expected_j + 0.4 * s2["locality_excess"])
    failed = scoring.score_records([dict(rec, status="infeasible", reason="limit")], cores, spec)
    assert failed["J"] >= 2 and not failed["feasible"]


@pytest.fixture
def spec_dir(tmp_path):
    base = json.loads((EXAMPLES / "research/native_cohort_synthetic.json").read_text())
    base.pop("random_seed")
    (tmp_path / "base.json").write_text(json.dumps(base))
    rows = []
    for core, (x, y) in dict(c1=(-8, 0), c2=(-4, 4), c3=(0, -4), c4=(4, 0), c5=(8, 4), c6=(-12, -4)).items():
        for top in (0, 10, 20):
            rows.append(dict(core_id=core, x_cm=x, y_cm=y, z_upper_cm=-top, z_lower_cm=-top - 10, radius_cm=1.5,
                             rld_cm_per_cm3=0.05 * (top < 20), split="dev"))
    rows.append(dict(core_id="held", x_cm=0, y_cm=0, z_upper_cm=0, z_lower_cm=-10, radius_cm=1.5, rld_cm_per_cm3=0.1, split="hold"))
    pd.DataFrame(rows).to_csv(tmp_path / "cores.csv", index=False)
    drift = "features.curvature.settings.by_order.{}.downward_drift_per_cm"
    spec = dict(
        base_config="base.json",
        cores=dict(path="cores.csv", filter=dict(split="dev"), exclude_cores=["held"],
                   frame=dict(model_x=dict(column="x_cm", sign=1), model_y=dict(column="y_cm", sign=1)),
                   folds=dict(k=2, seed=1, strata=[["c1", "c2", "c3"], ["c4", "c5", "c6"]])),
        lattice=dict(x_spacing_cm=300, y_spacing_cm=200, extent=1), band_mm=[0.5, 7.0], crown_kg=0.0,
        objective=dict(mass_band_kg=[0, 100], ratio_band=[0, 100], kg_weight=0.25, ratio_weight=0.5),
        supports=dict(left=dict(cores=["c1", "c6"], top_cm=0, bottom_cm=30), right=dict(cores=["c4", "c5"], top_cm=0, bottom_cm=30)),
        ratios=dict(left_right=["left", "right"]), guards=dict(left_right=dict(min=0.0)), deep_top_cm=20,
        probes=dict(groups=dict(first=[0]), supports=[dict(core="c1", top_cm=0, bottom_cm=30)]),
        limits=dict(workers=2, seconds=300, memory_gb=None),
        parameters=dict(
            drift=dict(kind="float", low=0.0, high=0.004, edits=[dict(op="set", paths=[drift.format(o) for o in "2345"])]),
            insertion=dict(kind="float", low=30.0, high=60.0,
                           edits=[dict(op="set", path="features.curvature.settings.by_order.2.insertion_mean_deg")]),
        ),
        arms=dict(pair=dict(seeds=[1, 2], baseline="base", probes=True, arms=dict(base={}, steep=dict(insertion=60.0))),
                  broken=dict(seeds=[1], arms=dict(bad=dict(drift=-1.0)))),
        stages=dict(space=dict(log2_n=2, seeds=[1], seed=3),
                    tpe=dict(seeds=[1], n_trials=3, n_startup_trials=2, sampler_seed=5, narrow_from_space=False),
                    confirm=dict(seeds=[1, 2], top=1, baseline={}, baseline_label="baseline")),
    )
    (tmp_path / "spec.json").write_text(json.dumps(spec))
    return tmp_path


def test_hold_out_core_in_the_table_is_rejected(spec_dir):
    spec = json.loads((spec_dir / "spec.json").read_text())
    spec["cores"]["filter"] = {}
    (spec_dir / "leaky.json").write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="excluded core"):
        search.load_search_spec(spec_dir / "leaky.json")


def test_stages_end_to_end_with_identity_checked_cache(spec_dir):
    ctx = search.load_search_spec(spec_dir / "spec.json")
    out = spec_dir / "out"
    logs = []
    table, per_seed = search.run_arms(ctx, out, "pair", logs.append)
    assert set(table.index) == {"base", "steep"} and table.loc["base", "paired_dloss"] == 0
    assert (out / "arms_pair_probes.csv").exists() and len(per_seed) == 4
    search.run_arms(ctx, out, "pair", logs.append)
    assert "4 cached, 0 to run" in logs[-1] or any("4 cached, 0 to run" in m for m in logs[-3:])
    # A record from another source revision is never reused.
    path = next((out / "arms_pair" / "results").rglob("1.json"))
    rec = json.loads(path.read_text()); rec["source_sha"] = "other"; path.write_text(json.dumps(rec))
    search.run_arms(ctx, out, "pair", logs.append)
    assert any("3 cached, 1 to run" in m for m in logs)
    with pytest.raises(RuntimeError, match="Run failed"):
        search.run_arms(ctx, out, "broken", logs.append)
    space, _ = search.run_space(ctx, out, logs.append)
    assert len(space) == 4 and {"J", "loss", "p_drift", "p_insertion"} <= set(space.columns)
    result = search.run_tpe(ctx, out, logs.append)
    assert result["completed_trials"] == 3 and result["stop_reason"] == "trial_budget_exhausted"
    tpe = pd.read_csv(out / "tpe_summary.csv")
    assert len(tpe) == 3 and tpe.J.notna().all()
    table, frozen = search.run_confirm(ctx, out, logs.append)
    assert frozen["label"].startswith("tpe_trial_") and "baseline" in table.index
    assert json.loads((out / "frozen_candidate.json").read_text())["config_sha"] == search.sha(frozen["config"])


@pytest.mark.parametrize("has_passing_trial", [True, False])
def test_confirmation_freezes_only_complete_finite_guard_passers(tmp_path, monkeypatch, has_passing_trial):
    cores = _cores({"a": (0, 0), "b": (10, 0)})
    cores["fold"] = cores.core_id.map(dict(a=0, b=1))
    seeds = [1, 2]
    spec = dict(
        lattice=dict(x_spacing_cm=300, y_spacing_cm=200, extent=0),
        objective=dict(ratio_band=[19, 22]), guards=dict(mean_ratio=True),
        parameters={}, stages=dict(confirm=dict(seeds=seeds, top=5)),
    )
    ctx = dict(spec=spec, base={}, cores=cores, identity={})

    def record(seed, rld, mass=4.0):
        return dict(seed=seed, status="ok", contributions=[[rld]] * len(cores),
                    root_kg=mass, organs={"1": 1}, seconds=1.0)

    data = {
        "baseline": [record(seed, 0.1) for seed in seeds],
        "tpe_trial_0000": [record(1, 0.1), dict(seed=2, status="infeasible", reason="limit")],
        "tpe_trial_0001": [record(1, 2.0), record(3, 2.0)],
        "tpe_trial_0002": [record(1, 2.0), record(2, 2.0, mass=np.nan)],
        "tpe_trial_0003": [record(seed, 0.1) for seed in seeds],
        "tpe_trial_0004": [record(seed, 2.1 if has_passing_trial else 0.2) for seed in seeds],
    }

    class RecordedRunner:
        source_sha = "synthetic"

        def __init__(self, *args):
            pass

        def run(self, stage, configs, required_seeds, probes=False):
            assert stage == "confirm" and set(configs) == set(data) and required_seeds == seeds
            return data

        def close(self):
            pass

    pd.DataFrame(dict(trial=range(5), J=range(5))).to_csv(tmp_path / "tpe_summary.csv", index=False)
    monkeypatch.setattr(search, "Runner", RecordedRunner)
    path = tmp_path / "frozen_candidate.json"
    if not has_passing_trial:
        path.write_text('{"label": "stale"}')
    table, result = search.run_confirm(ctx, tmp_path)
    assert pd.isna(table.at["tpe_trial_0000", "all_guards"])
    assert table.at["tpe_trial_0000", "J"] < table.at["tpe_trial_0001", "J"]
    assert result["all_guards_pass"] is has_passing_trial
    if has_passing_trial:
        assert result["label"] == "tpe_trial_0004" and json.loads(path.read_text()) == result
    else:
        assert result == dict(label=None, all_guards_pass=False, diagnostic_label="tpe_trial_0003")
        assert not path.exists()


def test_cli_option_is_registered(spec_dir):
    from deeprootgen.cli import _main

    with pytest.raises(SystemExit) as exit_:
        _main(["core-search", "--help"], None)
    assert exit_.value.code == 0
    args = argparse.Namespace(spec=spec_dir / "spec.json", stage="arms", name=None, outdir=spec_dir / "cli")
    with pytest.raises(ValueError, match="--name"):
        search.main(args)
