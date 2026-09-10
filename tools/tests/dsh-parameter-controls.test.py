"""UI-first modeling and existing-scene controls, with separate binding guarantees."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as b
import dsh_parameter_ui as ui
import dsh_hda_interfaces as state_api


def run(code, owner='controls-author', query=False):
    r=b.run_code(code,owner_session=owner,owner_call='controls-test',read_only=query)
    assert r['ok'],r.get('error')
    return r


def rejected(code, text, owner='controls-author'):
    r=b.run_code(code,owner_session=owner,owner_call='negative')
    assert not r['ok'] and text in r['error'],r
    return r


layout=[{'component':'section','name':'dimensions','label':'Dimensions','parms':[
    {'type':'float','name':'width','label':'Width','default':2.,'min':0.1,'max':10},
    {'component':'remap','name':'shape','label':'Shape Profile'}]}]
controller=run("__result__=tab_create('/obj','null',name='control_panel').path()")['result']
n=hou.node(controller)
before=n.parmTemplateGroup().asDialogScript()
preview=run(f'__result__=create_spare_parms({controller!r},layout={layout!r},dry_run=True)')
assert preview['transaction']['status']=='no_scene_change'
assert n.parmTemplateGroup().asDialogScript()==before
run(f'create_spare_parms({controller!r},layout={layout!r})')
info=run(f'__result__=parameter_ui({controller!r},analyze_ui=True)',query=True)['result']
assert info['definition'] is None and info['ui_analysis']['entries']>3
assert n.type().name()=='null'  # no HDA necessary

# UI first, then model and explicit binding.
box=run("g=tab_create('/obj','geo',name='model'); __result__=tab_create(g,'box',name='shape').path()")['result']
mapping=[{'source':'width','target':box+'/sizex','scale':1,'offset':0}]
plan=run(f'__result__=bind_controls({controller!r},{mapping!r},dry_run=True)')
assert plan['transaction']['status']=='no_scene_change'
assert hou.parm(box+'/sizex').keyframes()==()
revision=plan['result']['plan_sha256']
applied=run(f'__result__=bind_controls({controller!r},{mapping!r},expected_plan={revision!r})')['result']
assert applied['bindings'][0]['actual_value']==2
expression=hou.parm(box+'/sizex').expression()
run(f"set_parms({controller!r},{{'width':4}}); cook_node({box!r})")
assert abs(hou.node(box).geometry().boundingBox().sizevec()[0]-4)<1e-6

# Adding unrelated UI leaves bindings, animation, locked values and ramp intact.
k=hou.Keyframe();k.setFrame(1);k.setValue(4);n.parm('width').setKeyframe(k)
keys=n.parm('width').keyframes();n.parm('tx').lock(True)
ramp=n.parm('shape_ramp').evalAsRamp()
extra=[{'component':'row','parms':[{'type':'toggle','name':'show_debug','label':'Debug','default':False},
                                 {'type':'int','name':'samples','label':'Samples','default':8}]}]
run(f'create_spare_parms({controller!r},layout={extra!r})')
assert hou.parm(box+'/sizex').expression()==expression

denied=b.run_code(f'bind_controls({controller!r},{mapping!r},dry_run=True)',
                  owner_session='controls-author',read_only=True)
assert not denied['ok'] and 'read-only' in denied['error']
rejected(f'bind_controls({controller!r},[{{"source":"height","target":{box+"/sizez"!r}}}],dry_run=True)',
         'does not exist')

# Two adjacent tabs share a native folder-set identity but remain separate UI pages.
tabs=[{'type':'folder','name':'page_one','label':'Page One','folder_type':'tabs','parms':[
        {'type':'float','name':'tab_gain','default':1}]},
      {'type':'folder','name':'page_two','label':'Page Two','folder_type':'tabs','parms':[
        {'type':'float','name':'tab_bias','default':0}]}]
run(f'create_spare_parms({controller!r},layout={tabs!r})')
assert n.parm('tab_gain') is not None and n.parm('tab_bias') is not None
rejected(f"create_spare_parms({controller!r},layout=[{{'type':'float','name':'tx'}}])",'existing channel')
assert n.parm('width').keyframes()==keys and n.parm('tx').isLocked()
assert n.parm('shape_ramp').evalAsRamp().keys()==ramp.keys()

# Plan becomes stale if source or target state changes.
plan=run(f'__result__=bind_controls({controller!r},{mapping!r},dry_run=True)')['result']
run(f"set_parms({controller!r},{{'width':5}})")
rejected(f'bind_controls({controller!r},{mapping!r},expected_plan={plan["plan_sha256"]!r})','stale')
assert hou.parm(box+'/sizex').expression()==expression

# Scene first: read related scene input and derive a matching controller default.
run(f"set_parms({box!r},{{'sizey':3}})")
height=hou.parm(box+'/sizey').eval()
run(f"create_spare_parms({controller!r},layout=[{{'type':'float','name':'height','default':{height!r}}}])")
map2=[{'source':'height','target':box+'/sizey','scale':2,'offset':1}]
plan=run(f'__result__=bind_controls({controller!r},{map2!r},dry_run=True)')['result']
run(f'bind_controls({controller!r},{map2!r},expected_plan={plan["plan_sha256"]!r})')
assert hou.parm(box+'/sizey').eval()==7

# Existing drivers, loops, ambiguous targets and foreign ownership are rejected.
rejected(f'bind_controls({controller!r},{map2!r},expected_plan="outdated")','stale')
map3=[{'source':'height','target':box+'/sizez'}]
hou.parm(box+'/sizez').setExpression('2+$F',hou.exprLanguage.Hscript)
rejected(f'bind_controls({controller!r},{map3!r},dry_run=True)','existing driver')
rejected(f'bind_controls({controller!r},[{{"source":"width","target":{controller+"/width"!r}}}],dry_run=True)','self-binding')
rejected(f'bind_controls({controller!r},{mapping+mapping!r},dry_run=True)','duplicate')
rejected(f'bind_controls({controller!r},{mapping!r},dry_run=True)', 'ownership guard', owner='other')
hou.parm(box+'/sizez').deleteAllKeyframes();hou.parm(box+'/sizez').set(3)

# Failure after the first write restores all target expressions and values.
maps=[{'source':'height','target':box+'/sizey','scale':3,'offset':1},
      {'source':'width','target':box+'/sizez'}]
plan=run(f'__result__=bind_controls({controller!r},{maps!r},dry_run=True,replace_existing=True)')['result']
original=hou.Parm.setExpression
def fail_second(p,*args,**kwargs):
    if p.path()==box+'/sizez':raise RuntimeError('injected binding write failure')
    return original(p,*args,**kwargs)
before_y=hou.parm(box+'/sizey').keyframes()
try:
    hou.Parm.setExpression=fail_second
    r=rejected(f'bind_controls({controller!r},{maps!r},expected_plan={plan["plan_sha256"]!r},replace_existing=True)','injected binding')
finally:
    hou.Parm.setExpression=original
assert hou.parm(box+'/sizey').keyframes()==before_y
assert hou.parm(box+'/sizez').eval()==3 and not hou.parm(box+'/sizez').keyframes()

# Spare application rollback is independent of binding rollback.
saved_restore=state_api._restore
calls=[]
def fail_once(states):
    errors=saved_restore(states);calls.append(1)
    return errors+(['injected spare restore failure'] if len(calls)==1 else [])
before=n.parmTemplateGroup().asDialogScript(full_info=True)
try:
    state_api._restore=fail_once
    rejected(f"create_spare_parms({controller!r},layout=[{{'type':'float','name':'temporary_control'}}])",'injected spare')
finally:
    state_api._restore=saved_restore
assert n.parmTemplateGroup().asDialogScript(full_info=True)==before
assert n.parm('temporary_control') is None and n.parm('tx').isLocked()
assert hou.parm(box+'/sizex').expression()==expression

hou.node('/obj/model').destroy();n.destroy()
print('shared parameter UI, UI-first/scene-first binding, plan/ownership/driver/rollback passed on '+hou.applicationVersionString())
