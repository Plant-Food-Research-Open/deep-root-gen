"""Contains utilities for producing summary statistics.

This module defines utility functions for producing summary statistics that can be used to compare simulated and observational data.
"""

# mypy: ignore-errors

from abc import ABC, abstractmethod
from pydoc import locate
from typing import Callable

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy.spatial import ConvexHull

px.defaults.template = "ggplot2"


class SummaryStatisticBase(ABC):
    """The summary statistic abstract class."""

    def __init__(self, **_) -> None:
        """SummaryStatisticBase constructor."""
        super().__init__()
        self.statistic = ""
        self.unit = ""

    @abstractmethod
    def calculate(self, df: pd.DataFrame) -> float | np.ndarray:
        """Calculate the summary statistic.

        Args:
            df (pd.DataFrame):
                The root dataframe.

        Raises:
            NotImplementedError:
                Error raised for the unimplemented abstract method.
        """
        raise NotImplementedError("calculate() method not implemented.")

    def get_xy_comparison_data(
        self, df: pd.DataFrame, n_elements: int = 10
    ) -> np.ndarray:
        """Get summary statistic data for comparing against another summary statistic.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.
            n_elements (int, optional):
                The number of elements for the comparison. Defaults to 10.

        Returns:
            np.ndarray:
                The comparison data.
        """
        comparison_data, _ = self.calculate_statistic_per_layer(df)
        comparison_data = comparison_data[:n_elements]
        return comparison_data

    def get_number_of_roots(self, df: pd.DataFrame) -> int:
        """Get the number of roots in the root system.

        Args:
            df (pd.DataFrame):
                The root dataframe.

        Returns:
            int:
                The number of roots.
        """
        df = df.query("order > 0")
        n = len(df.organ_id.unique())
        return n

    def calculate_statistic_per_layer(
        self, df: pd.DataFrame, layer_decrement: int = 10
    ) -> tuple:
        """Calculate a summary statistic per soil layer.

        Args:
            df (pd.DataFrame):
                The root dataframe.
            layer_decrement (int, optional):
                The depth to decrement each soil layer. Defaults to 10.

        Returns:
            tuple:
                The list of summary statistics and soil layers.
        """
        soil_layers = range(0, df.z.min().astype("int"), -layer_decrement)
        soil_layers = np.array(soil_layers)

        statistics_per_layer: list[float] = []
        for soil_layer in soil_layers:
            layer_df = df.query(
                f"z > {soil_layer - layer_decrement} & z < {soil_layer}"
            )
            statistic = self.calculate(layer_df)
            statistics_per_layer.append(statistic)
        return statistics_per_layer, soil_layers

    def visualise(self, df: pd.DataFrame, layer_decrement: int = 10, **_) -> go.Figure:
        """Visualise the summary statistic by soil depth.

        Args:
            df (pd.DataFrame):
                The root dataframe.
            layer_decrement (int, optional):
                The depth to decrement each soil layer. Defaults to 10.

        Returns:
            go.Figure:
                The visualisation of the total root volume.
        """
        statistics, soil_layers = self.calculate_statistic_per_layer(
            df, layer_decrement
        )

        fig = px.scatter(
            title=f"{self.statistic} per soil layer ({layer_decrement} cm)",
            x=statistics,
            y=abs(soil_layers),
        ).update_layout(
            xaxis_title=f"{self.statistic} ({self.unit})", yaxis_title="Soil depth (cm)"
        )

        return fig


class DepthDistribution(SummaryStatisticBase):
    """The DepthDistribution summary statistic."""

    def calculate(self, df: pd.DataFrame, bins: int = 10) -> tuple:
        """Get the cumulative root distribution by soil depth.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.
            bins (int, optional):
                The number of bins for a histogram. Defaults to 10.

        Returns:
            tuple:
                The cumulative root distribution summary statistic.
        """
        depth = abs(df.z)
        count, bins_count = np.histogram(depth, bins=bins)
        bins_count = np.insert(bins_count, 0, 0)
        pdf = count / sum(count)
        cdf = np.cumsum(pdf)
        cdf = np.insert(cdf, 0, 0)
        bins_count = bins_count[1:]
        return cdf, bins_count

    def visualise(self, df: pd.DataFrame, bins: int = 10) -> go.Figure:
        """Visualise the cumulative root distribution by soil depth.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.
            bins (int, optional):
                The number of bins for a histogram. Defaults to 10.

        Returns:
            go.Figure:
                The visualisation of the cumulative root distribution summary statistic.
        """
        cdf, bins_count = self.calculate(df, bins)
        return px.scatter(
            title="Cumulative root distribution by soil depth",
            x=cdf,
            y=bins_count,
        ).update_layout(
            xaxis_title="Cumulative root fraction", yaxis_title="Soil depth (cm)"
        )

    def get_xy_comparison_data(
        self, df: pd.DataFrame, n_elements: int = 10
    ) -> np.ndarray:
        """Get summary statistic data for comparing against another summary statistic.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.
            n_elements (int, optional):
                The number of elements for the comparison. Defaults to 10.

        Returns:
            np.ndarray:
                The comparison data.
        """
        _, bins_count = self.calculate(df, n_elements)
        bins_count = bins_count[:n_elements]
        return bins_count


