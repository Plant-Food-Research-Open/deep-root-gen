# Grapevine root architecture notebooks

Start with the [DeepRootGen training folder](../training/README.md) for the invented exercises and the Claude-assisted fresh-data workflow.

[Site 1 irrigation branching and independent-vine spacing](Calvin_private/site1_irrigation_zones/irrigation_study.ipynb) · [Printable comparison](Calvin_private/site1_irrigation_zones/irrigation_review.pdf)

[Five-order parameter search on the fixed 0.50–2.50 mm target](Calvin_private/site1_broad_search_050/REPORT.md) · [Final Site 1 presentation](Calvin_private/site1_broad_search_050/site1_final_presentation.pptx) · [Printable slides](Calvin_private/site1_broad_search_050/site1_final_presentation.pdf)

[Current Site 1 RLD comparison and frozen 0.50–2.50 mm target](Calvin_private/site1_fixed_rld_050/REPORT.md)

[Calvin Site 1 model and lessons learned](Calvin_private/SITE1_MODEL_AND_LESSONS.md) brings together the generator rules, tissue densities, neighbourhood sampling, 24-seed comparison, tube 14 and local replay instructions.

The local [sibling-sector and terminal-retention confirmation](Calvin_private/site1_sector_retention_confirmation/confirmation.ipynb) tests both rules together on fresh vines and reports the depth profile of tube 14. The [paired results](Calvin_private/site1_sector_retention_confirmation/REPORT.md) distinguish empty increments from completely empty cores.

For the preceding Calvin Site 1 placement experiments, open the local [executed placement notebook](Calvin_private/site1_placement_2026-11-20/site1_placement.ipynb), [results and parameter comparison](Calvin_private/site1_placement_2026-11-20/REPORT.md) or [presentation update](Calvin_private/site1_placement_2026-11-20/site1_placement_update.pptx).

The preceding reference is archived in the [executed model review](Calvin_private/site1_selected_2026-11-20/site1_current_best.ipynb) and [model presentation](Calvin_private/site1_selected_2026-11-20/site1_model_review.pptx). That private folder contains its configuration, confirmation tables and offline 3D views of the vine and the sampled cores.

Open a notebook in this folder and run its cells in order. The seven exploration notebooks read the local study bundles in the DeepRootGen checkout. Their default cells inspect existing records. Simulation and search cells have explicit switches. Save executed copies with field data under `.runtime/`.

| Study | Notebook |
|---|---|
| Calvin Site 1 RLD search with fixed tissue density and separate whole-vine biomass constraint | [RLD and biomass search](calvin_site1_rld_mass_search.ipynb) |
| Synthetic lesson follow-up on taper and branching, virtual cores and candidate selection | [Teaching exercises D–F](calvin_synthetic_followup.ipynb) |
| Current Calvin Site 1 starting input, measured crown versus sampled crown | [Measured-crown review](calvin_measured_crown_review.ipynb) |
| Search with 20 cm burial and measured diameter priors | [Crown and diameter search](calvin_site1_crown20_search.ipynb) |
| Earlier search and held-core comparisons | [Site 1 search](calvin_site1_search.ipynb) |
| Effect of observation cutoff and measurement-quality flags | [Cutoff and QC](calvin_cutoff_qc_review.ipynb) |
| Compare branching assumptions in Calvin and SO4/T4 | [Spatial branching review](spatial_branching_review.ipynb) |
| Compare matched core profiles and SO4 spatial grids | [Spatial evaluation](spatial_evaluation.ipynb) |
| Inspect earlier trials, run manual changes and export the trial ledger | [Joint parameter exploration](parameter_exploration.ipynb) |

The [SO4/T4](so4_t4_parameter_review.ipynb) and [earlier Calvin Site 1](calvin_site1_parameter_review.ipynb) parameter notebooks also include synthetic examples for checkouts without the local study files.

The local-only [Site 1 parameter snapshot and small crown-root experiment](Calvin_private/site1_best_parameters_and_small_crown_roots.ipynb) contains the earlier fixed-density input, its eight-seed selection evidence and an editable extra-primary count. It requires the private study bundle for replay.


## Parameter records and guides

| Question | Start here |
|---|---|
| Which settings were explored, which combination was selected, and where does it still miss? | [Executed parameter record and lessons](Calvin_private/explored_parameters_and_lessons.ipynb). Run from the notebook folder or the repository root with Python 3. |
| Which files define the selected Site 1 model? | [Native scaffold](Calvin_private/site1_selected_2026-11-20/data/stepped_scaffold.schema4.private.json) and [terminal taper and orientation recipe](Calvin_private/site1_selected_2026-11-20/data/selected_recipe.json). The [illustrated review](Calvin_private/site1_selected_2026-11-20/site1_current_best.ipynb) uses the archived eight-seed results. |
| What do the architecture parameters mean? | [Illustrated guide](../../docs/ROOT_ARCHITECTURE_AND_SPATIAL_FITTING.md), [Site 1 parameter dictionary](../../Calvin_SO4_Parameter_Exploration_2026-11-18/Calvin_Site1_Parameter_Dictionary.xlsx) and [printable definitions](../../output/pdf/Calvin_Site1_Parameter_Guide.pdf). The dictionary and printable definitions describe the earlier input. |
| Which SO4/T4 settings should I compare? | [Spatial starter](../../Calvin_Structural_Optimization_2026-11-18/SO4_T4_direction_start.schema4.private.json), [geometry starter](../../Calvin_SO4_Parameter_Exploration_2026-11-18/SO4_T4_start.schema4.private.json) and [spatial evaluation](../../Calvin_SO4_Parameter_Exploration_2026-11-18/Spatial_Evaluation_2026-11-19/REPORT.md). The [19 November parameter tables](../../Calvin_SO4_Parameter_Exploration_2026-11-18/Detailed_Parameter_Report.md) document the preceding Calvin comparison as well. |
| How do I teach the workflow or present it? | [Teaching plan](../../Calvin_SO4_Parameter_Exploration_2026-11-18/Calvin_Model_Teaching_Plan.md), [illustrated Word guide](../../Calvin_SO4_Parameter_Exploration_2026-11-18/Root_Architecture_and_Calvin_Site1_Fitting.docx) and [printable selected-model review](Calvin_private/site1_selected_2026-11-20/site1_model_review.pdf). |

The parameter record and selected-model review include the data needed to inspect their results offline. Running older searches or regenerating fresh vines with the selected research recipe also requires the corresponding local study scripts and environment. The fitted inputs, processed core observations and research results in this checkout are for local use.
