# Offline runtime and optional local services

Use Python >=3.10,<3.11 and the existing Poetry lock. This integration does not upgrade dependencies. The model eagerly imports Torch/PyG; a NumPy-only environment cannot run it. See [development guidance](docs/DEVELOPMENT.md) for historical setup evidence versus recipes.

## Offline checks

After installing the locked development/Torch environment, run:

```bash
python -m pytest -p no:cacheprovider --run-integration
python -m deeprootgen simulate --config examples/synthetic_minimal.json --outdir .runtime/synthetic-new
python scripts/research/parameter_search.py --config examples/research/search_synthetic.json --outdir .runtime/search-new
```

The search command above validates only. Execution requires `--execute`; all example inputs are invented. Tests include synthetic simulator integration and mocked flow utilities; they do not qualify real storage/database services, empirical calibration or biological realism.

The optional bootstrap helper accepts an explicit Python 3.10 executable and creates a private environment using the existing lock. It performs dependency installation, so inspect it before use. This PR does not execute that helper or install dependencies.

## Optional local service recipe

`docker-compose.local.yaml` and `dockerfiles/*/Dockerfile.local` provide a separate local service configuration. Ports bind loopback; resources are bounded. Credentials are caller-generated, never supplied by the repository:

```bash
python scripts/local/configure.py
```

This creates a new ignored `.env.local`, refuses to overwrite an existing file, and does not print generated secrets. `.env.local.example` contains placeholders only. Inspect the compose file before any build/start. No Docker build, service startup, database/storage mutation, deployment, fitting or training was executed to qualify this integration. Existing historical runtime receipts are deliberately not published here.

Library output paths respect `DEEPROOTGEN_OUTPUT_DIR`. The ordinary CLI accepts native `RootSimulationModel` JSON. `CohortRootGenerator` uses its separate dictionary/API and root-only observation projection; see [model review](docs/MODEL_REVIEW_GUIDE.md). Full crown support edges must not be scored as root material.

Keep raw observations, empirical configuration/reference files, credentials, environments, caches and generated graphs/results out of version control and deployment/build contexts.