class RadialDistribution(SummaryStatisticBase):
    """The RadialDistribution summary statistic."""

    def calculate(self, df: pd.DataFrame, bins: int = 10) -> tuple:
        """Get the cumulative root distribution by horizontal distance.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.
            bins (int, optional):
                The number of bins for a histogram. Defaults to 10.

        Returns:
            tuple:
                The cumulative root distribution summary statistic.
        """
        horizontal = abs(df.melt(value_vars=["x", "y"]).value)
        count, bins_count = np.histogram(horizontal, bins=bins)
        bins_count = np.insert(bins_count, 0, 0)
        pdf = count / sum(count)
        cdf = np.cumsum(pdf)
        cdf = np.insert(cdf, 0, 0)
        bins_count = bins_count[1:]
        return cdf, bins_count

    def visualise(self, df: pd.DataFrame, bins: int = 10) -> go.Figure:
        """Visualise the cumulative root distribution by horizontal distance.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.
            bins (int, optional):
                The number of bins for a histogram. Defaults to 10.

        Returns:
            go.Figure:
                The visualisation of the cumulative root distribution summary statistic.
        """
        cdf, bins_count = self.calculate(df, bins)
        return px.scatter(
            title="Cumulative root distribution by horizontal distance",
            x=cdf,
            y=bins_count,
        ).update_layout(
            xaxis_title="Cumulative root fraction",
            yaxis_title="Horizontal root distance (cm)",
        )

    def get_xy_comparison_data(
        self, df: pd.DataFrame, n_elements: int = 10
    ) -> np.ndarray:
        """Get summary statistic data for comparing against another summary statistic.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.
            n_elements (int, optional):
                The number of elements for the comparison. Defaults to 10.

        Returns:
            np.ndarray:
                The comparison data.
        """
        _, bins_count = self.calculate(df, n_elements)
        bins_count = bins_count[:n_elements]
        return bins_count


class TotalVolume(SummaryStatisticBase):
    """The TotalVolume summary statistic."""

    def __init__(self, **_) -> None:
        """TotalVolume constructor."""
        super().__init__()
        self.statistic = "Total root volume"
        self.unit = "cm^3"

    def calculate(self, df: pd.DataFrame) -> float:
        """Caculate the total root volume.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.

        Returns:
            float:
                The total root volume.
        """
        radius = df.diameter / 2
        height = df.length
        volume = np.pi * radius**2 * height
        return np.sum(volume)


class AverageVolume(SummaryStatisticBase):
    """The AverageVolume summary statistic."""

    def __init__(self, **_) -> None:
        """AverageVolume constructor."""
        super().__init__()
        self.statistic = "Average root volume"
        self.unit = "cm^3"

    def calculate(self, df: pd.DataFrame) -> float:
        """Caculate the average root volume.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.

        Returns:
            float:
                The average root volume.
        """
        radius = df.diameter / 2
        height = df.length
        volume = np.pi * radius**2 * height
        total_volume = np.sum(volume)
        n = self.get_number_of_roots(df)
        average = total_volume / n
        return average


class TotalLength(SummaryStatisticBase):
    """The TotalLength summary statistic."""

    def __init__(self, **_) -> None:
        """TotalLength constructor."""
        super().__init__()
        self.statistic = "Total root length"
        self.unit = "cm"

    def calculate(self, df: pd.DataFrame) -> float:
        """Caculate the total root length.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.

        Returns:
            float:
                The total root length.
        """
        return df.length.sum()


