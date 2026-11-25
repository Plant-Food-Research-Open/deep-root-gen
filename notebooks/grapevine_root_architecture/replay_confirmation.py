"""Re-run one frozen SO4/T4 or Calvin confirmation with the local study bundle."""

import argparse
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd


CASES = {
    "so4-t4": ("starter", "local111"),
    "calvin-site1": ("qc_refine35", "sobol056"),
}


def read_json(path):
    return json.loads(path.read_bytes())


def verify_file(path, expected):
    if sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"Saved confirmation file differs from its receipt: {path}")


def compare_scores(replayed, saved, index, fields):
    expected = saved.set_index(index, verify_integrity=True)
    actual = replayed.set_index(index, verify_integrity=True)
    if set(actual.index) != set(expected.index):
        raise ValueError("Replayed score rows do not match the saved comparison")
    np.testing.assert_allclose(actual[fields], expected.loc[actual.index, fields], rtol=1e-10, atol=1e-12)


def replay_so4(research, spatial, study, source, case, config, workers):
    archive = json.loads(gzip.decompress((spatial / "so4_replay_records.json.gz").read_bytes()))
    if source != archive["source_sha256"]:
        raise ValueError("The SO4/T4 panel requires the recorded generator source")
    panel = study / "SO4-final"
    verify_file(spatial / "so4_spatial.py", archive["scorer_sha256"])
    verify_file(research / "scripts/data/grapevine3d_grid.py", archive["voxelizer_sha256"])
    verify_file(panel / "protocol.json", archive["protocol_sha256"])
    verify_file(panel / "confirmation.json", archive["candidate_table_sha256"])
    identity = read_json(panel / "protocol.json")
    verify_file(study / "SO4/search_so4.py", identity["identity"]["base_runner"])
    verify_file(study / "SO4-axial/search_axial.py", identity["identity"]["axial_runner"])

    import so4_spatial as scorer

    settings = next(row["settings"] for row in read_json(panel / "confirmation.json") if row["id"] == case)
    seeds = identity["confirmation_seeds"]
    if scorer.changed(settings, config["random_seed"]) != config:
        raise ValueError("The selected SO4/T4 input differs from the frozen candidate")
    recorded = {row["seed"]: row for row in archive["runs"] if row["candidate"] == case}
    if set(recorded) != set(seeds) or len(recorded) != archive["seed_count"]:
        raise ValueError("The SO4/T4 confirmation seed panel is incomplete")
    jobs = [(case, seed, settings, source) for seed in seeds]
    predicted, receipts = [], []
    print(f"Replaying the {len(jobs)} saved SO4/T4 seeds for {case}", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for record, grid in pool.map(scorer.replay, jobs, chunksize=2):
            original = recorded[record["seed"]]
            if record != original:
                raise ValueError(f"SO4/T4 replay differs from the saved voxel receipt at seed {record['seed']}")
            predicted.append(grid)
            receipts.append({key: value for key, value in record.items() if key != "voxels"})

    # The archived observed rows are already in the registered soil frame.
    shares = pd.read_csv(spatial / "so4_voxel_shares.csv")
    cells = shares.loc[shares.case.eq("Observed")].set_index(["x_index", "y_index", "depth_index"],
                                                             verify_integrity=True).share
    if cells.empty or not np.isfinite(cells).all() or (cells < 0).any() or not np.isclose(cells.sum(), 1.):
        raise ValueError("Unusable archived observed voxel shares")
    observed = cells.to_dict()
    mean_prediction = scorer.average(predicted)
    saved = pd.read_csv(spatial / "so4_spatial_scores.csv").query("candidate == @case")
    result = pd.DataFrame([scorer.score(observed, mean_prediction, case, len(seeds), size)
                           for size in saved.voxel_cm])
    fields = ["seeds", *(key for key in result if key.endswith("_tv"))]
    compare_scores(result, saved, "voxel_cm", fields)
    return result, receipts


def calvin_trial(job):
    from deeprootgen.model import RootSystemSimulation
    from search_calvin import observe

    stage, config, expected = job
    seed = config["random_seed"]
    simulation = RootSystemSimulation(random_seed=seed, simulation_tag=config["simulation_tag"])
    simulation.run(config)
    metadata = simulation.result.metadata
    if (metadata["root_summary"]["excluded_invalid_root_count"] != 0
            or metadata["run_identity_sha256"] != expected["run_identity_sha256"]):
        raise ValueError(f"Calvin replay geometry or identity differs for {stage} seed {seed}")
    predicted = observe(simulation)
    fingerprint = sha256(predicted.to_csv(index=False).encode()).hexdigest()
    if fingerprint != expected["predictions_sha"]:
        raise ValueError(f"Calvin core predictions differ for {stage} seed {seed}")
    receipt = dict(stage=stage, seed=seed, run_identity_sha256=metadata["run_identity_sha256"],
                   predictions_sha256=fingerprint)
    return predicted.set_index("target_row", verify_integrity=True), receipt


def calvin_jobs(scorer, runner, receipt, case, config, source):
    stages = ["Calvin-qc"] if case == "qc_refine35" else ["Calvin-final", "Calvin-qc"]
    density = config["parameters"]["root_tissue_density"]
    for stage in stages:
        panel = scorer.STUDY / stage
        identity_key, _, seed_key = scorer.ARCHIVES[stage]
        recorded = receipt["protocol_sha256"][stage]
        for filename in ("protocol.json", "confirmation.json"):
            verify_file(panel / filename, recorded[filename])
        protocol = read_json(panel / "protocol.json")
        identity = protocol[identity_key]
        if source != identity["generator_sha"]:
            raise ValueError("The Calvin panel requires the recorded generator source")
        verify_file(Path(runner.__file__), identity.get("scope_sha", identity["runner_sha"]))
        verify_file(runner.LAYOUT, identity["layout_sha"])
        confirmation = next(row for row in read_json(panel / "confirmation.json") if row["id"] == case)
        seeds = protocol[seed_key]
        if confirmation["runs"] != len(seeds) or confirmation["scored"]["Site1_hold"]["density_g_cm3"] != density:
            raise ValueError("The selected Calvin input differs from the frozen density or seed panel")
        for seed in seeds:
            path = panel / "runs/full" / case / str(seed)
            expected = read_json(path / "receipt.json")
            if (expected["id"], expected["seed"], expected["screening"], expected["source_identity"]) != (
                    case, seed, False, identity) or "error" in expected:
                raise ValueError(f"Invalid Calvin run receipt for {stage} seed {seed}")
            verify_file(path / "parameters.json", expected["params_sha"])
            trial = deepcopy(config)
            trial["random_seed"] = seed
            trial["parameters"]["root_tissue_density"] = 1.0
            if trial != read_json(path / "parameters.json"):
                raise ValueError(f"The selected Calvin input differs from the saved configuration for seed {seed}")
            yield stage, trial, expected


def replay_calvin(spatial, study, source, case, config, workers):
    receipt = read_json(spatial / "calvin_spatial_receipt.json")
    verify_file(spatial / "calvin_spatial.py", receipt["scorer_sha256"])
    sys.path.insert(0, str(study / "Calvin"))
    import calvin_spatial as scorer
    import search_calvin as runner

    verify_file(scorer.TARGETS, receipt["targets_sha256"])
    verify_file(scorer.SPLIT, receipt["holdout_sha256"])
    observations, folds, scales = scorer.support()
    jobs = list(calvin_jobs(scorer, runner, receipt, case, config, source))
    predictions, receipts = [], []
    print(f"Replaying the {len(jobs)} saved Calvin seeds for {case}", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for frame, record in pool.map(calvin_trial, jobs):
            if not frame.index.equals(observations.index):
                raise ValueError("Fresh predictions do not align with the saved core support")
            predictions.append(frame[scorer.PREDICTIONS].to_numpy())
            receipts.append(record)

    averaged = pd.DataFrame(np.mean(predictions, axis=0), index=observations.index, columns=scorer.PREDICTIONS)
    density = config["parameters"]["root_tissue_density"]
    paired = scorer.measure(observations, averaged, density)
    panel = "Calvin-qc" if case == "qc_refine35" else "combined_28"
    result = pd.DataFrame([
        dict(panel=panel, candidate=case, fold=fold, seeds=len(jobs), **scorer.evaluate(paired[mask], scales))
        for fold, mask in folds.items()
    ])
    saved = pd.read_csv(spatial / "calvin_spatial_scores.csv").query("candidate == @case and panel == @panel")
    fields = result.select_dtypes(include="number").columns.to_list()
    compare_scores(result, saved, "fold", fields)
    return result, receipts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--study", choices=CASES, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if args.case not in CASES[args.study] or args.workers < 1:
        parser.error("Choose a saved case for the selected study and a positive worker count")
    if args.outdir.exists():
        raise FileExistsError(args.outdir)
    os.umask(0o077)
    sys.dont_write_bytecode = True

    research = args.research_root.resolve()
    study = research / ".runtime/structural-search-20261118"
    spatial = research / "Calvin_SO4_Parameter_Exploration_2026-11-18/Spatial_Evaluation_2026-11-19"
    checkout = Path(__file__).resolve().parents[2]
    source_root = study / "source-final"
    if not (source_root / "deeprootgen/model/provenance.py").is_file():
        source_root = checkout
    sys.path[:0] = [str(source_root), str(research), str(spatial), str(checkout)]
    from deeprootgen.model.provenance import source_fingerprint

    source = source_fingerprint()
    config = read_json(args.config)
    if args.study == "so4-t4":
        scores, receipts = replay_so4(research, spatial, study, source, args.case, config, args.workers)
    else:
        scores, receipts = replay_calvin(spatial, study, source, args.case, config, args.workers)
    args.outdir.mkdir(parents=True)
    scores.to_csv(args.outdir / "scores.csv", index=False)
    summary = dict(study=args.study, case=args.case, source_sha256=source,
                   input_sha256=sha256(args.config.read_bytes()).hexdigest(),
                   verified_seeds=len(receipts), trials=receipts)
    (args.outdir / "receipt.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Verified {len(receipts)} seeds for {args.case}")


if __name__ == "__main__":
    main()
