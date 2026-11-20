"""Invented geometric recovery through the real local parameter-search engine.

This is an analytic model/operator/optimizer integration fixture, not native
RootSystemSimulation recovery or evidence about measured field data. The three
invented axes are deterministic and intentionally independent of ensemble seed.
Only pytest's temporary directories receive synthetic search receipts/SQLite.
"""

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deeprootgen.research.core_observation import (
    predict_core_observations,
    qualify_root_segments,
)
from deeprootgen.research.parameter_search import run_parameter_search


FACTORS = np.array([1.0, 0.8, 0.5])
CENTRES_CM = (0.0, 4.0, -4.0)
TRUTH = dict(length_scale_cm=6.0, diameter_cm=0.14, dry_density_g_cm3=0.4)
SEEDS = (17, 29)
LENGTH_OPTIONS = [4.0, 6.0, 8.0]
DIAMETER_OPTIONS = [0.1, 0.14, 0.18]


def invented_prediction(parameters):
    """Three root-only plants, one incoming geometric cylinder per plant."""
    nodes, edges, cores = [], [], []
    for plant, (x, factor) in enumerate(zip(CENTRES_CM, FACTORS), start=1):
        base_id = 10 * plant
        for node_id, parent, order, depth, diameter, kind in (
            (base_id, -1, 0, 0.0, 999.0, "base"),
            (
                base_id + 1,
                base_id,
                1,
                -parameters["length_scale_cm"] * factor,
                parameters["diameter_cm"],
                "fine",
            ),
        ):
            nodes.append(
                dict(
                    node_id=node_id,
                    parent_id=parent,
                    plant_id=plant,
                    order=order,
                    x=x,
                    y=0.0,
                    z=depth,
                    diameter=diameter,
                    root_type=kind,
                    invalid_root=False,
                )
            )
        edges.append(dict(parent_id=base_id, child_id=base_id + 1))
        cores.append(
            dict(
                core_id=f"invented-core-{plant}",
                x_cm=x,
                y_cm=0.0,
                z_lower_cm=-10.0,
                z_upper_cm=0.0,
                radius_cm=1.0,
                sampled=True,
            )
        )
    support = qualify_root_segments(
        pd.DataFrame(nodes),
        pd.DataFrame(edges),
        coordinate_frame="invented-axes-cm-v1",
        fine_diameter_max_mm=2.0,
        dry_density_g_cm3=parameters["dry_density_g_cm3"],
    )
    return predict_core_observations(support, cores, by_plant=True)


def analytic_prediction(parameters):
    """Independent full-containment length and cylinder-mass truth in cm and g."""
    lengths = FACTORS * parameters["length_scale_cm"]
    mass = (
        lengths
        * np.pi
        * parameters["diameter_cm"] ** 2
        / 4
        * parameters["dry_density_g_cm3"]
    )
    return np.column_stack((lengths, mass))


