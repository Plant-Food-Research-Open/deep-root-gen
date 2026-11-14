# Research primary-inclination construction hypothesis

Recorded before implementation. This is a separate scaffold experiment after
the completed fixed-scaffold direction experiment. Legacy defaults and the
original baseline remain unchanged.

## Limitation and evidence

`position_primary_roots()` samples hard-coded pitch ranges before optional yaw
and origin placement. There is no explicit research control for primary
inclination. A primary tangent determines both lateral emergence depth and the
plane of subsequent insertion. Altering continuation directions cannot move
the fixed parent attachments. The public acquisition protocol distinguishes
old adventitious/type-1 roots and basal/soil landmarks; it supports inspecting
their geometry, but supplies no coefficient for the rule below.
[Fichtl et al., Methods](https://pmc.ncbi.nlm.nih.gov/articles/PMC11633832/).

Local saved-geometry sensitivity and evidence audits remain separate and local.
This public hypothesis does not publish their values. It does not establish
that every directional parameterization is incapable of matching observations.

## One proposed opt-in rule

Add `research_primary_inclination_bias`, dimensionless, default `None`.
`None` or zero is an exact geometry/RNG no-op. Positive values are an explicit
research assumption, not a measured Fichtl parameter. Initially qualify values
in [0,1]; reject nonfinite or out-of-range input.

After legacy primary positioning and optional primary yaw, before origin
translation, let each basal-to-apex primary chord have unit direction `h` and
let `g=(0,0,-1)` in model centimetre coordinates. Define:

```text
h_target = (h + b*g) / norm(h + b*g)
inclination_down = asin(-h_z)
```

Plan a proper rotation taking `h` to `h_target`, then rigidly rotate the whole
primary subtree about the unchanged base. Use the same rotation for all its
descendants. Compute and validate all plans before mutating geometry. Reject
a zero chord or a degenerate zero target vector; do not silently clip angles.
Use deterministic handling of parallel/antiparallel directions. No new random
draws, root edges, segments, counts, lengths, diameter or density changes.

This preserves horizontal chord azimuth when it is defined and increases its
downward inclination. It changes attachment positions deliberately. It is a
construction operation in `model/root.py`, not hidden branching or length
logic in a tropism sampler. Both native construction and controlled INITIAL
construction must use the same opt-in stage; native validation must fail closed
if it later invalidates or reorients the declared scaffold. Positive keyed
research runs retain one matching constructor/configuration seed.

## Required synthetic checks

An analytic straight primary with a daughter verifies the target direction,
unchanged base and azimuth, rigid distances, attachment coincidence, all edge
lengths and unchanged node/edge identities and dimensions. A curved primary
verifies rigid rather than per-segment bending. Test several primaries,
deterministic seeds, parallel/antiparallel and degenerate plans, invalid bounds,
atomic rejection before mutation, disabled/zero legacy equivalence and RNG
state preservation. Verify proper rotation orthogonality/determinant and finite
rooted connected graph geometry with the existing tolerances unchanged.

Record diagnostics: original/target/realized chord, inclination, azimuth where
defined, coefficient, rotation, base and maximum edge-length residual. Bind
new construction runs to exact source, settings, shared seeds, INITIAL graphs
and physical soil rule. Requalify tests before any empirical experiment.
