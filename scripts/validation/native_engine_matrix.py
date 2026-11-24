#!/usr/bin/env python3
"""Offline invented-input matrix, tracked exports and exact export reload checks.

Run in the qualified Python 3.10 environment. Nothing is uploaded; existing
output directories are never overwritten. These are software checks only.
"""

import argparse
import copy
import hashlib
from itertools import product
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def spatial_cases():
    base = json.loads((ROOT / "examples/design/spatial_construction_synthetic.json").read_text())
    for alignment, origins, branching in product((False, True), repeat=3):
        value = copy.deepcopy(base)
        features = value["features"]
        if not alignment:
            features["curvature"]["settings"]["by_order"]["2"].pop("row_alignment_per_cm")
        features["primary_origins"]["enabled"] = origins
        if not branching:
            law = features["branching"]["settings"]["by_order"]
            law["2"] = copy.deepcopy(law["1"])
        yield f"spatial-R{int(alignment)}-O{int(origins)}-B{int(branching)}", value


def cases():
    base = json.loads((ROOT / "examples/design/native_feature_options.json").read_text())
    base["parameters"]["tropism_mode"] = "fichtl2024"
    base["parameters"]["gravitropism"] = 0.
    base["parameters"]["min_branching_diameter_cm"] = 0.
    yield "all-off", copy.deepcopy(base)
    default_branching = copy.deepcopy(base)
    del default_branching["parameters"]["min_branching_diameter_cm"]
    yield "structural-branch-default", default_branching
    primary = base["features"]["curvature"]["settings"]["by_order"]["1"]
    value = copy.deepcopy(base)
    value["features"]["curvature"]["enabled"] = True
    yield "primary-curvature", value
    value = copy.deepcopy(base)
    value["features"]["taper"] = dict(enabled=True, settings=dict(by_order={
        "1": base["features"]["taper"]["settings"]["by_order"]["1"]}))
    yield "parent-only-taper", value
    value = copy.deepcopy(base)
    insertion = dict(primary, initial_heading="insertion_angle", insertion_mean_deg=45., insertion_sd_deg=10.)
    value["features"]["curvature"] = dict(enabled=True, settings=dict(by_order={"1": primary, "2": insertion}))
    value["features"]["taper"]["enabled"] = True
    yield "mixed-orders", value
    value = json.loads((ROOT / "examples/design/native_features_fully_replaced.json").read_text())
    value["features"]["primary_origins"]["enabled"] = False
    value["features"]["curvature"]["settings"]["by_order"]["1"]["initial_heading"] = "scaffold_chord"
    value["parameters"].update(root_vary=2., segments_per_root=3)
    yield "common-origin-replaced-dimensions", value
    yield "paired-allocation-targets", json.loads((ROOT / "examples/design/native_allocation_targets.json").read_text())
    yield "buried-trunk-0-20cm", json.loads((ROOT / "examples/design/native_crown_0_20cm.json").read_text())
    yield from spatial_cases()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", required=True, type=Path)
    args = parser.parse_args()
    if args.outdir.exists():
        parser.error("Output directory already exists")
    sys.path.insert(0, str(ROOT))
    from deeprootgen.run_records import tracked_run

    args.outdir.mkdir(parents=True)
    summary = dict(script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   biological_validation=False, cases=[])
    for label, spec in cases():
        record = tracked_run(spec, args.outdir / label, label=label)
        replay = tracked_run(args.outdir / label / "parameters.json", args.outdir / (label + "-replay"), label=label + "-replay")
        for key in ("effective_model_sha256", "run_identity_sha256"):
            if record["model_identity"][key] != replay["model_identity"][key]:
                raise AssertionError(f"{label}: {key} changed on reload")
        files = {"nodes.csv", "edges.csv", "root_summary.json", "organs.csv", "branching.json"}
        files |= {"row_alignment.json", "vine_origin_catalogue.json"} & (
            record["outputs"].keys() | replay["outputs"].keys()
        )
        for name in sorted(files):
            if record["outputs"][name] != replay["outputs"][name]:
                raise AssertionError(f"{label}: {name} changed on reload")
        summary["cases"].append(dict(label=label, nodes=record["node_count"], edges=record["edge_count"],
                                     invalid_nodes=record["invalid_node_count"], model_identity=record["model_identity"],
                                     export_reload_exact=True))
    (args.outdir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
