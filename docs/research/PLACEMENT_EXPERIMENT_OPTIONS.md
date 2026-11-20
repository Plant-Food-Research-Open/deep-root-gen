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
