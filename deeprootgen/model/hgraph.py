"""Contains the hierarchical graph representation of the root system.

This module defines the hierarchical graph representation of the root system.
This includes integration with NetworkX and PyTorch Geometric.

"""

import base64
from io import StringIO
from typing import List

import networkx as nx
import numpy as np
import pandas as pd
import torch
import torch_geometric.transforms as T
from torch_geometric.data import Data
from torch_geometric.utils import from_networkx

from ..data_model import RootEdgeModel, RootNodeModel


class RootNode:
    """A node within the hierarchical graph representation of the root system."""

    def __init__(self, G: "RootSystemGraph", node_data: RootNodeModel) -> None:
        """RootNode constructor.

        Args:
            G: (RootSystemGraph):
                The hierarchical graph representation of the root system.
            node_data (RootNodeModel):
                The root node data model.

        Returns:
            RootNode:
                The RootNode instance.
        """
        self.G = G
        self.node_data = node_data

    def add_child_node(
        self, child_data: RootNodeModel, new_organ: bool = False
    ) -> "RootNode":
        """Add a child node to the hierarchical graph.

        Args:
            child_data (RootNodeModel):
                The node data for the child node.
            new_organ (bool):
                Whether the new child node belongs to a new plant organ.

        Returns:
            RootNode:
                The child node.
        """
        if new_organ:
            organ_id = self.G.increment_organ_id()
            segment_rank = 1
            order = self.node_data.order + 1  # type: ignore
        else:
            organ_id = self.node_data.organ_id  # type: ignore
            segment_rank = self.node_data.segment_rank + 1  # type: ignore
            order = self.node_data.order  # type: ignore

        child_data.parent_id = self.node_data.node_id
        child_data.organ_id = organ_id
        child_data.plant_id = self.node_data.plant_id
        child_data.segment_rank = segment_rank
        child_data.order = order

        child_node = self.G.add_node(child_data)
        edge_data = RootEdgeModel(
            parent_id=self.node_data.node_id, child_id=child_node.node_data.node_id
        )
        self.G.add_edge(edge_data)

        return child_node

    def as_dict(self) -> dict:
        """Return the graph node as a dictionary.

        Returns:
            dict:
                The node as a dictionary.
        """
        return self.node_data.dict()


class RootEdge:
    """An edge within the hierarchical graph representation of the root system."""

    def __init__(self, G: "RootSystemGraph", edge_data: RootEdgeModel) -> None:
        """RootEdge constructor.

        Args:
            G: (RootSystemGraph):
                The hierarchical graph representation of the root system.
            edge_data (RootEdgeModel):
                The root edge data model.

        Returns:
            RootEdge:
                The RootEdge instance.
        """
        self.G = G
        self.edge_data = edge_data

    def as_dict(self) -> dict:
        """Return the graph edge as a dictionary.

        Returns:
            dict:
                The edge as a dictionary.
        """
        return self.edge_data.dict()


