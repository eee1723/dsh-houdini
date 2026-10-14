"""Houdini node types. Executed on the Bridge owning thread."""
from __future__ import annotations

import difflib
import re
import hou
import dsh_node_access
import dsh_parameter_templates


_CATEGORIES = {
    "obj": hou.objNodeTypeCategory,
    "sop": hou.sopNodeTypeCategory,
    "dop": hou.dopNodeTypeCategory,
    "chop": hou.chopNodeTypeCategory,
    "cop": hou.copNodeTypeCategory,
    "cop2": hou.cop2NodeTypeCategory,
    "shop": hou.shopNodeTypeCategory,
    "vop": hou.vopNodeTypeCategory,
    "rop": hou.ropNodeTypeCategory,
    "top": hou.topNodeTypeCategory,
    "lop": hou.lopNodeTypeCategory,
}


_CATEGORY_ALIASES = {
    "object": "obj", "objects": "obj", "geometry": "sop", "sops": "sop",
    "driver": "rop", "drivers": "rop", "out": "rop", "dops": "dop",
    "chops": "chop", "vops": "vop", "tops": "top", "lops": "lop",
    "stage": "lop", "material": "shop", "materials": "shop",
    "shopnet": "shop", "copernicus": "cop", "cops": "cop", "img": "cop2",
}


_VERSION_RE = re.compile(r"^(.*)::(\d+(?:\.\d+)*)$")


def _category(category):
    if isinstance(category, hou.NodeTypeCategory):
        return category
    if isinstance(category, str):
        key = category.strip().lower()
        key = _CATEGORY_ALIASES.get(key, key)
        factory = _CATEGORIES.get(key)
        if factory is None:
            valid = ", ".join(sorted(_CATEGORIES))
            alias = ", ".join(f"{a}→{b}" for a, b in sorted(_CATEGORY_ALIASES.items()))
            raise ValueError(
                f"unknown node type category: {category!r}；"
                f"合法类别：{valid}；别名：{alias}"
            )
        return factory()
    raise ValueError(f"unknown node type category: {category!r}（合法：{', '.join(sorted(_CATEGORIES))}）")


def context_name(category) -> str:
    """hou.sopNodeTypeCategory() -> 'sop'（用于构造 shelf tool 名）。"""
    return _category(category).name().lower()


def _version_key(version: str):
    return tuple(int(p) for p in version.split("."))


def resolve_latest_type(category, base: str) -> str:
    """返回某节点族的最新版本全名，如 'copytopoints' -> 'copytopoints::2.0'。

    无版本化条目时返回已注册的 ``base``；有多个 ``::N`` 时取 ``N`` 最大者。
    只以 namespace 形式注册的族（'rigdoctor' -> 'kinefx::rigdoctor'）返回带
    namespace 的全名：`createNode(exact_type_name=True)` 不接受裸别名。
    多 namespace 同名时按名称排序取第一个（确定性兜底）。
    当前类别不存在该族时明确失败，不把未验证的输入伪装成解析结果。
    """
    cat = _category(category)
    names = cat.nodeTypes().keys()
    prefix = base + "::"
    best_key: tuple[int, ...] = ()
    best_name = base if base in names else None
    for name in names:
        if not name.startswith(prefix):
            continue
        m = _VERSION_RE.match(name)
        if not m:
            continue
        key = _version_key(m.group(2))
        if key > best_key:
            best_key = key
            best_name = name
    if best_name is not None:
        return best_name
    ns_key: tuple[int, ...] = ()
    ns_name = None
    for name in sorted(names):
        parts = name.split("::")
        if len(parts) == 2 and parts[1] == base and ns_name is None:
            ns_name = name
        elif len(parts) == 3 and parts[1] == base:
            key = _version_key(parts[2])
            if key > ns_key:
                ns_key = key
                ns_name = name
    if ns_name is not None:
        return ns_name
    raise ValueError(
        f"未知节点类型族：{base!r}；category={cat.name()}；"
        "用 search_tab_menu(category, query) 或 search_tab_entries(parent, query) 查当前版本的真实类型"
    )


def _visible_node_type(node_type) -> bool:
    try:
        if node_type.hidden() or node_type.deprecated():
            return False
    except Exception:
        pass
    return True


