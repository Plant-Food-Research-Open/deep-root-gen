# Options for testing root placement

Use the same focal vine, physical coring geometry and diameter definition
across each comparison. Generate vines before applying any sampling locations.
The following are experimental options for reviewing a spatial RLD model.

| Question | Paired change | What would support the mechanism? |
|---|---|---|
| Does repeating a single vine affect apparent clustering? | Compare translated and independently generated neighbours at the same offsets. | A change in empty-section frequency at matched mean root length, reproduced across independent groups of vines. |
| Can existing secondaries supply more shallow root length? | Give shallow-born secondaries a modest inclination towards horizontal. Keep their attachment sites, compass bearings and lengths matched. | Shallow RLD approaches the observed mean and shallow hits become more frequent without excessive deep loss. |
| Do sibling roots explore the same soil? | Randomly rotate sectors for sibling bearings. Test spacing of attachment sites separately. | Fewer empty sections and less length concentrated in an individual deep hit. |
| Would a different depth distribution of secondary origins help? | Reallocate part of a fixed expected branch count towards shallow primary segments. | The depth profile improves with comparable total length, crown-inclusive dry mass and horizontal spread. |

Start the neighbourhood comparison through the [generator API or offline CLI](../NATIVE_EXECUTION.md#growing-a-neighbourhood-of-vines).
Keep per-plant contributions, counts of completely empty cores, per-depth
occupancy, mean RLD when positive, and ordinary spatial loss. Preserve distinct
test sets for root-growth parameter selection and evaluation. Seed replicates
estimate simulator variability at the measured locations. Testing another
field transect addresses transfer to new locations.

Compare dry tissue density assumptions on fixed geometry when assessing
biomass. Root recovery and species assignment can also affect the measured
response. Replicated recovery samples and a blinded review of shallow and deep
fragments would help quantify those effects.

The [executed synthetic notebook](../../notebooks/grapevine_root_architecture/neighbourhood_comparison.ipynb)
shows the paired comparison, focal and neighbour decomposition, and where
collaborators can find the measured comparison in their local notebook archive.

## Core-informed placement and retention

A physical core measures the combined root length density (RLD, cm of root per cm³ of soil) of all intersecting vines. It can show that a model puts too much length in a few occupied sections while missing nearby sections. Several branching histories can produce the same RLD.

### Which decision changes?

| Experiment | Stochastic decision | Comparison |
|---|---|---|
| Move existing daughters | Weight eligible attachment sites by depth and distance to the nearest vine row. Preserve each parent's realized daughter count and anchored first site. | Unguided placement on the same eligible parent contour. |
| Change branching probability | Use the preference along the eligible parent contour to adjust the odds that the parent branches. Keep the conditional daughter-count law. | Spatially uniform odds adjusted to match expected recruitment. |
| Change terminal retention | Give eligible terminal axes a probability of survival. A partially retained control allows survival to increase or decrease locally. | Uniform retention matched for expected count. Report realized count and surviving length. |

The public [retention utility](../../scripts/research/realize_terminal_recruitment.py) samples fifth-order axes using their insertion depth. The local study also evaluated an offline method that uses the path of each **fully grown** candidate axis. Its fitted probabilities apply to those mature paths. The offline fit evaluates how selecting those paths changes the predicted core observations.

### Score the combined set of axes

Grow a common scaffold and its potential terminal daughters before projecting them into physical cores. For each optional axis, record its qualifying root length by depth and row-distance band, its dry mass, and its contribution to each core section. Keep every parent that could carry a candidate daughter. Group axes by operation and by the depth and row-distance bands containing the most qualifying length. Fit a depth-only rate first. In row zones supported by fewer than two training tubes, use that depth-only rate.

Add each candidate axis's expected RLD contribution, or subtract it for suppression, then score the resulting RLD profile. Coverage also depends on overlap. For example, if two optional axes are the only possible hits in one section and each is retained independently with probability 0.5, the probability of a hit is 0.75. A fixed axis crossing the section makes that probability 1. Apply a single seeded decision to each whole axis across all sections it intersects.

Cross guided and uniform placement with guided and uniform retention. Match realized counts within qualifying-length classes when testing the effect of location alone. For a dry-mass sensitivity, calculate expected added and removed mass on each vine. Scale the probabilities on the larger side by the ratio of the smaller to the larger mass. This balances mass in expectation. Individual draws still vary.

### Does the improvement transfer?

Fit the spatial preference and its rates on whole training tubes, keeping all depths from an omitted tube together. Pair each candidate with the rainfed reference on the same simulator seeds, reflections, neighbour layout, core geometry and observation diameter band. Freeze the rule before drawing fresh paired seeds.

| Evaluation | What it tests |
|---|---|
| Fresh seeds at the tubes used for fitting | Repeatability at calibrated locations. |
| Fresh seeds at whole tubes omitted during fitting | Transfer of the spatial rule to other measurement locations. |
| Expected-mass balance applied after examining the fresh panel | Sensitivity to total retained mass on that same panel. |

Compute the physical loss from 50% normalized absolute RLD error, 25% total variation of the joint tube-by-depth RLD shares, and 25% total variation of the depth shares. Give each tube equal total weight across its retained depths. Normalize absolute error by the training tubes' weighted mean observed RLD and average fold losses in proportion to their held-tube counts. Report the relative reduction as `1 − candidate loss / paired reference loss` for each evaluation. A 10% reduction requires a candidate loss at or below 0.90 times its paired reference. For a seed interval, resample whole paired seeds with all their tubes and reflections together.

Report deep empty-section frequency and RLD per occupied section alongside spatial loss. Report the mean underground dry mass per vine, including crown and rootstock, and the counts below, within and above the 6–8 kg target. When each held-tube fold has its own fitted rule, label pooled biomass counts as vine-by-fold realizations.

### Combine shallow branching with deep placement

A daughter born near the surface can still supply root length at depth. To test whether fewer shallow births produce a deeper root system, record the absolute length in the measured diameter band at 90–120 cm and 120–150 cm, the fraction of whole-vine length there, and the deepest point. Report the change against both the rainfed reference and the same deep-placement treatment with ordinary shallow branching.

| Mechanism | Paired comparison |
|---|---|
| Reduce shallow terminal emergence | Thin only daughters born in the surface layer. Apply the same thinning draws with and without deep recruitment. Record how much deep length the removed daughters contributed. |
| Replace terminal daughters at depth | Replace selected shallow daughters with the same number of eligible daughters on deeper parents. Also test deep recruitment alone. Record the realized counts and any shortage of eligible sites. Equal counts can yield different lengths and masses. |
| Move an earlier branch and its descendants | Before growing the daughter, sample deeper, diameter-compatible contour on its own parent. Keep the first accepted anchor in count-based branching and leave the bud in place if no compatible site exists. Report how many buds were selected, moved and retained for lack of support. |

Cross each relevant mechanism with the previous deep-recruitment, longer-primary or spatially guided treatment. Evaluate the fitted spatial preference at births throughout the vineyard cell, using only training tubes to estimate and normalize it. The original physical-core score and coverage on whole omitted tubes determine whether the combined change improves spatial prediction. Additional random cylinders measure coverage at new simulated positions. New field tubes are needed to verify transfer after repeated use of the historical comparison tubes.

### Screen 5,000 combinations on a common observation support

Cross 25 early-architecture settings with 200 terminal policies. Vary first-order contour length, lateral insertion angle, downward drift and the depth at which daughters emerge in the early settings. Within each resulting native tree, vary which eligible terminal daughters form or survive, the balance between shallow and deep sites, and sparse recruitment of an additional order. Keep the potential axes and their stochastic marks paired across terminal policies. Report the number of distinct realized treatments as well as the number of recipes. Multiple recipes on the same vine seed share that realization.

Fit each spatial rule on whole training tubes and normalize the field using those tubes. Freeze the shortlist on a development seed panel, refine it on another panel and freeze the primary before evaluating the paired comparison positions. Use the original physical loss and a common diameter band for the candidate, rainfed reference and earlier loss-leading challenger. A 10% reduction relative to the stronger comparator requires a loss at most 0.9 times the lower of the two paired reference losses. Report deep empty-section change, positive-section RLD, mean crown-inclusive dry mass and individual biomass counts alongside it.

Three follow-up experiments probe different parts of placement.

- **Where a daughter puts root length.** Represent the vineyard cell with a periodic horizontal field that changes smoothly with depth. For each potential terminal daughter, average the field along the portion of its curve in the measured diameter band. Use that average to adjust the log odds of emergence or retention. Fit coefficients from training tubes and compare the realized vines with birth-only, depth-only and spatially uniform odds. This offline experiment assumes that a potential path is available before the terminal survival draw.
- **Daughters sharing a parent.** Fit the frequencies of a set of possible branching policies on training tubes, then draw one policy for each eligible biological parent. Siblings share that decision. Expected length is additive. The probability of an empty section depends on which parents can supply it, so evaluate emptiness on each realized vine before averaging.
- **Horizontal direction at emergence.** Turn a selected order of daughter subtrees toward the vineyard row or across it while keeping each attachment fixed. A rigid horizontal rotation preserves segment length, depth and the native diameter profile. If the measurement model adjusts terminal taper by emergence position, recompute that adjustment at the displaced origin before clipping the measured diameter band and calculating dry mass. The unchanged tree with the same terminal rule provides a control for the effect of direction.

Check the mapping of survey bearings into model coordinates and whether translated vines beyond the nearest planting positions can reach a sampled cylinder. Score both candidates and references under the same orientation and vineyard extent. A simulation-seed interval measures variability at the existing positions. Additional cores at previously unmeasured positions can test transfer across the vineyard cell.
