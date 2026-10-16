"""Houdini hda operations. Executed on the Bridge owning thread."""
from __future__ import annotations

import os
import re
import hou
import dsh_node_access
import dsh_ownership
import dsh_parameter_templates


def _default_hda_file(name: str) -> str:
    hip_path = hou.hipFile.path()
    hip_dir = os.path.dirname(hip_path)
    if not hip_dir or os.path.basename(hip_path).lower() == "untitled.hip":
        raise ValueError(
            "当前 hip 尚未保存，无法推导默认 HDA 位置；请先保存 hip，"
            "或显式传 hda_file"
        )
    file_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._") or "asset"
    return os.path.join(hip_dir, "otls", file_stem + ".hda")


def hda_create(
    node,
    name: str,
    description: str | None = None,
    hda_file: str | None = None,
    min_inputs: int = 0,
    max_inputs: int = 0,
    replace: bool = False,
    allow_foreign: str | None = None,
    *,
    max_outputs: int | None = None,
) -> dict:
    """把已有节点（通常 subnet）转为 HDA；默认写到 ``$HIP/otls``。

    同名已安装类型或已存在目标文件在写前拒绝。replace=True不再支持；维护已有
    工具用hda_version在来源库追加原生版本，再hda_switch_version切换指定实例。
    hda_fork仅用于独立衍生新工具；项目新工具默认$HIP/otls，共享新工具指定package资源路径。
    max_outputs可选1..64，None保留原生默认；这是端口上限，不会自动接线。
    实例spare不保证进入定义；返回pending_spare_parameters与原地hda_edit('promote')指引。
    不以创建成功替代新实例/公共输出验证；转换只接续可证明来自同一锁定原生定义的自有后代。
    """
    n = dsh_node_access._resolve(node)
    dsh_ownership.require_owned(n, "hda_create", allow_foreign)
    if type(replace) is not bool:
        raise ValueError('replace must be boolean')
    if replace:
        raise ValueError('hda_create replace=True is not supported: it would destroy shared instances/definitions. '
                         'Maintain the source with hda_version, then hda_switch_version on selected instances. Use hda_fork only for an independent derived tool.')
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name 必须是非空 HDA 类型名")
    name = name.strip()
    if not isinstance(min_inputs, int) or not isinstance(max_inputs, int):
        raise ValueError("min_inputs/max_inputs 必须是整数")
    if min_inputs < 0 or max_inputs < min_inputs:
        raise ValueError(
            f"输入数不合法：需要 0 <= min_inputs <= max_inputs，"
            f"收到 {min_inputs}/{max_inputs}"
        )
    if max_outputs is not None and (type(max_outputs) is not int or not 1 <= max_outputs <= 64):
        raise ValueError('max_outputs must be an integer in 1..64 or None (native default)')

    category = n.type().category()
    existing_type = category.nodeTypes().get(name)
    if existing_type is not None:
        definitions = list(existing_type.allInstalledDefinitions())
        files = sorted({d.libraryFilePath() for d in definitions})
        raise ValueError(f"HDA 类型 '{name}' 已存在或为原生类型；definitions={files}。"
                         "已有工具用hda_version在来源库追加版本，再hda_switch_version；独立衍生才用hda_fork。")

    target = _default_hda_file(name) if hda_file is None else hou.expandString(str(hda_file))
    target = os.path.abspath(target)
    from dsh_hda_interfaces import require_library_location
    require_library_location(target)
    if os.path.lexists(target):
        raise ValueError(f'HDA target file already exists: {target}; hda_create only creates new tools/libraries. '
                         'For existing tool maintenance use hda_version to append a type version in its actual source library.')
    parent_dir = os.path.dirname(target)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    source_identity = int(n.sessionId())
    captured_identity = dsh_ownership.capture_identity(n)
    source_owner = captured_identity[1]
    native_before = dsh_ownership.snapshot_native_conversion(n)
    created = n.createDigitalAsset(
        name=name,
        hda_file_name=target,
        description=description,
        min_num_inputs=min_inputs,
        max_num_inputs=max_inputs,
        change_node_type=True,
        create_backup=True,
    )
    definition = created.type().definition()
    if definition is None:
        raise RuntimeError(f"createDigitalAsset 返回后类型 '{name}' 没有 definition")
    if max_outputs is not None:
        definition.setMaxNumOutputs(max_outputs)
    from dsh_hda_interfaces import register_created_definition
    register_created_definition(definition)
    # Conversion invalidates native delayed internals (e.g. a Wrangle's VOP).
    # Materialize only captured native anchors within this serialized mutation,
    # never arbitrary user definitions or a future cook/adoption rule.
    native_transfers = dsh_ownership.reconcile_native_conversion(native_before)
    # Conversion may replace the root HOM identity. Transfer only its trusted
    # existing provenance; never adopt foreign descendants or an allowed foreign source.
    dsh_ownership.transfer_identity(captured_identity, created)
    pending_spares = [p.name() for p in created.spareParms()
                      if definition.parmTemplateGroup().find(p.name()) is None]
    return {
        "node": created.path(),
        "type": created.type().name(),
        "description": created.type().description(),
        "hda_file": definition.libraryFilePath(),
        "min_inputs": definition.minNumInputs(),
        "max_inputs": definition.maxNumInputs(),
        "max_outputs": definition.maxNumOutputs(),
        "instance_interface_entries": len(created.parmTemplateGroup().entries()),
        "definition_interface_entries": len(definition.parmTemplateGroup().entries()),
        "pending_spare_parameters": pending_spares[:64],
        "pending_spare_parameter_count": len(pending_spares),
        "native_identity_transfers": native_transfers,
        "next_action": ("Instance spare controls are not yet in the definition. Read hda_edit help; "
                        "preview unlock if locked, then promote with expected_plan to migrate in place. "
                        "Verify a fresh instance before considering replacement."
                        if pending_spares else "Verify fresh-instance parameters and public outputs; later internal edits require hda_edit save."),
        "verification_scope": "definition created; spare migration, public outputs and fresh-instance behavior require separate verification",
        "replaced": False,
        "destroyed_instances": [],
        "removed_definitions": [],
    }


