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
import re
import tempfile

import hou

MAX_BYTES = 32 * 1024 * 1024
MAX_NODES = 1024
NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,79}$')


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
    if not isinstance(contract, dict) or set(contract) != {'module_id', 'revision', 'units', 'outputs'}:
        raise ValueError('contract requires exactly module_id, revision, units, outputs')
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


def _replacement_state(root):
    """Current identities and authored channels, independent of cooked geometry."""
    h = _h()
    nodes = _nodes(root)
    members = set(nodes)
    rows = []
    external_refs = []
    for node in nodes:
        h._require_owned(node, 'component_replace')
        parms = []
        for parm in node.parms():
            value = _parm_value(parm)
            parms.append([parm.name(), value, parm.isLocked()])
            external_refs.extend(p.path() for p in parm.parmsReferencingThis() if p.node() not in members)
        rows.append({'id': node.sessionId(), 'path': node.path(), 'type': node.type().name(), 'parms': parms,
                     'templates': node.parmTemplateGroup().asDialogScript(),
                     'wires': [(w.inputIndex(),
                                ('subnet', w.subnetIndirectInput().parent().sessionId(), w.subnetIndirectInput().number())
                                if w.subnetIndirectInput() is not None else ('node', w.inputNode().sessionId()),
                                w.outputIndex()) for w in node.inputConnections()],
                     'bypass': node.isBypassed() if isinstance(node, hou.SopNode) else False})
    if external_refs:
        raise ValueError('component replacement cannot migrate external parameter consumers: ' + ', '.join(external_refs[:8]))
    return rows


def component_replace(node, candidate, *, dry_run=True, expected_plan=None):
    """Preview/commit explicit output-wire replacement, retaining the old subnet.

    Both subnets must belong to this author and have the same parent. No node is
    deleted or renamed; external parameter consumers are refused. Public values
    are not guessed/copied: prepare and verify candidate controls before preview.
    Commit requires the unchanged preview hash and identities. This checks network
    health, not visual quality or cross-component contacts; rerun those afterward.
    """
    h = _h()
    h._cook_control.require_evaluation('component_replace')
    old, new = h._resolve(node), h._resolve(candidate)
    if old == new or old.parent() != new.parent():
        raise ValueError('distinct ordinary subnets with the same parent required')
    h._require_owned(old.parent(), 'component_replace')
    old_state, new_state = _replacement_state(old), _replacement_state(new)
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
    # Only wire migration is supported. Inbound links must already be configured
    # explicitly on the candidate and participate in the preview fingerprint.
    public = sorted({row['output'] for row in wires})
    _verify(new, {'outputs': public})
    state = {'old': old_state, 'candidate': new_state, 'wires': wires}
    plan = {'old_identity': old.sessionId(), 'candidate_identity': new.sessionId(), 'sha256': _hash(_json(state))}
    if dry_run is not False:
        if dry_run is not True:
            raise ValueError('dry_run must be boolean')
        return {'ok': True, 'scene_writes': 0, 'plan': plan, 'consumers': wires,
                'scope': 'output wires only; candidate controls must already be prepared', 'semantic_status': 'unverified'}
    if expected_plan != plan:
        raise ValueError('component replacement plan is stale or absent; no wires changed')
    changed = []
    try:
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
        return {'ok': True, 'node': new.path(), 'retained_previous': old.path(), 'consumers': wires,
                'semantic_status': 'unverified', 'scope': 'output wires only; no parameter migration or deletion'}
    except BaseException as error:
        failures = []
        for consumer, row in reversed(changed):
            try:
                consumer.setInput(row['input'], old, row['output'])
            except Exception as restore_error:
                failures.append(str(restore_error))
        if failures:
            raise RuntimeError('component replacement restoration failed: ' + '; '.join(failures)) from error
        raise
