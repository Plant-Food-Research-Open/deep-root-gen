![DeepRootGen](docs/logos/deep_root_gen.png)

# DeepRootGen

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Tests](https://github.com/JBris/deep-root-gen/actions/workflows/tests.yaml/badge.svg?branch=main)](https://github.com/JBris/deep-root-gen/actions/workflows/tests.yaml)
[![Documentation](https://github.com/JBris/deep-root-gen/actions/workflows/docs.yaml/badge.svg?branch=main)](https://github.com/JBris/deep-root-gen/actions/workflows/docs.yaml)
[![Build](https://github.com/JBris/deep-root-gen/actions/workflows/docker-build.yaml/badge.svg?branch=main)](https://github.com/JBris/deep-root-gen/actions/workflows/docker-build.yaml)

Website: [DeepRootGen](https://jbris.github.io/deep-root-gen/)

*A simulation model for the digital reconstruction of 3D root system architectures. Integrated with a simulation-based inference generative deep learning model.*

# Table of contents

- [DeepRootGen](#deeprootgen)
- [Table of contents](#table-of-contents)
- [Introduction](#introduction)
- [Development](#development)
- [Data Schema](#data-schema)
- [Contacts](#contacts)
  
# Introduction

This repository contains an implementation of a simulation model for generating a synthetic root system architecture, for the estimation of root parameters as informed by observational data collected from the field.

# Development

Use this repository as an independent Codex project. Start with the
[development and setup guide](docs/DEVELOPMENT.md),
[architecture/code map](docs/ARCHITECTURE.md),
[review notes](docs/REVIEW_NOTES.md), and [agent instructions](AGENTS.md).

The project requires Python `>=3.10,<3.11` and the Poetry lockfile. Full runtime
tests were unavailable in the 2026-10-28 documentation review. The existing
pytest test is a dummy; its pass does not validate model or inference behaviour.
The guide separates executed metadata/syntax checks from unexecuted setup recipes.

# Data Schema

The current `RootSystemGraph.as_df()` export is a pair of node and edge tables.
`pipeline/experiment.py` saves these as separate CSV artifacts. The node schema
is defined by `RootNodeModel` in `deeprootgen/data_model/simulation_data_models.py`.

| Node column | Meaning |
|---|---|
| `node_id` | Unique graph node ID. |
| `parent_id` | Parent node ID; the base node defaults to sentinel `-1`. |
| `plant_id` | Plant identifier. |
| `organ_id` | Root organ identifier. |
| `order` | Root order, with base node order zero. |
| `segment_rank` | Segment rank within the organ. |
| `x`, `y`, `z` | Separate spatial coordinates. |
| `diameter`, `length` | Stored segment dimensions. |
| `root_tissue_density` | Root tissue density. |
| `root_type` | String classification such as `structural`, `fine`, or `base`. |
| `order_type`, `position_type` | Additional string classifications. |
| `simulation_tag` | Simulation grouping tag. |
| `invalid_root` | Invalid-root flag retained in the exported table. |

The edge table contains `parent_id` and `child_id`. Forms and statistic labels
use centimetres for geometry, g/cm³ for tissue density and grams for weight;
the tables do not carry a separate units column. Verify units and invalid-root
policy before comparing with observations.

Older descriptions used `id`, `parent`, combined `coordinates`, numeric root
types and a GroIMP/XEG import convention. Those are not the current exported
field names/types. Inspect a downstream consumer before claiming compatibility
or translating identifiers. This documentation correction does not change
serialization or scientific code.

# Contacts

- DeepRootGen Developer: James Bristow 
- DeepRootGen Project Supervisor: Junqi Zhu
- Crop System Modeller: Xiumei Yang
