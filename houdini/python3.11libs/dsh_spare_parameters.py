"""Houdini spare parameters. Executed on the Bridge owning thread."""
from __future__ import annotations

import dsh_parameter_values

import math
import re
import hou
import dsh_errors
import dsh_node_access
import dsh_ownership
import dsh_parameter_templates


def _spare_spec_template(item: dict, path: str, names: set):
    if not isinstance(item, dict):
        raise ValueError(f"{path} 必须是 dict")
    kind = str(item.get("type", "")).strip().lower()
    if kind not in {"folder", "toggle", "int", "float", "string"}:
        raise ValueError(
            f"{path}.type 不支持 {kind!r}；可用 folder/toggle/int/float/string"
        )
    name = item.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"{path}.name 必须是合法 Houdini 参数名")
    if name in names:
        raise ValueError(f"参数/文件夹名 {name!r} 重复")
    names.add(name)
    label = str(item.get("label", name.replace("_", " ").title()))
    if kind == "folder":
        children = item.get("parms", [])
        if not isinstance(children, (list, tuple)) or not children:
            raise ValueError(f"{path}.parms 必须是非空 list")
        template = hou.FolderParmTemplate(name, label, folder_type=hou.folderType.Simple)
        for index, child in enumerate(children):
            template.addParmTemplate(
                _spare_spec_template(child, f"{path}.parms[{index}]", names)
            )
    elif kind == "toggle":
        template = hou.ToggleParmTemplate(
            name, label, default_value=bool(item.get("default", False))
        )
    elif kind in ("int", "float"):
        default = item.get("default", 0)
        minimum = item.get("min", 0)
        maximum = item.get("max", 10)
        kwargs = {
            "default_value": (float(default),) if kind == "float" else (int(default),),
            "min": float(minimum) if kind == "float" else int(minimum),
            "max": float(maximum) if kind == "float" else int(maximum),
            "min_is_strict": bool(item.get("min_strict", False)),
            "max_is_strict": bool(item.get("max_strict", False)),
        }
        cls = hou.FloatParmTemplate if kind == "float" else hou.IntParmTemplate
        template = cls(name, label, 1, **kwargs)
    else:
        template = hou.StringParmTemplate(
            name, label, 1, default_value=(str(item.get("default", "")),)
        )
    if item.get("help") is not None:
        template.setHelp(str(item["help"]))
    return template


