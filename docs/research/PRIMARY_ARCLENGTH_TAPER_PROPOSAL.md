# Proposed physical-arclength primary taper

Public design decision memo, 15 November 2026. **Proposed, not implemented or
adopted.** This memo uses inspected source and invented analytic examples only.
It authorizes no construction, parameter fitting, new biological threshold,
density adjustment or change to the frozen area-mean observation utilities.

## Source finding and the decision

The current explicit design defines `diameter_base_cm` and `diameter_apex_cm`
as the diameters of the first and last incoming **construction cylinders**.
`primary_dimensions` normalizes sampled segment weights to the requested total
length, then assigns `np.linspace(base, apex, segment_count)` independently of
those lengths. See [the dimensions helper](../../deeprootgen/utils/primary_design.py),
[the entry schema](../../deeprootgen/data_model/simulation_data_models.py) and
[`test_linear_rank_taper_and_constant_taper_child_cylinder_convention`](../../tests/test_primary_design.py).

`RootOrgan._prepare_branch_nodes` then holds each original cylinder diameter
constant over all its branch-cut fragments. Its fragment midpoints identify
the original cylinder; they do **not** evaluate a physical taper. This preserves
the original piecewise-cylinder volume when branch nodes are added. See
[branch subdivision and daughter construction](../../deeprootgen/model/root.py).

Unequal construction lengths therefore make a rank midpoint different from the
physical midpoint. A long final segment receives the full apex cylinder
diameter over its entire length. This is current documented behavior, rather
than a defect in cylinder-volume arithmetic.

Recommend a separate opt-in, versioned policy: **a piecewise-linear point
diameter law in physical arclength, exported as volume-equivalent constant
incoming cylinders**. Its base, midpoint and apex anchors describe point
diameters of the proposed continuous material law. Exported cylinder diameters
describe interval means of diameter squared. These are distinct quantities.
Both need explicit diagnostic names; an interval cylinder must not be reported
as a measured point diameter.

If the owner instead requires the first/last exported cylinders and the
cylinder containing the midpoint to equal three exact supplied values, that is
a different piecewise-cylinder policy. It cannot generally also preserve the
analytic volume of the continuous law on arbitrary unequal intervals. Do not
silently claim both contracts.

## Proposed opt-in contract

An illustrative entry extension is
`taper_mode="arclength_piecewise_linear_volume_equivalent_v1"` plus explicit
`diameter_midpoint_cm`. Under that named mode only, the existing base/apex
inputs would explicitly become point anchors at `s=0` and `s=L`. The omitted
mode retains the existing rank/cylinder interpretation and exact behavior.
Names are a proposal; changing this interpretation requires an explicit owner
decision before implementation.

Require finite nonboolean `L>0` and positive diameters
`d_base >= d_mid >= d_apex > 0`. Supply the midpoint; do not infer it from
observations, labels or category. If the declared scientific assumption is a
single linear taper, its midpoint must equal `(d_base+d_apex)/2`; three
independent anchors instead require the two linear pieces below. Keep cm for
arclength/diameter and the existing explicitly supplied dry density in g/cm3.

The reference length is the complete current primary contour length, not chord
length, depth, node rank or local fragment length. Direction changes must not
change this material coordinate. Record original contour stations, anchor
values, policy version, exported intervals and cylinder diameters. Do not add
an implicit diameter floor, fitted exponent, inferred density or automatic
daughter-diameter clamp.

## Point law and exact cylinder representation

Let `s` run from zero to `L`, with midpoint `m=L/2`:

```text
d(s) = d_base + (d_mid - d_base) * s/m                  0 <= s <= m
d(s) = d_mid  + (d_apex - d_mid) * (s-m)/(L-m)          m <= s <= L
```

Thus `d(0)=d_base`, `d(L/2)=d_mid`, and `d(L)=d_apex` by definition. These
equalities apply to the point law, not automatically to a child-node diameter.

For an interval `[a,b]` entirely within one linear piece, write `u=d(a)` and
`v=d(b)`. Its integrated squared diameter and exported cylinder diameter are

```text
I(a,b) = integral_a^b d(s)^2 ds = (b-a)*(u^2 + u*v + v^2)/3
D_equiv(a,b) = sqrt(I(a,b)/(b-a))
V_interval = pi/4 * (b-a) * D_equiv(a,b)^2
M_interval = rho_dry * V_interval
```

For an interval crossing `m`, add `I(a,m)+I(m,b)` before dividing by its full
length. The whole-primary reference is

```text
V_primary = pi*L/24 * (
    d_base^2 + d_base*d_mid + 2*d_mid^2 + d_mid*d_apex + d_apex^2
)
M_primary = rho_dry * V_primary
```

The node/edge schema remains constant-child-diameter cylinders; the base node
creates no incoming cylinder. No frustum interpretation is introduced into
existing audit or observation code. Adding exact interval integrals before
taking a square root avoids cancellation in differences of cubic antiderivatives.
Reject unrepresentable/nonfinite derived lengths, diameters, volumes or mass.

Sampling the point diameter at the interval midpoint is another approximation,
not this rule. For a linear piece of slope `k` and length `h`, it underestimates
`I` by `k^2*h^3/12`, hence cylinder volume by `pi*k^2*h^3/48`. Rank interpolation
is not a substitute for this quadrature correction.

## Material cuts, fine-root support and daughters

For the proposed policy to represent diameter-defined fine support consistently,
include the physical midpoint when its slope changes, and every crossing of the
declared fine-diameter cutoff, as material stations. For a monotone linear piece `[a,b]`, a cutoff
`d_cut_mm/10` strictly between its endpoint diameters occurs at

