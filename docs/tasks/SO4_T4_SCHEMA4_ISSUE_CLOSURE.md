# SO4/T4 and mature-vine code robustness, consistency and issue closure

Later Calvin continuation: the owner has requested an
[RLD-focused search with total biomass control](CALVIN_RLD_BIOMASS_SEARCH.md).
Its new planned iteration envelope and objective apply to that continuation;
the original study design, 480-call budget and evidence below remain historical
records. SO4 criteria are not changed by the Calvin objective revision.

Designed and revised 19 November 2026. The follow-up implemented the schema-4
contract fixes and ran the bounded development comparisons. The local
[execution record](../../.runtime/schema4-issue-closure-20261119/REPORT.md)
records the software checks, candidate decisions, and remaining evidence gaps.
The design and original acceptance rules are preserved below.

The three remaining construction features now have a
[detailed implementation plan](../research/SPATIAL_CONSTRUCTION_FEATURES_IMPLEMENTATION_PLAN.md):
versioned calculations, proposed canonical JSON, code ownership, conflicts,
analytic and integration tests, staged deliveries and bounded local evaluation.
Use that plan for the new feature implementation, alongside the follow-up
execution record above. Existing repairs and observation helpers must be reused;
the scientific/data protections and original evidence remain preserved here.
The [schema-4 implementation record](../research/SPATIAL_CONSTRUCTION_IMPLEMENTATION.md)
records the completed software checks, including the eight feature combinations.

The owner's cutoff follow-up adds a [local Calvin data/QC work package](../research/CALVIN_DIAMETER_CUTOFF_AND_QC_PLAN.md):
reprocess targets at 0.50 and 0.93 mm, preserve originals, document exclusions
for source inconsistencies, and compare cutoff/QC effects on matched supports.
The [local comparison report](../../.runtime/calvin-cutoff-qc-20261119/REPORT.md)
records the completed target preparation, workbook QA, paired observation
cutoffs and separate parent branching-gate sensitivity.

## Goal and current evidence

Improve robustness and consistency of the existing shared engine and its
configuration, branching, validation and run-record contracts. Close the remaining
issues from the 18-month schema-3 review without introducing a second engine.
Preserve the five-order curvature route and evaluate spatial allocation jointly
with depth. The owner accepts an optimized insertion angle, including the current
selected value; 35 degrees is an optional comparator, not a required baseline.
Use measured initial primary counts and arrangement when supplied. Otherwise let
optimization choose the count and outer/inner split within documented bounds;
seven primaries split 3/4 is a starting candidate, not a constraint.
These are static architecture inputs; an 18-month label does not enable growth.

The owner's subsequent source request adds a separate **mature-vine parameter
arm**: account for excavation damage, inspect the linked perennial model and
48-year-old 5C archive, and propose better priors for Calvin. In this task,
"old route" means the mature-vine reconstruction through the shared schema-4
engine; it does not authorize restoring or modifying an archived constructor.

The engine defect already has a schema-4 repair in PR #18, commit
`690f65b66fe644319eb32693e0dc5214d24273fd`. The canonical validator checks the
realized curve start and first-interval endpoint; materialization checks the
physical pieces. Do not implement a second repair or weaken graph checks.
Archived schema-3 execution retains its historical behavior. Public generation
requires explicit conversion to schema 4.

The earlier 19 November audit froze that PR commit and matched all 102 Python package files
against the canonical checkout. Forty-seven focused tests passed without skips,
including invented five-order curvature, Fichtl three-order curvature,
repeatability and a corrupt-attachment rejection. This is software evidence.
The existing full-suite and population receipts are separate historical runs.
Audit records are local at `.runtime/so4-issue-audit-20261119/`.

Read `docs/research/ACTIVE_SO4_RESEARCH.md` first. The later population search
already tested higher-order settings and passed its 16 scalar and three marginal
profile checks on 96 reserved seeds. The subsequent joint-spatial reanalysis
ranks the earlier starter ahead of that selected candidate. Reuse both records;
neither marginal agreement nor new simulator seeds establish unseen-vine validity.

## Frozen inputs and boundaries

1. Recheck the source owner's chat, **Complete single-route merge design**, PR #18
   and its final revision. At the earlier audit, that chat turn was interrupted
   while removing historical-source comparisons in its PR checkout. Coordinate ownership before
   editing; do not stage or overwrite its outstanding engine/test changes.
   Freeze the completed source revision and dependency lock for this task.
