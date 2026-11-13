"""Summary statistics for hierarchical DeepRootGen root-system architectures.

Input is the node DataFrame returned by ``simulation.G.as_df()``.  A root
segment is the edge from a node's parent to that node; its attributes belong
to the child node.  Only valid child segments of order > 0 are measured.

Lengths default to 3D geometric lengths.  Pass length_source='recorded' to
use the stored node length instead.  In particular, voxel statistics include
only the part of a segment lying inside the supplied soil grid.
"""

# mypy: ignore-errors
from __future__ import annotations

from abc import ABC, abstractmethod
from pydoc import locate
from typing import Callable

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy.spatial import ConvexHull, QhullError

px.defaults.template = "ggplot2"
_EPS = 1e-12


def _segments(
    df: pd.DataFrame,
    length_source: str = "geometric",
    root_types: list[str] | None = None,
) -> pd.DataFrame:
    """Valid child segments, with their parent coordinates and geometry.

    An invalid *parent point* is still retained as the start coordinate of a
    valid child segment.  The invalid flag is applied to the child segment,
    as in the existing DeepRootGen voxel aggregation code.
    """
    if length_source not in {"recorded", "geometric"}:
        raise ValueError("length_source must be 'recorded' or 'geometric'.")
    required = {"node_id", "parent_id", "x", "y", "z", "order", "organ_id", "segment_rank"}
    if length_source == "recorded":
        required.add("length")
    if root_types is not None:
        required.add("root_type")
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing root graph columns: {sorted(missing)}")
    if df["node_id"].duplicated().any():
        raise ValueError("node_id must be unique.")

    out = df.loc[df["order"].gt(0) & df["parent_id"].isin(df["node_id"])].copy()
    if "invalid_root" in out:
        out = out.loc[~out["invalid_root"].fillna(False).astype(bool)].copy()
    if root_types is not None:
        out = out.loc[out["root_type"].isin(root_types)].copy()

    parents = df[["node_id", "x", "y", "z", "organ_id", "order"]].rename(
        columns={
            "node_id": "parent_id", "x": "parent_x", "y": "parent_y",
            "z": "parent_z", "organ_id": "parent_organ_id",
            "order": "parent_order",
        }
    )
    out = out.merge(parents, on="parent_id", how="left", validate="many_to_one", sort=False)
    for axis in "xyz":
        out[f"d{axis}"] = out[axis].to_numpy(float) - out[f"parent_{axis}"].to_numpy(float)
        out[f"mid_{axis}"] = (out[axis].to_numpy(float) + out[f"parent_{axis}"].to_numpy(float)) / 2

    displacement = out[["dx", "dy", "dz"]].to_numpy(float)
    geometric = np.linalg.norm(displacement, axis=1)
    if not np.isfinite(geometric).all():
        raise ValueError("Nonfinite root coordinates.")
    if (geometric <= _EPS).any():
        raise ValueError("Zero-length segment encountered in valid root graph.")
    out["geometric_length_cm"] = geometric
    if length_source == "geometric":
        length = geometric
    else:
        length = out["length"].to_numpy(float)
    if not np.isfinite(length).all() or (length < 0).any():
        raise ValueError("Root segment lengths must be nonnegative and finite.")
    out["segment_length_cm"] = length
    for j, axis in enumerate("xyz"):
        out[f"unit_{axis}"] = displacement[:, j] / geometric
    return out


def _origin(df: pd.DataFrame, origin: tuple[float, float, float] | None = None) -> np.ndarray:
    """Use the supplied planting point or the first order-0 base node."""
    if origin is not None:
        arr = np.asarray(origin, dtype=float)
        if arr.shape != (3,) or not np.isfinite(arr).all():
            raise ValueError("origin must contain three finite coordinates.")
        return arr
    if "order" in df and "node_id" in df:
        bases = df.loc[df["order"].eq(0)]
        if len(bases):
            if "parent_id" in df:
                bases = pd.concat([
                    bases.loc[~bases["parent_id"].isin(df["node_id"])], bases
                ]).drop_duplicates("node_id", keep="first")
            return bases.iloc[0][["x", "y", "z"]].to_numpy(float)
    return np.zeros(3)


def _bin_edges(bins, maximum: float) -> np.ndarray:
    if isinstance(bins, (int, np.integer)):
        if bins < 1:
            raise ValueError("bins must be a positive integer.")
        edges = np.linspace(0.0, max(float(maximum), 1.0), int(bins) + 1)
    else:
        edges = np.asarray(bins, dtype=float)
    if (edges.ndim != 1 or len(edges) < 2 or
            not np.all(np.diff(edges) > 0) or edges[0] < 0 or
            not np.isfinite(edges[:-1]).all() or np.isnan(edges[-1])):
        raise ValueError("Bin edges must be increasing, nonnegative and valid.")
    return edges


