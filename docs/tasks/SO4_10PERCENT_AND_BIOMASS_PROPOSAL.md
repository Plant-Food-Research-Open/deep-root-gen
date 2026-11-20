# SO4/T2: proposed 10% reconstruction and whole-root dry-mass constraint

Status: **ARCHITECTURE EXPERIMENT FINISHED; REQUIRED INDEPENDENT REVIEWS PENDING. No production defaults or biomass target adopted.**
The owner authorized implementation and further recorded local trials after this
proposal. The 20% result remains sealed. The versioned 10% evaluator and diagnostic
mass operator are implemented; source qualification, completed trials, rejected
candidates and current work are indexed by the active research state. Required
new independent reviews remain pending local Claude authentication.
Prepared 14 November 2026. Read [active research state](../research/ACTIVE_SO4_RESEARCH.md)
first. The selected 20% candidate and its fresh-seed receipt remain the preserved
baseline. The new experiment's outcome and verification are in the ignored
research tree's `FINAL_REPORT.md` and `FINAL_VERIFICATION.json`.
Local empirical values, parameter arrays and comparison outputs
stay in the ignored research state; they are not included in this public method.

## Objective and baseline

Improve population-average representation using the qualified
`grapevine3d-soil-frame-v2` observation operator, while preserving the selected
20% candidate and its source/configuration/input/seed identities. The proposed
next engineering target is:

- Each of the same thirteen positive-valued traits: absolute relative difference
  between generated and observed population means <=0.10.
- Each of the same across-row, along-row and depth population profiles:
  total variation <=0.10, on the same 10 cm bins and equal-architecture weighting.
- Biomass: an additional, separately defined whole-root dry-mass constraint,
  enabled only once its target, support, uncertainty and tolerance are frozen.

TV is a normalized distribution distance, not a per-bin relative percentage.
The 10% target is a proposed representation tolerance, not a claim of biological
or measurement accuracy. Do not rewrite the historical 20% protocol or label
its passing candidate obsolete. Keep both evaluations in the new report.

Resolve current state from the latest completed receipt and independent
verification; an older CURRENT_STATE marker may lag later rounds. Preserve
historical documents and reconcile the active index before a new run.

## Stage 1: improve architecture using existing controls

First recompute the frozen candidate's thirteen errors and three profile TVs
from saved outputs. Examine signed residuals, depth-bin allocation and
along-row orientation by order and parent-arc position. Separate variation
between observed vines from Monte Carlo variation between model seeds.

Start with a small sensitivity screen, changing one existing direction control
at a time, using common INITIAL skeletons and the same innovations where the
implementation supports them. Initial candidates are order-2 insertion polar
angle, order-2 downward-objective probability and order-specific row-axial
insertion concentration. Retain primary yaw as a bounded interaction candidate
if the screen shows it matters. Freeze parameter ranges from evidence or
explicit research assumptions before running. Do not silently relabel tuned
values as published coefficients.

Initially hold current-length CDFs, counts, attachment construction, diameter,
density, verified base coordinates and primary scaffold fixed. Do not fit
legacy secondary-length bounds/reduction for orders whose CDF mode bypasses
those controls; do not optimize time for the static path where grow() is unused.

After screening, search only the two or three effective controls jointly.
Direction and row preference can trade depth against horizontal spread, so
acceptance must retain every trait/profile rather than improving one score.
Use the same controlled replay route for screening, selection and qualification;
native Fichtl execution has a different first-segment and boundary contract.

Let e_j be each relative trait difference and v_k each population-profile TV.
An interpretable selection score is:

```text
J_arch = max(max_j(e_j / 0.10), max_k(v_k / 0.10))
```

J_arch<=1 means all proposed architecture criteria pass. Retain the full vector
of errors and signed residuals; the scalar is only for ranking. Do not use the
inherited balanced voxel MAE as the sole objective. Report near-ties and Monte
Carlo uncertainty rather than searching for a favourable seed.

A suggested bounded round is 6-10 screening settings with ten shared seeds,
then at most 12 local-search candidates on ten shared seeds. Freeze one selected
candidate before qualification on at least 30 new seeds, increasing to 60-100
only when Monte Carlo uncertainty makes the decision unstable. Record every
attempt, failure and recovery; retain one worker/two threads and explicit
per-round time/storage limits. The owner permits further recorded trials, but
that does not require an unbounded optimizer or unused trial expenditure.

