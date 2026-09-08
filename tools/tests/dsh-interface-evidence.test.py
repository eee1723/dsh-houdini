"""Actual instance surfaces, sparse-vertex counterexample and intentional gaps."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h

root = h.tab_create('/obj', 'geo', '__surface_evidence')
try:
    h.build_module(root, [
        {'name':'receiver','type':'box','parms':{'sizex':4,'sizey':1,'sizez':4}},
        {'name':'receiver_tag','type':'attribwrangle','inputs':['receiver'],
         'parms':{'class':'primitive','snippet':'setprimgroup(0,"receiver_surface",@primnum,1);'}},
        {'name':'unit','type':'box','parms':{'sizex':.2,'sizey':.2,'sizez':.2,'ty':.6}},
        {'name':'unit_tag','type':'attribwrangle','inputs':['unit'],
         'parms':{'class':'point','snippet':'if(@P.y<0.51) setpointgroup(0,"mating_points",@ptnum,1);'}},
        {'name':'instance','type':'xform','inputs':['unit_tag']},
        {'name':'assembled','type':'merge','inputs':['receiver_tag','instance']},
    ], output='assembled')
    out = root.node('assembled')
    relation = {'id':'mating','source_group':'mating_points','target_group':'receiver_surface',
                'expected_points':4,'max_distance':.001}
    touching = h.geo_check_interfaces(out, [relation])
    assert touching['ok'] and touching['results'][0]['max_distance'] < 1e-6
    # Sparse vertices remain far apart even when the actual surfaces touch.
    a=root.node('unit').geometry();b=root.node('receiver').geometry()
    vertex_min=min(x.position().distanceTo(y.position()) for x in a.points() for y in b.points())
    assert vertex_min>2.5,vertex_min
    # The source prototype still touches; only the transformed final instance detaches.
    h.set_parm(root.node('instance'),'ty',.125)
    detached=h.geo_check_interfaces(out,[relation])
    assert detached['status']=='fail' and detached['results'][0]['failure_count']==4,detached
    assert abs(detached['results'][0]['max_distance']-.125)<1e-6
    assert abs(root.node('unit').geometry().boundingBox().minvec()[1]-.5)<1e-6
    # An explicitly allowed assembly gap is a positive counterexample: do not
    # force a weld, move the model, or pretend that proximity proves solidity.
    before=out.geometry().data()
    allowed=h.geo_check_interfaces(out,[{**relation,'max_distance':.126}])
    assert allowed['ok'] and allowed['semantic_status']=='unverified',allowed
    assert out.geometry().data()==before
    # Intersecting boxes can ALSO have positive vertex-to-vertex distances.
    h.set_parm(root.node('instance'),'ty',-.15)
    ag=root.node('instance').geometry();ab=ag.boundingBox();bb=b.boundingBox()
    overlaps=[min(ab.maxvec()[i],bb.maxvec()[i])-max(ab.minvec()[i],bb.minvec()[i]) for i in range(3)]
    assert min(overlaps)>0,overlaps  # exact for these axis-aligned solid Boxes
    assert min(x.position().distanceTo(y.position()) for x in ag.points() for y in b.points())>2.5
finally:
    root.destroy()
print('surface evidence: contact/detached instance/intentional gap/vertex-distance counterexample passed on '+hou.applicationVersionString())
