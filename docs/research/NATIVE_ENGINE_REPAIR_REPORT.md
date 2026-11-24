# Native engine review repairs

18 November 2026. Implements the [review sequence](NATIVE_ENGINE_REVIEW_AND_IMPROVEMENT_PLAN.md)
on baseline `57f6782cba05491c256766cce574548e1683d7e5`. The owner's existing
review-document edits were preserved. Changes are local and uncommitted; no
remote merge or push is included in this task.

This is software qualification with invented inputs. No empirical observations,
sealed SO4/Calvin runs, calibration settings, dependency locks, services or
programme integrations were changed. The new buried-trunk example is an explicit
construction assumption, not a fitted crown distribution.

## Correctness and configuration changes

| Review finding | Implemented behavior and owner | Verification |
|---|---|---|
| F1: parent taper leaked into daughter sampling | [Birth context](../../deeprootgen/model/axis_state.py) captures immutable native cylinders. [Native features](../../deeprootgen/model/native_features.py) retain taper as a separate material profile; daughter inheritance reads birth context. Explicit capping reads the active parent taper. | Parent-only taper, cap disabled, preserves untapered descendants' lengths and diameters in legacy and Fichtl cases. Analytic taper mass and cap tests pass. |
| F2: approximate merging discarded physical events | [Materializer](../../deeprootgen/model/materialize.py) retains real corners and attachment identities. Incoming tangents use the exact side of the attachment. Taper integration splits internally at every midpoint; only material output cuts indistinguishable at binary64 roundoff can coincide. Coordinate-scale floors reject unrepresentable edges. Historical cohort cut rules remain explicit. | Exact and nearby attachment cuts conserve geometry; tiny-axis analytic mass and existing one-ULP material cases pass. Corner postconditions are tighter, not relaxed. |
| F3: INITIAL callback could mutate execution | [INITIAL view](../../deeprootgen/model/initial_view.py) explicitly selects detached data, has no live simulator/RNG, rejects attribute writes, and returns copied tables/metadata. The two-argument recorder signature remains supported. | Parameter/node mutations fail; edits to returned tables/maps cannot affect execution, RNG or identity. Existing INITIAL capture comparisons remain exact. |
| F4: different unseeded runs shared one identity | [Provenance](../../deeprootgen/model/provenance.py) records initial native RNG state, run-start disk source, model-import checkpoint, loaded Python-function fingerprint, lock and package versions. Execution identity includes this record. Unseeded runs explicitly declare `unseeded_non_replayable`. | Different unseeded initial states produce different execution hashes. Seeded exports reload exactly. Runtime function changes are distinguished from disk source; source edits after model import require Python restart before allocation. |
| F5: enabled headings/foreign fields disappeared | [Resolver](../../deeprootgen/data_model/resolution.py) rejects a disk heading without its actual primary `origin_heading` consumer, disk-only fields on point origins, point-only fields on disk origins, and primary curvature insertion parameters with no consumer. | Focused pre-execution rejection tests; valid origin/curvature combinations continue to pass. |
| F6: requirements/hash ignored actual consumers | [Consumer map](../../deeprootgen/data_model/consumers.py) owns operation/order/status/units/RNG descriptions, required parameters, effective parameter selection and native birth-material selection. Replaced uniform bounds are unnecessary; compatibility draws retain draw counts. Cohort resource limits are excluded from model identity. | Omitted/revised replaced branching settings preserve tables, RNG and effective hash while changing supplied-input hash. Construction-step sigma remains an active consumer. Cohort limit-only edits preserve model identity. |
| F7: the last toggle selected a different forest regime | Schema 3 no longer calls `_fully_replaced`/`_configure_planned`; those functions were removed. It keeps native birth-order traversal and independently selected placement, corrections, dimensions, directions and material. [AxisState](../../deeprootgen/model/axis_state.py) is the common facade for every input. | The last length toggle works with unchanged common origins and correction policy. Replaced dimensions work with native placement. Mixed-order curvature/taper and construction-step/taper cases pass. |
| F8: limits checked after allocation | [Allocation budget](../../deeprootgen/model/budget.py) checks primary/count lower bounds before forest setup; organ reservations precede construction; construction nodes and physical stations are checked before their allocations; output graph size is checked before publication. | Instrumented small-limit cases verify explicit failures and bounded allocation counts. Historical cohort failure precedence remains unchanged. |

`AxisState` references the existing organ workspace for live geometry and
attachments, with immutable birth values and sampled lengths. Its curve and
material profile have separate owners. It introduces no second mutable forest
or new complete generator. Native kernels still use their transitional
graph-shaped workspace through this facade. The historical cohort adapter keeps
its declared sampling schedule; the public schema-3 option set never infers it.

## Canonical options and crown emergence

The [canonical option boundary](../../deeprootgen/data_model/native_options.py)
reuses established leaf kernels. The checked [field inventory](../../deeprootgen/data_model/inventory.py)
now gives canonical destinations for previously adapter-only controls:

- `primary_placement`: primary yaw/reversal, inclination bias and explicit design;
- `branch_sites`: native site placement, supplied counts, primary zone/fractions and parent-2 zone;
- `sibling_lengths`: tertiary sibling-length rank association;
- `insertion`: row-axial insertion by order;
- `direction`: per-order Fichtl sigma, higher-order assumptions, original construction-step stationing, first-insertion/boundary rules and explicit correction policies;
- `materialization`: bounded length-metadata reconciliation for tapered axes.

Competing owners fail explicitly. Existing v1 Fichtl/order/CDF/seed restrictions
are retained and documented. Canonical construction-step directions now feed the
same curve/materializer as curvature and can compose with taper. Their geometric
incoming tangents may differ from historical carried unit vectors by binary64
roundoff; matched invented canonical/adapter checks use `rtol=atol=1e-12`.
Historical adapter references and their exact comparisons were not loosened.

For a trunk buried 20 cm, use [native_crown_0_20cm.json](../../examples/design/native_crown_0_20cm.json):

```json
"primary_origins": {
  "enabled": true,
  "settings": {"layout": "disk", "radius_cm": 0.0, "depth_range_cm": [0.0, 20.0]}
}
```

Each first-order root samples its own depth below `soil_surface_z_cm`. Zero
radius places origins along the buried trunk; a positive radius adds lateral
crown spread. This emergence interval is separate from root-system depth. Default
common origins remain available. All origins are nonmaterial support points.
Primary-tree labels remain distinct from independent vine identities.

## Provenance and compatibility boundaries

Tracked inputs are frozen before execution, including original file bytes used
for the input-file hash. Exported parameters reproduce the executed input. The
loaded Python-function fingerprint is separate from the disk-source hash; it is
an audit fingerprint, not authentication of arbitrary mutable globals, function
closures, external native code or an entire notebook process. Source changes
after the model-import checkpoint fail before execution and require restart.
Legacy unseeded output is preserved, with its replay limitation explicit.

Schema-3 replaced-dimension runs now retain native placement/correction draws;
the former all-replaced/no-native-draw promise was part of the reviewed bundle
coupling and has been removed from tests and documentation. Native all-off and
historical adapter parity remain separate tests. The fully replaced example can
still omit unused dimension fallbacks.

All eight public historical references reconstruct from authenticated frozen
preimages in `baseline_modules.json.gz`. The archive was extracted from existing
manifest baseline commits and checked against existing hashes. No historical
postimage or numerical tolerance was rebound. Standalone preflight and tamper
checks distinguish fixture failures from intended diagnostic assertions.

The `graph_segments_v1` branch in `research/search_evaluation.py` is explicitly
archived and retains its historical replay. The supported construction-step
search branch already enters `run()` and uses the detached INITIAL adapter. The
tracked notebook now names `native_feature_options.json`; the previous
`.proposed.json` input remains executable for compatibility.

## Validation receipts

Final verification and exact source hashes are recorded locally under
`.runtime/native-improvement-20261118/`. Python 3.10.20 and the existing locked
overlay were used; no package installations or dependency upgrades occurred.

| Check | Final result |
|---|---|
| Full suite, `--run-integration` | **1,953 passed; 0 failures/errors/skips**, 103.805 s |
| Public fixture preflight | All 8 reconstructed; existing reference records/postimages unchanged |
| Canonical option probes | 25 passed in the focused final option run; included in full suite |
| Tracked export/reload matrix | 6 cases, all exact CSV/identity replay, all zero invalid nodes |
| Changed Python files, flake8 | 0 errors |
| `git diff --check` | Passed |
| Source/lock binding | `source_manifest.json`, 88 hashed files, unchanged after verification |
| Preserved files | Lock, dependency manifest, CONTRIBUTING and CODE_OF_CONDUCT unchanged |

The reusable [offline matrix script](../../scripts/validation/native_engine_matrix.py)
uses six invented cases: all-off; primary curvature; parent-only taper;
mixed orders; replaced dimensions with common origins; and buried-trunk origins.
Each exports, reloads saved parameters, and checks exact node/edge CSV and
execution-identity reproduction. Every case has zero invalid nodes.

```bash
CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$PWD/.runtime/native-integration-20261117/locked-overlay:$PWD" \
.runtime/envs/py310-qualification/bin/python -m pytest \
  -p no:cacheprovider --run-integration -q \
  --junitxml=.runtime/native-improvement-20261118/verified-full-tests.xml
```

Run the matrix with the same environment and a new output directory:

```bash
.runtime/envs/py310-qualification/bin/python \
  scripts/validation/native_engine_matrix.py --outdir .runtime/my-new-native-matrix
```

Changed-file lint and whitespace validation are scoped to this change. A broader
tracked-file lint run also reports existing style errors in the untouched
`scripts/docs/build_input_layers_pdf.py`; those were preserved. A first unscoped
lint invocation included ignored local report scripts, so its count is not a
repository validation result.

Claude was tried within the owner's authority but failed before receiving model
input (`connection_failed`, `EAI_AGAIN`); no Claude edits or API usage were
recorded. This environment exposes no usage-reset or automatic-resume control.
No reset was performed and no tomorrow continuation was scheduled. The report,
source manifest and receipts provide a continuation checkpoint if needed.