class AverageLength(SummaryStatisticBase):
    """The AverageLength summary statistic."""

    def __init__(self, **_) -> None:
        """AverageLength constructor."""
        super().__init__()
        self.statistic = "Average root length"
        self.unit = "cm"

    def calculate(self, df: pd.DataFrame) -> float:
        """Caculate the average root length.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.

        Returns:
            float:
                The average root length.
        """
        total_length = df.length.sum()
        n = self.get_number_of_roots(df)
        average = total_length / n
        return average


class TotalDiameter(SummaryStatisticBase):
    """The TotalDiameter summary statistic."""

    def __init__(self, **_) -> None:
        """TotalDiameter constructor."""
        super().__init__()
        self.statistic = "Total root diameter"
        self.unit = "cm"

    def calculate(self, df: pd.DataFrame) -> float:
        """Caculate the total root diameter.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.

        Returns:
            float:
                The total root diameter.
        """
        return df.diameter.sum()


class AverageDiameter(SummaryStatisticBase):
    """The AverageDiameter summary statistic."""

    def __init__(self, **_) -> None:
        """AverageDiameter constructor."""
        super().__init__()
        self.statistic = "Average root diameter"
        self.unit = "cm"

    def calculate(self, df: pd.DataFrame) -> float:
        """Caculate the average root diameter.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.

        Returns:
            float:
                The average root diameter.
        """
        total_length = df.diameter.sum()
        n = self.get_number_of_roots(df)
        average = total_length / n
        return average


class TotalSpecificRootLength(SummaryStatisticBase):
    def __init__(self, root_tissue_density: float, **_) -> None:
        """TotalSpecificRootLength constructor.

        Args:
            root_tissue_density (float):
                The root tissue density of the root system.
        """
        self.statistic = "Total specific root length"
        self.unit = "cm"
        self.root_tissue_density = root_tissue_density

    def calculate(self, df: pd.DataFrame) -> float:
        """Caculate the total specific root length.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.

        Returns:
            float:
                The total specific root length.
        """
        radius = df.diameter / 2
        height = df.length
        volume = np.pi * radius**2 * height
        mass = volume * self.root_tissue_density
        specific_root_length = df.length / mass
        total = sum(specific_root_length)
        return total


class AverageSpecificRootLength(SummaryStatisticBase):
    """The AverageSpecificRootLength statistic."""

    def __init__(self, root_tissue_density: float, **_) -> None:
        """AverageSpecificRootLength constructor.

        Args:
            root_tissue_density (float):
                The root tissue density of the root system.
        """
        self.statistic = "Average specific root length"
        self.unit = "cm"
        self.root_tissue_density = root_tissue_density

    def calculate(self, df: pd.DataFrame) -> float:
        """Caculate the average specific root length.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.

        Returns:
            float:
                The average specific root length.
        """
        radius = df.diameter / 2
        height = df.length
        volume = np.pi * radius**2 * height
        mass = volume * self.root_tissue_density
        specific_root_length = df.length / mass
        total = sum(specific_root_length)
        n = self.get_number_of_roots(df)
        average = total / n
        return average


class TotalWeight(SummaryStatisticBase):
    """The TotalWeight statistic."""

    def __init__(self, root_tissue_density: float, **_) -> None:
        """TotalWeight constructor.

        Args:
            root_tissue_density (float):
                The root tissue density of the root system.
        """
        self.statistic = "Total root weight"
        self.unit = "g"
        self.root_tissue_density = root_tissue_density

    def calculate(self, df: pd.DataFrame) -> float:
        """Caculate the total root weight.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.

        Returns:
            float:
                The total root weight.
        """
        radius = df.diameter / 2
        height = df.length
        volume = np.pi * radius**2 * height
        mass = volume * self.root_tissue_density
        total = sum(mass)
        return total


class AverageWeight(SummaryStatisticBase):
    """The AverageWeight statistic."""

    def __init__(self, root_tissue_density: float, **_) -> None:
        """AverageWeight constructor.

        Args:
            root_tissue_density (float):
                The root tissue density of the root system.
        """
        self.statistic = "Average root weight"
        self.unit = "g"
        self.root_tissue_density = root_tissue_density

    def calculate(self, df: pd.DataFrame) -> float:
        """Caculate the average root weight.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.

        Returns:
            float:
                The average root weight.
        """
        radius = df.diameter / 2
        height = df.length
        volume = np.pi * radius**2 * height
        mass = volume * self.root_tissue_density
        total = sum(mass)
        n = self.get_number_of_roots(df)
        average = total / n
        return average


