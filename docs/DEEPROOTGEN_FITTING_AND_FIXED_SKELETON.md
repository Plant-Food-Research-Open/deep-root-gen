---
pagetitle: DeepRootGen fitting and fixed skeleton
geometry: a4paper,top=19mm,bottom=19mm,left=19mm,right=19mm
fontsize: 11pt
colorlinks: true
linkcolor: "teal!55!black"
urlcolor: "teal!55!black"
header-includes:
  - |
    ```{=latex}
    \usepackage{fancyhdr,tikz,titlesec}
    \usetikzlibrary{arrows.meta,positioning}
    \definecolor{headingink}{HTML}{184046}
    \definecolor{softfill}{HTML}{EDF3F3}
    \renewcommand{\familydefault}{\sfdefault}
    \pagestyle{fancy}
    \fancyhf{}
    \fancyfoot[L]{\footnotesize\color{headingink}DeepRootGen \enspace\textbar\enspace Fitting and fixed skeleton}
    \fancyfoot[R]{\footnotesize\thepage}
    \renewcommand{\headrulewidth}{0pt}
    \renewcommand{\footrulewidth}{0.35pt}
    \setlength{\footskip}{23pt}
    \setlength{\emergencystretch}{2em}
    \titleformat*{\section}{\normalfont\Large\bfseries\color{headingink}}
    \titleformat*{\subsection}{\normalfont\large\bfseries\color{headingink}}
    \titleformat*{\subsubsection}{\normalfont\normalsize\bfseries\color{headingink}}
    \AtBeginDocument{\hypersetup{pdftitle={DeepRootGen fitting and fixed skeleton}}}
    ```
---

# DeepRootGen fitting and fixed skeleton

**Companion to the model handbook · 20–21 November 2026 · Schema 4**

Use this guide to turn a study plan into a bounded fit, test placement on an unchanged root skeleton, and compare the resulting vines on whole soil tubes. The Friday–Saturday work added ways to change where daughters form or point, a bounded whole-root search in Dash and a page for comparing previously projected core predictions.

## Write the fitting plan

| Decide before running | Record in the plan |
|----------------------|------------------------------------------------------|
| What the observations represent | Whole-root counts, lengths or dry mass, or root length density (RLD) from physical cores. For cores, record soil surface, coordinates, cylinder radius, sampled intervals and volumes, diameter band, sorting rules and how neighbouring vines enter. Keep measured zeroes and distinguish unsampled intervals. |
| What is fixed and what can change | Save the baseline schema-4 JSON and select one mechanism to test. Name the root orders, active parameter paths, units and ranges. For a fixed-skeleton fit, record which biological axes, attachments and material stay fixed and what the optional axes can do. |
| Which comparisons answer the question | Include the unchanged reference and a matched unguided control. For spatial guidance, compare depth-only and depth-plus-horizontal terms under the same proposal and material rules. Match count or mass when the question is about placement alone. |
| How the search and assessment are separated | Set development tubes, whole-tube omissions, search seeds, fresh assessment seeds, trial budget, loss and required mass or coverage checks. Hold every interval of a tube together. Freeze the chosen configuration and rule before the final comparison. |

The plan is a study record. Translate it into a schema-4 baseline, a bounded search request or a local research evaluator, and a split definition. If using Claude Code Plan mode, review the proposed commands, paths and trial budget there. Run restricted field work locally using the reviewed scripts and keep field inputs, fitted parameters and outputs in the local study.

### Choose the entry point

| Question | Entry point |
|----------------------|------------------------------------------------------|
| Which numeric controls match supported whole-root summaries? | **Architecture Search** in Dash or its local notebook. Fit one schema-4 law variant per search. |
| Which placement or retention rule improves RLD on physical tubes? | Local research fit using the finite-cylinder observer and training-fold scoring. Use the fixed-skeleton procedure on page 3 when the parents should stay fixed. |
| How well do frozen core predictions agree with measurements? | **Core Comparison** in Dash, using predicted RLD already aligned to held sections. |

