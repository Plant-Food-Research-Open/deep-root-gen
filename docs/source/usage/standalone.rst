Run the model independently
===========================

Use the offline Python runner to produce one architecture, explore model
parameters, and analyse simulation output in a notebook. For a CLI walkthrough
and the Simulation page, see :doc:`native_workflow`.

Install the Python package
--------------------------

From the repository root, install the locked dependencies with Poetry using
Python 3.10. Use the same environment as the kernel for notebooks.

.. code-block:: console

   poetry install --with dev,torch --no-interaction
   poetry run python

Generate a root system
----------------------

The invented crown example uses schema 4 and a fixed seed. Paste this cell into
a notebook opened from the repository root.

.. code-block:: python

   from pathlib import Path

   from deeprootgen.data_model import RootConfig
   from deeprootgen.model import RootSystemSimulation

   path = Path("examples/design/native_crown_0_20cm.json")
   config = RootConfig.model_validate_json(path.read_text())
   simulation = RootSystemSimulation(random_seed=config.random_seed)
   simulation.run(config)

   node_df, edge_df = simulation.G.as_df()
   summary = simulation.result.metadata["root_summary"]
   print(summary["by_order"])
   print(summary["diameter_classes"])

The node table contains centimetre coordinates and dimensions, numeric orders
and parent IDs. The edge table contains the parent-child links. Use
``deeprootgen.run_records.tracked_run`` or the CLI to export the graph and an
interactive ``roots.html`` together with the settings, seed and run record.

Optional soil voxel summaries
-----------------------------

Continue in the same notebook to summarize root material over a regular grid.
The dimensions below define the observation support. The soil grid and the
root graph use ``z`` for vertical coordinates, with negative values below
the soil surface in this example.

.. code-block:: python

   import numpy as np

   from deeprootgen.statistics.root_grid_aggregation import aggregate_root_grid

   soil_df = simulation.soil.create_soil_grid(
       soil_layer_height=25, soil_n_layers=8,
       soil_layer_width=25, soil_n_cols=4,
   )

   np.testing.assert_allclose(
       [soil_df["z"].min(), soil_df["z"].max()], [-200.0, 0.0]
   )
   grid_df, totals_df = aggregate_root_grid(
       node_df=node_df, soil_df=soil_df, length_source="recorded"
   )
   print(f"Soil voxels: {len(grid_df)}")
   print(totals_df)

Use the recorded axis convention and physical support of your observations
when setting the grid. For measured finite cores, use an observation operator
with matching cylinder positions, depths and diameter support.

Check segment geometry before spatial calibration
-------------------------------------------------

Before using the recorded segment lengths for spatial analysis, compare the
stored lengths with the distances between endpoints.

.. code-block:: python

   import numpy as np

   parents = node_df.set_index("node_id")
   segments = node_df.loc[
       (node_df["order"] > 0)
       & (~node_df["invalid_root"].fillna(False).astype(bool))
       & node_df["parent_id"].isin(parents.index)
   ]
   parent_xyz = parents.loc[segments["parent_id"], ["x", "y", "z"]].to_numpy()
   child_xyz = segments[["x", "y", "z"]].to_numpy()
   geometric = np.linalg.norm(child_xyz - parent_xyz, axis=1)
   recorded = segments["length"].to_numpy()
   np.testing.assert_allclose(recorded, geometric, rtol=1e-6, atol=1e-8)

Keep the model configuration, seed, source identity and outputs together.
