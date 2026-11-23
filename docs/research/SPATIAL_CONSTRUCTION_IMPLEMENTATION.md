# Spatial construction in schema 4

The three controls run through the shared static generator and reuse its
root organs, diameter eligibility, physical materialization and graph checks.
Use the [invented combined input](../../examples/design/spatial_construction_synthetic.json)
to review the syntax, and `--explain-config` to see active orders, units and
consumers. Empirical field assessment follows the separate comparison protocol.

## Direction along the row

Use `row_alignment_per_cm` on any order with correlated curvature. Each
physical step updates OU curvature, applies downward drift, then damps the
heading component perpendicular to the row by `exp(−strength × step_cm)`
relative to the along-row component. The kernel normalizes the heading and
applies the existing reflection and frame transport. Both signs of model y
are equivalent. Exactly perpendicular and exactly axial headings are fixed
under the isolated alignment update. This update consumes zero innovations.

A positive strength requires `strength × step_cm ≤ 0.5`. Heading alignment
alone composes exactly over substeps at float64 tolerance. Physical step
refinement changes the integration of the path and the interaction with OU
and downward drift. Material cuts reuse the physical trajectory. The
reported diagnostic weights the squared along-row tangent component by
the length of each physical piece.

## Length-dependent branch sites

The `length_poisson_sites_v1` law samples on the half-open contour zone
`[basal_exclusion_cm, parent_length_cm − apical_exclusion_cm)`. The two
exclusions and mean spacing are positive centimetre quantities. When the
parent activates, the proposal count is Poisson with intensity given by
usable zone length divided by mean spacing. The site's distribution is uniform
in that zone. The law can produce zero proposals on an active parent.
An empty zone or activation probability zero issues no branch stream.
Activation probability one skips its Bernoulli draw. The remaining draws
use a namespace keyed by biological parent ID.

The shared final-site filter rejects proposals where the parent point diameter
is below the configured minimum. The proposal receipt distinguishes first
proposed and first accepted arclength, original count, placed count, diameter
rejections and invalid descendants. Eligibility after the Poisson draw allows
disjoint suitable intervals and preserves the inclusive diameter threshold.

This law conflicts with exact-count conditioning and competing site or count
owners on the same parent order. Order-2 relocation and Poisson branching
on parent order 1 also conflict. Relocation on a different parent order
composes. Maturity can scale length and material. Its probability-scaling
setting must be off while the Poisson law is active. The execution budget
checks cumulative Poisson proposals and available workspace nodes before
allocating positions. Changes in branching can also change daughter birth
IDs and subsequent native RNG draws elsewhere in a vine.

## Whole-vine origin catalogues

A schema-4 catalogue embeds `entries` and a selection policy. Each
`common_point` entry has one `origin` with x, y and depth in cm.
Each `primary_layout` entry has a `primaries` list with the same coordinates
and unique zero-based `index` values. Indices cover the supplied
`primary_root_count` in outer-then-inner birth order. A complete primary
layout receives one nonmaterial anchor per primary and shares one plant ID.

`sample` sorts entries by ID, normalizes their positive `weight` values,
and uses a single run-level keyed draw. Omitted weights give equal vine
probabilities. `fixed` resolves one ID with zero selection draws. A record can
carry `provenance` with source frame, source SHA-256, conversion version and
a comment. `origins_status`, `crown_census_status` and `headings_status` records
describe the support of those inputs. The effective pool excludes presentation
metadata. The exported input retains all the records and their source fields.

Primary headings must be complete within an entry. Selectable records use
the same heading ownership. A record with `heading_unit` on every primary
uses `initial_heading: origin_heading` on order 1 and conflicts with primary
yaw and inclination controls. A primary layout also conflicts with an explicit
primary design. A common point can use an otherwise supported explicit design.
Convert field coordinates before embedding a record. The engine uses x across
row, y along row and depth measured down from its declared soil surface.

## Verification and replay

The [validation matrix](../../scripts/validation/native_engine_matrix.py)
checks all eight combinations of the three controls and exports and reloads
each through the same schema. It also runs the eight previous matrix cases.
Use a new directory for the results.

```bash
python scripts/validation/native_engine_matrix.py --outdir /tmp/deeprootgen-spatial-matrix
python -m deeprootgen simulate --config examples/design/spatial_construction_synthetic.json --outdir /tmp/deeprootgen-spatial-example
```

The full integration suite passed 2,072 tests on Python 3.10.20. Frozen
feature-off comparisons reproduce geometry, material, branch diagnostics,
effective-model identities and native and keyed RNG states. The caller
matrix covers the Python and notebook loader, CLI export/reload and the
application's advanced configuration mapping.

The SO4/Calvin field evaluation of the new construction controls is pending.
Field evaluations should treat diameter support and parent branching
eligibility as separate variables and preserve the observation support.
