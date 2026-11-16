"""Strict research audit of represented root cylinders, not inferred biomass.

Geometry and density are caller-declared in cm and g_dry/cm3. No stem, crown,
missing-root correction, clipping or diameter/density calibration is performed.
Audit validity alone never qualifies a biological mass acceptance target.
"""

from __future__ import annotations

import hashlib
import json
import math
import copy
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

import numpy as np
import pandas as pd

from ..statistics.summary_statistics import _mass

VERSION = "represented-root-cylinder-mass-audit-v1"
SCHEMA = "deeprootgen_root_only_node_edge_v1"
METRICS = ("segment_count", "length_cm", "volume_cm3", "mass_g")


@dataclass(frozen=True)
class RepresentedRootWholeSystemSupport:
    coordinate_frame: str
    order_to_compartment: Mapping[int, str]
    kind: str = "represented_root_whole_system"
    schema: str = SCHEMA
    coordinate_unit: str = "cm"
    diameter_unit: str = "cm"
    density_unit: str = "g_dry/cm3"

    def __post_init__(self):
        if isinstance(self.order_to_compartment, Mapping):
            object.__setattr__(self, "order_to_compartment", MappingProxyType(dict(self.order_to_compartment)))


@dataclass(frozen=True)
class DensitySource:
    """Provenance kind is generator_default, assumption, or evidence.

    Generator defaults must be labelled unqualified_assumption. Evidence is a
    caller declaration with a reference, not an automatically verified source.
    """

    mode: str
    provenance: str
    provenance_kind: str
    qualification: str
    uniform_density_g_cm3: float | None = None
    unit: str = "g_dry/cm3"


@dataclass(frozen=True)
class MassAcceptanceContract:
    """Independent evidenced mean dry-mass contract; no architecture epsilon."""

    version: str
    evidence_id: str
    support_sha256: str
    uncertainty: str
    target_mean_dry_mass_g: float | None = None
    absolute_tolerance_g: float | None = None
    relative_tolerance: float | None = None
    interval_g: tuple[float, float] | None = None

    def __post_init__(self):
        if isinstance(self.interval_g, (tuple, list)):
            object.__setattr__(self, "interval_g", tuple(self.interval_g))


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be explicit nonempty text")
    return value


def _integer(value, name, minimum=0):
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer))
            or value < minimum):
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _number(value, name, positive=False):
    if isinstance(value, (bool, np.bool_, np.ndarray)) or np.ma.isMaskedArray(value) or np.iscomplexobj(value):
        raise ValueError(f"{name} must be a finite number")
    try:
        value = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a finite number") from error
    if not np.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return value


def _source_primitive(value):
    """Lossless JSON-ready source identity, including ignored nonfinite metadata."""
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return {"__nonfinite_float__": repr(value)}
    if isinstance(value, Mapping):
        # Tag literal mappings too, so a caller's dict cannot impersonate the
        # nonfinite-float marker; retain integer versus string keys distinctly.
        entries = [[_source_primitive(key), _source_primitive(item)] for key, item in value.items()]
        entries.sort(key=lambda pair: json.dumps(pair[0], sort_keys=True, allow_nan=False))
        return {"__mapping__": entries}
    if isinstance(value, (list, tuple)):
        return [_source_primitive(item) for item in value]
    return value


def _digest(value):
    return hashlib.sha256(json.dumps(_source_primitive(value), sort_keys=True, allow_nan=False).encode()).hexdigest()


def _support_record(support):
    if not isinstance(support, RepresentedRootWholeSystemSupport):
        raise ValueError("Explicit represented-root support is required")
    if (support.kind != "represented_root_whole_system" or support.schema != SCHEMA
            or support.coordinate_unit != "cm" or support.diameter_unit != "cm"
            or support.density_unit != "g_dry/cm3"):
        raise ValueError("Unknown support/schema/unit mapping")
    mapping = support.order_to_compartment
    if not isinstance(mapping, Mapping) or not mapping:
        raise ValueError("Explicit root-only order coverage is required")
    orders = {}
    for order, compartment in mapping.items():
        order = _integer(order, "declared root order", minimum=1)
        if compartment != "root":
            raise ValueError("Only explicit root compartments are supported; no stem/crown mapping")
        orders[str(order)] = "root"
    return dict(kind=support.kind, schema=support.schema,
                coordinate_frame=_text(support.coordinate_frame, "coordinate_frame"),
                order_to_compartment=orders, coordinate_unit=support.coordinate_unit,
                diameter_unit=support.diameter_unit, density_unit=support.density_unit,
                invalid_policy="exclude_invalid_child_only", length_source="geometric",
                cylinder_attributes="child_diameter_and_selected_density")


