"""Pure primary-curve attachment relocation; no simulator, proposal or RNG calls.

The source must already be construction/sampler verified. This module checks
hashes, graph/curve/step geometry and deterministic placement; existing replay
preflight separately authenticates the unchanged source sampler records.
"""

import copy

import numpy as np
import pandas as pd

from ..data_model import RootSimulationModel
from ..utils.primary_attachment import FIELD, validate_distal_fraction, validate_distal_scope
from .primary_scaffold import _subtree_ids
from .so4_controlled import Skeleton, XYZ, derived_edges, digest, minimal_rotation, unit, validate_geometry

VERSION = 'so4-primary-attachment-distal-v1'
RECEIPT = 'primary_attachment_distal_v1'
CUTOFF_CM = 1e-12
CURVE_ATOL_CM = 1e-8
VOLUME_ATOL_CM3 = 1e-8  # Same existing numeric tolerance, separately named physical units.


def _verified_geometry(source):
    """No sampler re-derivation: verify geometry of an already verified source."""
    source.verify()
    nodes, edges = pd.DataFrame(source.payload['nodes']), pd.DataFrame(source.payload['edges'])
    validate_geometry(nodes, edges)
    if nodes.loc[nodes.order.le(1), 'z'].max() > 20.:
        raise ValueError('Original primary curve exceeds physical surface')
    rebuilt = Skeleton.from_tables(nodes, edges, source.payload['seed'], source.payload['parameters'])
    actual = {o['organ_id']: o for o in source.payload['organs']}
    expected = {o['organ_id']: o for o in rebuilt.payload['organs']}
    if len(actual) != len(source.payload['organs']) or actual.keys() != expected.keys():
        raise ValueError('Original organ membership is incomplete/duplicated')
    lookup = nodes.set_index('node_id')
    for oid, organ in actual.items():
        derived = expected[oid]
        if any(organ[key] != derived[key] for key in ('order', 'parent_id', 'node_ids')):
            raise ValueError('Original organ chain disagrees with graph')
        for key in ('headings', 'parent_tangent', 'attachment_arc_cm'):
            if not np.allclose(organ[key], derived[key], rtol=0, atol=CURVE_ATOL_CM):
                raise ValueError('Original organ geometry metadata disagrees with graph')
        if organ['order'] == 1:
            continue
        _verify_step_geometry(organ, lookup)
    return nodes, edges


def _verify_step_geometry(organ, nodes):
    metadata = organ.get('construction_steps')
    if not isinstance(metadata, dict) or metadata.get('version') != 'so4-construction-steps-v1':
        raise ValueError('Original positioned construction boundaries are required')
    lengths = np.asarray(metadata.get('lengths_cm'), dtype=float)
    boundaries = metadata.get('boundary_node_ids', [])
    ids = organ['node_ids']
    if (lengths.ndim != 1 or not len(lengths) or not np.isfinite(lengths).all()
            or (lengths <= CUTOFF_CM).any() or len(boundaries) != len(lengths)
            or len(set(boundaries)) != len(boundaries) or any(n not in ids for n in boundaries)):
        raise ValueError('Invalid original construction partition')
    points = nodes.loc[[organ['parent_id'], *boundaries], XYZ].to_numpy(float)
    recorded = np.asarray(metadata.get('positioned_boundary_xyz'), dtype=float)
    if recorded.shape != points.shape or not np.allclose(recorded, points, rtol=0, atol=CURVE_ATOL_CM):
        raise ValueError('Original positioned construction coordinates are stale')
    cumulative = np.cumsum(nodes.loc[ids, 'length'].to_numpy(float))
    previous = -1
    for j, (end_id, arc, length) in enumerate(zip(boundaries, np.cumsum(lengths), lengths)):
        end = ids.index(end_id)
        matches = np.flatnonzero(np.isclose(cumulative, arc, rtol=0, atol=CURVE_ATOL_CM))
        if len(matches) != 1 or int(matches[0]) != end or end <= previous:
            raise ValueError('Missing/ambiguous original construction arc')
        fragment_ids = ids[previous + 1:end + 1]
        fractions = np.cumsum(nodes.loc[fragment_ids, 'length'].to_numpy(float)) / length
        expected = points[j] + fractions[:, None] * (points[j + 1] - points[j])
        if (not np.isclose(np.linalg.norm(points[j + 1] - points[j]), length, rtol=0, atol=CURVE_ATOL_CM)
                or not np.allclose(expected, nodes.loc[fragment_ids, XYZ], rtol=0, atol=CURVE_ATOL_CM)):
            raise ValueError('Original construction corner/fragment geometry disagrees')
        previous = end
    if previous != len(ids) - 1:
        raise ValueError('Original construction partition does not cover apex')


