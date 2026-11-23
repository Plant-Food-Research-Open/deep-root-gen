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

### Can branching decisions respond to soil already occupied by roots?

Divide the periodically repeated vineyard cell into soil volumes. For each feasible subtree direction, assign qualifying root length to the volumes its segments cross. Split segments at soil boundaries and at the ends of the measured diameter interval. Verify that the sum across volumes reproduces whole-path length. A vine can then form its daughters in a seeded order, giving more weight to a direction that supplies length where the current vine falls below the training-derived spatial target. Update the occupied volumes after each realized choice and account for the mass available for later daughters. Compare with a control that sees a fixed expected distribution throughout growth. Reproject the chosen connected tree into the original physical cores for evaluation.

When the scanner records separate root lengths by diameter, a second fit can use composition to guide branching. Combine bins only at recorded boundaries. Require the class-specific lengths divided by sample volume to recover the original RLD in every section. Apply the same diameter cuts to the tapered model axes. Estimate class-specific preferences on training tubes, then score the selected subtrees on the original total RLD endpoint. This comparison leaves the interpretation of an observed zero and the assay diameter interval intact.

A third comparison can use the spread of simulated physical-core RLD during training. The ensemble continuous ranked probability score estimates the mean absolute error of a simulated draw and subtracts half the mean absolute difference between two independently simulated draws. For a finite panel, form the latter pairs across different vine seeds, averaging their possible reflections. Test whether this training criterion improves predictions on the original mean-field loss. A diagnostic that optimizes each subtree’s direction with direct access to the evaluation tubes measures attainable agreement on those particular geometries. Keep those choices out of any transferable rule.

### Search across depth preferences and soil competition

One expanded design combines six fixed controls with 4,994 Latin-hypercube settings. Its nine parameters govern competition strength, the amount of qualifying length sought, reliance on coring evidence, the horizontal contrast within each depth, three depth preferences, attraction toward the vine row, and the vine's dry-mass budget. Include a uniform target and a depth-only target. A model with a uniform target can still generate a nonuniform root system because daughters must attach to existing parents and draw on their available tissue.

Before growing an evaluation vine, freeze a rule on the training tubes. Evaluate on different seeds under two omissions of whole tubes, one with the established folds and one with contiguous groups of positions. Compare the locked rule both with the original paired controls and with the lowest-loss previous architecture on the same physical sections and seeds. Report the two thresholds explicitly. A population model can draw one plausible rule per vine. Compute the mean RLD across vines, but compute emptiness and biomass on each realized architecture before pooling.

An additional geometry control can exchange two terminal axes between related parents while retaining both axes and the existing attachment sites. Check diameter compatibility at each new origin, keep the connected shape of each daughter and reapply position-dependent taper before computing mass or clipping to the measured diameter band. A within-parent exchange on the same seed controls for the act of moving the daughters. Compare the resulting tissue supply by diameter class and depth. If a fine class is consistently undersupplied across omitted positions, the next construction experiment can vary the amount of fine tissue produced at fixed dry mass.

### Test fine-root supply on the same parent architecture

A diameter-class deficit can persist when existing daughters move between sites. Two physical comparisons can change the amount of fine tissue. One substitutes two terminal sister axes at an existing attachment and rotates their courses apart. Giving each sister the original contour and dividing its diameters by the square root of two preserves total cross-sectional area and doubles the replaced contour length. The second comparison keeps one connected terminal and extends its contour as its diameter decreases. Check the new route stays below ground. With density that varies by diameter, conserving volume can change mass. Compute both the dry mass from the structural taper and the dry mass under the measurement convention, including the crown, and report the realized change.

A 5,000-setting search can place these terminal sisters on a fixed early architecture. Four common controls and 4,996 space-filling settings vary baseline probability, shallow and deep preference, row preference, preference for thicker eligible terminals, response to the local RLD surface relative to its layer, and the chance of the wider sister angle. Use whole training tubes to estimate the surface and independent random marks for splitting and angle. Compare every selected tree with the same vine retaining its original terminals. Re-observe the physical cylinders on a fully reconstructed tree with the new daughters and record its qualifying length in each measured diameter class.

### Move connected material between soil layers and vineyard sectors

A branch relocation can move its whole descendant system. Pair two branches of the same order borne by different parents and test exchanging their insertion sites. Both receiving nodes must support the incoming diameter. Reject exchanges that take any descendant above the soil surface. Compare a translation with an exchange that also aligns each incoming branch with the original recipient’s horizontal heading. Recalculate the position-dependent taper and project the entire displaced tissue into the physical cores. The training surface can influence the odds through the change in qualifying length deposited along both proposed courses.

