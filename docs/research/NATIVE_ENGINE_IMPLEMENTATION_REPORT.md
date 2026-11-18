# Native engine implementation report

18 November 2026. Implements deliveries 0–5 of the
[native feature composition plan](NATIVE_FEATURE_COMPOSITION_REVIEW_AND_PLAN.md).
Base: HEAD `ff1a1df17381de3907f9799a56fb8f62008f6b47` plus the uncommitted
integration work, snapshotted with source hashes before any edit under
`.runtime/native-engine-20261118/before/`. Nothing was committed.

This is a software refactor. No fitting, calibration adoption, service startup,
private-data inspection or biological qualification took place; every input is
invented.

## 1. Outcome

* **One engine.** Every input runs through one resolver and one fixed engine
  lifecycle: legacy flat, schema 2 (native, `construction_steps_v1`,
  `cohort_v5`) and schema 3. The three separate complete bodies are deleted:
  `_run_native`, `run_construction_steps` and `run_cohort`, together with the
  queue `_realize_organs` and the in-place writer `apply_records`.
* **Exact historical outputs.** Old inputs are adapters that declare their
  historical laws, streams, identity allocation and output format. Their frozen
  references are unchanged and exact: tables, node IDs, RNG state, INITIAL
  snapshots, construction-step intervals and fragments, cohort diagnostics,
  sidecars and crown support.
* **Independent features.** One JSON switches correlated curvature (any order),
  point taper, primary origins, maturity, lengths, branching, parent capping
  and attachment relocation on and off. Each is a leaf law inside the shared
  phases, and supported combinations are declared and checked before execution.
* **First proof.** Native generation with primary curvature switched off → on →
  off in the same JSON file recovers the native baseline exactly. Biology,
  placement draws, material and organ identities stay unchanged while the
  curves change.
* **Traceable notebook runs.** `run_records.tracked_run` and
  `notebooks/grapevine_fichtl_2024/6_native_engine_tracked_runs.ipynb` record
  the input used, resolved laws, model identities, git state and an
  append-only ledger.

## 2. Architecture as implemented

| Owner | Responsibility |
|---|---|
| `data_model/resolution.py` | `load_json_config` (duplicate keys fail), `parse_config`, `resolve_config` producing `EngineLaws` (one law per stage and order) plus the resolved description and identities; adapters for old inputs; schema-3 supported-combination checks |
| `data_model/features.py` | Schema 3: top-level seed/tag, `parameters` (native fallbacks; construction fields optional when no native kernel uses them), eight feature blocks, `limits` |
| `data_model/inventory.py` | Checked inventory of all 106 historical fields (destination, units, activation, consumer, disposition) |
| `model/engine.py` | The fixed lifecycle and traversal; dispatch on `EngineLaws`, never on labels; workspace setup (including per-primary bases) and committing relocated attachments into the workspace |
| `model/root.py` | Native kernels, with feature hooks that are no-ops when no feature law is given |
| `model/laws.py`, `axis_laws.py`, `native_features.py` | Leaf laws: planned sampling, origins, headings, maturity, branching, curvature, taper. They allocate no graph identities (checked statically) |
| `model/execution.py`, `attachment.py`, `interval_geometry.py` | Construction-step kernels: the one distal-relocation law and the interval direction law |
| `model/materialize.py` | Cut union (construction, attachment, corner, material cuts), taper integration, per-segment classification |
| `model/hgraph.py` `publish_graph` | The one writer; two declared allocation policies: birth order, and records (construction-step contract) |
| `model/views.py` | One `SimulationResult` class; contents by capability; the historical serialization each adapter declares; receipts in `result.engine` |
| `model/streams.py` | The native sequential stream, cached keyed streams, and the historical cohort `SeedSequence([seed, organ, purpose])` streams |
| `run_records.py` | Tracked runs and ledger for notebooks and scripts |

The forest state during construction is the workspace: provisional
construction points plus `RootOrgan` axis records. Record-based interval laws
use a records view of the workspace from attachment mapping onward. The
published graph is written once, after geometry is stable. The workspace
stands in for the plan's array-backed `AxisState`; see section 7.

## 3. Deliveries

| Delivery | Implemented |
|---|---|
| 0. Input and baseline | Sources snapshotted. One parser. Duplicate keys rejected. Flat parsing (CLI, API and direct `RootSimulationModel`) rejects versioned keys, feature names and their case/plural/separator variants. Field inventory with a coverage test. |
| 1. Common state and lifecycle | Fixed phases, single writer and RNG owner. Exact native legacy and Fichtl parity (tables, IDs, final RNG state) for flat and schema-2 native inputs. |
| 2. Canonical JSON and first option | Schema 3 and primary curvature; off → on → off proof; dormant invariance; explanation; identities; caller parity. |
| 3. Material and origins | Point taper on native or planned axes (analytic volume, unchanged geometry, cutoff cuts); point and disk origins; parent cap; dependency checks before execution. |
| 4. Remaining calculations | Length laws (bounded lognormal; discrete CDF through the existing kernel), first-branch branching, maturity groups, distal relocation, curvature on daughter orders with a keyed insertion law, planned (fully replaced) construction. |
| 5. Adapters and runner removal | Construction-step and cohort adapters through the shared phases with exact frozen parity. Runners and duplicate writer removed. Capability-based result views. |

