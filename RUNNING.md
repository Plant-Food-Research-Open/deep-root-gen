# Running DeepRootGen

## Upstream 1.0 integration (13 November 2026)

The approved PFR upstream update at `80315af` is integrated with the local
runtime setup. Both textual conflicts were resolved by retaining the useful
content from each side. The source changes include the upstream 1.0 branching
and spatial-RLD interfaces, not merely container changes.

The complete merged suite passes **376 tests**, including opt-in simulation
integration, using the retained Python 3.10.20 host environment. This host
environment has not been reinstalled against the new lock. The synthetic
fixtures and simulation/deployment forms now use gravitropism `0.1`, matching
the upstream integration fixture and required `[0, 1]` domain. This is a
diagnostic input, not a calibrated value or a conversion of the old `7.5`.
The local configured output-directory behavior is preserved and tested.

**Calibration limitation:** the upstream calibration form still contains old
gravity slider defaults `4–9` and bounds `1–10`, incompatible with the new
model domain. Calibration and existing saved parameter files are not qualified.
Do not launch optimization from those defaults; scientific search ranges need
a separate decision. No observation fitting or calibration was performed.

The local Compose image now defaults to
`deeprootgen-local:upstream-80315af`; the old `runtime-ui` image and historical
volumes are retained. The local recipe preserves non-root execution and
loopback-only service ports; the upstream production recipe is also present
but should not be launched blindly on an exposed interface.

The remaining sections describe the historical October qualification, not
new evidence for the 1.0 model. In particular, its old lock hash and four-test
summary apply only to that earlier revision.

## Historical October setup and qualification

Qualified on **30 October 2026**, on branch `codex/deeprootgen-runtime-ui`,
based on source revision `39b942ff77098d52cf56cbed43d63c0e10fbbc14`.
The runtime changes are uncommitted development work. Use this guide instead of
historical installation examples in the older developer notes.

## Start here next week

The environment and container images already exist on this workstation. Open a
terminal and use the following commands; no reinstall is needed:

```bash
cd /home/jzhu/Workspace/Github/FruitCropXL/13-deep-root-gen-PFR-open
source .runtime/envs/py310-qualification/bin/activate
export CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
python --version
python -m pip check
run_dir=$(mktemp -d .runtime/week-test.XXXXXX)
python -m deeprootgen simulate \
  --config examples/synthetic_minimal.json --outdir "$run_dir/cli"
python examples/run_synthetic.py \
  --config examples/synthetic_minimal.json --outdir "$run_dir/python"
cmp "$run_dir/cli/nodes.csv" "$run_dir/python/nodes.csv"
cmp "$run_dir/cli/edges.csv" "$run_dir/python/edges.csv"
```

Expected: Python 3.10.20; no broken requirements; both runs report seed 42,
11 nodes, 10 edges and zero invalid nodes; both comparisons exit successfully.
Open `roots.html` in either output directory with a browser to inspect the plot.
`mktemp` creates a fresh parent so repeated tests do not overwrite earlier runs.
The same CLI/API sample and table parity have passed in this environment.

For the existing Docker UI, use the same repository directory:

```bash
docker compose --env-file .env.local -p drg-smoke-local \
  -f docker-compose.local.yaml up -d --wait --wait-timeout 300
docker compose --env-file .env.local -p drg-smoke-local \
  -f docker-compose.local.yaml ps
```

Open **http://127.0.0.1:8000/** for Dash, **http://127.0.0.1:4200/** for
Prefect and **http://127.0.0.1:5000/** for MLflow. A healthy Dash page alone
is insufficient: follow the run to Prefect's Completed state and check artifacts.
The synthetic UI procedure is described below. Services are left stopped after
qualification; named volumes and images are retained.

Next-week tester checklist:

- [ ] Run the CLI and Python commands above and compare the two tables.
- [ ] Start Compose, wait for health checks, and open Dash.
- [ ] Enter/load the tiny fixture below; submit once, verify Prefect Completed.
- [ ] Check MLflow node/edge CSVs and root plot; save outputs locally.
- [ ] Try the form YAML and run-history downloads in your normal browser.
- [ ] Stop the stack using the safe shutdown command below.

## What was actually verified

