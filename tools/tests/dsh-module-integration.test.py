"""Local checkpoint != final membership/contact; isolated HOM, no user HIP.

Exercises the execution mechanisms used by focused module work. This is not an
LLM behavior test and makes no visual-quality or full-domain acceptance claim.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as b
import dsh_quality_contracts as q

OWNER = 'module-integration-fixture'
with h._execution_owner(OWNER, 'setup'):
    root = h.tab_create('/obj', 'geo', '__module_integration')
try:
    def run(code, **options):
        return b.run_code(code, owner_session=OWNER, **options)

    def build(specs, output):
        reply = run(f'__result__=build_module({root.path()!r},{specs!r},output={output!r})')
        assert reply['ok'], reply
        return root.node(output)

    # Each functional component commits independently and is locally healthy.
    a = build([
        {'name':'a_shape','type':'box','parms':{'tx':.5}},
        {'name':'a_tag','type':'attribwrangle','inputs':['a_shape'],
         'parms':{'class':'primitive','snippet':'s@part="a"; i@group_a_surface=1;'}},
        {'name':'a_port','type':'attribwrangle','inputs':['a_tag'],
         'parms':{'class':'point','snippet':'if(@P.x>0.9) i@group_port=1;'}},
        {'name':'OUT_A','type':'null','inputs':['a_port']},
    ], 'OUT_A')
    receiver = build([
        {'name':'b_shape','type':'box','parms':{'tx':1.5}},
        {'name':'b_tag','type':'attribwrangle','inputs':['b_shape'],
         'parms':{'class':'primitive','snippet':'s@part="b"; i@group_receiver=1;'}},
        {'name':'OUT_B','type':'null','inputs':['b_tag']},
    ], 'OUT_B')
    identities = [a.sessionId(), receiver.sessionId()]
    signatures = [q._data_signature(n.geometry()) for n in (a, receiver)]
    with h._execution_owner(OWNER, 'controls'):
        ctrl = h.tab_create(root, 'null', 'CTRL')
        h.create_spare_parms(ctrl, spec=[{'type':'float','name':'offset','default':0}])
        h.tab_create(root, 'null', 'EMPTY')
    out = build([
        {'name':'place_a','type':'xform','inputs':['OUT_A'],
         'parms':{'tx':"2+ch('../CTRL/offset')"}},
        {'name':'place_b','type':'xform','inputs':['OUT_B'],
         'parms':{'tx':"2+ch('../CTRL/offset')"}},
        {'name':'choose_a','type':'switch','inputs':['place_a','EMPTY'],'parms':{'input':0}},
        {'name':'joined','type':'merge','inputs':['choose_a','place_b']},
        {'name':'OUT','type':'null','inputs':['joined']},
    ], 'OUT')
    interface = {'id':'actual_contact','source_group':'port','target_group':'receiver',
                 'expected_points':4,'max_distance':.001}

    def inspect():
        reply = run(f'__result__={{"network":verify_network({root.path()!r},output={out.path()!r}),'
                    f'"relations":geo_check_interfaces({out.path()!r},[{interface!r}])}}')
        assert reply['ok'], reply
        return reply['result']

    def members():
        return {p.attribValue('part') for p in out.geometry().prims()}

    assert members() == {'a','b'}
    assert inspect()['relations']['ok']
    # A valid source checkpoint does not certify downstream output membership.
    assert run(f'set_parm({root.node("choose_a").path()!r},"input",1)')['ok']
    missing = inspect()
    assert missing['network']['ok'] and missing['network']['healthy']
    assert members() == {'b'} and not missing['relations']['ok']
    assert [q._data_signature(n.geometry()) for n in (a, receiver)] == signatures
    assert run(f'set_parm({root.node("choose_a").path()!r},"input",0)')['ok']
    assert members() == {'a','b'} and inspect()['relations']['ok']
    # Both components still exist and cook, but their placed surfaces separate.
    assert run(f'set_parm({root.node("place_a").path()!r},"ty",.25)')['ok']
    detached = inspect()
    assert detached['network']['healthy'] and members() == {'a','b'}
    assert detached['relations']['status'] == 'fail'
    assert [q._data_signature(n.geometry()) for n in (a, receiver)] == signatures
    assert run(f'set_parm({root.node("place_a").path()!r},"ty",0)')['ok']
    # A failed later detail module cannot erase the independent source commits.
    failure = run(f'build_module({root.path()!r},[{{"name":"bad_detail","type":"attribwrangle",'
                  '"inputs":["OUT_A"],"parms":{"snippet":"unknown_integration_probe();"}}],output="bad_detail")')
    assert not failure['ok'] and root.node('bad_detail') is None
    assert [a.sessionId(),receiver.sessionId()] == identities
    assert [q._data_signature(n.geometry()) for n in (a, receiver)] == signatures
    assert inspect()['relations']['ok']
    # Shared controls must be tested on the actual placed assembly, not sources.
    tests = [{'id':'shared_move','values':{'offset':.3},'expectations':[
        {'metric':'bounds_center','group':'a_surface','axis':0,'delta':[.299,.301]},
        {'metric':'bounds_center','group':'receiver','axis':0,'delta':[.299,.301]},
    ]}]
    final_signature = q._data_signature(out.geometry())
    tested = run(f'__result__=test_controls({ctrl.path()!r},{out.path()!r},{tests!r},interfaces=[{interface!r}])')
    assert tested['ok'] and tested['result']['ok'] and tested['result']['restored'], tested
    assert ctrl.evalParm('offset') == 0 and q._data_signature(out.geometry()) == final_signature
    assert members() == {'a','b'}
    # A simple independent size edit remains ordinary exec/readback, no focus DB.
    assert run(f'set_parm({root.node("a_shape").path()!r},"sizey",.8)')['ok']
    assert root.node('a_shape').evalParm('sizey') == .8
finally:
    root.destroy()
print('module integration: source checkpoints, final membership, placed contacts, independent failure and shared-control restore passed on '+hou.applicationVersionString())
