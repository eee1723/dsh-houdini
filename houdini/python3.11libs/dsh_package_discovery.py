"""Read native Package files and current Houdini load facts without loading code.

Configured paths are resolved from this file's declarations and a small platform
variable set. Conditions and cross-package variables remain unresolved. Native
metadata is a separate observation; disk presence never proves active loading.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys

import hou

_VARIABLE = re.compile(r'\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))')
_SENSITIVE = re.compile(r'secret|token|password|credential|api_?key', re.I)
_BUILTINS = ('HFS', 'HH', 'HB', 'HOME', 'HSITE', 'HOUDINI_USER_PREF_DIR')
_RESOURCE_FOLDERS = ('otls', 'toolbar', 'python_panels', 'radialmenu', 'viewer_states',
                     'viewer_handles', 'scripts/python')
_PATH_VARIABLES = {'HOUDINI_PATH', 'PYTHONPATH', 'PATH', 'LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH'}
_CONFIG_FIELDS = {'enable', 'hpath', 'path', 'package_path', 'process_order',
                  'load_package_once', 'requires', 'recommends', 'version'}


def _path(value):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('an explicit absolute path is required')
    path = Path(value)
    if not path.is_absolute():
        raise ValueError('an explicit absolute path is required')
    return path.resolve()


def _key(path):
    return os.path.normcase(os.path.realpath(str(path)))


def _within(path, root):
    """Compare resolved native paths using the platform's case convention."""
    target, parent = _key(path), _key(root)
    return target == parent or target.startswith(parent.rstrip(os.sep) + os.sep)


def _is_link(path):
    # H21's Python 3.11 has no Path.is_junction; Windows reparse attributes
    # cover junctions without following their target to inspect its contents.
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)


def _public_value(value):
    if isinstance(value, dict):
        return {('<omitted>' if _SENSITIVE.search(str(key)) else key):
                '<omitted>' if _SENSITIVE.search(str(key)) else _public_value(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_public_value(item) for item in value]
    if isinstance(value, str) and any(_SENSITIVE.search(match[1] or match[2]) for match in _VARIABLE.finditer(value)):
        return '<omitted>'
    return value


def _path_variable(name):
    return name in _PATH_VARIABLES or name.startswith('HOUDINI_') and name.endswith('_PATH')


def _resource_variable(name):
    return name in ('HOUDINI_PATH', 'PYTHONPATH') or name.startswith('HOUDINI_') and name.endswith('_PATH')


def _duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def read_package_config(package_file):
    """Internal raw read for deliberate configuration edits; never execute it."""
    path = _path(package_file)
    if path.suffix.lower() != '.json' or not path.is_file():
        raise ValueError('an existing native Package JSON file is required')
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('Package JSON exceeds 8 MiB')
    content = path.read_bytes()
    data = json.loads(content.decode('utf-8-sig'), object_pairs_hook=_duplicates,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('invalid JSON number: ' + value)))
    if not isinstance(data, dict):
        raise ValueError('native Package JSON must contain an object')
    return path, data, hashlib.sha256(content).hexdigest()


def _loaded_package_metadata():
    """The single native Package observation boundary, shared by all consumers."""
    if not hou.isUIAvailable() or not hasattr(getattr(hou, 'ui', None), 'packageInfo'):
        return {'status': 'unavailable', 'packages': None, 'reason': 'GUI packageInfo API unavailable'}
    try:
        raw = hou.ui.packageInfo()
    except Exception as error:
        return {'status': 'unavailable', 'packages': None, 'reason': 'native packageInfo failed: ' + type(error).__name__}
    if not isinstance(raw, str):
        return {'status': 'unavailable', 'packages': None, 'reason': 'unexpected native packageInfo schema'}
    if len(raw) > 8 * 1024 * 1024:
        return {'status': 'unavailable', 'packages': None, 'reason': 'metadata exceeds 8 MiB'}
    try:
        rows = json.loads(raw)
    except ValueError:
        return {'status': 'unavailable', 'packages': None, 'reason': 'invalid native packageInfo JSON'}
    if not isinstance(rows, dict) or any(not isinstance(row, dict) for row in rows.values()):
        return {'status': 'unavailable', 'packages': None, 'reason': 'unexpected native packageInfo schema'}
    return {'status': 'observed', 'packages': rows}


