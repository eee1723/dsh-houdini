"""Independent exec checkpoints survive later modules/discovery/integration failures."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as b

with h._execution_owner('boundary-owner','setup'):
    root=h.tab_create('/obj','geo','__module_boundaries')
try:
    def run(code, **options):
        return b.run_code(code,owner_session='boundary-owner',**options)
    def module(name):
        return f'build_module({root.path()!r},[{{"name":{name!r},"type":"box"}}],output={name!r})'
    first=run(module('module_a'))
    assert first['ok'] and first['transaction']['status']=='committed',first
    original=root.node('module_a')
    identity=original.sessionId()
    points=len(original.geometry().points())
    bad_query=run(f'list_parms({original.path()!r},filter="size")',read_only=True)
    assert not bad_query['ok'] and bad_query['transaction']['status']=='no_scene_change',bad_query
    assert bad_query['evidence'][0]['phase']=='argument_binding' and 'signature' in bad_query['evidence'][0]
    assert root.node('module_a').sessionId()==identity
    bad_module=f'build_module({root.path()!r},[{{"name":"bad","type":"attribwrangle","inputs":["module_a"],"parms":{{"snippet":"unknown_boundary_probe();"}}}}],output="bad")'
    failed=run(module('module_b')+'\n'+bad_module)
    assert not failed['ok'] and failed['transaction']['status']=='rolled_back',failed
    assert root.node('module_b') is None and root.node('bad') is None
    assert root.node('module_a').sessionId()==identity and len(original.geometry().points())==points
    # No heuristic partial commit for a supposedly harmless tail query.
    failed=run(module('module_c')+f'\nlist_parms({original.path()!r},filter="size")')
    assert not failed['ok'] and failed['transaction']['status']=='rolled_back',failed
    assert root.node('module_c') is None and root.node('module_a').sessionId()==identity
    assert run(module('module_b'))['ok']
    failed=run(f'build_module({root.path()!r},[{{"name":"join","type":"merge","inputs":["module_a","missing"]}}],output="join")')
    assert not failed['ok'] and root.node('join') is None
    assert root.node('module_a') is not None and root.node('module_b') is not None
    joined=run(f'build_module({root.path()!r},[{{"name":"join","type":"merge","inputs":["module_a","module_b"]}}],output="join")')
    assert joined['ok'] and len(root.node('join').geometry().prims())==12,joined
    # Binding errors are detected before dispatch; implementation TypeErrors
    # retain their actual traceback and are never labelled zero-write binding.
    for name, call in [('set_parms',f'set_parms({original.path()!r},{{"sizex":4}},filter="wrong")'),
                       ('node_info','node_info(type="box",context="sop")')]:
        failed=run(call)
        assert not failed['ok'] and failed['evidence'][0]['phase']=='argument_binding',failed
        assert failed['transaction']['status']=='no_scene_change',failed
    def internal_error(value):
        raise TypeError('inside implementation')
    ledger=[]
    try:
        b._make_tracer('set_parm',internal_error,ledger)(1)
    except TypeError:
        pass
    assert ledger[0]['error']=='inside implementation' and 'summary' not in ledger[0],ledger
    for name, mode, returned in [('tab_create','exec','Node'),('list_parms','query_or_exec','list'),('read_parms','query_or_exec','list')]:
        info=b._verb_help(name)
        assert info['call_mode']==mode and returned in info['return_type'],info
finally:
    root.destroy()
print('module checkpoint/discovery failure/integration retry/atomic rollback/signature discovery passed on '+hou.applicationVersionString())