def search_tab_menu(category, query: str = "") -> dict:
    """只读：列出某 context 下匹配 ``query`` 的节点族，标注各自最新版本。

    返回 ``{families: [...], latest_of_query: ...}``。用于回答「有没有 cone /
    这个节点叫什么 / 最新版是什么」，而不是让模型去猜类型名。
    """
    cat = _category(category)
    q = query.lower().strip()
    q_key = re.sub(r"[^a-z0-9]+", "", q)

    # 按族键聚合（去版本），族键 = 名字去掉末尾 ::N
    families: dict[str, list[str]] = {}
    labels: dict[str, set[str]] = {}
    for name, node_type in cat.nodeTypes().items():
        m = _VERSION_RE.match(name)
        base = m.group(1) if m else name
        try:
            label = node_type.description() or ""
        except Exception:
            label = ""
        haystacks = (name.lower(), base.lower(), label.lower())
        compact = tuple(re.sub(r"[^a-z0-9]+", "", value) for value in haystacks)
        if q and not any(q in value for value in haystacks) and not (
            q_key and any(q_key in value for value in compact)
        ):
            continue
        families.setdefault(base, []).append(name)
        if label:
            labels.setdefault(base, set()).add(label)

    result = []
    for base in sorted(families):
        latest = resolve_latest_type(cat, base)
        result.append(
            {
                "base": base,
                "latest": latest,
                "versions": sorted(families[base]),
            }
        )

    # 若 query 精确命中某个族名，给出它的最新版
    exact = None
    if q:
        for entry in result:
            base_key = re.sub(r"[^a-z0-9]+", "", entry["base"].lower())
            label_keys = {
                re.sub(r"[^a-z0-9]+", "", label.lower())
                for label in labels.get(entry["base"], set())
            }
            if entry["base"].lower() == q or base_key == q_key or q_key in label_keys:
                exact = entry["latest"]
                break
    return {"families": result, "latest_of_query": exact}


def _node_parameter_cards(typ, counts=None):
    """Expand bounded static multiparm instances without creating scratch nodes."""
    counts = counts or {}
    cards = []
    def expand(name, indices):
        for i in indices:
            name = name.replace('#', str(i), 1)
        return name
    def visit(templates, indices=(), parents=()):
        for tpl in templates:
            name = expand(tpl.name(), indices)
            if isinstance(tpl, hou.FolderParmTemplate):
                if tpl.folderType() in (hou.folderType.MultiparmBlock, hou.folderType.ScrollingMultiparmBlock, hou.folderType.TabbedMultiparmBlock):
                    count = counts.get(name, tpl.defaultValue())
                    if type(count) is not int or not 0 <= count <= 64:
                        raise ValueError(f'{name}: static multiparm count must be an integer in 0..64; use tab_create/list_parms for dynamic counts')
                    cards.append({'name':name,'label':tpl.label(),'type':'Folder','size':1,'components':[name],
                                  'default':tpl.defaultValue(),'multiparm_count':True,'multiparm_parents':list(parents)})
                    start = int(tpl.tags().get('multistartoffset', '1'))
                    for i in range(start, start + count):
                        visit(tpl.parmTemplates(), indices + (i,), parents + (name,))
                else:
                    visit(tpl.parmTemplates(), indices, parents)
            else:
                card = dsh_parameter_templates._parm_template_card(tpl)
                card['name'] = name
                card['components'] = [expand(c, indices) for c in card.get('components', [])]
                if parents:
                    card['multiparm_parents'] = list(parents)
                cards.append(card)
            if len(cards) > 2048:
                raise ValueError('static parameter expansion exceeds 2048 entries; use primitive verbs')
    visit(typ.parmTemplates())
    return cards


def _node_type_suggestions(category, requested):
    """Suggest registered visible types by name/label, without resolving aliases."""
    query = _VERSION_RE.sub(r'\1', requested).lower()
    candidates = []
    for name, typ in category.nodeTypes().items():
        if not _visible_node_type(typ):
            continue
        family = _VERSION_RE.sub(r'\1', name).lower()
        label = (typ.description() or name).lower()
        score = max(difflib.SequenceMatcher(None, query, family).ratio(),
                    difflib.SequenceMatcher(None, query, label).ratio())
        if query == family or query in family or query in label:
            score = max(score, 0.9)
        if score >= 0.85:
            version = _VERSION_RE.match(name)
            candidates.append((score, _version_key(version.group(2)) if version else (),
                               family, name, typ.description() or name))
    # One visible version per family, keeping the newest registered candidate.
    result, seen = [], set()
    for _, _, family, name, label in sorted(candidates, reverse=True):
        if family not in seen:
            result.append({'type': name, 'label': label})
            seen.add(family)
        if len(result) == 6:
            break
    return result


