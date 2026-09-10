"""Optional UI composition and structural diagnostics, independent of asset recipes."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import math
import re


def expand_layout(layout):
    """Expand opt-in components to editable primitive specs; never inject callbacks."""
    budget = [0]
    def expand(items, depth=0):
        if not isinstance(items, (list, tuple)) or depth > 12:
            raise ValueError('layout requires lists with at most 12 nesting levels')
        result = []
        for source in items:
            budget[0] += 1
            if budget[0] > 512 or not isinstance(source, dict):
                raise ValueError('layout supports at most 512 object entries')
            item = deepcopy(source)
            component = item.pop('component', None)
            if component is None:
                if 'parms' in item:
                    item['parms'] = expand(item['parms'], depth+1)
                result.append(item)
                continue
            allowed = {
                'row': {'parms'},
                'section': {'name', 'label', 'parms', 'enabled', 'collapsed', 'header_parm', 'help'},
                'remap': {'name', 'label', 'enabled', 'ramp_type', 'help'},
                'repeater': {'name', 'label', 'parms', 'style', 'count', 'label_ref', 'help'},
            }
            if component not in allowed or set(item) - allowed[component]:
                raise ValueError(f'unknown component/fields: {component}')
            if component == 'row':
                row = expand(item.get('parms'), depth+1)
                if not row or any(p['type'] in ('folder', 'ramp') for p in row):
                    raise ValueError('row needs leaf controls, without folders/ramps')
                for index, p in enumerate(row):
                    p['join_next'] = index < len(row)-1
                result.extend(row)
                continue
            name = item.get('name')
            if not isinstance(name, str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', name):
                raise ValueError('component name must be a stable identifier')
            label = item.get('label', name)
            if 'enabled' in item and type(item['enabled']) is not bool:
                raise ValueError('component enabled must be boolean')
            if component == 'remap':
                result.extend([
                    {'type': 'toggle', 'name': name+'_enabled', 'label': label,
                     'default': item.get('enabled', False), 'help': item.get('help', '')},
                    {'type': 'ramp', 'name': name+'_ramp', 'label': label,
                     'ramp_type': item.get('ramp_type', 'float'), 'show_controls': False,
                     'hide_when': '{ '+name+'_enabled == 0 }'},
                ])
                continue
            children = expand(item.get('parms'), depth+1)
            if component == 'repeater':
                style = item.get('style', 'tabs')
                if style not in ('tabs', 'list', 'scroll'):
                    raise ValueError('repeater style must be tabs/list/scroll')
                tags = {'sidefx::multi_label': item['label_ref']} if item.get('label_ref') else {}
                result.append({'type': 'folder', 'name': name, 'label': label,
                    'folder_type': 'multiparm_'+style, 'default': item.get('count', 0),
                    'tags': tags, 'parms': children, 'help': item.get('help', '')})
                continue
            collapsed = item.get('collapsed', False)
            if type(collapsed) is not bool:
                raise ValueError('collapsed must be boolean')
            tags = {'group_default': '0' if collapsed else '1'}
            section = {'type': 'folder', 'name': name, 'label': label,
                       'folder_type': 'collapsible', 'tags': tags, 'parms': children,
                       'help': item.get('help', '')}
            if item.get('header_parm'):
                tags['sidefx::header_parm'] = item['header_parm']
            if 'enabled' in item:
                toggle_name = name+'_enabled'
                result.append({'type': 'toggle', 'name': toggle_name, 'label': label,
                               'default': item['enabled']})
                tags['sidefx::header_toggle'] = toggle_name
                section['disable_when'] = '{ '+toggle_name+' == 0 }'
                def gate_children(items):
                    for child in items:
                        if child['type'] not in ('folder', 'separator', 'label'):
                            prior = child.get('disable_when', '').strip()
                            if prior and not prior.startswith('{'):
                                prior = '{ '+prior+' }'
                            child['disable_when'] = (prior+' '+section['disable_when']).strip()
                        gate_children(child.get('parms', []))
                gate_children(children)
            result.append(section)
        return result
    return expand(layout)


def validate_layout_spec(spec):
    """Strict component path; legacy spec remains independently compatible."""
    common = {'type', 'name', 'label', 'help', 'tags', 'hidden', 'hide_label', 'join_next', 'hide_when', 'disable_when'}
    kinds = {'folder': {'parms', 'folder_type', 'default', 'ends_tab_group', 'tab_hide_when', 'tab_disable_when'},
             'float': {'default', 'min', 'max', 'min_strict', 'max_strict', 'components', 'look'},
             'int': {'default', 'min', 'max', 'min_strict', 'max_strict', 'components', 'look', 'menu'},
             'toggle': {'default'}, 'menu': {'default', 'menu'}, 'string': {'default', 'file'},
             'button': {'callback'}, 'separator': set(), 'label': set(),
             'ramp': {'ramp_type', 'basis', 'points', 'show_controls'}}
    def walk(items):
        for item in items:
            kind = item.get('type')
            if kind not in kinds or set(item) - common - kinds[kind]:
                raise ValueError(f'unknown layout fields/type for {item.get("name")}')
            for key in ('hidden', 'hide_label', 'join_next', 'min_strict', 'max_strict', 'ends_tab_group', 'show_controls'):
                if key in item and type(item[key]) is not bool:
                    raise ValueError(f'{key} must be boolean')
            for key in ('label', 'help', 'hide_when', 'disable_when', 'tab_hide_when', 'tab_disable_when'):
                if key in item and not isinstance(item[key], str):
                    raise ValueError(f'{key} must be string')
            for key in ('min', 'max'):
                if key in item and (type(item[key]) not in (int, float) or not math.isfinite(item[key]) or
                                    kind == 'int' and type(item[key]) is not int):
                    raise ValueError(f'{key} must be finite numeric and match the parameter type')
            if 'min' in item and 'max' in item and item['min'] > item['max']:
                raise ValueError('minimum exceeds maximum')
            if kind == 'toggle' and 'default' in item and type(item['default']) is not bool:
                raise ValueError('toggle default must be boolean')
            walk(item.get('parms', []))
    walk(spec)


def apply_spare_layout(node, layout, code_parm='snippet', dry_run=False):
    """Append UI to one node. Shared components never imply shared HDA edits."""
    import dsh_hou_helpers as h
    from dsh_hda_interfaces import _snapshot, _restore
    if type(dry_run) is not bool:
        raise ValueError('dry_run must be boolean')
    spec = expand_layout(layout)
    validate_layout_spec(spec)
    if not spec:
        raise ValueError('layout must not be empty')
    before = node.parmTemplateGroup()
    names = h._all_template_names(before.entries())
    before_names = set(names)
    templates = [h._build_interface_template(item, f'layout[{i}]', names, {}) for i, item in enumerate(spec)]
    for name in names - before_names:
        if '#' not in name and (node.parm(name) is not None or node.parmTuple(name) is not None):
            raise ValueError(f'layout conflicts with existing channel {name}')
    group = node.parmTemplateGroup()
    for template in templates:
        group.append(template)
    info = [h._template_info(t, 0, 20) for t in group.entries()]
    result = {'node': node.path(), 'mode': 'layout', 'ok': True,
              'created': sorted(names - before_names), 'ui_analysis': analyze_ui(info)}
    if dry_run:
        return {**result, 'dry_run': True, 'applied': False, 'scene_writes': 0, 'interface': info}
    source = node.parm(code_parm)
    if source is not None and source.isLocked():
        raise ValueError('code parameter is locked; cannot refresh dependencies')
    states = _snapshot([node])
    try:
        refreshed = h._apply_spare_interface(node, group, code_parm)
        failures = _restore(states)
        if failures:
            raise RuntimeError(f'spare layout channel restore failed: {failures}')
        # Compare fresh native state with intended template properties; automatic
        # tab-set names may normalize, so follow the ordered tree as HDA layouts do.
        current = node.parmTemplateGroup()
        tail = current.entries()[-len(templates):]
        if len(tail) != len(templates):
            raise RuntimeError('created spare template count mismatch')
        for template, actual in zip(templates, tail):
            if h._template_info(actual, 0, 20) != h._template_info(template, 0, 20):
                # Native tags and tab names normalize. Required leaf properties
                # are checked independently instead of weakening all validation.
                def check(wanted, observed):
                    if wanted.type() != observed.type() or wanted.label() != observed.label():
                        raise RuntimeError('spare template type/label mismatch')
                    for getter in ('conditionals', 'numComponents', 'joinsWithNext', 'isLabelHidden'):
                        if getattr(wanted, getter)() != getattr(observed, getter)():
                            raise RuntimeError(f'spare template {getter} mismatch')
                    for key, value in wanted.tags().items():
                        if observed.tags().get(key) != value:
                            raise RuntimeError(f'spare template tag {key} mismatch')
                    if hasattr(wanted, 'defaultValue') and wanted.defaultValue() != observed.defaultValue():
                        raise RuntimeError('spare template default mismatch')
                    if wanted.type().name() == 'Folder':
                        if wanted.tabConditionals() != observed.tabConditionals():
                            raise RuntimeError('spare tab conditions mismatch')
                        children = observed.parmTemplates()
                        if len(children) != len(wanted.parmTemplates()):
                            raise RuntimeError('spare folder child count mismatch')
                        for a,b in zip(wanted.parmTemplates(), children):check(a,b)
                check(template, actual)
        return {**result, 'applied': True, 'current_state_preserved': True,
                'refreshed_code_parm': refreshed, 'preserved_channels': len(states)}
    except Exception as error:
        failures = []
        try:
            node.setParmTemplateGroup(before, rename_conflicting_parms=False)
        except Exception as restoration_error:
            failures.append(str(restoration_error))
        failures.extend(_restore(states))
        raise h.CheckpointError(f'spare layout failed: {error}; restoration errors={failures}',
            {'ok': False, 'mode': 'layout', 'restored': not failures, 'restore_errors': failures}) from error


def analyze_ui(tree):
    """No HOM or menu execution. Missing local references are advisory, not repair."""
    entries = []
    issues = []
    def walk(items, depth=0, parents=()):
        row = []
        for item in items:
            entries.append((item, depth, parents))
            row.append(item['name'])
            if not item.get('join_next'):
                if len(row) > 3:
                    issues.append({'code': 'dense_row', 'parameters': row[:12],
                                   'message': 'Check narrow-pane readability; long rows may be intentional.'})
                row = []
            walk(item.get('parms', []), depth+1, parents+(item['name'],))
        if row:
            issues.append({'code': 'dangling_join', 'parameters': row,
                           'message': 'Last control joins beyond its sibling group.'})
    walk(tree)
    by_name = {p['name']: p for p, _, _ in entries}
    counts = Counter(p['type'] for p, _, _ in entries)
    references = []
    for item, depth, parents in entries:
        for field in ('conditionals', 'tab_conditionals'):
            for condition in item.get(field, {}).values():
                # Only bare local comparison operands. Complex syntax stays unverified.
                for name in re.findall(r'(?:\{|\s)([A-Za-z_][\w#]*)\s*(?:==|!=|>=|<=|>|<|=~|!~)', condition):
                    references.append((item, field, name))
                for name, value in re.findall(r'([A-Za-z_][\w#]*)\s*(?:==|!=)\s*(-?\d+)\b', condition):
                    target = by_name.get(name, {})
                    tokens = target.get('menu_items', [])
                    if tokens and value not in tokens and any(not str(t).lstrip('-').isdigit() for t in tokens):
                        issues.append({'code': 'menu_condition_token', 'parameter': item['name'],
                                       'reference': name, 'value': value,
                                       'message': 'Check actual menu tokens in UI conditions; an evaluated index is not necessarily a condition token.'})
        tags = item.get('tags', {})
        for field in ('sidefx::header_toggle', 'sidefx::header_parm', 'sidefx::multi_label'):
            if tags.get(field):
                references.append((item, field, tags[field]))
        if tags.get('sidefx::header_toggle') in by_name:
            target = by_name[tags['sidefx::header_toggle']]
            if target['type'] != 'Toggle':
                issues.append({'code': 'header_toggle_type', 'parameter': item['name'], 'reference': target['name']})
            descendants = {p['name'] for p, _, chain in entries if item['name'] in chain}
            if target['name'] in descendants:
                issues.append({'code': 'header_toggle_inside_section', 'parameter': item['name'],
                               'reference': target['name'], 'message': 'Header toggle should be outside the section it controls.'})
        if tags.get('sidefx::header_parm') in by_name:
            descendants = {p['name'] for p, _, chain in entries if item['name'] in chain}
            if tags['sidefx::header_parm'] not in descendants:
                issues.append({'code': 'header_parm_outside_section', 'parameter': item['name'],
                               'reference': tags['sidefx::header_parm']})
    for item, field, reference in references:
        if reference not in by_name:
            issues.append({'code': 'unresolved_reference', 'parameter': item['name'],
                           'field': field, 'reference': reference,
                           'message': 'Not in template tree; verify tuple component, external or dynamic references before changing.'})
    return {'entries': len(entries), 'types': dict(counts),
            'max_depth': max((d for _, d, _ in entries), default=0),
            'header_toggles': sum('sidefx::header_toggle' in p.get('tags', {}) for p, _, _ in entries),
            'tab_conditionals': sum(bool(p.get('tab_conditionals')) for p, _, _ in entries),
            'omitted_children': sum(p.get('parms_omitted', 0) for p, _, _ in entries),
            'issues': issues[:64], 'issues_truncated': len(issues) > 64,
            'scope': 'structural suggestions only; no UI rendering, callback execution or automatic fixes'}
