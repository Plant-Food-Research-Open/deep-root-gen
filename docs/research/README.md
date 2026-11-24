# Experimental root-architecture tools

These optional tools extend the existing 1.0 simulator with explicit research
controls, controlled replay and observation/evaluation contracts. Legacy remains
the default. The tools do not establish biological validity or adopt a fitted
configuration. Public examples use documented paper inputs and engineering
assumptions; tests use invented geometry and parameters.

## Interfaces and scope

| Interface | Purpose and qualification boundary |
| --- | --- |
| [Fichtl-inspired native mode](FICHTL_RESEARCH_MODE.md) | Explicit insertion, directional search and surface handling; a static approximation, not exact CPlantBox replay |
| [Four-arm replay](SO4_CONTROLLED_METHOD.md) | Cross legacy/Fichtl insertion with legacy/Fichtl continuation on a shared INITIAL; common physical surface and separate keyed random streams |
| [Construction-step replay](SO4_CONSTRUCTION_STEP_REPLAY_HYPOTHESIS.md) | Opt-in integration that separates growth-step resolution from geometric attachment cuts |
| [Current organ lengths](SO4_CURRENT_LENGTH_CDF.md) | Explicit order-specific distributions that avoid dependence on the length of a parent subsegment |
| [Construction rules](DAUGHTER_LENGTH_CONSTRUCTION_SPEC.md) | Explicit assumptions, graph validity and subdivision checks for construction changes |
| [Observation contract](OBSERVATION_FRAME_CONTRACT.md) | Caller-declared raw/RSML landmarks and coordinate verification; synthetic checks do not qualify a supplied measured dataset |
| [Population and mass evaluation](SO4_TARGET10_EVALUATION_AND_MASS.md) | Versioned trait/profile comparison and auditable cylindrical whole-root mass; no active biomass target without a qualified support/density contract |

Construction controls include buried origin, primary azimuth/inclination,
order-specific turning, length-dependent branch zones and within-parent tertiary
length ranking. Their units, coupling and routing restrictions are documented in
the corresponding `SO4_*` method files. Some controls require Fichtl mode,
orders1–3, explicit current-length CDFs and construction-step replay; invalid
combinations fail validation. They are not hidden changes to the legacy mode.

The [primary-curve attachment transform](SO4_PRIMARY_ATTACHMENT_DISTAL_HYPOTHESIS.md)
moves an existing attachment from arc `s` to `b*L+(1-b)*s`, `0<=b<1`, on an
unchanged generated primary curve. It preserves original vertices and biological
organ counts, adds necessary degree2 cut nodes, and rigidly transports complete
daughter subtrees. It compresses interattachment spacing; distal does not always
mean deeper. This is an assumed sensitivity rule, not a measured pruning law.
Fichtl's type1 roots are planted/pruned adventitious scaffolds; supplying their
measured geometry and branchpoints is a separate conditional reconstruction.

Native execution, graph-segment replay and construction-step replay have distinct
first-step and boundary semantics. Save the operator identity, source, parameter
file, seed and INITIAL hash with every comparison. A constructed root system
does not become an independent biological replicate merely by changing its seed.

## Run and test locally

Install the existing locked Python3.10 development/Torch environment as described
in the project instructions. No new dependency or lockfile change is required.
The bounded POSIX source-checkout runner can inspect the public configuration
without running an ensemble:

```bash
python scripts/research/so4_controlled_experiment.py \
  --config configs/research/so4_t2_controlled.json \
  --parameters examples/research/so4_t2_fichtl2024.json \
  --outdir outputs/so4-public-research
```

`--prepare` writes a durable identity and frozen input copies. `--execute` starts
the explicitly bounded ensemble and records every attempt, including failures;
it is not part of the smoke-test command above. Use a fresh output directory.
No training, database, storage service or experiment server is needed.

```bash
python -m pytest -p no:cacheprovider --run-integration
python -m flake8 --count --statistics
```

The source-reference parity tests retain their original old/new geometry,
serialization, diagnostics and RNG checks. Their public reference fixtures are
repository-contained; they must not require a developer's `/tmp` tree or a
specially named dependency directory. See `tests/fixtures/public_checkpoint_references/`
for provenance and reference construction details. These tests use the local Git
executable without fetching objects or accessing the network.

## Interpretation and known limits

The original four-arm method is preserved as a versioned method record. Its
statement that attachment arc coordinates are derived afresh overstates that
runner's check: attachment identities/stored lengths are hashed; geometric edge
and total lengths are checked separately. Do not claim an additional independent
geometric-arc audit from that wording alone.

The mass audit uses child-segment diameter and the declared dry-tissue density:
`mass_g = sum(density_g_cm3 * pi * (diameter_cm/2)^2 * length_cm)`.
Numerical conservation and agreement with `TotalWeight` do not verify measured
compartment support, root diameters, density or a biological tolerance. Published
mass and specific root length alone cannot identify both density and diameter.

The inherited attachment scalar validator has a known extended-precision edge
case: bounds are checked before conversion to Python float, so an extreme
`numpy.longdouble` can underflow to0 or round to1. Ordinary JSON float inputs are
unaffected. A converted-value guard and regression fixtures remain a follow-up.

The draft contains public code, methods and invented fixtures. Measured data,
prepared grids, fitted configurations and local comparison artifacts are not
included. Earlier source-checkpoint tests do not certify a new upstream tree;
record fresh integrated checks. Independent review of the new research source
remains pending; a draft PR and passing synthetic tests are not biological
validation or approval to merge.


## Additional optional research interfaces

- [Model inputs and review](../MODEL_REVIEW_GUIDE.md): native versus separate research APIs, units, defaults and observation support.
- [Cohort constructor](COHORT_ROOT_CONSTRUCTION.md): curved five-order crown-origin cohorts, taper and material accounting; caller owns biological parameters.
- [Five-order primary and material contracts](FIVE_ORDER_PRIMARY_AND_MASS_METHOD.md), [higher orders](HIGHER_ORDER_RESEARCH.md), [primary fractions](PRIMARY_BRANCH_FRACTIONS.md) and [finite-core scope](FINITE_CORE_RESEARCH.md).
- [Curvature](ORDER2_CURVATURE_METHOD.md), [roundoff reconciliation](NATIVE_LENGTH_ROUNDOFF.md), and [proposed primary taper](PRIMARY_ARCLENGTH_TAPER_PROPOSAL.md). Proposed laws are not automatically implemented or adopted.
- [Sequential search](NOTEBOOK_PARAMETER_SEARCH.md): resumable Optuna workers, separate scoring modes, frozen candidates and fresh seeds. Distributed examples are invented; notebook execution is disabled by default.
- [Saved-graph visualization](ROOT_ARCHITECTURE_VISUALIZATION.md) and [optimization guidance](OPTIMIZATION_GUIDE.md).
- [Local runtime recipe](../../RUNNING.md): optional loopback-only service configuration; offline tests do not qualify service deployment.

Observations, fitted configuration arrays, reference profiles and result artifacts remain local. Algorithm checks, scenario agreement, seed robustness and independent biological validation are separate claims. No new biological acceptance threshold or production default is adopted by this integration.
