"""Houdini node creation. Executed on the Bridge owning thread."""
from __future__ import annotations

import hou
import toolutils
import dsh_errors
import dsh_node_access
import dsh_node_layout
import dsh_node_types
import dsh_ownership
import dsh_parameter_values


_TAB_TOOL_ALLOWLIST = {
    "lop_karma_setup",
    "vop_karmamtlxsubnet",
}


_PENDING_TAB_USER_STATE = None


_TAB_RESTORE_POSTED = False


def _network_editor():
    if not hou.isUIAvailable():
        return None
    pane = toolutils.networkEditor()
    if pane is not None:
        return pane
    for tab in hou.ui.paneTabs():
        if tab.type() == hou.paneTabType.NetworkEditor:
            return tab
    return None


def _run_shelf_tool(tool, parent: hou.Node, type_name: str) -> hou.Node | None:
    """在目标网络中跑 shelf tool，返回其新建的节点；无 pane/失败时返回 None。"""
    pane = _network_editor()
    if pane is None:
        return None

    prev_pwd = pane.pwd()
    try:
        pane.setPwd(parent)
        if pane.pwd() is None or pane.pwd().path() != parent.path():
            return None
    except Exception:
        return None

    before = {c.sessionId() for c in parent.children()}
    try:
        toolutils.testTool(
            tool,
            kwargs={
                "pane": pane,
                "toolname": type_name,
                "autoplace": True,
                "shiftclick": False,
                "ctrlclick": False,
                "altclick": False,
            },
        )
    except BaseException:
        # A failed shelf script may already have created part of its network.
        # Never let tab_create reinterpret that semantic failure as permission
        # to create a weaker bare node; clean the known partial creations and
        # re-raise so the bridge can roll back any other undoable edits.
        for child in reversed(parent.children()):
            if child.sessionId() not in before:
                ids = [int(n.sessionId()) for n in (child, *child.allSubChildren())]
                try:
                    child.destroy()
                except Exception:
                    continue  # a live node keeps its registration
                # Headless has no undo, so the bridge registry restore never runs;
                # a partial child destroyed here must not leave a stale entry that
                # a later batch's undo reconcile could adopt.
                for identity in ids:
                    dsh_ownership.forget(identity)
        raise
    finally:
        try:
            if prev_pwd is not None:
                pane.setPwd(prev_pwd)
        except Exception:
            pass

    created = [c for c in parent.children() if c.sessionId() not in before]
    for child in created:
        dsh_ownership.register_owned_node(child)
    if len(created) == 1:
        return created[0]
    # 多个新节点：优先类型完全匹配；否则取第一个（绝不回退 createNode——
    # tool 已经建过节点，再建一次就是场景里的重复残留）
    match = next((c for c in created if c.type().name() == type_name), None)
    if match is not None:
        return match
    return created[0] if created else None


def _tool_context(tool, parent: hou.Node) -> dict:
    """Return Network Editor menu metadata and whether *tool* applies to parent."""
    pane_type = hou.paneTabType.NetworkEditor
    try:
        categories = tuple(tool.toolMenuCategories(pane_type) or ())
    except Exception:
        categories = ()
    try:
        op_type = str(tool.toolMenuOpType(pane_type) or "")
    except Exception:
        op_type = ""
    try:
        locations = list(tool.toolMenuLocations() or ())
    except Exception:
        locations = []

    child_category = parent.childTypeCategory()
    category_match = child_category in categories
    op_type_match = False
    if op_type:
        category_name, _, operator_name = op_type.partition("/")
        if category_name.lower() == child_category.name().lower():
            # Material Library presents a Vop/materialbuilder network even though its
            # owning node is a Lop/materiallibrary. This is the shipped context for the
            # Karma/USD Material Builder tools.
            if operator_name == "materialbuilder":
                op_type_match = (
                    parent.type().category() == hou.lopNodeTypeCategory()
                    and parent.type().name().split("::", 1)[0] == "materiallibrary"
                )
            else:
                parent_type = parent.type().name().split("::", 1)[0]
                op_type_match = parent_type == operator_name
    return {
        "categories": [category.name() for category in categories],
        "op_type": op_type or None,
        "locations": locations,
        "matches": bool(category_match or op_type_match),
    }


