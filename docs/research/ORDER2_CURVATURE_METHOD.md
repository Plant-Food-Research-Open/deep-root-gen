# Optional order-2 physical curvature: mechanism decision

Public-source decision memo, 15 November 2026. Inspected working-tree source
based on commit `d5918d8bd182e351817f374426687cb546eeaa10`; the checkout contains
pre-existing research changes. This memo uses no measured inputs or private
comparison outputs. It specifies a prospective numerical construction, not a
biologically estimated curvature law or a completed validation.

## First isolated construction

Use an opt-in physical maximum step of 2 cm, retain the configured sigma, and
retain the insertion-angle draw. Apply that insertion heading to the first
physical step; the remaining physical steps may turn, including those inside
the original first construction interval. Keeping that entire original
interval straight would retain its long straight span. The 2 cm value is an
engineering resolution trial, not a biological length scale. Change sigma in
a separate comparison only if this first construction remains inadequate.

The current `construction_step_replay.py` searches once per retained original
construction interval and linearly interpolates graph cuts. More cuts alone
cannot change its geometry. `utils/current_length.py` sorts normalized random
segment weights descending, so the first original interval is longest.
`so4_controlled.fichtl_proposal` draws angles with standard deviation
`sigma * sqrt(ds)` and chooses among
`1 + stochastic_round(trials * sqrt(ds))` candidates. Sigma has units
rad/sqrt(cm). Independent smaller-step proposals have the intended
unselected angular second-moment scaling, but candidate selection, objective
draws and surface intervention frequency also change with resolution. This
route must have a separate identity; it is neither exact native Fichtl replay
nor a demonstrated resolution-invariant stochastic process.

Every physical segment must be a real exported chord of its stated length.
Merge physical integration knots with existing attachment and diameter
breakpoints by arc position; cuts inside a physical chord interpolate it
without extra searches. Preserve each original diameter interval's allocated
length, hence each organ's length and `sum(diameter**2 * length)`. Preserving
only total length and the diameter list is insufficient. Retain biological
organ counts and parent-organ relationships; geometric degree-2 node counts
may increase. Higher-order daughters need their original attachment arc and
the local realised parent tangent. Record their consequent geometry change.

## Correlated-curvature fallback, only if diagnostics require it

Independent angular increments can retain a mixture of nearly straight spans
and isolated large turns. A candidate alternative is a transported, isotropic
Ornstein–Uhlenbeck (OU) curvature process along arc length. Its parameters are
an explicit correlation length `ell > 0` in cm and stationary per-component
curvature standard deviation `q >= 0` in rad/cm. Neither is biologically
identified by this memo. Let `t,e1,e2` be an orthonormal moving frame, and let
`c=(c1,c2)` be curvature components in its normal plane. Define

```text
dc = -(c/ell) ds + sqrt(2*q^2/ell) dW_s
a = exp(-h/ell)
c_next = a*c + eta
Var(eta_i) = q^2*(1-a^2)
Cov(c_i(s),c_i(s+r)) = q^2*exp(-abs(r)/ell)   [stationary]
```

`W_s` has increments of variance `ds`; the diffusion coefficient has units
rad/cm^(3/2). Draw `c0 ~ Normal(0,q^2 I)` for stationary curvature, independently
of the preserved insertion heading. A zero start is an alternative transient
assumption and must be named. Keep the original insertion heading on the first
physical chord and advance the latent process consistently across that chord.

An exact joint update for curvature and its integral over one interval avoids
incorrect independent curvature draws. For each component, with independent
standard normals `z1,z2`, use

```text
A = q^2*(1-a^2)
B = q^2*ell*(1-a)^2
C = q^2*(2*ell*h - 3*ell^2 + 4*ell^2*a - ell^2*a^2)
eta = sqrt(A)*z1
J = ell*(1-a)*c + (B/sqrt(A))*z1 + sqrt(C-B^2/A)*z2
c_next = a*c + eta
```

Here `J` is the integrated curvature in radians. Handle `q=0` explicitly;
evaluate small `h/ell` expressions with `expm1`/series to avoid cancellation.
The formulas are exact for the scalar OU process in transported coordinates;
the subsequent three-dimensional geometric integration remains numerical.
Do not call the whole spatial construction exact.

Let `v=J1*e1+J2*e2`, `theta=norm(v)`. The spherical exponential gives
`t_proposed=cos(theta)*t + sin(theta)*v/theta`, with the zero-angle limit `t`.
After the surface operator, transport the entire frame with the minimal
rotation from `t` to the accepted heading. Carry `c_next` components in that
transported frame; do not recreate the normal basis from a global axis at
each step. Recreating it introduces artificial discontinuities. Antiparallel
transport needs an explicit deterministic convention and a diagnostic.
Advance by `h*t_accepted` so every realised polyline chord retains length h.
Large integrated turns require resolution refinement; a silent angle cap
would define another process and bias its statistics.

For stationary curvature, each component has
`Var(J_i)=2*q^2*(ell*h-ell^2*(1-exp(-h/ell)))`.
At short distances total angular variance is approximately `2*q^2*h^2`;
at long distances it is approximately `4*q^2*ell*h`. Thus
`q=sigma/(2*sqrt(ell))` matches the old **unselected, small-angle, long-distance**
total angular variance. This is a transparent optional initialization, not
equivalence after search, spherical wrapping, drift or soil constraints.

## Directional preference and soil boundary

