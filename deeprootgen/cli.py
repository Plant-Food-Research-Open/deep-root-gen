"""Offline execution and explicit exports using the existing simulation API."""

import argparse
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path


def simulate(spec: dict, outdir: str | Path) -> dict:
    """Run a simulation and export to a new directory without services.

    The caller supplies model parameters; no calibration or uploads occur.
    Existing directories are never overwritten. Input is parsed and resolved
    by the shared resolver before any directory or simulation state exists.
    """
    from .data_model.resolution import canonical_input, resolve_config
    from .model import RootSystemSimulation

    return _export(spec, outdir, resolve_config, canonical_input, RootSystemSimulation)


def _export(spec, outdir, resolve_config, canonical_input, simulation_class):
    import copy
    import numpy as np

    spec = copy.deepcopy(spec)
    resolved = resolve_config(spec)
    parameters = resolved.config
    target = Path(outdir).expanduser().resolve()
    if target.exists():
        raise FileExistsError(f"Output directory already exists: {target}")
    simulation = simulation_class(
        random_seed=parameters.random_seed,
        simulation_tag=parameters.simulation_tag,
    )
    # Pass the raw input so every caller records the same supplied-input hash.
    simulation.run(spec)
    nodes, edges = simulation.G.as_df()
    geometry = nodes[["x", "y", "z", "length", "diameter"]].to_numpy()
    if not np.isfinite(geometry).all():
        raise ValueError("Simulation geometry contains non-finite values")
    target.mkdir(parents=True, exist_ok=False)
    nodes.to_csv(target / "nodes.csv", index=False)
    edges.to_csv(target / "edges.csv", index=False)
    resolved_parameters = canonical_input(parameters)
    (target / "parameters.json").write_text(json.dumps(resolved_parameters, indent=2) + "\n")
    if resolved.source_schema != "flat":
        import plotly.graph_objects as go

        figure = go.Figure()
        lookup = nodes.set_index("node_id")
        points = []
        for parent, child in edges[["parent_id", "child_id"]].itertuples(
            index=False, name=None
        ):
            points.extend(
                [
                    lookup.loc[parent, ["x", "y", "z"]].tolist(),
                    lookup.loc[child, ["x", "y", "z"]].tolist(),
                    [None, None, None],
                ]
            )
        if points:
            figure.add_trace(
                go.Scatter3d(
                    x=[p[0] for p in points],
                    y=[p[1] for p in points],
                    z=[p[2] for p in points],
                    mode="lines",
                    name="Root axes",
                )
            )
        figure.update_layout(scene=dict(aspectmode="data"))
        figure.write_html(target / "roots.html")
        result = simulation.result
        if "root_summary" in result.metadata:
            (target / "root_summary.json").write_text(
                json.dumps(result.metadata["root_summary"], indent=2, allow_nan=False) + "\n"
            )
        result.organ_table.to_csv(target / "organs.csv", index=False)
        if "irrigation" in result.diagnostics:
            (target / "irrigation.json").write_text(json.dumps(result.diagnostics["irrigation"], allow_nan=False) + "\n")
        if "branching" in result.diagnostics:
            (target / "branching.json").write_text(
                json.dumps(result.diagnostics["branching"], indent=2, allow_nan=False) + "\n"
            )
        _export_spatial_receipts(result.diagnostics, target)
        if not result.node_metadata.empty:
            result.node_metadata.to_csv(target / "node_metadata.csv", index=False)
        (target / "execution.json").write_text(
            json.dumps(result.metadata, indent=2) + "\n"
        )
        (target / "crown_support.json").write_text(
            json.dumps(result.crown_support, indent=2) + "\n"
        )
    else:
        figure = simulation.init_fig(parameters)
        simulation.plot_root_system(figure, nodes).write_html(target / "roots.html")
    if simulation.result is not None and simulation.result.resolved:
        (target / "resolved_config.json").write_text(
            json.dumps(simulation.result.resolved, indent=2) + "\n"
        )
    versions = {
        name: importlib.metadata.version(name)
        for name in ("deeprootgen", "numpy", "pandas", "torch", "pydantic")
    }
    manifest = {
        "python": platform.python_version(),
        "dependencies": versions,
        "seed": parameters.random_seed,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "invalid_node_count": int(nodes.invalid_root.sum()),
        "config_sha256": hashlib.sha256(
            json.dumps(resolved_parameters, sort_keys=True).encode()
        ).hexdigest(),
        "outputs": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(target.iterdir())
        },
        "scientific_validation": "not performed",
    }
    if simulation.result is not None and simulation.result.resolved:
        manifest["model_identity"] = {
            key: simulation.result.metadata[key]
            for key in ("supplied_input_sha256", "effective_model_sha256", "run_identity_sha256")
            if key in simulation.result.metadata
        }
    from .data_model.resolution import source_identity
    from .run_records import repository_state

    provenance = simulation.result.engine.get("provenance", {}) if simulation.result is not None else {}
    manifest["execution_provenance"] = provenance
    manifest["source_sha256"] = provenance.get("source_sha256", source_identity())
    manifest["repository"] = repository_state()
    (target / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def _export_spatial_receipts(diagnostics, target):
    alignment = [
        dict(organ_id=item["organ_id"], order=item["order"], **item["row_alignment"])
        for item in diagnostics.get("curvature", ()) if "row_alignment" in item
    ]
    for name, value in (
        ("row_alignment", alignment),
        ("vine_origin_catalogue", diagnostics.get("vine_origin_catalogue")),
    ):
        if value:
            (target / f"{name}.json").write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main(argv=None) -> int:
    """Parse the small command contract; help does not import model dependencies."""
    return _main(argv, simulate)


def _main(argv, run_config, explain=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("simulate", help="run and export an offline simulation")
    run.add_argument("--config", required=True, type=Path, help="model parameter JSON")
    run.add_argument("--outdir", type=Path, help="new output directory")
    run.add_argument(
        "--explain-config",
        action="store_true",
        help="print the resolved laws, inactive values and hashes, then exit without running",
    )
    group = commands.add_parser("neighbourhood", help="grow vines at supplied horizontal offsets")
    group.add_argument("--config", type=Path, required=True, help="seeded model parameter JSON")
    group.add_argument("--origins", type=Path, help="JSON array of [x_cm, y_cm] offsets")
    group.add_argument("--vine-distance-cm", type=float, help="distance along a row")
    group.add_argument("--row-distance-cm", type=float, help="distance between rows")
    group.add_argument("--mode", choices=("translated", "independent"), default="translated")
    group.add_argument("--outdir", type=Path, required=True, help="new graph export directory")
    args = parser.parse_args(argv)
    if args.command == "neighbourhood":
        from .research.neighbourhood import export_neighbourhood
        try:
            receipt = export_neighbourhood(args.config, args.origins, args.mode, args.outdir, vine_distance_cm=args.vine_distance_cm, row_distance_cm=args.row_distance_cm)
        except (OSError, ValueError, TypeError) as exc:
            parser.exit(1, f"Neighbourhood generation failed: {exc}\n")
        print(json.dumps(receipt, indent=2))
        return 0
    if not args.explain_config and args.outdir is None:
        parser.error("--outdir is required unless --explain-config is given")
    try:
        from .data_model.resolution import explain_config, load_json_config

        spec = load_json_config(args.config)
        if args.explain_config:
            result = (explain or explain_config)(spec)
        else:
            result = run_config(spec, args.outdir)
    except (OSError, ValueError, TypeError) as exc:
        if args.explain_config:
            # Dependency and validation errors are part of the explanation.
            print(json.dumps(dict(valid=False, error=str(exc)), indent=2))
        parser.exit(1, f"Simulation failed: {exc}\n")
    if args.explain_config:
        result = dict(valid=True, **result)
    print(json.dumps(result, indent=2))
    return 0