def _density_record(density):
    if not isinstance(density, DensitySource) or density.mode not in {"node", "uniform"}:
        raise ValueError("Density source must explicitly select node or uniform")
    if density.unit != "g_dry/cm3" or density.provenance_kind not in {"generator_default", "assumption", "evidence"}:
        raise ValueError("Unknown density units/provenance mapping")
    if density.qualification not in {"unqualified_assumption", "evidenced"}:
        raise ValueError("Unknown density qualification")
    if density.qualification == "evidenced" and density.provenance_kind != "evidence":
        raise ValueError("Generator defaults and assumptions must remain unqualified_assumption")
    value = density.uniform_density_g_cm3
    if density.mode == "uniform":
        value = _number(value, "uniform density", positive=True)
    elif value is not None:
        raise ValueError("Node density mode cannot also supply a uniform override")
    return dict(mode=density.mode, provenance=_text(density.provenance, "density provenance"),
                provenance_kind=density.provenance_kind, qualification=density.qualification,
                uniform_density_g_cm3=value, unit=density.unit)


def _validate_graph(nodes, edges, support):
    """Validate all graph structure before excluding any cylinder."""
    required = {"node_id", "parent_id", "order", "x", "y", "z", "diameter", "invalid_root", "root_type"}
    if not isinstance(nodes, pd.DataFrame) or not isinstance(edges, pd.DataFrame):
        raise ValueError("Nodes and edges must be DataFrames")
    if not required.issubset(nodes) or not {"parent_id", "child_id"}.issubset(edges):
        raise ValueError("Missing root node/edge schema columns")
    if nodes.columns.duplicated().any() or edges.columns.duplicated().any() or not len(nodes):
        raise ValueError("Empty graph or duplicate schema columns")
    if not nodes.node_id.is_unique:
        raise ValueError("Duplicate node IDs")
    parents, orders = {}, {}
    for row in nodes.itertuples(index=False):
        node = _integer(row.node_id, "node_id")
        parents[node] = _integer(row.parent_id, "parent_id", minimum=-1)
        orders[node] = _integer(row.order, "order")
        if not isinstance(row.invalid_root, (bool, np.bool_)):
            raise ValueError("invalid_root flags must be strict booleans")
    bases = [node for node, order in orders.items() if order == 0]
    if len(bases) != 1 or parents[bases[0]] != -1 or list(parents.values()).count(-1) != 1:
        raise ValueError("Graph requires exactly one base/root")
    base = bases[0]
    if not np.isfinite(nodes[["x", "y", "z"]].to_numpy(float)).all():
        raise ValueError("Nonfinite graph coordinates")
    if "plant_id" in nodes and (nodes.plant_id.isna().any() or nodes.plant_id.nunique() != 1):
        raise ValueError("A per-system audit cannot mix plant identities")
    _validate_edges_and_paths(edges, parents, base)
    roots = nodes.loc[nodes.node_id.ne(base)]
    if not roots.order.map(lambda order: str(order) in support["order_to_compartment"]).all():
        raise ValueError("Root order is outside declared support coverage")
    if not roots.root_type.isin(["fine", "structural"]).all() or nodes.loc[nodes.node_id.eq(base), "root_type"].iloc[0] != "base":
        raise ValueError("Unknown root-only root_type mapping")
    return base


def _validate_edges_and_paths(edges, parents, base):
    pairs = [(_integer(row.parent_id, "edge parent"), _integer(row.child_id, "edge child"))
             for row in edges.itertuples(index=False)]
    expected = {(parent, child) for child, parent in parents.items() if child != base}
    if len(pairs) != len(expected) or set(pairs) != expected:
        raise ValueError("Edge/parent agreement or unique incoming edge failed")
    if any(parent not in parents for child, parent in parents.items() if child != base):
        raise ValueError("Missing parent reference")
    reachable = {base}
    for start in parents:
        node, path = start, set()
        while node not in reachable:
            if node in path:
                raise ValueError("Directed cycle/disconnected component")
            path.add(node)
            node = parents[node]
        reachable.update(path)
    if reachable != set(parents):
        raise ValueError("Unreachable graph nodes")


