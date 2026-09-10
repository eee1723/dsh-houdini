"""Bounded definition-interface patches; no callback execution or scene loading."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from contextlib import contextmanager

import hou


def interface_revision(node):
    definition = node.type().definition()
    if definition is None:
        return None
    payload = [node.type().category().name(), node.type().name(),
               definition.libraryFilePath(), definition.sections()['DialogScript'].contents()]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode('utf-8')).hexdigest()


def parameter_states(node):
    """Read channels without evaluating expressions, menus, or cooking geometry."""
    result = []
    parms = node.parms()
    if len(parms) > 512:
        raise ValueError('include_state supports at most 512 channels; use read_parms for selected controls')
    for p in parms:
        keys = p.keyframes()
        result.append({'name': p.name(), 'raw_value': p.rawValue(),
                       'locked': p.isLocked(), 'keyframes': [k.asCode() for k in keys]})
    return result


def _walk(entries):
    for t in entries:
        yield t
        if isinstance(t, hou.FolderParmTemplate):
            yield from _walk(t.parmTemplates())


def _check_supported(group):
    templates = list(_walk(group.entries()))
    if len(templates) > 256:
        raise ValueError('patch supports at most 256 templates')
    names = [t.name() for t in templates]
    if len(set(names)) != len(names):
        raise ValueError('patch refuses ambiguous duplicate template names')
    for t in templates:
        if (t.type() == hou.parmTemplateType.Ramp or
                isinstance(t, hou.FolderParmTemplate) and not t.isActualFolder()):
            raise ValueError('ramp/multiparm interface patches are not yet supported')


def _update(t, fields):
    allowed = {'label', 'help', 'default', 'min', 'max', 'min_strict', 'max_strict',
               'hidden', 'join_next', 'disable_when', 'hide_when'}
    if not isinstance(fields, dict) or not fields or set(fields) - allowed:
        raise ValueError('update needs nonempty supported fields; name/type/callback/menu changes are excluded')
    for key, value in fields.items():
        if key in {'label', 'help', 'disable_when', 'hide_when'} and not isinstance(value, str):
            raise ValueError(f'{key} must be a string')
        if key in {'hidden', 'join_next', 'min_strict', 'max_strict'} and type(value) is not bool:
            raise ValueError(f'{key} must be boolean')
        if key in {'min', 'max'} and (type(value) not in (int, float) or not math.isfinite(value)):
            raise ValueError(f'{key} must be finite numeric')
        if key in {'min', 'max'} and t.type() == hou.parmTemplateType.Int and type(value) is not int:
            raise ValueError(f'{key} must be an integer for an integer template')
    setters = {'label': 'setLabel', 'help': 'setHelp', 'hidden': 'hide', 'join_next': 'setJoinWithNext',
               'min': 'setMinValue', 'max': 'setMaxValue', 'min_strict': 'setMinIsStrict', 'max_strict': 'setMaxIsStrict'}
    for field, setter in setters.items():
        if field in fields:
            if field in {'min', 'max', 'min_strict', 'max_strict'} and t.type() not in (hou.parmTemplateType.Float, hou.parmTemplateType.Int):
                raise ValueError('range fields require numeric templates')
            getattr(t, setter)(fields[field])
    for field, condition in [('disable_when', hou.parmCondType.DisableWhen), ('hide_when', hou.parmCondType.HideWhen)]:
        if field in fields:
            if isinstance(t, hou.FolderParmTemplate):
                raise ValueError('folder conditionals are outside the patch contract')
            value = fields[field]
            if value and not (value.startswith('{') and value.endswith('}')):
                raise ValueError('condition must use Houdini brace syntax or empty string')
            t.setConditional(condition, value)
    if 'default' in fields:
        kind, value = t.type(), fields['default']
        if (t.numComponents() != 1 or t.scriptCallback() or
                getattr(t, 'menuItems', lambda: ())() or
                getattr(t, 'itemGeneratorScript', lambda: '')() or
                any(getattr(t, 'defaultExpression', lambda: ())())):
            raise ValueError('defaults require literal scalar controls without menus/callbacks/default expressions')
        valid = ((kind == hou.parmTemplateType.Float and type(value) in (int, float) and math.isfinite(value)) or
                 (kind == hou.parmTemplateType.Int and type(value) is int and -(2**31) <= value < 2**31) or
                 (kind == hou.parmTemplateType.String and isinstance(value, str)) or
                 (kind == hou.parmTemplateType.Toggle and type(value) is bool))
        if not valid:
            raise ValueError('invalid literal default')
        t.setDefaultValue(value if kind == hou.parmTemplateType.Toggle else (value,))
    if t.type() in (hou.parmTemplateType.Float, hou.parmTemplateType.Int):
        if t.minValue() > t.maxValue():
            raise ValueError('min exceeds max')
        for value in t.defaultValue():
            if (t.minIsStrict() and value < t.minValue()) or (t.maxIsStrict() and value > t.maxValue()):
                raise ValueError('default outside strict limits')
    return t


def _snapshot(instances):
    states = []
    for node in instances:
        if len(node.parms()) > 512:
            raise ValueError('patch supports at most 512 channels per instance')
        for p in node.parms():
            if p.parmTemplate().type() in (hou.parmTemplateType.Button, hou.parmTemplateType.FolderSet):
                continue
            keys = tuple(p.keyframes())
            value = None if keys else (p.unexpandedString() if p.parmTemplate().type() == hou.parmTemplateType.String else p.eval())
            states.append((node, p.name(), keys, value, p.isLocked()))
    return states


def _restore(states):
    def same_value(a, b):
        if isinstance(a, hou.Ramp) and isinstance(b, hou.Ramp):
            return a.basis() == b.basis() and a.keys() == b.keys() and a.values() == b.values()
        return a == b
    errors = []
    for node, name, keys, value, locked in states:
        try:
            p = node.parm(name)
            if p is None:
                raise RuntimeError('original channel missing')
            current_keys = tuple(p.keyframes())
            current = None if current_keys else (p.unexpandedString() if p.parmTemplate().type() == hou.parmTemplateType.String else p.eval())
            if current_keys != keys or not same_value(current, value):
                p.lock(False)
                p.deleteAllKeyframes()
                if keys:
                    p.setKeyframes(keys)
                else:
                    p.set(value, follow_parm_reference=False)
            p.lock(locked)
            actual_keys = tuple(p.keyframes())
            actual = None if actual_keys else (p.unexpandedString() if p.parmTemplate().type() == hou.parmTemplateType.String else p.eval())
            if actual_keys != keys or not same_value(actual, value) or p.isLocked() != locked:
                raise RuntimeError('channel state readback mismatch')
        except Exception as error:
            errors.append(f'{node.path()}/{name}: {error}')
    return errors


def _replace_bytes(path, content):
    fd, temporary = tempfile.mkstemp(prefix='.dsh-hda-', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def definition_write_guard(node, operation, allow_foreign=None):
    # Definition writes are not scene-undo transactions. Recording their root
    # interface restoration in the scene undo group would undo the restoration
    # a second time and replace original channel values with definition defaults.
    with hou.undos.disabler():
        with _definition_write_guard(node, operation, allow_foreign):
            yield


@contextmanager
def _definition_write_guard(node, operation, allow_foreign=None):
    """Restore this call's disk definition/root interfaces on failure; not scene undo."""
    import dsh_hou_helpers as h
    definition = node.type().definition()
    instances = list(node.type().instances())
    if len(instances) > 64:
        raise ValueError('definition write supports at most 64 affected instances')
    for instance in instances:
        h._require_owned(instance, operation + ' affected instance', allow_foreign)
    library = definition.libraryFilePath()
    if not os.path.isfile(library) or os.path.islink(library) or os.path.getsize(library) > 32*1024*1024:
        raise ValueError('definition write requires a regular disk library <=32 MiB')
    with open(library, 'rb') as stream:
        original_file = stream.read()
    sections = {name: bytes(section.binaryContents()) for name, section in definition.sections().items()}
    if sum(map(len, sections.values())) > 32*1024*1024:
        raise ValueError('definition sections exceed 32 MiB')
    interfaces = [(n, n.parmTemplateGroup()) for n in instances]
    states = _snapshot(instances)
    try:
        yield
    except Exception as error:
        failures = []
        try:
            for name, section in list(definition.sections().items()):
                if name not in sections:
                    section.destroy()
            for name, content in sections.items():
                definition.addSection(name, content)
            for instance, interface in interfaces:
                instance.setParmTemplateGroup(interface)
            failures.extend(_restore(states))
            actual = {name: bytes(s.binaryContents()) for name, s in definition.sections().items()}
            if actual != sections:
                failures.append('definition section readback differs after restoration')
        except Exception as restore_error:
            failures.append(str(restore_error))
        try:
            _replace_bytes(library, original_file)
            with open(library, 'rb') as stream:
                if stream.read() != original_file:
                    failures.append('library bytes differ after restoration')
        except Exception as restore_error:
            failures.append(str(restore_error))
        raise h.CheckpointError(f'{operation} failed: {error}; restoration errors={failures}',
            {'ok':False,'phase':'write','restored':not failures,'restore_errors':failures,
             'scope':'this call definition sections/root interfaces/channels/library; external effects excluded'}) from error


