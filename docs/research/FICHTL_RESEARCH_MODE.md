# Optional Fichtl-inspired research mode

Research interface checkpoint; package version remains 1.0.0 and legacy remains
the default. This mode is a static approximation informed by
[Fichtl et al. 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11633832/), not exact
CPlantBox replay, an inferred calibration or biological qualification.

Set `tropism_mode="fichtl2024"` and provide every probability, sigma, trial and
insertion-angle parameter explicitly. Legacy `gravitropism` must be zero in this
mode; only orders 1–3 are supported. The public SO4/T2 example supplies these
settings and a nine-primary scaffold. Its length bounds approximate between-vine
means/SDs as per-organ uniform distributions; daughter lengths undergo the
existing order-dependent reduction. Rejection-truncated normal insertion angles
do not have the same realised mean/SD as the untruncated inputs. Global spacing,
diameters and count/growth settings contain engineering approximations.

Angles use degrees at the insertion API; angular perturbations use
`sigma*sqrt(segment_length_cm)` in radians. Type 2 selects the downward objective
with probability .65 in the public example, otherwise a horizontal objective;
type 3 uses the downward objective. Trial coefficients control stochastically
rounded candidate counts. Preserve seeds and all explicit settings.

The native optional mode filters candidate endpoints against its declared soil
surface and uses its documented feasible downward fallback. It disables the
legacy downward-apex requirement and post-tropism whole-organ reorientation.
The later controlled-replay checkpoint has a distinct common minimum-angle
projection rule; the two paths must not be described as identical.

## Offline example

```bash
python -m deeprootgen simulate --config examples/research/so4_t2_fichtl2024_v4.json --outdir .runtime/so4-research-example
python -m pytest -q tests/test_fichtl_tropism.py
```

Use a new output directory and the locked Python 3.10 environment. The example
sets `soil_surface_z_cm=20`; coordinates retain the simulator-base origin. A
model-side declared depth is `20-z`. This does not establish the observed-side
RSML soil reference or vertical-axis transform. Offset surfaces are not thereby
qualified for the existing UI, calibration or summary-statistic interfaces.

`tests/fixtures/fichtl_legacy_golden.json` contains synthetic pre-change legacy
regressions. Additional fixtures check seed repeatability, graph attachment,
length conservation, parameter rejection and surface handling. No observation
data, biomass inference, services or empirical fitting are needed.