If existing controls cannot jointly meet the target, consider one new mechanism:

1. **Primary inclination:** current primary pitch ranges are hard-coded, whereas
   research yaw preserves primary z. An opt-in, explicitly distributed primary
   inclination control may be more interpretable than moving the whole base.
2. **Directional persistence:** row preference acts at insertion; continuation
   selects downward versus horizontal directions. Add an order-specific
   persistence/curvature control only if saved trajectories show alignment
   decaying in a way existing controls cannot represent.

Do not introduce both simultaneously. Independent order-count controls are a
later option only if count residuals require them. A sampled length-angle or
length-count relationship needs measured or explicitly justified joint evidence;
matching separate marginal distributions does not establish those relationships.

## Stage 2: qualify the biomass observation

Preferred target: dry mass, in g per vine, of the matched SO4/T2 root compartment.
Distinguish roots from basal cutting/stem/crown material and the complete
recovered root system from a finite voxel prism or a fine-root sample. Verify
whether any recovered material was weighed but not digitized. If so, the
represented geometry and weighed support differ; a recovery correction requires
independent evidence and must not be a free multiplier used to force agreement.

The [Fichtl 2025 paper](https://juser.fz-juelich.de/record/1049167/files/mcaf193.pdf)
reports separate root, stem, shoot and leaf dry weights, with numerical biomass
results in supplementary Table S2. Main-text access establishes the measurement
method, not a verified SO4/T2 numerical target. No numeric target is supplied by
this proposal; supplementary values or matched measurements must be checked.

Minimum local observation contract:

| Field | Meaning |
| --- | --- |
| rootstock, timepoint, cohort | Explicit SO4/T2 match; additional site/treatment keys where relevant |
| vine_id or group_id | Per-vine target, or correctly labelled population aggregate |
| root_dry_mass_g | Measured mass; never inferred silently from default simulator density |
| uncertainty, uncertainty_type, n | SD, SE or CI explicitly distinguished; do not use SD as SE |
| compartment/support | Root inclusion, basal cutting/crown treatment, recovered material and diameter cutoff |
| method/provenance | Drying method, source table/file/version and measurement units |

With a group mean, compare the equally weighted ensemble mean to that mean.
Do not penalize every simulated vine for differing from a group mean. With
matched per-vine data, assess mass distribution and length-mass association;
do not invent seed-to-vine correspondence. Preserve original raw observations.

## Stage 3: add a versioned mass operator

Current `TotalWeight` already calculates piecewise cylindrical dry mass:

```text
M_g = sum_i rho_i * pi * (d_i / 2)^2 * L_i
L_i: geometric segment length, cm
d_i: child-segment diameter, cm
rho_i: dry mass per represented root volume, g/cm^3
```

It excludes order-0 and invalid child segments and validates diameter/density.
Do not reintroduce historical base-row defects or replace the current formula
without checking current source. Diameter is not radius. Subdivision copies
the segment diameter, consistent with cylinders; using parent and child
diameters as frustum endpoints would change the model, especially at branches.

Add an opt-in research mass evaluator over the final node/edge tables. Reuse
the checked cylinder arithmetic, but make support explicit and return an audit:
accepted/excluded segment count, length, volume and dry mass; exclusion reasons;
mass by order; density source/override; and a per-architecture total.

Reject missing parents, nonfinite inputs and unknown compartment mappings.
Exclude the base and any stem/support material. Apply the existing child-invalid
policy consistently. Select whole-system or soil-clipped support from the
measurement contract, not from whichever finite grid is convenient. A valid
whole-system mass includes roots outside the RLD observation prism. Never
concatenate seed graphs and call their summed mass a single-vine observation.

The research geometry tuples currently discard diameter and density. Evaluate
mass directly from the saved node/edge tables or retain a node-ID-linked
attribute table. Do not derive mass from RLD alone. `RootOrgan.calculate_mass`
uses stored lengths, and grid totals describe in-grid support; neither should
silently substitute for this declared mass observation operator.

## Diameter, density and identifiability

Current diameter bounds, order reduction and tissue density are generator
assumptions. A reported VTP radius field needs measurement provenance, units,
RSML correspondence and root-class coverage before becoming diameter evidence.

At fixed lengths, M is proportional to rho*d^2. A single whole-root mass cannot
identify free density and diameter scale independently: scaling diameters by s
and density by 1/s^2 gives the same mass. Initially fix density from a compatible
independent source and constrain at most one diameter-scale parameter, bounded
by diameter evidence. If density is uncertain, propagate its interval instead
of reporting a uniquely calibrated diameter.

Under a fixed validated density and diameter-shape family, a global scale has
M(s)=s^2*M(1); conditional scale can therefore be solved directly and checked
against independent bounds. This is conditional mass matching, not validation
of order-specific diameters or spatial biomass. Additional per-order taper or
density parameters need additional data, such as class-specific mass/diameters.
Compute volume segment by segment; a squared average diameter loses information.

Compatible specific root length can supply M=L/SRL as a separate empirical
alternative, with support/uncertainty declared. Because SRL itself is L/M, do
not count length, mass and derived SRL as three independent observations.

Direction-only replay preserves segment length and diameter, so whole-system
mass remains invariant when filtering/support is unchanged. Biomass cannot
identify where those roots lie. It supplies a size/volume constraint alongside
the architecture criteria; it does not replace spatial evaluation.

## Stage 4: constrained optimization and qualification

Start by calculating diagnostic mass without using it for selection. Verify
units/support and compare its range to the qualified measurement. Then freeze
either a positive biomass interval [B_low,B_high], based on measurement evidence,
or a relative mass tolerance epsilon_B. Do not automatically copy 10% from the
geometry target when biomass uncertainty does not support it.

With a relative mass contract, b=abs(mean(M_sim)-mean(M_obs))/mean(M_obs):

```text
J_joint = max(J_arch, b / epsilon_B)
accept only if all architecture criteria and the mass criterion pass
```

Alternatively, keep biomass as a feasibility interval while minimizing J_arch.
If using uncertainty-normalized residuals for search, account separately for
measurement/population-mean uncertainty and simulation-mean Monte Carlo error;
retain explicit acceptance checks outside the search loss. Report infeasible
tradeoffs rather than changing weights until a candidate appears to pass.

Use nested experiments: an outer construction/diameter candidate defines a new
hashed skeleton; an inner direction search replays it without changing mass
attributes. Reuse a skeleton only under its declared compatible controls.
Common seeds alone do not preserve biological-root pairing when topology changes
and allocated organ IDs change.

Freeze finalists before fresh-seed qualification. These seeds assess simulation
stability, not unseen-vine prediction. If estimating empirical CDFs, azimuth or
biomass parameters in cross-validation, split whole vines first and re-estimate
all such quantities inside each training fold. All current vines have already
informed development, so retrospective cross-validation remains exploratory;
new vines/cohorts are needed for genuinely independent biological validation.

## Proposed code scope and meaningful tests

| Component | Proposed change |
| --- | --- |
| New research evaluation module | Versioned 10% criteria, full metric vector, mass contract and worst-criterion ranking |
| `deeprootgen/statistics/summary_statistics.py` / shared mass helper | Reuse validated segment cylinder math; expose auditable strict mass evaluation without changing legacy defaults |
| Research runner/evaluator | Per-architecture mass and population summary, local target loading, paired screening and separate finalist seeds |
| `simulation_data_models.py` | Optional, finite validated mass-related research controls only when their definition is fixed |
| `model/root.py` | Change diameter law or primary inclination only after evidence justifies a missing control; no broad rewrite |

Tests: analytic single cylinder; sum over unequal-diameter segments; subdivision
and rigid-transform mass conservation; diameter doubling gives fourfold mass;
density doubling doubles mass; exclusion/support ledgers; missing-parent and
invalid-unit rejection; population mean rather than summed seeds; unchanged
legacy outputs with the feature disabled; and correct independent acceptance of
all traits/profiles/mass. Add surface-clipping conservation only for a contract
that actually uses soil-clipped mass. Keep algorithm and biological validation
separate.

Deliver a versioned candidate, local comparison/uncertainty report, immutable
source/input/config identities, attempts/review receipts and explicit remaining
data limitations. No biomass-constrained acceptance claim is possible until the
measurement contract and numerical biomass target are supplied and verified.
