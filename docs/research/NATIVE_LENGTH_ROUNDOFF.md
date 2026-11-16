# Opt-in native length-metadata roundoff reconciliation

This is an explicit numerical recovery for supplied native graph tables. Finite
exported endpoint coordinates are authoritative. The adapter may reconcile
stored length metadata to their represented Euclidean distance; it does not
move, snap, shorten or repair coordinates, fit parameters or establish biological
validity. Numerical agreement does not prove that roundoff caused a discrepancy.

## APIs and stage diagnostics

The standalone [helper](../../deeprootgen/research/native_roundoff.py) returns
copied node and edge tables plus an audit report:

```python
from deeprootgen.research.native_roundoff import reconcile_native_edge_lengths

corrected_nodes, corrected_edges, report = reconcile_native_edge_lengths(nodes, edges)
```

A later rigid primary/subtree transform can introduce a fresh endpoint-distance
roundoff discrepancy. For the [primary curvature operator](../../deeprootgen/research/primary_curvature.py),
use the explicit two-stage hook when that recovery assumption is appropriate:

```python
from deeprootgen.research.primary_curvature import curve_primary_roots

curved_nodes, curved_edges, diagnostics = curve_primary_roots(
    nodes, edges, primary_entries,
    seed=seed,
    curvature_sd_rad_cm=q,
    correlation_length_cm=ell,
    reconcile_length_roundoff=True,
)
```

Here the caller supplies the existing graph, explicit initial-tangent entries,
seed and curvature assumptions. The keyword is a strict boolean function option,
not a new simulator default or an observation/calibration parameter.
`diagnostics["length_roundoff_reconciliation"]` contains separate `input` and
`output` helper reports. The input call precedes the original input audit; the
output call immediately precedes the original output audit and conservation
checks. Explicit use with inactive curvature also records both stages.

The default is `False`. Omitted/False retains the previous output tables and
diagnostic shape. Deterministic, stochastic and inactive public fixtures were
compared exactly with the pre-hook implementation. A local import avoids the
helper/validator dependency becoming a circular module import.

## Numerical admission and units

Coordinates, stored lengths and diameters are cm; density is g/cm3. Let
`L = norm(childXYZ-parentXYZ)`, `S` be the stored positive length,
`E = abs(L-S)`, and `eps = np.finfo(np.float64).eps`. Only an edge failing the
unchanged test below is a correction candidate:

```python
np.isclose(L, S, rtol=1e-9, atol=0.0)
```

Both positive finite lengths must satisfy BOTH numerical agreement bounds:

```text
E <= 64 * eps * (norm(parentXYZ) + norm(childXYZ) + S)     [cm]
E / min(L, S) <= sqrt(eps)                              [dimensionless]
```

For binary64, `sqrt(eps)` is approximately 1.49e-8. The first bound depends on the
coordinate origin; the second caps the relative correction even at a far-away
origin. These are admission guards, not relaxed validator tolerances or proof of
cause. A larger discrepancy, nonfinite/zero/negative edge, collapsed geometry,
malformed schema/topology or edge-parent disagreement rejects the operation.
A correction requires binary64 stored-length metadata; the helper does not
promote the whole column or round the replacement into a lower-precision dtype.

Only admitted failing rows' `length` values can change. Passing rows, coordinates,
IDs, topology, diameters, density, other fields, row order, index, dtypes and
attributes remain exact. Inputs are not mutated. The original strict graph
validator runs afterward without a changed body or tolerance.

## Conservation and limits

The curvature operator's entire original conservation tail remains unchanged:
per-organ geometric length, `sum(diameter**2 * length)`,
`sum(density * diameter**2 * length)`, biological identities/counts, original-node
arc identities and the existing soil check must still pass their original
checks. Helper admission is necessary, not sufficient. An admitted correction
to a tiny whole organ or early prefix can still fail the original moment or
retained-node arc check. The positive public integration fixture uses a tiny
trailing segment after a longer daughter segment, consistent with sorted native
construction weights.

Reports retain changed IDs, old/new lengths, absolute/relative errors and both
guards. Per-order and total stored-length moments include before/after values,
summed edge deltas and relative deltas, including cylinder volume and dry mass.
Those metadata interpretations can change. Within each adapter call, geometry-based
length/volume/mass deltas are separately zero because endpoints and material
attributes are fixed.

Input reconciliation establishes the conservation reference for subsequent
curvature. It can slightly change summed primary stored length; the existing
`ceil(total_length/max_step_cm)` station-count sensitivity remains near exact
step-size multiples. The hook does not redefine that integration rule. Output
reconciliation leaves the already generated coordinates unchanged. Retain the
source identity and both stage reports for an explicitly versioned recovery.

## Executed public qualification

The adapter has **32 invented table-only cases** and **15 independent pure
probes**. The curvature hook adds **14 table-only cases** and **8 independent
pure probes**. These new cases call no native simulator constructor or `run`.
They cover passing-row parity, both admission bounds, unchanged geometry,
material-delta accounting, true defects, rotated trailing edges and retained
conservation failures.

The full qualified suite passed **1618 tests, with no failures, errors or skips**;
pytest reported 73.76 s. It includes existing synthetic native simulation tests;
the integration marker count does not enumerate every native call. This is
algorithm/compatibility qualification, not empirical or biological validation.
Python 3.10.20 and the existing qualified dependency overlay were used, with two
BLAS threads, bytecode writing disabled and pytest plugin autoload disabled.
The before/after source snapshot was identical:

`9f1fed3a782fef0fa16215864700b92a4612a159acbb8f17b4bbdb994ee37968`

Public local protocols, fixture accounting, review and full-suite receipts are
under `.runtime/research/public-native-roundoff-qa-20261116-v1/` and
`.runtime/research/public-curvature-roundoff-qa-20261116-v1/`.
The helper hash is `2e45f5122965ddebf2af5860a777e3085c648bdf1cf7a8748929c5834417053a`;
the qualified curvature-module hash is
`c0818619d6e300a516a6782a48c114d943d7fdcd8fe8cd12a95df5961dafdf0a`.
This methods note was added after the full-suite snapshot closed, without any
Python changes or further publication.
