"""Invented curves and coefficients only; no empirical inputs or trial settings."""

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from tests.public_checkpoint_reference import materialize_reference, subprocess_environment

from deeprootgen.model import RootSystemSimulation
from deeprootgen.research import so4_controlled as controlled
from deeprootgen.research import construction_step_replay as canonical
from deeprootgen.research.primary_attachment import RECEIPT, relocate_primary_attachments
from deeprootgen.utils.current_length import sample_current_lengths
from deeprootgen.utils.primary_attachment import FIELD, validate_distal_fraction
from tests.test_construction_step_replay import parameters as grid_parameters, resign
from tests.test_tertiary_length_rank import parameters as rank_parameters
from tests.test_order_specific_sigma import NONE_PARITY_SCRIPT

POLICY = 'minimum_angle_projection'


def analytic_source():
    """A hand-built sampler-authenticated operator fixture, not native birth sites."""
    p = grid_parameters(segments_per_root=2, outer_root_num=1, inner_root_num=0,
                        research_primary_yaw_mean_deg=None, research_primary_yaw_kappa=None,
                        research_primary_inclination_bias=None, research_base_origin_x_cm=2.,
                        research_base_origin_y_cm=-3., research_base_depth_cm=2.,
                        research_current_length_cdfs_cm={
                            2: dict(lengths_cm=[4.], cumulative_probabilities=[1.]),
                            3: dict(lengths_cm=[1.], cumulative_probabilities=[1.])})
    rows = []

    def node(nid, parent, oid, order, rank, xyz, length, diameter):
        rows.append(dict(node_id=nid, parent_id=parent, organ_id=oid, order=order, segment_rank=rank,
                         **dict(zip(controlled.XYZ, map(float, xyz))), length=float(length), diameter=diameter,
                         root_tissue_density=.5, invalid_root=False, plant_id=0, root_type='structural',
                         order_type='primary' if order <= 1 else 'secondary', position_type='outer', simulation_tag='invented'))

    node(0, -1, 0, 0, 0, [2, -3, 18], 0, 0.)
    node(1, 0, 1, 1, 1, [5, -3, 18], 3, .4)
    node(2, 1, 1, 1, 2, [8, -3, 18], 3, .4)
    node(3, 2, 1, 1, 3, [8, 6, 18], 9, .2)
    metadata = {}
    for oid, parent, first, order, direction in [(2, 1, 4, 2, [0, 0, -1]), (3, 2, 6, 2, [0, 0, -1]),
                                                 (4, 4, 8, 3, [1, 0, 0]), (5, 6, 10, 3, [1, 0, 0])]:
        lengths, sampler = sample_current_lengths(p.research_current_length_cdfs_cm[order], 2, 42, oid, order)
        start = np.array([next(row for row in rows if row['node_id'] == parent)[c] for c in controlled.XYZ])
        for j, length in enumerate(lengths):
            start = start + length * np.array(direction)
            node(first + j, parent if not j else first + j - 1, oid, order, j + 1, start, length, .1 / order)
        sampler.update(allocated_organ_id=oid, legacy_compatibility_draw_count=3, post_subdivision_length_cm=float(lengths.sum()))
        metadata[oid] = dict(version=canonical.VERSION, lengths_cm=lengths.tolist(),
                             boundary_node_ids=[first, first + 1], sampler=sampler)
    nodes = pd.DataFrame(rows)
    parameters = p.model_dump()
    parameters.pop(FIELD, None)
    source = controlled.Skeleton.from_tables(nodes, controlled.derived_edges(nodes), 42, parameters)
    lookup = nodes.set_index('node_id')
    for organ in source.payload['organs']:
        if organ['order'] > 1:
            meta = metadata[organ['organ_id']]
            meta['positioned_boundary_xyz'] = lookup.loc[[organ['parent_id'], *meta['boundary_node_ids']], controlled.XYZ].to_numpy(float).tolist()
            organ['construction_steps'] = meta
    source = resign(source)
    canonical.validate_construction_metadata(source)
    return source