| Route/check | Qualification result |
| --- | --- |
| Private CPython + original locked dependencies | Installed; `pip check` passes |
| Bootstrap helper repeat on the existing environment | Pass; no dependency changes |
| Simulator and eight Dash page imports | Pass |
| CLI and direct Python synthetic runs | Pass; identical node/edge CSVs |
| Tests | 4 passed, including the original dummy scaffold test |
| Flake8 / Black / whitespace | Pass for checked source; see commands below |
| App and MinIO container builds | Pass, including pinned base images |
| Local Compose services / Dash page | Health checks and browser rendering pass |
| Browser form -> Prefect -> MLflow / ArangoDB | Pass for seed-42 sample |
| MLflow artifact downloads through Python API | 7 artifacts retrieved; counts/hashes checked |
| Form export callbacks | YAML and history CSV created in shared volume and S3 |
| Browser save completion / file upload | Not qualified: automation limitations, detailed below |
| Stop/start and container recreation persistence | Pass; records and all artifact hashes unchanged |
| Scientific validity, measured data, inference or GPU | Not evaluated |

The UI qualification run was Prefect
`a77d09dc-bfb3-439b-b114-b2c66d64b3c1`, simulation UUID
`169d8a0c-3d5c-436d-8288-8d873bb2713f`, MLflow run
`ecdc886d81624e59a4e7bc8b849f9e03` (experiment 1). Those records should be
available after restart with this project and its preserved volumes.

## Python environment: reuse or clean install

The project requires **Python >=3.10,<3.11**. The qualified workstation is
Ubuntu 26.04.1 LTS, x86_64 Linux. System Python 3.14.4, pyenv defaults and
other Poetry installations were preserved. Do not activate an unrelated `.venv`.

Installed private interpreter:
`.runtime/cpython/3.10.20/bin/python3.10`.
The exact interpreter build used the already installed pyenv python-build helper:

```bash
# Already executed here. Do not run over an existing private interpreter.
MAKE_OPTS=-j4 /home/jzhu/.pyenv/plugins/python-build/bin/python-build \
  3.10.20 "$PWD/.runtime/cpython/3.10.20"
```

The helper downloaded the official Python 3.10.20 tar.xz from python.org and
verified SHA256 `de6517421601e39a9a3bc3e1bc4c7b2f239297423ee05e282598c83ec0647505`.
A fresh host needs a C compiler and CPython development libraries (OpenSSL,
zlib, bz2, readline, sqlite3, xz/liblzma and libffi); provisioning them on another
OS is not qualified here. Use an approved interpreter installer when the helper
is absent; do not replace system Python. Docker below is a separate route that
does not need host Python 3.10 or host Python compilation tools.

Given a trusted Python 3.10 interpreter, the tested isolated install is:

```bash
bash scripts/dev/bootstrap.sh "$PWD/.runtime/cpython/3.10.20/bin/python3.10"
source .runtime/envs/py310-qualification/bin/activate
python -m pip check
```

The helper creates `.runtime/tools/poetry-1.8.3` and
`.runtime/envs/py310-qualification`, uses Poetry **1.8.3**, and installs the
existing lock including `dev` and `torch` groups. It checks the selected venv,
refuses existing non-environment paths and does not run `poetry update`.
It was rerun successfully after initial installation. Keep old environments
until the replacement passes qualification. `.runtime` is ignored by Git and
excluded from Docker builds. Allow several GB for packages and build caches;
the completed host runtime/cache used about 14 GB here.

The unchanged `poetry.lock` SHA256 is
`8d6a2311736b5d677218d0bee0610348803fb3217ae2e60fc196bfe04b881ffd`.
Key installed versions: NumPy 1.26.4, pandas 2.2.2, SciPy 1.11.4,
Torch 2.4.0, PyG 2.5.3, Pydantic 2.8.2, Dash 2.17.1,
Prefect 2.20.2 and MLflow 2.15.1. The runtime receipt records actual installed
versions; the lock remains the full dependency authority.

The graph module eagerly imports Torch/PyG, so even basic simulation requires
that group. Linux locked Torch includes CUDA libraries, but qualification used
CPU with `CUDA_VISIBLE_DEVICES=`. No GPU, driver changes, training or inference
performance is qualified. A new CPU-only dependency resolution is outside this work.

## CLI and outputs

```bash
python -m deeprootgen --help
python -m deeprootgen simulate \
  --config examples/synthetic_minimal.json --outdir .runtime/my-new-cli-run
```

Use a new output directory. The CLI refuses an existing destination and returns
nonzero for invalid or missing input. It calls the existing simulator without
Prefect, MLflow, database or object-store connections. Default fixture limits
are deliberately small; there is no enforced wall-clock timeout for arbitrary
user-supplied large configurations.

