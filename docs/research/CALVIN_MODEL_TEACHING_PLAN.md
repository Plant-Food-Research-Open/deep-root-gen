# Teaching the Calvin Site 1 notebook workflow

Use the [Site 1 RLD and biomass notebook](../../notebooks/grapevine_root_architecture/calvin_site1_rld_mass_search.ipynb) to review a search from input settings through feasibility, ranking and confirmation. The notebook reads the locally prepared study bundle at `.runtime/calvin-rld-search-20261119`. It expects the bundle's frozen protocol, report, ledger and review figures. Leave `REBUILD_REVIEW = False` to read the available results. Use the synthetic exercise below for a checkout without the study bundle.

| Time | Activity |
| --- | --- |
| 0–10 min | Introduce primary roots, root order, attachment diameter and the soil frame. |
| 10–30 min | Run the two synthetic cases with the same seed. Compare topology, root length and the diameter-class summary. |
| 30–45 min | Read the exported node, edge and organ tables. Identify which quantities describe an axis and which describe part of it. |
| 45–75 min | Open the Site 1 notebook. Compare candidates on a shared seed panel and explain the choices for the first diameter and taper screen. |
| 75–90 min | Use the RLD and total-mass results to decide which candidates merit more seeds. |

## Run the lesson in JupyterLab

Use the repository's [Python 3.10 environment instructions](../../RUNNING.md) for local JupyterLab or a VS Code Python kernel. For Docker, the command below uses a locally built schema-4 image. Build the image as described in [RUNNING.md](../../RUNNING.md), or set `DRG_TEACHING_IMAGE` to the tag of an existing image with JupyterLab and the generator.

Run from the repository root:

```bash
mkdir -p .runtime
lesson_dir=$(mktemp -d "$PWD/.runtime/calvin-jupyter-XXXXXX")
printf 'Lesson files: %s\n' "$lesson_dir"
docker run --pull=never --rm -it \
  --user "$(id -u):$(id -g)" \
  -p 127.0.0.1:8888:8888 \
  -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl \
  -e DRG_PROJECT_ROOT=/lesson/project \
  -e DRG_LESSON_OUTPUT=/lesson/output \
  -v "$PWD:/lesson/project:ro" \
  -v "$lesson_dir:/lesson/output" \
  -w /lesson --entrypoint jupyter \
  "${DRG_TEACHING_IMAGE:-deeprootgen-local:schema4}" \
  lab --ip=0.0.0.0 --port=8888 --no-browser \
  --ServerApp.root_dir=/lesson
```

Open the token URL on the same workstation, using `127.0.0.1:8888` as the host and port. Browse to `project/notebooks/grapevine_root_architecture/calvin_site1_rld_mass_search.ipynb` and select **Python 3**. The container reads the mounted project. Create practice notebooks and exports in the writable `output` folder. Use the original workstation and the frozen study environment for an exact field replay.

## Run one synthetic comparison

Create a Python 3 notebook under `output` in the container or open a notebook within the repository when running locally. Paste this cell and compare the two `root_summary.json` files and the run ledger.

```python
import json
import os
from pathlib import Path
from tempfile import mkdtemp

from deeprootgen.run_records import tracked_run

if "DRG_PROJECT_ROOT" in os.environ:
    root = Path(os.environ["DRG_PROJECT_ROOT"])
else:
    cwd = Path.cwd()
    root = next(p for p in (cwd, *cwd.parents) if (p / "pyproject.toml").is_file())

fixture = root / "examples/design/native_crown_0_20cm.json"
output = Path(os.environ.get("DRG_LESSON_OUTPUT", str(root / ".runtime")))
output.mkdir(parents=True, exist_ok=True)
exercise = Path(mkdtemp(prefix="calvin-lesson-", dir=output))

for case, reporting_cm in (("A", 0.25), ("B", 0.06)):
    config = json.loads(fixture.read_text())
    config["parameters"]["threshold_root_diameter_cm"] = reporting_cm
    tracked_run(config, exercise / case, label=case, ledger=exercise / "runs.jsonl")

print(exercise)
```

The reporting threshold assigns material to diameter classes. Compare the class totals and check that the cases retain the same topology, lengths and total mass. Move the synthetic origins in a separate run using `features.primary_origins.settings.depth_range_cm` to demonstrate a geometry change. See the [schema-4 execution guide](../NATIVE_EXECUTION.md) and the [synthetic configuration](../../examples/design/native_crown_0_20cm.json).

## Teach taper and the daughter diameter cap

- Under `features.taper.settings.by_order.<order>`, `law` selects the taper. With `exponential_above_diameter`, `rate_per_cm` sets the exponential decrease along root contour above `thick_min_cm`. The thinner section uses `tip_cm` and `midpoint_diameter_fraction`.
- At an attachment, the daughter draws a starting diameter from its order's `base_cm` law. The optional `features.parent_diameter_cap.settings.fraction_max` limits that draw relative to the local parent diameter. A cap of 0.95 on a 5 mm parent allows up to 4.75 mm. A draw of 3 mm stays 3 mm.
- `parameters.min_branching_diameter_cm` controls site eligibility. In the native cylinder route, `parameters.diameter_reduction` scales a sampling bound by order. Point taper supplies its own base and tip law for each enabled order.

## Read the Site 1 search and choose the essential controls

Read **Standing-vine evidence and candidate priors** before choosing the diameter range. In **Feasibility at the sampled core locations**, compare cases with shared seeds. Lower `cv_score` is better. An RLD ratio of 1 means the model matches the observed mean. Read that ratio together with mean total dry mass and the fraction of realizations in the mass band. Use **Confirmation and replay** when confirmation records are available.

The per-order path is `features.<feature>.settings.by_order.<order>`.

| Priority | Settings | What to check |
| --- | --- | --- |
| Primary diameter and taper | Order 1 `taper.base_cm` and `taper.rate_per_cm`. The first screen crosses basal distribution factors 1.00, 1.25, 1.50 and 1.75 with rates near 0.0035, 0.00657 and 0.00875 cm⁻¹. | Total mass, local daughter eligibility and RLD in the observed diameter band. |
| Length and branching | Order-specific `lengths`, `branching.daughter_probabilities` on parent orders 3–4 and `branching.mean_spacing_cm` on parent orders 1–2 for the Poisson family. Assess order-2 and order-3 basal diameter separately after the first screen. | RLD magnitude and distribution between cores and depths. |
| Direction | `curvature.row_alignment_per_cm` and `curvature.downward_drift_per_cm` on orders 1–3. Explore `curvature.downward_drift_per_cm` and `curvature.insertion_mean_deg` on orders 4–5. | Along-row spread, RLD depth profile and joint core-by-depth allocation. |

For the initial screen, hold the nominal primary contour mean near 107.5 cm and the upper bound at 250 cm. Hold dry tissue density at 0.45 g/cm³, the parent gate at 0.093 cm and the daughter cap at 0.95. Compare measured and sampled crown layouts as named cases. Use RLD in the 0.93–2.50 mm band for ranking, with 0.50–2.50 mm as a sensitivity. Check the 5–7 kg total underground dry-mass constraint for one vine with a separately estimated crown/rootstock compartment.

Ask the learner to explain why a diameter change can affect both mass and RLD, and what a fresh seed panel tells them about a candidate. Keep trial failures in the ledger and compare the depth-only benchmark and QC reference on the same sampled supports.
