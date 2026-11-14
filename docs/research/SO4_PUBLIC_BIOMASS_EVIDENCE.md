# SO4/T2 public biomass evidence and unresolved qualifications

This note records public evidence only. It supplies no fitted parameters or
comparison results and does not activate a biomass acceptance contract.

Fichtl et al. (2025), supplementary Table S2, reports SO4/T2 root dry mass
**22.2 ± 7.0 g**, with the caption identifying mean ± standard deviation.
The study design uses eight vines per genotype and timepoint; effective sample
size for this particular table entry is not separately tabulated. Methods
separate roots, stem, shoots and leaves, followed by drying at 60 °C for
approximately two weeks. Inclusion of basal/crown and undigitized material must
still be reconciled with any represented-root graph. The root, stem and shoot
means sum to 71.2 g, whereas reported total woody mass is 72.9 g; do not silently
correct either entry. [Main paper](https://doi.org/10.1093/aob/mcaf193),
[official supplementary package, Table S2](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12718041/supplementaryFiles).

Supplementary Table S4 gives root length 2032.0 ± 451.9 cm and specific root
length 96.1 ± 20.8 cm/g. Specific root length uses the same measured root mass
as its denominator, so it is not independent density evidence or a second
independent validation of biomass. A ratio of published means does not recover
a mean of individual ratios. Convex-hull volume is spatial extent, not tissue
volume. [Methods](https://pmc.ncbi.nlm.nih.gov/articles/PMC12718041/),
[Table S4](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12718041/supplementaryFiles).

Fichtl et al. (2024), Table 2, gives SO4/T2 mean diameters of 0.36 ± 0.06 cm
for type 1 and 0.20 ± 0.04 cm for type 2. Table 4 labels the identical type-2
number as a radius and lists type-3 radius 0.05 ± 0.02 cm. Table-2 surface/length
ratios imply effective diameters near 0.20 and 0.05 cm respectively; this is an
arithmetic consistency check, not an author-approved erratum. Caliper methods
exclude fine roots. Type-1/2/3 volumes sum to 45.4 cm³, compared with reported
total volume 130.6 cm³. Their lengths also do not sum to the reported total.
These are digitization-derived volume estimates, not independent displacement
measurements. Compartment coverage remains unresolved.
[2024 Methods, Tables 2 and 4](https://pmc.ncbi.nlm.nih.gov/articles/PMC11633832/).

The later CPlantBox `wine_Fichtl.xml`, pinned at
`ebe6b08c09eb6a4b38a568042c8193bfab8cd12a`, instead gives subtype radii near
0.15, 0.075 and 0.025 cm. Its provenance does not establish a correction to the
paper or the SO4/T2 population parameterization. Keep it a separate source.
[Pinned XML](https://github.com/Plant-Root-Soil-Interactions-Modelling/CPlantBox/blob/ebe6b08c09eb6a4b38a568042c8193bfab8cd12a/modelparameter/structural/rootsystem/wine_Fichtl.xml),
[nearby estimator](https://github.com/Plant-Root-Soil-Interactions-Modelling/CPlantBox/blob/ebe6b08c09eb6a4b38a568042c8193bfab8cd12a/experimental/wine_fichtl/estimate_wine.py).

Neither paper supplies an independently verified dry-root tissue density for
the cylinder operator. Published diameter means alone do not identify the
length-weighted second moment of diameter. Do not freely fit diameter and
density to one mass value, interpret diameter as radius, infer missing-root
mass, or use the reported 7 g SD as a standard error or acceptance tolerance.
An active constraint requires reconciled root support, independent diameter
and density provenance, uncertainty and its own explicit tolerance.

Public-evidence scientific review: GPT-6 Astra, high reasoning. Code validation
and empirical comparison remain separately recorded; this memo is not a
biological qualification.
