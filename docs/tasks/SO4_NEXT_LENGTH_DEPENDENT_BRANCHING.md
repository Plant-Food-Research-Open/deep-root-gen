# Next construction improvement: length-dependent tertiary branching

Status: proposed mechanism and validation design; not implemented. Read
[active state](../research/ACTIVE_SO4_RESEARCH.md) and the local
`CONDITIONAL_BRANCHING_DIAGNOSIS_LOCAL.json` in the target10 research root.
Do not change the accepted thirteen-trait/three-profile tolerances.

## Limitation

`RootOrgan._draw_lateral_count()` gives order-2 parents a requested count from
the same small integer range, scaled by `growth_sec_root`. With the present
research configuration this produces four or five daughters on most parents.
That cap can reproduce population total counts while putting daughters on
short parents and preventing large daughter counts on long parents. The local
audit uses direct nested RSML associations and operational root labels; resolve
the recorded raw-parent exceptions before treating every association as a
qualified biological relationship. Keep geometry and topology evidence distinct.

## Evidence and one proposed rule

Fichtl et al. Table 4 gives SO4 type-2 basal zone 7.8 cm, apical zone 16.4 cm
and interlateral distance 4.8 cm, with substantial reported variation. These
are model-parameter evidence, not universal cutoffs or confidence bounds.
A static transfer to current-length DeepRootGen is an explicit research
assumption. [Fichtl et al., 2024, Table 4](https://pmc.ncbi.nlm.nih.gov/articles/PMC11633832/).

For a parent of current contour length L, a candidate opt-in rule is:

```text
A = L - basal_cm - apical_cm
n = 0                          if A < 0
n = 1 + floor(A / spacing_cm)  otherwise
sites_j = basal_cm + j * spacing_cm, j = 0,...,n-1
```

Require finite positive zone lengths and spacing, strict interior sites and
an explicit numerical allocation limit that rejects rather than truncates
an excessive count. Apply only to parent order 2, producing order-3 daughters.
Keep primary/secondary counts and current-length CDFs fixed initially. Defaults
must retain the original capped construction. Record changed topology,
attachment positions, counts, lengths, dimensions and organ-ID sampling keys;
do not claim fixed topology for this separate experiment.

An invented 10 cm parent has no daughters with these illustrative means;
an 80 cm parent has twelve, at 7.8 through 60.6 cm. Test the exact zone boundary,
short roots, long roots, finite geometry, connectivity, parent references,
deterministic seeds and realized counts/positions. Preserve existing numerical
tolerances and legacy fixtures.

## Resolve numerical coupling before interpreting a count experiment

The current directional replay integrates at graph segments, including nodes
inserted solely for daughter attachment. Its angular variance, candidate count
and random keys depend on those subdivisions. A changed branching rule can
therefore change the parent trajectory as well as daughter allocation. First
characterize that dependence with equivalent synthetic parent curves having
different attachment cuts. If isolating branch allocation, use a separately
versioned physical growth grid with graph cuts interpolated onto the resulting
curve, and verify invariant parent trajectories under added attachment nodes.
Do not retroactively relabel historical graph-grid results.

Changing the number of daughters also changes downstream draws in the legacy
shared construction RNG, including primary placement. Freeze a matched primary
scaffold or separate the relevant streams before claiming a pure branching
effect. Keep keyed current-length sampling conditional on stable organ identity
explicit; changed topology does not guarantee identical child samples.

## Bounded experiment and interpretation

After synthetic qualification, compare capped and zone-based allocation using
the same declared directional operator, seeds, origins and primary scaffold.
Record one construction rule at a time, all attempts and any failures. Begin
with ten matched seeds per arm and retain the existing CPU, time and storage
limits. Keep source/input/output hashes and compressed-artifact identities.

Evaluate all frozen traits/profiles, total length, validity, counts by order,
parent-length versus daughter-count distributions and the fraction of fine-root
length on short parents. The latter are diagnostics, not silently added
biological acceptance thresholds. A count improvement that ruins length or
spatial placement does not justify recommendation. Qualify any selected
candidate on fresh seeds before claiming the population target.

Whole-root biomass remains a separate evidence task: verify compartment
support, independent diameter/density provenance and its own tolerance before
activating a constraint. Do not infer missing root mass from this branching rule.
