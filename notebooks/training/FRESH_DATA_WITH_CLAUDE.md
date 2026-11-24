# Fit DeepRootGen to a fresh dataset with Claude Code

Keep a local notebook as the study record. Use the four [Claude prompts](CLAUDE_PROMPTS.md)
as separate steps. Claude helps interpret approved training summaries, map
patterns to implemented options and set up runs. DeepRootGen generates and
scores the candidates.

## 1. Check the data locally

Record the source and units, sampling design, target population and intended
prediction. Preserve the original data and save cleaning and conversion code
with the derived data. Choose the observation route before deciding what to fit.

| Supplied measurements | Checks and matching model output |
|---|---|
| Excavated or digitised architecture | Confirm the origin, units, parent links, root order, diameter measurements and completeness limits. Compare topology and traits on equivalent observed support. |
| Whole-root counts, lengths or dry mass | Confirm the vine or population represented, how counts were defined, and whether crown and rootstock are included. Use supported scalar statistics with matching units. Record per-vine variation alongside means. |
| Physical soil cores | Verify tube and section IDs, location relative to the row, soil-surface elevation, depth bounds, radius and sampled volume, root sorting and diameter band. Distinguish measured zero from unsampled and from below-detection values. Compare RLD on matching sections in cm root length per cm³ soil. |

Check integrity across the files locally, then freeze the split before
plotting patterns or suggesting search bounds. Reserve complete tubes for
spatial evaluation. Group all tubes associated with the same vine or
geographic block when the prediction concerns a new vine or location. For
whole-vine observations, reserve independent vines where the design permits.
Count the independent units in each split and keep the final field holdout
out of Claude's inputs and the model development process.

Using the development data, summarise counts, missing values, ranges and
outliers. For cores, plot RLD and field-hit fraction by depth and distance
from the row, with sample counts. Verify unusual observations against their
source. Score measured zeros and exclude unsampled sections. Document the
handling of below-detection measurements and report the chosen presence
threshold. The finite-cylinder implementation expects elevations to increase
upwards. Give each interval a unique section ID for intersection and retain
the physical tube ID for splitting and scoring. [Observation operator](../../deeprootgen/research/core_observation.py)

## 2. Describe the pattern and ask for a starting model

Write the target in field terms. For example, “The training summaries show
qualifying fine roots at 90–150 cm mainly within 50 cm of the row. I want a
configuration that reaches those depths while retaining the measured shallow
distribution and plausible whole-vine dry mass.” State the observation count,
uncertainty, diameter band and mass basis. Use the measured information to
constrain plausible settings. Treat the growth mechanism as a hypothesis.

