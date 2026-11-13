![DeepRootGen](docs/logos/deep_root_gen.png)

# DeepRootGen

[![Python](https://img.shields.io/badge/python-3.10-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/Plant-Food-Research-Open/deep-root-gen/HEAD?urlpath=lab/tree/notebooks/)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Coverage](https://plant-food-research-open.github.io/deep-root-gen/badges/coverage.svg)](https://github.com/Plant-Food-Research-Open/deep-root-gen/actions/workflows/test.yaml)
[![Lint](https://github.com/Plant-Food-Research-Open/deep-root-gen/actions/workflows/lint.yaml/badge.svg?branch=main)](https://github.com/Plant-Food-Research-Open/deep-root-gen/actions/workflows/lint.yaml)
[![Tests](https://github.com/Plant-Food-Research-Open/deep-root-gen/actions/workflows/tests.yaml/badge.svg?branch=main)](https://github.com/Plant-Food-Research-Open/deep-root-gen/actions/workflows/tests.yaml)
[![Documentation](https://github.com/Plant-Food-Research-Open/deep-root-gen/actions/workflows/docs.yaml/badge.svg?branch=main)](https://github.com/Plant-Food-Research-Open/deep-root-gen/actions/workflows/docs.yaml)
[![Build](https://github.com/Plant-Food-Research-Open/deep-root-gen/actions/workflows/docker-build.yaml/badge.svg?branch=main)](https://github.com/Plant-Food-Research-Open/deep-root-gen/actions/workflows/docker-build.yaml)

Website: [DeepRootGen](https://Plant-Food-Research-Open.github.io/deep-root-gen/)

*A stochastic simulation framework for generating, analysing and digitally reconstructing three-dimensional root system architectures, with support for model calibration and simulation-based inference.*

# Table of contents

- [DeepRootGen](#deeprootgen)
- [Table of contents](#table-of-contents)
- [Introduction](#introduction)
- [Features and Functionality](#features-and-functionality)
- [Model Overview](#model-overview)
  - [Root architecture generation](#root-architecture-generation)
  - [Hierarchical root representation](#hierarchical-root-representation)
- [Quickstart](#quickstart)
- [Installation](#installation)
  - [Requirements](#requirements)
  - [Installation with Poetry](#installation-with-poetry)
- [Usage with Binder](#usage-with-binder)
- [Root System Architecture Analysis](#root-system-architecture-analysis)
  - [Root morphology](#root-morphology)
  - [Root branching and orientation](#root-branching-and-orientation)
  - [Spatial root distributions](#spatial-root-distributions)
  - [Root length density](#root-length-density)
- [Model Calibration and Sensitivity Analysis](#model-calibration-and-sensitivity-analysis)
  - [Model calibration](#model-calibration)
  - [Sensitivity analysis](#sensitivity-analysis)
- [Data Schema](#data-schema)
  - [Node table](#node-table)
  - [Edge table](#edge-table)
- [Development](#development)
  - [Project resources](#project-resources)
  - [Running tests](#running-tests)
  - [Enabling pre-commit](#enabling-pre-commit)
- [Documentation](#documentation)
- [Communication](#communication)
- [Contributions and Support](#contributions-and-support)
- [License](#license)
- [Contacts](#contacts)
- [Funding and Acknowledgements](#funding-and-acknowledgements)

# Introduction

Root system architecture (RSA) plays an important role in plant growth and development, influencing soil exploration, water and nutrient uptake, and interactions with the surrounding environment. However, characterising root systems under field conditions remains challenging due to their spatial complexity, below-ground location, and the cost and destructive nature of many root measurement techniques.

DeepRootGen provides a computational framework for generating synthetic three-dimensional root system architectures using a stochastic, parameterised root simulation model. The model represents individual root organs and segments within a hierarchical graph, allowing their geometry, topology and spatial distribution to be analysed.

The framework is intended to support the digital reconstruction of root systems using observational data collected from the field. By combining mechanistic assumptions about root development with statistical calibration and inference methods, DeepRootGen provides a means of investigating plausible root architectures consistent with available measurements.

DeepRootGen has been developed with an emphasis on woody perennial root systems, including horticultural applications involving apple and grapevine rootstocks. The underlying simulator is parameterised to support different root system configurations and can be recalibrated for specific applications.

# Features and Functionality

DeepRootGen provides the following functionality:

- **Stochastic 3D root simulation:** Generate synthetic root system architectures with configurable root numbers, lengths, diameters, branching behaviour and growth orientations.
- **Hierarchical graph representation:** Represent root organs and segments using explicit parent–child relationships, branching orders and segment identifiers.
- **Root branching and development:** Simulate primary and higher-order roots, including stochastic branching locations and configurable interbranch distances.
- **Architectural analysis:** Calculate summary statistics describing root length, diameter, branching patterns, orientation, spatial extent and root length density.
- **Spatial aggregation:** Aggregate simulated root segments onto three-dimensional soil voxel grids for comparison against field observations.
- **Model calibration:** Estimate root system parameters using optimisation and statistical discrepancy measures.
- **Sensitivity analysis:** Investigate the influence of model parameters on simulated architectural characteristics.
- **Stochastic ensemble simulation:** Generate multiple plausible root architectures under a common parameter configuration to investigate variability between realisations.
- **Visualisation:** Explore root architectures and summary statistics through interactive three-dimensional visualisations and statistical plots.
- **Experiment management:** Support reproducible simulation workflows, experiment tracking and model artefact management.

The repository also contains infrastructure for simulation-based inference and generative modelling. The availability and configuration of individual inference workflows depend on the installed dependencies and repository revision.

# Model Overview

DeepRootGen uses a stochastic root growth simulator to construct root system architectures from a configurable set of parameters.

## Root architecture generation

A simulated root system consists of primary roots originating from the plant base, with lateral roots emerging from their parent organs according to the specified branching configuration.

The model supports several aspects of root development:

- Number and arrangement of primary roots.
- Root organ lengths and diameters.
- Maximum branching order.
- Number and length of lateral roots.
- Stochastic variation in root growth.
- Interbranch distances and lateral-root attachment locations.
- Root growth orientation and gravitropism.
- Classification of structural and fine roots.

Individual simulation runs may produce different architectures even when the input parameters are identical. Random seeds can be specified to reproduce individual stochastic realisations.

## Hierarchical root representation

Each root system is represented as a graph containing root nodes and their relationships.

Root organs are associated with unique identifiers, while individual segments retain their position within each organ. The hierarchy distinguishes primary roots from higher-order lateral roots and preserves the attachment relationships between parent and daughter organs.

This representation enables analysis of both root geometry and topology, including branching orders, root lengths, branching frequencies and spatial orientations.

# Quickstart

The following example generates a synthetic root system architecture and exports its node and edge tables.

```python
from deeprootgen.data_model import RootSimulationModel
from deeprootgen.model import RootSystemSimulation

# Specify simulation parameters
parameters = RootSimulationModel(
    random_seed=42,
    max_order=3,
    root_ratio=0.5,
    fine_root_threshold=0.15,
    outer_root_num=4,
    inner_root_num=2,
    min_primary_length=15.0,
    max_primary_length=40.0,
    base_diameter=0.5,
    diameter_reduction=0.2,
    apex_diameter=0.05,
    min_sec_root_num=1,
    max_sec_root_num=3,
    growth_sec_root=0.1,
    min_sec_root_length=3.0,
    max_sec_root_length=15.0,
    segments_per_root=6,
    length_reduction=0.7,
    root_vary=10.0,
    interbranch_distance=2.0,
    mechanical_constraints=0.0,
    root_tissue_density=0.15,
    gravitropism=0.1,
    t=1,
    enable_soil=False,
    soil_layer_height=10.0,
    soil_n_layers=10,
    soil_layer_width=10.0,
    soil_n_cols=10,
)

# Initialise and run the simulation
simulation = RootSystemSimulation(random_seed=42)
simulation.run(parameters)

# Extract the hierarchical root graph
node_df, edge_df = simulation.G.as_df()

# Export simulated architecture
node_df.to_csv("root_nodes.csv", index=False)
edge_df.to_csv("root_edges.csv", index=False)

print(f"Generated {len(node_df)} nodes")
print(f"Generated {len(edge_df)} edges")
```

The generated data can be used for architectural analysis, visualisation, and integration with downstream modelling workflows.

# Installation

## Requirements

DeepRootGen currently targets Python `>=3.10,<3.11` and uses Poetry for dependency management.

The repository contains a `poetry.lock` file for managing reproducible development environments.

## Installation with Poetry

Clone the repository:

```bash
git clone https://github.com/Plant-Food-Research-Open/deep-root-gen.git
cd deep-root-gen
```

Install Poetry if it is not already available:

```bash
pip install poetry
```

Install the project and its dependencies:

```bash
poetry install
```

Activate the Poetry environment:

```bash
poetry shell
```

Alternatively, execute commands directly in the project environment:

```bash
poetry run python
```

For development, refer to the [development and setup guide](docs/DEVELOPMENT.md) for environment configuration and additional tooling.

# Usage with Binder

You may wish to work with DeepRootGen using MyBinder. [You can do so by accessing the following link.](https://mybinder.org/v2/gh/Plant-Food-Research-Open/deep-root-gen/HEAD?urlpath=lab/tree/notebooks/)

# Root System Architecture Analysis

DeepRootGen provides summary statistics for characterising simulated root systems and comparing them with observational measurements.

## Root morphology

Root morphology can be described using statistics such as:

- Total root length and root number.
- Root length distributions.
- Root diameter distributions.
- Total and average root volume.
- Root dry mass and root tissue density.
- Specific root length.
- Root dry mass by diameter class.

Statistics may be calculated for individual root organs, branching orders or the complete root system, depending on the selected method.

## Root branching and orientation

The hierarchical root graph provides information for analysing root topology and spatial growth patterns.

Relevant characteristics include:

- Root number and length by branching order.
- Branching frequency and interbranch distance.
- Parent–daughter branching angles.
- Root elongation directions.
- Segment inclination and azimuth.
- Root-level growth orientation.

These metrics can be used to investigate how model parameters influence the geometry and structural organisation of simulated root systems.

## Spatial root distributions

DeepRootGen supports spatial analysis of root systems, including:

- Maximum rooting depth.
- Horizontal root spread and radial extent.
- Root length distributions by soil depth.
- Horizontal and radial root length distributions.
- Convex hull area and volume.
- Three-dimensional root length density.

Spatial distributions are particularly useful when comparing simulated architectures with soil-core, trench, excavation or voxel-based observations.

## Root length density

Root length density (RLD) describes the amount of root length contained within a specified soil volume:

\[
\mathrm{RLD} = \frac{\mathrm{Root\ length\ (cm)}}{\mathrm{Soil\ volume\ (cm^3)}}
\]

The `RootLengthDensity` statistic calculates simulated RLD using a three-dimensional voxel grid.

Root segments are intersected with voxel boundaries so that their lengths can be allocated to the corresponding soil volumes. Both recorded and geometrically derived segment lengths are supported.

The resulting voxel-level data can be aggregated by soil layer, row or column, enabling comparison with observed RLD distributions.

When comparing simulated and observed data, the coordinate system, voxel boundaries, root validity filters and length calculation method should be consistent.

# Model Calibration and Sensitivity Analysis

DeepRootGen includes workflows for estimating simulation parameters and evaluating model behaviour.

## Model calibration

Model calibration aims to identify parameter configurations that produce simulated root characteristics consistent with observational measurements.

The repository includes an optimisation workflow using [Optuna](https://optuna.org/), with support for specifying parameter bounds and minimising statistical discrepancies between simulated and observed summary statistics.

Calibration targets may include root length, diameter, root depth, branching characteristics or spatial root length density.

Because the simulator is stochastic, repeated simulations can be used to estimate the expected discrepancy for a candidate parameter configuration.

Independent observational units and held-out datasets can be used to evaluate predictive performance outside the calibration sample.

## Sensitivity analysis

Sensitivity analysis can be used to investigate how uncertainty or variation in simulation parameters affects root architecture characteristics.

The repository includes a sensitivity analysis workflow based on [SALib](https://salib.readthedocs.io/), supporting Sobol sensitivity indices.

First-order and total-order Sobol indices provide information about the influence of individual parameters and their interactions on a selected model output.

Sensitivity analysis may be applied to statistics such as:

- Total root length and root number.
- Maximum rooting depth.
- Root branching frequency.
- Mean or total root diameter.
- Spatially aggregated root length density.
- Replicate-to-replicate variability in root system characteristics.

For stochastic analyses, repeated simulations are needed to distinguish parameter-driven changes in model output from variation associated with random simulation realisations.

# Data Schema

The `RootSystemGraph.as_df()` export contains two tabular datasets: a node table and an edge table.

The node schema is defined by `RootNodeModel` in `deeprootgen/data_model/simulation_data_models.py`.

## Node table

| Node column           | Description                                                   |
| --------------------- | ------------------------------------------------------------- |
| `node_id`             | Unique identifier for a graph node.                           |
| `parent_id`           | Parent node identifier; the base node uses the sentinel `-1`. |
| `plant_id`            | Identifier for the simulated plant.                           |
| `organ_id`            | Identifier for the root organ.                                |
| `order`               | Root branching order; the base node has order zero.           |
| `segment_rank`        | Position of the segment within its root organ.                |
| `x`, `y`, `z`         | Three-dimensional root coordinates.                           |
| `diameter`            | Stored root segment diameter.                                 |
| `length`              | Stored root segment length.                                   |
| `root_tissue_density` | Root tissue density.                                          |
| `root_type`           | Root classification, such as `structural`, `fine` or `base`.  |
| `order_type`          | Additional root-order classification.                         |
| `position_type`       | Additional positional classification.                         |
| `simulation_tag`      | Simulation grouping identifier.                               |
| `invalid_root`        | Flag identifying root segments marked as invalid.             |

The spatial coordinates and dimensions are expressed in centimetres. Root tissue density is expressed in g/cm³, and root mass in grams.

## Edge table

The edge table describes the relationships between connected root nodes.

| Edge column | Description                    |
| ----------- | ------------------------------ |
| `parent_id` | Identifier of the parent node. |
| `child_id`  | Identifier of the child node.  |

Together, these tables preserve the hierarchical connectivity of the simulated root architecture.

Root node coordinates should be interpreted in conjunction with the edge table when calculating geometric segment lengths and spatial relationships.

# Development

DeepRootGen is developed as a Python research software project.

The repository uses Poetry for dependency management and includes configuration for formatting, testing, documentation and automated workflows.

## Project resources

The following documents provide additional development information:

- [Development and setup guide](docs/DEVELOPMENT.md)
- [Architecture and code map](docs/ARCHITECTURE.md)
- [Review notes](docs/REVIEW_NOTES.md)
- [Agent instructions](AGENTS.md)

## Running tests

Execute the project's test suite using:

```bash
poetry run pytest
```

Test coverage may vary between components. A successful test run does not by itself establish the scientific validity of simulated root architectures or calibrated parameter estimates.

Simulation changes should also be evaluated using representative root system configurations and checks on graph integrity, geometry, branching relationships and summary statistics.

## Enabling pre-commit

Install the configured pre-commit hooks:

```bash
poetry run pre-commit install
```

Run the hooks against the repository:

```bash
poetry run pre-commit run --all-files
```

The hooks support consistent formatting and code quality during development.

# Documentation

The project documentation is available at:

[DeepRootGen Documentation](https://Plant-Food-Research-Open.github.io/deep-root-gen/)

Documentation is maintained using [Sphinx](https://www.sphinx-doc.org/) and the Read the Docs theme.

To build the documentation locally, navigate to the `docs` directory and run:

```bash
cd docs
make html
```

The generated HTML documentation can then be viewed from `docs/build/html/index.html`.

# Communication

Please refer to the following links for project communication:

- [GitHub Issues](https://github.com/Plant-Food-Research-Open/deep-root-gen/issues) for bug reports and feature requests.
- [GitHub Pull Requests](https://github.com/Plant-Food-Research-Open/deep-root-gen/pulls) for proposed changes and code reviews.

When reporting a problem with a simulation, please include the relevant model parameters, random seed, software environment and steps needed to reproduce the issue.

# Contributions and Support

Contributions to DeepRootGen are welcome, particularly those that improve the simulator, architectural statistics, calibration workflows, documentation and automated testing.

For general guidelines on contributing to the project, please refer to [CONTRIBUTING.md](CONTRIBUTING.md).

Please also review the community [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

# License

DeepRootGen is distributed under the GNU General Public License v3.0 (GPL-3.0). See [LICENSE](LICENSE) for the full licence terms.

# Contacts

- DeepRootGen Developer: James Bristow
- DeepRootGen Project Supervisor: Junqi Zhu

# Funding and Acknowledgements

This work was funded by the New Zealand Ministry of Business, Innovation, and Employment (MBIE) through the Strategic Science Investment Fund (contract number C11X1702) as part of the Digital Horticultural Systems Ngā Pou Rangahau, a Growing Futures™ programme at Plant & Food Research. We sincerely thank the Fruit Physiology Group, orchard managers, and all those who contributed their time and effort to the management and operation of the orchards. Your dedication has been instrumental in the success of this project. Our gratitude extends to the wider Digital Horticultural Systems team for their invaluable support in the modelling and software development process. Our work would not have been possible without the considerable dedication and collaboration of all parties involved.