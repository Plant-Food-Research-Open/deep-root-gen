# Lessons for future AI coding

18 November 2026. These lessons come from the native/SO4/cohort integration and
its subsequent public-source review. They describe concrete risks and review
methods, not a claim that the proposed unified engine is implemented. Use the
[coding guide](AI_CODING_GUIDE.md) for the working procedure and change boundaries.

## 1. A shared entrypoint does not establish a shared engine

`RootSystemSimulation.run()` currently dispatches complete internal workers.
A common deque and native-looking organ objects also leave distinct construction
schedules and emitters intact. Shared ownership must extend to state, phase
ordering, materialization, graph writing and results.

Caller tracing also finds the archived `graph_segments_v1` search experiment
constructing a fresh INITIAL outside `run()`. Inspect all supported callers and
label archived paths explicitly rather than assume the entrypoint owns every
currently callable experiment. See [search evaluation](../deeprootgen/research/search_evaluation.py).

**Apply:** trace actual calls, not function names. New option tests must forbid
complete bundle runners; final migration also brings old inputs into the common
executor. See [current run implementation](../deeprootgen/model/root.py) and the
[revision plan](research/NATIVE_FEATURE_COMPOSITION_REVIEW_AND_PLAN.md).

## 2. Accepted JSON can contain ignored requests

The current CLI falls back to the legacy model without `schema_version`.
An unrecognized `features` block can disappear during that model's parsing.
Successful parsing therefore does not prove an option affected execution.

**Apply:** the planned common parser must recognize reserved keys before legacy
fallback, reject unknown and duplicate raw JSON keys, and expose effective
settings. Test each switch through its consuming stage. Disabled settings can
be retained intentionally, with no draw/output effect; silently dropped active
settings are a defect. See [CLI parsing](../deeprootgen/cli.py) and
[execution schema](../deeprootgen/data_model/execution.py). These parser changes
remain requirements of the proposed revision.

## 3. “Validation” can change the simulation

Native `RootOrgan.validate()` can consume RNG, rotate subtrees and mark roots
invalid. Moving it into a per-axis loop or replacing it with a pure assertion
changes the historical numerical contract. Fichtl also has a specific placement
of primary validation and post-direction lateral validation.

**Apply:** distinguish compatibility correction from final integrity checking.
Preserve old correction/draw order; make final checks pure. Reject an unsupported
combination where a later legacy ancestor repair would rotate an OU descendant
and invalidate its world-frame boundary/drift rule. See
[native validation](../deeprootgen/model/root.py) and
[pure result checks](../deeprootgen/model/integrity.py).

## 4. Graph fragments are not biological construction intervals

Native daughter dimensions inherit contributions from their original parent
segment. Attachment or taper cuts can split that segment into smaller graph
fragments. Reading the new fragment's length during sampling changes daughters
even if the intended biological model is unchanged. Node count also increases
when a curved axis gains geometric detail, without increasing root count.

**Apply:** retain original birth interval/material context and stable biological
IDs. Keep all physical curve corners when adding export cuts. Compare biological
counts, contour lengths and material integrals separately from node counts.
See `construct_root_from_parent` in [root.py](../deeprootgen/model/root.py) and
[interval geometry](../deeprootgen/model/interval_geometry.py).

## 5. Check dependencies before inventing a second scheduler

The first composition plan assumed cohort daughters needed a realized parent
curve before dimensions could be sampled. The source shows that sizing needs
parent point diameter, available from its sampled arclength material profile.
Only insertion heading needs the realized tangent. Purpose-keyed cohort streams
separate these operations.

**Apply:** list the actual inputs to each calculation. Prepare one biological/
material forest before world geometry; retain native draw ordering during that
extraction. This is the revised design, whose exact parity still needs runtime
proof. See [`_sample_organ` and daughter insertion](../deeprootgen/model/cohort.py).

## 6. Similar parameter names can hide different mathematics

Native primary rank taper specifies cylinder diameters. Cohort taper specifies
point diameters along arclength and integrates volume into equivalent cylinders.
The cohort `midpoint_fraction` controls the diameter at fixed `L/2`:
`d_mid = d_tip + fraction * (d_base - d_tip)`; it is not a midpoint position.

Cohort maturity scales length and basal diameter. The tip draw is unscaled and
then limited to the scaled/capped base. Scaling every cylinder or tip would be a
different model.

**Apply:** use explicit names, units and targets. The proposed canonical name is
`midpoint_diameter_fraction`, with `diameter_target="base_anchor"` for that
maturity law. Preserve old aliases in input adapters. Test analytic volume,
tip constraints and the declared scaling sequence. See
[native primary design](../deeprootgen/utils/primary_design.py),
[cohort material primitives](../deeprootgen/model/cohort_geometry.py) and
[cohort sampling](../deeprootgen/model/cohort.py).

