# Irrigation depth, lateral branching and vineyard spacing

Use the optional top-level `irrigation` setting in a seeded schema-4 root configuration. Depths, radii, coordinates and planting distances are in centimetres. Set `"irrigation": null` or `"irrigation": "rainfed"` for the baseline generator. Omitting the setting, specifying `"treatment": "rainfed"`, or setting `irrigation_depth_cm` to `null` or `"rainfed"` inside the setting also disables the response. Zero is a surface outlet. A positive number is the buried outlet depth below soil surface. A multiplier of 1 gives exactly the baseline branching geometry and consumes no additional random draws.

## Describe the installation

For a continuous line 30 cm below the surface and 15 cm to one side of the focal row, insert the following object into the configuration.

```json
"irrigation": {
  "treatment": "buried_drip",
  "irrigation_depth_cm": 30,
  "line_offsets_cm": [15],
  "across_radius_cm": 30,
  "upper_radius_cm": 15,
  "lower_radius_cm": 20,
  "peak_multiplier": 1.5,
  "response": "add"
}
```

The line runs along vineyard y. Its x coordinate is fixed in the surveyed frame. The across-row radius is the distance from the line to the outer edge of wetting. Upper and lower radii extend from the buried outlet. Add `emitter_spacing_cm`, `emitter_origin_y_cm` and `along_radius_cm` together for a periodic series of discrete emitters. Supply multiple surveyed line offsets explicitly or use one reference line and `row_period_cm` for a regularly repeated irrigation layout. Plant spacing alone does not establish which rows receive water. Overlapping outlets use the maximum local exposure.

For `surface_drip`, set depth to 0 and specify the horizontal footprint. The default `surface_profile` is `plateau`, with full depth weight through 40 cm and a smooth decline to zero at 50 cm. Use `deep_peak` for a maximum at 37.5 cm. For `broad_surface`, set depth to 0 and omit horizontal geometry. This gives all locations in the simulated plot the same depth rule. All footprints give zero weight above the surveyed soil surface. An installation survey or soil-moisture transect should determine which description applies.

## How a daughter is born

The default affected order is 4. The pilot operates on a terminal daughter order and requires both a realized parent curve and an insertion-angle curvature law for the daughter. At each possible site, the parent must meet the larger of the existing minimum and 0.093 cm. The core observation diameter range is a separate analysis input.

Let H be the integral of local exposure, between 0 and 1, over eligible parent length. For a peak multiplier m and background rate λ per centimetre, the expected additional count is (m − 1)λH. Each active parent draws from that Poisson distribution. Under the first-site/count law, λ is (N − 1)/(L − s₁) after the anchored first site. A single first site, failed activation or first site beyond the tip gives zero extra daughters. Under the length-Poisson law, λ is reciprocal mean spacing on the interval between basal and apical exclusions. A parent can draw extras after an active zero background draw. For example, at 10 cm background spacing with 20 fully exposed eligible centimetres, 2× adds two daughters in expectation.

The simulation integrates on the final parent path after placement and curvature. It splits intervals at material and footprint boundaries, applies 16-point Gauss–Legendre quadrature on the pieces, and inverts the integral for random attachment positions. The `add` arm samples extras proportionately to exposure. The `uniform_extra` arm uses exactly the same parent-level count draws and places them uniformly on eligible length. For `redistribute`, the accepted movable daughters are sampled with weight 1 + (m − 1)K. This preserves count and the first-site law’s anchored daughter. The parent cap applies at each new location. A numerical coincidence within 10⁻⁹ cm keeps the existing event. Supplemental births occur before core sampling and use the existing daughter length, taper and curvature laws.

## Recruit wet-zone parents as well as terminals

The terminal law above can only add fine roots on parent length that already crosses the wetting zone. Set `order_sensitivity` to let wetted soil also recruit non-terminal daughters. Its keys are daughter orders from 2 to `parent_order`, and its values s lie between 0 and 1. On an order k − 1 parent, the expected extra order-k count is s(m − 1)λH, using that parent's own exposure and background rate. Each recruited daughter then receives an ordinary native subtree: the same length, taper, branching and curvature laws, keyed by its new organ IDs. The terminal step afterwards also acts on the recruited parents. The terminal order always uses s = 1. A value of 0, or omitting the setting, keeps the terminal-only law draw for draw.

