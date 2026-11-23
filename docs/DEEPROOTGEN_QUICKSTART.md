---
pagetitle: "DeepRootGen quickstart"
geometry: "a4paper,top=16mm,bottom=17mm,left=18mm,right=18mm"
fontsize: 11pt
colorlinks: true
linkcolor: "blue!50!black"
urlcolor: "blue!50!black"
---

# DeepRootGen quickstart

**A 15-minute walkthrough for Kelvin · Schema 4**

DeepRootGen generates a 3D root system from a JSON configuration and a random
seed. An optimiser varies selected settings, simulates each candidate on the
same seeds, and ranks candidates by how closely they match chosen measurements.

## What to inspect in the generator

| Controls to try | What to check |
|:--|:--|
| Primary count, crown origins and root length by order | Number of axes, origins and reach. A 1–3 m primary contour is 100–300 cm along the root. |
| Branching chance, daughter count and attachment placement | Where daughters appear, how many are retained, and where branches reach. Check branch reports by order. |
| Gravitropism, curvature and row alignment | Depth and spread across the row. Compare weaker downward drift with the same starting seeds. |
| Taper, parent-diameter cap and tissue density | Diameter distribution and dry mass. Choose which crown and rootstock material is included when comparing mass. |

Set the baseline scalars in `parameters` and switch on optional laws in
`features`. Check **Active laws by order** in Dash or use
`--explain-config` in the CLI. The selected laws determine which controls
the optimiser can vary. In the local placement research, a fitted 3D core
surface can change relative odds by position and depth. Test daughter
placement, branch initiation and terminal retention as separate choices.

## Run the notebook lesson

Open this notebook in JupyterLab or VS Code.

`notebooks/grapevine_root_architecture/architecture_search_quickstart.ipynb`

Select the project's Python 3.10 kernel and use **Run All**. The notebook runs
locally from the invented `examples/synthetic_minimal.json`.

1. In **Search settings**, use primary count **2 to 4**, the target
   `root_number = 3`, **normalized MAE**, **5 trials**, **2 TPE startup trials**
   and simulation seeds **0, 1**. Leave other parameters fixed.
2. Run the preview and search. Expect **5 completed**, **best loss 0** and
   **3 primary roots**. TPE adapts proposals after startup. Set the method to
   `latin_hypercube` and rerun to try space-filling sampling.
3. Compare `trials.csv` with `best-configuration.json`. The notebook
   replays that JSON and exports `roots.html`, `nodes.csv`, `edges.csv` and
   the run manifest. The best JSON uses the first seed. The fitting score
   averages predictions across both seeds.

**Adapt the settings.** Change `RANGES`, `TARGETS_PATH` and `SEEDS` in the first cell.
Use the simulator's units for observations and check the chosen configuration
on fresh seeds.

**Next notebook.** For the field workflow, open
`calvin_site1_rld_mass_search.ipynb` in the same folder. It reads the
archived study bundle locally. Use the synthetic lesson first on a new machine.

\newpage

# Run the example in the web interface

Use **Architecture Search** on the current local dashboard at
[127.0.0.1:18002/architecture-search](http://127.0.0.1:18002/architecture-search).
For a different installation use its Dash address and the same page name.

1. Click **Load architecture JSON** and select
   `examples/synthetic_minimal.json`. Enter **2** and **4** in the
   **Primary root count** row. Leave the other ranges blank.
2. Paste these two CSV lines in **Targets and trials**.

   ```csv
   statistic_name,statistic_value
   root_number,3
   ```

3. Select **Adaptive Optuna TPE** and **Normalized MAE**. Set **Trials** to
   **5**, **Startup** to **2**, and **Seeds** to `0, 1`. **Check setup** should
   show one control, one target, and five trials by two seeds.
4. Click **Run search**. Running jobs requires the registered **Architecture
   Search** Prefect deployment, a worker and shared outputs. When it finishes,
   download **Trial table** and **Best configuration**. Load the best JSON in
   **Simulation** and use its seed to review the fitted graph.

Architecture Search fits supported whole-root scalar targets. The bounded
web form allows **2 to 60 trials**, up to **four seeds**, normalized MAE or RMSE,
and an optional positive target scale. For multiple targets, use scales that
represent meaningful tolerances. The **Optimisation** page provides the
original scalar fitting form.

## Check spatial fit on held cores

Open **Core Comparison** and load
`examples/research/core_comparison_synthetic.csv`. Leave the presence threshold
at zero and click **Compare candidates**. The `exact` candidate ranks first
with loss **0**. The `miss` candidate misses the observed positive section.

The main loss combines **50% normalized RLD error**, **25% tube-by-depth
distribution error**, and **25% depth-profile distribution error**. Absolute
RLD error charges an overestimate and an underestimate of the same size equally.
An observed hit with zero predicted RLD incurs the full magnitude error.
**Miss rate** and **false-hit rate** are separate diagnostics. RLD is root length
per soil volume, here in cm/cm³.

For field work, fit or select configurations locally on training tubes.
Project predictions to the same physical intervals and volumes on entire held
tubes with the same diameter band. Upload those aligned predictions to a local
**Core Comparison** page. Keep restricted field files on the workstation.

**Reference in the repository.** `RUNNING.md` covers setup.
`docs/WEB_OPTIMISATION.md` covers the web screens.
`docs/ARCHITECTURE_SCORING.md` explains the scores and spatial validation.

<!-- Rebuild from the repository root with
pandoc --standalone --pdf-engine=pdflatex docs/DEEPROOTGEN_QUICKSTART.md
-o output/pdf/DeepRootGen_Quickstart.pdf
-->