2. Preserve the original schema-3 parameter list, its PDF, sealed T2 studies,
   D-04 studies and all existing T4 candidates and receipts. Read processed T4
   evidence locally from the existing bundles. The specifically requested public
   mature-vine archive may be inspected locally. The owner's later cutoff
   request now includes local raw Calvin workbook reprocessing solely for the
   linked two-cutoff/QC work package. Preserve originals and existing derivatives;
   record hashes of every input, processing script and observation operator.
3. Use the `grapevine3d-soil-frame-v2` convention and the same eight-vine
   population. Preserve independent vine identity, root-only material and the
   soil-clipping operator. Fix bin origins, extents, overflow handling and vine
   weighting before comparisons.
4. No dependency upgrades, flows, services, deployment, whole-vine biomass fitting, remote
   empirical uploads, new paid agents, automatic merge or push. This design does
   not launch work. Use the existing Python 3.10 environment for later execution.
   The mature-vine arm may compare against the existing paired core RLD and
   dry-mass targets on their documented diameter and sampling support. Do not
   manufacture a whole-vine mass target from incomplete excavation counts.

## Work package 1: configuration decisions and exact branching assumptions

- Reuse a new version of the selected schema-4 input with curvature on orders
  1–5. Keep insertion angle adjustable within predeclared bounds and accept the
  fitted value if it survives the spatial and robustness checks. A 35-degree
  ablation is optional; do not replace a better supported value merely to restore
  the earlier suggestion.
- Distinguish initial conditions from inferred parameters. For an individual
  with known initial primary roots, fix its measured count/arrangement and record
  provenance. For an unknown individual or a population model, compare admissible
  integer counts and outer/inner allocations. Bounds come from the existing local
  processed evidence or explicit assumptions. Resolve each candidate once:
  `outer = round_half_up(primary_root_count * outer_primary_fraction)` and
  `inner = primary_root_count - outer`. Deduplicate identical resolved allocations
  in the search. Group membership is a placement convention, not automatically
  an anatomical shallow/steep label. Do not pool independent vines as primaries.
  The public count is currently a fixed integer per input; compare explicit
  integer candidates rather than silently interpreting it as a distribution.
- Describe each branching stage by parent order: first-site distribution,
  branch probability, daughter-count law, site placement and local diameter
  eligibility. Separate measured inputs, T2 transfers, assumptions and fitted
  values. State that the branch-free *distribution mean* is not a hard minimum.
- Reuse the existing order-3–5 trial history before proposing changes. Keep
  transferred assumptions visibly separate from empirically explored choices.
  Root counts and length CDFs supplied from the comparison population are
  conditioning information, not independent predictive evidence.
- Use `explain_config` to list supplied, effective, replaced and unused inputs.
  Remove unnecessary native fallback values from the new review file where
  supported, then verify identical seeded geometry and effective identity.
  Retain values consumed by birth material, discretization or compatibility draws.

Deliver a runnable private JSON, notebook review cells and a decision/provenance
table. Preserve original files rather than updating a sealed candidate in place.

### What the current branching law actually assumes

Inspect `model/laws.py:first_branch_sites`, `model/cohort_geometry.py:bounded_draw`,
`model/native_features.py:branch_sites` and `model/branch_eligibility.py` against
the frozen source. The current selected T4 input uses replacement branching for
parent orders 1–4 and has cohort maturity disabled:

1. For each parent, sample first-site distance `F` along its contour from a
   bounded lognormal. The supplied mean and SD describe the underlying
   **untruncated** lognormal, not necessarily the realized bounded moments.
2. Make a Bernoulli decision with the order's probability `p`. No daughters are
   proposed if that draw fails, `F >= parent_length`, or the parent is terminal.
3. If branching succeeds, draw `N` from the supplied categorical probabilities
   on counts 1, 2, ... . One daughter is at `F`; the remaining `N-1` sites are
   sorted independent uniform draws between `F` and the parent tip. No minimum
   spacing or hard apical exclusion follows from this replacement law.
4. For order-2 emergence, the enabled relocation moves primary attachment arcs
   through `s_new = b*L + (1-b)*s`; keep `b` explicitly supplied and recorded.
