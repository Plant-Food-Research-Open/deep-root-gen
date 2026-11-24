"""Local-only evidence audit; never imports or runs the root generator.

Read existing prepared tables and RSML without modifying them. Write private
per-vine QC and proposed membership to a fresh ignored directory. No network.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

EXPECTED_GRID_SHA256 = (
    "10e5b5332bd9bdf06cf73e1a64fb394c99ab174c822aa4744440fa7cd67fb4bf"
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def audit(data_dir, prepared_dir, out, repo):
    out = out.resolve()
    for protected in (data_dir.resolve(), prepared_dir.resolve()):
        if out == protected or protected in out.parents:
            raise ValueError("Output must be outside raw/prepared input directories")
    if subprocess.run(["git", "check-ignore", "-q", str(out)], cwd=repo).returncode:
        raise ValueError("Use an ignored output directory, e.g. .runtime/research/NEW")
    out.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location(
        "grapevine3d_local_converter", repo / "scripts/data/grapevine3d_grid.py"
    )
    converter = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = converter
    spec.loader.exec_module(converter)
    manifest = {
        "source_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=repo, text=True
        ).strip(),
        "status_before_audit": subprocess.check_output(
            ["git", "status", "--short"], cwd=repo, text=True
        ),
        "audit_python": sys.version,
        "files": {},
    }
    inputs = [
        prepared_dir / x
        for x in ("voxel_grid.csv", "vine_summary.csv", "analysis_metadata.json")
    ]
    inputs += [
        repo / "poetry.lock",
        repo / "pyproject.toml",
        repo / "scripts/data/grapevine3d_grid.py",
        Path(__file__).resolve(),
        repo / "data/grapevine/fichtl_2024_voxel_grid.csv",
    ]
    inputs += sorted((repo / "notebooks/grapevine_fichtl_2024").glob("*.ipynb"))
    inputs += sorted((repo / "deeprootgen").rglob("*.py"))
    inputs += sorted((repo / "docs/research/grapevine3d").glob("*"))
    inputs += sorted((data_dir / "RSML_Files").glob("T*/*.rsml"))
    inputs += sorted((data_dir / "VTP_Files").glob("T*/*.vtp"))
    for path in inputs:
        manifest["files"][str(path.resolve())] = {
            "sha256": digest(path),
            "bytes": path.stat().st_size,
        }
    # Header inventories are saved locally, never raw rows on stdout.
    schemas = {}
    with (prepared_dir / "vine_summary.csv").open() as handle:
        reader = csv.DictReader(handle)
        schemas["vine_summary"] = reader.fieldnames
        summary_rows = list(reader)
        summaries = {(r["timepoint"], r["vine_id"]): r for r in summary_rows}
        if len(summaries) != len(summary_rows):
            raise ValueError("Duplicate vine-summary keys")
    cells = defaultdict(dict)
    duplicate_cells = 0
    with (prepared_dir / "voxel_grid.csv").open() as handle:
        reader = csv.DictReader(handle)
        schemas["voxel_grid"] = reader.fieldnames
        for row in reader:
            key = row["timepoint"], row["vine_id"]
            cell = tuple(int(row[k]) for k in ("ix", "iy", "iz"))
            duplicate_cells += cell in cells[key]
            cells[key][cell] = row
    reports, groups = [], defaultdict(list)
    unit_counts, labels, vtp_fields, radii = Counter(), Counter(), Counter(), Counter()
    hierarchy_mismatches = 0
    hierarchy_pairs = Counter()
    for path in sorted((data_dir / "RSML_Files").glob("T*/*.rsml")):
        document = ET.parse(path).getroot()
        unit_counts[document.findtext("./metadata/unit")] += 1
        labels.update(r.get("label", "") for r in document.findall(".//root"))
        stem = document.find("./scene/plant/root")

        def check_labels(node, depth):
            mismatch = 0
            expected = (
                "stem",
                "primary",
                "secondary",
                "tertiary",
                "quaternary",
                "quinary",
            )
            label = node.get("label", "").lower()
            hierarchy_pairs[(depth, label)] += 1
            if depth >= len(expected) or label != expected[depth]:
                mismatch += 1
            return mismatch + sum(
                check_labels(child, depth + 1) for child in node.findall("./root")
            )

        hierarchy_mismatches += check_labels(stem, 0)
        vine = converter.read_vine(path)
        recomputed, stats = converter.grid_vine(vine, 10.0)
        key = vine.timepoint, vine.vine_id
        prepared = cells[key]
        summary = summaries[key]
        errors, class_errors, rld_errors = [], [], []
        for cell in set(prepared) | set(recomputed):
            row = prepared.get(cell)
            values = recomputed.get(cell, {})
            actual = math.fsum(values.values())
            if row is None:
                raise ValueError("Recomputed occupied cube outside prepared support")
            errors.append(abs(float(row["root_length_cm"]) - actual))
            rld_errors.append(abs(float(row["rld_cm_per_cm3"]) - actual / 1000))
            for label in converter.ROOT_CLASSES:
                class_errors.append(
                    abs(float(row[label + "_length_cm"]) - values.get(label, 0))
                )
        n_bounds = math.prod(
            int(summary[k + "_max"]) - int(summary[k + "_min"]) + 1
            for k in ("ix", "iy", "iz")
        )
        lengths = [float(row["root_length_cm"]) for row in prepared.values()]
        tolerance = 1e-8 * max(1.0, stats["soil_length_cm"])
        total_error = abs(math.fsum(lengths) - stats["soil_length_cm"])
        sha_match = digest(path) == summary["source_sha256"]
        passed = (
            max(errors) <= tolerance
            and max(class_errors) <= tolerance
            and max(rld_errors) <= tolerance / 1000
            and total_error <= tolerance
            and sha_match
            and n_bounds == len(prepared)
            and all(math.isfinite(x) and x >= 0 for x in lengths)
            and all(
                abs(float(summary[k]) - stats[k]) <= tolerance
                for k in (
                    "soil_length_cm",
                    "grid_length_cm",
                    "original_length_cm",
                    "above_surface_length_cm",
                )
            )
        )
        report = {
            "timepoint": vine.timepoint,
            "vine_id": vine.vine_id,
            "rootstock": vine.rootstock,
            "passed": passed,
            "source_hash_matches": sha_match,
            **stats,
            "grid_cell_count": len(prepared),
            "max_cell_error_cm": max(errors),
            "max_class_error_cm": max(class_errors),
            "max_rld_error": max(rld_errors),
            "total_error_cm": total_error,
            "shallow_0_20_length_cm": math.fsum(
                float(row["root_length_cm"])
                for row in prepared.values()
                if int(row["iz"]) in (0, 1)
            ),
            "bounds": {
                k: int(summary[k])
                for k in ("ix_min", "ix_max", "iy_min", "iy_max", "iz_min", "iz_max")
            },
        }
        reports.append(report)
        groups[(vine.rootstock, vine.timepoint)].append(report)
    for path in sorted((data_dir / "VTP_Files").glob("T*/*.vtp")):
        document = ET.parse(path).getroot()
        vtp_fields.update(e.get("Name", "unnamed") for e in document.iter("DataArray"))
        for array in document.iter("DataArray"):
            if (
                array.get("Name") == "radius"
                and array.get("format", "ascii") == "ascii"
            ):
                radii.update(float(x) for x in (array.text or "").split())
    # No private coring files are opened. Only inventory the named public DATA tree.
    expected_keys = {(r["timepoint"], r["vine_id"]) for r in reports}
    if set(summaries) != expected_keys or set(cells) != expected_keys:
        raise ValueError("RSML and prepared vine keys differ")
    expected_groups = {
        (g, t) for g in ("101-14", "SO4", "R110") for t in ("T1", "T2", "T3", "T4")
    }
    coverage_passed = (
        len(reports) == 96
        and set(groups) == expected_groups
        and all(len(v) == 8 for v in groups.values())
    )
    grid_hash = digest(prepared_dir / "voxel_grid.csv")
    identity_passed = grid_hash == EXPECTED_GRID_SHA256 and grid_hash == digest(
        repo / "data/grapevine/fichtl_2024_voxel_grid.csv"
    )
    extensions = Counter(p.suffix.lower() for p in data_dir.rglob("*") if p.is_file())
    biomass = {
        "scope": "named Grapevine3D DATA tree and prepared table headers only",
        "candidate_measurement_tables": [
            str(p.relative_to(data_dir))
            for p in data_dir.rglob("*")
            if p.suffix.lower() in (".csv", ".xlsx", ".xls", ".tsv")
        ],
        "mass_columns_in_prepared_tables": [
            c
            for cols in schemas.values()
            for c in cols
            if any(x in c.lower() for x in ("mass", "weight", "srl"))
        ],
        "join_status": "NOT_POSSIBLE_NO_MATCHED_MASS_TABLE",
        "matched_vines": 0,
        "unmatched_vines": len(reports),
        "duplicate_mass_keys": None,
        "duplicate_mass_keys_reason": "No measurement table available to audit",
        "block_mapping": "UNAVAILABLE; do not infer experimental blocks from ID spelling",
    }
    # Membership is provisional and deterministic, with no geometry-based selection.
    pilot = groups[("101-14", "T1")]
    membership = sorted(
        [r["vine_id"] for r in pilot],
        key=lambda x: hashlib.sha256(("DRG-G3D-01-v1/T1/" + x).encode()).hexdigest(),
    )
    configuration = {
        "status": "PROPOSED_NOT_EXECUTED",
        "version": "DRG-G3D-01-v1",
        "source_revision": manifest["source_revision"],
        "lock_sha256": digest(repo / "poetry.lock"),
        "grid_sha256": digest(prepared_dir / "voxel_grid.csv"),
        "paths": {
            "raw_data": str(data_dir.resolve()),
            "prepared": str(prepared_dir.resolve()),
            "support_and_qc": str(out / "per_vine_qc.json"),
        },
        "group": {"rootstock": "101-14", "timepoint": "T1"},
        "training_ids": membership[2:],
        "held_out_ids": membership[:2],
        "split_rule": "ascending SHA256(DRG-G3D-01-v1/T1/ + vine_id); first two held out",
        "split_status": "PROVISIONAL_UNGROUPED_NOT_POPULATION_QUALIFIED",
        "observation": {
            "grid_cm": 10,
            "length_source": "geometric",
            "depth_positive": True,
            "stem": "excluded",
            "invalid_roots": "excluded_and_reported",
            "outside_support": "unobserved",
            "mass_constraint": None,
            "transform": "x=x_sim; y=y_sim; positive_depth_cm=20-z_sim",
            "face_rule": "floor(coord/10) in positive depth; half-open upper faces",
            "topology_status": "NOT_QUALIFIED_LABEL_NESTING_MISMATCH",
            "shallow_band_status": "MODEL_GAP_VALID_ROOTS_CONFINED_TO_DEPTH_APPROX_20_OR_MORE",
        },
        "method_documents": {
            p.name: {"path": str(p.resolve()), "sha256": digest(p)}
            for p in sorted((repo / "docs/research/grapevine3d").glob("*"))
            if p.is_file()
        },
        "seeds": {
            "optimizer": 20261114,
            "training": [4101, 4102, 4103],
            "fresh": list(range(5101, 5121)),
            "select_best_seed": False,
        },
        "active_bounds": {
            "min_primary_length": [8, 14],
            "max_primary_length": [16, 24],
            "min_sec_root_length": [4, 20],
            "max_sec_root_length": [30, 70],
            "interbranch_distance": [0.25, 8.0],
            "gravitropism": [0.0, 0.75],
        },
        "bounds_status": "ENGINEERING_EXPLORATION_PROPOSAL_NOT_PAPER_PRIORS",
        "baseline_active_parameters": {
            "min_primary_length": 10,
            "max_primary_length": 20,
            "min_sec_root_length": 10,
            "max_sec_root_length": 50,
            "interbranch_distance": 2.0,
            "gravitropism": 0.1,
        },
        "fixed_generator_parameters": {
            "max_order": 5,
            "outer_root_num": 5,
            "inner_root_num": 6,
            "segments_per_root": 10,
            "length_reduction": 0.5,
            "min_sec_root_num": 2,
            "max_sec_root_num": 6,
            "growth_sec_root": 0.2,
            "root_vary": 30,
            "floor_threshold": 0.1,
            "ceiling_threshold": 0.9,
            "base_diameter": 0.27,
            "apex_diameter": 0.05,
            "diameter_reduction": 0.5,
            "fine_root_threshold": 0.06,
            "root_tissue_density": 0.05,
            "root_ratio": 0.5,
            "mechanical_constraints": 0.5,
            "t": 0,
            "enable_soil": False,
            "max_val_attempts": 50,
            "no_root_zone": 0.0001,
            "simulation_tag": "DRG-G3D-PROPOSED",
        },
        "fixed_parameters_status": "ENGINEERING_SCENARIO_REQUIRES_ACCEPTANCE_NOT_BIOLOGICAL_PRIORS",
        "objective": {
            "version": "balanced-voxel-absolute-v1",
            "occupied_weight": 0.5,
            "zero_weight": 0.5,
            "scaling": "training-only q75 positive RLD, floor 1e-6",
            "quantile_method": "numpy.quantile(method=linear)",
            "mass_weight": 0,
            "order_weight": 0,
            "total_length_weight": 0,
            "architecture_arm": "0.8 voxel + 0.2 normalized order-count/mean-length MAE",
        },
        "budget": {
            "candidate_sets": 50,
            "training_seeds": 3,
            "training_generator_calls": 150,
            "fresh_generator_calls": 20,
            "max_generator_calls_total": 170,
            "candidate_allocation": {
                "baseline": 1,
                "rld_only": 25,
                "rld_architecture": 24,
            },
            "fresh_allocation": {"baseline": 6, "rld_only": 7, "rld_architecture": 7},
            "cpu_workers": 1,
            "cpu_threads": 2,
            "wall_hours": 2,
            "storage_gib": 2,
        },
        "launchable": False,
        "gates": [
            "accepted scientific contract",
            "matched supported runtime",
            "common-operator face tests",
            "synthetic adequacy and timing",
            "block map for population claims",
            "label-to-organ definition for architecture arm",
            "shallow-root support and validation mechanism decision",
        ],
    }
    dump(out / "input_manifest.json", manifest)
    dump(out / "per_vine_qc.json", reports)
    dump(out / "biomass_join_audit.json", biomass)
    dump(out / "pilot.proposed.json", configuration)
    dump(
        out / "schema_coverage.json",
        {
            "schemas": schemas,
            "units": dict(unit_counts),
            "root_labels": dict(labels),
            "label_nesting_mismatches": hierarchy_mismatches,
            "topology_status": (
                "NOT_QUALIFIED" if hierarchy_mismatches else "LABEL_DEPTH_CHECK_ONLY"
            ),
            "label_nesting_pairs": [
                {"depth": k[0], "label": k[1], "n": v}
                for k, v in sorted(hierarchy_pairs.items())
            ],
            "vtp_array_names": dict(vtp_fields),
            "data_extensions": dict(extensions),
            "vtp_radius_audit": {
                "unique_values": len(radii),
                "min": min(radii) if radii else None,
                "max": max(radii) if radii else None,
                "value_counts": dict(radii),
                "provenance": "UNVERIFIED; presence is not measured-diameter evidence",
            },
            "vine_count": len(reports),
            "duplicate_cells": duplicate_cells,
            "all_geometry_qc_passed": all(r["passed"] for r in reports),
            "frozen_identity_passed": identity_passed,
            "expected_coverage_passed": coverage_passed,
            "grid_cell_count": sum(r["grid_cell_count"] for r in reports),
            "occupied_cell_count": sum(r["occupied_cell_count"] for r in reports),
            "max_total_error_cm": max(r["total_error_cm"] for r in reports),
            "groups": [
                {
                    "rootstock": k[0],
                    "timepoint": k[1],
                    "n": len(v),
                    "mean_original_length_cm": sum(r["original_length_cm"] for r in v)
                    / len(v),
                }
                for k, v in sorted(groups.items())
            ],
            "grid_identical_to_upstream": digest(prepared_dir / "voxel_grid.csv")
            == digest(repo / "data/grapevine/fichtl_2024_voxel_grid.csv"),
        },
    )
    print(
        json.dumps(
            {
                "output": str(out),
                "vines": len(reports),
                "all_geometry_qc_passed": all(r["passed"] for r in reports),
                "frozen_identity_passed": identity_passed,
                "expected_coverage_passed": coverage_passed,
                "topology_status": (
                    "NOT_QUALIFIED"
                    if hierarchy_mismatches
                    else "LABEL_DEPTH_CHECK_ONLY"
                ),
                "duplicate_cells": duplicate_cells,
                "mass_join": biomass["join_status"],
            }
        )
    )
    if (
        duplicate_cells
        or not all(r["passed"] for r in reports)
        or not coverage_passed
        or not identity_passed
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--prepared-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    audit(
        args.data_dir,
        args.prepared_dir,
        args.output_dir,
        Path(__file__).resolve().parents[2],
    )