def search_tab_entries(parent, query: str = "") -> dict:
    """列出父网络真实可见的节点/Tab tool entry，不把类型注册表冒充菜单。

    返回 entry 的 ``kind`` 为 ``node_type`` 或 ``tool``。Material Library 根层只
    暴露 builder tool；shader 应进入对应 builder 后再创建。隐藏/废弃 node type
    不进入 entries，但计入 excluded。``executable`` 仅表示 dsh 当前安全 allowlist，
    不是 SideFX 工具是否存在。
    """
    parent = dsh_node_access._resolve(parent)
    if not parent.isNetwork():
        raise ValueError(f"{parent.path()} 不是可创建子节点的网络")
    q = str(query or "").strip().lower()
    child_category = parent.childTypeCategory()
    entries = []
    excluded_hidden = 0

    # Since H20 the Material Library root is a builder launcher, not a free-form VOP
    # graph. Its tool entries below are the truthful UI surface.
    material_library_root = (
        parent.type().category() == hou.lopNodeTypeCategory()
        and parent.type().name().split("::", 1)[0] == "materiallibrary"
    )
    if not material_library_root:
        families: dict[str, list] = {}
        for name, node_type in child_category.nodeTypes().items():
            label = node_type.description() or name
            if q and q not in name.lower() and q not in label.lower():
                continue
            if not dsh_node_types._visible_node_type(node_type):
                excluded_hidden += 1
                continue
            match = dsh_node_types._VERSION_RE.match(name)
            base = match.group(1) if match else name
            families.setdefault(base, []).append(node_type)
        for base, node_types in families.items():
            def version_key(node_type):
                match = dsh_node_types._VERSION_RE.match(node_type.name())
                return dsh_node_types._version_key(match.group(2)) if match else ()
            latest = max(node_types, key=version_key)
            entries.append({
                "kind": "node_type",
                "name": latest.name(),
                "base": base,
                "label": latest.description() or latest.name(),
                "versions": sorted(node_type.name() for node_type in node_types),
                "executable": True,
            })

    for tool_id, tool in hou.shelves.tools().items():
        try:
            label = tool.label() or tool_id
        except Exception:
            continue
        if q and q not in tool_id.lower() and q not in label.lower():
            continue
        context = _tool_context(tool, parent)
        if not context["matches"]:
            continue
        entries.append({
            "kind": "tool",
            "name": tool_id,
            "label": label,
            "locations": context["locations"],
            "op_type": context["op_type"],
            "executable": tool_id in _TAB_TOOL_ALLOWLIST,
        })

    entries.sort(key=lambda item: (item["label"].lower(), item["kind"], item["name"]))
    return {
        "parent": parent.path(),
        "child_category": child_category.name(),
        "query": query,
        "entries": entries,
        "excluded_hidden_or_deprecated": excluded_hidden,
    }


def _initialize_created_render_settings(settings: hou.Node) -> None:
    """Shared defaults for newly authored Karma settings, before explicit parms."""
    if settings.type().name().split('::', 1)[0] != 'karmarendersettings':
        return
    from dsh_project_paths import directory_expression
    # Newly authored renders start clear and use the shared image directory.
    # Native variables preserve portability and follow later Save As operations.
    # render_frame never changes these persistent artistic settings.
    render_directory = directory_expression('render')
    for name, value in {'enabledof': 0,
                        'picture': render_directory + '/$HIPNAME.$OS.$F4.exr',
                        'productName': render_directory + '/$HIPNAME.$OS.$F4.checkpoint'}.items():
        parm = settings.parm(name)
        if parm is None:
            raise RuntimeError(f'Karma Setup parameter unavailable: {name}')
        parm.set(value)


