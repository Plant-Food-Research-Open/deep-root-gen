# Claude task prompt: repair DeepRootGen's local dashboard deployments

Copy the task below into Claude Code from the root of the DeepRootGen checkout.

## Task to paste

Work in `/home/jzhu/Workspace/Github/FruitCropXL/13-deep-root-gen-PFR-open`. Read `AGENTS.md`, its inherited instructions, the repo-local Python engineering skill, and [the UI examples](../DASH_UI_EXAMPLES.md) at `docs/DASH_UI_EXAMPLES.md`. Record the checkout revision, relevant uncommitted files, active local Compose projects and the app/worker code or image identities. Preserve existing changes, data, run history, volumes and credentials.

**Goal.** Make one supported local Dash URL serve and run the current Simulation, Optimisation, Architecture Search, Sensitivity Analysis, Approximate Bayesian Computation (ABC), Sequential Neural Posterior Estimation (SNPE) and Surrogate Model workflows. Verify the exploratory pages and the optional BentoML calls from **Deployments**. A user should see a clear validation, availability, queue, running, success or failure message after taking an action.

**Reproduce the reported failure first.** The review dashboard at `127.0.0.1:18002` accepted the Simulation form after the optional fine-root targets were cleared. Its callback then returned HTTP 500 because its Prefect server at port `14202` returned 404 for `simulation/run_simulation_flow`. That server registered only Architecture Search. The older full stack at ports `18001`/ `14201` had a completed Simulation and lacked the Architecture Search callback. Architecture Search also rejected spreadsheet-style pasted targets with tabs or spaces. Use literal commas to establish the valid baseline. Recheck these observations live before using either stack for repairs. Use an isolated loopback Compose project with unused ports for validation if the existing services are in use.

### Scope and implementation

1. **Trace the integration points.** Map the Dash page callbacks and their request payloads to the actual Prefect flow/deployment names, worker pool, image, entrypoint and shared output path. Start with `app/pages/`, `app/flows/prefect.yaml`, `docker-compose.local.yaml`, `dockerfiles/python/Dockerfile.local`, `scripts/local/initialize.py`, and `deeprootgen/pipeline/experiment.py`. Check that the built image has the current pages, forms, flows and Python modules. Confirm that the worker and Dash point to the same Prefect instance; confirm browser-facing links use the published local ports. Verify the readiness and artifact dependencies of each workflow, including MLflow, object storage, graph storage and writable outputs as applicable.
2. **Repair the supported local startup path.** Keep one authoritative deployment manifest and make registration safe to rerun. Test all seven names below against the same API and confirm a live worker consumes the intended queue. Check service restarts and preserve prior run records. Treat a successful page load, API health check, deployment listing or accepted submission as an intermediate check.
3. **Make feedback actionable.** Validate missing or malformed uploads, incompatible controls, invalid ranges, optional fraction targets without allocation bounds, and CSV headers at the page boundary. Preserve the submitted form on errors. Report missing deployment, unreachable service, worker failure and missing artifact separately. Show the run ID or link when a worker run exists. Test that **Check setup** does not submit a job. Avoid accidental duplicate submissions, especially when a network error leaves the result of a request uncertain. Keep existing valid schema-4 files and supported legacy calibration inputs usable. Keep the two root fraction inputs optional and in `[0, 1]`, with a clear hint about allocation controls.
4. **Verify the other UI routes.** EDA and Core Comparison should complete their examples independently of a Prefect worker. On **Deployments**, test Optimisation, Sensitivity, ABC, SNPE and Surrogate BentoML calls against compatible, explicitly identified synthetic artifacts in the local test stores. Check `docker-compose.model-deploy.yaml`, `app/deployments/` and the model registration and import logic in `deeprootgen/calibration/model_versioning.py`. Each endpoint should report missing model version, connection failure or invalid input clearly. Keep optional model serving unavailable with a visible explanation until its prerequisites are met. For any unsupported graph or inference mode, report the precise gap and expose that boundary in the UI.
5. **Update the documentation from the result.** Keep `docs/DASH_UI_EXAMPLES.md`, `RUNNING.md` and other affected entrypoints accurate. Give each page exact controls, a synthetic input, expected result and artifact location. Mark whether a check ran in the browser against the real worker, used a test double, or remains blocked. Record the supported startup command, one browser URL, service status checks, and instructions to recover without removing persistent data.

| Dash workflow | Prefect deployment |
|---|---|
| Simulation | `simulation/run_simulation_flow` |
| Optimisation | `optimisation/run_optimisation_flow` |
| Architecture Search | `architecture_search/run_architecture_search_flow` |
| Sensitivity Analysis | `sensitivity_analysis/run_sensitivity_analysis_flow` |
| Approximate Bayesian Computation | `abc/run_abc_flow` |
| Sequential Neural Posterior Estimation | `snpe/run_snpe_flow` |
| Surrogate Model | `surrogate/run_surrogate_flow` |

### Evidence and completion

- Use the existing Python 3.10 lock and smallest useful synthetic fixtures. Limit service and model-serving checks to the local test stack. Use bounded synthetic fits or training only where needed to verify a workflow. Keep raw observations, empirical fits and credentials out of prompts, test uploads, images and logs. Preserve the application algorithms, priors, objectives and calibrated defaults. Raise any needed scientific change separately.
- For each worker-backed action, record the tested input, observed browser feedback, deployment, run ID, terminal state, and a readable result artifact tied to that run. Verify node/edge CSVs for Simulation, a known three-primary-root result for the two fitting examples, and the method-specific outputs listed in the UI guide for the other flows. Confirm the same base and replay seed during replays.
- For each optional inference endpoint, verify the artifact identity and its expected request/response shape, then check that Dash offers a readable CSV. Use a synthetic artifact or an isolated test double for contract tests. Label test doubles and report live readiness separately. If a route cannot be fully exercised, identify the exact blocker and the smallest remaining check.
- Include focused regression checks for missing deployment, invalid and valid inputs, no-submit preview, worker failure and result export. Report the executed commands, image or source identity, files changed, current URL, verified routes and open items. Preserve the existing working tree and leave publication or production deployment to a separate request.
