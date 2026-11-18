# PR integration and review status

## Local upstream-main source update (16 November 2026)

At the owner's request, upstream main at `24ee8d9e677770b00d0206cdb93c1487304bf447`
was merged against the current local branch in an isolated copy. Git completed
the merge without conflicts. The resulting nine changed/added paths were applied
to this working tree: the upstream DOI/badge and Wong 2026 data/notebooks.
Existing uncommitted documentation and private results were preserved. Four
notebooks parse as JSON; none was executed. Model source and dependencies are
unchanged. CSV line endings follow the existing repository attributes; one
upstream trailing space on the DOI line was removed.

This is a verified **working-tree source update**, not a recorded merge commit:
the canonical `.git` directory remains read-only in this session. No push or
GitHub PR merge occurred. The preservation patch, incoming-source patch and
file identities are under `.runtime/upstream-main-sync-20261116/`.
The separate upstream PR15 was checked live and is already mergeable with main;
it is two commits ahead and zero behind. The fork checkpoint status below
records the earlier inspection and remains distinct from that upstream PR.

Checked 16 November 2026 through the GitHub connector for
`junqi108/deep-root-gen-PFR-open`. Local source before documentation edits:
`3672959b6460bd9b06170bee0c8fdbd48b1e5d31`, branch
`codex/deeprootgen-runtime-ui`, initially clean. The local branch is not the
published PR stack and must not be pushed wholesale as a shortcut to integration.

## GitHub operation remains outstanding