def _apply_karma_setup_recipe(parent: hou.Node) -> list:
    """Non-interactive adapter for SideFX ``lop_karma_setup`` semantics."""
    settings = parent.createNode("karmarendersettings", node_name="karmarendersettings")
    _initialize_created_render_settings(settings)
    rop = parent.createNode("usdrender_rop")
    rop.setInput(0, settings)
    settings_name = settings.name()
    required = {
        "rendersettings": f'chs("../{settings_name}/primpath")',
        "husk_instantshutter": f'1 - ch("../{settings_name}/enablemblur")',
        "renderer": (
            f'"BRAY_HdKarma" + ifs(strmatch(chs("../{settings_name}/engine"), '
            '"xpu"), "XPU", "")'
        ),
    }
    for parm_name, expression in required.items():
        parm = rop.parm(parm_name)
        if parm is None:
            raise RuntimeError(
                f"当前 Houdini 的 {rop.type().name()} 缺少 Karma Setup 参数 {parm_name!r}"
            )
        parm.setExpression(expression, language=hou.exprLanguage.Hscript)
    return [settings, rop]


def _apply_karma_material_builder_recipe(parent: hou.Node) -> list:
    """Use the installed SideFX builder initializer without its selection UI."""
    import voptoolutils

    setup = getattr(voptoolutils, "_setupMtlXBuilderSubnet", None)
    mask = getattr(voptoolutils, "KARMAMTLX_TAB_MASK", None)
    if setup is None or not mask:
        raise RuntimeError(
            "当前 Houdini 缺少 Karma Material Builder initializer；"
            "请检查 voptoolutils 版本"
        )
    builder = parent.createNode("subnet", node_name="karmamaterial")
    result = setup(
        subnet_node=builder,
        name="karmamaterial",
        mask=mask,
        folder_label="Karma Material Builder",
        render_context="kma",
    )
    if result is None:
        raise RuntimeError("SideFX Karma Material Builder initializer 返回空")
    return [result]


def _capture_tab_user_state(pane) -> dict:
    selected = list(hou.selectedNodes())
    pane_current = None
    try:
        pane_current = pane.currentNode() if pane is not None else None
    except Exception:
        pass
    return {
        "pane": pane,
        "pwd": pane.pwd().path() if pane is not None and pane.pwd() is not None else None,
        "selected": [node.path() for node in selected],
        "current": [node.path() for node in selected if node.isCurrent()],
        "pane_current": pane_current.path() if pane_current is not None else None,
    }


def _apply_tab_user_state(state: dict) -> dict:
    pane = state.get("pane")
    pwd_path = state.get("pwd")
    if pane is not None and pwd_path:
        pwd = hou.node(pwd_path)
        if pwd is not None:
            pane.setPwd(pwd)
    hou.clearAllSelected()
    for path in state.get("current", []):
        node = hou.node(path)
        if node is not None:
            node.setCurrent(True)
    pane_current = hou.node(state.get("pane_current")) if state.get("pane_current") else None
    if pane is not None and pane_current is not None:
        pane.setCurrentNode(pane_current)
    for path in state.get("selected", []):
        node = hou.node(path)
        if node is not None:
            node.setSelected(True)
    actual_selected = sorted(node.path() for node in hou.selectedNodes())
    expected_selected = sorted(
        path for path in state.get("selected", []) if hou.node(path) is not None
    )
    return {
        "network_pwd": pane is None or not pwd_path or (
            pane.pwd() is not None and pane.pwd().path() == pwd_path
        ),
        "selection": actual_selected == expected_selected,
    }


def _finish_pending_tab_restore():
    global _PENDING_TAB_USER_STATE, _TAB_RESTORE_POSTED
    state = _PENDING_TAB_USER_STATE
    _PENDING_TAB_USER_STATE = None
    _TAB_RESTORE_POSTED = False
    if state is not None:
        try:
            _apply_tab_user_state(state)
        except Exception:
            pass