def _interface_dialog(original, group):
    """Keep asset header/help/input metadata; replace only native parameter blocks.

    setParmTemplateGroup reintroduces/renames subnet switchers on H21. Emit full
    native templates instead of baseparm references, retaining the original header.
    """
    import dsh_hou_helpers as h
    def blocks(text):
        result, end = [], 0
        for match in re.finditer(r'(?m)^[ \t]*(\w+)[ \t]*\{[ \t]*\r?$', text):
            if match.start() < end:
                continue
            end = h._balanced_block_end(text, match.start())
            if match.group(1) == 'parm' or match.group(1).startswith('group'):
                result.append((match.start(), end))
        return result
    source = blocks(original)
    generated = group.asDialogScript(full_info=True)
    replacement = '\n\n'.join(generated[a:b] for a, b in blocks(generated))
    if not source:
        raise ValueError('patch requires an existing parameter block in DialogScript')
    result = original
    for index in range(len(source)-1, -1, -1):
        a, b = source[index]
        result = result[:a] + (replacement if index == 0 else '') + result[b:]
    return result


def patch_interface(node, edits, expected_sha256, dry_run, allow_foreign):
    import dsh_hou_helpers as h
    try:
        with hou.undos.disabler():
            return _patch_interface(node, edits, expected_sha256, dry_run, allow_foreign)
    except h.CheckpointError:
        raise
    except Exception as error:
        raise h.CheckpointError(str(error), {'ok': False, 'mode': 'patch',
                                'phase': 'preflight', 'scene_writes': 0,
                                'applied': False}) from error


