"""Native HDA type versions in their source library, and explicit instance switching."""
import os
import re

import hou


def _family(node_type):
    return tuple(node_type.nameComponents()[:3])


def _sections(definition):
    return {name: bytes(section.binaryContents()) for name, section in definition.sections().items()}


def _copy_version(source, library, name):
    source.copyToHDAFile(library, new_name=name)
    hou.hda.reloadFile(library)


def create_version(node, version, *, dry_run=False, allow_foreign=None):
    import dsh_hou_helpers as h
    from dsh_hda_interfaces import (require_definition_owned, _replace_bytes,
                                    _refresh_created_definition, register_created_definition,
                                    _OWNED_DEFINITIONS, _definition_key)
    n, source = h._hda_definition(node)
    if not isinstance(version, str) or not re.fullmatch(r'\d+(?:\.\d+)*', version):
        raise ValueError('version must be a native numeric type suffix, e.g. 1.1; not Version metadata')
    if type(dry_run) is not bool:
        raise ValueError('dry_run must be boolean')
    # The source definition is read, never its instance's unsaved contents.
    owned = require_definition_owned(source, 'hda_version', allow_foreign)
    library = source.libraryFilePath()
    old_type = n.type().name()
    old_version = n.type().nameComponents()[3]
    base = old_type[:-(len(old_version) + 2)] if old_version else old_type
    name = base + '::' + version
    category = n.type().category()
    definitions = list(hou.hda.definitionsInFile(library))
    if name in category.nodeTypes() or any(d.nodeTypeCategory() == category and d.nodeTypeName() == name for d in definitions):
        raise ValueError(f'Exact target type {name} already exists; inspect/switch to it or choose a new version, never overwrite it')
    plan = {'ok': True, 'dry_run': dry_run, 'applied': False, 'source_type': old_type,
            'type': name, 'type_version': version, 'hda_file': library,
            'source_library': library, 'instances_migrated': 0,
            'copied': 'saved definition; unsaved instance contents excluded',
            'source_matches_definition': n.matchesCurrentDefinition()}
    if dry_run:
        return dict(plan, scene_writes=0)
    with open(library, 'rb') as stream:
        original = stream.read()
    before = {(d.nodeTypeCategory().name(), d.nodeTypeName()): _sections(d) for d in definitions}
    source_key = _definition_key(source)
    target_key = (source_key[0], category.name(), name)
    prior_owners = {key: dict(value) for key, value in _OWNED_DEFINITIONS.items() if key[0] == source_key[0]}
    try:
        # Library edits are not covered by the enclosing scene undo group.
        with hou.undos.disabler():
            _copy_version(source, library, name)
            target_type = category.nodeTypes().get(name)
            target = target_type.definition() if target_type else None
            if target is None or os.path.normcase(os.path.realpath(target.libraryFilePath())) != os.path.normcase(os.path.realpath(library)):
                raise RuntimeError('new version did not resolve to its source library')
            after = {(d.nodeTypeCategory().name(), d.nodeTypeName()): _sections(d)
                     for d in hou.hda.definitionsInFile(library)}
            if set(after) != set(before) | {(category.name(), name)} or any(after.get(key) != value for key, value in before.items()):
                raise RuntimeError('existing library definitions changed while appending version')
            # Foreign library authority remains one-call. Creating a type inside
            # someone else's library must not silently claim that shared file.
            if owned:
                _refresh_created_definition(source)
                register_created_definition(target)
    except Exception as error:
        failures = []
        with hou.undos.disabler():
            try:
                for definition in hou.hda.definitionsInFile(library):
                    if definition.nodeTypeCategory() == category and definition.nodeTypeName() == name:
                        definition.destroy()
            except Exception as restore_error:
                failures.append(str(restore_error))
            try:
                _replace_bytes(library, original)
                hou.hda.reloadFile(library)
                with open(library, 'rb') as stream:
                    restored_file = stream.read()
                if restored_file != original or name in category.nodeTypes():
                    failures.append('library/type restoration readback mismatch')
                restored_definitions = {(d.nodeTypeCategory().name(), d.nodeTypeName()): _sections(d)
                                        for d in hou.hda.definitionsInFile(library)}
                if restored_definitions != before:
                    failures.append('definition sections differ after restoration')
            except Exception as restore_error:
                failures.append(str(restore_error))
        _OWNED_DEFINITIONS.pop(target_key, None)
        _OWNED_DEFINITIONS.update(prior_owners)
        raise h.CheckpointError(f'hda_version failed: {error}; restoration errors={failures}',
                                {'ok': False, 'restored': not failures, 'restore_errors': failures,
                                 'scope': 'this call library/new type; external callbacks excluded'}) from error
    return dict(plan, applied=True, definition_version_metadata=target.version(),
                next_action='Use hda_switch_version on explicitly selected instances, then edit the new definition. Existing instances retain their type.')


def switch_version(node, type_name, *, dry_run=False, allow_foreign=None):
    import dsh_hou_helpers as h
    n, source = h._hda_definition(node)
    if type(dry_run) is not bool:
        raise ValueError('dry_run must be boolean')
    h._require_owned(n, 'hda_switch_version', allow_foreign)
    if not isinstance(type_name, str) or not type_name:
        raise ValueError('type_name must be an exact installed type name from tool_inspect')
    target_type = n.type().category().nodeTypes().get(type_name)
    target = target_type.definition() if target_type else None
    if target is None or _family(target_type) != _family(n.type()):
        raise ValueError('target must be an installed HDA version with the same scope, namespace and base name')
    if not n.matchesCurrentDefinition():
        raise ValueError('source has unlocked contents; save/lock or explicitly discard through hda_edit before switching versions')
    descendants = list(n.allSubChildren())
    for child in descendants:
        h._require_owned(child, 'hda_switch_version replaced descendant', allow_foreign)
    result = {'ok': True, 'dry_run': dry_run, 'applied': False, 'node': n.path(),
              'source_type': n.type().name(), 'type': type_name,
              'source_library': source.libraryFilePath(), 'hda_file': target.libraryFilePath(),
              'affected_instances': [n.path()], 'keep_parms': True, 'keep_network_contents': False,
              'verification_scope': 'native type switch and common parameters; callbacks/external effects and semantic behavior require separate verification'}
    if dry_run or n.type() == target_type:
        return dict(result, scene_writes=0)
    source_id = int(n.sessionId())
    owner = h._OWNED_NODE_SESSIONS.get(source_id)
    # Native keep_parms preserves matching channels; old internal contents must
    # not overwrite the new version. No descendant is adopted by path or type.
    changed = n.changeNodeType(type_name, keep_name=True, keep_parms=True, keep_network_contents=False)
    if changed.type() != target_type or changed.type().definition() != target:
        raise RuntimeError('native switch resolved to a different type/definition')
    if owner is not None:
        h._OWNED_NODE_SESSIONS[int(changed.sessionId())] = dict(owner)
        if h._CREATION_JOURNAL is not None and source_id in h._CREATION_JOURNAL:
            h._CREATION_JOURNAL.add(int(changed.sessionId()))
        if hou.nodeBySessionId(source_id) is None:
            h._OWNED_NODE_SESSIONS.pop(source_id, None)
    return dict(result, applied=True, node=changed.path(), identity=int(changed.sessionId()),
                matches_definition=changed.matchesCurrentDefinition())