| File | Contents |
| --- | --- |
| nodes.csv | Node records, including the base node and invalid-root flags |
| edges.csv | Parent/child relationships |
| parameters.json | Validated full parameter model |
| roots.html | Interactive root plot with bundled JavaScript |
| run_manifest.json | Seed, versions, counts and file SHA256 checksums |

The fixture uses max_order 1, one outer and one inner primary root, five
segments each, t=0, seed 42 and soil disabled. It tests runtime plumbing and
initial geometry; it does not cover growth/branching biology. Same-seed CSV
content is repeatable in this qualified stack. Plot element IDs and timestamps
are not a byte-reproducibility guarantee.

## Direct Python API

The tested script writes the same exports:

```bash
python examples/run_synthetic.py \
  --config examples/synthetic_minimal.json --outdir .runtime/my-new-python-run
```

For in-memory Python use from the repository root:

```python
import json
from pathlib import Path
from deeprootgen.data_model import RootSimulationModel
from deeprootgen.model import RootSystemSimulation

spec = json.loads(Path("examples/synthetic_minimal.json").read_text())
params = RootSimulationModel(**spec)
model = RootSystemSimulation(
    random_seed=params.random_seed, simulation_tag=params.simulation_tag
)
model.run(params)
nodes, edges = model.G.as_df()
assert (len(nodes), len(edges)) == (11, 10)
```

The direct calls are exercised in the tests. No notebook server or kernel
installation was added or qualified. If using existing notebook tooling,
select this environment and set the working directory explicitly.

Node columns are node_id, plant_id, parent_id, organ_id, x, y, z, order,
segment_rank, diameter, length, root_tissue_density, root_type, order_type,
position_type, simulation_tag and invalid_root. Edge columns are parent_id and
child_id. Base parent sentinel is -1; classifications are strings. Labels in
source use cm, g/cm³ and g, but CSVs do not contain a separate units column.
This work does not validate or redefine units or treatment of base/invalid rows.

## Docker installation and local UI

Qualified engine **29.1.3**, Compose **2.40.3**. Docker must already be installed
and accessible through its supported local configuration. Do not change socket
permissions or add privileged access to work around a task sandbox denial.

On a fresh checkout, use any existing Python 3 for the standard-library-only
configuration generator. On this workstation, preserve the generated
`.env.local` and skip generation when it exists:

```bash
python3 scripts/local/configure.py
# If .env.local already exists, the helper deliberately refuses to overwrite it.
docker compose --env-file .env.local -p drg-smoke-local \
  -f docker-compose.local.yaml config --quiet
docker compose --env-file .env.local -p drg-smoke-local \
  -f docker-compose.local.yaml build app minio
docker compose --env-file .env.local -p drg-smoke-local \
  -f docker-compose.local.yaml up -d --wait --wait-timeout 300
```

These build/start forms were executed. The configuration has three random
passwords in a mode-0600 ignored file; tracked `.env` is not used or replaced.
Keep this file for restarting existing databases. Generating different passwords
against an existing initialized Postgres volume is not a password migration.
Do not share expanded `docker compose config` output or full container environments.

Python base, Go compiler, Debian base, Postgres and ArangoDB references are
pinned by digest in the local recipes. Python dependencies come from the original
Poetry lock. Apt system packages are resolved from Debian repositories at build
time, so a future image rebuild is not promised to be bit-for-bit identical.

