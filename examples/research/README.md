# SO4/T2 research example

For the new opt-in Optuna search bridge, start with the invented
`search_synthetic.json` example and the
[search method](../../docs/research/NOTEBOOK_PARAMETER_SEARCH.md).
It supports both current controlled simulation routes and preserves the
population-versus-per-seed scoring distinction. It is not a fitted SO4 setting.

`so4_t2_fichtl2024.json` is a complete offline `RootSimulationModel` input,
copied from the executed paper-inspired diagnostic scenario. It sets nine
primary roots with uniform lengths approximately7.77–16.43 cm (nominal mean
12.1 cm), the explicit SO4 tropism coefficients and the soil surface20 cm above
the generator base. Legacy gravity is zero in this mode. Counts, distributions,
diameter and global spacing contain explicit approximations; this is not a
calibration, exact CPlantBox replay or biological qualification.

See the [methods, evidence, results and reproduction commands](../../docs/research/grapevine3d/SO4_DIAGNOSTIC_PILOT.md).
The ordinary offline CLI accepts the file with a new output directory:

```bash
python -m deeprootgen simulate \
  --config examples/research/so4_t2_fichtl2024.json \
  --outdir .runtime/SO4-NEW
```

Use the qualified Python3.10 runtime/locked overlay from the methods document.
CSV coordinates retain the model-base origin; to compare soil depth use
`depth_cm = 20 - z`, as in the local comparison runner. Built-in soil rendering
and existing calibration/statistic interfaces have not been extended to this
offset frame. For empirical comparisons use the declared aligned observation
route, not endpoint voxelization or implicit zero-at-base depth.
