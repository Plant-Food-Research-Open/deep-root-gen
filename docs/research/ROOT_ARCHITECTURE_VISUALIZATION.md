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

## Interpretation

Diameter-filtered views change visibility, not geometry, RLD or biomass. Keep physical aspect ratios and camera conventions fixed across comparisons. Core markers show sampled observations; they are not measured root paths, and overlay colours must not be presented as model predictions. Retain the caller's source/configuration/frame identities with every local rendering.
