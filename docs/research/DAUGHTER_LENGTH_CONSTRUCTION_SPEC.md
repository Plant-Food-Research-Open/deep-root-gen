# Subdivision-independent daughter current-length rule: specification only

No new length mode or origin treatment is implemented here. The accompanying
`tests/test_subdivision_characterization.py` characterizes existing legacy
behavior using newly invented geometry, not observations. Saved observation
frames, references, completed trials and default legacy behavior stay unchanged.
A separate saved-graph orientation diagnosis precedes any later origin trial.
User permission to explore a buried initial point does not itself specify a
placement rule, evidence, implementation or successful trial.

## Existing coupling and actual-graph characterization

`RootOrgan.init_lengths` currently draws a nominal organ length from its configured
interval after the existing order reduction, draws and normalizes segment weights,
and returns segment lengths. `construct_root_from_parent` then adds

```text
incoming_parent_segment_length * (0.1 ** parent_order)
```

to **each** initially requested daughter segment. Thus its added organ length is
`requested_segments * incoming_parent_segment_length * (0.1 ** parent_order)`.
The incoming segment is a numerical subdivision element, not a stable biological
length. Moving or refining parent attachment cuts can change daughter totals
without changing the physical parent curve, diameter or attachment coordinate.
Later daughter subdivision conserves that already modified contour length.

The test builds actual connected orders 1–4 with the same bent order-2 curve of
10 cm, the same physical attachment at arc 5 cm, the same parent diameter,
tissue density and order, identical daughter RNG seed 42 and identical nominal
parameters. Coarse and refined incoming parent segments are respectively 5 cm
and 1 cm. With ten requested order-3 daughter segments the anticipated legacy
difference is `10*(5-1)*0.1**2 = 0.4 cm`.

The test observes the actual nominal and incremented arrays while delegating to
unchanged methods, checks post-subdivision daughter contour lengths, instantiates
all available order-4 daughters, and prints actual branch counts and their
difference. It does not require a branch-count difference: the cap or stochastic
spacing may yield equal counts despite different contour lengths. Its rooted
finite graphs must satisfy per-edge rel1e-5/abs1e-6 geometry and total accounting
within 1e-8 cm. This is a legacy compatibility characterization, not a fix or
biological validation.

## Proposed future opt-in rule

For a daughter organ of order o, draw one **current realised organ length**
`L_o ~ F_o`, in cm. Given positive finite subdivision weights w_j, construct

```text
ell_j = L_o * w_j / sum(w)
```

and preserve their sum through any subsequent attachment cuts. In this proposed
mode there is **no parent-subsegment length increment and no automatic legacy
order-reduction multiplier**. Order dependence belongs in the explicitly supplied
`F_o`, not in a numerical parent's incoming edge. Current length is distinct from
maximum attainable length and from elongation rate; none can substitute for
another without a separately justified developmental model.

No means, coefficients or observations are supplied here. Before implementation,
the owner must specify each order's current-length distribution and provenance.
Permissible future interfaces include explicit order-specific means in cm and
CVs (dimensionless) together with a named distribution family, or an explicit
CDF/empirical distribution with units and a sampling/interpolation rule. A mean
and CV alone do not define a distribution. Its support, truncation, treatment of
zero lengths and stochastic stream identity must also be declared.

Published between-vine variation must not be relabelled as within-organ SD or
CV. A distribution of vine summaries does not identify the distribution among
individual organs. Any use of published aggregate estimates as a proxy must be
separately justified, named and uncertainty-qualified; it is not an inferred
organ-level law. This specification supplies no actual-data values and makes no
claim that the required organ-level evidence is already available.

Diameter coupling, root-tissue density and biomass calibration are outside this
rule. Existing diameter behavior is not corrected or adopted by this proposal.
No origin translation, burial, polar-angle change, crown fitting, lateral-tropism
change, observed-data transform or count-law replacement is bundled with it.
The default remains the existing legacy length construction. A later feature
must have an explicit opt-in mode and preserve legacy regression outputs.

## Required invariants before any new-rule trial

Hold the physical parent curve, physical attachment arc and matching coordinate,
parent order/diameter/density, nominal distribution specification and daughter
random stream fixed. Refine or coarsen only the parent's representation while
retaining every physical corner. Then the proposed rule must yield:

- Identical sampled daughter current length and requested segment-length weights.
- Matching attachment points at rel1e-5/abs1e-6 and conserved contour length to
  1e-8 cm, regardless of the incoming parent edge length or parent mesh count.
- Matching daughter branch counts for the same fixed physical configuration,
  branching controls and matching branching randomness; no numerical parent-mesh
  change may become an unacknowledged count intervention.
- Finite connected rooted graphs and retained biological organ identities, with
  valid parent references even when numerical node/edge counts change.

When the daughter mesh is also refined, retain its sampled physical contour and
matching points; subdivision may divide that contour but may not redraw its
organ length or branch law. Node counts need not agree across meshes. Repeated
construction must use stable organ/physical-attachment randomness or explicitly
hold those streams equal: a shared sequential RNG that shifts after numerical
mesh changes cannot establish this invariance merely by using the same global
seed. The new rule's sampling/stream contract needs its own tests.

The present characterization verifies the legacy defect only. It does not assert
that these future-rule invariants currently pass or that a new observation
comparison, origin feature or length implementation has been authorized by this
specification alone.
