# Generation input migration

The current generation document has `schema_version: 4`. The public simulator,
CLI, tracked-run helper and simulation flow consume it. The model returns
organ counts and lengths by order, dry mass and length by diameter class, and
achieved allocation ratios. The CLI and flow save the material summary as
`root_summary.json`. [Current input guide](../NATIVE_EXECUTION.md)

## Input files and callers

| Source or caller | Current contract |
|---|---|
| `examples/synthetic_minimal.json` and `synthetic_ui.yaml` | Direct canonical JSON and YAML examples. The simulation page reads either representation and saves canonical JSON. |
| `examples/design/` | One current feature catalogue, a buried trunk example, a replacement-material example and an architecture-target example. New structural examples use a 0.093 cm branching minimum. |
| `examples/research/*_synthetic.json`, `search_synthetic_parameters.json`, `so4_t2_fichtl2024_v4.json` | Canonical generation files. `search_synthetic.json` and `search_synthetic_reference.json` hold an experiment design and observations respectively. |
| `examples/run_synthetic.py`, five-order primary/mass example, tracked-run notebook 6 and matrix script | Run the same public engine, with biological settings in the canonical model and output choices in the caller. |
| Fichtl and Wong calibration notebooks 2–4 | Preserve the experimental sampling coordinates used in their stored outputs. At every simulation call, the notebook constructs a schema-4 configuration from the sampled inner/outer counts, daughter bounds and other dimensions. The notebook grids own their soil settings. Notebook 1 is preparation/EDA. |
| Fichtl notebook 5 and `scripts/research/parameter_search.py` | Read a schema-4 base configuration. Scalar search suggestions update its nested `parameters` fields. Each worker gets a fresh seeded configuration. Per-seed and population comparisons retain their stated denominators. |
| Dash simulation page and Prefect simulation request | The page constructs a canonical document from named controls and advanced JSON. Advanced parameters, features and limits survive upload/edit/download. Optional ratio targets expose their adjustable dimensions through `parameters.allocation_controls`. Soil display settings travel in a separate flow argument. |
| Calibration pages and inference flows | Search intervals describe canonical scalar parameters. Each sampled parameter set constructs a canonical simulation request. The deployment surrogate prediction accepts numerical feature rows and selects the columns recorded by its trained model. |
| Historical SO4 pilot, controlled experiment and `CohortRootGenerator` | These named research procedures retain the historical simulation/replay API for the recorded study protocols. For fresh supported construction use the schema-4 native-steps, cohort-feature or SO4 public examples and the normal CLI. The frozen SO4 config references the original bytes at `examples/research/so4_t2_fichtl2024.json`. |
| Historical parser, exporter and engine tests | Execute explicit archive entrypoints against captured input bytes in `tests/fixtures/migration_inputs/`. The checkpoint reference builder retains its recorded code preimages. |

## Migrating an existing document

Run this command from the checkout using the qualified Python environment. The
destination must be a new path. The converter validates and resolves the result
before opening that path.

```bash
python -m scripts.migration.convert_input old.json converted.json
```

| Source field | Schema-4 destination or disposition |
|---|---|
| `outer_root_num`, `inner_root_num` | `primary_root_count` is their sum. `outer_primary_fraction` retains the outer share. |
| `min_sec_root_num`, `max_sec_root_num` | `daughters_per_parent` is an integer for equal bounds or a range with an exclusive upper bound. |
| `growth_sec_root` | `daughter_count_order_gain` retains the native order coefficient. |
| `min_sec_root_length`, `max_sec_root_length` | `min_lateral_length`, `max_lateral_length`, in cm. |
| `fine_root_threshold` or cohort `fine_cutoff_mm` | `threshold_root_diameter_cm` preserves the supplied value and unit conversion. |
| `apex_diameter` | The native material sampler retains this endpoint in cm. The converter explicitly sets `min_branching_diameter_cm=0` to preserve historic branch eligibility. |
| `root_ratio`, `t`, `mechanical_constraints`, `origin_min/max` | Inactive in the static generator. The conversion omits these fields. New allocation target values require a user-supplied fraction definition. |
| Soil-display controls | Belong to visualization or observation requests. If soil display was enabled, first capture the settings in that request and remove them from the generation source copy. |
| Native and construction-step research settings | Per-order lengths, placement, counts, insertion, direction, corrections and relocation map to their feature owners. |
| Cohort | Maps to optional material, length, maturity, origin, parent-cap, direction, branching and correction controls. Nonzero external crown/unrepresented mass requires an explicit observation compartment. |
| Execution seed, tag, budget | Top-level `random_seed`, `simulation_tag` and `limits`. |

Old SO4/cohort numerical receipts remain bound to their original schedules and
graph conventions. Canonical cohort conversion retains the pure surface check
and uses the shared traversal and current stream policy. Frozen biological
outputs remain attached to the source version that generated them.

The research search example varies scalar settings already present under
`parameters`. It supports Fichtl configurations with a 20 cm soil reference and
maximum order 3, 4 or 5. A construction-step protocol requires the matching
direction feature. The two recorded protocol names select the current measured
geometry through schema 4. Historical arm-D replay remains in the archive.
The generic calibration and surrogate request forms expose scalar parameter
columns. Use the simulation page or CLI to supply optional ratio targets and
their per-order allocation bounds.

The synthetic migration tests exercise conversion, old-field rejection, notebook
construction and form round trips. Hosted deployments, empirical notebooks and
model fitting require their own inputs and runtime environments. The migration
verification uses their offline request constructors and invented examples.
