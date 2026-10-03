"""Regression: caught verb exceptions must not commit an exec as successful."""

from __future__ import annotations

from pathlib import Path
import json
import os
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))

import dsh_bridge


result = dsh_bridge.run_code(
    "try:\n"
    "    set_parm('/obj/__dsh_node_that_does_not_exist__', 'tx', 1)\n"
    "except Exception as exc:\n"
    "    print('caught:', exc)\n"
    "__result__ = {'incorrect_success': True}\n"
)
assert result["ok"] is False, result
assert "caught and suppressed a verb exception" in result["error"], result["error"]
assert result["verbs"][-1]["verb"] == "set_parm"
assert result["verbs"][-1]["ok"] is False
assert "result" not in result
assert result['outcome']['batch'] == 'failed'
assert result['outcome']['operations']['failed'] == 1
assert result['outcome']['checks'] == {'failed': 0, 'warning': 0, 'unverified': 0}

print("caught verb failure regression passed")

# A failed write without recovery facts blocks later writes. A handled query
# error remains a per-item error and does not poison successful reads/writes.
calls = []
original = dict(dsh_bridge._VERBS)
try:
    for name in ('scene_save', 'scene_save_as', 'render_frame', 'set_parm'):
        dsh_bridge._VERBS[name] = lambda *a, **k: calls.append((a, k))
    query = dsh_bridge.run_code("try:\n    describe('/obj/__missing__')\nexcept Exception:\n    pass\n__result__=verb_help('describe')", read_only=True)
    assert query['ok'] and query['verbs'][0]['ok'] is False and query['verbs'][1]['ok'], query
    assert query['outcome'] == {'batch': 'completed', 'operations': {'total': 2, 'failed': 1},
                                'checks': {'failed': 0, 'warning': 0, 'unverified': 0}}, query
    assert 'checks' not in query and query['result'] == query['verbs'][1]['result'], query
    recovered = dsh_bridge.run_code("try:\n    describe('/obj/__missing__')\nexcept Exception:\n    pass\nscene_save()")
    assert recovered['ok'] and len(calls)==1, recovered
    assert recovered['outcome']['operations']['failed'] == 1
    calls.clear()
    def failed_write(*args, **kwargs):
        raise RuntimeError('synthetic dispatched mutation without recovery facts')
    dsh_bridge._VERBS['set_parms'] = failed_write
    code = "try:\n    set_parms('/obj', {})\nexcept Exception:\n    pass\n"
    code += "print(verb_help('describe'))\n"
    for name in ('scene_save', 'scene_save_as', 'render_frame', 'set_parm'):
        code += f'try:\n    {name}()\nexcept Exception as error:\n    print(error)\n'
    result = dsh_bridge.run_code(code)
    assert not result['ok'] and not calls, result
    assert result['transaction']['status'] == 'recovery_unverified', result
    assert result['verbs'][1]['verb'] == 'verb_help' and result['verbs'][1]['ok'], result
    assert all(v['summary']['dispatched'] is False for v in result['verbs'][2:]), result
    # The poison is local to one exec; a fresh exec can dispatch again.
    fresh = dsh_bridge.run_code('scene_save()')
    assert fresh['ok'] and len(calls) == 1, fresh
finally:
    dsh_bridge._VERBS.clear()
    dsh_bridge._VERBS.update(original)
print('caught unknown mutation blocks later writes; handled read/zero-write failures remain usable')

# Real empty geometry returns a failed validation without raising an operation
# exception. Export exact Bridge receipts for the native/PTC consumer test.
built = dsh_bridge.run_code("g=tab_create('/obj','geo',name='outcome_fixture')\n"
    "n=tab_create(g,'null',name='EMPTY')\n__result__=n.path()")
assert built['ok'], built
restored = dsh_bridge.run_code("try:\n"
    "    set_parm('/obj/outcome_fixture', 'tx', {'expression':'1/0','language':'python'})\n"
    "except Exception:\n    pass\n"
    "set_parm('/obj/outcome_fixture', 'ty', 2)\n"
    "__result__=read_parms('/obj/outcome_fixture', names=['tx','ty'])")
assert restored['ok'] and restored['outcome']['operations']['failed'] == 1, restored
assert restored['verbs'][0]['summary']['restored'] is True, restored
assert restored['result'][0]['value'] == 0 and restored['result'][1]['value'] == 2, restored
assert restored['outcome']['checks']['failed'] == 0, restored
checked = dsh_bridge.run_code("__result__=verify_network('/obj/outcome_fixture', "
    "output='/obj/outcome_fixture/EMPTY', require_valid=False)")
assert checked['ok'] and checked['outcome']['operations']['failed'] == 0, checked
assert checked['outcome']['checks']['failed'] == 1, checked
assert checked['checks'][0]['status'] == 'failed', checked
if os.environ.get('DSH_OUTCOME_FIXTURE_OUT'):
    Path(os.environ['DSH_OUTCOME_FIXTURE_OUT']).write_text(json.dumps(
        {'caught_read': query, 'failed_check': checked}, ensure_ascii=False, indent=2), encoding='utf-8')
assert dsh_bridge.run_code("delete_node('/obj/outcome_fixture')")['ok']
print('Bridge outcome separates completed batches, raised operations and returned validation failures')