def _update_spare_defaults(n, updates):
    """Update only literal scalar spare defaults; preserve live values/animation."""
    if not isinstance(updates, dict) or not 1 <= len(updates) <= 32:
        raise ValueError('update_defaults must contain 1..32 existing scalar spare parameters')
    group = n.parmTemplateGroup()
    before_group = n.parmTemplateGroup()
    targets, changes = [], {}
    for name, value in updates.items():
        if not isinstance(name, str) or not name:
            raise ValueError('update_defaults keys must be nonempty parameter names')
        p = n.parm(name)
        if p is None or not p.isSpare():
            raise ValueError(f'{name}: update_defaults requires an existing spare parameter')
        tpl = p.parmTemplate()
        kind = tpl.type()
        if (tpl.numComponents() != 1 or p.isMultiParmInstance() or tpl.scriptCallback()
                or kind not in (hou.parmTemplateType.Float, hou.parmTemplateType.Int,
                                hou.parmTemplateType.Toggle, hou.parmTemplateType.String)):
            raise ValueError(f'{name}: only scalar float/int/toggle/string defaults without callbacks or multiparms are supported')
        if getattr(tpl, 'menuItems', lambda: ())():
            raise ValueError(f'{name}: menu defaults are unsupported')
        if any(getattr(tpl, 'defaultExpression', lambda: ())()):
            raise ValueError(f'{name}: expression defaults are unsupported; do not silently replace their meaning')
        if kind == hou.parmTemplateType.String:
            valid = isinstance(value, str)
        elif kind == hou.parmTemplateType.Toggle:
            valid = type(value) is bool or (type(value) is int and value in (0, 1))
        elif kind == hou.parmTemplateType.Int:
            valid = type(value) is int and -(2**31) <= value < 2**31
        else:
            valid = type(value) in (int, float) and math.isfinite(value)
        if not valid:
            raise ValueError(f'{name}: invalid literal default for {kind.name()}')
        if kind in (hou.parmTemplateType.Float, hou.parmTemplateType.Int):
            if ((tpl.minIsStrict() and value < tpl.minValue())
                    or (tpl.maxIsStrict() and value > tpl.maxValue())):
                raise ValueError(f'{name}: default is outside strict parameter limits')
        old = tpl.defaultValue()
        # ToggleParmTemplate uses a scalar default; other scalar templates use a tuple.
        tpl.setDefaultValue(bool(value) if kind == hou.parmTemplateType.Toggle else (value,))
        group.replace(name, tpl)
        targets.append(p)
        changes[name] = {'before': dsh_node_access._val(old), 'after': dsh_node_access._val(tpl.defaultValue())}
    snapshots = dsh_parameter_values._parameter_snapshot(targets)  # preflight locks before the first write

    def restore_values():
        # Reacquire parms after replacing their templates.
        return dsh_parameter_values._restore_parameters(snapshots)

    try:
        n.setParmTemplateGroup(group, rename_conflicting_parms=False)
        errors = restore_values()
        if errors:
            raise RuntimeError(f'current parameter state restore failed: {errors}')
        for name, change in changes.items():
            p = n.parm(name)
            actual = dsh_node_access._val(p.parmTemplate().defaultValue())
            if actual != change['after']:
                raise RuntimeError(f'{name}: default readback mismatch: {actual!r}')
            _, keys, value = snapshots[name]
            current = (p.unexpandedString() if p.parmTemplate().type() == hou.parmTemplateType.String
                       else p.eval()) if not keys else None
            if tuple(p.keyframes()) != keys or current != value:
                raise RuntimeError(f'{name}: current value or animation changed during default update')
        return {'node': n.path(), 'mode': 'update_defaults', 'ok': True,
                'updated': changes, 'current_state_preserved': True,
                'current_values': {name: dsh_node_access._val(n.parm(name).eval()) for name in changes}}
    except Exception as error:
        restore_errors = []
        try:
            n.setParmTemplateGroup(before_group, rename_conflicting_parms=False)
        except Exception as rollback_error:
            restore_errors.append(str(rollback_error))
        restore_errors.extend(restore_values())
        if restore_errors:
            raise dsh_errors.CheckpointError(f'default update restoration failed: {restore_errors}',
                                  {'ok': False, 'node': n.path(), 'restored': False}) from error
        raise