def _strings(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str)]
    return []


def _split_paths(value):
    # Native Windows path lists use semicolons. Do not split drive colons.
    separator = ';' if ';' in value or os.name == 'nt' else ':'
    return [part.strip() for part in value.split(separator) if part.strip()]


def _native_locations(row):
    env = row.get('Environment Variables') or {}
    result = []
    if isinstance(env, dict):
        for variable, value in env.items():
            if not _path_variable(variable) or _SENSITIVE.search(variable):
                continue
            for item in _strings(value):
                for part in _split_paths(item):
                    if '$' not in part and part != '&' and Path(part).is_absolute():
                        result.append({'variable': variable, 'path': str(_path(part))})
    resources = row.get('Resources') or {}
    root = resources.get('Root folder') if isinstance(resources, dict) else None
    if isinstance(root, str) and Path(root).is_absolute():
        result.append({'variable': 'resource_root', 'path': str(_path(root))})
    return result


def native_package_state(package_file, metadata=None):
    """Exact config-file observation; an unavailable GUI is not 'not loaded'."""
    target = _path(str(package_file))
    metadata = _loaded_package_metadata() if metadata is None else metadata
    if metadata['status'] != 'observed':
        return {'status': metadata['status'], 'package': None, 'reason': metadata.get('reason')}
    for name, row in metadata['packages'].items():
        location = row.get('File path')
        if not isinstance(location, str) or not Path(location).is_absolute() or _key(location) != _key(target):
            continue
        locations = _native_locations(row)
        resources = row.get('Resources') or {}
        native_enable = row.get('enable', row.get('expression enable'))
        condition_enabled = native_enable if type(native_enable) is bool else native_enable == '1' if native_enable in ('0', '1') else None
        return {'status': 'observed', 'package': {'name': name, 'config_path': str(target),
                'active': row.get('Active'), 'auto_load': row.get('Auto load'),
                'condition_enabled': condition_enabled,
                'version': row.get('Version'), 'warnings': _public_value(row.get('Warnings', [])),
                'resource_root': resources.get('Root folder') if isinstance(resources, dict) else None,
                'search_roots': [item['path'] for item in locations if item['variable'] == 'HOUDINI_PATH'],
                'resource_locations': locations, 'resources': _public_value(resources)}}
    return {'status': 'not_loaded', 'package': None}


def _clauses(value, method=None, conditions=()):
    """Preserve native conditional branches; deliberately do not evaluate them."""
    if isinstance(value, str):
        yield value, method, list(conditions)
    elif isinstance(value, list):
        for item in value:
            yield from _clauses(item, method, conditions)
    elif isinstance(value, dict):
        selected = value.get('method', method)
        if 'value' in value:
            yield from _clauses(value['value'], selected, conditions)
        for condition, item in value.items():
            if condition not in ('value', 'method', 'var'):
                yield from _clauses(item, selected, (*conditions, condition))


def _env_items(data):
    env = data.get('env', [])
    if isinstance(env, list):
        for item in env:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get('var'), str):
                yield item['var'], {key: value for key, value in item.items() if key != 'var'}
            else:
                yield from item.items()


def _expand(value, local, package_path):
    def replacement(match):
        name = match[1] or match[2]
        if _SENSITIVE.search(name):
            return match[0]
        if name == 'HOUDINI_PACKAGE_PATH':
            return str(package_path)
        if name in local:
            return local[name] if local[name] is not None else match[0]
        if name in _BUILTINS:
            builtin = hou.getenv(name)
            return builtin if isinstance(builtin, str) and builtin and '$' not in builtin else match[0]
        return match[0]
    expanded = _VARIABLE.sub(replacement, value)
    if any(marker in expanded for marker in ('$', '`', '%', '\x00')):
        return None
    return str(_path(expanded)) if Path(expanded).is_absolute() else None