The historical `minio/minio:RELEASE.2023-05-27T05-56-19Z` image was unavailable
from Docker Hub. The local MinIO recipe instead builds the matching public
[official source commit](https://github.com/minio/minio/tree/394690dcfb1b80532d5785bbf5313a0e57b58a00),
checks its archive SHA256, respects its Go module lock and includes its AGPL
license. The official MinIO repository is archived; this legacy compatibility
stack is intended for local development. A supported production storage choice
needs separate review. No unofficial image mirror is used.

Required services are Dash, Postgres 15.3, MinIO's original 2023 release,
ArangoDB 3.11.3, MLflow, Prefect server, one process worker and two one-shot
initializers. Init jobs create private buckets and register the existing six
Prefect deployments. Only Simulation was exercised; registration does not imply
calibration/inference qualification. Prefect's generated UI files live in its
non-root user's writable home.

| Service | Published loopback URL | Data location |
| --- | --- | --- |
| Dash | http://127.0.0.1:8000/ | outputs-data at /app/outputs |
| Prefect | http://127.0.0.1:4200/ | postgres-data, database prefect |
| MLflow | http://127.0.0.1:5000/ | postgres-data + minio-data |
| Postgres / MinIO / ArangoDB | Internal only | their named volumes |

Set DRG_APP_PORT, DRG_PREFECT_PORT and DRG_MLFLOW_PORT in `.env.local` before
startup if needed. Do not kill unrelated listeners. MinIO 9000/9001, ArangoDB
8529 and Postgres 5432 are not published. Existing sidebar links for MinIO,
ArangoDB, Metabase and CloudBeaver are not enabled by this minimal stack.
BentoML model serving, Metabase and CloudBeaver are optional and not started.

All published ports bind 127.0.0.1. Storage/Arango authentication is enabled,
no public bucket policy is applied, and the app runs as non-root. No Docker
socket, host networking, privileged mode or GPU is used. Keep this development
stack local; Dash/Prefect/MLflow themselves have no added login layer.

Named volumes are scoped by `drg-smoke-local`: outputs-data, postgres-data,
minio-data, arangodb-data and arangodb-app-data. app/worker share /app/outputs.
The image contains code; no source mount hides packaging errors. Rebuild after
source changes. All configured limits total 17.25 GiB and 6 CPUs including initialization jobs;
long-lived services total 15 GiB and 5 CPUs. The worker has 2 CPUs,
4 GiB and one flow at a time. Dash has one Gunicorn worker with two threads to
avoid browser idle connections blocking its request handling. These are local
smoke limits, not a benchmark or a guarantee for larger simulations.

### Run the tiny browser fixture

On Dash's Simulation page, either load `examples/synthetic_ui.yaml` with
**Load parameters**, or edit these controls from their displayed defaults:

| Control | Value |
| --- | --- |
| Maximum order | 1 |
| Number of outer roots / inner roots | 1 / 1 |
| Maximum number of secondary roots | 2 |
| Secondary root minimum / maximum length | 10 / 20 |
| Segments per root | 5 |
| Time steps | 0 |
| Enable soil | Off |
| Soil layer height / width / layers / columns | 0 / 0 / 0 / 0 |
| Random seed | 42 |
| Simulation tag | synthetic-smoke-seed42 |

Leave the remaining values at defaults, as specified in the YAML fixture.
Click **Run procedure** once. A row should appear under Simulation Runs; its
workflow link leads to Prefect. Wait for **Completed**, then open MLflow,
experiment `root_model_simulation`, and select the matching simulation tag/UUID.
Its Artifacts contain timestamped nodes.csv, edges.csv, configuration YAML,
roots.html, hierarchical plot, data-profile HTML and summary-statistics CSV.
Expected counts are 11 nodes/10 edges; the same tables match the CLI fixture.
Do not infer successful completion solely from a toast or the run-history row.

**Save parameters** requests a YAML download. **Save simulation runs** requests
a run-history CSV; it does not export node/edge tables. Both also save to the
shared output volume and local `data` bucket. Browser-triggered creation and
S3 copies were verified. Automated download-event capture timed out, so final
browser Downloads-folder completion remains a manual tester check.

Automation file upload was blocked because the Chrome extension lacks file-URL
access. No browser permission was changed. Manual field entry was used for the
successful UI run. Ordinary manual browser upload of the YAML is a next-week
check, not a claimed pass. The generator's JSON file is for CLI/API; use the
full YAML for the UI because its loader expects every form key.

For a verified export route independent of browser download automation:

```bash
mkdir -p .runtime/docker-export
docker compose --env-file .env.local -p drg-smoke-local \
  -f docker-compose.local.yaml cp app:/app/outputs/. .runtime/docker-export/
```

This copies local task-generated artifacts without removing them. Use a fresh
destination when retaining multiple runs. The MLflow Python client was also
used successfully to download all seven sample artifacts and check SHA256s.

Run history in the Dash table is browser local storage, not the server's durable
record. Keep its CSV when needed; the underlying Prefect, MLflow and graph
records live in volumes and remain discoverable even from a fresh browser.

### Safe stop, restart and persistence

```bash
# Stop task-owned services, retain containers and all data:
docker compose --env-file .env.local -p drg-smoke-local \
  -f docker-compose.local.yaml stop --timeout 30
# Restart retained containers (this Compose version has no start --wait):
docker compose --env-file .env.local -p drg-smoke-local \
  -f docker-compose.local.yaml start
docker compose --env-file .env.local -p drg-smoke-local \
  -f docker-compose.local.yaml ps
# Alternatively remove containers/network while retaining named volumes:
docker compose --env-file .env.local -p drg-smoke-local \
  -f docker-compose.local.yaml down --timeout 30
# Recreate with current images and health checks:
docker compose --env-file .env.local -p drg-smoke-local \
  -f docker-compose.local.yaml up -d --wait --wait-timeout 300
```

Do not add `-v`, prune, delete volumes, or replace `.env.local`. There is no
reason to leave the stack consuming resources all week. Stop/start and normal down/up were executed successfully. Prefect state,
MLflow artifact hashes, ArangoDB counts, S3 exports and shared output hashes
were identical before and after both lifecycle checks. The final service state
is stopped, with all named volumes retained. See the checked-in
[runtime receipt](docs/RUNTIME_RECEIPT.json) for image identities and evidence.

## Tests and troubleshooting

```bash
source .runtime/envs/py310-qualification/bin/activate
export CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
export PREFECT_HOME="$PWD/.runtime/prefect-host"
export MPLCONFIGDIR="$PWD/.runtime/cache/matplotlib"
python -m pytest -q tests/test_scaffold.py tests/test_runtime_paths.py tests/test_simulation_smoke.py
python -m flake8 --count --show-source --statistics \
  deeprootgen app examples scripts/local \
  tests/test_scaffold.py tests/test_runtime_paths.py tests/test_simulation_smoke.py
python -m black --check deeprootgen app \
  tests/test_scaffold.py tests/test_runtime_paths.py tests/test_simulation_smoke.py
git diff --check
```

The commands above scope qualification to this runtime work. An earlier full
`python -m pytest -q` passed four tests; unrelated concurrent grapevine-grid
files subsequently appeared and are preserved. Their tests are outside this
qualification. Once that work is ready, run the complete suite separately.

Four runtime tests pass (three meaningful runtime tests plus the existing
`test_scaffold.py` asserting True). They cover finite/sample geometry,
IDs/schema/counts, seed parity, invalid CLI inputs, existing-output refusal,
no network during direct simulation and export from an unrelated working
directory. The many dependency/Pydantic deprecation warnings remain visible.
These checks do not establish biological or inference correctness.

- **Wrong Python or missing Torch:** check `which python`, `python --version`
  and `python -m pip check` after activation. Use bootstrap; do not global-pip
  packages into system Python or widen the project's Python constraint.
- **Poetry mismatch:** use private Poetry 1.8.3; verify lock hash before changing
  dependencies. Do not regenerate the lock or replace Torch incidentally.
- **Docker denied:** use authorized task execution or the user's normal Docker
  setup. Never chmod the socket or widen persistent access.
- **Build download failures:** preserve logs, verify official registry/source
  availability and proxy settings; do not disable certificate verification or
  silently use an unofficial mirror. Initial builds need network and disk.
- **Port collision:** change only local port variables and restart. Keep all
  host bindings at 127.0.0.1.
- **UI unreachable or queued:** inspect `ps` and targeted logs for `app`,
  `prefect-server`, `prefect-worker`, `prefect-deployments`, `storage-init`.
  One-shot jobs should exit 0; worker must poll the default process pool.
- **Prefect UI cache permission:** retain PREFECT_UI_STATIC_DIRECTORY from the
  local Compose file. Do not make the entire Python installation writable.
- **Slow/large runs:** start with the tiny fixture. Profile generation and
  inference can be expensive; do not infer their capacity from this smoke test.
- **Missing results:** the Dash CSV is history only; use MLflow artifacts or
  the output-volume copy command. Check bucket readiness and worker failure.
- **Git SHA warning in container MLflow logs:** Git is absent from the image;
  use the separate source/runtime receipt, not an inferred MLflow code revision.
- **Exit codes after an explicit stop:** this Prefect CLI prints Aborted and
  exits 1 on SIGINT; MLflow may exit 143 on SIGTERM. Both were observed only
  during the requested final stop. A nonzero exit during startup or a running
  flow requires log inspection and is not an expected pass.
- **Changed database password:** restore the original private configuration for
  existing volumes; do not delete data as a troubleshooting shortcut.

Known scientific questions in [REVIEW_NOTES](docs/REVIEW_NOTES.md) remain open:
base-row/invalid-root treatment, non-finite specific root length, distribution
support and calibration seed propagation. This t=0 sample does not settle them.
No calibration, optimisation, inference, measured-data compatibility or Calvin
raw-data inspection/upload was performed. Those require a separately scoped
scientific/data task. See [architecture](docs/ARCHITECTURE.md) for the code map.