Planning references · [Study worksheet](../notebooks/training/STUDY_WORKSHEET.md) · [Fresh-data workflow](../notebooks/training/FRESH_DATA_WITH_CLAUDE.md)

```{=latex}
\newpage
```

## Run a small whole-root fit

### Try the invented example

1. Open **Architecture Search** and upload `examples/synthetic_minimal.json`. Under **Active laws by order**, inspect the laws inherited from that file.
2. Set **Primary root count** to **2–4**. Use the following invented target. The one-order example has a target of three roots.

```csv
statistic_name,statistic_value
root_number,3
```

3. Choose **Normalized MAE**, **Adaptive Optuna TPE**, five trials, two startup trials and simulation seeds **0, 1**. Select **Check setup** to validate without dispatch. Select **Run search** to submit to the configured Prefect worker. In the local notebook, the same setup runs directly through Python.
4. Read the trial states and losses, then export the best JSON. The synthetic fixture expects five completed trials, three primary roots and zero loss. Run again with **Latin-hypercube screening** to try a fixed design with the same bounds, targets and simulation seeds.

### Understand the search result

| Item | How to use it |
|----------------------|------------------------------------------------------|
| Normalized MAE or RMSE | The worker averages predictions over the supplied seeds, then scales each residual by the CSV `scale` if supplied. Otherwise it uses the absolute target, or 1 for a zero target. Set a positive scale if a specific error tolerance should govern a target. |
| TPE or Latin hypercube | TPE adapts after startup. Latin hypercube distributes proposals through the ranges without using previous losses. The bounded route accepts 2–60 trials, up to six ranged controls and up to four distinct seeds. |
| `trials.csv` and `summary.json` | Review completed and failed trials before using the selected configuration. Save the request, seeds, method and output directory with the study plan. |
| `best-configuration.json` | The best trial's replayable configuration uses the first simulation seed. Assess the frozen settings across fresh seeds for a population comparison. |

To replay locally, run from the repository root with the project Python 3.10 environment. Substitute the actual search directory for `FIT_DIR`.

```bash
python -m deeprootgen simulate \
  --config "$FIT_DIR/best-configuration.json" \
  --outdir "$FIT_DIR/replay"
```

Local API · Pass the request to `validate_architecture_search` for a settings check. Pass the request and a new output directory to `run_architecture_search` to fit. The [notebook](../notebooks/grapevine_root_architecture/architecture_search_quickstart.ipynb) assembles the request. The [Dash guide](WEB_OPTIMISATION.md) covers the worker and exports.

```{=latex}
\newpage
```

## Fit placement on a fixed skeleton

Here the skeleton is the **generated, connected proximal graph** held fixed for a paired comparison. In the carrier experiment, that means the crown and orders 1–3 of each seed. Optional order-4 daughters on order-3 parents carry their full descendant subtrees. A terminal-only comparison instead fixes orders 1–4 and varies individual order-5 axes. Write the boundary into the plan.

```{=latex}
\begin{center}
\begin{tikzpicture}[
  box/.style={draw=headingink, rounded corners=2pt, fill=softfill, inner sep=5pt,
    align=center, text width=32mm, minimum height=13mm, font=\small},
  flow/.style={-{Latex[length=2mm]},line width=.55pt,draw=headingink},
  node distance=4mm]
\node[box] (fixed) {Fixed crown and\newline proximal axes};
\node[box,right=of fixed] (bank) {Bank optional axes\newline and descendants};
\node[box,right=of bank] (rule) {Fit a shared rule\newline on training tubes};
\node[box,right=of rule] (replay) {Realize whole vines\newline and score held tubes};
\draw[flow] (fixed) -- (bank);
\draw[flow] (bank) -- (rule);
\draw[flow] (rule) -- (replay);
\end{tikzpicture}
\end{center}
```

