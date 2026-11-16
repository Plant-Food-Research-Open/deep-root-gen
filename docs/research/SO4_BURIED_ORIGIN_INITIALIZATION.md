# Explicit buried root-origin initialization: hypothesis before implementation

The owner explicitly permits additional recorded trials as needed and placing
or burying the initial point. Earlier completed attempt caps/ledgers remain
historical. This is a new, separately evaluated construction change following
the corrected-frame audit, order-3 subdivision characterization/specification,
saved-graph orientation diagnosis and seed/connectivity validation fixes.

## Limitation and evidence

The current initial point at model(0,0,0), with soil S=20cm, assumes a vertically
aligned buried stem. The public raw protocol distinguishes soil horizon from
basal cutting node. Under a recovered raw-to-RSML mapping their relative position
can specify a buried-root origin, rather than being confused with the observed
soil reference. The [Fichtl2024 excavation/initialization method](https://pmc.ncbi.nlm.nih.gov/articles/PMC11633832/)
places the basal cutting node below soil and separates static initial roots from
laterals. A population mean basal displacement is a fitted initialization input,
not a published coefficient or independent validation datum.

## Single replacement rule

Add three paired optional parameters, all None by default:

```text
research_base_origin_x_cm: canonical across-row displacement from soil landmark
research_base_origin_y_cm: canonical along-row displacement from soil landmark
research_base_depth_cm:   positive depth of basal node below soil
```

Require all three together, finite x/y, finite positive depth, and an explicit
finite model soil surface. For declared soil coordinate S and base b:

```text
b_target = (x_origin, y_origin, S-depth)
delta = b_target-b_current
p_new = p_current+delta
```

Apply this once to the base and every initial graph node after existing primary
positioning/optional azimuth initialization and before tropism/validation. This
changes model initialization, not observation registration. Do not add a stem or
soil-to-base segment to the root-length total. No direction, inclination, count,
diameter, length law, branch window or coordinate observation rule changes.
The parameters are opt-in research controls, not new production defaults.

For local population reconstruction, x/y/depth can be fixed to equal-vine mean
soil-to-basal displacements derived from verified landmark identities. Keep the
observations and their frame fixed; do not choose offsets by minimizing a model
score. Numerical estimates and individual landmarks remain local. This first
candidate uses the measured initialization estimate once, rather than a free
translation search. Unknown measurement/acquisition uncertainty remains explicit.

## Invariants and numerical checks

Use invented synthetic values and nonzero existing bases to verify the exact
target and common translation of all initial nodes. Parent references, IDs,
edge count, diameters, per-edge/organ/total lengths and the original construction
RNG state must remain unchanged. Primary and lateral relative angles are
unchanged by translation. Check depth=S-base_z, all-or-none/finite/positive
parameter validation, repeat seeds, default/explicitNone legacy golden graphs,
finite connected trees and unchanged numerical tolerances. Keep assigned yaw
diagnostics distinguishable from the subsequent base-translation stage.

## Separate experiment

Use a fresh recorded execution round and ten matched seeds against the saved
azimuth construction. Record parameters, origin diagnostics, source/input/output
hashes and every attempted run. Preserve previous capped ledgers unchanged.
Use one worker/two threads,60seconds per attempt and a declared bounded execution
window. Evaluate the same accepted13trait/3profile target without rounding or
threshold changes. Translation cannot repair width or span ratio, so do not
claim it resolves those failures. If further changes are needed, diagnose and
record a separate mechanism before implementation. Final qualification must
bind the exact selected source and configuration.
