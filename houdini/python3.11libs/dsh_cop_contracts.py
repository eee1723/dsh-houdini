"""Bounded native Copernicus observations and reversible scalar-control checks.

Invoked only through helpers/Bridge on Houdini's owning thread. No network,
disk writes, geometry proxies or implicit sampling. GPU cook allocation itself
is not bounded by max_pixels; use the isolated worker for unknown graphs.
"""
import hashlib
import json
import math
import time

import hou
import numpy as np


def _helpers():
    import dsh_hou_helpers
    return dsh_hou_helpers


def _finite(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(label + ' must be finite numeric (not boolean)')
    return float(value)


def _budget(value):
    if type(value) is not int or not 1 <= value <= 16777216:
        raise ValueError('max_pixels must be 1..16777216')


def _range(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(label + ' must be [min,max]')
    low, high = (_finite(x, label) for x in value)
    if low > high:
        raise ValueError(label + ' min exceeds max')
    return low, high


def _exact(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(label + ' has unknown fields or is not an object')


_DEPENDENCY_NODE_LIMIT = 4096
_DEPENDENCY_EDGE_LIMIT = 32768
_DEPENDENCY_SECONDS = 2.0


def _cache_evidence(node):
    """Bounded native dependencies; not proof against dynamic/external effects."""
    pending, seen, sticky = [node], {node.sessionId()}, []
    edges = 0
    deadline = time.monotonic() + _DEPENDENCY_SECONDS
    while pending:
        current = pending.pop()
        if time.monotonic() > deadline:
            raise ValueError('COP dependency inspection time budget exceeded; freshness unverified')
        if isinstance(current, hou.CopNode) and current.type().nameComponents()[2] == 'cache':
            parm = current.parm('clearonchange')
            if parm is None or not parm.eval():
                sticky.append(current.path())
        for dependency in (*current.inputs(), *current.references()):
            if dependency is None:
                continue
            edges += 1
            if edges > _DEPENDENCY_EDGE_LIMIT:
                raise ValueError('COP dependency inspection edge budget exceeded; freshness unverified')
            identity = dependency.sessionId()
            if identity not in seen:
                if len(seen) >= _DEPENDENCY_NODE_LIMIT:
                    raise ValueError(f'COP dependency inspection exceeds {_DEPENDENCY_NODE_LIMIT} nodes; freshness unverified')
                seen.add(identity)
                pending.append(dependency)
    return {'sticky_cache_nodes': sorted(sticky), 'nodes_inspected': len(seen),
            'edges_inspected': edges, 'node_limit': _DEPENDENCY_NODE_LIMIT,
            'scope': 'native input/reference graph only; dynamic dependencies and external changes unverified'}


def _rect(rect):
    return list(rect.min()) + list(rect.max())


_ALIGNMENT = ('resolution', 'channels', 'data_window', 'display_window', 'pixel_scale',
              'pixel_aspect', 'image_to_world', 'projection', 'projection_transform', 'frame')


def _read(node, output, max_pixels):
    _budget(max_pixels)
    h = _helpers()
    from dsh_cook_control import require_evaluation
    require_evaluation('COP layer observation')
    n = h._resolve(node)
    if not isinstance(n, hou.CopNode):
        raise ValueError('requires a Copernicus node, not COP2/SOP/ROP')
    port = h._resolve_port(n, output, 'output')
    cache = _cache_evidence(n)
    cooked = h.cook_node(n)
    if not cooked['ok']:
        raise ValueError('COP cook failed; layer was not read: ' + str(cooked['errors']))
    frame = float(hou.frame())
    layer = n.layer(port)
    if layer is None:
        raise ValueError('selected output is not an ImageLayer')
    try:
        width, height = map(int, layer.bufferResolution())
        channels = int(layer.channelCount())
        if not 1 <= width * height <= max_pixels or width <= 0 or height <= 0:
            raise ValueError(f'buffer pixel budget/empty output: {width}x{height}, max_pixels={max_pixels}; no sampling')
        if channels not in (1, 2, 3, 4):
            raise ValueError('unsupported ImageLayer channel count')
        storage = layer.storageType().name()
        dtypes = {'Float16': np.float16, 'Float32': np.float32,
                  'Int8': np.int8, 'Int16': np.int16, 'Int32': np.int32}
        # Fixed-point layers need native decoding; do not reinterpret fixed bytes as integers.
        if storage not in dtypes:
            raise ValueError('unsupported storage type: ' + storage + '; no implicit conversion')
        meta = {'node': n.path(), 'identity': int(n.sessionId()), 'output': port,
                'output_name': n.outputNames()[port], 'output_type': n.outputDataTypes()[port],
                'resolution': [width, height], 'channels': channels, 'storage_type': storage,
                'type_info': str(layer.typeInfo()), 'data_window': _rect(layer.dataWindow()),
                'display_window': _rect(layer.displayWindow()), 'pixel_scale': list(layer.pixelScale()),
                'pixel_aspect': float(layer.pixelAspectRatio()),
                'image_to_world': list(layer.imageToWorldTransform().asTuple()),
                'projection': str(layer.projection()),
                'projection_transform': list(layer.projectionTransform().asTuple()),
                'border': str(layer.border()), 'frame': frame, 'runtime_version': hou.applicationVersionString()}
        raw = layer.allBufferElements()
        expected = width * height * channels * np.dtype(dtypes[storage]).itemsize
        if len(raw) != expected:
            raise ValueError(f'buffer layout mismatch: expected {expected} bytes, got {len(raw)}')
        data = np.frombuffer(raw, dtype=dtypes[storage]).reshape((height, width, channels)).copy()
        digest = hashlib.sha256(json.dumps(meta, sort_keys=True, allow_nan=False).encode())
        digest.update(raw)
        meta.update(sha256=digest.hexdigest(), checked_at=time.time(), warnings=cooked['warnings'],
                    cache=cache, freshness='unverified' if cache['sticky_cache_nodes'] else 'evaluated_current_graph',
                    scope='full current buffer; no semantic, external-source freshness or whole-asset guarantee')
        return meta, data
    finally:
        layer.close()


def _stats(data):
    result = []
    for index in range(data.shape[2]):
        channel = data[:, :, index].astype(np.float64)
        finite = np.isfinite(channel)
        values = channel[finite]
        def variation(axis):
            differences = np.abs(np.diff(channel, axis=axis))
            good = differences[np.isfinite(differences)]
            return float(np.mean(good)) if good.size else None
        result.append({'channel': index, 'finite_count': int(finite.sum()),
                       'nonfinite_count': int(channel.size - finite.sum()),
                       'min': float(values.min()) if values.size else None,
                       'max': float(values.max()) if values.size else None,
                       'mean': float(values.mean()) if values.size else None,
                       'mean_abs_gradient_u': variation(1), 'mean_abs_gradient_v': variation(0)})
    return result


def layer_stats(node, output=0, *, max_pixels=4194304):
    meta, data = _read(node, output, max_pixels)
    stats = _stats(data)
    finite = all(s['nonfinite_count'] == 0 for s in stats)
    return dict(meta, ok=finite, status=('unverified' if meta['cache']['sticky_cache_nodes'] else 'pass') if finite else 'fail', statistics=stats,
                semantic_status='unverified', sample_count=data.shape[0] * data.shape[1], sampled=False)


def _aligned(a, b):
    mismatch = [key for key in _ALIGNMENT if a[key] != b[key]]
    if mismatch:
        raise ValueError('layer alignment mismatch (no resampling): ' + ', '.join(mismatch))


def _require_finite(data):
    if not np.isfinite(data).all():
        raise ValueError('nonfinite layer cannot support a relation/control verdict')


def compare_layers(before, after, *, before_output=0, after_output=0, expected_delta=None,
                   tolerance=1e-6, max_pixels=4194304):
    tolerance = _finite(tolerance, 'tolerance')
    if tolerance < 0:
        raise ValueError('tolerance must be nonnegative')
    if expected_delta is not None:
        _exact(expected_delta, ('node', 'output'), 'expected_delta')
        if 'node' not in expected_delta:
            raise ValueError('expected_delta requires node')
    am, a = _read(before, before_output, max_pixels)
    bm, b = _read(after, after_output, max_pixels)
    _aligned(am, bm)
    _require_finite(a); _require_finite(b)
    difference = b.astype(np.float64) - a.astype(np.float64)
    result = {'before': am, 'after': bm, 'formula': 'after - before',
              'statistics': _stats(difference), 'max_abs_difference': float(np.max(np.abs(difference))),
              'status': 'unverified', 'ok': None, 'semantic_status': 'unverified',
              'scope': 'aligned full-buffer measurement; no semantic or visual certification'}
    if expected_delta is not None:
        dm, d = _read(expected_delta['node'], expected_delta.get('output', 0), max_pixels)
        _aligned(am, dm); _require_finite(d)
        error = float(np.max(np.abs(difference - d.astype(np.float64))))
        fresh = not any(m['cache']['sticky_cache_nodes'] for m in (am, bm, dm))
        result.update(expected_delta=dm, formula='(after - before) - expected_delta',
                      max_abs_error=error, tolerance=tolerance,
                      ok=(error <= tolerance) if fresh else None,
                      status=('pass' if error <= tolerance else 'fail') if fresh else 'unverified')
    return result


def _measure(data, baseline, expectation):
    values = data[:, :, expectation['channel']].astype(np.float64)
    metric = expectation['metric']
    if metric == 'mean': return float(values.mean())
    if metric == 'min': return float(values.min())
    if metric == 'max': return float(values.max())
    changes = np.abs(values - baseline[:, :, expectation['channel']].astype(np.float64))
    return float(changes.mean() if metric == 'mean_abs_change' else changes.max())


def test_controls(controller, output, tests, *, output_port=0, max_pixels=4194304, allow_foreign=None):
    h = _helpers()
    from dsh_cook_control import require_evaluation
    require_evaluation('test_cop_controls')
    _budget(max_pixels)
    ctrl = h._resolve(controller)
    h._require_owned(ctrl, 'test_cop_controls', allow_foreign)
    if not isinstance(tests, list) or not 1 <= len(tests) <= 16:
        raise ValueError('tests requires 1..16 cases')
    names, ids = set(), set()
    for test in tests:
        _exact(test, ('id', 'values', 'expectations'), 'test')
        if not isinstance(test.get('id'), str) or not test['id'] or test['id'] in ids:
            raise ValueError('test ids must be nonempty and unique')
        ids.add(test['id'])
        values, expectations = test.get('values'), test.get('expectations')
        if not isinstance(values, dict) or not 1 <= len(values) <= 8:
            raise ValueError('values requires 1..8 scalar controls')
        for name, value in values.items():
            _finite(value, 'control value')
            if not isinstance(name, str): raise ValueError('parameter name must be a string')
            p = ctrl.parm(name)
            if p is None: raise ValueError('unknown parameter: ' + name)
            tpl = p.parmTemplate()
            if tpl.type() not in (hou.parmTemplateType.Float, hou.parmTemplateType.Int, hou.parmTemplateType.Toggle):
                raise ValueError('only numeric scalar controls supported')
            if tpl.numComponents() != 1 or tpl.scriptCallback() or p.isMultiParmInstance():
                raise ValueError('tuple/callback/multiparm controls unsupported')
            if hasattr(tpl, 'menuItems') and tpl.menuItems(): raise ValueError('menu controls unsupported')
            if tpl.type() in (hou.parmTemplateType.Int, hou.parmTemplateType.Toggle) and type(value) is not int:
                raise ValueError('integer control needs integer value')
            if tpl.type() == hou.parmTemplateType.Toggle and value not in (0, 1):
                raise ValueError('toggle needs 0 or 1')
            if p.eval() == value: raise ValueError('perturbation must differ from baseline')
            names.add(name)
        if not isinstance(expectations, list) or not 1 <= len(expectations) <= 16:
            raise ValueError('expectations requires 1..16 measurements')
        nonzero = False
        for e in expectations:
            _exact(e, ('metric', 'channel', 'delta', 'range'), 'expectation')
            if e.get('metric') not in ('mean', 'min', 'max', 'mean_abs_change', 'max_abs_change'):
                raise ValueError('unsupported COP metric')
            if type(e.get('channel')) is not int or e['channel'] < 0:
                raise ValueError('channel must be a nonnegative index')
            low, high = _range(e.get('delta'), 'delta')
            nonzero |= low > 0 or high < 0
            if 'range' in e: _range(e['range'], 'range')
        if not nonzero: raise ValueError('each case needs a nonzero expected response')
    snapshots = h._parameter_snapshot([ctrl.parm(n) for n in sorted(names)])
    frame = float(hou.frame())
    meta, baseline = _read(output, output_port, max_pixels)
    if not h._parameter_restore_evidence(snapshots)['ok'] or float(hou.frame()) != frame:
        raise h.CheckpointError('baseline evaluation changed controller/frame; stop editing',
                               dict(ok=False, restored=False, controller=ctrl.path(), output=meta['node']))
    _require_finite(baseline)
    if meta['cache']['sticky_cache_nodes']:
        raise ValueError('sticky upstream Cache cannot certify control/restoration; zero parameter writes')
    baselines = {}
    for test in tests:
        for e in test['expectations']:
            if e['channel'] >= baseline.shape[2]: raise ValueError('channel outside layer; zero parameter writes')
        measurements = [_measure(baseline, baseline, e) for e in test['expectations']]
        baselines[test['id']] = measurements
        if any('range' in e and not e['range'][0] <= v <= e['range'][1]
               for e, v in zip(test['expectations'], measurements)):
            return dict(ok=False, status='fail', restored=True, parameter_writes=0,
                        controller=ctrl.path(), output=meta['node'], results=[], case_id=test['id'],
                        reason='baseline outside declared range', semantic_status='unverified')
    rows, writes = [], 0
    for test in tests:
        row = {'id': test['id'], 'values': test['values'], 'status': 'fail'}
        try:
            writes += len(test['values'])
            h.set_parms(ctrl, test['values'], allow_foreign=allow_foreign)
            actual = {name: ctrl.parm(name).eval() for name in test['values']}
            if any(not math.isclose(actual[n], v, rel_tol=1e-9, abs_tol=1e-12) for n,v in test['values'].items()):
                raise ValueError('requested perturbation not applied exactly')
            current_meta, current = _read(output, output_port, max_pixels)
            _aligned(meta, current_meta); _require_finite(current)
            if current_meta['cache']['sticky_cache_nodes']: raise ValueError('sticky cache appeared during test')
            checks = []
            for e, base in zip(test['expectations'], baselines[test['id']]):
                value = _measure(current, baseline, e)
                delta = value - base
                passed = e['delta'][0] <= delta <= e['delta'][1]
                if 'range' in e: passed &= e['range'][0] <= value <= e['range'][1]
                checks.append(dict(expectation=e, baseline=base, value=value, delta=delta,
                                   status='pass' if passed else 'fail'))
            row.update(status='pass' if all(c['status']=='pass' for c in checks) else 'fail',
                       measurements=checks, actual_values=actual, output_changed=not np.array_equal(current, baseline),
                       output_sha256=current_meta['sha256'], warnings=current_meta['warnings'])
        except h.CheckpointError:
            raise
        except Exception as error:
            row.update(status='fail', reason=str(error))
        finally:
            errors = h._restore_parameters(snapshots)
            if float(hou.frame()) != frame:
                try: hou.setFrame(frame)
                except Exception as error: errors.append('frame restore: ' + str(error))
            try:
                restored_meta, _ = _read(output, output_port, max_pixels)
                same = restored_meta['sha256'] == meta['sha256'] and not restored_meta['cache']['sticky_cache_nodes']
            except Exception as error:
                errors.append('output restore: ' + str(error)); same = False
            evidence = h._parameter_restore_evidence(snapshots)
            errors.extend(evidence['errors'])
            if float(hou.frame()) != frame: errors.append('frame changed during restoration cook')
            row.update(restored=not errors and same, parameter_restore=evidence, restore_errors=errors,
                       output_restored=same)
            if not row['restored']:
                raise h.CheckpointError('test_cop_controls restoration failed; stop editing',
                    dict(ok=False, status='fail', restored=False, controller=ctrl.path(), output=meta['node'], results=rows+[row]))
        rows.append(row)
    ok = all(row['status'] == 'pass' for row in rows)
    return dict(ok=ok, status='pass' if ok else 'fail', restored=True, controller=ctrl.path(), output=meta['node'],
                output_port=meta['output'], baseline=meta, results=rows, parameter_writes=writes,
                semantic_status='unverified', coverage={'declared_controls': sorted(names), 'cases':len(rows)},
                scope='declared scalar cases and full buffer only; external files, Python, solver effects not restored')