def _patch_interface(node, edits, expected_sha256, dry_run, allow_foreign):
    import dsh_hou_helpers as h
    n, definition = h._hda_definition(node)
    h._require_owned(n, 'hda_set_interface patch', allow_foreign)
    if type(dry_run) is not bool:
        raise ValueError('dry_run must be boolean')
    if not isinstance(edits, list) or not 1 <= len(edits) <= 32:
        raise ValueError('edits must contain 1..32 operations')
    before_hash = interface_revision(n)
    if expected_sha256 != before_hash:
        raise ValueError(f'stale interface revision; current sha256={before_hash}')
    instances = [i for i in n.type().instances() if i.type().definition() == definition]
    if len(instances) > 64:
        raise ValueError('patch supports at most 64 affected instances')
    for instance in instances:
        h._require_owned(instance, 'hda_set_interface patch affected instance', allow_foreign)
        if instance.parmTemplateGroup().asDialogScript(full_info=True) != definition.parmTemplateGroup().asDialogScript(full_info=True):
            raise ValueError('instance-specific interface overrides are not supported by definition patch')
    group = hou.ParmTemplateGroup()
    group.setToDialogScript(definition.sections()['DialogScript'].contents())
    _check_supported(group)
    changes = []
    for edit in edits:
        if not isinstance(edit, dict):
            raise ValueError('each edit must be an object')
        op = edit.get('op')
        if op == 'update' and set(edit) == {'op', 'name', 'fields'}:
            t = group.find(edit['name'])
            if t is None:
                raise ValueError(f'missing template {edit["name"]}')
            before = h._template_info(t, 0, 20)
            group.replace(edit['name'], _update(t, edit['fields']))
            changes.append({'op': op, 'name': edit['name'], 'before': before,
                            'after': h._template_info(group.find(edit['name']), 0, 20)})
        elif op == 'add' and set(edit) <= {'op', 'spec', 'folder'} and 'spec' in edit:
            names = {t.name() for t in _walk(group.entries())}
            spec = edit['spec']
            def validate_spec(item):
                if not isinstance(item, dict):
                    raise ValueError('add spec must be an object')
                kind = item.get('type')
                variants = {'folder': {'parms', 'folder_type'}, 'separator': set(), 'toggle': {'default'},
                            'int': {'default', 'min', 'max', 'min_strict', 'max_strict', 'menu'},
                            'float': {'default', 'min', 'max', 'min_strict', 'max_strict'},
                            'string': {'default', 'file'}, 'menu': {'menu', 'default'}, 'button': {'callback'}}
                allowed = {'type', 'name', 'label', 'help', 'join_next', 'hide_when', 'tags'} | variants.get(kind, set())
                if kind not in variants or set(item) - allowed:
                    raise ValueError('add spec contains unknown fields')
                for field in ('label', 'help', 'callback'):
                    if field in item and not isinstance(item[field], str):
                        raise ValueError(f'add {field} must be a string')
                for field in ('min_strict', 'max_strict', 'join_next'):
                    if field in item and type(item[field]) is not bool:
                        raise ValueError(f'add {field} must be boolean')
                for field in ('min', 'max'):
                    if field in item and (type(item[field]) not in (int, float) or not math.isfinite(item[field]) or
                                          kind == 'int' and type(item[field]) is not int):
                        raise ValueError(f'add {field} must be finite and match numeric type')
                if 'default' in item:
                    value = item['default']
                    valid = ((kind in ('int', 'menu') and type(value) is int and -(2**31) <= value < 2**31) or
                             (kind == 'float' and type(value) in (int, float) and math.isfinite(value)) or
                             (kind == 'toggle' and type(value) is bool) or
                             (kind == 'string' and isinstance(value, str)))
                    if not valid:
                        raise ValueError('add has invalid literal default')
                if kind == 'button':
                    h._validate_section_code('PythonModule', item.get('callback'))
                for child in item.get('parms', []):
                    validate_spec(child)
            validate_spec(spec)
            template = h._build_interface_template(spec, 'add.spec', names, {})
            for added in _walk([template]):
                if added.type() in (hou.parmTemplateType.Int, hou.parmTemplateType.Float):
                    _update(added, {'min': added.minValue()})  # validates limits/default, no scene writes
            folder = edit.get('folder')
            if folder is None:
                group.append(template)
            else:
                parent = group.find(folder)
                if not isinstance(parent, hou.FolderParmTemplate) or not parent.isActualFolder():
                    raise ValueError('add folder must identify an existing regular folder')
                group.appendToFolder(parent, template)
            changes.append({'op': op, 'name': template.name(), 'folder': folder})
        else:
            raise ValueError('supported edits: update(op/name/fields), add(op/spec/folder?); deletion, rename and move are excluded')
    _check_supported(group)
    result = {'node': n.path(), 'mode': 'patch', 'ok': True, 'dry_run': dry_run,
              'before_sha256': before_hash, 'changes': changes,
              'affected_instances': [i.path() for i in instances],
              'scope': 'definition interface and existing channel values/keys/locks; no callback or output validation'}
    original_dialog = definition.sections()['DialogScript'].contents()
    updated_dialog = _interface_dialog(original_dialog, group)
    if dry_run:
        return {**result, 'scene_writes': 0, 'applied': False}
    library = definition.libraryFilePath()
    if not os.path.isfile(library):
        raise ValueError('patch requires a disk-backed HDA library')
    with open(library, 'rb') as stream:
        original_file = stream.read()
    states = _snapshot(instances)
    try:
        definition.addSection('DialogScript', updated_dialog)
        actual = hou.ParmTemplateGroup()
        actual.setToDialogScript(definition.sections()['DialogScript'].contents())
        # Compare the native normalized templates, not just the submitted JSON.
        intended = [h._template_info(t, 0, 20) for t in group.entries()]
        observed = [h._template_info(t, 0, 20) for t in actual.entries()]
        if intended != observed:
            def differences(a, b, path='interface'):
                if isinstance(a, dict) and isinstance(b, dict):
                    return [d for k in a.keys() | b.keys() for d in differences(a.get(k), b.get(k), path+'.'+k)]
                if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == len(b):
                    return [d for i, (x, y) in enumerate(zip(a, b)) for d in differences(x, y, path+f'[{i}]')]
                return [] if a == b else [f'{path}: expected={repr(a)[:300]}, actual={repr(b)[:300]}']
            raise RuntimeError('interface template readback mismatch: ' + '; '.join(differences(intended, observed)[:8]))
        errors = _restore(states)
        if errors:
            raise RuntimeError(f'channel restoration failed: {errors}')
        return {**result, 'applied': True, 'after_sha256': interface_revision(n),
                'current_state_preserved': True, 'preserved_channels': len(states)}
    except Exception as error:
        failures = []
        try:
            definition.addSection('DialogScript', original_dialog)
        except Exception as restore_error:
            failures.append(str(restore_error))
        failures.extend(_restore(states))
        try:
            _replace_bytes(library, original_file)
            if interface_revision(n) != before_hash:
                failures.append('in-memory interface revision differs after rollback')
        except Exception as restore_error:
            failures.append(str(restore_error))
        raise h.CheckpointError(f'interface patch failed: {error}; restoration errors={failures}',
                                {'ok': False, 'mode': 'patch', 'restored': not failures,
                                 'restore_errors': failures, 'scope': 'this call interface/channels/library only'}) from error
