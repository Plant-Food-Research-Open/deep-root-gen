# Finite-core research observations and explicit primary design

These opt-in interfaces support local research with actual cylindrical soil
samples. They preserve existing generator defaults, spatial statistics and
sealed reconstruction experiments. They do not qualify biological priors,
whole-vine biomass or calibration acceptance by themselves.

## Explicit primary construction

`RootSimulationModel.research_primary_design` is an ordered list of records:

```python
dict(primary_id="invented-primary", category="assumed-horizontal",
     length_cm=20., diameter_base_cm=.8, diameter_apex_cm=.2,
     inclination_deg=15., azimuth_deg=30.)
```

These numbers are invented. Every entry requires finite numeric geometry and
unique IDs. Categories are metadata, not an automatic mapping to native
outer/inner classes. Supply exactly `outer_root_num + inner_root_num` entries,
ordered by those native constructor slots. The native slot assignment is
separate from the meaning of an observed direction category.

Length and diameter enter primary construction before daughter insertion
nodes are selected. The existing sampled segment-length proportions are
normalized once to the supplied total. Diameter tapers linearly by original
construction-segment rank, from the first segment's diameter to the last;
inserted cuts inherit the original cylindrical segment's diameter. This is not
a claim of taper linear in arclength. A single original segment requires equal
base/apex diameters. Daughters therefore inherit the changed attachment geometry
and diameters consistently.

Inclination `alpha` is the **complete primary's basal-to-apex chord** below
horizontal; azimuth `phi` is from +x toward +y:

```
u = (cos(alpha)*cos(phi), cos(alpha)*sin(phi), -sin(alpha))
```

A proper rigid rotation maps the existing chord to `u`, rotating the complete
primary subtree about the common base while retaining lengths and attachments.
The operation precedes optional common-origin translation and tropism. A field
protractor's local angle is a different observation; using it as the complete
chord is an explicit research proxy. It does not establish measured primary
trajectories, curvature or insertion tangents.

This interface requires static Fichtl research mode, an explicit matching
seed, maximum order 1–5 and a physical surface at z=0. Orders 4/5 retain the
required explicit [higher-order direction assumptions](HIGHER_ORDER_RESEARCH.md)
and their existing scope validation. Increasing maximum order does not supply
measured counts, lengths or directions. It rejects simultaneous
shared yaw/reversal/inclination controls. Primary origins share the single graph
base; distinct per-root origins require a separate scaffold/topology design.
Native and controlled graph replay support the new design, with authenticated
INITIAL parameters. Existing construction-step/search surface guards remain
unchanged. Absent-design branches retain prior behavior and RNG draws; inactive
design fields are omitted from saved INITIALs.

The optional native `research_primary_branch_zone_cm` is a distinct
construction-time placement control: it puts each supplied primary daughter
quota at midpoint sites inside an explicit physical arclength window. Its
scope requires static maximum order 3–5, explicit primary designs, supplied
counts and current-length CDFs. New attachment cylinders can change inherited
daughter diameters and mass; native geometry retains subdivision/RNG coupling.
The separate `curve_primary_roots` table operator instead accepts explicitly
named initial-tangent angles and constructs curved primaries while preserving
material intervals and attachment arcs. It does not reinterpret the native
design's chord-angle fields. See the
[five-order primary and mass method](FIVE_ORDER_PRIMARY_AND_MASS_METHOD.md)
for these distinctions, conservation checks and review evidence.

## One observation support for length and mass

`deeprootgen.research.core_observation.qualify_root_segments` validates explicit
node/edge forest topology, finite geometry, one base per plant, parent agreement
and strict invalid flags. It excludes an invalid node and its descendants from
both length and mass. The returned table retains exclusions for accounting.
Coordinates and diameters are in cm; the fine-diameter cutoff is supplied in mm
and compared against each child segment's diameter, inclusively. It does not
use the generator's organ-mean `root_type` to decide fine/coarse membership.

The support uses geometric segment length and an explicit uniform dry density
in g/cm³. A child-node diameter describes its incoming constant cylinder:

```
segment_volume_cm3 = pi * (diameter_cm / 2)**2 * geometric_length_cm
segment_dry_mass_g = dry_density_g_cm3 * segment_volume_cm3
```

`predict_core_observations` intersects each straight segment with each finite
vertical sampling cylinder. The same retained centreline fraction multiplies
length, root volume and dry mass. Core RLD divides included length by the exact
cylinder volume. Optional per-plant results add to the neighbourhood prediction.
No voxel approximation or spatial smoothing is introduced.

The root-volume calculation is a centreline-fraction approximation to actual
root/core volume overlap. This matters especially for coarse roots approaching
the core diameter; their core-mass predictions need separate qualification.
Overlapping sampling cylinders are separate observations and their totals must
not be presented as whole-system biomass. The closed-boundary convention is
explicit; exactly coplanar horizontal segments on shared depth faces require
care when summing adjacent intervals.

Core records require `core_id`, `x_cm`, `y_cm`, `z_lower_cm`, `z_upper_cm`,
`radius_cm` and strict boolean `sampled`. Use unique observation IDs for depth
increments and retain the physical core ID separately for whole-core splits.
Optional `known_volume_cm3` must agree numerically with the supplied geometry.
An unsampled increment produces missing values; a sampled empty cylinder
produces a real zero. Coordinates must already share the declared root frame.

The new intersection path corrects a legacy near-parallel endpoint-reversal
defect with true-zero motion tests and stable scaled quadratic algebra. The
original `statistics.spatial_rld.calculate_core_rld` remains unchanged. Numerical
fixtures distinguish these algorithm checks from biological validation.

## Local pilot workflow

Keep raw workbooks immutable and processed tables separate. Resolve or explicitly
freeze competing observation definitions before fitting. Source declarations,
geometry, masks, diameter support, lengths and density assumptions belong in a
versioned contract. A total dry-mass scenario is not an observed mass target.
Do not independently penalize measured length, mass and their derived SRL.

Freeze whole-core/spatial splits before optimization; estimate normalizations,
SRL/diameter summaries and baseline parameters from training data only. Preserve
true observed zeros and report MAE/RMSE/bias rather than row-wise percentage
errors at zero. Fresh seeds measure simulation variability, not unseen-vine
validation. Sparse finite-core intersections need a feasibility/sensitivity
screen before large searches.

Vine roots in a core may originate from neighbours. Record origin/seed/ID
offsets, assumptions about neighbour size and the subject-only contribution.
Check layout convergence or prove a conservative finite path-length bound for
unrepresented origins. Subject structural measurements do not measure each
neighbour's root architecture.

Empirical workbooks, fitted settings and comparison artifacts must stay local.
Current local Calvin Site 1 processing and feasibility work is under
`.runtime/research/calvin-site1-pilot-20261115-v1/`. Its workbooks, parameter
arrays, core predictions, fitted settings and figures remain local. Other
agents receive public code and invented fixtures only.
