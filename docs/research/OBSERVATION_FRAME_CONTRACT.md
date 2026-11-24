# Explicit Grapevine3D observation-frame contract

This is public preparation and synthetic algorithm qualification. It does not
qualify an observed dataset, fit model parameters, or change an existing grid.
The old converter and previously generated outputs remain unchanged.

The [2024 digitization methods](https://pmc.ncbi.nlm.nih.gov/articles/PMC11633832/#sec6)
define **raw point labels** 0 as grafting point, 1 as soil horizon and 2 as basal
node. The [dataset README, §2.2](https://zenodo.org/api/records/15632062/files/README.rtf/content)
describes below-ground raw axes: x downward, y along the planting row, z across
rows; coordinate units are cm. These labels are not RSML point-array indices.
The public paper/supplement describes customized TXT-to-RSML processing but does
not publish an explicit stem-point selection or complete coordinate transform.

A caller may explicitly test the **v2 candidate contract**:

- RSML stem index 0 corresponds to raw soil label `1`.
- RSML stem index 1 corresponds to raw basal label `2`.
- Raw-to-RSML axis permutation is `[1,2,0]` and signs are `[1,-1,1]`:
  `(rsml_x,rsml_y,rsml_z) = (raw_y,-raw_z,raw_x) + translation`.
- Translation is determined only by matching the declared raw and RSML soil
  anchors. The basal anchor is an independent check, not another fit constraint.
- Every exported RSML point must match at least one transformed raw record with
  Euclidean distance <= **1e-8 cm**. No alternate transforms, rotations, scales,
  model scores or optimized translations are selected by this verifier.

This candidate is a caller-supplied contract, not a mapping established by public
documentation. An independent local audit must establish its applicability,
uniqueness and input provenance before downstream observation comparison. Even
perfect coordinate-set matching does not establish attachments, edge topology,
root classes, branching semantics, acquisition completeness or biological validity.
The verifier does not infer a one-to-one point assignment: repeated branch points
can match multiple raw records, and all candidate ties are retained.

Canonical soil coordinates first subtract the declared RSML soil anchor, then
invert the contract's signed permutation. In recovered, soil-centered raw axes:

```text
across = raw_delta_z
along  = raw_delta_y
depth  = raw_delta_x
```

For the v2 candidate contract specifically this becomes:

```text
across = -(rsml_y - soil_rsml_y)
along  =   rsml_x - soil_rsml_x
depth  =   rsml_z - soil_rsml_z
```

Depth is positive below soil. This is a fixed axis transformation and anchor
subtraction. It preserves Euclidean distances and in-situ relative geometry;
it does not rotate individual roots, normalize planting orientation or repair
attachments. Whether the declared anchors represent the actual physical soil
surface for particular inputs is a separate verification question.

The standard-library APIs are in `scripts/data/grapevine3d_contract.py`:

```python
from scripts.data.grapevine3d_contract import (
    read_raw_records, read_rsml, v2_candidate_contract,
    verify_mapping, read_canonical_vine,
)

contract = v2_candidate_contract()  # explicit candidate selection, not a verdict
raw_records = read_raw_records(explicit_raw_path, units="cm")
architecture = read_rsml(explicit_rsml_path)
report = verify_mapping(raw_records, architecture, contract)
# report.status is fixed_contract_point_set_verified_only; topology_verified=False
vine = read_canonical_vine(explicit_rsml_path, contract)
```

`parse_raw_records(text, units="cm")` and `parse_rsml(text)` are pure parsing
alternatives. `canonical_point(point, soil_anchor, explicit_contract)` inverts
that contract's signed permutation before selecting raw (z,y,x). The two-argument
`canonical_point(point, soil_anchor)` is a documented v2-only shorthand; it does
not infer the export mapping. `read_canonical_vine` always passes its explicit
contract, so independently declared export permutations yield the same canonical
geometry when each is verified against the same raw architecture.
`signed_permutation(point, contract)` performs only its declared
raw-axis mapping. `duplicate_ids(records)` reports every repeated-ID occurrence.
`verify_mapping` raises `ValueError` on missing/ambiguous anchors, failed basal
mapping or any unmatched exported point. Its returned `MappingVerification`
retains the translation, selected anchor record indices, all point-match candidates,
duplicate IDs, maximum nearest residual and all unused raw record indices.

Raw parsing accepts a leading task header and `//Node` … `//EndModule` blocks
with `ID:` and `Parent:` annotations. IDs such as `2.1.3.1.1` remain strings;
leading zero components survive. A Parent may start with `Node`, and annotation
suffix kinds such as `Internode` are preserved verbatim. Coordinate rows contain
seven finite semicolon-separated numbers: constant; X; Y; Z; angle1; angle2;
angle3. Coordinates use fields 1:4 after the constant (zero-based slicing).
Every row and duplicate ID remains in input order with its source line and full
annotations; a dictionary keyed by ID must never replace these records.
Duplicate anchor IDs require an explicit zero-based occurrence in the contract;
other duplicate IDs and coordinate ties are retained and reported, not resolved.
Unexported raw records, including a potentially omitted graft point, are reported
without silently assuming the reason for their omission. No measured inputs are
included with this tool or its tests.

`read_canonical_vine(path, explicit_contract)` requires a contract, reads only
RSML, and therefore reports `declared_contract_only_raw_mapping_not_checked`.
It preserves labels and consecutive points within each nonstem root polyline;
it excludes stem segments and adds no inter-polyline attachment connectors.
Use the unchanged `grid_vine`, `clip_to_soil` and `split_segment_into_cells` from
`scripts/data/grapevine3d_grid.py`. Their positive-depth clipping and half-open
cube assignment by segment-piece midpoint remain in force. A segment exactly on
a cube face belongs to the cell selected by floor in canonical coordinates.

Tests use newly invented coordinates, modules and RSML only. They exercise
hierarchical/duplicate IDs, explicit wrong mappings, cm checks, soil-only
translation, all-point matching/ties, rigid length invariance, consecutive
polyline preservation, soil crossings and exact cube-face ties. These tests do
not examine observations and cannot verify the candidate contract for real vines.