Start Claude Code in a clean workspace containing public source and only
materials cleared for model-provider processing. Use
`claude --permission-mode plan` to preview its work. Plan mode limits what
Claude can change. It can still read and send context for inference.
[Claude Code data usage](https://code.claude.com/docs/en/data-usage) · [Claude Code permissions](https://code.claude.com/docs/en/permissions)

| Workflow | What Claude receives | Where the work runs |
|---|---|---|
| Invented or cleared example | Public source, invented fixtures or material explicitly cleared for model-provider processing | Claude Code can help run the approved local commands. |
| Restricted field study | A cleared development summary or an invented file with the same schema | Ask Claude for settings or a script. Apply them to private inputs in a plain local terminal or Jupyter session outside Claude Code. Keep field files, fitted JSON, tables, plots, command output and tracebacks there. |
| Final field assessment | The analysis plan can be shared as a template | Score the frozen configuration in the local study session. Keep the final field outcomes out of model selection. |

Ask Claude for a baseline and one or two alternative schema-4 configurations.
Require the exact setting paths, units, affected root orders, evidence for the
initial values and the expected observable change. Have it distinguish a
measured value, a plausible search range and a setting the data cannot identify.
For example, a shortfall at depth could justify comparing longer primaries,
a change to downward drift, or relocation of existing daughters. Inspect
these one at a time before combining them. Check each proposed path against the current
source and confirm that its consumer is active with `--explain-config`.
[Schema-4 guide](../../docs/NATIVE_EXECUTION.md)

## 3. Explore the baseline and alternatives in the interface

Run **Simulation** on the local dashboard with the base JSON. Open
**Active laws by order** in **Architecture Search** before choosing bounds.
Compare each change with the baseline at the same seeds. Inspect a few 3D
graphs and compare realized root counts, contour length, reach, branch sites,
diameter classes and dry mass as relevant. For field cores, project each graph
onto the measured sampling geometry locally and inspect the training
residuals and depth profiles. Use development folds during exploration.
Use **Core Comparison** on the reserved observations after the configuration
and construction law are frozen.

The same check can start in a terminal from the repository root.

```bash
python -m deeprootgen simulate --config examples/synthetic_minimal.json --explain-config
mkdir -p .runtime
review_dir=$(mktemp -d .runtime/training-review.XXXXXX)
python -m deeprootgen simulate --config examples/synthetic_minimal.json --outdir "$review_dir/baseline"
```

Proceed to fitting when the base and a planned comparison both run, the
intended output responds across paired seeds, and measured and simulated
values describe the same support. Keep the unchanged baseline for comparison.

## 4. Ask Claude to set up the optimisation

Give the last prompt a specific objective and a small trial budget. Review
the proposed commands and bounds after the preview. For authorised shareable
inputs, leave plan mode when ready and approve the specific local Python
command that runs the search. For restricted inputs, execute the reviewed
code yourself in the local study environment.

| Fitting question | DeepRootGen route |
|---|---|
| Which numeric settings fit supported whole-root scalars? | Use **Architecture Search** or call `run_architecture_search(request, outdir)` from the [lesson notebook](../grapevine_root_architecture/architecture_search_quickstart.ipynb). Use `validate_architecture_search(request)` for preflight. Give the runner a new local output directory. |
| Which construction law works better? | Make a separate base JSON for each law and resolve its active controls. Screen the law variants against the same reference with shared seeds, objectives and comparable budgets. Fit a small number of active numeric controls within each plausible variant. |
| Which settings improve root placement on physical tubes? | Use a local forward model with the declared core projection, training objective and [placement tools](../../docs/research/PLACEMENT_EXPERIMENT_OPTIONS.md). Fit any 3D coring surface on training tubes only and include a generic or zero-strength control. Compare daughter placement, birth probability and retention separately before testing combinations. The Dash **Core Comparison** page evaluates the already projected predictions. |

For a core-fitting pilot, ask Claude to prepare a small Python evaluator with
these steps. Review it first on an invented or cleared example.

1. Generate a graph for each proposed setting and seed using the current
   generator. Use the same simulator and list of seeds for the unchanged baseline.
2. Project the graph with the qualified observation operator. Confirm that
   the measured diameter band and sorting rules match the projection. Join
   predictions by unique section key and check every match before ordering
   predictions for the loss. Check mass and geometric constraints per vine.
3. Return a finite `loss` and component scores. Use
   [`score_core_placement`](../../deeprootgen/research/core_placement_cost.py)
   with a scale computed from the training tubes of each development fold.
   Compare law variants on development-fold results and record the number of
   fitted controls per variant. At final evaluation use the fixed development
   scale and the frozen model.
4. Try the unchanged baseline and a few named variants first. If a pilot
   warrants adaptive search, pass the reviewed evaluator to
   [`run_parameter_search`](../../deeprootgen/research/parameter_search.py).
   Its evaluator receives a parameter dictionary and the declared seeds and
   returns a result with `loss`. Keep the law name in the run identity. For
   example, compare native direction with a separately configured curvature
   law and tune downward drift only when it is active.

Use common seeds across candidates while searching. Start with a small
space-filling screen when trial coverage matters, or use TPE when a bounded
adaptive search is appropriate. Freeze the selected JSON and law before running
fresh seeds and held field positions. Fresh seeds test simulation variability.
Held positions test field transfer. Report each result separately.

Save the source revision, observation definitions and split, base and selected
JSON, candidate bounds, objective, seeds, trials including failures, and the
replayed outputs. For physical cores, report the matched baseline and candidate
spatial losses plus missed-hit and false-hit rates. If dry mass constrains the
fit, report its definition, mean, and vine counts below, within and above the
range. [Scoring and diagnostics](../../docs/ARCHITECTURE_SCORING.md)
