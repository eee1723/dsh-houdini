"""Read the active native tool registries; never load tools, run scripts or cook.

Rows are current process observations, not an installation or authoring ledger.
HDA candidates and public code are read only for an explicitly selected entry.
"""
from __future__ import annotations

import hashlib
import os

import hou

KINDS = ('node_type', 'shelf', 'panel', 'viewer_state', 'radial')
ORIGINS = ('factory', 'external', 'embedded', 'unknown')


def _path(value):
    if not value or value in ('Embedded', 'session:'):
        return value or None
    return os.path.normpath(hou.text.expandString(value))


def _origin(path):
    if path == 'Embedded' or path and path.startswith('session:'):
        return 'embedded'
    if not path or not os.path.isabs(path):
        return 'unknown'
    root = os.path.normcase(os.path.realpath(hou.text.expandString('$HFS')))
    resolved = os.path.normcase(os.path.realpath(path))
    try:
        return 'factory' if os.path.commonpath((root, resolved)) == root else 'external'
    except ValueError:
        return 'external'


def _node_row(node_type):
    definition = node_type.definition()
    path = _path(definition.libraryFilePath()) if definition is not None else None
    return {'kind': 'node_type', 'name': node_type.name(),
            'label': node_type.description(), 'category': node_type.category().name(),
            'source': path, 'origin': _origin(path),
            'implementation': 'hda' if definition is not None else 'native_or_compiled',
            'hidden': node_type.hidden(), 'deprecated': node_type.deprecated(),
            'editable_definition': definition is not None and path != 'Embedded',
            'edit_permission': 'not_inferred_from_discovery'}


def _registries(kinds, category, needle='', exact_name=None):
    categories = hou.nodeTypeCategories()
    if category is not None and category not in categories:
        raise ValueError('Unknown category; use the exact category name from scene/node observations')
    selected = [categories[category]] if category else sorted(categories.values(), key=lambda c: c.name())
    rows, objects, unavailable = [], {}, []
    def matches(name, label):
        return (exact_name is None or name == exact_name) and (not needle or needle in (name+'\n'+label).casefold())
    if 'node_type' in kinds:
        for cat in selected:
            registry = cat.nodeTypes()
            if exact_name is None:
                candidates = registry.items()
            elif exact_name in registry:
                candidates = [(exact_name, registry[exact_name])]
            else:
                continue
            for name, node_type in candidates:
                if not matches(name, node_type.description()):
                    continue
                row = _node_row(node_type)
                rows.append(row)
                objects[('node_type', cat.name(), name)] = node_type
    if 'shelf' in kinds:
        for name, tool in hou.shelves.tools().items():
            if not matches(name, tool.label()):
                continue
            path = _path(tool.filePath())
            cats = {cat.name() for pane in (hou.paneTabType.NetworkEditor, hou.paneTabType.SceneViewer)
                    for cat in tool.toolMenuCategories(pane)}
            if category and category not in cats:
                continue
            rows.append({'kind': 'shelf', 'name': name, 'label': tool.label(),
                         'categories': sorted(cats), 'source': path, 'origin': _origin(path),
                         'edit_permission': 'not_inferred_from_discovery'})
            objects[('shelf', None, name)] = tool
    if 'panel' in kinds:
        for name, panel in hou.pypanel.interfaces().items():
            if not matches(name, panel.label()):
                continue
            path = _path(panel.filePath())
            rows.append({'kind': 'panel', 'name': name, 'label': panel.label(),
                         'source': path, 'origin': _origin(path),
                         'edit_permission': 'not_inferred_from_discovery'})
            objects[('panel', None, name)] = panel
    if 'viewer_state' in kinds:
        if not hou.isUIAvailable():
            unavailable.append({'kind': 'viewer_state', 'reason': 'GUI registry unavailable'})
        else:
            # Category and viewer pane are part of the native state identity.
            # There is no public universal state-code source API; retain unknown.
            for cat in selected:
                for pane in (hou.paneTabType.SceneViewer, hou.paneTabType.CompositorViewer):
                    for state in cat.viewerStates(pane):
                        if not matches(state.name(), state.description()):
                            continue
                        key = ('viewer_state', cat.name(), state.name())
                        if key in objects:
                            continue
                        node_type = state.nodeType()
                        definition = node_type.definition() if node_type else None
                        source = _path(definition.libraryFilePath()) if definition else None
                        rows.append({'kind': 'viewer_state', 'name': state.name(),
                                     'label': state.description(), 'category': cat.name(),
                                     'source': source, 'origin': _origin(source),
                                     'source_scope': 'associated_hda' if source else 'unavailable',
                                     'node_type': node_type.name() if node_type else None,
                                     'edit_permission': 'not_inferred_from_discovery'})
                        objects[key] = state
    if 'radial' in kinds:
        if not hou.isUIAvailable():
            unavailable.append({'kind': 'radial', 'reason': 'GUI registry unavailable'})
        else:
            for menu in hou.ui.radialMenus():
                if not matches(menu.name(), menu.root().label()):
                    continue
                path = _path(menu.sourceFile())
                rows.append({'kind': 'radial', 'name': menu.name(), 'label': menu.root().label(),
                             'categories': menu.categories(), 'source': path, 'origin': _origin(path),
                             'edit_permission': 'not_inferred_from_discovery'})
                objects[('radial', None, menu.name())] = menu
    return rows, objects, unavailable


