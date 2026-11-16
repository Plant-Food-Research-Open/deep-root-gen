"""Invented primary polarity controls; no observations or empirical trials."""

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from deeprootgen.model import RootSystemSimulation
from deeprootgen.research import so4_controlled as controlled
from deeprootgen.research import construction_step_replay as canonical
from deeprootgen.utils.tropism import reverse_primary_yaw, sample_primary_yaw
from tests.test_primary_yaw_initialization import parameters, initial, assert_geometry
from tests.test_order_specific_sigma import NONE_PARITY_SCRIPT
from tests.test_parent2_branch_zone import parameters as zone_parameters, ZONE
from tests.test_construction_step_replay import parameters as grid_parameters

FIELD = "research_primary_yaw_reverse_probability"
YAW = dict(research_primary_yaw_mean_deg=35., research_primary_yaw_kappa=4.)


def test_independent_keyed_decisions_axial_invariance_and_no_original_yaw_changes():
    decisions = []
    for oid in range(1, 21):
        yaw = sample_primary_yaw(35., 4., 42, oid)
        target, receipt = reverse_primary_yaw(yaw, .5, 42, oid)
        assert (target, receipt) == reverse_primary_yaw(yaw, .5, 42, oid)
        assert yaw == sample_primary_yaw(35., 4., 42, oid)
        assert np.exp(2j * target) == pytest.approx(np.exp(2j * yaw), abs=1e-14)
        assert target - yaw == pytest.approx(math.pi * receipt['reversed'], abs=1e-15)
        assert reverse_primary_yaw(yaw, 1., 42, oid)[0] == yaw + math.pi
        for inactive in (None, 0., -0.):
            assert reverse_primary_yaw(yaw, inactive, None, None) == (yaw, None)
        assert receipt['uniform'] != reverse_primary_yaw(yaw, .5, 43, oid)[1]['uniform']
        assert receipt['uniform'] == reverse_primary_yaw(yaw, .8, 42, oid)[1]['uniform']
        decisions.append(receipt['reversed'])
    assert any(decisions) and not all(decisions)


@pytest.mark.parametrize('q', [1., .5])
def test_actual_whole_subtree_rotation_preserves_topology_dimensions_z_rng(q):
    baseline = initial(parameters(**YAW))
    changed = initial(parameters(**YAW, **{FIELD: q}))
    a, ae = baseline.G.as_df()
    b, be = changed.G.as_df()
    pd.testing.assert_frame_equal(ae, be, check_exact=True)
    pd.testing.assert_frame_equal(a.drop(columns=['x', 'y']), b.drop(columns=['x', 'y']), check_exact=True)
    assert baseline.rng.bit_generator.state == changed.rng.bit_generator.state
    old, new = a.set_index('node_id'), b.set_index('node_id')
    origin = old.loc[0, ['x', 'y']].to_numpy(float)
    for primary, receipt in zip(changed.organs[1], changed.primary_yaw_diagnostics):
        flip = receipt['polarity_reversal']['reversed']
        subtree = [primary]
        while subtree:
            organ = subtree.pop()
            for node in organ.segments:
                nid = node.node_data.node_id
                expected = origin + (-1 if flip else 1) * (old.loc[nid, ['x', 'y']].to_numpy(float) - origin)
                np.testing.assert_allclose(new.loc[nid, ['x', 'y']].to_numpy(float), expected, rtol=0, atol=1e-10)
            subtree.extend(organ.child_organs)
    assert_geometry(b, be)
    again = initial(parameters(**YAW, **{FIELD: q}))
    pd.testing.assert_frame_equal(b, again.G.as_df()[0], check_exact=True)


@pytest.mark.parametrize('q', [True, np.bool_(False), '0.5', -.1, 1.1, np.nan, np.inf, [0.5], 10**400, -(10**400)])
def test_malformed_probability_rejected_by_schema_helper_and_bypassed_model(q):
    with pytest.raises(ValueError):
        parameters(**YAW, **{FIELD: q})
    with pytest.raises(ValueError):
        reverse_primary_yaw(.3, q, 42, 1)
    sim = RootSystemSimulation(random_seed=42)
    p = parameters(**YAW).model_copy(update={FIELD: q})
    before = sim.G.as_df()
    state = copy.deepcopy(sim.rng.bit_generator.state)
    with pytest.raises(ValueError):
        sim.run(p)
    for a, b in zip(before, sim.G.as_df()):
        pd.testing.assert_frame_equal(a, b, check_exact=True)
    assert state == sim.rng.bit_generator.state


@pytest.mark.parametrize('updates', [{}, {'random_seed': None}, {'random_seed': True}, {'random_seed': '42'},
                                     {'random_seed': -1}, {'research_primary_yaw_kappa': None}])
def test_active_needs_explicit_yaw_and_seed(updates):
    values = {**YAW, FIELD: .5, **updates}
    if not updates:
        values = {FIELD: .5}
    with pytest.raises(ValueError):
        parameters(**values)


def test_bypassed_missing_yaw_and_mismatched_seed_fail_before_mutation():
    for updates in ({'random_seed': 43}, {'research_primary_yaw_kappa': None},
                    {'research_primary_yaw_mean_deg': np.nan}, {'random_seed': True}):
        p = parameters(**YAW, **{FIELD: .5}).model_copy(update=updates)
        sim = RootSystemSimulation(random_seed=42)
        before = sim.G.as_df()
        with pytest.raises(ValueError):
            sim.init_organs(p)
        for a, b in zip(before, sim.G.as_df()):
            pd.testing.assert_frame_equal(a, b, check_exact=True)
    p = parameters(**YAW, **{FIELD: .5}).model_dump()
    p['random_seed'] = 43
    with pytest.raises(ValueError, match='matching explicit seeds'):
        controlled.construct_skeleton(p, 42)