def _primary_curves(source, nodes):
    lookup = nodes.set_index('node_id')
    curves = {}
    for organ in sorted(source.payload['organs'], key=lambda o: o['organ_id']):
        if organ['order'] != 1:
            continue
        ids = [organ['parent_id'], *organ['node_ids']]
        points = lookup.loc[ids, XYZ].to_numpy(float)
        geometric = np.linalg.norm(np.diff(points, axis=0), axis=1)
        stored = lookup.loc[organ['node_ids'], 'length'].to_numpy(float)
        if (not np.isfinite(geometric).all() or (geometric <= CUTOFF_CM).any()
                or not np.allclose(geometric, stored, rtol=0, atol=CURVE_ATOL_CM)):
            raise ValueError('Original primary geometric/stored lengths disagree')
        curves[organ['organ_id']] = dict(organ_id=organ['organ_id'], node_ids=ids,
                                         points_cm=points.tolist(), cumulative_cm=np.r_[0., np.cumsum(geometric)].tolist(),
                                         edge_lengths_cm=geometric.tolist(), stored_lengths_cm=stored.tolist(),
                                         child_diameters_cm=lookup.loc[organ['node_ids'], 'diameter'].tolist())
    return curves


def _placements(source, nodes, curves, fraction):
    lookup = nodes.set_index('node_id')
    plans = []
    for organ in sorted(source.payload['organs'], key=lambda o: o['organ_id']):
        if organ['order'] != 2:
            continue
        parent = lookup.loc[organ['parent_id']]
        if int(parent.order) != 1 or int(parent.organ_id) not in curves:
            raise ValueError('Root2 must attach to an original primary curve')
        curve = curves[int(parent.organ_id)]
        old_index = curve['node_ids'].index(organ['parent_id'])
        if old_index == 0:
            raise ValueError('Root2 origin cannot use a primary base with no incoming tangent')
        old_arc, total = curve['cumulative_cm'][old_index], curve['cumulative_cm'][-1]
        if not np.isclose(organ['attachment_arc_cm'], old_arc, rtol=0, atol=CURVE_ATOL_CM):
            raise ValueError('Original physical Root2 arc disagrees with primary curve')
        new_arc = total if old_arc == total else fraction * total + (1. - fraction) * old_arc
        if (not np.isfinite(new_arc) or (old_arc < total and not old_arc < new_arc < total)):
            raise ValueError('Distal site cannot be represented without endpoint snapping/nonprogress')
        plans.append(dict(organ_id=organ['organ_id'], primary_organ_id=int(parent.organ_id),
                          old_parent_id=organ['parent_id'], old_arc_cm=old_arc, new_arc_cm=new_arc,
                          primary_length_cm=total))
    for oid in curves:
        family = [p for p in plans if p['primary_organ_id'] == oid]
        for a, b in zip(sorted(family, key=lambda p: p['old_arc_cm']), sorted(family, key=lambda p: p['old_arc_cm'])[1:]):
            if a['old_arc_cm'] != b['old_arc_cm'] and a['new_arc_cm'] == b['new_arc_cm']:
                raise ValueError('Distinct distal sites rounded to a collision')
    return plans


def _subdivide(rows, curves, plans):
    next_id = max(rows) + 1
    attachments, inserted = {}, []
    for oid, curve in curves.items():
        arcs = np.asarray(curve['cumulative_cm'])
        old_ids = curve['node_ids']
        points = np.asarray(curve['points_cm'])
        sites = sorted({p['new_arc_cm'] for p in plans if p['primary_organ_id'] == oid})
        cuts = sorted(set(arcs.tolist()) | set(sites))
        vertex_ids = dict(zip(arcs.tolist(), old_ids))
        previous_id, rank = old_ids[0], 0
        for arc in cuts[1:]:
            edge = int(np.searchsorted(arcs[1:], arc, side='left'))
            original_child = old_ids[edge + 1]
            if arc in vertex_ids:
                nid = vertex_ids[arc]
            else:
                nid, next_id = next_id, next_id + 1
                t = (arc - arcs[edge]) / (arcs[edge + 1] - arcs[edge])
                xyz = points[edge] + t * (points[edge + 1] - points[edge])
                rows[nid] = copy.deepcopy(rows[original_child])
                rows[nid].update(node_id=nid, **dict(zip(XYZ, xyz.tolist())))
                inserted.append(nid)
                vertex_ids[arc] = nid
            # Constant original child diameter and all other cylinder properties
            # over every split piece. Only chain/rank/length change on old nodes.
            row = rows[nid]
            previous_arc = cuts[rank]
            stored_length = curve['stored_lengths_cm'][edge] * ((arc - previous_arc) / (arcs[edge + 1] - arcs[edge]))
            distance = np.linalg.norm(np.array([row[c] for c in XYZ]) - np.array([rows[previous_id][c] for c in XYZ]))
            if stored_length <= CUTOFF_CM or distance <= CUTOFF_CM or not np.isfinite(distance):
                raise ValueError('Unsplittable positive primary edge; no epsilon snapping')
            rank += 1
            row.update(parent_id=int(previous_id), segment_rank=rank, length=float(stored_length))
            previous_id = nid
        for site in sites:
            attachments[(oid, site)] = vertex_ids[site]
    return attachments, inserted


