"""Refine local views from saved SO4 graphs; never runs the generator."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd


def create_views(run_dir):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    source = Path(__file__).with_name("grapevine3d_so4_pilot.py")
    manifest = json.loads((run_dir / "input_manifest.json").read_text())
    if (
        hashlib.sha256(source.read_bytes()).hexdigest()
        != manifest["files"][str(source.resolve())]
    ):
        raise ValueError("Use the exact scoring/view helper from the saved run")
    spec = importlib.util.spec_from_file_location("so4_views_helper", source)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    representative = json.loads((run_dir / "representatives.json").read_text())
    rsml = [Path(p) for p in manifest["files"] if p.endswith(".rsml")]
    observed = {}
    for path in rsml:
        observed[path.stem] = helper.summarize_geometry(helper.measured_records(path))[
            2
        ]
    config = manifest["config"]
    generated = {}
    for name in config["scenarios"]:
        generated[name] = {}
        for seed in config["seeds"]:
            nodes = pd.read_csv(run_dir / "graphs" / name / str(seed) / "nodes.csv")
            records, _ = helper.node_segments(nodes, config["primary_base_depth_cm"])
            generated[name][seed] = helper.summarize_geometry(records)[2]

    profile_rows = []
    labels = {
        "measured": "Measured digitized roots",
        "upstream_example": "Upstream example",
        "paper_proxy": "Paper length/count proxy",
        "branching_capacity": "Branching capacity",
        "fichtl_tropism": "Paper-inspired tropism",
    }
    fig, ax = plt.subplots(figsize=(9, 7), constrained_layout=True)
    for name, systems in {"measured": observed, **generated}.items():
        profiles = []
        for geometry in systems.values():
            values = np.zeros(25)
            for segment in geometry:
                for cell, length in helper.converter.split_segment_into_cells(
                    segment, 10
                ):
                    if 0 <= cell[2] < 25:
                        values[cell[2]] += length
            profiles.append(values)
        average = np.mean(profiles, axis=0)
        profile_colors = {
            "measured": "#333333",
            "upstream_example": "#a3a3a3",
            "paper_proxy": "#d18c25",
            "branching_capacity": "#2577b0",
            "fichtl_tropism": "#19836c",
        }
        ax.plot(
            average,
            np.arange(25) * 10 + 5,
            label=labels[name],
            linewidth=2,
            color=profile_colors[name],
        )
        profile_rows.extend(
            dict(scenario=name, depth_min_cm=i * 10, mean_length_cm=v)
            for i, v in enumerate(average)
        )
    ax.set_ylim(100, 0)
    ax.set(
        xlabel="Mean full-soil root length per 10 cm layer (cm)",
        ylabel="Depth below soil (cm)",
        title="SO4/T2 depth profile: observed vs generated, fixed 20 cm base",
    )
    ax.axhline(20, color="grey", linestyle=":", linewidth=1)
    ax.legend()
    fig.savefig(run_dir / "depth_profile_focus.png", dpi=170)
    plt.close(fig)
    pd.DataFrame(profile_rows).to_csv(run_dir / "depth_profile_means.csv", index=False)

    measured = observed[representative["measured_vine"]]
    candidates = generated["fichtl_tropism"]
    all_points = np.asarray(
        [
            p
            for geometry in [measured, *candidates.values()]
            for seg in geometry
            for p in (seg.start, seg.end)
        ]
    )
    lower, upper = all_points.min(axis=0), all_points.max(axis=0)
    figure = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "scene"}, {"type": "scene"}]],
        subplot_titles=[
            "Measured: median soil-length vine",
            "Generated: paper-inspired tropism",
        ],
        horizontal_spacing=0.04,
    )
    colors = ["#593d29", "#b16a2b", "#dea848", "#e4c58a", "#f0d9a9"]
    class_count = len(helper.CLASSES)
    initial = representative["fichtl_tropism"]
    for panel, seed, geometry in [(1, None, measured)] + [
        (2, seed, geometry) for seed, geometry in candidates.items()
    ]:
        for index, kind in enumerate(helper.CLASSES):
            segments = [s for s in geometry if s.root_class == kind]
            xyz = [
                [v for s in segments for v in (s.start[a], s.end[a], None)]
                for a in range(3)
            ]
            figure.add_trace(
                go.Scatter3d(
                    x=xyz[0],
                    y=xyz[1],
                    z=[-v if v is not None else None for v in xyz[2]],
                    mode="lines",
                    line=dict(width=3, color=colors[index]),
                    name=kind,
                    legendgroup=kind,
                    showlegend=panel == 1,
                    visible=panel == 1 or seed == initial,
                ),
                row=1,
                col=panel,
            )
    for scene in (figure.layout.scene, figure.layout.scene2):
        scene.update(
            xaxis=dict(title="x (cm)", range=[lower[0], upper[0]]),
            yaxis=dict(title="y (cm)", range=[lower[1], upper[1]]),
            zaxis=dict(title="z (cm)", range=[-upper[2], 0]),
            aspectmode="data",
            camera=dict(eye=dict(x=1.6, y=1.6, z=1.1)),
        )
    buttons = []
    for index, seed in enumerate(candidates):
        visible = [True] * class_count + [
            i == index for i in range(len(candidates)) for _ in range(class_count)
        ]
        buttons.append(
            dict(
                label=f"Seed {seed}" + (" (median)" if seed == initial else ""),
                method="update",
                args=[
                    dict(visible=visible),
                    dict(
                        title=f"SO4/T2 | measured vs paper-inspired tropism | seed {seed}"
                    ),
                ],
            )
        )
    figure.update_layout(
        title=f"SO4/T2 | measured vs paper-inspired tropism | seed {initial} (median)",
        height=850,
        width=1600,
        margin=dict(l=30, r=30, t=100, b=130),
        legend=dict(orientation="h", x=0.35, y=-0.04),
        updatemenus=[
            dict(
                buttons=buttons, active=list(candidates).index(initial), x=0.95, y=1.15
            )
        ],
        annotations=list(figure.layout.annotations)
        + [
            dict(
                x=0.5,
                y=-0.16,
                xref="paper",
                yref="paper",
                showarrow=False,
                text="Common physical axes; x across row, y along row, z below soil. Median display is not a best fit. No physiological validation.",
            )
        ],
    )
    figure.write_html(
        run_dir / "roots_3d_measured_vs_tropism.html", include_plotlyjs=True
    )
    output_names = [
        "depth_profile_focus.png",
        "depth_profile_means.csv",
        "roots_3d_measured_vs_tropism.html",
    ]
    helper.save_json(
        run_dir / "view_receipt.json",
        dict(
            generator_calls=0,
            source_sha256=helper.sha(Path(__file__)),
            source_helper_sha256=helper.sha(source),
            outputs={p: helper.sha(run_dir / p) for p in output_names},
        ),
    )
    print(
        "Saved focused depth view and measured/ten-seed interactive comparison; no simulations."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    create_views(args.run_dir.resolve())
