# SO4/T2 and research examples

`so4_t2_fichtl2024_v4.json` is the explicit paper-informed static input for the
optional research mode: a complete canonical generation input, copied
from the executed paper-inspired diagnostic scenario. It sets nine primary
roots with uniform lengths approximately 7.77–16.43 cm (nominal mean 12.1 cm),
the explicit SO4 tropism coefficients and the soil surface 20 cm above the
generator base. Legacy gravity is zero in this mode. Counts, distributions,
diameter and global spacing contain explicit approximations; this is not a
physiological calibration, exact CPlantBox replay or biological qualification.
The sealed controlled experiment binds the original flat file at `so4_t2_fichtl2024.json`. Use the versioned filename above for new simulations.

See the [research-mode guide](../../docs/research/FICHTL_RESEARCH_MODE.md) for
units, length scaling, angle truncation, offset-frame limitations and offline
commands, and the [methods, evidence, results and reproduction commands](../../docs/research/grapevine3d/SO4_DIAGNOSTIC_PILOT.md).
The ordinary offline CLI accepts the file with a new output directory:

```bash
python -m deeprootgen simulate \
  --config examples/research/so4_t2_fichtl2024_v4.json \
  --outdir .runtime/SO4-NEW
```

Use the qualified Python 3.10 runtime/locked overlay from the methods document.
CSV coordinates retain the model-base origin; to compare soil depth use
`depth_cm = 20 - z`, as in the local comparison runner. Built-in soil rendering
and existing calibration/statistic interfaces have not been extended to this
offset frame. For empirical comparisons use the declared aligned observation
route, not endpoint voxelization or implicit zero-at-base depth.

## Invented search and five-order examples

Start with `search_synthetic.json` and [the search contract](../../docs/research/NOTEBOOK_PARAMETER_SEARCH.md).
Validate without `--execute` before running. The Optuna search bridge supports
both current controlled simulation routes and preserves the population-versus-
per-seed scoring distinction. The reference and parameters are invented
plumbing examples, not a calibration or fitted SO4 setting.

`five_order_primary_mass_synthetic.py` demonstrates separate optional
construction and supplied-graph material interfaces. See [the five-order contract](../../docs/research/FIVE_ORDER_PRIMARY_AND_MASS_METHOD.md).
Do not equate root order with diameter-defined fine-root mass.
