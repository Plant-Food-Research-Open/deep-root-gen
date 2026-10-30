# Code review notes and validation backlog

Reviewed 2026-10-28 against `fc9136263eb7dff1b2e047d1cf3f0de8bdafbedf`.
Recheck current code before treating these as open defects. No fixes or
scientific changes were made in the documentation task.


This is bounded review, not a complete defect audit. No scientific behaviour
was changed. Probes below execute extracted source definitions with installed
NumPy/Pandas outside the supported environment; they support local arithmetic
findings, not end-to-end validation.

1. **Non-finite specific-root-length output with the default base row.**
   `RootNodeModel` defaults diameter/length to zero (:57–58), and
   `RootSystemGraph.__init__` includes that base node (:133–136).
   `TotalSpecificRootLength.calculate` at summary_statistics.py:444–449 divides
   each row's length by cylinder mass and sums, with no zero-mass/base-row
   exclusion. `AverageSpecificRootLength` repeats the operation (:478–485).
   A synthetic base row plus one nonzero segment returns `NaN`. Calibration
   uses the full `as_df()` table (:123) and logging iterates all statistics
   (`pipeline/experiment.py:223`), so finite-output checks are needed. Any
   proposed correction needs an agreed definition and units: a label of `cm`
   is insufficient for a length-per-mass statistic. Do not silently change
   the scientific formula.

2. **EDA distribution comparison drops the distribution.**
   `DepthDistribution.get_xy_comparison_data` (:195–197) and
   `RadialDistribution.get_xy_comparison_data` (:263–265) return bin boundaries,
   discarding the calculated CDF. EDA calls them at
   `app/pages/eda_root_system.py:605–606`. The probe's CDFs differ
   `[0, .75, 1]` versus `[0, .25, 1]`, yet both comparison vectors are `[0, 5]`.
   This can hide different spatial distributions in EDA. These methods were
   not found as direct callers in the inference flows; do not report that
   SNPE necessarily uses these erroneous vectors.

3. **Layer/column controls do not establish spatial calibration.**
   Form building stores `stat_by_soil_layer` and `stat_by_soil_column` at
   `form/components.py:675–676`; no consuming calculation was found in Python
   sources. `SummaryStatisticsModel.z_lower_bound/z_upper_bound` exist but
   `calculate_summary_statistics` (:126–139) computes whole-table scalars,
   ignores those bounds and skips tuple/list-valued distributions. A spatially
   labelled observation can therefore be compared against a whole-system
   statistic. This is a code-interface gap, not permission to implement a new
   scientific observation model.

4. **Zero primary-root counts can raise division by zero.**
   The form permits zero outer/inner roots. `position_primary_roots` calls
   `get_yaw` for each group even when that group is empty (:1159, :1169), and
   `get_yaw` does `360 / number_of_roots` (:796) without a guard. This is a
   static, directly traceable crash path; not exercised with the full model.

5. **Fixed simulation seed does not reproduce the whole inference pipeline.**
   `lhc_sample` seeds LatinHypercube (:112) but shuffles with
   `.sample(frac=1)` without `random_state` (:122), then assigns split labels.
   The Optuna TPESampler construction (`run_optimisation.py:80`) has no seed.
   The model uses `default_rng(random_seed)`; that alone does not reproduce
   train/validation/holdout membership or optimisation. GPU/training
   reproducibility also remains untested.

Further unverified concerns: the layer calculation uses strict inequalities,
so exact depth-boundary points are omitted (:98–100); its probe stopped at
`float.astype` in the installed Pandas environment, which is outside the
project constraints. Recheck against the pinned stack before classifying that
exception as a supported-environment defect. `invalid_root` is retained in
export and generic summary functions do not visibly filter it. Whether those
rows should contribute requires explicit scientific policy. The library
discrepancy helper also sums an empty distance list to zero; the dashboard
guards ordinary empty selections, so direct API contracts need their own
validation. No quantitative tolerance or biological pass threshold is inferred.


## Future observation compatibility

The user describes a local dataset of XYZ root locations, root length density
and biomass. Its schema and units have not been inspected or verified. Data
inspection and fitting are deferred, and raw data must stay local under the
protections in [AGENTS.md](../AGENTS.md).

The scalar summary-statistic and graph-node/edge interfaces do not establish
support for spatially sampled density observations. A source search in
`deeprootgen/` and `app/` Python/YAML found no explicit root-length-density or
biomass fields. `TotalWeight` calculates cylinder volume times tissue density;
that does not establish compatibility with measured biomass at XYZ locations.

A later, separately scoped local compatibility review needs coordinate frame,
z sign, units, sample/voxel support volume, root-class filters, replicate IDs,
dry/fresh biomass definition, tissue density provenance, missing-value semantics
and uncertainty. Mapping simulated segment lengths/mass to matching measured
support is a scientific observation-model decision, not an automatic column
rename. No calibration or optimisation is authorized by these notes.

## Small next steps for the independent project

1. Qualify an isolated Python 3.10 environment with a deliberately chosen Poetry
   version and the current lockfile. Stop for platform/lock failures; do not
   upgrade dependencies incidentally.
2. Reproduce the review findings on that pinned stack, using small synthetic
   frames and a tiny fixed-seed simulation. Establish graph IDs/edges, finite
   geometry and analytic length/volume/mass fixtures. The existing dummy test
   is not a baseline for model correctness.
3. Agree definitions, units and tolerances before any scientific fix. Review
   base/invalid-root policy, depth boundaries, distribution features and
   simulator/sampler/training seeds. Keep expected failures distinct from
   accepted biological behaviour.
4. Consider observation compatibility only in a later local data task. Do not
   start fitting, training, service deployment or a programme adapter here.

Use a bounded Python engineer task and a separate validation-review pass when
needed; these are responsibilities, not installed agents or standing paid
workers. The repository-local [Python skill](../.agents/skills/deeprootgen-python-engineering/SKILL.md)
provides source-specific guidance. Shared programme skills are optional routing
resources when available, not runtime dependencies of this independent project.

See [setup and evidence limits](DEVELOPMENT.md) and [architecture](ARCHITECTURE.md).
