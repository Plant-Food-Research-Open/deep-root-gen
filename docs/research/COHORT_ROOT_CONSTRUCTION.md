# Optional cohort-based mature-root construction

16 November 2026. Research-only extension, separate from native Fichtl calibration.
All field-derived inputs and comparisons remain local. No production defaults change.

## Reason for a separate construction route

The native explicit primary design already supports organ lengths and initial
orientations, while current-length CDFs support orders 2–5. Its existing global
branch controls do not express individual cohort-dependent daughter counts,
first-branch distances for every order, or distributed crown emergence. Native
heading decisions also depend on attachment subdivision. The new research route
reuses the existing insertion, correlated-curvature and finite-core utilities,
and exports compatible root-only observation tables alongside a full crown graph.
It is not an exact native/Fichtl replay or a replacement calibration.

## Frozen rules before implementation

- Cohort is latent developmental maturity, not measured age in years. Direct
  crown-origin roots retain order 1 in both cohorts. A configurable maturity
  variable correlates dimensions and daughter probability; diameter does not
  determine an inferred emergence date.
- Positive dimensions use bounded lognormal rejection samples. Input mean/SD
  parameterize the untruncated lognormal; truncation changes realized moments.
  Report realized summaries instead of claiming an exactly fitted distribution.
- Total contour length and first-branch distance have separate distributions.
  A sampled first branch beyond the axis end produces an unbranched axis; never
  extend the axis or force a branch at its tip. This conditioning changes the
  realized branched-root distribution and must be reported. Length can exceed
  the practical central scenario to accommodate measured branch extremes.
- Daughter counts are sampled from explicitly supplied discrete probabilities.
  Each child is inserted at a recorded physical parent arc, with a local tangent.
  Base diameter is sampled independently by order, subject to a maximum fraction
  of parent point diameter at the attachment; report constrained draws. This
  anatomical cap may conflict with marginal observed diameter distributions.
- Diameter tapers linearly along physical contour arclength. For endpoints
  d0,d1 on interval h, volume is pi*h*(d0²+d0*d1+d1²)/12.
  Export the equivalent constant cylinder sqrt((d0²+d0*d1+d1²)/3).
  Split at fine-diameter threshold crossings, attachment arcs and original
  geometry corners. Subdivision conserves length and volume; it does not create
  extra direction decisions. Basal point diameter is distinct from exported
  equivalent-cylinder diameter and from measured mid-axis diameter.
- Physical direction stations are independent of attachment cuts. Reuse the
  joint OU curvature integral and spherical exponential; a configurable downward
  drift is an engineering proxy. Surface-crossing steps are reflected downward,
  with a recorded count. There is no lower-depth clipping at the sampling limit.
- Crown nodes are an explicit non-root support skeleton. Their edges do not
  contribute root length or mass. A root-only projection creates one observation
  base per primary tree, preserving all root coordinates, IDs and mass. These
  projection plant IDs identify primary trees, not independent vines. Crown mass
  is a separate explicit input, never inferred from skeletal connector lengths.
- All root mass is geometry-derived using explicit dry density. Report <=cutoff
  and >cutoff compartments; these are diameter classes, not proof of lignification.
  No diameter or length rescaling to hit total biomass. Optional unrepresented
  fine-root mass must remain separate, with no invented spatial RLD.

## Qualification and experiment

Use invented fixtures for deterministic seeds, connected acyclic crown graphs,
exact root projection, length/material conservation after cuts, first-branch
arcs, child attachment constraints, cutoff accounting and invalid input rejection.
Test physical-step sensitivity separately; no assumption of biological convergence.
Freeze local source/input/configuration hashes, seeds and finite round budget.
Compare three count/cohort scenarios using the same rules. Report population
summaries and individual variability, sampled-core and larger-window results,
plus unresolved observation conventions. Biomass failures remain visible.

The owner-supplied primary-length central scenario is approximately 70 cm;
first branching around 30 cm is a different parameter. Larger bounds permit
long-branch-distance extremes. Earlier suggestions of SO4-sized primary stubs
are superseded for this task. SO4 mechanics may transfer; fitted dimensions,
counts and coefficients do not become mature-vine measurements.

## Owner clarifications

The owner confirmed rooting angles are measured from horizontal, positive
downward, and the initial biomass target includes the underground crown/rootstock.
Keep the crown contribution explicit: a transferred literature crown mass is
an assumption, not a measured Site1 value. Root/shoot ratios based only on trunk
and cordon are structural-compartment ratios, not ratios to complete shoot mass.

## Separate proximal-taper sensitivity

Version 2 permits `midpoint_fraction` in (0,1), default .5. With basal diameter
b and terminal diameter t, the physical midpoint diameter is t+(b-t)*fraction.
Interpolate linearly on each half-axis; retain the midpoint as a material cut
when the law is not globally linear. Integrate each piece with the same exact
volume-equivalent cylinder rule. This is a parameterized taper hypothesis,
not a measured universal taper curve. Child diameter limits use the point law
at the attachment; changing taper can intentionally change daughter dimensions.
Original .5 experiments are retained as a separate source epoch. Compare midpoint
and basal measurements separately before interpreting any biomass improvement.

