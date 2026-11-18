"""Historical SO4 study protocol. For a fresh model use the schema-4 CLI.

Bounded local SO4 diagnostic ensembles; no fitting, services or uploads."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import signal
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

import networkx as nx
import numpy as np
import pandas as pd

from deeprootgen.data_model import RootSimulationModel
from deeprootgen.archive.simulation import RootSystemSimulation

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "g3d_converter", REPO / "scripts/data/grapevine3d_grid.py"
)
converter = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = converter
spec.loader.exec_module(converter)
CLASSES = ("primary", "secondary", "tertiary", "quaternary", "quinary")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def scenario_parameters(name, literature):
    """Public, frozen proxy transformations; no observed values enter here."""
    p = dict(
        random_seed=4101,
        max_order=5,
        root_ratio=0.5,
        fine_root_threshold=0.15,
        outer_root_num=5,
        inner_root_num=5,
        min_primary_length=15.0,
        max_primary_length=40.0,
        base_diameter=0.5,
        diameter_reduction=0.2,
        apex_diameter=0.05,
        min_sec_root_num=1,
        max_sec_root_num=3,
        growth_sec_root=0.1,
        min_sec_root_length=3.0,
        max_sec_root_length=15.0,
        segments_per_root=6,
        length_reduction=0.7,
        root_vary=10.0,
        interbranch_distance=2.0,
        mechanical_constraints=0.0,
        root_tissue_density=0.15,
        gravitropism=0.01,
        t=0,
        enable_soil=False,
    )
    if name == "upstream_example":
        return p
    reduction = (
        literature["tertiary_length_mean_cm"] / literature["secondary_length_mean_cm"]
    )
    p.update(
        max_order=3,
        outer_root_num=4,
        inner_root_num=5,
        min_primary_length=literature["primary_length_mean_cm"]
        - math.sqrt(3) * literature["primary_length_sd_cm"],
        max_primary_length=literature["primary_length_mean_cm"]
        + math.sqrt(3) * literature["primary_length_sd_cm"],
        min_sec_root_length=(
            literature["secondary_length_mean_cm"]
            - math.sqrt(3) * literature["secondary_length_sd_cm"]
        )
        / reduction,
        max_sec_root_length=(
            literature["secondary_length_mean_cm"]
            + math.sqrt(3) * literature["secondary_length_sd_cm"]
        )
        / reduction,
        length_reduction=reduction,
        min_sec_root_num=2,
        max_sec_root_num=4,
        growth_sec_root=0.35,
        floor_threshold=0.1,
        ceiling_threshold=0.9,
        segments_per_root=10,
        interbranch_distance=4.8,
        base_diameter=0.36,
        root_tissue_density=0.05,
        fine_root_threshold=0.06,
        gravitropism=0.1,
    )
    if name in ("branching_capacity", "fichtl_tropism"):
        p["interbranch_distance"] = 0.75
    if name == "fichtl_tropism":
        p.update(
            gravitropism=0.0,
            tropism_mode="fichtl2024",
            soil_surface_z_cm=20,
            fichtl_probability_down=0.65,
            fichtl_sigma=0.2,
            fichtl_trials_type2=2.0,
            fichtl_trials_type3=1.0,
            fichtl_theta2_deg=51.8,
            fichtl_theta2_sd_deg=22.5,
            fichtl_theta3_deg=50.4,
            fichtl_theta3_sd_deg=22.5,
        )
    if name not in ("paper_proxy", "branching_capacity", "fichtl_tropism"):
        raise ValueError(f"Unknown scenario {name}")
    return p


def node_segments(nodes, base_depth=20, include_invalid=False):
    """Explicit child edges transformed to across-row/along-row/positive depth."""
    by_id = nodes.set_index("node_id")
    result, invalid = [], []
    for row in nodes.itertuples():
        if row.order == 0:
            continue
        if row.parent_id not in by_id.index:
            raise ValueError("Missing graph parent")
        parent = by_id.loc[row.parent_id]
        label = CLASSES[row.order - 1] if 1 <= row.order <= 5 else "other"
        start = (float(parent.x), float(parent.y), base_depth - float(parent.z))
        end = (row.x, row.y, base_depth - row.z)
        segment = converter.Segment(start, end, label)
        record = (segment, int(row.organ_id))
        if row.invalid_root:
            invalid.append(record)
        if include_invalid or not row.invalid_root:
            result.append(record)
    return result, invalid


def summarize_geometry(records):
    """Finite soil geometry, per-label organ proxies and exact length accounting."""
    cells = defaultdict(float)
    org_lengths = defaultdict(float)
    kept_records, points, weighted_depth, vertical, above = [], [], 0.0, 0.0, 0.0
    for segment, organ in records:
        kept, excluded = converter.clip_to_soil(segment)
        above += excluded
        if kept is None or math.dist(kept.start, kept.end) == 0:
            continue
        length = math.dist(kept.start, kept.end)
        org_lengths[(kept.root_class, organ)] += length
        weighted_depth += length * (kept.start[2] + kept.end[2]) / 2
        vertical += abs(kept.end[2] - kept.start[2])
        kept_records.append(kept)
        points.extend((kept.start, kept.end))
        for cell, piece in converter.split_segment_into_cells(kept, 10.0):
            cells[cell] += piece
    soil = math.fsum(org_lengths.values())
    if not math.isclose(math.fsum(cells.values()), soil, abs_tol=1e-8 * max(1.0, soil)):
        raise ValueError("Geometric length conservation failed")
    coordinates = np.asarray(points) if points else np.zeros((1, 3))
    xspan, yspan = np.ptp(coordinates[:, :2], axis=0)
    metrics = dict(
        soil_length_cm=soil,
        above_surface_length_cm=above,
        mean_depth_cm=weighted_depth / soil if soil else 0,
        max_depth_cm=float(coordinates[:, 2].max()),
        across_row_span_cm=float(xspan),
        along_row_span_cm=float(yspan),
        row_across_span_ratio=float(yspan / xspan) if xspan else None,
        verticality=vertical / soil if soil else 0,
        shallow_fraction=(
            sum(v for k, v in cells.items() if k[2] < 2) / soil if soil else 0
        ),
    )
    for label in CLASSES:
        lengths = [v for (kind, organ), v in org_lengths.items() if kind == label]
        metrics[label + "_count"] = len(lengths)
        metrics[label + "_mean_length_cm"] = float(np.mean(lengths)) if lengths else 0.0
        metrics[label + "_organ_sd_cm"] = (
            float(np.std(lengths, ddof=1)) if len(lengths) > 1 else 0.0
        )
    return metrics, dict(cells), kept_records


def score_grid(predicted, observed, scale):
    keys = [
        tuple(int(v) for v in row) for row in observed[["ix", "iy", "iz"]].to_numpy()
    ]
    y = observed.root_length_cm.to_numpy(float)
    p = np.array([predicted.get(k, 0.0) for k in keys])
    occupied = y > 0
    if not occupied.any() or occupied.all():
        raise ValueError("Expected both occupied and digitized-zero cubes")
    occupied_mae = float(np.abs(p[occupied] - y[occupied]).mean() / 1000)
    zero_mae = float(np.abs(p[~occupied] - y[~occupied]).mean() / 1000)
    in_prism = float(p.sum())
    total = math.fsum(predicted.values())
    metrics = dict(
        occupied_mae=occupied_mae,
        zero_mae=zero_mae,
        balanced_rld_mae=(occupied_mae + zero_mae) / 2,
        normalized_mae=(occupied_mae + zero_mae) / (2 * scale),
        predicted_in_prism_cm=in_prism,
        observed_in_prism_cm=float(y.sum()),
        exterior_length_cm=max(0.0, total - in_prism),
        exterior_fraction=max(0.0, total - in_prism) / total if total else 0.0,
    )
    for label, mask in (
        ("full", np.ones(len(keys), dtype=bool)),
        ("deep", observed.iz.to_numpy(int) >= 2),
    ):
        pp, yy = p[mask], y[mask]
        if yy.sum() > 0:
            metrics[label + "_shape_tv"] = (
                float(0.5 * np.abs(pp / pp.sum() - yy / yy.sum()).sum())
                if pp.sum()
                else 1.0
            )
            metrics[label + "_relative_length_error"] = float(
                (pp.sum() - yy.sum()) / yy.sum()
            )
        else:
            metrics[label + "_shape_tv"] = None
            metrics[label + "_relative_length_error"] = None
    return metrics


def measured_records(path):
    vine = converter.read_vine(path)
    document = ET.parse(path).getroot()
    stem = document.find("./scene/plant/root")
    records = []
    for organ, root in enumerate(stem.iter("root")):
        if root is stem:
            continue
        label = root.get("label", "other").lower()
        label = label if label in CLASSES else "other"
        points = [
            tuple(
                float(p.get(a)) - vine.surface_rsml_cm[i] for i, a in enumerate("xyz")
            )
            for p in root.findall("./geometry/polyline/point")
        ]
        records.extend(
            (converter.Segment(a, b, label), organ) for a, b in zip(points, points[1:])
        )
    return records


def check_graph(nodes, edges):
    if (
        not nodes.node_id.is_unique
        or not np.isfinite(nodes[["x", "y", "z", "length", "diameter"]]).all().all()
    ):
        raise ValueError("Invalid graph IDs or nonfinite geometry")
    graph = nx.DiGraph()
    graph.add_nodes_from(nodes.node_id)
    graph.add_edges_from(
        edges[["parent_id", "child_id"]].itertuples(index=False, name=None)
    )
    if (
        not nx.is_directed_acyclic_graph(graph)
        or len(edges) != len(nodes) - 1
        or not nx.is_weakly_connected(graph)
    ):
        raise ValueError("Graph is not a connected rooted tree")
    by_id = nodes.set_index("node_id")
    for row in nodes.itertuples():
        if row.order:
            parent = by_id.loc[row.parent_id]
            length = math.dist((parent.x, parent.y, parent.z), (row.x, row.y, row.z))
            if not math.isclose(length, row.length, rel_tol=1e-5, abs_tol=1e-6):
                raise ValueError("Parent attachment/recorded length mismatch")


def plot_outputs(
    out, observed_geometry, generated_geometry, traits, scores, primary_depth
):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    scenarios = list(generated_geometry)
    groups = ["measured"] + scenarios
    colors = ["#333333", "#a3a3a3", "#d18c25", "#2577b0", "#19836c"]
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)
    quantities = [
        ("soil_length_cm", "Valid soil root length (cm)"),
        ("max_depth_cm", "Maximum depth (cm)"),
        ("row_across_span_ratio", "Along-row / across-row span"),
        ("primary_count", "Label/order 1 organ count"),
        ("secondary_count", "Label/order 2 organ count"),
        ("tertiary_count", "Label/order 3 organ count"),
    ]
    for ax, (column, label) in zip(axes.flat, quantities):
        for index, group in enumerate(groups):
            frame = traits[
                (traits.scenario == group) & (traits.base_depth_cm == primary_depth)
            ]
            values = frame[column].dropna().to_numpy(float)
            ax.scatter(
                index + np.linspace(-0.12, 0.12, len(values)),
                values,
                color=colors[index],
                s=20,
            )
            ax.plot(
                [index - 0.2, index + 0.2],
                [np.mean(values)] * 2,
                color=colors[index],
                linewidth=2,
            )
        ax.set_xticks(range(len(groups)), groups, rotation=25, ha="right", fontsize=8)
        ax.set_ylabel(label)
    fig.suptitle(
        "SO4/T2: in-sample descriptive comparison; 20 cm base; no biomass validation"
    )
    fig.savefig(out / "architecture_comparison.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 6), constrained_layout=True)

    def depth_profile(items):
        values = np.zeros(25)
        for geometry in items:
            for seg in geometry:
                for cell, length in converter.split_segment_into_cells(seg, 10):
                    if 0 <= cell[2] < 25:
                        values[cell[2]] += length / len(items)
        return values

    observed_profile = depth_profile(list(observed_geometry.values()))
    axes[0].plot(
        observed_profile,
        np.arange(25) * 10 + 5,
        label="measured",
        color=colors[0],
        linewidth=2,
    )
    for i, group in enumerate(scenarios, 1):
        axes[0].plot(
            depth_profile(list(generated_geometry[group].values())),
            np.arange(25) * 10 + 5,
            label=group,
            color=colors[i],
        )
        subset = scores[
            (scores.scenario == group) & (scores.base_depth_cm == primary_depth)
        ]
        axes[1].scatter(
            [i] * len(subset), subset.normalized_mae, s=9, color=colors[i], alpha=0.4
        )
    axes[0].invert_yaxis()
    axes[0].set(
        xlabel="Mean full-soil length / 10 cm layer (cm)",
        ylabel="Depth below soil (cm)",
    )
    axes[0].legend(fontsize=8)
    axes[1].set_xticks(range(1, len(groups)), scenarios, rotation=25, ha="right")
    axes[1].set_ylabel("Balanced voxel absolute error / pooled positive RLD q75")
    fig.savefig(out / "density_comparison.png", dpi=170)
    plt.close(fig)

    observed_order = sorted(
        observed_geometry,
        key=lambda k: (sum(math.dist(s.start, s.end) for s in observed_geometry[k]), k),
    )
    representative = observed_order[len(observed_order) // 2]
    panels = [("Measured median soil-length vine", observed_geometry[representative])]
    representatives = {"measured_vine": representative}
    for group in scenarios:
        items = generated_geometry[group]
        ranks = sorted(
            items,
            key=lambda seed: (
                sum(math.dist(s.start, s.end) for s in items[seed]),
                seed,
            ),
        )
        selected = ranks[len(ranks) // 2]
        representatives[group] = selected
        panels.append((f"{group}: seed {selected} (median length)", items[selected]))
    columns = 3
    rows = math.ceil(len(panels) / columns)
    figure = make_subplots(
        rows=rows,
        cols=columns,
        specs=[[{"type": "scene"}] * columns for _ in range(rows)],
        subplot_titles=[p[0] for p in panels],
    )
    all_points = np.array(
        [p for _, segments in panels for seg in segments for p in (seg.start, seg.end)]
    )
    lower, upper = all_points.min(axis=0), all_points.max(axis=0)
    for index, (title, segments) in enumerate(panels):
        for order, kind in enumerate(CLASSES):
            selected = [s for s in segments if s.root_class == kind]
            xyz = [
                [v for s in selected for v in (s.start[a], s.end[a], None)]
                for a in range(3)
            ]
            figure.add_trace(
                go.Scatter3d(
                    x=xyz[0],
                    y=xyz[1],
                    z=[-v if v is not None else None for v in xyz[2]],
                    mode="lines",
                    line=dict(
                        width=3,
                        color=["#593d29", "#b16a2b", "#dea848", "#e4c58a", "#f0d9a9"][
                            order
                        ],
                    ),
                    name=kind,
                    legendgroup=kind,
                    showlegend=index == 0,
                ),
                row=index // columns + 1,
                col=index % columns + 1,
            )
    for index in range(1, rows * columns + 1):
        scene = "scene" if index == 1 else f"scene{index}"
        figure.layout[scene].update(
            xaxis=dict(title="Across row x (cm)", range=[lower[0], upper[0]]),
            yaxis=dict(title="Along row y (cm)", range=[lower[1], upper[1]]),
            zaxis=dict(title="z below soil (cm)", range=[-upper[2], 0]),
            aspectmode="data",
        )
    figure.update_layout(
        height=550 * rows,
        title="SO4/T2: measured polylines vs generated graphs; physical axes; median representatives; base 20 cm",
    )
    figure.write_html(out / "roots_3d.html", include_plotlyjs=True)
    save_json(out / "representatives.json", representatives)
    return representatives


def load_observations(config, data_dir, prepared_dir):
    if sha(prepared_dir / "voxel_grid.csv") != config["expected_grid_sha256"]:
        raise ValueError("Frozen prepared grid identity changed")
    grid = pd.read_csv(prepared_dir / "voxel_grid.csv")
    grid = grid[
        (grid.rootstock == config["rootstock"])
        & (grid.timepoint == config["timepoint"])
    ].copy()
    if (
        grid.vine_id.nunique() != 8
        or grid.duplicated(["vine_id", "ix", "iy", "iz"]).any()
    ):
        raise ValueError("Expected eight uniquely keyed SO4/T2 vines")
    inputs = [
        prepared_dir / name
        for name in ("voxel_grid.csv", "vine_summary.csv", "analysis_metadata.json")
    ]
    observed_geometry, traits = {}, []
    primary_depth = config["primary_base_depth_cm"]
    for vine_id, group in grid.groupby("vine_id", sort=True):
        path = data_dir / "RSML_Files" / config["timepoint"] / (vine_id + ".rsml")
        inputs.append(path)
        metrics, cells, geometry = summarize_geometry(measured_records(path))
        for row in group.itertuples():
            if not math.isclose(
                cells.get((row.ix, row.iy, row.iz), 0), row.root_length_cm, abs_tol=1e-8
            ):
                raise ValueError("Measured geometry/prepared cell mismatch")
        observed_geometry[vine_id] = geometry
        traits.append(
            dict(
                scenario="measured",
                seed=None,
                vine_id=vine_id,
                base_depth_cm=primary_depth,
                **metrics,
            )
        )
    scale = max(
        1e-6,
        float(
            np.quantile(
                grid.loc[grid.root_length_cm > 0, "rld_cm_per_cm3"],
                0.75,
                method="linear",
            )
        ),
    )
    return grid, observed_geometry, traits, inputs, scale


def run(config_path, data_dir, prepared_dir, out):
    config = json.loads(config_path.read_text())
    out = out.resolve()
    for protected in (data_dir.resolve(), prepared_dir.resolve()):
        if out == protected or protected in out.parents:
            raise ValueError("Output must be outside inputs")
    if subprocess.run(["git", "check-ignore", "-q", str(out)], cwd=REPO).returncode:
        raise ValueError("Output must be Git-ignored")
    out.mkdir(parents=True, exist_ok=False)
    grid, observed_geometry, traits, inputs, scale = load_observations(
        config, data_dir, prepared_dir
    )
    scores = []
    primary_depth = config["primary_base_depth_cm"]
    source_paths = sorted((REPO / "deeprootgen").rglob("*.py")) + [
        Path(__file__),
        config_path,
    ]
    source_paths += [
        REPO / "poetry.lock",
        REPO / "pyproject.toml",
        REPO / "scripts/data/grapevine3d_grid.py",
    ]
    manifest = dict(
        source_revision=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        dirty_status=subprocess.check_output(
            ["git", "status", "--short"], cwd=REPO, text=True
        ),
        files={str(p.resolve()): sha(p) for p in source_paths + inputs},
        config=config,
        interpreter=sys.version,
        executable=sys.executable,
        packages={
            p: importlib.metadata.version(p)
            for p in (
                "numpy",
                "pandas",
                "torch",
                "torch-geometric",
                "pydantic",
                "typing-extensions",
                "plotly",
                "matplotlib",
            )
        },
        rld_scale_cm_per_cm3=scale,
        design="NO_FITTING; IN_SAMPLE_DIAGNOSTIC; NO_BIOLOGICAL_VALIDATION",
    )
    save_json(out / "input_manifest.json", manifest)
    generated_geometry = {name: {} for name in config["scenarios"]}
    ledger, call = [], 0
    start = time.monotonic()

    def timeout_handler(signum, frame):
        raise TimeoutError("Per-call simulation budget exceeded")

    signal.signal(signal.SIGALRM, timeout_handler)
    for scenario in config["scenarios"]:
        parameters = scenario_parameters(scenario, config["literature"])
        save_json(
            out / f"parameters_{scenario}.json",
            RootSimulationModel(**parameters).model_dump(),
        )
        for seed in config["seeds"]:
            if (
                call >= config["budget"]["generator_calls"]
                or time.monotonic() - start >= config["budget"]["wall_seconds"]
            ):
                raise RuntimeError("Frozen call/time budget exhausted")
            call += 1
            elapsed = time.monotonic()
            receipt = dict(call=call, scenario=scenario, seed=seed, status="STARTED")
            ledger.append(receipt)
            save_json(out / "run_ledger.json", ledger)
            p = RootSimulationModel(
                **{
                    **parameters,
                    "random_seed": seed,
                    "simulation_tag": f"SO4-T2-{scenario}-{seed}",
                }
            )
            sim = RootSystemSimulation(
                random_seed=seed, simulation_tag=p.simulation_tag
            )
            before = []
            validate = sim.validate

            def record_validation(input_parameters, pitch=45, **kwargs):
                before.append(sim.G.as_df()[0].copy())
                validate(input_parameters, pitch, **kwargs)

            sim.validate = record_validation
            signal.setitimer(signal.ITIMER_REAL, config["budget"]["per_call_seconds"])
            try:
                sim.run(p)
            except Exception as error:
                receipt.update(
                    status="FAILED", error=type(error).__name__ + ": " + str(error)
                )
                save_json(out / "run_ledger.json", ledger)
                raise
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
            nodes, edges = sim.G.as_df()
            check_graph(nodes, edges)
            directory = out / "graphs" / scenario / str(seed)
            directory.mkdir(parents=True)
            nodes.to_csv(directory / "nodes.csv", index=False)
            edges.to_csv(directory / "edges.csv", index=False)
            before[-1].to_csv(directory / "nodes_before_validation.csv", index=False)
            aligned = nodes.copy()
            aligned["z"] -= primary_depth
            aligned.to_csv(directory / "nodes_soil_aligned.csv", index=False)
            save_json(directory / "parameters.json", p.model_dump())
            for base_depth in config["base_depths_cm"]:
                records, invalid = node_segments(nodes, base_depth)
                metrics, cells, geometry = summarize_geometry(records)
                invalid_metrics, invalid_cells, _ = summarize_geometry(invalid)
                raw_records, _ = node_segments(nodes, base_depth, include_invalid=True)
                raw_metrics, _, _ = summarize_geometry(raw_records)
                pre_records, _ = node_segments(
                    before[-1], base_depth, include_invalid=True
                )
                pre_metrics, _, _ = summarize_geometry(pre_records)
                metrics.update(
                    raw_soil_length_cm=raw_metrics["soil_length_cm"],
                    invalid_soil_length_cm=invalid_metrics["soil_length_cm"],
                    invalid_fraction=(
                        invalid_metrics["soil_length_cm"]
                        / raw_metrics["soil_length_cm"]
                        if raw_metrics["soil_length_cm"]
                        else 0.0
                    ),
                    invalid_shallow_length_cm=sum(
                        v for k, v in invalid_cells.items() if k[2] < 2
                    ),
                    prevalidation_soil_length_cm=pre_metrics["soil_length_cm"],
                    prevalidation_shallow_fraction=pre_metrics["shallow_fraction"],
                )
                traits.append(
                    dict(
                        scenario=scenario,
                        seed=seed,
                        vine_id=None,
                        base_depth_cm=base_depth,
                        **metrics,
                    )
                )
                if base_depth == primary_depth:
                    generated_geometry[scenario][seed] = geometry
                for vine_id, observed in grid.groupby("vine_id", sort=True):
                    scores.append(
                        dict(
                            scenario=scenario,
                            seed=seed,
                            vine_id=vine_id,
                            base_depth_cm=base_depth,
                            **score_grid(cells, observed, scale),
                        )
                    )
            receipt.update(
                status="COMPLETE",
                seconds=time.monotonic() - elapsed,
                nodes=len(nodes),
                edges=len(edges),
                tropism=getattr(sim, "tropism_diagnostics", None),
                validation=getattr(sim, "validation_diagnostics", None),
            )
            save_json(out / "run_ledger.json", ledger)
            if (
                sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
                > config["budget"]["storage_bytes"]
            ):
                raise RuntimeError("Frozen storage budget exceeded")
    traits = pd.DataFrame(traits)
    scores = pd.DataFrame(scores)
    traits.to_csv(out / "architecture_traits.csv", index=False)
    scores.to_csv(out / "voxel_comparisons.csv", index=False)
    mean_traits = (
        traits.groupby(["scenario", "base_depth_cm"])
        .mean(numeric_only=True)
        .drop(columns=["seed"], errors="ignore")
    )
    mean_scores = (
        scores.groupby(["scenario", "base_depth_cm"])
        .mean(numeric_only=True)
        .drop(columns=["seed"], errors="ignore")
    )
    mean_traits.to_csv(out / "mean_traits.csv")
    mean_scores.to_csv(out / "mean_scores.csv")
    representatives = plot_outputs(
        out, observed_geometry, generated_geometry, traits, scores, primary_depth
    )
    write_report(out, config, mean_traits, mean_scores, traits, ledger, representatives)
    if any(
        sha(p) != manifest["files"][str(p.resolve())] for p in source_paths + inputs
    ):
        raise RuntimeError("Input or source changed during run")
    save_json(
        out / "completion.json",
        dict(
            status="COMPLETE_DIAGNOSTIC_ONLY",
            generator_calls=call,
            seconds=time.monotonic() - start,
            artifacts={
                str(p.relative_to(out)): sha(p) for p in out.rglob("*") if p.is_file()
            },
        ),
    )
    print(
        json.dumps(dict(status="COMPLETE_DIAGNOSTIC_ONLY", calls=call, output=str(out)))
    )


def write_report(
    out, config, mean_traits, mean_scores, traits, ledger, representatives
):
    primary = config["primary_base_depth_cm"]
    columns = [
        "soil_length_cm",
        "max_depth_cm",
        "row_across_span_ratio",
        "shallow_fraction",
        "primary_count",
        "secondary_count",
        "tertiary_count",
        "invalid_fraction",
    ]

    def md_table(frame, wanted):
        frame = frame[[c for c in wanted if c in frame]].round(4).reset_index()
        lines = [
            "| " + " | ".join(map(str, frame.columns)) + " |",
            "| " + " | ".join(["---"] * len(frame.columns)) + " |",
        ]
        lines += [
            "| " + " | ".join(str(v) for v in row) + " |"
            for row in frame.itertuples(index=False, name=None)
        ]
        return "\n".join(lines)

    main_traits = mean_traits.xs(primary, level="base_depth_cm")
    main_scores = mean_scores.xs(primary, level="base_depth_cm")
    text = f"""# SO4/T2 local diagnostic architecture comparison

