"""Turn local Grapevine3D RSML root polylines into soil-cube root lengths.

This standalone script does not import the DeepRootGen runtime or contact any
service. Coordinates and lengths are in centimetres, as declared by RSML.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


ROOT_CLASSES = ("primary", "secondary", "tertiary", "quaternary", "quinary", "other")
Point = tuple[float, float, float]
Cell = tuple[int, int, int]


@dataclass(frozen=True)
class Segment:
    start: Point
    end: Point
    root_class: str


@dataclass(frozen=True)
class Vine:
    timepoint: str
    vine_id: str
    rootstock: str
    source: Path
    surface_rsml_cm: Point
    segments: tuple[Segment, ...]


def _point(element: ElementTree.Element) -> Point:
    values = tuple(float(element.attrib[axis]) for axis in "xyz")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Non-finite RSML coordinate")
    return values  # type: ignore[return-value]


def read_vine(path: Path) -> Vine:
    """Read root geometry only; stem points establish the soil-surface origin."""
    document = ElementTree.parse(path).getroot()
    unit = document.findtext("./metadata/unit")
    if unit != "cm":
        raise ValueError(f"{path}: expected RSML unit 'cm', found {unit!r}")
    plants = document.findall("./scene/plant")
    if len(plants) != 1:
        raise ValueError(f"{path}: expected one plant, found {len(plants)}")
    plant = plants[0]
    stem = plant.find("./root")
    if stem is None or stem.get("label") != "stem":
        raise ValueError(f"{path}: missing labelled stem root")
    stem_points = stem.findall("./geometry/polyline/point")
    if len(stem_points) < 2:
        raise ValueError(f"{path}: stem lacks a soil-surface point")
    surface = _point(stem_points[1])
    segments: list[Segment] = []
    for root in stem.iter("root"):
        if root is stem:
            continue
        label = root.get("label", "other").lower()
        root_class = label if label in ROOT_CLASSES else "other"
        points = [_point(point) for point in root.findall("./geometry/polyline/point")]
        for first, second in zip(points, points[1:]):
            start = tuple(first[i] - surface[i] for i in range(3))
            end = tuple(second[i] - surface[i] for i in range(3))
            segments.append(Segment(start, end, root_class))
    if not segments:
        raise ValueError(f"{path}: no root line segments")
    return Vine(path.parent.name, path.stem, plant.get("label", ""), path, surface, tuple(segments))


def _length(start: Point, end: Point) -> float:
    return math.dist(start, end)


def clip_to_soil(segment: Segment) -> tuple[Segment | None, float]:
    """Clip to depth >= 0; return kept segment and length above the surface."""
    start, end = segment.start, segment.end
    original = _length(start, end)
    if start[2] < 0 and end[2] < 0:
        return None, original
    if start[2] >= 0 and end[2] >= 0:
        return segment, 0.0
    fraction = -start[2] / (end[2] - start[2])
    crossing = tuple(start[i] + fraction * (end[i] - start[i]) for i in range(3))
    crossing = (crossing[0], crossing[1], 0.0)
    kept = Segment(crossing, end, segment.root_class) if start[2] < 0 else Segment(start, crossing, segment.root_class)
    return kept, original - _length(kept.start, kept.end)


def split_segment_into_cells(segment: Segment, size_cm: float) -> list[tuple[Cell, float]]:
    """Split at all cube faces; assign each piece using its midpoint."""
    start, end = segment.start, segment.end
    total = _length(start, end)
    if total == 0:
        return []
    cuts = [0.0, 1.0]
    for axis in range(3):
        low, high = sorted((start[axis], end[axis]))
        if high == low:
            continue
        first_face = math.floor(low / size_cm) + 1
        last_face = math.ceil(high / size_cm) - 1
        for face in range(first_face, last_face + 1):
            fraction = (face * size_cm - start[axis]) / (end[axis] - start[axis])
            if 0 < fraction < 1:
                cuts.append(fraction)
    cuts.sort()
    pieces: list[tuple[Cell, float]] = []
    for left, right in zip(cuts, cuts[1:]):
        if right - left <= 1e-12:
            continue
        midpoint = (left + right) / 2
        cell = tuple(math.floor((start[axis] + midpoint * (end[axis] - start[axis])) / size_cm) for axis in range(3))
        pieces.append((cell, total * (right - left)))
    return pieces


def grid_vine(vine: Vine, size_cm: float) -> tuple[dict[Cell, dict[str, float]], dict[str, float | int]]:
    cells: dict[Cell, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    original_lengths: list[float] = []
    retained_lengths: list[float] = []
    excluded_lengths: list[float] = []
    clipped_count = 0
    for segment in vine.segments:
        original_lengths.append(_length(segment.start, segment.end))
        kept, excluded = clip_to_soil(segment)
        excluded_lengths.append(excluded)
        if excluded > 0:
            clipped_count += 1
        if kept is None:
            continue
        retained_lengths.append(_length(kept.start, kept.end))
        for cell, length in split_segment_into_cells(kept, size_cm):
            if cell[2] < 0:
                raise ValueError(f"{vine.source}: below-surface segment assigned above soil")
            cells[cell][kept.root_class] += length
    original_total = math.fsum(original_lengths)
    retained_total = math.fsum(retained_lengths)
    excluded_total = math.fsum(excluded_lengths)
    grid_total = math.fsum(math.fsum(classes.values()) for classes in cells.values())
    tolerance = 1e-8 * max(1.0, retained_total)
    if abs(retained_total - grid_total) > tolerance or abs(original_total - retained_total - excluded_total) > tolerance:
        raise ValueError(f"{vine.source}: root length was not conserved by clipping and gridding")
    if not cells:
        raise ValueError(f"{vine.source}: no root segments below the soil surface")
    summary: dict[str, float | int] = {
        "segment_count": len(vine.segments),
        "clipped_or_excluded_segment_count": clipped_count,
        "original_length_cm": original_total,
        "above_surface_length_cm": excluded_total,
        "soil_length_cm": retained_total,
        "grid_length_cm": grid_total,
        "occupied_cell_count": len(cells),
    }
    return cells, summary


def _selected_files(data_dir: Path, timepoint: str | None, vine_id: str | None) -> list[Path]:
    source_dir = data_dir / "RSML_Files"
    if not source_dir.is_dir():
        raise ValueError(f"Missing RSML_Files directory: {source_dir}")
    files = sorted(source_dir.glob("T*/*.rsml"))
    if timepoint:
        files = [path for path in files if path.parent.name == timepoint]
    if vine_id:
        files = [path for path in files if path.stem == vine_id]
    if not files:
        raise ValueError("No RSML files matched the requested vine/timepoint")
    return files


def _draw_architecture(vine: Vine, cells: dict[Cell, dict[str, float]], size_cm: float, path: Path) -> None:
    """Make a local 3D root view plus a depth-integrated top-view heatmap."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import LogNorm
    from mpl_toolkits.mplot3d.art3d import Line3DCollection

    colors = {
        "primary": "#3b2b20", "secondary": "#a35323", "tertiary": "#d59640",
        "quaternary": "#e8b95e", "quinary": "#f4d782", "other": "#888888",
    }
    fig = plt.figure(figsize=(14, 7), constrained_layout=True)
    ax = fig.add_subplot(121, projection="3d")
    shown: list[Point] = []
    for label in ROOT_CLASSES:
        lines = []
        for segment in vine.segments:
            if segment.root_class != label:
                continue
            kept, _ = clip_to_soil(segment)
            if kept is None or _length(kept.start, kept.end) == 0:
                continue
            lines.append([kept.start, kept.end])
            shown.extend((kept.start, kept.end))
        if lines:
            ax.add_collection3d(Line3DCollection(lines, colors=colors[label], linewidths=1.25 if label == "primary" else 0.7, label=label))
    xs, ys, zs = ([point[i] for point in shown] for i in range(3))
    ax.set_xlim(min(xs), max(xs))
    ax.set_ylim(min(ys), max(ys))
    ax.set_zlim(max(zs), 0)
    ax.set_box_aspect((max(xs) - min(xs), max(ys) - min(ys), max(zs)))
    ax.set_xlabel("Inter-row x (cm)")
    ax.set_ylabel("Along-row y (cm)")
    ax.set_zlabel("Depth below soil (cm)")
    ax.view_init(elev=22, azim=-55)
    ax.set_title("Digitized root segments")
    ax.legend(loc="upper left", fontsize=8)

    ix = [cell[0] for cell in cells]
    iy = [cell[1] for cell in cells]
    image = np.zeros((max(iy) - min(iy) + 1, max(ix) - min(ix) + 1))
    for cell, classes in cells.items():
        image[cell[1] - min(iy), cell[0] - min(ix)] += math.fsum(classes.values())
    ax2 = fig.add_subplot(122)
    positive = image[image > 0]
    masked = np.ma.masked_less_equal(image, 0)
    extent = (min(ix) * size_cm, (max(ix) + 1) * size_cm, min(iy) * size_cm, (max(iy) + 1) * size_cm)
    display = ax2.imshow(masked, origin="lower", extent=extent, cmap="YlOrBr", norm=LogNorm(vmin=max(float(positive.min()), 1e-3), vmax=float(positive.max())))
    ax2.plot(0, 0, "k+", markersize=10, markeredgewidth=2)
    ax2.set_xlabel("Inter-row x (cm)")
    ax2.set_ylabel("Along-row y (cm)")
    ax2.set_title("Root length summed over depth")
    fig.colorbar(display, ax=ax2, label="Digitized root length per 10 × 10 cm column (cm)")
    fig.suptitle(f"Grapevine3D {vine.timepoint}/{vine.vine_id} — {vine.rootstock}")
    fig.savefig(path, dpi=170)
    plt.close(fig)


