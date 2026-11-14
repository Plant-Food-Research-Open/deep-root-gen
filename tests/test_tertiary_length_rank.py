"""Invented sibling pools only; no observations, fitted values or empirical runs."""

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
from deeprootgen.research import construction_step_replay as canonical
from deeprootgen.research import so4_controlled as controlled
from deeprootgen.utils.current_length import sample_current_lengths
from deeprootgen.utils.tertiary_length_rank import (
    FIELD, VERSION, plan_tertiary_length_family, rank_permutation, validate_rank_strength,
)
from tests.test_construction_step_replay import parameters as grid_parameters, resign
from tests.test_primary_yaw_reversal import NONE_PARITY_SCRIPT

ZONE = dict(basal_cm=1., apical_cm=1., spacing_cm=2.)
CDF3 = dict(lengths_cm=[1., 2., 3., 4.], cumulative_probabilities=[.15, .4, .75, 1.])
POLICY = 'minimum_angle_projection'


def parameters(strength=None, **updates):
    values = dict(research_parent2_branch_zone_cm=ZONE, min_sec_root_num=2, max_sec_root_num=3,
                  growth_sec_root=0., interbranch_distance=1., segments_per_root=3,
                  research_current_length_cdfs_cm={2: dict(lengths_cm=[10.], cumulative_probabilities=[1.]), 3: CDF3},
                  research_tertiary_length_rank_strength=strength)
    values.update(updates)
    return grid_parameters(**values)


def initial(p):
    sim = RootSystemSimulation(random_seed=p.random_seed)
    sim.init_organs(p)
    sim.position_secondary_roots(p)
    sim.position_primary_roots(p)
    return sim


def test_exact_analytic_permutation_ties_empty_singleton_and_partial():
    u = [.1, .8, .4, .2]
    assert rank_permutation(u, None)[0] == [0, 1, 2, 3]
    assert rank_permutation(u, 0.)[0] == [0, 1, 2, 3]
    assert rank_permutation(u, 1.)[0] == [1, 2, 3, 0]
    assert rank_permutation(u, .3)[0] == [3, 1, 2, 0]
    assert rank_permutation(u, .3) == rank_permutation(u, .3)
    assert rank_permutation([.4, .4, .4], 0.)[0] == [0, 1, 2]
    assert rank_permutation([.4, .4, .4], 1.)[0] == [2, 1, 0]
    assert rank_permutation([], .7) == ([], [])
    assert rank_permutation([.7], 1.)[0] == [0]
    # At this exact score tie, destination0 precedes destination1.
    assert rank_permutation([.25, .75], .5)[1] == [-.0, -.0]
    assert rank_permutation([.25, .75], .5)[0] == [0, 1]


@pytest.mark.parametrize('strength', [None, 0., .3, 1.])
def test_family_plan_source_lengths_own_weights_and_bijection(strength):
    strength = strength or 0.
    plans, family = plan_tertiary_length_family(CDF3, 3, 42, 2, 10, [1., 3., 5., 7., 9.], strength)
    originals = [sample_current_lengths(CDF3, 3, 42, oid, 3) for oid in range(10, 15)]
    assert sorted(family['source_indices']) == list(range(5))
    assert sorted(p[1]['sampled_current_length_cm'] for p in plans) == sorted(p[1]['sampled_current_length_cm'] for p in originals)
    for j, (lengths, sampler) in enumerate(plans):
        source = family['source_indices'][j]
        assert sampler['stream_version'] == VERSION
        assert sampler['expected_organ_id'] == sampler['weight_source_organ_id'] == 10 + j
        assert sampler['length_source_organ_id'] == 10 + source
        assert sampler['destination_draw'] == originals[j][1]
        assert sampler['source_draw'] == originals[source][1]
        np.testing.assert_array_equal(sampler['normalized_weights'], originals[j][1]['normalized_weights'])
        np.testing.assert_array_equal(lengths, originals[source][1]['sampled_current_length_cm'] * np.array(sampler['normalized_weights']))
    if strength == 1.:
        assert np.all(np.diff([p[1]['sampled_current_length_cm'] for p in plans]) <= 0)
    for sites in ([], [1.]):
        first = plan_tertiary_length_family(CDF3, 3, 42, 2, 10, sites, .5)
        second = plan_tertiary_length_family(CDF3, 3, 42, 2, 10, sites, .5)
        assert first[1] == second[1]
        assert first[1]['source_indices'] == list(range(len(sites)))


