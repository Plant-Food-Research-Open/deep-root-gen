# DeepRootGen dashboard examples

These examples use invented inputs. Start with Simulation, then reuse its model and outputs in the other screens. The links below are route paths on the supported local Dash URL, **http://127.0.0.1:18003/** when started as in [the dashboard stack](../RUNNING.md#dashboard-stack-supported-local-startup). Every example below was run on that stack on 23 November 2026; see [the verification record](#verification-record-23-november-2026).

## Pick a page

| Page | Route | Input | Result to look for |
|---|---|---|---|
| [Simulation](#1-simulation) | `/` | Schema-4 root configuration | One generated root graph and its summaries |
| [Exploratory Data Analysis](#2-exploratory-data-analysis) | `/eda` | Node CSV | Plots of graph attributes and summary statistics |
| [Optimisation](#3-optimisation) | `/optimisation` | Scalar target CSV and parameter ranges | Trial history and the best scalar fit |
| [Architecture Search](#4-architecture-search) | `/architecture-search` | Saved schema-4 JSON, active ranges and pasted CSV | Trial table and replayable best JSON |
| [Core Comparison](#5-core-comparison) | `/core-comparison` | Aligned predicted and observed core RLD CSV | Held-tube loss and occupancy diagnostics |
| [Sensitivity Analysis](#6-sensitivity-analysis) | `/sensitivity_analysis` | Scalar target CSV, ranges and Sobol sample size | Sensitivity indices for the selected discrepancy |
| [Approximate Bayesian Computation](#7-approximate-bayesian-computation) | `/abc` | Scalar target CSV, prior ranges and run budget | Accepted populations, particles and distances |
| [Sequential Neural Posterior Estimation](#8-sequential-neural-posterior-estimation) | `/snpe` | Scalar target CSV or a paired node/edge upload | Posterior draws and checks |
| [Surrogate Model](#9-surrogate-model) | `/surrogate` | Scalar target CSV, feature ranges and split sizes | Cost emulator and split metrics |
| [Deployments](#10-deployments) | `/deployments` | Installed Bento model and model-specific inputs | Prediction or previously computed result as CSV |

Every worker-backed page has **Check setup**, which validates the form and shows what would run without submitting anything, and **Run** (*Run procedure* or *Run search*). After Run the message names the run UUID and links to Prefect. **Queued** means Prefect accepted it; **Already queued** means the identical request was accepted before and no second run was started (change the tag, seed or any input for a new run). Errors name their class: invalid form (fields listed, nothing submitted), *Prefect is unreachable* or *Deployment missing* (nothing submitted), or *Submission result uncertain* (click Run again without changing the form; it returns the same run). The message stays until dismissed. The run table's **State** column follows the run and on completion names the MLflow run and its artifact count; a failed run says to open its worker log. Architecture Search shows the same states in its own status line and serves downloads from the app and worker's shared output directory.

## 1. Simulation

1. Click **Load parameters** and choose [synthetic_minimal.json](../examples/synthetic_minimal.json). Loading replaces the form inputs. The uploaded config represents two primary roots of order 1, five segments per root and seed 42. Leave both optional fine-root targets blank. A structured daughter-count range from the file can appear under **Advanced settings (JSON)** with its numeric field blank. Leave it there for this example.
2. For this exercise, leave **Enable soil** off. Click **Check setup**: *Setup is valid. Nothing was submitted. Schema 4 · seed 42 … 2 primary roots · Fine-root targets: none*. Click **Run procedure**: *Queued: simulation run <UUID>*. The row's State becomes *Completed · MLflow run <id> · 15 artifacts* within about 10 s; the MLflow run under `root_model_simulation` carries the same UUID tag.
3. Open the root plot and inspect the timestamped `*_nodes.csv` and `*_edges.csv` files. The small reference architecture has **11 nodes and 10 edges**, including the base node. Save the node CSV for EDA and keep the corresponding edge CSV if trying a graph input.
4. **Save parameters** downloads the current schema-4 JSON. **Save simulation runs** exports the visible run-history table; its CSV contains job links and tags. Use the associated MLflow run for graph and statistics artifacts. Clear-history controls affect the browser's table.

**Validation example.** Type `0.5` in **Target fine-root length fraction** without allocation controls and click **Check setup**: *Check the form. Nothing was submitted.* with the reason *Root ratio targets and their allocation_controls must be supplied together* and a hint that both fractions are optional values in [0, 1]. Clear the field to continue.

**Example with a fine-root target.** Use **Load parameters** with [native_allocation_targets.json](../examples/design/native_allocation_targets.json). It pairs a length target of `0.5` and a biomass target of `0.1` with order-2 scale bounds. The bounds belong in `parameters.allocation_controls` in **Advanced settings (JSON)**. Enter a target in the form or JSON once. To switch off targeting, clear both fraction inputs and remove the allocation controls from the JSON. A fraction of `1.0` means 100%. The reporting diameter remains the upper bound of the fine-root class in the summary.

## 2. Exploratory Data Analysis

1. Click **Load simulation data** and choose the node CSV from Simulation. You can also use `nodes.csv` from [the offline CLI example](../RUNNING.md#cli-and-outputs).
2. Choose **X axis** `diameter`, **Y axis** `length`, and **Group by** `order`. Inspect the X/Y histograms and box plots, scatter plot and heatmap. Coordinates and diameters in the node export are in centimetres.
3. Choose **X summary statistic** **Total Length** and **Y summary statistic** **Average Diameter** to inspect summaries of the uploaded table. A single generated tree is enough to see the plotting route. Use **Clear simulation data** before switching to a different input.

Use the **node** CSV for these charts. Parent/child connectivity comes from the matching edge table. For field comparisons, use the same exclusions and observation support as the intended metric. EDA charts require no Prefect flow.

## 3. Optimisation

1. Click **Load statistics data** and upload [optimisation_summary_synthetic.csv](../examples/research/optimisation_summary_synthetic.csv), which sets `root_number` to 3.
2. Start with the [synthetic range preset](../examples/research/ui_calibration_ranges_synthetic.yaml) using **Load parameters**, or use the ranges table below. In Parameters, fix **Maximum order** at `1–1) and **Segments per root** at `5–5`. Set **Primary count** to `2–4`. Set the other bounds to compatible values or leave the preset's narrow ranges. Ensure the highest minimum length is no greater than the lowest maximum length for each of primary and lateral roots.
3. Select **Root Number** and **Mean Absolute Error**. Leave the soil-layer and soil-column switches off. Set **Trials** to 5, **Startup trials** to 2, **Number of parallel trials** to 1 and **Random seed** to 0.
4. Click **Check setup** to validate, then **Run procedure** to submit. Inspect the trial CSV and history plot in the matching MLflow run after completion. The fixture's known optimum is three primary roots with loss zero. Check which counts were actually tried if a finite sampler returns a different result.

The [web optimisation guide](WEB_OPTIMISATION.md#start-with-a-synthetic-fit) records a test-harness run with real local MLflow artifacts and substitutes for graph and registry writes.

## 4. Architecture Search

1. Click **Load architecture JSON** and select [synthetic_minimal.json](../examples/synthetic_minimal.json) or the same configuration exported by Simulation. Check **Active laws by order** shows order 1.
2. Set the **Lower** and **Upper** cells for **Primary root count** to `2` and `4`. Leave other bounds blank.
3. Paste the following into **Targets and trials**. Commas, tabs (a direct spreadsheet copy), semicolons or runs of spaces are all accepted as separators.

```csv
statistic_name,statistic_value
root_number,3
```

4. Choose **Adaptive Optuna TPE**, **Normalized MAE**, 5 trials, 2 startup trials and seeds `0, 1`. **Check setup** shows *Setup is valid. Nothing was submitted. 1 controls · 1 targets · 5 trials × 2 seeds*. Click **Run search**; the status reaches *Completed · 5 trials completed · 0 failed · best loss 0* in a few seconds.
5. Once complete, download **Best configuration** and **Trial table**. Review failed as well as completed trials. The known example returns three primaries and normalized loss zero. Replay the best configuration in **Simulation → Load parameters** to see one graph using the first search seed. Switch to **Latin-hypercube screening** to repeat the exercise with a fixed sampling design.

An optional positive CSV column called `scale` sets the denominator for the residual of that target. The [fitting and fixed-skeleton guide](DEEPROOTGEN_FITTING_AND_FIXED_SKELETON.md) covers experimental planning and the separate local soil-core fitting route.

## 5. Core Comparison

1. Click **Load core CSV** and choose [core_comparison_synthetic.csv](../examples/research/core_comparison_synthetic.csv). Use the default presence threshold of `0 cm/cm³` and click **Compare candidates**. The fixture has one training tube and one held tube, with the same held observation supplied for both candidates.
2. Inspect the **exact** prediction, which has loss 0 and misses no observed hits. The **miss** candidate predicts zero where the held measurement is positive. Its diagnostic miss rate is 100%. A false-hit rate is undefined when the comparison has no observed-empty sections.
3. Try a positive presence threshold to see how hit/miss calls change. The continuous loss uses the original RLD values. Use a new upload to compare candidates projected on another held set.

Required columns are `split,candidate,core_id,z_lower_cm,z_upper_cm,core_volume_cm3,rld_est,predicted_rld`. Training and held sets must have disjoint tube IDs. Keep every candidate's held tube/interval keys, volumes and measured RLD identical. This page consumes **precomputed** predictions in cm/cm³. See [physical-core scoring](ARCHITECTURE_SCORING.md).

## Calibration exercise inputs

For Sensitivity Analysis, ABC, SNPE and Surrogate Model, click **Load statistics data** and choose [ui_total_length_synthetic.csv](../examples/research/ui_total_length_synthetic.csv). The invented 50 cm target describes total whole-root length. For exact bounds, use **Load parameters** with [ui_calibration_ranges_synthetic.yaml](../examples/research/ui_calibration_ranges_synthetic.yaml). Check the values and switches after loading. Use **Total Length** as the selected statistic, **Mean Absolute Error** wherever a distance menu is present, seed 0, and turn off soil-layer and soil-column comparisons. Each exercise below completed on the worker on 23 November 2026 with these settings. Press **Check setup** first; it lists the varying ranges, statistics and settings. The page rejects zero-width ranges where the method needs width (Sobol, SNPE, the surrogate's sampled features and ABC's continuous priors) and names the parameter.

```csv
statistic_name,statistic_value
total_length,50
```

Use the following small nonzero-width ranges for samplers and priors that require increasing bounds. They keep long and short length intervals separated. The exact endpoint treatment of discrete settings is method-specific. These are software-exercise ranges.

| Control | Lower | Upper |
|---|---:|---:|
| Maximum order | 1 | 3 |
| Reporting diameter (cm) | 0.05 | 0.07 |
| Primary count | 2 | 5 |
| Outer placement fraction | 0.4 | 0.6 |
| Primary root minimum length | 18 | 21 |
| Primary root maximum length | 27 | 30 |
| Base root diameter | 0.10 | 0.12 |
| Native cylinder endpoint (cm) | 0.02 | 0.03 |
| Diameter reduction | 0.15 | 0.25 |
| Daughters per parent | 1 | 3 |
| Daughter-count increase by order | 0.1 | 0.2 |
| Secondary root minimum length | 8 | 10 |
| Secondary root maximum length | 14 | 18 |
| Segments per root | 4 | 6 |
| Length reduction | 0.4 | 0.5 |
| Root segment variance | 20 | 30 |
| Interbranch distance | 0.006 | 0.009 |
| Root tissue density | 0.04 | 0.06 |
| Gravitropism factor | 0.08 | 0.12 |

### 6. Sensitivity Analysis

Use the total-length CSV and the ranges above. Set **Samples** to 4 and **Number of parallel simulations** to 1. Run the procedure and find the `*_sobol_samples.csv`, `*_total_si.csv`, `*_first_si.csv` and `*_second_si.csv` in MLflow. Samples is the Sobol base count. With 19 inputs and second-order sampling the flow evaluates 160 settings at base size 4. Inspect the sample discrepancy and whether the index table is finite. This size exercises the route. In a scientific study the sample size needs a separate convergence check.

### 7. Approximate Bayesian Computation

Use the same target and prior bounds. Start with **Number of particles** 4, **Maximum population size** 1, **Maximum simulations** 80, **Maximum walltime** 2 minutes and **Minimum epsilon** 0.1. The form label **Maximum population size** maps to the number of populations the worker may run. Open the population, particle and distance CSVs after the flow completes. Check that a population was accepted and how many simulations the procedure used. A budget exhausted before acceptance is informative about this setup. It gives no usable sample for the Deployments example.

### 8. Sequential Neural Posterior Estimation

1. Use the total-length CSV and shared ranges. Turn on **Use summary statistics** and select **Total Length**.
2. For a bounded integration exercise, set **Number of simulations** to 64, **Posterior predictive samples** to 10, **Calibration samples** to 10, **Number of hidden features** to 5 and **Number of transforms** to 2. The current summary-statistic branch calls the library's default training routine. A small simulation count alone does not cap its training time.
3. Inspect the corresponding MLflow run for posterior samples and predictive diagnostics. Check actual completion and sampled parameter values.

**Graph input example.** To exercise input setup, switch **Use summary statistics** off and upload the corresponding Simulation node and edge CSVs under **Load simulation data** and **Load edge data**. **Check setup** requires both uploads and the columns `node_id,parent_id` (nodes) and `parent_id,child_id` (edges). Graph-mode SNPE training was not run in this verification, and **served graph inference is not implemented**: the SNPE service answers such a model with *Not supported by the served model*.

### 9. Surrogate Model

1. Load the total-length CSV, turn on **Use cost emulation** and select **Total Length** and **Mean Absolute Error**. Set the shared ranges. To sample a small feature subspace, choose **Primary root minimum length** and **Primary root maximum length** under **Include parameters**. Other sampled-model settings take interval midpoints when omitted by that filter.
2. Set **Number of simulations** to 16, **Number of validation simulations** and **Number of holdout simulations** to 4 each, **Number of epochs** to 5, **Number of inducing points** to 8, and leave **Learning rate** at 0.01. Run with the small synthetic budget.
3. Look for samples and the training, validation and holdout metric and prediction tables. Check that the model artifact has a feature signature before trying to serve it (here `min_primary_length`, `max_primary_length`). The implemented training branch emulates the discrepancy against the selected target. **Graph mode is not implemented for the surrogate:** with **Use cost emulation** off the flow would only log its configuration, so the page refuses with *Graph-mode surrogate training is not implemented*.

## 10. Deployments

This page calls optional BentoML services started with the `serving` profile ([RUNNING.md](../RUNNING.md#optional-model-serving)). Each completed calibration run imports its model into the shared store; restart a service after a new run to serve it. **Check model services** lists every service as *not running*, *no model* or *serving* with its model tag and the UUID of the run that produced it. Each call reports one of: *Model service not running*, *No model version to serve*, *Invalid input*, *Not supported by the served model* or *Model service error*; a success downloads a CSV and names the served model and its source run.

| Action | Example input | Check the downloaded CSV |
|---|---|---|
| **Optimisation calibrator** | Use the synthetic Optimisation result and set **Number of trials** to 1. | One requested best stored trial with its parameters and objective, when available. |
| **Sensitivity calibrator** | Serve the synthetic Sobol result. Select **Primary count** in **Parameter names**. | The total-order index row for `primary_root_count`. |
| **Bayesian calibrator** | Serve the ABC run with an accepted population. Set **Monte Carlo time step** to 0 if population 0 is present. | Particle rows for the selected population. |
| **Neural density calibrator** | Serve a summary-statistic SNPE model trained on the total-length example. Use **Load statistics data** with `ui_total_length_synthetic.csv` and check **Total length** is 50. | Posterior draws conditional on that scalar, using the served model's statistic names and order. |
| **Emulation calibrator** | Serve the cost emulator and use a valid prediction row in **Explicit trained features (JSON)**. Start from a row in its exported sample table, retain exactly the fields in the model signature and use numeric values. | The model's prediction for that row. Compare it with the served signature and check a finite result. |

**Deployment Links** opens each service's own page on its loopback port (5101–5105). All five calls above returned the described CSVs from models produced by the synthetic runs on 23 November 2026.

## When a click leaves no result

| Symptom | Check |
|---|---|
| Simulation reports that ratio targets and allocation controls must be supplied together. | Clear both targets and remove allocation controls for an untargeted run. If fitting fractions, pair the targets with feasible per-order scale bounds. |
| Architecture Search asks for CSV columns. | Paste comma-separated header and values exactly as in the example, then use **Check setup**. |
| *Deployment missing* | Re-register: `$P up prefect-deployments` (RUNNING.md). The older review container at 18002 had only Architecture Search and the stack at 18001 lacked it; use the supported stack. |
| *Prefect is unreachable* | `$P ps` and `$P logs prefect-server`; nothing was submitted, so retry after it is healthy. |
| *Submission result uncertain* | Click Run again without changing the form; the same run is returned rather than a duplicate. |
| The run stays scheduled. | The queue message warns when no worker polls pool `default`. Check `$P logs prefect-worker`; the worker runs one flow at a time, so later runs wait. |
| The run failed. | Open the Prefect logs and find the task that failed. Prefer the smallest synthetic fixture for reproducing a service or schema problem. |
| The run completed with no download. | Check the artifact in MLflow or the worker output directory, and confirm the web app can see the same shared output path for Architecture Search. Check browser downloads separately. |

## Verification record (23 November 2026)

Stack: Compose project `drg-dash-repair`, image `deeprootgen-local:dashboard`
`sha256:3a77faff1e21…` built from `57f6782` plus the uncommitted working tree
(build-input hash `2d877013…`, recorded in `.runtime/dash-repair-20261123/`).
**Browser** = real headless Chrome 155 via Playwright (`scripts/local/dash_browser_check.mjs`).
**Callback** = the browser's own `/_dash-update-component` requests, including
uploads, sent by `scripts/local/dash_workflow_check.py`; it shows the text a
page displays, not its rendering. Every worker run below reached its terminal
state on the real worker; no test double was used.

| Page / action | Method | Deployment | Run (UUID) | State | Result tied to the run |
|---|---|---|---|---|---|
| Simulation | Browser | simulation/run_simulation_flow | 23fa8583… | Completed | MLflow e06372c5: 15 artifacts; nodes/edges 11/10 (callback run 58555931…) |
| Optimisation | Callback | optimisation/run_optimisation_flow | 8ed6541c… | Completed | trials CSV: best trial 3 primaries, loss 0 |
| Architecture Search | Browser | architecture_search/run_architecture_search_flow | 33166af7… | Completed | 5 trials, 0 failed, loss 0; best JSON 3 primaries, seed 0 |
| Replay of that best JSON in Simulation | Callback | simulation/run_simulation_flow | (replay) | Completed | seed 0, 3 primary roots, 16 nodes / 15 edges |
| Sensitivity Analysis | Callback | sensitivity_analysis/run_sensitivity_analysis_flow | ec94ad9c… | Completed | 160 Sobol samples; 19 finite total-order rows; first/second-order CSVs |
| ABC | Callback | abc/run_abc_flow | 424b7d47… | Completed | population t=0 accepted, 4 particles; populations/particles/distances CSVs |
| SNPE (summary statistics) | Callback | snpe/run_snpe_flow | 1c8930ce… | Completed | diagnostics CSV, posterior model |
| Surrogate | Callback | surrogate/run_surrogate_flow | f5284810… | Completed | samples; train/validation/test metrics and predictions; signature of 2 features |
| EDA | Callback | none | — | — | 11 node rows; scatter, histogram, summary figures |
| Core Comparison | Callback | none | — | — | exact loss 0; miss loss 0.75, miss rate 100%, false-hit undefined |
| Check setup on all seven pages | Callback + Browser | — | — | — | valid message; Prefect run count unchanged (7 → 7) |
| Deployments: all five calls | Callback | BentoML `serving` profile | models from the runs above | — | 1 trial row (3 primaries); `primary_root_count` index row; 4 particles; 100 posterior draws; 1 finite prediction |

Failure paths exercised live: missing deployment (surrogate deleted, then
restored by re-registration; run count unchanged), Prefect API stopped (no run
created; recovered after restart with pool READY), identical double submission
(one run, second reply *Already queued*), failed-run State text (baseline failed
Optimisation run), stopped model service, and a service without a model version.
The *uncertain send* path, idempotent retry after it, and service 400/501/empty
replies are covered only by test doubles in `tests/test_dashboard_submission.py`.

Not verified: graph-mode SNPE training, served graph inference (not
implemented), graph-mode surrogate (not implemented), soil-layer/column
statistics, and Firefox/Safari rendering. Downloads in the browser run were
saved through Playwright's download event, not a desktop Downloads folder.
