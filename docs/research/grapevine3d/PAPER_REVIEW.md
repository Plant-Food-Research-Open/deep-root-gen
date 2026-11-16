# Grapevine3D evidence review

DRG-G3D-01, 14 November 2026. **Evidence package prepared; scientific acceptance
pending; no model execution or fitting.** Start with the
[proposed pilot](PILOT_SPECIFICATION.md), [observation contract](OBSERVATION_CONTRACT.md)
and [parameter evidence matrix](PARAMETER_EVIDENCE.csv).

## Source identity and access

The researcher is **Lukas Fichtl**. The two primary sources serve different roles:

| Source | Version inspected | Role and access limits |
|---|---|---|
| [Fichtl et al. 2024, Plant Phenomics 6:0280](https://pmc.ncbi.nlm.nih.gov/articles/PMC11633832/), DOI 10.34133/plantphenomics.0280 | Published 11 December 2024; live PMC HTML, Tables 1/2/4, methods and pseudocode | Parameterization, recovery limitations, measured initialization and probabilistic tropism |
| [2024 supplement](https://pmc.ncbi.nlm.nih.gov/articles/instance/11633832/bin/plantphenomics.0280.f1.docx) | Link located, binary retrieval failed | Sections S1/S2 and Figs S1–S7, including direct Fig. S7 content: **UNAVAILABLE** in this review; main-text account reviewed |
| [Fichtl et al. 2025, Annals of Botany 136:1613–1629](https://juser.fz-juelich.de/record/1049167/files/mcaf193.pdf), DOI 10.1093/aob/mcaf193 | Published article, 17-page institutional PDF; methods p. 1616 and Figs 2/5/7 | Dry mass, SRL, four destructive sampling campaigns and spatial architecture |
| [2025 PMC record and supplement listing](https://pmc.ncbi.nlm.nih.gov/articles/PMC12718041/) | Search index exposes `mcaf193_supplementary_data.pdf` (7.8 MB); live page returned browser verification | Numerical Tables S2/S4/S5/S6 **UNAVAILABLE** here; existence is verified, numerical content is not |
| [Grapevine3D](https://doi.org/10.5281/zenodo.15632062) | Named local archive and prepared files checked locally; live Zenodo record unavailable through the web tool | Local bytes are frozen in the private manifest; no claim that these are the newest archive version |

No public binary was successfully downloaded in this run: shell DNS was
unavailable; web retrieval supplied readable article text. Therefore there is
no invented download hash for either paper or inaccessible supplement. Local
input hashes and retrieval/code snapshots are retained separately. Missing
supplements do not prevent the RLD-only proposal; they prevent numeric biomass
adoption and an exact historical parameter replay.

Author code inspected through the connected GitHub reader was frozen at:

- CPlantBox default snapshot `ebe6b08c09eb6a4b38a568042c8193bfab8cd12a`:
  [estimator](https://github.com/Plant-Root-Soil-Interactions-Modelling/CPlantBox/blob/ebe6b08c09eb6a4b38a568042c8193bfab8cd12a/gui/estimate/estimate_data.py),
  [tropism implementation](https://github.com/Plant-Root-Soil-Interactions-Modelling/CPlantBox/blob/ebe6b08c09eb6a4b38a568042c8193bfab8cd12a/src/structural/tropism.cpp),
  and `experimental/wine_fichtl/estimate_wine.py` / `estimate_wine_fineroots.py`.
- Later author branch `perennial2026`, snapshot
  `7d190b50728c514baab6ccfbaa49ad98156f217d`:
  [101-14 parameter XML](https://github.com/Plant-Root-Soil-Interactions-Modelling/CPlantBox/blob/7d190b50728c514baab6ccfbaa49ad98156f217d/modelparameter/structural/rootsystem/Parameter_101-14.xml)
  and corresponding SO4/R110 files. These are useful corroborating code, **not
  verified exact 2024 executable parameter files**. Later thermal-time and
  perennial mechanisms are outside this task.

## Sampling, overlap and observation limits

The 2024 experiment sampled 48 different vines: three rootstocks, two campaigns
(July/November 2023; 3/6 months after planting), eight vines per group. The 2025
study describes 96 vines at T1–T4 (3/6/15/18 months after planting), expanding
the same May-2023 vineyard experiment through July/November 2024. Rootstocks
are 101-14, SO4 and Richter 110; `R110`, `110R` and `Richter 110` are aliases,
not extra genotypes. Riesling N90 is the common scion. The main design has four
blocks, two replicate plots per genotype per block, one excavated vine per
replicate per campaign. These are destructive cohorts, not longitudinal vines
or independent sites. The 2024 Cina method-validation vines and the 2025
SO4/R110 early-growth side experiment are distinct experiments.

**Overlap decision:** treat the 2024 T1/T2 evidence as potentially derived from
the archive's T1/T2 vines. Exact per-vine cross-publication correspondence and
archive-version identity were not established. Paper-derived group parameters
therefore contaminate claims of fully independent validation on those groups.
Metadata QC of all vines is permissible; no held-out morphology was used to
choose parameters or tolerances. Experimental block/plot mapping remains
unverified: an ID prefix must not silently become a block label.

The 2024 methods report one-year-old nursery cuttings with adventitious roots
pruned to about 10–15 cm and the stem base about 20 cm below soil. Caliper
diameters were measured except for fine roots; visible fine roots at least
0.5 cm long were digitized. Both excavation loss and digitization limits matter.
Table 1's separate Cina comparison has only two vines per extraction method:
excavated fine-root lengths 640.7/689.8 cm versus washout 1776.9/1449.7 cm.
This supports missed fine length, not a transferable correction factor per
vine, depth or voxel.

The technical length RMSE of 0.154 cm, mean bias 0.075 cm and repeated-point
mean separation 0.182 cm in the 2024 paper describe digitization checks. They
are neither voxel-RLD standard deviations nor tolerances for biological model
adequacy. Use coordinate-error sensitivity as a later sensitivity scenario.

## Initialization and tropism: what transfers

CPlantBox imports measured type-1 adventitious geometry as a static scaffold,
retains it with effectively infinite lifetime, and attaches growing type-2
roots at measured emergence positions. Emergence time is zero and emergence
probability one in this setup. Its 180-day illustrations consequently include
measured initialization. Scaffold count, positions and geometry cannot then
be independent validation endpoints.

Let a candidate unit heading be `q`, segment increment `dx` in cm, a standard
normal draw `Z`, and uniform azimuth `beta`. Inspected CPlantBox code samples

```text
alpha = sigma * Z * sqrt(dx),       beta ~ Uniform(0, 2*pi)
Jgravity(q) = q_z,                  Jplagiotropic(q) = abs(q_z)
```

The paper mixes the two objectives with type-2 downward weights
`p = 0.85 / 0.65 / 0.95` for 101-14/SO4/R110; type 3 is gravitropic.
It reports `N=2/1` for type 2/3 and `sigma=0.2`. These are tuned model choices.
The inspected C++ scales the extra-candidate count by `N*sqrt(dx)` with
stochastic rounding, in addition to an initial candidate. Thus `sigma` acts
dimensionally as radians/sqrt(cm), and `N` as a discretization-dependent trial
intensity. Paper pseudocode draws the Bernoulli inside objective evaluation;
its precise switching granularity is not established by an exact 2024 override.
Do not claim permanent root-level tropism classes or exact stochastic replay.

In merged DeepRootGen, [root.py](../../../deeprootgen/model/root.py) `run()`
(lines 801–807) constructs a static system with `grow()` disabled. Gravity
(809–845) applies

```text
u_new = normalize((1-g)*u_old + g*(0,0,-1)),     0 <= g <= 1
```

while preserving each segment's geometric length and attachment. `g` is a
dimensionless direction blend, **not** CPlantBox's `p`. `root_vary` is uniform
pitch/yaw noise in degrees per constructed segment, with discretization
dependence; it is not `sigma`. Hard-coded primary/lateral rotations do not
provide a free insertion-angle control, order-specific tropism or row bias.
All primaries share one base point, without the measured distributed scaffold.
The observation proposal translates that point to 20 cm depth; it does not
add a biological crown mechanism.

## Parameter evidence and ambiguous printed units

[PARAMETER_EVIDENCE.csv](PARAMETER_EVIDENCE.csv) preserves every Table 4 entry,
including dashes, and selected observation/measurement constraints. Allowed
decisions are `DIRECT`, `TRANSFORM_REQUIRED`, `VALIDATION_ONLY`, `MODEL_GAP`,
`UNAVAILABLE`. `DIRECT` means an operational definition can be reused; it is
not permission to adopt a coefficient without a scientific decision.

| Family | Evidence | Decision |
|---|---|---|
| Maximum length | Table 4 type2/type3 `lmax`: 99.5/47.2, 89.9/66.7, 110.1/77.4 cm | `TRANSFORM_REQUIRED`: attainable dynamic maximum differs from a current static length draw |
| Elongation | `r`: .28/.07, .29/.08, .37/.10; table prints cm, author XML specifies cm/day | `MODEL_GAP`: no temporal growth in current `run()` |
| Basal/apical zones | Type-2 `lb` and `la` in cm with large SD | `MODEL_GAP`: generator uses global fractional branching windows, not order-specific measured zones |
| Interbranch distance | Type-2 `ln`: 4.1±3.2, 4.8±3.5, 6.7±6.4 cm at T2 | `TRANSFORM_REQUIRED`: one global lognormal spacing and a count cap differ from these pooled root-type estimates |
| Insertion angle | Table prints approximately 50–58 rad | `TRANSFORM_REQUIRED`: estimator computes degrees, folds obtuse angles and converts to radians on write; intermediate XML numbers still have misleading radian comments |
| Radius | Table 4 type-2 `.23/.20/.22 cm` “radius” equals Table 2 type-2 diameter | `UNAVAILABLE` for mass: later XML radii about .044375/.039920/.046853 cm do not resolve by simply doubling/halving |
| Angular spread/tropism | `sigma`, `N` and `p` above | `MODEL_GAP` for direct transfer; preserve definitions rather than renaming controls |
| Root order/class | Nursery scaffold/type-2/type-3 are biological/model classes | `TRANSFORM_REQUIRED`: distinguish archive nesting order from these classes and diameter classes |

The author estimator also contains resolution scaling and an explicit
`/10 RSWMS hack` in parameter writing. Later XMLs and overrides cannot be
used to silently repair the published radius or angle labels. Table 2 prints
an anomalous R110/T1 type-1 diameter `0.035±0.06 cm`; it remains a printed
ambiguity, not a corrected measurement.

For the provisional 101-14/T1 group, Table 2 gives eight-vine means±SD:
type-1 count 11±3 and mean length 14.4±3.4 cm; type-2 count 37±11 and mean
length 15.6±5.2 cm; type-3 count 61±19 and mean length 4.5±0.7 cm. The SD of
vine-level means does not define an individual-organ sampling distribution.
Do not convert these into exact uniform bounds without qualification.
The proposed numerical search envelope is explicitly an engineering scenario.

There is a further support/definition ambiguity: Table 2's 101-14/T1
type-specific lengths sum to 972 cm versus a printed total of 1106 cm.
Differences between products of means and mean totals may reflect covariance;
non-reconciling exhaustive order totals need the original definitions. The
existing RSML-versus-published T4 length discrepancy was rechecked in the local
report and remains unresolved. Do not add inferred parent connectors, stem
length or a fitted correction factor to force agreement.

## Biomass and SRL decision

The 2025 methods (p. 1616) separate roots, stem, shoots and leaves, record wet
weights, then dry material at **60°C for about two weeks** before measuring
dry weights. Woody compartment fractions use the sum of root/stem/shoot dry
mass, excluding leaves. Published whole-root SRL is

```text
SRL = digitized total root length / recovered root dry mass    [cm/g]
```

It combines digitization and recovery limitations. Table S2 contains biomass
results; S4 contains global traits/SRL; S5/S6 contain depth/horizontal traits.
The main text reports SO4/T1 SRL 192.1 cm/g and approximate T4 convergence to
27–32 cm/g, but neither supplies the missing 101-14/T1 per-vine dry masses or
their uncertainty. We did not digitize plot bars or invent supplement values.

The named local Grapevine3D DATA tree has no candidate CSV/XLS/XLSX/TSV mass
table, and the prepared grid/summary have no mass or SRL fields. All 96 vines
therefore remain unmatched to dry mass in this scoped audit. Duplicate mass
keys are **not assessable**, rather than zero. Private coring and management
files were not opened for this work.

**Diameter qualification:** RSML lacks diameter/radius fields in the inspected
archive, but VTP has a variable `radius` array. Presence alone does not establish
units, measured versus assigned status, mapping to RSML edges, taper or fine-root
coverage. The earlier blanket “no diameter evidence” assumption must therefore
be narrowed. VTP radius is a follow-up provenance lead; it is not approved for
mass conversion. Local field summaries stay in the private report.

**Decision: biomass is unconstrained in the first proposal.** If a matched
measurement table becomes available, prefer whole-root dry mass with recovered
compartment/support reconciled. Group-level means can constrain a group
ensemble, not every vine as an exact observation. Compatible SRL can define
`M=L/SRL`, with uncertainty and support mismatch propagated. A uniform-SRL
voxel scenario `mass_density=RLD/SRL` is derived and is not spatial mass
validation. Since SRL is calculated from length and mass, do not count all
three as independent targets.

For a later diameter/density route, `M=sum(rho*pi*d^2*L/4)` in g is valid only
with defensible dry density and diameter provenance. RLD alone cannot identify
both. Current [whole-RSA SRL](../../../deeprootgen/statistics/summary_statistics.py)
(398–409) now uses total length/total mass: the historical sum-of-ratios defect
is superseded. `AverageSpecificRootLength` is a different organ-average
statistic and does not match the paper's whole-plant SRL.

## Review outcome

Public-literature and current-source reviews were performed by separate agents;
neither received Contacts data. A further independent contract review is
recorded in [the pilot specification](PILOT_SPECIFICATION.md). The evidence
supports a bounded **digitized-architecture feasibility** proposal, with biomass,
exact CPlantBox replay and biological completeness explicitly unresolved.
It does not establish physiological validity, drought performance or recovery
of a unique excavated topology.
