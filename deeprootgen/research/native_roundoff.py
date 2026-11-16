"""Opt-in reconciliation of native stored length metadata to exported geometry.

Coordinates/lengths/diameters are cm; density is g/cm3. This adapter treats finite
exported binary64 coordinates as authoritative, without moving or snapping them.
It changes only stored lengths that fail the unchanged rtol1e-9/atol0 check AND
satisfy both declared roundoff-scale agreement bounds. The bounds do not prove
roundoff caused a discrepancy. This is not geometry repair or biological/model
qualification; all metadata moment deltas remain explicit.
"""

import math
from numbers import Real

import numpy as np
import pandas as pd

from .primary_curvature import _audit

VERSION = "native-length-metadata-roundoff-v1"
EPS = np.finfo(np.float64).eps
RELATIVE_CAP = float(np.sqrt(EPS))
XYZ = ["x", "y", "z"]


def _finite_real_columns(table, columns):
    for name in columns:
        for value in table[name]:
            if (
                isinstance(value, (bool, np.bool_))
                or not isinstance(value, Real)
                or not np.isfinite(value)
            ):
                raise ValueError(f"{name} must contain finite nonbool real values")


def _integer_column(values, name, minimum=0):
    if any(
        isinstance(value, (bool, np.bool_))
        or not isinstance(value, (int, np.integer))
        or value < minimum
        for value in values
    ):
        raise ValueError(f"{name} must contain integers >= {minimum}")


def _preflight(nodes, edges):
    required = {
        "node_id",
        "parent_id",
        "organ_id",
        "order",
        "segment_rank",
        "length",
        "diameter",
        "root_tissue_density",
        *XYZ,
    }
    if (
        not isinstance(nodes, pd.DataFrame)
        or not isinstance(edges, pd.DataFrame)
        or nodes.columns.duplicated().any()
        or edges.columns.duplicated().any()
        or not required.issubset(nodes)
        or not {"parent_id", "child_id"}.issubset(edges)
    ):
        raise ValueError(
            "Expected native node/edge tables with unique required columns"
        )
    if nodes.empty or not nodes.node_id.is_unique:
        raise ValueError("Native nodes must be nonempty with unique node IDs")
    for name in ("node_id", "organ_id", "order", "segment_rank"):
        _integer_column(nodes[name], name)
    _integer_column(nodes.parent_id, "parent_id", -1)
    _integer_column(edges.parent_id, "edge parent_id")
    _integer_column(edges.child_id, "edge child_id")
    _finite_real_columns(nodes, [*XYZ, "length", "diameter", "root_tissue_density"])
    if (nodes[["length", "diameter", "root_tissue_density"]].to_numpy(float) < 0).any():
        raise ValueError("Native length/material metadata must be nonnegative")
    bases = nodes.loc[nodes.order.eq(0)]
    if len(bases) != 1 or int(bases.parent_id.iloc[0]) != -1:
        raise ValueError("Require exactly one order-0 base with parent_id=-1")
    roots = nodes.loc[nodes.order.gt(0)]
    if roots.organ_id.isin(bases.organ_id).any():
        raise ValueError("Native base organ IDs cannot be reused by root organs")
    expected = set(zip(roots.parent_id, roots.node_id))
    actual = list(zip(edges.parent_id, edges.child_id))
    if (
        len(actual) != len(expected)
        or set(actual) != expected
        or not set(roots.parent_id).issubset(set(nodes.node_id))
    ):
        raise ValueError("Exported edges must uniquely match node parent references")
    if "plant_id" in nodes:
        _integer_column(nodes.plant_id, "plant_id")
        plants = nodes.set_index("node_id").plant_id
        if not np.array_equal(
            roots.plant_id.to_numpy(), plants.loc[roots.parent_id].to_numpy()
        ):
            raise ValueError("Native edges cannot cross plant IDs")
    return roots


def _moment_arrays(length, diameter, density):
    with np.errstate(over="ignore", invalid="ignore"):
        d2l = diameter**2 * length
        rho_d2l = density * d2l
        result = dict(
            length_cm=length,
            diameter2_length_cm3=d2l,
            density_diameter2_length_g=rho_d2l,
            cylinder_volume_cm3=np.pi / 4 * d2l,
            dry_mass_g=np.pi / 4 * rho_d2l,
        )
    if not all(np.isfinite(value).all() for value in result.values()):
        raise ValueError("Nonfinite stored cylinder-moment arithmetic")
    return result


def _finite_sum(values):
    try:
        value = math.fsum(values)
    except OverflowError as error:
        raise ValueError("Nonfinite aggregate cylinder-moment arithmetic") from error
    if not math.isfinite(value):
        raise ValueError("Nonfinite aggregate cylinder-moment arithmetic")
    return value


def _moment_report(before, after, positions):
    result = {}
    for name in before:
        old, new = before[name][positions], after[name][positions]
        total_before, total_after = _finite_sum(old), _finite_sum(new)
        # Sum edge deltas separately: cancellation in large totals must not hide
        # a tiny metadata change in the audit trail.
        delta = _finite_sum(new - old)
        relative = delta / total_before if total_before else None
        if relative is not None and not np.isfinite(relative):
            raise ValueError("Nonfinite relative cylinder-moment delta")
        result[name] = dict(
            before=total_before,
            after=total_after,
            delta=delta,
            relative_delta=relative,
            after_minus_before=total_after - total_before,
        )
    return result


