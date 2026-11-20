# Supplied primary branch fractions

`research_primary_branch_fractions` is an **opt-in native construction assumption**.
It supplies the same list of daughter emergence fractions to every primary. It
uses no measured observations and does not fit lengths, counts or diameters.
The default is `None` and retains existing behavior.

## Rule and API

For a primary with physical contour length `L`, fraction `f` places an order 2
attachment at arc coordinate `s = f * L`, measured from the primary origin.
Fractions must be a nonempty, strictly increasing list of finite numeric values
strictly inside `(0, 1)`. Booleans, strings, duplicates and endpoints are rejected.
There is no endpoint snapping. Unrepresentable sites or subsegments below the
existing construction cutoff fail rather than silently changing the list.

For example, the invented list `[0.2, 0.5, 0.8]` gives sites `[2, 5, 8]` cm on a
10 cm primary. The rule applies to contour length, not projected distance,
depth or distance from a trunk. Category labels do not determine these sites.

Starting from a complete, supported explicit-primary specification with two
primaries, the following invented topology uses three daughters per primary:

```python
from deeprootgen.data_model import RootSimulationModel
from deeprootgen.model import RootSystemSimulation

# spec already contains the complete native Fichtl max5 configuration,
# two explicit primary-design entries and the required CDFs/order controls.
spec.update(
    research_primary_branch_fractions=[0.2, 0.5, 0.8],
    research_primary_branch_zone_cm=None,
    research_root_counts_by_order={1: 2, 2: 6, 3: 4, 4: 3, 5: 2},
)
parameters = RootSimulationModel(**spec)
simulation = RootSystemSimulation(random_seed=parameters.random_seed)
simulation.run(parameters)
```

The pure helper API in
[`primary_branch_fractions.py`](../../deeprootgen/utils/primary_branch_fractions.py)
is `primary_fraction_sites(length_cm, retained_count, fractions)`. Each planned
primary quota must equal `len(fractions)`, and the supplied population must satisfy
`count2 = count1 * len(fractions)`. A different fraction-list length therefore
requires a different order 2 count; it does not preserve the previous topology.
Each native primary exposes `primary_branch_fractions_diagnostics` containing the
version, supplied fractions, contour length, quota and realized sites in cm.

## Supported scope and retained couplings

The active field requires static native `tropism_mode="fichtl2024"`, `t=0`,
`max_order` 3 through 5, physical `soil_surface_z_cm=0`, an explicit primary design,
matching explicit constructor/parameter seeds, exact counts for all represented
orders and current-length CDFs for orders 2 through the maximum. Higher-order
Fichtl assumptions remain mandatory for orders 4 and 5. The construction grid must
be `None`.

An absolute primary branch zone cannot be coactive. Existing restrictions on
count conditioning, including parent2-zone, active tertiary-rank and distal
attachment combinations, remain in force. **Controlled replay rejects active
fractions explicitly**: its older count-site authentication uses global windows
and does not establish this native construction contract.

Only order 1 parent attachment sites change. Later parent orders retain their
existing global `floor_threshold`/`ceiling_threshold` rule. Primary fractions
bypass the unused primary global-window redistribution. Site placement draws no
random numbers; original primary corners and incoming-cylinder material
intervals remain present after subdivision. This preserves primary contour
length and cylindrical volume/mass at the original density.

Daughter CURRENT lengths remain CDF-conditioned without a parent-fragment length
addition. Daughter diameters still inherit the diameter of the new attachment
cylinder, so mass can change. Native Fichtl geometry also retains its existing
graph-fragment and shared-RNG dependence. Changing counts, seeds or biological
organ IDs can change the keyed CDF draws; this mechanism does not promise an
unchanged length pool across different topologies. Subsequent primary curvature
preserves the attachment arc, but is a separate optional operator.

For inactive `None`, no fraction placement or RNG action occurs. Both
`Skeleton.from_tables` and `_initial_saved_parameters` omit the inactive field
from saved parameters, preserving historical INITIAL payload hashes.

## Executed public qualification

All evidence uses invented public fixtures, independently of empirical trials.
The [37 new test cases](../../tests/test_primary_branch_fractions.py) include
max3/max4/max5 native fixtures with `[0.2, 0.5, 0.8]` or `[0.1, 0.6]`, exact attachment
arcs/counts, daughter CURRENT lengths, primary material conservation, rooted-tree
exports, determinism, invalid inputs/quotas, inactive hash parity and rejection
of active controlled replay. Four native determinism cases perform eight full
`run` calls; initialization, serialization and preconstruction guards are
accounted for separately.

The reviewed shadow source passed **218 focused tests**. Independent public
review passed **25 pure checks**, including a bent parent, physical material
conservation and a regression for the unused primary global-window calculation.
After the five-file integration, the full qualified suite passed **1572 tests,
with no failures, errors or skips**; pytest reported 73.61 s. The before/after source
snapshot SHA256 was identical:

`16c4147507077b884d4394f4229f60fd820cbf82ae876b634d7cc02015823985`

The full run used Python 3.10.20, the existing locked overlay, NumPy 1.26.4,
Pandas 2.2.2 and two BLAS threads, with bytecode writing and pytest plugin autoload
disabled. From the repository root with that qualified environment:

```bash
PYTHONPATH=.runtime/research/so4-t2-diagnostic-20261114-v1/locked-overlay:$PWD \
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2 \
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
.runtime/envs/py310-qualification/bin/python -m pytest \
  -p no:cacheprovider --run-integration
```

Local receipts, exact source hashes, fixture accounting and the reviewed patch
are under `.runtime/research/public-primary-fractions-qa-20261116-v1/`.
This note was added after the full-suite source snapshot closed; no Python
source changed for the documentation addition. These checks establish numerical
and compatibility behavior, not biological validity or an adopted calibration.