def hda_fork(node, name: str, hda_file: str, description: str | None = None) -> dict:
    """Copy the source's actual HDA definition into a NEW type and NEW library.

    Reading the source does not require node ownership. Never copies unsaved
    instance edits, changes the original definition, migrates original instances,
    or creates an instance. The new type is installed only in this process; use
    tab_create with the returned exact type and verify its public behavior.
    """
    n, source = dsh_node_access._hda_definition(node)
    if not isinstance(name, str) or not name.strip():
        raise ValueError('name must be an explicit nonempty new HDA type name')
    name = name.strip()
    category = n.type().category()
    if name == n.type().name() or name in category.nodeTypes():
        raise ValueError('hda_fork requires a new type name; never shadows an installed type or migrates its instances')
    if not isinstance(hda_file, str) or not hda_file.strip():
        raise ValueError('hda_file must be an explicit new independent library path')
    if description is not None and (not isinstance(description, str) or not description.strip()):
        raise ValueError('description must be a nonempty string or None')
    target = os.path.abspath(hou.expandString(hda_file))
    from dsh_hda_interfaces import require_library_location
    require_library_location(target)
    if os.path.lexists(target):
        raise ValueError(f'HDA target file already exists: {target}; fork requires a new independent library')
    os.makedirs(os.path.dirname(target), exist_ok=True)
    source_file = source.libraryFilePath()
    try:
        source.copyToHDAFile(target, new_name=name, new_menu_name=description)
        hou.hda.installFile(target)
        fork_type = category.nodeTypes().get(name)
        definition = fork_type.definition() if fork_type else None
        if definition is None or os.path.normcase(os.path.realpath(definition.libraryFilePath())) != os.path.normcase(os.path.realpath(target)):
            raise RuntimeError('fork did not resolve to its newly created library')
        from dsh_hda_interfaces import register_created_definition
        register_created_definition(definition)
    except Exception:
        # Only this absent-before file/new type is eligible for failed-copy cleanup.
        for loaded in hou.hda.loadedFiles():
            if os.path.normcase(os.path.realpath(loaded)) == os.path.normcase(os.path.realpath(target)):
                hou.hda.uninstallFile(loaded)
        if os.path.isfile(target):
            os.unlink(target)
        raise
    return {'ok': True, 'category': category.name(), 'type': definition.nodeTypeName(),
            'description': definition.description(), 'hda_file': definition.libraryFilePath(),
            'source_node': n.path(), 'source_type': n.type().name(), 'source_library': source_file,
            'copied': 'current definition only; unsaved instance changes excluded',
            'source_instances_migrated': 0, 'instances_created': 0,
            'next_action': 'Create an instance with tab_create using this exact type, then verify controls, public outputs and dependencies.'}


