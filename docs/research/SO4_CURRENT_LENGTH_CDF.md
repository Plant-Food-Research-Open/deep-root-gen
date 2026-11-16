# Opt-in current organ length from explicit discrete CDFs

## Mechanism hypothesis and provenance

Numerical parent subdivision must not determine daughter contour length. An explicit distribution of current organ lengths can represent heterogeneity that an aggregate-summary uniform proxy may omit. This static reconstruction hypothesis does not specify growth rates, ultimate lengths, biomass or biological acceptance. Model-data selection stays local. A change in eligible branching-window length may affect counts through the existing law; record that consequence separately.

The public acquisition/model evidence is Fichtl et al.2024 (https://pmc.ncbi.nlm.nih.gov/articles/PMC11633832/). The new discrete distribution and its sampling implementation are research construction choices, not equations claimed from that paper. Any actual distribution inputs need their own provenance and units. Published between-vine variation is not a within-organ distribution.

## Frozen construction rule before implementation

Add research_current_length_cdfs_cm: optional mapping of orders2/3 to explicit lengths_cm and cumulative_probabilities arrays. Default None retains legacy behavior. Primaries remain legacy. Require a nonempty mapping, matching nonempty arrays, finite positive strictly increasing support in cm, and finite positive strictly increasing cumulative probabilities ending exactly at1. No implicit fitting, interpolation or extrapolation.

For selected order o, select the first support value with CDF strictly greater than a keyed uniform u in[0,1), using searchsorted(side=right). Let independent keyed positive weights w_j=1-U_j (sorted descending). Construct ell_j=L_o*w_j/sum(w). Current total length has no legacy order reduction and receives no parent incoming-edge increment. Preserve total contour length through attachment subdivision. Unselected orders retain their old path; diameter coupling and direction/branch rules are unchanged.

Preserve the existing shared-RNG scalar length and segment-weight calls exactly once, discarding their values only for selected orders. Key new SHA256-derived NumPy streams by a fixed version, authoritative seed, order, biological next-organ ID and purpose (current_length versus segment_weights). CDF identity is provenance, not part of the key, retaining common quantiles between CDF variants. Capture the expected next organ ID before sampling and verify allocation agrees. Node IDs are prohibited in keys. Identity is conditional on fixed biological organ structure, not arbitrary topology changes. Require explicit matching simulator/input seeds whenever this feature is active.

Expose stream/CDF identity, quantile/index, sampled current length and pre/post-subdivision totals for diagnostics. No new RNG or changed numerical tolerance is hidden in validation.

## Qualification and separate experiment

Use invented synthetic distributions only in public tests. Verify boundary/singleton selection, malformed schemas, positive normalized weights, stable key independent of parent node mesh, unchanged shared-RNG consumption, selected/unselected orders, exact-seed repeatability and legacy goldens. Extend the coarse/fine order2 parent fixture to an order3 daughter: same physical parent/attachment and matched branch randomness must give identical sampled segment vectors, daughter coordinates/diameters, realised contour length and instantiated daughter counts. Enforce length accounting at1e-8cm and retained edge/attachment tolerances. Verify finite single-root connected acyclic graphs.

No measured values or fitted distribution arrays belong in public artifacts or review packets. Freeze code/tests and qualify them before local trials. Evaluate this as a separately named construction experiment after the buried-origin experiment, with all other current controls fixed. Keep the accepted13trait/3profile definitions and thresholds unchanged.
