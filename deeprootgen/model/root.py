"""Contains the underlying root system simulation model.

This module defines the root system architecture simulation model for constructing 3D root systems.

"""

# mypy: ignore-errors

import math
import copy
from typing import Dict, List

import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from numpy.random import default_rng

from ..data_model import RootNodeModel, RootSimulationModel, RootType, RootTypeModel
from ..spatial import get_transform_matrix, make_homogenous
from ..utils.branching import (
    PARENT2_DECIMAL_POLICY, parent2_zone_sites, redistribute_capped_sites,
    sample_branch_sites, validate_parent2_branch_zone,
)
from ..utils.order_controls import (COUNTS_FIELD, QUOTA_VERSION, direction_controls, plan_child_quotas, validate_order_scope)
from ..utils.current_length import sample_current_lengths
from ..utils.primary_attachment import FIELD as ATTACH_FIELD, validate_distal_fraction, validate_distal_scope
from ..utils.tertiary_length_rank import plan_tertiary_length_family, validate_rank_scope, validate_rank_strength
from ..utils.primary_branch_zone import (
    FIELD as PRIMARY_ZONE_FIELD, VERSION as PRIMARY_ZONE_VERSION,
    primary_branch_zone_sites, validate_primary_branch_zone_scope,
)
from ..utils.primary_branch_fractions import (
    FIELD as PRIMARY_FRACTIONS_FIELD, VERSION as PRIMARY_FRACTIONS_VERSION,
    primary_fraction_sites, validate_primary_branch_fractions_scope,
)
from ..utils.primary_orientation import chord_angles, check_edge_conservation, inclination_rotation
from ..utils.primary_design import (
    FIELD as DESIGN_FIELD, VERSION as DESIGN_VERSION, design_rotation,
    primary_dimensions, validate_primary_design_scope,
)
from ..utils.tropism import (
    insertion_heading, row_axial_controls_active, row_axial_insertion_heading,
    resolve_fichtl_sigma, sample_heading, sample_primary_yaw, validate_fichtl_sigma_by_order,
    reverse_primary_yaw, validate_primary_yaw_reverse_probability,
)
from .hgraph import RootNode, RootSystemGraph
from .soil import Soil
from .streams import RandomStreams


