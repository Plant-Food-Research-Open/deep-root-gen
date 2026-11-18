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
    Existing directories are never overwritten.
    """
    import numpy as np

    from .data_model import RootSimulationModel, RootSimulationConfig
    from .model import RootSystemSimulation

    target = Path(outdir).expanduser().resolve()
    if target.exists():
        raise FileExistsError(f"Output directory already exists: {target}")
    if "construction" in spec and "schema_version" not in spec:
        raise ValueError("Extended construction requires explicit schema_version=2")
    parameters = (
        RootSimulationConfig(**spec)
        if "schema_version" in spec
        else RootSimulationModel(**spec)
    )
    simulation = RootSystemSimulation(
        random_seed=parameters.random_seed,
        simulation_tag=parameters.simulation_tag,
    )
    simulation.run(parameters)
    nodes, edges = simulation.G.as_df()
    geometry = nodes[["x", "y", "z", "length", "diameter"]].to_numpy()
    if not np.isfinite(geometry).all():
        raise ValueError("Simulation geometry contains non-finite values")
    target.mkdir(parents=True, exist_ok=False)
    nodes.to_csv(target / "nodes.csv", index=False)
    edges.to_csv(target / "edges.csv", index=False)
    resolved = parameters.model_dump()
    (target / "parameters.json").write_text(json.dumps(resolved, indent=2) + "\n")
    if isinstance(parameters, RootSimulationConfig):
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
        result.organ_table.to_csv(target / "organs.csv", index=False)
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
            json.dumps(resolved, sort_keys=True).encode()
        ).hexdigest(),
        "outputs": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(target.iterdir())
        },
        "scientific_validation": "not performed",
    }
    (target / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main(argv=None) -> int:
    """Parse the small command contract; help does not import model dependencies."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("simulate", help="run and export an offline simulation")
    run.add_argument("--config", required=True, type=Path, help="model parameter JSON")
    run.add_argument("--outdir", required=True, type=Path, help="new output directory")
    args = parser.parse_args(argv)
    try:
        spec = json.loads(args.config.read_text())
        result = simulate(spec, args.outdir)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"Simulation failed: {exc}\n")
    print(json.dumps(result, indent=2))
    return 0
