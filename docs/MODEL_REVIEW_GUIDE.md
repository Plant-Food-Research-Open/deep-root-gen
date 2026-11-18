# Model configurations, inputs and review workflow

This guide describes optional interfaces integrated with the 1.0 offline runtime.
Native defaults remain available. Empirical calibration files and validation
receipts are caller-owned local inputs; these interfaces do not establish
biological qualification. See [research interfaces](research/README.md).

17 November integration update: [native execution and compatibility contracts](NATIVE_EXECUTION.md)
now describe the supported engine. The route diagrams below retain the
pre-consolidation source review; cohort generation and fresh SO4 construction-step
samples now execute through native `RootSystemSimulation.run()`.

For diagrams of how these interfaces connect and which functions they share,
start with [input layers and detailed model flow](INPUT_LAYERS_AND_MODEL_FLOW.md).
Its parameter crosswalk compares the same architectural controls across routes.

Source review: 16 November 2026, local revision
`3672959b6460bd9b06170bee0c8fdbd48b1e5d31`. Since 18 November
2026 that local work, including the single native engine, is merged into main;
see [native execution](NATIVE_EXECUTION.md). No model parameters or scientific defaults were
changed by this documentation update.

## Choose the interface first

| Route | Configuration and entrypoint | Intended review |
|---|---|---|
| Native static model, default `legacy` | JSON accepted by `RootSimulationModel`; `RootSystemSimulation.run(parameters)` or `python -m deeprootgen simulate` | Basic geometry, topology, parameters, deterministic synthetic examples |
| Native optional `fichtl2024` | Same schema, with explicit Fichtl coefficients and `gravitropism=0` | Static direction/insertion hypotheses; not exact CPlantBox growth |
| Controlled SO4 replay | Saved INITIAL plus explicitly named construction/replay route; [method](research/SO4_CONTROLLED_METHOD.md) and [construction steps](research/SO4_CONSTRUCTION_STEP_REPLAY_HYPOTHESIS.md) | Matched architecture comparisons, with authenticated construction and RNG provenance |
| Mature-vine cohort research | Separate dictionary to `CohortRootGenerator(config).generate(seed, older_count, later_count)` | Five-order, curved, distributed crown-origin architectures and material accounting |
| Dash / Prefect / inference | Hydra `app/conf`, pages, flows and stored models | Application workflows with storage/database effects; separately qualified from offline model review |

The native `run()` currently leaves `self.grow(...)` commented out. It builds
and positions a static architecture; `t` does not make that entrypoint a
time-evolving growth model. Cohort maturity is also a static latent capacity,
not an inferred age in years. A density or biomass match does not establish
unique recovered topology or biological qualification.

## Native parameter dictionary

Source: [schema](../deeprootgen/data_model/simulation_data_models.py),
[construction](../deeprootgen/model/root.py), and
[branch placement](../deeprootgen/utils/branching.py).
The first table lists all required fields, using the checked-in
[tiny synthetic input](../examples/synthetic_minimal.json) as a concrete
example. These values are plumbing inputs, not a calibrated vine. Schema
acceptance alone does not establish scientifically sensible ranges.

