"""Houdini parameter values. Executed on the Bridge owning thread."""
from __future__ import annotations

import difflib
import hashlib
import math
import re
import hou
import dsh_errors
import dsh_node_access
import dsh_ownership
import dsh_parameter_templates


def _menu_setting(entries, value):
    if isinstance(value, str):
        for item in entries:
            if item['token'] == value: return item['set_value']
    elif type(value) is int:
        # Native ordered menus also accept indices; Int menus expose storage values.
        for item in entries:
            if value == item['set_value'] or (isinstance(item['set_value'], str) and value == item['index']):
                return item['set_value']
    raise ValueError(f'invalid menu value {value!r}; use a menu token/set_value from node_info or list_parms; expressions require {{expression,language}}')


def list_parms(node) -> list:
    """参数**目录**：名字/标签/类型/帮助，不给值（导航用，回答「想改的参数叫什么」）。"""
    n = dsh_node_access._resolve(node)
    out = []
    for pt in n.parmTuples():
        entry: dict = {"name": pt.name()}
        entry['components'] = [p.name() for p in pt]
        entry['locked_components'] = [p.name() for p in pt if p.isLocked()]
        tpl = pt.parmTemplate()
        if tpl is not None:
            try:
                entry["label"] = tpl.label()
            except Exception:
                entry["label"] = None
            try:
                entry["type"] = tpl.type().name()
            except Exception:
                entry["type"] = None
            try:
                entry["size"] = tpl.numComponents()
            except Exception:
                try:
                    entry["size"] = len(pt)
                except Exception:
                    pass
            for field, getter in (("help", "help"), ("description", "description")):
                try:
                    v = getattr(tpl, getter)()
                    if v:
                        entry[field] = v
                except Exception:
                    pass
            try:
                card = dsh_parameter_templates._parm_template_card(tpl)
                entry.update({k: v for k, v in card.items() if k in ("menu", "menu_dynamic", "default")})
                if len(pt) == 1:
                    tokens, labels = pt[0].menuItems(), pt[0].menuLabels()
                    if tokens:
                        entry["menu"] = dsh_parameter_templates._menu_entries(tpl, tokens, labels)
            except (AttributeError, hou.Error):
                pass
        else:
            entry["label"] = None
        out.append(entry)
    return out