def primary_totals(skeleton):
    nodes = pd.DataFrame(skeleton.payload['nodes']).set_index('node_id')
    roots = nodes[nodes.order.eq(1)]
    lengths = [np.linalg.norm(row[controlled.XYZ].to_numpy(float) - nodes.loc[row.parent_id, controlled.XYZ].to_numpy(float))
               for _, row in roots.iterrows()]
    return sum(lengths), roots.length.sum(), np.sum(np.array(lengths) * (roots.diameter.to_numpy(float) / 2.)**2 * np.pi)


@pytest.mark.parametrize('b', [.25, .5])
def test_analytic_curve_arcs_tangents_volume_dimensions_and_atomic_pure_transport(b, monkeypatch):
    source = analytic_source()
    snapshot = copy.deepcopy(source.payload)

    def forbidden(*args, **kwargs):
        pytest.fail('Pure attachment transform called simulator/proposal/RNG')

    with monkeypatch.context() as context:
        context.setattr(np.random, 'default_rng', forbidden)
        context.setattr(RootSystemSimulation, '__init__', forbidden)
        context.setattr(controlled, 'fichtl_proposal', forbidden)
        transformed = relocate_primary_attachments(source, b)
    assert source.payload == snapshot
    repeated = relocate_primary_attachments(source, b)
    assert transformed.payload == repeated.payload and transformed.sha256 == repeated.sha256
    before, after = pd.DataFrame(source.payload['nodes']).set_index('node_id'), pd.DataFrame(transformed.payload['nodes']).set_index('node_id')
    np.testing.assert_array_equal(after.loc[[0, 1, 2, 3], controlled.XYZ], before.loc[[0, 1, 2, 3], controlled.XYZ])
    np.testing.assert_allclose(primary_totals(source), primary_totals(transformed), rtol=0, atol=1e-8)
    old = before[before.order.gt(1)]
    new = after[after.order.gt(1)]
    pd.testing.assert_frame_equal(old.drop(columns=[*controlled.XYZ, 'parent_id']),
                                  new.drop(columns=[*controlled.XYZ, 'parent_id']), check_exact=True)
    for report in transformed.payload[RECEIPT]['transforms']:
        expected_arc = b * 15. + (1. - b) * report['old_arc_cm']
        assert report['new_arc_cm'] == expected_arc
        assert after.loc[report['new_parent_id'], 'order'] == 1
        assert new.loc[next(o for o in transformed.payload['organs'] if o['organ_id'] == report['organ_id'])['node_ids'][0], 'parent_id'] == report['new_parent_id']
        matrix = np.array(report['rotation'])
        np.testing.assert_allclose(matrix.T @ matrix, np.eye(3), rtol=0, atol=1e-12)
        assert np.linalg.det(matrix) == pytest.approx(1., abs=1e-12)
        expected = report['new_anchor_cm'] + (before.loc[report['subtree_node_ids'], controlled.XYZ].to_numpy(float) - report['old_anchor_cm']) @ matrix.T
        np.testing.assert_allclose(after.loc[report['subtree_node_ids'], controlled.XYZ], expected, rtol=0, atol=1e-10)
    # b=.25 sends first attachment EXACTLY to old corner s=6; incoming x edge.
    first = transformed.payload[RECEIPT]['transforms'][0]
    if b == .25:
        assert first['new_arc_cm'] == 6. and first['new_parent_id'] == 2
        assert first['new_tangent'] == [1., 0., 0.]
    else:
        assert first['new_arc_cm'] == 9. and first['new_tangent'] == [0., 1., 0.]
    inserted = transformed.payload[RECEIPT]['inserted_node_ids']
    assert all(n > before.index.max() for n in inserted)
    assert list(after[after.order.eq(1)].sort_values('segment_rank').segment_rank) == list(range(1, 4 + len(inserted)))
    assert all(after.loc[n, 'diameter'] == .2 for n in inserted)  # Both sites on original second edge.
    canonical.validate_construction_metadata(transformed)
    controlled.validate_geometry(after.reset_index(), pd.DataFrame(transformed.payload['edges']))