def hda_version(node, version: str, *, dry_run=False, allow_foreign=None) -> dict:
    """Append a native ::version type to the actual SOURCE library; preserve older definitions.

    version is a numeric suffix such as 1.1, not HDADefinition Version metadata.
    Copies saved definition only, preserves scope/namespace, never migrates instances.
    Refuses duplicate types; restores library/new type on failure. Foreign library
    needs one-call allow_foreign and is not adopted by creating a version inside it.
    Then hda_switch_version the selected instance before editing the new definition.
    """
    from dsh_hda_versions import create_version
    return create_version(node, version, dry_run=dry_run, allow_foreign=allow_foreign)


def hda_switch_version(node, type_name: str, *, dry_run=False, allow_foreign=None) -> dict:
    """Switch one locked HDA instance to an exact installed version of the same family.

    Native changeNodeType keeps name/common parameter channels and connections,
    loads target contents; never migrates other instances. For a current-session
    instance, only internal identities newly created by this switch are registered;
    existing identities and foreign instances never gain ownership from a switch.
    Read tool_inspect type_versions and source libraries first; dry_run reports scope.
    Unlocked contents require hda_edit save/lock or explicit discard before switching.
    Node and replaced descendants require ownership or one-call allow_foreign.
    Scene undo covers scene edits only; arbitrary asset callback effects are excluded.
    """
    from dsh_hda_versions import switch_version
    return switch_version(node, type_name, dry_run=dry_run, allow_foreign=allow_foreign)


def hda_edit(node, action, *, dry_run=False, expected_plan=None, discard_changes=False, allow_foreign=None) -> dict:
    """Preview-bound unlock/save/lock/promote of a disk HDA, never flatten/unpack.

    First dry_run=True, review plan_sha256/affected_instances; apply with expected_plan.
    lock requires discard_changes=True for unmatched contents; discarded descendants
    must also be owned/explicitly authorized. Unlock never grants descendant ownership.
    save requires unlocked source with definition interface (no spare overlays), checks
    every affected instance, restores this call's definition/library on write failure.
    promote moves the source additive spare interface into the definition while
    preserving existing root channels/keys/locks; rejects other instance overlays.
    <=64 instances/512 editable descendants/32MiB library/2MiB source. Locked nested
    HDA definitions count once for the work bound; ownership still checks full contents.
    No cook/GUI/semantic proof.
    """
    from dsh_hda_lifecycle import edit
    return edit(node, action, dry_run=dry_run, expected_plan=expected_plan,
                discard_changes=discard_changes, allow_foreign=allow_foreign)


