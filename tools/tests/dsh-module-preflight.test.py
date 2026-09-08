"""Static module errors carry zero writes; preceding or subsequent edits do not."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as b

root=h.tab_create('/obj','geo','__module_preflight')
source=h.tab_create(root,'box','source')
try:
    cases=[
        ([{'name':'hidden','type':'partition'}],'hidden','hidden/deprecated'),
        ([{'name':'unknown','type':'nonexistent_test_type'}],'unknown','未知节点类型'),
        ([{'name':'bad','type':'box','parms':{'bad_parm':1}}],'bad','unknown parameter'),
        ([{'name':'bad','type':'tube','parms':{'rad':1.2}}],'bad','tuple needs 2'),
        ([{'name':'bad','type':'sphere','parms':{'rad':1.2}}],'bad','tuple needs 3'),
        ([{'name':'bad','type':'sphere','parms':{'rad':{'expression':'1'}}}],'bad','tuple needs 3'),
        ([{'name':'bad','type':'xform','inputs':['missing']}],'bad','earlier spec'),
        ([{'name':'valid','type':'box'}],'missing','newly created'),
        ([{'name':'source','type':'box'}],'source','exists'),
    ]
    for specs,output,message in cases:
        before={n.sessionId() for n in root.children()}
        dry=b.run_code(f'build_module({root.path()!r},{specs!r},output={output!r},dry_run=True)')
        assert not dry['ok'] and message in dry['error'],dry
        assert before=={n.sessionId() for n in root.children()}
        env=b.run_code(f'build_module({root.path()!r},{specs!r},output={output!r})')
        assert not env['ok'] and message in env['error'],env
        assert env['transaction']['status']=='no_scene_change',env
        evidence=env['evidence'][0]
        assert evidence['phase']=='static_preflight' and evidence['scene_writes']==0,env
        assert before=={n.sessionId() for n in root.children()}
    # Valid tuple literals and component expressions retain the existing API.
    for parms in ({'rad':[1,2,3]}, {'radx':{'expression':'0+1','language':'hscript'}}):
        specs=[{'name':'valid_shape','type':'sphere','parms':parms}]
        assert h.build_module(root,specs,output='valid_shape',dry_run=True)['valid']
        h.build_module(root,specs,output='valid_shape')
        assert len(root.node('valid_shape').geometry().prims())>0
        h.delete_node(root.node('valid_shape'))
    # Zero-write information concerns this module, never preceding mutations.
    env=b.run_code(f'set_parm({source.path()!r},"sizex",3)\n'
                   f'build_module({root.path()!r},[{{"name":"hidden","type":"partition"}}],output="hidden")')
    assert not env['ok'] and env['transaction']['status']=='rolled_back',env
    assert source.evalParm('sizex')==1
    # A caught static failure followed by a mutation still fails the whole exec.
    env=b.run_code(f'try:\n build_module({root.path()!r},[{{"name":"hidden","type":"partition"}}],output="hidden")\n'
                   f'except ValueError:\n pass\nset_parm({source.path()!r},"sizex",4)')
    assert not env['ok'] and env['transaction']['status']=='no_scene_change',env
    assert env['verbs'][-1]['summary']['dispatched'] is False,env
    assert source.evalParm('sizex')==1
    # Cook/VEX failure happens AFTER writes and may never acquire zero-write metadata.
    env=b.run_code(f'build_module({root.path()!r},[{{"name":"made","type":"box"}},'
                   '{"name":"bad_vex","type":"attribwrangle","inputs":["made"],'
                   '"parms":{"snippet":"nonexistent_function_probe();"}}],output="bad_vex")')
    assert not env['ok'] and env['transaction']['status']!='no_scene_change',env
    assert all(e.get('scene_writes')!=0 for e in env.get('evidence',[])),env
    assert root.node('made') is None and root.node('bad_vex') is None
finally:
    root.destroy()
print('module preflight zero-write/previous mutation/caught failure/post-write recovery passed on '+hou.applicationVersionString())