def _length_distribution(
    segments: pd.DataFrame,
    edges: np.ndarray,
    coordinate: str,
    origin: np.ndarray,
) -> np.ndarray:
    """Allocate exact straight-segment length to depth slabs or radial rings.

    Crossings with depth planes are linear.  Crossings with radial cylinders
    use quadratic intersections, so a segment can enter and leave one ring.
    """
    result = np.zeros(len(edges) - 1, dtype=float)
    for row in segments.itertuples(index=False):
        a = np.array([row.parent_x, row.parent_y, row.parent_z], dtype=float)
        delta = np.array([row.dx, row.dy, row.dz], dtype=float)
        cuts = [0.0, 1.0]
        if coordinate == "depth":
            value0 = origin[2] - a[2]
            dv = -delta[2]
            if abs(dv) > _EPS:
                cuts.extend((edges[np.isfinite(edges)] - value0) / dv)

            def evaluate(t):
                return value0 + dv * t

        elif coordinate == "radius":
            xy = a[:2] - origin[:2]
            dxy = delta[:2]
            A = float(np.dot(dxy, dxy))
            B = 2.0 * float(np.dot(xy, dxy))
            C0 = float(np.dot(xy, xy))
            if A > _EPS:
                for radius in edges[np.isfinite(edges)]:
                    C = C0 - radius**2
                    disc = B * B - 4 * A * C
                    if disc >= 0:
                        sq = np.sqrt(max(disc, 0.0))
                        cuts.extend([(-B - sq) / (2 * A), (-B + sq) / (2 * A)])

            def evaluate(t):
                return np.linalg.norm(xy + dxy * t)

        else:
            raise ValueError("coordinate must be 'depth' or 'radius'.")

        cuts = np.unique(np.clip(np.asarray(cuts, dtype=float), 0, 1))
        for lo, hi in zip(cuts[:-1], cuts[1:]):
            if hi - lo <= _EPS:
                continue
            v = evaluate((lo + hi) / 2)
            index = int(np.searchsorted(edges, v, side="right") - 1)
            if 0 <= index < len(result):
                result[index] += (hi - lo) * row.segment_length_cm
    return result


def _distribution_table(edges: np.ndarray, lengths: np.ndarray, prefix: str):
    total = lengths.sum()
    fraction = lengths / total if total > 0 else np.zeros_like(lengths)
    return pd.DataFrame({
        f"{prefix}_min_cm": edges[:-1], f"{prefix}_max_cm": edges[1:],
        "root_length_cm": lengths, "root_length_fraction": fraction,
        "cumulative_root_length_fraction": np.cumsum(fraction),
    })


def _root_count(segments: pd.DataFrame) -> int:
    return int(segments["organ_id"].nunique())


def _mass(segments: pd.DataFrame, root_tissue_density: float | None) -> np.ndarray:
    if "diameter" not in segments:
        raise ValueError("Missing diameter column.")
    diameter = segments["diameter"].to_numpy(float)
    if not np.isfinite(diameter).all() or (diameter < 0).any():
        raise ValueError("Diameters must be finite and nonnegative.")
    if root_tissue_density is None:
        if "root_tissue_density" not in segments:
            raise ValueError("root_tissue_density must be supplied or present on nodes.")
        density = segments["root_tissue_density"].to_numpy(float)
    else:
        density = np.asarray(root_tissue_density, dtype=float)
    if not np.isfinite(density).all() or (density <= 0).any():
        raise ValueError("Root tissue density must be positive and finite.")
    return np.pi * (diameter / 2) ** 2 * segments["segment_length_cm"].to_numpy(float) * density


