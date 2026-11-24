"""Generate a mature five-order research vine with stochastic terminal recruitment.

Use a native schema-4 potential vine with point-sampled taper on every order.
The output is a local NPZ of retained biological axes, including centreline
vertices (cm), biological IDs, parent IDs and the source taper parameters.
No sampled core locations or RLD measurements enter construction.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from deeprootgen.model import RootSystemSimulation


def retained_terminals(orders, organ_ids, depths_cm, seed, deep_probability, midpoint_cm):
    """Draw one persistent/absent outcome per terminal from its insertion depth."""
    if not 0 <= deep_probability <= 1 or not np.isfinite(midpoint_cm):
        raise ValueError("Recruitment needs a finite midpoint and a probability in [0, 1]")
    if not np.isfinite(depths_cm).all() or not np.isin(orders, [1, 2, 3, 4, 5]).all():
        raise ValueError("Expected five-order geometry with finite insertion depths")
    # Native biological IDs are dense positive integers. Key draws by ID so
    # that iterating over organs in a different order gives the same vine.
    rng = np.random.default_rng(np.random.SeedSequence([seed, 69273]))
    draws = rng.random(int(organ_ids.max()) + 1)[organ_ids]
    exponent = np.clip((depths_cm - midpoint_cm) / 8.0, -500, 500)
    probability = deep_probability + (1 - deep_probability) / (1 + np.exp(exponent))
    return (orders < 5) | (draws < probability)


def mature_axes(config, seed, deep_probability, midpoint_cm):
    if config.get("parameters", {}).get("max_order") != 5:
        raise ValueError("This research protocol requires a five-order native configuration")
    sim = RootSystemSimulation(random_seed=seed)
    sim.run(dict(config, random_seed=seed))
    if sim.result.metadata["root_summary"]["excluded_invalid_root_count"]:
        raise ValueError("Potential vine includes invalid organs")
    groups = [(order, organ) for order, organs in sim.organs.items() for organ in organs]
    orders = np.array([order for order, _ in groups])
    ids = np.array([organ.segments[0].node_data.organ_id for _, organ in groups])
    surface = config["parameters"].get("soil_surface_z_cm", 0.0)
    depths = np.array([surface - organ.parent_node.node_data.z for _, organ in groups])
    keep = retained_terminals(orders, ids, depths, seed, deep_probability, midpoint_cm)
    points, profiles, parents = [], [], []
    for (_, organ), retained in zip(groups, keep):
        if not retained:
            continue
        base = organ.parent_node.node_data
        points.append(np.vstack(([base.x, base.y, base.z], organ.get_coordinates())))
        parents.append(base.organ_id)
        material = organ.axis_state.material
        profiles.append([material["base"], material["tip"], material["midpoint"],
                         material.get("rate_per_cm", -1), material.get("thick_min_cm", 0)])
    return dict(points=np.vstack(points), sizes=np.array([len(curve) for curve in points]),
                order=orders[keep], parent=np.array(parents), profile=np.array(profiles),
                organ_id=ids[keep])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--deep-probability", type=float, required=True)
    parser.add_argument("--midpoint-cm", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    data = mature_axes(config, args.seed, args.deep_probability, args.midpoint_cm)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as handle:
        np.savez_compressed(handle, **data)


if __name__ == "__main__":
    main()

