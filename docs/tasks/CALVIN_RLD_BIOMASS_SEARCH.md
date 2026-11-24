# Calvin: RLD reconstruction with total underground biomass control

19 November 2026. Proposed implementation and iterative local study, following
the owner's deep-review request and confirmation of the biomass compartment.

## Outcome

Build a new versioned research objective that selects candidate architectures
using root-length-density magnitude, depth and joint core-by-depth allocation.
Fix `parameters.root_tissue_density` to the owner-supplied 0.45 g/cm³. Use 5–7 kg
dry mass per subject vine, including underground crown/rootstock, as a separate
feasibility condition. Dry-mass profiles remain available for diagnosis.

The [private review and full search plan](../../.runtime/calvin-rld-mass-review-20261119/REVIEW_AND_SEARCH_PLAN.md)
contains the saved-result audit, measured parameter evidence, trial ranges,
resource schedule and unresolved crown-mass assumptions. The
[proposed protocol](../../.runtime/calvin-rld-mass-review-20261119/SEARCH_PROTOCOL.proposed.json)
is a research specification, not a schema-4 generator input or completed run.

## Implementation sequence

1. Freeze the generator, observation operator, local measurement/QC inputs,
   core folds, candidate identities and seed schedules. Preserve the previous
   experiments and the current uncommitted work.
2. Implement `calvin_rld_only_v1`: 0.50 normalized RLD absolute error + 0.25
   joint core-depth TV + 0.25 depth TV, with training-only normalization and
   equal total core weight. Use RLD eligibility independently of biomass.
3. Implement explicit order-1 basal-diameter and taper search controls. Existing
   framework-wide diameter changes do not isolate the requested effect. Rebuild
   geometry for every diameter change because eligibility, daughter caps and
   diameter-filtered RLD can change.
4. Add a compartment ledger outside the generator: valid subject-root mass plus
   an independently specified below-soil crown/rootstock mass. Do not give graph
   anchors mass or derive crown mass as the remainder needed to meet the target.
   All diameters count toward total biomass; observation cutoffs affect RLD only.
5. Audit scoring, volume/mass identities, source/input immutability, zero cases,
   invalid-root handling and deterministic replay with small meaningful checks.
6. Execute the proposed staged study: saved-library reuse, diameter/taper
   feasibility, broad search, four adaptive rounds, shortlist stability, fresh
   seed confirmation, assumption sensitivity and synthetic recovery.

The proposed new envelope is **4,096 generator calls**, one model worker,
one numerical thread, 4 GiB of derivatives and 72 hours maximum, stopping at
the first cap or an evidence-based stopping condition. This request for a larger
iterative study creates a new protocol; it does not rewrite the earlier 480-call
study or turn prepared stages into executed work. Failures, replays and extra
neighbour realizations count. Compact saved-prediction rescoring does not.

## Research safeguards and acceptance

Retain the QC and measured-crown cases as distinct references. Measured primary
origins/headings and the class-limited crown census constrain initialization;
uncertain lateral measurements inform priors. Preserve the distinction between
recorded size classes and hypothetical maturity scaling. Keep the parent diameter
gate distinct from RLD observation cutoffs and the reporting diameter split.

Use the full-resolution physical geometry in candidate ranking. Make the
training-only mean-RLD normalization, whole-core folds, mass-feasibility and RLD
magnitude guards explicit before optimization. Report infeasible candidates,
invalid runs, alternative parameter sets and individual-realization performance.
Do not select only favorable seeds or exclude observations because of model
residuals. Previously inspected cores remain developmental evidence; fresh
simulator seeds do not provide new biological validation.

The total-mass claim is conditional on a defensible crown/rootstock compartment.
The proposed geometric crown scenario and its uncertainty are recorded locally.
The former combined-score threshold is not equivalent to the new RLD objective.
Retain an explicit aspiration and component-wise diagnostics rather than claiming
that changing the objective itself establishes the previous target.

Deliver local notebooks, source-bound receipts, all attempts, feasible-frontier
and uncertainty plots, mass by compartment/order/class, matched core profiles,
representative geometry, runnable inputs and an updated printable report. Public
source may contain generic methods and invented fixtures only. No dependencies,
services, archived constructors, external uploads, merge or push are in scope.

## Current completion status

The owner authorized execution on 19 November 2026. The [local execution report](../../.runtime/calvin-rld-search-20261119/REPORT.md)
and [review notebook](../../notebooks/grapevine_root_architecture/calvin_site1_rld_mass_search.ipynb)
track full-resolution trials and the separate rootstock mass scenario. The protocol
preserves the original review as the pre-execution record. Use the complete
matched-seed panels and their uncertainty when assessing a new starting input.

## Coring diameter and recovery preference

Compare the model on three cylinders at identical positions and depths. The
physical reference uses the recorded soil volume. Two virtual diameters, 3.8 cm
and 7.6 cm, test whether the field RLD is representative of a wider local mean.
Divide each predicted length by its own sampled volume. Use the original RLD,
sampling weights and whole-core folds for all three comparisons. Report changes
in zero intersections, absolute RLD, core-by-depth allocation and depth profile.

Retain the symmetric measured-core objective. A second selection uses the
7.6 cm support and charges 80% of the usual magnitude error for the first 20%
of overprediction in an increment. All additional excess, all underprediction
and all positive predictions on observed zeros carry their full marginal cost.
This preference expresses possible recovery loss without estimating how much
was lost. Both tracks use the same mass and mean-RLD guards. Freeze both
development selections before viewing their confirmation results.
[Paired observation protocol](../../.runtime/calvin-rld-search-20261119/area_support/PROTOCOL.json)