| Input | Synthetic value | Meaning and units |
|---|---:|---|
| `random_seed` | 42 | Integer random seed; use a fresh simulator per realization and the same seed in the schema and constructor |
| `max_order` | 1 | Maximum branching order; primaries are order 1, base is order 0 |
| `root_ratio` | 0.5 | Retained schema field; no runtime consumer found in the current model; does not impose a root/shoot or mass ratio |
| `fine_root_threshold` | 0.06 | cm; native daughter-organ class uses mean constructed diameter, rather than splitting every segment at the threshold |
| `outer_root_num`, `inner_root_num` | 1, 1 | Counts of outer/inner primary groups; not measured vine counts |
| `min_primary_length`, `max_primary_length` | 20, 30 | cm; uniform primary contour-length draw before placement |
| `base_diameter` | 0.11 | cm; native basal diameter scale |
| `diameter_reduction` | 0.2 | Dimensionless reduction: initial diameter scale is `base_diameter*(1-diameter_reduction)**parent_order`; daughter attachment adds an inherited term |
| `apex_diameter` | 0.02 | cm; other bound of native segment-diameter draws, sorted from large to small; not the cohort taper law |
| `min_sec_root_num`, `max_sec_root_num` | 1, 2 | Base daughter-count interval; upper bound is exclusive, except equal endpoints produce the fixed count; physical spacing can further limit actual branches |
| `growth_sec_root` | 0.2 | `[0,1)`; requested count at parent order k is `ceil(n*(1-growth_sec_root)**(-(k-1)))`; a static count multiplier |
| `min_sec_root_length`, `max_sec_root_length` | 10, 20 | cm; nonprimary base length interval before order reduction and any inherited attachment-length addition |
| `segments_per_root` | 5 | Initial direction/length pieces per organ; attachment subdivision can add graph nodes |
| `length_reduction` | 0.5 | Nonprimary interval multiplied by `length_reduction**parent_order`; optional current-length CDFs replace that length law for selected orders |
| `root_vary` | 30 | Degrees; native local pitch/yaw jitter, not smooth correlated curvature |
| `interbranch_distance` | 0.0078 | cm; mean lognormal distance between lateral insertion sites within the permitted branch zone |
| `mechanical_constraints` | 0.5 | Retained schema field; no current runtime consumer found; not a calibrated soil-mechanics response |
| `root_tissue_density` | 0.05 | g/cm³; geometry-derived mass multiplier, not a direct biomass observation |
| `gravitropism` | 0.1 | Legacy direction blend in `[0,1]`; zero disables it; must be zero in `fichtl2024` mode |
| `t` | 0 | Retained iteration field; growth is not called by current `run()` |

Native optional fields and their schema defaults:

| Input | Default | Meaning |
|---|---|---|
| `origin_min`, `origin_max` | 0.001, 0.01 | Retained schema fields with no current model consumer; use the explicit research origin controls when qualified |
| `enable_soil` | false | Adds the visual soil grid; not a water/nutrient/soil-growth model |
| `soil_layer_height`, `soil_layer_width` | 0, 0 | cm; grid cell dimensions when rendering soil |
| `soil_n_layers`, `soil_n_cols` | 0, 0 | Display-grid counts; supply valid positive geometry when enabling soil |
| `max_val_attempts` | 50 | Maximum geometric validation/reorientation attempts |
| `simulation_tag` | `default` | Output metadata label |
| `no_root_zone` | 0.0001 | Legacy z-coordinate threshold in cm for geometric validation; Fichtl uses the explicit surface convention |
| `floor_threshold`, `ceiling_threshold` | 0.4, 0.9 | Fractions of parent contour length bounding the branch zone; require `0 <= floor < ceiling <= 1` |
| `tropism_mode` | `legacy` | Selects native legacy or optional `fichtl2024` kernel |
| `soil_surface_z_cm` | 0 | cm, model z upward; depth is `soil_surface_z_cm-z`; a nonzero offset requires the aligned offline observation route and disallows built-in soil rendering |

Native root class strings and the cohort's pointwise diameter compartments are
different definitions. Keep topology order, fine/coarse diameter class and
organ position group separate.

### Optional Fichtl and construction controls

All coefficients below default to `None` unless indicated. Supply the eight
`fichtl_*` coefficients explicitly when choosing `fichtl2024`. They are not
automatically estimated from field data.

