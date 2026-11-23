# Run the first fit

Use the Python 3.10 environment in [RUNNING.md](../../RUNNING.md). Open the
[Architecture Search notebook](../grapevine_root_architecture/architecture_search_quickstart.ipynb)
with that Jupyter kernel and run the cells from **Search settings** onwards.

- Base JSON is [synthetic_minimal.json](../../examples/synthetic_minimal.json).
  The single target is [root_number = 3](../../examples/research/optimisation_summary_synthetic.csv).
  This fixture has maximum order 1, so every counted root is a primary.
- Search primary root count **2–4** using normalized MAE, **5 trials**, **2 TPE
  startup trials** and seeds **0, 1**.
- Review `trials.csv` and open the best configuration's replayed `roots.html`.
  The selected configuration uses the first seed for replay. The fit uses both.
- Switch `METHOD` to `latin_hypercube` and rerun from **Search settings**.
  Compare the proposals. TPE adapts after startup. Latin hypercube spreads
  its proposals across the bounds using a fixed design.

## Check the first run

- The kernel reports Python 3.10 and imports `deeprootgen`.
- The request in `fit/study/manifest.json` records seeds 0 and 1. `trials.csv` contains five
  completed rows, and the best JSON specifies three primaries with replay seed 0.
- Both samplers recovered zero loss in the verified exercise. Open
  `roots.html` and check the three primary axes. If your result differs,
  compare the fixture, controls, trial states, seeds and package revision
  before trying a field input.

## Repeat the lesson in Dash

1. Open **Architecture Search** at `/architecture-search` in your local Dash
   installation. Load the base JSON and enter both bounds for **Primary root
   count**. Leave the other controls fixed.
2. Paste the CSV header and its single target row. Use the same search method, loss,
   trial budget and seeds as the notebook. Click **Check setup** and confirm
   one control, one target, five trials and two seeds.
3. Click **Run search** with the Architecture Search Prefect deployment and
   worker running. See [the service setup](../../RUNNING.md). Download
   **Trial table** and **Best configuration**.
   Load the best JSON through **Simulation** to inspect the architecture.
4. Open **Core Comparison** at `/core-comparison` to score predictions that
   were already projected onto physical sections. Load the
   [synthetic core comparison CSV](../../examples/research/core_comparison_synthetic.csv),
   leave the threshold at zero and click **Compare candidates**. The `exact`
   candidate has loss zero. The `miss` candidate misses the positive held
   observation. Repeat in the [local core scoring notebook](core_comparison_lesson.ipynb).

The [two-page quickstart source](../../docs/DEEPROOTGEN_QUICKSTART.md) covers the
main generator switches and can be rendered for print with Pandoc.