class SummaryStatisticBase(ABC):
    """Base for root architecture statistics; accepts full node DataFrames."""

    def __init__(self, length_source: str = "geometric", **_) -> None:
        self.statistic = ""
        self.unit = ""
        if length_source not in {"geometric", "recorded"}:
            raise ValueError("Invalid length_source.")
        self.length_source = length_source

    def segments(self, df: pd.DataFrame) -> pd.DataFrame:
        return _segments(df, self.length_source)

    @abstractmethod
    def calculate(self, df: pd.DataFrame):
        raise NotImplementedError

    def get_number_of_roots(self, df: pd.DataFrame) -> int:
        return _root_count(self.segments(df))

    def calculate_statistic_per_layer(self, df: pd.DataFrame, layer_decrement: int = 10):
        """Midpoint-assigned approximation for scalar statistics.

        Exact length-by-depth allocation is in DepthDistribution, and exact
        grid-layer RLD is in RootLengthDensity.  Parent nodes are retained
        for graph geometry while non-layer child segments are masked out.
        """
        if layer_decrement <= 0:
            raise ValueError("layer_decrement must be positive.")
        segs = self.segments(df)
        if segs.empty:
            return [], np.array([])
        n = int(np.ceil(max(0.0, -float(segs[["z", "parent_z"]].min().min())) / layer_decrement))
        tops = -np.arange(n) * layer_decrement
        results = []
        for top in tops:
            selected = segs.loc[(segs.mid_z <= top) & (segs.mid_z > top - layer_decrement), "node_id"]
            partial = df.copy()
            invalid = partial["invalid_root"].fillna(False).astype(bool) if "invalid_root" in partial else False
            partial["invalid_root"] = invalid | ~partial["node_id"].isin(selected)
            results.append(self.calculate(partial))
        return results, tops

    def get_xy_comparison_data(self, df: pd.DataFrame, n_elements: int = 10) -> np.ndarray:
        values, _ = self.calculate_statistic_per_layer(df)
        return np.asarray(values[:n_elements])

    def visualise(self, df: pd.DataFrame, layer_decrement: int = 10, **_) -> go.Figure:
        values, tops = self.calculate_statistic_per_layer(df, layer_decrement)
        fig = px.scatter(x=values, y=-tops, title=f"{self.statistic} per soil layer (approximate)")
        fig.update_layout(xaxis_title=f"{self.statistic} ({self.unit})", yaxis_title="Depth (cm)")
        fig.update_yaxes(autorange="reversed")
        return fig