## 4. Decisions made during implementation (please confirm or redirect)

Each is implemented, tested and recorded in the resolved description.

1. **Native schedule.** A replaced direction law draws only from its keyed
   stream. Native validation visiting a replaced axis takes its usual draw but
   only checks. Biology and placement draws are unchanged; later correction
   draws can differ when validity outcomes differ (an invalid axis draws
   nothing). A replaced construction law draws nothing natively.
2. **Initial headings.** `scaffold_chord` (the placed native scaffold, after
   the Fichtl primary correction where that applies), `origin_heading` (disk
   origin with radial inclination) or `insertion_angle` (a keyed truncated
   normal about the realized parent tangent; required for daughter orders).
3. **Native daughters of a replaced parent.** Legacy daughters move rigidly
   with their attachment point, because the native legacy law orients daughters
   in the parent's placement frame. Fichtl daughters start from the incoming
   realized curve piece, approached from the same side as the published edge.
4. **Materialization.** One merge rule applies to native axes and to schema-3
   planned axes. Construction cuts are kept exactly. A direction corner is
   added only if it is more than 1e-9 cm from every kept cut, and a material
   cut (midpoint, fine-cutoff crossing) likewise, so a merged material
   breakpoint moves by at most 1e-9 cm. The cohort adapter keeps its exact
   historical union, in which near-coincident cuts fail as before.
5. **Taper on native axes.** Native daughters inherit the equivalent diameter
   of their birth construction interval. Every tapered segment is classified
   fine/structural by its equivalent diameter, primaries included. Native
   diameter draws still occur at their historical positions, so geometry and
   topology stay paired.
6. **Lengths.** `bounded_lognormal` keeps the native segment proportions and
   adds no inherited parent-length term, matching the existing CDF law.
   `discrete_cdf` reuses the keyed current-length CDF kernel and is supported
   on daughter orders 2–5.
7. **Maturity.** Groups of zero-based primary indices (outer, then inner).
   A range with low == high is fixed (no draw); otherwise uniform. Maturity
   scales whole organ length, the taper base and, when declared, branch
   probability. It never changes origin layout.
8. **Branching.** The feature law replaces native count and spacing, with no
   native draws for that organ. The terminal order is `max_order`.
9. **Origins.** `point` uses the one common-base translation kernel shared with
   the historical research origin, without that input's Fichtl-only
   restriction. `disk` gives each primary a zero-material base (cohort
   template) after native placement.
10. **Planned construction.** It is selected when nothing native remains:
    curvature, taper, bounded lengths and branching on every order, and disk
    origins with a heading. Mixed native/planned forests are rejected.
11. **Streams.** Schema-3 features draw from independent keyed streams per
    purpose and biological organ ID. The cohort adapter keeps its historical
    shared streams and draw order.
12. **Identity.** Labels, resource limits, inactive mode fallbacks, no-op
    research values and dormant settings never change the effective-model hash.
13. **Numerical bounds.** For curvature: step 1e-3–1e3 cm, correlation
    1e-3–1e6 cm, SD ≤ 100 rad/cm, with OU coefficients checked finite.
    Rejection samplers must accept enough draws: radial inclination at least
    1% (the cohort validator's rule) and insertion at least 5% (its sampler
    has 1000 tries). Schema-3 native construction needs at least one outer and
    one inner primary, because native placement spaces each group around the
    base; old inputs keep their historical behaviour.
14. **Supported combinations.** Maturity diameter scaling and parent capping
    need taper on every order. Probability scaling needs the branching law.
    With legacy fallbacks, curvature must cover orders 1..k. Relocation needs
    daughters realized from the final attachment and excludes capping.

## 5. Behaviour changes for existing callers

* Every run needs a fresh simulator. A second flat run on a used simulator
  previously appended a new forest silently.
* Flat runs publish `simulation.result` and pass the pure integrity checks. A
  physically meaningless flat input (negative material) now fails explicitly;
  app and calibration bounds cannot produce one.
* Engine receipts (lifecycle, pre-direction RNG fingerprint, keyed streams,
  law receipts) live in `result.engine`. `result.diagnostics` holds model
  diagnostics; the historical adapters keep their exact dictionaries.
