# Architecture and code map

For an illustrated walkthrough from crown emergence to field comparison, read [How DeepRootGen builds and fits grapevine root systems](ROOT_ARCHITECTURE_AND_SPATIAL_FITTING.md).

Fresh generation uses one [schema-4 input](NATIVE_EXECUTION.md).
[`RootConfig`](../deeprootgen/data_model/canonical.py) validates the document.
The [resolver](../deeprootgen/data_model/resolution.py) identifies the active
calculations and their parameter consumers. The
[engine](../deeprootgen/model/engine.py) constructs and materializes the same
axis state across native and feature-selected calculations. Branching,
direction, crown placement, length and material settings each have their
own rules. The CLI, Simulation page and notebook helpers share this
generation contract.

Use the [migration guide](research/SINGLE_INPUT_MIGRATION.md) for older
generation inputs and the [historical contracts](NATIVE_EXECUTION_V1_V3.md)
for exact replay. The [repair report](research/NATIVE_ENGINE_REPAIR_REPORT.md)
records the observer, geometry and material changes. Observation and
calibration take place downstream of the generated root system. The
[workflow guide](source/usage/native_workflow.rst) describes what to run.

For further AI-assisted changes, start with the [AI coding guide](AI_CODING_GUIDE.md)
and [lessons learned](AI_CODING_LESSONS.md). They distinguish preserved contracts,
current implementation and the proposed single-engine architecture.

The [input-layer diagrams](INPUT_LAYERS_AND_MODEL_FLOW.md) and source map
below retain the historical interfaces alongside the current generation guide.

Reviewed 2026-10-28 against code revision
`fc9136263eb7dff1b2e047d1cf3f0de8bdafbedf`. Paths below are relative to this
repository. This is a source map, not proof that the application runs locally.

DeepRootGen is maintained as an independent Codex project. Use this repository
as the project root. Its Python simulation, schemas and inference services have
their own environment and validation needs. No FruitCropXL supervisor adapter,
agent installation or automatic worker dispatch is part of this documentation
change. Parent programme instructions still apply when this checkout is inside
that workspace; programme registry/configuration changes belong to their owner.

The inspected local directory is `13-deep-root-gen-PFR-open`, with origin
`git@github.com:junqi108/deep-root-gen-PFR-open.git`. The parent registry still
names `13-deep-root-gen`; report that mismatch to its owner rather than renaming
the checkout or editing central configuration as a side effect.

## Source map


| Source | Responsibility and boundary |
|---|---|
| `deeprootgen/model/root.py:24`, `:759`, `:1215` | RootOrgan and RootSystemSimulation. `run(parameters)` initializes organs, grows, positions secondary/primary roots and applies geometric plausibility checks. This is the direct in-memory simulation entrypoint. |
| `deeprootgen/model/hgraph.py:119` | RootSystemGraph, node/edge ID allocation, `as_df()` at :218, NetworkX at :230, PyTorch Geometric at :281. Imports Torch/PyG eagerly. |
| `deeprootgen/model/soil.py`, `spatial/transform.py` | Soil grid/visualisation and rotation/translation matrices. Soil display does not establish a measured-density observation operator. |
| `deeprootgen/data_model/simulation_data_models.py:79` | Required typed simulation parameters; calibration intervals at :172 and calibration request model at :206. Pydantic typing is not a comprehensive scientific range validator. |
| `deeprootgen/statistics/summary_statistics.py` | Length, diameter, cylinder volume, tissue-density-derived weight, specific root length, depth/horizontal distributions and hull statistics. Display labels imply cm and g; form configuration labels tissue density as g/cm³. |
| `deeprootgen/statistics/distance_metrics.py` | Vector distances, including L1 and sklearn error measures. |
| `deeprootgen/calibration/summary_statistics.py:22`, `:100`, `:147` | Select observed scalar statistics, run simulation and compute discrepancies. These are the core optimisation/ABC/surrogate summary-statistic interfaces. |
| `deeprootgen/calibration/parameters.py:75`, `surrogates.py`, `model_versioning.py` | Latin-hypercube samples and splits; GP/training utilities; MLflow model wrappers and graph/neural feature models. |
| `app/app.py` | Dash application and `server` for Gunicorn. Hydra composes `app/conf/config.yaml`; pages are registered from `app/pages/`. Direct script binds port 8000 on all interfaces. No package CLI is declared in pyproject.toml. |
| `app/pages/*_root_system.py`, `deeprootgen/form/components.py:597` | Dashboard form validation/configuration, uploads, EDA and dispatch. Dispatch calls Prefect deployments through `pipeline/experiment.py:357`. |
| `app/flows/run_simulation.py:78` | `run_simulation_flow(input_parameters, simulation_uuid)`; constructs simulator, logs to MLflow, saves graph to ArangoDB. This is not a side-effect-free smoke entrypoint. |
| `app/flows/run_optimisation.py:295`, `run_sensitivity_analysis.py:320`, `run_abc.py:372`, `run_snpe.py:641`, `run_surrogate.py:449` | Prefect flow entrypoints for Optuna, sensitivity analysis, ABC, SNPE and surrogate training. All unexecuted during this review. |
| `app/flows/prefect.yaml` | The single dashboard deployment manifest: seven deployment entrypoints (including Architecture Search) with container `/app/flows/…` paths. Root `prefect.yaml` is an older scaffold referring to absent `app/flows/test_flow.py`; do not use it as the working deployment manifest. |
| `deeprootgen/pipeline/experiment.py:29`, `:180`; `io/simulation_data.py` | Output directory hard-coded to `/app/outputs`; node/edge CSVs, plots/profile and summary CSVs logged to MLflow. Explicit S3 upload helper and ArangoDB persistence exist. |
| `app/deployments/*_service.py`, `docker-compose.model-deploy.yaml` | BentoML inference services; import can load latest stored models. These consume existing artifacts and are not a setup test. |
| `docker-compose.yaml`, `dockerfiles/`, `apptainer/` | Full application/service infrastructure: Dash, MLflow, Prefect server/worker/deployment bootstrap, Postgres, MinIO and bucket bootstrap, ArangoDB, plus CloudBeaver and Metabase. Not started. |
| `docs/source/`, `scripts/docs/create.sh` | Sphinx introduction and API reference; documentation build imports project modules and the helper deletes/recreates an `html` directory. Not run. |

