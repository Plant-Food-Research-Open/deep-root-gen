# How DeepRootGen scores candidate architectures

## Physical core comparison

Lower loss means closer agreement with the measured distribution of qualifying roots. In the placement study, the simulator measures root length inside a finite cylinder at the actual tube location and depth interval, applies the field diameter band, and divides by the sampled volume. Predictions are averaged over matched simulated vines and the study's spatial reflections before calculating the main loss. The study retained measured zeroes, excluded unsampled sections, and held out complete tubes. Coordinate alignment, diameter bands, neighbours and sampled volumes are part of the observation definition. [Core observation operator](../deeprootgen/research/core_observation.py) · [Placement experiments](research/PLACEMENT_EXPERIMENT_OPTIONS.md)

| Component | Weight | What it charges |
|---|---:|---|
| Normalized absolute RLD error | 50% | The weighted mean of `abs(observed RLD − predicted RLD)`, divided by the weighted **training-tube** mean observed RLD. |
| Joint tube-by-depth total variation | 25% | Half the absolute difference between observed and predicted weighted RLD shares across all tube sections. It detects roots placed in the wrong tube at the same depth. |
| Depth-profile total variation | 25% | Half the absolute difference between shares summed within common physical depth bands. It detects roots placed too shallow or too deep. |

A tube has the same total statistical weight as every other tube. Each of its sampled intervals receives weight in proportion to its share of that tube's sampled volume. Both total-variation terms are one if one complete weighted profile is empty and the other contains qualifying roots. They are zero when both complete profiles are empty. The main score uses full weight in shallow soil and uncapped errors. Report gain as `100 × (1 − candidate loss / matched reference loss)` with matching seeds and observation support. The 10% research target refers to percentage reduction, alongside a mean 6–8 kg of dry underground mass including crown and rootstock, vine-level mass counts, and at least two percentage points fewer empty deep sections at 90–150 cm versus the paired rainfed reference. [Physical score implementation](../deeprootgen/research/core_placement_cost.py)

## Missed roots and false hits

| Observation | Prediction | Contribution to the main score |
|---|---|---|
| Positive RLD | Zero | The magnitude contribution uses the full observed RLD as its error. The joint share is missing at that section, and the depth term responds to any change in its layer's share. |
| Zero RLD | Positive | The magnitude contribution uses the full predicted RLD as its error. The joint share is misplaced, and the depth term responds to changes in its layer's share. |
| Positive RLD | Positive | The magnitude component charges the difference in length density. Two equally large positive and negative residuals have the same absolute-error cost at that section. |
| Zero RLD | Zero | The interval contributes zero absolute error. |

The current objective has no extra constant penalty for a missed hit. A large observed density costs more to miss than a tiny positive reading. The deep occupancy guard measures simulated empty sections before averaging across vines and reflections. As a separate diagnostic, **miss rate** counts simulated empties among field-positive sections, and **false-hit rate** counts simulated hits among field-zero sections. Report both so filling every cylinder cannot look like success on occupancy alone. A positive detection limit can be used for both fields when measurement quality supports one. The default diagnostic uses positive RLD as a hit. [Presence calculation](../deeprootgen/research/core_presence.py)

## Asymmetric and robust training costs

The main magnitude term uses symmetric errors. A separate recovery sensitivity charged 80% of the first 20% of overprediction relative to observed RLD. Further overprediction paid the full marginal cost. Underprediction and any prediction above an observed zero paid full cost. For example, a 10% overestimate paid 8% of the observed RLD and a 10% underestimate paid 10%. That experiment used a wider virtual cylinder. The effect of that score cannot establish how much material the physical corer recovered. [Virtual core and recovery assumptions](research/AREA_MEAN_CORE_METHOD.md)

Separate reranking tested half weight for 0–30 cm and capping the magnitude residual at 2.5 times the training mean. Those studies assessed the resulting candidates with the original physical score. If testing a dedicated missed-hit or false-hit penalty later, predeclare its two weights, use both terms, and compare against the published symmetric score on entire omitted tubes.

## Whole-root dashboard comparison

**Optimisation** compares uploaded numeric whole-root summaries with the native scalar model using selected distances. **Architecture Search** uses a saved schema-4 configuration, applies ranges to active controls, and compares the mean over paired seeds with each numeric whole-root target. It offers normalized MAE and normalized RMSE with adaptive Optuna TPE or fixed Latin-hypercube screening. It divides each residual by an explicit CSV scale or the target's absolute magnitude, using 1 for a zero target without a scale. The whole-root routes and the physical-core comparison use different observation supports. [Dashboard workflow](WEB_OPTIMISATION.md)
