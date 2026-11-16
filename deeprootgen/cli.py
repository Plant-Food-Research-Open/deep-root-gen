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

    from .data_model import RootSimulationModel
    from .model import RootSystemSimulation

    target = Path(outdir).expanduser().resolve()
    if target.exists():
        raise FileExistsError(f"Output directory already exists: {target}")
    parameters = RootSimulationModel(**spec)
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