@pytest.mark.parametrize('mode', ['legacy', 'fichtl2024'])
def test_native_routes_active_control(mode):
    p = grid_parameters(active=False, **YAW, **{FIELD: 1.})
    if mode == 'legacy':
        # Origin is Fichtl-only; the reversal itself supports both native modes.
        p = p.model_copy(update=dict(tropism_mode='legacy', research_base_origin_x_cm=None,
                                     research_base_origin_y_cm=None, research_base_depth_cm=None))
    sim = RootSystemSimulation(random_seed=42)
    sim.run(p)
    assert all(d['polarity_reversal']['reversed'] for d in sim.primary_yaw_diagnostics)
    assert all(not getattr(o, 'validation_reorientations', 0) and not o.invalid_root for o in sim.organs[1])
    assert_geometry(*sim.G.as_df())


def test_both_replay_guards_and_combined_canonical_zone_sigma():
    p = zone_parameters(ZONE).model_copy(update={**YAW, FIELD: .5, 'research_fichtl_sigma_by_order': {2: .04, 3: .3}})
    saved = controlled.construct_skeleton(p, 42)
    result = canonical.replay_construction_steps(saved, 'D', p.model_dump(), 'minimum_angle_projection')
    controlled.validate_geometry(result['nodes'], result['edges'], 20.)
    assert result['diagnostics']['invariant_hashes'] == controlled.invariant_hashes(pd.DataFrame(saved.payload['nodes']))
    with pytest.raises(ValueError, match='reversal.*INITIAL'):
        canonical.replay_construction_steps(saved, 'D', {**p.model_dump(), FIELD: .7}, 'minimum_angle_projection')
    p = grid_parameters(active=False, **YAW, **{FIELD: .5})
    saved = controlled.construct_skeleton(p, 42)
    for arm in 'ABCD':
        controlled.replay_arm(saved, arm, p.model_dump(), 'minimum_angle_projection')
        with pytest.raises(ValueError, match='reversal.*INITIAL'):
            controlled.replay_arm(saved, arm, {**p.model_dump(), FIELD: None}, 'minimum_angle_projection')
    for active in (False, True):
        p = grid_parameters(active=active)
        saved = controlled.construct_skeleton(p, 42)
        fn = canonical.replay_construction_steps if active else controlled.replay_arm
        fn(saved, 'D', {**p.model_dump(), FIELD: 0.}, 'minimum_angle_projection')


def test_none_zero_prechange_subprocess_exact_bytes_rng(tmp_path):
    current = Path(__file__).parents[1]
    old = Path('/tmp/drg-primary-yaw-reversal-public/preimplementation/source')
    assert (old / 'deeprootgen/model/root.py').is_file()
    script = NONE_PARITY_SCRIPT.replace('research_fichtl_sigma_by_order', FIELD).replace(
        "('explicit_none',{'" + FIELD + "':None})", "('explicit_none',{'" + FIELD + "':None}),('explicit_zero',{'" + FIELD + "':0.})")
    configs = dict(native_legacy=parameters(**YAW).model_dump(),
                   native_fichtl=grid_parameters(active=False, **YAW).model_dump(),
                   graph=grid_parameters(active=False, **YAW).model_dump(),
                   canonical=zone_parameters(ZONE).model_copy(update=YAW).model_dump())
    # Preserve active sigma behavior too; native legacy cannot use sigma maps.
    for name, values in configs.items():
        values.pop(FIELD, None)
        if name != 'native_legacy':
            values['research_fichtl_sigma_by_order'] = {'2': .04, '3': .3}
        if name == 'graph':
            values['research_fichtl_sigma_by_order'] = None  # Includes legacy continuation arms A/B.
    overlay = next(p for p in sys.path if p.endswith('/locked-overlay'))
    results, hashes = {}, {}
    for name, source in [('old', old), ('current', current)]:
        run = subprocess.run([sys.executable, '-c', script], input=json.dumps(configs), capture_output=True,
                             text=True, check=True, timeout=90, cwd=source,
                             env={**os.environ, 'PYTHONPATH': overlay + os.pathsep + str(source), 'PYTHONDONTWRITEBYTECODE': '1'})
        result = json.loads(run.stdout)
        assert Path(result['loaded_root']).resolve() == (source / 'deeprootgen/model/root.py').resolve()
        assert result['outputs']['omitted'] == result['outputs']['explicit_none'] == result['outputs']['explicit_zero']
        results[name] = result['outputs']
        hashes[name] = {f: hashlib.sha256((source / f).read_bytes()).hexdigest() for f in (
            'deeprootgen/model/root.py', 'deeprootgen/utils/tropism.py',
            'deeprootgen/data_model/simulation_data_models.py', 'deeprootgen/research/so4_controlled.py',
            'deeprootgen/research/construction_step_replay.py')}
    assert results['old'] == results['current']
    destination = Path(os.environ.get('DRG_YAW_REVERSAL_PARITY_DIR', str(tmp_path)))
    destination.mkdir(parents=True, exist_ok=True)
    receipt = dict(source_hashes=hashes, output_sha256={k: controlled.digest(v) for k, v in results.items()},
                   exact_geometry_rng_initial_diagnostics=True)
    (destination / 'parity.json').write_text(json.dumps(receipt, indent=2) + '\n')