| Input | Meaning |
|---|---|
| `fichtl_probability_down` | Probability `[0,1]` of selecting a downward rather than horizontal objective for order 2 |
| `fichtl_sigma` | Turning scale in rad/√cm: `alpha = sigma*sqrt(length_cm)*Z` |
| `fichtl_trials_type2`, `fichtl_trials_type3` | Nonnegative search-effort coefficients; additional candidates scale with √segment length using stochastic rounding; not a literal fixed trial count |
| `fichtl_theta2_deg`, `fichtl_theta3_deg` | Insertion-angle means relative to parent heading in degrees, constrained to 0–90 |
| `fichtl_theta2_sd_deg`, `fichtl_theta3_sd_deg` | SDs before truncated insertion-angle sampling, in degrees |
| `research_fichtl_sigma_by_order` | Optional order-to-sigma overrides; same units as global sigma; unavailable in legacy mode |
| `research_branch_placement` | Default `legacy_spacing`; `redistribute_capped` spreads the retained capped sites through the permitted zone |
| `research_current_length_cdfs_cm` | Order-keyed CDFs with `lengths_cm` and `cumulative_probabilities`; explicit current contour lengths, supported orders 2–5 locally; retain exact config and seed |
| `research_current_length_grid` | Only active value `construction_steps_v1`; direction stations independent of attachment cuts; requires the named controlled route, Fichtl, explicit seed and exact CDF coverage |
| `research_parent2_branch_zone_cm` | `basal_cm`, `apical_cm`, `spacing_cm` for tertiary sites on current order-2 contour length; controlled construction scope |
| `research_tertiary_length_rank_strength` | `[0,1]`; reassigns a fixed sibling length pool toward longer proximal daughters; affects length/diameter covariance; controlled route only |
| `research_insertion_row_axial_kappa` | Order-keyed concentration around the row axis; changes azimuth while preserving polar insertion angles; seeded Fichtl scope |
| `research_primary_yaw_mean_deg`, `research_primary_yaw_kappa` | Paired primary orientation controls: circular mean in degrees from model x toward y and dimensionless von Mises concentration |
| `research_primary_yaw_reverse_probability` | Keyed probability of a π yaw reversal; requires the explicit paired yaw controls; changes construction identity |
| `research_primary_inclination_bias` | `[0,1]` rigid downward inclination bias applied to complete primary subtrees; not degrees |
| `research_primary_attachment_distal_fraction` | `b` in `[0,1)` moves existing attachment arc s to `b*L+(1-b)*s`, preserving the primary curve; controlled research route; distal need not mean deeper |
| `research_base_origin_x_cm`, `research_base_origin_y_cm`, `research_base_depth_cm` | Supply together with explicit surface; x/y translations and positive depth below that surface; Fichtl scope |
| `research_primary_design` | Explicit primary list: `primary_id`, `category`, `length_cm`, `diameter_base_cm`, `diameter_apex_cm`, `inclination_deg`, `azimuth_deg`; diameters specify first/last incoming construction cylinders, orientation specifies the initial chord; see [five-order method](research/FIVE_ORDER_PRIMARY_AND_MASS_METHOD.md) for compatibility limits |
| `research_primary_branch_zone_cm` | `start_cm`, `end_cm` bounding a physical primary branch zone, clipped by current length; [contract](research/FIVE_ORDER_PRIMARY_AND_MASS_METHOD.md) distinguishes it from normalized fractions |
| `research_primary_branch_fractions` | Explicit normalized primary attachment positions; supplied count quotas must agree; [contract](research/PRIMARY_BRANCH_FRACTIONS.md) |
| `research_higher_order_tropism` | Explicit direction assumptions for higher orders; [higher-order scope](research/HIGHER_ORDER_RESEARCH.md) |
| `research_root_counts_by_order` | Exact supplied topology conditioning, not a predicted count distribution; [higher-order scope](research/HIGHER_ORDER_RESEARCH.md) |

These options are not freely composable. Schema and route validators reject
unsupported combinations. In particular, a construction-step or distal/rank
configuration cannot be passed to ordinary `run()`/`simulate`. Public PR15
predates some local five-order and cohort capabilities.

## Cohort research configuration dictionary

Source: [constructor](../deeprootgen/research/cohort_root_generator.py),
[construction contract](research/COHORT_ROOT_CONSTRUCTION.md), and
[invented complete fixture](../tests/test_cohort_root_generator.py).
Current version string: `cohort-root-research-v5`. Required biological inputs
come from the caller; there is no adopted default mature-vine parameter set.