def _declarations(path, data):
    local, locations, relevant = {}, [], set()
    env_items = list(_env_items(data))
    for variable, value in env_items:
        if not isinstance(variable, str) or _SENSITIVE.search(variable):
            continue
        clauses = list(_clauses(value))
        if _path_variable(variable):
            for raw, method, conditions in clauses:
                for part in _split_paths(raw):
                    resolved = None if part == '&' else _expand(part, local, path.parent)
                    relevant.update(match[1] or match[2] for match in _VARIABLE.finditer(part))
                    status = 'default_path_marker' if part == '&' else 'conditional' if conditions else 'resolved' if resolved else 'unresolved'
                    locations.append({'variable': variable, 'type': 'houdini' if variable == 'HOUDINI_PATH' else 'python' if variable == 'PYTHONPATH' else 'search',
                                      'raw': '<omitted>' if any(_SENSITIVE.search(value) for value in conditions) else _public_value(part),
                                      'path': resolved, 'resolved': status == 'resolved',
                                      'status': status, 'method': method or 'prepend',
                                      'conditions': ['<omitted>' if _SENSITIVE.search(value) else value for value in conditions]})
        else:
            # A local scalar binding is safe only when no conditional branch or
            # inherited append/prepend value participates in its construction.
            if len(clauses) == 1 and not clauses[0][2] and clauses[0][1] in (None, 'replace'):
                local[variable] = _expand(clauses[0][0], local, path.parent)
            else:
                local[variable] = None
    for keyword in ('hpath', 'path', 'package_path'):
        declaration = data.get(keyword)
        if keyword in ('hpath', 'path') and isinstance(declaration, dict) and any(key in declaration for key in ('value', 'method')):
            # Native hpath accepts a value/method item inside an array, while a
            # standalone object is ignored by the observed native loader.
            locations.append({'variable': 'package_path' if keyword == 'package_path' else 'HOUDINI_PATH',
                              'type': 'package_directory' if keyword == 'package_path' else 'houdini',
                              'declaration': keyword, 'raw': '<unsupported declaration>', 'path': None,
                              'resolved': False, 'status': 'unresolved', 'method': None, 'conditions': [],
                              'reason': 'standalone top-level value/method object is not a native path declaration'})
            continue
        for raw, method, conditions in _clauses(declaration):
            for part in _split_paths(raw):
                resolved = None if part == '&' else _expand(part, local if keyword != 'package_path' else {}, path.parent)
                relevant.update(match[1] or match[2] for match in _VARIABLE.finditer(part))
                status = 'default_path_marker' if part == '&' else 'conditional' if conditions else 'resolved' if resolved else 'unresolved'
                locations.append({'variable': 'package_path' if keyword == 'package_path' else 'HOUDINI_PATH',
                                  'type': 'package_directory' if keyword == 'package_path' else 'houdini',
                                  'declaration': keyword, 'raw': '<omitted>' if any(_SENSITIVE.search(value) for value in conditions) else _public_value(part), 'path': resolved,
                                  'resolved': status == 'resolved', 'status': status,
                                  'method': method or 'prepend', 'conditions': ['<omitted>' if _SENSITIVE.search(value) else value for value in conditions]})
    # Follow references between local roots for a useful, minimal config view.
    pending = list(relevant)
    by_name = dict(env_items)
    while pending:
        name = pending.pop()
        for raw, _, _ in _clauses(by_name.get(name)):
            for match in _VARIABLE.finditer(raw):
                reference = match[1] or match[2]
                if reference not in relevant:
                    relevant.add(reference)
                    pending.append(reference)
    return locations, relevant