## Numerical qualification after independent review

Version 3 transports the moving curvature frame by the existing minimal proper
rotation, instead of rebuilding a basis from coordinate axes at each step.
Curvature state resets on surface reflection. Starts above soil are rejected.
Near-terminal roundoff stations are merged before integration; near-coincident
material cuts are rejected rather than moving an attachment or relaxing length
conservation. Exported root segments retain the strict rtol=1e-9, atol=0 check.
Crown skeleton edges are excluded from that root-material interpretation.

Configuration validation is explicit, probabilities must sum to one within
1e-12, and nonzero-SD lognormal rejection laws must have at least one percent
probability inside the supplied bounds. Maturity scales apply after those draws;
the supplied bounds describe established-root distributions before scaling.
Tip clamps and daughter-diameter constraints are counted. Stable organ IDs key
random streams within a fixed topology; changing topology can change later IDs
and therefore is not claimed to preserve paired innovations for every organ.

```python
from deeprootgen.research.cohort_root_generator import CohortRootGenerator
architecture = CohortRootGenerator(configuration).generate(
    seed=123, older_count=8, later_count=4
)
# Full graph includes nonmaterial crown supports:
full_nodes, full_edges = architecture.nodes, architecture.edges
# Root-only forest for existing finite-core observation utilities:
root_nodes = architecture.observation_nodes
root_edges = architecture.observation_edges
```

See `tests/test_cohort_root_generator.py` for a complete invented configuration.
Do not pass the full crown graph into legacy root-only statistics. Use the
qualified projection and sum its primary-tree contributions for one vine.
Native `RootSystemSimulation.run()` and its default parameters are unchanged.

## Optional metadata reconciliation for dense attachment graphs

Version 4 adds `reconcile_length_metadata=False`. If enabled, only an interval
failing the unchanged strict geometric/stored length comparison may be changed.
Coordinates and cut positions are untouched. Require both
`abs(error) <= 64*eps*(norm(parent)+norm(child)+stored)` and
`abs(error)/min(actual,stored) <= sqrt(eps)`, with positive lengths. These are the
existing native metadata adapter's agreement bounds, not proof of an error's
cause. Record each old/new length and error. Recheck every interval and the
whole organ at rtol=1e-9, atol=0. Material moments use the reconciled interval
length and are therefore subject to the reported tiny metadata changes. This
option does not repair a geometrically invalid root or authorize changing
biological dimensions. Earlier failed attempts remain in their original ledger.

Version 5 exposes the pure `reconcile_interval_lengths` helper. It rejects an
interval below the coordinate-scale floor64eps*(norm(parent)+norm(child)) and
raises an explicit ValueError for remaining unresolvable intervals. Generation
adds the organ identity to that error. No biological site is silently moved or
resampled. Tests exercise acceptance and both independent guard rejections.
Curvature starts at zero at each organ base and after surface reflection, so
short organs need not reach stationary curvature variance. This transient is
part of the current research model, not a fitted age-dependent curvature law.

These research tables satisfy the finite-core operator's required columns.
They are not thereby qualified for Dash/Prefect, database upload, native graph
serialization or the existing calibration notebook. Additional cohort and
primary-tree metadata belong to this separate research interface.

## Optimization interpretation (16 November 2026)

Curvature comparisons can freeze counts, contour lengths, taper profiles,
attachment arcs and mass while moving positions and attached subtrees. A smaller
integration step changes OU draws; without coupled innovations, similar summary
statistics across steps are a resolution sensitivity, not pathwise convergence.
The literal exported paths should drive both quantitative diagnostics and views.

Material changes have additional coupling. Length affects whether a first branch
is censored beyond the tip; taper changes the point-diameter cap for daughters.
The current constructor shares a within-organ random stream for bounded length,
base/tip diameter and branch draws. A different rejection count can shift later
draws. Stable seeds alone therefore do not guarantee paired organ dimensions or
topology across material configurations. Record realised quantities and reserve
strict fixed-architecture claims for comparisons that verify them explicitly.

A fixed daughter-count distribution does not enforce a fine-mass fraction in
every stochastic realization. Any per-realization conditioning rule needs its
own declared target, adjustment scope, failure behavior and ledger; it is not
currently an automatic guarantee of this API. A material match must still pass
anatomical and spatial checks. Root order and diameter class require separate
accounting, with crown inclusion explicit in the mass denominator.

See [optimization guidance](OPTIMIZATION_GUIDE.md) for the next-work sequence
and the [interface index](README.md); see [active research state](ACTIVE_CALVIN_RESEARCH.md)
for local run records, which stay local.
