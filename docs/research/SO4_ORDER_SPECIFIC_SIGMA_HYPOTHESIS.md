# Research order-specific Fichtl-inspired direction persistence

Recorded before implementation against public source25ae482. This is one
optional direction-control extension. Counts, construction lengths, branch
sites, origin, insertion laws, objectives and physical boundary operators are
unchanged. Historical source epochs and the global-sigma default remain intact.

## Mechanism, units and provenance

Both existing proposal paths use alpha = sigma * sqrt(ds_cm) * Z, Z~N(0,1).
Alpha is a turning angle in radians; sigma therefore has units
rad*cm^(-1/2). Retain this equation and the existing candidate-count rule,
1+stochastic_round(N*sqrt(ds_cm)).

Add research_fichtl_sigma_by_order, default None. An active nonempty mapping
selects orders2 and/or3; omitted orders use the required existing global
fichtl_sigma. Keys are integer2/3 or their exact JSON string spellings; reject
boolean/float/unknown/duplicate-normalized keys. Values must be explicit finite
nonboolean numbers >=0. Zero is deliberately allowed, matching global sigma's
valid straight-direction limiting case. Do not skip any existing random draw
at zero. Reject empty maps and orders beyond max_order.

Resolve the effective order-specific sigma once and use it for BOTH validation
and multiplication. A shared alpha-sampling helper must retain the original
multiplication order and RNG calls. No extra stream or key version is introduced.
The separate research assumption is labelled research-fichtl-sigma-by-order-v1
in active-only diagnostics, with effective coefficient and override/fallback
source. None adds no diagnostics and is omitted from saved INITIAL parameters.

Different persistence of main lateral axes and tertiary directions might
separate horizontal transport from fine-root directional response. This is an
explicit engineering assumption, not a measured per-order coefficient or an
attribution that Fichtl reports separate sigma2/sigma3 values. The retained
paper-inspired global sigma remains the default. No new step-convergence,
physiological time-step or CPlantBox equivalence claim is made. This extension
supplies no fitted values or biological acceptance threshold.

## Routes and retained couplings

Apply the resolver/shared alpha helper in the existing graph-segment controlled
Fichtl proposal and the construction-step operator that calls it. Permit the
map to vary as a directional replay setting without rebuilding the scaffold.
Reject active maps for controlled legacy continuation (armsA/B), legacy
native tropism, or unvalidated callers that would otherwise ignore the map.
Support native Fichtl using the same resolver/alpha formula while preserving
its existing candidate filtering and first-segment search semantics. The
controlled construction operator still bypasses search on its first full step;
a one-step organ has no direct continuation-sigma response there.

Sigma3 alone leaves order2 replay trajectories exact. Sigma2 may move tertiary
origins/tangents, so identical tertiary trajectories are not promised. Selection
objectives and surface interventions can alter persistence; decreasing sigma
is not asserted to improve a measured metric monotonically. Active coefficients
may change boundary decisions, but cannot change counts, stored dimensions,
construction RNG, candidate draws/counts or the objective draw schedule.

## Numerical checks before empirical work

Use invented proposals to verify ds1->4 gives a factor2 in alpha at fixed
candidate count and matched Z, unit vectors, per-order selection/fallback,
zero with unchanged draws, and deterministic seeded outputs. Maps equal to
global sigma must reproduce geometry and innovations exactly. Check sigma3
leaves order2 exact; distinguish sigma2's downstream attachment coupling.
Exercise native and canonical boundary cases and their distinct first-step
rules. Reject malformed/empty/bool/nonfinite/out-of-order maps and unsupported
routes, including bypassed schema input. Check JSON map keys.

Compare missing versus explicit None in separate subprocesses against the
qualified prechange public source, preserving exact nodes/edges, diagnostics,
serialization and RNG where those outputs are exposed. Retain all existing
conservation/attachment tolerances, default goldens and full synthetic tests.
No empirical simulations or calibration are part of implementation qualification.