def _public_config(data, relevant):
    # Non-path environment values are intentionally omitted, even when their
    # names do not look secret. Internal writers consume read_package_config.
    result = {('<omitted>' if _SENSITIVE.search(key) else key): _public_value(value) if key in _CONFIG_FIELDS and not _SENSITIVE.search(key) else '<omitted>'
              for key, value in data.items() if key != 'env'}
    if 'env' in data:
        projection = []
        for item in data['env'] if isinstance(data['env'], list) else []:
            if not isinstance(item, dict):
                projection.append('<omitted>')
            elif isinstance(item.get('var'), str):
                name = item['var']
                include = not _SENSITIVE.search(name) and (_path_variable(name) or name in relevant)
                projection.append({('<omitted>' if _SENSITIVE.search(key) else key):
                                   '<omitted>' if _SENSITIVE.search(key) else _public_value(value) if key in ('var', 'method') or include else '<omitted>'
                                   for key, value in item.items()})
            else:
                projection.append({('<omitted>' if _SENSITIVE.search(name) else name): _public_value(value) if not _SENSITIVE.search(name) and (_path_variable(name) or name in relevant) else '<omitted>'
                                   for name, value in item.items()})
        result['env'] = projection if isinstance(data['env'], list) else '<omitted>'
    return result


def _summary(path, data, digest, metadata):
    locations, relevant = _declarations(path, data)
    roots = list(dict.fromkeys(item['path'] for item in locations
                              if item['variable'] == 'HOUDINI_PATH' and item['resolved']))
    runtime = native_package_state(path, metadata)
    relevant_locations = [item for item in locations if _resource_variable(item['variable'])]
    comparable = not any(item['status'] in ('conditional', 'unresolved') for item in relevant_locations)
    matches = None
    if comparable and runtime['status'] == 'observed' and runtime['package']['condition_enabled'] is not False:
        declared = {(item['variable'], _key(item['path'])) for item in relevant_locations if item['resolved']}
        actual = {(item['variable'], _key(item['path'])) for item in runtime['package']['resource_locations'] if _resource_variable(item['variable'])}
        if actual or declared:
            matches = actual == declared
            # packageInfo versions that expose only a Resource root retain the
            # narrow one-root comparison; never infer direct variable paths.
            if not actual and len(declared) == 1 and roots and runtime['package']['resource_root']:
                matches = _key(runtime['package']['resource_root']) == _key(roots[0])
    return {'name': path.stem, 'package_file': str(path), 'config_status': 'valid',
            'config_sha256': digest, 'enabled_in_config': _public_value(data.get('enable', True)),
            'declared_resource_roots': roots, 'resource_locations': locations,
            'unresolved_paths': [item for item in locations if item['status'] in ('conditional', 'unresolved')],
            'runtime': runtime, 'runtime_root_matches_config': matches,
            'edit_permission': 'not_inferred_from_discovery'}, relevant


def _directories(explicit, metadata):
    values = []
    pref, site, hfs = (hou.getenv(name) for name in ('HOUDINI_USER_PREF_DIR', 'HSITE', 'HFS'))
    if pref:
        values.append((str(Path(pref) / 'packages'), 'user_preferences'))
    if site:
        version = '%d.%d' % hou.applicationVersion()[:2]
        values.append((str(Path(site) / ('houdini' + version) / 'packages'), 'site'))
    for item in _split_paths(hou.getenv('HOUDINI_PACKAGE_DIR') or ''):
        values.append((item, 'HOUDINI_PACKAGE_DIR'))
    if hfs:
        values.append((str(Path(hfs) / 'packages'), 'installation'))
    if metadata['status'] == 'observed':
        for row in metadata['packages'].values():
            source = row.get('File path')
            if isinstance(source, str) and Path(source).is_absolute():
                values.append((str(Path(source).parent), 'native_loaded_config'))
    if explicit is not None:
        if not isinstance(explicit, (list, tuple)) or not all(isinstance(value, str) for value in explicit) or len(explicit) > 64:
            raise ValueError('directories must be an array of at most 64 absolute paths')
        values.extend((item, 'explicit') for item in explicit)
    rows = {}
    for value, source in values:
        try:
            path = _path(value)
        except ValueError:
            if source == 'explicit':
                raise
            continue
        row = rows.setdefault(_key(path), {'path': str(path), 'sources': [], 'exists': path.is_dir()})
        if source not in row['sources']:
            row['sources'].append(source)
    return list(rows.values())


