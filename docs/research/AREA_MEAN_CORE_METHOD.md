# Measured cores and conditional area-mean comparisons

Public scientific design memo, 15 November 2026. This note uses public source
and methodological literature only; no private observations, fitted arrays or
comparison artifacts were inspected. The owner permits larger virtual sampling
volumes and an assumed area-mean interpretation. This changes the research
estimand; it does not change the volume actually sampled. No new biological
acceptance threshold, calibration adoption or source implementation is approved
by this memo.

## Decision and meaning of accuracy

Retain the original thin-core comparison and add a separately named virtual
area-mean comparison. A larger virtual cylinder averages model root length
over a larger region and may reduce sensitivity to whether a discrete root
happens to intersect a thin core. An improved fit after that change is evidence
about a different observation assumption, not automatically better prediction
of the original thin-core observations.

Root-coring simulations have demonstrated that sampling location, number of
cores and core diameter can affect estimates of root length density. Those
results motivate a support sensitivity analysis; they do not validate a
particular radius or homogeneity assumption for the present site.
[Wu et al., soil-coring study](https://academic.oup.com/aob/article/121/5/809/4634015).
More generally, changing spatial support requires an explicit averaging model;
uncertainty at the new scale is not supplied by relabelling observations.
[Belmonte et al., change-of-support methods](https://www.mdpi.com/2072-4292/14/21/5442).

Use the following distinct labels:

| Comparison | Observed quantity | Model quantity | Interpretation |
|---|---|---|---|
| Measured-core support | Density in the actual sampled cylinder | Density in that same cylinder | Direct support-matched comparison |
| Pooled measured support | Sum of measured length divided by sum of actual sampled volumes | Identical pooling of predictions at actual cylinders | Comparison on the union of specified measured pieces, excluding gaps |
| Conditional local area mean | Actual density or a declared pooled estimate used as a local-mean proxy | Density in a larger virtual cylinder or declared region | Agreement conditional on local homogeneity/representativeness |

For a fixed depth thickness `h`, mean volumetric RLD over a horizontal area
`A` is `L(A x depth_band)/(area(A)*h)`, in cm/cm3. Root length per ground area,
`L/area(A)`, has different units and differs by the depth thickness. Do not
exchange these quantities when referring to an "area mean".

## Preserve measured density and provenance

For observation `i`, retain its immutable physical geometry and sampled flag:

```text
V_obs_i = pi * r_obs_i^2 * h_obs_i
y_i = L_obs_i / V_obs_i
V_virtual_i = pi * R_i^2 * h_virtual_i
yhat_virtual_i = L_model(virtual cylinder i) / V_virtual_i
```

If `R_i > r_obs_i`, keep `y_i` unchanged. Dividing the measured length
`L_obs_i` by `V_virtual_i` would dilute the observation without collecting more
soil. For an invented example, 200 cm measured in 100 cm3 gives 2 cm/cm3.
A virtual volume of 400 cm3 does not turn that observation into 0.5 cm/cm3.
Under a constant-density assumption, `2 * 400 = 800 cm` is an implied expected
length in the larger region, not a measured length or additional evidence.

Preserve `physical_core_id`, original increment ID, original radius, depth
limits, observed volume, units, sampled status and original values separately
from `virtual_support_id`, radius, depth band and virtual volume. An original
`known_volume_cm3` must not be passed unchanged to a newly enlarged cylinder:
the existing core validator correctly requires agreement with its geometry.
Record both volumes in the mapping; never overwrite the observed volume.

The conditional assumption is that the measured core is representative of a
specified local mean, not that the entire larger region was observed. Keep
row/inter-row position, plant distance and depth strata separate unless the
amendment explicitly assumes their means can be pooled. Sparse measurements
cannot by themselves establish local homogeneity or the spatial correlation
range. Larger windows must not automatically receive narrower confidence
intervals: no additional observations have been collected.

## Multi-scale comparison before another construction search

First reuse preserved graphs and compute predictions at the original support
and at two predeclared larger radii. For example, `r_obs`, `2*r_obs` and
`4*r_obs` are an invented engineering screen, not recommended biological
scales. The owner should freeze actual radii from the spatial question,
sampling layout and available neighbour coverage before inspecting candidate
rankings. Keep depth unchanged in this first radius screen. Report absolute
length numerator, volume denominator, RLD, zero/nonzero intersections and
subject/neighbour contributions at every scale.

Select one declared area-mean support for the next construction comparison;
retain other radii as sensitivity views. Do not optimize radius alongside
growth parameters or choose the best radius separately for every candidate.
Keep measured-core performance visible even when area-mean agreement is the
exploratory primary objective. A smoother curve or fewer zero predictions is
not itself an accuracy criterion. Across simulations, distinguish
`loss(mean_prediction, observation)` from `mean(loss(single_prediction,
observation))`: the former evaluates an ensemble mean; the latter also
penalizes realization variability. Predeclare which is primary and report
seed variability separately.

Only then consider depth pooling as a separate support change. For complete
sampled increments within one declared physical-core/depth group:

```text
pooled_observed_RLD = sum(y_i * V_obs_i) / sum(V_obs_i)
pooled_actual_prediction = sum(yhat_actual_i * V_obs_i) / sum(V_obs_i)
pooled_virtual_proxy_prediction = sum(yhat_virtual_i * V_obs_i) / sum(V_obs_i)
```

The last line is an observed-volume-weighted mean of virtual density
predictions. Its denominator is a comparison weight, not the virtual union
volume; it does not estimate model root length in the union of overlapping
virtual cylinders. If virtual predictions already refer to one common depth
band, emit one pooled row rather than scoring a repeated identical band for
every original increment.

Pool lengths and volumes before taking ratios; a simple arithmetic mean is
equivalent only for equal volumes. Exclude unsampled increments from both
numerator and denominator; retain sampled zeros. A gap is missing support,
not a zero-density layer. Either retain the exact observed pieces or mark the
pooled interval incomplete. Predicting a continuous virtual band across a gap
requires an additional, explicit vertical representativeness assumption.
Do not split a measured increment at a new depth boundary without declaring
an assumption about its internal density.

## Whole-core holdouts and overlapping virtual regions

Assign every depth increment of a physical core to the same training or
holdout group before pooling, normalization, smoothing or parameter selection.
Never construct a pooled observed target using both groups. Estimate scales,
spatial means, smoothing choices and baseline parameters from training data
only. Held-out values cannot choose radius, depth bands, neighbours or the
winning mechanism. Compare against a simple training-only depth/position
baseline at the same declared support.

Keep whole-core IDs as the unit for weighting and resampling. Larger virtual
windows centred on nearby cores can overlap heavily: they are correlated
views, not independent new samples. Reusing a value at three radii does not
triple sample size. For the minimal comparison, score each physical core once
at each scale and report scales separately; do not sum all scale-specific
losses as if they were independent observations. Equal whole-core weighting
can prevent a core with more sampled increments from dominating: normalize
depth weights within each core, then average across cores. If adjacent cores
are strongly dependent, report spatially grouped holdouts where feasible;
whole-core holdout alone is not unseen-site or independent-region validation.

If a genuine regional area average is later needed, specify a disjoint
partition of the region or integrate its union once. For overlapping regions
`C_j`, a partition-of-unity construction is possible:

```text
k(x) = number of regions containing x
w_j(x) = 1[x in C_j] / k(x)       where k(x) > 0
V_j_effective = integral w_j(x) dx
L_j_effective = integral w_j(x) d(root length)
union_RLD = sum(L_j_effective) / sum(V_j_effective)
```

This requires spatially varying overlap weights for both soil volume and
root-segment length. Multiplying each whole-cylinder total by one guessed
overlap factor is not generally equivalent. The current finite-cylinder
operator treats overlapping observations separately; it does not implement
union geometry or this partition. No such regional total is claimed by the
minimal screen. Area-representation weights for observed samples additionally
require a declared sampling/representativeness model; sampled volume alone
does not identify how much unsampled horizontal area a core represents.

## Fixed neighbours at every declared support

Retain the same saved neighbour graphs, origins and seeds across subject-only
mechanism arms. Re-evaluate those graphs at each virtual radius/depth support;
do not copy thin-core neighbour predictions into larger windows or multiply
them by a volume ratio. Freeze the resulting background separately for each
support, and add subject and background length/mass before calculating
densities or ratios. This preserves attribution within each support while
changing the observation operator explicitly.

Larger windows may intersect roots from previously omitted neighbour origins.
Before interpreting a new radius, inspect its coverage using conservative
origin-to-region distances and the maximum attainable root path length under
the frozen construction. A branch path-length bound can prove an omitted
origin cannot reach a region only if the bound also covers the scenario's
possible lengths; a typical or mean length cannot do this. Otherwise perform
a small, separate neighbourhood-ring sensitivity check with a predeclared
numerical convergence rule and budget. Do not tune subject growth to compensate
for known missing origins. Keep missing-neighbour uncertainty explicit if the
screen cannot establish coverage.

Neighbour stability and unchanged graph bytes establish a conditional
comparison, not that the background is correct. If the fixed background
already exceeds an observed total, preserve that incompatibility; do not
create a negative subject contribution. Training-informed backgrounds cannot
use held-out core values while retaining an independent holdout claim.

## Objective, conservation and biomass limits

A minimal exploratory objective is whole-core-balanced MAE of the declared
fine-root RLD quantity. Use the same immutable target, support, mask and weights
for every candidate. A dimensionless loss may divide by one positive
training-only scale, frozen before the comparison; define a positive fallback
for an all-zero training set. Do not divide each residual by its observed
value, because true zeros are valid observations. Report MAE, RMSE, signed bias
and the sampled zero/nonzero pattern at measured and virtual supports. No
numeric biological PASS threshold is introduced here.

Changing only evaluation support must leave graph coordinates, topology,
lengths, diameters, density and whole-system mass unchanged. With the same
depth band and fixed graph, nested radii have nondecreasing included root
length and mass; their densities need not be monotone. Fine plus coarse must
equal total, and per-plant contributions must sum to the neighbourhood result.
Disjoint support pieces must reconcile with their union, with explicit
ownership of shared faces: the current closed-cylinder convention can count
a root lying exactly on a shared depth face in both adjacent layers.
Overlapping-window totals must never be used as a whole-system conservation
check. Keep numerical integration/roundoff tolerances separate from fit
tolerances.

Use the existing cylinder-mass audit before and after any construction change.
Changing radius does not repair a diameter taper or qualify density. Primary
branch-window changes can alter inherited daughter diameters and mass even
when counts and sampled lengths are fixed. The 25% joint order-4/5 allocation
remains an arbitrary order-mass scenario, not observed fine-root biomass.
Check diameter-defined classes again after scaling, retain locked dimensions,
and report parent-child diameter inversions and feasibility failures. Do not
thicken roots or refit density to improve the enlarged-window RLD objective.
These constraints and initial-tangent/chord distinctions remain as documented
in [the five-order method](FIVE_ORDER_PRIMARY_AND_MASS_METHOD.md).

## Small bounded next comparison

1. **Support screen with no new construction.** Freeze the amendment, physical
   and virtual support mapping, whole-core split, target convention, radii and
   depth groups. Reuse saved subject/background graphs. Check density units,
   overlap, shared faces, neighbour reach and all conservation identities.
   Retain the original thin-core result; do not rewrite its interpretation.
2. **One geometric mechanism.** At one frozen support, compare the retained
   subject baseline with at most two prespecified settings of one existing
   control, for example curvature amplitude with its correlation length,
   drift, lengths, topology and diameters held fixed. Pair unchanged random
   mechanisms across arms and keep the background fixed. If reach diagnostics
   instead justify moving primary branch placement, use that as a separate
   comparison and audit its inherited-diameter coupling; do not change both.
3. **Small confirmation.** Select using training cores only. Re-evaluate the
   baseline and one candidate with fresh subject seeds, then report held-out
   whole-core and multi-scale diagnostics once. If held-out values have already
   guided earlier choices, label them development data and avoid an untouched
   validation claim.

A proposed engineering cap is three arms including baseline on three paired
development seeds (at most nine subject constructions), followed only if useful
by baseline versus one candidate on three fresh seeds (six constructions).
These counts are a small screen, not a precision justification or biological
sample size. Reuse matching saved baseline graphs where available. Record a
wall-time/output cap before execution and amend explicitly before another
round; the owner may authorize further bounded trials. Do not launch a joint
count/length/diameter/density/tropism search or new inference training merely
because the larger windows give a smoother objective.

The resulting evidence can support conditional local-mean agreement and
mechanism sensitivity. It cannot establish the true individual root system,
whole-field accuracy, independently measured area biomass or biological
adoption. Root processes private data locally. This public memo introduces no
new external model calls; the configured Astra review is reused and Claude
review remains deferred.

## Implemented support and pooling interface

`deeprootgen.research.area_mean_observation` uses version
`explicit-volume-area-mean-proxy-v1`. `make_virtual_cores` returns separate
simulation geometry, an original-to-virtual geometry/volume mapping and
diagnostics. Original observation values and geometry remain unchanged. A
shared depth band is an explicit pair of z limits in cm; it is not inferred
from a height or a midpoint.

`pool_area_mean_observations` requires matching observation/prediction IDs and
sampled masks, explicit sampled known volumes and nonoverlapping groups. Its
`quantity_columns` are **caller-declared additive quantities only**: root length,
root volume or dry mass. If the input measurement is RLD, first calculate
`observed_length_cm = observed_RLD_cm_cm3 * original_sampled_known_volume_cm3`.
Never use the virtual volume for this conversion or pass normalized RLD as an
additive length column. The generic column names do not establish units or
verify that the caller supplied an additive quantity.

The two explicit prediction modes are:

- `matched_support`: require identical physical support and calculate each
  pooled density as `sum(q_i) / sum(V_obs_i)`. The predicted additive total is
  a physical sum on those specified measured supports.
- `observed_volume_weighted_virtual_density`: calculate
  `sum((q_virtual_i / V_virtual_i) * V_obs_i) / sum(V_obs_i)`. Its
  `predicted_additive_total` is intentionally missing. The separately named
  equivalent on observed volume is a comparison proxy, not root length or mass
  in a virtual union.

Missing samples contribute neither zero quantity nor volume. The helper rejects
overlapping sampled observed cylinders in one coordinate frame; separate
replicate frames need separate calls. Virtual overlaps are reported as
correlated windows. Summed virtual window volumes are audit metadata, not an
observed or union volume. These utilities implement the arithmetic distinction
above; they do not establish local homogeneity, choose an objective or qualify
the empirical comparison.
