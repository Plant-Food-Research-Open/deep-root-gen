# Calvin diameter-cutoff sensitivity and measurement QC

Added 19 November 2026 at the owner's request. This is a planned local data
work package, linked to the [construction-feature plan](SPATIAL_CONSTRUCTION_FEATURES_IMPLEMENTATION_PLAN.md)
and [issue-closure task](../tasks/SO4_T4_SCHEMA4_ISSUE_CLOSURE.md).
It authorizes a separate 0.50 mm target preparation and comparison alongside the
preserved 0.93 mm baseline. No new targets or fitted results are claimed here.

## Objective and parameter meanings

Test whether conclusions about Calvin's RLD, dry mass and depth allocation are
robust to including scanned roots down to 0.50 mm. Treat scanner uncertainty as
a reason for sensitivity analysis; this plan does not establish an instrument
accuracy limit or make 0.50 mm the preferred biological boundary.

| Quantity | Baseline | Sensitivity | Meaning |
|---|---:|---:|---|
| Observation lower diameter | 0.93 mm | 0.50 mm | Retained material in derived targets and the corresponding prediction operator |
| `parameters.min_branching_diameter_cm` | 0.093 cm | Optional explicit 0.050 cm arm | Inclusive local **parent** diameter at final attachment; controls construction |
| `parameters.threshold_root_diameter_cm` | 0.25 cm | Unchanged | Existing 2.5 mm reporting split; separate from the preceding two quantities |

Changing observation support does not automatically change the construction
gate. The parent gate does not guarantee that every daughter has that diameter.
Keep both settings explicit in configs, manifests, filenames and plots.

## Q0: preserve and inventory the sources

Use the original local `Paper2_full_RLD_Sites1-5_and_Site1_excavation_9.xlsx`
and its preparation/data-description workbook under the Calvin contact folder.
Preserve their bytes, formulas, sheets and existing derivatives. Record source
SHA-256, sheet/row identities, units, sampled flags, site/core/depth keys,
coordinates, core volumes, reported RLD, each scanned length class, and measured
fine/coarse dry weights. Reconfirm class definitions and mass units from source
metadata. Do not infer missing weights or lengths as zero.

Reuse the existing preparation logic at
`.runtime/structural-starts-20261118/Calvin/prepare_targets.py` as a reference;
make a versioned, parameterized successor rather than modifying the historical
script or its hard-coded `CUT = 0.93` receipts. First reproduce its 0.93 mm output
on the same input, with declared floating-point tolerance and an explicit diff
for any intentional repair. Recheck the coordinate/operator mapping separately
before using targets with the current simulation route.

## Q1: derive both cutoff targets from one extraction

The existing saved bin inventory has an exact 0.50 mm class boundary; 0.93 mm
crosses the 0.80–1.00 mm class. Reconfirm this inventory against the workbook.
For each sampled core increment and cutoff c, retain source values alongside
the following estimates, bounds and assumptions:

- **Scanned RLD:** sum retained scanned length / sampled core volume. For a
  crossing class [a,b], use retained fraction `(b-c)/(b-a)` for the point estimate
  and fractions 0/1 for its lower/upper bounds. Whole retained classes contribute
  fully. The 0.50 mm arm needs no within-bin length allocation when the boundary
  is confirmed. This removes interpolation uncertainty at that boundary, not
  scanning/detection uncertainty. Source rounding at the edge remains explicit.
- **Dry mass:** retain the existing volume-fraction method as a named assumption.
  For length L in [a,b], the uncut volume proxy is
  `L*(b*b + a*b + a*a)/3`; for b>c the retained proxy is
  `L*(b**3 - max(a,c)**3)/(3*(b-a))`. The common geometrical/unit factors cancel
  in the retained/total ratio. Allocate measured scanned-class dry weight using
  this ratio, then add separately measured >2.5 mm dry weight. Keep conservative
  allocation bounds and the source weights. Even at the exact 0.50 mm boundary,
  this mass allocation assumes equal mass per scanned volume within a core;
  it is not a direct diameter-resolved weighing. Preserve the existing broad
  bounds unless independent evidence justifies tightening them.
- **Support:** scanned RLD covers c–2.5 mm, while the retained total dry-mass
  target includes material above c, including the separately weighed coarse
  class. Apply the appropriate diameter interval separately to each predicted
  metric on the identical core cylinder/depth support. Do not add unmeasured
  >2.5 mm length to the scanned RLD target or call these two diameter ranges
  identical. Fix the 2.5 mm boundary convention without gaps or double counting.

Store both arms in a tidy target table with `cutoff_mm`, immutable sample key,
source-row references, estimates, bounds, QC codes and per-metric eligibility.
Keep the cutoff identity outside sample IDs so the same sample pairs across arms.

## Q2: exclude documented measurement errors reproducibly

Build QC from source measurements before fitting or inspecting model residuals.
Use one cutoff-independent source-QC table, plus explicit derivation failures
for each cutoff. No source record is deleted: exclusions create analysis views
with reasons, affected metrics and retained source values.

