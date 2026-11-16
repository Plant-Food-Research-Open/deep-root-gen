"""Invented cohort fixtures only; no field data."""
import copy

import numpy as np
import pandas as pd
import pytest

from deeprootgen.research.cohort_root_generator import (
    CohortRootGenerator, bounded_draw, equivalent_diameter, integrate_curve,
    material_cuts, taper_diameter,
)


def config():
    def fixed(x):
        return dict(mean=x, sd=0, min=x, max=x)
    return dict(step_cm=3., dry_density_g_cm3=.3, fine_cutoff_mm=2.5, max_organs=100,
        crown_mass_g=0., crown_depth_cm=[5.,8.], crown_radius_cm=1.,
        later_maturity=[.3,.6], maturity_length_power=.5, maturity_diameter_power=.5,
        child_diameter_fraction_max=.8, inclination_mean_deg=30., inclination_sd_deg=10.,
        inclination_bounds_deg=[0.,90.], insertion_mean_deg=40., insertion_sd_deg=5.,
        orders={str(o):dict(length_cm=fixed(10.),base_diameter_cm=fixed(.8/o),
            tip_diameter_cm=fixed(.05),first_branch_cm=fixed(4.),
            branch_probability=1.,daughter_probabilities=[1.],
            curvature_sd_rad_cm=.005, correlation_cm=10., downward_drift_per_cm=0.)
            for o in range(1,6)})


def test_material_integral_and_cutoff_are_subdivision_invariant():
    vols=[]
    fines=[]
    for stations in ([0.,10.], [0.,1.,3.,10.]):
        cuts=material_cuts(10., stations, [2.,4.,8.], .8,.1,.25)
        d=taper_diameter(cuts,10.,.8,.1)
        e=equivalent_diameter(d[:-1],d[1:])
        vols.append(np.pi/4*np.dot(np.diff(cuts),e**2))
        fines.append(np.diff(cuts)[e<=.25].sum())
    np.testing.assert_allclose(vols, np.pi*10*(.8**2+.8*.1+.1**2)/12,rtol=1e-12)
    np.testing.assert_allclose(fines,10*(.25-.1)/(.8-.1),rtol=1e-12)


def test_reproducible_connected_projection_and_dimensions():
    g=CohortRootGenerator(config())
    a,b=g.generate(9,2,1),g.generate(9,2,1)
    pd.testing.assert_frame_equal(a.nodes,b.nodes)
    ids=set(a.nodes.node_id)
    assert len(a.edges)==len(ids)-1
    assert all(p<c for p,c in a.edges.to_numpy())
    assert set(a.organs.order)==set(range(1,6))
    assert len(a.organs.query('order==1'))==3
    assert set(a.organs.query('order==1').cohort)=={'A','B'}
    assert (a.nodes.z<=0).all()
    assert (a.organs.dropna(subset=['first_branch_cm']).first_branch_cm==4.).all()
    assert a.observation_nodes.query('order==0').shape[0]==3
    np.testing.assert_allclose(a.organs.dry_mass_g.sum(),a.diagnostics['root_totals']['dry_mass_g'],rtol=1e-12)
    for _,organ in a.organs.iterrows():
        rows=a.nodes.loc[a.nodes.organ_id.eq(organ.organ_id)]
        np.testing.assert_allclose(rows.length.sum(),organ.length_cm,rtol=1e-12)
        for _,row in rows.iterrows():
            parent=a.nodes.loc[a.nodes.node_id.eq(row.parent_id)].iloc[0]
            np.testing.assert_allclose(np.linalg.norm(row[['x','y','z']].to_numpy(float)-parent[['x','y','z']].to_numpy(float)),row.length,rtol=1e-9,atol=0)


def test_branch_beyond_axis_is_unbranched_not_extended():
    c=config()
    c['orders']['1']['first_branch_cm']=dict(mean=20.,sd=0,min=20.,max=20.)
    a=CohortRootGenerator(c).generate(2,1,0)
    assert len(a.organs)==1
    assert a.organs.iloc[0].length_cm==10.
    assert a.diagnostics['branch_beyond_tip']==1


def test_physical_heading_unchanged_by_attachment_cuts():
    args=(10.,[0,0,-2],[1.,0,0],3.,.005,10.,0.)
    arc,xyz,_=integrate_curve(*args,np.random.default_rng(9))
    for attachments in ([],[2.,4.,8.]):
        cuts=material_cuts(10.,arc,attachments,.8,.1,.25)
        split=np.column_stack([np.interp(cuts,arc,xyz[:,k])for k in range(3)])
        np.testing.assert_allclose(np.linalg.norm(np.diff(split,axis=0),axis=1).sum(),10.,rtol=1e-12)
        np.testing.assert_allclose(split[np.searchsorted(cuts,arc)],xyz,rtol=0,atol=0)


@pytest.mark.parametrize('spec',[dict(mean=-1,sd=0,min=-2,max=1),dict(mean=1,sd=-1,min=.1,max=2),dict(mean=1,sd=1,min=2,max=3)])
def test_invalid_distribution_rejected(spec):
    with pytest.raises(ValueError):bounded_draw(spec,np.random.default_rng(1))


def test_budget_fails_instead_of_silent_truncation():
    c=config();c['max_organs']=2
    with pytest.raises(ValueError,match='budget'):CohortRootGenerator(c).generate(0,1,0)


