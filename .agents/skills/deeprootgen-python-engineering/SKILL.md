---
name: deeprootgen-python-engineering
description: Inspect and maintain DeepRootGen Python simulation, graph schemas, summary statistics and Dash/Prefect interfaces in this repository, with small synthetic validation checks.
---

# DeepRootGen Python engineering

Read [repository instructions](../../../AGENTS.md) first. Treat this as an
independent Codex project; this repository-local guidance does not install an
agent, enable a supervisor or authorize scientific/data changes. Use shared
FruitCropXL Python guidance when available, without requiring another checkout
for ordinary Python maintenance.

- Use [development guidance](../../../docs/DEVELOPMENT.md) for environment and
  command evidence. Inspect current pyproject/lock and CI before selecting an
  interpreter. The reviewed code requires Python 3.10 and eagerly imports
  Torch/PyG in model/hgraph.py. A NumPy-only environment cannot import the model.
- Trace RootSimulationModel to RootSystemSimulation.run and
  RootSystemGraph.as_df using the [code map](../../../docs/ARCHITECTURE.md).
  Preserve the separate node/edge schemas and inspect consumers before changing
  IDs, parent semantics, root classes or units.
- Prefer a tiny direct in-memory synthetic simulation once the supported
  environment is qualified. Dashboard pages, Prefect flows and BentoML services
  add dependencies and side effects; experiment outputs use `/app/outputs`.
  Do not start these layers merely to inspect the library.
- Treat tests/test_scaffold.py as a dummy. For changed code, target actual
  behaviour with cheap fixtures: graph/ID relations, fixed-seed repeatability,
  finite geometry/statistics and analytic length/volume/mass. Missing runtime
  dependencies or an unexecuted recipe cannot count as scientific PASS.
- Read [review notes](../../../docs/REVIEW_NOTES.md) for statistics/calibration
  work and recheck the findings against current source. Review base/invalid-root
  handling, distribution features, spatial support and seed propagation before
  trusting inference. Agree formula definitions, units and tolerances before
  scientific corrections; do not silently change the objective.
- Record source/config/lock identity, interpreter/package versions and exact
  executed commands. Separate supported-runtime tests from source-extracted
  probes or syntax checks in another interpreter. Keep generated artifacts out
  of tracked source unless deliberately approved fixtures.
- Preserve AGENTS.md local-data boundaries. XYZ measured density/biomass is not
  automatically the graph-node schema. Do not inspect raw observations, fit,
  upload or adopt calibration outside an explicit later local-data task.

Provenance: repository source and documentation reviewed at fc91362 on
2026-10-28. Current source takes precedence over historical review notes.