**Executed; no fitting or biological validation.** Eight measured vines are
compared with {len(config['seeds'])} fixed seeds per scenario. Published SO4/T2
means may derive from this cohort: these are in-sample consistency diagnostics.
No held-out population claim, biomass constraint or adopted calibration.

## Architecture at the fixed 20 cm root base

{md_table(main_traits, columns)}

## Realised lengths by label/order

{md_table(main_traits, [kind + suffix for kind in CLASSES[:3] for suffix in ('_mean_length_cm', '_organ_sd_cm')])}

These are means of per-vine/per-seed organ means and within-organ-population
SDs. They do not have the same sampling basis as the paper's between-vine SDs.
The paper's nominal SO4/T2 mean lengths are12.1/40.3/8.9 cm; fixed primary
number9 removes the reported between-vine count SD3. The count caps are not
realised counts; finite branching windows and spacing can bind first.

Full-soil generated length and observed digitized soil length have different
recovery/censoring limits. Compare in-prism lengths below as well. Counts are
labelled-polyline versus generated-order proxies; archive XML nesting does not
establish a reliable attachment topology. Seed variation is conditional on the
fixed configuration, not biological, parameter or posterior uncertainty.

## Voxel comparison at the fixed 20 cm root base

{md_table(main_scores, ['balanced_rld_mae','normalized_mae','exterior_fraction','full_shape_tv','deep_shape_tv','full_relative_length_error'])}