def hda_set_interface(
    node,
    spec: list | None = None,
    keep_std: bool = True,
    hide_builtin_tabs: bool = False,
    allow_foreign: str | None = None,
    *,
    edits: list | None = None,
    expected_sha256: str | None = None,
    dry_run: bool = False,
    layout: list | None = None,
) -> dict:
    """按 JSON 安全 spec 声明式重建 HDA 参数面板并验证 conditional。

    原始spec字段（同样适用于create_spare_parms的layout，不适用于其简化spec）：
    每项必填type/name；label默认name。全局唯一稳定name，multiparm内每层含一个#。
    float/int: default为标量；components=2..4时default须等长数组；look=regular/vector/color，
    color要求3/4分量。min/max是建议范围，min_strict/max_strict才是硬限制。
    int+menu: menu={items:[token,...],labels:[label,...]}，default是整数索引，不是token；
    type=menu同样以整数索引指定default。float不接受menu，string不创建菜单。
    toggle: default布尔。string: default文本，可选file=dir/geo/alembic/image/any。
    folder: parms子项，folder_type=simple/tabs/collapsible/multiparm_list/multiparm_tabs/
    multiparm_scroll；multiparm的default为0..64条目数。separator/label只需type/name。
    ramp: ramp_type=float/color，points=2..16，basis=linear/constant/catmullrom/bspline，
    show_controls布尔。button必须给非空Python callback；创建不执行callback。
    通用可选字段：help/join_next/hidden/hide_label/tags/hide_when/disable_when。
    条件为Houdini条件字符串，例如{ enabled == 0 }，不是Python表达式。
    未列字段不要猜测；先用小layout及dry_run验证，不需要读取插件实现源码。

    最小示例（先预检，确认后原样应用；输出/绑定仍须单独实现）::

        layout = [{"type":"folder","name":"controls","parms":[
            {"type":"float","name":"width","default":1.0,"min":0.1,"max":5.0},
            {"type":"int","name":"mode","default":0,
             "menu":{"items":["draft","final"],"labels":["Draft","Final"]}},
            {"type":"float","name":"tint","components":3,"look":"color",
             "default":[0.6,0.3,0.1]}]}]
        hda_set_interface(node, layout=layout, dry_run=True)

    普通Null/子网的实例参数用create_spare_parms(node,layout=layout,dry_run=True)，
    不为创建控制面板强制转HDA。只读参数值/元数据用parameter_ui/read_parms。

    layout为可选组件列表，与spec/edits互斥，仍是整组重建。component支持section
    (name/label/parms, enabled?/collapsed?/header_parm?)、row(parms)、remap
    (name/label/enabled?/ramp_type?)、repeater(name/label/parms/style?/count?/label_ref?)。
    可混用普通spec；新增label/ramp、numeric components/look、multiparm与tab条件。
    dry_run=True只预检并返回展开interface/ui_analysis，不写入；各模式仍须exec。
    layout成功仍是整组替换、不保证旧通道保持；写后失败恢复本调用定义/实例界面/通道/库。
    定义写入与场景undo隔离，后续同exec失败不撤销已经成功的库写入；布局组件不代表业务功能。

    增量模式：spec省略，传edits=[{op:'update',name,fields}或{op:'add',spec,folder?}]
    并把parameter_ui返回的interface_sha256传为expected_sha256。update支持label/help/default/min/max/min_strict/
    max_strict/hidden/join_next/disable_when/hide_when。dry_run=True预览但仍须exec。
    所有受影响实例均检查ownership；保留旧通道值/keys/locks，新实例用新默认。
    不支持删除/改名/移动/类型转换/ramp/multiparm/实例界面覆盖；最多32项、64实例。
    同步失败恢复本调用的定义、通道、磁盘库，不保证外部副作用或后续exec失败恢复。

    自定义部分是**整组重建**，不是 merge。``keep_std`` 对 subnet HDA 从原生
    subnet 类型重新取得 Transform/Subnet 等标准页，避免把旧自定义参数夹带回来；
    ``hide_builtin_tabs`` 通过公开的 ParmTemplateGroup.hide 隐藏这些页。所有
    ``hide_when`` 在提交后读回验证，Houdini 若吞掉 conditional，则自动补丁
    DialogScript 的 ``hidewhen`` 并再次验证。
    SOP subnet标准label1..label4管理字段保留但隐藏，不影响输入名称/接线或自定义Label。
    与现有实例spare同名的重建在定义/磁盘写入前拒绝，不隐式合并或丢弃spare。
    """
    if edits is None:
        kwargs = dict(spec=spec, keep_std=keep_std, hide_builtin_tabs=hide_builtin_tabs,
                      allow_foreign=allow_foreign, expected_sha256=expected_sha256, layout=layout)
        if type(dry_run) is not bool:
            raise ValueError('dry_run must be boolean')
        preview = _rebuild_hda_interface(node, dry_run=True, **kwargs)
        if dry_run:
            return preview
        from dsh_hda_interfaces import definition_write_guard
        n, _ = dsh_node_access._hda_definition(node)
        with definition_write_guard(n, 'hda_set_interface rebuild', allow_foreign):
            return _rebuild_hda_interface(node, dry_run=False, **kwargs)
    return _rebuild_hda_interface(node, spec, keep_std, hide_builtin_tabs, allow_foreign,
                                  edits=edits, expected_sha256=expected_sha256, dry_run=dry_run, layout=layout)


