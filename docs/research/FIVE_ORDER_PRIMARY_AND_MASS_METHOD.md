# Five-order primary curvature and mass scenarios

An entirely invented, executable demonstration is available at
[`examples/research/five_order_primary_mass_synthetic.py`](../../examples/research/five_order_primary_mass_synthetic.py).
It constructs a small five-order tree, curves explicit initial primary tangents,
checks conservation and applies a grouped mass scenario. It contains no measured
data or adopted biological parameterization.

Public method decision, 15 November 2026, against the working tree based on
`d5918d8bd182e351817f374426687cb546eeaa10`. The tree contains existing research
work. This memo contains no local observations, fitted parameters or empirical
comparison results. Numerical examples below are invented. These are optional
research constructions; they do not change historical defaults or establish
biological parameter values.

## Primary angle means an initial tangent in the curved route

The existing [explicit primary design](FINITE_CORE_RESEARCH.md) rotates the
complete basal-to-apex chord to the supplied inclination and azimuth. That
historical interpretation remains valid for its existing route. A local field
angle and a whole-root chord angle are different quantities.

For the new curved-primary replay, the supplied inclination `alpha` below
horizontal and azimuth `phi` from +x toward +y define the **assigned initial
unit tangent**:

```text
t0 = (cos(alpha) cos(phi), cos(alpha) sin(phi), -sin(alpha))
```

The first physical chord uses this heading, subject to the explicitly selected
soil-boundary operator. Subsequent chords turn under the declared curvature
law. The terminal chord direction and tip location emerge from that path;
neither is constrained to equal the initial angle. Record assigned heading,
realized first heading and boundary intervention separately. A root starting
on the surface with an upward assigned heading cannot preserve that heading
and remain below the surface. Reject unsupported origins and report accepted
boundary changes instead of describing the realized angle as exact.

Use a distinct route/version and an explicit initial-vector mapping. Do not
silently reinterpret a saved historical chord-angle setting. A constructed
polyline is only a numerical representation of an assumed trajectory; a
protractor angle does not measure its curvature, complete course or tip.

## Geometry, attachment and conservation contract

Follow the physical-step and optional OU conventions in
[the curvature method](ORDER2_CURVATURE_METHOD.md). Each physical increment
must be exported as a real chord of its stated length. Attachment-only graph
cuts subdivide these chords without making new curvature proposals. Preserve
the source diameter and density interval boundaries by arclength, including
when a physical chord crosses a boundary.

For a fixed-topology curvature comparison, preserve each biological organ's
total arclength, each original diameter/density interval's length, biological
parent relationship and daughter attachment arclength. Consequently both
`sum(diameter_cm**2 * length_cm)` and
`sum(density_g_cm3 * diameter_cm**2 * length_cm)` remain constant. Preserving
only total length and a diameter list would not preserve volume or mass.
Geometric degree-2 nodes may increase; they are not additional roots.

A daughter starts at its parent's realized attachment point and uses the local
realized parent tangent. Preserve its insertion innovation in that local frame;
its absolute world heading may change. At a physical knot use the incoming
chord tangent consistently, and record this one-sided convention. At the base
use the explicitly declared initial tangent. Attachments inside a chord use
that chord's tangent. Descendants must follow parents in topological order.
Invalid flags and excluded descendants must use the same support convention
before and after replay, so exclusion cannot masquerade as conservation.

The soil operator must preserve chord length while constraining the endpoint;
shortening an offending chord changes the construction. Record interventions
separately from interior curvature. With OU curvature, transport the moving
frame through the accepted heading and retain the declared latent-curvature
boundary policy. A changed numerical step size changes the experiment unless
convergence has been established. Same seeds alone do not establish pathwise
coupling across resolutions.

## Five orders are a declared topology scenario