Errors are balanced occupied/zero-cell MAE in cm/cm³, divided by the observed
positive-cell q75 for normalized error. Shape TV is total variation of normalized
in-prism length vectors. Deep TV uses depth>=20 cm. Overflow is unobserved, not
penalized as biological absence. No best seed or post-fit rotation was selected.

## Figures and graphs

- [Measured and representative generated roots, interactive](roots_3d.html)
- [Architecture distributions](architecture_comparison.png)
- [Depth profiles and voxel errors](density_comparison.png)
- [Per-seed/per-vine comparisons](voxel_comparisons.csv)
- [Per-order and geometric traits](architecture_traits.csv)
- [Complete node/edge graphs](graphs/)
- [Source/config/input/runtime identity](input_manifest.json)
- [Every attempted generator call](run_ledger.json)

The displayed seed is the median valid-soil-length rank, independent of target
error. Graphs retain IDs, attachments and invalid flags; aligned z is negative
below the soil surface. The measured view contains only consecutive polyline
pieces, with no invented XML-parent connector. All 3D panels use common physical
axis ranges. No diameter or mass interpretation follows from line width.

## Transfer and mechanism gaps

1. Global4.8 cm spacing applied to short initial roots can limit secondary
   counts. The.75 cm capacity scenario is an assumption, not measured spacing.