@pytest.mark.parametrize('b', [None, 0., -0.])
def test_pure_noop_is_exact(b):
    source = analytic_source()
    result = relocate_primary_attachments(source, b)
    assert result.payload == source.payload and result.sha256 == source.sha256
    assert RECEIPT not in result.payload


@pytest.mark.parametrize('b', [True, np.bool_(False), '0.25', -.1, 1., 1.1, np.nan, np.inf, 10**400, -(10**400)])
def test_malformed_fraction_rejects_helper_schema_and_bypass_before_mutation(b):
    with pytest.raises(ValueError):
        validate_distal_fraction(b)
    with pytest.raises(ValueError):
        grid_parameters(**{FIELD: b})
    p = grid_parameters().model_copy(update={FIELD: b})
    sim = RootSystemSimulation(random_seed=42)
    before = sim.G.as_df()
    with pytest.raises(ValueError):
        sim.init_organs(p)
    for a, c in zip(before, sim.G.as_df()):
        pd.testing.assert_frame_equal(a, c, check_exact=True)


@pytest.mark.parametrize('b', [np.nextafter(0., 1.), np.nextafter(1., 0.)])
def test_unrepresentable_or_unsplittable_sites_reject_without_snapping_or_mutation(b):
    source = analytic_source()
    before = copy.deepcopy(source.payload)
    with pytest.raises(ValueError, match='snapping|collision|Unsplittable'):
        relocate_primary_attachments(source, b)
    assert source.payload == before


@pytest.mark.parametrize('updates', [dict(research_current_length_grid=None), dict(max_order=2), dict(tropism_mode='legacy'),
                                     dict(random_seed=None), dict(random_seed=True), dict(random_seed='42'),
                                     dict(research_current_length_cdfs_cm=None)])
def test_scope_and_seed_guards(updates):
    with pytest.raises(ValueError):
        grid_parameters(**{FIELD: .25, **updates})
    p = grid_parameters(**{FIELD: .25}).model_copy(update=updates)
    sim = RootSystemSimulation(random_seed=42)
    with pytest.raises(ValueError):
        sim.init_organs(p)


def test_native_legacy_and_saved_settings_guards_and_empty_provenance():
    source = analytic_source()
    result = relocate_primary_attachments(source, .25)
    for method in ['run', 'apply_fichtl_tropism']:
        p = grid_parameters(**{FIELD: .25}).model_copy(update=dict(research_current_length_grid=None, research_current_length_cdfs_cm=None))
        with pytest.raises(ValueError, match='named controlled replay'):
            getattr(RootSystemSimulation(random_seed=42), method)(p)
    for arm in 'ABCD':
        with pytest.raises(ValueError, match='construction-step'):
            controlled.replay_arm(result, arm, result.payload['parameters'], POLICY)
    with pytest.raises(ValueError, match='setting.*INITIAL'):
        canonical.replay_construction_steps(result, 'D', {**result.payload['parameters'], FIELD: .5}, POLICY)
    with pytest.raises(ValueError, match='untransformed'):
        relocate_primary_attachments(result, .25)
    nodes = pd.DataFrame(source.payload['nodes'])
    nodes = nodes.loc[nodes.order.le(1)]
    empty = controlled.Skeleton.from_tables(nodes, controlled.derived_edges(nodes), 42, source.payload['parameters'])
    transformed = relocate_primary_attachments(empty, .25)
    assert transformed.payload[RECEIPT]['transforms'] == []
    canonical.validate_construction_metadata(transformed)
    for defect in ['missing', 'inactive']:
        changed = copy.deepcopy(transformed)
        if defect == 'missing':
            changed.payload.pop(RECEIPT)
        else:
            changed.payload['parameters'][FIELD] = 0.
        with pytest.raises(ValueError, match='provenance'):
            canonical.validate_construction_metadata(resign(changed))


