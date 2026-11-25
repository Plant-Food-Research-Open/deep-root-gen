# DeepRootGen model reference

This reference describes every function of the schema-4 root generator, the options each function offers, the observation operators that sample a simulated vine like a soil core, and the scores used to compare simulated and measured roots. It gives definitions, units, equations and code defaults.

**Source basis.** Written on 25 November 2026 from the source on branch `site4-irrigation-core-search-20261124` (commit `0463a03`), including the uncommitted numerical fixes in that working tree (interval-length reconciliation and the stricter `core-search --stage confirm` freeze rule). It was written from source inspection. It reports no simulation results and does not qualify any configuration biologically.

**Site-specific values are not in this file.** Values fitted to Calvin's survey sites are private and stay in local, git-ignored files. In a checkout that holds them, see the [Site 1 reference parameters](research/Calvin_private/SITE1_REFERENCE_PARAMETERS.md) and the [coring-to-architecture methods](research/Calvin_private/CORING_TO_ARCHITECTURE_METHODS.md). Those links do not resolve in a public clone.

Use this file with the worked examples in [NATIVE_EXECUTION.md](NATIVE_EXECUTION.md), the irrigation guide [IRRIGATION_INPUTS.md](research/IRRIGATION_INPUTS.md) and the search guide [CORE_LATTICE_SEARCH.md](research/CORE_LATTICE_SEARCH.md). The JSON snippets below use invented values to show the syntax. They are not calibrated settings.

## Contents

