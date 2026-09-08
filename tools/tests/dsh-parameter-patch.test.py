"""Literal source patches: all anchors before writes, exact state and real cook."""
import hashlib
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as b

def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def patch(source, old, new, count=1):
    return {'expected_sha256':sha(source), 'patch':[{'old':old, 'new':new, 'count':count}]}

def rejects(fn, expected):
    try:
        fn()
    except Exception as error:
        assert expected in str(error), str(error)
    else:
        raise AssertionError('expected '+expected)

with h._execution_owner('patch-owner', 'test'):
    root = h.tab_create('/obj','geo','__parameter_patch')
    source = 'int n=2; for(int i=0;i<n;i++) addpoint(0,set(i,0,0));'
    n = h.tab_create(root,'attribwrangle','generator')
    h.set_parms(n,{'class':'detail','snippet':source})
    h.create_spare_parms(n,spec=[{'type':'string','name':'label','default':'alpha alpha'},
                               {'type':'float','name':'amplitude','default':1}])
    try:
        assert h.cook_node(n,force=True)['ok'] and len(n.geometry().points())==2
        row=next(x for x in h.read_parms(n) if x['name']=='snippet')
        assert row['source_sha256']==sha(source)
        selected=h.read_parms(n,names=['label','snippet'])
        assert [r['name'] for r in selected]==['label','snippet']
        assert selected[0]['source_sha256']==sha('alpha alpha'),'explicit default-valued field must not be omitted'
        rejects(lambda:h.read_parms(n,names=['label','missing']),'missing scalar')
        rejects(lambda:h.read_parms(n,names=['label','label']),'unique scalar')
        proposal=patch(source,'n=2','n=3')
        result=h.set_parm(n,'snippet',proposal)
        changed=source.replace('n=2','n=3')
        assert result['patch']['after_sha256']==sha(changed) and result['value_omitted']
        assert h.cook_node(n,force=True)['ok'] and len(n.geometry().points())==3
        # Reapplying a stale proposal never restores/rewrites the parameter.
        restore=h._restore_parameters
        restores=[]
        try:
            def spy(snapshots):
                restores.append(1)
                return restore(snapshots)
            h._restore_parameters=spy
            rejects(lambda:h.set_parm(n,'snippet',proposal),'stale source')
            assert not restores
        finally:
            h._restore_parameters=restore
        for bad, reason in [(patch(changed,'not found','x'),'found 0'),
                            (patch('alpha alpha','alpha','beta'),'found 2'),
                            (patch(changed,'n=3','n=3'),'different new'),
                            (patch(changed,'n=3','n=4',True),'integer count')]:
            field='label' if reason=='found 2' else 'snippet'
            rejects(lambda:h.set_parm(n,field,bad),reason)
        # A late bad patch prevents even earlier ORDINARY writes in set_parms.
        setter=h.set_parm
        writes=[]
        try:
            def write_spy(*args,**kwargs):
                writes.append(1)
                return setter(*args,**kwargs)
            h.set_parm=write_spy
            rejects(lambda:h.set_parms(n,{'amplitude':9,'snippet':patch(changed,'n=3','n=4'),
                                          'label':patch('alpha alpha','missing','x')}),'found 0')
            assert not writes and n.evalParm('amplitude')==1
            assert n.parm('snippet').unexpandedString()==changed
        finally:
            h.set_parm=setter
        # Sequential edits are validated against the proposed intermediate text.
        edits=patch(changed,'n=3','n=4')
        edits['patch'].append({'old':'n=4','new':'n=5','count':1})
        good=h.set_parms(n,{'snippet':edits,'label':patch('alpha alpha','alpha','β',2)})
        assert good['patched']==['snippet','label'] and 'int n=' not in str(good)
        assert n.evalParm('label')=='β β'
        assert h.cook_node(n,force=True)['ok'] and len(n.geometry().points())==5
        # Hashes describe RAW strings, not evaluated $HIP expansions.
        h.set_parm(n,'label','$HIP/旧文本')
        label=next(x for x in h.read_parms(n) if x['name']=='label')
        assert label['raw_value']=='$HIP/旧文本' and label['source_sha256']==sha('$HIP/旧文本')
        h.set_parm(n,'label',patch('$HIP/旧文本','旧','新'))
        assert n.parm('label').unexpandedString()=='$HIP/新文本'
        rejects(lambda:h.set_parms(n,{'label':patch('$HIP/新文本','新','旧')},strict=False),'strict=True')
        rejects(lambda:h.set_parm(n,'amplitude',patch('1','1','2')),'scalar string')
        n.parm('label').setExpression(repr('literal'),hou.exprLanguage.Python)
        keys=n.parm('label').keyframes()
        rejects(lambda:h.set_parm(n,'label',patch('literal','literal','changed')),'expression-driven')
        assert n.parm('label').keyframes()==keys
        h.set_parm(n,'label','plain')
        n.parm('label').lock(True)
        rejects(lambda:h.set_parm(n,'label',patch('plain','plain','changed')),'locked')
        n.parm('label').lock(False)
        callback=hou.StringParmTemplate('callback','Callback',1,default_value=('plain',))
        callback.setScriptCallback('raise RuntimeError("must not run")')
        callback.setScriptCallbackLanguage(hou.scriptLanguage.Python)
        n.addSpareParmTuple(callback)
        rejects(lambda:h.set_parm(n,'callback',patch('plain','plain','next')),'callback')
        # Inject a failure on the SECOND physical patch; all current values and
        # unrelated animation in the batch restore, independently of Bridge undo.
        n.parm('amplitude').setExpression('2+$F',hou.exprLanguage.Hscript)
        keys=n.parm('amplitude').keyframes()
        before=n.parm('snippet').unexpandedString()
        apply=h._apply_parameter_patch
        attempts=[]
        def fail_second(p,plan):
            attempts.append(p.name())
            if len(attempts)==2:
                raise RuntimeError('injected second write failure')
            return apply(p,plan)
        try:
            h._apply_parameter_patch=fail_second
            rejects(lambda:h.set_parms(n,{'amplitude':9,'snippet':patch(before,'n=5','n=7'),
                                          'label':patch('plain','plain','next')}),'injected second write')
        finally:
            h._apply_parameter_patch=apply
        assert n.parm('snippet').unexpandedString()==before and n.evalParm('label')=='plain'
        assert n.parm('amplitude').keyframes()==keys
        # Real exec: a valid text patch may produce invalid VEX; the explicit
        # geometry checkpoint must still fail and restore the whole batch.
        broken=patch(before,'addpoint(0,set(i,0,0))','nonexistent_patch_probe()')
        reply=b.run_code(f'set_parm({n.path()!r},"snippet",{broken!r})\n'
                         f'verify_network({root.path()!r},output={n.path()!r})',owner_session='patch-owner')
        assert not reply['ok'] and reply['transaction']['status']=='rolled_back',reply
        assert n.parm('snippet').unexpandedString()==before
        assert h.cook_node(n,force=True)['ok'] and len(n.geometry().points())==5
        for options, reason in [({'read_only':True},'read-only'),({'owner_session':'foreign'},'ownership guard')]:
            reply=b.run_code(f'set_parm({n.path()!r},"snippet",{patch(before,"n=5","n=8")!r})',**options)
            assert not reply['ok'] and reason in reply['error'],reply
        invalid=b.run_code(f'set_parms({n.path()!r},{{"snippet":{patch(before,"absent","x")!r}}})',owner_session='patch-owner')
        assert invalid['transaction']['status']=='no_scene_change',invalid
        assert invalid['evidence'][0]['phase']=='parameter_patch_preflight',invalid
        valid=b.run_code(f'__result__=set_parms({n.path()!r},{{"snippet":{patch(before,"n=5","n=6")!r}}})',owner_session='patch-owner')
        assert valid['ok'] and valid['result']['patched']==['snippet'],valid
        assert valid['evidence'][0]['patches']['snippet']['after_sha256']==sha(before.replace('n=5','n=6'))
        assert len(n.geometry().points())==6
        # Preflight is per node, while cross-node calls keep normal exec atomicity.
        other=h.tab_create(root,'attribwrangle','other_generator')
        h.set_parms(other,{'class':'detail','snippet':source})
        current=before.replace('n=5','n=6')
        first_code=f'set_parm({n.path()!r},"snippet",{patch(current,"n=6","n=7")!r})'
        second_bad=f'set_parm({other.path()!r},"snippet",{patch(source,"missing","replacement")!r})'
        joint=b.run_code(first_code+'\n'+second_bad,owner_session='patch-owner')
        assert not joint['ok'] and joint['transaction']['status']=='rolled_back',joint
        assert n.parm('snippet').unexpandedString()==current
        assert b.run_code(first_code,owner_session='patch-owner')['ok']
        assert not b.run_code(second_bad,owner_session='patch-owner')['ok']
        assert len(n.geometry().points())==7,'independent committed patch survives a later failed exec'
    finally:
        h.delete_node(root)
print('literal patch preflight/hash/count/raw source/atomic restoration/geometry/ownership passed on '+hou.applicationVersionString())