def create_spare_parms(node, code_parm: str = "snippet",
                       defaults: dict | None = None,
                       spec: list | None = None,
                       allow_foreign: str | None = None, *, update_defaults: dict | None = None,
                       layout: list | None = None, dry_run: bool = False) -> dict:
    """从代码参数的 ch/chf/chi/chv/chs 引用创建缺失 spare parameters。

    layout可选模式：与spec/defaults/update_defaults互斥，复用houdini-parameter-ui
    组件，默认追加到单节点而不改HDA定义。dry_run=True返回展开界面/建议且零写入。
    拒绝同名模板/通道；保持已有值/keys/locks，失败恢复旧接口和通道；不创建绑定。
    菜单/颜色tuple/ramp等完整layout字段和可执行示例见verb_help('hda_set_interface', detail='full')；
    下方简化spec只支持folder与scalar，不要将完整layout字段混入简化spec。

    对齐 Wrangle 参数编辑器的 Create Parameters 意图，但要求默认值显式可审计；
    已存在参数默认不重建。``chramp`` 等复杂引用列入 unsupported，交给 HDA/interface
    或裸 hou 处理。

    ``spec`` 的精确递归 schema：folder 条目是
    ``{"type":"folder","name":"controls","label":"Controls","parms":[...]}``；
    scalar 条目是 ``{"type":"toggle|int|float|string","name":"speed",
    "label":"Speed","default":1,"min":0,"max":10,
    "min_strict":False,"max_strict":False,"help":"..."}``。只有 folder 接受
    ``parms``；scalar 必须有 ``name``，其余字段可选。例如::

        create_spare_parms(node, spec=[
            {"type": "folder", "name": "controls", "parms": [
                {"type": "toggle", "name": "enabled", "default": True},
                {"type": "float", "name": "speed", "default": 1.0,
                 "min": 0.0, "max": 10.0},
            ]},
        ])

    新建参数接口后重新赋写code_parm原始源码/keys以刷新编译依赖，不改源码或烘焙表达式。
    返回refreshed_code_parm（未刷新为None）；源码锁定在写入接口前拒绝。
    spec 模式返回 ``node/mode/created/leaf_values``；扫描模式返回
    ``node/code_parm/references/created/existing/defaults_applied/unsupported``。
    显式 ``update_defaults={name:literal}`` 仅更新1..32个已有scalar spare默认值，
    与spec/defaults/非默认code_parm互斥；保留当前值、表达式和keys，不重置当前值。
    仅float/int/toggle/string，拒绝内建参数、tuple/menu/callback/multiparm、表达式默认值。
    返回updated前后默认值、current_values/current_state_preserved；要同时改变当前值另用set_parms。
    """
    if not isinstance(code_parm, str):
        raise ValueError('code_parm must be a parameter name string; pass a parameter specification as spec=[...]')
    n = dsh_node_access._resolve(node)
    dsh_ownership.require_owned(n, "create_spare_parms", allow_foreign)
    if layout is not None:
        if spec is not None or defaults is not None or update_defaults is not None:
            raise ValueError('layout is exclusive with spec/defaults/update_defaults')
        from dsh_parameter_ui import apply_spare_layout
        try:
            return apply_spare_layout(n, layout, code_parm, dry_run)
        except dsh_errors.CheckpointError:
            raise
        except Exception as error:
            raise dsh_errors.CheckpointError(str(error), {'ok': False, 'mode': 'layout',
                'phase': 'preflight', 'scene_writes': 0}) from error
    if dry_run is not False:
        raise ValueError('dry_run requires layout mode')
    if update_defaults is not None:
        if spec is not None or defaults is not None or code_parm != 'snippet':
            raise ValueError('update_defaults is exclusive with spec/defaults/code_parm scanning')
        return _update_spare_defaults(n, update_defaults)
    if spec is not None:
        if not isinstance(spec, (list, tuple)) or not spec:
            raise ValueError("spec 必须是非空 list")
        names = set()
        templates = [
            _spare_spec_template(item, f"spec[{index}]", names)
            for index, item in enumerate(spec)
        ]
        conflicts = sorted(
            name for name in names
            if n.parm(name) is not None or n.parmTuple(name) is not None
        )
        if conflicts:
            raise ValueError(
                f"节点 {n.path()} 已存在同名参数/文件夹：{conflicts}；"
                "显式 spec 不做隐式覆盖"
            )
        group = n.parmTemplateGroup()
        for template in templates:
            group.append(template)
        refreshed = dsh_parameter_values._apply_spare_interface(n, group, code_parm)
        leaves = []
        def collect(items):
            for item in items:
                if str(item.get("type", "")).strip().lower() == "folder":
                    collect(item.get("parms", []))
                else:
                    leaves.append(item["name"])
        collect(spec)
        return {
            "node": n.path(),
            "mode": "spec",
            "created": sorted(names),
            "refreshed_code_parm": refreshed,
            "leaf_values": {
                name: dsh_node_access._val(n.parm(name).eval()) for name in leaves
            },
        }
    defaults = {} if defaults is None else defaults
    if not isinstance(defaults, dict):
        raise ValueError("defaults 必须是 dict：{参数名: 默认值}")
    code_parameter = n.parm(code_parm)
    if code_parameter is None:
        raise ValueError(
            f"节点 {n.path()} 没有代码参数 {code_parm!r}；"
            "先用 list_parms 找真实代码参数名"
        )
    code = code_parameter.evalAsString()
    pattern = re.compile(
        r"\b(?P<func>ch|chf|chi|chv|chs)\s*\(\s*['\"](?P<name>[A-Za-z_]\w*)['\"]"
    )
    references = {}
    for match in pattern.finditer(code):
        references.setdefault(match.group("name"), match.group("func"))
    unsupported = sorted(set(
        match.group(1) for match in re.finditer(
            r"\b(chramp|chdict|chsop|chsoplist)\s*\(", code
        )
    ))
    if not references:
        return {
            "node": n.path(), "code_parm": code_parm,
            "created": [], "existing": [], "unsupported": unsupported,
        }
    group = n.parmTemplateGroup()
    templates = []
    created_names = []
    existing = []
    for name, func in references.items():
        if n.parm(name) is not None or n.parmTuple(name) is not None:
            existing.append(name)
            continue
        label = name.replace("_", " ").title()
        default = defaults.get(name)
        if func == "chi":
            value = int(0 if default is None else default)
            template = hou.IntParmTemplate(name, label, 1, default_value=(value,))
        elif func == "chv":
            if default is None:
                values = (0.0, 0.0, 0.0)
            elif isinstance(default, (list, tuple)) and len(default) == 3:
                values = tuple(float(value) for value in default)
            else:
                raise ValueError(f"chv 参数 {name!r} 的默认值必须是 3 分量 list/tuple")
            template = hou.FloatParmTemplate(name, label, 3, default_value=values)
        elif func == "chs":
            value = "" if default is None else str(default)
            template = hou.StringParmTemplate(name, label, 1, default_value=(value,))
        else:  # ch / chf
            value = float(0.0 if default is None else default)
            template = hou.FloatParmTemplate(name, label, 1, default_value=(value,))
        templates.append(template)
        created_names.append(name)
    for template in templates:
        group.append(template)
    refreshed = dsh_parameter_values._apply_spare_interface(n, group, code_parm) if templates else None
    applied = {}
    for name in created_names:
        if name in defaults:
            result = dsh_parameter_values.set_parm(n, name, defaults[name])
            applied[name] = result.get("value", result.get("expression"))
    return {
        "node": n.path(),
        "code_parm": code_parm,
        "references": references,
        "created": created_names,
        "existing": existing,
        "defaults_applied": applied,
        "unsupported": unsupported,
        "refreshed_code_parm": refreshed,
    }


