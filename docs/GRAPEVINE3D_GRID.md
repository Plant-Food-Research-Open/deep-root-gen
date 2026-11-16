# Grapevine3D 10 cm root-length grid

**Historical v1 material — superseded for physical soil comparisons.**
Read [the active v2 research state](research/ACTIVE_SO4_RESEARCH.md) first. The recovered soil frame
uses RSML stem point0 as soil, point1 as basal, and explicit canonical horizontal
axes. The original prepared grids, receipts and text below are preserved as
history; earlier calls to increase shallow allocation are superseded.
The coordinate audit is completed locally; current work targets population
representation under the accepted13-trait/3-profile criterion.


This is a local, descriptive analysis of the open [Grapevine3D dataset](https://doi.org/10.5281/zenodo.15632062). It prepares a spatial observation for later comparison with DeepRootGen. It does not fit or change the generator.

For the staged reconstruction goal, upstream integration checks, paper-derived
parameters and biomass options, see the [research plan](GRAPEVINE3D_RECONSTRUCTION_PLAN.md)
and its [first evidence-review task](tasks/GRAPEVINE3D_01_EVIDENCE_AND_CONTRACT.md).

## Run

The downloaded archive must contain `RSML_Files/T1` through `T4`. Use a new or empty output directory outside this repository:

```bash
python3 scripts/data/grapevine3d_grid.py \
  --data-dir "$DATA_DIR" \
  --output-dir "$DERIVED_DIR" \
  --plot-vine T4/B-11
```

The converter itself uses the Python standard library; only `--plot-vine` needs Matplotlib. It does not import DeepRootGen, start its services, or transmit data. It was checked locally with Python 3.14; the project application still requires its pinned Python 3.10 environment.

Outputs:

- `voxel_grid.csv`: one row for **every** 10 × 10 × 10 cm cube in each vine's bounded prism, including cubes with zero *digitized* root length. It gives indices, lower bounds, total root length, root length density in cm/cm³, and lengths by RSML root class. Cube indices are half-open: `ix=0` covers `0 ≤ x < 10 cm`.
- `vine_summary.csv`: vine-level length conservation, original length, excluded above-surface length, soil length, occupied/total cube counts, soil-surface RSML coordinates, grid bounds and source SHA-256.
- `analysis_metadata.json`: method, units, source-file hashes and coverage definition.
- `architecture_T4_B-11.png` when requested: a 3D root-segment view and a top-view heatmap of length summed through depth. The source `.vtp` files can also be opened in ParaView for interactive 3D inspection.

## Scientific definition

The RSML metadata declares **cm**. Its first stem polyline point is the graft point; the second marks soil level. The script subtracts that second point from RSML coordinates, using `x` across the row, `y` along the row, and positive `z` as depth below the surface. These axis interpretations follow the dataset's associated study; the raw `.txt` digitizer axes have a different orientation and are **not** read by this converter.

Only consecutive points **within each RSML root polyline** form segments. Stem length and an inferred link from each root to its parent are excluded. Each segment is clipped at depth zero and split at every intersected cube face; its Euclidean length is allocated by the midpoint of each piece. The reported root length density is `digitized root length (cm) / 1000 cm³` for a 10 cm cube. It is not a soil-core measurement. The source can miss small or broken roots. The script records the above-surface portion separately in the vine summary rather than silently counting it as soil root length.

The full grid spans each vine's observed x/y range (and includes the vine centre) and depth 0 to its deepest occupied cube. A zero means **no digitized RSML segment in that cube**. It does not imply complete detection of living roots, and no absence can be inferred outside the output prism. The source contains no segment diameters or tissue-density measurements sufficient for a segment-level biomass estimate. Do not multiply these root lengths by DeepRootGen's tissue-density parameter to infer mass.

## Verification and next Codex task

The focused tests check face crossings, a 3D diagonal, soil-surface clipping, nested RSML roots and length conservation. A full-data run should check that there are 96 vines (8 per rootstock per timepoint), that every `grid_length_cm` equals `soil_length_cm`, and that summing `voxel_grid.csv` reproduces each vine's summary. Record any above-surface length and compare root-length aggregates with the associated paper before interpreting biological differences.

In the local 10 cm run on 2026-10-30, all 96 RSML files passed the length checks. The grid had 63,653 cubes, of which 12,383 contained digitized length. The excluded above-surface portions summed to 5,100 cm across vines, so the clipped soil length is **not** interchangeable with the original whole-root length. As another check, the T4 mean of *unclipped consecutive RSML segments* was 4,456 cm (101-14), 5,063 cm (SO4), and 5,666 cm (R110), versus 4,597, 5,267, and 5,806 cm in the [associated paper](https://juser.fz-juelich.de/record/1049167/files/mcaf193.pdf). The remaining difference has not been reconciled with the authors' reconstruction method. Do not add a straight connector from every child root to its XML parent as a shortcut: some such connectors in the archive would be implausibly long.

**Ready-to-use follow-up task:** Build a **read-only DeepRootGen-to-Grapevine3D comparison** using this derived grid. First define and record a common spatial domain for observed and simulated vines, a root-class mapping, the simulation's coordinate rotation/translation and soil-surface convention, and whether to compare total digitized length or class-specific length. Convert *simulated segments*, including portions crossing cube faces, with the same grid algorithm; do not assign an entire segment to its endpoint cube. Compare per-vine total length, depth profile, top-view length map and 3D cube length using descriptive plots and clearly labelled metrics. Keep observed and simulated zero/support masks separate. Stratify the 96 destructively sampled vines by rootstock and timepoint; they are not 96 repeated measures of the same plant. Do not calibrate, change growth rules, infer biomass or declare biological validation without a separate scientific definition and authorization.
