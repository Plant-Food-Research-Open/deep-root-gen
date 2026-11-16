"""Opt-in explicit primary construction; all supplied dimensions are in cm.

Labels are metadata, not measured directions. Entries follow native outer then
inner allocation order. A diameter belongs to the incoming cylindrical segment:
the first/last original construction segments receive base/apex diameter, with
linear interpolation by segment rank between them. Branch cuts inherit their
original cylinder's diameter. A single segment requires equal base/apex values.
Length is fixed before attachment selection; no daughter is rescaled.

API example, starting with a synthetic Fichtl parameter dictionary ``spec``::

    spec.update(outer_root_num=1, inner_root_num=0, soil_surface_z_cm=0.,
                research_base_origin_x_cm=0., research_base_origin_y_cm=0.,
                research_base_depth_cm=10., research_primary_design=[dict(
                    primary_id="invented-A", category="unknown",
                    length_cm=8., diameter_base_cm=.4, diameter_apex_cm=.1,
                    inclination_deg=45., azimuth_deg=30.)])
    params = RootSimulationModel(**spec)
    sim = RootSystemSimulation(random_seed=params.random_seed)
    sim.run(params)

Numeric angles above are explicit assumptions, including an unknown category;
the example is not a biological reconstruction or a fitted parameterization.
"""

import math

import numpy as np

from .primary_orientation import proper_rotation

FIELD = "research_primary_design"
VERSION = "drg-explicit-primary-design-v1"


def entry_values(entry):
    return entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)


def validate_primary_design_scope(parameters, constructor_seed=None):
    """Validate this static, seed-bound Fichtl research path, including mutations."""
    entries = getattr(parameters, FIELD, None)
    if entries is None:
        return None
    from ..data_model.simulation_data_models import ResearchPrimaryDesignEntry

    if not isinstance(entries, list) or not entries:
        raise ValueError("Explicit primary design requires a nonempty list")
    values = [
        ResearchPrimaryDesignEntry(**entry_values(entry)).model_dump()
        for entry in entries
    ]
    identifiers = [entry["primary_id"] for entry in values]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Explicit primary design primary_id values must be unique")
    counts = (parameters.outer_root_num, parameters.inner_root_num)
    if any(
        isinstance(n, (bool, np.bool_)) or not isinstance(n, (int, np.integer)) or n < 0
        for n in counts
    ):
        raise ValueError(
            "Explicit primary design needs nonnegative integer native root counts"
        )
    if len(values) != sum(counts):
        raise ValueError(
            "Explicit primary design count must equal outer_root_num + inner_root_num"
        )
    if (
        parameters.tropism_mode != "fichtl2024"
        or not 1 <= parameters.max_order <= 5
        or parameters.t != 0
    ):
        raise ValueError(
            "Explicit primary design requires static Fichtl max_order 1..5"
        )
    if parameters.max_order > 3:
        # Preserve the existing explicit higher-order assumption/provenance gate.
        from .order_controls import validate_order_scope

        validate_order_scope(parameters, constructor_seed)
    if parameters.soil_surface_z_cm != 0.0:
        raise ValueError(
            "Explicit primary design requires physical soil_surface_z_cm=0"
        )
    seed = parameters.random_seed
    if (
        isinstance(seed, (bool, np.bool_))
        or not isinstance(seed, (int, np.integer))
        or seed < 0
    ):
        raise ValueError(
            "Explicit primary design requires an explicit nonnegative integer seed"
        )
    if constructor_seed is not None:
        if (
            isinstance(constructor_seed, (bool, np.bool_))
            or not isinstance(constructor_seed, (int, np.integer))
            or constructor_seed != seed
        ):
            raise ValueError(
                "Explicit primary design requires matching constructor and parameter seeds"
            )
    for key in (
        "research_primary_yaw_mean_deg",
        "research_primary_yaw_kappa",
        "research_primary_yaw_reverse_probability",
        "research_primary_inclination_bias",
    ):
        if getattr(parameters, key, None) is not None:
            raise ValueError(
                "Explicit primary design cannot be combined with shared yaw/inclination controls"
            )
    n = parameters.segments_per_root
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError(
            "Explicit primary design requires positive integer segments_per_root"
        )
    if n == 1 and any(
        entry["diameter_base_cm"] != entry["diameter_apex_cm"] for entry in values
    ):
        raise ValueError("A single primary segment requires constant diameter")
    return values


def primary_dimensions(entry, sampled_lengths):
    """Bind total length and segment taper before branch-site construction."""
    entry = entry_values(entry)
    lengths = np.asarray(sampled_lengths, dtype=float)
    if (
        lengths.ndim != 1
        or not len(lengths)
        or not np.isfinite(lengths).all()
        or np.any(lengths <= 0)
    ):
        raise ValueError(
            "Explicit primary construction needs finite positive segment weights"
        )
    lengths = lengths / lengths.sum() * entry["length_cm"]
    # Bind the last segment to the requested floating point total.
    lengths[-1] = entry["length_cm"] - float(lengths[:-1].sum())
    diameters = np.linspace(
        entry["diameter_base_cm"], entry["diameter_apex_cm"], len(lengths)
    )
    return diameters, lengths


def target_direction(entry):
    """Inclination is degrees below horizontal, azimuth rotates +x toward +y."""
    entry = entry_values(entry)
    alpha, phi = math.radians(entry["inclination_deg"]), math.radians(
        entry["azimuth_deg"]
    )
    return np.array(
        [
            math.cos(alpha) * math.cos(phi),
            math.cos(alpha) * math.sin(phi),
            -math.sin(alpha),
        ]
    )


def design_rotation(chord, entry):
    target = target_direction(entry)
    rotation = proper_rotation(chord, target)
    return rotation, target
