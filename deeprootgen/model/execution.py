"""Native live-organ construction-step execution; no saved-skeleton replay."""

import copy
from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..utils.tropism import validate_row_axial_kappas
from .attachment import subdivide_primary
from .controlled_geometry import unit, minimal_rotation
from .interval_geometry import realize_intervals

XYZ = ["x", "y", "z"]


@dataclass
class SimulationResult:
    metadata: dict
    organ_table: pd.DataFrame = field(default_factory=pd.DataFrame)
    diagnostics: dict = field(default_factory=dict)
    crown_support: dict = field(default_factory=dict)
    node_metadata: pd.DataFrame = field(default_factory=pd.DataFrame)

    def cohort_tables(self, graph):
        """Explicit historical full-support view; canonical graph stays root-only."""
        if self.metadata["execution"] != "cohort_v5":
            raise ValueError("Cohort support view requires cohort execution")
        nodes, _ = graph.as_df()
        nodes = nodes.merge(self.node_metadata, on="node_id", validate="one_to_one")
        center = dict(
            node_id=0,
            parent_id=-1,
            plant_id=1,
            primary_tree_id=0,
            organ_id=0,
            order=0,
            segment_rank=0,
            **dict(zip(XYZ, self.crown_support["center_cm"])),
            diameter=0.0,
            length=0.0,
            root_tissue_density=float(nodes.root_tissue_density.iloc[0]),
            invalid_root=False,
            root_type="base",
            cohort="crown"
        )
        nodes.loc[nodes.order.eq(0), "parent_id"] = 0
        columns = list(center)
        nodes = pd.concat([pd.DataFrame([center]), nodes[columns]], ignore_index=True)
        edges = (
            nodes.loc[nodes.node_id.ne(0), ["parent_id", "node_id"]]
            .rename(columns={"node_id": "child_id"})
            .reset_index(drop=True)
        )
        return nodes, edges

    def observation_tables(self, graph):
        """One primary tree per temporary observer plant ID; preserve vine map."""
        nodes, edges = graph.as_df()
        if self.metadata["execution"] == "cohort_v5":
            nodes = nodes.merge(self.node_metadata, on="node_id", validate="one_to_one")
            nodes["vine_id"] = nodes.plant_id
            nodes["plant_id"] = nodes.primary_tree_id
        return nodes, edges


def _records(simulation):
    return {n.node_data.node_id: n.node_data.model_dump() for n in simulation.G.nodes}


def _organ_records(simulation):
    return [
        dict(
            organ_id=int(o.segments[0].node_data.organ_id),
            order=order,
            parent_id=int(o.parent_node.node_data.node_id),
            node_ids=[int(n.node_data.node_id) for n in o.segments],
        )
        for order in sorted(simulation.organs)
        for o in simulation.organs[order]
    ]


def _relocate(rows, organs, fraction):
    """Shared pure attachment geometry, committed with native object links later."""
    from .attachment import _primary_curves, _placements, transform_rows

    nodes = pd.DataFrame(list(rows.values()))
    lookup = nodes.set_index("node_id")
    for organ in organs:
        parent = lookup.loc[organ["parent_id"]]
        chain = nodes.loc[
            (nodes.organ_id == parent.organ_id)
            & (nodes.segment_rank <= parent.segment_rank)
        ]
        organ["attachment_arc_cm"] = float(chain.length.sum())
    curves = _primary_curves(organs, nodes)
    plans = _placements(organs, nodes, curves, fraction)
    transformed, inserted, _ = transform_rows(
        list(rows.values()), organs, curves, plans
    )
    rows.clear()
    rows.update(transformed)
    for organ in organs:
        chain = sorted(
            (
                nid
                for nid, row in rows.items()
                if row["organ_id"] == organ["organ_id"] and row["order"] > 0
            ),
            key=lambda nid: rows[nid]["segment_rank"],
        )
        organ["node_ids"] = chain
        organ["parent_id"] = rows[chain[0]]["parent_id"]
    return inserted


def _partition(organ, rows, source):
    lengths = source._construction_step_lengths_cm
    boundaries = source.construction_step_boundary_node_ids
    ids = organ["node_ids"]
    partitions, previous = [], -1
    for step, (length, boundary) in enumerate(zip(lengths, boundaries)):
        end = ids.index(boundary)
        fragments = ids[previous + 1 : end + 1]
        fractions = np.cumsum([rows[n]["length"] for n in fragments]) / length
        fractions[-1] = 1.0
        partitions.append(
            dict(
                step_index=step,
                length_cm=float(length),
                node_ids=fragments,
                fractions=fractions.tolist(),
            )
        )
        previous = end
    if previous != len(ids) - 1:
        raise ValueError("Construction partition does not cover organ")
    organ["construction_steps"] = dict(
        version="so4-construction-steps-v1",
        lengths_cm=lengths.tolist(),
        boundary_node_ids=list(boundaries),
        positioned_boundary_xyz=[
            [rows[n][k] for k in XYZ] for n in [organ["parent_id"], *boundaries]
        ],
        sampler=copy.deepcopy(source.construction_step_provenance),
    )
    return partitions