def read_parms(node, changed_only: bool = True, *, names: list | None = None) -> list:
    """参数值：默认保留非默认值、表达式、引用、关键帧或时间依赖的参数。

    带表达式的参数会顺带解析引用目标（``referenced_parm``），被其他参数引用的
    参数会标 ``referenced_by``——两个方向的依赖对 agent 判断「动谁会波及谁」都需要。
    返回 ``list[dict]``，每项至少有 ``name/value``；不是 name→value 字典。
    Ramp value为{type:'ramp',basis:[名称],keys:[位置],values:[标量或RGB数组]}，
    可直接json.dumps；仅当前求值控制点，不证明动画恢复，也不是setter输入格式。
    changed_only必须为bool；选择名称用read_parms(node, names=['radius', 'scale'])。
    names可显式选1..32个唯一标量或tuple参数，按请求顺序返回且不受changed_only过滤；
    tuple返回聚合value和带完整诊断的components；缺失字段报错。
    无动画的string含原始UTF-8源码source_sha256；求值不同于原文时另含raw_value。
    """
    if type(changed_only) is not bool:
        raise ValueError("changed_only must be boolean; select parameters with read_parms(node, names=['radius', 'scale'])")
    n = dsh_node_access._resolve(node)
    out = []
    requested = None
    if names is not None:
        if (not isinstance(names, list) or not 1 <= len(names) <= 32
                or any(not isinstance(name, str) or not name for name in names) or len(set(names)) != len(names)):
            raise ValueError('names must contain 1..32 unique scalar/tuple parameter names')
        requested = []
        missing = []
        parameters = []
        seen = set()
        for name in names:
            scalar = n.parm(name)
            if scalar is not None:
                group = ('scalar', name, (scalar,))
            else:
                parm_tuple = n.parmTuple(name)
                if parm_tuple is None:
                    missing.append(name)
                    continue
                group = ('tuple', name, tuple(parm_tuple))
            requested.append(group)
            for parm in group[2]:
                if parm.name() not in seen:
                    seen.add(parm.name())
                    parameters.append(parm)
        if missing:
            raise ValueError(f'missing scalar/tuple parameter names: {missing}; use list_parms for the current interface')
    else:
        parameters = n.parms()
    for p in parameters:
        # hou.Parm 没有 hasExpression()（H21/H22 均无；静默 try/except 曾让表达式
        # 维度整个失效）。正确判定：expression() 在无表达式时抛 OperationFailed。
        try:
            expr = p.expression()
            has_expr = True
        except Exception:
            expr = None
            has_expr = False
        try:
            # hou.Parm 也没有 isReferencedBy()；引用自省用 parmsReferencingThis()。
            is_ref = bool(p.parmsReferencingThis())
        except Exception:
            is_ref = False
        try:
            keys = list(p.keyframes())
        except Exception:
            keys = []
        try:
            time_dependent = bool(p.isTimeDependent())
        except Exception:
            time_dependent = False
        tpl = p.parmTemplate()
        if (names is None and changed_only and not has_expr and not is_ref
                and not keys and not time_dependent):
            # A ramp's ordinary default query only covers its multiparm count;
            # the dedicated API compares its actual knots and values.
            is_default = (p.isAtRampDefault() if tpl is not None and tpl.type() == hou.parmTemplateType.Ramp
                          else p.isAtDefault())
            if is_default:
                continue
        entry: dict = {"name": p.name()}
        if tpl is not None:
            try:
                entry["label"] = tpl.label()
            except Exception:
                entry["label"] = None
        previous_errors=tuple(str(e) for e in n.errors()) if has_expr else ()
        try:
            value = p.eval()
            if isinstance(value, hou.Ramp):
                entry['value'] = {'type': 'ramp', 'basis': [str(b).rsplit('.', 1)[-1] for b in value.basis()],
                                  'keys': [float(k) for k in value.keys()],
                                  'values': [[float(v.r()),float(v.g()),float(v.b())] if isinstance(v,hou.Color)
                                             else dsh_node_access._val(v) for v in value.values()]}
                entry['value_scope'] = 'evaluated ramp knots only; not animation, callbacks or a setter payload'
            else:
                entry["value"] = dsh_node_access._val(value)
        except Exception:
            try:
                entry["value"] = p.evalAsString()
            except Exception:
                entry["value"] = None
        if has_expr:
            entry["expression"] = expr
            try:
                language='python' if p.expressionLanguage()==hou.exprLanguage.Python else 'hscript'
                entry['language']=language
                entry['evaluation']=_expression_evaluation(p,entry.get('value'),language,previous_errors)
                entry['value']=entry['evaluation']['value']
                entry['effect_status']='unverified'
            except Exception as error:
                entry['evaluation']={'status':'unverified','reason':str(error)}
            try:
                ref = p.getReferencedParm()
                if ref is not None:
                    entry["referenced_parm"] = ref.path()
            except Exception:
                pass
        if tpl is not None and tpl.type() == hou.parmTemplateType.String and not keys and not has_expr:
            raw = p.unexpandedString()
            entry['source_sha256'] = hashlib.sha256(raw.encode('utf-8')).hexdigest()
            if raw != entry.get('value'):
                entry['raw_value'] = raw
        if is_ref:
            entry["referenced_by"] = True
        if keys or time_dependent:
            entry["animated"] = True
            entry["time_dependent"] = time_dependent
        if keys:
            frames = sorted(float(key.frame()) for key in keys)
            curves = []
            for key in keys:
                try:
                    curve = key.expression()
                except Exception:
                    curve = None
                if curve and curve not in curves:
                    curves.append(curve)
            entry.update({
                "key_count": len(keys),
                "first_frame": frames[0],
                "last_frame": frames[-1],
            })
            if curves:
                entry["curves"] = curves
        out.append(entry)
    if requested is not None:
        by_name = {entry['name']: entry for entry in out}
        selected = []
        for kind, name, parms in requested:
            components = [by_name[parm.name()] for parm in parms]
            if kind == 'scalar':
                selected.append(components[0])
                continue
            parm_tuple = n.parmTuple(name)
            template = parm_tuple.parmTemplate() if parm_tuple is not None else None
            entry = {
                'name': name,
                'label': template.label() if template is not None else None,
                'type': 'tuple',
                'size': len(components),
                'component_names': [component['name'] for component in components],
                'value': [component.get('value') for component in components],
                'components': components,
            }
            if any(component.get('animated') for component in components):
                entry['animated'] = True
            if any(component.get('time_dependent') for component in components):
                entry['time_dependent'] = True
            selected.append(entry)
        return selected
    return out


