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

Four follow-up experiments probe different parts of placement.

- **Where a daughter puts root length.** Represent the vineyard cell with a periodic horizontal field that changes smoothly with depth. For each potential terminal daughter, average the field along the portion of its curve in the measured diameter band. Use that average to adjust the log odds of emergence or retention. Fit coefficients from training tubes and compare the realized vines with birth-only, depth-only and spatially uniform odds. This offline experiment assumes that a potential path is available before the terminal survival draw.
- **Daughters sharing a parent.** Fit the frequencies of a set of possible branching policies on training tubes, then draw one policy for each eligible biological parent. Siblings share that decision. Expected length is additive. The probability of an empty section depends on which parents can supply it, so evaluate emptiness on each realized vine before averaging.
- **Horizontal direction at emergence.** Turn a selected order of daughter subtrees toward the vineyard row or across it while keeping each attachment fixed. A rigid horizontal rotation preserves segment length, depth and the native diameter profile. If the measurement model adjusts terminal taper by emergence position, recompute that adjustment at the displaced origin before clipping the measured diameter band and calculating dry mass. The unchanged tree with the same terminal rule provides a control for the effect of direction.
- **Depth-specific gravitropism during growth.** On descending sections of early laterals, weaken or strengthen the downward direction within a fixed soil layer. Retain the original bearing and contour step length, taper smoothly back to the native response outside the layer, and grow daughters from the resulting parent sites and tangents. Compare with ordinary downward drift on the same seed, with and without a count-preserving transfer of shallow terminal daughters to deep sites. This tests whether early parents can supply missing depths before terminal recruitment is adjusted.

Check the mapping of survey bearings into model coordinates and whether translated vines beyond the nearest planting positions can reach a sampled cylinder. Score both candidates and references under the same orientation and vineyard extent. A simulation-seed interval measures variability at the existing positions. Additional cores at previously unmeasured positions can test transfer across the vineyard cell.

### Let an early branching decision change the whole tree

A terminal daughter can change the amount of qualifying tissue only where its parent already reaches. To test earlier placement, generate additional fourth-order branches on third-order parents before the fifth-order daughters grow. Make one emergence decision per fourth-order branch. Keeping it retains a connected subtree, including all descendants. Record the fixed proximal scaffold separately. Compare the fitted law with uniform emergence on the same enriched tree and with the original rainfed tree.

A conditional terminal law gives the two levels separate roles. First sample whether the carrier forms, then sample survival of each daughter on that carrier. A daughter's marginal survival probability equals its conditional probability times its carrier's emergence probability. For an otherwise empty core, daughters on a common carrier share that first decision. Check empty-core predictions on the realized graph and verify that every accepted daughter still has its recorded parent.

Two spatial comparisons can distinguish a better fitted surface from a better architecture. One fits root-length density on training tubes, integrates the fitted distribution across one vineyard cell and adjusts whole-subtree emergence to approach that distribution at a given tissue budget. Another evaluates the fitted surface at virtual cylinders and tests whether a single branching law reproduces the predicted pattern there. In both cases evaluate the realized vines on the original measured tubes. Report performance of the fitted surface itself separately, with whole-tube and contiguous-location omissions. A prediction of mean RLD alone supplies neither a vine biomass nor an empty-core probability.

A count-preserving comparison changes the insertion direction of an earlier branch with its whole subtree attached. A horizontal turn can move length across the rows. A change in inclination can also move length between depth bands. Reject orientations that bring roots above the soil, reapply any position-dependent measurement taper and use the same candidate angles for the unguided control. Compare unchanged and guided trees on the same seeds.

### Search combinations of branching rules with a finite mass budget

A complementary search can keep a common bank of connected fourth-order subtrees and vary how each vine chooses among them. Combine preferences estimated from the emergence site, the whole qualifying path, depth alone, length per unit mass, or a continuous RLD surface. A surface can guide the model through its integrated shape over the vineyard cell or through predictions at virtual cylinders. Center and scale each preference across the potential subtrees of the current vine, using their dry masses as weights. This makes a positive value a relative preference within that vine. Use the training tubes to estimate the preference functions before applying them to new geometries.

One 5,000-rule design uses eight specified comparisons and 4,992 Latin-hypercube combinations. Vary the spatial weights, their overall strength, suppression of shallow births, promotion of deep births, preference for isolated possible branch sites and the fraction of available subtree mass. Rank candidates with the resulting preference and one fixed random draw per biological axis. Retain the prefix of complete subtrees whose combined mass with the fixed scaffold is closest to the vine target. A vine whose proposals cannot reach that mass retains all candidates. Compare its realized mass and coverage with the same-seed controls.

For each whole-tube omission, select one rule using only the remaining tubes and a training panel of vines. Freeze the selection, then score that rule on both the omitted locations and different vine seeds. A crossed comparison using the original or new seeds and the training or omitted tubes can show which part of a training gain transfers. Freeze a single selection on all development tubes before the historical comparison. Record independent tube and seed counts alongside the number of parameter evaluations.

To understand a failed transfer, compare the observed RLD in each physical section with the simulated mean for the fixed scaffold alone and for the scaffold retaining all candidate subtrees. A section beyond those limits requires different potential tissue on that panel. A section inside its limits can still conflict with the biomass budget or the requirements in other sections.

Two further comparisons use the same evaluation. First, rerank the fixed parameter sets after reducing shallow section weights, limiting the contribution of large RLD residuals, or applying both changes. Evaluate the selected trees with the original physical loss and original weights. Plot the estimated RLD in each layer relative to that layer’s whole-cell average. Refit after omitting groups of training tubes and report where a previously preferred horizontal location changes to below-average predicted RLD. A spatial rule can use the agreement among training-only fits to reduce its local preference toward uniform odds.

Second, give a potential fourth-order branch a choice of complete, connected paths. It can retain its original bearing, turn toward its nearest row, turn away, or fail to emerge. Estimate separate effects for whether the branch forms and which feasible course it follows. For a given core, the probability of a miss from that branch is the sum of the probabilities of choices that miss. With independent decisions among branches, their miss probabilities multiply unless fixed tissue already reaches the core. Verify attachment continuity, mass and the physical projection on a fully realized tree containing several choices.