@pytest.mark.parametrize('defect', ['source_sha', 'source_curve', 'arc', 'rotation', 'piece_D', 'higher_D', 'missing_receipt', 'target'])
def test_resealed_provenance_geometry_and_membership_tampering_rejected(defect):
    result = relocate_primary_attachments(analytic_source(), .5)
    receipt = result.payload[RECEIPT]
    if defect == 'source_sha':
        receipt['source_sha256'] = 'tampered'
    elif defect == 'source_curve':
        receipt['source_payload']['nodes'][1]['diameter'] *= 2
    elif defect == 'arc':
        receipt['transforms'][0]['new_arc_cm'] += .1
    elif defect == 'rotation':
        receipt['transforms'][0]['rotation'][0][0] += .1
    elif defect in ['piece_D', 'higher_D']:
        node = next(n for n in result.payload['nodes'] if n['node_id'] in receipt['inserted_node_ids']) if defect == 'piece_D' else next(n for n in result.payload['nodes'] if n['order'] == 3)
        node['diameter'] *= 2
    elif defect == 'missing_receipt':
        result.payload.pop(RECEIPT)
    else:
        receipt['fraction'] = .25
    with pytest.raises(ValueError):
        canonical.validate_construction_metadata(resign(result))


def test_actual_constructor_equals_pure_transform_with_sigma_q_rank_and_json_roundtrip(monkeypatch):
    p = rank_parameters(.35, research_primary_yaw_reverse_probability=.5, research_fichtl_sigma_by_order={2: .11, 3: .21})
    source = controlled.construct_skeleton(p, 42)
    canonical.validate_construction_metadata(source)
    pure = relocate_primary_attachments(source, .125)
    direct = controlled.construct_skeleton({**p.model_dump(), FIELD: .125}, 42)
    assert pure.payload == direct.payload and pure.sha256 == direct.sha256
    loaded = controlled.Skeleton(json.loads(json.dumps(source.payload, sort_keys=True)), source.sha256)
    assert relocate_primary_attachments(loaded, .125).sha256 == pure.sha256
    original = {o['organ_id']: o for o in source.payload['organs']}
    for organ in pure.payload['organs']:
        if organ['order'] > 1:
            a, b = original[organ['organ_id']]['construction_steps'], organ['construction_steps']
            assert a['sampler'] == b['sampler'] and a['lengths_cm'] == b['lengths_cm'] and a['boundary_node_ids'] == b['boundary_node_ids']
    first = canonical.replay_construction_steps(pure, 'D', pure.payload['parameters'], POLICY)
    second = canonical.replay_construction_steps(direct, 'D', direct.payload['parameters'], POLICY)
    pd.testing.assert_frame_equal(first['nodes'], second['nodes'], check_exact=True)
    assert first['diagnostics'] == second['diagnostics']


def test_added_primary_cut_preserves_curve_and_semantic_step_innovations():
    source = analytic_source()
    rows = copy.deepcopy(source.payload['nodes'])
    new = copy.deepcopy(rows[1])
    new.update(node_id=12, parent_id=0, x=3., length=1., segment_rank=1)
    rows.append(new)
    rows[1].update(parent_id=12, length=2., segment_rank=2)
    rows[2]['segment_rank'] = 3
    rows[3]['segment_rank'] = 4
    nodes = pd.DataFrame(rows)
    refined = controlled.Skeleton.from_tables(nodes, controlled.derived_edges(nodes), 42, source.payload['parameters'])
    old = {o['organ_id']: o for o in source.payload['organs']}
    for organ in refined.payload['organs']:
        if organ['order'] > 1:
            organ['construction_steps'] = copy.deepcopy(old[organ['organ_id']]['construction_steps'])
    refined = resign(refined)
    canonical.validate_construction_metadata(refined)
    results = []
    for s in [source, refined]:
        transformed = relocate_primary_attachments(s, .5)
        results.append(canonical.replay_construction_steps(transformed, 'D', transformed.payload['parameters'], POLICY))
    for a, b in zip(results[0]['diagnostics']['construction_steps'], results[1]['diagnostics']['construction_steps']):
        assert (a['organ_id'], a['step_index']) == (b['organ_id'], b['step_index'])
        assert a.get('innovations_sha256') == b.get('innovations_sha256')
        np.testing.assert_allclose(a['accepted_endpoint'], b['accepted_endpoint'], rtol=0, atol=1e-8)


