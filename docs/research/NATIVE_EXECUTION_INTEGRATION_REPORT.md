# Native execution consolidation: implementation and verification

17 November 2026. Packages A, B and C are implemented locally and pass the
synthetic verification below. Changes are uncommitted. Reference HEAD is
`ff1a1df17381de3907f9799a56fb8f62008f6b47`; this commit alone does not identify
the modified implementation. Exact changed-source/configuration/fixture hashes,
patch, reference archive, commands and receipts are retained under
`.runtime/native-integration-20261117/`.

## Outcome and scope

The supported public generation owner is `RootSystemSimulation.run()` for native
legacy, native Fichtl, construction-step compatibility and cohort v5 compatibility.
The original native body retains its call/draw ordering in `_run_native`.
Extended construction uses the simulator-owned parent-before-child queue,
native `RootOrgan` objects, `RootSystemGraph` assembly and common pure integrity
checks. No supported extended path calls an independent complete generator.

SO4 preparation reuses native initialization and positioning. Its trajectory
kernel is shared with saved-INITIAL replay through separate live/table adapters.
Primary relocation shares pure cut/rigid-transform mathematics, then updates
native node/edge and organ-object relationships together. All four saved SO4
INITIAL/node/edge cases captured before editing match exactly; broader reference
cases also cover sibling ranking, parent2 zones, distal attachments and
order-specific direction controls.

Cohort dimensions and branch sites are sampled per organ inside native
scheduling. Curvature/taper operations have one shared implementation. Native
objects carry the realized segments, parent relationships and mass; graph
allocation reserves the existing biological identities independently of graph
cuts. The old `CohortRootGenerator` now adapts configuration and the historical
export format to native execution. The canonical graph is root-only; crown
support and primary-tree/cohort metadata are separate.

The offline CLI accepts the versioned typed schema. Notebook 5's construction-
step search bridge calls native `run()` and a read-only INITIAL recorder.
Legacy flat inputs and node/edge columns are retained; `run()` returns `None`.
New cohort inputs require no dummy native dimensions and reject unknown or
irrelevant native controls. Prefect simulation entrypoints explicitly reject
offline-only extended requests before tracking, storage or task submission. Unsupported combinations fail before construction;
mutated nested configurations are revalidated before use. Extended simulator
instances cannot be reused, including through the flat entrypoint.

See [usage and consumer capabilities](../NATIVE_EXECUTION.md) for examples.
The previous [design](NATIVE_EXECUTION_CONSOLIDATION_DESIGN.md) and
[goal plan](NATIVE_EXECUTION_CONSOLIDATION_PLAN.md) remain preserved planning
records; their pending-stage language describes the planning epoch.

## Milestones and evidence

| Package | Delivery | Acceptance evidence |
|---|---|---|
| A0/A1 | Independent references and shared controlled/interval/attachment primitives | Seven initial synthetic cases frozen before edits; 12 expanded cases generated from an isolated unchanged reference archive, with source/configuration hashes. Shared functions moved once, historical imports retained. |
| A2 | Live native SO4 execution and snapshot recorder | Exact INITIAL hash, node/edge CSV hash, construction-step and fragment receipts; primary/daughter object links and mass checked. |
| B0 | Planned-organ initialization, explicit bases, taper/material and result support | Existing analytic taper/cutoff, geometry, attachment, graph and core tests pass; primary-tree projection retains true vine identity. |
| B1 | Native cohort scheduling and graph ownership | Exact historical node/edge/organ/projection tables and diagnostics for two frozen seeds, plus the original cohort test suite. |
| C0 | CLI, notebook and search migration | Eight CLI simulations versus direct API output, exact node/edge CSV equality; search keeps requested/internal tags and INITIAL identities. |
| C1 | Generator retirement and ownership checks | Old cohort implementation replaced by an adapter; native tests forbid calls to old constructor/replay entrypoints. Saved replay and graph-segment experiment tools remain historical APIs. |

The existing graph-segment four-arm and saved replay interfaces are retained
for historical experiment reproduction. They are not additional supported
version-2 fresh-generation contracts. No historical source/result epoch was
rewritten or relabelled as a result from this implementation.

## Executed verification

Final full suite: **1,660 passed; zero failures, errors or skips.** This includes
20 new native-execution tests and the opt-in native simulation integration tests.
Expected reference outputs were never regenerated from the candidate to resolve
a mismatch.

The 12 frozen reference cases comprise two seeds each for native legacy/native
Fichtl, six SO4 construction-step cases, and two cohort cases. Native legacy and
Fichtl tables and shared RNG state match. SO4 tables, INITIAL identities and
purpose-keyed interval records match. Cohort historical tables and diagnostic
material totals match. New tests also verify input rejection, native object
ownership, isolated-base conversion, projection identity, partial-failure status
and simulator reuse rejection.

Eight bounded CLI runs used seeds 42 and 44 for each contract. Every CLI run
returned zero, produced finite geometry and matched direct API node/edge CSVs
exactly. The fixtures are invented; no empirical fit, optimization or biological
validation ran.