def _clear_animation(p) -> str | None:
    """参数上有表达式/关键帧时清除并返回描述；没有则返回 None。

    2026-08-20 OTL 会话（seq 28944）：``parm.set`` 被 ``$FEND`` 表达式静默架空，
    eval 纹丝不动但无报错。「set 就是 set」——清掉再设，并在返回里告知清了什么。
    """
    try:
        expr = p.expression()
    except Exception:
        expr = None
    keys = []
    try:
        keys = list(p.keyframes())
    except Exception:
        pass
    if expr is None and not keys:
        return None
    desc = f"expression {expr!r}" if expr is not None else f"{len(keys)} keyframe(s)"
    p.deleteAllKeyframes()
    return desc


class _ParameterReference:
    """Stable channel address while native multiparm instances are recreated."""
    def __init__(self, parm):
        self.node_identity = parm.node().sessionId()
        self.name = parm.name()
        self.path = parm.path()
        self.locked = parm.isLocked()
        self.multiparm = parm.isMultiParmParent()
        self.depth = len(parm.multiParmInstanceIndices())
        self.instances = tuple(p.name() for p in parm.multiParmInstances()) if self.multiparm else None

    def resolve(self):
        node = hou.nodeBySessionId(self.node_identity)
        parm = node.parm(self.name) if node is not None else None
        if parm is None:
            raise RuntimeError(f'{self.path}: original parameter identity no longer exists')
        return parm


def _parameter_snapshot(targets) -> dict:
    """Snapshot explicit channels and every instance removed by a count edit."""
    targets = tuple(targets)
    for target in targets:
        if target.isLocked():
            raise ValueError(f"参数已锁定：{target.path()}")
    snapshots = {}

    def capture(target):
        if target.name() in snapshots:
            return
        if target.parmTemplate().type() == hou.parmTemplateType.Data:
            raise ValueError(f'{target.path()}: data parameters are not scalar values; zero writes. Use the documented node initialization workflow (for example Stash Input), not set_parm(s) on embedded geometry.')
        keys = tuple(target.keyframes())
        value = (target.unexpandedString() if target.parmTemplate().type() == hou.parmTemplateType.String
                 else target.eval()) if not keys else None
        reference = _ParameterReference(target)
        snapshots[reference.name] = (reference, keys, value)
        if reference.multiparm:
            # HOM returns immediate instances only; nested count channels need
            # their own complete snapshots before any outer count can shrink.
            for instance in target.multiParmInstances():
                capture(instance)

    for target in targets:
        capture(target)
    return snapshots


def _parameter_restore_evidence(snapshots) -> dict:
    """Read back exact channel state; matching output geometry is insufficient.

    Re-resolve by original node identity and parameter name, never by a path
    that could now identify a replacement node. No parameter or geometry writes.
    """
    errors, channels = [], []
    for reference, keys, value in snapshots.values():
        try:
            p = reference.resolve()
            actual_keys = tuple(p.keyframes())
            raw = (p.unexpandedString() if p.parmTemplate().type() == hou.parmTemplateType.String
                   else p.eval()) if not actual_keys else None
            # H21 Ramp equality is not a structural channel comparison. The
            # basis, knot positions and values are the native ramp payload.
            value_matches = (raw.basis() == value.basis() and raw.keys() == value.keys()
                             and raw.values() == value.values()
                             if isinstance(raw, hou.Ramp) and isinstance(value, hou.Ramp)
                             else raw == value)
            exact = actual_keys == keys and (bool(keys) or value_matches)
            structure_matches = (not reference.multiparm or
                p.isMultiParmParent() and tuple(child.name() for child in p.multiParmInstances()) == reference.instances)
            exact = exact and structure_matches and p.isLocked() == reference.locked
            channels.append({'node_identity':reference.node_identity,'parameter':p.path(),
                'key_count_before':len(keys),'key_count_after':len(actual_keys),
                'state_matches':exact,
                **({'multiparm_structure_matches':structure_matches} if reference.multiparm else {}),
                **({'expected_value':dsh_node_access._val(value),'actual_value':dsh_node_access._val(raw)} if not keys
                   else {'animation_matches':actual_keys == keys})})
            if not exact:
                errors.append(f'{p.path()}: restored value/expression/keyframes/lock or multiparm structure differ from snapshot')
        except Exception as error:
            errors.append(f'parameter restoration readback: {error}')
    return {'ok':not errors,'channels':channels,'errors':errors,
            'scope':'exact snapshotted channels and multiparm instance structure only; no external side effects or future-state guarantee'}


