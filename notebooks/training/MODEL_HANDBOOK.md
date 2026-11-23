# DeepRootGen model handbook for training

DeepRootGen produces a static, stochastic 3D root architecture. The
schema-4 document defines the baseline, optional construction laws, and
random seed. The simulator resolves the configuration, lays out primary
roots, places daughters, constructs the paths and assigns material and
diameter. Its root graph becomes a prediction of measured data only after
applying a matching observation rule.

## Configure the architecture

Baseline values belong in `parameters`. Enable a supported law with
`enabled: true` and its `settings` in the correct section of the document.
Per-order feature maps use string order keys such as `"2"`. Use
**Active laws by order** in Dash or `--explain-config` in the CLI before
choosing a range. Fit the field consumed by the selected law. The resolver
checks which calculations own each feature.

| Observed pattern | Candidate controls to explore | Output to inspect |
|---|---|---|
| More primaries or a different crown spread | `primary_root_count`, `primary_origins`, `primary_placement` | Count and origin of primary axes, inclination and bearing |
| Insufficient reach | Active primary length settings, order-specific `lengths`, active direction or `curvature` controls | Contour length versus vertical depth, lateral reach, and cutoff at the soil boundary |
| Too many or too few branches | `branching` probability, daughter count, or eligible spacing and local diameter gate | Eligible and realized branches by parent order |
| Branches cluster in the wrong place | `branch_sites`, `attachment_relocation`, or active insertion and direction settings | Attachment location, connected descendants and where root length is deposited |
| Diameter and dry mass disagree | `taper`, optional `parent_diameter_cap`, tissue density and the reporting diameter split | Segment diameter along the axis, length and mass by band, and separate crown inclusion |
| Different placement or retention by depth or row position | Local research variants, including a training-fitted spatial surface and its zero-effect baseline | Held-core loss, depth profile, miss and false-hit rates, and per-vine dry mass |

Some optional controls live outside the `features` block. Use the
[schema-4 execution guide](../../docs/NATIVE_EXECUTION.md) and a checked-in
[design example](../../examples/design) for the exact nesting and units.
The [full generator handbook](../../docs/DEEPROOTGEN_HANDBOOK.md) covers
more features, including materialization, allocation and cohort controls.
Use the [placement experiments guide](../../docs/research/PLACEMENT_EXPERIMENT_OPTIONS.md)
for research operators and their comparison designs.

## Read a simulation

For a first run, use the invented JSON described in the [quickstart](QUICKSTART.md).
The CLI and notebook can run locally with a saved input.

| Output | Use |
|---|---|
| `roots.html` | Rotate the graph and inspect crown shape, spread and above-soil segments. |
| `organs.csv`, `nodes.csv`, `edges.csv` | Compare axes and graph topology. Join edge endpoints to node IDs. Verify connector and invalid-node inclusion against the measurement definition. |
| `branching.json` when produced | Check eligible and realized branching and any failed attachment gates. |
| `root_summary.json` when produced | Inspect realized root traits and material summaries. |
| `execution.json`, `run_manifest.json` | Check effective configuration, seed and provenance before comparing runs. |
| `trials.csv`, `best-configuration.json` from Architecture Search | Check completed and failed trials, then replay the selected input with its saved seed. |

Lengths and simulator geometry normally use cm. Diameter classes from
field coring may be supplied in mm. Declared soil elevation increases
upwards, so depth is soil-surface elevation minus vertical coordinate.
Root contour length follows the path and can exceed its vertical reach.
Root order follows the attachment topology. Cohort maturity controls
properties of primary trees and their descendants.

**Where to run.** Use **Simulation** for one configuration, **Architecture
Search** for a bounded whole-root scalar fit, and **Core Comparison** to
evaluate aligned held predictions. For a fresh field study work through
the [data and fitting guide](FRESH_DATA_WITH_CLAUDE.md).

## Terms used in the lessons

| Term | Meaning |
|---|---|
| Observation support | The roots and physical area or volume represented by a measurement. |
| Observation operator | The calculation that applies that measurement definition to a simulated graph. |
| Section and tube IDs | One key identifies an interval. A second key groups intervals sampled from the same tube. |
| Coring surface and zero-strength control | A smooth estimate across position and depth, and a matched comparison with its effect switched off. |
| Paired seeds and baseline | The same list of random seeds applied to variants and to the unchanged comparison configuration. |
| Holdout | Independent observations reserved for evaluation of the frozen configuration. |