The owner requested merging all drafts. There are **13 open draft PRs** and
one additional open, ready PR (#15). PR #6 was already incorporated into #5.
No PR was merged, retargeted or changed by this session. The attempted
transition of #1 to ready was rejected with:

> MCP tool call requires approval, but approval policy is never

The local `.git` directory is also read-only in this session (`git fetch`
cannot write `FETCH_HEAD`). Source/documentation edits and read-only Git
inspection are available; committing, fetching and pushing this checkout are
unavailable. This is an execution-permission limitation, not a request for
additional scientific approval. The owner's current merge instruction
supersedes historical “no merge” wording in the checkpoint plans.

The connector reported #1 as `mergeable=false`; all other open heads were
reported `mergeable=true`. It did not explain #1's result, so no conflict
resolution or clean merge is claimed. Combined commit-status lists and
submitted GitHub review lists were empty for all fourteen heads. Empty lists
are not passing CI or completed independent review. The PR-triggered workflow
query for #1 also returned no runs. Prior public test/review statements in PR
bodies retain their original source epochs.

## Stack order and inspected heads

| PR | Change | State | Inspected head |
|---|---|---|---|
| [1](https://github.com/junqi108/deep-root-gen-PFR-open/pull/1) | Public 1.0 runtime and offline tests | Draft; targets main | `fffa8474` |
| [2](https://github.com/junqi108/deep-root-gen-PFR-open/pull/2) | Optional Fichtl-inspired tropism | Draft; on #1 | `566e5e2c` |
| [3](https://github.com/junqi108/deep-root-gen-PFR-open/pull/3) | Controlled replay | Draft; on #2 | `ff129788` |
| [4](https://github.com/junqi108/deep-root-gen-PFR-open/pull/4) | Explicit observation contract | Draft; on #3 | `149ca004` |
| [5](https://github.com/junqi108/deep-root-gen-PFR-open/pull/5) | Current-length/construction controls, including #6 | Draft; on #4 | `ffb1ea68` |
| [7](https://github.com/junqi108/deep-root-gen-PFR-open/pull/7) | Population evaluation and mass audit | Draft; on #5 | `b4e15a01` |
| [8](https://github.com/junqi108/deep-root-gen-PFR-open/pull/8) | Primary inclination | Draft; on #7 | `2791adb9` |
| [9](https://github.com/junqi108/deep-root-gen-PFR-open/pull/9) | Construction-step replay | Draft; on #8 | `0b8291c5` |
| [10](https://github.com/junqi108/deep-root-gen-PFR-open/pull/10) | Length-dependent tertiary branching | Draft; on #9 | `25ae482d` |
| [11](https://github.com/junqi108/deep-root-gen-PFR-open/pull/11) | Order-specific turning scales | Draft; on #10 | `8c8a1460` |
| [12](https://github.com/junqi108/deep-root-gen-PFR-open/pull/12) | Primary yaw reversal | Draft; on #11 | `d0242ac1` |
| [13](https://github.com/junqi108/deep-root-gen-PFR-open/pull/13) | Tertiary length ranking | Draft; on #12 | `d36f2ecf` |
| [14](https://github.com/junqi108/deep-root-gen-PFR-open/pull/14) | Primary attachment relocation | Draft; on #13 | `12b23bfd` |
| [15](https://github.com/junqi108/deep-root-gen-PFR-open/pull/15) | Finite-core and area-mean observations | Already ready; on #14 | `e4d3221f` |

To complete the authorized draft merges in a session with GitHub write access:

1. Refresh the remote PR heads, reviews, checks and main. Inspect/resolve #1's
   reported mergeability before proceeding; preserve main and checkpoint content.
2. Merge #1 with a merge commit and an expected-head SHA guard. Retain branches
   while their descendant PRs still use them as bases.
3. For each of `2 3 4 5 7 8 9 10 11 12 13 14`, in order, retarget onto main
   after its prerequisite is merged, inspect the remaining diff/checks, mark
   ready, then merge with the expected head. Stop on a changed head, conflict
   or required failing check. Do not bypass branch protections.
4. #15 is already ready, so it is recorded separately from the requested
   drafts. Do not silently report it as a draft merge.
5. Verify every requested PR's `merged` state and ancestry on main, refresh the
   local branch deliberately, and rerun affected checks if integration changes
   code. Update this status only after those operations succeed.

Merge commits preserve the stacked commit ancestry. Squashing/rebasing early
checkpoints can cause descendant diffs to repeat already integrated changes.
Do not delete checkpoint branches before retargeting their descendants.

## Fresh local checks

Executed in this session, without services, dependency installation or empirical
simulation/fitting:

| Source | Check | Result |
|---|---|---|
| Exact public PR15 archive, `e4d3221fcae940fb84ee0b986643a6febc1265a1` | Full suite, including opt-in simulator integration | **1023 passed**, zero failed/errors/skips, 67.78 s |
| Local `3672959` source | Cohort constructor, core observations, area means, simulation smoke and UI parameter contracts | **116 passed**, zero failed/errors/skips |
| Documentation and result protection | Native field inventory, edited Markdown links, current/future/nested ignore probes, tracked-result inventory, whitespace | **66 fields documented**, links resolve, **10 ignore probes passed**, no tracked matching result files; `git diff --check` passed |

The public suite includes its inherited dummy scaffold test. It establishes
technical regression evidence, not calibration or biological qualification.
The local targeted tests cover additional cohort source absent from PR15;
neither result is a fresh full-suite qualification of every local research file.

Environment: Python 3.10.20, NumPy 1.26.4, Pandas 2.2.2, existing
`.runtime/envs/py310-qualification` with the existing pinned
`typing_extensions` overlay at
`.runtime/research/so4-t2-diagnostic-20261114-v1/locked-overlay`.
This environment was reused, not reinstalled against the current lock.

Common test environment (repository-root absolute paths for the public archive):

```bash
export PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
export PYTHONPATH="$PWD/.runtime/research/so4-t2-diagnostic-20261114-v1/locked-overlay:$PWD"
.runtime/envs/py310-qualification/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_cohort_root_generator.py tests/test_core_observation.py \
  tests/test_area_mean_observation.py tests/test_simulation_smoke.py \
  tests/test_runtime_ui_contract.py --run-integration
```

The exact PR15 source was extracted with `git archive` to
`/tmp/deeprootgen-pr15-review-20261116`; the same interpreter ran pytest there
with that archive as its source path, `--run-integration -o addopts=''`, and a
JUnit report. Public-suite warnings include disabled-plugin `env` configuration,
Pydantic `.dict()` deprecations, tensor transpose and scaler feature-name
warnings. Startup emitted three stream-fd permission diagnostics; collection
and all tests completed successfully. No services or real database/storage
operations were launched; mocked flow tests are not service qualification.
An initial targeted invocation named absent `tests/test_cli.py` and collected
no tests; the corrected executed command above uses the existing smoke tests.

Machine-readable remote snapshot and preserved test report are local under
`.runtime/qa/pr-merge-review-20261116/`. These records are ignored.

## Local file protections and documentation

`.gitignore` now excludes `[Cc]alvin*/` and
`[Rr]oot_[Aa]rchitecture_[Pp]resentation*/` directories at any depth, covering
current and future dated results. Existing local bytes are preserved; none of
the current matching result folders was tracked before this change.
Docker/Prefect context exclusions also keep these folders out of later build
and deployment packages; no build or deployment was executed.

Start scientific review with [MODEL_REVIEW_GUIDE.md](MODEL_REVIEW_GUIDE.md).
Exact empirical settings remain in the ignored local review pack. Public docs
describe the interfaces and meanings without publishing fitted arrays or
comparison outputs. Source algorithms, scientific defaults, the lock,
CONTRIBUTING and CODE_OF_CONDUCT are unchanged.
