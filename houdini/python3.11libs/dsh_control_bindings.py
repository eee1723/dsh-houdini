"""Explicit numeric controller bindings with preflight revisions and channel rollback."""
from __future__ import annotations

import hashlib
import json
import math

import hou


def _channel(p):
    keys = tuple(p.keyframes())
    if len(keys) > 256:
        raise ValueError('binding plan supports at most 256 keys per channel')
    t = p.parmTemplate()
    return {'path': p.path(), 'node_identity': p.node().sessionId(),
            'keys': [key.asCode() for key in keys], 'locked': p.isLocked(),
            'value': p.eval(), 'template': {'type': t.type().name(), 'components': t.numComponents(),
                'min': getattr(t,'minValue',lambda:None)(), 'max': getattr(t,'maxValue',lambda:None)(),
                'min_strict':getattr(t,'minIsStrict',lambda:None)(), 'max_strict':getattr(t,'maxIsStrict',lambda:None)()}}


def _numeric(p, source=False):
    if p is None:
        raise ValueError('binding parameter does not exist')
    t = p.parmTemplate()
    kinds = (hou.parmTemplateType.Float, hou.parmTemplateType.Int, hou.parmTemplateType.Toggle)
    if (t.type() not in kinds or p.isMultiParmInstance() or t.scriptCallback() or
            getattr(t, 'menuItems', lambda: ())() or getattr(t, 'itemGeneratorScript', lambda: '')()):
        raise ValueError(f'{p.path()}: binding needs numeric channels without menus/callbacks/multiparms')
    if not source and (p.isLocked() or t.type() == hou.parmTemplateType.Toggle):
        raise ValueError(f'{p.path()}: target must be unlocked float/int')
    if source:
        # Arbitrary upstream expressions require graph reasoning beyond this bounded contract.
        for key in p.keyframes():
            try:
                expression = key.expression()
            except hou.KeyframeValueNotSet:
                continue
            if key.expressionLanguage() != hou.exprLanguage.Hscript or expression not in {
                    'constant()', 'linear()', 'bezier()', 'cubic()', 'qlinear()', 'spline()'}:
                raise ValueError(f'{p.path()}: expression-driven sources require a separate dependency plan')
    value = p.eval()
    if not math.isfinite(value):
        raise ValueError(f'{p.path()}: non-finite channel value')
    return value


def bind_controls(controller, bindings, dry_run=False, expected_plan=None,
                  replace_existing=False, allow_foreign=None):
    import dsh_hou_helpers as h
    try:
        plan, prepared = _prepare(controller, bindings, dry_run, replace_existing, allow_foreign)
        if dry_run:
            return {**plan, 'ok': True, 'dry_run': True, 'scene_writes': 0, 'applied': False}
        if expected_plan != plan['plan_sha256']:
            raise ValueError('stale or missing binding plan; preview again with dry_run=True')
        # _parameter_snapshot keys by name; targets on different nodes may have the same name.
        snapshots = {target.path(): next(iter(h._parameter_snapshot([target]).values()))
                     for source, target, expression, value in prepared}
    except Exception as error:
        raise h.CheckpointError(str(error), {'ok': False, 'phase': 'binding_preflight',
                                'scene_writes': 0, 'applied': False}) from error
    try:
        installed = []
        for source, target, expression, expected_value in prepared:
            try:
                same = target.expressionLanguage() == hou.exprLanguage.Hscript and target.expression() == expression
            except hou.OperationFailed:
                same = False
            if not same:
                target.deleteAllKeyframes()
                target.setExpression(expression, hou.exprLanguage.Hscript, replace_expression=True)
            if target.expression() != expression or target.expressionLanguage() != hou.exprLanguage.Hscript:
                raise RuntimeError(f'{target.path()}: expression readback mismatch')
            actual = target.eval()
            if not math.isclose(actual, expected_value, rel_tol=1e-7, abs_tol=1e-7):
                raise RuntimeError(f'{target.path()}: value mismatch, expected {expected_value}, got {actual}')
            installed.append({'source': source.path(), 'target': target.path(), 'expression': expression,
                              'actual_value': actual, 'changed': not same})
        return {'ok': True, 'applied': True, 'controller': plan['controller'],
                'bindings': installed, 'plan_sha256': plan['plan_sha256'],
                'scope': 'binding expression/current channel value only; domain output unverified'}
    except Exception as error:
        failures = h._restore_parameters(snapshots)
        raise h.CheckpointError(f'binding failed: {error}; restoration errors={failures}',
            {'ok': False, 'restored': not failures, 'restore_errors': failures,
             'scope': 'target channel values/keys only; external effects unverified'}) from error


def _prepare(controller, bindings, dry_run, replace_existing, allow_foreign):
    import dsh_hou_helpers as h
    n = h._resolve(controller)
    if type(dry_run) is not bool or type(replace_existing) is not bool:
        raise ValueError('dry_run/replace_existing must be boolean')
    if not isinstance(bindings, list) or not 1 <= len(bindings) <= 32:
        raise ValueError('bindings requires 1..32 entries')
    prepared, summary, targets, sources = [], [], set(), set()
    for item in bindings:
        if (not isinstance(item, dict) or set(item) - {'source', 'target', 'scale', 'offset'} or
                not isinstance(item.get('source'), str) or '/' in item['source'] or
                not isinstance(item.get('target'), str) or not item['target'].startswith('/')):
            raise ValueError('binding needs source parameter name and explicit absolute target parameter path')
        source, target = n.parm(item['source']), hou.parm(item['target'])
        source_value = _numeric(source, source=True)
        old_value = _numeric(target)
        h._require_owned(target.node(), 'bind_controls target', allow_foreign)
        if target.path() in targets:
            raise ValueError('duplicate binding target')
        targets.add(target.path()); sources.add(source.path())
        scale, offset = item.get('scale', 1), item.get('offset', 0)
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (scale, offset)):
            raise ValueError('scale/offset must be finite numeric literals')
        if target.parmTemplate().type() == hou.parmTemplateType.Int and (
                source.parmTemplate().type() not in (hou.parmTemplateType.Int, hou.parmTemplateType.Toggle) or
                type(scale) is not int or type(offset) is not int):
            raise ValueError('integer targets require integer sources and integer scale/offset')
        relative = target.node().relativePathTo(source.node()) + '/' + source.name()
        expression = f'ch({json.dumps(relative)}) * {scale!r} + {offset!r}'
        keys = tuple(target.keyframes())
        if keys and not replace_existing:
            try:
                same = target.expressionLanguage() == hou.exprLanguage.Hscript and target.expression() == expression
            except hou.OperationFailed:
                same = False
            if not same:
                raise ValueError(f'{target.path()}: existing driver/animation requires replace_existing=True')
        expected = source_value * scale + offset
        if not math.isfinite(expected):
            raise ValueError('mapped value is non-finite')
        template = target.parmTemplate()
        if ((template.minIsStrict() and expected < template.minValue()) or
                (template.maxIsStrict() and expected > template.maxValue())):
            raise ValueError('mapped value exceeds target strict range')
        summary.append({'source': _channel(source), 'target': _channel(target),
                        'expression': expression, 'before': old_value, 'after': expected})
        prepared.append((source, target, expression, expected))
    if targets & sources:
        raise ValueError('self-binding or source/target chains in one batch are unsupported')
    payload = {'controller': n.path(), 'identity': n.sessionId(), 'frame': hou.frame(),
               'replace_existing': replace_existing, 'bindings': summary}
    revision = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    return {**payload, 'plan_sha256': revision}, prepared