def bind_controls(controller, bindings: list, *, dry_run: bool = False,
                  expected_plan: str | None = None, replace_existing: bool = False,
                  allow_foreign: str | None = None) -> dict:
    """Bind explicit numeric controls to target parameter paths; never chooses targets.

    bindings=[{source:'control_name',target:'/obj/node/parm',scale:1,offset:0}].
    First dry_run=True; apply requires its expected_plan=plan_sha256. Protects
    existing keys/expressions unless replace_existing=True. Source expressions,
    menus/callbacks/multiparms and source-target chains in a batch are unsupported.
    Integer targets need integer sources and scale/offset. Failure restores target
    channels; expression/value readback does not verify final domain geometry.
    """
    from dsh_control_bindings import bind_controls as bind
    return bind(controller, bindings, dry_run, expected_plan, replace_existing, allow_foreign)


def parameter_ui(node, max_depth: int = 6, include_state: bool = False, analyze_ui: bool = False) -> dict:
    """只读任意节点的实例/定义模板树与interface_sha256。

    analyze_ui=True给出计数/深度、标题/条件引用、菜单token与密集行建议；仅分析
    返回树，截断见omitted_children。不求值表达式/菜单，不cook或自动修复。
    """
    n = dsh_node_access._resolve(node)
    if type(include_state) is not bool:
        raise ValueError('include_state must be boolean')
    if type(analyze_ui) is not bool:
        raise ValueError('analyze_ui must be boolean')
    if not isinstance(max_depth, int) or max_depth < 0 or max_depth > 20:
        raise ValueError("max_depth 必须是 0..20 的整数")
    definition = n.type().definition()
    out = {
        "node": n.path(),
        "category": n.type().category().name(),
        "type": n.type().name(),
        "description": n.type().description(),
        "definition": None,
        "interface": [
            dsh_parameter_templates._template_info(entry, 0, max_depth)
            for entry in n.parmTemplateGroup().entries()
        ],
    }
    if definition is not None:
        from dsh_hda_interfaces import interface_revision
        out['interface_sha256'] = interface_revision(n)
        sections = []
        for name, section in sorted(definition.sections().items()):
            try:
                size = len(section.contents())
            except Exception:
                size = None
            sections.append({"name": name, "chars": size})
        out["definition"] = {
            "library_file": definition.libraryFilePath(),
            "node_type": definition.nodeTypeName(),
            "description": definition.description(),
            "version": definition.version(),
            "min_inputs": definition.minNumInputs(),
            "max_inputs": definition.maxNumInputs(),
            "max_outputs": definition.maxNumOutputs(),
            "sections": sections,
            "interface": [dsh_parameter_templates._template_info(entry, 0, max_depth)
                          for entry in definition.parmTemplateGroup().entries()],
        }
        out['matches_definition'] = n.matchesCurrentDefinition()
        out['locked'] = n.isLockedHDA()
    if include_state:
        from dsh_hda_interfaces import parameter_states
        out['parameter_states'] = parameter_states(n)
    if analyze_ui:
        from dsh_parameter_ui import analyze_ui as inspect_ui
        out['ui_analysis'] = inspect_ui(out['interface'])
        out['ui_analysis']['max_depth_requested'] = max_depth
    return out