5. The current baseline requires local parent diameter **at the final attachment**
   to be at least 0.093 cm (0.93 mm). The linked cutoff work package may compare
   an explicit 0.050 cm gate separately from observation filtering; neither is
   an automatic default change. Thin sites are rejected before daughter/subtree
   allocation. Exact-count conditioning must fail explicitly if infeasible.
   Diameter filtering and other documented construction failures can reduce
   realized counts relative to the count proposal.

This is the selected young SO4/T4 parameterization, not the mature-vine Excel
parameterization. A short nursery scaffold and a mature trunk-borne main axis
must not receive the same prior simply because both have order number 1.
Use the mature-vine arm below for the separate excavation-damage question.

Consequences: within a parent order the selected law does not make the count
distribution increase continuously with parent length. Length acts through the
`F < L` censoring, site positions and diameter eligibility. Probability/count
parameters were chosen to reproduce pooled count ratios; that does not identify
the observed parent-child association. First-site mean, minimum distance and a
hard branch-free zone are different parameters.

Export the exact current per-order values into a **local** assumptions table:
first-site underlying mean/SD/bounds, `p`, every daughter-count probability,
relocation and eligibility. Include the corresponding resolved JSON paths and
whether each value is measured, transferred, assumed or fitted. The local
`BRANCHING_ASSUMPTIONS_UPDATE.md` alongside the audit records captures the values
inspected for this revision; reread the final executed configuration before use.
Do not copy empirical/fitted tables into public repository documentation.

## Work package 2: shared code contracts and robustness fixes

Make this the implementation priority. Begin with small invented counterexamples,
then fix only confirmed defects. Retain existing default and archived behavior
unless a separately specified correction requires a versioned difference.

- **One configuration meaning:** Python, CLI, supported notebook helpers and
  application request builders must resolve an equivalent schema-4 document to
  the same active laws, units, initial conditions and effective identity. Check
  seeded geometry and export/reload agreement through these supported routes;
  use offline/mocked request builders without starting flows or services.
- **One owner per operation and order:** requirements must follow active
  consumers. Replaced fields must either be explicitly inactive or rejected as
  conflicts, rather than silently activating another construction regime. Test
  omission and perturbation of inactive fields against effective hashes, geometry
  and unrelated RNG streams. Preserve documented compatibility draws.
- **Branching validation:** reject nonfinite/negative probabilities, invalid
  categorical totals, impossible supports and malformed order maps before
  allocation. Test analytic proposal probability and expected count
  `p * P(F < L) * E[N]` before diameter filtering, using tractable invented
  fixtures and a declared stochastic tolerance where sampling is necessary.
  Test the bounded distribution rather than treating its input mean as the
  realized mean. Cover terminal order, no daughters, one daughter, `F == L`,
  and local diameter just below, exactly at and above the inclusive minimum.
- **Attachment and material consistency:** verify eligibility after relocation,
  continuity on curved parents, descendant parent links and finite geometry.
  Graph subdivisions must not create new biological branches or direction draws.
  Preserve total length and material under pure subdivision and relocation where
  the selected law promises conservation; do not impose invariance on intentional
  length/material changes. A corrupted attachment must still fail.
- **Stable initial conditions:** test integer count and split resolution,
  including zero in either group, rounding boundaries and mismatched supplied
  arrangements. Reject inconsistent inputs before constructing a partial forest.
- **Reproducible and truthful records:** seeded runs must repeat their outputs
  and identities; input, effective-model and run identities retain their separate
  meanings. Record resolved integer counts/splits, sampled first sites, proposed
  and accepted daughter counts, rejection reasons and invalid axes by order.
  Never turn invalid geometry into a successful optimization trial, silently
  drop failed seeds, or call an unseeded run replayable.

Completion of code hardening is independent of a better fit. A failed spatial
target must remain a research result, not a reason to weaken a validator, alter
an observation operator or change a test tolerance after seeing the outcome.

## Work package 3: distinguish implemented controls from remaining gaps

Build a route-specific availability matrix with canonical JSON path, active
consumer, supported combinations, units, conflicts and test evidence:

