Explore and fit a schema-4 root system
======================================

Use the same schema-4 JSON for offline simulation, a Python notebook and the
Simulation page. Each run produces a root architecture for one parameter set
and seed. The active feature settings govern calculations by root order.

Run an invented example
-----------------------

In the repository's locked Python 3.10 environment, run the following from the
repository root. The second command requires a new output directory.

.. code-block:: bash

   python -m deeprootgen simulate --config examples/design/native_crown_0_20cm.json --explain-config
   python -m deeprootgen simulate --config examples/design/native_crown_0_20cm.json --outdir .runtime/crown-demo

Open ``roots.html`` to rotate the generated structure. The ``nodes.csv`` and
``edges.csv`` pair records each node and parent-child relationship.
``organs.csv`` contains whole axes. Open ``root_summary.json`` for valid axis
counts and lengths by order and for length and dry mass by diameter class.
The run manifest records the seed and file identities.

Change one control in the interface
-----------------------------------

On a running local stack, go to **Simulation** and use **Load parameters** to
open the same JSON. The ordinary fields cover controls such as the seed and
reporting diameter. **Advanced settings (JSON)** includes ``features`` and
``limits``. To try a shallower crown, change
``features.primary_origins.settings.depth_range_cm`` to ``[0, 8]`` and keep
the seed fixed. **Save parameters** downloads a reusable JSON.

**Run procedure** submits the job to Prefect. Once it completes, open the
matching MLflow artifacts. On the EDA page, load the synthetic node CSV and
plot ``x`` against ``z`` grouped by ``order``. The offline HTML and CSV provide
the same geometry for use without a running service stack.

The default branching gate is 0.093 cm of parent diameter at a daughter
attachment. The default reporting cut of 0.25 cm groups length and dry mass.
With allocation targets unset, changing the reporting cut leaves the geometry
and total length and mass unchanged. Optional ``root_ratio_length`` and
``root_ratio_biomass`` are requested lower-class fractions. Their allocation
controls specify which dimensions may change to reach them.

Compare and calibrate
---------------------

Start with paired trials that change one setting and share a seed. In a
notebook, use ``deeprootgen.run_records.tracked_run`` to save the config,
outputs, seed and source identity in a new run directory. For a wider search,
set plausible bounds and use common fitting seeds across candidates. Save
failed trials with their diagnostics. Freeze a candidate before checking new
seeds and held observations.

The packaged calibration flows operate on selected summaries and parameter
intervals. Sensitivity Analysis estimates Sobol effects on the discrepancy.
Optimisation searches for a low discrepancy with Optuna. ABC and SNPE
characterize parameter uncertainty conditional on chosen observations and
priors. Surrogates approximate simulator outputs and Deployments call a
configured prediction service.

For a study fitting spatial root length density and biomass, define the actual
sampling volumes, depth convention and diameter support for each observation.
Use its corresponding observation operator and check the two responses
separately. Keep private input data and empirical configurations local.
