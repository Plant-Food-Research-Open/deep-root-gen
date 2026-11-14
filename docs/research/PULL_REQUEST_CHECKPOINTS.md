# Research pull request checkpoints

Open or update a draft PR when a coherent checkpoint has reproducible technical
checks and a clear review scope. Keep dependent changes in a stack; merge only
after the prerequisite and maintainer reviews are complete. Opening a draft does
not authorize a merge, release, biological adoption or new experiment budget.

## Current stack

| Checkpoint | Scope | Base and review condition |
| --- | --- | --- |
| [1: public runtime](https://github.com/junqi108/deep-root-gen-PFR-open/pull/1) | Existing 1.0 runtime, standalone CLI, graph/statistic code, synthetic examples and tests | GitHub main; review runtime/API compatibility and CI |
| [2: optional tropism](https://github.com/junqi108/deep-root-gen-PFR-open/pull/2) | Explicit Fichtl-inspired mode, public input, legacy golden regressions and assumptions | Checkpoint 1; review parameter semantics and default preservation |
| 3: controlled replay, this change | Four-arm replay, shared boundary, keyed streams, invariant/budget/recovery checks and public method | Checkpoint 2; review algorithm, synthetic checks and scientific claim limits |
| 4: explicit observation contract | Hierarchical raw IDs, declared point-set verification and canonical soil axes | Checkpoint 3; qualify raw/RSML inputs locally before new comparisons |

Review the stack in order. After merging a prerequisite, retarget its dependent
PR to main and verify the resulting diff before marking it ready. The current
workflow's pull-request filter targets main, so stacked PRs do not inherit a
claim of remote CI success. Each checkpoint is tested locally on its isolated
publication tree; remote checks and maintainer review remain separate.

The public branches start from GitHub main using an explicit source-file export.
They do not carry the unpublished local merge ancestry. Measured roots, prepared
grids, observation-comparison artifacts, notebooks with observations, local
runtime receipts, environments and credentials remain local. Synthetic graph
fixtures and publicly documented paper parameters are the publication boundary.

## Controlled replay contract

The [method](SO4_CONTROLLED_METHOD.md) and configuration define ten matched seeds
and four arms: legacy/Fichtl-inspired insertion crossed with legacy/Fichtl-inspired
continuation. One INITIAL scaffold is reused per seed, preserving topology,
segment lengths/diameters, attachment node/arc identities and primary geometry.
Higher-order attachment world coordinates move with parent paths. Keyed
insertion, continuation and boundary streams omit arm from the key.

All arms use the same minimum-angle feasible projection at S=20 cm. Boundary
activation can differ between arms, so the contrasts include boundary effects.
The first segment follows the assigned insertion unless the boundary overrides
it; search starts at segment 2. Diagnostic one-step proposals are not a coherent
unconstrained architecture. The durable reservation ledger counts every attempt,
including failures, against the fixed cap; no automatic retries or hidden
counterfactual replay are permitted. This is a POSIX source-checkout tool.

The private local experiment remains frozen. For publication, three Python files
are formatted and intentional import-order/controller-complexity lint comments
are added; their Python ASTs, including the synthetic test logic, match the
reviewed originals. The config, public parameter input and frozen method bytes
are retained. Fresh publication-tree tests establish the exported artifact;
older local run receipts do not identify this newly formatted source tree.

Prior independent Claude Opus 5.5 reviews covered public code/evidence and
synthetic fixtures; they did not inspect protected measured comparisons. The
public draft and any later maintainer review remain separate from those static
reviews. No new biological conclusion or configuration adoption is asserted.

## Method erratum and observation limits

The frozen method's phrase about deriving attachment arc coordinates afresh
overstates the runner's geometric recomputation. Its attachment/edge hashes use
identity fields and stored lengths. Per-edge and total-length checks run inside
`validate_geometry`; separate local post-hoc geometric-arc checks are not part
of that frozen implementation or this PR's validation claim. The method is
retained unchanged to preserve its prior identity.

Every observation-referenced quantity requires a joint mapping: the observed
RSML reference point/axes and model-side S=20 cm, depth=20-z. The public dataset
README defines raw digitizer axes and graft point 0 but does not establish the
exported RSML transform or identify stem point 1 as physical soil. This remains
an unresolved observation contract, not a demonstrated export bug. Post-excavation
preservation of in-situ geometry and branch attachment definitions also need
evidence. Published means/SDs are inputs; scaled lengths and truncated insertion
angles have different realised distributions. No biomass conversion is inferred.

The next scientific checkpoint should establish an authoritative landmark, axis
and attachment contract using documentation/export metadata or explicit author
confirmation, before choosing a configuration or fitting. Accept a mapping from
that evidence, never because it improves a score. An observation-side mapping
change can reuse existing model-coordinate graphs; a model-side scaffold/surface
change needs a new explicitly bounded experiment. This PR launches neither.

## Commands for public qualification

With the locked Python 3.10 environment:

```bash
python -m pytest -q --run-integration
python -m flake8 --count --statistics
```

These commands use public/synthetic fixtures and never load measured observations.
The controlled CLI requires an explicit output directory and `--execute` to run
an ensemble; `--prepare` writes a source/input manifest without any attempt.
The caller owns the separate end-to-end bound described by the method. CI and
routine qualification must not launch the fixed empirical ensemble as a smoke
test or silently create another attempt budget.
