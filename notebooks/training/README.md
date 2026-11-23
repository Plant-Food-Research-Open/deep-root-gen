# DeepRootGen training

Learn the workflow used in the Calvin study: check the observations, describe
the root architecture to reproduce, choose a starting configuration, explore
it in Dash, and fit only after the simulator and measurement comparison agree
on what is being measured. The exercises use invented data and a Python 3.10
environment with DeepRootGen and a Jupyter kernel.

| Time | Activity | Material |
|---|---|---|
| 10 min | Locate the active model settings. Run the five-trial notebook and open the replayed roots. | [Quickstart](QUICKSTART.md) |
| 10 min | Compare whole-core holdout, missing measurements and detected roots. Explain a missed field hit. | [Core scoring lesson](core_comparison_lesson.ipynb) |
| 10 min | Repeat the fit in Dash and save the best JSON. Then change one range and inspect the preview. | [Dash instructions](../../docs/WEB_OPTIMISATION.md) |
| 20 min | Draft a fresh-data brief and ask Claude to recommend a base and one alternative. Review both before planning a search. | [Fresh-data guide](FRESH_DATA_WITH_CLAUDE.md) · [Claude prompts](CLAUDE_PROMPTS.md) |

## References and study materials

- [Model handbook](MODEL_HANDBOOK.md) for choosing and checking active construction laws.
- [Statistical reference](STATISTICAL_REFERENCE.md) for choosing targets, losses and evaluation splits.
- [Pilot worksheet](STUDY_WORKSHEET.md) for collecting evidence and turning a manual comparison into a reproducible search.

For a longer lesson, try the [synthetic taper, branching and virtual-core exercises](../grapevine_root_architecture/calvin_synthetic_followup.ipynb).
The [Calvin RLD and biomass notebook](../grapevine_root_architecture/calvin_site1_rld_mass_search.ipynb)
shows the field-study structure on the authorised workstation with its local
study bundle. Open the field notebook in a plain local Jupyter session.
The [generator handbook](../../docs/DEEPROOTGEN_HANDBOOK.md) covers
additional features and commands.