class ConvexHullArea(SummaryStatisticBase):
    """The ConvexHullArea statistic."""

    def __init__(self, **_) -> None:
        """ConvexHullArea constructor."""
        self.statistic = "Convex hull area"
        self.unit = "cm^2"

    def calculate(self, df: pd.DataFrame) -> float:
        """Caculate the area of the convex hull.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.

        Returns:
            float:
                The area of the convex hull.
        """
        coordinates = df[["x", "y", "z"]].values
        if not np.any(coordinates):
            return -1
        hull = ConvexHull(points=coordinates)
        return hull.area


class ConvexHullVolume(SummaryStatisticBase):
    """The ConvexHullVolume statistic."""

    def __init__(self, **_) -> None:
        """ConvexHullVolume constructor."""
        self.statistic = "Convex hull volume"
        self.unit = "cm^3"

    def calculate(self, df: pd.DataFrame) -> float:
        """Caculate the volume of the convex hull.

        Args:
            df (pd.DataFrame):
                The dataframe of root data.

        Returns:
            float:
                The volume of the convex hull.
        """
        coordinates = df[["x", "y", "z"]].values
        if not np.any(coordinates):
            return -1
        hull = ConvexHull(points=coordinates)
        return hull.volume



class RootLengthDensity(SummaryStatisticBase):
    """Root length density within a 3D soil voxel grid."""

    def __init__(
        self,
        soil_df: pd.DataFrame,
        length_source: str = "recorded",
        root_types: list[str] | None = None,
        **_,
    ) -> None:
        super().__init__()
        self.statistic = "Root length density"
        self.unit = "cm/cm^3"

        if length_source not in {"recorded", "geometric"}:
            raise ValueError(
                "length_source must be 'recorded' or 'geometric'"
            )

        self.length_source = length_source
        self.root_types = root_types

        # Grid points define voxel boundaries.
        self.edges = [
            np.sort(soil_df[axis].unique().astype(float))
            for axis in ("x", "y", "z")
        ]

        if any(
            len(e) < 2 or not np.all(np.isfinite(e))
            for e in self.edges
        ):
            raise ValueError("Invalid soil grid coordinates.")

        self.shape = tuple(len(e) - 1 for e in self.edges)

        self.soil_volume = float(
            np.prod([e[-1] - e[0] for e in self.edges])
        )

    def _voxel_lengths(self, df: pd.DataFrame) -> np.ndarray:
        """Allocate root segment lengths to intersected voxels."""

        required = {
            "node_id", "parent_id", "x", "y", "z", "length"
        }
        missing = required - set(df.columns)

        if missing:
            raise ValueError(f"Missing columns: {sorted(missing)}")

        nodes = df.set_index("node_id")

        # Select children with known parent coordinates.
        children = df.loc[
            df["parent_id"].isin(nodes.index)
        ]

        if "invalid_root" in children.columns:
            children = children.loc[
                ~children["invalid_root"]
                .fillna(False)
                .astype(bool)
            ]

        if "order" in children.columns:
            children = children.loc[children["order"] > 0]

        if self.root_types is not None:
            children = children.loc[
                children["root_type"].isin(self.root_types)
            ]

        grid = np.zeros(self.shape, dtype=float)
        eps = 1e-12

        for row in children.itertuples(index=False):
            parent = nodes.loc[row.parent_id]

            a = np.array(
                [parent.x, parent.y, parent.z], dtype=float
            )
            b = np.array(
                [row.x, row.y, row.z], dtype=float
            )

            displacement = b - a
            geometric_length = float(
                np.linalg.norm(displacement)
            )

            segment_length = (
                float(row.length)
                if self.length_source == "recorded"
                else geometric_length
            )

            if not np.isfinite(segment_length) or segment_length < 0:
                raise ValueError("Invalid segment length.")

            if segment_length == 0:
                continue

            if geometric_length <= eps:
                raise ValueError(
                    f"Node {row.node_id} has positive length "
                    "but coincident endpoints."
                )

            # Clip segment against the soil grid bounding box.
            lo, hi = 0.0, 1.0

            for j, edges in enumerate(self.edges):
                if abs(displacement[j]) <= eps:
                    if a[j] < edges[0] or a[j] > edges[-1]:
                        hi = -1.0
                        break
                else:
                    ts = (
                        edges[[0, -1]] - a[j]
                    ) / displacement[j]

                    lo = max(lo, float(np.min(ts)))
                    hi = min(hi, float(np.max(ts)))

            if hi - lo <= eps:
                continue

            # Find intersections with internal voxel boundaries.
            cuts = [lo, hi]

            for j, edges in enumerate(self.edges):
                if abs(displacement[j]) > eps:
                    t = (
                        edges[1:-1] - a[j]
                    ) / displacement[j]

                    cuts.extend(
                        t[
                            (t > lo + eps)
                            & (t < hi - eps)
                        ].tolist()
                    )

            cuts = np.sort(np.asarray(cuts))

            # Allocate each subsegment to its containing voxel.
            for t0, t1 in zip(cuts[:-1], cuts[1:]):
                if t1 - t0 <= eps:
                    continue

                midpoint = a + displacement * (
                    (t0 + t1) / 2
                )

                idx = tuple(
                    int(np.clip(
                        np.searchsorted(
                            edges, midpoint[j], side="right"
                        ) - 1,
                        0,
                        len(edges) - 2,
                    ))
                    for j, edges in enumerate(self.edges)
                )

                grid[idx] += (
                    (t1 - t0) * segment_length
                )

        return grid

    def calculate(self, df: pd.DataFrame) -> float:
        """Whole-grid root length density."""
        root_length = self._voxel_lengths(df).sum()
        return float(root_length / self.soil_volume)

    def calculate_per_voxel(
        self, df: pd.DataFrame
    ) -> pd.DataFrame:
        """Calculate RLD for every soil voxel."""
        lengths = self._voxel_lengths(df)

        ix, iy, iz = np.indices(
            self.shape
        ).reshape(3, -1)

        x, y, z = self.edges

        volumes = (
            np.diff(x)[ix]
            * np.diff(y)[iy]
            * np.diff(z)[iz]
        )

        return pd.DataFrame({
            "column": ix,
            "row": iy,
            "layer": iz,
            "x_min": x[ix],
            "x_max": x[ix + 1],
            "y_min": y[iy],
            "y_max": y[iy + 1],
            "z_min": z[iz],
            "z_max": z[iz + 1],
            "root_length_cm": lengths.ravel(),
            "soil_volume_cm3": volumes,
            "rld_cm_cm3": lengths.ravel() / volumes,
        })

    @staticmethod
    def aggregate(
        voxels: pd.DataFrame,
        by: str,
    ) -> pd.DataFrame:
        """Aggregate voxel RLD by row, column, or layer."""

        groups = {
            "row": ["row", "y_min", "y_max"],
            "column": ["column", "x_min", "x_max"],
            "layer": ["layer", "z_min", "z_max"],
        }

        if by not in groups:
            raise ValueError(
                "by must be 'row', 'column', or 'layer'"
            )

        result = voxels.groupby(
            groups[by], as_index=False
        )[
            ["root_length_cm", "soil_volume_cm3"]
        ].sum()

        result["rld_cm_cm3"] = (
            result["root_length_cm"]
            / result["soil_volume_cm3"]
        )

        if by == "layer":
            result["depth_top_cm"] = -result["z_max"]
            result["depth_bottom_cm"] = -result["z_min"]

            result = result.sort_values(
                "depth_top_cm"
            ).reset_index(drop=True)

        return result

    def calculate_per_row(
        self, df: pd.DataFrame
    ) -> pd.DataFrame:
        return self.aggregate(
            self.calculate_per_voxel(df), "row"
        )

    def calculate_per_column(
        self, df: pd.DataFrame
    ) -> pd.DataFrame:
        return self.aggregate(
            self.calculate_per_voxel(df), "column"
        )

    def calculate_per_layer(
        self, df: pd.DataFrame
    ) -> pd.DataFrame:
        return self.aggregate(
            self.calculate_per_voxel(df), "layer"
        )

    def calculate_statistic_per_layer(
        self, df: pd.DataFrame,
        layer_decrement: int = 10,
    ) -> tuple:
        """Compatibility with the existing base-class interface.

        Uses actual soil grid layers, not layer_decrement.
        """
        layers = self.calculate_per_layer(df)
        return (
            layers["rld_cm_cm3"].tolist(),
            layers["z_max"].to_numpy(),
        )

    def visualise(self, df: pd.DataFrame, **_) -> go.Figure:
        """Visualise RLD using the actual soil depth layers."""
        layers = self.calculate_per_layer(df)

        fig = px.scatter(
            layers,
            x="rld_cm_cm3",
            y="depth_top_cm",
            title="Root length density by soil layer",
        )
        fig.update_layout(
            xaxis_title="RLD (cm/cm³)",
            yaxis_title="Soil depth (cm)",
        )
        fig.update_yaxes(autorange="reversed")
        return fig


