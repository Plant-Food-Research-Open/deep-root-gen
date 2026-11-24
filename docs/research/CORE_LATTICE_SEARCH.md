# Lattice core score and search

An opt-in research pipeline compares simulated vines with soil-core root length density (RLD) and searches configuration parameters against that comparison. It does not qualify a model. Its two modules are `deeprootgen/research/core_lattice_scoring.py` (the score) and `deeprootgen/research/core_lattice_search.py` (the search driver). It is selected with its own command:

```bash
python -m deeprootgen core-search --spec spec.json --stage arms --name W1 --outdir runs/search
python -m deeprootgen core-search --spec spec.json --stage space --outdir runs/search
python -m deeprootgen core-search --spec spec.json --stage tpe --outdir runs/search
python -m deeprootgen core-search --spec spec.json --stage confirm --outdir runs/search
```

## Score

- **Diameter band.** Observed and simulated length are compared in one root-diameter band. Simulated length counts on graph segments whose constant child diameter d satisfies `band_mm[0] < 10 d <= band_mm[1]`.
- **Intersection.** The finite-cylinder intersection comes from `core_observation`.
- **Planting.** Each simulated vine is summed over a translated lattice of planting positions (`lattice`: x and y spacing, extent 1 gives 3 × 3), so one seed represents a periodic planting.
- **Independent neighbours.** Per-copy contributions are kept, so a variant can take neighbours from other seeds (`independent_loss`).
- **Loss.** `score_core_placement` on whole-core folds, normalised by each fold's training cores, averaged over folds and then seeds. It is reported with its three weighted components: 0.5 × normalised MAE, 0.25 × joint TV and 0.25 × depth TV.
- **Objective.** The search minimises J = loss + `kg_weight` × (mean kg outside `mass_band_kg`) + `ratio_weight` × (seed-mean RLD ratio units outside `ratio_band`). Any infeasible seed (organ, memory or time limit) gives J = 2 + the infeasible share.
- **Guards and diagnostics.** These are reported, not imposed: named supports (mean RLD over listed cores and a depth range), ratios of supports, guard thresholds, recovery of positive increments below `deep_top_cm` with false hits, and optional attribution probes. The probes break band RLD down by lattice copy, crown group and root order, and give the structural carrier length near a core.

## Spec

A JSON file whose paths are relative to the spec itself:

| Key | Meaning |
|---|---|
| `base_config` | Schema-4 configuration that every candidate starts from. |
| `cores` | CSV `path`; equality `filter`; `exclude_cores`, which must not appear (for example a frozen hold-out); `frame`, the column and sign for model x and y; `folds` (`k`, `seed`, and `strata` listing every core once); optional `columns` renames. |
| `lattice`, `band_mm`, `crown_kg`, `dry_density_g_cm3` | Planting lattice, diameter band, fixed below-ground mass added to the simulated roots, and density used only for segment support. |
| `objective`, `supports`, `ratios`, `guards`, `deep_top_cm`, `probes` | As above. |
| `limits` | `workers`, per-run `seconds` and worker `memory_gb`. The organ cap belongs in the base configuration's `limits.max_organs`. |
| `parameters` | Name → `kind` (`float`, `int`, `categorical`), bounds or choices, optional `log`, and `edits`. An edit is `set` (a value at one or more dot paths; digit keys of mappings stay strings and list positions are integers), `scale` (fields of an object as multiples of `reference` values) or `choice` (replace an object by a named value). |
| `arms` | Named sets of matched comparisons: `seeds`, `baseline`, `probes`, and `arms` mapping labels to parameter values. |
| `stages` | `space` (`log2_n`, `seeds`, `seed`); `tpe` (`seeds`, `n_trials`, `n_startup_trials`, `sampler_seed`, `narrow_from_space`, `top_fraction`, `min_rank_correlation`, `max_parameters`, `timeout_seconds`); `confirm` (`seeds`, `top`, `baseline`, `baseline_label`, `probes`). |

## Stages

- **`arms`** runs named settings on common seeds. It reports paired per-seed changes against the baseline, by component and by fold.
- **`space`** runs a scrambled-Sobol design of 2^`log2_n` points over the declared parameters, batch-parallel.
- **`tpe`** calls `parameter_search.run_parameter_search`: sequential trials with durable receipts, identity-bound and resumable.
  - Each trial evaluates its seeds in parallel.
  - With `narrow_from_space`, the bounds come from the best `top_fraction` of feasible space designs. Parameters whose absolute Spearman correlation with J falls below `min_rank_correlation` are fixed at the best design.
  - The callback's `loss` is J; the RLD fold loss is `rld_loss`.
- **`confirm`** reruns the `top` TPE trials and the baseline on the confirmation seeds. It then freezes a candidate in `frozen_candidate.json`: the lowest-loss candidate that passes every guard, otherwise the lowest J.

## Identity and limits

- **Identity.** Each simulation runs in-process in a worker. Its record carries the canonical configuration SHA-256, seed, imported source fingerprint, scorer version and cores digest, and a cached record is reused only when all match.
- **Failures.** A failed run stops the stage. Runs over the organ, memory or time limits are recorded as infeasible.
- **Outputs.** Records keep per-core contributions and diagnostics, not graphs. Output directories hold full parameters and per-core predictions, so they stay local when the cores are private.
