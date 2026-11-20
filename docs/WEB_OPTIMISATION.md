# Explore and optimise root systems in Dash

## Start with a synthetic fit

Use the Dash, Prefect and artifact services described in [RUNNING](../RUNNING.md#docker-installation-and-local-ui). The **Simulation** page explores one configuration. It accepts schema-4 settings through the advanced JSON field and can export an editable configuration. Match the plotted soil frame, actual root lengths, dry-biomass summary and branching report to what you expect before changing search bounds.

Use **Optimisation** for an invented whole-root example. Upload [the synthetic summary](../examples/research/optimisation_summary_synthetic.csv), select **Root Number**, and choose **Mean Absolute Error**. In the parameter form, set both maximum-order bounds to **1**, both segment-count bounds to **5** and primary count to **2–4**. Keep other ranges narrow, or set equal bounds to their current values. Use seed **0**, five trials, two startup trials and one parallel job. For primary length, the greatest possible minimum must be no greater than the smallest possible maximum. The same constraint applies to the lateral lengths.

Select **Check setup** to verify the observations, active ranges and trial settings. Preview uses the input validator and returns the settings summary without submitting a job. To launch through the configured deployment, use the run button. Open its Prefect link to inspect the queued or running state and the worker logs. Look in the configured tracking output for the trial-history CSV and best graph only after the flow has finished. Compare completed trials and converged candidates before interpreting the best score. The expected minimum on the invented example is zero for a tree with three primary roots.

Use the CSV columns `statistic_name,statistic_value`. Values are numeric and use the simulator's units for the selected whole-root statistic. Prefer one metric at first. When selecting several metrics the worker sums those discrepancies. Save the ranges together with the seed, the original upload, the observed units and the final training result. The existing Dash form is intended for supported whole-root scalar comparisons. Local coring studies and canonical feature combinations use the documented research routes.

## Which controls belong on the starting screen?

| Control | Place in the interface | Explanation |
|---|---|---|
| Base architecture, number of primary roots, maximum order | Simulation and first search section | These change the size and organization of the crown-to-tip graph. Begin with total primary count. Keep order fixed when matching order-specific observations. |
| Primary length range in cm, downward bias, approximate daughter count | First search section | These have direct interpretations for reach, direction and branching. Numeric bounds should adapt to the selected construction law. |
| Lateral lengths, length reduction, bearing and insertion, branch spacing and site gate | Advanced search ranges | Enable only the controls consumed by the selected law. When changing a branch count or site, inspect the realized branching report. |
| Taper, base/tip dimensions, tissue density, reporting cutoff and dry-mass convention | Material or observation section | Keep measured values fixed by default in a spatial fit. Confirm the reporting cutoff independently of the physical branching threshold. |
| Soil coordinates, sampling geometry, diameter band and observations | Observation setup | Define and preview these before search. Show their physical units and count whole tubes, not just rows. Keep this panel tied to the actual observer. |
| Seed, trials, startup trials, per-run limits | Run budget | Give informative defaults and an explicit preview. Seed the trial sampler and keep one job when reproducing trial order. Show failed and completed counts. |
| Custom features and nested per-order parameters | Advanced schema-4 document | Validate through the same resolver as the CLI. Show why a parameter is active or superseded before giving it a search range. |

## Extend the interface in stages

1. **Promote the present scalar workflow.** Keep the preview and error display close to the run button. Begin with one active range and a synthetic upload. The current implementation checks ranges and target support and uses the configured Prefect deployment.
2. **Reuse canonical generation controls.** Load the Simulation page's saved schema-4 JSON as a fixed starting point. Build the searchable parameter list from the resolver's consumers, expose only deliberate overrides and show their effective model. Keep the base document and retain a replayable JSON for every candidate. Handle small seeds, failed trials and a resource ceiling using the local search machinery.
3. **Add a separate physical core workflow.** Provide an observation preview with the depth frame, soil volume, radius, units, diameter interval, treatment and whole-tube train/holdout assignment. Require explicit mass and deep-coverage settings for a study that uses them. Use the existing finite-cylinder or declared grid observer. The browser can show status, but local restricted observations need a local runner and local outputs. Offer loss components, paired reference losses, root distribution plots and biomass counts.
4. **Qualify automated runs.** Test preview without queuing, malformed input, workflow assignment, known best trial on a synthetic target, failed-trial recovery, best-config export and identical replay. Run end-to-end on a configured development stack before calling the UI integration ready. Independently assess held positions before promoting an empirical fit.

The [engineering handoff](tasks/WEB_OPTIMISATION_NEXT.md) scopes the next implementation slice and its checks. [Generator handbook](DEEPROOTGEN_HANDBOOK.md) · [Local alternative](research/NOTEBOOK_PARAMETER_SEARCH.md)
