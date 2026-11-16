# Local root architecture comparison views

`scripts/research/root_architecture_viewer.py` builds an offline, self-contained
HTML comparison from two explicit sets of polylines. It uses the installed
Plotly package and does not import the simulator, start a server, run a model or
change geometry. Coordinates are `[across, along, depth]`, with positive depth
down. Use one verified coordinate frame and unit for both panels.

The viewer provides linked cameras, oblique/front/side/top presets, a soil
surface toggle and root-order filters. Both panels use the full union of input
coordinate ranges and the same explicit physical aspect ratio. Filtering roots
does not change those ranges or ratios. Every camera uses orthographic
projection to retain comparable geometry and avoid graphics-context recreation
when switching presets. Root orders 1–5 use consistent colours in both panels.
Line widths indicate order for readability; they do not supply missing diameter
measurements.

Supply literal polylines: the builder never infers connectors, recentres vines,
fits transformations or changes their coordinates. The caller owns the soil
frame, stem/invalid-root inclusion, observation support and any metric text.
Summary rows are displayed verbatim and are not a new comparison operator.
Schema/finite-number validation rejects ambiguous geometry and unknown fields;
display prose and JSON are safely embedded. All assets are inline, and the
page blocks network connections. JavaScript/WebGL must be enabled locally.

The module docstring contains a complete invented payload. To render it:

```python
from pathlib import Path
from scripts.research.root_architecture_viewer import build_comparison_html

build_comparison_html(payload, Path(".runtime/root-comparison.html"))
```

Keep measured coordinates and empirical comparison artifacts under local
`.runtime` directories. Do not put these payloads in public examples, commits,
review packets, Pages or external artifact stores.

The current SO4/T4 D-04 views are local under
`.runtime/research/so4-t4-visualization-20261115-v1/`:

- `architecture_explorer.html`: rotatable linked views and summary metrics.
- `architecture_perspective.png` / `.pdf`: high-resolution fixed oblique view.
- `architecture_opposite.png` / `.pdf`: the same geometry from the opposite side.
- `README.md`: input/source identities, reproduction and interpretation.

These views reuse the declared seed-15011 starter and original RSML polylines.
The starter has similar length/depth but still differs spatially; presentation
quality must not be described as a biological fit. No new simulations are
needed to produce the visualizations.

## Later local presentation bundles

The owner-requested visible presentation directory is
`Root_Architecture_Presentation_2026-11-16/`; its sealed notes supersede the older
seed-15011 preview for presentation selection. New cohort population views are
in `Calvin_Population_2026-11-16/`. Both are local ignored output directories,
not public assets. `.runtime` remains the hidden original workspace (Ctrl+H to
show it). Never imply that Calvin core positions are measured root polylines.


Calvin diameter-filtered local views (16 November 2026): `Calvin_Population_2026-11-16/Diameter_Views/START_HERE.html`. The standalone renderer reconstructs continuous local taper from saved organ base/mid/tip diameters, filters at 0.5/1/2.5 mm, preserves every qualifying path portion and fixes the physical scale. Fine-root strokes are thinner/fainter but remain illustrative; use the included receipt and README for counts, length conservation and browser checks. These are visibility variants of the same experimental vine, not new calibrated architectures.

High-resolution core-overlay plates are available locally at `Calvin_Population_2026-11-16/High_Resolution_Core_Comparison/START_HERE.html`: four 8000×4400 PNGs at400dpi and matching PDFs, using seed63004 and all/≥0.5/≥1/≥2.5mm local-diameter filters. The left panel shows measured fine-RLD core markers; the right repeats those observations over generated roots. Right-panel marker colours are observations, not simulated RLD. Read the adjacent README and render receipt for provenance and exact reproduction.


Latest Calvin curvature/material figures: `Calvin_Curvature_Mass_2026-11-16/START_HERE.html`. Includes matched primary top/side/full-root views, diameter-filtered explorers and8000×4400 core overlays for the central and higher-mass scenarios. Read the report before interpreting similarity: marker colours show measured RLD, neighbour results are a separate clone sensitivity, and fixed fresh-seed constraints did not qualify.