class RootNumber(SummaryStatisticBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Root number", "roots"

    def calculate(self, df):
        return self.get_number_of_roots(df)


class TotalLength(SummaryStatisticBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Total root length", "cm"

    def calculate(self, df):
        return float(self.segments(df)["segment_length_cm"].sum())


class AverageLength(SummaryStatisticBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Average length per root", "cm"

    def calculate(self, df):
        s = self.segments(df)
        return float(s.segment_length_cm.sum() / len(s.organ_id.unique())) if len(s) else float("nan")


class TotalVolume(SummaryStatisticBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Total root volume", "cm³"

    def calculate(self, df):
        s = self.segments(df)
        return float((np.pi * (s.diameter / 2) ** 2 * s.segment_length_cm).sum())


class AverageVolume(TotalVolume):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.statistic = "Average volume per root"

    def calculate(self, df):
        n = self.get_number_of_roots(df)
        return float(super().calculate(df) / n) if n else float("nan")


class TotalDiameter(SummaryStatisticBase):
    """Legacy sum of segment diameters (sensitive to graph subdivision)."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Total segment diameter (legacy)", "cm"

    def calculate(self, df):
        return float(self.segments(df)["diameter"].sum())


class AverageDiameter(SummaryStatisticBase):
    """Length-weighted mean root-segment diameter."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Length-weighted mean root diameter", "cm"

    def calculate(self, df):
        s = self.segments(df)
        total = s.segment_length_cm.sum()
        return float(np.dot(s.diameter, s.segment_length_cm) / total) if total else float("nan")


class TotalSpecificRootLength(SummaryStatisticBase):
    """Whole-RSA length per dry mass (cm/g), not sum of segment SRLs."""
    def __init__(self, root_tissue_density: float, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Specific root length", "cm/g"
        self.root_tissue_density = root_tissue_density

    def calculate(self, df):
        s = self.segments(df)
        m = _mass(s, self.root_tissue_density).sum()
        return float(s.segment_length_cm.sum() / m) if m > 0 else float("nan")


class AverageSpecificRootLength(TotalSpecificRootLength):
    """Arithmetic mean of organ-specific length/mass ratios (cm/g)."""
    def __init__(self, root_tissue_density: float, **kwargs):
        super().__init__(root_tissue_density, **kwargs)
        self.statistic = "Average organ-specific root length"

    def calculate(self, df):
        s = self.segments(df).copy()
        if s.empty:
            return float("nan")
        s["segment_mass_g"] = _mass(s, self.root_tissue_density)
        roots = s.groupby("organ_id")[["segment_length_cm", "segment_mass_g"]].sum()
        roots = roots.loc[roots.segment_mass_g > 0]
        return float((roots.segment_length_cm / roots.segment_mass_g).mean()) if len(roots) else float("nan")


class TotalWeight(SummaryStatisticBase):
    def __init__(self, root_tissue_density: float, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Total root dry mass", "g"
        self.root_tissue_density = root_tissue_density

    def calculate(self, df):
        return float(_mass(self.segments(df), self.root_tissue_density).sum())


class AverageWeight(TotalWeight):
    def __init__(self, root_tissue_density: float, **kwargs):
        super().__init__(root_tissue_density, **kwargs)
        self.statistic = "Average root dry mass"

    def calculate(self, df):
        n = self.get_number_of_roots(df)
        return float(super().calculate(df) / n) if n else float("nan")


class ConvexHullArea(SummaryStatisticBase):
    """Surface area of the 3D convex hull, not projected horizontal area."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "3D convex hull surface area", "cm²"

    def calculate(self, df):
        return _convex_measure(self.segments(df), "area")


class ConvexHullVolume(SummaryStatisticBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "3D convex hull volume", "cm³"

    def calculate(self, df):
        return _convex_measure(self.segments(df), "volume")


def _convex_measure(s: pd.DataFrame, what: str) -> float:
    if s.empty:
        return float("nan")
    points = np.unique(np.vstack([
        s[["x", "y", "z"]].to_numpy(float),
        s[["parent_x", "parent_y", "parent_z"]].to_numpy(float),
    ]), axis=0)
    if len(points) < 4:
        return float("nan")
    try:
        return float(getattr(ConvexHull(points), what))
    except QhullError:
        return float("nan")


class RootLengthDistribution(SummaryStatisticBase):
    """Histogram of complete valid-root lengths, one observation per organ."""
    def __init__(self, length_bins_cm=None, bins: int = 10, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Root length distribution", "roots"
        self.length_bins_cm = length_bins_cm
        self.bins = bins

    def per_root(self, df):
        s = self.segments(df)
        if s.empty:
            return pd.DataFrame(columns=["organ_id", "order", "root_length_cm"])
        return s.groupby(["organ_id", "order"], as_index=False).agg(
            root_length_cm=("segment_length_cm", "sum")
        )

    def calculate_df(self, df):
        roots = self.per_root(df)
        values = roots.root_length_cm.to_numpy(float)
        edges = _bin_edges(self.length_bins_cm if self.length_bins_cm is not None else self.bins,
                           float(values.max()) if len(values) else 0.0)
        counts, _ = np.histogram(values, edges)
        return pd.DataFrame({
            "length_min_cm": edges[:-1], "length_max_cm": edges[1:],
            "root_count": counts,
        })

    def calculate(self, df):
        return self.calculate_df(df)["root_count"].to_numpy()

    def get_xy_comparison_data(self, df, n_elements=10):
        return self.calculate(df)[:n_elements]

    def visualise(self, df, **_):
        table = self.calculate_df(df)
        return px.bar(table, x="length_min_cm", y="root_count", title=self.statistic,
                      labels={"length_min_cm": "Root length bin start (cm)"})


class RootDiameterDistribution(SummaryStatisticBase):
    """Length-weighted distribution by segment diameter (mm)."""
    def __init__(self, diameter_bins_mm=None, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Root length by diameter class", "cm"
        if diameter_bins_mm is None:
            diameter_bins_mm = [0, 0.5, 1, 2, 5, 10, 20, np.inf]
        self.edges = _bin_edges(diameter_bins_mm, 0.0)

    def calculate(self, df):
        s = self.segments(df)
        lengths, _ = np.histogram(s.diameter.to_numpy(float) * 10,
                                  bins=self.edges, weights=s.segment_length_cm.to_numpy(float))
        return lengths

    def calculate_df(self, df):
        lengths = self.calculate(df)
        return pd.DataFrame({
            "diameter_min_mm": self.edges[:-1], "diameter_max_mm": self.edges[1:],
            "root_length_cm": lengths,
            "root_length_fraction": lengths / lengths.sum() if lengths.sum() else np.zeros_like(lengths),
        })

    def get_xy_comparison_data(self, df, n_elements=10):
        return self.calculate(df)[:n_elements]

    def visualise(self, df, **_):
        data = self.calculate_df(df)
        return px.bar(data, x="diameter_min_mm", y="root_length_cm", title=self.statistic)


class RootBranchingOrderDistribution(SummaryStatisticBase):
    """Counts and root lengths by topological order."""
    def __init__(self, max_order: int | None = None, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Root branching order distribution", "roots"
        self.max_order = max_order

    def calculate_df(self, df):
        s = self.segments(df)
        highest = self.max_order or (int(s.order.max()) if len(s) else 0)
        orders = pd.DataFrame({"order": np.arange(1, highest + 1, dtype=int)})
        if s.empty:
            return orders.assign(root_count=0, root_length_cm=0.0)
        counts = s.groupby("order").organ_id.nunique().rename("root_count")
        lengths = s.groupby("order").segment_length_cm.sum().rename("root_length_cm")
        return orders.join(counts, on="order").join(lengths, on="order").fillna(0)

    def calculate(self, df):
        return self.calculate_df(df).root_count.to_numpy()

    def get_xy_comparison_data(self, df, n_elements=10):
        return self.calculate(df)[:n_elements]

    def visualise(self, df, **_):
        return px.bar(self.calculate_df(df), x="order", y="root_count", title=self.statistic)


class RootBranchingFrequency(SummaryStatisticBase):
    """Lateral-root emergence events per cm of eligible parent-root length.

    Eligible orders are < max_order.  If max_order is not supplied, the
    highest observed order (at least 2) is used.  Supply the model's
    max_order for comparable results even if high orders happen to be absent.
    """
    def __init__(self, max_order: int | None = None, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Root branching frequency", "branches/cm"
        self.max_order = max_order

    def calculate(self, df):
        s = self.segments(df)
        if s.empty:
            return 0.0
        highest = int(self.max_order) if self.max_order is not None else max(int(s.order.max()), 2)
        parents = s.loc[s.order < highest]
        bases = s.loc[
            s.segment_rank.eq(1) & s.order.gt(1) &
            s.parent_order.eq(s.order - 1) & s.parent_order.gt(0) &
            s.parent_organ_id.ne(s.organ_id)
        ]
        denominator = float(parents.segment_length_cm.sum())
        return float(bases.organ_id.nunique() / denominator) if denominator > 0 else float("nan")


class RootBranchingAngleDistribution(SummaryStatisticBase):
    """Angle (degrees) between parent incoming tangent and daughter start.

    Excludes primary roots attached to the origin and junctions where the
    incoming parent segment is not valid/available.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Lateral branching angles", "degrees"

    def calculate_df(self, df):
        s = self.segments(df)
        bases = s.loc[s.segment_rank.eq(1) & s.order.gt(1)].copy()
        parent_tangent = s[["node_id", "organ_id", "order", "unit_x", "unit_y", "unit_z"]].rename(
            columns={"node_id": "parent_id", "organ_id": "incoming_organ_id", "order": "incoming_order",
                     "unit_x": "parent_ux", "unit_y": "parent_uy", "unit_z": "parent_uz"}
        )
        bases = bases.merge(parent_tangent, on="parent_id", how="inner", validate="many_to_one")
        bases = bases.loc[
            bases.incoming_order.eq(bases.order - 1) &
            bases.incoming_organ_id.ne(bases.organ_id)
        ].copy()
        dot = (bases.unit_x * bases.parent_ux + bases.unit_y * bases.parent_uy +
               bases.unit_z * bases.parent_uz)
        bases["branching_angle_deg"] = np.degrees(np.arccos(np.clip(dot, -1, 1)))
        return bases[["organ_id", "order", "parent_id", "incoming_organ_id", "branching_angle_deg"]].rename(
            columns={"incoming_organ_id": "parent_organ_id"}
        ).reset_index(drop=True)

    def calculate(self, df):
        return self.calculate_df(df).branching_angle_deg.to_numpy(float)

    def get_xy_comparison_data(self, df, n_elements=10):
        return self.calculate(df)[:n_elements]

    def visualise(self, df, **_):
        return px.histogram(self.calculate_df(df), x="branching_angle_deg", title=self.statistic)


class RootOrientationDistribution(SummaryStatisticBase):
    """Segment inclination and azimuth, plus net base-to-tip root direction.

    Inclination 0° = vertically downward, 90° = horizontal, 180° = upward.
    Azimuth is measured counterclockwise from +x in the horizontal plane.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Segment inclination distribution", "degrees"

    def calculate_df(self, df):
        s = self.segments(df).copy()
        s["inclination_deg"] = np.degrees(np.arccos(np.clip(-s.unit_z, -1, 1)))
        s["azimuth_deg"] = (np.degrees(np.arctan2(s.dy, s.dx)) + 360) % 360
        s["vertical_downward_fraction"] = -s.unit_z
        s["horizontal_fraction"] = np.hypot(s.unit_x, s.unit_y)
        return s[["node_id", "organ_id", "order", "segment_length_cm",
                  "inclination_deg", "azimuth_deg", "vertical_downward_fraction", "horizontal_fraction"]]

    def per_root(self, df):
        s = self.segments(df)
        rows = []
        for (organ_id, order), g in s.groupby(["organ_id", "order"]):
            first = g.sort_values("segment_rank").iloc[0]
            last = g.sort_values("segment_rank").iloc[-1]
            # An invalid/missing segment can leave a discontinuous organ.
            ranks = np.sort(g["segment_rank"].to_numpy(int))
            if ranks[0] != 1 or not np.all(np.diff(ranks) == 1):
                continue
            v = last[["x", "y", "z"]].to_numpy(float) - first[["parent_x", "parent_y", "parent_z"]].to_numpy(float)
            norm = np.linalg.norm(v)
            if norm <= _EPS:
                continue
            v /= norm
            rows.append({"organ_id": organ_id, "order": order,
                         "inclination_deg": float(np.degrees(np.arccos(np.clip(-v[2], -1, 1)))),
                         "azimuth_deg": float((np.degrees(np.arctan2(v[1], v[0])) + 360) % 360),
                         "vertical_downward_fraction": float(-v[2]),
                         "net_displacement_cm": float(norm)})
        return pd.DataFrame(rows, columns=["organ_id", "order", "inclination_deg", "azimuth_deg",
                                           "vertical_downward_fraction", "net_displacement_cm"])

    def calculate(self, df):
        return self.calculate_df(df).inclination_deg.to_numpy(float)

    def get_xy_comparison_data(self, df, n_elements=10):
        return self.calculate(df)[:n_elements]

    def visualise(self, df, **_):
        s = self.calculate_df(df)
        return px.histogram(s, x="inclination_deg", y="segment_length_cm", histfunc="sum",
                            title="Root length by segment inclination")


class RootingExtent(SummaryStatisticBase):
    """Maximum vertical depth, maximum radius and x/y spreads (cm)."""
    def __init__(self, origin: tuple[float, float, float] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Rooting extent", "cm"
        self.origin = origin

    def calculate_df(self, df):
        s = self.segments(df)
        if s.empty:
            return pd.DataFrame([dict(max_depth_cm=0., max_radius_cm=0., x_spread_cm=0.,
                                      y_spread_cm=0., bounding_circle_diameter_cm=0.)])
        coords = np.vstack([s[["x", "y", "z"]].to_numpy(float),
                            s[["parent_x", "parent_y", "parent_z"]].to_numpy(float)])
        origin = _origin(df, self.origin)
        depth = np.maximum(origin[2] - coords[:, 2], 0)
        radial = np.linalg.norm(coords[:, :2] - origin[:2], axis=1)
        return pd.DataFrame([{
            "max_depth_cm": float(depth.max()), "max_radius_cm": float(radial.max()),
            "x_spread_cm": float(np.ptp(coords[:, 0])), "y_spread_cm": float(np.ptp(coords[:, 1])),
            # Diameter of a circle centred on the origin containing the RSA;
            # not the maximum distance between any pair of roots.
            "bounding_circle_diameter_cm": float(2 * radial.max()),
        }])

    def calculate(self, df):
        return self.calculate_df(df).iloc[0].to_numpy(float)

    def get_xy_comparison_data(self, df, n_elements=10):
        return self.calculate(df)[:n_elements]

    def visualise(self, df, **_):
        vals = self.calculate_df(df).iloc[0]
        return px.bar(x=vals.index.tolist(), y=vals.to_numpy(float), title=self.statistic)


class DepthDistribution(SummaryStatisticBase):
    """Cumulative *root length* fraction versus depth below planting origin."""
    def __init__(self, origin=None, bins=10, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Cumulative root length by depth", "fraction"
        self.origin = origin
        self.bins = bins

    def calculate_df(self, df, bins=None):
        s = self.segments(df)
        o = _origin(df, self.origin)
        maximum = max(0., float(o[2] - s[["z", "parent_z"]].min().min())) if len(s) else 0.
        edges = _bin_edges(self.bins if bins is None else bins, maximum)
        lengths = _length_distribution(s, edges, "depth", o)
        return _distribution_table(edges, lengths, "depth")

    def calculate(self, df, bins=None):
        result = self.calculate_df(df, bins)
        return np.r_[0., result.cumulative_root_length_fraction.to_numpy()], np.r_[
            result.depth_min_cm.iloc[0], result.depth_max_cm.to_numpy()
        ]

    def get_xy_comparison_data(self, df, n_elements=10):
        return self.calculate(df, bins=n_elements)[0][1:]

    def visualise(self, df, bins=None):
        cdf, edges = self.calculate(df, bins)
        fig = px.line(x=cdf, y=edges, markers=True, title=self.statistic)
        fig.update_layout(xaxis_title="Cumulative root length fraction", yaxis_title="Depth (cm)")
        fig.update_yaxes(autorange="reversed")
        return fig


class RadialDistribution(SummaryStatisticBase):
    """Cumulative *root length* fraction versus actual horizontal radius."""
    def __init__(self, origin=None, bins=10, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Cumulative root length by radius", "fraction"
        self.origin = origin
        self.bins = bins

    def calculate_df(self, df, bins=None):
        s = self.segments(df)
        o = _origin(df, self.origin)
        coords = np.vstack([s[["x", "y"]].to_numpy(float),
                            s[["parent_x", "parent_y"]].to_numpy(float)]) if len(s) else np.empty((0, 2))
        maximum = float(np.linalg.norm(coords - o[:2], axis=1).max()) if len(coords) else 0.
        edges = _bin_edges(self.bins if bins is None else bins, maximum)
        lengths = _length_distribution(s, edges, "radius", o)
        return _distribution_table(edges, lengths, "radius")

    def calculate(self, df, bins=None):
        result = self.calculate_df(df, bins)
        return np.r_[0., result.cumulative_root_length_fraction.to_numpy()], np.r_[
            result.radius_min_cm.iloc[0], result.radius_max_cm.to_numpy()
        ]

    def get_xy_comparison_data(self, df, n_elements=10):
        return self.calculate(df, bins=n_elements)[0][1:]

    def visualise(self, df, bins=None):
        cdf, edges = self.calculate(df, bins)
        fig = px.line(x=cdf, y=edges, markers=True, title=self.statistic)
        fig.update_layout(xaxis_title="Cumulative root length fraction", yaxis_title="Radius (cm)")
        return fig


class VerticalRootLengthDistribution(DepthDistribution):
    """Root length (cm) allocated to vertical depth slabs."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Root length by depth", "cm"

    def calculate(self, df, bins=None):
        return self.calculate_df(df, bins).root_length_cm.to_numpy(float)

    def get_xy_comparison_data(self, df, n_elements=10):
        return self.calculate(df, bins=n_elements)

    def visualise(self, df, bins=None):
        data = self.calculate_df(df, bins)
        fig = px.bar(data, x="root_length_cm", y="depth_min_cm", orientation="h", title=self.statistic)
        fig.update_yaxes(autorange="reversed")
        return fig


class HorizontalRootLengthDistribution(RadialDistribution):
    """Root length (cm) allocated to concentric horizontal radial rings."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Root length by horizontal radius", "cm"

    def calculate(self, df, bins=None):
        return self.calculate_df(df, bins).root_length_cm.to_numpy(float)

    def get_xy_comparison_data(self, df, n_elements=10):
        return self.calculate(df, bins=n_elements)

    def visualise(self, df, bins=None):
        return px.bar(self.calculate_df(df, bins), x="radius_min_cm", y="root_length_cm", title=self.statistic)


class RootLengthDensity(SummaryStatisticBase):
    """Root length density within a 3D soil-voxel grid.

    Exact intersection of straight graph segments with every voxel crossed;
    only lengths inside the supplied grid are included.
    """
    def __init__(self, soil_df: pd.DataFrame, length_source="geometric", root_types=None, **kwargs):
        super().__init__(length_source=length_source, **kwargs)
        self.statistic, self.unit = "Root length density", "cm/cm³"
        self.root_types = root_types
        self.edges = [np.sort(soil_df[axis].unique().astype(float)) for axis in ("x", "y", "z")]
        if any(len(e) < 2 or not np.isfinite(e).all() or not (np.diff(e) > 0).all()
               for e in self.edges):
            raise ValueError("Invalid soil grid boundaries.")
        self.shape = tuple(len(e) - 1 for e in self.edges)
        self.soil_volume = float(np.prod([e[-1] - e[0] for e in self.edges]))

    def _voxel_lengths(self, df):
        segs = _segments(df, self.length_source, self.root_types)
        result = np.zeros(self.shape, dtype=float)
        for row in segs.itertuples(index=False):
            a = np.array([row.parent_x, row.parent_y, row.parent_z], dtype=float)
            d = np.array([row.dx, row.dy, row.dz], dtype=float)
            lo, hi = 0., 1.
            for j, edge in enumerate(self.edges):
                if abs(d[j]) <= _EPS:
                    if a[j] < edge[0] or a[j] > edge[-1]:
                        hi = -1.
                        break
                else:
                    intersection = (edge[[0, -1]] - a[j]) / d[j]
                    lo = max(lo, float(np.min(intersection)))
                    hi = min(hi, float(np.max(intersection)))
            if hi - lo <= _EPS:
                continue
            cuts = [lo, hi]
            for j, edge in enumerate(self.edges):
                if abs(d[j]) > _EPS:
                    t = (edge[1:-1] - a[j]) / d[j]
                    cuts.extend(t[(t > lo + _EPS) & (t < hi - _EPS)].tolist())
            cuts = np.sort(cuts)
            for start, end in zip(cuts[:-1], cuts[1:]):
                if end - start <= _EPS:
                    continue
                midpoint = a + d * ((start + end) / 2)
                index = tuple(int(np.clip(np.searchsorted(edge, midpoint[j], side="right") - 1,
                                          0, len(edge) - 2)) for j, edge in enumerate(self.edges))
                result[index] += (end - start) * row.segment_length_cm
        return result

    def calculate(self, df):
        return float(self._voxel_lengths(df).sum() / self.soil_volume)

    def calculate_per_voxel(self, df):
        length = self._voxel_lengths(df)
        ix, iy, iz = np.indices(self.shape).reshape(3, -1)
        x, y, z = self.edges
        volume = np.diff(x)[ix] * np.diff(y)[iy] * np.diff(z)[iz]
        return pd.DataFrame({
            "column": ix, "row": iy, "layer": iz,
            "x_min": x[ix], "x_max": x[ix + 1],
            "y_min": y[iy], "y_max": y[iy + 1],
            "z_min": z[iz], "z_max": z[iz + 1],
            "root_length_cm": length.ravel(), "soil_volume_cm3": volume,
            "rld_cm_cm3": length.ravel() / volume,
        })

    @staticmethod
    def aggregate(voxels, by):
        groups = {"row": ["row", "y_min", "y_max"],
                  "column": ["column", "x_min", "x_max"],
                  "layer": ["layer", "z_min", "z_max"]}
        if by not in groups:
            raise ValueError("by must be 'row', 'column', or 'layer'.")
        result = voxels.groupby(groups[by], as_index=False)[["root_length_cm", "soil_volume_cm3"]].sum()
        result["rld_cm_cm3"] = result.root_length_cm / result.soil_volume_cm3
        if by == "layer":
            result["depth_top_cm"] = -result.z_max
            result["depth_bottom_cm"] = -result.z_min
            result = result.sort_values("depth_top_cm").reset_index(drop=True)
        return result

    def calculate_per_row(self, df):
        return self.aggregate(self.calculate_per_voxel(df), "row")

    def calculate_per_column(self, df):
        return self.aggregate(self.calculate_per_voxel(df), "column")

    def calculate_per_layer(self, df):
        return self.aggregate(self.calculate_per_voxel(df), "layer")

    def calculate_statistic_per_layer(self, df, layer_decrement=10):
        layers = self.calculate_per_layer(df)
        return layers.rld_cm_cm3.tolist(), layers.z_max.to_numpy()

    def visualise(self, df, **_):
        layers = self.calculate_per_layer(df)
        fig = px.scatter(layers, x="rld_cm_cm3", y="depth_top_cm", title="Root length density by soil layer")
        fig.update_layout(xaxis_title="RLD (cm/cm³)", yaxis_title="Soil depth (cm)")
        fig.update_yaxes(autorange="reversed")
        return fig


class RootDryMassByDiameter(SummaryStatisticBase):
    """Segment dry mass (g) per diameter class (mm)."""
    def __init__(self, diameter_bins_mm: list[float], root_tissue_density: float | None = None, **kwargs):
        super().__init__(**kwargs)
        self.statistic, self.unit = "Root dry mass by diameter", "g"
        self.diameter_bins_mm = _bin_edges(diameter_bins_mm, 0.)
        self.root_tissue_density = root_tissue_density

    def calculate(self, df):
        s = self.segments(df)
        mass = _mass(s, self.root_tissue_density)
        return np.histogram(s.diameter.to_numpy(float) * 10,
                            bins=self.diameter_bins_mm, weights=mass)[0]

    def calculate_df(self, df):
        return pd.DataFrame({
            "diameter_min_mm": self.diameter_bins_mm[:-1],
            "diameter_max_mm": self.diameter_bins_mm[1:],
            "dry_mass_g": self.calculate(df),
        })

    def get_xy_comparison_data(self, df, n_elements=10):
        return self.calculate(df)[:n_elements]

    def visualise(self, df, **_):
        data = self.calculate_df(df)
        labels = [f"{a:g}–{b:g}" if np.isfinite(b) else f"≥{a:g}"
                  for a, b in zip(data.diameter_min_mm, data.diameter_max_mm)]
        return px.bar(x=labels, y=data.dry_mass_g, title=self.statistic,
                      labels={"x": "Root diameter (mm)", "y": "Root dry mass (g)"})


def get_summary_statistic_func(summary_statistic: str) -> Callable:
    name = summary_statistic.replace("_", " ").title().replace(" ", "")
    return locate(f"deeprootgen.statistics.summary_statistics.{name}")


def get_summary_statistics() -> list[dict]:
    names = [
        "root_number", "total_volume", "average_volume", "total_length", "average_length",
        "total_diameter", "average_diameter", "root_length_distribution",
        "root_diameter_distribution", "root_branching_order_distribution",
        "root_branching_frequency", "root_branching_angle_distribution",
        "root_orientation_distribution", "rooting_extent", "depth_distribution",
        "radial_distribution", "vertical_root_length_distribution",
        "horizontal_root_length_distribution", "root_length_density",
        "root_dry_mass_by_diameter", "total_specific_root_length",
        "average_specific_root_length", "total_weight", "average_weight",
        "convex_hull_area", "convex_hull_volume",
    ]
    return [{"value": value, "label": value.replace("_", " ").title()} for value in names]