def analyse(data_dir: Path, output_dir: Path, size_cm: float = 10.0, timepoint: str | None = None, vine_id: str | None = None, plot_vine: str | None = None) -> dict:
    if not math.isfinite(size_cm) or size_cm <= 0:
        raise ValueError("Grid size must be a positive finite number")
    files = _selected_files(data_dir, timepoint, vine_id)
    if data_dir.resolve() == output_dir.resolve() or data_dir.resolve() in output_dir.resolve().parents:
        raise ValueError("Write derivatives outside the raw DATA directory")
    if plot_vine and plot_vine not in {f"{path.parent.name}/{path.stem}" for path in files}:
        raise ValueError(f"Plot vine {plot_vine!r} was not selected")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    volume_cm3 = size_cm ** 3
    summary_rows = []
    source_files = []
    voxel_path = output_dir / "voxel_grid.csv"
    with voxel_path.open("w", newline="") as handle:
        fields = ["timepoint", "vine_id", "rootstock", "ix", "iy", "iz", "x_min_cm", "y_min_cm", "depth_min_cm", "root_length_cm", "rld_cm_per_cm3"] + [f"{label}_length_cm" for label in ROOT_CLASSES]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for source in files:
            vine = read_vine(source)
            cells, summary = grid_vine(vine, size_cm)
            x_indices = [cell[0] for cell in cells]
            y_indices = [cell[1] for cell in cells]
            z_indices = [cell[2] for cell in cells]
            bounds = (min(min(x_indices), 0), max(max(x_indices), 0), min(min(y_indices), 0), max(max(y_indices), 0), 0, max(z_indices))
            ix_min, ix_max, iy_min, iy_max, iz_min, iz_max = bounds
            for iz in range(iz_min, iz_max + 1):
                for iy in range(iy_min, iy_max + 1):
                    for ix in range(ix_min, ix_max + 1):
                        classes = cells.get((ix, iy, iz), {})
                        length = math.fsum(classes.values())
                        row = {
                            "timepoint": vine.timepoint, "vine_id": vine.vine_id, "rootstock": vine.rootstock,
                            "ix": ix, "iy": iy, "iz": iz,
                            "x_min_cm": ix * size_cm, "y_min_cm": iy * size_cm, "depth_min_cm": iz * size_cm,
                            "root_length_cm": length, "rld_cm_per_cm3": length / volume_cm3,
                        }
                        row.update({f"{label}_length_cm": classes.get(label, 0.0) for label in ROOT_CLASSES})
                        writer.writerow(row)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            source_files.append({"path": str(source), "sha256": digest})
            summary_rows.append({
                "timepoint": vine.timepoint, "vine_id": vine.vine_id, "rootstock": vine.rootstock,
                "source_sha256": digest,
                "surface_x_rsml_cm": vine.surface_rsml_cm[0],
                "surface_y_rsml_cm": vine.surface_rsml_cm[1],
                "surface_z_rsml_cm": vine.surface_rsml_cm[2],
                **summary,
                "grid_cell_count": (ix_max - ix_min + 1) * (iy_max - iy_min + 1) * (iz_max - iz_min + 1),
                "ix_min": ix_min, "ix_max": ix_max, "iy_min": iy_min, "iy_max": iy_max, "iz_min": iz_min, "iz_max": iz_max,
            })
            if plot_vine == f"{vine.timepoint}/{vine.vine_id}":
                _draw_architecture(vine, cells, size_cm, output_dir / f"architecture_{vine.timepoint}_{vine.vine_id}.png")
    with (output_dir / "vine_summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)
    metadata = {
        "source_dataset": "Grapevine3D, doi:10.5281/zenodo.15632062",
        "source_files": source_files,
        "grid_size_cm": size_cm,
        "grid_volume_cm3": volume_cm3,
        "coordinate_transform": "RSML x/y/z minus stem polyline point 2; z is positive depth below soil surface; x inter-row, y along-row",
        "grid_rule": "Each segment is split exactly at intersected grid faces; each piece is assigned to the cube containing its midpoint. Cubes are half-open and aligned to zero.",
        "coverage": "Full cuboid from the minimum to maximum occupied x/y index, including the vine at x=y=0, and depth index 0 through deepest occupied cube. Zero means no digitized root segment in that cube; it is not a field-measured zero.",
        "root_selection": "All RSML root polylines except the stem; only consecutive points within each root polyline are connected. Above-surface portions are excluded.",
        "biomass": "Not calculated: RSML does not supply root diameter or root tissue density for segment-level mass conversion.",
        "length_conservation_tolerance": "1e-8 times max(1 cm, retained soil length)",
        "vine_count": len(summary_rows),
        "grid_cell_count": sum(int(row["grid_cell_count"]) for row in summary_rows),
    }
    (output_dir / "analysis_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True, help="Local Grapevine3D DATA directory")
    parser.add_argument("--output-dir", type=Path, required=True, help="New or empty local derivative directory")
    parser.add_argument("--grid-size-cm", type=float, default=10.0)
    parser.add_argument("--timepoint", choices=("T1", "T2", "T3", "T4"))
    parser.add_argument("--vine-id", help="One vine, e.g. B-23")
    parser.add_argument("--plot-vine", help="Make one PNG, e.g. T4/B-11; requires matplotlib")
    args = parser.parse_args()
    metadata = analyse(args.data_dir, args.output_dir, args.grid_size_cm, args.timepoint, args.vine_id, args.plot_vine)
    print(f"Processed {metadata['vine_count']} vine(s), {metadata['grid_cell_count']} soil cubes; output: {args.output_dir}")


if __name__ == "__main__":
    main()