| Global input | Meaning and units |
|---|---|
| `step_cm` | Physical direction integration spacing, cm; attachment/material cuts do not add direction draws |
| `dry_density_g_cm3` | Explicit dry density in g/cm³; mass is proportional to it |
| `fine_cutoff_mm` | Diameter threshold in mm; split taper at crossings and account fine/coarse material separately |
| `max_organs` | Positive integer allocation budget; exceeding it raises an error rather than silently truncating roots |
| `crown_mass_g` | Separate nonnegative underground crown/rootstock mass, g; not inferred from connector geometry |
| `unrepresented_fine_mass_g` | Optional separate diagnostic mass, default 0; cannot invent its spatial RLD |
| `crown_depth_cm` | `[minimum, maximum]` positive-down emergence depths; internal coordinates use z upward and soil at zero |
| `crown_radius_cm` | Emergence disk radius, cm; sampled radius uses `R*sqrt(U)` |
| `later_maturity` | `[minimum, maximum]` uniform latent maturity for later-origin cohort, within `(0,1]`; established cohort has maturity 1 |
| `maturity_length_power`, `maturity_diameter_power` | Exponents multiplying bounded length and basal diameter by `maturity**power` |
| `child_diameter_fraction_max` | `(0,1]` maximum child basal diameter as a fraction of parent point diameter at attachment |
| `inclination_mean_deg`, `inclination_sd_deg`, `inclination_bounds_deg` | Truncated-normal initial primary inclination; zero horizontal, positive downward; input moments precede truncation |
| `insertion_mean_deg`, `insertion_sd_deg` | Lateral insertion relative to incoming parent tangent, degrees; truncated-angle sampling |
| `reconcile_length_metadata` | Optional false by default; bounded floating-point metadata reconciliation, with diagnostics; never moves geometry or biological sites |
| `orders` | Exactly string keys `"1"` through `"5"`, each containing the rule below |

| Per-order input | Meaning and units |
|---|---|
| `length_cm` | Positive bounded-lognormal whole-axis contour length, with `mean`, `sd`, `min`, `max` in cm |
| `base_diameter_cm`, `tip_diameter_cm` | Separate bounded-lognormal point-diameter distributions, cm; base is maturity-scaled and parent-capped, tip is clamped to base |
| `first_branch_cm` | Separate bounded-lognormal first-branch arc distance, cm; a draw at/beyond the tip leaves the axis unbranched |
| `branch_probability` | Probability multiplied by latent maturity; order 5 is terminal regardless |
| `daughter_probabilities` | Array of probabilities for counts **1 through N**, summing to 1; zero probability of branching belongs in `branch_probability`; additional daughter sites are uniform after the first site |
| `curvature_sd_rad_cm` | Stationary per-component OU curvature SD, rad/cm; the state starts at zero at each organ base and after reflection |
| `correlation_cm` | Positive curvature correlation length, cm; larger values prolong curvature persistence |
| `downward_drift_per_cm` | Nonnegative downward heading drift coefficient, 1/cm; require `step_cm*drift < 1` |
| `midpoint_fraction` | Optional 0.5; `(0,1)` diameter interpolation fraction: `d_mid = d_tip + f*(d_base-d_tip)`; not a biomass fraction |

For every bounded-lognormal dictionary, mean/SD refer to the untruncated
distribution. Truncation, maturity, attachment caps and branching censoring
change realized summaries. Report both inputs and realized quantities.

`generate(seed, older_count, later_count)` takes nonnegative integer seed/counts
and requires at least one established primary. Both cohorts start at order 1.
Same seed means repeatability with the same configuration/source; changing
rejection sampling or topology can change later draws and organ identities.

The returned full graph includes nonmaterial crown connectors. Use
`observation_nodes` and `observation_edges` for root-only operators. Projection
`plant_id` means a primary tree; sum all such trees for one vine. Use the
`organs` table for biological counts, point diameters and contour lengths.
Extra segment nodes do not represent extra biological roots.

For each taper interval h with endpoint diameters a,b (all cm):

