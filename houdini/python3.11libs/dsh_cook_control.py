"""Cook policy and known unsafe VEX rejection. Timeouts are cooperative only."""
import re
import hou


def validate_vex(source):
    # Preserve strings while dropping comments, so commented examples do not block.
    cleaned = re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/',
                     lambda m: m.group(0) if m.group(0).startswith('"') else ' ', source)
    dangerous = re.search(r'\bwhile\s*\(\s*n(points|primitives)\s*\(\s*0\s*\)\s*>\s*0\s*\)', cleaned)
    if dangerous and re.search(r'\bremove(point|prim)\s*\(', cleaned):
        raise ValueError('unsafe VEX deletion loop: input counts do not decrease during VEX execution; use a bounded loop over the original count. Test unknown generators in an isolated process.')


def preflight(node):
    pending, seen = [node], set()
    while pending:
        n = pending.pop()
        if n.sessionId() in seen: continue
        seen.add(n.sessionId())
        if len(seen) > 512:
            raise ValueError('cook dependency preflight exceeds 512 nodes; narrow the output or use isolated validation')
        if 'wrangle' in n.type().name():
            p = n.parm('snippet')
            if p is not None and not p.keyframes(): validate_vex(p.unexpandedString())
        pending.extend(x for x in n.inputs() if x is not None)


def set_update_mode(mode, expected_mode):
    modes = {'auto': hou.updateMode.AutoUpdate, 'manual': hou.updateMode.Manual,
             'on_mouse_up': hou.updateMode.OnMouseUp}
    before = hou.updateModeSetting()
    current = next(k for k,v in modes.items() if v == before)
    if mode not in modes or expected_mode != current:
        raise ValueError(f'invalid/stale update mode; current={current}; read scene_info before switching')
    hou.setUpdateMode(modes[mode])
    return {'before':current, 'after':mode, 'changed':before != modes[mode],
            'scope':'global update policy; switching to auto may cook dirty networks, not a cancellation mechanism'}
