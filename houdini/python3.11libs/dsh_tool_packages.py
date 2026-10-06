"""Direct native Package registration and explicit current-process actions.

The selected source directory is the only resource copy. Config bytes and
Houdini metadata remain the facts; no installation ledger is maintained.
Call all HOM through the Bridge serialized main-thread queue.
"""
from __future__ import annotations

import hashlib
import importlib.machinery
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import types
import xml.etree.ElementTree as ET

import hou
from dsh_package_discovery import native_package_state, package_inspect, read_package_config

HOUDINI_VERSION = re.compile(r'^\d+\.\d+$')
RESOURCE_LOCATIONS = {'HOUDINI_PATH': None, 'PYTHONPATH': 'python',
                      'HOUDINI_OTLSCAN_PATH': 'otls', 'HOUDINI_TOOLBAR_PATH': 'toolbar',
                      'HOUDINI_PYTHON_PANEL_PATH': 'python_panels',
                      'HOUDINI_RADIALMENU_PATH': 'radialmenu',
                      'HOUDINI_VIEWERSTATE_PATH': 'viewer_states',
                      'HOUDINI_VIEWERHANDLE_PATH': 'viewer_handles',
                      'HOUDINI_SCRIPT_PATH': 'scripts', 'HOUDINI_UI_ICON_PATH': 'icons'}


def _reparse(path):
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)
    except FileNotFoundError:
        return False


def _path(value):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('an explicit absolute path is required')
    path = Path(value)
    if not path.is_absolute():
        raise ValueError('an explicit absolute path is required')
    for ancestor in (path, *path.parents):
        if _reparse(ancestor):
            raise ValueError('tool package paths cannot contain links or junctions')
    return path.resolve()


def _outside_hfs(path):
    hfs = hou.getenv('HFS')
    if hfs and path.is_relative_to(Path(hfs).resolve()):
        raise ValueError('package registration never writes inside $HFS')


def _checkpoint(error, phase, **facts):
    import dsh_hou_helpers as helpers
    raise helpers.CheckpointError(str(error), {'ok': False, 'phase': phase, **facts}) from error


def _versions(values):
    if values is None:
        return None
    if not isinstance(values, (list, tuple)) or not values or any(
            not isinstance(value, str) or not HOUDINI_VERSION.fullmatch(value) for value in values):
        raise ValueError('houdini_versions must be a nonempty list of major.minor versions, for example 21.0')
    return sorted(set(values), key=lambda value: tuple(map(int, value.split('.'))))


def _condition(versions):
    return ' or '.join("(houdini_version >= '%s' and houdini_version < '%d.%d')" %
                       (value, int(value.split('.')[0]), int(value.split('.')[1]) + 1) for value in versions)