1. Quarantine affected targets for invalid units/support, negative lengths or
   dry weights, conflicting sample keys, or other demonstrated source errors.
   Distinguish unsampled, missing and measured zero. Keep an unaffected metric
   usable where its derivation remains valid; paired RLD/mass scores use the
   intersection of their eligible samples.
2. Preserve the existing large-length-disagreement rule: flag when
   `abs(sum(class_lengths)/core_volume - reported_RLD)` exceeds both
   `0.001 cm/cm3` and `5% of max(reconstructed_RLD, reported_RLD)`.
   Record both readings and the discrepancy; the flag identifies an unresolved
   inconsistency, not which reading is correct. Exclude these records from the
   strict RLD view and the strict paired view, while retaining the all-usable
   sensitivity view. Do not silently overwrite reported totals with bin sums.
3. Check biomass against independently measured totals, subsamples, tare and
   unit records **where available**, comparing only equivalent material and
   accounting for documented weighing precision. A supplied total that is just
   the sum of the same two weights is an arithmetic check, not independent
   confirmation. Record a large-discrepancy threshold from that evidence before
   applying it. If there is no independent check, label the error magnitude
   unknown rather than inventing a percentage or inferring error from the model.
4. Flag unusual mass/length or scanned-volume/mass ratios for investigation by
   site/depth and measurement support. A large biomass value, long root sample,
   or extreme ratio alone does not prove an error. Exclude such a record only
   when a documented measurement/metadata inconsistency supports the decision.
   Do not select an outlier rule to improve fit. Any statistical screening rule
   must be fixed using training data before application to held cores.

Freeze the exclusion ledger and whole-core train/held split before new fitting.
Reuse existing split identities where appropriate; previously inspected held
data remain previously inspected. Retain individual depth-increment exclusions
without moving other increments from that core into another split. Report
eligible/excluded counts by site, core, depth and metric so preferential loss of
deep or high-mass samples remains visible.

## Q3: compare cutoff and QC effects without confounding construction

First rescore the **same** saved geometries at 0.93 and 0.50 mm. Keep construction
gate, parameters, seed, cylinder clipping, neighbour assumptions and source
identity fixed. Reintegrate length and dry mass across taper/diameter crossings;
saved aggregate 0.93 mm scores cannot recover material below that cutoff. Check
that saved graphs retain sufficient material/taper information; otherwise
regenerate the exact configurations and count those calls in the shared budget.

Report four observation views for each configuration: two cutoffs crossed with
all-usable and strict-QC data. Compare cutoffs first on the common eligible
sample support; additionally show each arm's full usable support. Report paired
core RLD and mass errors, observed/predicted depth shares and centroids, uncertainty,
and the existing depth-only benchmark. Refit that benchmark on training targets
for each cutoff/QC view. Changing support changes the scientific target, so raw
error differences alone cannot establish which cutoff is more accurate.

If testing the lower branching gate is warranted, explicitly add construction
gates 0.093 and 0.050 cm crossed with both observation cutoffs, using common
seeds. This distinguishes a measurement-support effect from increased branching.
The gate comparison uses fresh geometry; it is not a free rescore. Keep all three
new spatial features fixed during this gate comparison. Parameter optimization,
if subsequently performed, remains separate for each declared target/support;
do not choose a cutoff or exclusion rule by the smallest held-set residual.

All new simulations, regenerations and failures share the construction plan's
480-call envelope. Data preparation and valid saved-graph rescoring do not add
simulation calls. Reallocate unstarted calls in a recorded revised schedule
before any gate/optimization arm; this addition does not double the experiment.
If capacity is insufficient, deliver the target/QC and fixed-geometry comparison
first and mark the construction-gate sensitivity pending.

## Checks and deliverables

Sequence Q0 → Q1 → Q2 → frozen support/splits → Q3. Target/QC preparation should
precede Calvin feature evaluation so that observed targets do not change halfway
through an experiment. SO4's observation definition remains unchanged.

Check exact bin boundaries, crossing bins, diameter conversion (mm to cm),
2.5 mm class ownership, missing versus zero, duplicate keys, finite outputs,
positive core volumes and per-row bounds. On the same valid sample, retained
length and estimated mass at 0.50 mm must be at least their 0.93 mm counterparts
and no greater than the corresponding unfiltered totals. Test analytic synthetic
class distributions, volume fractions and prediction-operator diameter cuts.
Verify deterministic regeneration, source hashes before/after, and reproduction
of the preserved baseline. Tests of arithmetic are separate from biological
validation and scanner-accuracy evidence.

Write private derivatives under a new ignored local Calvin analysis directory:
parameterized preparation script/notebook, source manifest/data dictionary,
two-cutoff target table and review workbook, QC/exclusion ledger, support and
split manifests, before/after-QC summaries, paired predictions/plots and a report.
Keep raw data, empirical values, workbooks and fitted configs local. Public code
may contain general processing methods and invented fixtures only. Report data
preparation, simulation and parameter adoption as separate completion states.