| Contract | Seed | Nodes | Edges | API/CLI CSV parity |
|---|---:|---:|---:|---|
| Native legacy | 42 | 20 | 19 | Exact |
| Native legacy | 44 | 20 | 19 | Exact |
| Native Fichtl | 42 | 23 | 22 | Exact |
| Native Fichtl | 44 | 23 | 22 | Exact |
| Native construction steps | 42 | 23 | 22 | Exact |
| Native construction steps | 44 | 23 | 22 | Exact |
| Native cohort | 42 | 59 | 56 | Exact |
| Native cohort | 44 | 58 | 55 | Exact |

Changed-source lint and `git diff --check` pass. A repository-wide lint probe
also identifies seven existing findings in unchanged
`research/order_mass_allocation.py`; those were not changed incidentally.
`pip check` reports no broken requirements. Dependencies and lock were not
modified or reinstalled.

Runtime: Python 3.10.20, NumPy 1.26.4, pandas 2.2.2, Pydantic 2.8.2, Torch 2.4.0,
PyG 2.5.3, pytest 8.3.2. `poetry.lock` SHA-256 is
`ac9d8a5d67c7bcb75ca801c8ab79e290fbc41b88752caf95fba03d8ecc0e3d31`.
This qualifies the retained host environment; it is not a clean-install claim.

Representative final commands, run from the repository root:

```bash
CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$PWD/.runtime/native-integration-20261117/locked-overlay:$PWD" \
.runtime/envs/py310-qualification/bin/python -m pytest --run-integration -q \
  --tb=short \
  --junitxml=.runtime/native-integration-20261117/final-tests.xml

.runtime/envs/py310-qualification/bin/python -m flake8 --jobs 1 \
  deeprootgen/model deeprootgen/data_model deeprootgen/cli.py \
  deeprootgen/research/cohort_root_generator.py \
  deeprootgen/research/construction_step_replay.py \
  deeprootgen/research/curvature_process.py \
  deeprootgen/research/primary_attachment.py \
  deeprootgen/research/search_evaluation.py \
  deeprootgen/research/so4_controlled.py \
  tests/test_native_execution.py tests/test_search_evaluation.py \
  app/flows/run_simulation.py

.runtime/envs/py310-qualification/bin/python -m deeprootgen simulate \
  --config examples/research/native_steps_synthetic.json \
  --outdir .runtime/a-new-native-steps-check

.runtime/envs/py310-qualification/bin/python -m deeprootgen simulate \
  --config examples/research/native_cohort_synthetic.json \
  --outdir .runtime/a-new-native-cohort-check
```

Some existing historical parity tests expect a `locked-overlay` path entry and
retained public prechange snapshots under `/tmp`. The empty local overlay path
satisfies that harness's discovery convention; it supplies no replacement
packages. Final full-suite evidence is specific to this host. The new frozen
reference fixtures themselves are portable and contain only invented inputs.

Failed attempts remain recorded. The initial baseline run lacked the historical
harness overlay entry. A later refactor produced six analytic-test failures
because their lightweight test objects lacked a new bound helper; the call was
corrected without altering expected outputs. The final full rerun passes.

## Review status and parameter decisions

GPT-6.1 Sol performed implementation and local source review. Two explicitly
requested Claude Fable attempts were made with public-only packets and tools
disabled. The plan request failed with API DNS error `EAI_AGAIN`; the code request
timed out. Neither returned a review or a model-usage identity. Their receipts
are retained locally. **Claude review remains unavailable; it is not counted as
completed review evidence.**

No historic flat parameter was removed merely because a new construction
ignores it. Source inspection identifies `root_ratio`, `mechanical_constraints`,
`origin_min` and `origin_max` as declarations without model/runtime consumers in
the inspected Python source. They remain compatibility fields in the flat
schema and are not introduced into cohort inputs. Removing them from old saved
requests/serialization would contradict this migration's parity boundary.
Cohort terminal-order branch fields also retain v5 sampling/diagnostic semantics;
any future schema reduction should be versioned. New unknown parameters fail
instead of silently doing nothing.

## Remaining limitations

- This is code/algorithm compatibility evidence, not biological qualification
  or a new SO4/Calvin fit. Existing empirical conclusions retain their source
  epochs and limitations.
- Only the four compatibility contracts are supported. New combinations of
  cohort sampling, Fichtl directions, boundaries or RNG schemes require a
  separate scientific specification and evaluation.
- Dash/Prefect persistence, BentoML and generic native calibration/statistics
  retain their flat request interfaces. Prefect boundary guards are covered by
  pure guard tests and source-order inspection, without importing or starting services. Extended consumer adoption is not
  qualified by calling native `run()`; use the explicit offline result/observer
  adapters described in the usage guide.
- Crown mass and unrepresented mass remain separate assumptions. No spatial
  material was invented to close a biomass deficit, and primary trees are not
  treated as independent vines.
- No services, containers, deployments, training, optimization or pushes ran.
  Existing source/document work, raw data and sealed empirical results remain
  preserved. The working tree is ready for review and a separately requested
  Git publication step.