def _queue_final_tab_restore():
    """Second event-loop hop: run after Houdini's deferred node-selection post."""
    try:
        hou.ui.postEventCallback(_finish_pending_tab_restore)
    except Exception:
        _finish_pending_tab_restore()


def tab_apply(parent, tool_id: str) -> dict:
    """应用 allowlist 内的非交互 Tab setup recipe，返回全部新增节点。

    这和 ``tab_create`` 的单节点契约不同。当前只允许 H21/H22 的 Karma (Setup)
    与 Karma Material Builder；运行时仍验证真实 tool/context，但通过 SideFX recipe
    adapter 避开通用 shelf UI 的 selection/current/modal 副作用。未知工具明确拒绝。
    """
    parent = dsh_node_access._resolve(parent)
    if not parent.isNetwork():
        raise ValueError(f"{parent.path()} 不是可应用 Tab tool 的网络")
    if not isinstance(tool_id, str) or not tool_id.strip():
        raise ValueError("tool_id 必须是非空字符串")
    tool_id = tool_id.strip()
    tool = hou.shelves.tool(tool_id)
    if tool is None:
        raise ValueError(f"找不到 Tab tool {tool_id!r}")
    context = _tool_context(tool, parent)
    if not context["matches"]:
        raise ValueError(
            f"Tab tool {tool_id!r} 不适用于 {parent.path()}"
            f"（child category={parent.childTypeCategory().name()}, "
            f"tool categories={context['categories']}, op_type={context['op_type']!r}）"
        )
    if tool_id not in _TAB_TOOL_ALLOWLIST:
        raise ValueError(
            f"Tab tool {tool_id!r} 存在但不在 dsh 安全 allowlist；"
            f"当前允许：{sorted(_TAB_TOOL_ALLOWLIST)}"
        )
    global _PENDING_TAB_USER_STATE, _TAB_RESTORE_POSTED
    pane = _network_editor() if hou.isUIAvailable() else None
    if pane is not None:
        if _PENDING_TAB_USER_STATE is None:
            _PENDING_TAB_USER_STATE = _capture_tab_user_state(pane)
        user_state = _PENDING_TAB_USER_STATE
    else:
        user_state = _capture_tab_user_state(None)
    before = {child.sessionId() for child in parent.children()}
    try:
        try:
            if tool_id == "lop_karma_setup":
                recipe_nodes = _apply_karma_setup_recipe(parent)
            elif tool_id == "vop_karmamtlxsubnet":
                recipe_nodes = _apply_karma_material_builder_recipe(parent)
            else:  # guarded by allowlist, defensive for future edits
                raise ValueError(f"Tab tool {tool_id!r} 没有安全 recipe adapter")
        except BaseException:
            # GUI exec has an undo transaction, but headless does not. Clean only
            # children created by this recipe attempt so a partial setup never leaks.
            for child in reversed(parent.children()):
                if child.sessionId() not in before:
                    ids = [int(n.sessionId()) for n in (child, *child.allSubChildren())]
                    try:
                        child.destroy()
                    except Exception:
                        continue  # a live node keeps its registration
                    for identity in ids:
                        dsh_ownership.forget(identity)
            raise
        created = [child for child in parent.children() if child.sessionId() not in before]
        if not created:
            raise RuntimeError(f"Tab tool {tool_id!r} 没有在 {parent.path()} 创建节点")
        for child in created:
            dsh_ownership.register_owned_node(child)
        if not all(node in created for node in recipe_nodes):
            raise RuntimeError(f"Tab tool {tool_id!r} recipe 返回了父网络外节点")
        created.sort(key=lambda node: node.path())
        result = {
            "tool_id": tool_id,
            "label": tool.label() or tool_id,
            "parent": parent.path(),
            "execution": "sidefx_recipe_adapter",
            "created": [
                {
                    "path": node.path(),
                    "type": node.type().name(),
                    "category": node.type().category().name(),
                    "inputs": [source.path() if source is not None else None for source in node.inputs()],
                }
                for node in created
            ],
        }
    finally:
        try:
            immediate_state = _apply_tab_user_state(user_state)
        except Exception:
            immediate_state = {"network_pwd": False, "selection": False}
        if pane is not None and not _TAB_RESTORE_POSTED:
            try:
                # First hop runs after the surrounding exec unwinds; it queues the
                # actual restoration one event turn later than node creation's own
                # deferred selection update.
                hou.ui.postEventCallback(_queue_final_tab_restore)
                _TAB_RESTORE_POSTED = True
            except Exception:
                _finish_pending_tab_restore()

    result["state_restored"] = immediate_state
    result["final_restore"] = "posted" if pane is not None else "synchronous"
    return result


