# Research primary-azimuth initialization: hypothesis before implementation

Second, separate construction improvement; implement only after the first
capped-branch redistribution experiment is evaluated. Ten construction attempts
remain under the owner's total60-attempt limit (40ablation+20construction).
This document is recorded before implementation or the second ten-seed run.

## Limitation and evidence

The existing primary-positioning loops distribute root azimuths around a full
circle. They do not represent a population with a directional initial-root
layout. A lateral-growth objective cannot repair that initial architecture
without changing another mechanism. The
[Fichtl2024 initial-root method](https://pmc.ncbi.nlm.nih.gov/articles/PMC11633832/#sec13)
explicitly separates measured static adventitious roots from subsequently
emerging laterals and acknowledges planting-dependent initial positions.

Test one opt-in initialization rule: sample the azimuth of each initial primary
root from an explicit von Mises distribution, rotating its complete initial
subtree around the vertical axis through the root-system base **before** lateral
tropism/replay. Retain its inclination, bent-polyline shape, all segment lengths,
diameters, counts, IDs, attachment arcs and primary z coordinates. Keep the base
position, construction window/spacing controls and lateral tropism fixed. This
is not a fitted display rotation or a post-growth architecture alignment.

## Rules, units and provenance

For primary basal-to-apex vector v in model coordinates, let original azimuth
phi0=atan2(v_y,v_x). Draw phi from

```text
p(phi | mu,kappa) = exp(kappa*cos(phi-mu)) / (2*pi*I0(kappa))
delta = phi-phi0
p_new = base + Rz(delta)*(p_old-base)
```

Apply the same Rz to all nodes of the primary subtree. Coordinates and lengths
are cm. API mean azimuth is degrees, measured from the across-row x axis toward
the along-row y axis. Kappa is dimensionless and nonnegative. Trigonometric
calculation uses radians. An independent versioned seed/primary-organ stream
must not advance the existing construction/direction RNG. Record assigned and
realised initial azimuths.

Add paired optional parameters `research_primary_yaw_mean_deg` and
`research_primary_yaw_kappa`. Defaults are None; both absent preserves the
legacy path exactly. Require both together, finite values, mean in[-180,180]
degrees and kappa in[0,100]. This adds no biologically measured default.

For the local experiment, fit mu and kappa from the verified canonical primary
crown geometry, with equal total weight per vine. For observed primary
azimuths phi_i and weights w_i summing to1:

```text
C = sum(w_i*cos(phi_i)); S = sum(w_i*sin(phi_i))
mu = atan2(S,C); R = sqrt(C*C+S*S)
I1(kappa)/I0(kappa) = R
```

This is an in-sample initialization estimate, not a published coefficient,
biological prior or independent architecture-validation channel. Numerical
values and individual crown records remain local. The von Mises family is an
explicit research approximation; it is not evidence of a biological growth
response. No additional free translation, length/count change, polar-angle fit
or tropism fit belongs to this variant.

## Synthetic and numerical checks

- Known rigid yaw around a nonzero base preserves every z coordinate, subtree
  parent/child attachment, per-edge length and cumulative parent arc.
- All descendants rotate with their primary; different primaries use distinct
  keyed streams; repeat seeds reproduce the assigned azimuths.
- Default versus explicit absent controls preserve pre-change golden graphs;
  the existing RNG state is unchanged by the additional independent stream.
- Validate parameter pairing, finite/range errors and zero-horizontal-chord
  rejection; verify finite connected realised graphs and conserved counts/lengths.
- Retain existing rel1e-5/abs1e-6 per-edge and1e-8cm accounting tolerances.

## Separate evaluation and stopping rule

Use the same ten matched seeds as the first construction variant. Evaluate the
already frozen13relative-trait and3profile criteria on versioned soil-frame
observations. All prior baseline/ablation/first-construction artifacts remain
unchanged, with per-variant source and parameter hashes. Charge every attempt,
failed run and recovery to the final ten available slots. Stop adding mechanisms
when that meaningful verification no longer fits. If the accepted20% target is
not met, report it explicitly; budget exhaustion is not goal completion.