The current export is a **node table plus edge table**, different from the README schema at the
reviewed code revision. `RootNodeModel` has `node_id`, `parent_id`, `plant_id`, `organ_id`,
`x/y/z`, `order`, `segment_rank`, `diameter`, `length`, `root_tissue_density`,
`root_type`, `order_type`, `position_type`, `simulation_tag`, `invalid_root`.
Edges have `parent_id` and `child_id`. Root type is represented by strings such
as `structural`/`fine`; The earlier README described numeric codes and
`id`/`parent`/`coordinates` columns; the current README now documents the
node/edge schema. Preserve current serialization until a downstream
consumer is inspected. The historical GroIMP/XEG reference alone does not prove a
currently compatible importer.


## Validation boundaries

### Optional offline research interfaces (16 November 2026)

The source map above retains its historical review date. The following local
research modules were inspected separately on 16 November; their presence does
not imply integration with the native calibration, Dash or Prefect routes.

| Source | Responsibility and boundary |
|---|---|
| `deeprootgen/research/cohort_root_generator.py` | `CohortRootGenerator.generate()` constructs a static five-order architecture with distributed crown emergence, hypothetical maturity cohorts, physical-step curvature, attachment rules and integrated taper volume. Returns a full crown support graph, a root-only observation projection, organ records and diagnostics. |
| `deeprootgen/research/curvature_process.py`, `physical_step_replay.py`, `primary_curvature.py` | Correlated curvature primitives and separate optional replay/primary construction interfaces. The order-2-and-above physical replay and the cohort constructor have different primary-root handling; inspect the selected route before applying parameters. |
| `deeprootgen/research/core_observation.py`, `mass_audit.py` | Qualified geometric root-segment support, finite cylindrical-core predictions and represented root-axis material audits. Crown mass needs a separate explicit term. |
| `deeprootgen/research/area_mean_observation.py` | Virtual-core and pooling utilities for separately declared spatial supports. Enlarged windows do not enlarge actual measured samples. |
| `deeprootgen/research/order_mass_allocation.py` | Separate diagnostic/material-allocation research API. Its constraints and rescaling semantics are not automatically part of the cohort constructor. |

The full cohort crown graph contains nonmaterial connector edges. Use
`observation_nodes` and `observation_edges` for root-only operators. Their
`plant_id` values identify **primary trees**, not independent vines; sum trees
for a single vine and supply crown mass separately. Equivalent-cylinder segment
diameters conserve taper volume and differ from point basal or mid-axis diameter.

Read the [cohort construction contract](research/COHORT_ROOT_CONSTRUCTION.md),
[optimization guide](research/OPTIMIZATION_GUIDE.md), and
[research interfaces](research/README.md) and the
[active Calvin state](research/ACTIVE_CALVIN_RESEARCH.md) before continuing that
research. Empirical settings and comparisons remain in excluded local folders.

Direct simulation is the smallest prospective offline runtime check, but its
imports still require the locked Python/Torch stack. A full Prefect flow adds
tracking, storage and database effects; BentoML services load existing model
artifacts. Keep those layers distinct when diagnosing a failure.

See [development and setup](DEVELOPMENT.md) for executed versus prospective
commands and [review notes](REVIEW_NOTES.md) for known issues to recheck before
trusting scientific outputs. See [agent guidance](../AGENTS.md) for task scope
and local-data protections.