def _build(source, fraction):
    nodes, _ = _verified_geometry(source)
    curves = _primary_curves(source, nodes)
    plans = _placements(source, nodes, curves, fraction)
    rows = {int(row['node_id']): copy.deepcopy(row) for row in source.payload['nodes']}
    source_rows = copy.deepcopy(rows)
    attachments, inserted = _subdivide(rows, curves, plans)
    children = {nid: [] for nid in source_rows}
    for row in source.payload['nodes']:
        if row['order'] > 0:
            children[row['parent_id']].append(row['node_id'])
    organ_lookup = {o['organ_id']: o for o in source.payload['organs']}
    covered, transforms = set(), []
    for plan in plans:
        organ = organ_lookup[plan['organ_id']]
        old_parent_id = plan['old_parent_id']
        new_parent_id = attachments[(plan['primary_organ_id'], plan['new_arc_cm'])]
        old_parent, new_parent = source_rows[old_parent_id], rows[new_parent_id]
        old_anchor = np.array([old_parent[c] for c in XYZ])
        new_anchor = np.array([new_parent[c] for c in XYZ])
        old_tangent = unit(old_anchor - np.array([source_rows[old_parent['parent_id']][c] for c in XYZ]))
        new_tangent = unit(new_anchor - np.array([rows[new_parent['parent_id']][c] for c in XYZ]))
        rotation = minimal_rotation(old_tangent, new_tangent)
        ids = _subtree_ids(organ['node_ids'][0], children)
        if covered & ids or any(source_rows[nid]['order'] <= 1 for nid in ids):
            raise ValueError('Overlapping/non-Root2 subtree in primary placement')
        for nid in sorted(ids):
            point = np.array([source_rows[nid][c] for c in XYZ])
            xyz = new_anchor + rotation @ (point - old_anchor)
            rows[nid].update(dict(zip(XYZ, xyz.tolist())))
        rows[organ['node_ids'][0]]['parent_id'] = int(new_parent_id)
        covered.update(ids)
        transforms.append(dict(**plan, new_parent_id=int(new_parent_id), subtree_node_ids=sorted(ids),
                               old_anchor_cm=old_anchor.tolist(), new_anchor_cm=new_anchor.tolist(),
                               old_tangent=old_tangent.tolist(), new_tangent=new_tangent.tolist(), rotation=rotation.tolist()))
    if covered != {nid for nid, row in source_rows.items() if row['order'] > 1}:
        raise ValueError('Primary placement subtrees do not cover all higher orders')
    realised = pd.DataFrame([rows[nid] for nid in sorted(rows)])
    edges = derived_edges(realised)
    validate_geometry(realised, edges)
    _check_conservation(nodes, realised)
    parameters = copy.deepcopy(source.payload['parameters'])
    parameters[FIELD] = fraction
    result = Skeleton.from_tables(realised, edges, source.payload['seed'], parameters)
    live = realised.set_index('node_id')
    target_arcs = {plan['organ_id']: plan['new_arc_cm'] for plan in plans}
    for organ in result.payload['organs']:
        if (organ['order'] == 2
                and not np.isclose(organ['attachment_arc_cm'], target_arcs[organ['organ_id']], rtol=0, atol=CURVE_ATOL_CM)):
            raise ValueError('Rebuilt physical attachment arc disagrees with mathematical target')
        for key, value in organ_lookup[organ['organ_id']].items():
            if key not in organ:
                organ[key] = copy.deepcopy(value)
        if 'construction_steps' in organ:
            meta = organ['construction_steps']
            meta['positioned_boundary_xyz'] = live.loc[[organ['parent_id'], *meta['boundary_node_ids']], XYZ].to_numpy(float).tolist()
    for key, value in source.payload.items():
        if key not in result.payload:
            result.payload[key] = copy.deepcopy(value)
    result.payload[RECEIPT] = dict(version=VERSION, fraction=fraction, source_sha256=source.sha256,
                                   source_payload=copy.deepcopy(source.payload), primary_curves=list(curves.values()),
                                   inserted_node_ids=inserted, transforms=transforms,
                                   source_primary_sha256=digest(nodes.loc[nodes.order.le(1)].to_dict('records')),
                                   result_geometry_sha256=digest(result.payload),
                                   curve_equivalence_atol_cm=CURVE_ATOL_CM, volume_equivalence_atol_cm3=VOLUME_ATOL_CM3, tangent_convention='live incoming edge')
    result.sha256 = digest(result.payload)
    return result