2. A shared length reduction matches nominal order means approximately but
   predicts tertiary SD~2.67 cm rather than the printed1.0 cm, before the
   parent-segment increment. Between-vine SD is not individual-root SD.
3. Legacy validation prohibits valid geometry above the base and forces lateral
   apices downward. At20 cm depth it suppresses physically allowed shallow roots.
4. The optional Fichtl-inspired mode retains the generated primary scaffold,
   uses explicit paper-angle proxies and the stochastic objective search, and
   constrains roots at the actual surface20 cm above the base. It combines
   tropism, insertion and validation changes; their separate effects are not
   identified by this comparison. It is not an exact CPlantBox replay or age growth.
5. The kernel chooses one gravity/plagiotropism objective per segment. Exact
   historical switching granularity is unresolved. Candidate scaling and
   discretization, truncation of angle draws, and downward surface fallback are
   explicit implementation choices. See method documentation and tests.
6. Missing higher orders, a one-point crown, no row anisotropy, fixed primary
   number and simplified diameter profiles constrain architectural realism.
7. Recovery misses fine roots, observed zero is digitized zero, nesting is
   inconsistent, radius provenance and matched dry mass remain unresolved.

## Improvement plan

1. Reconcile public digitizer topology/labels, diameter provenance and paper
   totals; verify block mapping and matched dry mass before independent tests.
