# DRG-G3D-01 — Fichtl evidence review and reconstruction contract

**Historical v1 material — superseded for physical soil comparisons.**
Read [the active v2 research state](../research/ACTIVE_SO4_RESEARCH.md) first. The recovered soil frame
uses RSML stem point0 as soil, point1 as basal, and explicit canonical horizontal
axes. The original prepared grids, receipts and text below are preserved as
history; earlier calls to increase shallow allocation are superseded.
The coordinate audit is completed locally; current work targets population
representation under the accepted13-trait/3-profile criterion.


Status: **evidence review executed; proposed contract prepared; scientific acceptance pending**.
Owner: independent DeepRootGen project.
Prepared 14 November 2026 (Pacific/Auckland).

Deliverables: [paper review](../research/grapevine3d/PAPER_REVIEW.md),
[parameter matrix](../research/grapevine3d/PARAMETER_EVIDENCE.csv),
[observation contract](../research/grapevine3d/OBSERVATION_CONTRACT.md) and
[pilot specification / execution receipt](../research/grapevine3d/PILOT_SPECIFICATION.md).
No simulation, fitting, mechanism change or dependency installation was performed.

Parent goal: [Grapevine3D architecture reconstruction](../GRAPEVINE3D_RECONSTRUCTION_PLAN.md).

## Ready-to-use Codex task

Work in `/home/jzhu/Workspace/Github/FruitCropXL/13-deep-root-gen-PFR-open`.
Prepare the evidence and scientific specification needed to reconstruct
plausible Fichtl Grapevine3D architectures from the existing 10 cm RLD grids.
Complete a deep analysis of the 2024 Plant Phenomics paper, the 2025 Annals of
Botany paper and accessible supplements/parameter files before selecting model
parameters. Assess whether matched root dry mass or SRL can constrain the
generator. Deliver a concrete reviewed specification for a later bounded pilot;
stop before changing model mechanisms, simulation, optimization or training.

Read `AGENTS.md`, inherited guidance, the DeepRootGen Python engineering skill,
`docs/ARCHITECTURE.md`, `docs/REVIEW_NOTES.md`, `RUNNING.md`,
`docs/GRAPEVINE3D_GRID.md` and the parent plan. Recheck facts against the final
source; historical review notes and qualification results are not current PASS.
Record revision, branch, status, candidate/merge identity and lock hash. Preserve
ongoing work and do not complete or restart another task's merge.

### Scope and permitted work

- Read source and public papers; retrieve public supplements and authors'
  published parameter files where accessible, with source/version provenance.
- Inspect the named Grapevine3D files locally to establish schema, units,
  coverage and join keys. Local scripts may compute compact QC summaries;
  raw data stays on disk and must not be sent to agents/services. Do not print
  raw rows into chats. Do not include private coring/management datasets.
- Write analysis code and evidence/contract documentation needed for this
  review. Preserve raw inputs; put extracted tables, join audits and figures in
  a fresh local research output directory outside raw `DATA` and tracked source.
- Delegate public literature and source review if useful, without sharing
  Contacts data. No containers, deployments, workers, remote artifact stores,
  fitting, model formula changes, dependency upgrades, commits or pushes.

### Frozen starting inputs to recheck

1. Final merged DeepRootGen source, once available. Planning snapshots were
   local `16309d38dc36030b92ae19e61f5e22a5f4e585e3` and upstream
   `80315af38f196e7f65452bbb132d4251d8c710e6`; no final merge is assumed.
2. Local `DATA/RSML_Files`, `DATA/VTP_Files` and
   `Grapevine3D_grid_10cm/{voxel_grid.csv,vine_summary.csv,analysis_metadata.json}`
   under `/home/jzhu/Workspace/Contacts/Australia/Calvin Lam/`.
3. Upstream `data/grapevine/fichtl_2024_voxel_grid.csv` and the four
   `notebooks/grapevine_fichtl_2024/` notebooks. Verify identity with the prepared
   data; do not regenerate or silently replace it. Expected grid SHA-256:
   `10e5b5332bd9bdf06cf73e1a64fb394c99ab174c822aa4744440fa7cd67fb4bf`.
