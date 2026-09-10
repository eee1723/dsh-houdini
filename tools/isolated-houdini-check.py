"""Run a trusted builder and explicit cook/cache/ROP checks in a NEW hython scene.

Never connects to live Houdini, loads a HIP, adopts foreign identities or retries
an uncertain run. Isolation limits our worker tree, not arbitrary script side
effects, GPU allocations or external services. --trusted is required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from houdini_test_environment import isolated_environment, launch_directory

SCOPE = ('New owned scene; trusted builder through Bridge/Raw Gate; explicit output checks only. '
         'No live HIP, foreign adoption, automatic retry or visual/semantic certification. '
         'Absolute-path, imported-code, callback and external-service side effects are not sandboxed/restored.')


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON field: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('nonfinite JSON value: ' + value)
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('JSON report/manifest exceeds 4 MiB')
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique, parse_constant=invalid)


def write_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(temporary, path)


def relative_file(value):
    if not isinstance(value, str) or not value or value.startswith('/') or re.search(r'[\\<>:"|?*\x00-\x1f$%]', value):
        raise ValueError('file must be a literal relative path with / separators')
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *('COM' + i for i in '123456789¹²³'), *('LPT' + i for i in '123456789¹²³')}
    for part in value.split('/'):
        if part in ('', '.', '..') or part != part.strip() or part.endswith('.') or part.split('.')[0].rstrip().upper() in reserved:
            raise ValueError('file contains an unsafe/aliased path component')
    return value


def is_reparse(path):
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)
    except FileNotFoundError:
        return False


def regular_file(root, relative):
    if is_reparse(root):
        raise ValueError('declared root is a symlink/reparse point')
    path = root
    for part in relative_file(relative).split('/'):
        path = path / part
        if is_reparse(path):
            raise ValueError('symlinks/reparse points are not accepted in inputs/artifacts')
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('file must stay inside its declared root')
    return path


def artifact_target(directory, check):
    """Validate existing ancestors BEFORE export, not only after it wrote bytes."""
    if is_reparse(directory):
        raise ValueError('run directory became a symlink/reparse point')
    path = directory
    parts = relative_file('artifacts/' + check['id'] + '/' + check['file']).split('/')
    for part in parts[:-1]:
        path = path / part
        if is_reparse(path):
            raise ValueError('artifact ancestor is a symlink/reparse point')
        path.mkdir(exist_ok=True)
    target = path / parts[-1]
    if target.exists() or is_reparse(target):
        raise ValueError('artifact already exists; refusing overwrite')
    return target


def load_manifest(path):
    data = read_json(path)
    if not isinstance(data, dict) or set(data) - {'script', 'files', 'checks'}:
        raise ValueError('manifest fields: script, files?, checks')
    script = relative_file(data.get('script'))
    if not script.endswith('.py'):
        raise ValueError('script must be a trusted .py builder, not a HIP')
    files = data.get('files', [])
    if not isinstance(files, list) or len(files) > 32:
        raise ValueError('files must contain at most 32 explicit relative files')
    inputs = [script, *(relative_file(value) for value in files)]
    if len(set(value.casefold() for value in inputs)) != len(inputs):
        raise ValueError('duplicate/aliased input file')
    size = 0
    for index, name in enumerate(inputs):
        source = regular_file(path.parent, name)
        size += source.stat().st_size
        if index == 0 and source.stat().st_size > 1024 * 1024:
            raise ValueError('builder exceeds 1 MiB')
    if size > 2 * 1024 ** 3:
        raise ValueError('declared inputs exceed 2 GiB')
    checks = data.get('checks')
    if not isinstance(checks, list) or not 1 <= len(checks) <= 16:
        raise ValueError('checks must contain 1..16 explicit operations')
    ids = set()
    for check in checks:
        if not isinstance(check, dict) or set(check) - {'id', 'kind', 'node', 'frame', 'file', 'expect'}:
            raise ValueError('unknown check fields')
        ident = check.get('id')
        if not isinstance(ident, str) or not re.fullmatch(r'[a-z0-9_-]{1,48}', ident) or ident in ids:
            raise ValueError('check id must be unique lowercase ASCII letters/digits/_/-')
        relative_file(ident)
        ids.add(ident)
        node = check.get('node')
        if not isinstance(node, str) or not node.startswith('/'):
            raise ValueError('node must be an explicit absolute Houdini path')
        relative_file(node[1:])
        frame = check.get('frame')
        if type(frame) not in (int, float) or not math.isfinite(frame) or abs(frame) > 1000000:
            raise ValueError('frame must be explicit, finite and within +/-1000000')
        kind = check.get('kind')
        if kind not in ('cook', 'cache', 'render'):
            raise ValueError('kind must be cook/cache/render')
        if kind == 'cook':
            if 'file' in check:
                raise ValueError('cook does not write an artifact')
        else:
            filename = relative_file(check.get('file'))
            extensions = ('.bgeo', '.bgeo.sc') if kind == 'cache' else ('.bgeo', '.bgeo.sc', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.exr')
            if not filename.lower().endswith(extensions):
                raise ValueError('unsupported artifact extension for ' + kind)
        expected = check.get('expect', {})
        if not isinstance(expected, dict) or set(expected) - {'points', 'primitives'}:
            raise ValueError('expect accepts only points/primitives counts')
        if kind == 'render' and expected:
            raise ValueError('render does not certify geometry counts')
        if any(type(value) is not int or value < 0 for value in expected.values()):
            raise ValueError('expected counts must be nonnegative integers')
    return data


def worker(request_file):
    # The caller has assigned this process to its limited Job before GO.
    request = read_json(request_file)
    directory = request_file.parent
    result_file = directory / 'worker-result.json'
    result = {'ok': False, 'run_id': request['run_id'], 'phase': 'initialize', 'checks': [], 'scope': SCOPE}
    write_json(result_file, result)
    try:
        sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
        import hou
        import dsh_bridge as bridge
        import dsh_hou_helpers as h
        session = 'isolated-' + request['run_id']
        result['runtime'] = {'houdini': hou.applicationVersionString(), 'runtime_id': bridge._RUNTIME_ID,
                             'execution_contract': bridge._EXECUTION_CONTRACT_VERSION,
                             'verb_catalog_sha256': bridge._VERB_CATALOG_HASH, 'owner_session': session}

        def execute(code, call):
            return bridge._execute(lambda: bridge.run_code(code, owner_session=session, owner_call=call))

        def successful(envelope):
            if not envelope['ok']:
                raise RuntimeError(envelope.get('error') or 'Bridge execution failed')
            return envelope.get('result')

        def run():
            # Reserved driver initialization, on this worker's owning thread.
            # No existing scene is loaded/saved; $HIP only anchors new artifacts.
            if Path(hou.hipFile.path()).name.lower() != 'untitled.hip':
                raise RuntimeError('worker did not start with a new scene')
            hou.hipFile.setName(str(directory / 'scene.hip'))
            manifest = request['manifest']
            script = directory / 'inputs' / manifest['script']
            for row in request['inputs']:
                if digest(regular_file(directory / 'inputs', row['file'])) != row['sha256']:
                    raise ValueError('staged input digest mismatch')
            sys.path.insert(0, str(script.parent))
            result['phase'] = 'builder'
            write_json(result_file, result)
            result['builder'] = execute(script.read_text(encoding='utf-8'), 'builder')
            successful(result['builder'])
            for check in manifest['checks']:
                row = {'id': check['id'], 'kind': check['kind'], 'node': check['node'], 'frame': check['frame'], 'status': 'running'}
                result['checks'].append(row)
                result['phase'] = 'check:' + check['id']
                write_json(result_file, result)
                try:
                    node = hou.node(check['node'])
                    if node is None:
                        raise ValueError('missing explicit output: ' + check['node'])
                    with h._execution_owner(session, check['id']):
                        h._require_owned(node, 'isolated check')
                    frame_code = f'set_timeline(current_frame={check["frame"]!r})\n'
                    if check['kind'] == 'render':
                        artifact = artifact_target(directory, check)
                        row['execution'] = execute(frame_code + f'__result__=render_frame({node.path()!r},picture={str(artifact)!r},frame={check["frame"]!r})', check['id'])
                        rendered = successful(row['execution'])
                        if rendered.get('errors') or rendered.get('fresh') is not True:
                            raise ValueError('render did not produce a fresh error-free artifact')
                    else:
                        if node.type().category() != hou.sopNodeTypeCategory():
                            raise ValueError('cook/cache require a SOP output')
                        row['execution'] = execute(frame_code + f'__result__=verify_network({node.parent().path()!r},output={node.path()!r},nodes=[{node.path()!r}])', check['id'])
                        geometry = successful(row['execution'])['geometry']
                        counts = {'points': geometry['points'], 'primitives': geometry['prims']}
                        row['geometry'] = counts
                        for name, value in check.get('expect', {}).items():
                            if counts[name] != value:
                                raise ValueError(f'{name}: actual={counts[name]}, expected={value}')
                        if check['kind'] == 'cache':
                            artifact = artifact_target(directory, check)
                            frozen = node.geometry().freeze(read_only=True)
                            frozen.saveToFile(str(artifact))
                            reread = hou.Geometry()
                            reread.loadFromFile(str(artifact))
                            if len(reread.points()) != counts['points'] or len(reread.prims()) != counts['primitives']:
                                raise ValueError('cache roundtrip counts changed')
                    if check['kind'] != 'cook':
                        file = regular_file(directory / 'artifacts', check['id'] + '/' + check['file'])
                        if file.stat().st_size <= 0:
                            raise ValueError('empty artifact')
                        row['artifact'] = {'file': 'artifacts/' + check['id'] + '/' + check['file'],
                                           'bytes': file.stat().st_size, 'sha256': digest(file)}
                    row['status'] = 'passed'
                except Exception as error:
                    row.update(status='failed', error=str(error) or type(error).__name__)
                    raise
                finally:
                    write_json(result_file, result)
            result.update(ok=True, phase='completed')
        bridge._execute(run)
    except BaseException as error:
        result['error'] = str(error) or type(error).__name__
    write_json(result_file, result)
    return 0 if result['ok'] else 1


def check(manifest_path, hython, output_dir, *, trusted=False, timeout=120, memory_mb=4096, cancel_file=None):
    if trusted is not True:
        raise ValueError('explicit trusted=True/--trusted authorization is required to execute the builder and dependencies')
    manifest_path, hython, output_dir = Path(manifest_path).resolve(), Path(hython).resolve(), Path(output_dir).resolve()
    manifest = load_manifest(manifest_path)
    if output_dir.is_relative_to(ROOT):
        raise ValueError('output directory must be outside the plugin repository')
    output_dir.mkdir()  # exclusive run directory; never overwrite prior evidence
    run_id = uuid.uuid4().hex
    report = {'ok': False, 'run_id': run_id, 'phase': 'staging', 'scope': SCOPE}
    inputs = []
    try:
        for name in [manifest['script'], *manifest.get('files', [])]:
            source = regular_file(manifest_path.parent, name)
            target = output_dir / 'inputs' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            before = digest(source)
            shutil.copy2(source, target)
            if digest(target) != before:
                raise ValueError('input changed during staging')
            inputs.append({'file': name, 'sha256': before, 'bytes': target.stat().st_size})
        request = {'run_id': run_id, 'manifest': manifest, 'inputs': inputs}
        request_file = output_dir / 'request.json'
        write_json(request_file, request)
        env = isolated_environment(output_dir / 'runtime', executable=hython if hython.is_file() else None)
        sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
        from dsh_worker_limits import run_gated_worker
        process = run_gated_worker([str(hython), str(Path(__file__).resolve()), '--worker', str(request_file)],
                                  cwd=launch_directory(hython) if hython.is_file() else output_dir,
                                  env=env, timeout=timeout, memory_mb=memory_mb, cancel_file=cancel_file)
        report.update(phase='worker_result', worker=process)
        result_file = output_dir / 'worker-result.json'
        if result_file.exists():
            result = read_json(result_file)
            if not isinstance(result, dict) or result.get('run_id') != run_id:
                raise ValueError('worker result identity mismatch')
            report['result'] = result
        else:
            result = {}
        if process['status'] == 'completed' and process.get('returncode') == 0 and result.get('ok') is True:
            runtime = result.get('runtime', {}).get('runtime_id')
            builder = result.get('builder', {})
            if (result.get('phase') != 'completed' or not isinstance(runtime, str)
                    or not re.fullmatch('[0-9a-f]{32}', runtime) or builder.get('ok') is not True
                    or builder.get('execution', {}).get('runtime_id') != runtime):
                raise ValueError('worker result lacks completed builder/runtime evidence')
            rows = result.get('checks', [])
            if not isinstance(rows, list) or len(rows) != len(manifest['checks']):
                raise ValueError('worker result is missing checks')
            for expected, row in zip(manifest['checks'], rows):
                if (not isinstance(row, dict) or any(row.get(key) != expected[key] for key in ('id', 'kind', 'node', 'frame'))
                        or row.get('status') != 'passed' or row.get('execution', {}).get('ok') is not True
                        or row.get('execution', {}).get('execution', {}).get('runtime_id') != runtime):
                    raise ValueError('worker result has incomplete/mismatched checks')
                if expected['kind'] != 'render':
                    checkpoint = row['execution'].get('result', {})
                    if checkpoint.get('ok') is not True or checkpoint.get('nonempty') is not True:
                        raise ValueError('geometry checkpoint did not pass')
                    for name, value in expected.get('expect', {}).items():
                        actual = row.get('geometry', {}).get(name)
                        if type(actual) is not int or actual != value:
                            raise ValueError('worker geometry expectation mismatch')
                else:
                    rendered = row['execution'].get('result', {})
                    if rendered.get('fresh') is not True or rendered.get('errors'):
                        raise ValueError('render checkpoint did not pass')
                if expected['kind'] != 'cook':
                    relative = 'artifacts/' + expected['id'] + '/' + expected['file']
                    artifact = row.get('artifact', {})
                    file = regular_file(output_dir, relative)
                    if file.stat().st_size <= 0 or artifact.get('file') != relative or artifact.get('sha256') != digest(file) or artifact.get('bytes') != file.stat().st_size:
                        raise ValueError('artifact integrity mismatch')
            report.update(ok=True, phase='completed')
        if not report['ok']:
            report['error'] = result.get('error') or process.get('error') or 'worker did not complete all checks'
    except Exception as error:
        report.update(ok=False, error=str(error) or type(error).__name__)
    try:
        unchanged = all(digest(regular_file(manifest_path.parent, row['file'])) == row['sha256'] for row in inputs)
    except Exception as error:
        unchanged = False
        report['input_check_error'] = str(error) or type(error).__name__
    report.update(inputs=inputs, inputs_unchanged=unchanged)
    if not unchanged:
        report.update(ok=False, error='source inputs changed; external side effects are not restored')
    write_json(output_dir / 'report.json', report)
    return report


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        if sys.stdin.readline().strip() != 'GO':
            return 2
        return worker(Path(sys.argv[2]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--hython', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--trusted', action='store_true')
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--memory-mb', type=int, default=4096)
    parser.add_argument('--cancel-file', type=Path)
    args = parser.parse_args()
    try:
        result = check(args.manifest, args.hython, args.output_dir, trusted=args.trusted,
                       timeout=args.timeout, memory_mb=args.memory_mb, cancel_file=args.cancel_file)
    except Exception as error:
        result = {'ok': False, 'phase': 'preflight', 'error': str(error) or type(error).__name__}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
