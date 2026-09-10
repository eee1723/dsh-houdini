"""Check trusted authored HDAs in a disposable hython process, never a live HIP.

Process/path isolation is not a security sandbox for arbitrary asset code. Inputs
must be assets the author is authorized to execute. Declared libraries are copied;
resolved dependencies outside the delivery/factory installation fail the check.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


@contextlib.contextmanager
def callback_diagnostics():
    """HOM can write callback failures to native stderr without raising Python errors."""
    with tempfile.TemporaryFile(mode='w+b') as capture:
        sys.stderr.flush()
        saved = os.dup(2)
        try:
            os.dup2(capture.fileno(), 2)
            yield capture
        finally:
            sys.stderr.flush()
            os.dup2(saved, 2)
            os.close(saved)


def diagnostic_text(capture):
    sys.stderr.flush()
    capture.flush()
    capture.seek(0)
    text = capture.read().decode('utf-8', errors='replace')
    capture.seek(0, 2)
    return text


def definition_inventory(node, libraries, factory_root):
    dependencies = []
    for child in node.allSubChildren():
        definition = child.type().definition()
        library = definition.libraryFilePath() if definition else None
        dependencies.append({'path': child.path(), 'type': child.type().name(),
                             'source': child.type().source().name(), 'library': library})
        if library:
            path = Path(library).resolve()
            if path not in libraries and not path.is_relative_to(factory_root):
                raise RuntimeError(f'undeclared HDA dependency: {child.type().name()} from {library}')
    return dependencies


def load_manifest(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    allowed = {'assets', 'python_paths', 'category', 'type', 'cases'}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError('manifest has unknown fields')
    if data.get('category') not in ('Object', 'Sop') or not isinstance(data.get('type'), str):
        raise ValueError('category must be Object/Sop and type must be explicit')
    if not isinstance(data.get('assets'), list) or not 1 <= len(data['assets']) <= 32:
        raise ValueError('assets requires 1..32 library paths')
    if not isinstance(data.get('python_paths', []), list):
        raise ValueError('python_paths must be a list')
    cases = data.get('cases')
    if not isinstance(cases, list) or not 1 <= len(cases) <= 32:
        raise ValueError('cases requires 1..32 cases')
    ids = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) - {'id', 'values', 'buttons', 'menus', 'expect_parms', 'expect_geometry', 'expect_error'}:
            raise ValueError('case has unknown fields')
        if not isinstance(case.get('id'), str) or not case['id'] or case['id'] in ids:
            raise ValueError('case id must be nonempty and unique')
        ids.add(case['id'])
        for field in ('values', 'menus', 'expect_parms'):
            if not isinstance(case.get(field, {}), dict):
                raise ValueError(f'{field} must be an object')
        buttons = case.get('buttons', [])
        if not isinstance(buttons, list) or len(buttons) > 32 or any(not isinstance(x, str) for x in buttons):
            raise ValueError('buttons must be at most 32 parameter names')
        if 'expect_error' in case and (not isinstance(case['expect_error'], str) or not case['expect_error']):
            raise ValueError('expect_error must be a nonempty substring')
        if not any(case.get(k) for k in ('expect_parms', 'expect_geometry', 'expect_error')):
            raise ValueError('each case needs an observable result, not only a successful callback')
        geo = case.get('expect_geometry')
        if geo is not None:
            if (not isinstance(geo, dict) or set(geo) - {'output', 'points', 'primitives'} or
                    not isinstance(geo.get('output'), str) or
                    not any(k in geo for k in ('points', 'primitives'))):
                raise ValueError('expect_geometry needs relative output and point/primitive counts')
            if geo['output'].startswith('/') or '..' in geo['output'].split('/'):
                raise ValueError('geometry output must stay inside the case instance')
            for key in ('points', 'primitives'):
                if key in geo and (type(geo[key]) is not int or geo[key] < 0):
                    raise ValueError('geometry counts must be nonnegative integers')
    return data


def worker(manifest_path, result_path):
    import hou
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'houdini/python3.11libs'))
    import dsh_hou_helpers as h
    manifest = load_manifest(manifest_path)
    for path in reversed(manifest.get('python_paths', [])):
        sys.path.insert(0, path)
    report = {'ok': False, 'houdini': hou.applicationVersionString(), 'cases': [],
              'scope': 'isolated HOM button/menu/geometry checks; GUI, hotkeys, Engine and arbitrary external side effects unverified'}
    try:
        for library in manifest['assets']:
            hou.hda.installFile(library, force_use_assets=True)
        category = hou.nodeTypeCategories()[manifest['category']]
        node_type = category.nodeTypes().get(manifest['type'])
        if node_type is None or node_type.definition() is None:
            raise RuntimeError('declared HDA type was not loaded')
        loaded = Path(node_type.definition().libraryFilePath()).resolve()
        if loaded not in {Path(x).resolve() for x in manifest['assets']}:
            raise RuntimeError('HDA resolved outside the copied delivery libraries')
        report['loaded_library'] = str(loaded)
        parent = hou.node('/obj')
        if manifest['category'] == 'Sop':
            parent = parent.createNode('geo', 'delivery_fixture', run_init_scripts=False)
        for index, case in enumerate(manifest['cases']):
            node = None
            result = {'id': case['id'], 'ok': False, 'buttons_executed': [], 'menus': {}}
            try:
                node = parent.createNode(manifest['type'], f'case_{index}', exact_type_name=True)
                allowed_libraries = {Path(x).resolve() for x in manifest['assets']}
                factory_root = Path(hou.text.expandString('$HFS')).resolve()
                result['node_definitions'] = definition_inventory(node, allowed_libraries, factory_root)
                with h._execution_owner('delivery-check', case['id']):
                    h._register_owned_node(node)  # trusted fixture creation, no user nodes
                    if case.get('values'):
                        h.set_parms(node, case['values'])
                callback_error = None
                diagnostic = ''
                try:
                    with callback_diagnostics() as diagnostics:
                        for name, expected in case.get('menus', {}).items():
                            p = node.parm(name)
                            if p is None:
                                raise RuntimeError(f'missing menu parameter {name}')
                            items = list(p.menuItems())
                            result['menus'][name] = items
                            if items != expected:
                                raise AssertionError(f'{name}: menu tokens {items!r} != {expected!r}')
                        for name in case.get('buttons', []):
                            p = node.parm(name)
                            if p is None or p.parmTemplate().type() != hou.parmTemplateType.Button:
                                raise RuntimeError(f'missing button parameter {name}')
                            p.pressButton()  # real Houdini callback context, never exec(section)
                            diagnostic = diagnostic_text(diagnostics)
                            if diagnostic:
                                raise RuntimeError(diagnostic)
                            result['buttons_executed'].append(name)
                        diagnostic = diagnostic_text(diagnostics)
                except Exception as error:
                    callback_error = str(error)
                if diagnostic:
                    callback_error = diagnostic
                    result['callback_diagnostics'] = diagnostic[-8000:]
                expected_error = case.get('expect_error')
                if expected_error:
                    if not callback_error or expected_error not in callback_error:
                        raise AssertionError(f'expected callback error {expected_error!r}; actual={callback_error!r}')
                    result['expected_error_observed'] = callback_error
                elif callback_error:
                    raise RuntimeError(callback_error)
                actual = {}
                for name, expected in case.get('expect_parms', {}).items():
                    actual[name] = node.evalParm(name)
                    if actual[name] != expected:
                        raise AssertionError(f'{name}: actual={actual[name]!r}, expected={expected!r}')
                result['parameters'] = actual
                if case.get('expect_geometry'):
                    expected = case['expect_geometry']
                    output = node if expected['output'] in ('', '.') else node.node(expected['output'])
                    if output is None or output.type().category() != hou.sopNodeTypeCategory():
                        raise AssertionError('expected SOP output is missing')
                    with h._execution_owner('delivery-check', case['id']):
                        h.cook_node(output)
                    if output.errors():
                        raise AssertionError(str(output.errors()))
                    geo = output.geometry()
                    counts = {'points': len(geo.points()), 'primitives': len(geo.prims())}
                    result['geometry'] = counts
                    for key in ('points', 'primitives'):
                        if key in expected and expected[key] != counts[key]:
                            raise AssertionError(f'{key}: actual={counts[key]}, expected={expected[key]}')
                result['node_definitions'] = definition_inventory(node, allowed_libraries, factory_root)
                result['ok'] = True
            except Exception as error:
                result['error'] = str(error)
            finally:
                if node is not None:
                    try:
                        node.destroy()
                    except Exception as error:
                        result['ok'] = False
                        result['cleanup_error'] = str(error)
            report['cases'].append(result)
        report['ok'] = all(case['ok'] for case in report['cases'])
    except Exception as error:
        report['error'] = str(error)
    result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1


def check(manifest_path, hython, timeout=120, memory_mb=4096, cancel_file=None):
    manifest = load_manifest(manifest_path)
    with tempfile.TemporaryDirectory(prefix='dsh-delivery-') as temporary:
        temp = Path(temporary)
        copies, hashes = [], []
        for index, value in enumerate(manifest['assets']):
            source = (manifest_path.parent / value).resolve()
            if not source.is_file():
                raise ValueError(f'missing asset {source}')
            target = temp / 'assets' / f'{index}{source.suffix}'
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(source, target)
            copies.append(str(target))
            hashes.append({'file': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
        module_paths = []
        for index, value in enumerate(manifest.get('python_paths', [])):
            source = (manifest_path.parent / value).resolve()
            if not source.is_dir() or any(p.is_symlink() for p in source.rglob('*')):
                raise ValueError('python_paths must be regular directories without symlinks')
            target = temp / 'modules' / str(index)
            shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            module_paths.append(str(target))
        manifest.update(assets=copies, python_paths=module_paths)
        copied = temp / 'manifest.json'
        copied.write_text(json.dumps(manifest), encoding='utf-8')
        report_file = temp / 'report.json'
        env = dict(os.environ)
        for key in list(env):
            if (key.upper() in {'PYTHONPATH', 'PYTHONHOME', 'HSITE', 'HFS', 'HHP', 'HB', 'HDSO'} or
                    key.upper().startswith('HOUDINI_') and key.upper() != 'HOUDINI_LICENSE_SERVER'):
                env.pop(key)
        packages = temp / 'packages'; packages.mkdir()
        env.update(HOUDINI_PATH='&', HOUDINI_NO_ENV_FILE='1',
                   HOUDINI_USER_PREF_DIR=str(temp / 'prefs__HVER__'),
                   HOUDINI_PACKAGE_DIR=str(packages), PYTHONIOENCODING='utf-8',
                   PYTHONNOUSERSITE='1', HFS=str(hython.parent.parent))
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'houdini/python3.11libs'))
        from dsh_worker_limits import run_gated_worker
        process=run_gated_worker([str(hython), str(Path(__file__).resolve()), '--worker',
                                 str(copied), str(report_file)],cwd=temp,env=env,timeout=timeout,
                                 memory_mb=memory_mb,cancel_file=cancel_file)
        report = json.loads(report_file.read_text(encoding='utf-8')) if report_file.exists() else {'ok': False, 'error': 'worker produced no report'}
        report.update(exit_code=process['returncode'], assets=hashes, worker=process)
        report['ok'] = report.get('ok') is True and process['status']=='completed'
        if not report['ok']:
            report['worker_output'] = process['output']
        return report


def main():
    if len(sys.argv) == 4 and sys.argv[1] == '--worker':
        if sys.stdin.readline().strip()!='GO':return 2
        return worker(Path(sys.argv[2]), Path(sys.argv[3]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--hython', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--memory-mb', type=int, default=4096)
    parser.add_argument('--cancel-file', type=Path)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    report = check(args.manifest.resolve(), args.hython.resolve(), args.timeout,args.memory_mb,args.cancel_file)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    print(text)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