def _restore_parameters(snapshots) -> list:
    errors = []
    # Counts rebuild the parameter tree, outermost first. Restore leaves only
    # after all counts exist, irrespective of the caller's dictionary order.
    ordered = sorted(snapshots.values(), key=lambda state: (
        not state[0].multiparm, state[0].depth))
    for reference, keys, value in ordered:
        try:
            target = reference.resolve()
            # An implicit instance may originally be locked. Its containing
            # count was authorized, so restore its data and original lock as
            # one state. A newly locked, originally unlocked target still
            # reports a restoration failure rather than overriding callbacks.
            if reference.locked:
                target.lock(False)
            try:
                target.deleteAllKeyframes()
                if keys:
                    target.setKeyframes(keys)
                else:
                    target.set(value, follow_parm_reference=False)
            finally:
                if reference.locked:
                    target.lock(True)
        except Exception as error:
            errors.append(f"{reference.path}: {error}")
    errors.extend(_parameter_restore_evidence(snapshots)['errors'])
    return errors


def _prepare_parameter_patch(p, value):
    """Bounded sequential literal replacements, fully planned before writes."""
    def reject(message):
        raise dsh_errors.ParameterPatchError(f'{p.path()}: {message}', p.path())
    if set(value) != {'patch', 'expected_sha256'}:
        reject('patch object requires only patch and expected_sha256')
    expected = value['expected_sha256']
    if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
        reject('expected_sha256 must be the current raw UTF-8 string SHA-256')
    tpl = p.parmTemplate()
    if tpl.type() != hou.parmTemplateType.String or tpl.numComponents() != 1:
        reject('patch requires a literal scalar string parameter')
    if p.isLocked() or p.keyframes():
        reject('patch refuses locked, animated or expression-driven strings')
    # Wrangle source editors have a StringReplace snippet menu; that is an
    # editable source field, not an enum. Never evaluate its menu generator.
    if tpl.scriptCallback() or ((tpl.menuItems() or tpl.itemGeneratorScript())
                               and tpl.menuType() == hou.menuType.Normal):
        reject('patch refuses callback and fixed-menu parameters')
    patches = value['patch']
    if not isinstance(patches, list) or not 1 <= len(patches) <= 32:
        reject('patch requires 1..32 literal replacement objects')
    source = p.unexpandedString()
    if len(source) > 524288:
        reject('source exceeds 524288 characters; split into smaller editable modules')
    before_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()
    if before_hash != expected:
        reject(f'stale source: expected {expected}, current {before_hash}')
    result, matches, text_budget = source, [], 0
    for index, edit in enumerate(patches):
        if not isinstance(edit, dict) or set(edit) != {'old', 'new', 'count'}:
            reject(f'patch[{index}] requires only old/new/count')
        old, new, count = edit['old'], edit['new'], edit['count']
        if not isinstance(old, str) or not old or not isinstance(new, str) or old == new:
            reject(f'patch[{index}] needs a nonempty old string and a different new string')
        text_budget += len(old) + len(new)
        if text_budget > 131072 or type(count) is not int or not 1 <= count <= 256:
            reject(f'patch[{index}] exceeds text budget or needs integer count in 1..256')
        actual = result.count(old)
        if actual != count:
            reject(f'patch[{index}] anchor count: expected {count}, found {actual}; no parameters written')
        result = result.replace(old, new, count)
        if len(result) > 524288:
            reject('patched source exceeds 524288 characters')
        matches.append({'count': count, 'old_chars': len(old), 'new_chars': len(new)})
    if result == source:
        reject('patch sequence makes no net change')
    return {'source': source, 'result': result, 'evidence': {
        'before_sha256': before_hash, 'after_sha256': hashlib.sha256(result.encode('utf-8')).hexdigest(),
        'before_chars': len(source), 'after_chars': len(result), 'replacements': matches}}


def _apply_parameter_patch(p, plan):
    # Another parameter callback in this batch may have changed the source;
    # this is a write-phase failure, never zero-write evidence for the batch.
    if p.keyframes() or p.unexpandedString() != plan['source']:
        raise RuntimeError(f'{p.path()}: source changed after patch preflight')
    p.set(plan['result'], follow_parm_reference=False)
    if p.keyframes() or p.unexpandedString() != plan['result']:
        raise RuntimeError(f'{p.path()}: literal patch readback mismatch')
    return {'parm': p.name(), 'patch': plan['evidence'], 'value_omitted': True}


