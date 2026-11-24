# Optional excavation measurements for reconstruction

19 November 2026. Proposed follow-up to the
[construction-feature plan](SPATIAL_CONSTRUCTION_FEATURES_IMPLEMENTATION_PLAN.md).
The owner's clarification is that measurements should help reconstruction;
there is no requirement to import and extend the measured roots. This document
supersedes the conversational suggestion of a preserved measured scaffold with
generated continuations. It does not implement a new input or alter fitted data.

The subsequent [local measured-crown comparison](../../.runtime/calvin-site1-fit-20261119/crown20/optional_layout/REPORT.md)
uses the existing schema-4 catalogue. It holds the candidate architecture
settings and simulation seeds fixed while replacing the sampled crown with a
field-conditioned layout. The report records the paired loss, the two depth
errors, uncertainty, the angle preparation, and a runnable input. This is a
conditional result for the study vine. Direct lateral measurement constraints
remain a separate proposed stage.

## Intended behavior

Optionally use order-1, order-2 and order-3 excavation measurements to constrain
a **fresh static reconstruction**. Generate whole candidate architectures through
the shared schema-4 engine; use the reliable information to fix supported initial
conditions, inform uncertain parameter distributions, and assess agreement on
the actual measured support. Unknown roots and dimensions remain generated.

Do not require measured polylines, preserved broken tips, root-tip continuation,
time stepping or physiological growth. Those would be different features.
Root order describes parentage, not a chronological sequence of observations.

The current source supports coherent primary-origin catalogues and optional
complete primary headings. It does not supply a general measurement-conditioned
input for arbitrary order-2/3 roots. `initial_recorder` is a detached output
snapshot, not an import interface. `run()` requires a fresh simulator; reuse that
entrypoint rather than attempting to resume an excavated graph.

## What to retain and what it can constrain

| Measurement | Required context | Appropriate use |
|---|---|---|
| Primary count | Vine identity, crown census coverage and minimum detectable class | Fix count for a complete census; otherwise retain an observed lower bound and uncertainty |
| Root origin or attachment position | Coordinate frame, soil reference, root identity and parent identity where known | Existing primary-origin input where applicable; conditional placement or a spatial observation term for laterals |
| Initial direction or insertion angle | Global versus parent-relative definition, units, sign, reference plane and measured station | Fix a reliable supported heading; otherwise fit an angular distribution or a soft angular constraint |
| Daughter count | Named parent, observed contour interval, class detection and completeness | Count or lower-bound observation on that interval; do not impose the whole-vine count from a partial excavation |
| Local diameter | Named root, distance from its base or another unambiguous station, measurement method and uncertainty | Constrain local diameter and jointly infer basal diameter/taper where identifiable |
| Recovered length or branch gap | Whole-axis versus segment definition, recovered support, broken/boundary status | Appropriate exact, interval or censored observation; no automatic full-axis mean |

Positions and angles alone do not determine diameters or missing daughter counts.
For example, a diameter measured 30 cm from a root's base is a constraint on
`d(30 cm)`, not its basal diameter. A parent-relative insertion angle alone does
not specify the lateral's full 3D heading; its azimuth about the parent is also
needed or must remain uncertain. A complete crown census does not establish a
complete order-2 or order-3 inventory.

Measurements from one excavated vine condition that vine. Measurements used as
population priors retain vine grouping and variation; do not combine multiple
independent crowns into one simulated vine. Lukas's mature 5C archive can inform
a separately labelled prior sensitivity, not an exact SO4 or Calvin initial state.

## Optional input and ownership contract

Design a versioned local measurement bundle, separate from the generator's
effective parameter dictionary. These are proposed semantic fields, not
currently accepted schema-4 JSON keys:

- Bundle identity, source hashes, conversion version, vine/site, observation date,
  coordinate transform, units and measured spatial/diameter support.
- Measurement ID, observed root ID/order, known parent ID, quantity, station,
  value or bounds, uncertainty definition, and exact/lower-bound/missing status.
- Census/interval completeness and measurement reliability; record missing
  relationships explicitly. Unmapped detached roots may inform grouped priors
  but cannot silently become fixed attachments to a selected parent.
- Declared use: fixed initial condition, prior information, reconstruction target,
  or held-out assessment. Record any intentional overlap; do not count one
  measurement as both independent prior evidence and independent validation.