1. **Generate and save the bank.** Keep the seed, crown and fixed axis IDs, parent IDs, contours and taper profiles. Grow optional axes before projecting them onto cores. Save each option's parent link, qualifying length per section, dry mass and seeded draw. Build an all-retained reconstruction and check it against the full generated vine. Node subdivisions may differ where extra daughters attach, so compare physical contours as well as graph identities.
2. **Fit the rule.** Project the fixed axes and each complete optional axis or subtree onto the same physical sections. Fit shared retention, branching or placement coefficients using training tubes only. The same random draw per biological option is shared across paired selection rules, sections and reflections. For the location-only question, compare a uniform control matched to the relevant realized count or material budget.
3. **Realize and remeasure.** Keep or remove a complete terminal axis or carrier subtree. When retention is conditional, retaining a daughter also requires retaining its carrier. Check parent closure, feasible attachments, dry mass and the presence of roots on each complete realization. Recompute intersections whenever courses, taper or diameter eligibility change.

### Why expected RLD and occupancy need separate checks

Suppose a section has no fixed roots and two optional axes can reach it. Each contributes **0.02 cm/cm³** when retained. If each survives independently with probability 0.5, the expected RLD is **0.02 cm/cm³** and the hit probability is **75%**. Survival of daughters on a shared carrier is linked. Calculate occupancy on realized vines before averaging.

### Which kind of skeleton can be used?

The [placement experiments](research/PLACEMENT_EXPERIMENT_OPTIONS.md) document the local generated-bank workflow. The [terminal utility](../scripts/research/realize_terminal_recruitment.py) grows a compatible five-order potential vine and exports retained axes to NPZ by birth depth. Run the example twice with the same seed and distinct filenames. Set the deep probability to 1 for the all-retained control.

```bash
python -m scripts.research.realize_terminal_recruitment \
  --config examples/research/native_cohort_synthetic.json --seed 101 \
  --deep-probability 0.7 --midpoint-cm 30 --output .runtime/terminal-07.npz
```

For measured inputs, schema 4 supports selected [crown origins and complete primary headings](NATIVE_EXECUTION.md). General measured-lateral import and tip continuation remain proposals. [SO4 INITIAL replay](research/SO4_CONTROLLED_METHOD.md) is a separate archived comparison.

```{=latex}
\newpage
```

## Select a spatial construction treatment

Use a separate baseline JSON per construction law and verify the active paths with `python -m deeprootgen simulate --config FILE --explain-config`. Run each candidate and its control at the same seeds. A native configuration change can regenerate the architecture. Use the fixed bank when the experiment calls for holding all proximal geometry constant.

| What changes | Schema-4 control and paired comparison |
|-------------------------|---------------------------------------------------|
| Where existing daughters attach | `daughter_placement` with `redistribute` weights eligible movable sites on the parent and preserves count and the anchored first daughter. Compare neutral placement on the same eligible contour. |
| Whether a parent branches | `branch_probability` changes parent branching odds using a frozen profile. Keep the conditional count law and include the uniform odds control. Inspect realized counts because matching expectations can still give different vines. |
| Whether terminal daughters persist | `retention` varies terminal survival. Compare with partially retained uniform survival so both increases and decreases are possible. For a bank of complete mature paths use the local research procedure on page 3. |
| Extra daughters and where they are spread | Compare depth-targeted `add` against `uniform_extra`. For sparse trials, `sparse_depth_balanced` spreads a matched number of deep recruits among eligible parent sites using horizontal cells. Compare with `sparse_depth`. |
| Bearings and sibling placement | `surface_bearing` uses a frozen `vineyard_3d_v1` preference for selected daughter orders. It guides bearing with the configured insertion angle. `sibling_sectors` distributes sibling bearings around a parent in contour windows. `stratify_distal_sites` separately spreads births along the parent. |
| Moving selected shallow births deeper | `birth_depth_transfer` moves eligible buds on their own curved parent before final direction and descendants. It preserves the first anchor for count-based branching. Compare transfer off and inspect moves versus failures to find compatible contour. |
| Response to a wet zone | `irrigation` describes a surveyed footprint. Compare `add`, `uniform_extra` with matched count draws, or count-preserving `redistribute`, against rainfed. Specify outlet depth and distances in centimetres. |

