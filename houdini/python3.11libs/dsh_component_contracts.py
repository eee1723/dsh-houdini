"""Explicit, hash-pinned ordinary SOP subnet exchange (not an HDA library).

Native node archives contain executable expressions. Import is an explicit trusted
artifact operation, not a sandbox or an automatic acceptance of a child report.
No module import side effects; HOM callers are serialized by the Bridge.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import tempfile

import hou

MAX_BYTES = 32 * 1024 * 1024
MAX_NODES = 1024
NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,79}$')

# Candidate provenance for this Bridge session only: import records the accepted
# contract so replace can refuse a stale or unknown-revision draft. Records do not
# survive a Bridge restart; replace then refuses expected_contract checks (safe side).
_IMPORT_RECORDS = {}


def _h():
    import dsh_hou_helpers
    return dsh_hou_helpers


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ValueError('component name must be an ASCII identifier, at most 80 characters')
    return value


def _path(filename, *, writing=False):
    if not isinstance(filename, str) or not filename or '\x00' in filename:
        raise ValueError('explicit component file path required')
    p = Path(hou.expandString(filename))
    if not p.is_absolute() or p.suffix != '.dshcomponent':
        raise ValueError('absolute .dshcomponent path required')
    for ancestor in (p, *p.parents):
        if ancestor.is_symlink() or (hasattr(ancestor, 'is_junction') and ancestor.is_junction()):
            raise ValueError('component paths cannot contain links/junctions')
    p = p.resolve()
    if writing:
        hip = Path(hou.hipFile.path()).resolve()
        if hip.name.lower() == 'untitled.hip' or not p.is_relative_to(hip.parent):
            raise ValueError('component export must be inside the named $HIP directory')
        if p.exists():
            raise ValueError('component export never overwrites an existing revision')
        if not p.parent.is_dir():
            raise ValueError('component export parent directory must already exist')
    else:
        stat = p.stat()
        if not p.is_file() or stat.st_nlink != 1 or stat.st_size > MAX_BYTES:
            raise ValueError('component file must be a bounded regular single-link file')
    return p


def _nodes(root):
    if root.type().category() != hou.sopNodeTypeCategory() or root.type().name() != 'subnet':
        raise ValueError('component root must be an ordinary SOP subnet, not an HDA')
    nodes = (root, *root.allSubChildren(sync_delayed_definition=True))
    if len(nodes) > MAX_NODES:
        raise ValueError('component node budget exceeded')
    return nodes


def _sidefx_definition_ancestor(node, root, hfs):
    """Return the owning built-in HDA instance for definition implementation nodes."""
    cursor = node
    while cursor is not None and cursor != root.parent():
        definition = cursor.type().definition()
        if definition is not None:
            library = Path(definition.libraryFilePath()).resolve()
            if library.is_relative_to(hfs):
                return cursor
        if cursor == root:
            break
        cursor = cursor.parent()
    return None


def _parm_value(parm):
    """Serializable authored channels or literal values, shared by both snapshots."""
    keys = parm.keyframes()
    if keys:
        return {'keys': [key.asCode() for key in keys]}
    if parm.parmTemplate().type() == hou.parmTemplateType.String:
        return {'string': parm.unexpandedString()}
    value = parm.eval()
    if isinstance(value, hou.Ramp):
        return {'ramp': {'basis': [str(b) for b in value.basis()],
                         'keys': list(value.keys()),
                         'values': [list(v) if isinstance(v, tuple) else v for v in value.values()]}}
    return {'value': value}


def _snapshot(root, *, check_owned=False):
    """Boundary inventory, public controls and dependency checks, not a node codec.

    Native archives retain internal values. Only root spare parameters are
    mirrored for interface comparison; dependency inspection remains independent.
    """
    h = _h()
    nodes = _nodes(root)
    if any(root.inputs()):
        raise ValueError('connected component root inputs are not yet supported; export a self-contained candidate')
    members = set(nodes)
    rows = []
    hfs = Path(hou.getenv('HFS')).resolve()
    public_parms = set(root.spareParms())
    for node in nodes:
        sidefx_instance = _sidefx_definition_ancestor(node, root, hfs)
        if check_owned:
            try:
                h._require_owned(node, 'component export')
            except ValueError as ownership_error:
                # Some SideFX HDAs materialize implementation children only on
                # their first cook. Those child session ids were not present when
                # the owned HDA instance was created, but they are definition
                # contents rather than separately authored scene nodes. Accept
                # only internals of an owned, SideFX-installed definition. A
                # foreign direct child or a custom HDA still fails normally.
                if sidefx_instance is None:
                    raise ownership_error
                h._require_owned(sidefx_instance, 'component export built-in HDA instance')
        if node.eventCallbacks() or node.userData(h._RENDER_OWNER_KEY):
            raise ValueError('component cannot contain callbacks or persistent service nodes')
        definition = node.type().definition()
        if definition:
            library = Path(definition.libraryFilePath()).resolve()
            if not library.is_relative_to(hfs):
                raise ValueError('custom HDA dependencies are not supported by component exchange')
        if node.type().name().split('::')[0] in ('python', 'pythonoperator', 'file', 'filecache', 'rop_geometry', 'solver'):
            raise ValueError('external/script/solver SOPs are not supported by component exchange')
        parms = []
        for parm in node.parms():
            template = parm.parmTemplate()
            if template.scriptCallback() and sidefx_instance is None:
                raise ValueError('component parameter callbacks are unsupported')
            keys = parm.keyframes()
            # Inspect reference-bearing channels without serializing every
            # internal numeric/ramp value into a competing archive representation.
            value = (_parm_value(parm) if keys or template.type() == hou.parmTemplateType.String else None)
            if keys:
                for key in keys:
                    try:
                        if key.expressionLanguage() == hou.exprLanguage.Python:
                            raise ValueError('Python parameter expressions are unsupported')
                    except hou.OperationFailed:
                        pass
                    try:
                        expression = key.expression()
                    except hou.OperationFailed:
                        continue
                    for match in re.finditer(r'\bch(?:f|i|s|v)?\s*\(\s*[\'\"]([^\'\"]+)[\'\"]', expression):
                        referenced = node.parm(match.group(1))
                        if referenced is None or referenced.node() not in members:
                            raise ValueError('external or missing expression channel: ' + parm.path())
            text = json.dumps(value, ensure_ascii=False) if value is not None else ''
            if re.search(r'(?:/obj/|/stage/|[A-Za-z]:[/\\]|\$HIP|\$JOB|opdef:|oplib:|hou\.session)', text):
                raise ValueError('external/absolute component parameter reference: ' + parm.path())
            if template.type() == hou.parmTemplateType.String and template.stringType() == hou.stringParmType.NodeReference:
                # Authored expressions remain in the snapshot; resolve their
                # current target for containment without treating them as literals.
                raw = parm.evalAsString() if keys else parm.unexpandedString()
                if raw and (node.node(raw) not in members):
                    raise ValueError('external node reference: ' + parm.path())
            reference = parm.getReferencedParm()
            if reference.node() not in members:
                raise ValueError('external parameter reference: ' + parm.path())
            if parm in public_parms:
                parms.append([parm.name(), _parm_value(parm), parm.isLocked()])
        wires = []
        if node != root:
            for wire in node.inputConnections():
                indirect = wire.subnetIndirectInput()
                if indirect is not None:
                    if indirect.parent() not in members:
                        raise ValueError('external subnet input: ' + node.path())
                    wires.append([wire.inputIndex(), {'subnet': root.relativePathTo(indirect.parent()),
                                                     'input': indirect.number()}, wire.outputIndex()])
                    continue
                source = wire.inputNode()
                if source not in members:
                    raise ValueError('external internal wire: ' + node.path())
                wires.append([wire.inputIndex(), root.relativePathTo(source), wire.outputIndex()])
        rows.append({'path': '.' if node == root else root.relativePathTo(node),
                     'type': node.type().name(), 'category': node.type().category().name(),
                     'parms': parms, 'wires': wires,
                     'spare_templates': [p.asCode() for p in root.parmTemplateGroup().entries()] if node == root else [],
                     'display': node.isDisplayFlagSet() if node != root and isinstance(node, hou.SopNode) else None,
                     'render': node.isRenderFlagSet() if node != root and isinstance(node, hou.SopNode) else None})
    return sorted(rows, key=lambda row: row['path'])


def _contract(contract):
    if not isinstance(contract, dict) or not {'module_id', 'revision', 'units', 'outputs'} <= set(contract) \
            or not set(contract) <= {'module_id', 'revision', 'units', 'outputs', 'inputs'}:
        raise ValueError('contract requires exactly module_id, revision, units, outputs (inputs optional)')
    _name(contract['module_id'])
    if type(contract['revision']) is not int or contract['revision'] < 1:
        raise ValueError('positive integer contract revision required')
    if contract['units'] not in ('m', 'cm', 'mm'):
        raise ValueError('units must be m/cm/mm')
    outputs = contract['outputs']
    if not isinstance(outputs, list) or not outputs or len(outputs) > 64:
        raise ValueError('one or more public output indices required')
    if any(type(i) is not int or i < 0 or i > 63 for i in outputs) or len(set(outputs)) != len(outputs):
        raise ValueError('public output indices must be unique integers in 0..63')
    inputs = contract.get('inputs', [])
    if not isinstance(inputs, list) or len(inputs) > 64 \
            or any(type(i) is not int or i < 0 or i > 63 for i in inputs) or len(set(inputs)) != len(inputs):
        raise ValueError('declared public input slots must be unique integers in 0..63')
    return json.loads(_json(contract))


def _verify(root, contract):
    h = _h()
    checks = []
    for index in contract['outputs']:
        ports = [n for n in root.children() if n.type().name() == 'output' and n.parm('outputidx').eval() == index]
        if len(ports) != 1 or ports[0].input(0) is None:
            raise ValueError('missing/ambiguous/unconnected public output ' + str(index))
        checks.append(h.verify_network(root, output=ports[0].input(0), output_index=index))
    if any(not c.get('healthy') for c in checks):
        raise ValueError('component public output is not healthy')
    return checks


def component_export(node, filename, contract):
    """Export an owned ordinary SOP subnet to a new $HIP .dshcomponent file.

    node: a current-session-owned ordinary SOP subnet (node or absolute path).
    filename: a NEW absolute .dshcomponent path inside the named HIP directory;
    '$HIP/part_r1.dshcomponent' works. The parent directory must exist; no overwrite.
    contract: exactly {'module_id': ASCII identifier, 'revision': positive integer,
                       'units': 'm'|'cm'|'mm', 'outputs': [public output indices]}.
    outputs is a nonempty list of unique integers in 0..63. Each output must be
    published inside the subnet with sop_set_output(..., output_index=index),
    connected to healthy nonempty geometry. Inputs, external files/Python callbacks
    and custom HDA definitions are not portable in this candidate.

    Example (houdini_exec code, with the Host-assigned HIP already named):
        geo = tab_create('/obj', 'geo', 'help_author')
        module = tab_create(geo, 'subnet', 'part')
        shape = tab_create(module, 'box', 'shape')
        sop_set_output(shape, output_index=0)
        __result__ = component_export(module, '$HIP/help_part_r1.dshcomponent',
                                      {'module_id': 'part', 'revision': 1,
                                       'units': 'm', 'outputs': [0]})

    Same-build native archive; file effects cannot be undone. Returns file,
    sha256 and contract for the parent to verify before explicit trusted import.
    Neither the hash nor a successful export certifies geometry or visual quality.
    """
    h = _h()
    h._cook_control.require_evaluation('component_export')
    root = h._resolve(node)
    contract = _contract(contract)
    target = _path(filename, writing=True)
    before = _snapshot(root, check_owned=True)
    _verify(root, contract)
    with tempfile.TemporaryDirectory(prefix='dsh-component-export-') as temp:
        archive = Path(temp) / 'nodes.cpio'
        root.parent().saveItemsToFile([root], str(archive), save_hda_fallbacks=False)
        payload = archive.read_bytes()
    if before != _snapshot(root, check_owned=True):
        raise ValueError('component changed while exporting')
    data = _json({'schema': 2, 'houdini': hou.applicationVersionString(), 'root_name': root.name(),
                  'contract': contract, 'snapshot': before, 'payload': base64.b64encode(payload).decode('ascii')})
    if len(data) > MAX_BYTES:
        raise ValueError('component archive byte budget exceeded')
    # Exclusive creation: a competing revision is never replaced.
    with target.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {'ok': True, 'file': str(target), 'sha256': _hash(data), 'contract': contract,
            'nodes': len(before), 'scene_writes': 0, 'semantic_status': 'unverified'}


def component_import(parent, filename, expected_sha256, name, *, trusted=False):
    """Import an explicitly trusted, hash-pinned same-build ordinary subnet.

    trusted=True acknowledges executable native node content; hashes do not sandbox
    archives. No automatic child report acceptance. Creates only a new candidate,
    never replaces a live module or its wires. All new identities belong to caller.
    """
    h = _h()
    if trusted is not True:
        raise ValueError('native archives can execute code; explicit trusted=True is required')
    h._cook_control.require_evaluation('component_import')
    parent = h._resolve(parent)
    h._require_owned(parent, 'component_import')
    if parent.childTypeCategory() != hou.sopNodeTypeCategory():
        raise ValueError('SOP parent required')
    name = _name(name)
    if parent.node(name) is not None:
        raise ValueError('component import never overwrites an existing node')
    if not isinstance(expected_sha256, str) or not re.fullmatch('[0-9a-fA-F]{64}', expected_sha256):
        raise ValueError('expected_sha256 must be a 64-character hexadecimal digest')
    expected_sha256 = expected_sha256.lower()
    with _path(filename).open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or _hash(data) != expected_sha256:
        raise ValueError('component content hash mismatch')
    package = json.loads(data)
    if not isinstance(package, dict) or set(package) != {'schema', 'houdini', 'root_name', 'contract', 'snapshot', 'payload'} or package['schema'] != 2:
        raise ValueError('unsupported component schema; re-export a new file from the source subnet (old files are not modified)')
    if package['houdini'] != hou.applicationVersionString():
        raise ValueError('component Houdini build mismatch')
    contract = _contract(package['contract'])
    _name(package['root_name'])
    payload = base64.b64decode(package['payload'], validate=True)
    state = h._capture_tab_user_state(None)
    stage = None
    created = []
    try:
        stage = parent.createNode('subnet', node_name='__component_stage', run_init_scripts=False)
        h._register_owned_node(stage)
        with tempfile.TemporaryDirectory(prefix='dsh-component-import-') as temp:
            archive = Path(temp) / 'nodes.cpio'
            archive.write_bytes(payload)
            stage.loadItemsFromFile(str(archive), ignore_load_warnings=False)
        created = list(stage.children())
        if len(created) != 1 or created[0].name() != package['root_name']:
            raise ValueError('archive root inventory mismatch')
        candidate = created[0]
        if _snapshot(candidate) != package['snapshot']:
            raise ValueError('archive node content differs from export snapshot')
        h._register_owned_node(candidate)
        _verify(candidate, contract)
        # Houdini may recreate identities when relocating nodes across networks.
        # Register only this exact returned subtree, never the destination parent.
        previous_ids = [n.sessionId() for n in (candidate, *candidate.allSubChildren())]
        candidate.setName(name)
        moved = hou.moveNodesTo([candidate], parent)[0]
        created = [moved]
        if _snapshot(moved) != package['snapshot']:
            raise ValueError('relocation changed component references')
        h._register_owned_node(moved)
        live_ids = {n.sessionId() for n in (moved, *moved.allSubChildren())}
        for identity in set(previous_ids) - live_ids:
            h._OWNED_NODE_SESSIONS.pop(identity, None)
        _verify(moved, contract)
        _IMPORT_RECORDS[moved.sessionId()] = {'module_id': contract['module_id'], 'revision': contract['revision'],
                                              'inputs': contract.get('inputs', []), 'sha256': expected_sha256}
        return {'ok': True, 'node': moved.path(), 'sha256': expected_sha256, 'contract': contract,
                'identity': moved.sessionId(), 'semantic_status': 'unverified', 'status': 'candidate'}
    except BaseException:
        for node in created:
            if node.parent() == parent:
                ids = [n.sessionId() for n in (node, *node.allSubChildren())]
                node.destroy()
                for identity in ids:
                    h._OWNED_NODE_SESSIONS.pop(identity, None)
        raise
    finally:
        if stage is not None:
            ids = [n.sessionId() for n in (stage, *stage.allSubChildren())]
            stage.destroy()
            for identity in ids:
                h._OWNED_NODE_SESSIONS.pop(identity, None)
        h._apply_tab_user_state(state)


def _replacement_state(root, *, migratable_public=frozenset()):
    """Current identities and authored channels, independent of cooked geometry.

    External parameter consumers are refused, except references to root spare
    public parameters explicitly listed in migratable_public (handled by the
    migration plan).
    """
    h = _h()
    nodes = _nodes(root)
    members = set(nodes)
    public = {p.path() for p in root.spareParms()}
    rows = []
    external_refs = []
    for node in nodes:
        h._require_owned(node, 'component_replace')
        parms = []
        for parm in node.parms():
            value = _parm_value(parm)
            parms.append([parm.name(), value, parm.isLocked()])
            for consumer in parm.parmsReferencingThis():
                if consumer.node() in members:
                    continue
                if node is root and parm.path() in public and parm.tuple().name() in migratable_public:
                    continue
                external_refs.append(consumer.path())
        rows.append({'id': node.sessionId(), 'path': node.path(), 'type': node.type().name(), 'parms': parms,
                     'templates': node.parmTemplateGroup().asDialogScript(),
                     'wires': [(w.inputIndex(),
                                ('subnet', w.subnetIndirectInput().parent().sessionId(), w.subnetIndirectInput().number())
                                if w.subnetIndirectInput() is not None else ('node', w.inputNode().sessionId()),
                                w.outputIndex()) for w in node.inputConnections()],
                     'bypass': node.isBypassed() if isinstance(node, hou.SopNode) else False})
    if external_refs:
        raise ValueError('component replacement cannot migrate external parameter consumers '
                         'outside the declared migration plan: ' + ', '.join(external_refs[:8]))
    return rows


def _migration(value):
    """Explicit migration plan: per-slot input mapping and named public parameters."""
    if value is None:
        return {'inputs': {}, 'public_parms': []}
    if not isinstance(value, dict) or not set(value) <= {'inputs', 'public_parms'}:
        raise ValueError('migration may only declare inputs and public_parms')
    inputs = value.get('inputs', {})
    if not isinstance(inputs, dict):
        raise ValueError('migration inputs must map unique integer slots 0..63 to unique target slots')

    def _slot(key):
        # The Host transport is JSON: object keys arrive as digit strings. The
        # canonical JSON form is accepted and normalized to the integer slot it
        # names; anything else stays rejected.
        if type(key) is int:
            return key
        if isinstance(key, str) and re.fullmatch(r'(0|[1-9][0-9]*)', key):
            return int(key)
        return None

    normalized = {}
    for key, target in inputs.items():
        slot = _slot(key)
        if slot is None or type(target) is not int or not 0 <= slot <= 63 or not 0 <= target <= 63:
            raise ValueError('migration inputs must map unique integer slots 0..63 to unique target slots')
        if slot in normalized:
            raise ValueError(f'migration inputs declare slot {slot} twice with different spellings '
                             f'({normalized[slot]!r} and {target!r}); the plan is ambiguous and refused')
        normalized[slot] = target
    if len(set(normalized.values())) != len(normalized):
        raise ValueError('migration inputs must map unique integer slots 0..63 to unique target slots')
    names = value.get('public_parms', [])
    if not isinstance(names, list) or any(not isinstance(n, str) or not NAME.fullmatch(n) for n in names) \
            or len(set(names)) != len(names):
        raise ValueError('migration public_parms must be unique parameter names')
    return {'inputs': normalized, 'public_parms': list(names)}


def _input_wires(node):
    return [{'slot': w.inputIndex(), 'source': w.inputNode().path(), 'identity': w.inputNode().sessionId(),
             'output': w.outputIndex()} for w in node.inputConnections()]


def _capture_parm(parm):
    """Restorable snapshot of one live channel; expression-driven keys cannot be restored.

    Segment functions (bezier()/linear()/...) are plain animation data and migrate;
    any other keyframe expression is refused rather than rewritten. The snapshot
    carries the Keyframe objects returned by keyframes() VERBATIM - frame, value,
    slopes, acceleration and segment state all survive - instead of rebuilding a
    partial copy field by field.
    """
    keys = parm.keyframes()
    if keys:
        for key in keys:
            # Per-key segment initialization: the segment state must reset for
            # every key. The first key of a curve routinely carries no
            # expression, so an uninitialized `segment` would raise NameError
            # there - and a leaked previous key's segment could misjudge this
            # key's refusal.
            segment = None
            try:
                if key.isExpressionSet():
                    segment = key.expression()
            except hou.OperationFailed:
                continue
            if segment is not None and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\(\)', segment.strip()):
                raise ValueError('keyframes driven by expressions are not migrated: ' + parm.path())
        return ('keys', keys)
    if parm.parmTemplate().type() == hou.parmTemplateType.String:
        return ('string', parm.unexpandedString())
    return ('value', parm.eval())


def _restore_parm(parm, captured):
    kind, payload = captured
    if kind == 'keys':
        parm.deleteAllKeyframes()
        parm.setKeyframes(list(payload))
        # Per-key segment initialization: a batch set can grow a spurious
        # incoming acceleration on keys whose captured segment carries none
        # (a trailing linear() key after a bezier key grows one). Rebuild such
        # keys minimally so every restored key holds exactly its captured
        # segment state - slopes, acceleration and segment expression alike.
        by_frame = {key.frame(): key for key in parm.keyframes()}
        for source in payload:
            target = by_frame.get(source.frame())
            if target is None:
                continue
            try:
                source.inAccel()
                captured_set = True
            except hou.KeyframeValueNotSet:
                captured_set = False
            try:
                target.inAccel()
                restored_set = True
            except hou.KeyframeValueNotSet:
                restored_set = False
            if captured_set or not restored_set:
                continue
            minimal = hou.Keyframe(source.value())
            minimal.setFrame(source.frame())
            if source.isExpressionSet():
                minimal.setExpression(source.expression(), source.expressionLanguage())
            parm.setKeyframe(minimal)
        return
    parm.deleteAllKeyframes()
    parm.set(payload)


def _resolve_channel_reference(node, path):
    """Absolute target of one HScript channel reference, relative to `node`.

    '..' climbs parents; an absolute path is taken as-is; everything else hangs
    under the consumer node itself (Houdini's own resolution for parm
    expressions). The result is normalized, so redundant navigation inside the
    reference ('.', 'a/../b', doubled slashes) still resolves to the same
    network location. Returns a node path + optional channel suffix, not a
    hou.Parm.
    """
    if path.startswith('/'):
        return posixpath.normpath(path)
    base = node
    parts = path.split('/')
    while parts and parts[0] == '..':
        base = base.parent()
        parts = parts[1:]
    rest = '/'.join(part for part in parts if part and part != '.')
    return posixpath.normpath((base.path() + '/' + rest) if rest else base.path())


_CH_CALL = re.compile(r"(ch[a-zA-Z]*)\s*\(")


class _ExpressionLexError(ValueError):
    pass


def _hscript_strings(expression):
    """Segment an HScript channel expression into code and string literal runs.

    Returns a list of (kind, start, end) with kind 'code' or 'string' and
    half-open offsets into `expression`. HScript string literals keep their raw
    text verbatim: a backslash does not change the value, it only stops the
    next character from terminating the literal (probed on H21: "a\"b"
    evaluates to a\"b, not a"b). HScript channel expressions have no comment
    syntax, so every non-string byte is code. Channel-call shaped text inside
    a string segment is data and must never be rewritten.
    """
    segments = []
    i, n, code_start = 0, len(expression), 0
    while i < n:
        char = expression[i]
        if char == '"' or char == "'":
            j = i + 1
            while j < n:
                if expression[j] == '\\':
                    j += 2
                    continue
                if expression[j] == char:
                    break
                j += 1
            if j >= n:
                raise _ExpressionLexError('unterminated string literal starting at offset %d in %r' % (i, expression))
            if i > code_start:
                segments.append(('code', code_start, i))
            segments.append(('string', i, j + 1))
            i = code_start = j + 1
        else:
            i += 1
    if code_start < n:
        segments.append(('code', code_start, n))
    return segments


_CH_CALL = re.compile(r"\b(ch[a-zA-Z]*)\s*\(")


def _repoint_expression(consumer, old, new):
    """Rewrite one consumer expression's references from the old component to the
    candidate, preserving each reference's form and the rest of the expression.

    Expression-language scope: ONLY HScript channel expressions are rewritten.
    A python-language consumer is refused before any write (its reference
    syntax and semantics are out of scope). The scan is lexical: channel calls
    are recognized in code segments only; string literals are data whose raw
    text is preserved verbatim, so an ordinary string that happens to contain
    ch(...) text is never rewritten and survives byte-identical. Only the
    first literal argument of an actual channel call (ch/chf/chi/chs/...) is a
    candidate reference, and only when the reference RESOLVES - relative to
    the consumer node - to the declared old component or a parameter on it.
    Deep-relative references that resolve elsewhere (e.g. ../../part/width from
    a sibling network) are left untouched; a consumer referencing several
    migrated channels is rewritten ONCE for all of them. Any channel-call
    argument that is not a single literal ending the argument (computed
    fragments, variables, nested calls) refuses before any write: it cannot
    be proven independent of the old component. The consumer set comes from
    Houdini's dependency graph (parmsReferencingThis), but every literal
    reference inside a detected consumer is repointed by its RESOLVED target -
    including forms the dependency graph does not track (mid-path '..'
    navigation), so no textual reference into the old component survives the
    migration. Python-language references are invisible to that graph
    (probed), so component_replace additionally audits the other parms of
    every detected consumer node and refuses when one mentions the old
    component instead of silently leaving a stale live reference behind.
    In HOM an expression lives on keyframes, so an expression-driven consumer
    has keys; value-keyframed consumers without an expression are refused.
    """
    try:
        expression = consumer.expression()
        language = consumer.expressionLanguage()
    except hou.OperationFailed:
        raise ValueError('external consumer is not expression-driven (keyframed consumers are not migrated): '
                         + consumer.path()) from None
    if language != hou.exprLanguage.Hscript:
        raise ValueError(f'unsupported expression language {language} in {consumer.path()}: '
                         'only HScript channel expressions are migrated; the consumer is refused before any write')
    old_abs, new_abs = old.path(), new.path()
    try:
        segments = _hscript_strings(expression)
    except _ExpressionLexError as error:
        raise ValueError(f'unsupported reference form in {consumer.path()}: {error}; '
                         'the consumer is refused before any write') from None
    string_ends = {start: end for kind, start, end in segments if kind == 'string'}
    rewritten_parts = []
    pos, matched = 0, False
    refusal = None
    for kind, start, end in segments:
        if kind != 'code':
            continue
        for call in _CH_CALL.finditer(expression, start, end):
            # The argument scan runs over the whole expression: only spaces may
            # sit between the call's parenthesis and its literal, and spaces are
            # always code, so the first non-space byte decides.
            i = call.end()
            while i < len(expression) and expression[i] in ' \t':
                i += 1
            if i >= len(expression) or expression[i] not in '"\'' or i not in string_ends:
                refusal = (f'channel call {call.group(1)}(...) takes a non-literal argument; '
                           f'cannot prove it is independent of {old_abs}')
                break
            string_end = string_ends[i]
            # The literal must END the argument: the next non-space character has
            # to close the call or start another argument. A literal followed by
            # more expression ('..' + "/name", f-strings, format calls) is a
            # fragment of a computed reference - rewriting the literal alone
            # would silently migrate half a reference, so it refuses before any
            # write.
            after = string_end
            while after < len(expression) and expression[after] in ' \t':
                after += 1
            if after >= len(expression) or expression[after] not in '),':
                refusal = (f'channel call {call.group(1)}(...) takes a computed argument; the literal '
                           f'{expression[i:string_end]} is embedded in a larger expression and cannot '
                           f'be proven independent of {old_abs}')
                break
            path = expression[i + 1:string_end - 1]
            resolved = _resolve_channel_reference(consumer.node(), path)
            suffix = None
            if resolved == old_abs:
                suffix = ''
            elif resolved.startswith(old_abs + '/'):
                suffix = resolved[len(old_abs):]
            new_literal = None
            if suffix is not None:
                if path.startswith('/'):
                    new_literal = new_abs + suffix
                else:
                    climb = consumer.node()
                    climb_prefix = ''
                    parts = path.split('/')
                    while parts and parts[0] == '..':
                        climb_prefix += '../'
                        climb = climb.parent()
                        parts = parts[1:]
                    new_literal = climb_prefix + climb.relativePathTo(new) + suffix
                matched = True
            elif resolved == new_abs or resolved.startswith(new_abs + '/') or hou.node(resolved) is None:
                pass  # a reference to the candidate or to a (possibly absent) channel elsewhere: leave it
            else:
                refusal = (f'channel call {call.group(1)}("{path}") resolves to the network node {resolved}, '
                           f'not a channel; cannot prove it is independent of {old_abs}')
            rewritten_parts.append(expression[pos:i + 1])
            if new_literal is not None:
                rewritten_parts.append(new_literal)
            else:
                rewritten_parts.append(path)
            rewritten_parts.append(expression[string_end - 1])
            pos = string_end
        if refusal is not None:
            break
    rewritten_parts.append(expression[pos:])
    if refusal is not None:
        raise ValueError(f'unsupported reference form in {consumer.path()}: {refusal}; '
                         'the consumer is refused before any write')
    rewritten = ''.join(rewritten_parts)
    if not matched:
        raise ValueError('unsupported consumer reference form: ' + consumer.path())
    return expression, language, rewritten


def _expected_contract(value):
    if (not isinstance(value, dict) or set(value) != {'module_id', 'revision'}
            or not isinstance(value['module_id'], str) or not NAME.fullmatch(value['module_id'])
            or not isinstance(value['revision'], int) or isinstance(value['revision'], bool)
            or value['revision'] < 1):
        raise ValueError('expected_contract must contain exactly module_id and a positive integer revision')
    return value


def component_replace(node, candidate, *, dry_run=True, expected_plan=None, expected_contract=None, migration=None):
    """Preview/commit an explicit replacement, retaining the old subnet.

    Both subnets must belong to this author and have the same parent. No node is
    deleted or renamed. Output wires always migrate; connected root inputs and
    public parameter values/keys with their external expression consumers migrate
    (public parameters are declared by their tuple name and migrate with every
    channel; channel-level declarations are refused, never partially migrated).
    only when the explicit migration plan declares them (per-slot input mapping,
    named public parameters). Undeclared inputs or consumers refuse the commit —
    nothing is guessed by position. Commit requires the unchanged preview hash and
    identities; a mismatch names the drifted side (old component manual edits are a
    retained local fork, candidate edits, consumer wiring changes, or migration
    drift). expected_contract pins the candidate to a module_id/revision recorded
    by component_import in this session, refusing a late older draft. Any commit
    failure restores wires, expressions and parameter values in reverse order.
    This checks network health, not visual quality or cross-component contacts;
    rerun those afterward.
    """
    h = _h()
    h._cook_control.require_evaluation('component_replace')
    old, new = h._resolve(node), h._resolve(candidate)
    if old == new or old.parent() != new.parent():
        raise ValueError('distinct ordinary subnets with the same parent required')
    h._require_owned(old.parent(), 'component_replace')
    record = _IMPORT_RECORDS.get(new.sessionId())
    if expected_contract is not None:
        _expected_contract(expected_contract)
        if record is None:
            raise ValueError('candidate provenance is unknown in this session; '
                             'import it with component_import or drop expected_contract')
        if record['module_id'] != expected_contract['module_id'] or record['revision'] != expected_contract['revision']:
            raise ValueError('candidate contract is stale or unexpected: expected %s revision %s, session holds %s revision %s; '
                             'a late older draft is refused'
                             % (expected_contract['module_id'], expected_contract['revision'],
                                record['module_id'], record['revision']))
    migration = _migration(migration)

    def _spare_channels(root):
        """Declared-name -> spare channels. spareParms() yields per-channel Parm
        objects; a multi-channel tuple appears as name+'x/y/z' style channels and
        its tuple name is the only canonical declaration that preserves every
        channel. Channel-level declarations are refused below, never partially
        migrated."""
        channels = {}
        for parm in root.spareParms():
            channels.setdefault(parm.tuple().name(), []).append(parm)
        return channels

    public_spares = _spare_channels(old)
    new_spares = _spare_channels(new)
    # Plan validation runs before the state scan so a channel-level declaration
    # is reported as itself, not masked by an unrelated external-ref error.
    for name in migration['public_parms']:
        if name not in public_spares:
            owner = next((tuple_name for tuple_name, chan in public_spares.items()
                          if any(p.name() == name for p in chan)), None)
            if owner is not None:
                raise ValueError(f'public parameter {name!r} is one channel of tuple {owner!r}; '
                                 f'declare the tuple name {owner!r} so every channel migrates')
            raise ValueError('declared public parameter missing on the old component: ' + name)
        if name not in new_spares:
            raise ValueError('candidate lacks the declared public parameter: ' + name)
        if len(public_spares[name]) != len(new_spares[name]):
            raise ValueError('candidate public parameter arity differs from the old component: ' + name)
        if [p.parmTemplate().type() for p in public_spares[name]] != [p.parmTemplate().type() for p in new_spares[name]]:
            raise ValueError('candidate public parameter type differs from the old component: ' + name)
    old_state, new_state = _replacement_state(old, migratable_public=frozenset(migration['public_parms'])), \
        _replacement_state(new)
    old_inputs = _input_wires(old)
    for row in old_inputs:
        source = hou.nodeBySessionId(row['identity'])
        if source is None or source.path() != row['source']:
            raise ValueError('input source identity changed')
        h._require_owned(source, 'component_replace input source')
        if row['slot'] not in migration['inputs']:
            raise ValueError('connected old component input slot %d is not covered by the migration plan' % row['slot'])
    candidate_inputs = _input_wires(new)
    occupied = {row['slot'] for row in candidate_inputs}
    for source_slot, target_slot in migration['inputs'].items():
        if target_slot in occupied:
            raise ValueError('candidate input slot %d is already connected' % target_slot)
    old_record = _IMPORT_RECORDS.get(old.sessionId())
    if old_record is not None and old_record['inputs'] \
            and any(slot not in old_record['inputs'] for slot in migration['inputs']):
        raise ValueError('migration source slot outside the old component declared inputs')
    if record is not None and record['inputs'] \
            and any(slot not in record['inputs'] for slot in migration['inputs'].values()):
        raise ValueError('migration target slot outside the candidate declared inputs')
    wires = []
    for wire in old.outputConnections():
        consumer = wire.outputNode()
        if consumer == new:
            raise ValueError('replacement candidate depends on old component output')
        h._require_owned(consumer, 'component_replace consumer')
        wires.append({'consumer': consumer.path(), 'identity': consumer.sessionId(),
                      'input': wire.inputIndex(), 'output': wire.outputIndex()})
    if not wires:
        raise ValueError('old component has no explicit output consumers')
    if new.outputConnections():
        raise ValueError('candidate already has consumers; refuse implicit shared replacement')
    public = sorted({row['output'] for row in wires})
    _verify(new, {'outputs': public})
    consumers = []
    old_members = set(_nodes(old))
    new_members = set(_nodes(new))
    consumers = []
    consumer_channels = {}
    for name in migration['public_parms']:
        for public_parm in public_spares[name]:
            for consumer in public_parm.parmsReferencingThis():
                if consumer.node() in old_members:
                    continue
                if consumer.node() in new_members:
                    raise ValueError('replacement candidate depends on an old component public parameter: ' + consumer.path())
                h._require_owned(consumer.node(), 'component_replace consumer')
                # A consumer referencing several migrated channels is aggregated:
                # one rewritten expression, one commit - never one row per channel.
                consumer_channels.setdefault(consumer.path(), {'consumer': consumer, 'channels': set()})['channels'].add(public_parm.name())
    # Expression-language audit: Houdini's dependency graph does not track
    # python-language references (probed), so a python parm on a detected
    # consumer node could keep silently reading the retained frozen copy after
    # the replace. Refuse before any write instead of guessing; the audit only
    # covers nodes the graph already reported as consumers.
    for consumer_path, row in consumer_channels.items():
        node = row['consumer'].node()
        for parm in node.parms():
            if parm.path() in consumer_channels:
                continue
            try:
                language_other = parm.expressionLanguage()
                if language_other == hou.exprLanguage.Hscript:
                    continue
                text = parm.expression()
            except hou.OperationFailed:
                continue
            hit = next((form for form in (old.path(), node.relativePathTo(old))
                        if form and form in text), None)
            if hit is not None:
                raise ValueError(f'unsupported expression language {language_other} in {parm.path()}: '
                                 f'the consumer expression mentions the old component ({hit}); only HScript '
                                 'channel expressions are migrated, so the replace refuses before any write')
    for parm_path, row in consumer_channels.items():
        original, language, rewritten = _repoint_expression(row['consumer'], old, new)
        consumers.append({'parm': parm_path, 'channels': sorted(row['channels']),
                          'from': original, 'to': rewritten})
    # Feasibility is checked at preview, not discovered mid-commit.
    for name in migration['public_parms']:
        for old_parm, new_parm in zip(public_spares[name], new_spares[name]):
            _capture_parm(old_parm)
            if new_parm.isLocked():
                raise ValueError('candidate public parameter is locked: ' + new_parm.path())
            _capture_parm(new_parm)
    migration_state = {'plan': migration, 'old_inputs': old_inputs, 'candidate_inputs': candidate_inputs,
                       'consumers': consumers}
    state = {'old': old_state, 'candidate': new_state, 'wires': wires, 'migration': migration_state}
    plan = {'old_identity': old.sessionId(), 'candidate_identity': new.sessionId(), 'sha256': _hash(_json(state)),
            'parts': {side: _hash(_json(state[side])) for side in ('old', 'candidate', 'wires', 'migration')}}
    if dry_run is not False:
        if dry_run is not True:
            raise ValueError('dry_run must be boolean')
        return {'ok': True, 'scene_writes': 0, 'plan': plan, 'consumers': wires, 'contract': record,
                'migration': {'inputs': old_inputs, 'public_parms': migration['public_parms'],
                              'parameter_consumers': consumers},
                'scope': 'declared migration plan only; undeclared inputs/consumers refuse the commit',
                'semantic_status': 'unverified'}
    if expected_plan != plan:
        reasons = []
        if isinstance(expected_plan, dict):
            if expected_plan.get('old_identity') != old.sessionId():
                reasons.append('old component identity changed (recreated node)')
            if expected_plan.get('candidate_identity') != new.sessionId():
                reasons.append('candidate identity changed (recreated node)')
            parts = expected_plan.get('parts')
            if isinstance(parts, dict):
                if parts.get('old') != plan['parts']['old']:
                    reasons.append('old component modified after preview: manual edits are a local fork, '
                                   'the old subnet is retained; re-preview or merge explicitly')
                if parts.get('candidate') != plan['parts']['candidate']:
                    reasons.append('candidate modified after preview')
                if parts.get('wires') != plan['parts']['wires']:
                    reasons.append('output consumers changed after preview')
                if parts.get('migration') != plan['parts']['migration']:
                    reasons.append('migration inputs/parameters/consumers changed after preview')
        detail = ': ' + '; '.join(dict.fromkeys(reasons)) if reasons else ''
        raise ValueError('component replacement plan is stale or absent; no wires changed' + detail)
    moved_inputs = []
    moved_parms = []
    repointed = []
    changed = []
    failures = []
    try:
        for row in old_inputs:
            source = hou.nodeBySessionId(row['identity'])
            if source is None or source.path() != row['source']:
                raise ValueError('input source identity changed')
            target_slot = migration['inputs'][row['slot']]
            # Register the rollback ledger entry BEFORE mutating: a failure raised
            # by the second mutation of this iteration (or mid-way through any
            # later restore) must still see this wire in the ledger.
            moved_inputs.append((row, target_slot))
            old.setInput(row['slot'], None)
            new.setInput(target_slot, source, row['output'])
        for name in migration['public_parms']:
            for old_parm, new_parm in zip(public_spares[name], new_spares[name]):
                if new_parm.isLocked():
                    raise ValueError('candidate public parameter is locked: ' + new_parm.path())
                captured = _capture_parm(new_parm)
                moved_parms.append((new_parm, captured))
                _restore_parm(new_parm, _capture_parm(old_parm))
        for row in consumers:
            consumer = hou.parm(row['parm'])
            if consumer is None or consumer.expression() != row['from']:
                raise ValueError('consumer expression changed')
            language = consumer.expressionLanguage()
            repointed.append((consumer, row['from'], language))
            consumer.setExpression(row['to'], language)
        for name in migration['public_parms']:
            for old_parm, new_parm in zip(public_spares[name], new_spares[name]):
                expected = {row['parm'] for row in consumers if old_parm.name() in row['channels']}
                lingering = {p.path() for p in old_parm.parmsReferencingThis()} & expected
                arrived = {p.path() for p in new_parm.parmsReferencingThis()} & expected
                if lingering or arrived != expected:
                    raise ValueError('consumer reference did not migrate to the candidate public parameter: '
                                     + old_parm.path())
        for row in wires:
            consumer = hou.nodeBySessionId(row['identity'])
            if consumer is None or consumer.path() != row['consumer']:
                raise ValueError('consumer identity changed')
            consumer.setInput(row['input'], new, row['output'])
            changed.append((consumer, row))
        for consumer, _ in changed:
            result = h.cook_node(consumer)
            if not result.get('healthy'):
                raise ValueError('replacement consumer is not healthy')
        _IMPORT_RECORDS.pop(new.sessionId(), None)
        return {'ok': True, 'node': new.path(), 'retained_previous': old.path(), 'consumers': wires,
                'contract': record, 'migrated': {'inputs': len(moved_inputs), 'public_parms': migration['public_parms'],
                                                 'parameter_consumers': len(repointed)},
                'semantic_status': 'unverified',
                'scope': 'declared migration plan; old module retained, not renamed or deleted'}
    except BaseException as error:
        for consumer, row in reversed(changed):
            try:
                consumer.setInput(row['input'], old, row['output'])
            except Exception as restore_error:
                failures.append(str(restore_error))
        for consumer, original, language in reversed(repointed):
            try:
                consumer.setExpression(original, language)
            except Exception as restore_error:
                failures.append(str(restore_error))
        for target, captured in reversed(moved_parms):
            try:
                _restore_parm(target, captured)
            except Exception as restore_error:
                failures.append(str(restore_error))
        for row, target_slot in reversed(moved_inputs):
            try:
                source = hou.nodeBySessionId(row['identity'])
                new.setInput(target_slot, None)
                if source is not None:
                    old.setInput(row['slot'], source, row['output'])
            except Exception as restore_error:
                failures.append(str(restore_error))
        if failures:
            raise RuntimeError('component replacement restoration failed: ' + '; '.join(failures)) from error
        raise
