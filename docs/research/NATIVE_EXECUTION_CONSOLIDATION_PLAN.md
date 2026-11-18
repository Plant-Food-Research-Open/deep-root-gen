# Native execution consolidation goal plan

> **Next input-design plan, 18 November 2026:** [one format and parameter simplification](SINGLE_INPUT_AND_PARAMETER_SIMPLIFICATION_PLAN.md). The owner now prefers full conversion of active inputs rather than permanent legacy loading, one scalar maximum order, explicit count scopes and cohort only if it adds a distinct useful mechanism. This is a documentation-only planning update; the implementation history below is preserved.

> Historical 17 November plan. The authoritative next implementation plan is
> [Native feature composition, revision 2](NATIVE_FEATURE_COMPOSITION_REVIEW_AND_PLAN.md).
> It requires one fixed engine with independent options and supersedes the
> sequence below. Historical status statements below describe that planning epoch.

17 November 2026. **Planning complete; implementation milestones below are pending.**
Based on [the consolidation design](NATIVE_EXECUTION_CONSOLIDATION_DESIGN.md)
and inspected working tree at `ff1a1df17381de3907f9799a56fb8f62008f6b47`.
The working tree contains uncommitted source and documentation changes; this
revision alone does not identify a reproducible implementation baseline.

## Goal and completion boundary

Make `RootSystemSimulation.run()` the single supported execution owner for
native legacy, native Fichtl, SO4 construction-step compatibility and cohort v5
compatibility. Each uses native organ state, graph assembly, result contracts
and integrity checks, with explicit scientific policies inside that lifecycle.
Independent complete generators must not remain hidden behind `run()` dispatch.

Deliver in three packages, in order:

1. **A — native SO4 parity:** freeze references, consolidate shared kernels and
   execute SO4 from live native organs. This is the first implementation goal.
2. **B — native cohort parity:** add planned-organ initialization, origins,
   material and result support, then migrate cohort construction.
3. **C — caller migration and retirement:** move supported offline callers onto
   the native engine and retire duplicate mutable execution implementations.

Package A completion is a useful release boundary, not completion of the full
consolidation goal. This planning task delivers the plan only; it does not
authorize or report implementation, new fitting or scientific adoption.

## Scope, frozen inputs and constraints

Before implementation, record HEAD, status, patch and hashes of every affected
tracked or untracked source, reference fixture and configuration. Preserve all
intervening work, particularly the current attachment/controlled/interval
geometry extraction and research wrappers. Inspect these changes before
deciding what still needs moving; do not repeat an existing extraction.

Freeze invented fixtures for native legacy/Fichtl, SO4 construction intervals
and a small cohort v5 case against their current reference implementations.
Record their seeds, source identities, configuration, environment, expected
outputs and RNG state or purpose-keyed draw receipts. Reference outputs must
predate migration and remain independent of the candidate implementation.
Never regenerate expected outputs merely to accommodate a mismatch.

The design's four supported compatibility contracts are the initial scope.
Preserve legacy defaults, flat input behavior, table columns, `run()` return
convention and existing strict geometric/material tolerances. Extended inputs
use a versioned typed schema with no meaningless native placeholders. Reject
conflicting, irrelevant, unknown or unsupported extended options before any
construction. Preserve caller/internal SO4 tags through explicit metadata.

Keep native validation draws and ordering unchanged. New checks, recording and
export consume no randomness. Keep biological organ identities separate from
graph IDs, and direction stations separate from attachment/material cuts.
Scientific changes in trajectories, sampling, conditioning, boundaries or RNG
design require a new contract and separate evaluation.

No dependency upgrades, lock regeneration, services, containers, deployments,
training, optimization, supervisor integration, pushes or new agents are part
of this plan. Empirical inputs, photographs, fitted settings and sealed results
stay local and unchanged. Initial verification uses invented fixtures. Any
later empirical receipt replay needs an explicitly recorded local scope; it is
not required to start the code migration or permission to refit.

## Milestones and evidence gates

Every milestone produces a bounded diff, source/configuration hashes, exact
commands and outcomes, and an acceptance record listing remaining limitations.
All milestones currently have status **pending**; historical tests and design
reviews are not fresh implementation evidence.