A separate crown-level test rotates each complete first-order root about its own vertical attachment axis. Uniform rotation, correlated directions among primaries, and a preference derived from the training RLD surface test different explanations of row-scale coverage. A depth transformation can then change where those courses pass through adjacent layers. Keep the crown attachments and deep boundary fixed, require depth to increase monotonically, insert points at crossed depth knots, and update descendant attachment indices. Recompute segment lengths, sampled diameter intervals and dry mass along the resulting connected vine. Compare the rotated-only, depth-only and combined constructions on the same native trees. When the depth response varies across rows, bound it by weighting admissible maps and measure convergence as the path subdivision is refined.

Report layer means and the original spatial loss alongside empty deep sections. A soil layer may receive too little length while its immediate neighbour receives too much. Stronger deep recruitment alone cannot account for that reversal. To test whether a fitted growth rule is sensitive to simulated population size, expand the training vine panel while keeping the omitted field positions, assessment seeds, observation support and comparison architecture fixed.

### Cross early architecture with late branching and retention

A 5,000-setting design gives the same 1,000 terminal policies to each of five early architectures. The early choices keep the original bearings and depth profile, randomize the primary bearings, shift tissue between neighbouring depth layers, combine those changes, or apply the depth change to a random half of the turned primaries. Move complete connected descendants with each primary. A terminal policy can suppress a shallow daughter, retain its original course, or split a deeper daughter into two finer sisters at its existing insertion. The probability of splitting applies after the retention draw. The surface term uses the logarithm of the predicted local RLD divided by its layer mean. A coefficient of zero recovers the generic depth rule. A positive coefficient can favour both retention and branching where the fitted field predicts higher RLD than the layer mean.

Within each early architecture, reserve five fixed controls and use 995 space-filling settings for the remaining policies. Vary the two response rates, the depth at which shallow suppression ends, the depth at which deep recruitment begins, separate surface coefficients for retention and splitting, and row and diameter preferences. Screen all settings on the same training vines, then reassess a shortlist on an expanded training population. Record both the gain over the unchanged strongest architecture and the contribution of the terminal policy on its own early architecture. Keep independent vine seeds and whole omitted positions for assessment.

A change in a parent's contour can move a daughter along its taper, even when the insertion remains geometrically connected. After a deformation, remeasure parental diameter at each receiving site. Count existing daughters above the growth law's diameter cap, sites that would have been too narrow to branch, and any newly generated sisters failing those criteria. Reapply recruitment and sizing on the changed parent when interpreting a deformation as a growth mechanism. Report dry mass and physical RLD again after this correction. Rotation by a common angle about the vertical crown attachment preserves contour length. An angle varying with depth or a change in horizontal reach generally changes it.


When applying several mechanisms to one population, specify which biological unit draws a treatment. A whole vine can draw one common rule, a vine can choose a rule using its pre-existing size and depth distribution, or each primary can choose separately and carry all its descendants with it. For a whole-vine draw, average the empty-core indicator of each complete option under its probability. For independent primary-level draws, multiply the probabilities that each primary misses the same physical section. Use the original physical intersections for both calculations. Compare this expected population field with actual seeded trees, and verify one complete graph against the original core observer.

### Allocate a fixed mass to terminal elongation

Group three fifth-order roots of similar initial dry mass before consulting a spatial field. Keep their parent sites, initial bearings and basal diameters. Change their contour lengths by extending one or two terminals while shortening the others. A fractional length change scales the mass of a terminal with fixed taper on relative contour length. Choose a direction of exchange perpendicular to both triplets of masses, one calculated from native diameters and the other from the positional diameter adjustment used for comparison with the cores. Scale each direction separately to satisfy all three native length limits and keep the tips and intermediate points below ground. Recompute both mass sums after each change.

| Part of the design | Settings |
|---|---|
| Early geometry | Native primary bearings or rigid rotation about the crown insertion |
| Fixed comparisons per geometry | Original lengths, random exchange, local crowding, depth preference, continuous coring surface |
| Sampled settings per geometry | 2,495 Latin-hypercube draws, shared across the two geometries |
| Exchange log-odds intercept | −4 to +2 |
| Seven preference coefficients | −3 to +3 for each of four depth contrasts, cross-row location, local root density and relative RLD from the fitted surface |

This gives 5,000 prescriptions. Each group draws once among its unchanged length allocation and two feasible exchanges. Use common random draws across settings. The spatial predictors describe the length each option would deposit along all three paths. A negative crowding coefficient can shift length away from cells that already contain more roots than their layer average. Remove the surface term from the selected rule to measure what the coring data added.