1. [What the generator builds](#1-what-the-generator-builds)
2. [Running the model](#2-running-the-model)
3. [The schema-4 configuration](#3-the-schema-4-configuration)
4. [Execution order](#4-execution-order)
5. [Root crown (head) and first-order roots](#5-root-crown-head-and-first-order-roots)
6. [Root lengths](#6-root-lengths)
7. [Diameter, taper and root material](#7-diameter-taper-and-root-material)
8. [Branching: daughter number and sites](#8-branching-daughter-number-and-sites)
9. [Daughter placement options](#9-daughter-placement-options)
10. [Root direction and path](#10-root-direction-and-path)
11. [Irrigation response](#11-irrigation-response)
12. [Vineyard neighbourhood](#12-vineyard-neighbourhood)
13. [Outputs and receipts](#13-outputs-and-receipts)
14. [Observation operators](#14-observation-operators)
15. [Scoring and search](#15-scoring-and-search)
16. [Parameter glossary](#16-parameter-glossary)
17. [Reproducibility and limits](#17-reproducibility-and-limits)
18. [Other entry points and related documents](#18-other-entry-points-and-related-documents)

---

## 1. What the generator builds

DeepRootGen builds a **static** three-dimensional root system for one vine. There is no time stepping: the legacy `t` field has no consumer, and maturity factors are latent size multipliers, not ages. Each run takes one configuration and one random seed and returns one realization of the configured distributions.

**Topology.** The below-ground crown is order 0 and carries no root material. First-order roots (primaries) attach to the crown. Every daughter has its parent's order plus one. `max_order` is the terminal order and never branches.

**Graph.** The result is a node table and an edge table. Each node except a crown base carries the length and diameter of the segment that ends at it.

| Table | Columns |
|---|---|
| Nodes | `node_id`, `parent_id`, `plant_id`, `organ_id`, `x`, `y`, `z`, `order`, `segment_rank`, `diameter`, `length`, `root_tissue_density`, `root_type`, `order_type`, `position_type`, `simulation_tag`, `invalid_root` |
| Edges | `parent_id`, `child_id` |

`organ_id` identifies one root axis. An organs table summarizes the axes. Crown-support connectors and invalid roots must be filtered according to the measurement being simulated.

**Frame and units.**

| Quantity | Convention |
|---|---|
| Length, diameter, coordinates | cm (observation diameter bands are written in mm) |
| Dry mass, tissue density | g, g/cm³ |
| Angles | degrees, unless the field name says `rad` |
| Vertical axis | model `z` increases upward. The soil surface is at `soil_surface_z_cm` (default 0). Depth = `soil_surface_z_cm − z`. |
| Row axis | model `+y` runs along the vine row and `x` runs across it. Row alignment, row-axial insertion, vineyard profiles, irrigation lines and planting lattices use this convention. |

**Randomness.** Native kernels draw from one sequential stream seeded by `random_seed`. Feature laws (lengths, taper, branching, maturity, origins, curvature, insertion, placement, irrigation) use **keyed streams** identified by purpose, version and organ ID (policy `feature_keyed_v1`). Disabling one feature therefore leaves the other features' draws unchanged. A change that alters topology can still change which organs exist downstream.

## 2. Running the model

Use Python 3.10 and the locked environment described in [RUNNING.md](../RUNNING.md) and [DEVELOPMENT.md](DEVELOPMENT.md). The graph module imports Torch and PyTorch Geometric eagerly.

### Command line

```bash
# Resolve and explain the configuration without simulating
python -m deeprootgen simulate --config config.json --explain-config

# Run one seeded vine into a new directory
python -m deeprootgen simulate --config config.json --outdir runs/vine-001

# Grow a focal vine with neighbours (3 x 3 grid, independent seeds)
python -m deeprootgen neighbourhood --config config.json --mode independent \
  --vine-distance-cm 200 --row-distance-cm 300 --outdir runs/neighbours-001

# Opt-in soil-core search (see section 15.4)
python -m deeprootgen core-search --spec spec.json --stage arms --name W1 --outdir runs/search
```

Each output directory must be new. `--explain-config` prints the resolved laws, the active and dormant features, the status of every native parameter (`active`, `replaced` or `inactive`) and the model hashes.

### Python

```python
import json
from deeprootgen.model.root import RootSystemSimulation

config = json.load(open("config.json"))
simulation = RootSystemSimulation(random_seed=config["random_seed"],
                                  simulation_tag=config.get("simulation_tag", "default"))
simulation.run(config)          # dict, JSON text, pathlib.Path or RootConfig
nodes, edges = simulation.G.as_df()
summary = simulation.result.metadata["root_summary"]
```

Use a fresh simulator for every run. The simulator seed must equal the configuration seed. `deeprootgen.research.neighbourhood.generate_neighbourhood(config, mode=..., vine_distance_cm=..., row_distance_cm=...)` is the Python form of the neighbourhood command.

## 3. The schema-4 configuration

Fresh generation accepts only `schema_version: 4`. Older flat and schema-2/3 inputs are converted offline by [`deeprootgen/data_model/migration.py`](../deeprootgen/data_model/migration.py). Validation is strict: unknown keys, non-finite numbers, duplicate JSON keys and wrongly typed values fail. Per-order maps use canonical order strings such as `"2"`; `"02"` is rejected.

### Top-level keys

| Key | Type and default | Meaning |
|---|---|---|
| `schema_version` | `4`, required | Input contract |
| `random_seed` | integer ≥ 0, or `null` | Required when any keyed law is active: curvature, disk origins, a sampled vine catalogue, maturity, branching laws, stochastic lengths or taper, irrigation, rainfed placement or birth-depth transfer |
| `simulation_tag` | string, `"default"` | Output label only |
| `parameters` | object, required | Global and native values ([section 16.1](#161-global-parameters)) |
| `features` | object | Fourteen optional feature blocks, each `{"enabled": bool, "settings": {...}}` |
| `limits` | object | Resource limits ([section 17](#17-reproducibility-and-limits)) |
| `irrigation` | `null`, `"rainfed"` or object | Wet-zone response ([section 11](#11-irrigation-response)) |
| `daughter_placement` | `null` or object | Rainfed terminal-daughter preference ([section 9.4](#94-terminal-daughter-placement-daughter_placement)) |
| `birth_depth_transfer` | `null` or object | Moves shallow buds deeper on the same parent ([section 9.3](#93-birth-depth-transfer)) |
| `minimum_realized_primary_length_cm` | `null` or number > 0 | Conditions the primary length draw ([section 6](#6-root-lengths)) |

### Feature blocks

A disabled block keeps its settings but has no effect. An enabled block must be complete. The resolver gives each quantity on each order one owner and rejects conflicting owners, for example a native daughter-count override and a branching law on the same parent order.

| Feature | Owns | Section |
|---|---|---|
| `primary_origins` | Where first-order roots start and, optionally, their initial headings | 5 |
| `primary_placement` | Legacy primary yaw, inclination bias and explicit primary design | 5 |
| `cohort_maturity` | One maturity factor per primary, inherited by its descendants | 5, 6, 7 |
| `lengths` | Per-order contour-length law | 6 |
| `taper` | Per-order point-diameter profile | 7 |
| `parent_diameter_cap` | Daughter basal diameter limit relative to the parent | 7 |
| `materialization` | Reconciliation of stored interval lengths with geometry | 7 |
| `branching` | Per-order first-site/count law or length-Poisson law | 8 |
| `branch_sites` | Legacy research site and count conditioning | 8 |
| `sibling_lengths` | Tertiary length-rank research control (controlled replay only) | 8 |
| `attachment_relocation` | Distal relocation of order-2 attachments on primaries | 9 |
| `curvature` | Per-order correlated curvature, insertion heading, sibling sectors, deep carriers and row alignment | 9, 10 |
| `insertion` | Row-axial bias of the insertion azimuth | 9, 10 |
| `direction` | Fichtl overrides, construction stationing and correction policies | 10 |

## 4. Execution order

Every input runs through one lifecycle in [`deeprootgen/model/engine.py`](../deeprootgen/model/engine.py), resolved by [`deeprootgen/data_model/resolution.py`](../deeprootgen/data_model/resolution.py).

| Phase | What happens |
|---|---|
| `prepare_forest` | Selects a vine-origin catalogue entry if used. Creates one zero-material base per primary for disk or indexed layouts. Builds all organs breadth-first: lengths, taper dimensions, maturity, branch sites and the diameter gate on proposed sites. |
| `place_scaffold` | Native placement of primaries and laterals, then the origin translation and heading laws of `primary_origins`. |
| `record_initial` | Optional read-only snapshot of the initial scaffold. |
| `pre_direction` | Optional Fichtl primary repair or a frozen-scaffold surface check. |
| `attachments` | Optional distal relocation of order-2 attachments. |
| `realize_directions` | Order by order, from 1 to `max_order` (details below). |
| `post_direction` | Legacy validation and repair, a Fichtl lateral check, or a pure surface check that fails rather than repairs. |
| `materialize` | Final diameter-gate and cap checks, then the material intervals of every axis. |
| `emit` | Publishes the graph and applies diameter-banded tissue density. |
| `check` | Integrity and geometric postconditions. It never draws or repairs. |
| `publish` | Builds the result and `root_summary`. |

Within `realize_directions`, each order k that has a curvature law is processed in this sequence:

1. **Birth-depth transfer** for daughters of parent order k − 1, if configured.
2. **Rainfed terminal placement** (`daughter_placement`), when k is the terminal daughter order.
3. **Sibling sectors** for order-k daughters.
4. **Irrigation recruitment** of order-k daughters on realized order k − 1 parents. New daughters also receive sibling-sector bearings when configured.
5. For each order-k axis: initial heading (scaffold chord, origin heading or insertion angle), then the sibling transverse direction, the row-axial bias and the surface bearing, then curvature integration with optional moisture-directed pull.

Placement, transfer and irrigation therefore act on the **realized** three-dimensional parent paths, before the daughters' own paths exist. Orders without a curvature law use the native direction kernel chosen by `tropism_mode`.

## 5. Root crown (head) and first-order roots

The crown is the below-ground base of the trunk or rootstock where first-order roots emerge. It carries no root material in the graph. Any trunk or crown dry mass must be added outside the generator, for example with `crown_kg` in a core-search specification.

### 5.1 Number and grouping of primaries

`parameters.primary_root_count` sets the number of first-order roots. `outer_primary_fraction` (default 0.5) assigns `round_half_up(fraction × count)` of them to an outer group and the rest to an inner group. **Birth indices** are zero-based, outer group first. Maturity groups, azimuth groups and indexed origin layouts refer to these indices.

### 5.2 Five ways to place the crown

| Method | Settings | What it does | Typical use |
|---|---|---|---|
| **A. Native common base** (default) | `primary_origins` disabled | One base node at the model origin. Outer and inner primaries get group-specific pitch ranges and evenly spaced yaw with jitter. | Generic tests and legacy inputs |
| **B. Common point** | `layout: "point"`, `x_cm`, `y_cm`, `depth_cm` ≥ 0 | Rigid translation of the common base to `(x, y, surface − depth)`. No random draw. | A trunk represented by one point |
| **C. Disk** | `layout: "disk"`, `radius_cm` ≥ 0, `depth_range_cm: [min, max]` | Each primary gets its own base. Polar angle φ is uniform, radius is `radius_cm·√U` (uniform over area) and depth is uniform in the range. A radius of 0 places origins along a vertical trunk line. | Distributed emergence along a buried trunk |
| **D. Vine catalogue** | `layout: "vine_catalogue"` with `entries` | Selects one coherent crown record: either one common point or indexed origins (with optional measured headings) for every primary. | A surveyed or excavated crown |
| **E. Legacy primary placement** | `primary_placement` feature | Yaw mean and concentration, reverse-yaw probability, rigid inclination bias, or an explicit primary design on the native scaffold | Fichtl/SO4 research |

#### Disk options

| Setting | Meaning |
|---|---|
| `heading` | `{"law": "radial_inclination", "inclination_mean_deg", "inclination_sd_deg", "inclination_bounds_deg": [low, high]}` with bounds inside [−90, 90]. The initial heading points radially outward along φ and dips below horizontal by a truncated-normal angle (positive is downward). At least 1% of draws must fall within the bounds. Requires curvature on order 1 with `initial_heading: "origin_heading"`. |
| `azimuth_groups` | List of `{"primary_indices", "mean_deg", "concentration", "half_plane"}`. Listed primaries draw φ from a von Mises distribution with the given mean (degrees from model +x towards +y) and concentration κ ≥ 0. With `half_plane: true`, each angle is redrawn until it lies within 90° of the group mean, so every member emerges on its own side. Unlisted primaries keep uniform angles. Groups must not share indices. Because the heading is radial, the group also sets the initial bearing. |

For κ = 0.5, 1, 1.5 and 2 without `half_plane`, about 65%, 78%, 87% and 92% of draws fall within 90° of the mean.

#### Vine catalogue

```json
"primary_origins": {
  "enabled": true,
  "settings": {
    "layout": "vine_catalogue",
    "catalogue_version": "vine_origins_v1",
    "coordinate_frame": "model_soil_cm_v1",
    "selection": {"mode": "fixed", "entry_id": "surveyed-crown"},
    "entries": [{
      "entry_id": "surveyed-crown",
      "layout": "primary_layout",
      "origins_status": "complete",
      "crown_census_status": "complete",
      "headings_status": "complete",
      "primaries": [
        {"index": 0, "x_cm": 2.0, "y_cm": -1.0, "depth_cm": 6.0, "heading_unit": [0.94, 0.0, -0.342]},
        {"index": 1, "x_cm": -1.5, "y_cm": 2.5, "depth_cm": 12.0, "heading_unit": [-0.7, 0.7, -0.141]}
      ]
    }]
  }
}
```

The values above are invented. Rules:

- `selection` is `{"mode": "fixed", "entry_id": ...}`, which uses that entry without a draw, or `{"mode": "sample"}`, which draws one entry per run in proportion to `weight` (default 1).
- A `common_point` entry supplies `origin: {x_cm, y_cm, depth_cm}`.
- A `primary_layout` entry must list indices `0 … primary_root_count − 1` exactly once. Depth is positive below the surface.
- `heading_unit` must be a unit vector in the model frame (z up). Supply it for all primaries or for none. Measured headings need curvature on order 1 with `initial_heading: "origin_heading"`. They conflict with `primary_placement` yaw and inclination controls.
- `origins_status`, `crown_census_status`, `headings_status` and `provenance` (`source_frame`, `source_sha256`, `conversion_version`, `comment`) document the evidence. The run writes the selected record to `vine_origin_catalogue.json`.
- Spatial profiles evaluate indexed origins relative to the crown at model (0, 0).

#### Legacy primary placement (`primary_placement`)

| Setting | Meaning |
|---|---|
| `yaw_mean_deg`, `yaw_kappa` | Paired circular mean (degrees from x towards y) and von Mises concentration for primary yaw |
| `yaw_reverse_probability` | Keyed probability of reversing a primary's yaw by 180° |
| `inclination_bias` | Rigid downward bias in [0, 1] applied to whole primary subtrees. It is not an angle. |
| `explicit_design` | List of primaries with `primary_id`, `category`, `length_cm`, `diameter_base_cm`, `diameter_apex_cm`, `inclination_deg`, `azimuth_deg`. It owns primary dimensions and requires a common origin. |

### 5.3 Primary maturity groups (`cohort_maturity`)

| Setting | Meaning |
|---|---|
| `groups` | `[{label, primary_indices, maturity_range: [low, high]}]`, covering every primary exactly once, with 0 < low ≤ high ≤ 1. Equal bounds give a fixed factor; otherwise the factor is uniform within the range. Descendants inherit their primary's factor. |
| `length_power` | Whole-axis length is multiplied by `maturity ** length_power` |
| `diameter_power` | Point-taper base diameter is multiplied by `maturity ** diameter_power`. Requires taper on every order. |
| `scale_branch_probability` | When true, the branch probability is multiplied by `maturity`. Requires the first-site/count law on every non-terminal order and is incompatible with the length-Poisson law. |
| `diameter_target` | Only `"base_anchor"` is supported |

Maturity represents a hypothetical older or later crown cohort. It is not chronological age. First-branch distances and tip diameters are not maturity-scaled.

### 5.4 Minimum realized primary length

`minimum_realized_primary_length_cm` conditions a stochastic `bounded_lognormal` primary length so that the **realized** length after maturity scaling is at least the floor. The lower truncation becomes `max(min, floor / maturity**length_power)`, and the run fails if no admissible support remains. It requires a nonzero SD and no allocation targets.

## 6. Root lengths

Lengths are **contour lengths**: distances along the curved path. Curvature never changes them.

| Law | Settings | Behaviour |
|---|---|---|
| Native (no `lengths` entry for the order) | `min_primary_length`, `max_primary_length`, `min_lateral_length`, `max_lateral_length`, `length_reduction` | Primary length is uniform in [min, max]. A lateral draws from its interval scaled by `length_reduction ** parent_order`, plus an inherited attachment term. |
| Fixed | `"k": 120.0` | Exact length |
| Nominal | `"k": {"nominal_cm": 120.0}` | Starting length that allocation may scale within the order's range ([section 7.5](#75-length-and-biomass-ratio-targets)) |
| Bounded lognormal | `{"law": "bounded_lognormal", "mean", "sd", "min", "max"}` | Lognormal with untruncated mean and SD, accepted only inside [min, max]. At least 1% of draws must be accepted. SD 0 returns the mean. |
| Discrete CDF | `{"law": "discrete_cdf", "lengths_cm": [...], "cumulative_probabilities": [...]}` | An empirical current-length distribution. Orders 2–5 only, with `max_order` ≤ 5, and not combined with maturity scaling. |

For the bounded lognormal, `σ² = ln(1 + (sd/mean)²)` and `μ = ln(mean) − σ²/2`. Because of truncation, realized means and SDs differ from the inputs. A feature length replaces the organ's total length and keeps the native proportions of its construction segments. The order of operations is: draw → maturity scaling → allocation scaling.

## 7. Diameter, taper and root material

### 7.1 Native cylinders

Without a taper law, native segments use `base_diameter`, `diameter_reduction` and `apex_diameter`. The initial scale is `base_diameter × (1 − diameter_reduction) ** parent_order`, and segment diameters are drawn towards `apex_diameter`. An untapered daughter inherits the equivalent diameter of the construction interval where it was born.

### 7.2 Point taper (`taper.settings.by_order`)

| Law | Profile along arclength s on an axis of length L |
|---|---|
| `piecewise_linear_arclength` | Linear from `base` at s = 0 to `tip + f·(base − tip)` at s = L/2, then linear to `tip` at s = L. `midpoint_diameter_fraction` f lies in (0, 1); the default is 0.5. |
| `exponential_above_diameter` | Adds `rate_per_cm` k ≥ 0 and `thick_min_cm`. While thick, `d(s) = base·exp(−k·s)` until the join `s_j = ln(base / thick_min) / k`. The remaining length uses the piecewise-linear taper from `thick_min` to `min(tip, thick_min)` with the same midpoint fraction. An axis whose base is below `thick_min` uses the piecewise taper throughout. With k = 0 the whole axis stays at its base diameter. |

`base_cm` and `tip_cm` each accept:

- a number (fixed);
- `{"nominal_cm": x}`, which allocation may scale;
- `{"law": "truncated_normal", "mean", "sd", "min", "max"}`, which needs at least 1% acceptance;
- `{"law": "bounded_lognormal", ...}`, or the same fields without `law`.

The base and tip are resolved in this order:

1. Draw the base and multiply by the allocation diameter scale.
2. Multiply the base by `maturity ** diameter_power`.
3. Apply the parent cap.
4. Draw the tip, limited to at most the base.

The branch gate (section 8.4) reads the local point diameter.

### 7.3 Parent diameter cap (`parent_diameter_cap`)

`fraction_max` in (0, 1] limits a daughter's basal diameter to `fraction_max × (local parent diameter at the final attachment)`. It requires point taper on every order. When a daughter is moved (placement, transfer or irrigation), the cap is re-applied at its new site.

### 7.4 Published segments and tissue density

Each axis is cut at curvature stations, attachments, taper bends and the crossing of `threshold_root_diameter_cm`. Every published segment stores the diameter of a cylinder with the same integrated volume:

```text
linear piece with end diameters a, b over length h:
  volume_cm3 = pi * h * (a*a + a*b + b*b) / 12
  equivalent_diameter_cm = sqrt((a*a + a*b + b*b) / 3)
exponential piece:  equivalent_diameter_cm = sqrt( integral(d(s)^2 ds) / h )
dry_mass_g = volume_cm3 * tissue_density_g_cm3
```

`root_type` is `fine` when the equivalent diameter is at or below `threshold_root_diameter_cm`, and `structural` otherwise.

`parameters.root_tissue_density` is either a scalar in g/cm³ or diameter bands:

```json
"root_tissue_density": {
  "bounds_mm": [1.0, 2.0, 2.5, 12.0, 30.0],
  "density_g_cm3": [0.25, 0.30, 0.40, 0.45, 0.50, 0.50],
  "equality_to_finer": [false, true, true, true, true]
}
```

Bounds must increase, one more density than bounds is required, and each `equality_to_finer` flag assigns a diameter exactly on that bound to the finer (true) or coarser (false) band. Banded density is integrated exactly along the point taper. Each node stores the resulting volume-weighted density. The example values equal the code's built-in grapevine stepped profile (`GRAPEVINE_STEPPED` in [`tissue_density.py`](../deeprootgen/model/tissue_density.py)), which is a research assumption.

### 7.5 Length and biomass ratio targets

`threshold_root_diameter_cm` (default 0.25 cm) splits whole-vine totals into `at_or_below` and `above`. The optional targets `root_ratio_length` and `root_ratio_biomass` ask for those fractions of valid root length and dry mass in the lower class. They must be supplied with `allocation_controls`:

```json
"allocation_controls": {
  "length_scale_by_order": {"4": [0.5, 2.0]},
  "diameter_scale_by_order": {"1": [0.8, 1.25]}
}
```

Each range must contain 1. The solver evaluates scaled forests from the same initial random state and accepts a realization whose achieved fractions lie within **0.01** of each target. A fixed length or diameter conflicts with allocation on that order; use `nominal_cm` instead. `execution.json` records whether the outcome was a proven conflict or an exhausted search.

### 7.6 Length-metadata reconciliation (`materialization`)

`reconcile_length_metadata: true` replaces a stored interval length with its endpoint geometric length when the two differ only at floating-point roundoff. It never moves coordinates or cuts and requires at least one point-taper axis. Each change is recorded in the run counters.

## 8. Branching: daughter number and sites

Every non-terminal order has one branching owner. A parent proposes sites, the diameter gate removes ineligible sites, and the surviving sites receive daughters. Daughters on the terminal order never branch. A branching entry supplied for the terminal order is kept as dormant input.

### 8.1 Native spacing law

This law applies when an order has no `branching` entry.

| Setting | Meaning |
|---|---|
| `daughters_per_parent` | A fixed integer or `{"min", "max_exclusive"}`. A range draws a base count in [min, max_exclusive). |
| `daughters_by_parent_order` | `{"k": n}` fixed requested count on non-terminal parent order k |
| `daughter_count_order_gain` g ∈ [0, 1) | Requested count at parent order k is `ceil(n × (1 − g) ** −(k − 1))` |
| `floor_threshold`, `ceiling_threshold` | Branch zone as fractions of parent length (defaults 0.4 and 0.9) |
| `interbranch_distance` | Mean lognormal spacing (cm) between sites in the zone |

The capacity of the zone can reduce the realized count.

### 8.2 First-site and daughter-count law

```json
"branching": {"enabled": true, "settings": {"by_order": {
  "2": {"law": "first_branch_and_daughter_count",
        "first_branch_cm": {"mean": 10.0, "sd": 4.0, "min": 2.0, "max": 30.0},
        "branch_probability": 0.8,
        "daughter_probabilities": [0.2, 0.3, 0.3, 0.2],
        "stratify_distal_sites": false}
}}}
```

For each parent of contour length L:

1. Draw the first-site distance s₁ along the parent from the bounded law.
2. With probability `branch_probability` p (multiplied by maturity when enabled), the parent is active. An inactive parent gets no daughters.
3. If s₁ ≥ L, the parent gets no daughters and the `branch_beyond_tip` counter increases.
4. Otherwise draw the family size N from `daughter_probabilities`, where entry i is P(N = i + 1). The entries must be nonnegative and sum to 1. Zero daughters is controlled by p, not by this vector.
5. Sites are s₁ plus N − 1 positions uniform on (s₁, L). With `stratify_distal_sites: true`, (s₁, L) is split into N − 1 equal intervals with one uniform position in each.

### 8.3 Length-Poisson law

```json
"3": {"law": "length_poisson_sites_v1", "basal_exclusion_cm": 5.0,
      "apical_exclusion_cm": 10.0, "mean_spacing_cm": 4.0, "branch_probability": 1.0}
```

The usable length is `W = L − basal − apical`. With probability p the parent is active, and then `N ~ Poisson(W / mean_spacing_cm)`, with sites uniform on [basal, L − apical]. This law cannot be combined with maturity-scaled probability. When it is active, `limits.max_branch_proposals` defaults to 100,000, and exceeding it fails the run.

### 8.4 Diameter gate

`parameters.min_branching_diameter_cm` (default **0.093 cm**; 0 disables it) is the smallest local parent diameter at which a daughter may start. Each proposed site is tested at its final attachment, after any relocation. A thin site is dropped without replacement. Before materialization the engine checks every realized attachment again. The gate concerns initiation only: thinner existing roots still contribute length and mass, and a primary can emerge from the crown at any diameter.

### 8.5 Legacy research site controls (`branch_sites`, `sibling_lengths`)

| Setting | Meaning |
|---|---|
| `placement` | `legacy_spacing` or `redistribute_capped`, which spreads retained capped sites through the permitted zone |
| `counts_by_order` | Exact supplied topology counts (conditioning, not prediction) |
| `primary_zone_cm` | `{start_cm, end_cm}`, a physical primary branch zone |
| `primary_fractions` | Normalized primary attachment positions |
| `parent2_zone_cm` | Tertiary zone on order-2 parents (controlled replay only) |
| `sibling_lengths.tertiary_rank_strength` | Sibling length-rank reassignment (controlled replay only) |

These controls conflict with the replacement branching laws on the same orders. Native `run()` rejects controls that need the controlled-replay route.

### 8.6 Branching receipt

`branching.json` reports, for each parent order: proposals, placed sites, accepted daughters, invalid daughters, rejection reasons and the sampled first sites. Rejection reasons are `diameter_below_branch_minimum`, `coincident_sites`, `bernoulli_rejected`, `first_site_at_or_beyond_tip`, `inactive`, `poisson_zero` and `empty_zone`. Poisson parents also report their usable zone and draw. Irrigation births are included in the proposal and placement counts.

## 9. Daughter placement options

Daughter placement is decided in layers. Each layer is optional except the site law and the gate.

| Layer | Option | Acts on | Changes |
|---|---|---|---|
| 1. Site law | Uniform after the first site, stratified distal sites, Poisson with exclusions, or native zone spacing | All non-terminal parents | Positions along the parent |
| 2. Eligibility | `min_branching_diameter_cm` | All proposed sites | Removes thin sites |
| 3. Relocation | `attachment_relocation` | Order-2 daughters on primaries | Moves attachments distally |
| 4. Transfer | `birth_depth_transfer` | Listed parent orders | Moves shallow buds deeper on the same parent |
| 5. Terminal placement | `daughter_placement` modes | Terminal daughters | Moves, adds, thins or retains terminals by a spatial preference |
| 6. Irrigation | `irrigation` | Parents crossing the wet zone | Adds or moves daughters ([section 11](#11-irrigation-response)) |
| 7. Orientation | Insertion angle, sibling sectors, row-axial bias, surface bearing | Daughter orders | Initial heading at birth |
| 8. Post-hoc retention | `scripts/research/realize_terminal_recruitment.py` | Fifth-order axes | Depth-dependent thinning after growth |

### 9.1 Site law and gate

See sections 8.2–8.4. Under the first-site law, the first realized daughter is the **anchor**. Transfer and terminal redistribution keep it in place.

### 9.2 Distal relocation (`attachment_relocation`)

```json
"attachment_relocation": {"enabled": true,
  "settings": {"orders": [2], "distal_fraction": 0.25, "preserve_sampled_daughter_dimensions": true}}
```

Each order-2 attachment arc s on a primary of length L moves to `b·L + (1 − b)·s`, where b is `distal_fraction` in (0, 1]. Sampled daughter dimensions are kept, the gate and cap are evaluated at the new arc, and each daughter subtree is transported with a minimal rotation. Only `orders: [2]` is supported. It requires `max_order` ≥ 2 and curvature on order 2 (or Fichtl mode). It cannot be combined with the Poisson law on order 1 or with irrigation of primaries.

### 9.3 Birth-depth transfer

```json
"birth_depth_transfer": {"parent_orders": [1, 2, 3], "shallow_depth_cm": 30,
                         "deep_depth_cm": 60, "transfer_probability": 0.5}
```

For each listed parent order, every existing daughter born shallower than `shallow_depth_cm` is a candidate, except the first-site anchor. Each candidate is selected with `transfer_probability`. A selected bud moves to a position drawn uniformly on that parent's eligible contour deeper than `deep_depth_cm`. Eligible means the local diameter passes the gate, and with a cap it must also support the daughter's existing base. If no such contour exists, the bud stays where it is and is recorded as a shortfall.

The move happens before the daughter's direction and descendants are realized. Identities and sampled dimensions are kept. Requirements: a seed, an ordinary branching law, a curved parent, and an insertion-angle curved daughter on each listed pair of orders. The transfer cannot act on the parent order used by active irrigation or rainfed terminal placement. Receipts are in `diagnostics.birth_depth_transfer.by_parent_order`.

### 9.4 Terminal-daughter placement (`daughter_placement`)

This top-level option applies a spatial preference to **terminal** daughters on parents of `parent_order`. It is intended for rainfed configurations and cannot be combined with an active irrigation response, except in `surface_bearing` mode.

| Field | Type and default | Meaning |
|---|---|---|
| `parent_order` | integer ≥ 2, default 4 | Must equal `max_order − 1` |
| `strength` | [0, 1], default 0 | 0 is inactive, except `retention`, which then thins uniformly |
| `mode` | default `redistribute` | See the mode table |
| `profile` | `null`, `occurrence_v1` or `vineyard_3d_v1` | Spatial preference. `null` uses the built-in depth layer. Profiles are allowed with `redistribute`, the two `branch_probability` modes, `retention` and `surface_bearing`. `add`, `uniform_extra` and the sparse modes use the depth layer only. |
| `layer_depths_cm` | `[a, b, c, d]`, 0 ≤ a < b ≤ c < d | Start of rise, plateau start, plateau end, end of fall. Default (80, 90, 150, 170). Only with `redistribute`, `add` or `uniform_extra` and no profile. |
| `layer_peak_multiplier` | (1, 5] | Layer peak at full strength. Default 1.5. Same restriction as `layer_depths_cm`. |
| `spatial_cell_width_cm` | > 0 | `sparse_depth_balanced` only |
| `bearing_orders` | list of daughter orders ≥ 2 | `surface_bearing` only |

Requirements: a seed; curvature on the parent and terminal orders with insertion-angle daughters; a branching law on `parent_order`; point taper on the terminal order; a gate of at least 0.093 cm.

#### Preference weight w at a contour point

- **Built-in depth layer** (no profile): `w(d) = 1 + strength × (peak − 1)/2 × (1 − cos(π·r(d)))`, with `r(d) = clip(min((d − a)/(b − a), (dd − d)/(dd − c)), 0, 1)` for `layer_depths_cm` = (a, b, c, dd).
- **Profiles**: `w = 1.5 ** (strength × P)`, where P is the preference in [−1, 1].
  - `occurrence_v1` (a frozen regression fitted on training cores):

    ```text
    P = clip((β0 + β1·d/100 + β2·max(d − 30, 0)/100 + β3·max(d − 90, 0)/100
              + (β4 + row_depth_slope·(d − 90)/100) · c · support − training_mean) / 0.20, −1, 1) · fade
    ```

    Here d is clipped to `depth_range_cm`. `fade = clip(1 − (distance outside the depth range)/fade_cm, 0, 1)`. The term c is the distance to the nearest row as a fraction of half `row_period_cm`. `support = min(tubes in the management zone / 2, 1)`, using the cross-row `zone_boundaries` and `zone_tube_counts`.
  - `vineyard_3d_v1` (a smooth vineyard-cell surface):

    ```text
    P = clip(a0(d) + a1(d)·cos(2πx/Px) + a2(d)·cos(2πy/Py) + a3(d)·cos(2πx/Px)·cos(2πy/Py), −1, 1) · fade
    ```

    x and y are measured from the crown. The coefficients are interpolated linearly between `depth_knots_cm`, and Px and Py are `across_period_cm` and `along_period_cm`.

Fit profiles offline with [`fit_core_preference_surface`](../deeprootgen/research/core_preference_surface.py) (`mode="all"` or `"depth_only"`) on training cores only. A positive target means the reference under-predicts roots there.

#### Modes

| Mode | Rule | Daughter count |
|---|---|---|
| `redistribute` | Keeps the anchor. Moves each other existing terminal daughter to a site drawn in proportion to w on the eligible contour. The daughter's base and tip are re-drawn from the same pre-cap draw and capped at the new site. In layer mode, parents whose eligible contour lies wholly outside the layer are skipped. | Unchanged |
| `add` | Extra daughters per active parent with expectation `(w̄ − 1) × eligible length × λ`, where w̄ is the contour-average weight and λ is the parent's background site rate. The count is Poisson; positions are accepted in proportion to w − 1. A deep-envelope fallback handles parents that barely enter the layer. | Increases |
| `uniform_extra` | Same Poisson counts as `add` on paired seeds; positions uniform on the eligible contour | Increases (control) |
| `branch_probability` | Per-parent multiplier M is the contour average of w; `p' = p·M / (1 − p + p·M)`. Reuses each parent's original activation draw. A newly activated parent receives daughters at its replayed proposed sites. Requires a profile. | Changes |
| `branch_probability_uniform` | One common multiplier for the vine, chosen to match the expected eligible daughters of `branch_probability` | Matched in expectation (control) |
| `retention` | Each terminal is kept with probability `expit(logit(0.85) + ln w + a)`, with a fitted so the mean is 0.85. At zero strength, 85% are kept uniformly. | About 85% |
| `sparse_depth` | Requires terminal `branch_probability` = 0. Each terminal parent with eligible contour below 90 cm activates with probability = `strength` and receives one daughter uniformly on that deep contour. | At most 1 per parent |
| `sparse_uniform` | The same realized number of families as `sparse_depth`, drawn among all eligible parents, with one daughter uniformly on the full eligible contour | Matched (control) |
| `sparse_depth_balanced` | The same number of deep births, spread over horizontal cells of `spatial_cell_width_cm`. The grid has a random offset per vine, and every occupied cell supplies one birth before any cell supplies a second. | Matched |
| `surface_bearing` | Changes only the initial azimuth of daughters on `bearing_orders` ([section 9.5](#95-orientation-at-birth)) | Unchanged |

`diagnostics.daughter_placement` records every parent decision, probability and birth coordinate.

### 9.5 Orientation at birth

Orientation needs curvature on the daughter order with `initial_heading: "insertion_angle"`.

| Option | Setting | Rule |
|---|---|---|
| Insertion angle | `insertion_mean_deg` ∈ [0, 90], `insertion_sd_deg` ≥ 0 | The polar angle from the local parent tangent is normal and rejected outside [0, 90]°; at least 5% of draws must be accepted. The azimuth around the tangent is uniform. 0° means straight ahead. |
| Sibling sectors | `curvature.settings.by_order.k.sibling_sectors: {"window_cm", "fraction", "min_birth_depth_cm"}` | Daughters of one parent are grouped in successive `window_cm` arclength windows. A window with two or more daughters is selected with probability `fraction`. It receives a random rotation, each daughter gets a different sector of 360°/n at random, and a uniform jitter is added within the sector. A normal frame transported along the parent keeps adjacent bearings comparable. The polar angle is kept. `min_birth_depth_cm` excludes shallow births. |
| Row-axial bias | `insertion.settings.row_axial_kappa_by_order: {"k": κ}` | The azimuth follows a von Mises distribution around the projected row axis (±y), keeping the polar angle. It acts after sibling sectors; κ = 0 leaves the draw unchanged. |
| Surface bearing | `daughter_placement.mode: "surface_bearing"` with a `vineyard_3d_v1` profile | The native heading and its three quarter-turns about the parent tangent are scored at a straight probe of length min(40 cm, daughter length). A probe that would leave the soil is reflected downward. Weights are `exp(2 × strength × P)`. The native bearing is kept with probability min(1, 4·p₀); otherwise the bearing moves to a candidate whose probability exceeds 1/4. It cannot share an order with sibling sectors or row-axial bias. |

### 9.6 Post-hoc depth-dependent terminal retention

[`scripts/research/realize_terminal_recruitment.py`](../scripts/research/realize_terminal_recruitment.py) grows a five-order potential vine, keeps orders 1–4 and keeps each fifth-order axis with probability:

```text
p(d) = p_deep + (1 − p_deep) / (1 + exp((d − midpoint_cm) / 8))
```

Here d is the insertion depth in cm below the surface. Draws are keyed by seed and organ ID. The archive stores the retained polylines and the source taper parameters. Mass and RLD of the retained vine are computed from that archive, not from the native run.

## 10. Root direction and path

### 10.1 Direction owners

Each order is owned either by the curvature feature or by the native kernel selected by `tropism_mode`.

| Owner | When | Behaviour |
|---|---|---|
| `legacy` native kernel (default) | Orders without curvature | Segment directions are blended towards gravity: `(1 − g)·u + g·(0, 0, −1)`, normalized, with `gravitropism` g ∈ [0, 1]. `root_vary` (degrees) adds local jitter. Geometric validation can reorient roots, up to `max_val_attempts` attempts with the `no_root_zone` threshold. In legacy mode, curvature orders must be a prefix 1…k. |
| `fichtl2024` native kernel | `tropism_mode: "fichtl2024"` | Keeps the primary scaffold and rebuilds lateral paths by a candidate heading search. It requires `gravitropism` = 0 and the eight `fichtl_*` coefficients, supports `max_order` ≤ 5, and needs `direction.higher_order_tropism` for active orders 4 and 5. |
| Correlated curvature | `features.curvature` | Physical-step curved paths (section 10.2) |

### 10.2 Correlated curvature

```json
"curvature": {"enabled": true, "settings": {"by_order": {
  "1": {"law": "correlated_curvature", "step_cm": 2.0, "curvature_sd_rad_cm": 0.02,
        "correlation_length_cm": 20.0, "downward_drift_per_cm": 0.001,
        "boundary": "reflect_downward", "first_interval": "integrate",
        "initial_heading": "origin_heading"},
  "2": {"law": "correlated_curvature", "step_cm": 2.0, "curvature_sd_rad_cm": 0.03,
        "correlation_length_cm": 10.0, "downward_drift_per_cm": 0.005,
        "boundary": "reflect_downward", "first_interval": "integrate",
        "initial_heading": "insertion_angle", "insertion_mean_deg": 60.0, "insertion_sd_deg": 15.0}
}}}
```

| Setting | Units and limits | Meaning |
|---|---|---|
| `step_cm` h | cm, [0.001, 1000] | Physical integration step. Corners lie every h along the contour. |
| `curvature_sd_rad_cm` q | rad/cm, [0, 100] | Stationary SD of each of two curvature components, which sets typical bending |
| `correlation_length_cm` ℓ | cm, [0.001, 10⁶] | Distance over which a bend persists |
| `downward_drift_per_cm` | 1/cm, ≥ 0, with h × drift < 1 | Pull of the heading towards −z per cm of arclength |
| `boundary`, `first_interval` | `reflect_downward`, `integrate` | Required conventions |
| `initial_heading` | Order 1: `scaffold_chord` (default) or `origin_heading`. Orders ≥ 2: `insertion_angle`. | Start direction |
| `row_alignment_per_cm` a | 1/cm, ≥ 0, with a × h ≤ 0.5 | After each step the heading component perpendicular to ±y shrinks by `exp(−a·h)` |
| `deep_carrier` | `{"fraction", "trigger_depth_cm", "drift_multiplier" > 1}` | A random fraction of axes (lateral orders only) multiply their drift after first crossing the trigger depth downward. Requires h × drift × multiplier < 1. |
| `sibling_sectors` | see [section 9.5](#95-orientation-at-birth) | Daughter orders only |

**Integration.** The curvature state is a two-component Ornstein–Uhlenbeck process in arclength. Its exact transition over each step gives both the next curvature and the integrated turning angle. Each step then proceeds as follows:

1. The heading is rotated by the integrated angle within a frame transported along the root.
2. The heading gains `h × drift` towards −z and, if active, the moisture pull `h × gain × ∇K` (section 11.6).
3. The heading is normalized.
4. Row alignment, if active, is applied.
5. If the next point would rise above the soil surface, the vertical component is reflected downward and the curvature state is reset.

Contour length is preserved exactly. Construction intervals keep their lengths and are placed at the same arclengths on the realized curve. Each axis has its own keyed curvature stream, so adding or removing other axes leaves its draws unchanged.

### 10.3 Direction corrections and controlled settings (`direction`)

| Setting | Values | Meaning |
|---|---|---|
| `post_correction` | `native`, `pure_surface_check` | A pure check fails the run if any node lies above the surface. It never repairs. |
| `primary_correction` | `native`, `frozen_surface_check` | Checks that the frozen primary scaffold lies below the surface |
| `sigma_by_order`, `higher_order_tropism` | per order | Fichtl turning scales and higher-order direction assumptions |
| `stationing`, `boundary`, `first_interval` | `construction_steps_v1`, `minimum_angle_projection`, `assigned_insertion` | Construction-step direction stations (controlled replay scope) |

## 11. Irrigation response

The irrigation option represents a long-term wetted soil volume around drip lines or outlets, or a broad surface wetting. Daughters form more readily on parent length that runs through the wetted volume, and roots can optionally turn towards it. It is a static, phenomenological rule. There is no soil-water model.

### 11.1 Activation

The top-level key `irrigation` is inactive when it is omitted, `null` or `"rainfed"`, when it is `{"treatment": "rainfed"}`, or when `irrigation_depth_cm` is `null` or `"rainfed"`. A `peak_multiplier` of 1 is also inactive: geometry is identical to the rainfed run and no extra random draws are consumed.

### 11.2 Settings

| Field | Default | Meaning |
|---|---|---|
| `treatment` | required | `buried_drip`, `surface_drip` or `broad_surface` |
| `irrigation_depth_cm` | required | Outlet depth: > 0 for buried drip, 0 for surface treatments |
| `peak_multiplier` m | 1 | Local daughter intensity at full exposure (K = 1) relative to the background |
| `response` | `add` | `add`, `uniform_extra` or `redistribute` |
| `parent_order` | 4 | Parent order of the terminal law. Must equal `max_order − 1`. |
| `order_sensitivity` | `null` | `{"k": s}` for daughter orders k from 2 to `parent_order`, with s ∈ [0, 1]. The terminal order `parent_order + 1` always uses s = 1. |
| `max_extra_fraction` | `null` | Budget f > 0 for recruited daughters (section 11.5) |
| `moisture_tropism` | `null` | `{"k": gain}` per root order, gain ∈ [0, 10] (section 11.6) |
| `line_offsets_cm` | drip only | Surveyed x position of each line. The lines run along y. Values must be distinct. |
| `row_period_cm` | `null` | Repeats one reference line periodically across rows. Requires exactly one line offset. |
| `across_radius_cm` R⊥ | drip only | Horizontal distance from the line to the edge of wetting |
| `emitter_spacing_cm`, `emitter_origin_y_cm`, `along_radius_cm` R∥ | `null` | Discrete emitters along the line. All three are supplied together. |
| `upper_radius_cm`, `lower_radius_cm` | buried only | Vertical reach above and below the outlet |
| `surface_profile` | `plateau` | Surface treatments: `plateau` or `deep_peak` |
| `origin_x_cm`, `origin_y_cm` | 0 | Field position of this vine's crown, which registers the local frame to the vineyard |
| `reflect_x`, `reflect_y` | 1 | ±1 mirror of the local frame |

### 11.3 Exposure field K

Model points are converted to surveyed coordinates `(X, Y, D) = (origin_x + reflect_x·x, origin_y + reflect_y·y, surface − z)`. Every treatment uses the raised-cosine kernel `c(r) = ½(1 + cos(π·min(max(r, 0), 1)))`, which falls from 1 at the centre to 0 at r = 1.

```text
horizontal:   r_h^2 = (ΔX / R⊥)^2  [+ (ΔY / R∥)^2 for discrete emitters]
              ΔX = distance to the nearest line (periodic if row_period_cm);
              ΔY = distance to the nearest emitter (periodic in y)
buried_drip:  K = c( sqrt( r_h^2 + (ΔD / R_v)^2 ) ), ΔD = D − outlet depth,
              R_v = upper_radius_cm above the outlet, lower_radius_cm below it
surface_drip, plateau:   K = c(r_h) · c((D − 40) / 10)   full to 40 cm, zero from 50 cm
surface_drip, deep_peak: K = c(r_h) · c(s),  s = (37.5 − D)/37.5 above 37.5 cm,
                                                 s = (D − 37.5)/12.5 below it
broad_surface:           K = vertical profile only (no horizontal term)
K = 0 above the soil surface
```

### 11.4 Recruitment law

The law is applied to each realized parent of order `parent_order`, and also to order k − 1 parents for each k with s_k > 0.

1. **Usable contour.** Under the first-site law it runs from the first site s₁ to the tip. Under the Poisson law it runs between the basal and apical exclusions.
2. **Eligible contour.** The parts of the usable contour where the local diameter is at least `max(0.093 cm, min_branching_diameter_cm)`.
3. **Exposure integral** `H = ∫ K ds` over the eligible contour. It uses 16-point Gauss–Legendre quadrature on pieces split at depth planes, footprint edges, 10 cm depth bins and material cuts.
4. **Background rate λ (per cm).** Under the first-site law, `λ = (N − 1)/(L − s₁)`, which is 0 for a single site, an inactive parent or a first site beyond the tip. Under the Poisson law, λ is `1/mean_spacing_cm` when the parent is active.
5. **Expected extra daughters** `E = s × (m − 1) × λ × H`.

| Response | Births |
|---|---|
| `add` | `Poisson(E)` new daughters at positions drawn in proportion to K on the eligible contour. The local intensity is `λ·(1 + (m − 1)·K)`. |
| `uniform_extra` | The same parent-level counts, placed uniformly on the eligible contour. This control separates the effect of more daughters from where they are placed. |
| `redistribute` | No new daughters. Existing movable, eligible daughters beyond the first site are moved. Each goes to a K-weighted site with probability `(m − 1)H / (L_eligible + (m − 1)H)`, otherwise to a uniform site, so the density is proportional to `1 + (m − 1)K` while the count is kept. The daughter's base is re-capped at its new site. Terminal law only. |

New terminal daughters use the native terminal length, taper and curvature laws through their own keyed streams. A daughter recruited on an upstream order (s_k > 0) receives a complete native subtree, and the terminal law then also acts on its descendants. Recruitment inserts attachment nodes; it never moves existing axes, except under `redistribute`. A site within 10⁻⁹ cm of an existing event is skipped and counted as `coincident`.

### 11.5 Recruitment budget

With `max_extra_fraction` f, the expectations of all parents of one recruited order are multiplied by `min(1, f × N_existing / ΣE)`, where N_existing is that order's daughter count before recruitment. The wet-zone allocation is unchanged. The budget prevents runaway recruitment when steering keeps roots inside the wet zone. It applies to `add` and `uniform_extra`.

### 11.6 Moisture-directed growth

For each order listed in `moisture_tropism`, every curvature step of length h adds `h × gain × ∇K` to the heading before normalization. ∇K is the analytic gradient in the model frame. It is zero outside the footprint, at its centre and above the surface, so roots near the edge are turned back into the wet zone and soil beyond the footprint exerts no pull. The term uses no random numbers, so paired seeds stay paired.

The resolver rejects a gain when `h × (drift + gain × π / (2 × shortest kernel length)) ≥ 1`, because one step could then reverse a heading. The largest cross-row gradient is π/(2R⊥) per cm, which is about 0.04 per cm for R⊥ = 40 cm. Moisture-directed growth needs curvature on each listed order and an active response (m > 1).

### 11.7 Requirements and conflicts

- An explicit seed, and `parent_order + 1 = max_order`.
- A stochastic branching law on each affected parent order, with no daughter-count quota and no exact counts.
- A curved parent and insertion-angle curvature on the terminal order. Upstream recruitment also needs curvature on the recruited order and every descendant order.
- No irrigation of relocated primary attachments.
- No combination with rainfed `daughter_placement` (other than `surface_bearing`), or with `birth_depth_transfer` on the same parent order.

### 11.8 Examples and receipt

```json
"irrigation": {"treatment": "buried_drip", "irrigation_depth_cm": 30,
  "line_offsets_cm": [15], "across_radius_cm": 30,
  "upper_radius_cm": 15, "lower_radius_cm": 20,
  "peak_multiplier": 1.5, "response": "add"}

"irrigation": {"treatment": "surface_drip", "irrigation_depth_cm": 0,
  "line_offsets_cm": [0], "across_radius_cm": 35, "peak_multiplier": 2.0}

"irrigation": {"treatment": "broad_surface", "irrigation_depth_cm": 0, "peak_multiplier": 1.5}
```

The examples are illustrative. A runnable synthetic vine is in [`examples/research/irrigated_terminal_daughters.json`](../examples/research/irrigated_terminal_daughters.json).

`irrigation.json` records the settings and the minimum parent diameter. For every parent it records the decision, usable and eligible length, H, λ, expected, drawn and accepted extras, coincident sites, and each birth's surveyed coordinates, depth and exposure. It also bins eligible length and exposure by 10 cm depth and by 10 cm line distance, and reports the `upstream` and `budget` blocks.

## 12. Vineyard neighbourhood

| Mode | Behaviour |
|---|---|
| `translated` | The same seeded vine is copied to each crown position |
| `independent` | The focal vine keeps the configured seed; every other position gets a distinct, reproducible seed |

Positions come from `--vine-distance-cm` and `--row-distance-cm`, which give a 3 × 3 grid, or from `--origins` with explicit [x, y] offsets that include [0, 0]. An active irrigation footprint is evaluated at each crown's field position, even for translated copies. The export holds the graph in the surveyed horizontal frame, plus `plants.csv` (seed, placement and geometry identity per vine) and `origins.json`.

The core-lattice scorer (section 15.4) emulates a planting differently. It sums the contributions of translated copies of one simulated vine at lattice offsets. Its `independent_loss` variant takes the neighbours from other seeds.

## 13. Outputs and receipts

`python -m deeprootgen simulate --outdir` writes:

| File | Content |
|---|---|
| `nodes.csv`, `edges.csv` | The root graph |
| `organs.csv` | One row per root axis |
| `parameters.json` | Canonical supplied input. Use it to repeat a seeded run. |
| `resolved_config.json` | Resolved laws, active and dormant features, consumers, units and hashes |
| `execution.json` | Result metadata, including the integer crown split and allocation results |
| `root_summary.json` | Count and contour length by order; length and dry mass `at_or_below` and `above` the threshold; achieved fractions; excluded invalid roots |
| `branching.json` | Branch proposals, sites, acceptances and rejections by parent order |
| `irrigation.json`, `row_alignment.json`, `vine_origin_catalogue.json` | Receipts of active spatial options |
| `crown_support.json` | Crown support records |
| `node_metadata.csv` | Optional per-node metadata |
| `roots.html` | Interactive 3D view |
| `run_manifest.json` | Python and package versions, seed, node and edge counts, invalid nodes, configuration and output hashes, model identity hashes, source fingerprint and repository state. It states `"scientific_validation": "not performed"`. |

Curvature receipts are kept in `simulation.result.diagnostics["curvature"]` rather than in a file. They record the per-axis heading, stations, surface reflections, deep-carrier and moisture-gain details, sibling-sector use, row-axial insertion and surface-bearing choices.

## 14. Observation operators

The generator produces geometry. An **observation operator** decides what a measurement would see. Keep these operators separate from the generator settings.

### 14.1 Finite-cylinder soil cores

[`deeprootgen/research/core_observation.py`](../deeprootgen/research/core_observation.py):

```python
support = qualify_root_segments(nodes, edges, coordinate_frame="model",
                                fine_diameter_max_mm=2.5, dry_density_g_cm3=0.45)
result = predict_core_observations(support, cores)
```

- **Segments.** Each non-base node defines a straight segment with a constant equivalent diameter. Invalid nodes and all their descendants are excluded. The graph must be a root-only forest with one base per plant.
- **Cores.** The core table has `core_id`, `x_cm`, `y_cm`, `z_lower_cm`, `z_upper_cm`, `radius_cm`, `sampled` and optionally `known_volume_cm3`. Coordinates must already be in the model frame; the frame label performs no conversion. `sampled = false` means a missing observation, not a zero.
- **Intersection.** The root centreline is clipped exactly to the cylinder and depth interval. The same clipped fraction is applied to length, volume and dry mass.
- **Results.** Fine, coarse and total length (cm), volume, dry mass and RLD for each core section, where `RLD = intercepted length / cylinder volume` in cm/cm³.

**Diameter bands.** `band_support` in [`core_lattice_scoring.py`](../deeprootgen/research/core_lattice_scoring.py) counts a segment when its equivalent diameter d satisfies `band_low_mm < 10·d ≤ band_high_mm`. Segments are cut exactly at the reporting threshold and at taper bends, but not at other band edges. Those edges are therefore resolved to the segment length, at most one curvature step.

### 14.2 Lattice neighbours, reflections and virtual cores

- **Lattice.** Offsets `(i·x_spacing, j·y_spacing)` for i, j in −extent…extent emulate neighbouring vines. Each core is evaluated at its position minus each offset, and the contributions are summed.
- **Reflections.** A study can also score mirrored copies of each simulated vine (x → −x, y → −y) to represent uncertainty in crown orientation. This is a study-design choice, not an option of the public lattice scorer. Reflections add no independent field information.
- **Virtual cores.** Wider cylinders smooth chance encounters and change the estimand. Report them separately from the physical support. See [AREA_MEAN_CORE_METHOD.md](research/AREA_MEAN_CORE_METHOD.md).

### 14.3 Other operators

Voxel grids ([`root_grid_aggregation.py`](../deeprootgen/statistics/root_grid_aggregation.py)), the native core RLD API ([`spatial_rld.py`](../deeprootgen/statistics/spatial_rld.py)) and whole-root summary statistics ([`summary_statistics.py`](../deeprootgen/statistics/summary_statistics.py)) serve the dashboard and older calibration routes. They use different supports from the finite-cylinder operator.

## 15. Scoring and search

### 15.1 Physical core-placement loss

[`score_core_placement(training, held, predictions, top30_weight=1.0, cap_multiple=None)`](../deeprootgen/research/core_placement_cost.py) compares predicted and observed RLD on held-out core sections. Both tables need `core_id`, `z_lower_cm`, `z_upper_cm` (≤ 0 at the surface), `core_volume_cm3` and `rld_est`.

**Weights.** Every tube carries the same total weight. Within a tube, each section's weight is proportional to its effective volume. The shallow (0–30 cm) part of a section can be down-weighted by `top30_weight` in (0, 1].

Let o_i and p_i be the observed and predicted RLD, w_i the weights, and `ō_train` the weighted mean observed RLD of the **training** tubes.

```text
normalized_MAE = Σ w_i |o_i − p_i| / ō_train          (optionally capping each |o_i − p_i| at cap_multiple · ō_train)
joint_TV       = ½ Σ_i | w_i o_i / Σ w o  −  w_i p_i / Σ w p |
depth_TV       = ½ Σ_bands | Σ_{i in band} (share difference_i · fraction of i in band) |
loss           = 0.5 · normalized_MAE + 0.25 · joint_TV + 0.25 · depth_TV
```

- `joint_TV` detects roots at the wrong tube at the right depth.
- `depth_TV` marginalizes the signed share differences over tubes onto the union of all depth boundaries, so it detects roots placed too shallow or too deep.
- If one profile is empty and the other is not, both TV terms equal 1. If both are empty, they equal 0.
- A missed positive costs its full observed RLD, and a false hit costs its full predicted RLD. There is no separate constant miss penalty.

Lower loss is better. Report improvements as `gain % = 100 × (1 − candidate loss / matched reference loss)`, with matched seeds and the same observation support.

### 15.2 Presence diagnostics

[`core_presence(comparison, predictions, threshold_rld=0)`](../deeprootgen/research/core_presence.py) measures occupancy per realization before averaging. A hit is RLD greater than the threshold on either side. It returns:

| Output | Meaning |
|---|---|
| `observed_hit` | Weighted share of field sections with roots |
| `predicted_empty` | Weighted share of simulated sections with no qualifying roots |
| `miss_rate_given_observed_hit` | Simulated empties among field-positive sections |
| `false_hit_rate_given_observed_empty` | Simulated hits among field-zero sections |

Report miss and false-hit rates together, so filling every cylinder cannot pass as success.

### 15.3 Validation design

- **Whole-tube folds.** Keep complete tubes together in cross-validation, and normalize each fold by its own training tubes.
- **Reserved tubes.** Keep reserved tubes out of selection until a candidate is frozen.
- **Paired seeds.** Compare candidates on the same seeds. Confirm on fresh seeds that were not used in selection.
- **Benchmark.** A depth-only profile fitted on training tubes is a benchmark for what the architecture parameters add.
- **Interpretation.** New seeds measure simulator variability at the sampled locations. They do not measure transfer to other field vines.

### 15.4 Core-lattice search (`python -m deeprootgen core-search`)

[`core_lattice_scoring.py`](../deeprootgen/research/core_lattice_scoring.py) and [`core_lattice_search.py`](../deeprootgen/research/core_lattice_search.py), documented in [CORE_LATTICE_SEARCH.md](research/CORE_LATTICE_SEARCH.md).

| Spec key | Meaning |
|---|---|
| `base_config` | Schema-4 configuration every candidate starts from |
| `cores` | CSV path, equality `filter`, `exclude_cores` (must be absent, for example a hold-out), `frame` (column and sign for model x and y), `folds` (`k`, `seed`, `strata` listing every core once), optional `columns` |
| `lattice` | `x_spacing_cm`, `y_spacing_cm`, `extent` (1 gives 3 × 3) |
| `band_mm` | Diameter band, for example `[0.5, 2.5]` |
| `crown_kg` | Fixed below-ground mass added to each simulated vine's root mass |
| `dry_density_g_cm3` | Density used only for segment support |
| `objective` | `mass_band_kg`, `ratio_band`, `kg_weight`, `ratio_weight`, `locality_weight`, `top30_weight`, `cap_multiple` |
| `supports`, `ratios`, `guards`, `deep_top_cm`, `probes` | Named diagnostic supports and their ratios, guard rules, deep-recovery depth, attribution probes |
| `parameters` | Searched parameters with `kind`, bounds or choices, optional `log`, and configuration `edits` (`set`, `scale` or `choice`) |
| `arms`, `stages`, `limits` | Matched comparison sets, stage settings, worker count, per-run seconds and memory |

**Objective.**

```text
J = mean fold loss + kg_weight × (mean kg outside mass_band_kg)
                   + ratio_weight × (seed-mean RLD ratio units outside ratio_band)
                   + locality_weight × (relative violation of min/max ratio guards)
J = 2 + infeasible share   when any seed fails an organ, memory or time limit
```

The loss is reported with its three weighted components. Also reported are the ensemble (seed-mean) loss, the independent-neighbour loss, the mass mean and in-band count, and deep recovery of field positives with deep false hits.

**Stages.**

| Stage | What it does |
|---|---|
| `arms` | Named settings on common seeds, with paired per-seed changes against a baseline |
| `space` | A scrambled-Sobol design of 2^`log2_n` points |
| `tpe` | Sequential Optuna TPE trials with durable, resumable receipts. It can narrow the bounds from the best `space` designs and fix weakly ranked parameters. |
| `confirm` | Re-runs the top TPE trials and the baseline on confirmation seeds. It freezes the lowest-loss candidate that has finite scores, a complete successful seed panel and an explicit pass on every guard. If none qualifies it writes no frozen candidate and reports the lowest-J feasible diagnostic. |

Every run record carries the configuration hash, seed, source fingerprint, scorer version and cores digest. A cached record is reused only when all of these match. Outputs contain per-core predictions, so keep them local when the cores are private.

### 15.5 Dashboard and flows

The Dash application (`app/app.py`) has the pages Simulate, EDA, Optimisation, Sensitivity Analysis, ABC, SNPE, Surrogate, Deployments, **Architecture Search** and **Core Comparison**. Architecture Search applies ranges to the active controls of a saved schema-4 configuration. It compares the mean over paired seeds with numeric whole-root targets using normalized MAE or RMSE, through Optuna TPE or Latin-hypercube screening.

The Prefect flows in `app/flows/` are `run_simulation`, `run_optimisation`, `run_sensitivity_analysis`, `run_abc`, `run_snpe`, `run_surrogate` and `run_architecture_search`. They log to MLflow and can write to ArangoDB and object storage, so they are not side-effect-free checks. See [WEB_OPTIMISATION.md](WEB_OPTIMISATION.md) and [DASH_UI_EXAMPLES.md](DASH_UI_EXAMPLES.md).

## 16. Parameter glossary

### 16.1 Global parameters

These are the keys of `parameters`. Native fallbacks apply only while no feature law owns the quantity; `--explain-config` reports each one as `active`, `replaced` or `inactive`.

| Parameter | Units | Default | Definition |
|---|---|---|---|
| `max_order` | – | required | Highest root order; that order is terminal |
| `primary_root_count` | – | required | Number of first-order roots |
| `outer_primary_fraction` | fraction | 0.5 | Share of primaries in the outer group, rounded half up |
| `root_tissue_density` | g/cm³ | required | Scalar or diameter bands (section 7.4) |
| `min_branching_diameter_cm` | cm | 0.093 | Smallest local parent diameter that can start a daughter; 0 disables the check |
| `threshold_root_diameter_cm` | cm | 0.25 | Reporting split for whole-vine length and mass, and the fine/structural segment class |
| `root_ratio_length`, `root_ratio_biomass` | fraction | unset | Targets for the lower-class fractions; need `allocation_controls` |
| `allocation_controls` | – | unset | Per-order `[min, max]` scale ranges containing 1 |
| `daughters_per_parent` | – | unset | Native count: an integer or `{min, max_exclusive}` |
| `daughters_by_parent_order` | – | `{}` | Native fixed count per non-terminal parent order |
| `daughter_count_order_gain` | – | 0 | Native count growth with parent order, in [0, 1) |
| `min_primary_length`, `max_primary_length` | cm | unset | Native uniform primary length bounds |
| `min_lateral_length`, `max_lateral_length` | cm | unset | Native lateral length bounds |
| `length_reduction` | – | unset | Native lateral length factor per parent order |
| `base_diameter`, `apex_diameter` | cm | unset | Native cylinder diameter bounds |
| `diameter_reduction` | fraction | unset | Native diameter reduction per order |
| `segments_per_root` | – | unset (resolves to 1) | Native construction pieces per axis |
| `root_vary` | degrees | unset (resolves to 0) | Native local direction jitter |
| `interbranch_distance` | cm | unset | Native mean site spacing |
| `floor_threshold`, `ceiling_threshold` | fraction | 0.4, 0.9 | Native branch zone along the parent |
| `gravitropism` | – | unset | Legacy blend towards gravity, in [0, 1] |
| `max_val_attempts`, `no_root_zone` | –, cm | 50, 0.0001 | Legacy validation attempts and z threshold |
| `tropism_mode` | – | `legacy` | `legacy` or `fichtl2024` |
| `soil_surface_z_cm` | cm | 0 | Height of the soil surface in model z |
| `fichtl_probability_down`, `fichtl_sigma`, `fichtl_trials_type2`, `fichtl_trials_type3`, `fichtl_theta2_deg`, `fichtl_theta2_sd_deg`, `fichtl_theta3_deg`, `fichtl_theta3_sd_deg` | see [MODEL_REVIEW_GUIDE.md](MODEL_REVIEW_GUIDE.md#optional-fichtl-and-construction-controls) | unset | Fichtl kernel coefficients, required in `fichtl2024` mode |

Schema 4 rejects these keys in `parameters`: `random_seed` and `simulation_tag` (they are top-level); `root_ratio`, `mechanical_constraints`, `origin_min`, `origin_max` and `t` (no consumer); soil-grid display settings; and `research_*` aliases (use the feature blocks).

### 16.2 Per-order law parameters

| Law and parameter | Units | Definition |
|---|---|---|
| `lengths.k.mean`, `sd`, `min`, `max` | cm | Untruncated lognormal moments and acceptance bounds of contour length |
| `taper.k.base_cm`, `tip_cm` | cm | Basal and tip point diameters (fixed, nominal or a bounded distribution) |
| `taper.k.midpoint_diameter_fraction` | – | Position of the midpoint diameter between tip (0) and base (1) |
| `taper.k.rate_per_cm` | 1/cm | Exponential thinning rate of the thick part; `1 − exp(−10k)` is the loss per 10 cm |
| `taper.k.thick_min_cm` | cm | Diameter where the exponential part joins the thin taper |
| `branching.k.first_branch_cm` | cm | Distance along the parent from its base to the first daughter |
| `branching.k.branch_probability` | – | Probability that a parent branches at all |
| `branching.k.daughter_probabilities` | – | P(N = 1), P(N = 2), … for the family size of a branching parent |
| `branching.k.stratify_distal_sites` | – | One site per equal interval instead of independent uniform sites |
| `branching.k.basal_exclusion_cm`, `apical_exclusion_cm`, `mean_spacing_cm` | cm | Poisson-law zone and spacing |
| `curvature.k.step_cm` | cm | Integration step |
| `curvature.k.curvature_sd_rad_cm` | rad/cm | Bending magnitude |
| `curvature.k.correlation_length_cm` | cm | Bend persistence |
| `curvature.k.downward_drift_per_cm` | 1/cm | Downward pull |
| `curvature.k.insertion_mean_deg`, `insertion_sd_deg` | degrees | Angle between a daughter's first heading and the parent tangent |
| `curvature.k.row_alignment_per_cm` | 1/cm | Continuous alignment along the row |
| `curvature.k.sibling_sectors`, `deep_carrier` | – | Sections 9.5 and 10.2 |

### 16.3 Crown, placement and irrigation parameters

| Group | Parameters | Section |
|---|---|---|
| Crown | `primary_origins.layout`, `radius_cm`, `depth_range_cm`, `x_cm`, `y_cm`, `depth_cm`, `heading.*`, `azimuth_groups[*]`, catalogue `entries[*]` | 5 |
| Maturity | `cohort_maturity.groups[*]`, `length_power`, `diameter_power`, `scale_branch_probability` | 5.3 |
| Placement | `attachment_relocation.*`, `birth_depth_transfer.*`, `daughter_placement.*`, `insertion.row_axial_kappa_by_order` | 9 |
| Irrigation | `irrigation.*` | 11 |
| Limits | `limits.max_organs`, `max_nodes`, `max_stations`, `max_branch_proposals` | 17 |

### 16.4 Observation and scoring parameters

These belong to the comparison, not to the generator.

| Parameter | Units | Definition |
|---|---|---|
| Diameter band `band_mm` | mm | Root diameters counted in observed and simulated RLD |
| Core radius, depth interval, sampled volume | cm, cm, cm³ | Physical support of each observed section |
| Lattice spacing and extent | cm | Neighbouring planting positions summed into a prediction |
| `crown_kg` | kg | Below-ground crown or trunk mass added to root mass |
| `mass_band_kg`, `ratio_band` | kg, – | Whole-vine mass range and predicted/observed mean RLD range |
| `top30_weight`, `cap_multiple` | – | Shallow weighting and residual cap (sensitivity only) |
| Folds, reserved tubes, seed panels | – | Validation design (section 15.3) |

## 17. Reproducibility and limits

- **Seeds.** A fixed configuration and seed reproduce the same vine on the same source. Configurations that use keyed laws require an explicit seed.
- **Hashes.** `run_manifest.json` records `supplied_input_sha256`, `effective_model_sha256` and `run_identity_sha256`, together with output hashes and the source fingerprint.
- **Limits.** `limits.max_organs`, `max_nodes`, `max_stations` and `max_branch_proposals` fail the run when exceeded. The generator never truncates a root system silently.
- **Static model.** Results describe a hypothetical standing architecture, not a growth trajectory.

## 18. Other entry points and related documents

| Topic | Document |
|---|---|
| Worked schema-4 examples | [NATIVE_EXECUTION.md](NATIVE_EXECUTION.md) |
| Illustrated workflow from crown to core comparison | [ROOT_ARCHITECTURE_AND_SPATIAL_FITTING.md](ROOT_ARCHITECTURE_AND_SPATIAL_FITTING.md) |
| Input routes and the older parameter crosswalk | [INPUT_LAYERS_AND_MODEL_FLOW.md](INPUT_LAYERS_AND_MODEL_FLOW.md) |
| Native field dictionary and legacy research controls | [MODEL_REVIEW_GUIDE.md](MODEL_REVIEW_GUIDE.md) |
| Irrigation inputs and neighbourhoods | [research/IRRIGATION_INPUTS.md](research/IRRIGATION_INPUTS.md) |
| Spatial construction options | [research/SPATIAL_CONSTRUCTION_IMPLEMENTATION.md](research/SPATIAL_CONSTRUCTION_IMPLEMENTATION.md) |
| Placement experiments | [research/PLACEMENT_EXPERIMENT_OPTIONS.md](research/PLACEMENT_EXPERIMENT_OPTIONS.md) |
| Scoring guide | [ARCHITECTURE_SCORING.md](ARCHITECTURE_SCORING.md) |
| Core-lattice search | [research/CORE_LATTICE_SEARCH.md](research/CORE_LATTICE_SEARCH.md) |
| Measured and virtual core supports | [research/AREA_MEAN_CORE_METHOD.md](research/AREA_MEAN_CORE_METHOD.md) |
| Code map | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Historical (schema 1–3) contracts | [NATIVE_EXECUTION_V1_V3.md](NATIVE_EXECUTION_V1_V3.md) |
