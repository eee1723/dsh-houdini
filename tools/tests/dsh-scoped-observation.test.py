"""Large final-output selections retain real groups and full restoration."""
import sys, json, os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_parameter_values as parameters

def run(code,ok=True):
    r=b.run_code(code,owner_session='scoped-fixture',owner_call='scoped-test')
    if r['ok'] is not ok:
        print(json.dumps(r.get('verbs'),default=str)[:14000],flush=True)
    assert r['ok'] is ok,r.get('error')
    return r

run('''g=tab_create('/obj','geo','scoped')
create_spare_parms(g,spec=[{'type':'float','name':'width','default':1.0},{'type':'float','name':'offset','default':100.0},{'type':'int','name':'resolution','default':1100}])
box=tab_create(g,'box','shape',parms={'sizex':'ch("../width")'})
part=tab_create(g,'attribwrangle','part',inputs=[box],parms={'class':1,'snippet':'@group_target=1;'})
grid=tab_create(g,'grid','background',parms={'rows':'ch("../resolution")','cols':'ch("../resolution")','tx':'ch("../offset")'})
out=tab_create(g,'merge','OUT',inputs=[part,grid])
''')
p='/obj/scoped';output=p+'/OUT'
source=hou.node(output).geometry()
assert source.intrinsicValue('primitivecount')>1000000
relation=[{'id':'width','method':'physical_extent','target_group':'target','axis':0,'expected_mm':1000,'tolerance_mm':.1}]
r=run(f'__result__=geo_check_interfaces({output!r},{relation!r})')['result']
assert r['ok'] and r['geometry_scope']['kind']=='selected_final_primitives',r
assert r['geometry_scope']['selected']['primitives']==6,r
bad=[dict(relation[0],expected_mm=2000)]
r=run(f'__result__=geo_check_interfaces({output!r},{bad!r})')['result']
assert not r['ok'] and r['status']=='fail',r
test=[{'id':'wider','values':{'width':2.},'expectations':[{'metric':'bounds_size','axis':0,'group':'target','delta':[.999,1.001]}]}]
r_envelope=run(f'__result__=test_controls({p!r},{output!r},{test!r})')
r=r_envelope['result']
assert r['ok'] and r['restored'] and r['results'][0]['geometry_restore']['full_output']['matches'],r
assert r_envelope['evidence'][0]['geometry_scope']==r['geometry_scope']
if os.environ.get('DSH_HDA_PRESENTATION_FIXTURE'):
    Path(os.environ['DSH_HDA_PRESENTATION_FIXTURE']).write_text(json.dumps(r_envelope),encoding='utf-8')
assert hou.node(p).evalParm('width')==1.
outside=[{'id':'outside-only','values':{'offset':101.},'expectations':[{'metric':'bounds_size','axis':0,'group':'target','delta':[.999,1.001]}]}]
outside_result=run(f'__result__=test_controls({p!r},{output!r},{outside!r})')['result']
assert not outside_result['ok'] and outside_result['restored']
assert outside_result['results'][0]['geometry_changed'] is None,'unchanged selected data cannot prove an unchanged entire output'
crossing=[{'id':'smaller-output','values':{'width':2.,'resolution':8},'expectations':test[0]['expectations']}]
crossed=run(f'__result__=test_controls({p!r},{output!r},{crossing!r})')['result']
assert crossed['ok'] and crossed['restored'] and crossed['results'][0]['geometry_changed'] is None,'different collection scopes cannot compare fingerprints'
unscoped=[{'id':'wider','values':{'width':2.},'expectations':[{'metric':'bounds_size','axis':0,'delta':[.999,1.001]}]}]
assert 'budget' in run(f'test_controls({p!r},{output!r},{unscoped!r})',False)['error']
assert hou.node(p).evalParm('width')==1.
restore=parameters._restore_parameters
def drift_outside_selection(states):
    errors=restore(states)
    hou.node(p+'/background').parm('tx').set(101.)
    return errors
parameters._restore_parameters=drift_outside_selection
try:
    r=run(f'test_controls({p!r},{output!r},{test!r})',False)
    assert 'restoration failed' in r['error'],r
    assert 'full_output' in json.dumps(r) and 'matches' in json.dumps(r),r
finally:parameters._restore_parameters=restore
print('PASS large final geometry: exact group, wrong dimension, controls, unscoped refusal and unselected drift '+hou.applicationVersionString())
