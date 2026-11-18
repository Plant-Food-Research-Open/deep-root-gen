# Schema-4 implementation and verification

On 18 November 2026, the public generation API, CLI and tracked runs accepted a
single schema-4 configuration. The work builds on revision
`57f6782cba05491c256766cce574548e1683d7e5` with the local engine repairs included.
The tested engine source digest was
`392d2f1f965d0390e832f99a7ad5a8c59cdcce50dee347d4dd3cb60251934c92`.
The [parameter guide](../NATIVE_EXECUTION.md) gives runnable inputs and units.

| Plan stage | Delivered behavior | Evidence |
|---|---|---|
| P0–P1 | One validated input, explicit offline conversion, consumer-specific requirements and effective identities. `max_order` is a single integer. | [Schema](../../deeprootgen/data_model/canonical.py), [resolver](../../deeprootgen/data_model/resolution.py), [caller inventory](SINGLE_INPUT_MIGRATION.md) |
| P2 | A local parent diameter of at least 0.093 cm permits a proposed daughter at its final attachment. Each order supplies an organ count and total length. Material lengths and dry masses are integrated on either side of the reporting threshold, 0.25 cm by default. Optional ratio targets vary permitted dimensions. | [Branch eligibility tests](../../tests/test_canonical_branch_eligibility.py), [allocation and material tests](../../tests/test_material_allocation.py) |
| P3 | An ordinary positive basal-diameter draw works by itself. Optional maturity can induce shared size or branching across a primary tree. Per-order diameter, length, placement and direction choices use the common state. | [Dimension and maturity checks](../../tests/test_canonical_point_dimensions.py), [axis state](../../deeprootgen/model/axis_state.py) |
| P4–P5 | CLI, application request builders, supported notebooks and fresh search inputs use schema 4. Historical constructors and schedules have explicit archive entrypoints. An original SO4 input stays at its manifest-bound path with a schema-4 companion. | [Migration and exceptions](SINGLE_INPUT_MIGRATION.md), [historical inputs](../../tests/fixtures/migration_inputs), [engine](../../deeprootgen/model/engine.py) |
| P6 | The offline integration suite and a tracked export/reload matrix passed on the same working-tree source. | [Matrix script](../../scripts/validation/native_engine_matrix.py), [CLI and replay tests](../../tests/test_canonical_execution.py) |

## Verification

The Python 3.10.20 environment ran **1,998 tests with zero failures, errors or
skips** using `pytest --run-integration`. Flake8 using the repository
configuration reported zero findings across 102 changed or new Python files.
The source manifest passed its SHA-256 recheck. The lock file SHA-256 was
`ac9d8a5d67c7bcb75ca801c8ab79e290fbc41b88752caf95fba03d8ecc0e3d31`.

Eight seeded configurations reproduced their effective and run identities
and their `nodes.csv`, `edges.csv` and `root_summary.json` bytes after reloading
the exported input. All eight had zero invalid nodes. They exercised native
construction, the structural branching default, primary curvature, parent-only
taper, mixed orders, common origins with replaced dimensions, paired allocation
and crown emergence along a trunk buried from 0 to 20 cm.

The paired example requested fractions of 0.50 for length and 0.10 for dry
mass in the lower diameter class. The generated roots achieved 0.490612 and
0.091712, within the specified absolute tolerance of 0.01. Changing the apex
alone can leave thin sites eligible in the historical model. The schema-4
branching check tests the actual local parent material before it creates a
daughter, including after distal relocation.

The full command, runtime versions, lock, input and source hashes, and
individual matrix receipts are stored locally in
`.runtime/canonical-v4/FINAL_VERIFICATION.json`. The XML suite receipt,
source manifest, replay directory and lint output are alongside it. The suite
exercises software behavior with synthetic and archived fixtures. Live services
and the predictive validity of a particular vineyard population require separate
evidence.
