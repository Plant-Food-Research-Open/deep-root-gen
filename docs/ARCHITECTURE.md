# Architecture and code map

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
| `app/flows/prefect.yaml` | Six actual deployment entrypoints with container `/app/flows/…` paths. Root `prefect.yaml` is an older scaffold referring to absent `app/flows/test_flow.py`; do not use it as the working deployment manifest. |
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

Direct simulation is the smallest prospective offline runtime check, but its
imports still require the locked Python/Torch stack. A full Prefect flow adds
tracking, storage and database effects; BentoML services load existing model
artifacts. Keep those layers distinct when diagnosing a failure.

See [development and setup](DEVELOPMENT.md) for executed versus prospective
commands and [review notes](REVIEW_NOTES.md) for known issues to recheck before
trusting scientific outputs. See [agent guidance](../AGENTS.md) for task scope
and local-data protections.
