"""Disposable H21/H22 regression: explicit outputs, bounded evidence and paths."""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as bridge


def reject(fn, expected):
    try:
        fn()
    except Exception as error:
        assert expected in str(error), str(error)
        return
    raise AssertionError('expected failure: ' + expected)


root = hou.node('/obj').createNode('geo', '__checkpoint_test')
try:
    source = root.createNode('box', 'source')
    ctrl = root.createNode('null', 'CONTROLS'); ctrl.setDisplayFlag(True)
    out = root.createNode('null', 'OUT'); out.setInput(0, source)
    reject(lambda: h.verify_network(root), 'output')
    assert h.verify_network(root, output=out)['ok']
    reject(lambda: h.verify_network(root, output=ctrl), 'empty_output')
    diagnostic = h.verify_network(root, output=ctrl, require_valid=False)
    assert not diagnostic['ok'] and diagnostic['failure_reasons'] == ['empty_output']
    assert diagnostic['output'] == ctrl.path() and diagnostic['next_action']
    failed = bridge.run_code(f'verify_network({root.path()!r}, output={ctrl.path()!r})')
    assert not failed['ok'] and failed['evidence'][0]['failure_reasons']==['empty_output']
    assert failed['evidence'][0]['output']==ctrl.path()

    subnet = root.createNode('subnet', 'module')
    child = subnet.createNode('null', 'consumer')
    reject(lambda: h.connect(source, child, 1), 'different_parent')
    assert not child.inputs()
    reject(lambda: h.tab_create(subnet, 'xform', 'bad', inputs=[source]), 'different_parent')
    assert subnet.node('bad') is None
    local= subnet.createNode('object_merge','imported')
    h.set_parms(local, {'objpath1':source.path(),'xformtype':'none'})
    h.connect(local,child)
    assert child.geometry().intrinsicValue('pointcount')==8

    # Sparse secondary-input geometry is a normal Wrangle pattern, not a reason
    # to avoid the module constructor. An explicit port map avoids dummy nodes.
    specs = [
        {'name':'lookup', 'type':'attribwrangle', 'parms':{'class':'detail',
          'snippet':'vector p = point(1, "P", 0); addpoint(0, p);'},
         'inputs':[None, 'source']},
        {'name':'MODULE_OUT', 'type':'null', 'inputs':['lookup']},
    ]
    assert h.build_module(root, specs, output='MODULE_OUT', dry_run=True)['valid']
    built = h.build_module(root, specs, output='MODULE_OUT')
    assert built['validation']['geometry']['points'] == 1
    assert root.node('lookup').input(0) is None
    assert root.node('lookup').input(1) == source
    reject(lambda: h.build_module(root, [{'name':'badmenu','type':'attribwrangle',
        'parms':{'class':'not-valid'}}], output='badmenu', dry_run=True), 'menu')
    assert root.node('badmenu') is None

    sequence=root.createNode('attribwrangle','sequence')
    h.set_parms(sequence, {'class':'detail','snippet': 'float xs[]=array(0.,1.,2.,2.1,3.1); foreach(float x;xs) addpoint(0,set(x,0,0));'})
    spacing=h.geo_point_spacing(sequence,expected=1,tolerance=.001)
    assert not spacing['ok'] and spacing['pair_count']==4 and spacing['failure_count']==1
    assert spacing['failures'][0]['from_point']==2 and spacing['failures'][0]['to_point']==3
    assert spacing['coverage']=='all_adjacent_pairs'
    reject(lambda:h.geo_point_spacing(sequence,1,.001,max_points=3), 'no sampling')
    h.set_parms(sequence, {'snippet':'vector ps[]=array(set(0,0,0),set(1,0,0),set(1,1,0),set(0,1,0)); foreach(int i;vector p;ps) {int pt=addpoint(0,p);setpointattrib(0,"order",pt,i);} '})
    assert h.geo_point_spacing(sequence,1,.001,closed=True,order_attrib='order')['ok']
    reject(lambda:h.geo_point_spacing(sequence,1,.001,order_attrib='missing'), 'order_attrib')
    failed_check=bridge.run_code(f'__result__=geo_point_spacing({sequence.path()!r}, 2, 0.01, closed=True)',read_only=True)
    assert failed_check['ok'] and failed_check['checks'][0]['status']=='failed'
    assert failed_check['evidence'][0]['failure_count']==4

    # Missing evidence cannot become success simply because Python returned.
    missing = h._render_validation({'fresh':True, 'file_bytes':10, 'errors':[]}, {'error':'decode'}, False)
    assert not missing['ok'] and missing['pixel_status'] == 'failed'
    ledger=[]
    bridge._make_tracer('render_view', lambda:{**missing,'output':'Z:/test/render/a.png','frame':1,'check':{'error':'decode'}},ledger)()
    assert ledger[0]['check_status']=='failed' and ledger[0]['summary']['pixel_status']=='failed'
    hdr = h._render_validation({'fresh':True, 'file_bytes':10, 'errors':[]}, None, False, pixel_supported=False)
    assert hdr['ok'] and hdr['pixel_status'] == 'unverified'
    stale = h._render_validation({'fresh':True, 'file_bytes':10, 'errors':[]}, {'presentation':{}}, True)
    assert not stale['ok']
    ledger=[]
    bridge._make_tracer('verify_network',lambda: diagnostic,ledger)()
    assert ledger[0]['summary']['output'] == ctrl.path()
    assert ledger[0]['summary']['failure_reasons'] == ['empty_output']

    with tempfile.TemporaryDirectory(prefix='dsh-checkpoint-') as tmp:
        base=Path(tmp); hip=base/'project.hip'
        hou.hipFile.save(hip.as_posix())
        path=h._resolve_output_path('preview.$F4.png', frame=3, default_subdir='render')
        assert Path(path)==base/'render'/'preview.0003.png', path
        assert Path(h._resolve_output_path('render/preview.png', frame=1, default_subdir='render'))==base/'render'/'preview.png'
        reject(lambda:h._resolve_output_path('../outside.png',frame=1,default_subdir='render'), 'outside')
        reject(lambda:h._resolve_output_path('no_extension',frame=1,default_subdir='render'), 'extension')
        reject(lambda:h._resolve_output_path(str(Path(__file__).resolve().parents[2]/'bad.png'),frame=1,default_subdir='render'), 'repository')
        rop=hou.node('/out').createNode('geometry','__checkpoint_rop')
        try:
            rop.parm('soppath').set(source.path())
            old=rop.parm('sopoutput').unexpandedString()
            result=h.render_frame(rop,picture='cache.$F4.bgeo.sc',frame=3,timeout=5)
            assert Path(result['output'])==base/'geo'/'cache.0003.bgeo.sc', result
            assert Path(result['output']).exists() and result['fresh']
            assert rop.parm('sopoutput').unexpandedString()==old
            reject(lambda:h.render_frame(rop,picture='no_extension',frame=4), 'extension')
            assert rop.parm('sopoutput').unexpandedString()==old
        finally:rop.destroy()
finally:root.destroy()

print('explicit output/path/checkpoint regressions passed')