| Earlier gap | Current disposition and next action |
|---|---|
| Curved daughter validity | Repaired for schema 4. Promote the local strong-curve positive and corrupt-attachment negative probes into maintained tests if equivalent coverage is absent. Include descendants and a first construction interval containing several curve pieces. |
| Primary yaw/inclination/reversal | Available through `primary_placement`; verify the chosen five-order combination. |
| Row-axial insertion | Available through `insertion.row_axial_kappa_by_order`, including curved insertion headings. It controls the initial azimuth, not persistent along-row drift. |
| Counts, branch zones and supplied fractions | Canonical `branch_sites` controls exist but retain scope restrictions and conflict with replacement branching. Do not claim they compose with every five-order curvature configuration. |
| Per-order sigma, higher-order Fichtl rules and construction stations | Canonical `direction` controls exist with explicit ownership and assumptions. They are alternatives to a competing curvature owner. The chosen route needs no new Fichtl law. |
| Sibling length-rank association | Canonical `sibling_lengths` exists; check its supported route before use. |
| Persistent along-row drift | Not implemented. Detailed plan D1 adds opt-in symmetric row-axis alignment inside physical curvature integration; qualification and paired spatial comparisons are separate. |
| Joint origin catalogue | Not implemented. Detailed plan D3 selects one coherent common-point or complete primary-origin record per vine, with explicit count/frame ownership and local provenance. |
| Parent-length-dependent daughter counts | Not implemented as the new general law. Detailed plan D2 adds a separately named Poisson site process over a parent branch zone with the existing diameter gate; retain the older restricted branch-zone control and first-site/count law. |

One additional consumer limitation was reproduced: an all-curved five-order
configuration with fallback `fichtl2024` is rejected for missing higher-order
Fichtl entries. The approved all-curved legacy-fallback route works. Check whether
this is a documented scope constraint or an unnecessary inactive requirement;
only change canonical validation after defining and testing the consumer rule.
Preserve archived behavior and reject genuinely missing active Fichtl laws.

Do not add all possible controls at once. If a scientific construction change is
needed, specify its distribution, coordinates, units, seed stream, default-off
behavior and conservation properties first. Change one construction rule per
comparison. No silent mapping of Fichtl sigma into curvature parameters.

## Work package 4: spatial comparison and bounded refinement

Reuse the existing notebook, replay archive and scoring scripts under
`Calvin_SO4_Parameter_Exploration_2026-11-18/Spatial_Evaluation_2026-11-19/`.
The earlier starter and selected `local111` candidate are separate comparators.

1. After software checks pass, verify saved identities and reuse the selected
   angle as a starting candidate on a common, declared development seed panel.
   Optimize unknown primary counts/splits along with the declared orientation
   controls; fix measured initial conditions. Existing reserved seeds are now inspected
   evidence and must not be relabeled as a new untouched confirmation panel.
2. Rank by joint across-row/along-row/depth root-length allocation. Show joint
   XYZ, across-by-depth and along-by-depth TV at fixed 10, 20 and 40 cm grids,
   alongside marginal profiles and the existing scalar checks. Whole-root length
   alone cannot select the winner. Show per-vine variability and uncertainty.
3. If refinement is needed, propose at most three sequential rounds, each with
   at most eight candidates on 12 common development seeds. Include paired
   ablations of orientation, curvature/drift, then branching only as needed.
   Cap new refinement calls at 288; stop early when no useful improvement appears.
   Use one worker, two compute threads and at most 1 GiB of new phase outputs.
4. Freeze one candidate before a new 96-seed confirmation panel, disjoint from
   all previously used seeds. Compare the frozen candidate and a fixed spatial
   comparator on those same seeds: at most 192 confirmation calls. Total proposed
   new-simulation cap is 480, including any initial or 35-degree ablation in refinement.
   Save failures as trials rather than dropping them or replacing their seeds.

Proposed acceptance: maintain every existing T4 scalar relative-error check at
or below 20% and all three marginal profile TVs at or below .20; improve the
10 cm joint spatial score over the earlier spatial comparator, and report
coarser-grid and projected changes. Freeze any allowed non-regression tolerance
before selection. The prior .20 threshold was **not** a joint-voxel tolerance.
There is no owner-approved absolute joint-TV qualification threshold yet.
If the spatial and scalar conditions conflict, report the tradeoff without
declaring a qualified architecture or relaxing the criteria after seeing results.

