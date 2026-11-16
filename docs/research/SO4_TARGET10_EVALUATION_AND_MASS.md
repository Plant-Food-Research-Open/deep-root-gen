# Versioned10% population evaluation and represented-root mass audit

The owner requested the separately versioned13trait/3profile epsilon0.10 investigation, preserving the sealed epsilon0.20 baseline. This is research representation; no biological accuracy or numerical mass target is adopted. Implement two research-only modules and synthetic tests; retain production statistics/model defaults and old protocols unchanged.

## Architecture evaluator

Names/units: soil_length_cm,mean_depth_cm,max_depth_cm,across_row_span_cm,along_row_span_cm,primary_mean_length_cm,secondary_mean_length_cm,tertiary_mean_length_cm are cm; primary_count,secondary_count,tertiary_count are population mean counts; row_across_span_ratio andverticality are dimensionless. Supply exactly these13positive finite means and3nonnegative profiles (across,along,depth) normalized per architecture before equal-architecture averaging. Ratios are per-architecture traits before averaging. Do not replace this aggregation with normalization after length pooling.

Use version architecture-population-eps0.10-v1. Freeze coordinate/operator/support and aggregation metadata, units and shared10cm lattice/bin edges. Candidate/reference population IDs and sizes differ legitimately; require comparison-support/operator compatibility, not identical source IDs. Missing bins must be explicitly zero-padded onto common declared edges by the caller; no interpolation or silent renormalization. Reject malformed/nonfinite/missing/extra criteria and incompatible metadata. Profile sum tolerance1e-8 is a numerical validation only, not an acceptance tolerance change.

For reference y and candidate x, e_i=abs(x_i-y_i)/y_i; v_axis=.5sum(abs(p-q)); return full vectors, signed residuals, every pass flag/tied worst criterion and J=max(e_i,v_axis)/.10. All individual values must pass unrounded<=.10. Retain old20% evaluation separately. No acceptance can use a favourable average hiding another failed criterion.

## Strict mass audit, diagnostic until observation qualification

Support is explicit represented_root_whole_system under the DeepRootGen root-only node/edge schema, with declared cm coordinate/diameter andg_dry/cm3 density units. Require explicit root-compartment semantics/order coverage; reject unknown support/unit/mapping. No spatial clipping, finite-voxel-prism substitution or inferred stem/crown/missing-root mass. Order0base has no incoming cylinder and is separately excluded. Existing child-invalid semantics apply: invalid child cylinders excluded; a valid child of an invalid parent remains accepted and is counted explicitly.

Validate unique IDs, one base, exact edge/parent agreement, all parents, reachability/no cycles, strict boolean invalid flags, finite geometry, positive geometric edge lengths, finite nonnegative diameters and finite positive selected density. Reject malformed excluded root cylinders too, since their excluded totals must be auditable. Stored length is not the mass length; report disagreement rather than using it. Base-only attributes do not create a cylinder.

For each root edge use L=norm(child-parent),V=pi*(d_child/2)^2*L,M=rho_selected*V. Reuse current statistics.summary_statistics._mass arithmetic after strict validation; do not change its legacy implementation. Density source explicitly selects per-node densities or a uniform override with provenance/units; no inferred/default empirical density. Generator defaults can be diagnosed only with an unqualified-assumption label.

Return per-edge acceptance/reason, selected density/provenance, length/volume/mass, accepted/excluded totals and by-order totals, zero-diameter and valid-child/invalid-parent counts, support/source hashes. Per-system identity must remain explicit. Population mass is mean(per-system mass), not summed seed masses; preserve systems and reject incompatible support/identities.

Optional mass acceptance is separate and NOT_QUALIFIED unless an evidenced versioned target/support/uncertainty and its own positive tolerance or interval are supplied. Architecture epsilon must not become mass epsilon. No new mass-related simulation parameters, density/diameter fitting or changed cylinder/frustum law in this implementation.

An explicit target cannot qualify an assumed density: if any retained system uses a generator default or other unqualified density, return NOT_QUALIFIED with no pass/fail decision and identify that cause. Evidence labels are caller declarations requiring an external provenance audit; the evaluator does not certify a publication or compartment match. Keep target evidence and density evidence independent.

Snapshot caller-owned nested comparison mappings and arrays when constructing frozen contracts, so later mutation cannot change their meaning. Reject masked and complex numerical inputs before float conversion. Source hashes must distinguish special floating values, mapping contents and mapping key types rather than allowing metadata to mimic an internal serialization marker.

## Checks before real-data use

Invented analytic cylinders, unequal diameters, geometric-versus-recorded lengths, per-node/uniform density, diameter2x=>mass4x, density2x=>mass2x, subdivision and rigid-motion conservation, invalid-child/base/support accounting, accepted+excluded conservation, malformed graphs/units, population mean-versus-sum, exact10%threshold/ties, identical/disjoint profiles, bin/support/aggregation mismatch and missing/extra criteria. Retain legacy tests; no raw observations or fitted values in public fixtures/review packets. Freeze code and qualify tests before local scoring.
