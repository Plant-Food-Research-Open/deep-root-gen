# Running DeepRootGen with one root-system input

Fresh runs use schema version 4 through `RootSystemSimulation.run()`, the CLI and
tracked runs. The JSON contains native parameters, a seed, and the features
selected for that architecture. The engine resolves calculations by root order.
[RootConfig](../deeprootgen/data_model/canonical.py) ·
[Example with first-order origins along a buried trunk](../examples/design/native_crown_0_20cm.json)

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


## Rainfed daughter placement

Schema 4 accepts an optional top-level `daughter_placement`. The attachment
and recruitment modes operate on the seeded terminal-parent order. For these
modes, both parent and daughter use correlated curvature, and
the daughter uses an insertion-angle heading and point taper. The final
parent diameter must meet the configured gate of at least 0.093 cm. This
option is available for rainfed configurations. Use a separate irrigation arm
for an outlet response.

- `{"strength": 0.5}` uses a peak multiplier of 1.25 in the default
  `redistribute` mode, with a full-preference layer at 90–150 cm, a smooth
  rise from 80 cm and taper to 170 cm. The default parent order is four.
  The mode keeps the first realized site, daughter identities, counts and
  length draws. It reapplies the terminal base and tip laws at the new site,
  including the local diameter cap.
- A frozen `profile` supplies an intercept, scaled depth, two depth hinges
  and a nearest-row distance coefficient. The profile also carries the
  training mean, support bounds, fade distance, row spacing and tube support
  by zone. Strength scales the spatial odds or site weight by
  `1.5 ** (strength * preference)`. The generator receives the coefficients
  and support, with fitting performed offline.
- The `branch_probability` mode uses the contour-average multiplier on the
  ordinary first-site law's branch odds. The `retention` mode centres the
  local odds multipliers to preserve an expected 85% retained count per vine.
  At zero strength, redistribution and branching reproduce seeded rainfed
  geometry, while retention draws use the uniform 85% control.
- The fixed-layer `add` and `uniform_extra` modes draw the same extra
  counts per parent on paired seeds and use weighted and uniform eligible
  positions respectively. The local cap can change the realized material.

- Fixed-layer recruitment or relocation can set four `layer_depths_cm`
  boundaries for the start of the rise, plateau start, plateau end and end of
  the fall. `layer_peak_multiplier` specifies the maximum at full strength.
  This optional control can represent a shallow layer in a rainfed study.
  The built-in profile retains its 80–170 cm support and 1.5 peak. When
  a parent barely enters the chosen layer and the ordinary sampler exhausts
  its proposal budget, deep addition continues from its accepted sites on the
  portions of contour with positive recruitment weight. It uses the same
  depth-dependent acceptance law.
- A profile may set `row_depth_slope` to make the cross-row effect change
  with depth, centred at 90 cm. Sparse row-zone support and the depth taper
  attenuate this term in the same way as the additive row effect.
- `branch_probability_uniform` uses the supplied profile to calculate the
  expected number of eligible daughters, then matches that expectation
  with one common odds multiplier for the vine. Both arms reuse the original
  branch-activation and conditional family draws. Realized totals can differ.
- `sparse_depth` activates at most one terminal daughter per parent with
  eligible contour below 90 cm. Its strength is the parent activation
  probability. `sparse_uniform` draws the same realized number of families
  across the full eligible contour. Set the ordinary terminal branch
  probability to zero to isolate either sparse arm.
- `sparse_depth_balanced` takes the same realized number of deep births
  and spreads them among eligible parents using horizontal cells. Specify
  `spatial_cell_width_cm`. The grid gets a random offset for each vine.
  The diagnostic `grid_origin_offset_cm` is measured from the fixed model
  x/y origin. Translating a crown can therefore change cell membership.
  Each occupied cell supplies one candidate before a cell supplies a
  second. Compare with `sparse_depth` on the same parent geometry and seed.

### A continuous vineyard preference from soil cores

An optional `vineyard_3d_v1` profile represents one repeating vineyard cell.
Model x runs across the row, y runs along it, and depth is positive below the
soil surface. The horizontal origin is the vine crown. At each depth knot the
four coefficients weight a constant, the across-row cosine, the along-row
cosine and their product. The field interpolates between depth knots, clips
the preference to [−1, 1], and fades to zero beyond its fitted depth range.
The cosine terms assume symmetry on either side of the row and vine. The
generator subtracts the declared x/y of a translated common-point crown.
For an indexed primary layout, supply survey coordinates relative to the
vine crown, with the crown at (0, 0) in model x/y.

Fit the field offline using training tubes. For example, given a frame
`training` with `core_id`, `depth_cm`, `cross_cm`, `along_cm` and a
signed `target` in [−1, 1], the following attaches the fitted surface to a
seeded, compatible five-order rainfed configuration. A positive target
indicates that the reference underpredicts roots. The distances in this
example are in centimetres.