Maximum order five permits orders 1 through 5; it does not guarantee every
order is populated. Positive desired totals require an explicit construction
rule, positive parent support and lengths. Record order-specific root counts,
length distributions, daughter allocation and attachment zones. Generic
higher-order counts and lengths are assumptions unless independently observed;
they must not be labelled measured traits. Transferred order-3 direction laws
for orders 4 and 5 remain extrapolations. See
[higher-order controls](HIGHER_ORDER_RESEARCH.md) for the existing scope.

Keep adding higher-order branches separate from changing primary curvature.
First compare curvature with a fixed topology and the conservation contract
above. Then compare explicit branch-addition scenarios. Those scenarios
intentionally change total count, length and potentially mass; failure of those
quantities to remain constant is not a curvature bug. State whether their
budget is fixed total length, fixed total dry mass, fixed diameter distribution,
or unconstrained branch addition. These choices answer different questions.
For example, adding roots at unchanged diameters adds mass; redistributing a
fixed mass across more length necessarily reduces a weighted diameter scale.

Use independent, versioned random streams for topology, lengths, insertion,
curvature and boundary operations, keyed by stable biological identities.
Adding a daughter must not perturb the retained primaries merely by consuming
the next number in a shared random stream. Pair unchanged mechanisms across
arms and repeat across recorded seeds; audit whether native constructor RNG
coupling prevents that pairing. Freeze parameter grids, per-round attempt and
runtime/output budgets before each bounded comparison. Preserve rejected
trials and state which parameter changed.

## Audit represented mass before changing diameters

Use the same qualified segment support for length and mass. Record units,
diameter-versus-radius interpretation, excluded/invalid descendants, supported
orders, positive lengths, tissue-density provenance and represented organs.
For incoming constant cylinders in cm and dry density in g/cm3:

```text
M = (pi/4) * sum(rho_i * d_i**2 * L_i)
```

This is represented root-cylinder dry mass. Stem, crown, missing roots and
unsampled space are not automatically included. Distinguish whole represented
systems, subject-only systems, neighbourhoods and finite sampling cylinders.
Mass in overlapping cores cannot be summed to estimate total system mass.
Compare analytical and exported-geometry totals before any scaling. Report
mass by order, by declared anatomical compartment and by diameter threshold as
separate summaries.

The existing `mass_audit` accepted partition excludes invalid children but
retains valid descendants; the finite-core qualifier excludes invalid nodes
and all descendants. These are different policies. For a finite-core scenario,
derive allocation and comparison totals from the finite-core-qualified support
or explicitly reject graphs with relevant invalid ancestry. Do not silently
mix the existing audit's accepted total with the finite-core total.

A total-mass target and density assumption do not identify a unique architecture
or taper. At fixed length, multiplying every diameter by `a` multiplies mass by
`a**2`; multiplying density by `b` multiplies mass by `b`. A single mass target
therefore cannot identify both density and diameter. Freeze independently
supported density and locked measured dimensions before constructing a
diameter scenario. Do not score measured length, mass and their derived
specific root length as three independent observations.

## The requested 25% is an order-group scenario

Define the explicit exhaustive groups `F={4,5}` and `C={1,2,3}` and a target
share `p=0.25`, with a separately declared total target `M_target`:

```text
M_F_target = p * M_target
M_C_target = (1-p) * M_target
```

This allocates **25% of represented dry mass jointly to orders 4 and 5**. It
does not mean 25% to each order and does not identify the split between them.
A common group scale preserves their starting mass ratio; any different split
requires another explicit assumption. Root order describes branching
hierarchy. Diameter-defined fine roots can occur in other orders, and an
order-4 segment can exceed a fine-root diameter cutoff. Recompute the actual
diameter-defined fine share after scaling; never relabel the order share as
measured fine-root biomass.

For group `g`, let `B_g` be locked mass and `A_g` the current adjustable mass.
With lengths and density fixed, its common adjustable diameter scale is

```text
a_g = sqrt((M_g_target - B_g) / A_g)
```