Retain original angles and transform them into the model frame: x across row,
y along row, z upward, with depth positive down from the declared soil surface.
Store both the source and converted definitions. Prefer unit heading vectors
when direction is fully known. Treat azimuth differences circularly and compare
full headings with vector angles rather than ordinary subtraction at 0/360°.

Keep one active owner per quantity. A fixed measured primary heading replaces
that primary's inferred heading; it must not also receive an independent fitted
yaw/inclination. A complete measured count replaces the competing count proposal.
An uncertain measurement informs a prior or score rather than becoming an
undocumented exact override. Unsupported combinations fail explicitly.

## Staged implementation

1. **M0 — local preparation and baseline.** Inventory available order-1–3
   measurements without changing originals. Reuse the excavation exact/bound/
   missing contract. Produce a source/reliability table and document which
   positions, angles, diameters and parent links actually exist. No missing
   angle, diameter or parent is inferred from a picture or plotted line width.
2. **M1 — measured priors and existing supported inputs.** Reuse complete
   primary-origin/heading catalogues where valid. Use trustworthy count and
   diameter/taper information to tighten justified search ranges; retain broad
   uncertainty for incomplete higher orders. The current primary catalogue
   requires complete headings or none within an entry: sparse heading evidence
   must initially inform priors, not bypass that contract. This stage does not
   need an imported root graph or arbitrary per-root constraint solver.
3. **M2 — support-aware reconstruction scoring.** Add explicit observations for
   measured positions, directions, local diameters and interval counts. Match
   named roots using known ancestry and stations when available; otherwise use
   declared grouped distributions. Do not match each observation independently
   to whichever generated root is nearest, as this can reuse roots and ignore
   parentage. Freeze correspondence, residual scaling, uncertainty treatment
   and weights before fitting. Report structural and core-RLD/mass scores
   separately instead of hiding conflicts in one favorable aggregate.
4. **M3 — optional direct lateral constraints, only if needed.** If priors and
   scoring cannot express reliable order-2/3 attachment/heading evidence, add a
   separately reviewed canonical constraint adapter inside the shared lifecycle.
   Reconcile parent IDs, attachment arclength, positions and count ownership
   before allocation. Unsupported or conflicting constraints must fail rather
   than trigger post-generation translation, rotation or diameter replacement.
   This is still reconstruction from measurements, without a continuation API.

M1–M2 are the preferred first implementation. M3 is contingent, not a prerequisite
for using the measurements. No second generator, physiological growth model,
resumed simulator or new default route is part of this proposal.

## Evaluation, robustness and deliverables

Compare an unconditioned reference with the optional measurement-informed
reconstruction on the same observation operator and predeclared seed panels.
Keep diameter cutoff/QC masks independent of which model fits best. Reuse the
[0.50/0.93 mm protocol](CALVIN_DIAMETER_CUTOFF_AND_QC_PLAN.md) for core targets;
excavation detection classes and the parent branching gate remain distinct.
Respect whole-core holdouts and vine-level grouping. Agreement with measurements
used as input is conditional reconstruction evidence, not independent prediction.
Retain joint spatial and held-core RLD/dry-mass assessment.

Check unit/frame and angular conversions, unique identities and parent mapping,
local versus basal diameter, incomplete versus complete counts, missing versus
zero, interval censoring and deterministic replay. Disabling the feature must
preserve current effective inputs and geometry without new RNG draws. Use small
invented observations to verify matching and scoring before local fitting; run
affected/full engine checks only when implementation changes warrant them.

Reuse existing modules where their contracts fit: canonical origins and resolver,
`research/excavation.py`, research parameter preparation/search, observation
operators, run records and the existing integrity/material machinery. Freeze
current working-source hashes before edits; HEAD alone is insufficient while
other work remains uncommitted. Existing implementation reports, including the
three spatial controls, are not fresh test results for this proposed feature.

Deliver the local measurement dictionary, source/reliability table, prepared
priors/targets, mapping and ownership diagnostics, reconstruction notebook and
separate software/research dispositions. Publish only generic methods and invented
fixtures. Do not add simulations on top of the existing 480-call envelope:
reallocate unstarted trials under a recorded protocol or leave this comparison
pending. No data preparation, new optimization or engine implementation was run
for this design update.
