# Opt-in capped-branch redistribution: hypothesis before implementation

Research construction experiment, recorded before implementation. The completed
four-arm direction ablation remains unchanged. The owner has authorized at most
60 new ensemble attempts in total: 40 completed ablation attempts plus at most
20 construction attempts/recovery, including failures and reruns. This supersedes
the intervening 200-attempt proposal. Synthetic algorithm tests remain separate.

## Limitation and minimal replacement

The current sampler starts at `floor*parent_length + Uniform(0,spacing)` and
advances sequentially by stochastic interbranch spacing. It stops as soon as
the requested count cap is reached. When spacing is small and the parent is
long, the retained daughters occupy only a proximal prefix of the eligible
window. A count cap therefore changes both count and emergence distribution.

Test one construction change: retain the number of sites produced by the legacy
sampler and its complete random-number consumption, but redistribute those n
sites across the same declared arc-length window. For parent geometric contour
length L cm, eligible fractions f and c, and j=0,...,n-1:

```text
a = f*L
b = c*L
s_j = a + (j+0.5)*(b-a)/n
```

For n=0 return no sites. Require finite positive parent segment lengths,
`0 <= f < c <= 1`, and finite strictly interior sites. Preserve the existing
parent-polyline corners and subdivide only at new attachment sites using the
current geometric construction. No fitted rotation, observation alignment,
growth-direction change or new length formula is part of this variant.

The new explicit opt-in parameter is
`research_branch_placement="redistribute_capped"`; default
`"legacy_spacing"` retains the current path exactly. The legacy sampler runs
once in either mode, so requested/capped count and RNG state are preserved at
the sampling operation. Downstream realised lengths/counts may still differ
because parent subdivision affects the existing daughter-construction terms;
measure and disclose those differences rather than claiming whole-system identity.

## Evidence and assumptions

The limitation is directly traceable to `sample_branch_sites` and its
`max_branches` break, and to the existing geometric attachment construction.
The [Fichtl2024 pipeline](https://pmc.ncbi.nlm.nih.gov/articles/PMC11633832/)
supports separating the static initial roots from emerging laterals and
parameterizing architecture from digitized geometry. It does not establish
this redistribution equation. Quantile placement is an explicit engineering
research assumption, not a measured biological spacing law. The declared
eligible window remains an existing assumption; no provenance is invented.

The previous .75 cm global spacing is an engineering capacity input. In this
variant it still governs legacy capped count selection but does not describe
the realised redistributed spacing, which is `(c-f)*L/n`. Report that realised
spacing explicitly. Published tropism coefficients, current-length controls,
base depth, scaffold orientations and their production defaults remain fixed.

## Synthetic checks and numerical contracts

- A straight 40 cm parent, f=.1, c=.9, n=4 yields sites 8,16,24,32 cm rather
  than a short proximal prefix. The sites lie in the declared window.
- A bent parent uses geometric cumulative arc length; attachment points remain
  on the parent and conserved subsegment lengths sum to the original contour.
- Legacy versus redistribution consumes the same sampler RNG state and retains
  its sampled site count. Explicit/default legacy produce the same seeded graph.
- Check n=0, invalid geometry/fractions, finite output and deterministic seeds.
- Real graph checks cover connectivity, parent references, nonnegative finite
  dimensions, realised counts/lengths and the pre-change legacy golden outputs.

Keep existing per-edge rel1e-5/abs1e-6 and geometric accounting 1e-8 cm checks.
These are numerical tolerances, not biological thresholds.

## Bounded separate experiment

First run ten matched seeds against the saved arm-D reference, using the same
paper-informed inputs and the same insertion/continuation/surface rules. Charge
every new construction attempt to the remaining 20-attempt ledger before work.
Preserve the reference, raw data and prior observation operators. Use the
independently verified versioned soil-frame observations for physical comparisons;
never replace a transform because it improves a model score.

Evaluate the user-accepted population target: 13 positive-valued architecture
traits each within20% relative difference, and three normalized population
profile total variations <=.20. No voxel threshold or biological adoption is
implied. Shallow fraction is reported separately. All eight vines are already
known descriptive references, so this is in-sample representation.

Answer explicitly: does emergence shift as intended; are length/count changes
acceptable under the frozen target; are all graphs valid; and does population
placement improve? Only then consider another separately documented construction
mechanism. Do not add one when the remaining attempt budget cannot support a
meaningful ten-seed verification. No additional ensemble is authorized here.