def _check_conservation(original, result):
    for nodes in (original, result):
        if nodes.loc[nodes.order.le(1), 'z'].max() > 20.:
            raise ValueError('Relocated primary curve exceeds physical surface')
    for oid in original.loc[original.order.eq(1), 'organ_id'].unique():
        totals = []
        for nodes in (original, result):
            lookup = nodes.set_index('node_id')
            chain = nodes.loc[nodes.organ_id.eq(oid) & nodes.order.eq(1)]
            lengths = [np.linalg.norm(row[XYZ].to_numpy(float) - lookup.loc[int(row.parent_id), XYZ].to_numpy(float))
                       for _, row in chain.iterrows()]
            totals.append([sum(lengths), chain.length.sum(), float(np.sum(np.array(lengths) * (chain.diameter.to_numpy(float) / 2.)**2 * np.pi))])
        if (not np.allclose(totals[0][:2], totals[1][:2], rtol=0, atol=CURVE_ATOL_CM)
                or not np.isclose(totals[0][2], totals[1][2], rtol=0, atol=VOLUME_ATOL_CM3)):
            raise ValueError('Primary curve length/stored length/cylinder volume changed')
    a, b = original.loc[original.order.gt(1)].sort_values('node_id'), result.loc[result.order.gt(1)].sort_values('node_id')
    try:
        pd.testing.assert_frame_equal(a.drop(columns=[*XYZ, 'parent_id']).reset_index(drop=True),
                                      b.drop(columns=[*XYZ, 'parent_id']).reset_index(drop=True), check_exact=True)
    except AssertionError as error:
        raise ValueError('Primary placement changed higher-order dimensions/identities') from error


def relocate_primary_attachments(verified_untransformed_skeleton, b):
    """Return a new INITIAL with no simulator/proposal/RNG calls; never mutate.

    Requires an already construction/sampler-verified untransformed source.
    None/zero preserve its exact payload; positive b must be strictly below1.
    """
    fraction = validate_distal_fraction(b)
    source = verified_untransformed_skeleton
    source.verify()
    if not fraction:
        return Skeleton(copy.deepcopy(source.payload), source.sha256)
    if RECEIPT in source.payload or validate_distal_fraction(source.payload['parameters'].get(FIELD)):
        raise ValueError('Primary attachment relocation requires an untransformed source; cannot compound')
    values = copy.deepcopy(source.payload['parameters'])
    values[FIELD] = fraction
    parameters = RootSimulationModel(**values)
    validate_distal_scope(parameters, source.payload['seed'])
    return _build(source, fraction)


def validate_primary_attachment_provenance(skeleton):
    """Authenticate source and deterministic TABLE transform, without RNG calls."""
    fraction = validate_distal_fraction(skeleton.payload['parameters'].get(FIELD))
    receipt = skeleton.payload.get(RECEIPT)
    if not fraction:
        if RECEIPT in skeleton.payload:
            raise ValueError('Inactive primary placement cannot retain active provenance')
        return
    if (not isinstance(receipt, dict) or receipt.get('version') != VERSION
            or not isinstance(receipt.get('source_payload'), dict) or not isinstance(receipt.get('source_sha256'), str)):
        raise ValueError('Active primary placement requires original source/transform provenance')
    source = Skeleton(receipt['source_payload'], receipt['source_sha256'])
    expected = relocate_primary_attachments(source, fraction)
    if digest(skeleton.payload) != expected.sha256:
        raise ValueError('Primary attachment source/curve/placement/transform provenance mismatch')