def _tool_has_extra_init(tool) -> bool:
    """判断 shelf tool 是否在 genericTool 之外还有「实质性」初始化。

    只有会真正改场景的操作才算额外初始化（按初始化按钮 / 建配套节点 / 连输入 /
    应用 recipe）；给 ``kwargs`` 设默认值（bbox/parms）或普通赋值不算——那些
    agent 直接设参数即可，不值得为每个节点做昂贵的 pane 导航 + testTool。
    """
    markers = ("pressButton(", "createNode(", "setInput(", "applyTabToolRecipe", ".parm(")
    script = tool.script() or ""
    for line in script.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("import ") or s.startswith("from "):
            continue
        if "genericTool(" in s:
            continue
        if any(m in s for m in markers):
            return True
    return False


def _initialize_created_inputs(node, input_nodes):
    """Reconcile the shipped Sweep initializer with an explicit second input."""
    if node.type().name() == 'sweep::2.0' and len(input_nodes) > 1 and input_nodes[1] is not None:
        shape = node.parm('surfaceshape')
        if shape is None or 'input' not in shape.menuItems():
            raise ValueError('Sweep 2.0 input initializer contract changed; cannot select supplied cross-section')
        shape.set('input')


def _prepare_tab_create(parent, type_name, inputs, parms):
    """Resolve creation and wires completely before calling a shelf or createNode."""
    parent = dsh_node_access._resolve(parent)
    cat = parent.childTypeCategory()
    if cat is None:
        raise ValueError(
            f'tab_create parent={parent.path()!r} is not a network that can create nodes; '
            f'use its existing creation network {parent.parent().path()!r}'
        )
    ctx = dsh_node_types.context_name(cat)
    latest = dsh_node_types.resolve_latest_type(cat, type_name)
    node_type = hou.nodeType(cat, latest)
    if inputs is not None and not isinstance(inputs, list):
        raise ValueError("inputs 必须是 source 节点/path 的 list")
    if parms is not None and (not isinstance(parms, dict) or not parms):
        raise ValueError("parms 必须是非空 {参数名: 值} dict")
    if inputs and cat == hou.objNodeTypeCategory():
        raise ValueError("Object inputs are parenting; create first, then use set_object_parent")
    input_nodes = [None if source is None else dsh_node_access._resolve_in_parent(parent, source) for source in (inputs or [])]
    for source in input_nodes:
        if source is not None and source.parent() != parent:
            raise ValueError(f'different_parent: source={source.path()} parent={source.parent().path()}, destination parent={parent.path()}; use an Object Merge inside the destination SOP network or an explicit subnet input, not cross-network wires')
    if node_type is not None and len(input_nodes) > node_type.maxNumInputs():
        raise ValueError(f"{latest} 最多接受 {node_type.maxNumInputs()} 个输入，收到 {len(input_nodes)}")
    if node_type is not None and not dsh_node_types._visible_node_type(node_type):
        raise ValueError(f"节点类型 {latest!r} 在当前 Houdini 中 hidden/deprecated；请用 search_tab_entries(parent, query) 查真实 Tab entry，setup 工具用 tab_apply(parent, tool_id)")
    if (parent.type().category() == hou.lopNodeTypeCategory()
            and parent.type().name().split("::", 1)[0] == "materiallibrary"):
        raise ValueError(f"Material Library 根层不直接创建 {latest!r}；先用 search_tab_entries(parent, query) 选择 Karma/USD/Preview Builder，再用 tab_apply 执行对应 builder tool")
    return parent, ctx, latest, input_nodes