def set_parm(node, name: str, value,
             allow_foreign: str | None = None) -> dict:
    """设参；numeric string 是表达式，Menu string 是精确 token。

    失败恢复本参数的值/表达式/关键帧，不跟随引用修改其他节点。菜单动画可显式传
    {"expression": "...", "language": "hscript"|"python"}。外部回调不属回滚范围。
    multiparm数量修改同时快照全部嵌套实例；恢复先重建数量/结构，再恢复实例通道与锁定状态。
    Data/内嵌Geometry参数在快照与写入前拒绝；按节点原生初始化流程处理，不用标量setter。
    字面string可用{"expected_sha256":原始UTF8源码hash,"patch":[{"old":锚点,"new":替换,"count":精确次数}]}。
    1..32项顺序替换，先验证全部锚点/版本；拒绝锁定、动画/表达式、callback和固定菜单。
    源码上限524288字符，替换文本累计131072字符，count为1..256；不执行正则或补丁脚本。
    返回patch的前后hash/字符数/替换次数，value_omitted=True；不证明VEX或几何通过，另做cook/verify_network。
    表达式返回language/write_status/evaluation/effect_status；合法0不算错误。本次新增且原生明确指向本参数的求值
    错误或非有限数值抛CheckpointError并恢复参数；节点/tuple warning只报告范围，不认证几何或全部引用。
    """
    n = dsh_node_access._resolve(node)
    dsh_ownership.require_owned(n, "set_parm", allow_foreign)
    if name == 'snippet' and isinstance(value, str) and 'wrangle' in n.type().name():
        from dsh_cook_control import validate_vex
        validate_vex(value)
    p = n.parm(name)
    targets = (p,) if p is not None else n.parmTuple(name)
    is_patch = isinstance(value, dict) and 'patch' in value
    if is_patch and p is None:
        raise dsh_errors.ParameterPatchError(f'{name}: patch requires an existing scalar string parameter', n.path())
    plan = _prepare_parameter_patch(p, value) if is_patch else None
    snapshots = _parameter_snapshot(targets) if targets is not None else {}
    try:
        if plan is not None:
            return _apply_parameter_patch(p, plan)
        return _set_parm_impl(n, name, value, allow_foreign)
    except BaseException as error:
        restore_errors = _restore_parameters(snapshots)
        evidence = error.evidence if isinstance(error, dsh_errors.CheckpointError) else {
            'ok': False, 'node': n.path(), 'parm': name, 'phase': 'parameter_write'}
        evidence.update({'restored': not restore_errors,
            'parameter_state_restored': not restore_errors, 'parameter_restore_errors': restore_errors,
            'restore_errors': restore_errors, 'write_status': 'restored' if not restore_errors else 'recovery_unverified',
            'restoration_scope': 'snapshotted parameter values, expressions and keys only; callbacks, cooks and external side effects are separate'})
        error.evidence = evidence
        raise


def _validate_numeric_parameter_value(value, components=(), *, size=None) -> None:
    """Shared static/runtime value-shape check; never evaluate an expression.

    A size-one template names a scalar Parm, not a ParmTuple-only setter.
    Full numeric tuples accept finite literals; scalar/component fields accept
    literals or explicit expressions. Menus retain their separate token policy.
    """
    # Tuple width is a template fact, independent of whether its naming scheme
    # is known here. An unrecognized scheme must never turn a tuple into scalar.
    size = size if size is not None else len(components) or 1
    if size > 1:
        names = f': {list(components)}' if components else ''
        if not isinstance(value, (list, tuple)) or len(value) != size:
            raise ValueError(f'tuple needs {size} components{names}')
        if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
            target = str(list(components)) if components else 'from list_parms on the created node'
            raise ValueError(f'numeric tuple requires finite numeric values; expressions use component names {target}')
        return
    if isinstance(value, str):
        return  # Numeric strings are HScript, not implicit menu tokens.
    if isinstance(value, dict):
        if set(value) - {'expression', 'language'} or not isinstance(value.get('expression'), str):
            raise ValueError('scalar expression object accepts expression string and optional language only')
        if value.get('language', 'hscript') not in ('hscript', 'python'):
            raise ValueError('expression language must be hscript/python')
        return
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('numeric scalar requires a finite number or expression, not a list/tuple or null')