| Milestone | Work and concrete deliverables | Required evidence before advancing |
|---|---|---|
| A0 — freeze and inspect (design stage 0) | Baseline manifest; invented golden fixtures; consumer and random-stream inventory; verify existing extraction work and available Python 3.10 environment. | Reference cases run on frozen source; numeric tables, IDs, flags, organ relationships and RNG evidence captured. Unavailable dependencies are recorded as a blocker, not replaced by scaffold tests. |
| A1 — shared kernels (stage 1) | Promote only needed controlled direction, boundary and interval primitives to core owners; retain forwarding imports. Inventory cohort primitives for B without broadening A unnecessarily. | Existing API outputs remain exact on the pinned environment; imports point toward core; no duplicate numerical implementations or changed draws. |
| A2 — native SO4 (stage 2) | Typed extended configuration/resolver; live-organ trajectory executor; atomic attachment operation; optional INITIAL recorder; native result metadata and negative-input tests. | Native legacy/Fichtl tables and RNG remain exact. Direct SO4 matches the frozen replay reference for interval proposals, first chord, boundaries, geometry, material and invented observation summaries. Explicit ID/cut mapping explains any allowed presentation difference. |
| B0 — origins and material (stage 3) | Complete planned `RootOrgan` factory; identity reservation; explicit root bases; taper writer; organ/node sidecars; root-only result and separate crown support; named core projection adapter. | Analytic length/volume/mass, threshold/corner cuts, multi-base and empty-material cases pass. Legacy tables unchanged; no phantom base. Unsupported consumers reject extended semantics explicitly. |
| B1 — native cohort (stage 4) | Extract bounded dimensions, maturity and branching into per-organ planning within the native queue/registry/writer. | Mapped equivalence to small frozen cohort v5 cases: breadth-first reserved IDs, rejection/draw order, censoring, parent point-diameter caps, insertion, curvature/reflection, material and diagnostics. No second complete generator on the supported native path. |
| C0 — migrate callers (stage 5) | Existing offline CLI, notebook and search bridge call native `run()`; schema round trips; result-aware observation/export adapters; capability table for downstream consumers. | Invented API/CLI outputs and observation scores agree; frame/source/conditioning receipts survive round trips. Tests catch calls to independent generators. Service consumers are tested offline where feasible or explicitly reject unsupported modes. |
| C1 — retire and document (stage 6) | Old APIs become native adapters or pinned archival replay tools; remove redundant mutable generation paths; update architecture, input-flow, development and reproduction documentation. | Source ownership audit plus focused and full-suite evidence proves a single active owner per mechanism. Archives remain reproducible and clearly distinguished from supported execution. All goal-level acceptance items below have evidence. |

Dependencies are A0 → A1 → A2 → B0 → B1 → C0 → C1. Keep one construction
change per reviewable step. At A2, close and review package A before beginning
B; at B1, close B before caller retirement. Do not delete a reference path
before its replacement passes its own equivalence gate. These are technical
gates, not claims of biological qualification or an added human-approval rule.

## Package A execution checklist

1. Inspect `model/root.py`, `model/hgraph.py`, the existing simulation schema,
   current core geometry helpers, `research/so4_controlled.py`,
   `research/construction_step_replay.py` and attachment code. Capture the actual
   changed bytes alongside HEAD, including untracked helpers.
2. Select small existing invented fixtures that exercise legacy and native
   Fichtl validation, SO4 branching/rank controls, distal attachments, primary
   options and boundary events. Add only fixtures needed to expose uncovered
   behavior. Record original construction intervals and draw namespaces.
3. Define the extended SO4 schema and unsupported-combination table. Keep
   constructor/request seeds consistent, reject used extended simulator
   instances, define limits as errors rather than truncation, and ensure
   failure cannot expose a partial graph as a successful result.
4. Integrate retained interval geometry into native live-organ realization,
   parent before child, preserving the preparation and validation sequence.
   Do not construct FINAL by replaying exported DataFrames.
5. Apply distal attachment after topology/dimensions are prepared. Update
   graph links, `segments`, `base_node`, `child_organs`, parent associations,
   interval maps and registry references atomically; preserve daughter
   dimensions and original direction innovations.
6. Compare recorder-on/off and extra-cut cases. Extra material or attachment
   nodes must neither add heading draws nor move original direction stations.
   Keep graph-dependent legacy modes explicitly outside this invariant.
