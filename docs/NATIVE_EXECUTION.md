# Running DeepRootGen with one root-system input

Fresh runs use schema version 4 through `RootSystemSimulation.run()`, the CLI and
tracked runs. The JSON contains native parameters, a seed, and the features
selected for that architecture. The engine resolves calculations by root order.
[RootConfig](../deeprootgen/data_model/canonical.py) ·
[Example with first-order origins along a buried trunk](../examples/design/native_crown_0_20cm.json)
· [Exploration and notebook workflow](source/usage/native_workflow.rst)

```bash
python -m deeprootgen simulate --config examples/design/native_crown_0_20cm.json --explain-config
python -m deeprootgen simulate --config examples/design/native_crown_0_20cm.json --outdir /tmp/grapevine-roots
```

The output directory must be new. Open `root_summary.json` for counts and
physical lengths by order, length and dry biomass by diameter class, and
achieved fractions. `execution.json` records allocation results when a target is
supplied. The graph uses cm for lengths and diameters, and g for dry mass.
Use the exported `parameters.json` to repeat a seeded run.
The resolved integer crown split is in `execution.json`. Open
`branching.json` for site proposals, placed sites, accepted daughters and
invalid daughters by parent order. Replacement laws also record the first-site
draw and branch decision for each parent. For native spacing, the proposal count
starts at the sites placed by that calculation. Diameter rejections count
sites, while Bernoulli rejections and first sites at or beyond the tip count
parent decisions.

## Parameters for structural-root simulations

| Setting under `parameters` | Meaning |
|---|---|
| `max_order` | Integer ceiling. Crown roots have order 1 and each daughter has its parent's order plus one. |
| `primary_root_count`, `outer_primary_fraction` | Number of first-order organs and optional fraction assigned to outer placement. The outer count rounds half up. The other roots form the inner group. |
| `daughters_per_parent` | A fixed integer or an integer range with `min` and `max_exclusive`. Optional `daughters_by_parent_order` overrides the request on named parent orders. |
| `apex_diameter` | Endpoint of the native cylinder-diameter sampling interval in cm. The point taper feature supplies a separate physical tip diameter. |
| `min_branching_diameter_cm` | Defaults to **0.093 cm (0.93 mm)**. Each proposed daughter needs a final attachment site at least this thick. Zero disables the diameter check. Existing thin roots still contribute length and dry mass. |
| `threshold_root_diameter_cm` | Defaults to **0.25 cm (2.5 mm)**. Summaries and allocation targets use two classes, diameter at or below this cutoff and diameter above it. |
| `root_ratio_length`, `root_ratio_biomass` | Optional targets for the fractions of total valid root length and root dry biomass in the lower diameter class. Both use fractions from 0 to 1. |
| `allocation_controls` | Positive ranges for length and diameter scale factors by numeric root order. The solver adjusts the permitted dimensions and checks the achieved fractions on the generated geometry. |
| `root_tissue_density` | Dry mass per material volume in g/cm³. Crown support and invalid roots are excluded from the root summary. |
| `features.primary_origins` (top-level feature) | For a buried trunk, disk radius 0 and depth range [0, 20] cm place first-order origins along the trunk below the specified soil surface. |