2. Replace shared length scaling with independently supported per-order current
   length distributions; distinguish vine variation from within-root variation.
3. Add evidence-backed order-specific spacing/count distributions and separate
   basal/apical branching zones. Validate realised distributions and attachment.
4. Isolate surface-only, insertion-only and tropism-only ablations; measure
   directional distributions by order/depth using verified topology. Refine the
   candidate search/discretization against the archived author implementation.
5. Represent a buried crown with distributed adventitious origins and verified
   row anisotropy. Use fixed observed-frame transforms, never score-driven rotation.
6. Only after synthetic/output adequacy, freeze an independently grouped split,
   uncertainty-aware objective and bounded calibration. Evaluate new vines/seeds.
7. Add whole-root dry mass only with defensible matched measurements and density/
   diameter units. Develop temporal growth separately from static reconstruction.

## Appendix: nonphysiological zero-depth alignment sensitivity

{md_table(mean_scores, ['normalized_mae','exterior_fraction','deep_shape_tv'])}

These use the same graphs translated to0 cm, not a calibrated origin. An improved
score indicates a support/alignment effect, not that the base is at0 cm. For
the physical-surface mode this translation also moves the soil constraint:
above-surface pieces are clipped and separately reported; it is not a second
physically consistent model run.

## Reproduction

Run the command in the maintained SO4 diagnostic method document with a fresh
ignored destination. Configuration and source hashes must match. The run used
{len(ledger)} generator calls with no retries. Inspect `completion.json` for file
hashes. Source/config modification requires a new run, not resumed evidence.
"""
    (out / "REPORT.md").write_text(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--prepared-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(
        args.config.resolve(),
        args.data_dir.resolve(),
        args.prepared_dir.resolve(),
        args.output_dir,
    )
