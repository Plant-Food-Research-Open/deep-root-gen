# SO4 paper-informed architecture comparison

Continuation status, 14 November 2026: the separate accepted four-arm experiment
is complete (40 new attempts; no failures/retries). The baseline below was
verified and reused without regeneration. See the
[local controlled final report](../../../.runtime/research/so4-t2-controlled-20261114-v1/FINAL_REPORT.md)
and [all-seed 3D view](../../../.runtime/research/so4-t2-controlled-20261114-v1/comparison/roots_3d_all_seeds.html).
Observation-referenced quantities are conditional on the unresolved joint
coordinate mapping. The current priority is the
[authoritative observation contract](../../tasks/GRAPEVINE3D_03_OBSERVATION_LANDMARK_CONTRACT.md);
the scaffold/ablation proposal linked later in this historical baseline is
not the current next task. No configuration is recommended or adopted.

Prepared 14 November 2026 for the user's request to continue, use SO4, generate
architectures, compare differences, identify gaps and plan improvements.
This explicitly extends the earlier evidence-only task into **local diagnostic
generation, an optional paper-inspired tropism mode and comparison**. An optional research tropism and explicit soil-boundary mechanism are now
authorized by the follow-up request. No empirical optimization biomass adoption or population-validation claim is part of this run.

## Frozen design before generation

- Source: `d5918d8bd182e351817f374426687cb546eeaa10`; optional mode changes are recorded as a hash-bound dirty patch. Preserve existing
  uncommitted documentation and scripts.
- Data: existing SO4/T2 (six months after planting), all eight vines. This
  matches the parameterization stage of
  [Fichtl et al. 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11633832/).
  The prepared grid hash is frozen in the [configuration](../../../configs/research/so4_t2_fichtl2024.json).
- Evidence: Table 2 current organ lengths/counts; Table 4 interbranch spacing.
  Dynamic maximum lengths, elongation rates, ambiguous radius/angle labels and
  CPlantBox tropism probabilities are not substituted into unlike controls.
- Ensemble: four predeclared parameter scenarios ×10 seeds =40 generator
  calls; at most15 minutes, one worker/two threads, 1 GiB outputs; no retries.
  Each generated graph is reused at base-depth20 cm and at0 cm for an explicitly
  nonphysiological alignment sensitivity. No rotation or transform fitting.
- Comparison: same positive-depth cube splitter as observations, geometric
  lengths, invalid/exterior ledgers, occupied/zero RLD errors, full soil length,
  depth/spread, orientation, and labelled organ proxies. Biomass is unconstrained.
- Validation: common synthetic face/clipping/ledger fixtures and fixed-seed
  runtime checks before comparison. These qualify algorithms, not biology.
- Outputs: ignored local run directory with full source/config/input/runtime
  hashes, graph CSVs, measured/generated 3D HTML, PNG comparisons, a report and
  run ledger. Measured rows and geometry stay local and are not sent to reviewers.

## Parameter transfer

The [complete single-seed simulator input](../../../examples/research/so4_t2_fichtl2024.json)
is ready for the offline CLI; the [ensemble configuration](../../../configs/research/so4_t2_fichtl2024.json)
freezes the four-scenario diagnostic design.

The paper's SO4/T2 type1/type2/type3 mean lengths are12.1/40.3/8.9 cm, with
between-vine SD2.5/12.1/1.0 cm; counts are9/24/94 (SD3/6/26). The generator's
primary roots are a **hypothesized** proxy for the nursery scaffold, not an
established equivalence between XML nesting, label, biological type and order.

For the static paper proxy, primary uniform bounds are
`12.1 ± sqrt(3)*2.5`. Set length reduction to `8.9/40.3` and divide the
secondary bounds `40.3 ± sqrt(3)*12.1` by that reduction before passing them to
the generator. This matches nominal means before the existing parent-segment
increment. It assumes SD of vine means can serve as a per-organ scale and cannot
represent independent order-specific variance. Actual generated lengths and
counts must be reported, not claimed to match by construction.

Use four outer/five inner primaries, a requested branching count of2–3, and
count multiplier `growth_sec_root=.35`. These allocations are explicit
engineering assumptions. In `paper_proxy`, global spacing is4.8 cm, although
the published value applies to type2 roots. `branching_capacity` changes only
that global spacing to.75 cm as a predeclared adequacy sensitivity; it is not
a measured spacing or accepted biological improvement. The third ensemble
retains the upstream notebook's example configuration for context.

No finite ensemble identifies a parameter distribution from this experiment.
Seed variation measures conditional generator variation, not posterior,
measurement, parameter or biological uncertainty. Published means from the
same cohort are setup evidence, not independent validation.

## Known gaps to quantify

The legacy validator confines valid roots below the model base. Translating
the base to20 cm makes shallower roots unrepresentable. Generation here is an
authorized **model-gap diagnostic** despite that known inadequacy, not a claim
that the earlier gate to empirical fitting has passed. The0 cm comparison
isolates alignment effects without selecting a biologically convenient origin.

Other known limits are one global spacing/count window, hard-coded angles,
no row anisotropy, one-point crown, static growth, incomplete fine-root
recovery, uncertain label/nesting topology, unverified VTP radius provenance,
and no matched dry-mass table. The report will distinguish observation,
parameter-transfer, mechanism and evaluation gaps, with bounded next tasks.