7. Remove only the native guards whose complete paths are now qualified.
   Run affected tests, then package-release checks and write the A acceptance
   record. Report SO4 parity and the still-pending B/C work separately.

## Package B invariants

The planned-organ factory must initialize full native state without resampling
dimensions, applying legacy offsets/transforms or consuming extra draws.
Reserve cohort biological IDs when daughters enter the queue; graph emission
reuses them. Parents must have realized point diameters and tangents before
daughter plans are sampled. Preserve cohort v5 breadth-first allocation and
purpose-stream names, including within-organ rejection order.

Canonical `simulation.G` contains root material and zero-material bases.
Keep vine `plant_id` distinct from sidecar `primary_tree_id`; retain separate
crown-support links and explicit crown mass. The finite-core adapter projects
to temporary tree IDs and aggregates back to vines before population weighting
or crown addition. Test that several primary trees remain one vine.

Retain point diameters separately from volume-equivalent exported diameters.
Verify exact frustum integrals, taper breakpoints, diameter-class crossings and
direction corners. Convert mm/cm cutoffs explicitly. Preserve strict roundoff
guards and any declared reconciliation receipt; do not silently move geometry
or relax tolerances. New options do not establish better biological predictions.

## Verification and receipts

Use Python 3.10 and the existing lock. Inspect the actual environment before
running commands: `docs/DEVELOPMENT.md` describes historical missing-runtime
evidence, while `RUNNING.md` identifies a later local environment. Neither is
a fresh pass. Current CI uses `--run-integration`; include it so simulator
coverage cannot silently disappear. The scaffold test is not model coverage.

Extend the existing test families named in design section 13: Fichtl tropism,
SO4 controlled/construction replay, attachments/rank/zones, cohort generation,
curvature/physical replay, analytic material, graph/core and caller tests.
Also inspect current test skip rules before accepting a report.

For each package, first run targeted tests of changed behavior. After they
pass, run the established full suite with `--run-integration` once on the
release candidate and lint changed Python code. Record the exact interpreter,
package and lock identities, commands, exit codes, counts and every skip.
Repeat only when a change, failure or unresolved concern warrants it. Do not
start Dash, Prefect or BentoML as an import smoke test.

Equality rules follow design section 9: exact numeric/ID/RNG compatibility for
unchanged native kernels in the same environment; deterministic complete
one-to-one mappings for allowed extended graph presentation differences.
Any arithmetic tolerance must have an explicit analytic justification agreed
before acceptance. Similar aggregate scores cannot excuse different random
draws, geometry or biological relationships.

Store machine-readable receipts and generated outputs in a fresh ignored local
run directory; maintain a concise non-empirical acceptance report with links to
the relevant source/tests. Receipts include reference/candidate hashes, seed,
contract version, mapping, frame, conditioning, commands and result. Preserve
failed cases. Stop the affected milestone on unexplained mismatch, environment
failure, stale-reference inconsistency or a necessary new scientific decision;
continue independent inspection/documentation where useful.

## Final completion audit

The implementation goal is complete only when evidence proves every item:

- Native `run()` owns the four supported contracts through native organ,
  graph and validation state; it does not delegate to whole research generators.
- Legacy defaults and native Fichtl retain their frozen numerical and RNG
  behavior; direct native SO4 and cohort pass their respective parity gates.
- Typed extended inputs work without dummy dimensions, reject unsupported
  combinations and preserve existing callers through explicit adapters.
- Direction decisions are independent of graph subdivisions where specified;
  live organ references, reserved IDs, attachments and material are consistent.
- Root/crown separation, true vine identity, complete ID mappings, material
  units and observation-frame contracts survive supported exports and callers.
- Offline CLI/notebook/search routes use native execution; other consumers have
  verified support or explicit unsupported-mode behavior.
- Duplicate active execution is removed, archival reproduction remains usable,
  and architecture/user documentation describes the implemented state.
- Source-bound focused tests, full integration suite, lint and limitation
  records support the final candidate; no missing runtime evidence is called a
  pass and no empirical fit is presented as qualification of the refactor.

There is no arbitrary time or trial budget. Estimate subsequent work after A0
and A2 reveal actual compatibility costs. A mismatch changes the next task,
not the definition of success.