def reconcile_native_edge_lengths(nodes, edges):
    """Return copied ``(nodes, edges, diagnostics)`` with bounded metadata edits.

    Only failing ``np.isclose(actual,stored,rtol=1e-9,atol=0)`` edges may change.
    Require abs(error) <=64*eps*(norm(parent)+norm(child)+stored), and relative
    error abs(error)/min(actual,stored) <=sqrt(eps). Both lengths must be finite
    and positive. No clamping, geometry edits, dropped rows or input mutation.
    Binary64 length metadata is required when a correction is needed, avoiding
    silent dtype promotion or rounding of the corrected geometric norm.

    The existing strict graph/length validator runs after reconciliation. Every
    other value, table order, index, dtype and attribute remains unchanged. The
    adapter does not infer why the original metadata and coordinates disagreed.
    """
    roots = _preflight(nodes, edges)
    lookup = nodes.set_index("node_id")
    parent = lookup.loc[roots.parent_id, XYZ].to_numpy(float)
    child = roots[XYZ].to_numpy(float)
    stored = roots.length.to_numpy(float)
    with np.errstate(over="ignore", invalid="ignore", under="ignore"):
        actual = np.linalg.norm(child - parent, axis=1)
    if not np.isfinite(actual).all() or (actual <= 0).any() or (stored <= 0).any():
        raise ValueError(
            "Native actual and stored edge lengths must be finite and positive"
        )
    passing = np.isclose(actual, stored, rtol=1e-9, atol=0.0)
    changed = np.flatnonzero(~passing)
    root_positions = np.flatnonzero(nodes.order.to_numpy() > 0)
    corrected = stored.copy()
    changes = []
    for index in changed:
        absolute = float(abs(actual[index] - stored[index]))
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            coordinate_guard = float(
                64
                * EPS
                * (
                    np.linalg.norm(parent[index])
                    + np.linalg.norm(child[index])
                    + stored[index]
                )
            )
            relative = float(absolute / min(actual[index], stored[index]))
        if (
            not np.isfinite(coordinate_guard)
            or not np.isfinite(relative)
            or absolute > coordinate_guard
            or relative > RELATIVE_CAP
        ):
            raise ValueError(
                "Native length discrepancy exceeds absolute or relative roundoff agreement guard"
            )
        corrected[index] = actual[index]
        changes.append(
            dict(
                node_id=int(roots.node_id.iloc[index]),
                parent_id=int(roots.parent_id.iloc[index]),
                order=int(roots.order.iloc[index]),
                old_length_cm=float(stored[index]),
                new_length_cm=float(actual[index]),
                absolute_error_cm=absolute,
                relative_error=relative,
                absolute_guard_cm=coordinate_guard,
                relative_guard=RELATIVE_CAP,
                original_strict_isclose=False,
            )
        )
    if len(changed) and nodes.length.dtype != np.dtype(np.float64):
        raise ValueError(
            "Corrected native length metadata requires binary64 dtype; no column promotion permitted"
        )
    result, result_edges = nodes.copy(deep=True), edges.copy(deep=True)
    length_column = result.columns.get_loc("length")
    for index in changed:
        result.iat[int(root_positions[index]), length_column] = corrected[index]
    # No validator tolerance or implementation is changed or bypassed.
    _audit(result, result_edges)
    diameter = roots.diameter.to_numpy(float)
    density = roots.root_tissue_density.to_numpy(float)
    before = _moment_arrays(stored, diameter, density)
    after = _moment_arrays(corrected, diameter, density)
    orders = roots.order.to_numpy()
    per_order = {
        int(order): dict(
            edge_count=int(np.sum(orders == order)),
            changed_edge_count=int(np.sum((orders == order) & ~passing)),
            moments=_moment_report(before, after, np.flatnonzero(orders == order)),
        )
        for order in sorted(set(orders))
    }
    diagnostics = dict(
        version=VERSION,
        operation="stored_length_metadata_reconciliation_only",
        qualification="NUMERICAL_AGREEMENT_BOUNDS_NOT_PROOF_OF_CAUSE_OR_BIOLOGICAL_VALIDATION",
        geometry_authority="finite_exported_binary64_endpoint_coordinates_cm",
        strict_test=dict(rtol=1e-9, atol=0.0),
        machine_epsilon=float(EPS),
        absolute_guard_factor=64,
        relative_guard=RELATIVE_CAP,
        edge_count=len(roots),
        changed_edge_count=len(changed),
        changed_node_ids=[record["node_id"] for record in changes],
        changes=changes,
        reported_moment_basis="stored_length_metadata_before_and_after",
        geometric_moment_deltas={name: 0.0 for name in before},
        per_order=per_order,
        totals=_moment_report(before, after, np.arange(len(roots))),
        geometry_changed=False,
        topology_changed=False,
        material_attributes_changed=False,
        existing_strict_graph_validator_passed=True,
        limitation="Origin-dependent absolute bound is capped by relative agreement; neither bound establishes the discrepancy's cause",
    )
    return result, result_edges, diagnostics
