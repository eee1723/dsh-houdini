"""Real large parameter catalogs remain typed and selected output stays distinct."""
from pathlib import Path
import json
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import hou
import dsh_bridge as bridge
from dsh_execution import _verb_value, _unrecovered_mutation
from dsh_execution_results import _jsonable, _MAX_RESULT_BYTES

# Small allocations that used to expand exponentially during snapshotting.
# Exercise both the public result converter and HOM ledger converter, which
# must share the same budget without flattening normal large typed catalogs.
started = time.monotonic()
cycle = []
cycle.extend([cycle] * 1001)
shared = {'payload': 'x' * 4096}
expanded = [[shared] * 100] * 100
class CustomLeaf:
    def __repr__(self):
        return '<custom diagnostic leaf>'
for convert in (_jsonable, _verb_value):
    assert 'JSON value omitted: cyclic container reference' in convert(cycle)
    assert f'JSON value omitted: exceeds {_MAX_RESULT_BYTES} serialized bytes' in convert(expanded)
    nested = convert({'nested': [{'custom': CustomLeaf(), 'zero': -0.0, 'finite': float('inf')}], 'repeat': [shared, shared]})
    assert nested['nested'][0] == {'custom': '<custom diagnostic leaf>', 'zero': 0.0, 'finite': 'inf'}
    assert isinstance(nested['repeat'][0], dict) and nested['repeat'][0] == nested['repeat'][1]
    assert nested['repeat'][0] is not nested['repeat'][1], 'snapshots detach repeated mutable containers'
    depth = 'leaf'
    for _ in range(25):
        depth = [depth]
    assert 'JSON depth exceeds' in json.dumps(convert(depth))
    assert 'JSON value omitted' in convert('x' * (_MAX_RESULT_BYTES + 1))
assert _unrecovered_mutation({'verb': 'set_parms', 'ok': False, 'summary': _jsonable(cycle)}), 'unavailable recovery evidence never proves restoration'
print('bounded cyclic/shared/nested/custom serialization seconds:', round(time.monotonic() - started, 3))

settings = hou.node('/stage').createNode('karmarendersettings', '__catalog_settings')
rop = hou.node('/stage').createNode('usdrender_rop', '__catalog_rop')
geometry = hou.node('/obj').createNode('geo', '__catalog_conditions')
copnet = geometry.createNode('copnet', 'images')
noise = copnet.createNode('fractalnoise', 'noise')
dense = geometry.createNode('tube', 'dense_target')
dense.parm('type').set('poly');dense.parm('cap').set(True);dense.parm('cols').set(4100)
tag = geometry.createNode('attribwrangle', 'tag_target');tag.setInput(0,dense)
tag.parm('class').set('primitive');tag.parm('snippet').set('setprimgroup(0,"solid",@primnum,1);')
try:
    # The same pattern as test69 seq676: the author selects fields from actual
    # list_parms values; the ledger is an independent, addressable full catalog.
    result = bridge.run_code(
        f"__result__={{'settings':[p for p in list_parms({settings.path()!r}) if p['name'] in ('res_mode','resolution')],"
        f"'rop':[p for p in list_parms({rop.path()!r}) if p['name']=='renderer'],"
        f"'conditions':{{'static':node_info({copnet.path()!r},'fractalnoise',parm_filter='element'),"
        f"'live':[p for p in list_parms({noise.path()!r}) if p['name'].startswith('element')]}},"
        f"'surface_cards':{{t:{{k:v for k,v in node_info({geometry.path()!r},t).items() if k in ('operation_card','usage_notes','operation_parameters')}} for t in ('polybevel','boolean')}},"
        "'interface_limits':verb_help('geo_check_interfaces',detail='full')['runtime_limits'],"
        f"'interface_observation':geo_check_interfaces({tag.path()!r},[{{'id':'clearance','method':'bore_clearance','target_group':'solid','axis':1,'start':[0,-1,0],'end':[0,1,0],'radius':.1}}],max_pairs=100000)}}", read_only=True)
    assert result['ok'], result
    for entry in result['verbs'][:2]:
        assert isinstance(entry['result'], list) and len(entry['result']) > 50, entry
        assert entry['summary']['kind'] == 'parameter_catalog'
        assert entry['summary']['parameter_count'] == len(entry['result'])
        assert 'check_status' not in entry, 'catalog discovery does not certify a validation'
    resolution = next(p for p in result['result']['settings'] if p['name'] == 'resolution')
    assert resolution['locked_components'] == ['resolutiony'], resolution
    static={p['name']:p for p in result['result']['conditions']['static']['parameters']}
    live={p['name']:p for p in result['result']['conditions']['live']}
    assert static['elementscale']['conditionals']==live['elementscale']['conditionals']
    assert static['elementsizetype']['menu'][0]['set_value']==1
    for card in result['result']['surface_cards'].values():
        assert card['usage_notes'] and card['operation_card']['source']
    observation=result['result']['interface_observation']
    assert observation['status']=='unverified' and observation['runtime_limits']==result['result']['interface_limits']
    assert observation['results'][0]['reason']=='target_primitive_limit_exceeded'
    assert json.loads(json.dumps(result))['verbs'][0]['result'][-1]['name']
    # The 50/1000 item thresholds are not permissions to flatten canonical data.
    many = [{'name':f'field_{i}','menu':[{'token':'x','label':'X'}]} for i in range(1100)]
    assert _verb_value(many)[1099]['menu'][0]['token'] == 'x'
    assert _verb_value({str(i):many[i] for i in range(1100)})['1099']['name'] == 'field_1099'
    selected = bridge.run_code("__result__=[{'name':str(i)} for i in range(1100)]", read_only=True)
    assert selected['result'][1099]['name'] == '1099', 'large explicit results also remain typed within the byte/depth envelope'
    cyclic = bridge.run_code("a=[]\na.extend([a]*1001)\n__result__=a", read_only=True)
    assert cyclic['ok'] and 'JSON value omitted: cyclic container reference' in cyclic['result'], cyclic
    failed = bridge.run_code("list_parms('/obj/__catalog_missing__')", read_only=True)
    assert not failed['ok'] and not failed['verbs'][0]['ok']
    assert failed['verbs'][0].get('summary', {}).get('kind') != 'parameter_catalog'
    if os.environ.get('DSH_CATALOG_FIXTURE_OUT'):
        Path(os.environ['DSH_CATALOG_FIXTURE_OUT']).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
finally:
    geometry.destroy()
    settings.destroy()
    rop.destroy()
print('typed native parameter catalogs, selected output, locks and failure preservation passed on ' + hou.applicationVersionString())
