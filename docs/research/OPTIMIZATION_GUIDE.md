# Research optimization guidance

Updated 16 November 2026 from current source and retained local run reports.
This guide records reusable methods; field summaries, fitted configurations,
photographs and comparison outputs remain local. Read
[active Calvin research](ACTIVE_CALVIN_RESEARCH.md) or
[active SO4 research](ACTIVE_SO4_RESEARCH.md) for the applicable experiment.

## Choose the construction and observation contracts first

The native `RootSystemSimulation.run(RootSimulationModel(...))`, controlled
offline replay, and separate `CohortRootGenerator` are different interfaces.
The [cohort method](COHORT_ROOT_CONSTRUCTION.md) supports curved primaries,
five explicit orders and nonmaterial crown supports. Its observation projection
uses primary-tree identifiers. Sum those contributions for one vine; crown mass
is separate. Native Fichtl defaults and sealed experiments remain available.

Record coordinates, units, soil surface, validity rules, sampled/missing status,
diameter cutoff and the exact support of each observation. Branching order,
diameter-defined fine roots and hypothetical cohort maturity are distinct.
Basal point diameter, midpoint diameter and exported volume-equivalent cylinder
diameter are also distinct. Fine-root SRL uses sampled fine length divided by
matched sampled dry mass; it is not a whole-system biomass conversion.

Map the actual measurement location before comparing diameters. A midpoint of
an excavated portion need not be the midpoint of a complete generated axis;
recovered endpoints may be cut rather than living tips. A ratio of marginal
order medians is not a median of paired daughter/parent ratios. Report these
estimands separately. Unbranched recovered lengths may be censored lower bounds,
not complete axes or observed first-branch locations.

Match fine-root diameter-class length shares jointly with sampled mass and SRL.
A bulk mass or SRL match can conceal the wrong diameter distribution and therefore
the wrong length per unit mass. Whole-cell voxel distributions are model-only
unless an equivalent observed grid exists; pooled core distributions retain core
sampling support even when positions are ignored.

Branch-junction and terminal-endpoint density/depth can diagnose topology beyond
RLD. Define junctions as distinct daughter-attachment sites and distinguish
represented endpoints from active apices. Use these as optimization targets only
with comparable observed counts and censoring rules. Do not invent data for
unrepresented root orders or confuse projection crossings with junctions.

## Priorities for further construction work

1. **Reconcile anatomical inputs jointly.** Keep each measurement's population
   and location. Model basal/midpoint/tip diameter and taper together, respecting
   parent diameter at each daughter attachment. Compare tails, spread, clipping
   frequency and realised correlations as well as marginal means. Reconcile
   total axis length with first-branch distance and unbranched censoring.
2. **Establish the coarse/crown material budget.** Use independent evidence and
   explicit assumptions. Fine-root core RLD cannot identify coarse or crown mass.
   At fixed length and density, selected-axis mass scales with diameter squared;
   changing taper can also change descendant diameters through attachment caps.
   Global thickening is therefore a coupled biological hypothesis.
3. **Define fine-mass conditioning explicitly.** Keep order-based and
   diameter-based targets separate and state the denominator. Predeclare allowed
   changes, anatomical bounds, convergence margin and infeasibility behavior.
   Record every attempted adjustment. Selected-seed success does not establish
   that a fixed count distribution meets the constraint across a population.
4. **Improve spatial placement at frozen material budgets.** Test origin depth,
   branch emergence, continuation and orientation one mechanism at a time.
   Use smooth correlated curvature with physical distance and moving parent
   tangents. Smaller output fragments alone do not establish better biology.
5. **Evaluate neighbourhood and sampling support.** Retain subject-only results.
   Label translated clones as a layout sensitivity; independently vary neighbour
   architectures for uncertainty. Keep actual-core and area-window comparisons
   separate. A sampling-depth limit is not a maximum root depth.

## Evidence required for each candidate

| Question | Required record |
|---|---|
| Is the computation sound? | Connected crown graph and valid root projection; finite geometry; geometric/stored length agreement; attachment consistency; cutoff accounting; independent cylinder mass; explicit numerical failures. |
| Did the intended mechanism change? | Before/after counts, organ lengths, point diameters, taper, material budgets, branch arcs and spatial diagnostics. Verify claimed invariants. |
| Is anatomy plausible? | Realised distributions, tails, parent caps, branch censoring and uncertainty in cohort assumptions. |
| Is sampled spatial prediction adequate? | Matched core length and mass, SRL, MAE/RMSE, aggregate bias, occupancy, and depth/horizontal profiles. A better mean can accompany worse local errors. |
| Does it generalize? | Frozen configuration on fresh simulation seeds, all outcomes retained; separate observed-vine validation where available. Repeatedly inspected cores remain exploratory evidence. |

Freeze source/configuration/input hashes, seed lists, selection rules and a finite
round budget before execution. Distinguish empirical attempts from invented test
fixtures and exact replay. Preserve source epochs, failed attempts and review
dispositions. Tests qualify algorithms; biomass agreement qualifies only that
constraint; neither establishes biological adoption.

For source-specific checks, use affected geometry/material tests and the
qualified Python environment in [development guidance](../DEVELOPMENT.md).
Historical test counts are retained evidence, not a fresh pass. A documentation
update alone requires no new empirical simulation or fitting.
