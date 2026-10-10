"""Bounded, preview-bound HDA lifecycle; never flatten or adopt descendants."""
import hashlib
import json
import os

import hou


def _interface_differences(actual, expected):
    """Compare native templates, including fields omitted by HOM equality.

    DialogScript may replace a separator's empty label with its name even
    though the native templates are identical. Native equality preserves
    properties such as export level that asCode does not recreate, but H21/
    H22 omit help and conditional strings; compare those explicitly, including
    folder children and tab conditionals.
    """
    differences = []

    def compare(entries, reference, parent=''):
        names = tuple(t.name() for t in entries)
        reference_names = tuple(t.name() for t in reference)
        if names != reference_names:
            differences.append(f'{parent or "<root>"}: template order/names {names!r} != {reference_names!r}')
        for template, source in zip(entries, reference):
            if template.name() != source.name():
                continue
            path = '/'.join(filter(None, (parent, template.name())))
            fields = []
            if template.type() != source.type():
                fields.append('type')
            else:
                left, right = template, source
                if isinstance(template, hou.FolderParmTemplate):
                    left, right = template.clone(), source.clone()
                    left.setParmTemplates(())
                    right.setParmTemplates(())
                    compare(template.parmTemplates(), source.parmTemplates(), path)
                    if template.tabConditionals() != source.tabConditionals():
                        fields.append('tab conditionals')
                if left != right:
                    fields.append('template properties')
                if template.help() != source.help():
                    fields.append('help')
                if template.conditionals() != source.conditionals():
                    fields.append('conditionals')
            if fields:
                differences.append(path+': '+', '.join(fields))

    compare(actual.entries(), expected.entries())
    return differences