def _rebuild_hda_interface(node, spec=None, keep_std=True, hide_builtin_tabs=False, allow_foreign=None,
                           *, edits=None, expected_sha256=None, dry_run=False, layout=None):
    if layout is not None:
        if spec is not None or edits is not None or expected_sha256 is not None:
            raise ValueError('layout is exclusive with spec/edits/expected_sha256')
        from dsh_parameter_ui import expand_layout, validate_layout_spec
        spec = expand_layout(layout)
        validate_layout_spec(spec)
    if edits is not None:
        if spec is not None or keep_std is not True or hide_builtin_tabs is not False:
            raise ValueError('edits is exclusive with spec/keep_std/hide_builtin_tabs options')
        from dsh_hda_interfaces import patch_interface
        return patch_interface(node, edits, expected_sha256, dry_run, allow_foreign)
    if expected_sha256 is not None:
        raise ValueError('expected_sha256 requires edits mode')
    if type(dry_run) is not bool:
        raise ValueError('dry_run must be boolean')
    n, definition = dsh_node_access._hda_definition(node)
    dsh_ownership.require_owned(n, "hda_set_interface", allow_foreign)
    from dsh_hda_interfaces import require_definition_owned
    require_definition_owned(definition, 'hda_set_interface rebuild', allow_foreign)
    for instance in n.type().instances():
        dsh_ownership.require_owned(instance, 'hda_set_interface rebuild affected instance', allow_foreign)
    if not isinstance(spec, (list, tuple)):
        raise ValueError("spec 必须是参数条目 list")
    names: set = set()
    conditions: dict[str, str] = {}
    custom = [
        dsh_parameter_templates._build_interface_template(item, f"spec[{index}]", names, conditions)
        for index, item in enumerate(spec)
    ]
    # An instance overlay can survive definition replacement and merge multiparm
    # children. Refuse the ambiguity BEFORE touching the shared library.
    definition_names = dsh_parameter_templates._all_template_names(definition.parmTemplateGroup().entries())
    for instance in n.type().instances():
        overlay_names = dsh_parameter_templates._all_template_names(instance.parmTemplateGroup().entries()) - definition_names
        collisions = names & overlay_names
        if collisions:
            raise ValueError(f'instance spare interface conflicts with definition rebuild on {instance.path()}: '
                             f'{sorted(collisions)}; no definition/library writes. '
                             'Keep the source intact; use a clean definition instance and verify migration separately.')

    standard = dsh_parameter_templates._standard_interface_entries(n) if keep_std else []
    conflicts = names & dsh_parameter_templates._all_template_names(standard)
    if conflicts:
        raise ValueError(
            f"自定义 spec 与 Houdini 标准参数重名：{sorted(conflicts)}；"
            "请改自定义 name（不要覆盖 tx/rx 等内置参数）"
        )

    group = hou.ParmTemplateGroup()
    # 自定义界面优先：顶层按钮会自然出现在最上方，标准页排在其后。
    for template in custom:
        group.append(template)
    standard_names = []
    for template in standard:
        # Native SOP subnet input-label editors are authoring metadata, not
        # business controls. Keep their values/port semantics, hide only these
        # standard templates; do not hide custom Label/heading controls.
        if (n.type().category() == hou.sopNodeTypeCategory()
                and template.name() in {'label1', 'label2', 'label3', 'label4'}):
            template.hide(True)
        group.append(template)
        standard_names.append(template.name())
    if hide_builtin_tabs:
        for name in standard_names:
            try:
                group.hide(name, True)
            except Exception as e:
                raise ValueError(f"隐藏标准页 {name!r} 失败：{e}") from e

    from dsh_parameter_ui import analyze_ui as inspect_ui
    preview_tree = [dsh_parameter_templates._template_info(t, 0, 20) for t in group.entries()]
    if dry_run:
        return {'node': n.path(), 'mode': 'layout' if layout is not None else 'rebuild',
                'ok': True, 'dry_run': True, 'applied': False, 'scene_writes': 0,
                'interface': preview_tree, 'ui_analysis': inspect_ui(preview_tree)}
    definition.setParmTemplateGroup(group, rename_conflicting_parms=False)

    # H21 实测 setParmTemplateGroup 会吞一部分 API setConditional：先读回，
    # 只对丢失项走 DialogScript 兜底，避免无谓改写定义源码。
    after = n.parmTemplateGroup()
    missing = {}
    for name, expected in conditions.items():
        template = after.find(name)
        actual = None
        if template is not None:
            actual = template.conditionals().get(hou.parmCondType.HideWhen)
        if actual != expected:
            missing[name] = expected
    patched = []
    if missing:
        sections = definition.sections()
        if "DialogScript" not in sections:
            raise RuntimeError(
                f"conditional 被 Houdini 吞掉，但定义没有 DialogScript section：{sorted(missing)}"
            )
        dialog = sections["DialogScript"].contents()
        for name, condition in missing.items():
            dialog = dsh_parameter_templates._patch_dialog_hide_when(dialog, name, condition)
            patched.append(name)
        definition.addSection("DialogScript", dialog)

    verified = {}
    final_group = n.parmTemplateGroup()
    from dsh_hda_interfaces import _walk
    observed_templates = list(_walk(final_group.entries()))
    business_order = []
    for index, template in enumerate(custom):
        def verify_template(expected, actual):
            if actual.type() != expected.type() or actual.label() != expected.label():
                raise RuntimeError(f'UI template order/type/label mismatch: {expected.name()}')
            for key, value in expected.tags().items():
                if actual.tags().get(key) != value:
                    raise RuntimeError(f'UI tag readback mismatch: {expected.name()}/{key}')
            for getter in ('joinsWithNext', 'isLabelHidden', 'numComponents', 'defaultValue'):
                if hasattr(expected, getter) and getattr(actual, getter)() != getattr(expected, getter)():
                    raise RuntimeError(f'UI property readback mismatch: {expected.name()}/{getter}')
            for condition, value in expected.conditionals().items():
                if actual.conditionals().get(condition) != value:
                    raise RuntimeError(f'UI conditional readback mismatch: {expected.name()}/{condition}')
            if isinstance(expected, hou.FolderParmTemplate):
                if actual.folderType() != expected.folderType():
                    raise RuntimeError(f'UI folder layout mismatch: {expected.name()}')
                if actual.tabConditionals() != expected.tabConditionals():
                    raise RuntimeError(f'UI tab conditional readback mismatch: {expected.name()}')
                children = actual.parmTemplates()
                if len(children) != len(expected.parmTemplates()):
                    raise RuntimeError(f'UI folder child count mismatch: {expected.name()}')
                for child, actual_child in zip(expected.parmTemplates(), children):
                    verify_template(child, actual_child)
        # Existing hide_when fallback below owns legacy HideWhen verification.
        if layout is not None:
            actual = final_group.find(template.name())
            if actual is None and isinstance(template, hou.FolderParmTemplate):
                # Houdini normalizes tab-set names and can wrap OBJ controls in
                # a spare folder. Match a renamed folder only when its native
                # type/label is unique, never by its old positional index.
                candidates = [t for t in _walk(final_group.entries())
                              if isinstance(t, hou.FolderParmTemplate)
                              and t.label()==template.label() and t.folderType()==template.folderType()]
                if len(candidates)==1:
                    actual=candidates[0]
            if actual is None:
                raise RuntimeError(f'UI template missing or ambiguous after native normalization: {template.name()}')
            positions = [i for i,t in enumerate(observed_templates) if t.name()==actual.name() and t.type()==actual.type()]
            if len(positions)!=1:
                raise RuntimeError(f'UI template order is ambiguous: {template.name()}')
            business_order.append(positions[0])
            verify_template(template, actual)
    if business_order != sorted(set(business_order)):
        raise RuntimeError('UI custom template order changed during native normalization')
    for name, expected in conditions.items():
        template = final_group.find(name)
        actual = None if template is None else template.conditionals().get(
            hou.parmCondType.HideWhen
        )
        if actual != expected:
            raise RuntimeError(
                f"参数 {name!r} hide_when 写后验证失败：expected={expected!r}, actual={actual!r}"
            )
        verified[name] = actual

    hidden_std = []
    if hide_builtin_tabs:
        final_group = n.parmTemplateGroup()
        for template in final_group.entries():
            try:
                if template.isHidden() and template.label() in {
                    t.label() for t in standard
                }:
                    hidden_std.append(template.label())
            except Exception:
                pass
    return {
        "node": n.path(),
        "custom_entries": [t.name() for t in custom],
        "custom_parms": sorted(names),
        "standard_kept": bool(keep_std),
        "standard_entries": standard_names,
        "hidden_standard_tabs": sorted(hidden_std),
        "hide_when_verified": verified,
        "dialogscript_patched": patched,
        'mode': 'layout' if layout is not None else 'rebuild',
        'ok': True, 'applied': True,
        'ui_analysis': inspect_ui([dsh_parameter_templates._template_info(t, 0, 20) for t in final_group.entries()]),
    }