def tab_create(
    parent: hou.Node,
    type_name: str,
    name: str | None = None,
    inputs: list | None = None,
    parms: dict | None = None,
) -> hou.Node | None:
    """按 Tab Menu 语义创建节点：最新版本 + 完整初始化，返回创建的节点。

    - ``parent``：目标父节点（hou.Node 或 path 字符串，如 '/obj'）。
    - ``type_name``：基名即可（'copytopoints'、'box'、'geo'），内部解析最新版。
    - ``inputs``：可选，创建后按序连到 input 0..n（节点、绝对路径或parent相对路径；None保留空槽；
      连接失败会抛错，不会静默跳过）。
    - ``parms``：可选非空严格参数批次，创建/接线后通过set_parms应用；
      任一字段失败会连同新节点一起清理。复杂模块仍优先build_module。
      Sweep 2.0声明第二输入时在接线后校正surfaceshape=input；build_module显式parms随后可覆盖。
      新建Karma Render Settings默认关闭景深、按HIPNAME分组输出；显式parms可覆盖。
    - 有对应 shelf tool 且其带额外初始化时走 tool；否则回退 createNode(latest)
      （避免对 box/grid 这类纯节点做昂贵的 pane 导航）。
    - 落位：连完 inputs 后自动摆放——有输入时以下游均值为首选；无输入时以父网络
      右侧新列为首选（空网络落原点）。再对兄弟节点、其他Network Box、Sticky Note和
      Network Dot做有界避障；找不到安全位置则创建失败并由调用事务清理。间距由节点
      实际尺寸推导，见``_place_created_node``。
    """
    try:
        parent, ctx, latest, input_nodes = _prepare_tab_create(parent, type_name, inputs, parms)
    except Exception as error:
        raise dsh_errors.CheckpointError(str(error), {'ok': False, 'phase': 'preflight',
            'scene_writes': 0, 'dispatched': False, 'restored': True,
            'scope': 'Tab creation/type/input resolution; no shelf or node creation was dispatched'}) from error

    tool = None
    try:
        tool = hou.shelves.tool(f"{ctx}_{latest}")
    except Exception:
        tool = None

    before = set(parent.children())
    provenance = dsh_ownership.snapshot()
    node: hou.Node | None = None
    try:
        if tool is not None and _tool_has_extra_init(tool):
            node = _run_shelf_tool(tool, parent, latest)
        if node is None:
            node = parent.createNode(latest, node_name=name, exact_type_name=True)
            dsh_ownership.register_owned_node(node)
        elif name is not None:
            node.setName(name, unique_name=True)
        for index, source in enumerate(input_nodes):
            if source is not None:
                node.setInput(index, source)
        # Sweep's shipped shelf selects a built-in tube before our explicit
        # second input is connected. Reconcile this known input-dependent
        # initializer after wiring. build_module applies explicit parms later.
        _initialize_created_inputs(node, input_nodes)
        _initialize_created_render_settings(node)
        if parms is not None:
            dsh_parameter_values.set_parms(node, parms)
        dsh_node_layout._place_created_node(node)
    except BaseException as error:
        # Headless has no undo stack. Never leave a half-created semantic node
        # or provenance after a failed shelf initializer/input/name operation.
        restore_errors = []
        partials = [partial for partial in reversed(parent.children()) if partial not in before]
        for partial in partials:
            try:
                partial.destroy()
            except BaseException as restore_error:
                restore_errors.append(str(restore_error))
        dsh_ownership.restore(provenance)
        raise dsh_errors.CheckpointError(str(error), {'ok': False, 'phase': 'apply_failure',
            'scene_writes': None, 'dispatched': True, 'created_node_count': len(partials),
            'restored': not restore_errors, 'restore_errors': restore_errors,
            'scope': 'new direct children removed; external shelf/Python side effects are not covered'}) from error
    return node
