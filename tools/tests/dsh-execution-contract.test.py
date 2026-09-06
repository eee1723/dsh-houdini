"""H21/H22: strict parameter edits, SOP checkpoints and safe scene naming.

Run only in disposable hython; the live scene is never contacted.
"""
from pathlib import Path
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_bridge as bridge
import dsh_hou_helpers as h


def rejects(fn, text=None):
    try:
        fn()
    except Exception as error:
        if text:
            assert text in str(error), str(error)
        return
    raise AssertionError('expected rejection')


root = hou.node('/obj').createNode('geo', '__contract_test')
try:
    box = root.createNode('box', 'source')
    original = box.evalParm('sizex')
    rejects(lambda: h.set_parms(box, {'sizex': 3, 'not_a_parm': 1}), 'not_a_parm')
    assert box.evalParm('sizex') == original, 'strict batch must not leave a partial assignment'
    box.parm('tx').setExpression('2+3', hou.exprLanguage.Hscript)
    box.parm('ty').lock(True)
    rejects(lambda: h.set_parms(box, {'tx': 9, 'ty': 4}))
    assert box.parm('tx').expression() == '2+3', 'rollback must restore expressions, not evaluated values'
    box.parm('ty').lock(False)
    partial = h.set_parms(box, {'sizex': 2, 'not_a_parm': 1}, strict=False)
    assert partial['ok'] is False and partial['failed'] and box.evalParm('sizex') == 2
    wr = root.createNode('attribwrangle', 'wrangle')
    cards = h.node_info(root, 'attribwrangle', parm_filter='class')
    menu = next(p for p in cards['parameters'] if p['name'] == 'class')['menu']
    assert any(item['token'] == 'detail' for item in menu), cards
    h.set_parm(wr, 'class', 'detail')
    assert wr.parm('class').evalAsString() == 'detail'
    before = wr.evalParm('class')
    rejects(lambda: h.set_parm(wr, 'class', 'not-a-valid-token'))
    assert wr.evalParm('class') == before
    wr.parm('snippet').set('float keep_me = 1;')
    rejects(lambda: h.set_parms(wr, {'snippet': 'float changed = 2;', 'class': 'invalid'}))
    assert wr.parm('snippet').unexpandedString() == 'float keep_me = 1;'
    box.parm('tx').setExpression('2+3', hou.exprLanguage.Hscript)
    rejects(lambda: h.set_parm(box, 'tx', []))
    assert box.parm('tx').expression() == '2+3', 'single-parm failure must also preserve animation'
    h.set_parm(wr, 'class', {'expression': '0', 'language': 'hscript'})
    assert wr.evalParm('class') == 0
    h.set_parm(box, 'tx', 'ch("ty")+1')
    assert box.evalParm('tx') == box.evalParm('ty') + 1
    original_tuple = box.parmTuple('t').eval()
    rejects(lambda: h.set_parm(box, 't', [1, 2]))
    assert box.parmTuple('t').eval() == original_tuple
    assert any(p['name'] == 'class' and p.get('menu') for p in h.list_parms(wr))

    # Invalid connection indices must not silently become another input.
    dst = root.createNode('xform', 'destination')
    rejects(lambda: h.connect(box, dst, 8))
    assert not dst.inputs()
    previous = set(root.children())
    rejects(lambda: h.tab_create(root, 'xform', 'bad_create', inputs=[box, box]))
    assert set(root.children()) == previous
    rejects(lambda: h.tab_create('/obj', 'geo', '__parenting_bypass', inputs=[root]), 'parent')
    assert hou.node('/obj/__parenting_bypass') is None

    # One small build specification, zero live writes for dry_run, explicit output.
    spec = [{'name': 'unit', 'type': 'box', 'parms': {'sizex': 2}},
            {'name': 'out', 'type': 'null', 'inputs': ['unit']}]
    previous = set(root.children())
    plan = h.build_module(root, spec, output='out', dry_run=True)
    assert plan['valid'] and set(root.children()) == previous
    made = h.build_module(root, spec, output='out')
    assert made['validation']['healthy'], made
    assert root.node('out').input(0) == root.node('unit')
    assert made['validation']['output'] == root.node('out').path()
    display_before, render_before = root.displayNode(), root.renderNode()
    if display_before is not None: display_before.setDisplayFlag(False)
    if render_before is not None: render_before.setRenderFlag(False)
    flags_before = {n.path(): (n.isDisplayFlagSet(), n.isRenderFlagSet()) for n in root.children()}
    with h._execution_owner('module-owner', 'module-test'):
        h.build_module(root, [{'name': 'owned_unit', 'type': 'box'}], output='owned_unit')
        assert h.node_provenance(root.node('owned_unit'))['status'] == 'owned_current_session'
    assert {n.path(): (n.isDisplayFlagSet(), n.isRenderFlagSet()) for n in root.children() if n.path() in flags_before} == flags_before
    assert not root.node('owned_unit').isDisplayFlagSet() and not root.node('owned_unit').isRenderFlagSet()
    if display_before is not None: display_before.setDisplayFlag(True)
    if render_before is not None: render_before.setRenderFlag(True)
    rejects(lambda: h.build_module(root, spec, output='out'), 'exists')
    previous = set(root.children())
    rejects(lambda: h.build_module(root, [
        {'name': 'a', 'type': 'box'},
        {'name': 'b', 'type': 'attribwrangle', 'inputs': ['a'],
         'parms': {'snippet': 'this is not valid VEX;'}}], output='b'))
    assert set(root.children()) == previous, 'cook failures must clean only this module'

    # The output null hides upstream warnings: verification must not.
    wr.destroy()
    dst.destroy()
    plain = root.createNode('box', 'plain')
    colored = root.createNode('color', 'colored'); colored.setInput(0, plain)
    merge = root.createNode('merge', 'merge'); merge.setInput(0, plain); merge.setInput(1, colored)
    final = root.createNode('null', 'final'); final.setInput(0, merge)
    check = h.verify_network(root, output=final)
    assert check['ok'] and not check['warning_free'] and not check['healthy'], check
    assert merge.path() in check['warning_nodes'], check
    assert check['semantic_status'] == 'unverified'
    old_signature = check['output_fingerprint']['signature']
    h.set_parm(plain, 'sizex', 5)
    assert h.verify_network(root, output=final)['output_fingerprint']['signature'] != old_signature
    empty = root.createNode('null', 'empty')
    rejects(lambda: h.verify_network(root, output=empty), 'empty_output')
    assert not h.verify_network(root, output=empty, require_valid=False)['ok']

    with tempfile.TemporaryDirectory(prefix='dsh-save-as-') as directory:
        target = str(Path(directory) / 'named.hip')
        before = hou.hipFile.path()
        rejects(lambda: h.scene_save_as(target, expected_current_path=before, reason=''), 'reason')
        rejects(lambda: h.scene_save_as(target, expected_current_path=target, reason='test'), 'expected_current_path')
        saved = h.scene_save_as(target, expected_current_path=before, reason='user-selected test directory')
        assert saved['bytes'] > 0 and Path(target).exists()
        occupied = Path(directory) / 'occupied.hip'; occupied.write_bytes(b'preserve me')
        rejects(lambda: h.scene_save_as(str(occupied), expected_current_path=target, reason='test'), 'exists')
        assert occupied.read_bytes() == b'preserve me'
        assert hou.hipFile.path().replace('\\', '/') == target.replace('\\', '/')
        saved_untitled = Path(directory) / 'untitled.hip'
        hou.hipFile.save(saved_untitled.as_posix())
        assert h.scene_info()['has_named_path'], 'a saved file can legitimately be named untitled.hip'
        assert h.scene_save()['bytes'] > 0

    # Guard hints must identify the actual HIP operation, not a node rename.
    usage = bridge._raw_usage_analysis("hou.hipFile.setName('x.hip')")
    assert all(v['verb'] != 'rename_node' for v in usage['coveredMutations']), usage
    assert 'scene_save_as' in bridge._gate_message("hou.hipFile.setName('x.hip')")

    # Rejected calls may not relay a previous call's image.
    with tempfile.NamedTemporaryFile(suffix='.png') as image:
        h._PRODUCED_IMAGES.append(image.name)
        blocked = bridge.run_code("hou.node('/obj').createNode('geo')")
        assert not blocked.get('images'), blocked
    errors = []
    def worker():
        try:
            bridge._execute(lambda: errors.append('HOM WOULD RUN ON WORKER'))
        except RuntimeError:
            errors.append('rejected')
    t = threading.Thread(target=worker); t.start(); t.join(2)
    assert errors == ['rejected'], errors
finally:
    root.destroy()

print('execution contract regression passed')
