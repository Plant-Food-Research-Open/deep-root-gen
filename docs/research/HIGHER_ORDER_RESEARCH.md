# Explicit root-order 4/5 research controls

15 November 2026. Opt-in implementation; legacy defaults and sealed SO4/T2
experiments remain unchanged. This extension prepares conditional T4
reconstruction. It does not establish biological validation or run a search.

## Mechanism and parameter provenance

The previous construction/replay/evaluation route ended at order 3. Simply
raising `max_order` would omit higher-order evidence from evaluation or use
unspecified direction coefficients. A single branching-number/growth rule also
cannot independently represent increasing counts followed by a decline across
orders. Explicit higher-order direction assumptions and optional count
conditioning address these two limitations separately.

For Fichtl mode with `max_order: 4` or `5`, supply
`research_higher_order_tropism` with exactly the entries `4..max_order`. Each
entry contains `theta_deg`, `theta_sd_deg`, `probability_down` and `trials`.
Finite, nonboolean values are required: angle 0–90 degrees, standard deviation
at least zero degrees, probability 0–1, trials 0–100. Sigma uses the existing
global `fichtl_sigma` or explicit `research_fichtl_sigma_by_order`; it is not
duplicated in the higher-order map.

[Fichtl et al. (2024), Table 4](https://pmc.ncbi.nlm.nih.gov/articles/PMC11633832/)
provides SO4/T2 type-2/type-3 directional coefficients: insertion values
51.8/50.4, spread 22.5/22.5, sigma 0.2/0.2, trial coefficients 2/1 and downward
probabilities 0.65/1. These are six-month evidence. Type 1 describes the static
adventitious scaffold; type 3 describes second-order laterals. This is not a
measured parameter set for T4 or types 4/5.

An explicit starter assumption may transfer the type-3 coefficients to orders
4/5. Record that extrapolation. The table labels insertion values as radians
despite degree-scale magnitudes; this implementation uses a degree proxy. The
table's sigma unit is also not a literal verification of the implementation's
`rad/sqrt(cm)` angular-noise convention. Existing heading search draws an
initial candidate plus a stochastically rounded number of extra candidates
proportional to `trials * sqrt(ds_cm)`; `trials=1` does not mean no selection.
These numerical conventions preserve the existing research implementation.

## Optional count-conditioned construction

`research_root_counts_by_order` supplies positive integer totals `N_1..N_m`.
It requires explicit matching constructor/model seeds, Fichtl mode, `m` in
3–5, `N_1 = inner_root_num + outer_root_num`, and explicit current-length CDFs
for orders `2..m`. Counts are conditioning inputs, not predictions.

Before constructing child order `k`, divide its requested count among the
`N_(k-1)` parents:

```
q, r = divmod(N_k, N_(k-1))
n_parent = q + 1[parent in a seeded subset of size r]
```

The subset uses a separate SHA256-keyed stream containing the topology-control
version, seed and child order. It excludes experimental arm. Parents receiving
zero children remain valid terminal roots. This balanced allocation is an
engineering assumption, not an estimate of observed parent assignments.

Use the existing `redistribute_capped_sites` rule directly for each assigned
count. On a parent of arclength `L` cm, within fractional band `[f,c]`, sites are:

```
s_j_cm = f * L + (j + 0.5) * (c - f) * L / n_parent
j = 0, ..., n_parent - 1
```

This opt-in rule bypasses legacy spacing/growth caps. It does not hide a change
in counts or length inside tropism. Daughter current lengths are independently
sampled from the explicitly supplied order-specific inverse CDFs in cm, using
the existing keyed sampler. This retains length distributions in expectation;
it does not recreate the observed joint tree or guarantee each sample mean.
Primary lengths and initial scaffold remain separately specified inputs.

Quota conditioning rejects simultaneous parent-2 branch-zone, positive
tertiary-rank or positive distal-attachment controls. The latter two remain
restricted to their qualified order-3 construction scope. Unsupported
combinations fail explicitly.

## Replay and observation support

Native construction, `graph_segments_v1` and `construction_steps_v1` support
orders through 5. Replays authenticate saved higher-order controls, counts,
parent-chain geometry and planned attachment sites. The controlled routes use
the same existing minimum-angle boundary projection and physical surface at
`z=20 cm`, with comparison depth `20-z`. Native boundary semantics remain
separately identified. `t` does not simulate elapsed months.

The search bridge requires explicit contiguous `root_orders` in both parameter
and reference scope. Orders 1–3 retain the original 13 traits and comparison
version. Order 4 adds its count and mean organ length (15 traits); order 5 adds
two more (17 traits). All represented root orders contribute to total length,
depth, spans, verticality and the three normalized 10 cm profiles. Exterior
profile support remains scored. Zero/undefined positive traits fail closed.

Higher-order contracts are separately versioned as
`architecture-population-order4/5-eps0.10-v1` and
`research-search-evaluation-order4/5-v1`. Epsilon 0.10 is a research diagnostic
normalization, not a newly adopted individual-vine biological threshold.
Measured counts and length marginals supplied to construction must be marked
as conditioned when interpreting the diagnostic. Fresh seeds assess stochastic
variability; they do not provide unseen-vine validation.

## Biomass and local parameter bundles

[Fichtl et al. (2025), supplementary S2/S4](https://pmc.ncbi.nlm.nih.gov/articles/PMC12718041/)
reports SO4/T4 population root dry mass 183.2 ± 65.0 g, digitized length
5266.6 ± 643.8 cm, and SRL 31.7 ± 8.0 cm/g (means ± SD). These do not identify an
individual vine's measured mass. A length/SRL transfer estimate must remain
labelled as conditional. A one-SD SRL sensitivity range is not a confidence
interval or biomass acceptance tolerance.

Geometric dry mass needs independently supported diameters and dry tissue
density. The 2024 text/table has an unresolved diameter/radius naming conflict;
soil bulk density cannot supply root dry tissue density. Do not fit both
density and diameter freely against one mass reference, or score length, mass
and SRL as independent observations. The architecture search objective remains
unchanged and excludes biomass until support/weights are qualified.

Empirical parameters, CDFs, reference profiles and comparison artifacts stay in
local `.runtime` bundles. Notebook execution remains disabled by default. The
current owner has deferred Claude reviews; internal synthetic tests and source
inspection do not claim completion of those independent reviews.

## Numerical qualification

Use invented fixtures to check finite geometry, a single connected acyclic
root graph, valid parent references, exact supplied counts, current-length
realization, deterministic seeds, strict input rejection, saved-control
authentication and both replay routes. Analytic order-4/5 fixtures must show
that higher-order length contributes to global statistics/profiles. Compare
inactive/order-3 outputs with preserved source to detect accidental RNG,
INITIAL identity or default changes. Source-bound receipts and executed test
counts belong to the local task report.