```python
from deeprootgen.research.core_preference_surface import fit_core_preference_surface

profile = fit_core_preference_surface(
    training, across_period_cm=300, along_period_cm=200, mode="all",
)
config["daughter_placement"] = dict(
    mode="branch_probability", parent_order=4, strength=1.0, profile=profile,
)
```

The native rule multiplies the local odds or attachment weight by
`1.5 ** (strength × preference)`. For a parent at a uniform preference of +1,
branch probability 0.60 becomes about 0.692 at strength 1. For a parent
that crosses several layers, the branching rule averages the multiplier
over eligible contour. Retention evaluates each terminal at its birth and
adjusts a common intercept to preserve the expected retained count.
Redistribution changes movable attachment sites at fixed daughter count.

Before evaluating a held tube, exclude every depth from that tube when
estimating both the residual targets and the profile. Compare `mode="all"`
with the fitter's `mode="depth_only"` and the corresponding unguided growth
control. A lower top-layer weight or capped residual changes the evaluation
cost. Report the original physical score as well, using the same simulated
vines for all costs. [Spatial cost implementation](../deeprootgen/research/core_placement_cost.py)

### Related controls for root direction

Set `daughter_placement.mode` to `surface_bearing`, supply the frozen
vineyard `profile`, set `strength` from 0 to 1, and list the daughter
orders in `bearing_orders` (for example, `[2, 3]`). The rule guides the
initial azimuth of daughters in those orders. Each selected order needs
seeded correlated curvature with an insertion-angle heading. The terminal
parent diameter and branch gates used for recruitment do not apply here.
Active sibling sectors and row-axial insertion each own the bearing on their
configured orders. Select other orders for surface bearing.

The rule compares the native heading with three quarter-turn rotations around
the realized parent tangent. It scores the tip of each straight probe at the
shorter of 40 cm and the daughter's sampled contour length. A probe crossing
the soil surface reflects its vertical step downward from the birth height.
Candidate weights are proportional to `exp(2 × strength × preference)`. The
sampling rule keeps the original bearing whenever possible under these
weights, including every birth on a flat field. It preserves the sampled
polar angle and the curvature noise stream. Each scored curve records its
chosen quarter-turn, probe length, number of reflected probes and preferences.

Under a lateral curvature law, `sibling_sectors.min_birth_depth_cm` filters
eligible births before forming sibling windows. `deep_carrier` specifies
`fraction`, `trigger_depth_cm` and `drift_multiplier`. For selected axes,
the increased drift begins on the next curvature step after the first
downward crossing of the trigger depth. The integration retains the same
curvature noise stream.

`minimum_realized_primary_length_cm` conditions the primary lognormal length
draw on reaching the stated contour length after cohort scaling. It preserves
the nominal upper bound and fails if that cohort has no admissible support.
A new floor is an experimental input. Standard inputs use their existing
length law.


## Transfer ordinary daughter births to deeper parent contour

A seeded schema-4 vine can move selected ordinary daughters before their
directions and descendants are realized. For example, this top-level setting
selects half of eligible shallow births on first-, second- and third-order
parents in expectation.

```json
{
  "birth_depth_transfer": {
    "parent_orders": [1, 2, 3],
    "shallow_depth_cm": 30,
    "deep_depth_cm": 60,
    "transfer_probability": 0.5
  }
}
```

A candidate must be born shallower than 30 cm below the configured soil
surface. Its destination is sampled in proportion to eligible contour length
deeper than 60 cm on the same parent. The local parent diameter must support
the existing daughter. The rule preserves the first accepted daughter under
a count-based first-branch law. A selected bud stays in place if the parent
lacks compatible contour. Existing buds and their descendants keep their
identities and dimensions. Their final geometry and any later recruitment
can respond to the changed origin.

Ordinary branching, a curved parent and an insertion-angle curved daughter
are required on each selected pair of orders. Other attachment rules can
act on distinct orders in the same vine. Combine this rule with sparse deep
recruitment on later parents, or with a fitted spatial preference there.
Per-order receipts in `diagnostics.birth_depth_transfer.by_parent_order`
report the eligible shallow buds, selection draws, successful moves and
shortfalls. For a multi-order treatment, each order's starting depths already
include the effects of upstream moves. Compare a separate transfer-off vine
at the same seed to measure the net change across the whole root system.

## Migrating an existing input

The [offline conversion function](../deeprootgen/data_model/migration.py) returns
a new document. Preserve historical source files and review the converted
settings before use. Converted comparison inputs can carry their original
reporting threshold and an explicit zero branch minimum to reproduce the
intended baseline. Newly authored structural simulations use the defaults above.
The [historical contracts](NATIVE_EXECUTION_V1_V3.md) document the original
adapters and sealed reference results.