Select the angle and unknown primary arrangement by the frozen objective and
confirmation evidence. Neither 35 degrees nor a 3/4 split is a pass condition.
Explicitly distinguish measured initial conditions, optimized parameters,
starting comparator, development winner and confirmed research candidate.
Population fit remains on the observed support.

## Work package 5: mature-vine priors and incomplete excavation observations

Read the local evidence and proposed values in
[mature-vine source audit and parameter proposal](../../.runtime/mature-vine-branching-evidence-20261119/PARAMETER_PROPOSAL.md).
It includes the exact provisional numerical values, source hashes, axis inventory,
reproducible extraction and limitations. These are review candidates, not adopted
defaults or a completed fit. Keep empirical tables and resulting configurations
local.

### Evidence and source reconciliation

- [Zenodo 17637194](https://zenodo.org/records/17637194) contains three 48-year-old
  Riesling/5C vines with a restricted excavation window. It is a different
  population from Calvin and young SO4. Its archive and README were retrieved
  locally with published checksum verification.
- The requested [dumux-rosi branch](https://github.com/Plant-Root-Soil-Interactions-Modelling/dumux-rosi/tree/2c6c98c47231c9a081f91f1addb5e608c158ad7e)
  was inspected. The corresponding grapevine construction parameters and script
  overrides are in the author's [CPlantBox branch](https://github.com/Plant-Root-Soil-Interactions-Modelling/CPlantBox/tree/7d190b50728c514baab6ccfbaa49ad98156f217d),
  linked by the [2026 paper](https://nph.onlinelibrary.wiley.com/doi/10.1111/nph.71727).
  Do not execute or install these frameworks as a side effect of parameter review.
- The public raw-ID and supplied RSML axis inventories disagree beyond primary
  order. A conflicting duplicate raw point ID also exists in one vine. Resolve
  conversion/filtering definitions and axis correspondence before adopting a
  distribution. No silent duplicate removal, coordinate choice or assumption
  that the larger inventory is complete biological truth is allowed. The local
  analysis excludes ambiguous geometry and preserves explicit sensitivity cases.
- Identify root order by anatomical parentage, not a fixed numerical offset.
  Author successor probabilities are per-site and age-dependent; the simulation
  script rescales them when it changes interbranch spacing to its computational
  step. They are not equivalent to the present per-parent branching probability.
  Potential dynamic maximum lengths are not static current-length means.

### Observation reliability and proposed parameter changes

1. Preserve useful excavation information while representing incompleteness.
   Distinguish known initial crown counts, local diameter/taper measurements,
   segment-to-next-branch lengths, whole-axis recovered lengths, broken tips,
   missing daughters, complete zeros and unavailable values. A broken recovered
   whole axis can provide a lower bound; a segment length is not automatically
   a whole-axis lower bound or an interbranch interval.
2. Retain the current Calvin fit as comparator. Add the local proposal's mature
   structural reference for first-site, branch probability and conditional
   daughter-count priors. Its proposed sparse higher-order arm is separate from
   the existing dense higher-order allocation. Some parameters remain too weakly
   observed to justify a new point value. Verify structural/fine root class and
   diameter support before preferring either allocation.
3. Treat the proposal's rounded numerical settings as engineering starting
   candidates informed by censored observations. First observed branches are
   measured on a selected branch-positive subset; fit or compare the full
   length/diameter/recovery observation process rather than equating that sample
   mean with an unconditional lognormal parameter. Use vine-level resampling;
   individual axes within three vines are not independent replicates.
4. Test recovery multipliers 1, 2 and 3 as labelled **sensitivity scenarios** on
   specified order-specific counts and sampled support. A factor of three is not
   an observed correction. Define its implied detection fraction and affected
   material. Do not multiply branch probability, all generation counts, lengths,
   diameters and known initial root numbers together; effects can compound down
   a subtree. The raw/RSML count ratio is a representation issue, not a recovery
   estimate. Do not inflate independent core RLD or dry-mass measurements.
5. Consider a length-dependent site/count law if it improves structural
   consistency. Observed successive gaps can motivate a spacing prior but do
   not alone determine the overall branch rate across all material. A new law
   requires explicit basal/apical support, probability/count meaning, default-off
   behavior and tests. Do not claim the current uniform-sites law already
   implements the author's spacing process.
6. A longer primary upper-support sensitivity may be justified because both
   archives and excavations are truncated. Retain the existing comparator and
   distinguish an upper-bound scenario from a distribution mean. No observed
   depth limit or universal whole-axis maximum follows from excavation extent.

### Comparison and code acceptance

Use the current fit, mature structural reference and predeclared recovery
scenarios in the **same shared task budget** as work package 4. Allocate candidate
slots between SO4 and mature-vine arms before execution; do not add an unbounded
new search. Unused scenarios may remain prepared if the budget is exhausted.
Keep measured initial conditions fixed, tune only identified unknown parameters,
and compare matched core location/depth RLD and dry mass with whole cores held
out. Report joint allocation, paired errors, measurement sensitivity and
uncertainty. The mature arm has its own population and criteria; SO4's marginal
TV and scalar thresholds are not Calvin acceptance criteria.

Add source-adapter and observation-contract checks: duplicate IDs fail with a
useful diagnostic; raw/RSML count discrepancies stay visible; root/type/unit
crosswalks are explicit; boundary-truncated length cannot become a full-length
target; missing cannot become zero or a fixed threefold correction. For any
new branching law, test expected counts on analytic fixtures, seeded replay,
eligibility at final attachment, and invariance to purely geometric subdivision.
Search bookkeeping must retain unsuccessful/censored trials and separate input
assumptions from generated observations. Preserve sealed SO4 fits and historical
Calvin constructors/results.

Deliver a private mature-vine parameter proposal, prior/source/reliability table,
observation support contract and notebook comparisons beside the existing SO4
deliverables. Keep source-reconciliation uncertainty explicit if it remains.
Software hardening can pass while biological parameter adoption remains pending.

## Work package 6: Calvin cutoff sensitivity and measurement QC

Execute the [two-cutoff/QC plan](../research/CALVIN_DIAMETER_CUTOFF_AND_QC_PLAN.md)
before new Calvin feature comparisons. Reproduce the historical 0.93 mm targets,
derive 0.50 mm targets from the original local diameter classes and weights, and
freeze a source-based exclusion ledger. Preserve both all-usable and strict-QC
views; large model residuals are not measurement-error evidence. Keep the parent
branching gate and observation cutoff distinct, and retain the 2.5 mm reporting
split. Rescore identical geometries first; any regenerated or lower-gate runs
consume the existing 480-call budget. Deliver local target/workbook derivatives,
support counts, scripts and before/after-QC comparisons without overwriting raw
data or claiming a new cutoff is validated by a better fit alone.

## Optional follow-up: use excavation measurements in reconstruction

The owner's clarification adds an [optional measurement-conditioning design](../research/OPTIONAL_EXCAVATION_CONDITIONED_RECONSTRUCTION.md).
Use order-1–3 positions, directions, documented counts and local diameters to
inform a fresh reconstruction through supported initial conditions, uncertain
priors and support-aware scoring. Importing a measured graph and extending its
broken tips are not required. Start with preparation and existing supported
controls; direct order-2/3 constraints are a contingent later adapter. Preserve
measurement completeness, ancestry, station definitions and independent
assessment. Do not infer diameters/counts from positions and angles alone or
add trials outside the shared recorded budget. This is a proposed follow-up,
not a claim that arbitrary measured-root constraints already execute.

## Validation and deliverables

For any engine change, run focused synthetic tests, the applicable full
`pytest --run-integration` suite, changed-file lint and whitespace checks on a
frozen source. Preserve meaningful current-engine checks during the other chat's
test cleanup. Verify export/reload identities and exact geometry for supported
seeded cases. Record commands, environment, source/lock/config/operator hashes,
invalid organs by order, finite material, attachment continuity and graph integrity.

Keep empirical deliverables local: the review JSON, complete trial ledger,
reproducible notebook, joint spatial plots, private assessment, and an updated
printable parameter list with editable source. Regenerate and visually verify
the PDF, mark the original schema-3 document historical, and list unresolved
assumptions. Public documentation may describe software semantics and invented
examples without exposing observed arrays or fitted settings.

Finish with an issue-by-issue disposition and evidence links. State separately
what is implemented, tested, still uncommitted, present in the PR, and merged.
Provide separate software and research dispositions. The software disposition
requires the shared contracts, meaningful regression cases, applicable full
suite, lint and exact supported replay checks. The research disposition may
remain unresolved even when code robustness and consistency are verified.