This requires a nonnegative residual and positive `A_g` when residual mass is
positive. If `A_g=0`, feasibility requires the target to equal locked mass;
scaling cannot create missing geometry. If zero diameter is forbidden, a zero
residual with existing adjustable positive-length segments is also infeasible.
Check both groups before changing any data. Reject overlapping, uncovered or
invalid order groups and targets that require changing locked dimensions.

For locked coarse mass `B_C`, a necessary lower bound is
`M_target >= B_C/(1-p)`. With the 25% share it is `B_C/0.75`, not merely `B_C`.
Equality leaves no mass for adjustable coarse roots and is infeasible when
they must retain positive diameters. For example, an invented locked primary
mass of 2 g makes a 1 g total impossible; even a 2.5 g total fails because its
coarse budget is only 1.875 g. If fine-group mass is also locked, additionally
require `M_target >= B_F/p`. Diameter bounds, parent-child taper conditions and
required minimum diameters may impose stronger restrictions. A scale that
satisfies algebra alone does not establish anatomical plausibility.

Keep a failed target as an explicit infeasibility result. Do not silently
thicken all roots, shrink the locked primary, alter density or change the
target to hide the conflict. A successful scaling receipt must report original
and resulting group masses, locked masses, scales, total mass and residuals,
with unchanged topology, lengths and coordinates verified separately.

## Evidence and interpretation

Numerical fixtures should cover assigned-versus-realized first headings,
boundary interventions, local daughter tangents, cut invariance, deterministic
streams, five-order connectivity, per-interval mass conservation, analytic
quadratic scaling and infeasible locked-mass targets. They establish software
behavior, not biological calibration.

For local data comparisons, freeze whole-core or spatial holdouts before
tuning, and compute normalizations and baseline estimates from training data
only. Keep true sampled zeros and unsampled observations distinct. Report
training fit, held-out-core prediction and fresh-seed variability separately.
Held-out cores can assess conditional prediction within a sampled setting;
they do not recover a unique root topology or establish validation on unseen
vines, sites or biological mechanisms. A 25% scenario remains a scenario even
if its training fit improves. Claude review is currently deferred, not
completed. Local empirical inputs and results remain outside this memo.

## Implemented public interfaces and independent review

`deeprootgen.research.primary_curvature.curve_primary_roots` accepts supplied
node/edge tables and explicit per-organ `initial_inclination_deg` and
`initial_azimuth_deg`. Its optional OU controls are `curvature_sd_rad_cm`,
`correlation_length_cm` and `downward_drift_rad_cm`; `None` curvature is an exact
copy route. Zero diffusion with positive correlation length is active and may
still bend if downward drift is positive. It supports selected primaries and
retains descendant orders through five. This is a table transformation, not a
new native growth law. The separate native explicit-primary design gate now
permits orders through five while retaining the explicit higher-order control
validation; its historical angle remains a chord angle.

`deeprootgen.research.order_mass_allocation.audit_root_mass` audits supplied
graphs using the finite-core geometric-cylinder operator and an explicit
uniform dry density. It rejects any invalid flag rather than mixing exclusion
policies. Supplied nonbase density metadata must agree with that density.
`allocate_order_mass` requires exhaustive order groups and optional locked
orders. It preserves the starting total unless `target_total_g` is explicit.
Its generic API permits zero target mass and zero resulting diameters; this
mathematical allowance is not anatomical qualification. It reports diameter
cutoff migration and daughter/parent diameter inversions without repairing
them or applying an invented biological limit.

Independent public-source review found and resolved nonfinite derived-moment
acceptance in primary replay and insufficient organ-chain validation in the
mass audit. The latter now checks one entry and no internal branching per
supplied organ identity. Mass diagnostics avoid an unnecessary squared-scale
overflow, and mark unrepresentable specific root length explicitly undefined.
No material engineering blocker remained for the bounded scenario comparison.

The final independent execution used Python 3.10.20 and only invented fixtures:

