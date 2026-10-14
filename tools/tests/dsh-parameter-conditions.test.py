"""Native H21/H22 menu storage, conditional discovery and actual COP response.

Isolated fixture only; public operations go through Bridge. No live/user HIP.
"""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import hou
import dsh_bridge as bridge

def call(code,ok=True,owner='parameter-conditions'):
    result=bridge.run_code(code,owner_session=owner,owner_call='fixture')
    assert result['ok'] is ok,result.get('error',result)
    return result

call('''
g=tab_create('/obj','geo','parameter_conditions')
c=tab_create(g,'copnet','images')
r=tab_create(c,'layer','resolution',parms={'setres':1,'resx':128,'resy':128,'f1':1})
n=tab_create(c,'fractalnoise','noise',inputs=[r],parms={'elementsize':.07,'elementscale':(.35,12),'percomp':0})
__result__={'static':node_info(c,'fractalnoise',parm_filter='element'),
            'live':[p for p in list_parms(n) if p['name'].startswith('element')],
            'baseline':cop_layer_stats(n)}
''')
root='/obj/parameter_conditions'
noise=root+'/images/noise'
discovered=call(f"__result__={{'static':node_info('{root}/images','fractalnoise',parm_filter='element'),'live':list_parms({noise!r})}}")
static={p['name']:p for p in discovered['result']['static']['parameters']}
live={p['name']:p for p in discovered['result']['live']}
assert static['elementscale']['conditionals']==live['elementscale']['conditionals']
assert 'elementsizetype' in static['elementscale']['conditionals']['HideWhen']
mode=static['elementsizetype']
assert mode['menu_kind']=='toggle_strip' and mode['menu'][0]['set_value']==1,mode
summary=discovered['verbs'][0]['summary']['setting_cards']
assert next(p for p in summary if p['name']=='elementscale')['conditionals']==static['elementscale']['conditionals']
def stats():return call(f'__result__=cop_layer_stats({noise!r})')['result']
baseline=stats()
call(f"set_parms({noise!r},{{'elementscale':(12,.35)}})")
assert stats()['sha256']==baseline['sha256'],'inactive mode must explain stored-but-ineffective scale'
call(f"set_parms({noise!r},{{'elementsizetype':1}})")
enabled=stats()
assert enabled['sha256']!=baseline['sha256'],'per-axis mode must affect actual image data'
call(f"set_parms({noise!r},{{'elementsizetype':0}})")
assert stats()['sha256']==baseline['sha256']
call(f"set_parms({noise!r},{{'elementsizetype':{mode['menu'][0]['token']!r}}})")
assert stats()['sha256']==enabled['sha256'],'token selects its declared bit, not its menu index'

# Native fixtures establish the distinction between multi-select bit fields,
# exclusive button indices and ordinary token menus without a COP-only rule.
node=hou.node(root)
group=node.parmTemplateGroup()
for name,kind,strip in [('bits',hou.menuType.StringToggle,True),('exclusive',hou.menuType.Normal,True),('ordinary',hou.menuType.Normal,False)]:
    group.append(hou.MenuParmTemplate(name,name,menu_items=('red','green','blue'),menu_labels=('R','G','B'),menu_type=kind,is_button_strip=strip))
node.setParmTemplateGroup(group)
for value in (0,1,5,7):
    call(f"set_parms({root!r},{{'bits':{value}}})")
    assert node.evalParm('bits')==value
call(f"set_parms({root!r},{{'bits':'green','exclusive':'blue','ordinary':'green'}})")
assert [node.evalParm(n) for n in ('bits','exclusive','ordinary')]==[2,2,1]
for invalid in (-1,8,True,1.5):
    call(f"set_parms({root!r},{{'bits':{invalid!r}}})",ok=False)
    assert node.evalParm('bits')==2
call(f"set_parms({root!r},{{'bits':1}})",ok=False,owner='foreign')
assert node.evalParm('bits')==2
call(f"set_parms({root!r},{{'bits':3}})\nraise RuntimeError('rollback bit field')",ok=False)
assert node.evalParm('bits')==2
print(json.dumps({'version':hou.applicationVersionString(),'conditions':static['elementscale']['conditionals'],
    'toggle_set_value':mode['menu'][0]['set_value'],'inactive_scale_unchanged':True,'enabled_scale_changed':True,
    'baseline_gradient':[baseline['statistics'][0][k] for k in ('mean_abs_gradient_u','mean_abs_gradient_v')],
    'enabled_gradient':[enabled['statistics'][0][k] for k in ('mean_abs_gradient_u','mean_abs_gradient_v')]}))