The [terminal elongation module](https://github.com/junqi108/deep-root-gen-PFR-open/blob/41599e615996734198dc28377d26f243660963d0/deeprootgen/research/terminal_elongation.py) implements this design. Call `elongation_design()` to obtain its 5,000 rows. Pass the two masses and the lower and upper length bounds of each terminal triplet to `exchange_scales`. The resulting three alternatives can be drawn with `choose_exchange` using a design row, standardized changes in deposition and fixed uniform random marks. Its module example shows a two-budget exchange on a synthetic triplet.

Two other experiments distinguish elongation from lateral spread. Change the alignment of successive terminal segments while preserving every step length and the original first tangent. Count corrections at the soil surface because they can change local turning even when the overall course straightens. In a branching experiment, allow fine sisters to emerge at distinct legal sites on one parent, then compare with sisters at the same site and with the unsplit terminal. When splitting earlier root orders, retest diameter and daughter-count limits throughout the altered subtree. Record how many subtrees are actually eligible.

### Test whether an auxiliary coring measurement predicts vine-root placement

A second measurement in each training core can guide branching if its spatial pattern predicts where the vine model misses roots. Two candidates are the survey's non-vine root fraction and lengths from vine-sorted roots below the diameter band used for evaluation. Check the bin edges, units, missing measurements and whether the length in a subset exceeds the measured total for that fraction. Document how the field team separated material. Report how sensitive the result is to inconsistent sections.

Fit the auxiliary RLD through depth within each training tube and smooth the profiles across both periodic soil coordinates. Shrink each horizontal prediction towards the depth profile. At a proposed daughter site use the log ratio of the predicted local auxiliary RLD to its depth baseline, with the same training-derived pseudocount in numerator and denominator. Fit the association between this contrast and the difference between observed vine RLD and the unchanged simulator. Estimate it on whole inner tubes omitted from map fitting, bandwidth selection and scale estimation. A signed, regularized slope allows either association and pulls weak effects toward zero. A depth-varying slope can borrow strength from the whole profile.

Add this correction to the existing relative vine-RLD surface. Separate parameters multiply retention and branching odds by the exponential of their respective coefficients times the combined field. Keep the odds neutral beyond measured depth support. Compare a generic policy, the vine-only surface, the auxiliary-only surface and the combined surface against the same architecture and physical score. At omitted tubes, report how well the field predicted the auxiliary measurement, how well it predicted the vine model’s error, and how much it improved the score on fully realized vine graphs. Record below-, within- and above-target biomass counts. If native structural and positional diameter conventions give different mass totals, report both.

The [relative core surface module](https://github.com/junqi108/deep-root-gen-PFR-open/blob/41599e615996734198dc28377d26f243660963d0/deeprootgen/research/relative_core_surface.py) accepts training sections and arbitrary query positions. Pass the row and vine periods, three bandwidths and sampled depth interval explicitly. Use the same field for both decisions when appropriate, with separate coefficients for retention and branching. For example, a local-to-layer ratio of two doubles the odds at unit strength. An original probability of 0.20 then becomes one third.

```python
import numpy as np
from deeprootgen.research.relative_core_surface import adjust_branching_odds

retention = adjust_branching_odds(0.20, np.log(2.0), strength=1.0)
branching = adjust_branching_odds(0.20, np.log(2.0), strength=0.0)
```

Use `relative_core_surface` to estimate the log ratio from allowed training tubes and `compose_relative_surfaces` to add a fitted auxiliary correction. The caller supplies the whole-tube split, fits the coefficients and passes the probabilities to the growth experiment.

### Combine terminal allocation with primary inclination, neighbouring roots and a structural mass target

A rigid inclination change rotates a complete primary and its descendants about their actual crown insertion. Evaluate shallower and steeper options and reject any that put tissue above ground. Cross the chosen inclination with terminal elongation on the resulting graph. Recompute its available length bounds, local crowding and positional assay before choosing which terminals extend. Compare each combination with the same inclined tree retaining its original terminal lengths.

A root can also respond to expected crowding from other vines. Deposit the simulated roots of each training vine into soil voxels at their absolute positions around its own crown. Sum the mean distribution translated to the surrounding crown positions, excluding the focal crown and excluding the focal training vine from the donor mean. A daughter can then favour elongation along a less crowded course. Turn off only the neighbouring-root coefficient to measure its contribution while preserving the focal vine’s own crowding response. Use the original core observer for both treatments.

To target structural biomass directly, calculate the dry mass that lengthening each terminal can add, and the mass available from shortening it. Keep its attachment, structural diameter and crown fixed. Allocate the required change within the native length and soil bounds. Recompute the physical intersections for any fractionally extended or shortened terminal. Record the requested and attained mass of each vine, both diameter conventions, and the remaining deficit if all eligible terminals exhaust their capacity.

A population can assign different complete rules to different vines. If testing mixtures, estimate their proportions using training tubes and training vines. Compare this selection with a prespecified equal-share population. On the assessment set, distinguish realized vine-by-vine counts from expected counts under a distribution. A retrospective upper bound over all common proportions can establish whether any mixture within the tested library could reach the target across every panel. Its scope is limited to that library and those measured positions.

### Test which side of a parent a lateral emerges from

A daughter can change the tissue it deposits across vineyard rows while retaining its original angle to the parent. Turn its **entire attached subtree** about the incoming tangent of its parent at the actual insertion. Evaluate the original orientation, ±60°, ±120° and 180°. Reject an angle if any descendant rises above the soil. All sections, reflections and neighbouring-vine translations of the same root share one angle. Recalculate the core intersections and any location-dependent diameter adjustment after rotation.

The [lateral orientation module](https://github.com/junqi108/deep-root-gen-PFR-open/blob/41599e615996734198dc28377d26f243660963d0/deeprootgen/research/lateral_orientation.py) supplies the rotation, the normalized choice probabilities and the full parameter table. Each of two primary architectures and two lateral orders receives ten fixed controls and 1,240 jointly sampled settings. These 5,000 settings vary turn frequency, angular width, birth depth and where the subtree deposits tissue across three depth bands, relative crowding and the fitted 3D coring field. Every fifth sampled rule disables the coring term. The same fixed controls and random draws on each background allow direct comparisons.

```python
from deeprootgen.research.lateral_orientation import lateral_orientation_design, roll_options

rules = lateral_orientation_design()
# Synthetic points share an insertion at z = -20. Positive z is upwards.
options, feasible = roll_options([[0, 0, -20], [5, 1, -22]], [0, 0, -20], [1, 0, -1])
```

For an exact check on stochastic simulations, average the physical RLD of each legal angle using its choice probability. To estimate empty cores, calculate each subtree's probability of missing the individual cylinder and multiply those probabilities across independently chosen subtrees. Include unchanged tissue as a potential hit. Average over reflections only after computing emptiness for each complete geometry. Compare the physical score of the expected field with scores from actual seeded whole vines. The loss is nonlinear, so these quantities can differ.

### Add material where it can grow without changing the sampled fine roots

The [proximal thickening module](https://github.com/junqi108/deep-root-gen-PFR-open/blob/41599e615996734198dc28377d26f243660963d0/deeprootgen/research/proximal_thickening.py) applies secondary growth to the basal portion of eligible exponential tapers. Increase the basal diameter and adjust the decay rate so the new taper rejoins the original at the specified coarse diameter, or reaches the original tip diameter if the entire root is coarse. Keep each attachment, contour, terminal diameter and fine distal profile. Use each axis's original receiving-parent diameter and its order- and maturity-specific limits to cap the treatment. Calculate the achievable dry-mass increment from the increased material using the supplied diameter-class tissue densities.

Measure the original crown-inclusive dry mass once. Set a per-vine target and record the mass attained, the actual mass added by root order and any deficit when the eligible coarse roots reach their limits. Choose the coarse cutoff above the largest diameter included in the spatial assay when testing a mass-only change. Verify that the fine-class intersections, the eligible root length, and deep-empty indicators still agree with a complete geometric replay. Report the separate outcome of controlling mass alongside the original physical spatial loss.

### Distinguish variation among vines from variation among field positions

When assessments use different simulated vine groups at different field positions, cross the groups with **both sets of positions** using a fixed, training-selected treatment and its paired control. Reproject each whole vine through the same core cylinders under both arrangements. If the original folds used different scaffold settings, repeat with a common setting. Evaluate pooled loss from the mean physical field of all vines. Averaging percentage gains from small groups would give a different quantity. Preserve each vine across all its positions and folds when resampling. Report interval estimates conditional on the observed tubes and count distinct vines separately from vine-by-fold realizations.

For a survey with multiple reflections, check the spatial symmetry of the observer as well as the empirical support available to fit a signed contrast. Report whether mirrored locations were sampled. A signed feature in a branching decision can change individual realized geometries even when its linear contribution cancels in a reflection-averaged field. Comparing signed and sign-deleted fields on the same root decisions and comparing fine, middle and coarse diameter classes by sector help distinguish directional effects from a persistent diameter-class mismatch.

Core dry weight can supply another auxiliary field. Divide the independently recorded dry mass of the relevant sorted fraction by actual sampled soil volume, verify the recorded density and preserve true zero values. Fit the dry-matter field and its coupling to qualifying-RLD residuals using the nested whole-tube procedure above. Report its transfer against a depth-only auxiliary predictor, against the original vine-only placement rule, and against the physically matched reference architecture. Distinguish a sampled mass per soil volume from whole-vine dry mass and from root-tissue density.
