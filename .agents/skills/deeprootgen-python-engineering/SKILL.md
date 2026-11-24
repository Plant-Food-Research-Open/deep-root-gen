---
name: deeprootgen-python-engineering
description: Inspect and maintain DeepRootGen Python simulation, graph schemas, summary statistics and Dash/Prefect interfaces. Validate with small synthetic checks and hand off local results with clickable links, copyable folder paths and VS Code commands.
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

## Local result links

Link the main local result or index using its absolute path. Give the containing
folder's absolute path as copyable text once per result folder, so it survives
copying into LibreOffice or a message. For opening the folder in VS Code, include
`code --reuse-window "/absolute/path/to/results"` when `code` is available on
the user's desktop. Quote paths that contain spaces.

## Optional SO4 research mode (14 November 2026)

For the current population-reconstruction continuation, read
[ACTIVE_SO4_RESEARCH.md](../../../docs/research/ACTIVE_SO4_RESEARCH.md) first.
The qualified v2 soil frame supersedes the historical root-base interpretation;
use versioned comparison identities and preserve original observations.

The user-authorized [SO4 diagnostic task](../../../docs/research/grapevine3d/SO4_DIAGNOSTIC_PILOT.md)
adds an opt-in `tropism_mode="fichtl2024"`; the default remains `legacy`.
Read its explicit angle/probability/unit and soil-frame assumptions before use.
It is static research code, not exact CPlantBox replay or biological qualification.
Use a fresh simulator per seed, preserve the published coefficients separately
from engineering proxies, and retain direction/validation diagnostics. Offset
soil surfaces require the offline aligned observation route; the existing
calibration/UI/statistic routes are not thereby qualified for this mode.

Provenance: repository source and documentation reviewed at fc91362 on
2026-10-28. Current source takes precedence over historical review notes.

## Optional mature-root cohort research

For the owner-authorized mature-root task, use [ACTIVE_CALVIN_RESEARCH.md](../../../docs/research/ACTIVE_CALVIN_RESEARCH.md) and the linked construction contract. CohortRootGenerator is a separate static research API reusing existing geometry/observation utilities, not a RootSimulationModel or notebook-native route. Preserve its source epochs, failure ledger and local-only evidence. Qualify root material on the root-only projection; crown connectors carry no root mass. Root order, diameter class, cohort maturity and chronological age are distinct. Do not report sampled-core agreement or an assumed whole-root mass as unseen-vine validation.