```bash
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
CUDA_VISIBLE_DEVICES='' .runtime/envs/py310-qualification/bin/python \
  -m pytest -p no:cacheprovider tests/test_primary_curvature.py \
  tests/test_order_mass_allocation.py tests/test_core_observation.py \
  tests/test_curvature_process.py
```

Result: **176 passed in 1.51 seconds**. SHA-256 identities were unchanged before
and after this execution:

| Source | SHA-256 |
|---|---|
| `deeprootgen/research/primary_curvature.py` | `275eaee923dba98cfa9381cfe9b047fe778f078cc8f5577d7dce990071e1baf8` |
| `deeprootgen/research/order_mass_allocation.py` | `006ec39d8c84e9aeccdc45511207df96f3dd04647e68c6ffecaee827b83b7add` |
| `tests/test_primary_curvature.py` | `527d053337992435fc6a7486883f42a03c0b1480644344967e09734be5da3f6f` |
| `tests/test_order_mass_allocation.py` | `4f872d7e33307c1f6be9e502e264eec836b46caa792d69aa6cfdbaef2a65eebf` |

This review did not execute native simulations or inspect private inputs,
observations or empirical outputs. The native order-five design extension was
inspected but is outside this independent executed test count. Numerical
conservation and synthetic scenario checks do not establish geometric
resolution convergence, biological parameters or empirical success.

## Follow-up: physical primary branch window and replay optimization

`research_primary_branch_zone_cm={"start_cm": a, "end_cm": b}` is an optional
**construction-time** input. For each primary's supplied daughter quota `n`,
the branch-site helper places midpoint quantiles
`s_j = a + (j+0.5)*(b-a)/n`, `j=0..n-1`. It requires `0<a<b<L` for every explicit
primary length `L`; there is no silent shortening or clipping of the zone.
Sites are distances along the primary contour in cm, not spatial depth or a
fraction of its length. Zero quota gives no sites.

This interface is restricted to native static Fichtl construction, explicit
primary designs, supplied counts and keyed current-length CDFs through maximum
order three, four or five. It does not alter daughter counts or sampled current
lengths. Primary curve/material intervals are retained through subdivision;
only primaries use this site override. The old fractional branch-zone setting
does not define the active primary window. Higher-order branch positioning
retains its existing rules.

This constructor route is distinct from moving an already built daughter
subtree. A daughter inherits diameter from its new primary attachment cylinder;
its diameter and mass may change even with its length fixed. Native Fichtl
geometry also retains its dependence on graph subdivision and shared proposal
RNG. The site helper consumes no RNG, but that fact alone does not establish
identical final native geometry across windows. Audit mass after construction
and label this as a coupled branch-placement comparison. It does not satisfy
the fixed-diameter subtree-conservation contract of primary-curvature replay.

The primary-curvature implementation now gathers audit arrays once and batches
descendant rotations when every candidate endpoint is safely below the soil
surface. It accumulates the original stored edge lengths in topological order;
it does not assume those lengths equal geometric chords beyond the existing
audit tolerance. A conservative arithmetic envelope routes exact and
near-surface cases through the unchanged sequential boundary operator. This
envelope selects the implementation path; it does not relax soil containment,
change projection geometry or alter the boundary RNG keys. Interior batch
geometry has numerical-tolerance parity, not asserted bitwise identity.

The optimized path also falls back for nonfinite or at-most-1e-12 vector norms,
preserving the original `unit()` rejection semantics. The independent review
compared optimized source
`38bc6d911f8314708de2e0f6894125c99a35e49b0e27f16d45d540a7474adf8f` against preserved
public source `275eaee923dba98cfa9381cfe9b047fe778f078cc8f5577d7dce990071e1baf8`.
Twenty-seven invented cases crossed three seeds, three angle/curvature settings
and three starting depths, including the surface and 1e-14 cm below it.
Material fields, edges, primary records, attachment records and descendant
boundary records were exactly equal. Maximum coordinate difference was
`1.3322676295501878e-15 cm`, checked with `rtol=0, atol=1e-12 cm`. Source identity
was unchanged across the comparison. These small fixture results do not
establish pathwise parity for every possible graph or biological validation.