```text
volume_cm3 = pi*h*(a*a + a*b + b*b)/12
exported_equivalent_diameter_cm = sqrt((a*a + a*b + b*b)/3)
dry_mass_g = volume_cm3 * dry_density_g_cm3
whole_total_g = represented_root_axes_g + crown_mass_g + unrepresented_fine_mass_g
```

Do not interpret exported equivalent-cylinder diameter as measured basal or
midpoint diameter. Report the fine-share denominator explicitly, including
crown and any unrepresented term.

## How to review the model

1. **Start with saved evidence.** Read the [interface contracts](research/README.md) and the
   [active Calvin state](research/ACTIVE_CALVIN_RESEARCH.md) or
   [active SO4 state](research/ACTIVE_SO4_RESEARCH.md), then your local source-bound
   experiment report. Inspect the retained graphs and figures before generating replacements.
2. **Freeze identity and support.** Record source hashes, lock, interpreter,
   input bytes, seed list, constructor route, coordinate axes, soil surface,
   diameter units/class cutoff and mass denominator. For SO4 use the qualified
   `grapevine3d-soil-frame-v2` contract, not older base-aligned grids.
3. **Audit construction.** Check positive finite segments, graph connectivity,
   parent links, order/cohort counts, physical versus stored lengths, material
   conservation, clipping/reflections, branch censoring and diameter-cap counts.
   Inspect literal paths; visual smoothing is not a model correction.
4. **Audit material.** Compare basal and midpoint anatomy with matching
   measurements; keep fine/coarse mass by diameter separate from root order.
   Crown contributes once. Review density provenance, not just total mass.
5. **Audit observation support.** Use exact finite-cylinder intersections at
   sampled cores; sampled zero and unsampled are different. RLD is cm/cm³.
   Show subject and neighbour contributions separately. Larger virtual windows
   are conditional area-mean proxies, not newly measured soil volume; see the
   [area-mean contract](research/AREA_MEAN_CORE_METHOD.md).
6. **Review populations and limitations.** Show individual-seed variability,
   separately frozen fresh seeds and every criterion/residual. A selected
   successful realization does not qualify a population. Geometry tests,
   mass conditions, spatial agreement and biological validation are distinct.

Keep empirical settings, saved-view links and comparison reports in ignored local directories.
For the current local Calvin settings, open
`Calvin_Current_Best_Review_2026-11-16/REVIEW_USAGE.md` for saved-view links and
the full configuration tables, then
`REVIEW_REPORT.md`, `SIMULATION_SETTINGS.json` and `ORDER_SETTINGS.csv` in the
same folder. Exact empirical JSON inputs and comparison outputs stay ignored
and local. The current configurations remain experimental and unadopted.

### Small offline technical review

Reuse the existing qualified Python 3.10 environment; no install, dependency
upgrade, services, fitting or calibration is needed for this synthetic example:

```bash
source .runtime/envs/py310-qualification/bin/activate
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
# Existing pinned overlay used for current source qualification:
export PYTHONPATH="$PWD/.runtime/research/so4-t2-diagnostic-20261114-v1/locked-overlay:$PWD"
review_dir=$(mktemp -d .runtime/model-review.XXXXXX)
python -m deeprootgen simulate \
  --config examples/synthetic_minimal.json --outdir "$review_dir/native"
```

The CLI writes `nodes.csv`, `edges.csv`, resolved `parameters.json`,
`roots.html` and `run_manifest.json` to a new directory and refuses to
overwrite one. Review geometry and the manifest together. This synthetic
input exercises only primaries; it cannot qualify lateral branching or Calvin
biology. [RUNNING.md](../RUNNING.md) separates historical service checks from
current offline tests and documents clean-environment setup.

For a tiny invented cohort check without empirical data, use the complete
fixture in `tests/test_cohort_root_generator.py`; targeted test commands and
the [research guide](research/README.md) describes the numerical checks; fresh
results are in [integration status](PR_INTEGRATION_STATUS.md). The
ordinary CLI accepts native model JSON, not cohort dictionaries. Cohort
regeneration requires its separate API and a source/configuration identity
check; use saved outputs for routine scientific review.