def node_info(parent, type_name: str, parm_filter: str = "", limit: int = 24) -> dict:
    """Read a static version-resolved node card in an existing network (no scratch nodes).

    parm_filter is a literal case-insensitive substring, NOT regex or glob.
    An empty match is not an empty type: retry with parm_filter=''.
    Static templates include menu tokens/labels/defaults, button-strip storage
    semantics and parameter-local conditionals (not evaluated UI enablement).
    Dynamic menus require
    ``list_parms`` on an actual node; this card does not run shelf scripts.
    operation_parameters additionally carries unfiltered critical settings and
    operation_card.decisions; retain these even when filtering other parameters.
    ``parent`` supplies an existing creation network, not a guessed category.
    requested_type preserves your input; type is the exact resolved node type.
    Unknown types report nearby registered visible types; no alias is created.
    SOP example: ``node_info(existing_geo, "box")``. With no SOP container,
    first create one via ``tab_create("/obj", "geo", name=...)`` in exec;
    querying ``node_info("/obj", "box")`` cannot discover an SOP Box.
    """
    if isinstance(parent, str) and not parent.startswith('/'):
        raise ValueError('node_info(parent,type): parent must be an existing absolute network path, not a category; create the geometry container with tab_create("/obj","geo",name) first')
    p = dsh_node_access._resolve(parent)
    if not p.isNetwork() or p.childTypeCategory() is None:
        raise ValueError(f'node_info parent={p.path()!r} is not a network that can create nodes; use its existing creation network {p.parent().path()!r}')
    if not isinstance(type_name, str) or not type_name.strip():
        raise ValueError('type_name must be a non-empty registered type name; e.g. node_info(existing_geo, "box")')
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 256:
        raise ValueError("limit 必须在 1..256")
    cat = p.childTypeCategory()
    try:
        latest = resolve_latest_type(cat, type_name)
    except ValueError as error:
        candidates = _node_type_suggestions(cat, type_name)
        raise ValueError(
            f'Unknown node type {type_name!r}; existing parent={p.path()!r} creates {cat.name()} nodes. '
            f'Registered visible name/label suggestions (not replacements): {candidates}. '
            f'Use search_tab_entries({p.path()!r}, query="part of a type name or label") to discover this context. '
            'For SOP nodes the parent must be an existing geometry network, not /obj.'
        ) from error
    typ = hou.nodeType(cat, latest)
    if typ is None:
        raise ValueError(f"未知节点类型：{type_name}; parent={p.path()} creates {cat.name()} nodes. For SOP types use an existing geometry container, not /obj; search_tab_entries(parent,query) lists valid types.")
    if not isinstance(parm_filter, str):
        raise ValueError('parm_filter must be a literal substring string')
    all_parameters = _node_parameter_cards(typ)
    from dsh_operation_cards import operation_card, operation_metadata, operation_parameters
    operation = operation_card(latest)
    important, missing = operation_parameters(operation, all_parameters) if operation else ([], [])
    parameters = [c for c in all_parameters if not parm_filter or parm_filter.lower() in (c['name'] + ' ' + c['label']).lower()]
    return {"parent": p.path(), "requested_type": type_name, "type": latest, "category": cat.name(),
            **({'usage_notes': operation['notes'], 'operation_card': operation_metadata(operation),
                'operation_parameters': important, 'operation_parameters_missing': missing,
                'operation_parameter_scope': 'Unfiltered critical static templates; defaults are not Shelf-created values. Missing fields require runtime inspection, not guessed replacements.'} if operation else {}),
            "version": hou.applicationVersionString(), "description": typ.description(),
            "visible": _visible_node_type(typ), "min_inputs": typ.minNumInputs(),
            "max_inputs": typ.maxNumInputs(), "max_outputs": typ.maxNumOutputs(),
            "parameters": parameters[:limit], "parameter_count": len(parameters),
            "total_parameter_count": len(all_parameters), "filter_mode": "literal_substring",
            "filter": parm_filter,
            **({'next_action': "No literal matches; retry node_info with parm_filter='' before creating a probe. Pipe/glob/regex syntax is not interpreted."} if parm_filter and not parameters else {}),
            "truncated": len(parameters) > limit, "help_url": typ.defaultHelpUrl(),
            "note": "Static type contract; dynamic menus and shelf initialization may add parameters."}
