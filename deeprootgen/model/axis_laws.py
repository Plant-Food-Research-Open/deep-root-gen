"""Leaf direction laws used by the native engine.

A law receives one axis (its construction intervals and scaffold placement),
its resolved settings and a keyed random stream. It returns a realized curve.
It cannot instantiate a simulator, generate a forest, allocate graph nodes,
write files or call observation/search services.
"""

import numpy as np

from ..data_model.features import CURVATURE_LAW_VERSION, CURVATURE_STREAM_NAMESPACE
from .cohort_geometry import integrate_curve
from .materialize import AxisCurve


def scaffold_chord_heading(organ):
    """Initial heading from the placed native scaffold: base-to-apex chord."""
    base = organ.parent_node.node_data
    apex = organ.segments[-1].node_data
    return np.array([apex.x - base.x, apex.y - base.y, apex.z - base.z], dtype=float)


def realize_correlated_curvature(organ, law, streams, *, start=None, heading=None, length=None, arcs=None,
                                 rng=None, reserve_stations=None):
    """Correlated (OU) curvature over the organ's sampled contour length.

    Construction intervals keep their lengths and material; their boundaries
    are placed at the same arclength on the realized curve. Corners lie at
    physical stations of ``step_cm``. The first interval is integrated and an
    upward step at the declared surface is reflected downward. By default the
    curve starts at the organ's attachment point along the placed scaffold's
    base-to-apex chord; callers pass ``start``/``heading`` for other heading laws.
    """
    if law["first_interval"] != "integrate" or law["boundary"] != "reflect_downward":
        raise ValueError("Unsupported correlated-curvature first-interval or boundary convention")
    if arcs is None:
        lengths = np.array([node.node_data.length for node in organ.segments], dtype=float)
        if not np.isfinite(lengths).all() or np.any(lengths <= 0):
            raise ValueError("Correlated curvature requires positive finite construction intervals")
        arcs = np.cumsum(lengths)
    total = float(arcs[-1]) if length is None else length
    if start is None:
        base = organ.parent_node.node_data
        start = np.array([base.x, base.y, base.z], dtype=float)
    if heading is None:
        if law["initial_heading"] != "scaffold_chord":
            raise ValueError("A non-scaffold initial heading must be supplied by its heading law")
        heading = scaffold_chord_heading(organ)
    identity = int(organ.segments[0].node_data.organ_id)
    if rng is None:
        rng = streams.keyed(CURVATURE_STREAM_NAMESPACE, CURVATURE_LAW_VERSION, identity)
    if reserve_stations is not None:
        import math

        reserve_stations("stations", math.ceil(total / law["step_cm"]) + 1)
    alignment = law.get("row_alignment")
    carrier = law.get("deep_carrier")
    carrier_receipt = {}
    if carrier is not None:
        selected = streams.keyed("feature.curvature.deep_carrier", "1", identity).random() < carrier["fraction"]
        carrier = dict(carrier, selected=bool(selected))
    stations, points, reflections = integrate_curve(
        total,
        start,
        heading,
        law["step_cm"],
        law["curvature_sd_rad_cm"],
        law["correlation_length_cm"],
        law["downward_drift_per_cm"],
        rng,
        surface_z=law["surface_z_cm"],
        row_alignment_per_cm=alignment["row_alignment_per_cm"] if alignment else 0.0,
        deep_carrier=carrier, carrier_receipt=carrier_receipt,
    )
    unit_heading = np.asarray(heading, dtype=float)
    receipt = dict(
        organ_id=identity,
        order=int(organ.segments[0].node_data.order),
        law=law["law"],
        version=law.get("version", CURVATURE_LAW_VERSION),
        initial_heading=law["initial_heading"],
        contour_length_cm=float(total),
        construction_intervals=len(arcs),
        stations=len(stations),
        surface_reflections=int(reflections),
        initial_heading_unit=(unit_heading / np.linalg.norm(unit_heading)).tolist(),
    )
    if carrier is not None:
        receipt["deep_carrier"] = carrier_receipt
    if alignment is not None:
        widths = np.diff(stations)
        along_row = np.diff(points[:, 1]) / widths
        receipt["row_alignment"] = dict(
            alignment, step_cm=law["step_cm"],
            length_weighted_squared_row_component=float(np.dot(widths, along_row**2) / total),
        )
    return AxisCurve(identity, stations, points, np.asarray(arcs, dtype=float), dict(law), receipt)