def tool_package_create(resource_root, package_file, *, houdini_versions=None, enable=True):
    """Create a new native JSON pointing directly to an existing source directory.

    Does not copy resources, create source folders or load the package. The JSON
    parent must already exist; the filename and both locations are explicit.
    """
    try:
        if type(enable) is not bool:
            raise ValueError('enable must be boolean')
        source, target = _path(resource_root), _path(package_file)
        _outside_hfs(target)
        versions = _versions(houdini_versions)
        if not source.is_dir():
            raise ValueError('resource_root must be an existing source directory')
        if target.suffix.lower() != '.json' or not target.parent.is_dir():
            raise ValueError('package_file must be a JSON in an existing directory')
        if target.exists():
            raise ValueError('package_file already exists; existing registrations are never overwritten')
        config = {'enable': _condition(versions) if enable and versions else enable,
                  'env': [{'HOUDINI_PATH': {'value': source.as_posix(), 'method': 'append'}}]}
        content = (json.dumps(config, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    except Exception as error:
        _checkpoint(error, 'package_create_preflight', file_writes=[], scene_writes=0,
                    native_action_attempted=False, restored=True, dispatched=False)
    temporary, published = None, False
    try:
        descriptor, filename = tempfile.mkstemp(prefix='.' + target.name + '-', suffix='.tmp', dir=str(target.parent))
        temporary = Path(filename)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # Atomic exclusive publication never overwrites a competing file.
        os.link(temporary, target)
        published = True
        temporary.unlink()
    except Exception as error:
        cleanup_errors = []
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as cleanup_error:
                cleanup_errors.append(str(cleanup_error))
        _checkpoint(error, 'package_create_failure', package_file=str(target),
                    resource_root=str(source), registration_created=published,
                    package_exists=target.exists(), file_writes=[str(target)] if published else [],
                    cleanup_errors=cleanup_errors, scene_writes=None if published or cleanup_errors else 0,
                    native_action_attempted=False,
                    restored=not published and not cleanup_errors)
    return {'ok': True, 'package_file': str(target), 'resource_root': str(source),
            'config_sha256': hashlib.sha256(content).hexdigest(), 'enabled_in_config': config['enable'],
            'houdini_versions': versions, 'created': True, 'loaded': False,
            'resource_files_copied': False, 'file_writes': [str(target)], 'scene_writes': 0,
            'startup_load_verified': False}


def _within(filename, root):
    if not isinstance(filename, str) or not filename:
        return False
    try:
        # Reject ordinary external files without resolving or stat-ing their
        # ancestors. Links pointing into this root are already disallowed.
        candidate = Path(filename)
        if not candidate.is_absolute() or not Path(os.path.abspath(filename)).is_relative_to(root):
            return False
        return _path(filename).is_relative_to(root)
    except (ValueError, OSError):
        return False


def _module_file(module):
    # PEP 562 __getattr__ and custom ModuleType overrides are executable code.
    if isinstance(module, types.ModuleType):
        return types.ModuleType.__getattribute__(module, '__dict__').get('__file__')
    return None


def _files(root, resource_folder=None):
    """Read resource folders Houdini consumes, never an entire project tree."""
    result = []
    folders = ('otls', 'toolbar', 'python_panels', 'radialmenu', 'viewer_states',
               'viewer_handles', 'scripts', 'python%d.%dlibs' % sys.version_info[:2])
    for folder in [root] if resource_folder is not None else [root / name for name in folders]:
        if not folder.exists():
            continue
        for current, directories, filenames in os.walk(folder):
            current = Path(current)
            if _reparse(current):
                raise ValueError('resource inspection cannot follow links or junctions: ' + str(current))
            directories[:] = [value for value in directories if value not in ('.git', 'node_modules', '__pycache__')]
            for value in directories:
                child = current / value
                if _reparse(child):
                    raise ValueError('resource inspection cannot follow links or junctions: ' + str(child))
            for value in filenames:
                path = current / value
                if _reparse(path):
                    raise ValueError('resource inspection cannot follow links or junctions: ' + str(path))
                result.append(path)
    return sorted(result)


def _entries(root, files, resource_folder=None):
    entries, conflicts = [], []
    for p in files:
        relative = p.relative_to(root).as_posix()
        if p.suffix.lower() in ('.hda', '.otl', '.hdalc', '.hdanc') and (resource_folder == 'otls' or relative.startswith('otls/')):
            for definition in hou.hda.definitionsInFile(str(p)):
                category, name = definition.nodeTypeCategory(), definition.nodeTypeName()
                row = {'kind': 'hda', 'name': name, 'category': category.name(), 'file': relative}
                entries.append(row)
                existing = category.nodeTypes().get(name)
                current = existing.definition() if existing is not None else None
                row['registered_source'] = current.libraryFilePath() if current else 'native operator' if existing is not None else None
                row['registered_from_package'] = bool(current is not None and _within(current.libraryFilePath(), root))
                if existing is not None:
                    if current is None or not _within(current.libraryFilePath(), root):
                        conflicts.append({**row, 'source': current.libraryFilePath() if current else 'native operator'})
        elif p.suffix == '.shelf' and (resource_folder == 'toolbar' or relative.startswith('toolbar/')):
            document = ET.parse(p)
            for tag, registry in (('tool', hou.shelves.tools()), ('toolshelf', hou.shelves.shelves()), ('shelfSet', hou.shelves.shelfSets())):
                for element in document.findall('.//' + tag):
                    name = element.get('name')
                    if not name:
                        continue
                    row = {'kind': tag, 'name': name, 'file': relative}
                    entries.append(row)
                    old = registry.get(name)
                    row['registered_source'] = old.filePath() if old is not None else None
                    row['registered_from_package'] = bool(old is not None and _within(old.filePath(), root))
                    if old is not None and not _within(old.filePath(), root):
                        conflicts.append({**row, 'source': old.filePath()})
        elif p.suffix == '.pypanel' and (resource_folder == 'python_panels' or relative.startswith('python_panels/')):
            for element in ET.parse(p).findall('.//interface'):
                name = element.get('name')
                if not name:
                    continue
                row = {'kind': 'panel', 'name': name, 'file': relative}
                entries.append(row)
                old = hou.pypanel.interfaces().get(name)
                row['registered_source'] = old.filePath() if old is not None else None
                row['registered_from_package'] = bool(old is not None and _within(old.filePath(), root))
                if old is not None and not _within(old.filePath(), root):
                    conflicts.append({**row, 'source': old.filePath()})
        elif p.suffix == '.radialmenu' and (resource_folder == 'radialmenu' or relative.startswith('radialmenu/')):
            data = json.loads(p.read_text(encoding='utf-8'))
            if not isinstance(data, list) or len(data) % 2 or not all(isinstance(key, str) for key in data[::2]):
                raise ValueError('radial menu must use Houdini alternating key/value JSON: ' + relative)
            name = dict(zip(data[::2], data[1::2])).get('name')
            if not isinstance(name, str) or not name:
                raise ValueError('radial menu must declare a top-level name: ' + relative)
            row = {'kind': 'radialmenu', 'name': name, 'file': relative}
            entries.append(row)
            if hou.isUIAvailable() and hasattr(getattr(hou, 'ui', None), 'radialMenus'):
                old = next((menu for menu in hou.ui.radialMenus() if menu.name() == name), None)
                row['registered_source'] = old.sourceFile() if old is not None else None
                row['registered_from_package'] = bool(old is not None and _within(old.sourceFile(), root))
                if old is not None and not _within(old.sourceFile(), root):
                    conflicts.append({**row, 'source': old.sourceFile()})
            else:
                row['registered_source'] = None
                row['registered_from_package'] = None
    names = {}
    for row in entries:
        key = (row['kind'], row.get('category'), row['name'])
        if key in names:
            conflicts.append({**row, 'source': 'duplicate resource in this package: ' + names[key]})
        names[key] = row['file']
    module_folders = [root] if resource_folder == 'python' else [p for p in root.iterdir() if p.is_dir() and p.name == 'python%d.%dlibs' % sys.version_info[:2]] if resource_folder is None else []
    if resource_folder is None and (root / 'scripts/python').is_dir():
        module_folders.append(root / 'scripts/python')
    if resource_folder == 'scripts' and (root / 'python').is_dir():
        module_folders.append(root / 'python')
    for folder in module_folders:
        if folder.is_dir():
            for child in folder.iterdir():
                suffix = next((value for value in sorted(importlib.machinery.all_suffixes(), key=len, reverse=True) if child.name.endswith(value)), None)
                if child.name in ('__init__.py', '__pycache__', '.git', 'node_modules') or not (child.is_dir() or suffix):
                    continue
                name = child.name[:-len(suffix)] if child.is_file() else child.name
                if not name.isidentifier():
                    continue
                row = {'kind': 'python', 'name': name, 'file': child.relative_to(root).as_posix()}
                entries.append(row)
                loaded = sys.modules.get(name)
                origin = _module_file(loaded)
                if (name in sys.builtin_module_names or name in sys.modules) and not origin:
                    conflicts.append({'kind': 'python', 'name': name, 'file': child.relative_to(root).as_posix(), 'source': 'existing built-in or originless module'})
                    continue
                if not origin:
                    spec = importlib.machinery.PathFinder.find_spec(name, sys.path)
                    origin = spec.origin if spec else None
                    if spec and spec.submodule_search_locations and any(not _within(value, root) for value in spec.submodule_search_locations):
                        conflicts.append({'kind': 'python', 'name': name, 'file': child.relative_to(root).as_posix(), 'source': list(spec.submodule_search_locations)})
                if origin and not _within(origin, root):
                    conflicts.append({'kind': 'python', 'name': name, 'file': child.relative_to(root).as_posix(), 'source': origin})
    return entries, conflicts



def resource_report(locations):
    """Observe resource names without parsing Package JSON or executing source."""
    entries, conflicts, files, seen, missing, unsupported, roots = [], [], [], {}, [], [], []
    unique = set()
    for location in locations:
        location = location if isinstance(location, dict) else {'path': str(location), 'variable': 'HOUDINI_PATH'}
        variable = location['variable']
        source = _path(str(location['path']))
        key = (variable, os.path.normcase(str(source)))
        if key in unique:
            continue
        unique.add(key)
        roots.append(source)
        if variable not in RESOURCE_LOCATIONS:
            unsupported.append({'variable': variable, 'path': str(source)})
            continue
        if not source.is_dir():
            missing.append(str(source))
            continue
        resource_folder = RESOURCE_LOCATIONS[variable]
        source_files = _files(source, resource_folder)
        rows, collisions = _entries(source, source_files, resource_folder)
        for row in rows:
            row = {**row, 'resource_root': str(source)}
            key = (row['kind'], row.get('category'), row['name'])
            if key in seen and seen[key] != str(source / row['file']):
                conflicts.append({**row, 'source': 'duplicate name across resource directories: ' + seen[key]})
            seen[key] = str(source / row['file'])
            entries.append(row)
        conflicts.extend(collisions)
        files.extend(source_files)
    cached = _cached(roots)
    unverified = ['dynamic dependencies and callback side effects',
                  'open widgets and retained callbacks are not enumerated or removed',
                  'tool usability and public output correctness']
    if any('viewer_states' in path.parts or 'viewer_handles' in path.parts for path in files) or any(
            item[0] in ('HOUDINI_VIEWERSTATE_PATH', 'HOUDINI_VIEWERHANDLE_PATH') for item in unique):
        unverified.append('dynamic Viewer State/Handle registration-name conflicts')
    return {'entries': entries, 'conflicts': conflicts, 'missing_resource_roots': missing,
            'unsupported_resource_locations': unsupported, 'cached_python_modules': cached, 'unverified': unverified}


def _cached(roots):
    return sorted(name for name, module in list(sys.modules.items()) if any(
        _within(_module_file(module), root) for root in roots))


def _instances(roots):
    # Native definitions remain in use after their disk library is moved.
    result = []
    for category in hou.nodeTypeCategories().values():
        for node_type in category.nodeTypes().values():
            instances = node_type.instances()
            if not instances:
                continue
            definition = node_type.definition()
            if definition is not None and any(_within(definition.libraryFilePath(), root) for root in roots):
                result.extend(node.path() for node in instances)
    return sorted(set(result))


def _failure_runtime(package_file):
    try:
        return native_package_state(str(package_file))
    except Exception as error:
        return {'status': 'unavailable', 'package': None, 'readback_error': str(error)}


def _require_gui():
    if not hou.isUIAvailable() or not hasattr(getattr(hou, 'ui', None), 'loadPackage'):
        raise ValueError('native package actions require a Houdini GUI session')


def tool_package_action(package_file, action, *, dry_run=True, expected_sha256=None):
    """Load/activate/deactivate/unload a selected Package in this process only.

    Never writes JSON, deletes files, clears Python modules, closes widgets or
    force-unloads resources. Load requires an unloaded package because HOM
    otherwise silently reloads. Persistent changes use ordinary JSON edits.
    """
    try:
        if action not in ('load', 'activate', 'deactivate', 'unload') or type(dry_run) is not bool:
            raise ValueError('action must be load, activate, deactivate or unload; dry_run must be boolean')
        _require_gui()
        path, config, digest = read_package_config(package_file)
        if expected_sha256 is not None and (not isinstance(expected_sha256, str) or expected_sha256 != digest):
            raise ValueError('package JSON changed since inspection; inspect it again before applying')
        before = package_inspect(str(path))
        runtime = before['runtime']
        if runtime['status'] == 'unavailable':
            raise ValueError('native package state is unavailable; no action was dispatched')
        loaded = runtime['status'] == 'observed'
        if action == 'load' and loaded:
            raise ValueError('package is already loaded; load would implicitly reload existing resources')
        if action != 'load' and not loaded:
            raise ValueError('package is not loaded; use the explicit load action first')
        if loaded and before.get('runtime_root_matches_config') is False and runtime['package'].get('condition_enabled') is not False:
            raise ValueError('package config differs from the current native loaded resources; inspect both before changing runtime state')
        configured_locations = [item for item in before['resource_locations'] if item['resolved'] and item['type'] != 'package_directory']
        native_locations = [item for item in (runtime['package'] or {}).get('resource_locations', [])
                            if item['variable'] != 'resource_root']
        if not any(item['variable'] == 'HOUDINI_PATH' for item in native_locations) and (runtime['package'] or {}).get('resource_root'):
            native_locations.append({'variable': 'HOUDINI_PATH', 'path': runtime['package']['resource_root']})
        locations = native_locations if action in ('deactivate', 'unload') else configured_locations
        roots = [_path(item['path']) for item in locations]
        if action in ('load', 'activate') and before.get('unresolved_paths'):
            raise ValueError('package resource paths cannot be fully resolved; inspect its conditions and environment before loading')
        if action in ('deactivate', 'unload') and not locations and (before['declared_resource_roots'] or before.get('unresolved_paths')) and runtime['package'].get('condition_enabled') is not False:
            raise ValueError('native loaded resource locations are unavailable; no runtime action was dispatched')
        report = resource_report(locations)
        native_roots = [_path(item['path']) for item in native_locations]
        affected = _instances([*roots, *native_roots])
        already_requested = loaded and ((action == 'activate' and runtime['package']['active'] is True) or
                                        (action == 'deactivate' and runtime['package']['active'] is False))
        blockers = []
        if affected and not already_requested:
            blockers.append('package is still used by HDA instances: ' + ', '.join(affected))
        if action in ('load', 'activate') and report['conflicts']:
            blockers.append('resource names conflict with existing content: ' + json.dumps(report['conflicts'], ensure_ascii=False))
        if action in ('load', 'activate') and report['missing_resource_roots']:
            blockers.append('declared resource directories do not exist: ' + ', '.join(report['missing_resource_roots']))
        if report['unsupported_resource_locations']:
            blockers.append('resource locations cannot be inspected by this action: ' + json.dumps(report['unsupported_resource_locations']))
        if action == 'activate' and config.get('enable') is False:
            blockers.append('package is disabled in its original JSON; activation does not rewrite persistent conditions')
        condition_enabled = (runtime['package'] or {}).get('condition_enabled')
        if action == 'activate' and condition_enabled is False:
            blockers.append('the native package enable condition is false; activation cannot bypass it')
        if action == 'activate' and type(config.get('enable', True)) is not bool and condition_enabled is not True:
            blockers.append('the native package enable condition is not known to be satisfied; activation cannot bypass it')
        result = {'ok': True, 'action': action, 'package_file': str(path), 'config_sha256': digest,
                  'resource_roots': [str(root) for root in roots], 'resource_locations': locations,
                  'dry_run': dry_run, 'applied': False, 'runtime_only': True,
                  'before': before, 'affected_instances': affected, 'blockers': blockers,
                  'config_unchanged': True, 'source_files_retained': True, 'file_writes': [], **report}
        if dry_run:
            return result
        if blockers:
            raise ValueError('; '.join(blockers))
        if already_requested:
            return {**result, 'runtime': runtime, 'native_action_attempted': False, 'scene_writes': 0}
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('package JSON changed during preflight; no action was dispatched')
    except Exception as error:
        _checkpoint(error, 'package_action_preflight', action=action, package_file=str(package_file),
                    file_writes=[], scene_writes=0, native_action_attempted=False,
                    restored=True, dispatched=False)
    native_attempted = False
    try:
        native_attempted = True
        getattr(hou.ui, {'load': 'loadPackage', 'activate': 'activatePackage',
                         'deactivate': 'deactivatePackage', 'unload': 'unloadPackage'}[action])(str(path))
        after = package_inspect(str(path))
        state = after['runtime']
        if state['status'] == 'unavailable':
            raise RuntimeError('native package readback is unavailable after dispatch')
        if action == 'unload' and state['status'] != 'not_loaded':
            raise RuntimeError('native package unload did not remove the runtime registration')
        if action == 'deactivate' and (state['status'] != 'observed' or state['package']['active'] is not False):
            raise RuntimeError('native package deactivate did not report an inactive package')
        if action in ('load', 'activate'):
            if state['status'] != 'observed':
                raise RuntimeError('native package load did not report a runtime registration')
            if action == 'activate' and state['package']['active'] is not True:
                raise RuntimeError('native activation did not report an active package; original conditions were preserved')
            if state['package']['active'] is True and state['package'].get('condition_enabled') is not False and config.get('enable') is not False and after.get('runtime_root_matches_config') is not True:
                raise RuntimeError('native active resource roots do not match the selected config')
        if after['config_sha256'] != digest:
            raise RuntimeError('package JSON changed during native dispatch; this operation did not write it')
    except Exception as error:
        _checkpoint(error, 'package_action_failure', action=action, package_file=str(path),
                    resource_roots=[str(root) for root in roots], config_sha256=digest,
                    file_writes=[], runtime=_failure_runtime(path), native_action_attempted=native_attempted,
                    restored=False, scene_writes=None, scope='native callbacks and partial resources are not rolled back')
    cached = _cached([*roots, *native_roots])
    return {**result, 'applied': True, 'runtime': state, 'native_action_attempted': True,
            'config_unchanged': True, 'cached_python_modules': cached,
            'restart_required_for_python_cache': bool(cached) and action in ('deactivate', 'unload'),
            'scene_writes': None, 'scope': 'current process native resources; no callback or scene rollback guarantee'}