@pytest.mark.parametrize('value', [True, np.bool_(False), '.3', -.1, 1.1, np.nan, np.inf, [0.3], 10**400, -(10**400)])
def test_invalid_strength_helper_schema_and_bypass_before_mutation(value):
    with pytest.raises(ValueError):
        validate_rank_strength(value)
    with pytest.raises(ValueError):
        parameters(value)
    bad = parameters().model_copy(update={FIELD: value})
    sim = RootSystemSimulation(random_seed=42)
    before = sim.G.as_df()
    state = copy.deepcopy(sim.rng.bit_generator.state)
    with pytest.raises(ValueError):
        sim.init_organs(bad)
    for a, b in zip(before, sim.G.as_df()):
        pd.testing.assert_frame_equal(a, b, check_exact=True)
    assert state == sim.rng.bit_generator.state


@pytest.mark.parametrize('updates', [dict(research_current_length_grid=None), dict(research_parent2_branch_zone_cm=None),
                                     dict(max_order=2), dict(tropism_mode='legacy'), dict(random_seed=None),
                                     dict(random_seed=True), dict(random_seed='42'), dict(random_seed=-1),
                                     dict(research_current_length_cdfs_cm=None),
                                     dict(research_current_length_cdfs_cm={2: dict(lengths_cm=[10.], cumulative_probabilities=[1.])})])
def test_schema_scope_and_bypassed_scope_rejected(updates):
    with pytest.raises(ValueError):
        parameters(.5, **updates)
    sim = RootSystemSimulation(random_seed=42)
    bad = parameters(.5).model_copy(update=updates)
    before = sim.G.as_df()
    with pytest.raises(ValueError):
        sim.init_organs(bad)
    for a, b in zip(before, sim.G.as_df()):
        pd.testing.assert_frame_equal(a, b, check_exact=True)


def test_authoritative_seed_native_and_legacy_route_guards():
    p = parameters(.5)
    for seed in (None, 43):
        sim = RootSystemSimulation(random_seed=seed)
        with pytest.raises(ValueError, match='seed'):
            sim.init_organs(p)
    with pytest.raises(ValueError, match='matching explicit seeds'):
        controlled.construct_skeleton(p, 43)
    bad = p.model_copy(update=dict(research_current_length_grid=None, research_parent2_branch_zone_cm=None))
    for method in ('run', 'apply_fichtl_tropism'):
        with pytest.raises(ValueError, match='named controlled replay'):
            getattr(RootSystemSimulation(random_seed=42), method)(bad)
    saved = controlled.construct_skeleton(p, 42)
    for arm in 'ABCD':
        with pytest.raises(ValueError, match='construction-step replay'):
            controlled.replay_arm(saved, arm, p.model_dump(), POLICY)
    with pytest.raises(ValueError, match='rank setting.*INITIAL'):
        canonical.replay_construction_steps(saved, 'D', {**p.model_dump(), FIELD: .2}, POLICY)
    old = controlled.construct_skeleton(parameters(), 42)
    with pytest.raises(ValueError, match='rank setting.*INITIAL'):
        controlled.replay_arm(old, 'D', {**parameters().model_dump(), FIELD: .5}, POLICY)


