"""Result class and record-based construction-step law kernels.

The fixed engine (``model/engine.py``) owns phase order; these pure functions
are the construction-step attachment-relocation and partition leaf laws over a
records view of the workspace. There is no complete runner here.
"""

import copy
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


XYZ = ["x", "y", "z"]


@dataclass
class SimulationResult:
    metadata: dict
    organ_table: pd.DataFrame = field(default_factory=pd.DataFrame)
    diagnostics: dict = field(default_factory=dict)
    crown_support: dict = field(default_factory=dict)
    node_metadata: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Resolved description (active laws, inactive values, hashes) of engine runs.
    resolved: dict = field(default_factory=dict)
    # Engine receipts: lifecycle trace, RNG fingerprint, keyed streams, law receipts.
    engine: dict = field(default_factory=dict)

    def capability(self, name):
        """Result capabilities select views; route labels never do."""
        return bool(self.metadata.get("capabilities", {}).get(name, False))

    def cohort_tables(self, graph):
        """Explicit historical full-support view; canonical graph stays root-only."""
        if not self.capability("crown_support_view"):
            raise ValueError("Crown support view requires a result with crown support metadata")
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
        if self.capability("tree_to_vine_map"):
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
