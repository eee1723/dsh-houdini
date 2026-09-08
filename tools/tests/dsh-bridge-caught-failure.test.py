"""Regression: caught verb exceptions must not commit an exec as successful."""

from __future__ import annotations

from pathlib import Path
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

print("caught verb failure regression passed")

# A suppressed failure poisons the batch immediately, before any later known
# mutation/file side effect is dispatched. Read-only discovery remains usable.
calls = []
original = dict(dsh_bridge._VERBS)
try:
    for name in ('scene_save', 'scene_save_as', 'render_frame', 'set_parm'):
        dsh_bridge._VERBS[name] = lambda *a, **k: calls.append((a, k))
    code = "try:\n    describe('/obj/__missing__')\nexcept Exception:\n    pass\n"
    code += "print(verb_help('describe'))\n"
    for name in ('scene_save', 'scene_save_as', 'render_frame', 'set_parm'):
        code += f'try:\n    {name}()\nexcept Exception as error:\n    print(error)\n'
    result = dsh_bridge.run_code(code)
    assert not result['ok'] and not calls, result
    assert result['transaction']['status'] == 'no_scene_change', result
    assert result['verbs'][1]['verb'] == 'verb_help' and result['verbs'][1]['ok'], result
    assert all(v['summary']['dispatched'] is False for v in result['verbs'][2:]), result
    # The poison is local to one exec; a fresh exec can dispatch again.
    fresh = dsh_bridge.run_code('scene_save()')
    assert fresh['ok'] and len(calls) == 1, fresh
finally:
    dsh_bridge._VERBS.clear()
    dsh_bridge._VERBS.update(original)
print('caught failure blocks later mutation/save/render, permits diagnostics and fresh exec')