```text
s_cross = a + (b-a)*(d(a)-d_cut)/(d(a)-d(b))
```

Use the union of original corners, attachment sites and these material
stations; retain original nodes and add only necessary degree-two cut nodes.
Assign `D_equiv` on each final incoming interval. This guarantees that no
nonconstant interval straddles the fine threshold, so the represented fine
length and volume agree with the continuous material-law integrals. Equality
at the cutoff follows the existing inclusive diameter-class convention.
The caller supplies that cutoff; 2.5 mm is an illustrative existing default,
not a new biological decision.

Recomputing equivalent diameters after a cut conserves primary volume because
the interval integrals add. It deliberately replaces the old rule that copies
one original diameter onto every fragment. Do not recompute an unrelated taper
by final node rank. Keep `root_type` and order labels unchanged: order-4/5 mass
allocation, string root labels and diameter-defined fine support remain separate.

There is a smaller **volume-only** variant: calculate equivalent diameters on
original construction intervals, then keep the existing inherited-fragment
rule. This preserves primary volume and avoids adding material cut nodes, but
its diameter-defined fine length can depend strongly on the source intervals.
It must report threshold-straddling intervals and cannot claim the fine-support
guarantee above. It is not the recommended route if fine RLD is being compared.

The existing daughter law also matters. In `construct_root_from_parent`, each
initially drawn daughter diameter receives

```text
D_daughter,j = D_draw,j + 0.1^(parent_order) * D_attachment_cylinder
```

Consequently a primary attachment-cylinder change `delta_D` adds `0.1*delta_D`
to its secondary diameters even when topology, lengths and innovations are held
fixed. Mass changes quadratically in those resulting diameters. Do not claim
whole-system mass invariance from primary integral conservation.

With the existing inheritance rule, further subdivision immediately upstream
of an attachment can change its incoming equivalent cylinder, and therefore
daughter dimensions. Preserve and report that coupling. Replacing it with
`d(s_attachment)` would remove this particular material-mesh dependence, but
would be a separate daughter-inheritance decision, not an unreported correction.

Material nodes can also change native Fichtl geometry because its direction
updates depend on graph subdivision. Preserve the same original dimensions,
attachment quotas and innovation schedule where possible, and test the exact
chosen route. Extra nodes do not imply unchanged realized geometry. Avoid
introducing a new discretization or replay route merely to mask this coupling.

## Invented analytic example

Take `L=10 cm`, point anchors `0.8, 0.4, 0.1 cm`, and original lengths
`[1,2,7] cm`. Current rank taper gives `[0.8,0.45,0.1] cm`; the entire final
7 cm is an apex cylinder, including physical midpoint `s=5`. Its squared-diameter
integral is `1.115 cm3` and its cylinder volume is `pi*1.115/4 cm3`.

The proposed point law instead has
`integral_0^10 d(s)^2 ds = 133/60 cm3` and
`V_primary = 133*pi/240 cm3`. Source-interval equivalent diameters are
approximately `[0.760351,0.641665,0.341230] cm`. The final source cylinder does
not equal either the midpoint anchor or the apex point diameter.

At a 2.5 mm cutoff the physical crossing is `s=7.5 cm`. The continuous fine
length is `2.5 cm`, and its squared-diameter integral is `13/160 cm3`, giving
fine volume `13*pi/640 cm3`. Current rank cylinders would label 7 cm fine; the
volume-only equivalent source cylinders would label zero fine. Adding the
midpoint and cutoff stations, then recomputing interval equivalents, represents
the proposed 2.5 cm fine support exactly. These are invented arithmetic
contrasts, not predictions, observations or recommended biological diameters.

## Proposed analytic acceptance tests before any native trial

1. **Anchors and units:** verify all three point values at physical arclengths;
   reject booleans, missing midpoint, nonfinite/nonpositive values, reversed
   taper anchors, nonpositive lengths and unknown mode. Omitted mode must retain
   current serialization, geometry, diameters, diagnostics and RNG exactly.
2. **Constant taper:** all anchors equal `d`; every exported diameter equals
   `d`, volume equals `pi*d^2*L/4`, and no unnecessary material station is added.
3. **Known unequal intervals:** reproduce the invented integrals above, rather
   than accepting an unweighted rank average or a last-cylinder apex value as
   a physical-midpoint check.
4. **Subdivision:** insert arbitrary cuts without changing the point law;
   reconcile sum of cylinder volumes with the analytic integral. With cutoff
   stations present, also reconcile fine/coarse lengths, volumes and dry masses.
   Preserve the no-incoming-base convention and finite positive interval lengths.
5. **Daughter coupling:** with frozen draws/lengths, verify exactly the existing
   `0.1^(parent_order)*delta_D` diameter contribution; independently recompute
   daughter mass. Check attachment inversions without silently clamping them.
6. **Boundary cases:** cover midpoint/cutoff coinciding with an existing corner
   or attachment, a constant region exactly at cutoff, nearly coincident cuts,
   one original construction interval and extreme finite inputs. A requirement
   of one exported cylinder is incompatible with three unequal point anchors;
   reject that combination or explicitly allow material subdivision.
7. **Isolation and route:** no density changes, allocation rescaling, length
   changes or raw-data access. A deterministic table-level check is distinct
   from a later synthetic constructor check, which is distinct from biology.
   Any native discretization effect needs its own reported comparison.

The single construction decision to authorize would be the named physical
arclength/material policy, including its point-versus-cylinder contract and
cutoff treatment. Daughter inheritance and native discretization couplings
remain explicit limits. No implementation or native test was run for this memo.