def _cylinders(nodes, base, density):
    lookup = nodes.set_index("node_id")
    roots = nodes.loc[nodes.node_id.ne(base)].copy()
    lengths, diameters, densities = [], [], []
    for row in roots.itertuples(index=False):
        parent = lookup.loc[row.parent_id]
        length = np.linalg.norm(np.asarray([row.x, row.y, row.z], float) - parent[["x", "y", "z"]].to_numpy(float))
        lengths.append(_number(length, "geometric root length", positive=True))
        diameters.append(_number(row.diameter, "diameter"))
        selected = row.root_tissue_density if density["mode"] == "node" else density["uniform_density_g_cm3"]
        densities.append(_number(selected, "selected density", positive=True))
    roots["segment_length_cm"] = lengths
    roots["diameter"] = diameters
    roots["root_tissue_density"] = densities
    with np.errstate(over="ignore", invalid="ignore"):
        masses = _mass(roots, None)
        volumes = np.pi * (np.asarray(diameters) / 2.) ** 2 * np.asarray(lengths)
    if not np.isfinite(masses).all() or not np.isfinite(volumes).all():
        raise ValueError("Cylinder arithmetic overflow")
    records = []
    for row, mass, volume in zip(roots.itertuples(index=False), masses, volumes):
        parent = lookup.loc[row.parent_id]
        record = dict(child_id=int(row.node_id), parent_id=int(row.parent_id), order=int(row.order),
                      accepted=not bool(row.invalid_root), reason="invalid_child" if row.invalid_root else None,
                      length_cm=float(row.segment_length_cm), diameter_cm=float(row.diameter),
                      density_g_dry_cm3=float(row.root_tissue_density), volume_cm3=float(volume), mass_g=float(mass),
                      density_source=density["mode"], density_provenance=density["provenance"],
                      density_qualification=density["qualification"],
                      valid_child_invalid_parent=bool(not row.invalid_root and parent.invalid_root))
        if "length" in roots:
            stored = float(row.length)
            if not np.isfinite(stored):
                raise ValueError("Present recorded root lengths must be finite for disagreement reporting")
            record.update(recorded_length_cm=stored, geometric_minus_recorded_cm=float(row.segment_length_cm - stored),
                          recorded_length_agrees=bool(np.isclose(stored, row.segment_length_cm, rtol=1e-5, atol=1e-6)))
        records.append(record)
    return records


def _totals(records):
    return dict(segment_count=len(records), **{
        key: math.fsum(record[key] for record in records) for key in METRICS[1:]
    })


def _partition_totals(records):
    return dict(accepted=_totals([r for r in records if r["accepted"]]),
                excluded=_totals([r for r in records if not r["accepted"]]),
                all_root_cylinders=_totals(records))


def audit_cylindrical_mass(nodes, edges, *, system_id, support, density):
    """Audit all represented root edges; biological mass remains NOT_QUALIFIED."""
    _text(system_id, "system_id")
    support_record, density_record = _support_record(support), _density_record(density)
    base = _validate_graph(nodes, edges, support_record)
    if density_record["mode"] == "node" and "root_tissue_density" not in nodes:
        raise ValueError("Node density selection requires root_tissue_density")
    records = _cylinders(nodes, base, density_record)
    result = dict(
        version=VERSION, system_id=system_id, qualification="NOT_QUALIFIED",
        support=support_record, support_sha256=_digest(support_record), density=density_record,
        source_hashes=dict(nodes=_digest(nodes.to_dict("records")), edges=_digest(edges.to_dict("records"))),
        per_edge=records, totals=_partition_totals(records),
        by_order={order: _partition_totals([r for r in records if str(r["order"]) == order])
                  for order in support_record["order_to_compartment"]},
        base_exclusion=dict(node_id=base, reason="order0_no_incoming_cylinder", node_count=1,
                            segment_count=0, length_cm=0., volume_cm3=0., mass_g=0.),
        zero_diameter_count=sum(r["diameter_cm"] == 0 for r in records),
        valid_child_invalid_parent_count=sum(r["valid_child_invalid_parent"] for r in records),
        recorded_length_disagreement_count=sum(not r["recorded_length_agrees"] for r in records if "recorded_length_agrees" in r),
    )
    result["audit_sha256"] = _digest(result)
    return result


def _verify_report(report, hash_key, version):
    if not isinstance(report, Mapping) or report.get("version") != version:
        raise ValueError("Unknown audit report version")
    if report.get(hash_key) != _digest({key: value for key, value in report.items() if key != hash_key}):
        raise ValueError("Audit report identity mismatch")