@pytest.mark.parametrize('strength', [.35, 1.])
def test_actual_graph_pool_own_weights_draw_schedule_and_primary_root2_exact(strength, monkeypatch):
    import deeprootgen.model.root as module
    import deeprootgen.utils.tertiary_length_rank as rank_module

    native_sampler, calls = module.sample_current_lengths, []

    def observed(*args):
        calls.append((args[2], args[3], args[4]))
        return native_sampler(*args)

    monkeypatch.setattr(module, 'sample_current_lengths', observed)
    monkeypatch.setattr(rank_module, 'sample_current_lengths', observed)
    old = initial(parameters())
    old_calls = calls.copy()
    calls.clear()
    new = initial(parameters(strength))
    assert calls == old_calls  # Every original organ draw, once, same keys/order.
    a, ae = old.G.as_df()
    b, be = new.G.as_df()
    pd.testing.assert_frame_equal(ae, be, check_exact=True)
    pd.testing.assert_frame_equal(a[a.order.le(2)], b[b.order.le(2)], check_exact=True)
    pd.testing.assert_frame_equal(a.drop(columns=['x', 'y', 'z', 'length']), b.drop(columns=['x', 'y', 'z', 'length']), check_exact=True)
    assert old.rng.bit_generator.state == new.rng.bit_generator.state
    moved = False
    for before, after in zip(old.organs[2], new.organs[2]):
        lengths_before = [child.current_length_diagnostics['sampled_current_length_cm'] for child in before.child_organs]
        lengths_after = [child.current_length_diagnostics['sampled_current_length_cm'] for child in after.child_organs]
        assert sorted(lengths_before) == sorted(lengths_after)
        assert len(before.child_organs) == len(after.child_organs) == 5
        moved |= lengths_before != lengths_after
        for old_child, new_child in zip(before.child_organs, after.child_organs):
            report = new_child.current_length_diagnostics
            assert report['normalized_weights'] == old_child.current_length_diagnostics['normalized_weights']
            assert report['allocated_organ_id'] == report['expected_organ_id'] == new_child.segments[0].node_data.organ_id
            assert report['legacy_compatibility_draw_count'] == 4
            assert report['source_draw']['expected_organ_id'] == report['length_source_organ_id']
            assert report['destination_draw']['expected_organ_id'] == report['weight_source_organ_id']
    assert moved
    assert a.length.sum() == pytest.approx(b.length.sum(), rel=0, abs=1e-8)
    controlled.validate_geometry(b, be, 20.)


@pytest.mark.parametrize('sites', [dict(basal_cm=6., apical_cm=5., spacing_cm=2.), dict(basal_cm=5., apical_cm=5., spacing_cm=2.)])
def test_actual_zero_and_singleton_families_capture_and_replay(sites):
    p = parameters(1., research_parent2_branch_zone_cm=sites)
    saved = controlled.construct_skeleton(p, 42)
    canonical.validate_construction_metadata(saved)
    for parent in (o for o in saved.payload['organs'] if o['order'] == 2):
        receipt = parent['tertiary_length_rank_family']
        n = len(receipt['destination_organ_ids'])
        assert n <= 1 and receipt['source_indices'] == list(range(n))
    canonical.replay_construction_steps(saved, 'D', p.model_dump(), POLICY)


def test_combined_zone_sigma_q_root2_trajectory_and_innovations_exact():
    extra = dict(research_primary_yaw_reverse_probability=.5, research_fichtl_sigma_by_order={2: .04, 3: .3})
    p, q = parameters(**extra), parameters(1., **extra)
    old, new = controlled.construct_skeleton(p, 42), controlled.construct_skeleton(q, 42)
    a, b = pd.DataFrame(old.payload['nodes']), pd.DataFrame(new.payload['nodes'])
    pd.testing.assert_frame_equal(a[a.order.le(2)], b[b.order.le(2)], check_exact=True)
    outputs = [canonical.replay_construction_steps(s, 'D', v.model_dump(), POLICY) for s, v in [(old, p), (new, q)]]
    first, second = outputs
    assert [r for r in first['diagnostics']['construction_steps'] if r['order'] == 2] == [r for r in second['diagnostics']['construction_steps'] if r['order'] == 2]
    pd.testing.assert_frame_equal(first['nodes'][first['nodes'].order.le(2)], second['nodes'][second['nodes'].order.le(2)], check_exact=True)
    for output, source in zip(outputs, [old, new]):
        controlled.validate_geometry(output['nodes'], output['edges'], 20.)
        assert output['diagnostics']['invariant_hashes'] == controlled.invariant_hashes(pd.DataFrame(source.payload['nodes']))
    repeated = canonical.replay_construction_steps(new, 'D', q.model_dump(), POLICY)
    pd.testing.assert_frame_equal(second['nodes'], repeated['nodes'], check_exact=True)
    assert second['diagnostics'] == repeated['diagnostics']


@pytest.mark.parametrize('mutation', ['source_id', 'permutation', 'quantile', 'strength', 'weights', 'destination_id',
                                      'missing_family', 'missing_child', 'duplicate_source', 'cdf', 'own_draw', 'lengths'])