def _expression_evaluation(p, value, language, previous_errors=()):
    """Use Houdini's diagnostics, never infer failure from a zero value.

    This reads the last evaluation diagnostics, without cooking the node or
    evaluating the expression again. Tuple warnings can concern a sibling.
    """
    node=p.node()
    errors=[str(e) for e in node.errors()]
    warnings=[str(e) for e in node.warnings()]
    exact=re.compile(re.escape(p.path())+r'(?![A-Za-z0-9_])')
    evaluation_path=re.compile(re.escape('('+p.path()+'))')+r'\.?\s*$')
    own_errors=[e for e in errors if 'Unable to evaluate expression' in e and evaluation_path.search(e)]
    new_errors=[e for e in own_errors if e not in previous_errors]
    tuple_path=node.path()+'/'+p.tuple().name()
    related=re.compile(re.escape(tuple_path)+r'(?![A-Za-z0-9_])')
    related_warnings=[w for w in warnings if exact.search(w) or related.search(w)]
    finite=not isinstance(value,(int,float)) or math.isfinite(value)
    if not finite:
        own_errors.append('expression evaluated to a non-finite numeric value')
        new_errors.append(own_errors[-1])
    status='failed' if new_errors else 'unverified' if own_errors else 'warning' if related_warnings else 'unverified' if errors or warnings else 'evaluated'
    return {'status':status,'parameter':p.path(),'language':language,'frame':float(hou.frame()),
        'value':dsh_node_access._val(value) if finite else repr(value),'errors':own_errors,
        'new_errors':new_errors,'prior_diagnostics_present':bool(previous_errors),
        'warnings':related_warnings,'node_errors':errors,'node_warnings':warnings,
        **({'next_action':'Inspect reference targets and explicitly cook/check the intended output; unchanged node errors may be cached from an earlier cook, and a zero value alone proves neither success nor failure.'} if status in ('warning','unverified') else {}),
        'scope':'last parameter evaluation; tuple warnings may concern a sibling, node diagnostics may predate this write; no geometry cook or effect validation'}


def _set_expression(p, expression, language):
    previous_errors=tuple(str(e) for e in p.node().errors())
    try:
        _clear_animation(p)
        p.setExpression(expression,language=hou.exprLanguage.Hscript if language=='hscript' else hou.exprLanguage.Python)
    except Exception as error:
        raise dsh_errors.CheckpointError(f'expression write failed at {p.path()} ({language}): {error}',
            {'ok':False,'node':p.node().path(),'parm':p.name(),'expression':expression,'language':language,
             'failure_stage':'write','write_status':'failed','evaluation':{'status':'not_run'},'effect_status':'unverified'}) from error
    try:
        value=p.eval()
        evaluation=_expression_evaluation(p,value,language,previous_errors)
    except Exception as error:
        raise dsh_errors.CheckpointError(f'expression evaluation raised at {p.path()} ({language}): {error}',
            {'ok':False,'node':p.node().path(),'parm':p.name(),'expression':expression,'language':language,
             'failure_stage':'evaluation','write_status':'written','evaluation':{'status':'failed','errors':[str(error)]},'effect_status':'unverified'}) from error
    result={'parm':p.name(),'node':p.node().path(),'expression':expression,'language':language,
            'value':evaluation['value'],'write_status':'written','evaluation':evaluation,'effect_status':'unverified'}
    if evaluation['status']=='failed':
        raise dsh_errors.CheckpointError(f'expression evaluation failed at {p.path()} ({language}): '+ '; '.join(evaluation['errors']),
                              {'ok':False,'failure_stage':'evaluation',**result})
    return result