Reviewer model provenance: the parent reports the delegated review was
configured/requested as `gpt-6-astra` with `high` reasoning. The child context
does not independently expose the actual backend identity; this is a requested
configuration record, not a verified returned-model claim. No Claude call was
made for this review; Claude review remains deferred.

The follow-up source review covered the branch-zone helper, its schema/scope
validation, the primary-only `_prepare_branch_nodes` override, inactive INITIAL
serialization, and the curvature audit/batched-descendant changes. The final
branch-zone integration emits an explicit empty receipt for zero-quota
primaries without changing their arrays or RNG. Inactive fields short-circuit
before accessing new parent metadata and are omitted in both INITIAL creation
paths, preserving the existing physical replay hashes.

Independent execution on Python 3.10.20 gave **75 passed in 4.00 seconds**:

```bash
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
CUDA_VISIBLE_DEVICES='' .runtime/envs/py310-qualification/bin/python \
  -m pytest -p no:cacheprovider \
  tests/test_primary_curvature.py tests/test_physical_step_replay.py \
  tests/test_primary_branch_zone.py::test_midpoint_api_is_exact_deterministic_and_handles_zero_quota \
  tests/test_primary_branch_zone.py::test_primitive_quota_and_unrepresentable_sites_fail_closed \
  tests/test_primary_branch_zone.py::test_exact_existing_curve_knot_is_retained_without_rng_or_duplicate_cut \
  tests/test_primary_branch_zone.py::test_zero_quota_primary_emits_explicit_empty_receipt_without_array_or_rng_changes
```

These are supplied invented-graph, helper and fake-organ fixtures. No native
simulation or private input was executed by the independent reviewer. Source
hashes were identical before and after the run:

| Source | SHA-256 |
|---|---|
| `deeprootgen/research/primary_curvature.py` | `38bc6d911f8314708de2e0f6894125c99a35e49b0e27f16d45d540a7474adf8f` |
| `deeprootgen/utils/primary_branch_zone.py` | `5a88f828f308fa9eee130ac401bcec598e4dea0958d5f2b683167d331ab4e734` |
| `deeprootgen/model/root.py` | `28f442643522293bc776b1be0ed96cead6b5838aefd92908514c7d9967aaf832` |
| `deeprootgen/data_model/simulation_data_models.py` | `1b3c22435dd277694575bad9ab8f60ca1c53403c0929816a8d34c50d77eb3b10` |
| `deeprootgen/research/so4_controlled.py` | `186db950c91ceaf5eb39b93e62eefb83eeb58dd2be30b9b6199a0157ea172ad6` |
| `tests/test_primary_curvature.py` | `6f425484405751889cc12c18cc6a7f8b3adb832121750ffa8c640765300d7daa` |
| `tests/test_primary_branch_zone.py` | `30df7aa933920460ab5b44f67aa371913b7cf2fd88943ac64a108a2d5d1abc34` |

No material blocker remained in this bounded public-source review. This receipt
does not replace the separately executed full repository suite or native
constructor integration checks, and it makes no empirical-fit claim.

## Invented end-to-end example

From the repository root, using the qualified Python 3.10 environment with the
locked runtime dependencies available on `PYTHONPATH`:

```bash
python examples/research/five_order_primary_mass_synthetic.py
```

The [public example](../../examples/research/five_order_primary_mass_synthetic.py)
constructs a small five-order graph with an explicit primary branch window,
applies initial-tangent primary curvature, audits mass, then assigns orders 4
and 5 jointly 25% of the original total mass. It prints a JSON verification
summary to stdout and does not read observations or write artifacts. Every
count, length, density and direction is invented. All orders are unlocked in
this example, so the mass scenario can alter primary diameters. Diameter-class
migration and parent-child diameter inversions are reported, not repaired;
successful numerical checks are not a biological pass or a recommended taper.
