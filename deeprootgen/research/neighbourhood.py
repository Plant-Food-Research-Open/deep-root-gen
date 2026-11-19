"""Generate single-vine realizations for specified planting positions in centimetres."""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class VinePlacement:
    x_cm: float
    y_cm: float
    seed: int


def neighbourhood_plan(
    origins_cm,
    focal_seed: int,
    mode: Literal["translated", "independent"] = "translated",
):
    """Keep the focal seed fixed and assign a reproducible seed to each origin.

    Coordinates are offsets from the focal crown in the model's horizontal frame.
    The returned tuple preserves the input order. Reordering the same origins
    preserves the seed attached to each position.
    """
    if mode not in ("translated", "independent"):
        raise ValueError("mode must be translated or independent")
    if (
        isinstance(focal_seed, (bool, np.bool_))
        or not isinstance(focal_seed, (int, np.integer))
        or focal_seed < 0
    ):
        raise ValueError("focal_seed must be a nonnegative integer")
    positions = np.asarray(origins_cm, dtype=float)
    if (
        positions.ndim != 2
        or positions.shape[1] != 2
        or not np.isfinite(positions).all()
    ):
        raise ValueError("origins_cm must contain finite (x, y) pairs")
    offsets = [tuple(xy) for xy in positions.tolist()]
    if (0.0, 0.0) not in offsets or len(set(offsets)) != len(offsets):
        raise ValueError("supply distinct origins including the focal (0, 0)")
    focal_seed = int(focal_seed)
    seeds = dict.fromkeys(offsets, focal_seed)
    if mode == "independent":
        rng = np.random.default_rng(np.random.SeedSequence([focal_seed, 0x56494E45]))
        used = {focal_seed}
        for xy in sorted(set(offsets) - {(0.0, 0.0)}):
            seed = int(rng.integers(0, 2**32))
            while seed in used:
                seed = int(rng.integers(0, 2**32))
            seeds[xy] = seed
            used.add(seed)
    return tuple(VinePlacement(*xy, seeds[xy]) for xy in offsets)


@dataclass(frozen=True)
class NeighbourhoodGraph:
    """Translated graph records and the seed/identity for each plant_id."""

    nodes: "pd.DataFrame"
    edges: "pd.DataFrame"
    plants: "pd.DataFrame"


def generate_neighbourhood(config, origins_cm, mode="translated") -> NeighbourhoodGraph:
    """Grow a focal vine and place translated copies or independent vines around it.

    Accepts a seeded native configuration through the standard parser. All
    translations follow growth. Each offset specifies the displacement from
    that vine's original crown location. Lengths and diameters remain in cm.
    """
    from deeprootgen.data_model.resolution import parse_config
    from deeprootgen.model import RootSystemSimulation

    document = parse_config(config)
    plan = neighbourhood_plan(origins_cm, document.random_seed, mode)

    def grow(seed):
        simulation = RootSystemSimulation(
            random_seed=seed, simulation_tag=document.simulation_tag
        )
        supplied = document.model_dump(mode="json", exclude_unset=True)
        supplied["random_seed"] = seed
        simulation.run(supplied)
        nodes, edges = simulation.G.as_df()
        return nodes, edges, simulation.result.metadata["run_identity_sha256"]

    template = grow(document.random_seed)
    plants, node_tables, edge_tables = [], [], []
    node_offset = organ_offset = 0
    for plant_id, site in enumerate(plan):
        nodes, edges, identity = (
            template if site.seed == document.random_seed else grow(site.seed)
        )
        if nodes.plant_id.nunique() != 1:
            raise ValueError("Each input realization must describe a single vine")
        placed = nodes.copy()
        placed["plant_id"] = plant_id
        placed["node_id"] += node_offset
        placed.loc[placed.parent_id >= 0, "parent_id"] += node_offset
        placed["organ_id"] += organ_offset
        placed["x"] += site.x_cm
        placed["y"] += site.y_cm
        links = (
            edges.reindex(columns=["parent_id", "child_id"]).astype("int64")
            + node_offset
        )
        plants.append(
            dict(
                plant_id=plant_id,
                x_cm=site.x_cm,
                y_cm=site.y_cm,
                seed=site.seed,
                run_identity_sha256=identity,
                node_id_offset=node_offset,
                organ_id_offset=organ_offset,
            )
        )
        node_tables.append(placed)
        edge_tables.append(links)
        node_offset = int(placed.node_id.max()) + 1
        organ_offset = int(placed.organ_id.max()) + 1
    return NeighbourhoodGraph(
        pd.concat(node_tables, ignore_index=True),
        pd.concat(edge_tables, ignore_index=True),
        pd.DataFrame(plants),
    )


def export_neighbourhood(config_path, origins_path, mode, outdir):
    """Write the graph, seed map and replay inputs into a new directory."""
    import json
    import os
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from deeprootgen.data_model.resolution import load_json_config

    target = Path(outdir).resolve()
    if target.exists():
        raise FileExistsError(f"Output directory already exists: {target}")
    origins = json.loads(Path(origins_path).read_text())
    config = load_json_config(Path(config_path))
    graph = generate_neighbourhood(config, origins, mode)
    receipt = dict(
        mode=mode,
        plant_count=len(graph.plants),
        focal_seed=config["random_seed"],
        coordinate_units="cm",
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=target.parent) as tmp:
        stage = Path(tmp) / "export"
        stage.mkdir()
        graph.nodes.to_csv(stage / "nodes.csv", index=False)
        graph.edges.to_csv(stage / "edges.csv", index=False)
        graph.plants.to_csv(stage / "plants.csv", index=False)
        for name, value in (
            ("config", config),
            ("origins", origins),
            ("manifest", receipt),
        ):
            (stage / f"{name}.json").write_text(
                json.dumps(value, indent=2, allow_nan=False) + "\n"
            )
        # Reserve the name before publishing so concurrent callers cannot replace a result.
        target.mkdir()
        try:
            os.replace(stage, target)
        except OSError:
            target.rmdir()
            raise
    return receipt
