"""Run a trusted builder or copied saved HIP, with optional checks, in a NEW hython.

Never connects to live Houdini, edits the source HIP or retries
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
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from houdini_test_environment import isolated_environment, launch_directory

DETAIL_POLICY = json.loads((ROOT / 'houdini/result-detail-policy.json').read_text(encoding='utf-8'))
DETAIL_THRESHOLD = DETAIL_POLICY['detailThresholdChars']
MAX_ARCHIVE_BYTES = DETAIL_POLICY['maxArchiveBytes']

SCOPE = ('Disposable process; trusted builder or exact copied saved HIP; optional explicit output checks. '
         'Without checks, success proves only builder execution or snapshot loading. '
         'No live HIP edits, automatic retry or visual/semantic certification. '
         'Absolute-path, imported-code, callback and external-service side effects are not sandboxed/restored.')


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def read_json(path, max_bytes=4 * 1024 * 1024):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON field: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('nonfinite JSON value: ' + value)
    if path.stat().st_size > max_bytes:
        raise ValueError('JSON exceeds the %d byte read limit' % max_bytes)
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique, parse_constant=invalid)


def write_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(_encoded(value), encoding='utf-8')
    os.replace(temporary, path)


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _pointer(parent, key):
    return parent + '/' + str(key).replace('~', '~0').replace('/', '~1')


def _bounded(value, pointer, budget=DETAIL_THRESHOLD, *, retained=True):
    """A display projection only. The archived envelope owns omitted values."""
    text = _encoded(value)
    if len(text) <= budget:
        return value
    omitted = ({'detail_pointer': pointer, 'omitted_chars': len(text)} if retained else
               {'unavailable_field': pointer, 'omitted_chars': len(text),
                'reason': 'Complete execution details were not retained'})
    if isinstance(value, dict):
        out = dict(omitted)
        # These are existing execution/check facts, never inferred statuses.
        priority = ('ok', 'runtime_id', 'owner_session', 'sequence', 'nonempty', 'fresh', 'healthy',
                    'status', 'phase', 'scope', 'semantic_status', 'restored', 'current_state_preserved',
                    'dispatched', 'output', 'errors', 'failure_reasons', 'restore_errors', 'geometry')
        keys = [k for k in priority if k in value] + [k for k in value if k not in priority]
        for key in keys:
            remaining = budget - len(_encoded(out)) - len(_encoded(key)) - 16
            if remaining < 160:
                break
            out[key] = _bounded(value[key], _pointer(pointer, key), remaining, retained=retained)
        return out
    if isinstance(value, list):
        out = []
        for index, item in enumerate(value):
            remaining = budget - len(_encoded(out)) - len(_encoded(omitted)) - 16
            if remaining < 160:
                break
            out.append(_bounded(item, _pointer(pointer, index), min(remaining, 2048), retained=retained))
        return out + [omitted]
    return omitted


def _brief_text(value, budget=DETAIL_THRESHOLD, *, retained=None):
    if not isinstance(value, str) or len(value) <= budget:
        return value
    # Retain both the call context and final/root exception, with an explicit gap.
    note = ('see execution details' if retained is True else 'complete execution data was not retained'
            if retained is False else 'this field was shortened; a full source may exist separately')
    return value[:budget // 3] + '\n[Omitted; ' + note + ']\n' + value[-budget // 2:]


def execution_projection(directory, identifier, envelope, *, inline_budget=None):
    """Archive a large immutable returned envelope once; retain bounded facts.

    Failure to retain details must not change an already executed operation's
    ok/error. Mutable worker progress itself is never described by this hash.
    """
    text = _encoded(envelope)
    if len(text) < DETAIL_THRESHOLD:
        return envelope
    details = {'stored': False}
    try:
        data = text.encode('utf-8')
        if len(data) > MAX_ARCHIVE_BYTES:
            raise ValueError('returned envelope exceeds result retention budget')
        relative = 'executions/' + relative_file(identifier + '.json')
        target = directory / relative
        if is_reparse(directory) or is_reparse(target.parent) or is_reparse(target):
            raise ValueError('execution detail path contains a reparse point')
        target.parent.mkdir(exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
        details = {'stored': True, 'path': str(target.resolve()), 'sha256': hashlib.sha256(data).hexdigest(),
                   'bytes': len(data), 'format': 'returned_bridge_envelope_json'}
    except Exception as error:
        details['error'] = str(error) or type(error).__name__
        # Retain the complete inline fallback when it fits the *remaining run*
        # budget. Several failed archives cannot each consume a whole report.
        budget = MAX_ARCHIVE_BYTES - 65536 if inline_budget is None else inline_budget
        details['fallback'] = 'Full returned envelope retained inline; no separate execution archive'
        fallback = {**envelope, 'details': details}
        if len(_encoded(fallback).encode('utf-8')) <= budget:
            return fallback
        details['fallback'] = 'Complete execution data could not be retained; unavailable fields are explicit'
        details['full_retained'] = False
    retained = details['stored'] is True
    out = {'ok': envelope.get('ok'), 'details': details}
    for key in ('error', 'stderr', 'advisory'):
        if key in envelope:
            out[key] = _brief_text(envelope[key], retained=retained)
    if 'stdout' in envelope:
        out['stdout'] = _brief_text('\n'.join(line for line in envelope['stdout'].splitlines()
                                             if not line.startswith('[verb] ')), retained=retained)
    for key in ('outcome', 'transaction', 'execution', 'script', 'rollback', 'rawUsage', 'checks', 'result',
                'artifactCandidates', 'scope', 'semantic_status', 'restored'):
        if key in envelope:
            out[key] = _bounded(envelope[key], '/' + key, retained=retained)
    if 'evidence' in envelope:
        evidence = envelope['evidence']
        if len(_encoded(evidence)) > DETAIL_THRESHOLD:
            ledger = envelope.get('verbs', [])
            failed = {index + 1 for index, row in enumerate(ledger) if row.get('ok') is False}
            checked = {index + 1 for index, row in enumerate(ledger) if row.get('check_status')}
            def priority(item):
                row = item[1]
                if (row.get('ledgerIndex') in failed or row.get('ok') is False
                        or 'restored' in row and row['restored'] is not True or row.get('restore_errors')):
                    return 0
                return 1 if row.get('ledgerIndex') in checked else 2
            rows = sorted(enumerate(evidence), key=priority)
            out['evidence'] = []
            for index, row in rows:
                remaining = DETAIL_THRESHOLD - len(_encoded(out['evidence'])) - 160
                if remaining < 256:
                    break
                out['evidence'].append(_bounded(row, '/evidence/' + str(index), min(remaining, 2048), retained=retained))
            out['evidence'].append({('detail_pointer' if retained else 'unavailable_field'): '/evidence',
                                    'entries': len(evidence)})
        else:
            out['evidence'] = evidence
    return out


def read_execution(directory, envelope):
    """Read an immutable detail through its recorded content identity only."""
    details = envelope.get('details', {})
    if details.get('stored') is not True:
        return envelope
    try:
        path = Path(details['path'])
        relative = path.relative_to(directory.resolve()).as_posix()
        if len(Path(relative).parts) != 2 or not relative.startswith('executions/'):
            raise ValueError('execution details must stay inside this run executions directory')
        path = regular_file(directory, relative)
        if (details.get('format') != 'returned_bridge_envelope_json'
                or path.stat().st_size != details.get('bytes') or path.stat().st_size > MAX_ARCHIVE_BYTES
                or digest(path) != details.get('sha256')):
            raise ValueError('execution detail integrity mismatch')
        raw = read_json(path, MAX_ARCHIVE_BYTES)
        if (not isinstance(raw, dict) or raw.get('ok') != envelope.get('ok')
                or raw.get('execution', {}).get('runtime_id') != envelope.get('execution', {}).get('runtime_id')):
            raise ValueError('execution detail does not match projected execution identity')
        return raw
    except (ValueError, OSError, KeyError, TypeError) as error:
        envelope['details_error'] = str(error) or type(error).__name__
        return envelope


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


def manifest_input_root(path, manifest):
    value = manifest.get('input_root')
    if value is None:
        root = path.parent
    else:
        if not isinstance(value, str) or not value or '\x00' in value:
            raise ValueError('input_root must be an explicit directory path')
        root = Path(value)
        if not root.is_absolute():
            root = path.parent / root
    # An explicitly selected root may itself use a junction or filesystem alias.
    # After resolving that root, regular_file checks every child against it.
    root = root.resolve()
    if not root.is_dir():
        raise ValueError('input_root must be an existing directory')
    return root


def manifest_inputs(manifest):
    return [manifest[key] for key in ('hip', 'script') if key in manifest] + manifest.get('files', [])


def load_manifest(path):
    data = read_json(path)
    if not isinstance(data, dict) or set(data) - {'script', 'hip', 'input_root', 'files', 'checks'} or not ({'script', 'hip'} & set(data)):
        raise ValueError('manifest requires script and/or hip, plus optional input_root/files/checks')
    if 'script' in data and not relative_file(data['script']).endswith('.py'):
        raise ValueError('script must be a trusted .py builder, not a HIP')
    if 'hip' in data and not relative_file(data['hip']).lower().endswith(('.hip','.hiplc','.hipnc')):
        raise ValueError('hip must be an explicit saved HIP file')
    files = data.get('files', [])
    if not isinstance(files, list) or len(files) > 32:
        raise ValueError('files must contain at most 32 explicit relative files')
    inputs = [relative_file(value) for value in manifest_inputs(data)]
    if len(set(value.casefold() for value in inputs)) != len(inputs):
        raise ValueError('duplicate/aliased input file')
    size = 0
    input_root = manifest_input_root(path, data)
    for name in inputs:
        source = regular_file(input_root, name)
        size += source.stat().st_size
        if name == data.get('script') and source.stat().st_size > 1024 * 1024:
            raise ValueError('builder exceeds 1 MiB')
    if size > 2 * 1024 ** 3:
        raise ValueError('declared inputs exceed 2 GiB')
    checks = data.get('checks', [])
    if not isinstance(checks, list) or len(checks) > 16:
        raise ValueError('checks must contain 0..16 explicit operations')
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
    data['checks'] = checks
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
        import dsh_ownership
        session = 'isolated-' + request['run_id']
        result['runtime'] = {'houdini': hou.applicationVersionString(), 'runtime_id': bridge._RUNTIME_ID,
                             'execution_contract': bridge._EXECUTION_CONTRACT_VERSION,
                             'verb_catalog_sha256': bridge._VERB_CATALOG_HASH, 'owner_session': session}

        def execute(code, call, *, script=None):
            return bridge._execute(lambda: bridge.run_code(code, owner_session=session, owner_call=call, script=script))

        def retain(envelope, identifier):
            remaining = len(request['manifest']['checks']) - len(result['checks'])
            # Reserve room for future bounded projections and the outer report.
            # The raw fallback consumes one shared run budget, not 32 MiB per call.
            reserve = 65536 + len(_encoded(request).encode('utf-8')) + remaining * DETAIL_THRESHOLD * 80
            budget = MAX_ARCHIVE_BYTES - len(_encoded(result).encode('utf-8')) - reserve
            return execution_projection(directory, identifier, envelope, inline_budget=budget)

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
            input_directory = directory / 'inputs'
            script = input_directory / manifest['script'] if 'script' in manifest else None
            snapshot = input_directory / manifest['hip'] if 'hip' in manifest else None
            for row in request['inputs']:
                if digest(regular_file(directory / 'inputs', row['file'])) != row['sha256']:
                    raise ValueError('staged input digest mismatch')
            sys.path.insert(0, str(input_directory))
            if script is not None:
                sys.path.insert(0, str(script.parent))
            result['phase'] = 'snapshot_load' if 'hip' in manifest else 'builder'
            write_json(result_file, result)
            if 'hip' in manifest:
                # Trusted driver import into this fresh disposable process only.
                # Attribution is to identities created by this exact load, never
                # to a path, pre-existing scene, or original user's live nodes.
                before={int(n.sessionId()) for n in hou.node('/').allSubChildren()}
                warnings=[]
                try:hou.hipFile.load(str(snapshot),suppress_save_prompt=True,ignore_load_warnings=False)
                except hou.LoadWarning as error:
                    from dsh_load_warnings import preview
                    original=str(error);excerpt,omitted=preview(original)
                    warning_file=directory/'load-warnings.txt';warning_file.write_text(original,encoding='utf-8')
                    warnings.append({'text':excerpt,'omitted_chars':omitted,'file':str(warning_file),'sha256':digest(warning_file)})
                if Path(hou.hipFile.path()).resolve()!=snapshot.resolve():raise ValueError('snapshot load did not select the copied HIP')
                with dsh_ownership.execution_owner(session,'snapshot_load'):
                    for parent in hou.node('/').children():
                        for node in parent.children():
                            if int(node.sessionId()) not in before:dsh_ownership.register_owned_node(node,exclude_ids=before)
                result['snapshot']={'path':str(snapshot),'sha256':digest(snapshot),'load_warnings':warnings,
                    'scope':'Copied saved state only; unsaved live edits and undeclared external dependencies are not represented.'}
            result['phase'] = 'builder'
            write_json(result_file, result)
            if script is not None:
                data = script.read_bytes()
                source_hash = hashlib.sha256(data).hexdigest()
                declared = next(row for row in request['inputs'] if row['file'] == manifest['script'])
                if source_hash != declared['sha256'] or len(data) != declared['bytes']:
                    raise ValueError('staged script changed before execution')
                record = {'path': str(script.resolve()), 'sha256': source_hash, 'bytes': len(data)}
                raw_builder = execute(data.decode('utf-8'), 'builder', script=record)
            else:
                raw_builder = execute('__result__={"snapshot_loaded":True}', 'snapshot_loaded')
            result['builder'] = retain(raw_builder, 'builder')
            successful(raw_builder)
            for check in manifest['checks']:
                row = {'id': check['id'], 'kind': check['kind'], 'node': check['node'], 'frame': check['frame'], 'status': 'running'}
                result['checks'].append(row)
                result['phase'] = 'check:' + check['id']
                write_json(result_file, result)
                try:
                    node = hou.node(check['node'])
                    if node is None:
                        raise ValueError('missing explicit output: ' + check['node'])
                    with dsh_ownership.execution_owner(session, check['id']):
                        dsh_ownership.require_owned(node, 'isolated check')
                    frame_code = f'set_timeline(current_frame={check["frame"]!r})\n'
                    if check['kind'] == 'render':
                        artifact = artifact_target(directory, check)
                        raw_execution = execute(frame_code + f'__result__=render_frame({node.path()!r},picture={str(artifact)!r},frame={check["frame"]!r})', check['id'])
                        row['execution'] = retain(raw_execution, 'check-' + check['id'])
                        rendered = successful(raw_execution)
                        if rendered.get('errors') or rendered.get('fresh') is not True:
                            raise ValueError('render did not produce a fresh error-free artifact')
                    else:
                        if node.type().category() != hou.sopNodeTypeCategory():
                            raise ValueError('cook/cache require a SOP output')
                        raw_execution = execute(frame_code + f'__result__=verify_network({node.parent().path()!r},output={node.path()!r},nodes=[{node.path()!r}])', check['id'])
                        row['execution'] = retain(raw_execution, 'check-' + check['id'])
                        geometry = successful(raw_execution)['geometry']
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
                    row.update(status='failed', error=_brief_text(str(error) or type(error).__name__))
                    raise
                finally:
                    write_json(result_file, result)
            result.update(ok=True, phase='completed')
        bridge._execute(run)
    except BaseException as error:
        result['error'] = _brief_text(str(error) or type(error).__name__)
    write_json(result_file, result)
    return 0 if result['ok'] else 1


def check(manifest_path, hython, output_dir, *, trusted=False, timeout=120, memory_mb=4096, cancel_file=None):
    if trusted is not True:
        raise ValueError('explicit trusted=True/--trusted authorization is required to execute the builder and dependencies')
    manifest_path, hython, output_dir = Path(manifest_path).resolve(), Path(hython).resolve(), Path(output_dir).resolve()
    manifest = load_manifest(manifest_path)
    input_root = manifest_input_root(manifest_path, manifest)
    output_dir.mkdir()  # exclusive run directory; never overwrite prior evidence
    cancel_file = Path(cancel_file).resolve() if cancel_file is not None else output_dir / 'cancel.request'
    run_id = uuid.uuid4().hex
    report = {'ok': False, 'run_id': run_id, 'phase': 'staging', 'finished':False,
              'cancel_file': str(cancel_file), 'scope': SCOPE}
    write_json(output_dir / 'report.json',report)
    inputs = []
    runtime_directory = None
    runtime_identity = None
    process = None
    try:
        for name in manifest_inputs(manifest):
            source = regular_file(input_root, name)
            target = output_dir / 'inputs' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            before = digest(source)
            shutil.copy2(source, target)
            if digest(target) != before:
                raise ValueError('input changed during staging')
            inputs.append({'file': name, 'sha256': before, 'bytes': target.stat().st_size})
        request = {'run_id': run_id, 'manifest': manifest, 'input_root': str(input_root), 'inputs': inputs}
        request_file = output_dir / 'request.json'
        write_json(request_file, request)
        runtime_parent = Path(tempfile.gettempdir()).resolve()
        runtime_directory = Path(tempfile.mkdtemp(prefix='dsh-isolated-runtime-', dir=runtime_parent))
        runtime_identity = runtime_directory.stat()
        report['runtime_environment'] = {'path': str(runtime_directory), 'cleaned': False}
        env = isolated_environment(runtime_directory, executable=hython if hython.is_file() else None)
        sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
        from dsh_worker_limits import run_gated_worker
        process = run_gated_worker([str(hython), str(Path(__file__).resolve()), '--worker', str(request_file)],
                                  cwd=launch_directory(hython) if hython.is_file() else output_dir,
                                  env=env, timeout=timeout, memory_mb=memory_mb, cancel_file=cancel_file)
        report.update(phase='worker_result', worker=process)
        result_file = output_dir / 'worker-result.json'
        if result_file.exists():
            result = read_json(result_file, MAX_ARCHIVE_BYTES)
            if not isinstance(result, dict) or result.get('run_id') != run_id:
                raise ValueError('worker result identity mismatch')
            builder = read_execution(output_dir, result.get('builder', {}))
            checked_executions = [read_execution(output_dir, row.get('execution', {})) if isinstance(row, dict) else {}
                                  for row in result.get('checks', [])]
            report['result'] = result
        else:
            result = {}
        if process['status'] == 'completed' and process.get('returncode') == 0 and result.get('ok') is True:
            runtime = result.get('runtime', {}).get('runtime_id')
            if (result.get('phase') != 'completed' or not isinstance(runtime, str)
                    or not re.fullmatch('[0-9a-f]{32}', runtime) or builder.get('ok') is not True
                    or builder.get('execution', {}).get('runtime_id') != runtime):
                raise ValueError('worker result lacks completed builder/runtime evidence')
            if 'hip' in manifest:
                snapshot=result.get('snapshot',{})
                hip_input = next(row for row in inputs if row['file'] == manifest['hip'])
                if (snapshot.get('sha256')!=hip_input['sha256']
                    or Path(snapshot.get('path','')).resolve()!=(output_dir/'inputs'/manifest['hip']).resolve()):
                    raise ValueError('worker snapshot source identity mismatch')
            rows = result.get('checks', [])
            if not isinstance(rows, list) or len(rows) != len(manifest['checks']):
                raise ValueError('worker result is missing checks')
            for expected, row, execution in zip(manifest['checks'], rows, checked_executions):
                if (not isinstance(row, dict) or any(row.get(key) != expected[key] for key in ('id', 'kind', 'node', 'frame'))
                        or row.get('status') != 'passed' or execution.get('ok') is not True
                        or execution.get('execution', {}).get('runtime_id') != runtime):
                    raise ValueError('worker result has incomplete/mismatched checks')
                if expected['kind'] != 'render':
                    checkpoint = execution.get('result', {})
                    if checkpoint.get('ok') is not True or checkpoint.get('nonempty') is not True:
                        raise ValueError('geometry checkpoint did not pass')
                    for name, value in expected.get('expect', {}).items():
                        actual = row.get('geometry', {}).get(name)
                        if type(actual) is not int or actual != value:
                            raise ValueError('worker geometry expectation mismatch')
                else:
                    rendered = execution.get('result', {})
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
        report.update(ok=False, error=_brief_text(str(error) or type(error).__name__))
    finally:
        if runtime_directory is not None:
            environment = report['runtime_environment']
            if process is not None and process.get('tree_reaped') is True:
                try:
                    # Remove only this invocation's exact mkdtemp identity after
                    # the owned Job reports zero processes, never a user run root.
                    current = runtime_directory.lstat()
                    if (runtime_directory.parent != runtime_parent
                            or not runtime_directory.name.startswith('dsh-isolated-runtime-')
                            or is_reparse(runtime_directory) or runtime_directory.resolve() != runtime_directory
                            or (current.st_dev, current.st_ino) != (runtime_identity.st_dev, runtime_identity.st_ino)):
                        raise ValueError('runtime temporary directory identity changed; retained')
                    shutil.rmtree(runtime_directory)
                    environment['cleaned'] = True
                except Exception as error:
                    environment['cleanup_error'] = str(error) or type(error).__name__
            else:
                environment['retained_reason'] = 'owned worker tree exit was not confirmed'
    try:
        unchanged = all(digest(regular_file(input_root, row['file'])) == row['sha256'] for row in inputs)
    except Exception as error:
        unchanged = False
        report['input_check_error'] = str(error) or type(error).__name__
    report.update(inputs=inputs, inputs_unchanged=unchanged,finished=True)
    if not unchanged:
        report['ok'] = False
        report.setdefault('input_check_error', 'source inputs changed; external side effects are not restored')
        report.setdefault('error', report['input_check_error'])
    write_json(output_dir / 'report.json', report)
    return report


def status(directory, cancel=False):
    directory=Path(directory).resolve()
    report=read_json(directory/'report.json', MAX_ARCHIVE_BYTES)
    request=(read_json(directory/'request.json') if (directory/'request.json').exists()
             else {'run_id':report.get('run_id'),'inputs':report.get('inputs',[])})
    if not re.fullmatch('[0-9a-f]{32}',str(report.get('run_id',''))):raise ValueError('invalid run report identity')
    if report.get('run_id')!=request.get('run_id'):raise ValueError('run report identity mismatch')
    cancel_file=Path(report.get('cancel_file',directory/'cancel.request'))
    if cancel and report.get('finished') is not True:
        write_json(cancel_file,{'run_id':request['run_id'],'action':'cancel_owned_worker'})
    progress=read_json(directory/'worker-result.json', MAX_ARCHIVE_BYTES) if (directory/'worker-result.json').exists() else None
    if progress is not None and progress.get('run_id')!=request['run_id']:raise ValueError('progress identity mismatch')
    result=report.get('result') or progress or {}
    def brief(value):
        if not isinstance(value,str) or len(value)<=2000:return value
        return value[:2000]+'\n[Longer error preview retained in report.json]'
    worker=report.get('worker')
    if isinstance(worker,dict):
        # The report keeps worker output and complete execution errors. Status
        # is a small machine-readable view, not a second execution ledger.
        worker={key:brief(value) if key=='error' else value for key,value in worker.items() if key!='output'}
    return {'ok':report.get('ok') is True,'run_id':request['run_id'],'finished':report.get('finished') is True,
        'phase':report.get('phase') if report.get('finished') else result.get('phase',report.get('phase')),
        'worker':worker, 'error':brief(report.get('error')),
        'cancel_requested':cancel_file.exists(),
        'inputs':report.get('inputs',request['inputs']),'inputs_unchanged':report.get('inputs_unchanged'),
        'snapshot':result.get('snapshot'),
        'checks':[{k:brief(r[k]) if k=='error' else r[k] for k in ('id','kind','node','frame','status','geometry','artifact','error') if k in r}
                  for r in result.get('checks',[])],
        'report':str(directory/'report.json'),'progress':str(directory/'worker-result.json'),
        'runtime_environment':report.get('runtime_environment'),
        'scope':'Last recorded run evidence, not a live-process liveness claim. Cancellation is a request until a terminal report confirms it. Large immutable execution details are referenced from the report.'}


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        if sys.stdin.readline().strip() != 'GO':
            return 2
        return worker(Path(sys.argv[2]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--hython', type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--trusted', action='store_true')
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--memory-mb', type=int, default=4096)
    parser.add_argument('--cancel-file', type=Path)
    parser.add_argument('--status',action='store_true',help='Read durable progress/result without executing Houdini')
    parser.add_argument('--cancel',action='store_true',help='Request cancellation of this run only; does not start or retry work')
    args = parser.parse_args()
    if args.status or args.cancel:
        print(json.dumps(status(args.output_dir,cancel=args.cancel),ensure_ascii=False,separators=(',',':')))
        return 0
    if args.manifest is None or args.hython is None:parser.error('--manifest and --hython required for execution')
    try:
        result = check(args.manifest, args.hython, args.output_dir, trusted=args.trusted,
                       timeout=args.timeout, memory_mb=args.memory_mb, cancel_file=args.cancel_file)
    except Exception as error:
        result = {'ok': False, 'phase': 'preflight', 'error': str(error) or type(error).__name__}
    print(json.dumps(status(args.output_dir) if result.get('run_id') else result, ensure_ascii=False, separators=(',',':')))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
