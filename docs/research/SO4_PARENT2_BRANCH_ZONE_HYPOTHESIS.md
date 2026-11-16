# Opt-in parent-order-2 branching zone

Recorded before implementation, after qualification and bounded evaluation of
the construction-step replay operator. This is one separate biological
construction rule; existing defaults and all historical attempts remain intact.

## Limitation, provenance and assumption

The current requested daughter count on most order-2 parents is capped by a
small integer draw, largely independent of current parent length. That can put
daughters on short parents while limiting long-parent degrees. Qualified
geometry alone does not qualify every observed parent link; the local
association audit retains its exceptions and remains separate from this public
method. Do not add or change biological acceptance thresholds.

Fichtl et al. Table 4 gives SO4 type-2 basal zone 7.8 cm, apical zone 16.4 cm
and interlateral distance 4.8 cm, with between-root variation. A deterministic
static transfer to CURRENT contour length is a research assumption, not the
paper's dynamic growth model or a universal biological cutoff. Report provenance
and any locally tested spacing separately from measured coefficients.
[Fichtl et al., 2024, Table 4](https://pmc.ncbi.nlm.nih.gov/articles/PMC11633832/).

## One rule and explicit scope

Add `research_parent2_branch_zone_cm`, default None, containing explicit
`basal_cm`, `apical_cm`, `spacing_cm`. Require finite positive values, Fichtl
mode, max order 3, explicit matching seeds, CDFs for orders 2/3 and the qualified
`construction_steps_v1` grid. Native execution remains unsupported for that
grid and must continue to fail closed. Use controlled research replay.

For sampled CURRENT order-2 parent length L:

```text
A = L - basal_cm - apical_cm
n = 0                          if A < 0
n = 1 + floor(A / spacing_cm)  otherwise
site_j = basal_cm + j * spacing_cm, j = 0,...,n-1
```

State a deterministic decimal-input policy for this discrete count and test
exact/adjacent floating values; do not introduce a tolerance band around the
biological boundary. Reject excessive site counts before allocating memory
using a documented numerical limit, never silent truncation. Validate strict
interior and increasing representable sites. Existing geometric tolerances
remain unchanged.

Override only order-2 parents, creating order-3 daughters. Consume the original
count and legacy spacing draws first, then replace their sites deterministically.
Handle an original zero cap without adding legacy spacing draws or suppressing
the active zone. None must preserve the original path exactly. Use sampled
current L, checking its existing geometric agreement; do not let mesh rounding
decide the count. Primary redistribution and all CDF samplers remain unchanged.

Expose per-parent original requested/retained counts, current L, zone inputs,
realized sites and count. Topology, cuts, tertiary counts and total system length
can change intentionally. Moving a site also changes inherited daughter
diameter; record that existing coupling. Global birth-organ IDs may shift and
therefore change tertiary keyed samples. Do not claim identical surviving
tertiary samples across changed topologies.

## Isolate parent geometry

Changing daughter counts shifts legacy shared construction/placement draws.
Provide a pure controlled-research helper that freezes the PRIMARY scaffold
to a matched reference INITIAL with the same seed, primary identities,
lengths, dimensions, attachments and base. Transport each complete order-2
subtree from its old primary attachment/tangent to the reference one, then
copy the reference primary coordinates exactly. Reject mismatched references
before mutation. Consume no RNG and preserve all edge lengths/dimensions.

Rebuild INITIAL organ geometry and refresh positioned construction-boundary
metadata from live nodes, retaining original sampler receipts and boundary
identities. Record reference SHA and transforms. Under canonical replay,
unchanged order-2 identities and construction steps must then produce identical
parent trajectories despite different daughter counts/cuts. This isolates
parent geometry; tertiary birth-key shifts remain explicitly reported.

## Meaningful synthetic checks and first experiment

Test short/equality/spacing boundaries, adjacent floats and decimal arithmetic,
nonfinite/bool/invalid inputs, allocation limit, original zero caps, legacy draw
consumption, realized graph counts/positions, primary-reference atomic rejection,
finite connected acyclic graphs, deterministic seeds and existing tolerances.
Test exact primary equality and order-2 construction-step proposal/path equality
between capped and changed-count cases. An invented 10 cm parent has no sites
with the illustrative paper means; an 80 cm parent has twelve, from 7.8 through
60.6 cm. Default/None native and controlled regressions must remain unchanged.

After qualification, begin with a separately frozen four-setting comparison:
capped control and three explicit zone spacings, ten matched seeds each. Use
the same canonical operator and reference primary scaffold. Record all40attempts,
including failures; one worker/two threads,60s/attempt,900s generation and1800s
round limits, within the existing phase storage cap. Values/configurations and
empirical results remain local. Evaluate the frozen13traits/3profiles plus
conditional branching diagnostics; no biomass inference or biological adoption.
Any selected candidate requires fresh qualification and independent review.