def mean_population_mass(audits):
    """Equal-system arithmetic means, with every per-system audit retained."""
    if not isinstance(audits, Mapping) or not audits:
        raise ValueError("A nonempty identity-keyed population is required")
    supports, identities = set(), set()
    for system_id, audit in audits.items():
        _verify_report(audit, "audit_sha256", VERSION)
        if system_id != audit["system_id"] or system_id in identities:
            raise ValueError("Population system identity mismatch/duplicate")
        identities.add(system_id)
        supports.add(audit["support_sha256"])
    if len(supports) != 1:
        raise ValueError("Incompatible population mass support")
    first, count = next(iter(audits.values())), len(audits)

    def means(selector):
        return {group: {metric: math.fsum(selector(audit)[group][metric] / count for audit in audits.values())
                        for metric in METRICS} for group in ("accepted", "excluded", "all_root_cylinders")}

    result = dict(version=VERSION + "-population-mean", qualification="NOT_QUALIFIED",
                  n_systems=count, aggregation="equal_system_arithmetic_mean",
                  support=copy.deepcopy(first["support"]), support_sha256=first["support_sha256"],
                  system_audits=copy.deepcopy(dict(audits)), mean_totals=means(lambda audit: audit["totals"]),
                  mean_by_order={order: means(lambda audit: audit["by_order"][order]) for order in first["by_order"]})
    result["mean_dry_mass_g"] = result["mean_totals"]["accepted"]["mass_g"]
    result["population_sha256"] = _digest(result)
    return result


def _acceptance_bounds(contract):
    for name in ("version", "evidence_id", "support_sha256", "uncertainty"):
        _text(getattr(contract, name), name)
    target, absolute, relative, interval = (
        contract.target_mean_dry_mass_g, contract.absolute_tolerance_g,
        contract.relative_tolerance, contract.interval_g,
    )
    if interval is not None:
        if (any(value is not None for value in (target, absolute, relative))
                or not isinstance(interval, (tuple, list)) or len(interval) != 2):
            raise ValueError("Use an independent interval OR target plus one tolerance")
        lo, hi = (_number(value, "mass interval") for value in interval)
        if hi <= lo:
            raise ValueError("Mass interval must have positive width")
        return lo, hi
    target = _number(target, "target mean dry mass", positive=True)
    if (absolute is None) == (relative is None):
        raise ValueError("Supply exactly one independent positive mass tolerance")
    tolerance = (_number(absolute, "absolute mass tolerance", positive=True) if absolute is not None
                 else target * _number(relative, "relative mass tolerance", positive=True))
    return max(0., target - tolerance), _number(target + tolerance, "upper mass bound")


def evaluate_mass_acceptance(population, contract=None):
    """Require both an evidenced target and evidenced density for every system.

    An otherwise valid explicit target with any unqualified density returns
    NOT_QUALIFIED, passed=None and the affected system IDs; it is never PASS.
    """
    _verify_report(population, "population_sha256", VERSION + "-population-mean")
    mass = population["mean_dry_mass_g"]
    if contract is None:
        return dict(status="NOT_QUALIFIED", mean_dry_mass_g=mass, passed=None,
                    support_sha256=population["support_sha256"])
    if not isinstance(contract, MassAcceptanceContract):
        raise ValueError("An explicit independent MassAcceptanceContract is required")
    if contract.support_sha256 != population["support_sha256"]:
        raise ValueError("Mass target support does not match represented-root support")
    lower, upper = _acceptance_bounds(contract)
    unqualified = [system_id for system_id, audit in population["system_audits"].items()
                   if audit["density"]["qualification"] != "evidenced" or audit["density"]["provenance_kind"] != "evidence"]
    if unqualified:
        return dict(status="NOT_QUALIFIED", cause="UNQUALIFIED_DENSITY", passed=None,
                    unqualified_system_ids=unqualified, mean_dry_mass_g=mass,
                    support_sha256=population["support_sha256"])
    return dict(status="EVIDENCED_CONTRACT_EVALUATED", version=contract.version,
                evidence_id=contract.evidence_id, uncertainty=contract.uncertainty,
                support_sha256=contract.support_sha256, mean_dry_mass_g=mass,
                acceptance_interval_g=[lower, upper], passed=bool(lower <= mass <= upper))