```json
"order_sensitivity": {"3": 0.4, "4": 0.8}
```

Recruitment inserts an attachment node but never moves an existing axis. It is available for `add` and `uniform_extra`. It also requires a stochastic branching law on each affected parent order and insertion-angle curvature at the recruited order and every descendant order. `irrigation.json` reports these births under `upstream`, keyed by daughter order, together with each parent's native subtree size.

## Recruitment budget

Set `max_extra_fraction` to cap wet-zone recruitment. For each recruited order, the total expected extra daughters is capped at this fraction of that order's daughters present before recruitment. Every parent's expectation is scaled by the same factor, so the wet-zone allocation is unchanged. Without the setting the law is uncapped as before. The budget applies to `add` and `uniform_extra`. `irrigation.json` records `budget` with the baseline count, the uncapped expectation and the applied scale. Use it with moisture-directed growth: steering keeps parents inside the wet zone, which raises their exposure, so uncapped recruitment can grow without bound.

## Moisture-directed growth

Set `moisture_tropism` to let roots of chosen orders turn towards wetter soil while they grow. Its keys are root orders and its values are non-negative gains a. At each curvature step of length h, the heading gains h · a · ∇K before normalisation, where K is the exposure above and ∇K is its gradient per centimetre in the model frame.

```json
"moisture_tropism": {"1": 0.5, "2": 1.0, "3": 1.0, "4": 1.5, "5": 1.5}
```

The gradient is the analytic derivative on soil support. It is zero outside the footprint, at its centre and above the surface, and nothing is evaluated in air. Roots near the edge of the wet zone are therefore turned back into it, and soil beyond the footprint exerts no pull. With the cosine kernel, the largest gradient across the row is π/(2R) per centimetre, about 0.04 for R = 40 cm. A gain of 1 then turns a heading by up to about 0.08 rad per 2 cm step. The term uses no random draws, so streams stay paired with the same configuration without it. A gain of 0, or omitting the setting, reproduces the old law exactly. It applies only to orders with correlated curvature and only while the irrigation response is active (`peak_multiplier` > 1). Resolution rejects a gain if `step_cm × (downward drift + gain × π / (2 × shortest kernel length))` ≥ 1, because one step could then reverse a heading. Order keys must be canonical, so `"2"` is accepted and `"02"` is rejected. Curvature receipts record the gain, and `moisture_tropism` in the diagnostics lists the active orders.

## Run a single vine or a planted neighbourhood

```bash
python -m deeprootgen simulate \
  --config examples/research/irrigated_terminal_daughters.json \
  --outdir /tmp/irrigated-vine

python -m deeprootgen neighbourhood \
  --config examples/research/irrigated_terminal_daughters.json \
  --mode independent --vine-distance-cm 200 --row-distance-cm 300 \
  --outdir /tmp/irrigated-neighbours
```

The second command creates a 3 × 3 grid of nine vines. The example uses 200 cm along each row and 300 cm between rows. The central vine retains the configured seed. Independent neighbours receive reproducible, distinct seeds. Use `--mode translated` to place the same seeded scaffold at each crown. With an active footprint the generator evaluates wetting at every crown’s actual field position, even for a repeated scaffold. For irregular layouts, pass `--origins path.json` containing distinct [x, y] offsets including [0, 0]. Python callers can use `generate_neighbourhood(config, mode="independent", vine_distance_cm=200, row_distance_cm=300)`.

A single-vine export includes `irrigation.json` for an active response. It records each parent’s decision, eligible and exposure-weighted length, count intensity, draws and accepted births, plus their surveyed coordinates. The neighbourhood export includes seeds, placement and geometry identity per vine in `plants.csv`, resolved offsets in `origins.json`, replay settings and units. Positive depth d equals soil surface z minus model z. `origin_x_cm` and `origin_y_cm` register a focal crown’s local frame to the vineyard. Optional `reflect_x` and `reflect_y` take +1 or −1. The single-vine graph stays in its native frame and the neighbourhood graph is exported in the surveyed horizontal frame.

[Runnable synthetic configuration](../../examples/research/irrigated_terminal_daughters.json)
