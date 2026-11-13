"""Contains the underlying root system simulation model.

This module defines the root system architecture simulation model for constructing 3D root systems.

"""

# mypy: ignore-errors

import math
from typing import Dict, List

import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from numpy.random import default_rng

from ..data_model import RootNodeModel, RootSimulationModel, RootType, RootTypeModel
from ..spatial import get_transform_matrix, make_homogenous
from ..utils.branching import sample_branch_sites
from .hgraph import RootNode, RootSystemGraph
from .soil import Soil


class RootOrgan:
    """One root organ and its ordered segment nodes."""

    def __init__(
        self,
        parent_node: RootNode,
        input_parameters: RootSimulationModel,
        root_type: RootTypeModel,
        simulation_tag: str,
        rng: np.random.Generator,
    ) -> None:
        self.parent_node = parent_node
        self.segments: List[RootNode] = []
        self.child_organs: List["RootOrgan"] = []
        self.lateral_attachment_nodes: List[RootNode] = []
        self.input_parameters = input_parameters
        self.root_type = root_type
        self.base_diameter = input_parameters.base_diameter
        self.fine_root_threshold = input_parameters.fine_root_threshold
        self.proot_length_interval = np.array(
            [input_parameters.min_primary_length, input_parameters.max_primary_length]
        )
        self.sroot_length_interval = np.array(
            [input_parameters.min_sec_root_length, input_parameters.max_sec_root_length]
        )
        self.length_reduction = input_parameters.length_reduction
        self.mass = 0.0
        self.reset_transform()
        self.simulation_tag = simulation_tag
        self.rng = rng
        self.invalid_root = False

    def init_diameters(self, segments_per_root: int, apex_diameter: float) -> np.ndarray:
        diameter_reduction = 1 - self.input_parameters.diameter_reduction
        base_diameter = self.base_diameter * diameter_reduction ** (
            self.parent_node.node_data.order
        )
        lb, ub = sorted((base_diameter, apex_diameter))
        diameters = self.rng.uniform(lb, ub, segments_per_root)
        return np.sort(diameters)[::-1]

    def init_lengths(self, segments_per_root: int) -> np.ndarray:
        order = self.parent_node.node_data.order + 1
        if order > 1:
            reduction_factor = self.length_reduction ** self.parent_node.node_data.order
            min_length, max_length = self.sroot_length_interval * reduction_factor
        else:
            min_length, max_length = self.proot_length_interval
        lb, ub = sorted((min_length, max_length))
        root_length = self.rng.uniform(lb, ub)
        segment_samples = self.rng.uniform(0, 1, segments_per_root)
        segment_samples = np.sort(segment_samples)[::-1]
        segment_samples /= segment_samples.sum()
        return segment_samples * root_length

    def add_child_node(
        self,
        parent_node: RootNode,
        diameters: np.ndarray,
        lengths: np.ndarray,
        coordinates: np.ndarray,
        root_type: RootTypeModel,
        root_tissue_density: float,
        i: int,
        new_organ: bool = False,
    ) -> RootNode:
        x, y, z = coordinates[i]
        node_data = RootNodeModel(
            x=x,
            y=y,
            z=z,
            diameter=diameters[i],
            length=lengths[i],
            root_tissue_density=root_tissue_density,
            root_type=root_type.root_type,
            order_type=root_type.order_type,
            position_type=root_type.position_type,
            simulation_tag=self.simulation_tag,
        )
        child_node = parent_node.add_child_node(node_data, new_organ=new_organ)
        child_node.organ = self
        self.segments.append(child_node)
        return child_node

    def init_segment_coordinates(
        self, segments_per_root: int, lengths: np.ndarray
    ) -> np.ndarray:
        """Generate local centreline points with geometric segment lengths."""
        coordinates = [np.zeros(3)]
        root_vary = self.input_parameters.root_vary
        y_rotations = self.rng.uniform(-root_vary, root_vary, segments_per_root)
        z_rotations = self.rng.uniform(-root_vary, root_vary, segments_per_root)
        for i, segment_length in enumerate(lengths):
            displacement = np.full((1, 3), segment_length / np.sqrt(3.0))
            homogeneous = make_homogenous(displacement)
            transform = get_transform_matrix(
                pitch=y_rotations[i],
                yaw=z_rotations[i],
                translation=coordinates[-1],
            )
            coordinates.append((transform @ homogeneous)[:3, 0])
        coordinates = np.asarray(coordinates)
        coordinates[:, 2] *= -1
        return coordinates[1:]

    def _draw_lateral_count(self) -> int:
        """Draw requested lateral count using the original branching-count rule.

        ``max_sec_root_num`` retains the original *exclusive* upper bound.
        """
        p = self.input_parameters
        current_order = int(self.parent_node.node_data.order) + 1
        if current_order >= int(p.max_order):
            return 0
        lo, hi = sorted((int(p.min_sec_root_num), int(p.max_sec_root_num)))
        if lo < 0:
            raise ValueError("min_sec_root_num must be nonnegative")
        if lo == hi:
            hi += 1
        n = int(self.rng.integers(lo, hi))
        growth = float(p.growth_sec_root)
        if not 0 <= growth < 1:
            raise ValueError("growth_sec_root must lie in [0, 1)")
        # Primary (order 1) -> secondaries: exponent zero, as previously.
        factor = (1 - growth) ** -(current_order - 1)
        return int(math.ceil(n * factor))

    def _prepare_branch_nodes(
        self,
        diameters: np.ndarray,
        lengths: np.ndarray,
        coordinates: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[int]]:
        """Subdivide the local polyline at new lateral attachment sites.

        New nodes are inserted before edges are created, retaining existing
        RootSystemGraph parent/child rules. Each site is an endpoint of a
        parent-organ segment, and is mapped to its new segment index.
        """
        n_requested = self._draw_lateral_count()
        if n_requested == 0:
            return diameters, lengths, coordinates, []
        diameters = np.asarray(diameters, dtype=float)
        lengths = np.asarray(lengths, dtype=float)
        coordinates = np.asarray(coordinates, dtype=float)
        polyline = np.vstack((np.zeros((1, 3)), coordinates))
        original_lengths = np.linalg.norm(np.diff(polyline, axis=0), axis=1)
        if np.any(original_lengths <= 1e-12):
            raise ValueError("Root centreline contains zero-length segments")
        np.testing.assert_allclose(original_lengths, lengths, rtol=1e-5, atol=1e-6)
        cumulative = np.r_[0.0, np.cumsum(original_lengths)]

        p = self.input_parameters
        sites = sample_branch_sites(
            parent_xyz=polyline,
            interbranch_distance=float(p.interbranch_distance),
            rng=self.rng,
            floor_threshold=float(p.floor_threshold),
            ceiling_threshold=float(p.ceiling_threshold),
            max_branches=n_requested,
        )
        if not sites:
            return diameters, lengths, coordinates, []
        sites = np.asarray(sites, dtype=float)
        if sites.ndim != 1 or not np.all(np.isfinite(sites)):
            raise ValueError("sample_branch_sites must return finite arc lengths")
        total_length = float(cumulative[-1])
        if np.any((sites <= 0) | (sites >= total_length)):
            raise ValueError("Branch sites must lie strictly inside the parent root")

        # The original centreline corners and sites are retained exactly.
        cuts = np.unique(np.r_[cumulative, sites])
        subdivided = np.column_stack([
            np.interp(cuts, cumulative, polyline[:, axis])
            for axis in range(3)
        ])
        new_lengths = np.linalg.norm(np.diff(subdivided, axis=0), axis=1)
        if np.any(new_lengths <= 1e-12):
            raise ValueError("Branching subdivision created a zero-length segment")

        # Hold each original segment's diameter constant over its subsegments.
        midpoints = (cuts[:-1] + cuts[1:]) / 2.0
        old_indices = np.searchsorted(cumulative[1:], midpoints)
        new_diameters = diameters[old_indices]
        attachment_indices = []
        for site in sites:
            cut_index = int(np.argmin(np.abs(cuts - site)))
            if not np.isclose(cuts[cut_index], site, atol=1e-8, rtol=0):
                raise ValueError("A sampled insertion point was not retained")
            attachment_indices.append(cut_index - 1)

        np.testing.assert_allclose(
            new_lengths.sum(), original_lengths.sum(), rtol=1e-6, atol=1e-6
        )
        return (
            new_diameters,
            new_lengths,
            subdivided[1:],
            sorted(set(attachment_indices)),
        )

    def _construct_segment_nodes(
        self,
        diameters: np.ndarray,
        lengths: np.ndarray,
        coordinates: np.ndarray,
        root_type: RootTypeModel,
        root_tissue_density: float,
        attachment_indices: list[int],
    ) -> List[RootNode]:
        """Construct the root chain and remember the actual insertion nodes."""
        if self.segments:
            raise RuntimeError("This organ has already been constructed")
        insertion_set = set(attachment_indices)
        self.lateral_attachment_nodes = []
        for i in range(len(lengths)):
            parent = self.parent_node if i == 0 else self.segments[-1]
            node = self.add_child_node(
                parent_node=parent,
                diameters=diameters,
                lengths=lengths,
                coordinates=coordinates,
                root_type=root_type,
                root_tissue_density=root_tissue_density,
                i=i,
                new_organ=(i == 0),
            )
            if i == 0:
                self.base_node = node
            if i in insertion_set:
                self.lateral_attachment_nodes.append(node)
        self.mass = self.calculate_mass()
        return self.segments

    def calculate_mass(self) -> float:
        diameters = self.get_diameters()
        lengths = self.get_lengths()
        volume = np.pi * (diameters / 2) ** 2 * lengths
        return float((volume * self.input_parameters.root_tissue_density).sum())

    def construct_root(
        self, segments_per_root: int, apex_diameter: float, root_tissue_density: float
    ) -> List[RootNode]:
        """Construct primary root, inserting daughter attachment nodes first."""
        diameters = self.init_diameters(segments_per_root, apex_diameter)
        lengths = self.init_lengths(segments_per_root)
        coordinates = self.init_segment_coordinates(segments_per_root, lengths)
        diameters, lengths, coordinates, attachments = self._prepare_branch_nodes(
            diameters, lengths, coordinates
        )
        return self._construct_segment_nodes(
            diameters, lengths, coordinates, self.root_type,
            root_tissue_density, attachments,
        )

    def add_child_organ(
        self, floor_threshold: float = 0.4, ceiling_threshold: float = 0.9
    ) -> "RootOrgan":
        """Create daughter organ at the next precomputed insertion node.

        Threshold arguments remain for API compatibility. The thresholds were
        applied earlier by _prepare_branch_nodes.
        """
        if not self.lateral_attachment_nodes:
            raise RuntimeError("No lateral insertion nodes remain on this organ")
        parent_node = self.lateral_attachment_nodes.pop(0)
        child_organ = RootOrgan(
            parent_node,
            input_parameters=self.input_parameters,
            root_type=self.root_type,
            simulation_tag=self.simulation_tag,
            rng=self.rng,
        )
        self.child_organs.append(child_organ)
        return child_organ

    def construct_root_from_parent(
        self, segments_per_root: int, apex_diameter: float
    ) -> List[RootNode]:
        """Construct higher-order root, with additional attachment nodes if needed."""
        diameters = self.init_diameters(segments_per_root, apex_diameter)
        lengths = self.init_lengths(segments_per_root)
        parent_data = self.parent_node.node_data
        parent_order = parent_data.order
        diameters += parent_data.diameter * 0.1**parent_order
        lengths += parent_data.length * 0.1**parent_order
        coordinates = self.init_segment_coordinates(segments_per_root, lengths)

        root_type_name = (
            RootType.STRUCTURAL.value if diameters.mean() > self.fine_root_threshold
            else RootType.FINE.value
        )
        root_type = RootTypeModel(
            root_type=root_type_name,
            order_type=RootType.SECONDARY.value,
            position_type=self.root_type.position_type,
        )
        diameters, lengths, coordinates, attachments = self._prepare_branch_nodes(
            diameters, lengths, coordinates
        )
        return self._construct_segment_nodes(
            diameters, lengths, coordinates, root_type,
            parent_data.root_tissue_density, attachments,
        )

    def reset_transform(self) -> np.ndarray:
        self.transform_matrix = np.eye(4)
        return self.transform_matrix

    def update_transform(
        self,
        roll: float = 0,
        pitch: float = 0,
        yaw: float = 0,
        translation: List[float] = [0, 0, 0],
        reflect: List[float] = [1, 1, 1, 1],
        scale: List[float] = [1, 1, 1, 1],
    ) -> np.ndarray:
        transformation_matrix = get_transform_matrix(
            roll=roll,
            pitch=pitch,
            yaw=yaw,
            translation=translation,
            reflect=reflect,
            scale=scale,
        )
        self.transform_matrix = self.transform_matrix @ transformation_matrix
        return self.transform_matrix

    def cascading_update_transform(
        self,
        roll: float = 0,
        pitch: float = 0,
        yaw: float = 0,
        translation: List[float] = [0, 0, 0],
        reflect: List[float] = [1, 1, 1, 1],
        scale: List[float] = [1, 1, 1, 1],
    ) -> None:
        self.update_transform(
            roll=roll, pitch=pitch, yaw=yaw,
            translation=translation, reflect=reflect, scale=scale,
        )
        for child in self.child_organs:
            child.cascading_update_transform(
                roll=roll, pitch=pitch, yaw=yaw,
                translation=translation, reflect=reflect, scale=scale,
            )

    def get_coordinates(self, as_array: bool = True) -> np.ndarray:
        coords = [
            [node.node_data.x, node.node_data.y, node.node_data.z]
            for node in self.segments
        ]
        return np.asarray(coords) if as_array else coords

    def set_coordinates(self, coordinates: list[tuple]) -> np.ndarray:
        for node, position in zip(self.segments, coordinates):
            node.node_data.x, node.node_data.y, node.node_data.z = position
        return coordinates

    def get_diameters(self, as_array: bool = True) -> np.ndarray:
        values = [node.node_data.diameter for node in self.segments]
        return np.asarray(values) if as_array else values

    def get_lengths(self, as_array: bool = True) -> np.ndarray:
        values = [node.node_data.length for node in self.segments]
        return np.asarray(values) if as_array else values

    def transform(self) -> np.ndarray:
        coordinates = self.get_coordinates()
        homogeneous = np.vstack((coordinates.T, np.ones(len(coordinates))))
        transformed = (self.transform_matrix[:-1] @ homogeneous).T
        self.set_coordinates(transformed)
        return self.reset_transform()

    def cascading_transform(self) -> None:
        self.transform()
        for child in self.child_organs:
            child.cascading_transform()

    def get_parent_origin(self) -> np.ndarray:
        p = self.parent_node.node_data
        return np.array([p.x, p.y, p.z])

    def get_local_origin(self) -> np.ndarray:
        return self.get_parent_origin()

    def get_apex_coordinates(self) -> np.ndarray:
        p = self.segments[-1].node_data
        return np.array([p.x, p.y, p.z])

    def cascading_to_world_origin(self) -> None:
        self.cascading_update_transform(translation=-self.get_local_origin())

    def set_invalid_root(self) -> None:
        self.invalid_root = True
        for node in self.segments:
            node.node_data.invalid_root = True

    def cascading_set_invalid_root(self) -> None:
        self.set_invalid_root()
        for child in self.child_organs:
            child.cascading_set_invalid_root()

    def validate(
        self, no_root_zone: float, pitch: int = 90, max_attempts: int = 50
    ) -> None:
        if self.invalid_root:
            return

        def _reorient(**kwargs):
            local_origin = self.get_local_origin()
            self.cascading_to_world_origin()
            self.cascading_transform()
            self.cascading_update_transform(**kwargs)
            self.cascading_transform()
            self.cascading_update_transform(translation=local_origin)
            self.cascading_transform()

        if self.rng.binomial(1, 0.5) == 1:
            pitch *= -1
        iterations = 0
        current_order = self.segments[0].node_data.order
        if current_order > 1:
            while self.get_apex_coordinates()[2] > self.get_local_origin()[2]:
                if iterations > max_attempts:
                    return self.cascading_set_invalid_root()
                _reorient(pitch=pitch)
                iterations += 1
        iterations = 0
        coordinates = self.get_coordinates()
        while np.any(coordinates[:, 2] > no_root_zone):
            if iterations > max_attempts:
                return self.cascading_set_invalid_root()
            _reorient(pitch=pitch)
            coordinates = self.get_coordinates()
            iterations += 1

        if current_order > 1:
            parent = self.get_parent_origin()
            first = self.get_coordinates()[0]
            distance = np.linalg.norm(first - parent)
            expected = self.segments[0].node_data.length
            if not np.isclose(distance, expected, rtol=1e-5, atol=1e-6):
                return self.cascading_set_invalid_root()

    def grow(
        self, simulation: "RootSystemSimulation", input_parameters: RootSimulationModel
    ) -> None:
        """Grow this root organ (retained from original; not called by run())."""
        diameter_growth = self.rng.uniform(1.01, 1.05)
        diameters = self.get_diameters()
        last_diameter = diameters[-1]
        diameters *= diameter_growth
        for i, segment in enumerate(self.segments):
            segment.node_data.diameter = diameters[i]
        diameters = diameters.tolist()
        diameters.append(last_diameter)
        diameters = np.array(diameters)

        lengths = self.get_lengths(False)
        new_length = self.init_lengths(1) / (len(lengths) + 1)
        lengths.append(new_length.item())
        lengths = np.array(lengths)
        coordinates = self.get_coordinates(False)
        new_coordinate = self.get_coordinates()[-1] + self.init_segment_coordinates(
            1, new_length
        )[0]
        coordinates.append(new_coordinate)
        coordinates = np.array(coordinates)
        apex_segment = self.segments[-1]
        self.add_child_node(
            apex_segment,
            diameters=diameters,
            lengths=lengths,
            coordinates=coordinates,
            root_type=self.root_type,
            root_tissue_density=input_parameters.root_tissue_density,
            i=len(lengths) - 1,
            new_organ=False,
        )