def test_authentication_rejects_resealed_metadata_tampering(mutation):
    saved = controlled.construct_skeleton(parameters(.6), 42)
    changed = copy.deepcopy(saved)
    parent = next(o for o in changed.payload['organs'] if o['order'] == 2)
    child = next(o for o in changed.payload['organs'] if o['order'] == 3)
    report = child['construction_steps']['sampler']
    family = parent['tertiary_length_rank_family']
    if mutation == 'source_id':
        report['source_draw']['expected_organ_id'] += 1
    elif mutation == 'permutation':
        family['source_indices'] = list(reversed(family['source_indices']))
    elif mutation == 'quantile':
        report['source_draw']['quantile'] = .001
    elif mutation == 'strength':
        changed.payload['parameters'][FIELD] = .7
    elif mutation == 'weights':
        report['normalized_weights'][0] += .001
    elif mutation == 'destination_id':
        report['expected_organ_id'] += 1
    elif mutation == 'missing_family':
        parent.pop('tertiary_length_rank_family')
    elif mutation == 'missing_child':
        changed.payload['organs'].remove(child)
    elif mutation == 'duplicate_source':
        family['source_indices'][1] = family['source_indices'][0]
    elif mutation == 'cdf':
        report['cdf_sha256'] = 'tampered'
    elif mutation == 'own_draw':
        report['destination_draw']['quantile'] = .001
    elif mutation == 'lengths':
        child['construction_steps']['lengths_cm'][0] += .001
    changed = resign(changed)
    with pytest.raises(ValueError):
        canonical.validate_construction_metadata(changed)


def test_none_zero_prechange_native_graph_canonical_active_sigma_q_parity(tmp_path):
    current = Path(__file__).parents[1]
    old = materialize_reference(current, tmp_path, 'tertiary_length_rank')
    script = NONE_PARITY_SCRIPT.replace('research_fichtl_sigma_by_order', FIELD).replace(
        "('explicit_none',{'" + FIELD + "':None})", "('explicit_none',{'" + FIELD + "':None}),('explicit_zero',{'" + FIELD + "':0.})")
    from tests.test_primary_yaw_initialization import parameters as legacy_parameters
    yaw = dict(research_primary_yaw_mean_deg=35., research_primary_yaw_kappa=4., research_primary_yaw_reverse_probability=.5)
    configs = dict(native_legacy=legacy_parameters(**yaw).model_dump(),
                   native_fichtl=grid_parameters(active=False, **yaw).model_dump(),
                   graph=grid_parameters(active=False, **yaw).model_dump(),
                   canonical=parameters(research_fichtl_sigma_by_order={2: .04, 3: .3}, **yaw).model_dump())
    configs['native_fichtl']['research_fichtl_sigma_by_order'] = {2: .04, 3: .3}
    for config in configs.values():
        config.pop(FIELD, None)
    results, hashes = {}, {}
    for name, source in [('old', old), ('current', current)]:
        run = subprocess.run([sys.executable, '-c', script], input=json.dumps(configs), capture_output=True,
                             text=True, check=True, timeout=90, cwd=source,
                             env=subprocess_environment(source))
        result = json.loads(run.stdout)
        assert Path(result['loaded_root']).resolve() == (source / 'deeprootgen/model/root.py').resolve()
        assert result['outputs']['omitted'] == result['outputs']['explicit_none'] == result['outputs']['explicit_zero']
        results[name] = result['outputs']
        hashes[name] = {f: hashlib.sha256((source / f).read_bytes()).hexdigest() for f in (
            'deeprootgen/model/root.py', 'deeprootgen/data_model/simulation_data_models.py',
            'deeprootgen/research/so4_controlled.py', 'deeprootgen/research/construction_step_replay.py')}
    assert results['old'] == results['current']
    destination = Path(os.environ.get('DRG_TERTIARY_RANK_PARITY_DIR', str(tmp_path)))
    destination.mkdir(parents=True, exist_ok=True)
    receipt = dict(source_hashes=hashes, output_sha256={name: controlled.digest(result) for name, result in results.items()})
    (destination / 'parity.json').write_text(json.dumps(receipt, indent=2) + '\n')


@pytest.mark.parametrize('inactive', [None, 0.])
def test_empty_family_active_receipts_cannot_be_resealed_as_inactive(inactive):
    p = parameters(1., research_parent2_branch_zone_cm=dict(basal_cm=6., apical_cm=5., spacing_cm=2.))
    saved = controlled.construct_skeleton(p, 42)
    assert not any(o['order'] == 3 for o in saved.payload['organs'])
    assert any('tertiary_length_rank_family' in o for o in saved.payload['organs'])
    saved.payload['parameters'][FIELD] = inactive
    with pytest.raises(ValueError, match='Inactive tertiary rank.*family'):
        canonical.validate_construction_metadata(resign(saved))