def _commit(simulation, rows, organs):
    """Publish validated row changes and synchronize native organ references."""
    graph = simulation.G
    live = graph.apply_records(rows)
    objects = {
        int(o.segments[0].node_data.organ_id): o
        for group in simulation.organs.values()
        for o in group
    }
    for record in organs:
        organ = objects[record["organ_id"]]
        organ.segments = [live[n] for n in record["node_ids"]]
        organ.parent_node = live[record["parent_id"]]
        organ.base_node = organ.segments[0]
        organ.child_organs = []
        for node in organ.segments:
            node.organ = organ
        organ.mass = organ.calculate_mass()
    for record in organs:
        organ = objects[record["organ_id"]]
        if record["order"] > 1:
            objects[rows[record["parent_id"]]["organ_id"]].child_organs.append(organ)
        # Remaining branch-node queues have already been consumed by init_organs.
        organ.lateral_attachment_nodes = []


def run_construction_steps(simulation, config, *, initial_recorder=None):
    p = config.construction.parameters.model_copy(
        update={"simulation_tag": "SO4-T2-controlled-INITIAL"}
    )
    simulation.simulation_tag = p.simulation_tag
    simulation.init_organs(p)
    simulation.position_secondary_roots(p)
    simulation.position_primary_roots(p)
    if initial_recorder is not None:
        initial_recorder(simulation, p)
    rows, organs = _records(simulation), _organ_records(simulation)
    if any(r["z"] > 20.0 for r in rows.values() if r["order"] <= 1):
        raise ValueError("Frozen primary scaffold exceeds common physical surface")
    if p.research_primary_attachment_distal_fraction:
        _relocate(rows, organs, p.research_primary_attachment_distal_fraction)
    objects = {
        int(o.segments[0].node_data.organ_id): o
        for group in simulation.organs.values()
        for o in group
    }
    kappas = validate_row_axial_kappas(
        p.research_insertion_row_axial_kappa, p.max_order
    )
    partitions = {
        o["organ_id"]: _partition(o, rows, objects[o["organ_id"]])
        for o in organs
        if o["order"] > 1
    }
    incoming, steps, fragments, receipts = {}, [], [], []

    def realize(organ):
        parts = partitions[organ["organ_id"]]
        records, mapping, receipt = realize_intervals(
            organ,
            parts,
            rows,
            p.model_dump(),
            config.random_seed,
            "minimum_angle_projection",
            20.0,
            kappas,
            incoming.get(organ["parent_id"]),
        )
        for item in mapping:
            incoming[item["node_id"]] = records[item["step_index"]]["accepted_heading"]
        steps.extend(records)
        fragments.extend(mapping)
        receipts.append(receipt)

    simulation._realize_organs(
        deque(
            sorted(
                (o for o in organs if o["order"] > 1),
                key=lambda o: (o["order"], o["organ_id"]),
            )
        ),
        realize,
    )
    # Pure final checks; never invoke native reorientation or consume shared RNG.
    for nid, row in rows.items():
        if row["order"] == 0:
            continue
        actual = np.linalg.norm(
            np.array([row[k] for k in XYZ])
            - np.array([rows[row["parent_id"]][k] for k in XYZ])
        )
        if row["z"] > 20.0 or not np.isclose(
            actual, row["length"], rtol=1e-5, atol=1e-6
        ):
            raise ValueError(
                "Native construction-step geometry failed integrity checks"
            )
    _commit(simulation, rows, organs)
    simulation.result = SimulationResult(
        metadata=dict(
            schema_version=2,
            execution="construction_steps_v1",
            seed=config.random_seed,
            requested_simulation_tag=config.simulation_tag,
            internal_simulation_tag=p.simulation_tag,
            coordinate_frame="model-x-across-y-along-depth20-minus-z-cm",
            biological_validation=False,
        ),
        organ_table=pd.DataFrame(
            [{k: v for k, v in o.items() if k != "construction_steps"} for o in organs]
        ),
        diagnostics=dict(
            construction_steps=steps, graph_fragments=fragments, organs=receipts
        ),
    )
