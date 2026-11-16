# Local notebook search integration

This opt-in tool combines the upstream notebook's sequential Optuna search and
checkpointing with this checkout's controlled simulation routes and versioned
architecture comparison. It does not alter generator defaults, the sealed SO4
results, scientific tolerances, dependencies or biological qualification.

The implementation uses the installed Optuna dependency. It does not start
Dash, Prefect, MLflow, storage services or training. Outputs and observations
stay in a caller-selected local directory. No API keys or model calls are used.

## What was combined

| Notebook feature | Integration |
|---|---|
| Optuna TPE parameter proposals | Sequential ask/evaluate/tell, with more total trials than startup trials |
| Repeated stochastic simulations | Same explicit seeds for every candidate; each worker receives its own seed |
| Durable studies | SQLite plus atomic trial receipts and source/input/configuration identities |
| Comparison metrics | 13/15/17 positive traits for maximum order 3/4/5, and 3 full-support, normalized 10 cm profiles |
| Independent assessment stage | Separately invoked evaluation of a frozen candidate on predeclared fresh seeds |
| Offline notebook use | Thin notebook calls the same validated CLI; execution is opt-in |

Reviewed upstream methods at commit
[`24ee8d9e`](https://github.com/Plant-Food-Research-Open/deep-root-gen/commit/24ee8d9e677770b00d0206cdb93c1487304bf447).
The Fichtl sequential notebook's default five trials/twenty startup trials and
six-worker call are not copied. Its weighted voxel objective is not silently
substituted for the current architecture criteria. The Wong notebook offers
useful sequential-search patterns but its cylindrical-core observation contract
does not apply to excavated SO4 architectures. These are Optuna optimization
workflows, not neural posterior inference.

## First run with invented inputs

Use the supported Python 3.10 environment described in [RUNNING](../../RUNNING.md).
From the repository root:

```bash
python scripts/research/parameter_search.py \
  --config examples/research/search_synthetic.json \
  --outdir .runtime/search-synthetic-new
```

Without `--execute`, this validates input schemas and route compatibility and
creates no output directory. It cannot certify stochastic construction or a
scientific fit. The example reference is an invented three-organ graph, and
the generator parameters are invented test settings. This is an integration
demonstration, not a SO4 calibration or an expected acceptance pass.

```bash
python scripts/research/parameter_search.py \
  --config examples/research/search_synthetic.json \
  --outdir .runtime/search-synthetic-new --execute

python scripts/research/parameter_search.py \
  --config examples/research/search_synthetic.json \
  --outdir .runtime/search-synthetic-new --phase qualify --execute --resume
```

The same workflow is available in
[notebook 5](../../notebooks/grapevine_fichtl_2024/5_controlled_research_search.ipynb).
Its execution flags default to false. Qualification verifies the saved best
candidate against the study/receipt history before freezing its plan. It uses
the disjoint seeds already declared in the configuration; it cannot launch
another parameter search. Repeated completed qualification reads retained
samples. Failed or interrupted qualification seeds are consumed and are not
automatically retried.

## Configuration and observation contract

`parameters_file` and `reference_file` are relative to the config file, not the
notebook's current directory. The complete synthetic examples document the JSON
schema. Keep empirical parameter arrays and references out of source control.
Searches currently vary named top-level model parameters. Nested per-order
maps, origin catalogues and joint hierarchical distributions remain fixed
inputs; this tool does not invent a parameter decoder for them.

The reference records a population/vine ID, number of architectures, the
trait means, sparse profiles indexed by integer 10 cm bins, explicit
frame/operator/root-support identifiers and contiguous `root_orders: [1,...,m]`
for maximum order 3, 4 or 5. The original 13-trait order-3 contract is unchanged;
order 4 adds its count/mean length, and order 5 adds two more traits, with separate
comparison versions. Each profile
must sum to one. Zero/missing traits, unknown orders, nonfinite numbers and
ambiguous bins are rejected rather than silently dropping criteria. Caller
identifiers declare the observation contract; the software cannot prove that
an external CSV or its metadata has the correct physical meaning.

The bridge reuses the existing geometric-length, soil-clipping and summary
operators. It pads the union of observed and generated profile bins, so length
outside the observed profile range remains scored. It does not copy the older
notebooks' implicit depth=-z registration. The controlled routes require
surface_z=20 cm and use depth=20-z. Actual origin/scaffold inputs must already
be qualified for the selected observation contract.

Choose the simulation route explicitly:

- `graph_segments_v1`: existing controlled graph-segment arm D.
- `construction_steps_v1`: existing construction-step arm D, including its
  explicitly configured optional construction controls.

Both use the existing minimum-angle boundary projection. Every candidate/seed
constructs a fresh, hashed INITIAL. Shared seeds alone are not a guarantee of
the same biological-root pairing after topology changes. The old constructor
tag is retained for byte/behavior compatibility; diagnostics separately record
the requested tag, explicit route, INITIAL hash and run identity.

Both routes support orders through 5 with explicit higher-order direction
assumptions and matching parameter/reference scope. All represented orders
contribute to global metrics and profiles. The optional supplied-count
construction is separate from direction controls. See
[higher-order controls and provenance](HIGHER_ORDER_RESEARCH.md) for requirements,
equations, unsupported compositions and the distinction between conditioning
and prediction. `t` does not cause growth and cannot represent elapsed months.

The local D-04 starter bundle is
`.runtime/research/so4-t4-order5-20261115-v1/d04_bundle/search_config.private.json`.
Notebook 5 can select it explicitly; its execution flags still default to false.
The local bundle records the RSML nesting/class inconsistency, retained label
semantics and inactive biomass reference. It is a prepared conditional research
case, not a fitted or biologically qualified T4 model. Do not publish the bundle.

## Population versus individual reconstruction

`objective_mode` is mandatory:

- `population_mean`: average traits and per-architecture normalized profiles
  equally, then calculate the existing worst-criterion score J.
- `per_seed_mean`: calculate the existing J against the same reference for
  every generated architecture, then average those losses.

Both modes retain population and per-seed reports, every criterion and the
per-seed joint-pass fraction. Opposite seed errors may cancel in population
means; they cannot cancel before calculation of per-seed losses. No report
claims that a mean pass means every seed passes. A one-vine reference is
supported, but the current positive-trait/count requirements remain explicit.
Per-seed comparison is a reconstruction diagnostic, not new biological
validation or an automatically accepted individual-vine tolerance.

Measured scaffold geometry, counts or current-length CDFs supplied as inputs
must be labelled as conditioning, not independent predictions. A single best
seed is not silently selected. Fresh-seed evaluation assesses simulation
variability; withheld vines/branches require a separately declared design.
Biomass remains outside this objective until its scientific target and support
are qualified. The standalone mass audit remains available separately.

## Resume, failures and execution limits

The root CLI locks the experiment; search is sequential and each worker uses
two CPU threads. The total trial count includes failed/interrupted trials.
Successful TPE startup evaluations are required before adaptive proposals;
failure-heavy runs may still have no adaptive proposals despite a larger budget.

Each global trial number has a deterministic sampler seed; completed history
drives its proposal. Resume checks source, input, configuration, dependency and
seed identities. No pickle sampler state is loaded. A changed dependency,
source or objective requires a new directory/versioned experiment. Budget
extension also requires a separately recorded experiment, not editing an old
manifest. Common raw data must stay read-only.

Worker reservations and outcomes are recorded under `calls/`. Each worker has
an independent deadline and lock; resume refuses a live orphan worker and
marks abandoned calls without retry. Model calls are separately visible from
Optuna trials: a failed trial can have fewer completed seeds than requested.
The per-seed timeout includes process/import time. Invocation timeout limits
the current CLI call; total trials bound work across resumes. These controls
do not confer new scientific execution authority.

`output_stop_bytes` is an output admission threshold, not a filesystem quota.
The CLI reserves room for receipts/checkpoints and bounds serialized worker
samples; SQLite journals and terminal failure records still need disk space
after stopping. Use sufficient headroom under any independently imposed phase
storage cap. Budget/source stop conditions stop the invocation rather than
turning every remaining trial into an immediate failure. No historical sealed
output is overwritten or removed.

`search/summary.json` identifies the best completed trial and full parameters;
`search/trials/` retains losses and diagnostic vectors. `qualification_plan.json`
freezes the candidate and seeds; `qualification.json` contains fresh-seed
results. Full graphs are not stored by this compact search bridge: reproduce
the chosen parameters/seed/route with the recorded source epoch when a graph
artifact is needed. No graph is formed by averaging coordinates across seeds.

## Validation

Tests cover analytic geometry and legacy metric parity, positive/order support,
full-bin unions, population cancellation versus per-seed loss, both controlled
routes, changed-construction identity, sequential search, failure accounting,
identity-mismatch rejection, interruption recovery, sampler resume behavior,
best-candidate verification, seed propagation, deadline and output admission
controls. Invented fixtures and synthetic runtime checks do not establish a
biological fit. Current execution receipts belong to the local task output;
do not transfer historical test counts to a later source revision.

## Separate mature-root cohort route

The later [cohort constructor](COHORT_ROOT_CONSTRUCTION.md) is an explicit
research API, not another native `RootSimulationModel` configuration. The
notebook's existing native/controlled routes do not automatically support its
crown graph, cohort dictionary or observation projection. Use its separate
source-bound runner and root-only projection. No notebook search default or
accepted SO4 configuration changes as part of this extension.