OU curvature replaces independent turning; it does not by itself preserve
the Fichtl candidate-selection objective. Reusing that search at every tiny
step changes both the OU law and the selection frequency. Keep any such
variant explicitly separate. Prefer a declared drift per unit length if a
correlated process is selected. For example a tangent-plane drift can be
written `g=lambda_d*P_t(-ez)-lambda_h*t_z*P_t(ez)`, where
`P_t=I-t*t.T`, `ez` points upward, and the lambdas have units 1/cm. Add `h*g`
to the tangent-plane angle increment. This equation defines possible downward
and horizontal tendencies; it supplies no coefficient values. Existing
trial counts or downward probabilities cannot be renamed as these lambdas.
Freeze the chosen law and coefficient interpretation before comparing it.

Apply the existing minimum-angle surface projection after the proposal at
each physical step. Record proposal/accepted headings, intervention arc,
angle, and location. Transport the latent frame through the accepted change;
retaining latent curvature can repeatedly push into the surface, so report
that behavior. Resetting or reflecting curvature would be a separate boundary
law. Soil projection itself creates sharp turns and can produce long planar
spans; diagnose interior and boundary-affected curvature separately.

## Required numerical evidence

Use public invented fixtures to check lengths, diameter-squared-length,
biological counts, attachment arcs, finite geometry, soil containment,
deterministic seeds, and unchanged legacy output. Test exact graph-cut
invariance: adding attachment-only cuts must not create new physical proposals
or change existing physical paths. Include the first-step insertion convention.

Compare physical caps 2, 1 and 0.5 cm with fixed model coefficients. Compare
turning over fixed physical arc windows, not raw adjacent-node angles, which
necessarily shrink with smaller steps. Include distributions of near-zero
turns, upper-tail turns, direction autocorrelation, path/chord ratio and soil
interventions; boundary and interior samples are distinct. Match windows by
physical support and report insufficiently long organs rather than inventing
zero turns. An apparent change in node-angle statistics alone is not evidence
of improved root curvature.

Same seed plus a new step index does not couple stochastic paths across
resolutions. Use coupled OU integral bridges or a recorded fine reference
noise path if claiming pathwise convergence; otherwise report distributional
resolution sensitivity across seeds. Analytic OU covariance/integral tests
check the process separately from geometric convergence and measured-data
agreement. No universal numerical tolerance or biological curvature target is
asserted here. The owner retains local empirical comparison and adoption.

## Public implementation review

The first physical-step implementation received an independent public-source
review on 15 November 2026. Its initially changed insertion RNG was corrected
to the original construction insertion stream. Review found no remaining
material blocker for the bounded local screen. The physical module SHA-256
was `e4e7e4b545476e5e9944b1e094809b51780cfb232b8bfe2d78a7521f7434a16a`;
the curvature diagnostics module SHA-256 was
`1d9b9ee54409d035c3cca18ca6924ccbc44c5271fb3cc1951e321ddbab9cb925`.

The independent executed check used only invented graph/geometry fixtures:

```bash
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
CUDA_VISIBLE_DEVICES='' .runtime/envs/py310-qualification/bin/python \
  -m pytest -p no:cacheprovider tests/test_physical_step_replay.py \
  tests/test_curvature_diagnostics.py
```

Result: 57 passed in 1.50 seconds. These cover insertion equality, actual
physical-vertex export, per-organ geometric length and diameter/density budgets,
original IDs and attachment arcs, seed authentication, exact inactive-route
delegation, invented order-5 topology, and analytic physical-scale metrics.
No native simulation, private observations or private comparison outputs were
used by this review. No app/config/native-construction caller was introduced
for these optional modules. These checks do not establish empirical success,
physical-step convergence or the OU fallback, which was unimplemented at that
source epoch.

The subsequent optional OU extension received a separate independent review.
Its implemented row preference is
`lambda_r * sign(assigned_heading_y) * P_t(ey)` with the insertion's row sign
frozen; downward preference is `lambda_d * P_t(-ez)`. This is a declared
engineering alternative to the illustrative horizontal drift above. Both
coefficients are rad/cm; neither is inferred from Fichtl trial counts or
probabilities. The extension uses stationary initial curvature, exact joint
scalar OU increments/integrals, the spherical heading update, and minimal
frame rotation through the accepted heading. It retains curvature components
after soil projection. The first chord preserves insertion while advancing
latent curvature; it discards that chord's integrated turn explicitly.

Review identified a numeric edge where finite inputs could produce an
overflowed or underflowed `h/ell` and silently suppress integral noise. The
helper now rejects an unrepresentable ratio before computing coefficients.
Independent re-execution of `tests/test_curvature_process.py` and
`tests/test_physical_step_replay.py`, using the same command/environment prefix
above, gave **77 passed in 2.29 seconds**. These include analytic covariance,
small-step conditional variance, stationary moments, synthetic transport,
boundary latent continuity, three pre-OU full-output parity hashes and
conservation fixtures. No native simulation or private data was used.

The reviewed helper SHA-256 is
`8e0a42ed78637d5734ec1811e3cc187dcdc162262da5be9f74626110afca94fd`;
the updated physical replay SHA-256 is
`f426c8dc3fb68e8b2515eb3f45fe185ddd08ec6c3c3b672f0a217a39230273b8`.
No material engineering blocker remained for a bounded local OU screen.
This does not establish empirical accuracy, geometric resolution convergence,
or biological values for q, ell and either drift coefficient.