class RootSystemGraph:
    """The hierarchical graph representation of the root system."""

    def __init__(self, create_base: bool = True) -> None:
        """RootSystemGraph constructor.

        Returns:
            RootSystemSimulation:
                The RootSystemGraph instance.
        """
        self.nodes: List[RootNode] = []
        self.edges: List[RootEdge] = []
        self.node_id = 0
        self.organ_id = 0

        # Base organ node
        self.base_node = None
        self.bases = []
        if create_base:
            node_data = RootNodeModel()
            node_data.organ_id = self.increment_organ_id()
            self.base_node = self.add_node(node_data)
            self.bases.append(self.base_node)

        self.organ_columns = dict(
            organ_coordinates=["x", "y", "z"],
            organ_classification=["root_type", "order_type", "position_type"],
            organ_hierarchy=["organ_id", "order", "segment_rank"],
            organ_size=["diameter", "length", "root_tissue_density"],
            organ_meta=["simulation_tag", "invalid_root"],
        )

    def add_node(self, node_data: RootNodeModel) -> RootNode:
        """Construct a new RootNode.

        Args:
            node_data (RootNodeModel):
                The root node data model.

        Returns:
            RootNode:
                The new RootNode.
        """
        node_data.node_id = self.increment_node_id()
        node = RootNode(self, node_data)

        self.nodes.append(node)
        return node

    def add_edge(self, edge_data: RootEdgeModel) -> RootEdge:
        """Construct a new RootEdge.

        Args:
            node_data (RootEdgeModel):
                The root edge data model.

        Returns:
            RootEdge:
                The new RootEdge.
        """
        edge = RootEdge(self, edge_data)
        self.edges.append(edge)
        return edge

    def increment_node_id(self) -> int:
        """Increment the node ID.

        Returns:
            int:
                The node ID prior to incrementation.
        """
        node_id = self.node_id
        self.node_id += 1
        return node_id

    def increment_organ_id(self) -> int:
        """Increment the organ ID.

        Returns:
            int:
                The organ ID prior to incrementation.
        """
        organ_id = self.organ_id
        self.organ_id += 1
        return organ_id

    def as_dict(self) -> tuple:
        """Return the graph as a tuple of node and edge lists.

        Returns:
            tuple:
                The graph as a tuple of node and edge lists.
        """
        nodes = []
        for n in self.nodes:
            nodes.append(n.as_dict())

        edges = []
        for e in self.edges:
            edges.append(e.as_dict())

        return nodes, edges

    def as_df(self) -> tuple:
        """Return the graph as a tuple of node and edge dataframes.

        Returns:
            tuple:
                The graph as a tuple of node and edge dataframes.
        """
        nodes, edges = self.as_dict()
        node_df = pd.DataFrame(nodes)
        edge_df = pd.DataFrame(edges)
        return node_df, edge_df

    def as_networkx(
        self,
        node_df: pd.DataFrame = None,
        edge_df: pd.DataFrame = None,
        drop: bool = False,
    ) -> nx.Graph:
        """Return the graph as a NetworkX graph.

        Args:
            node_df (pd.DataFrame, optional):
                The node dataframe. Defaults to None.
            edge_df (pd.DataFrame, optional):
                The edge dataframe. Defaults to None.
            drop (bool, optional):
                Whether to drop the node ID index. Defaults to False.

        Returns:
            tuple:
                The graph in NetworkX format.
        """
        if node_df is None and edge_df is None:
            node_df, edge_df = self.as_df()
        elif node_df is None:
            node_df, _ = self.as_df()
        elif edge_df is None:
            _, edge_df = self.as_df()

        G = (nx.Graph() if edge_df.empty else nx.from_pandas_edgelist(
            edge_df, "parent_id", "child_id", create_using=nx.Graph()
        ))
        G.add_nodes_from(node_df.node_id)

        def set_node_attributes(k: str, columns: list) -> None:
            columns.append("node_id")
            node_features = (
                node_df[columns].set_index("node_id", drop=drop).T.to_dict()
            )
            nx.set_node_attributes(G, node_features, k)

        set_node_attributes("organ_coordinates", ["x", "y", "z"])
        set_node_attributes(
            "organ_classification", ["root_type", "order_type", "position_type"]
        )
        set_node_attributes("organ_hierarchy", ["organ_id", "order", "segment_rank"])
        set_node_attributes("organ_size", ["diameter", "length", "root_tissue_density"])
        set_node_attributes("organ_meta", ["simulation_tag", "invalid_root"])

        node_features = node_df.set_index("node_id", drop=drop).T.to_dict()
        nx.set_node_attributes(G, node_features, "x")

        return G

    def as_torch(
        self,
        node_df: pd.DataFrame = None,
        edge_df: pd.DataFrame = None,
        drop: bool = False,
    ) -> Data:
        """Return the graph as a PyTorch Geometric graph dataset.

        Args:
            node_df (pd.DataFrame, optional):
                The node dataframe. Defaults to None.
            edge_df (pd.DataFrame, optional):
                The edge dataframe. Defaults to None.
            drop (bool, optional):
                Whether to drop the node ID index. Defaults to False.

        Returns:
            tuple:
                The graph as a PyTorch Geometric graph dataset.
        """
        G = self.as_networkx(node_df=node_df, edge_df=edge_df, drop=drop)
        torch_G = from_networkx(G)
        return torch_G

    def from_content_string(
        self, observed_data_content: str, raw_edge_content: str
    ) -> tuple:
        """Contruct the node and edge dataframes from raw content strings.

        Args:
            observed_data_content (str):
                The node content.
            raw_edge_content (str):
                The edge content.

        Returns:
            tuple:
                The node and edge dataframes.
        """
        decoded_node = base64.b64decode(observed_data_content).decode("utf-8")
        node_df = pd.read_csv(StringIO(decoded_node))

        decoded_edge = base64.b64decode(raw_edge_content).decode("utf-8")
        edge_df = pd.read_csv(StringIO(decoded_edge))

        return node_df, edge_df


def publish_graph(workspace, organs, *, axes=None, records=None, organ_records=None, first_node_id=0):
    """The sole writer of published graphs and their organ registry.

    Two declared identity-allocation policies exist, one per serialization
    contract: ``birth_order`` (``axes``: bases first, then each organ's
    materialized intervals in arc order) and ``records`` (record-based interval
    laws: construction points keep IDs, inserted attachment cuts carry their
    reserved IDs, edges ordered by parent then child).
    """
    if records is not None:
        objects = {int(o.segments[0].node_data.organ_id): o for o in organs}
        return _publish_records(workspace, records, organ_records, objects)
    return _publish_birth_order(workspace, organs, axes, first_node_id)