4. [Fichtl 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11633832/), especially
   parameterization methods, Tables 1/2/4 and Fig. S7; and
   [Fichtl 2025](https://juser.fz-juelich.de/record/1049167/files/mcaf193.pdf),
   especially biomass/SRL methods and Tables S2/S4/S5/S6. Track actual downloaded
   versions and citations; filenames are not authoritative publication dates.

### Work packages

**A. Reconcile identity and sampling.** Resolve author/dataset names, rootstock
aliases, timepoints, plant IDs and block/replicate labels. Determine overlap
between the papers and archive versions, destructive sampling design, root
recovery limits and available diameter measurements. Inventory the exact
biomass files, if present. Distinguish raw measurements, published means,
model-fitted parameters and quantities derived from the same measurements.

**B. Extract paper evidence.** Build one row per candidate parameter/constraint:

```text
evidence_id, source_doi, source_version, page_table_equation,
genotype, timepoint_age, root_class, sample_size, statistic,
value_or_distribution, printed_unit, verified_unit, uncertainty,
measurement_or_fit, source_equation, deeprootgen_destination,
transfer_rule, decision, unresolved_issue
```

Classify entries as `DIRECT`, `TRANSFORM_REQUIRED`, `VALIDATION_ONLY`,
`MODEL_GAP` or `UNAVAILABLE`. Audit diameter/radius, angle units, elongation
rates and angular variability against author code. Describe CPlantBox's
probabilistic tropism and initialization mathematically, then compare them with
DeepRootGen's implementation. Do not insert paper coefficients solely because
their parameter names look similar. Where source ambiguity remains, preserve
the printed value and mark it unusable pending resolution.

**C. Audit observation compatibility.** Specify soil origin/root-base depth,
x/y conventions, z sign, units, geometric length, face boundaries, clipping,
order/class mapping and missing/zero semantics. Verify existing conservation
claims locally and investigate the documented RSML/published-length discrepancy
without adding hypothetical connectors. Define full-plant versus observed-grid
support and an overflow policy. Check that final merged defaults cannot silently
switch between recorded and geometric segment length.

**D. Decide the biomass route.** Establish dry/fresh basis, root compartment,
measurement uncertainty and joins by actual plant ID or genotype/timepoint.
Report unmatched/duplicate keys and coverage. Prefer directly matched total dry
mass; otherwise use group-level mass constraints or an explicitly uncertain SRL
scenario. Do not manufacture voxel biomass or infer diameter and tissue density
separately from RLD alone. Explain dependence among length, mass and SRL.
If data are unavailable, deliver an RLD/architecture-only specification with
biomass clearly pending; do not block all useful planning.

**E. Assess model adequacy and upstream integration.** Review generator,
branching, grid aggregation, core operator, SRL/mass definitions and notebook
loss/seed/resume logic. Identify active versus unused parameters, changed
gravitropism ranges, `t`/growth semantics, and representation of measured
initial/adventitious roots. Separate merge compatibility repairs from proposed
biological changes. Propose the smallest correction only if required, with its
test and scientific rationale; do not implement it in this task.

**F. Freeze the proposed pilot.** Nominate a single rootstock/timepoint and
parameter subset; propose objective terms, uncertainty scaling, bounds,
representative-seed policy and non-redundant biomass use. Specify conditional
reconstruction versus population prediction. Freeze training/validation IDs,
account for any paper-prior overlap, and identify which architecture traits
remain unfitted. Define a numerical acceptance table before fitting, using
measurement uncertainty and a baseline rather than convenient post-fit values.
Set maximum trials, seeds, generator calls, CPU/wall time and storage; explain
when the budget may be insufficient to establish feasibility.

### Deliverables

Repository deliverables (non-sensitive methods and source citations only):

- `docs/research/grapevine3d/PAPER_REVIEW.md`: deep synthesis, equations,
  uncertainty, source ambiguities and relevance to this generator.
- `docs/research/grapevine3d/PARAMETER_EVIDENCE.csv`: the evidence matrix;
  include public literature values only, with explicit provenance.
- `docs/research/grapevine3d/OBSERVATION_CONTRACT.md`: definitions, schematic,
  class/support rules, dependency decisions and synthetic validation cases.
- `docs/research/grapevine3d/PILOT_SPECIFICATION.md`: a concrete proposed run
  specification, active parameters, objective, split policy, acceptance table,
  budget and readiness decision, plus the bounded implementation task.

Local-only deliverables in a new run-specific research directory:

- Input/hash manifest, schema/coverage report, any per-vine extraction and
  biomass join audit, local plots, and exact held-out plant membership.
- Machine-readable configuration draft with paths, seeds, bounds, objective
  version, support masks and budget. Label it `PROPOSED_NOT_EXECUTED`.

### Completion and handoff

The task is complete when each proposed parameter has a justified classification,
the biomass option has an evidence-backed decision, the observation contract is
unambiguous, validation is distinct from fitting, and the next task is bounded
and reproducible. Missing supplements or model features must have exact
`UNAVAILABLE`/`MODEL_GAP` entries and their consequences, not guessed values.

Have an independent reviewer check units, transfer semantics, circular targets,
support mismatch, holdout leakage and physiological plausibility. Record the
checks actually executed and remaining uncertainties. Present the complete
scientific contract for the scientist's decision before model changes or fitting,
as required by the repository's scientific-definition instructions. This review
gate does not prevent finishing the evidence package or proposing concrete
defaults now. Do not claim that this task reconstructs or validates real roots.
