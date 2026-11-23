# Statistical reference for DeepRootGen fitting

Use the measurement definition to choose a statistic. Record the unit,
eligible roots, sampling position, and how the statistic is aggregated before
setting a target.

| Measurement | What to compare | What to record |
|---|---|---|
| Root count and contour length | Number of qualifying organs and their lengths in cm | Unit of replication, parent order, completeness cutoff and invalid-axis treatment. A graph node is a point or segment record. Use organ identities to count roots. |
| Diameter and dry mass | Diameter distribution, integrated root volume and dry mass | Diameter bins in a single unit, tissue density, whether the crown and rootstock are included, and mass per vine. Report both mean mass and vine counts in each acceptance category. |
| Depth, lateral spread and order profiles | Root length by band or its share of total length | Same depths, origin, distance definition and bins. Keep overflow. Report absolute totals alongside shared profiles. |
| Root length density (RLD) | Qualifying root contour length within the sampled soil volume, in cm/cm³ | Actual core geometry, diameter class, row coordinates, treatment and whether the sample includes neighbouring vines. Preserve measured zeros and mark missing sections separately. |
| Presence and occupancy | Field-positive sections missed and field-zero sections predicted to contain roots | Detection threshold and denominators. Estimate occupancy per realization before averaging when the question concerns empty cores in individual simulated vines. |

Use the [summary statistic implementation](../../deeprootgen/statistics/summary_statistics.py)
and [physical observer](../../deeprootgen/research/core_observation.py) to
confirm units and support for the route you choose.

## Whole-root Architecture Search

The runner takes the mean prediction across the supplied seeds for each
target. It divides each residual by the positive target `scale`, or by the
absolute observed value if no scale is supplied. For a zero target with no
scale it uses 1. Normalized MAE averages the absolute scaled residuals.
Normalized RMSE takes the square root of the mean of their squares and
emphasizes relatively large errors.

For example, with a measured length of 100 cm and a tolerance scale of
10 cm, a prediction of 115 cm has scaled absolute error 1.5. With no
explicit scale the error is 0.15. Choose scales consistently before seeing
the fit. A candidate averaging three roots across two seeds can score zero
against a mean target of three even if its vines have two and four roots.
Check the per-vine distribution separately when it matters.

## Physical core comparison

The main loss is **0.50 × normalized MAE + 0.25 × joint tube-by-depth
total variation + 0.25 × depth-profile total variation**. Equal total
weight goes to each tube. Section weights within a tube follow sampled
volume. The magnitude scale is the weighted training-tube mean RLD.
Total variation is half the sum of absolute differences between the
observed and predicted length shares under these weights. Joint variation
is sensitive to which tube contains the roots. Depth variation looks at
the pooled distribution across common depth bands.

A missed observed root incurs its full RLD residual. False hits incur
their full predicted RLD residual. The magnitude component charges both
signs equally. Conditional miss and false-hit rates describe errors
among field-positive and field-zero sections respectively. An empty
denominator makes a rate undefined. Altering the diagnostic detection
threshold leaves the continuous loss unchanged.

Compare candidates on the same observed and predicted support. Use an
unchanged baseline and calculate percentage gain as
`100 × (1 − candidate loss / baseline loss)` when the baseline loss is
positive. Report the signed change and the components as well. If testing
shallow weights, residual caps, or asymmetric penalties during search,
record the settings and evaluate the selected configuration against the
same fixed reporting score. [Detailed scoring](../../docs/ARCHITECTURE_SCORING.md)

## Choose the method and the check

| Method | Use it for |
|---|---|
| Named variants with paired seeds | Testing one change such as turning a placement rule on and off. Inspect the intermediate geometry before fitting ranges. |
| Latin-hypercube screening | Exploring continuous bounds with a fixed, space-filling design. A tighter follow-up range should be supported by development results. |
| Optuna TPE | Adapting proposals to earlier losses after startup. Record the budget and failures, and keep several trials after startup. |
| Sensitivity or inference | Sensitivity asks which inputs drive variation under the declared ranges. Inference asks which parameter combinations remain plausible under the model and observation assumptions. See the [full handbook](../../docs/DEEPROOTGEN_HANDBOOK.md) for the additional workflows. |

Use the same seeds for paired candidate comparisons, then assess the
frozen choice on fresh seeds. For claims about field transfer, hold out
entire tubes, vines or geographic blocks as appropriate. Use the development
data for all rule selection, surface fitting and bounds. Where the sample
supports it, summarize spread across vines or blocks, or resample at that
level. Depth sections inside one tube share sampling context.