def _set_parm_impl(node, name: str, value,
                   allow_foreign: str | None = None) -> dict:
    """设参数（组件名或元组名均可）；失败时列出相似参数名供自纠。

    数值型参数收到字符串值时按**表达式**处理（H21/H22 实测 ``Parm.set(str)``
    对数值参数直接抛 TypeError，必须走 ``setExpression``）——这让
    ``set_parm(n, 'tx', 'ch(\"ty\")')`` 这类最高频操作可用。

    参数上已有表达式/关键帧时**自动清除再设值**（2026-08-20 拍板），返回带
    ``note`` 说明清掉了什么；想保留动画请显式传字符串表达式。
    """
    n = dsh_node_access._resolve(node)
    dsh_ownership.require_owned(n, "set_parm", allow_foreign)
    p = n.parm(name)
    if p is not None:
        if isinstance(value, dict):
            if set(value) - {"expression", "language"} or not isinstance(value.get("expression"), str):
                raise ValueError("表达式对象只接受 expression 和可选 language")
            language = value.get("language", "hscript")
            if language not in ("hscript", "python"):
                raise ValueError("expression language 必须为 hscript/python")
            return _set_expression(p,value['expression'],language)
        # Menu tokens are not expressions. Do not let an invalid token silently
        # evaluate to 0 or leave an animated parameter with its keys deleted.
        tpl = p.parmTemplate()
        try: tokens = tuple(p.menuItems()) if tpl.type() in (hou.parmTemplateType.Menu, hou.parmTemplateType.Int) else ()
        except hou.OperationFailed:
            if tpl.type() == hou.parmTemplateType.Menu: raise
            tokens = ()  # plain integer controls are not menus
        if tokens or tpl.type() == hou.parmTemplateType.Menu:
            setting = _menu_setting(dsh_parameter_templates._menu_entries(tpl, tokens, p.menuLabels()), value)
            cleared = _clear_animation(p)
            p.set(setting)
            return {"parm": p.name(), "value": dsh_node_access._val(p.eval()), "menu_token": p.evalAsString(),
                    **({"note": f"cleared {cleared}"} if cleared else {})}
        if tpl.type() in (hou.parmTemplateType.Int, hou.parmTemplateType.Float):
            _validate_numeric_parameter_value(value)
        if isinstance(value, str):
            tpl_type = None
            try:
                tpl_type = p.parmTemplate().type()
            except Exception:
                pass
            if tpl_type in (hou.parmTemplateType.Int, hou.parmTemplateType.Float):
                return _set_expression(p,value,'hscript')
        cleared = _clear_animation(p)
        p.set(value)
        out = {"parm": p.name(), "value": dsh_node_access._val(p.eval())}
        if cleared:
            out["note"] = f"cleared {cleared}"
        return out

    pt = n.parmTuple(name)
    if pt is not None:
        if isinstance(value, (list, tuple)):
            if len(value) != len(pt):
                raise ValueError(f"{pt.name()} 需要 {len(pt)} 个分量，收到 {len(value)}")
            if pt.parmTemplate().type() in (hou.parmTemplateType.Int, hou.parmTemplateType.Float):
                _validate_numeric_parameter_value(value, [p.name() for p in pt])
            cleared = [c for pp in pt for c in [_clear_animation(pp)] if c]
            pt.set(value)
            out = {"parm": pt.name(), "value": [dsh_node_access._val(v) for v in pt.eval()]}
            if cleared:
                out["note"] = f"cleared {', '.join(cleared)}"
            return out
        comps = [pp.name() for pp in n.parms() if pp.tuple().name() == name]
        raise ValueError(
            f"'{name}' 在 '{n.path()}' 上是 {len(comps)} 分量元组 "
            f"({', '.join(comps)})；请传 list/tuple"
        )

    names = [pp.name() for pp in n.parms()]
    suggestions = difflib.get_close_matches(name, names, n=5, cutoff=0.4)
    raise ValueError(
        f"节点 '{n.path()}' (type={n.type().name()}) 没有参数 '{name}'。相似参数：{suggestions}；请用 list_parms 查询实际节点"
    )


