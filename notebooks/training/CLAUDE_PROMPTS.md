# Claude Code prompts for a fresh dataset

Replace bracketed placeholders with approved material. Start with the
[quickstart](QUICKSTART.md) to see what DeepRootGen should return on invented
inputs. Keep restricted data in the separate local workflow described in the
[fresh-data guide](FRESH_DATA_WITH_CLAUDE.md).

## 1. Check data and describe what to reproduce

> Here are my cleared training summary, column definitions and sampling details
> [insert]. I want to reproduce [root pattern and prediction goal]. List the
> evidence by depth, distance from the row, diameter class or root order where
> measured. For each pattern give a number or range and its sample support.
> Identify missing and zero observations, possible outliers, and any uncertain
> units, coordinates or sampling volumes. Separate what I observed from proposed
> biological explanations. Draft a short set of targets and questions I should
> confirm locally. Recommend the observation route and the matching model
> output. Use the development summaries only.

## 2. Recommend starting parameters and functions

> Use the current DeepRootGen source and schema-4 docs to map the confirmed
> targets to a simple baseline and one alternative construction law. For each
> proposal give the exact JSON setting path or research function, units, root
> order, initial value, plausible range and expected output. Distinguish values
> measured directly from values we would fit. Give me an editable base JSON
> based on a documented example. Cite the source file or schema section for
> each proposed path and flag any unverified path. Give the command to inspect its effective
> settings. Keep the candidate mechanisms as hypotheses. Pause before running.

## 3. Plan a manual comparison in Dash

> Using the reviewed JSON and my baseline results [insert cleared results],
> give me a short Dash exercise that changes one active control at a time.
> Specify the baseline and two values to try, shared seeds, what to look for in
> the graph and branch report, and what outcome would justify moving to fitting.
> Use the observation route we agreed on. Ask me to record the exported
> configuration and checks.

## 4. Run a bounded search using DeepRootGen

> The manual checks passed [insert checks]. My target and observation operator
> are [describe], with baseline [JSON], candidate law variants [list], active
> control bounds [list], loss [definition], shared training seeds [list],
> evaluation budget [trial count per variant] and output folder [new local
> path]. First show me the schema validation, planned commands and the
> evaluations this budget implies. Use the Python 3.10 DeepRootGen environment.
> Once I confirm the preview, run the bounded fit for invented or cleared
> development inputs only. For restricted inputs, deliver the script for
> local execution and stop there.
> Use `run_architecture_search` for supported whole-root scalars. For physical
> cores, use the agreed local forward projection and training loss. Keep the
> baseline and variant budgets comparable. Save the score components, failed
> trials and best replayable JSON. Report development baseline and candidate
> results, seed spread and checks actually run. Prepare a separate command
> for me to evaluate the frozen JSON on the reserved field split locally.

For a first live Claude-assisted exercise, use the invented whole-root example
and set the budget to five trials with seeds 0 and 1. Ask Claude to verify
the five trial rows and replay the selected configuration through the CLI.

Verify the replay command from the repository root with the example's actual
output path and a new destination.

```bash
python -m deeprootgen simulate --config /path/to/best-configuration.json --outdir /path/to/new-replay
```

## Review a parameter suggestion

For the invented first-order example, `parameters.primary_root_count` is an
appropriate count control. The fixture has `max_order = 1`, so there are no
laterals. Bounds of 2–4 are an exercise setting. For a field study, check
whether basal root counts were actually measured before selecting bounds.
A suggestion such as `parameters.deep_root_bias` needs a verified schema path
and an active consumer before it can be considered.