def test_invented_core_search_recovers_unique_truth_and_exposes_density_diameter_alias(
    tmp_path,
):
    truth = analytic_prediction(TRUTH)
    seen_seed_tuples = []

    def evaluate(parameters, seeds):
        """The engine calls evaluate(full_candidate_dict, frozen_seed_tuple)."""
        assert seeds == SEEDS
        seen_seed_tuples.append(seeds)
        result = invented_prediction(parameters)
        predicted = result.cores[["fine_length_cm", "fine_dry_mass_g"]].to_numpy()
        # Both channels have dimensionless relative residuals, explicitly given
        # equal weight for this invented recovery experiment only.
        residuals = (predicted - truth) / truth
        return dict(
            loss=float(np.mean(residuals**2)),
            diagnostics=dict(
                fixture="invented-three-full-contained-axes-v1",
                seed_policy="deterministic_analytic_axes_independent_of_seed",
                seeds=list(seeds),
                predicted_fine_length_cm=predicted[:, 0].tolist(),
                predicted_fine_dry_mass_g=predicted[:, 1].tolist(),
                coordinate_frame=result.support.coordinate_frame,
                included_segment_count=result.diagnostics["included_segment_count"],
            ),
        )

    # Independent analytic identification: length fixes L; at fixed density,
    # the mass/length ratio fixes d**2. Every competing grid point is worse.
    grid = {}
    for length, diameter in itertools.product(LENGTH_OPTIONS, DIAMETER_OPTIONS):
        candidate = TRUTH | dict(length_scale_cm=length, diameter_cm=diameter)
        analytic = analytic_prediction(candidate)
        observed = (
            invented_prediction(candidate)
            .cores[["fine_length_cm", "fine_dry_mass_g"]]
            .to_numpy()
        )
        np.testing.assert_allclose(observed, analytic, rtol=1e-14, atol=1e-15)
        grid[(length, diameter)] = float(np.mean(((analytic - truth) / truth) ** 2))
    assert min(grid, key=grid.get) == (6.0, 0.14)
    assert grid[(6.0, 0.14)] == 0.0
    assert all(loss > 0 for pair, loss in grid.items() if pair != (6.0, 0.14))

    source_root = Path(__file__).parents[1]
    identity = dict(
        fixture="invented-three-full-contained-axes-v1",
        truth=TRUTH,
        factors=FACTORS.tolist(),
        centres_cm=list(CENTRES_CM),
        channels=["fine_length_cm", "fine_dry_mass_g"],
        loss="equal_weight_mean_squared_relative_residual",
        source_sha256={
            name: hashlib.sha256((source_root / name).read_bytes()).hexdigest()
            for name in (
                "deeprootgen/research/core_observation.py",
                "tests/test_core_parameter_search.py",
            )
        },
    )
    summaries, receipts = [], []
    for repetition in ("first", "repeat"):
        outdir = tmp_path / repetition
        summaries.append(
            run_parameter_search(
                base_parameters=dict(TRUTH),
                search_space=dict(
                    length_scale_cm=dict(kind="categorical", choices=LENGTH_OPTIONS),
                    diameter_cm=dict(kind="categorical", choices=DIAMETER_OPTIONS),
                ),
                seeds=list(SEEDS),
                outdir=outdir,
                n_trials=32,
                n_startup_trials=3,
                sampler_seed=2026,
                timeout_seconds=60.0,
                identity=identity,
                evaluate=evaluate,
            )
        )
        receipts.append(
            [
                json.loads(path.read_text())
                for path in sorted((outdir / "trials").glob("trial_*.json"))
            ]
        )
    for summary in summaries:
        assert summary["completed_trials"] == summary["attempted_trials"] == 32
        assert summary["failed_trials"] == 0
        assert summary["best_parameters"] == TRUTH
        assert summary["best_loss"] == pytest.approx(0.0, abs=1e-28)
        assert not summary["model_qualified"]
    assert len(seen_seed_tuples) == 64
    assert [r["sampler_phase"] for r in receipts[0]][:4] == ["startup"] * 3 + ["tpe"]
    assert receipts[0][0]["result"]["loss"] > summaries[0]["best_loss"]
    assert any(
        record["sampler_phase"] == "tpe" and record["result"]["loss"] == 0.0
        for record in receipts[0]
    )
    for first, repeated in zip(*receipts):
        assert first["parameters"] == repeated["parameters"]
        assert first["sampler_seed"] == repeated["sampler_seed"]
        assert first["result"] == repeated["result"]
        assert first["result"]["diagnostics"]["included_segment_count"] == 3

    # Freeing density destroys uniqueness: these distinct fine-root diameters
    # have equal rho*d**2, so both length and dry mass observations coincide.
    alias = TRUTH | dict(diameter_cm=0.1, dry_density_g_cm3=0.4 * (0.14 / 0.1) ** 2)
    assert alias["diameter_cm"] != TRUTH["diameter_cm"]
    assert alias["dry_density_g_cm3"] != TRUTH["dry_density_g_cm3"]
    alias_result, truth_result = invented_prediction(alias), invented_prediction(TRUTH)
    columns = ["fine_length_cm", "fine_dry_mass_g", "fine_rld_cm_cm3"]
    np.testing.assert_allclose(
        alias_result.cores[columns], truth_result.cores[columns], rtol=1e-14, atol=1e-15
    )
    assert alias_result.cores.fine_volume_cm3.sum() != pytest.approx(
        truth_result.cores.fine_volume_cm3.sum()
    )