def edit(node, action, *, dry_run=False, expected_plan=None, discard_changes=False, allow_foreign=None):
    import dsh_hou_helpers as h
    from dsh_hda_interfaces import definition_write_guard, require_definition_owned, _snapshot, _restore, parameter_states
    n, definition = h._hda_definition(node)
    if action not in ('unlock', 'save', 'lock', 'promote'):
        raise ValueError('action must be unlock, save, lock or promote; flatten/unpack is not supported')
    if type(dry_run) is not bool or type(discard_changes) is not bool:
        raise ValueError('dry_run/discard_changes must be boolean')
    if discard_changes and action != 'lock':
        raise ValueError('discard_changes is only valid for lock')
    h._require_owned(n, 'hda_edit '+action, allow_foreign)
    if action in ('save', 'promote'):
        require_definition_owned(definition, 'hda_edit '+action, allow_foreign)
    library = definition.libraryFilePath()
    if not os.path.isfile(library) or os.path.islink(library) or os.path.getsize(library)>32*1024*1024:
        raise ValueError('hda_edit requires a regular disk library <=32 MiB')
    descendants = list(n.allSubChildren())
    if len(descendants)>512:
        raise ValueError('hda_edit supports at most 512 descendants')
    affected = list(n.type().instances()) if action in ('save','promote') else [n]
    if len(affected)>64:
        raise ValueError('hda_edit supports at most 64 affected instances')
    for instance in affected:
        h._require_owned(instance, 'hda_edit affected instance', allow_foreign)
    locked = n.isLockedHDA()
    matches = n.matchesCurrentDefinition()
    if action in ('save','promote') and locked:
        raise ValueError('save requires an unlocked authoring instance')
    if action=='lock' and not matches and not discard_changes:
        raise ValueError('lock discards internal edits; explicitly set discard_changes=True after reviewing the plan')
    if action=='lock' and not matches:
        for child in descendants:
            h._require_owned(child, 'hda_edit lock discarded descendant', allow_foreign)
    if action=='save':
        differences=_interface_differences(n.parmTemplateGroup(),definition.parmTemplateGroup())
        if differences:
            raise ValueError('save refuses instance spare/overridden interface; migrate the interface explicitly first: '
                             +'; '.join(differences))
    if action=='promote':
        definition_interface=definition.parmTemplateGroup()
        for other in affected:
            if other != n:
                differences=_interface_differences(other.parmTemplateGroup(),definition_interface)
                if differences:
                    raise ValueError('promote refuses other instance interface overrides at '+other.path()+': '
                                     +'; '.join(differences))
        # This operation promotes an additive interface, never silently deletes
        # or changes existing definition parameter types.
        source_group=n.parmTemplateGroup()
        from dsh_hda_interfaces import _walk
        for template in _walk(definition.parmTemplateGroup().entries()):
            actual=source_group.find(template.name())
            if actual is None or actual.type()!=template.type():
                raise ValueError('promote requires all existing definition templates with unchanged types')
    source = n.asCode(recurse=True)
    if len(source.encode('utf-8'))>2*1024*1024:
        raise ValueError('hda_edit source snapshot exceeds 2 MiB')
    with open(library,'rb') as stream:
        library_hash=hashlib.sha256(stream.read()).hexdigest()
    sections={key:hashlib.sha256(bytes(value.binaryContents())).hexdigest()
              for key,value in definition.sections().items()}
    plan={'node':n.path(),'identity':int(n.sessionId()),'action':action,
          'library':library,'library_sha256':library_hash,'sections':sections,
          'source_sha256':hashlib.sha256(source.encode('utf-8')).hexdigest(),
          'locked':locked,'matches_definition':matches,'discard_changes':discard_changes,
          'affected_instances':[(i.path(),int(i.sessionId())) for i in affected],
          'affected_state_sha256':hashlib.sha256(json.dumps([parameter_states(i) for i in affected],sort_keys=True).encode()).hexdigest(),
          'descendants':[(i.path(),int(i.sessionId())) for i in descendants]}
    revision=hashlib.sha256(json.dumps(plan,sort_keys=True).encode('utf-8')).hexdigest()
    result={k:v for k,v in plan.items() if k not in ('sections','descendants')}
    result.update(ok=True,plan_sha256=revision,dry_run=dry_run,applied=False,
                  descendant_count=len(descendants),
                  discarded_descendants=plan['descendants'] if action=='lock' and not matches else [],
                  promoted_templates=sorted(h._all_template_names(n.parmTemplateGroup().entries())
                      - h._all_template_names(definition.parmTemplateGroup().entries())) if action=='promote' else [],
                  scope='definition lifecycle only; only fresh identities rebuilt for current-session owned instances are registered; no output/callback/GUI validation')
    if dry_run:
        return {**result,'scene_writes':0}
    if expected_plan != revision:
        raise ValueError('missing/stale expected_plan; preview the current asset and affected instances again')
    if action=='unlock':
        n.allowEditingOfContents(propagate=False)
        if n.isLockedHDA():
            raise RuntimeError('unlock readback failed')
    elif action=='lock':
        with h._track_owned_definition_rebuilds([n]):
            n.matchCurrentDefinition()
        if not n.isLockedHDA() or not n.matchesCurrentDefinition():
            raise RuntimeError('lock readback failed')
    elif action=='save':
        with h._track_owned_definition_rebuilds(affected), definition_write_guard(n,'hda_edit save',allow_foreign):
            definition.updateFromNode(n)
            if n.type().definition()!=definition or not os.path.isfile(library):
                raise RuntimeError('saved definition identity/library readback failed')
    else:
        with h._track_owned_definition_rebuilds(affected), definition_write_guard(n,'hda_edit promote',allow_foreign):
            states=_snapshot(affected)
            group=n.parmTemplateGroup()
            if n.type().category()==hou.sopNodeTypeCategory():
                for name in ('label1','label2','label3','label4'):
                    if group.find(name) is not None:
                        group.hide(name,True)
            # Remove the SOURCE overlay before writing the shared interface;
            # writing first causes native multiparm children to merge twice.
            n.removeSpareParms()
            definition.setParmTemplateGroup(group,rename_conflicting_parms=False)
            errors=_restore(states)
            if errors:
                raise RuntimeError('promotion channel restoration failed: '+str(errors))
            definition.updateFromNode(n)
            errors=_restore(states)
            if errors:
                raise RuntimeError('promotion post-save restoration failed: '+str(errors))
            expected=h._all_template_names(group.entries())
            actual=h._all_template_names(definition.parmTemplateGroup().entries())
            if not expected<=actual:
                raise RuntimeError('promoted definition omitted templates')
    with open(library,'rb') as stream:
        after_hash=hashlib.sha256(stream.read()).hexdigest()
    return {**result,'applied':True,'after_library_sha256':after_hash,
            'locked_after':n.isLockedHDA(),'matches_definition_after':n.matchesCurrentDefinition()}