def tool_catalog(query='', kind=None, category=None, origin=None, offset=0, limit=64) -> dict:
    """Search current node/Shelf/Panel/state/radial registries with bounded results.

    category is an exact native category, e.g. Sop. Factory means a resource
    under $HFS, not verified publisher identity. Native/compiled node source is
    unknown. No disk scan, code execution, permission inference or cached ledger.
    """
    if not isinstance(query, str) or len(query) > 256:
        raise ValueError('query must be a string <=256 characters')
    if kind is not None and kind not in KINDS:
        raise ValueError('kind must be node_type/shelf/panel/viewer_state/radial or None')
    if origin is not None and origin not in ORIGINS:
        raise ValueError('origin must be factory/external/embedded/unknown or None')
    if type(offset) is not int or not 0 <= offset <= 100000 or type(limit) is not int or not 1 <= limit <= 256:
        raise ValueError('offset must be 0..100000 and limit 1..256')
    needle = query.casefold().strip()
    rows, _, unavailable = _registries([kind] if kind else KINDS, category, needle=needle)
    rows = [row for row in rows if origin is None or row['origin'] == origin]
    rows.sort(key=lambda row: (row['kind'], row.get('category', ''), row['name']))
    return {'ok': True, 'source': 'current Houdini native registries',
            'houdini_version': hou.applicationVersionString(), 'total': len(rows),
            'offset': offset, 'limit': limit, 'entries': rows[offset:offset+limit],
            'truncated': offset+limit < len(rows), 'unavailable': unavailable,
            'scope': 'active entries only; inactive Shelf/Panel/radial definitions and Python import provenance are not enumerated'}


def _code(text, max_chars):
    return {'code': text[:max_chars], 'chars': len(text), 'truncated': len(text) > max_chars,
            'sha256': hashlib.sha256(text.encode('utf8')).hexdigest()}


def _packages(source):
    from dsh_package_discovery import package_sources_for_path
    return package_sources_for_path(source)


def tool_inspect(kind, name, category=None, include_code=False, max_chars=16000) -> dict:
    """Read one exact active tool, definition candidates and optional public code.

    Node types require the exact category, without creating an instance.
    HDA section summaries include sizes; public text code is bounded and opt-in.
    Viewer state source is only its associated HDA when available. Never executes
    callbacks/menus or treats discovery as authorization to modify the source.
    """
    if kind not in KINDS or not isinstance(name, str) or not name or len(name) > 256:
        raise ValueError('use an exact kind and nonempty name from tool_catalog')
    if type(include_code) is not bool or type(max_chars) is not int or not 256 <= max_chars <= 100000:
        raise ValueError('include_code must be bool; max_chars must be 256..100000')
    if kind in ('node_type', 'viewer_state') and category is None:
        raise ValueError('node_type/viewer_state inspection requires an exact category')
    rows, objects, unavailable = _registries([kind], category, exact_name=name)
    row = next((entry for entry in rows if entry['name'] == name), None)
    if row is None:
        return {'ok': False, 'status': 'unavailable' if unavailable else 'not_found', 'unavailable': unavailable}
    key = (kind, category if kind in ('node_type', 'viewer_state') else None, name)
    item = objects[key]
    result = {'ok': True, 'entry': row, 'packages': _packages(row.get('source'))}
    if kind == 'node_type':
        import dsh_hou_helpers as h
        definition = item.definition()
        result['interface'] = [h._template_info(t, 0, 8) for t in item.parmTemplateGroup().entries()]
        candidates = []
        for candidate in item.allInstalledDefinitions():
            path = _path(candidate.libraryFilePath())
            candidates.append({'library_file': path, 'origin': _origin(path),
                               'current': candidate == definition, 'preferred': candidate.isPreferred(),
                               'version': candidate.version()})
        result['definitions'] = candidates
        components = item.nameComponents()
        result['type_version'] = components[3]
        result['definition_version_metadata'] = definition.version() if definition else None
        related = [nt for nt in item.category().nodeTypes().values()
                   if nt.nameComponents()[:3] == components[:3] and nt.definition() is not None]
        result['type_versions'] = [dict(type=nt.name(), type_version=nt.nameComponents()[3],
                                       library_file=_path(nt.definition().libraryFilePath()))
                                   for nt in sorted(related, key=lambda nt: nt.name())[:64]]
        result['type_versions_truncated'] = len(related) > 64
        result['maintenance'] = {'library_file': row.get('source'),
                                 'version_operation': 'hda_version', 'switch_operation': 'hda_switch_version',
                                 'note': 'Maintain the actual source library/package. Version metadata is not the native ::version suffix; fork only for an independent tool.'}
        result['instances'] = [n.path() for n in item.instances()][:256]
        result['instances_truncated'] = len(item.instances()) > 256
        if definition:
            result['sections'] = [{'name': section_name, 'bytes': section.size()}
                                  for section_name, section in sorted(definition.sections().items())]
            if include_code:
                result['code'] = {section_name: _code(section.contents(), max_chars)
                                  for section_name, section in definition.sections().items()
                                  if section_name in ('PythonModule', 'ViewerStateModule', 'OnCreated', 'OnLoaded', 'OnUpdated')}
        else:
            result['code_status'] = 'native_or_compiled_implementation_unavailable'
    elif kind in ('shelf', 'panel'):
        result['help'] = item.help()[:max_chars]
        if include_code:
            result.update(_code(item.script(), max_chars))
        if kind == 'shelf':
            result['language'] = item.language().name()
    elif kind == 'radial':
        result['code_status'] = 'inspect source_file when needed; no arbitrary callbacks executed'
    else:
        result['code_status'] = 'use associated HDA sections when available; standalone registration source unavailable'
    return result