def _publish_birth_order(workspace: RootSystemGraph, organs: list, axes: dict, first_node_id: int = 0) -> RootSystemGraph:
    """Birth-order allocation of a published graph and its organ registry.

    ``workspace`` holds provisional construction points; ``organs`` are the
    biological organs in birth order; ``axes`` maps each organ ID to its
    materialized intervals. Bases are written first, then each organ's
    intervals in arc order, so unchanged forests keep their historical IDs.
    Organ objects are rebound to the published nodes in the same step.
    """
    published = RootSystemGraph(create_base=False)
    published.node_id = first_node_id
    ledger = {}
    for base in workspace.nodes:
        if base.node_data.order != 0:
            continue
        node = published.add_node(base.node_data.model_copy())
        ledger[base.node_data.node_id] = node
        published.bases.append(node)
    if workspace.base_node is not None:
        published.base_node = ledger[workspace.base_node.node_data.node_id]
    elif published.bases:
        published.base_node = published.bases[0]
    for organ in organs:
        parent = ledger[organ.parent_node.node_data.node_id]
        attachment = parent
        segments = []
        for rank, interval in enumerate(axes[int(organ.segments[0].node_data.organ_id)], 1):
            data = (interval.template if interval.data is None else interval.data).model_copy()
            data.parent_id = parent.node_data.node_id
            data.segment_rank = rank
            if interval.data is None and interval.xyz is not None:
                data.x, data.y, data.z = interval.xyz
                data.length, data.diameter = interval.length, interval.diameter
            node = published.add_node(data)
            published.add_edge(RootEdgeModel(parent_id=parent.node_data.node_id, child_id=node.node_data.node_id))
            node.organ = organ
            if interval.source is not None:
                ledger[interval.source.node_data.node_id] = node
            segments.append(node)
            parent = node
        organ.segments = segments
        organ.base_node = segments[0]
        organ.parent_node = attachment
    for organ in organs:
        organ.lateral_attachment_nodes = [ledger[n.node_data.node_id] for n in organ.lateral_attachment_nodes]
    published.organ_id = workspace.organ_id
    return published


def _publish_records(workspace: RootSystemGraph, rows: dict, organ_records: list, organs: dict) -> RootSystemGraph:
    """Record-based allocation for interval laws (construction steps).

    Existing construction points keep their IDs; attachment cuts inserted by
    relocation carry the explicit IDs reserved for them. Nodes are ordered by
    ID and material edges by (parent_id, child_id), the historical contract.
    """
    published = RootSystemGraph(create_base=False)
    data = {nid: RootNodeModel(**row) for nid, row in rows.items()}
    if not {node.node_data.node_id for node in workspace.nodes}.issubset(data):
        raise ValueError("A geometry edit cannot silently remove native nodes")
    live = {}
    for nid in sorted(data):
        live[nid] = RootNode(published, data[nid])
        published.nodes.append(live[nid])
    published.node_id = max(live) + 1
    published.edges = [
        RootEdge(published, RootEdgeModel(parent_id=rows[n]["parent_id"], child_id=n))
        for n in sorted(rows, key=lambda n: (rows[n]["parent_id"], n))
        if rows[n]["order"] > 0
    ]
    published.organ_id = workspace.organ_id
    published.base_node = live[workspace.base_node.node_data.node_id]
    published.bases = [published.base_node]
    for record in organ_records:
        organ = organs[record["organ_id"]]
        organ.segments = [live[n] for n in record["node_ids"]]
        organ.parent_node = live[record["parent_id"]]
        organ.base_node = organ.segments[0]
        organ.child_organs = []
        for node in organ.segments:
            node.organ = organ
        organ.mass = organ.calculate_mass()
    for record in organ_records:
        organ = organs[record["organ_id"]]
        if record["order"] > 1:
            organs[rows[record["parent_id"]]["organ_id"]].child_organs.append(organ)
        # Branch-node queues were consumed during construction.
        organ.lateral_attachment_nodes = []
    return published


def process_graph(
    G: nx.Graph, organ_keys: str, transform: T.Compose
) -> tuple[torch.Tensor, torch.Tensor]:
    """Process a new NetworkX graph.

    Args:
        G (nx.Graph):
            The NetworkX graph.
        organ_keys (str):
            The list of organ keys within the graph data object.
        transform (T.Compose)
            The composition of graph transformations.

    Returns:
        tuple:
            The node and edge features.
    """
    for k in organ_keys:
        G[k] = torch.Tensor(pd.DataFrame(G[k]).values).double()

    train_data = transform(G)
    organ_features = []
    for k in organ_keys:
        organ_features.append(train_data[k])

    x = torch.Tensor(np.hstack(organ_features))
    edge_index = train_data.edge_index
    return x, edge_index
