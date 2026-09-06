"""H21/H22: accidental positional ports or non-string values are not authority."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import hou
import dsh_hou_helpers as h
import dsh_bridge as b

def reject(fn, match):
    try: fn()
    except (TypeError, ValueError) as error:
        assert match in str(error), str(error)
    else: raise AssertionError('expected rejection')

root = hou.node('/obj').createNode('geo', '__authorization_args')
try:
    src = root.createNode('box', 'source')
    old = root.createNode('box', 'original')
    dst = root.createNode('merge', 'target')
    dst.setInput(0, old)
    # Exact test9 mistake: 0,5 is NOT (source output,target input).
    reject(lambda: h.connect(src, dst, 0, 5), 'positional')
    reject(lambda: h.disconnect_input(dst, 0, 5), 'positional')
    assert dst.input(0) == old and len(dst.inputs()) == 1
    for value in (0, 5, True, False, {}, [], '', '  '):
        for mode in (None, 'foreign-session', 'owner-session'):
            with h._execution_owner(mode, 'test'):
                if mode == 'owner-session': h._register_owned_node(dst)
                reject(lambda: h.connect(src, dst, allow_foreign=value), 'allow_foreign')
                reject(lambda: h.disconnect_input(dst, allow_foreign=value), 'allow_foreign')
                reject(lambda: h.set_parms(dst, {}, allow_foreign=value), 'allow_foreign')
                assert dst.input(0) == old
    # Host/Bridge execution rejects the same malformed call before it can wire.
    response = b.run_code(f'connect({src.path()!r},{dst.path()!r},0,5)', owner_session='owner-session', owner_call='bad-port')
    assert not response['ok'] and 'positional' in response['error'], response
    assert dst.input(0) == old
    with h._execution_owner('foreign-session', 'test'):
        reject(lambda: h.connect(src, dst), 'ownership guard')
        result = h.connect(src, dst, index=1, allow_foreign='User explicitly requested this target connection')
        assert result['input'] == 1 and dst.input(0) == old and dst.input(1) == src
        dst.setUserData(h._RENDER_OWNER_KEY, h._RENDER_OWNER_VALUE)
        reject(lambda: h.connect(src, dst, allow_foreign='User requested'), 'persistent')
        dst.destroyUserData(h._RENDER_OWNER_KEY)
    # Valid direct Python-shell use remains supported without fake authorization.
    h.disconnect_input(dst, index=1)
    h.connect(src, dst, index=0)
    assert dst.input(0) == src
finally:
    root.destroy()
print('authorization argument regression passed')