class RootOrgan:
    """One root organ and its ordered segment nodes."""

    def __init__(
        self,
        parent_node: RootNode,
        input_parameters: RootSimulationModel,
        root_type: RootTypeModel,
        simulation_tag: str,
        rng: np.random.Generator,
        planned: bool = False,
    ) -> None:
        self.parent_node = parent_node
        self.segments: List[RootNode] = []
        self.child_organs: List["RootOrgan"] = []
        self.lateral_attachment_nodes: List[RootNode] = []
        self.input_parameters = input_parameters
        self.root_type = root_type
        self.mass = 0.0
        self.reset_transform()
        self.simulation_tag = simulation_tag
        self.rng = rng
        self.invalid_root = False
        if planned:
            self.fine_root_threshold = input_parameters.fine_root_threshold
            return
        self.base_diameter = input_parameters.base_diameter
        self.fine_root_threshold = input_parameters.fine_root_threshold
        self.proot_length_interval = np.array(
            [input_parameters.min_primary_length, input_parameters.max_primary_length]
        )
        self.sroot_length_interval = np.array(
            [input_parameters.min_sec_root_length, input_parameters.max_sec_root_length]
        )
        self.length_reduction = input_parameters.length_reduction

    def init_diameters(
        self, segments_per_root: int, apex_diameter: float
    ) -> np.ndarray:
        features = getattr(self, "feature_laws", None)
        canonical = getattr(self.input_parameters, "canonical_generation", False)
        if canonical and hasattr(self, "primary_design"):
            return np.zeros(segments_per_root)  # Supplied primary profile owns these values.
        if features is not None and not features.uses_birth_diameter(int(self.parent_node.node_data.order) + 1):
            # Preserve the native compatibility draw count without requiring
            # replaced cylinder parameters or exposing dummy material.
            if not canonical:
                self.rng.uniform(0., 1., segments_per_root)
            return np.zeros(segments_per_root)
        diameter_reduction = 1 - self.input_parameters.diameter_reduction
        base_diameter = self.base_diameter * diameter_reduction ** (
            self.parent_node.node_data.order
        )
        lb, ub = sorted((base_diameter, apex_diameter))
        diameters = self.rng.uniform(lb, ub, segments_per_root)
        return np.sort(diameters)[::-1]

    def init_lengths(self, segments_per_root: int) -> np.ndarray:
        cdf = self._current_length_cdf()
        if cdf is not None and not hasattr(self, "_current_length_expected_organ_id"):
            raise ValueError("Current-length sampling requires a captured next organ ID")
        order = self.parent_node.node_data.order + 1
        features = getattr(self, "feature_laws", None)
        bounded = features is not None and features.laws.lengths.get(int(order), {}).get("law") == "bounded_lognormal"
        canonical = getattr(self.input_parameters, "canonical_generation", False)
        if cdf is not None and canonical:
            return self._sample_cdf_partition(cdf, segments_per_root, order, compatibility_draws=0)
        if bounded or cdf is not None or (canonical and hasattr(self, "primary_design")):
            # These values are compatibility draws only; native bounds have no
            # numerical consumer once the total length law is replaced.
            min_length, max_length = 0., 1.
        elif order > 1:
            reduction_factor = self.length_reduction**self.parent_node.node_data.order
            min_length, max_length = self.sroot_length_interval * reduction_factor
        else:
            min_length, max_length = self.proot_length_interval
        lb, ub = sorted((min_length, max_length))
        root_length = (1.0 if canonical and (bounded or hasattr(self, "primary_design"))
                       else self.rng.uniform(lb, ub))
        segment_samples = self.rng.uniform(0, 1, segments_per_root)
        segment_samples = np.sort(segment_samples)[::-1]
        segment_samples /= segment_samples.sum()
        legacy_lengths = segment_samples * root_length
        if cdf is None:
            return legacy_lengths
        return self._sample_cdf_partition(cdf, segments_per_root, order, compatibility_draws=1 + segments_per_root)

    def _sample_cdf_partition(self, cdf, segments_per_root, order, compatibility_draws):
        if order == 3 and validate_rank_strength(getattr(self.input_parameters, "research_tertiary_length_rank_strength", None)):
            if not hasattr(self, "_tertiary_length_plan"):
                raise ValueError("Active tertiary rank requires a preplanned biological sibling family")
            lengths, diagnostics = copy.deepcopy(self._tertiary_length_plan)
            if diagnostics["expected_organ_id"] != self._current_length_expected_organ_id:
                raise ValueError("Prospective tertiary family ID disagrees with next allocation")
        else:
            lengths, diagnostics = sample_current_lengths(
                cdf, segments_per_root, self.input_parameters.random_seed,
                self._current_length_expected_organ_id, int(order),
            )
        diagnostics["legacy_compatibility_draw_count"] = compatibility_draws
        self.current_length_diagnostics = diagnostics
        return lengths

    def _current_length_cdf(self):
        cdfs = getattr(self.input_parameters, "research_current_length_cdfs_cm", None)
        order = int(self.parent_node.node_data.order) + 1
        return None if cdfs is None else cdfs.get(order)

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
        root_vary = 0.0 if root_vary is None else root_vary
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
        overrides = getattr(p, "daughters_by_parent_order", {})
        if current_order in overrides:
            return overrides[current_order]
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

    def _requested_daughter_count(self):
        count_mode = getattr(self.input_parameters, COUNTS_FIELD, None) is not None
        if count_mode and not hasattr(self, "_conditioned_child_quota"):
            raise ValueError("Count conditioning requires a planned per-parent quota before construction")
        return self._conditioned_child_quota if count_mode else self._draw_lateral_count()

    def _prepare_branch_nodes(
        self,
        diameters: np.ndarray,
        lengths: np.ndarray,
        coordinates: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[int]]:
        """Subdivide the local polyline at new lateral attachment sites.

        New nodes are inserted before edges are created, retaining existing
        RootSystemGraph parent/child rules. Each site is an endpoint of a
        parent-organ segment, and is mapped to its new segment index. A
        replaced branching law supplies the sites; subdivision is shared.
        """
        features = getattr(self, "feature_laws", None)
        if features is not None and features.replaces_branching(self):
            diameters = np.asarray(diameters, dtype=float)
            lengths = np.asarray(lengths, dtype=float)
            coordinates = np.asarray(coordinates, dtype=float)
            polyline = np.vstack((np.zeros((1, 3)), coordinates))
            original_lengths = np.linalg.norm(np.diff(polyline, axis=0), axis=1)
            cumulative = np.r_[0.0, np.cumsum(original_lengths)]
            sites = features.branch_sites(self, float(cumulative[-1]), len(original_lengths))
            if not sites:
                return diameters, lengths, coordinates, []
            return RootOrgan._subdivide_at_sites(self, diameters, lengths, polyline, original_lengths, cumulative, sites)
        count_mode = getattr(self.input_parameters, COUNTS_FIELD, None) is not None
        n_requested = RootOrgan._requested_daughter_count(self)
        zone = getattr(self.input_parameters, "research_parent2_branch_zone_cm", None)
        if zone is not None and int(self.parent_node.node_data.order) + 1 != 2:
            zone = None
        primary_zone = getattr(self.input_parameters, PRIMARY_ZONE_FIELD, None)
        if primary_zone is not None and int(self.parent_node.node_data.order) + 1 != 1:
            primary_zone = None
        primary_fractions = getattr(self.input_parameters, PRIMARY_FRACTIONS_FIELD, None)
        if primary_fractions is not None and int(self.parent_node.node_data.order) + 1 != 1:
            primary_fractions = None
        if primary_fractions is not None and n_requested != len(primary_fractions):
            raise ValueError("Each primary quota must equal the number of supplied fractions")
        if n_requested == 0 and zone is None and primary_zone is None and primary_fractions is None:
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
        sites = [] if n_requested == 0 or count_mode else sample_branch_sites(
            parent_xyz=polyline,
            interbranch_distance=float(p.interbranch_distance),
            rng=self.rng,
            floor_threshold=float(p.floor_threshold),
            ceiling_threshold=float(p.ceiling_threshold),
            max_branches=n_requested,
        )
        if n_requested > 0 and primary_fractions is None and (count_mode or getattr(p, "research_branch_placement", "legacy_spacing") == "redistribute_capped"):
            sites = redistribute_capped_sites(
                parent_xyz=polyline,
                retained_count=n_requested if count_mode else len(sites),
                floor_threshold=float(p.floor_threshold),
                ceiling_threshold=float(p.ceiling_threshold),
            )
        if primary_zone is not None:
            sites = primary_branch_zone_sites(float(cumulative[-1]), n_requested, primary_zone)
            self.primary_branch_zone_diagnostics = dict(
                version=PRIMARY_ZONE_VERSION, zone_cm=dict(primary_zone),
                primary_length_cm=float(cumulative[-1]), retained_count=n_requested,
                sites_cm=sites.copy(), placement="supplied_count_midpoint_quantiles",
                retained_couplings=["daughter diameter inherits new attachment cylinder",
                                    "native Fichtl geometry depends on graph subdivision/shared RNG"],
                daughter_length_policy="keyed current-length CDF; no attachment-length addition",
            )
        if primary_fractions is not None:
            sites = primary_fraction_sites(float(cumulative[-1]), n_requested, primary_fractions)
            self.primary_branch_fractions_diagnostics = dict(
                version=PRIMARY_FRACTIONS_VERSION, fractions=list(primary_fractions),
                primary_length_cm=float(cumulative[-1]), retained_count=n_requested,
                sites_cm=sites.copy(), placement="supplied_arc_fractions",
                retained_couplings=["daughter diameter inherits new attachment cylinder",
                                    "native Fichtl geometry depends on graph subdivision/shared RNG"],
                daughter_length_policy="keyed current-length CDF; no attachment-length addition",
            )
        if zone is not None:
            current = self._expected_current_length()
            if not np.isclose(cumulative[-1], current, rtol=0, atol=1e-8):
                raise ValueError("Parent2 CURRENT and geometric lengths disagree")
            inputs = validate_parent2_branch_zone(zone)
            retained = len(sites)
            sites = parent2_zone_sites(current, **inputs)
            self.parent2_zone_diagnostics = dict(
                original_requested_count=n_requested, original_retained_count=retained,
                sampled_current_length_cm=current, zone_cm=inputs, sites_cm=sites.copy(), count=len(sites),
                decimal_policy=PARENT2_DECIMAL_POLICY,
                retained_couplings=["inherited daughter diameter depends on attachment", "global tertiary birth keys may shift"],
            )
        if not sites:
            return diameters, lengths, coordinates, []
        return RootOrgan._subdivide_at_sites(self, diameters, lengths, polyline, original_lengths, cumulative, sites)

    def _subdivide_at_sites(self, diameters, lengths, polyline, original_lengths, cumulative, sites):
        """Insert attachment cuts at arc-length sites; corners and material unchanged."""
        sites = np.asarray(sites, dtype=float)
        if sites.ndim != 1 or not np.all(np.isfinite(sites)):
            raise ValueError("sample_branch_sites must return finite arc lengths")
        total_length = float(cumulative[-1])
        if np.any((sites <= 0) | (sites >= total_length)):
            raise ValueError("Branch sites must lie strictly inside the parent root")

        # The original centreline corners and sites are retained exactly.
        cuts = np.unique(np.r_[cumulative, sites])
        if hasattr(self, "feature_laws"):
            self.feature_laws.reserve_construction(len(cuts) - 1, self.parent_node.G)
        subdivided = np.column_stack(
            [np.interp(cuts, cumulative, polyline[:, axis]) for axis in range(3)]
        )
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
        if hasattr(self, "current_length_diagnostics"):
            if self.parent_node.G.organ_id != self.current_length_diagnostics["expected_organ_id"]:
                raise ValueError("Next biological organ ID changed after current-length sampling")
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
                if hasattr(self, "current_length_diagnostics"):
                    if node.node_data.organ_id != self.current_length_diagnostics["expected_organ_id"]:
                        raise ValueError("Allocated biological organ ID disagrees with current-length sampling key")
                    self.current_length_diagnostics["allocated_organ_id"] = int(node.node_data.organ_id)
                self.base_node = node
            if i in insertion_set:
                self.lateral_attachment_nodes.append(node)
        self.mass = self.calculate_mass()
        if hasattr(self, "current_length_diagnostics"):
            realised = float(self.get_lengths().sum())
            if not np.isclose(realised, self._expected_current_length(), rtol=0, atol=1e-8):
                raise ValueError("Post-subdivision current organ length conservation exceeds 1e-8 cm")
            self.current_length_diagnostics["post_subdivision_length_cm"] = realised
        if hasattr(self, "_construction_step_lengths_cm"):
            cumulative = np.cumsum(self.get_lengths())
            boundaries = []
            for arc in np.cumsum(self._construction_step_lengths_cm):
                matches = np.flatnonzero(np.isclose(cumulative, arc, rtol=0, atol=1e-8))
                if len(matches) != 1:
                    raise ValueError("Missing or ambiguous original construction boundary")
                boundaries.append(int(self.segments[int(matches[0])].node_data.node_id))
            self.construction_step_boundary_node_ids = boundaries
            self.construction_step_provenance = copy.deepcopy(self.current_length_diagnostics)
        return self.segments

    def _expected_current_length(self):
        draw = self.current_length_diagnostics
        return draw.get("allocated_length_cm", draw["sampled_current_length_cm"])

    def calculate_mass(self) -> float:
        diameters = self.get_diameters()
        lengths = self.get_lengths()
        volume = np.pi * (diameters / 2) ** 2 * lengths
        if getattr(self, "diameter_density_applied", False):
            densities = [node.node_data.root_tissue_density for node in self.segments]
            return float(np.dot(volume, densities))
        return float((volume * self.input_parameters.root_tissue_density).sum())

    def construct_root(
        self, segments_per_root: int, apex_diameter: float, root_tissue_density: float
    ) -> List[RootNode]:
        """Construct primary root, inserting daughter attachment nodes first."""
        if hasattr(self, "feature_laws"):
            self.feature_laws.reserve_construction(segments_per_root, self.parent_node.G)
        diameters = self.init_diameters(segments_per_root, apex_diameter)
        lengths = self.init_lengths(segments_per_root)
        if hasattr(self, "primary_design"):
            diameters, lengths = primary_dimensions(self.primary_design, lengths)
        features = getattr(self, "feature_laws", None)
        if features is not None:
            replaced = features.replace_lengths(self, lengths)
            lengths = features.scale_lengths(self, lengths if replaced is None else replaced)
            diameters = features.scale_diameters(self, diameters)
        coordinates = self.init_segment_coordinates(segments_per_root, lengths)
        diameters, lengths, coordinates, attachments = self._prepare_branch_nodes(
            diameters, lengths, coordinates
        )
        return self._construct_segment_nodes(
            diameters,
            lengths,
            coordinates,
            self.root_type,
            root_tissue_density,
            attachments,
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
        if hasattr(self, "feature_laws"):
            self.feature_laws.reserve_organ()
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
        rank_strength = validate_rank_scope(self.input_parameters)
        if rank_strength and self.parent_node.node_data.order == 2 and not hasattr(self, "_tertiary_length_plan"):
            raise ValueError("Active tertiary rank requires a preplanned biological sibling family")
        if self._current_length_cdf() is not None:
            self._current_length_expected_organ_id = int(self.parent_node.G.organ_id)
        if hasattr(self, "feature_laws"):
            self.feature_laws.reserve_construction(segments_per_root, self.parent_node.G)
        diameters = self.init_diameters(segments_per_root, apex_diameter)
        lengths = self.init_lengths(segments_per_root)
        features = getattr(self, "feature_laws", None)
        parent_data = self.parent_node.node_data if features is None else features.birth_context(self.parent_node)
        parent_order = parent_data.order
        diameters += parent_data.diameter * 0.1**parent_order
        features = getattr(self, "feature_laws", None)
        replaced = None if features is None else features.replace_lengths(self, lengths)
        if replaced is not None:
            lengths = replaced
        elif self._current_length_cdf() is None:
            lengths += parent_data.length * 0.1**parent_order
        if features is not None:
            lengths = features.scale_lengths(self, lengths)
            diameters = features.scale_diameters(self, diameters)
        if getattr(self.input_parameters, "research_current_length_grid", None) is not None:
            self._construction_step_lengths_cm = lengths.copy()
        coordinates = self.init_segment_coordinates(segments_per_root, lengths)

        root_type_name = (
            RootType.STRUCTURAL.value
            if diameters.mean() > self.fine_root_threshold
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
            diameters,
            lengths,
            coordinates,
            root_type,
            parent_data.root_tissue_density,
            attachments,
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
            roll=roll,
            pitch=pitch,
            yaw=yaw,
            translation=translation,
            reflect=reflect,
            scale=scale,
        )
        for child in self.child_organs:
            child.cascading_update_transform(
                roll=roll,
                pitch=pitch,
                yaw=yaw,
                translation=translation,
                reflect=reflect,
                scale=scale,
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
        self,
        no_root_zone: float,
        pitch: int = 90,
        max_attempts: int = 50,
        enforce_downward_apex: bool = True,
        allow_reorient: bool = True,
    ) -> None:
        self.validation_reorientations = 0
        if self.invalid_root:
            return

        def _reorient(**kwargs):
            self.validation_reorientations += 1
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
        if current_order > 1 and enforce_downward_apex:
            while self.get_apex_coordinates()[2] > self.get_local_origin()[2]:
                if not allow_reorient or iterations > max_attempts:
                    return self.cascading_set_invalid_root()
                _reorient(pitch=pitch)
                iterations += 1
        iterations = 0
        coordinates = self.get_coordinates()
        while np.any(coordinates[:, 2] > no_root_zone):
            if not allow_reorient or iterations > max_attempts:
                return self.cascading_set_invalid_root()
            _reorient(pitch=pitch)
            coordinates = self.get_coordinates()
            iterations += 1

        if current_order > 1:
            parent = self.get_parent_origin()
            first = self.get_coordinates()[0]
            expected = self.segments[0].node_data.length
            curve = getattr(getattr(self, "axis_state", None), "curve", None)
            if getattr(self.input_parameters, "canonical_generation", False) and curve is not None:
                # Construction endpoints can span several physical curve pieces.
                # The materializer checks their lengths when it emits the corners.
                first_interval_ok = (
                    np.allclose(parent, curve.points[0], rtol=0, atol=1e-6)
                    and np.allclose(first, curve.position(expected)[0], rtol=0, atol=1e-6)
                )
            else:
                first_interval_ok = np.isclose(np.linalg.norm(first - parent), expected, rtol=1e-5, atol=1e-6)
            if not first_interval_ok:
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
        new_coordinate = (
            self.get_coordinates()[-1] + self.init_segment_coordinates(1, new_length)[0]
        )
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
        self.random_seed = random_seed
        # One owner: native kernels draw from streams.native in historical order.
        self.streams = RandomStreams(random_seed)
        self.rng = self.streams.native

    def get_yaw(self, number_of_roots: int) -> tuple:
        if number_of_roots == 0:
            return 0., 0., 0.
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
            x=x_nodes,
            y=y_nodes,
            z=z_nodes,
            mode="markers",
            marker=dict(
                symbol="circle",
                size=4,
                color="green",
                line=dict(color="black", width=0.5),
            ),
            text=node_texts,
            hoverinfo="text",
        )
        for src, dst in G.edges():
            node_src, node_dst = G.nodes[src], G.nodes[dst]
            x_edges += [
                node_src[feature_key][x_key],
                node_dst[feature_key][x_key],
                None,
            ]
            y_edges += [
                node_src[feature_key][y_key],
                node_dst[feature_key][y_key],
                None,
            ]
            z_edges += [
                node_src[feature_key][z_key],
                node_dst[feature_key][z_key],
                None,
            ]
        trace_edges = go.Scatter3d(
            x=x_edges,
            y=y_edges,
            z=z_edges,
            mode="lines",
            line=dict(color="green", width=10),
            hoverinfo="none",
        )
        axis = dict(
            showbackground=False,
            showline=False,
            zeroline=False,
            showgrid=False,
            showticklabels=False,
        )
        layout = go.Layout(
            width=1000,
            height=1000,
            showlegend=False,
            scene=dict(xaxis=dict(axis), yaxis=dict(axis), zaxis=dict(axis)),
            margin=dict(t=100),
            hovermode="closest",
        )
        return go.Figure(data=[trace_edges, trace_nodes], layout=layout)

    def plot_root_system(self, fig: go.Figure, node_df: pd.DataFrame) -> go.Figure:
        node_df = node_df.query("invalid_root == False")
        fig.add_trace(
            go.Scatter3d(
                name="root",
                x=node_df["x"],
                y=node_df["y"],
                z=node_df["z"],
                mode="markers",
                line=dict(color="green", colorscale="brwnyl", width=10),
                marker=dict(size=4, color="green", colorscale="brwnyl", opacity=1),
                customdata=np.stack(
                    (
                        node_df.organ_id,
                        node_df.order,
                        node_df.segment_rank,
                        node_df.diameter,
                        node_df.length,
                        node_df.root_type,
                        node_df.order_type,
                        node_df.position_type,
                        node_df.simulation_tag,
                    ),
                    axis=-1,
                ),
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
            )
        )
        axis = dict(
            showbackground=False,
            showline=False,
            zeroline=False,
            showgrid=False,
            showticklabels=False,
        )
        fig.update_traces(connectgaps=False)
        fig.update_layout(
            width=1000,
            height=1000,
            showlegend=False,
            scene=dict(xaxis=dict(axis), yaxis=dict(axis), zaxis=dict(axis)),
            margin=dict(t=100),
            hovermode="closest",
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
            scene=dict(
                xaxis=dict(title="x"), yaxis=dict(title="y"), zaxis=dict(title="z")
            )
        )
        return fig

    def init_organs(
        self, input_parameters: RootSimulationModel, laws=None
    ) -> Dict[int, List[RootOrgan]]:
        """Construct organs; daughters attach at sampled parent arc-length sites.

        ``laws`` (engine-supplied) replaces selected leaf laws: feature
        lengths, point taper, branching, maturity and distributed origins.
        """
        self._validate_primary_yaw_seed(input_parameters)
        primary_design = validate_primary_design_scope(input_parameters, getattr(self, "random_seed", None))
        self.organs = {
            order: [] for order in range(1, int(input_parameters.max_order) + 1)
        }
        if laws is not None:
            laws.begin(self)
        counts = validate_order_scope(input_parameters, getattr(self, "random_seed", None))
        quota_plans = {} if counts is None else {
            order: plan_child_quotas(input_parameters.random_seed, order + 1, counts[order], counts[order + 1])
            for order in range(1, input_parameters.max_order)
        }
        if counts is not None:
            self.count_conditioning_diagnostics = dict(
                version=QUOTA_VERSION, interpretation="supplied topology conditioning; not count prediction",
                requested_counts_by_order={str(k): v for k, v in counts.items()},
                child_quotas_by_parent_order={str(k): v for k, v in quota_plans.items()},
                seed=input_parameters.random_seed,
            )
        self._init_primary_organs(input_parameters, laws, counts, quota_plans, primary_design)

        for order in range(2, int(input_parameters.max_order) + 1):
            for parent_organ in self.organs[order - 1]:
                if laws is not None:
                    laws.filter_branch_sites(parent_organ)
                rank_plans = None
                if order == 3 and validate_rank_strength(getattr(input_parameters, "research_tertiary_length_rank_strength", None)):
                    zone = parent_organ.parent2_zone_diagnostics
                    sites = zone.get("eligible_sites_cm", zone["sites_cm"])
                    if len(sites) != len(parent_organ.lateral_attachment_nodes):
                        raise ValueError("Tertiary rank family branch-site count disagrees with parent2 zone")
                    rank_plans, family = plan_tertiary_length_family(
                        input_parameters.research_current_length_cdfs_cm[3], (input_parameters.segments_per_root or 1),
                        input_parameters.random_seed, int(parent_organ.segments[0].node_data.organ_id),
                        int(self.G.organ_id), sites, input_parameters.research_tertiary_length_rank_strength,
                    )
                    parent_organ.tertiary_length_rank_family = family
                child_index = 0
                while parent_organ.lateral_attachment_nodes:
                    child = parent_organ.add_child_organ(
                        floor_threshold=input_parameters.floor_threshold,
                        ceiling_threshold=input_parameters.ceiling_threshold,
                    )
                    if laws is not None:
                        laws.assign_daughter(child, parent_organ)
                    if rank_plans is not None:
                        child._tertiary_length_plan = rank_plans[child_index]
                    if counts is not None:
                        child._conditioned_child_quota = (quota_plans[order][len(self.organs[order])]
                                                          if order < input_parameters.max_order else 0)
                    self.organs[order].append(child)
                    child.construct_root_from_parent(
                        (input_parameters.segments_per_root or 1),
                        input_parameters.apex_diameter,
                    )
                    if laws is not None:
                        laws.after_construction(child)
                    child_index += 1
        if counts is not None:
            realised = {str(k): len(v) for k, v in self.organs.items()}
            if realised != self.count_conditioning_diagnostics["requested_counts_by_order"]:
                raise ValueError("Count-conditioned construction did not realize supplied population totals")
            self.count_conditioning_diagnostics["realized_counts_by_order"] = realised
        return self.organs

    def _init_primary_organs(self, input_parameters, laws, counts, quota_plans, primary_design):
        """Outer then inner primaries, in birth order (one organ ID each)."""
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
                if laws is not None:
                    laws.reserve_organ()
                organ = RootOrgan(
                    self.G.base_node if laws is None else laws.primary_parent(self, len(self.organs[1])),
                    input_parameters=input_parameters,
                    root_type=root_type,
                    simulation_tag=self.simulation_tag,
                    rng=self.rng,
                )
                if laws is not None:
                    laws.assign_primary(organ, len(self.organs[1]), int(self.G.organ_id))
                if counts is not None:
                    organ._conditioned_child_quota = quota_plans[1][len(self.organs[1])]
                if primary_design is not None:
                    organ.primary_design = copy.deepcopy(primary_design[len(self.organs[1])])
                organ.construct_root(
                    (input_parameters.segments_per_root or 1),
                    input_parameters.apex_diameter,
                    input_parameters.root_tissue_density,
                )
                if laws is not None:
                    laws.after_construction(organ)
                self.organs[1].append(organ)

    def _validate_primary_yaw_seed(self, input_parameters: RootSimulationModel) -> None:
        if getattr(input_parameters, DESIGN_FIELD, None) is not None:
            if getattr(self, "random_seed", None) is None:
                raise ValueError("Explicit primary design requires matching constructor and parameter seeds")
            validate_primary_design_scope(input_parameters, self.random_seed)
        validate_order_scope(input_parameters, getattr(self, "random_seed", None))
        validate_primary_branch_zone_scope(input_parameters, getattr(self, "random_seed", None))
        validate_primary_branch_fractions_scope(input_parameters, getattr(self, "random_seed", None))
        if validate_distal_scope(input_parameters):
            if self.random_seed is None:
                raise ValueError("Primary attachment placement requires matching explicit constructor seed")
            validate_distal_scope(input_parameters, self.random_seed)
        if validate_rank_scope(input_parameters):
            if self.random_seed is None:
                raise ValueError("Tertiary length rank requires matching explicit constructor seed")
            validate_rank_scope(input_parameters, self.random_seed)
        reversal = validate_primary_yaw_reverse_probability(
            getattr(input_parameters, "research_primary_yaw_reverse_probability", None))
        if reversal and (getattr(input_parameters, "research_primary_yaw_mean_deg", None) is None
                         or getattr(input_parameters, "research_primary_yaw_kappa", None) is None):
            raise ValueError("Active primary yaw reversal requires explicit yaw mean/kappa")
        if reversal:
            mean = input_parameters.research_primary_yaw_mean_deg
            kappa = input_parameters.research_primary_yaw_kappa
            if (isinstance(mean, (bool, np.bool_)) or not isinstance(mean, (int, float, np.integer, np.floating))
                    or not np.isfinite(mean) or not -180 <= mean <= 180
                    or isinstance(kappa, (bool, np.bool_)) or not isinstance(kappa, (int, float, np.integer, np.floating))
                    or not np.isfinite(kappa) or not 0 <= kappa <= 100):
                raise ValueError("Active primary yaw reversal requires valid explicit yaw mean/kappa")
        sigma_map = getattr(input_parameters, "research_fichtl_sigma_by_order", None)
        if sigma_map is not None:
            if getattr(input_parameters, "tropism_mode", "legacy") != "fichtl2024":
                raise ValueError("Order sigma overrides require fichtl2024 mode")
            validate_fichtl_sigma_by_order(sigma_map, input_parameters.max_order)
        row_active = row_axial_controls_active(getattr(input_parameters, "research_insertion_row_axial_kappa", None))
        if row_active and getattr(input_parameters, "tropism_mode", "legacy") != "fichtl2024":
            raise ValueError("Active row-axial insertion requires Fichtl mode")
        if (getattr(input_parameters, "research_primary_yaw_mean_deg", None) is None
                and getattr(input_parameters, "research_current_length_cdfs_cm", None) is None
                and not getattr(input_parameters, "research_primary_inclination_bias", None)
                and not row_active):
            return
        constructor_seed = getattr(self, "random_seed", None)
        parameter_seed = getattr(input_parameters, "random_seed", None)
        if (constructor_seed is None or parameter_seed is None
                or isinstance(constructor_seed, (bool, np.bool_))
                or not isinstance(constructor_seed, (int, np.integer))
                or isinstance(parameter_seed, (bool, np.bool_))
                or not isinstance(parameter_seed, (int, np.integer))
                or constructor_seed != parameter_seed or (reversal and parameter_seed < 0)):
            raise ValueError("Research keyed initialization requires equal explicit constructor and parameter seeds")

    def position_secondary_roots(self, input_parameters: RootSimulationModel) -> None:
        self._validate_primary_yaw_seed(input_parameters)
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
        self._validate_primary_yaw_seed(input_parameters)
        if getattr(input_parameters, DESIGN_FIELD, None) is not None:
            self.apply_primary_design_initialization(input_parameters)
            if getattr(input_parameters, "research_base_depth_cm", None) is not None:
                self.apply_root_origin_initialization(input_parameters)
            return
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

        if getattr(input_parameters, "research_primary_yaw_mean_deg", None) is not None:
            self.apply_primary_yaw_initialization(input_parameters)
        if getattr(input_parameters, "research_primary_inclination_bias", None):
            self.apply_primary_inclination_initialization(input_parameters)
        if getattr(input_parameters, "research_base_depth_cm", None) is not None:
            self.apply_root_origin_initialization(input_parameters)

    def apply_primary_design_initialization(self, input_parameters: RootSimulationModel) -> None:
        """Rigid complete-primary-subtree rotations before origin and tropism.

        Native positional allocation is retained as metadata, but its random
        positioning is bypassed only in this explicit-design branch. The whole
        plan is checked before mutation; no dimensions or random state change.
        """
        self._validate_primary_yaw_seed(input_parameters)
        entries = validate_primary_design_scope(input_parameters, self.random_seed)
        if entries is None:
            return
        if len(self.organs[1]) != len(entries):
            raise ValueError("Explicit primary design does not match constructed organ count")
        nodes = {node.node_data.node_id: node for node in self.G.nodes}
        original = {key: np.array([node.node_data.x, node.node_data.y, node.node_data.z], float)
                    for key, node in nodes.items()}
        if not all(np.isfinite(xyz).all() for xyz in original.values()):
            raise ValueError("Explicit primary design requires finite graph coordinates")
        base_id = self.G.base_node.node_data.node_id
        origin = original[base_id]
        parents = {key: node.node_data.parent_id for key, node in nodes.items()}
        proposed, assigned, diagnostics = {base_id: origin.copy()}, set(), []
        for primary, entry in zip(self.organs[1], entries):
            if primary.parent_node is not self.G.base_node or getattr(primary, "primary_design", None) != entry:
                raise ValueError("Explicit primary design differs from common-origin construction")
            rotation, target = design_rotation(primary.get_apex_coordinates() - origin, entry)
            subtree, node_ids, seen = [primary], set(), set()
            while subtree:
                organ = subtree.pop()
                if id(organ) in seen:
                    raise ValueError("Primary subtree contains a repeated/cyclic organ")
                seen.add(id(organ))
                for node in organ.segments:
                    nid = node.node_data.node_id
                    if nid in assigned or nid in node_ids or nid == base_id:
                        raise ValueError("Primary subtrees overlap or contain duplicate nodes")
                    node_ids.add(nid)
                    proposed[nid] = origin + rotation @ (original[nid] - origin)
                subtree.extend(organ.child_organs)
            residual = check_edge_conservation(original, proposed, parents, node_ids, base_id)
            realised = proposed[primary.segments[-1].node_data.node_id] - origin
            realised /= np.linalg.norm(realised)
            if not np.allclose(realised, target, rtol=0, atol=1e-12):
                raise ValueError("Explicit primary chord misses requested target")
            diagnostics.append(dict(version=DESIGN_VERSION, **copy.deepcopy(entry),
                                    organ_id=int(primary.segments[0].node_data.organ_id),
                                    native_position_type=primary.root_type.position_type,
                                    rotation=rotation.tolist(), target_chord_unit=target.tolist(),
                                    realised_chord_unit=realised.tolist(),
                                    maximum_edge_length_residual_cm=residual,
                                    stage="before_common_origin_and_tropism"))
            assigned.update(node_ids)
        if assigned != set(nodes) - {base_id}:
            raise ValueError("Explicit primary subtrees do not cover complete initial graph")
        check_edge_conservation(original, proposed, parents, assigned, base_id)
        for nid in assigned:
            data = nodes[nid].node_data
            data.x, data.y, data.z = proposed[nid]
        self.primary_design_diagnostics = diagnostics

    def apply_primary_inclination_initialization(self, input_parameters: RootSimulationModel) -> None:
        """Plan all rigid primary-subtree rotations after yaw, before origin."""
        bias = getattr(input_parameters, "research_primary_inclination_bias", None)
        if bias is None or bias == 0:
            return
        self._validate_primary_yaw_seed(input_parameters)
        nodes = {node.node_data.node_id: node for node in self.G.nodes}
        original = {key: np.array([node.node_data.x, node.node_data.y, node.node_data.z], float)
                    for key, node in nodes.items()}
        if not all(np.isfinite(xyz).all() for xyz in original.values()):
            raise ValueError("Primary inclination requires finite graph coordinates")
        base_id = self.G.base_node.node_data.node_id
        origin = original[base_id]
        parents = {key: node.node_data.parent_id for key, node in nodes.items()}
        proposed, assigned, diagnostics = {base_id: origin.copy()}, set(), []
        for primary in self.organs[1]:
            rotation, report = inclination_rotation(primary.get_apex_coordinates() - origin, bias)
            subtree, node_ids, seen = [primary], set(), set()
            while subtree:
                organ = subtree.pop()
                if id(organ) in seen:
                    raise ValueError("Primary subtree contains a repeated/cyclic organ")
                seen.add(id(organ))
                for node in organ.segments:
                    nid = node.node_data.node_id
                    if nid in assigned or nid in node_ids or nid == base_id:
                        raise ValueError("Primary subtrees overlap or contain duplicate nodes")
                    node_ids.add(nid)
                    proposed[nid] = origin + rotation @ (original[nid] - origin)
                subtree.extend(organ.child_organs)
            if not all(np.isfinite(proposed[nid]).all() for nid in node_ids):
                raise ValueError("Primary inclination produced nonfinite coordinates")
            residual = check_edge_conservation(original, proposed, parents, node_ids, base_id)
            apex_id = primary.segments[-1].node_data.node_id
            realised = proposed[apex_id] - origin
            realised /= np.linalg.norm(realised)
            if not np.allclose(realised, report["target_chord_unit"], rtol=0, atol=1e-12):
                raise ValueError("Realised primary chord misses inclination target")
            report.update(organ_id=int(primary.segments[0].node_data.organ_id), base_cm=origin.tolist(),
                          realised_chord_unit=realised.tolist(), realised_angles=chord_angles(realised),
                          maximum_edge_length_residual_cm=residual,
                          stage="after_primary_yaw_before_origin_and_tropism")
            diagnostics.append(report)
            assigned.update(node_ids)
        if assigned != set(nodes) - {base_id}:
            raise ValueError("Primary subtrees do not cover the complete initial graph")
        check_edge_conservation(original, proposed, parents, assigned, base_id)
        for nid in assigned:
            data = nodes[nid].node_data
            data.x, data.y, data.z = proposed[nid]
        self.primary_inclination_diagnostics = diagnostics

    def apply_root_origin_initialization(self, input_parameters: RootSimulationModel) -> None:
        """Translate the complete initial graph to an explicitly buried base.

        Surface-aware research initialization only. No new edge, rotation,
        length change or random draw; preceding yaw diagnostics are retained.
        """
        values = (getattr(input_parameters, "research_base_origin_x_cm", None),
                  getattr(input_parameters, "research_base_origin_y_cm", None),
                  getattr(input_parameters, "research_base_depth_cm", None))
        surface = getattr(input_parameters, "soil_surface_z_cm", None)
        if (any(value is None or not math.isfinite(value) for value in values)
                or values[2] <= 0 or surface is None or not math.isfinite(surface)
                or "soil_surface_z_cm" not in getattr(input_parameters, "model_fields_set", set())
                or getattr(input_parameters, "tropism_mode", "legacy") != "fichtl2024"):
            raise ValueError("Root-origin initialization requires explicit finite x/y/positive depth and surface in fichtl2024")
        self.root_origin_diagnostics = self.translate_common_base(values[0], values[1], values[2], surface)

    def translate_common_base(self, x_cm, y_cm, depth_cm, surface_z_cm):
        """The one common-base origin law: rigid translation, no draw or rotation.

        Shared by the historical research origin (whose old-input restrictions
        are checked by its caller) and the schema-3 ``point`` origin layout.
        """
        base = self.G.base_node.node_data
        old = np.array([base.x, base.y, base.z], dtype=float)
        target = np.array([x_cm, y_cm, surface_z_cm - depth_cm], dtype=float)
        nodes = self.G.nodes
        coordinates = np.array([[node.node_data.x, node.node_data.y, node.node_data.z] for node in nodes])
        if not np.isfinite(coordinates).all() or not np.isfinite(target).all():
            raise ValueError("Root-origin initialization requires finite graph coordinates and target")
        translated = target + (coordinates - old)
        if not np.isfinite(translated).all():
            raise ValueError("Root-origin translation produced nonfinite coordinates")
        for node, xyz in zip(nodes, translated):
            node.node_data.x, node.node_data.y, node.node_data.z = xyz
        return dict(
            stage="after_primary_positioning_and_yaw_before_tropism",
            old_base_cm=old.tolist(), target_base_cm=target.tolist(),
            delta_cm=(target - old).tolist(), soil_surface_z_cm=surface_z_cm,
            base_depth_cm=depth_cm, translated_node_count=len(nodes),
        )

    def apply_primary_yaw_initialization(self, input_parameters: RootSimulationModel) -> None:
        """Rigid initial-subtree yaw after native positioning, before tropism.

        The basal-to-apex chord defines yaw. Rotate about the unchanged system
        base; keep every z value unchanged and never draw from self.rng.
        """
        self._validate_primary_yaw_seed(input_parameters)
        base = self.G.base_node.node_data
        origin = np.array([base.x, base.y, base.z], dtype=float)
        plans = []
        for primary in self.organs[1]:
            chord = primary.get_apex_coordinates() - origin
            if not np.isfinite(chord).all() or np.linalg.norm(chord[:2]) <= 1e-12:
                raise ValueError("Primary azimuth is undefined for a zero-horizontal chord")
            organ_id = int(primary.segments[0].node_data.organ_id)
            assigned = sample_primary_yaw(
                input_parameters.research_primary_yaw_mean_deg,
                input_parameters.research_primary_yaw_kappa,
                input_parameters.random_seed, organ_id,
            )
            assigned, reversal = reverse_primary_yaw(
                assigned, getattr(input_parameters, "research_primary_yaw_reverse_probability", None),
                input_parameters.random_seed, organ_id,
            )
            old_yaw = math.atan2(chord[1], chord[0])
            delta = assigned - old_yaw
            rotation = np.array([[math.cos(delta), -math.sin(delta)],
                                 [math.sin(delta), math.cos(delta)]])
            plans.append((primary, organ_id, old_yaw, assigned, delta, rotation, reversal))
        self.primary_yaw_diagnostics = []
        for primary, organ_id, old_yaw, assigned, delta, rotation, reversal in plans:
            subtree = [primary]
            while subtree:
                organ = subtree.pop()
                coordinates = organ.get_coordinates().copy()
                coordinates[:, :2] = (coordinates[:, :2] - origin[:2]) @ rotation.T + origin[:2]
                organ.set_coordinates(coordinates)
                subtree.extend(organ.child_organs)
            realised_chord = primary.get_apex_coordinates() - origin
            realised = math.atan2(realised_chord[1], realised_chord[0])
            self.primary_yaw_diagnostics.append(dict(
                organ_id=organ_id, stream_version="drg-primary-yaw-v1",
                base_cm=origin.tolist(), old_yaw_deg=math.degrees(old_yaw),
                assigned_yaw_deg=math.degrees(assigned), realised_yaw_deg=math.degrees(realised),
                rotation_deg=math.degrees(delta),
                **({"polarity_reversal": reversal} if reversal is not None else {}),
            ))

    def validate(
        self,
        input_parameters: RootSimulationModel,
        pitch: int = 45,
        orders=None,
        allow_reorient: bool = True,
        check_only=None,
    ) -> None:
        """Native validation; ``check_only`` organ IDs draw as usual but never repair.

        Replaced direction laws own their axes, so a native repair must not
        rotate them. Their historical draw is still consumed, keeping the
        native sequential schedule unchanged.
        """
        mode = getattr(input_parameters, "tropism_mode", "legacy")
        if mode == "fichtl2024" and not hasattr(self, "validation_diagnostics"):
            self.validation_diagnostics = []
        for order in (
            range(1, input_parameters.max_order + 1) if orders is None else orders
        ):
            for organ in self.organs[order]:
                extra = {}
                if mode == "fichtl2024":
                    extra["enforce_downward_apex"] = False
                    extra["allow_reorient"] = allow_reorient
                if check_only is not None and int(organ.segments[0].node_data.organ_id) in check_only:
                    extra["allow_reorient"] = False
                organ.validate(
                    (input_parameters.no_root_zone if mode == "legacy" else 0.0)
                    + getattr(input_parameters, "soil_surface_z_cm", 0.0),
                    pitch,
                    input_parameters.max_val_attempts,
                    **extra,
                )
                if mode == "fichtl2024":
                    self.validation_diagnostics.append(
                        dict(
                            order=order,
                            organ_id=organ.segments[0].node_data.organ_id,
                            reorientations=organ.validation_reorientations,
                            invalid=organ.invalid_root,
                        )
                    )

    def grow(
        self, simulation: RootSimulationModel, input_parameters: RootSimulationModel
    ) -> None:
        for _ in range(input_parameters.t):
            for order in range(2, input_parameters.max_order + 1):
                for organ in self.organs[order]:
                    organ.grow(simulation, input_parameters)

    def _check_optional_primary_validation(self, input_parameters: RootSimulationModel) -> None:
        if (getattr(input_parameters, "research_primary_yaw_mean_deg", None) is None
                and getattr(input_parameters, "research_base_depth_cm", None) is None
                and not getattr(input_parameters, "research_primary_inclination_bias", None)
                and getattr(input_parameters, DESIGN_FIELD, None) is None):
            return
        for primary in self.organs[1]:
            if getattr(primary, "validation_reorientations", 0) or primary.invalid_root:
                raise ValueError("Primary validation changed or invalidated optional yaw/origin/inclination initialization")

    def diameter_material(self, density=None):
        """Measure the finished vine by diameter, using a specified dry-density law.

        Returns per-order tissue volume, length and dry mass in each band. With
        no argument, uses the configured bands or the grapevine profile. Crown material
        is accounted for separately by the field study.
        """
        from .tissue_density import GRAPEVINE_STEPPED, summarize_diameter_material

        if getattr(self, "result", None) is None:
            raise ValueError("Run the simulation before measuring diameter material")
        profile = getattr(self, "diameter_density", GRAPEVINE_STEPPED) if density is None else density
        return summarize_diameter_material(self, profile)

    def run(self, input_parameters, *, initial_recorder=None) -> None:
        """Generate a root system from a canonical configuration."""
        from ..data_model.resolution import resolve_config
        from .engine import execute_canonical

        resolved = resolve_config(input_parameters)
        if len(self.G.nodes) != 1 or self.organs or getattr(self, "_extended_run_started", False):
            raise ValueError("Use a fresh simulator for each run")
        if self.random_seed != resolved.seed:
            raise ValueError("Simulator and configuration random_seed must match")
        self._extended_run_started = True
        self.simulation_tag = resolved.simulation_tag
        self.result = None
        execute_canonical(self, resolved, initial_recorder=initial_recorder)

    def _check_extended_result(self):
        from .integrity import validate_result
        try:
            validate_result(self)
        except Exception:
            self.result = None
            raise

    def apply_fichtl_tropism(
        self, parameters: RootSimulationModel, *, scaffold=None, tangent_at=None, orders=None,
        reset_diagnostics=True,
    ) -> None:
        """Keep the generated primary scaffold; reconstruct attached lateral paths.

        Order 2 uses the gravity/plagiotropism mixture; order 3 uses gravity.
        Higher orders use explicit research direction assumptions.
        This is a static, optional kernel with explicit insertion/surface
        assumptions, not temporal CPlantBox growth or an exact 2024 replay.

        ``scaffold`` supplies interval lengths captured before any direction
        law ran; ``tangent_at(attachment_node, chord)`` returns the realized
        parent tangent when the parent axis has a replaced law; ``orders``
        realizes a subset so replaced orders can interleave parent-first, with
        diagnostics accumulated unless ``reset_diagnostics``. All default to
        the historical behaviour.
        """
        if (getattr(parameters, "research_current_length_grid", None) is not None
                or getattr(parameters, "research_parent2_branch_zone_cm", None) is not None
                or validate_rank_strength(getattr(parameters, "research_tertiary_length_rank_strength", None))
                or validate_distal_fraction(getattr(parameters, ATTACH_FIELD, None))):
            raise ValueError("Construction-step grid/tertiary rank requires named controlled replay; native tropism is unsupported")
        self._validate_primary_yaw_seed(parameters)
        row_kappas = getattr(parameters, "research_insertion_row_axial_kappa", None)
        if row_kappas is not None and (reset_diagnostics or not hasattr(self, "row_insertion_diagnostics")):
            self.row_insertion_diagnostics = []
        by_id = {n.node_data.node_id: n for n in self.G.nodes}
        original = (
            {
                k: np.array([n.node_data.x, n.node_data.y, n.node_data.z])
                for k, n in by_id.items()
            }
            if scaffold is None
            else scaffold
        )
        lengths = {
            k: np.linalg.norm(v - original[by_id[k].node_data.parent_id])
            for k, v in original.items()
            if by_id[k].node_data.parent_id in original
        }
        if reset_diagnostics or not hasattr(self, "tropism_diagnostics"):
            self.tropism_diagnostics = {
                "segments": 0,
                "downward": 0,
                "surface_fallback": 0,
                "rejected_surface": 0,
                "by_order": {},
            }
        for order in (range(2, parameters.max_order + 1) if orders is None else orders):
            sigma, sigma_receipt = resolve_fichtl_sigma(
                parameters.fichtl_sigma, order, getattr(parameters, "research_fichtl_sigma_by_order", None),
            )
            by_order = {
                "segments": 0,
                "downward": 0,
                "surface_fallback": 0,
                "rejected_surface": 0,
                "length_sum_cm": 0.0,
                "min_step_cm": None,
                "max_step_cm": 0.0,
                **sigma_receipt,
            }
            self.tropism_diagnostics["by_order"][str(order)] = by_order
            for organ in self.organs[order]:
                if organ.invalid_root:
                    continue
                parent = organ.parent_node.node_data
                grandparent = by_id.get(parent.parent_id)
                if grandparent is None:
                    raise ValueError("Lateral insertion lacks a parent tangent")
                position = np.array([parent.x, parent.y, parent.z])
                gp = grandparent.node_data
                tangent = position - np.array([gp.x, gp.y, gp.z])
                if tangent_at is not None:
                    tangent = tangent_at(organ.parent_node, tangent)
                control = direction_controls(parameters, order)
                mean, sd = control["theta_deg"], control["theta_sd_deg"]
                heading = insertion_heading(tangent, mean, sd, self.rng)
                row_report = None
                if row_kappas is not None:
                    heading, row_report = row_axial_insertion_heading(
                        tangent, heading, row_kappas.get(order), parameters.random_seed,
                        int(organ.segments[0].node_data.organ_id), order,
                    )
                    row_report.update(
                        order=order, organ_id=int(organ.segments[0].node_data.organ_id),
                        realisation_stage="native_search_from_segment1_with_candidate_surface_filter",
                        row_alignment_by_arc=[],
                    )
                    self.row_insertion_diagnostics.append(row_report)
                insertion = heading.copy()
                arc = 0.
                for node in organ.segments:
                    length = lengths[node.node_data.node_id]
                    heading, diagnostics = sample_heading(
                        heading,
                        length,
                        control["probability_down"],
                        sigma,
                        control["trials"],
                        self.rng,
                        start_z=position[2],
                        surface_z=parameters.soil_surface_z_cm,
                    )
                    if row_report is not None:
                        if not row_report["row_alignment_by_arc"]:
                            row_report["post_boundary_heading"] = heading.tolist()
                            row_report["post_search_and_boundary_polar_angle_deg"] = float(np.degrees(np.arccos(
                                np.clip(heading @ (tangent / np.linalg.norm(tangent)), -1., 1.))))
                        row_report["row_alignment_by_arc"].append(dict(
                            node_id=int(node.node_data.node_id), arc_start_cm=arc, arc_end_cm=arc + length,
                            row_projection=float(heading[1]), axial_row_alignment=float(heading[1]**2),
                            alignment_with_insertion=float(heading @ insertion),
                            surface_fallback=bool(diagnostics["surface_fallback"]),
                            rejected_surface_candidates=diagnostics["rejected_surface"],
                        ))
                    arc += length
                    position = position + length * heading
                    node.node_data.x, node.node_data.y, node.node_data.z = position
                    self.tropism_diagnostics["segments"] += 1
                    by_order["segments"] += 1
                    by_order["length_sum_cm"] += length
                    by_order["min_step_cm"] = (
                        length
                        if by_order["min_step_cm"] is None
                        else min(length, by_order["min_step_cm"])
                    )
                    by_order["max_step_cm"] = max(length, by_order["max_step_cm"])
                    for name in ("downward", "surface_fallback", "rejected_surface"):
                        self.tropism_diagnostics[name] += int(diagnostics[name])
                        by_order[name] += int(diagnostics[name])

    def apply_gravitropism(self, gravitropism: float, *, fixed=None) -> None:
        """Legacy blend toward gravity; ``fixed`` node IDs belong to replaced laws.

        A fixed node keeps its realized position; its native daughters blend
        relative to it as they do relative to any parent.
        """
        if not 0 <= gravitropism <= 1:
            raise ValueError("gravitropism must be between 0 and 1")
        if gravitropism == 0:
            return
        gravity = np.array([0.0, 0.0, -1.0])
        original = {
            node.node_data.node_id: np.array(
                [
                    node.node_data.x,
                    node.node_data.y,
                    node.node_data.z,
                ],
                dtype=float,
            )
            for node in self.G.nodes
        }
        updated = {}
        for node in self.G.nodes:
            data = node.node_data
            node_id, parent_id = data.node_id, data.parent_id
            if parent_id not in original or (fixed is not None and node_id in fixed):
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