### Pair the geometry and observer

Use `neighbourhood --mode independent` and `--mode translated` for the same crown offsets when testing neighbour effects. Read `plants.csv` for placements and seed identities. Match both versions to the same physical tubes and keep their coordinate frames, diameter and biomass definitions aligned.

Inspect `execution.json` and `branching.json` for realized geometry and decisions; where active, inspect irrigation and birth-transfer diagnostics. Check counts, depth reached, eligible and accepted sites, and root mass before viewing aggregate RLD.

The local research comparisons also tested turning entire attached subtrees, reallocating terminal length under a fixed mass budget, and adding coarse proximal material while preserving the sampled fine-root profile. Reproject realized geometry and report the attained mass and any deficit. These are separate treatments from the schema-4 controls above.

Configuration references · [Schema-4 execution](NATIVE_EXECUTION.md) · [Irrigation and spacing](research/IRRIGATION_INPUTS.md) · [Placement experiment controls](research/PLACEMENT_EXPERIMENT_OPTIONS.md)

```{=latex}
\newpage
```

## Evaluate a frozen fit on physical cores

1. **Match the physical support.** For every realized vine or neighbourhood, measure qualifying contour inside each actual cylinder and divide by sampled soil volume. Match cylinder position, sampled depth, filtering and observed root class. Join measured and predicted rows by tube and interval. Preserve the same geometry and study split for every candidate.
2. **Score the frozen candidate and its paired reference.** Estimate any spatial preference and the RLD normalization from training tubes only. Fit the rule there, then reuse the frozen coefficients and scales on omitted tubes. Use fresh paired simulation seeds to check Monte Carlo stability and whole held positions to test spatial transfer.
3. **Report multiple responses.** Keep the aggregate score, deep empty-section rate, conditional misses and false hits, mean RLD in occupied sections, and dry mass per vine. State how the crown or rootstock is counted, show the numbers below, within and above the study's mass range, and retain trial and replay records.

### The physical spatial score

| Weight | Measures |
|---------|-------------------------------------------------------------------|
| 50% | Mean absolute RLD error normalized by the weighted **training-tube** mean observed RLD. |
| 25% | Total variation of the joint tube-by-depth shares. |
| 25% | Total variation of the depth-profile shares. |

Each tube carries equal total weight, apportioned to its intervals by sampled volume. Report relative loss reduction against the same-seed reference. A hit requires RLD strictly above the common presence threshold, which defaults to zero. A miss occurs when only the measurement is a hit. A false hit occurs when only the prediction is a hit. For per-realization diagnostics use `core_presence` on the individual vine or reflected fields before averaging. The continuous loss uses the mean prediction field in the placement study.

### Try Core Comparison and keep the fit auditable

Open **Core Comparison** and upload `examples/research/core_comparison_synthetic.csv`. Compare the exact prediction with the candidate that misses a hit. The uploaded CSV contains `split`, `candidate`, `core_id`, `z_lower_cm`, `z_upper_cm`, `core_volume_cm3`, `rld_est` and `predicted_rld`. The page checks that train and held tube IDs are disjoint and that every candidate has the same held sections and observations. Its hit rates describe the uploaded field.

Archive the plan, baseline and resolved configuration, split and units, all seeds, search and realization receipts, held predictions, and a paired control report. Saturday's saved checks show that the bounded whole-root fit ran on invented targets and that an archived local study exercised adaptive fitting on projected cores. The archived core trial verified execution. Transfer gains varied by assessment panel, and the fitted rule remained experimental.

Scoring references · [Score definitions](ARCHITECTURE_SCORING.md) · [Finite-cylinder observer](research/FINITE_CORE_RESEARCH.md) · [Dash and CSV examples](WEB_OPTIMISATION.md)

<!-- From the repository root, rebuild the print layout with:
pandoc --standalone --pdf-engine=pdflatex docs/DEEPROOTGEN_FITTING_AND_FIXED_SKELETON.md
-o output/pdf/DeepRootGen_Fitting_and_Fixed_Skeleton.pdf
-->
