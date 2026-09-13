"""H21/H22 isolated Bridge: named ports, native layers, relations and restoration.

Direct HOM writes only arrange failure/user-state fixtures; tested agent actions
use Bridge verbs. Never opens a user HIP or contacts live Houdini.
"""
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_cop_contracts as cop

OWNER = 'cop-contract-test'


def call(code, ok=True, read_only=False, owner=OWNER):
    result = b.run_code(code, owner_session=owner, read_only=read_only)
    assert result['ok'] is ok, result
    return result


def value(code):
    return call('__result__ = ' + code)['result']


def rejects(code, text, **kwargs):
    result = call(code, ok=False, **kwargs)
    assert text.lower() in str(result).lower(), result
    return result


setup = call("""
g = tab_create('/obj','geo',name='__cop_contracts')
c = tab_create(g,'copnet',name='images')
for name, v in [('a',.25),('b',.75),('increment',.5)]:
    n=tab_create(c,'layer',name=name)
    set_parms(n,{'setres':1,'resx':16,'resy':8,'f1':v})
uv=tab_create(c,'uvmap',name='coordinates')
connect(c.node('a'),uv,'size_ref')
n=tab_create(c,'fractalnoise',name='noise')
connect(uv,n,'size_ref',output='uv')
out=tab_create(c,'constant',name='second_output')
__result__=c.path()
""")
root = setup['result']
a, z, inc, uv, noise = [root + '/' + x for x in ('a','b','increment','coordinates','noise')]
try:
    # Two ordinary native HDAs exceeded the old 512-node freshness limit.
    call(f'''
large=tab_create('/obj/__cop_contracts','copnet',name='large')
set_parms(large,{{'setres':1,'res1':32,'res2':32}})
left=tab_create(large,'tilepattern',name='left')
right=tab_create(large,'tilepattern',name='right')
mix=tab_create(large,'blend',name='mix')
connect(left,mix,0)
connect(right,mix,1)
''')
    large_out='/obj/__cop_contracts/large/mix'
    measured=value(f'cop_layer_stats({large_out!r})')
    assert measured['cache']['nodes_inspected'] > 512, measured['cache']
    assert measured['resolution']==[32,32],measured
    call('''
gain=tab_create('/obj/__cop_contracts/large','layer',name='gain')
set_parms(gain,{'setres':1,'resx':32,'resy':32,'f1':0.25})
out=tab_create('/obj/__cop_contracts/large','blend',name='controlled')
set_parms(out,{'mode':'add'})
connect('/obj/__cop_contracts/large/mix',out,0)
connect(gain,out,1)
''')
    large_gain='/obj/__cop_contracts/large/gain'
    large_controlled='/obj/__cop_contracts/large/controlled'
    large_cases=[{'id':'gain','values':{'f1':.5},'expectations':[{'metric':'mean','channel':0,'delta':[.24,.26]}]}]
    control=value(f'test_cop_controls({large_gain!r},{large_controlled!r},{large_cases!r})')
    assert control['ok'] and control['restored'],control
    relation=value(f'cop_compare_layers({large_out!r},{large_controlled!r},expected_delta={{"node":{large_gain!r}}})')
    assert relation['status']=='pass',relation
    call('''
cache=tab_create('/obj/__cop_contracts/large','cache',name='sticky')
connect('/obj/__cop_contracts/large/left',cache)
connect(cache,'/obj/__cop_contracts/large/mix',0)
set_parms(cache,{'clearonchange':0})
''')
    assert value(f'cop_layer_stats({large_controlled!r})')['freshness']=='unverified'
    rejects(f'test_cop_controls({large_gain!r},{large_controlled!r},{large_cases!r})','sticky')
    call("set_parms('/obj/__cop_contracts/large/sticky',{'clearonchange':1})")
    old_limit=cop._DEPENDENCY_NODE_LIMIT
    try:
        cop._DEPENDENCY_NODE_LIMIT=512
        rejects(f'cop_layer_stats({large_out!r})','exceeds 512')
    finally:
        cop._DEPENDENCY_NODE_LIMIT=old_limit
    old_edges=cop._DEPENDENCY_EDGE_LIMIT
    try:
        cop._DEPENDENCY_EDGE_LIMIT=1
        rejects(f'cop_layer_stats({large_out!r})','edge budget')
    finally:
        cop._DEPENDENCY_EDGE_LIMIT=old_edges
    old_seconds=cop._DEPENDENCY_SECONDS
    try:
        cop._DEPENDENCY_SECONDS=-1
        rejects(f'cop_layer_stats({large_out!r})','time budget')
    finally:
        cop._DEPENDENCY_SECONDS=old_seconds

    if hou.applicationVersion()[0]>=22:
        call('''
tml=tab_create('/stage','texturemateriallibrary',name='__cop_material_contract')
rgb=tab_create(tml,'constant',name='rgb')
mono=tab_create(tml,'constant',name='mono')
set_parms(rgb,{'signature':'f3'})
set_parms(mono,{'signature':'f1'})
''')
        material='/stage/__cop_material_contract/usdmaterial1'
        rgb='/stage/__cop_material_contract/rgb'
        mono='/stage/__cop_material_contract/mono'
        for src, port in ((rgb,0),(mono,3),(mono,12)):
            linked=value(f'connect({src!r},{material!r},{port})')
            assert linked['type_check']=='cop_material_exact_signature',linked
            assert hou.node(material).input(port).path()==src
        prior=hou.node(material).input(0)
        rejects(f'connect({mono!r},{material!r},0)','incompatible')
        assert hou.node(material).input(0)==prior
        rejects(f'connect({rgb!r},{material!r},0)','foreign',owner='another')
        assert value(f'cook_node({material!r})')['ok']
        call("delete_node('/stage/__cop_material_contract')")

    ports = value(f'describe({noise!r})')["ports"]
    assert ports['inputs'][0]['name'] == 'size_ref' and ports['inputs'][1]['name'] == 'pos', ports
    wired = value(f'connect({uv!r},{(root+"/second_output")!r},"source",output="uvscale")')
    assert wired['source_output'] == 1 and wired['verified'] and wired['semantic_status']=='unverified', wired
    assert value(f'connect({uv!r},{noise!r},1,output=0)')['input_name']=='pos'
    assert value(f'connect({a!r},{noise!r})')['source_output']==0
    original = hou.node(noise).inputConnections()
    def wires():
        return [(x.inputIndex(),x.inputNode().path(),x.outputIndex()) for x in hou.node(noise).inputConnections()]
    initial = wires()
    for code, text in [
        (f'connect({uv!r},{noise!r},"does_not_exist")','exactly once'),
        (f'connect({uv!r},{noise!r},"pos",output="bad")','exactly once'),
        (f'connect({uv!r},{noise!r},True)','nonnegative'),
        (f'connect({uv!r},{noise!r},"pos",output=99)','outside'),
        (f'connect({uv!r},{noise!r},"pos",1)','positional'),
    ]:
        rejects(code,text); assert wires()==initial
    rejects(f'connect({uv!r},{noise!r},"pos")','foreign',owner='other')
    call(f'connect({uv!r},{noise!r},"pos",allow_foreign="user explicitly selected this node")',owner='other')
    before=wires()
    rejects(f'connect({uv!r},{noise!r},"size_ref",output=1)\nraise RuntimeError("rollback_probe")','rollback_probe')
    assert wires()==before
    rejects(f'hou.node({noise!r}).setInput(0,hou.node({a!r}))','gate')
    for verb in (f'cop_layer_stats({a!r})', f'cop_compare_layers({a!r},{z!r})',
                 f'test_cop_controls({a!r},{a!r},[])'):
        rejects(verb,'read-only',read_only=True)

    stats=value(f'cop_layer_stats({a!r})')
    assert stats['resolution']==[16,8] and stats['channels']==1 and stats['sampled'] is False,stats
    assert stats['statistics'][0]['mean']==.25 and stats['sample_count']==128,stats
    rejects(f'cop_layer_stats({a!r},max_pixels=127)','budget')
    rejects(f'cop_layer_stats({a!r},output="missing")','exactly once')
    relation=value(f'cop_compare_layers({a!r},{z!r},expected_delta={{"node":{inc!r}}})')
    assert relation['status']=='pass' and relation['max_abs_error']==0,relation
    bindings=call(f'cop_compare_layers({a!r},{z!r},expected_delta={{"node":{inc!r}}})')['execution']['outputs']
    assert {d['node'] for d in bindings[0]['dependencies']}=={a,z,inc},bindings
    port_bindings=call(f'cop_layer_stats({uv!r},output=1)')['execution']['outputs']
    assert port_bindings[0]['path']==uv,port_bindings
    wrong=value(f'cop_compare_layers({a!r},{inc!r},expected_delta={{"node":{inc!r}}})')
    assert wrong['status']=='fail',wrong
    assert value(f'cop_compare_layers({a!r},{z!r})')['status']=='unverified'
    call(f'set_parms({inc!r},{{"resx":8}})')
    rejects(f'cop_compare_layers({a!r},{inc!r})','alignment')
    call(f'set_parms({inc!r},{{"resx":16}})')

    cases=[{'id':'gain','values':{'f1':.5},'expectations':[{'metric':'mean','channel':0,'delta':[.24,.26]}]}]
    check=value(f'test_cop_controls({a!r},{a!r},{cases!r})')
    assert check['ok'] and check['restored'] and hou.node(a).parm('f1').eval()==.25,check
    assert value(f'cop_layer_stats({a!r})')['sha256']==stats['sha256']
    env=call(f'__result__=test_cop_controls({a!r},{a!r},{cases!r})')
    ledger=next(x for x in env['verbs'] if x['verb']=='test_cop_controls')
    assert ledger['check_status']=='passed' and ledger['summary']['restored'],ledger
    bad=[{'id':'bad','values':{'f1':.5},'expectations':[{'metric':'mean','channel':0,'delta':[1,2]}]}]
    env=call(f'__result__=test_cop_controls({a!r},{a!r},{bad!r})')
    assert env['result']['status']=='fail' and env['result']['restored'],env
    assert next(x for x in env['verbs'] if x['verb']=='test_cop_controls')['check_status']=='failed'
    no_write=[{'id':'baseline','values':{'f1':.5},'expectations':[{'metric':'mean','channel':0,'delta':[.1,.5],'range':[.4,.8]}]}]
    assert value(f'test_cop_controls({a!r},{a!r},{no_write!r})')['parameter_writes']==0

    # Wrong coordinate port still cooks; the response test must fail, not certify semantics.
    call(f'disconnect_input({noise!r},1)\nconnect({uv!r},{noise!r},"size_ref",output="uv")')
    response=[{'id':'coordinate_driver','values':{'ushift':.317},'expectations':[{'metric':'mean_abs_change','channel':0,'delta':[1e-5,10]}]}]
    check=value(f'test_cop_controls({uv!r},{noise!r},{response!r})')
    assert check['status']=='fail' and check['restored'],check
    call(f'connect({uv!r},{noise!r},"pos",output="uv")')
    check=value(f'test_cop_controls({uv!r},{noise!r},{response!r})')
    assert check['ok'] and check['restored'],check
    uvstats=value(f'cop_layer_stats({uv!r},"uv")')
    assert uvstats['channels']==2 and uvstats['statistics'][0]['mean_abs_gradient_u']>0,uvstats
    assert uvstats['statistics'][1]['mean_abs_gradient_v']>0,uvstats

    # Full multichannel and integer identity values, not first-volume or float16 proxies.
    call(f'set_parms({inc!r},{{"signature":"f4","f4r":.125,"f4g":.25,"f4b":.5,"f4a":1.0}})')
    rgba=value(f'cop_layer_stats({inc!r})')
    assert [s['mean'] for s in rgba['statistics']]==[.125,.25,.5,1],rgba
    call(f'set_parms({inc!r},{{"signature":"i","i":16777217}})')
    ident=value(f'cop_layer_stats({inc!r})')
    assert ident['statistics'][0]['min']==16777217,ident

    p=hou.node(a).parm('f1')
    key=hou.Keyframe(); key.setFrame(1); key.setValue(.25); p.setKeyframe(key)
    keys=p.keyframes(); frame=hou.frame()
    assert value(f'test_cop_controls({a!r},{a!r},{cases!r})')['restored']
    assert p.keyframes()==keys and hou.frame()==frame
    # Perturbed read failure must still restore, then retain fail rather than success.
    original_read=cop._read
    def failed_read(*args,**kwargs):
        if hou.node(a).parm('f1').eval()==.5: raise ValueError('injected read failure')
        return original_read(*args,**kwargs)
    cop._read=failed_read
    try:
        fail=value(f'test_cop_controls({a!r},{a!r},{cases!r})')
        assert fail['status']=='fail' and fail['restored'],fail
    finally: cop._read=original_read

    call(f'cache=tab_create({root!r},"cache",name="sticky")\nconnect({a!r},cache)\nset_parms(cache,{{"clearonchange":0}})')
    sticky=root+'/sticky'
    assert value(f'cop_layer_stats({sticky!r})')['freshness']=='unverified'
    rejects(f'test_cop_controls({a!r},{sticky!r},{cases!r})','sticky')
    old_mode=hou.updateModeSetting()
    hou.setUpdateMode(hou.updateMode.Manual)
    try:
        rejects(f'cop_layer_stats({a!r})','manual')
        rejects(f'test_cop_controls({a!r},{a!r},{cases!r})','manual')
        assert p.keyframes()==keys
    finally: hou.setUpdateMode(old_mode)

    # Exact restoration failure must abort; it must not be returned as restored success.
    reads=[0]
    def bad_restore(*args,**kwargs):
        reads[0]+=1
        if reads[0]==3: raise ValueError('injected restoration failure')
        return original_read(*args,**kwargs)
    cop._read=bad_restore
    try:
        failed=rejects(f'test_cop_controls({a!r},{a!r},{cases!r})','restoration failed')
        assert failed['execution']['impact']['global'],failed
    finally: cop._read=original_read

    # Actual 2K float data export + File COP readback; no proxy dimension or 8-bit clamp.
    directory=Path(tempfile.mkdtemp(prefix='dsh-cop-delivery-'))
    hip=(directory/'fixture.hip').as_posix()
    exr=(directory/'height.exr').as_posix()
    value(f'scene_save_as({hip!r},expected_current_path={hou.hipFile.path()!r},reason="isolated authored regression fixture")')
    call(f'set_parms({inc!r},{{"signature":"f1","f1":-1.25,"resx":2048,"resy":2048}})')
    final_stats=value(f'cop_layer_stats({inc!r})')
    assert final_stats['resolution']==[2048,2048] and final_stats['statistics'][0]['min']==-1.25
    call(f'''r=tab_create({root!r},'rop_image',name='image_export')
set_parms(r,{{'coppath':{inc!r},'copoutput':{exr!r},'colorconversion':'raw','size1':'float32','raw1':1,'useport1':1,'port1':0}})
__result__=render_frame(r,picture={exr!r},frame=1)
''')
    assert Path(exr).is_file() and Path(exr).stat().st_size>0
    call(f'''f=tab_create({root!r},'file',name='file_readback')
set_parms(f,{{'filename':{exr!r},'colorspace':'raw','aovs':1}})
set_parms(f,{{'aov1':'C','type1':'float','precision1':'file','raw1':1}})
__result__=cop_layer_stats(f)
''')
    reader=root+'/file_readback'
    decoded=value(f'cop_layer_stats({reader!r})')
    assert decoded['resolution']==[2048,2048] and decoded['statistics'][0]['min']==-1.25,decoded
    assert decoded['storage_type']=='Float32',decoded
    value(f'scene_save(expected_path={hip!r})')
    # This is a newly authored isolated test HIP, never the user's saved scene.
    hou.hipFile.load(hip, suppress_save_prompt=True, ignore_load_warnings=True)
    reopened=value(f'cop_layer_stats({reader!r})')
    assert reopened['resolution']==[2048,2048] and reopened['statistics'][0]['mean']==-1.25,reopened
finally:
    node=hou.node('/obj/__cop_contracts')
    if node: node.destroy()
print('COP contract regression passed',hou.applicationVersionString())