def package_catalog(directories=None, query='', offset=0, limit=64):
    """Search top-level native JSON files and separately report current loading."""
    if not isinstance(query, str) or len(query) > 256:
        raise ValueError('query must be a string <=256 characters')
    if type(offset) is not int or not 0 <= offset <= 100000 or type(limit) is not int or not 1 <= limit <= 256:
        raise ValueError('offset must be 0..100000 and limit 1..256')
    metadata = _loaded_package_metadata()
    directories = _directories(directories, metadata)
    paths, errors = {}, []
    needle = query.casefold().strip()
    if metadata['status'] == 'observed':
        # A loaded registration remains a useful fact after its file has been
        # moved or removed. Absence on disk never erases the native observation.
        for native in metadata['packages'].values():
            source = native.get('File path')
            if isinstance(source, str) and Path(source).is_absolute() and (not needle or needle in source.casefold()):
                paths[_key(source)] = Path(source)
    for directory in directories:
        if not directory['exists']:
            continue
        try:
            for path in Path(directory['path']).iterdir():
                if path.is_file() and path.suffix.lower() == '.json' and (not needle or needle in str(path).casefold()):
                    paths[_key(path)] = path
        except OSError as error:
            errors.append({'directory': directory['path'], 'error': str(error)})
    rows = []
    for path in sorted(paths.values(), key=lambda value: str(value).casefold()):
        try:
            p, data, digest = read_package_config(str(path))
            row, _ = _summary(p, data, digest, metadata)
        except (OSError, UnicodeError, ValueError) as error:
            try:
                status = 'invalid' if path.exists() else 'missing'
            except OSError:
                status = 'unreadable'
            row = {'name': path.stem, 'package_file': str(path), 'config_status': status,
                   'error': str(error), 'runtime': native_package_state(path, metadata),
                   'edit_permission': 'not_inferred_from_discovery'}
        rows.append(row)
    return {'ok': True, 'source': 'native Package JSON and hou.ui.packageInfo',
            'houdini_version': hou.applicationVersionString(), 'runtime_status': metadata['status'],
            'runtime_reason': metadata.get('reason'), 'directories': directories,
            'total': len(rows), 'offset': offset, 'limit': limit, 'entries': rows[offset:offset + limit],
            'truncated': offset + limit < len(rows), 'scan_errors': errors,
            'scope': 'top-level JSON only; dynamic package_path folders require actual native load facts or an explicit directory; discovery does not authorize edits or prove compatibility'}


def _file_fact(path, root, digest=False):
    if _is_link(path):
        if digest:
            raise ValueError('explicit resource files must not be symbolic links or junctions')
        return {'path': str(path), 'relative_path': path.relative_to(root).as_posix(), 'kind': 'link', 'bytes': None}
    if not _within(path, root):
        raise ValueError('resource file resolves outside its root')
    fact = {'path': str(path), 'relative_path': path.relative_to(root).as_posix(),
            'kind': 'directory' if path.is_dir() else 'file', 'bytes': path.stat().st_size if path.is_file() else None}
    if digest and path.is_file():
        stream_hash = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                stream_hash.update(chunk)
        fact['sha256'] = stream_hash.hexdigest()
    return fact