def set_parms(node, values: dict,
              allow_foreign: str | None = None, strict: bool = True) -> dict:
    """批量设参：``{name: value}`` 逐项走 ``set_parm`` 同一套语义（含表达式/关键帧清除）。

    默认 strict：预检参数名，失败恢复本批参数（含表达式/关键帧）并抛错。
    multiparm数量包含其全部嵌套实例快照；恢复后回读实例结构、值、keys与锁定状态。
    ``strict=False`` 仅用于明确允许部分成功的诊断/恢复，返回 ``ok/set/failed``。
    参数回调的外部副作用不能靠参数快照回滚，复杂批次仍需 Bridge undo 事务。
    value支持set_parm的字面string patch对象；只允许strict=True，整批patch验证通过后才写任何参数。
    补丁字段在set中返回前后hash/字符数/替换次数（不回传整份源码），patched列出这些字段名。
    预检限本节点本批values；其他节点/其他调用不属此预检范围。
    表达式字段另给evaluations；明确求值失败在strict模式恢复本批值/keys，warning/unverified单独报告。
    """
    n = dsh_node_access._resolve(node)
    dsh_ownership.require_owned(n, "set_parms", allow_foreign)
    if not isinstance(values, dict) or not values:
        raise ValueError("values 必须是非空 dict：{参数名: 值}")
    if not isinstance(strict, bool):
        raise ValueError("strict 必须是 bool")
    snapshots, patch_plans = {}, {}
    if not strict and any(isinstance(v, dict) and 'patch' in v for v in values.values()):
        raise dsh_errors.ParameterPatchError('literal patches require strict=True', n.path())
    if strict:
        explicit_targets = {}
        for key in values:
            parm = n.parm(key)
            targets = (parm,) if parm is not None else n.parmTuple(key)
            if targets is None:
                raise ValueError(f"{n.path()} (type={n.type().name()}) 没有参数 {key!r}；请用 list_parms 查询实际节点")
            for target in targets:
                if target.name() in explicit_targets:
                    raise ValueError(f"同批参数重叠：{key!r} 与 {target.name()!r}")
                explicit_targets[target.name()] = target
        snapshots = _parameter_snapshot(explicit_targets.values())
        # Validate EVERY patch before the first regular or patch parameter write.
        for key, value in values.items():
            if isinstance(value, dict) and 'patch' in value:
                parm = n.parm(key)
                if parm is None:
                    raise dsh_errors.ParameterPatchError(f'{key}: patch requires a scalar string parameter', n.path())
                patch_plans[key] = _prepare_parameter_patch(parm, value)
    done, failed, notes, evaluations = {}, {}, {}, {}
    for key, value in values.items():
        try:
            r = (_apply_parameter_patch(n.parm(key), patch_plans[key]) if key in patch_plans
                 else set_parm(n, key, value, allow_foreign=allow_foreign))
            done[r["parm"]] = r['patch'] if 'patch' in r else r.get("value", r.get("expression"))
            if "note" in r:
                notes[r["parm"]] = r["note"]
            if 'evaluation' in r:evaluations[r['parm']]=r['evaluation']
        except Exception as e:
            failed[key] = str(e)
            if strict:
                restore_errors = _restore_parameters(snapshots)
                if isinstance(e,dsh_errors.CheckpointError):
                    e.evidence.update({'restored':not restore_errors, 'restore_errors':restore_errors,
                                       'batch_parameter_state_restored':not restore_errors,
                                       'batch_restore_errors':restore_errors,'write_status':'restored' if not restore_errors else 'recovery_unverified',
                                       'restoration_scope':'all snapshotted parameters in this batch; callbacks, cooks and external side effects are separate'})
                    raise
                raise dsh_errors.CheckpointError(f"set_parms failed at {key!r}: {e}; parameter_restore_errors={restore_errors}",
                    {'ok':False, 'node':n.path(), 'phase':'parameter_write',
                     'restored':not restore_errors, 'restore_errors':restore_errors,
                     'restoration_scope':'all snapshotted parameters in this batch; callbacks, cooks and external side effects are separate'}) from e
    out = {"node": n.path(), "ok": not failed, "set": done}
    if patch_plans:
        out['patched'] = list(patch_plans)
    if notes:
        out["notes"] = notes
    if failed:
        out["failed"] = failed
    if evaluations:
        out['evaluations']=evaluations
        out['effect_status']='unverified'
        if any(e['status']=='unverified' for e in evaluations.values()):out['status']='unverified'
        if any(e['status'] in ('warning','unverified') for e in evaluations.values()):out['warning_free']=False
    return out


def _apply_spare_interface(n, group, code_parm):
    """Refresh a code parm without flattening its source, references or animation.

    A wrangle cooked before its local channels exist can retain missing-channel
    dependencies after setParmTemplateGroup, even on a forced cook. Reassigning
    the original source/keyframes invalidates those compiled dependencies.
    """
    source = n.parm(code_parm)
    if source is not None and source.parmTemplate().type() != hou.parmTemplateType.String:
        raise ValueError(f'{code_parm}: code parameter must be a string')
    snapshots = _parameter_snapshot([source]) if source is not None else {}
    before = n.parmTemplateGroup()

    def refresh():
        errors = _restore_parameters(snapshots)
        if errors:
            raise RuntimeError(f'code dependency refresh failed: {errors}')
        for name, (_, keys, value) in snapshots.items():
            current = n.parm(name)
            if tuple(current.keyframes()) != keys or (not keys and current.unexpandedString() != value):
                raise RuntimeError(f'{name}: code state changed during dependency refresh')

    try:
        n.setParmTemplateGroup(group, rename_conflicting_parms=False)
        refresh()
    except Exception as error:
        try:
            n.setParmTemplateGroup(before, rename_conflicting_parms=False)
            refresh()
        except Exception as restore_error:
            raise dsh_errors.CheckpointError(f'spare interface restoration failed: {restore_error}',
                                  {'ok': False, 'node': n.path(), 'restored': False}) from error
        raise
    return code_parm if snapshots else None
