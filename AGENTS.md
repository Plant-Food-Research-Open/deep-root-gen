# DeepRootGen

Work in this independently versioned Python repository as its own Codex project.
Preserve inherited instructions: when present, read `../AGENTS.md`,
`../.agents/ROUTING.md` and `../.agents/SHARED_RESOURCES.md`. This file supplements
their scientific/data protections and does not grant cross-repository authority.
Preserve CONTRIBUTING.md and CODE_OF_CONDUCT.md.

## Ownership and task scope

This repository owns the root generator, schemas/statistics, Dash application,
Prefect flows and inference services. Programme registry/configuration and the
FruitCropXL supervisor belong to their own repositories. The verified local
directory is `13-deep-root-gen-PFR-open`; do not rename it to satisfy a stale
programme reference. Do not force GroIMP/XL contracts onto the Python runtime.

Follow the active task scope. Documentation/setup work does not authorize
scientific changes, calibration adoption, fitting, dependency upgrades, service
deployment, programme adapters or new autonomous/paid agents. Current direction
is an independent Codex project; no supervisor integration is enabled.

## Start with source and environment

- Record revision/status and preserve intervening work before edits.
- Read [architecture](docs/ARCHITECTURE.md) and inspect the relevant source.
  Simulation entrypoint: `RootSystemSimulation.run(RootSimulationModel(...))`.
  UI: `app/app.py`, `app/pages/`, Hydra `app/conf/`. Flows: `app/flows/`.
- Inspect pyproject.toml, poetry.lock, CI/container recipes and pytest settings
  before selecting commands. Current Python constraint is `>=3.10,<3.11`;
  the graph module eagerly imports Torch/PyG. Do not regenerate the lock or
  upgrade dependencies incidentally to make local setup pass.
- Use [development guidance](docs/DEVELOPMENT.md) to distinguish executed checks
  from unverified recipes. Python 3.10/full application tests were unavailable
  at documentation adoption; do not repeat a historical result as a fresh pass.

## Interfaces and scientific validation

Current exports have node_id/parent_id node records and parent_id/child_id edge
records, with string root classifications. Inspect current serialization and
consumers before changing identifiers, parent relationships, classes or units.
Do not infer XEG/GroIMP compatibility from historical prose.

Trace seeds, configuration, units and observation support through the changed
path. Agree scientific definitions/tolerances before changing growth, mass or
density formulae, summary statistics, objectives or priors. Keep algorithm
checks, synthetic regressions and biological validation distinct.

`tests/test_scaffold.py` asserts True; its pass is not model coverage. For actual
code changes, use small tests of the affected behaviour and meaningful graph,
finite-output, deterministic-seed or analytic-statistic fixtures as appropriate.
Report missing dependencies as an environment blocker. Read [review notes](docs/REVIEW_NOTES.md)
when working on statistics or calibration; recheck findings against current code.

## Execution and local data

Direct simulation is the smallest prospective offline runtime check. Full
flows can write artifacts, upload to storage and create/delete database
collections. Do not treat Dash/Prefect/BentoML imports as harmless smoke tests.
Do not start Docker/Apptainer, workers, deployments, training or tuning unless
in scope. Do not print `.env`/expanded credentials or run rewriting hooks during
inspection. Keep generated outputs, environments and caches out of source control.

Calvin Lam's raw data at `/home/jzhu/Workspace/Contacts/Australia/Calvin Lam/`
must stay local. Do not upload its contents to agents, artifact stores,
MLflow/S3 or other services. Data inspection and fitting are deferred in the
current phase. The reported XYZ/root-length-density/biomass description is not
a verified schema or permission to adopt a calibration. A later data task needs
explicit scope and local processing; these instructions do not relax parent
scientific/data protections.

## Python guidance

Use [.agents/skills/deeprootgen-python-engineering/SKILL.md](.agents/skills/deeprootgen-python-engineering/SKILL.md)
for source-specific Python work. When available, shared
`fruitcropxl-python-data-workflows` supplements it; use `fruitcropxl-data-curator`
only for scoped data work and `fruitcropxl-ci-containers` for scoped infrastructure
work. Do not install workers or register supervisor roles as a side effect.
