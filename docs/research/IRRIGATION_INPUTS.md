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