## 7. Shared output columns do not guarantee shared classification

Native lateral organs use mean cylinder diameter for an organ-wide root label;
native primaries are labelled structural. Cohort emission classifies individual
intervals using equivalent diameter and its threshold convention.

**Apply:** centralize classification ownership while retaining an explicit law.
Do not silently apply one segment cutoff everywhere merely because both outputs
have a `root_type` column. Preserve strings and old semantics in compatibility
tests, and inspect consumers before changing scientific classification. See
[native construction](../deeprootgen/model/root.py) and
[cohort emission](../deeprootgen/model/cohort.py).

## 8. Shared random numbers or helpers do not make direction laws equivalent

Native Fichtl, controlled construction-step realization and cohort OU integration
have different first-step, stationing, boundary and frame contracts. Fichtl sigma
is rad/sqrt(cm); OU stationary curvature SD is rad/cm. Zero OU noise does not
reproduce a kinked native curve.

**Apply:** version numerical laws and preserve units/namespaces. Key new feature
streams by stable biological identity and purpose, never exported node IDs or
Python `hash()`. Test disabled behavior against native parity; test zero-noise
enabled behavior against its own analytic limit. See
[tropism](../deeprootgen/utils/tropism.py),
[construction intervals](../deeprootgen/model/interval_geometry.py) and
[OU integration](../deeprootgen/model/cohort_geometry.py).

## 9. Feature independence still has real dependencies

Two controls must not independently own the same order's length law. A parent
diameter cap satisfied at an original attachment can fail after the attachment
moves to a thinner parent location. Probability scaling cannot silently thin
supplied exact counts. Origin layout does not inherently require maturity.

**Apply:** resolve one active law per operation/order; retain native fallbacks
elsewhere. Reject unsupported active interactions before construction and state
the dependency precisely. Do not silently disable a switch, resample dimensions
or create a whole alternate execution path. See the
[feature and migration contracts](research/NATIVE_FEATURE_COMPOSITION_REVIEW_AND_PLAN.md).

## 10. Root support and observation support must be explicit

A full crown support graph contains nonmaterial connectors. A root-only
projection may use primary-tree `plant_id` values to satisfy a one-base observer;
those trees are not independent vines. Equivalent segment diameter also differs
from measured basal or mid-axis point diameter.

**Apply:** retain the tree-to-vine map, coordinate frame, units and material
definition. Keep crown and any unrepresented mass separate from root segments.
Match core/voxel/support geometry before comparing data; a whole-system statistic
is not automatically a sampled-density prediction. See
[result views](../deeprootgen/model/execution.py),
[core observation](../deeprootgen/research/core_observation.py) and
[observation frame contract](research/OBSERVATION_FRAME_CONTRACT.md).

## 11. Strong evidence answers a specific claim

Frozen-reference parity proves preservation for those configurations and source
bytes. It does not prove that options compose independently. An algorithm test,
healthy UI or biomass match does not establish unseen-vine accuracy. Different
SO4 and Calvin objectives/supports cannot establish a general performance ranking.

**Apply:** pair preservation fixtures with actual native-plus-feature hybrids,
dormant-setting invariance, analytic checks and caller parity. Record exact
commands, source/config/environment identities and failures. Preserve independent
expected results; do not regenerate them from the candidate under test. Keep
algorithm correctness, reproducibility, fit and biological validation separate.
See [native parity tests](../tests/test_native_execution.py),
[integration evidence](research/NATIVE_EXECUTION_INTEGRATION_REPORT.md) and
[active research status](research/ACTIVE_CALVIN_RESEARCH.md).

## 12. Historical documentation and review requests are not current evidence

The working tree can contain important uncommitted files absent from HEAD.
Older setup documents can correctly describe a past missing environment while
a later one exists. Historical test totals and proposed commands do not show
that today's code ran. The original scaffold-only check was a dummy, not model
coverage; that file is absent from this reviewed checkout.

Similarly, requesting a specific external reviewer does not establish that it
returned a review. Authentication, network or credit failures remain failures,
not silent approvals or permission to buy credits.

**Apply:** inspect current status/source and exact receipts, preserve unrelated
changes, and label historical versus newly executed evidence. Record actual
review findings/model identity or the returned limitation. Keep empirical data
out of public review packets. See [RUNNING.md](../RUNNING.md),
[historical development evidence](DEVELOPMENT.md),
[revision review status](research/NATIVE_FEATURE_COMPOSITION_REVIEW_AND_PLAN.md)
and [repository data boundaries](../AGENTS.md).

## Maintaining these lessons

When a lesson changes, record the new source evidence and its date. Mark a defect
fixed only after the relevant behavior is verified; keep the general lesson and
link to its regression check. Do not turn temporary environment failures or old
model availability into permanent rules. Prefer updating these two documents
and the owning design contract over creating another competing guidance file.