def test_midpoint_taper_integral_and_cutoff():
    results=[]
    for stations in ([0.,10.], [0.,1.,7.,10.]):
        cuts=material_cuts(10.,stations,[2.,8.],.8,.1,.25,.75)
        d=taper_diameter(cuts,10.,.8,.1,.75)
        e=equivalent_diameter(d[:-1],d[1:])
        results.append(np.pi/4*np.dot(np.diff(cuts),e**2))
        assert 5. in cuts
        assert taper_diameter(5.,10.,.8,.1,.75)==pytest.approx(.625)
        crossing=5+5*(.625-.25)/(.625-.1)
        assert np.min(abs(cuts-crossing))<1e-12
    expected=np.pi*5/12*(.8**2+.8*.625+2*.625**2+.625*.1+.1**2)
    np.testing.assert_allclose(results,expected,rtol=1e-12)


def test_multiple_step_endpoint_and_input_immutability():
    heading=np.array([1.,0.,0.]);original=heading.copy()
    arc,points,_=integrate_curve(.9,[0,0,-1],heading,.3,0.,10.,0.,np.random.default_rng(2))
    np.testing.assert_array_equal(heading,original)
    np.testing.assert_allclose(np.diff(arc),[.3,.3,.3],rtol=1e-12)
    np.testing.assert_allclose(points[-1],[.9,0,-1],rtol=1e-12)


def test_nearly_coincident_material_cuts_fail_without_relaxed_tolerance():
    with pytest.raises(ValueError,match='material cuts'):
        material_cuts(10.,[0.,2.,10.],[np.nextafter(2.,3.)],.8,.1,.25)


def test_reflection_and_above_soil_rejection():
    arc,xyz,n=integrate_curve(10.,[0,0,-.1],[0,0,1.],1.,.01,10.,0.,np.random.default_rng(0))
    assert n>=1 and (xyz[:,2]<=0).all()
    np.testing.assert_allclose(np.linalg.norm(np.diff(xyz,axis=0),axis=1),np.diff(arc),rtol=1e-9,atol=0)
    with pytest.raises(ValueError,match='soil start'):
        integrate_curve(1.,[0,0,1.],[1.,0,0],1.,0.,10.,0.,np.random.default_rng(0))


@pytest.mark.parametrize('key,value',[('crown_mass_g',float('nan')),('crown_depth_cm',[-1,2]),('later_maturity',[.8,.2]),('crown_radius_cm',-1),('max_organs',2.5)])
def test_invalid_controls_reject_before_generation(key,value):
    c=config();c[key]=value
    with pytest.raises(ValueError):CohortRootGenerator(c)


def test_graph_complete_reproducibility_and_multiple_daughters():
    c=config();c['orders']['1']['daughter_probabilities']=[0.,1.]
    a=CohortRootGenerator(c).generate(21,2,1);b=CohortRootGenerator(c).generate(21,2,1)
    for name in ('nodes','edges','organs','observation_nodes','observation_edges'):
        pd.testing.assert_frame_equal(getattr(a,name),getattr(b,name))
    assert a.diagnostics==b.diagnostics
    assert a.edges.child_id.is_unique
    assert set(a.edges.child_id)==set(a.nodes.node_id)-{0}
    assert set(a.edges.parent_id)<=set(a.nodes.node_id)
    assert a.organs.query('order==1 and cohort=="A"').daughter_count.eq(2).all()
    other=CohortRootGenerator(c).generate(22,2,1)
    assert not a.nodes.equals(other.nodes)


def test_nonzero_sd_sampling_is_bounded():
    rng=np.random.default_rng(2)
    x=[bounded_draw(dict(mean=2.,sd=1.,min=.5,max=4.),rng)for _ in range(1000)]
    assert min(x)>=.5 and max(x)<=4 and np.std(x)>.2


def test_roundoff_option_preserves_normal_geometry_and_rejects_nonbool():
    c=config();a=CohortRootGenerator(c).generate(21,2,0)
    c['reconcile_length_metadata']=True;b=CohortRootGenerator(c).generate(21,2,0)
    pd.testing.assert_frame_equal(a.nodes,b.nodes)
    assert b.diagnostics['length_metadata_reconciliations']==[]
    c['reconcile_length_metadata']='yes'
    with pytest.raises(ValueError):CohortRootGenerator(c)


def test_reconciliation_accept_and_each_guard():
    from deeprootgen.research.cohort_root_generator import reconcile_interval_lengths
    coords=np.array([[1e5,0.,0.],[1e5+1e-4,0.,0.]])
    actual=np.linalg.norm(coords[1]-coords[0])
    stored=np.array([actual*(1+2e-9)])
    with pytest.raises(ValueError,match='disabled'):reconcile_interval_lengths(coords,stored)
    fixed,records=reconcile_interval_lengths(coords,stored,True)
    assert fixed[0]==actual and len(records)==1 and stored[0]!=actual
    with pytest.raises(ValueError,match='absolute'):
        reconcile_interval_lengths([[0,0,0],[100,0,0]],[100*(1+2e-9)],True)
    with pytest.raises(ValueError,match='relative'):
        reconcile_interval_lengths(coords,[actual*(1+1e-6)],True)
    with pytest.raises(ValueError,match='resolution'):
        reconcile_interval_lengths([[1e5,0,0],[1e5+1e-12,0,0]],[1e-12],True)


def test_missing_controls_and_impossible_inclination_rejected():
    c=config();del c['crown_mass_g']
    with pytest.raises(ValueError,match='Missing'):CohortRootGenerator(c)
    c=config();c['inclination_bounds_deg']=[30.,30.]
    with pytest.raises(ValueError,match='Inclination'):CohortRootGenerator(c)