* The INITIAL recorder keeps its historical guard for old inputs: it is
  accepted only for construction steps. It is also available for schema-3
  native construction. Planned construction has no placed scaffold at that
  phase and rejects it.
* Cohort error precedence is unchanged. The organ-budget error is deferred
  until the overflowing organ has been realized, as the old runner did, and
  matches it on the review cases. Other doubly invalid inputs report the first
  error in phase order (sampling, then geometry, then material).
* The CLI writes `resolved_config.json` for every run. Its manifest adds model
  identities, the generator source hash and git state. Its `parameters.json`
  for schema-3 input reloads to the same model.
* Two orchestration tests that stubbed every kernel on a fake graph were
  rewritten as call-through spies on a real run. No expected output changed.
* Cost: about 1 ms extra per small run and 17–19% on a 530-node legacy run
  (63.9 → 74.9 ms in the final benchmark, `final/benchmark.log`), from
  resolution and law description, one emission copy, checks and the result view. Node counts are unchanged; nothing is generated
  twice.

## 6. Evidence

The command is `.runtime/native-engine-20261118/pytest.sh --run-integration`,
the established Python-3.10 command. The `locked-overlay` path on `PYTHONPATH`
is required by six prechange subprocess-parity tests.

| Gate | Result |
|---|---|
| Before any edit (with overlay path) | 1660 / 1660 |
| Delivery 1 | 1660 / 1660 |
| Delivery 2 | 1836 / 1836 |
| After first review fixes and notebook helper | 1856 / 1856 |
| Deliveries 3–5, runners removed | 1895 / 1895 |
| Final tree (ownership moves, examples) | 1902 / 1902; changed-source flake8 clean |
| After second review fixes | see `RECEIPT.json` (`final`) |
| Frozen references (flat, Fichtl, construction steps, cohort) through the one engine | exact |
| Notebook code cells run in order (no kernel installed) | all pass |

Receipts are in `.runtime/native-engine-20261118/`, one folder per gate, plus
`RECEIPT.json` with final source hashes and counts.

## 7. Remaining work

* **Research controls.** The engine executes these for old inputs (inventory
  `adapter_law`), but they have no schema-3 keys yet: primary yaw/reversal,
  inclination bias, explicit primary design, primary branch zone/fractions,
  parent2 zone, tertiary rank, row-axial insertion, per-order Fichtl sigma,
  higher-order tropism, count conditioning, the construction-step interval
  direction law and cohort length-metadata reconciliation.
* **Array-backed `AxisState`.** Native kernels still create workspace points
  while sampling. The published graph is single-owner, but a pure array state
  was not needed for parity or features and is not implemented.
* **Unsupported cases.** Mixed native/planned construction, other curvature
  boundary or first-interval conventions, and schema-3 input to services remain
  unsupported (services are flat-only by design).
* **Calibration throughput.** If needed, the identity case of emission could
  adopt workspace nodes instead of copying them.

## 8. Review status

An independent code review of deliveries 0–2 found eight defects. All were
fixed with regression tests:

1. The native-schedule claim was overstated; it was corrected and the review
   case added.
2. Unrepresentable curvature values failed late; they are now rejected up front.
3. Top-level feature names and their variants could be silently dropped by
   flat parsing; they are now rejected.
4. Integrity failure for negative flat material is now documented.
5. Simulator reuse is now documented.
6. The tangent side at a merged corner was wrong; it now matches the published
   edge.
7. The CLI's schema-3 `parameters.json` was not reloadable; it now is.
8. Inactive mode fallbacks changed the effective hash; they no longer do.

A second independent review covered deliveries 3–5 on the final tree. It
compared old and new trees on invented cases with no differences in tables,
IDs, RNG, diagnostics or organ bindings:

* cohort: 691 cases (442 successful runs);
* construction steps: 860 cases (711 successful runs);
* flat/native: 500 cases (454 successful runs).

It also confirmed that the native generator is untouched under fully replaced
construction, that taper keeps geometry and analytic volume, that origins and
maturity are independent, that relocation binds correctly, and that there is
one writer call per run. It found four defects and two minor differences,
all fixed with regression tests:

1. A corner and a material cut 1 ulp apart failed on tapered axes. Both now
   use the merge rule above.
2. A heading law with less than 1% acceptance failed late. It is now rejected
   at resolution.
3. The INITIAL-recorder guard had been removed. The historical guard is
   restored, and planned construction rejects the recorder.
4. Cohort budget-versus-reconciliation precedence had changed. The budget
   error is deferred again and matches the old runner.
5. Planned organs kept unconsumed birth queues. They are now consumed.
6. A cohort run changed the simulator's tag. The constructor's tag is kept, as
   before.

Two issues predate the refactor and are unchanged for old inputs: zero
primaries in a native group, and the cohort's 1-ulp site/station failure.
Schema 3 now rejects the first before execution and avoids the second through
the merge rule.