Fichtl et al. use **0.93 mm** as their minimum structural-root diameter. Here
the user selected it as the local parent diameter needed for a new daughter.
This rule represents branching in the structural-root architecture. Tissue age
and lignification require developmental information. A 1.2 mm attachment can
therefore produce a daughter and still count toward the lower 2.5 mm reporting
class. [Fichtl et al. (2026)](https://doi.org/10.1111/nph.71727) ·
[Gambetta et al. (2013)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3813648/)

## Selecting optional features

Native cylinder and length kernels supply ordinary dimensions. Use numeric
lengths under `features.lengths.settings.by_order` for fixed whole-axis lengths.
A point taper accepts fixed base/tip diameters and bounded positive draws,
including a truncated normal for the first-order base. Means and SDs describe
the distribution before truncation. Enable `cohort_maturity` only to give
descendants a shared primary-tree factor affecting size or branch probability.
Routing and publication use the same native axis state for these choices.

For `features.branching.settings.by_order`, the bounded lognormal sets the
first-site distance in cm, measured along the parent. Its mean and SD describe
the underlying distribution. The branch probability applies per parent. When
the draw succeeds and the first site lies before the tip, the conditional
count probabilities control the family size. The remaining sites are uniform
between the first site and the tip. The final diameter gate applies after any
relocation. An entry supplied for the terminal order is retained as inactive
input and creates no branch draws.

For a measured thick-root taper, set the order's taper `law` to
`exponential_above_diameter`. Set `rate_per_cm` to the nonnegative decay rate
and `thick_min_cm` to the lower measurement limit. The diameter follows
`d(s) = d₀ exp(−ks)` on arclength through the thick part. When the axis reaches the
lower limit, the remaining thin taper joins that diameter and uses the configured
tip and midpoint fraction. Axes whose sampled bases are already below the limit
use the original point taper. The branch gate reads the local point diameter.
The graph stores an equivalent diameter that preserves integrated volume.

With point taper on every order, `features.parent_diameter_cap` limits each
daughter's basal diameter to a fraction of the parent diameter at the final
attachment. Enabling distal relocation therefore evaluates both branching
eligibility and the daughter cap farther along the primary taper.

Curved laterals with `initial_heading: "insertion_angle"` can also use
`features.insertion.settings.row_axial_kappa_by_order`. A positive concentration
biases insertion azimuth around the simulator's row axis (+y), preserving
the sampled polar angle relative to the parent. Zero leaves the angle draw intact.

In `fichtl2024` mode, Fichtl angle and trial settings apply only to orders using
the Fichtl direction kernel or Fichtl construction-step directions.
`features.direction.settings.higher_order_tropism` supplies the controls for
the active Fichtl orders 4 and 5. Curvature-owned orders use their own parameters.
When every active Fichtl order supplies `sigma_by_order`, the global
`fichtl_sigma` can be omitted. Fichtl-mode primary and post-direction validation
remain selected by the validation controls.

Schema 4 can also hold an indexed crown in
`features.primary_origins.settings` with `layout: vine_catalogue` and a persistent
along-row heading adjustment in
`features.curvature.settings.by_order.<order>.row_alignment_per_cm`.
The catalogue sets each primary's position and, where supplied, heading.
The curvature adjustment aligns the horizontal heading with the row axis
during growth. The [synthetic five-order example](../examples/design/spatial_construction_synthetic.json)
combines both controls with length-dependent branching and can be loaded in
the Simulation page. The CLI writes `vine_origin_catalogue.json` and
`row_alignment.json` when those controls are active.

For an example with two adjustable dimensions, run the [paired allocation
input](../examples/design/native_allocation_targets.json). It requests 50% of
length and 10% of dry biomass below or at 2.5 mm. A scalar fixes an axis
dimension. Use `{"nominal_cm": 3.0}` for a value the solver may adjust inside
the order's scale range. The accepted realization must reach each supplied
fraction within 0.01. A proven conflict and an exhausted search have different
outcomes in the allocation receipt.

The separate reporting and branching parameters allow a finer reporting cutoff
without regenerating a different topology when allocation targets are absent.
When a target is active, a changed reporting cutoff can change the architecture
required to reach it. The result reports the actual achieved fractions.
[Input plan and scientific definitions](research/SINGLE_INPUT_AND_PARAMETER_SIMPLIFICATION_PLAN.md)

## Migrating an existing input

The [offline conversion function](../deeprootgen/data_model/migration.py) returns
a new document. Preserve historical source files and review the converted
settings before use. Converted comparison inputs can carry their original
reporting threshold and an explicit zero branch minimum to reproduce the
intended baseline. Newly authored structural simulations use the defaults above.
The [historical contracts](NATIVE_EXECUTION_V1_V3.md) document the original
adapters and sealed reference results.

```bash
python scripts/migration/convert_input.py previous.json converted.schema4.json
python -m deeprootgen simulate --config converted.schema4.json --explain-config
```

### Random placement of related lateral roots

For a curvature order with an insertion angle, set `sibling_sectors` to a window length in cm and the fraction of eligible sibling groups to stratify, for example `{"window_cm": 12, "fraction": 0.5}`. Each selected group receives a random angular offset and each daughter draws within its assigned sector. The insertion-angle distribution remains the one supplied for the order. A fraction of zero keeps the independent bearings.

With the first-site and daughter-count branching law, `stratify_distal_sites: true` draws one distal attachment per equal arclength interval beyond the first site. A separate research tool, `scripts/research/realize_terminal_recruitment.py`, can retain fifth-order axes probabilistically as a function of their insertion depth. The complete vine can be sampled at any set of soil locations.

### Growing a neighbourhood of vines

Use the offline Python generator to compare translated copies of a focal vine
with vines grown from independent seeds. Supply crown offsets in centimetres
in the model's x/y frame, including the focal position (0, 0) exactly once.
Here the distances and configuration are synthetic.

```python
import json
from pathlib import Path
from deeprootgen.research.neighbourhood import generate_neighbourhood

config = json.loads(Path("examples/synthetic_minimal.json").read_text())
origins = [(x, y) for x in (-180, 0, 180) for y in (-140, 0, 140)]
translated = generate_neighbourhood(config, origins)
independent = generate_neighbourhood(config, origins, mode="independent")
```

The translated mode grows the focal vine once. Independent mode uses the same
focal realization and grows a new vine for each other position under the same
parameters. Generation precedes translation. Each result has node and edge
tables with globally unique node IDs, plus a plant table with offsets, seeds
and single-vine run identities. Identify the focal plant by its zero offsets.
The single-vine generation API continues to produce one vine. The neighbourhood
wrapper represents overlapping root systems grown without plant competition.

For a comparison, keep origins, rotations, physical core volumes and diameter
filters identical. Measure root length density (RLD) by summing intercepted
length across plants and dividing once by the volume of each core. Keep the
focal contribution as a separate output. The finite-cylinder observation API
accepts root-only node and edge tables and can report a row per plant. Where
the growth configuration includes crown support or a tapered-axis observation
model, retain the matching root projection and observer for both arms.
See the [finite-core method](research/FINITE_CORE_RESEARCH.md).

Review how often a section is empty, how much RLD a positive section contains,
and how often every section in a whole core is empty. A shift in mean RLD on
a small panel can reflect the vines drawn for the neighbours. A balanced
check can isolate spatial overlap: within a set of nine generated vines, let
each vine occupy each of the nine positions exactly once across nine different
layouts, then compare with the nine all-copy layouts. The pooled mean is equal
by construction, while occupancy and the amount conditional on a hit can vary.
Treat all layouts reusing the same nine vines as one block for uncertainty.

The offline CLI also accepts the layout as a JSON array of coordinate pairs:

```bash
python -m deeprootgen neighbourhood --config examples/synthetic_minimal.json \
  --origins offsets_cm.json --mode independent --outdir independent-vines
```

The new directory contains the node and edge tables, the plant seed map, both
input documents and a manifest. Omit `--mode` for the translated comparison.
See the [placement experiment options](research/PLACEMENT_EXPERIMENT_OPTIONS.md)
for review questions and tests that separate placement from total root length.

[Configure irrigation depth, daughter recruitment and vineyard spacing](research/IRRIGATION_INPUTS.md)
