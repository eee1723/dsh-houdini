"""Cook policy and known unsafe VEX rejection. Timeouts are cooperative only."""
import re
import hou


def require_evaluation(operation):
    """Fail before geometry/camera/render work; cached data is not fresh proof."""
    if hou.updateModeSetting() == hou.updateMode.Manual:
        raise ValueError(f'{operation} requires geometry evaluation, unavailable in Manual mode. '
                         'Keep metadata inspection/editing in Manual; explicitly authorize '
                         'set_update_mode before evaluation. No empty/fresh result is inferred.')


_VEX_TOKENS = re.compile(
    r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    r'|[A-Za-z_]\w*|\d+(?:\.\d*)?|\S')


def _delimiter_ends(tokens):
    stack, ends = [], {}
    for index, token in enumerate(tokens):
        if token in ('(', '{'):
            stack.append((index, token))
        elif token in (')', '}'):
            if not stack or stack[-1][1] != {')': '(', '}': '{'}[token]:
                return None
            ends[stack.pop()[0]] = index
    return None if stack else ends


def _flat_deletions(tokens, start, stop, ends):
    """Recognize only direct deletion statements with simple/pure arguments.

    Branches, exits, nested loops and custom calls are deliberately unknown,
    not classified by searching for words elsewhere in the source.
    """
    index = start
    if start >= stop:
        return False
    while index < stop:
        if tokens[index] not in ('removepoint', 'removeprim') or tokens[index + 1:index + 2] != ['(']:
            return False
        end = ends.get(index + 1)
        if end is None or end + 1 >= stop or tokens[end + 1:end + 2] != [';']:
            return False
        arguments = tokens[index + 2:end]
        if arguments[:2] != ['0', ','] or any(t in ('<string>', '{', '}', ';') for t in arguments):
            return False
        for offset, token in enumerate(arguments[:-1]):
            if token.isidentifier() and arguments[offset + 1] == '(':
                if token not in ('npoints', 'nprimitives') or arguments[offset + 1:offset + 4] != ['(', '0', ')']:
                    return False
        index = end + 2
    return True


def validate_vex(source):
    """Reject canonical nonterminating deletion loops, not certify other VEX.

    Input counts do not decrease during a VEX invocation. A loop guarded only
    by that count and consisting solely of deletion calls cannot finish on a
    nonempty input. Other control flow remains unknown; this is not a sandbox
    or a general termination analysis. Preprocessing remains unknown too.
    """
    tokens = []
    for token in _VEX_TOKENS.findall(source):
        if token.startswith(('//', '/*')):
            continue
        tokens.append('<string>' if token.startswith(('"', "'")) else token)
    if '#' in tokens:
        return  # macros/conditional compilation require the native preprocessor
    ends = _delimiter_ends(tokens)
    if ends is None:
        return  # malformed source belongs to the native compiler
    for index, token in enumerate(tokens):
        if token != 'while' or tokens[index + 1:index + 2] != ['(']:
            continue
        end = ends.get(index + 1)
        if end is None:
            continue
        condition = tokens[index + 2:end]
        if not (condition[:1] in (['npoints'], ['nprimitives']) and condition[1:] == ['(', '0', ')', '>', '0']):
            continue
        start = end + 1
        if tokens[start:start + 1] == ['{']:
            stop = ends[start]
            start += 1
        else:
            call_end = ends.get(start + 1)
            if call_end is None:
                continue
            stop = call_end + 2
        if _flat_deletions(tokens, start, stop, ends):
            raise ValueError('unsafe VEX deletion loop: input counts do not decrease during VEX execution; use a bounded loop over the original count. Test unknown generators in an isolated process.')


def preflight(nodes):
    """Check one explicit read-only batch's dependency union, without cooking.

    No state survives the call. A large dependency graph is not itself unsafe;
    verify_network's declared scope limit is separate from this source check.
    """
    pending, seen = list(nodes), set()
    while pending:
        n = pending.pop()
        identity = n.sessionId()
        if identity in seen: continue
        seen.add(identity)
        if 'wrangle' in n.type().name():
            p = n.parm('snippet')
            if p is not None and not p.keyframes(): validate_vex(p.unexpandedString())
        pending.extend(x for x in n.inputs() if x is not None)


def set_update_mode(mode, expected_mode):
    modes = {'auto': hou.updateMode.AutoUpdate, 'manual': hou.updateMode.Manual,
             'on_mouse_up': hou.updateMode.OnMouseUp}
    names = {value: name for name, value in modes.items()}
    before = hou.updateModeSetting()
    current = names[before]
    if mode not in modes or expected_mode != current:
        raise ValueError(f'invalid/stale update mode; current={current}; read scene_info before switching')
    if mode == 'on_mouse_up' and not hou.isUIAvailable():
        raise ValueError('on_mouse_up is unsupported without a Houdini GUI; no mode was changed. '
                         'Headless Houdini coerces it to auto, which could leave Manual and start cooking.')
    observed, failure = None, None
    try:
        hou.setUpdateMode(modes[mode])
        observed = hou.updateModeSetting()
    except Exception as error:
        failure = error
        try:
            observed = hou.updateModeSetting()
        except Exception:
            pass  # Still attempt restoration; no current-mode claim is possible.
    if failure is None and observed == modes[mode]:
        return {'before': current, 'after': names[observed], 'changed': before != observed,
                'scope': 'global update policy; switching to auto may cook dirty networks, not a cancellation mechanism'}
    restore_errors = []
    if observed != before:
        try:
            hou.setUpdateMode(before)
        except Exception as error:
            restore_errors.append(str(error) or type(error).__name__)
    try:
        restored_mode = hou.updateModeSetting()
    except Exception as error:
        restored_mode = None
        restore_errors.append('restoration readback: ' + (str(error) or type(error).__name__))
    detail = (str(failure) or type(failure).__name__) if failure is not None else 'requested mode was not applied'
    raise RuntimeError(
        f'set_update_mode failed: requested={mode}; readback={names.get(observed, "unknown")}; '
        f'current_mode={names.get(restored_mode, "unknown")}; previous_mode_restored={restored_mode == before}; '
        f'{detail}; restore_errors={restore_errors}. Only the mode is restored; '
        'cooks and external side effects triggered by the switch are not undone.'
    ) from failure