class RootDryMassByDiameter(SummaryStatisticBase):
    """Root dry mass grouped by root diameter class."""

    def __init__(
        self,
        diameter_bins_mm: list[float],
        root_tissue_density: float | None = None,
        **_,
    ) -> None:
        super().__init__()
        self.statistic = "Root dry mass by diameter"
        self.unit = "g"

        self.diameter_bins_mm = np.asarray(
            diameter_bins_mm, dtype=float
        )
        self.root_tissue_density = root_tissue_density

        if (
            len(self.diameter_bins_mm) < 2
            or self.diameter_bins_mm[0] < 0
            or not np.all(np.diff(self.diameter_bins_mm) > 0)
        ):
            raise ValueError("Invalid diameter bins.")

        if (
            root_tissue_density is not None
            and root_tissue_density <= 0
        ):
            raise ValueError("RTD must be positive.")

    def calculate(self, df: pd.DataFrame) -> np.ndarray:
        """Calculate root dry mass (g) in each diameter class."""
        df = df.copy()

        if "invalid_root" in df.columns:
            df = df.loc[
                ~df["invalid_root"].fillna(False).astype(bool)
            ]

        if "order" in df.columns:
            df = df.loc[df["order"] > 0]

        diameter_cm = df["diameter"].to_numpy(dtype=float)
        length_cm = df["length"].to_numpy(dtype=float)

        if self.root_tissue_density is None:
            rtd = df["root_tissue_density"].to_numpy(
                dtype=float
            )
        else:
            rtd = self.root_tissue_density

        # Cylindrical root segment volume (cm3).
        volume = np.pi * (diameter_cm / 2) ** 2 * length_cm

        # Root dry mass (g).
        mass = volume * rtd

        # Convert root diameters from cm to mm.
        diameter_mm = diameter_cm * 10

        mass_per_class, _ = np.histogram(
            diameter_mm,
            bins=self.diameter_bins_mm,
            weights=mass,
        )

        return mass_per_class

    def calculate_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a dataframe of root dry mass by diameter."""
        mass = self.calculate(df)

        return pd.DataFrame({
            "diameter_min_mm": self.diameter_bins_mm[:-1],
            "diameter_max_mm": self.diameter_bins_mm[1:],
            "dry_mass_g": mass,
        })

    def get_xy_comparison_data(
        self, df: pd.DataFrame, n_elements: int = 10
    ) -> np.ndarray:
        return self.calculate(df)[:n_elements]

    def visualise(self, df: pd.DataFrame, **_) -> go.Figure:
        """Visualise dry mass by diameter class."""
        results = self.calculate_df(df)

        labels = [
            (
                f"{lo:g}–{hi:g}"
                if np.isfinite(hi)
                else f"≥{lo:g}"
            )
            for lo, hi in zip(
                results["diameter_min_mm"],
                results["diameter_max_mm"],
            )
        ]

        return px.bar(
            x=labels,
            y=results["dry_mass_g"],
            labels={
                "x": "Root diameter (mm)",
                "y": "Root dry mass (g)",
            },
            title=self.statistic,
        )

def get_summary_statistic_func(summary_statistic: str) -> Callable:
    """Get the summary statistic function by name.

    Args:
        summary_statistic (str):
            The summary statistic name.

    Returns:
        Callable:
            The summary statistic function.
    """
    summary_statistic = summary_statistic.replace("_", " ").title().replace(" ", "")
    module = "deeprootgen.statistics.summary_statistics"
    return locate(f"{module}.{summary_statistic}")


def get_summary_statistics() -> list[dict]:
    """Get a list of available summary statistics and labels.

    Returns:
        list[dict]:
            A list of available summary statistics and labels.
    """
    summary_statistics: list[str] = [
        "root_dry_mass_by_diameter",
        "total_volume",
        "average_volume",
        "total_length",
        "average_length",
        "total_diameter",
        "average_diameter",
        "root_length_density",
        # "total_specific_root_length",
        # "average_specific_root_length",
        "total_weight",
        "average_weight",
        "depth_distribution",
        "radial_distribution",
        "convex_hull_area",
        "convex_hull_volume",
    ]

    summary_statistic_list = []
    for summary_statistic in summary_statistics:
        label = summary_statistic.replace("_", " ").title()
        summary_statistic_list.append({"value": summary_statistic, "label": label})

    return summary_statistic_list