def _resource_facts(locations, files):
    if files is not None and (not isinstance(files, (list, tuple)) or len(files) > 256 or not all(isinstance(value, str) for value in files)):
        raise ValueError('files must be at most 256 explicit relative resource paths')
    relative_files = []
    for value in files or []:
        relative = Path(value)
        if not value or relative.is_absolute() or '..' in relative.parts or '\x00' in value:
            raise ValueError('files must stay inside declared resource locations')
        relative_files.append(relative)
    roots, rows, requested = {}, [], {}
    for item in locations:
        if item['resolved'] and _resource_variable(item['variable']):
            roots.setdefault((item['variable'], _key(item['path'])), item)
    for item in roots.values():
        root = Path(item['path'])
        row = {'root': str(root), 'variable': item['variable'], 'exists': root.is_dir(), 'folders': [], 'errors': []}
        if root.is_dir():
            folders = [root / value for value in _RESOURCE_FOLDERS] if item['variable'] == 'HOUDINI_PATH' else [root]
            if item['variable'] == 'HOUDINI_PATH':
                try:
                    folders.extend(path for path in root.iterdir() if path.is_dir() and re.fullmatch(r'python\d+\.\d+libs', path.name))
                except OSError as error:
                    row['errors'].append({'path': str(root), 'error': str(error)})
            for folder in folders:
                try:
                    if not folder.is_dir() or _is_link(folder) or not _within(folder, root):
                        continue
                    children = []
                    for child in folder.iterdir():
                        if child.name in ('.git', 'node_modules', '__pycache__'):
                            continue
                        children.append(child)
                        if len(children) == 65:
                            break
                    truncated = len(children) > 64
                    children = sorted(children[:64], key=lambda path: path.name.casefold())
                    facts = []
                    for path in children[:64]:
                        try:
                            facts.append(_file_fact(path, root))
                        except OSError as error:
                            facts.append({'path': str(path), 'error': str(error)})
                    row['folders'].append({'path': str(folder), 'total': None if truncated else len(children),
                                           'listed_count': len(facts), 'truncated': truncated, 'children': facts})
                except OSError as error:
                    row['errors'].append({'path': str(folder), 'error': str(error)})
            for relative in relative_files:
                path = root / relative
                if not _within(path, root):
                    raise ValueError('explicit resource file resolves outside its root')
                if path.is_file() and _key(path) not in requested:
                    try:
                        requested[_key(path)] = _file_fact(path, root, digest=True)
                    except OSError as error:
                        requested[_key(path)] = {'path': str(path), 'error': str(error)}
        rows.append(row)
    return rows, list(requested.values())


def package_inspect(package_file, *, files=None):
    """Inspect arbitrary native JSON, shallow resource folders or explicit files."""
    path, data, digest = read_package_config(package_file)
    row, relevant = _summary(path, data, digest, _loaded_package_metadata())
    resources, requested = _resource_facts(row['resource_locations'], files)
    return {'ok': True, **row, 'config': _public_config(data, relevant),
            'resource_folders': resources, 'files': requested,
            'unverified': ['conditions and cross-package variables are not evaluated',
                           'dynamic resource registration names, dependencies and callbacks',
                           'edit permission, compatibility and public tool behavior'],
            'scope': 'sanitized read-only config projection, not an editable copy; bounded one-level resource listings; no source import or recursive project scan'}


def package_sources_for_path(source):
    """Associate a tool with all native package search roots, without ownership."""
    metadata = _loaded_package_metadata()
    if metadata['status'] != 'observed':
        return {'status': metadata['status'], 'matches': [], 'reason': metadata.get('reason')}
    matches = []
    if isinstance(source, str) and Path(source).is_absolute():
        target = _path(source)
        for name, row in metadata['packages'].items():
            relations = [item for item in _native_locations(row) if _within(target, item['path'])]
            if relations:
                matches.append({'name': name, 'config_path': row.get('File path'), 'active': row.get('Active'),
                                'relation': 'source_under_native_search_path', 'locations': relations})
    return {'status': 'observed', 'matches': matches,
            'scope': 'path relation to native package resource/Python/search paths; not publisher verification or exclusive ownership'}