## Optional spatial construction

The [invented five-order input](../examples/design/spatial_construction_synthetic.json)
uses all three controls below. Each control can be selected independently.
The [implementation notes](research/SPATIAL_CONSTRUCTION_IMPLEMENTATION.md)
describe units, conflicts and validation.

| Control | Schema-4 setting | Run receipt |
|---|---|---|
| Alignment along either row direction | `features.curvature.settings.by_order.<order>.row_alignment_per_cm` | `row_alignment.json` records the strength, step and length-weighted squared along-row component |
| Branch sites per usable contour length | `features.branching.settings.by_order.<order>.law` set to `length_poisson_sites_v1` | `branching.json` records the zone, activation, proposal and acceptance for each affected parent |
| One coherent vine origin record | `features.primary_origins.settings.layout` set to `vine_catalogue` | `vine_origin_catalogue.json` records the selected record, its source metadata and the active pool identity |

Row alignment acts on the current heading at each physical curvature step.
The row axis is model y, with equal preference for both directions.
The default strength is zero. The product of strength and physical step
must be at most 0.5. Use `insertion.row_axial_kappa_by_order` for an
azimuth preference that applies only at emergence.

For Poisson branch sites, supply `basal_exclusion_cm`,
`apical_exclusion_cm`, `mean_spacing_cm` and `branch_probability`.
An active parent draws a count with mean equal to its usable contour
length divided by spacing. Positions lie between its basal and apical
exclusions. The existing local diameter gate determines eligibility.
The execution limit `limits.max_branch_proposals` defaults to 100,000 for
Poisson runs. It bounds cumulative proposals before position allocation.
An excessive draw fails the run and retains its original count in the error.

A vine catalogue declares `catalogue_version: vine_origins_v1` and
`coordinate_frame: model_soil_cm_v1` and embeds the origin records.
Use `selection.mode: sample` with a seed, or `selection.mode: fixed`
with an `entry_id`. Each record supplies a common point or all indexed
primary origins. A primary layout must agree with `primary_root_count`.
Primary headings, if supplied, use primary curvature with
`initial_heading: origin_heading`. Export/reload preserves the entire
supplied catalogue and reproduces the selected record for a seeded run.

### Random placement of sibling roots

Two optional settings control how daughters share their parent's contour and
the space around it. Neither uses observation coordinates.

* On a **parent** order using `first_branch_and_daughter_count`, set
  `stratify_distal_sites` to `true` to spread births along the contour.
  The law draws the first branch and daughter count as usual. For the remaining
  daughters it divides the contour from the first branch to the tip into equal
  intervals and draws one random position per interval. The diameter gate
  still acts at each proposed site.
* On a **daughter** order using `initial_heading: insertion_angle`, add
  `"sibling_sectors": {"window_cm": 15, "fraction": 1.0}` to its curvature
  settings. Group eligible daughters by parent and by successive windows of
  physical arclength measured from its base. In a selected window containing
  two or more daughters, draw a random rotation and assign each daughter a
  different angular sector at random. Each bearing has additional uniform
  jitter inside its sector. A frame transported along the curved parent keeps
  those bearings comparable at adjacent sites. The insertion angle to the
  local parent tangent and the downstream curvature draws are retained.
  A nonzero row-axial insertion control conflicts with active sibling sectors
  on the same order. The curve receipt records `sibling_sector_applied`.

Both settings are off by default. A fraction of 0.5 selects half the eligible
windows in expectation. Singleton windows retain their original bearing.

### Depth-dependent terminal recruitment in a research vine

The [offline research constructor](../scripts/research/realize_terminal_recruitment.py)
accepts a five-order schema-4 potential vine with native taper parameters.
It grows the potential vine, keeps orders 1–4, and draws one retention outcome
per fifth-order axis using its realized insertion depth in cm below the soil
surface. Its retention probability is
`p_deep + (1 - p_deep) / (1 + exp((depth_cm - midpoint_cm) / 8))`.
The two inputs describe a hypothetical mature population. A deep probability
of one keeps every eligible terminal. Seeded draws use biological organ IDs.

```bash
python scripts/research/realize_terminal_recruitment.py \
  --config population.schema4.json --seed 101 \
  --deep-probability 0.7 --midpoint-cm 30 --output mature_vine.npz
```

The archive contains complete retained polylines (`points`, `sizes`), organ
and parent IDs, orders and source taper parameters. It can be generated before
any observation coordinates are available. The native run describes the
potential population. Compute mature-vine mass and spatial summaries from
the retained axes and the study's tissue-density and taper recipe.

[Configure irrigation depth, daughter recruitment and vineyard spacing](research/IRRIGATION_INPUTS.md)

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