## Review

Claude Opus 5.5 completed a public-only design review, source review and correction
recheck through Claude Code. No local measured data or generated observation
comparisons were supplied. Its final recheck found no unresolved material defects
in the supplied source excerpts; it did not execute tests. Exact responses,
model identity, source packets and dispositions are retained locally.

Run status: **COMPLETE_DIAGNOSTIC_ONLY**. All 40 generator calls completed with
no retries. All 388 tests, including integration and two pre-change legacy golden
cases, passed. This includes the inherited dummy test; that test alone is not
coverage. No biological validity or calibration adoption follows from these checks.

Local deliverables (contain measured geometry; do not upload):

- [Findings and bounded next task](../../../.runtime/research/so4-t2-diagnostic-20261114-v1/comparison/INTERPRETATION.md)
- [Measured vs ten-seed interactive 3D view](../../../.runtime/research/so4-t2-diagnostic-20261114-v1/comparison/roots_3d_measured_vs_tropism.html)
- [Full numeric comparison](../../../.runtime/research/so4-t2-diagnostic-20261114-v1/comparison/REPORT.md)
- [Focused depth profile](../../../.runtime/research/so4-t2-diagnostic-20261114-v1/comparison/depth_profile_focus.png)

The new mode brings depth and overall length closer to the measured scale, but
does not reproduce shallow length allocation or the spatial voxel pattern.
The next proposed task prioritizes measured initial-scaffold conditioning and
separate mechanism ablations before any fitting. Its own acceptance and budget
remain separate from this completed diagnostic run.
The [ready-to-review follow-up task](../../tasks/GRAPEVINE3D_02_SO4_SCAFFOLD_AND_ABLATION.md)
freezes its metadata gate, conditional interpretation, twelve-call budget and
deliverables. All eight current SO4/T2 vines were examined descriptively and
must not later be relabelled as untouched holdouts.

## Optional tropism mechanism authorized in the follow-up

The user explicitly requested primary-root number/length and a new tropism
based on the paper. `tropism_mode="fichtl2024"` is an opt-in research mode; the
legacy default stays available. Legacy gravity must be zero in the new mode.
Primary geometry is generated, validated against the physical surface, then kept as a
static scaffold. Order2 samples insertion about its parent tangent using
51.8±22.5 degrees and subsequent headings with downward probability.65,
sigma.2 radians/sqrt(cm), and N=2. Order3 uses50.4±22.5 degrees, downward
probability1 and N=1. Truncated-normal angle draws in[0,90] and one Bernoulli
objective per segment are explicit approximations; exact historical code
switching granularity remains unverified. Angles are verified degree values
from the estimator despite the table's printed radian labels.

For segment length ds, angular noise is sigma*sqrt(ds)*Normal(0,1), azimuth is
uniform0..2pi, and there is one initial candidate plus stochastic rounding of
N*sqrt(ds) extra candidates. Minimize heading_z for gravity or abs(heading_z)
for horizontal preference. Reject directions crossing the soil surface; if
none remain, use a recorded downward fallback. Keep geometric segment lengths and graph
attachments. Step sizes come from DeepRootGen segments, not the author model's
increments; trial intensity and noise depend on that discretization. Orders
above3 are rejected in this research mode. After tropism, laterals are checked
without reorientation, so world-referenced directions remain intact. This is a static directional reconstruction, not dynamic growth,
physiological adoption or an exact CPlantBox replay.

`soil_surface_z_cm=20` explicitly locates the physical surface above the model
base. The new mode permits below-surface upward laterals and omits the legacy
downward-apex check. Its comparison with the capacity scenario combines soil
validation, insertion and tropism changes; separate ablations are a next task.
The explicit bounds, fixtures and legacy regression checks qualify algorithms;
no biological tolerance is implied.

## Reproducible local command

The exact pinned typing-extensions4.16.0 wheel is installed into a run-local
overlay; its SHA256 is checked against poetry.lock. Other installed locked
package versions match. The existing Python environment and lock are preserved.

```bash
PYTHONPATH="$PWD/.runtime/research/so4-t2-diagnostic-20261114-v1/locked-overlay:$PWD" \
CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
.runtime/envs/py310-qualification/bin/python \
  scripts/research/grapevine3d_so4_pilot.py \
  --config configs/research/so4_t2_fichtl2024.json \
  --data-dir "$G3D_DATA_DIR" --prepared-dir "$G3D_PREPARED_DIR" \
  --output-dir .runtime/research/so4-t2-diagnostic-20261114-v1/comparison
```

Use the named local Grapevine3D input paths and a new ignored destination when
repeating. Outputs contain measured geometry and must remain local. No remote
plot libraries or storage services are used. The HTML bundles its JavaScript.

Claude code-review dispositions: post-tropism rotations were removed; scaffold
validation precedes direction search. Above-surface starts and nonfinite inputs
are rejected; unsupported higher orders and offset built-in soil rendering are
rejected. The new mode requires explicit coefficients and zero legacy gravity.
Step-size and per-order diagnostics are saved. The reviewer described the
attachment check as newly introduced, but it already exists at `d5918d8`;
it remains intact. Geometric lengths are deliberately retained rather than
silently replaced by stored lengths; malformed zero/degenerate paths fail as
contract violations. Golden CSV hashes from the pre-change revision test legacy
behavior in addition to ordinary regressions.