def test_none_zero_isolated_prechange_parity_with_active_prior_controls(tmp_path):
    current = Path(__file__).parents[1]
    old = materialize_reference(current, tmp_path, 'primary_attachment_distal')
    script = NONE_PARITY_SCRIPT.replace('research_fichtl_sigma_by_order', FIELD).replace(
        "('explicit_none',{'" + FIELD + "':None})", "('explicit_none',{'" + FIELD + "':None}),('explicit_zero',{'" + FIELD + "':0.})")
    from tests.test_primary_yaw_initialization import parameters as legacy_parameters
    yaw = dict(research_primary_yaw_mean_deg=35., research_primary_yaw_kappa=4., research_primary_yaw_reverse_probability=.5)
    configs = dict(native_legacy=legacy_parameters(**yaw).model_dump(),
                   native_fichtl=grid_parameters(active=False, **yaw).model_dump(),
                   graph=grid_parameters(active=False, **yaw).model_dump(),
                   canonical=rank_parameters(.35, research_fichtl_sigma_by_order={2: .11, 3: .21}, **yaw).model_dump())
    for config in configs.values():
        config.pop(FIELD, None)
    results, hashes = {}, {}
    for name, source in [('old', old), ('current', current)]:
        run = subprocess.run([sys.executable, '-c', script], input=json.dumps(configs), capture_output=True,
                             text=True, check=True, timeout=90, cwd=source,
                             env=subprocess_environment(source))
        record = json.loads(run.stdout)
        assert Path(record['loaded_root']).resolve() == (source / 'deeprootgen/model/root.py').resolve()
        assert record['outputs']['omitted'] == record['outputs']['explicit_none'] == record['outputs']['explicit_zero']
        results[name] = record['outputs']
        hashes[name] = {f: hashlib.sha256((source / f).read_bytes()).hexdigest() for f in (
            'deeprootgen/model/root.py', 'deeprootgen/data_model/simulation_data_models.py',
            'deeprootgen/research/so4_controlled.py', 'deeprootgen/research/construction_step_replay.py')}
    assert results['old'] == results['current']
    destination = Path(os.environ.get('DRG_PRIMARY_ATTACHMENT_PARITY_DIR', str(tmp_path)))
    destination.mkdir(parents=True, exist_ok=True)
    receipt = dict(source_sha256=hashes, output_sha256={name: controlled.digest(record) for name, record in results.items()})
    (destination / 'parity.json').write_text(json.dumps(receipt, indent=2) + '\n')


def test_accumulated_stored_arc_error_rejects_instead_of_misreporting_target():
    original = analytic_source()
    nodes = pd.DataFrame(original.payload['nodes'])
    nodes = nodes.loc[~nodes.organ_id.isin([3, 5])].copy()
    for nid, delta in [(1, 6e-9), (2, 6e-9), (3, -6e-9)]:
        nodes.loc[nodes.node_id.eq(nid), 'length'] += delta
    source = controlled.Skeleton.from_tables(nodes, controlled.derived_edges(nodes), 42, original.payload['parameters'])
    previous = {o['organ_id']: o for o in original.payload['organs']}
    for organ in source.payload['organs']:
        if organ['order'] > 1:
            organ['construction_steps'] = copy.deepcopy(previous[organ['organ_id']]['construction_steps'])
    source = resign(source)
    canonical.validate_construction_metadata(source)  # Existing global1e-8 geometry contract passes.
    snapshot = copy.deepcopy(source.payload)
    with pytest.raises(ValueError, match='physical attachment arc'):
        relocate_primary_attachments(source, .25)
    assert source.payload == snapshot