class RootSystemSimulation:
    """The root-system architecture simulation model."""

    def __init__(
        self, simulation_tag: str = "default", random_seed: int = None
    ) -> None:
        self.soil: Soil = Soil()
        self.G: RootSystemGraph = RootSystemGraph()
        self.organs: Dict[int, List[RootOrgan]] = {}
        self.simulation_tag = simulation_tag
        self.rng = default_rng(random_seed)

    def get_yaw(self, number_of_roots: int) -> tuple:
        yaw_base = 360 / number_of_roots
        return yaw_base, yaw_base * 0.05, yaw_base

    def plot_hierarchical_graph(
        self,
        G: nx.Graph,
        feature_key: str = "x",
        x_key: str = "x",
        y_key: str = "y",
        z_key: str = "z",
    ) -> go.Figure:
        src_indx, dest_indx = 0, 1
        x_edges, y_edges, z_edges = [], [], []
        x_nodes, y_nodes, z_nodes = [], [], []
        node_texts = []
        for node_indx in G.nodes:
            node = G.nodes[node_indx]
            x_nodes.append(node[feature_key][x_key])
            y_nodes.append(node[feature_key][y_key])
            z_nodes.append(node[feature_key][z_key])
            node_texts.append(
                f"x: {node[feature_key][x_key]}<br>"
                f"y: {node[feature_key][y_key]}<br>"
                f"z: {node[feature_key][z_key]}<br>"
                f"Organ ID: {node[feature_key]['organ_id']}<br>"
                f"Order: {node[feature_key]['order']}<br>"
                f"Segment rank: {node[feature_key]['segment_rank']}<br>"
                f"Diameter: {node[feature_key]['diameter']}<br>"
                f"Length: {node[feature_key]['length']}<br>"
                f"Root type: {node[feature_key]['root_type']}<br>"
                f"Order type: {node[feature_key]['order_type']}<br>"
                f"Position type: {node[feature_key]['position_type']}<br>"
                f"Simulation tag: {node[feature_key]['simulation_tag']}<br>"
            )
        trace_nodes = go.Scatter3d(
            x=x_nodes, y=y_nodes, z=z_nodes,
            mode="markers",
            marker=dict(symbol="circle", size=4, color="green",
                        line=dict(color="black", width=0.5)),
            text=node_texts, hoverinfo="text",
        )
        for src, dst in G.edges():
            node_src, node_dst = G.nodes[src], G.nodes[dst]
            x_edges += [node_src[feature_key][x_key], node_dst[feature_key][x_key], None]
            y_edges += [node_src[feature_key][y_key], node_dst[feature_key][y_key], None]
            z_edges += [node_src[feature_key][z_key], node_dst[feature_key][z_key], None]
        trace_edges = go.Scatter3d(
            x=x_edges, y=y_edges, z=z_edges, mode="lines",
            line=dict(color="green", width=10), hoverinfo="none",
        )
        axis = dict(
            showbackground=False, showline=False, zeroline=False,
            showgrid=False, showticklabels=False,
        )
        layout = go.Layout(
            width=1000, height=1000, showlegend=False,
            scene=dict(xaxis=dict(axis), yaxis=dict(axis), zaxis=dict(axis)),
            margin=dict(t=100), hovermode="closest",
        )
        return go.Figure(data=[trace_edges, trace_nodes], layout=layout)

    def plot_root_system(self, fig: go.Figure, node_df: pd.DataFrame) -> go.Figure:
        node_df = node_df.query("invalid_root == False")
        fig.add_trace(go.Scatter3d(
            name="root", x=node_df["x"], y=node_df["y"], z=node_df["z"],
            mode="markers",
            line=dict(color="green", colorscale="brwnyl", width=10),
            marker=dict(size=4, color="green", colorscale="brwnyl", opacity=1),
            customdata=np.stack((
                node_df.organ_id, node_df.order, node_df.segment_rank,
                node_df.diameter, node_df.length, node_df.root_type,
                node_df.order_type, node_df.position_type,
                node_df.simulation_tag,
            ), axis=-1),
            hovertemplate=(
                "x: %{x}<br>y: %{y}<br>z: %{z}<br>"
                "Organ ID: %{customdata[0]}<br>"
                "Order: %{customdata[1]}<br>"
                "Segment rank: %{customdata[2]}<br>"
                "Diameter: %{customdata[3]}<br>"
                "Length: %{customdata[4]}<br>"
                "Root type: %{customdata[5]}<br>"
                "Order type: %{customdata[6]}<br>"
                "Position type: %{customdata[7]}<br>"
                "Simulation tag: %{customdata[8]}<br>"
            ),
        ))
        axis = dict(
            showbackground=False, showline=False, zeroline=False,
            showgrid=False, showticklabels=False,
        )
        fig.update_traces(connectgaps=False)
        fig.update_layout(
            width=1000, height=1000, showlegend=False,
            scene=dict(xaxis=dict(axis), yaxis=dict(axis), zaxis=dict(axis)),
            margin=dict(t=100), hovermode="closest",
        )
        return fig

    def init_fig(self, input_parameters: RootSimulationModel) -> go.Figure | None:
        if input_parameters.enable_soil:
            soil_df = self.soil.create_soil_grid(
                input_parameters.soil_layer_height,
                input_parameters.soil_n_layers,
                input_parameters.soil_layer_width,
                input_parameters.soil_n_cols,
            )
            fig = self.soil.create_soil_fig(soil_df)
        else:
            fig = go.Figure()
        fig.update_layout(
            scene=dict(xaxis=dict(title="x"), yaxis=dict(title="y"),
                       zaxis=dict(title="z"))
        )
        return fig

    def init_organs(
        self, input_parameters: RootSimulationModel
    ) -> Dict[int, List[RootOrgan]]:
        """Construct organs; daughters attach at sampled parent arc-length sites."""
        self.organs = {
            order: [] for order in range(1, int(input_parameters.max_order) + 1)
        }
        for position_type, n_roots in (
            (RootType.OUTER.value, input_parameters.outer_root_num),
            (RootType.INNER.value, input_parameters.inner_root_num),
        ):
            root_type = RootTypeModel(
                root_type=RootType.STRUCTURAL.value,
                order_type=RootType.PRIMARY.value,
                position_type=position_type,
            )
            for _ in range(int(n_roots)):
                organ = RootOrgan(
                    self.G.base_node,
                    input_parameters=input_parameters,
                    root_type=root_type,
                    simulation_tag=self.simulation_tag,
                    rng=self.rng,
                )
                organ.construct_root(
                    input_parameters.segments_per_root,
                    input_parameters.apex_diameter,
                    input_parameters.root_tissue_density,
                )
                self.organs[1].append(organ)

        for order in range(2, int(input_parameters.max_order) + 1):
            for parent_organ in self.organs[order - 1]:
                while parent_organ.lateral_attachment_nodes:
                    child = parent_organ.add_child_organ(
                        floor_threshold=input_parameters.floor_threshold,
                        ceiling_threshold=input_parameters.ceiling_threshold,
                    )
                    self.organs[order].append(child)
                    child.construct_root_from_parent(
                        input_parameters.segments_per_root,
                        input_parameters.apex_diameter,
                    )
        return self.organs

    def position_secondary_roots(self, input_parameters: RootSimulationModel) -> None:
        for order in range(2, input_parameters.max_order + 1):
            for secondary_root in self.organs[order]:
                yaw = self.rng.uniform(-30, 240)
                pitch, roll = self.rng.uniform(60, 110, 2)
                secondary_root.update_transform(yaw=yaw)
                secondary_root.update_transform(pitch=pitch, roll=-roll)
                secondary_root.transform()
                secondary_root.update_transform(pitch=-45, roll=35)
                secondary_root.transform()
        for order in range(input_parameters.max_order, 1, -1):
            for secondary_root in self.organs[order]:
                parent_origin = secondary_root.get_parent_origin()
                secondary_root.cascading_update_transform(translation=parent_origin)
                secondary_root.cascading_transform()

    def position_primary_roots(self, input_parameters: RootSimulationModel) -> None:
        position_type = RootType.OUTER.value
        yaw_base, yaw_noise_base, yaw = self.get_yaw(input_parameters.outer_root_num)
        for primary_root in self.organs[1]:
            if primary_root.root_type.position_type != position_type:
                continue
            pitch = self.rng.uniform(-20, -15)
            primary_root.cascading_update_transform(pitch=pitch, yaw=yaw)
            primary_root.cascading_transform()
            yaw += yaw_base + self.rng.uniform(-yaw_noise_base, yaw_noise_base)
        position_type = RootType.INNER.value
        yaw_base, yaw_noise_base, yaw = self.get_yaw(input_parameters.inner_root_num)
        for primary_root in self.organs[1]:
            if primary_root.root_type.position_type != position_type:
                continue
            pitch = self.rng.uniform(0, 45)
            primary_root.cascading_update_transform(pitch=pitch, yaw=yaw)
            primary_root.cascading_transform()
            yaw += yaw_base + self.rng.uniform(-yaw_noise_base, yaw_noise_base)

    def validate(self, input_parameters: RootSimulationModel, pitch: int = 45) -> None:
        for order in range(1, input_parameters.max_order + 1):
            for organ in self.organs[order]:
                organ.validate(
                    input_parameters.no_root_zone,
                    pitch,
                    input_parameters.max_val_attempts,
                )

    def grow(
        self, simulation: RootSimulationModel, input_parameters: RootSimulationModel
    ) -> None:
        for _ in range(input_parameters.t):
            for order in range(2, input_parameters.max_order + 1):
                for organ in self.organs[order]:
                    organ.grow(simulation, input_parameters)

    def run(self, input_parameters: RootSimulationModel) -> None:
        self.init_organs(input_parameters)
        # self.grow(self, input_parameters)
        self.position_secondary_roots(input_parameters)
        self.position_primary_roots(input_parameters)
        self.apply_gravitropism(input_parameters.gravitropism)
        self.validate(input_parameters, pitch=60)

    def apply_gravitropism(self, gravitropism: float) -> None:
        if not 0 <= gravitropism <= 1:
            raise ValueError("gravitropism must be between 0 and 1")
        if gravitropism == 0:
            return
        gravity = np.array([0.0, 0.0, -1.0])
        original = {
            node.node_data.node_id: np.array([
                node.node_data.x, node.node_data.y, node.node_data.z,
            ], dtype=float)
            for node in self.G.nodes
        }
        updated = {}
        for node in self.G.nodes:
            data = node.node_data
            node_id, parent_id = data.node_id, data.parent_id
            if parent_id not in original:
                updated[node_id] = original[node_id].copy()
                continue
            displacement = original[node_id] - original[parent_id]
            length = np.linalg.norm(displacement)
            if length < 1e-12:
                updated[node_id] = updated[parent_id].copy()
                continue
            direction = displacement / length
            direction = (1 - gravitropism) * direction + gravitropism * gravity
            norm = np.linalg.norm(direction)
            direction = gravity.copy() if norm < 1e-12 else direction / norm
            updated[node_id] = updated[parent_id] + length * direction
        for node in self.G.nodes:
            node.node_data.x, node.node_data.y, node.node_data.z = updated[
                node.node_data.node_id
            ]
