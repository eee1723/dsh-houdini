"""Houdini parameter templates. Executed on the Bridge owning thread."""
from __future__ import annotations

import math
import re
import hou
import dsh_node_access


def _menu_kind(tpl):
    """Native button strips use indices or bit fields, not icon-name values."""
    if isinstance(tpl, hou.MenuParmTemplate) and (tpl.isButtonStrip() or tpl.isIconStrip()):
        return 'toggle_strip' if tpl.menuType() == hou.menuType.StringToggle else 'exclusive_strip'
    return None


def _menu_entries(tpl, tokens, labels):
    """One setting-value contract for static cards and live setters."""
    numeric = tpl.type() == hou.parmTemplateType.Int
    try: use_tokens = bool(tpl.menuUseToken())
    except (AttributeError, hou.Error): use_tokens = False
    kind = _menu_kind(tpl)
    rows = []
    for i, token in enumerate(tokens):
        value = (1 << i) if kind == 'toggle_strip' else i if kind == 'exclusive_strip' or numeric else token
        if numeric and use_tokens and kind is None:
            try: value = int(token)
            except ValueError:
                raise ValueError('integer token-valued menu contains noninteger tokens; use an explicit expression')
        rows.append({'index':i, 'token':token, 'label':labels[i] if i < len(labels) else token, 'set_value':value})
    return rows


def _parm_template_card(tpl) -> dict:
    entry = {"name": tpl.name(), "label": tpl.label(), "type": tpl.type().name(),
             "size": tpl.numComponents()}
    if tpl.numComponents() == 1:
        entry["components"] = [tpl.name()]
    else:
        scheme = tpl.namingScheme().name()
        entry['naming_scheme'] = scheme
        suffixes = {"XYZW": "xyzw", "RGBA": "rgba", "UVW": "uvw", "XYWH": "xywh",
                    "MinMax": ("min", "max"), "MaxMin": ("max", "min"),
                    "StartEnd": ("start", "end")}.get(scheme)
        if suffixes:
            entry["components"] = [tpl.name() + s for s in suffixes[:tpl.numComponents()]]
        elif scheme == "BeginEnd":
            # Built-in H21/H22 tuples use prefixes (beginangle/endangle),
            # unlike the suffix-based StartEnd scheme. No scratch node needed.
            entry["components"] = [s + tpl.name() for s in ("begin", "end")[:tpl.numComponents()]]
        elif scheme in ("Base0", "Base1"):
            start = 0 if scheme == "Base0" else 1
            entry["components"] = [tpl.name() + str(i + start) for i in range(tpl.numComponents())]
    for field, method in (("help", "help"), ("default", "defaultValue")):
        try:
            value = getattr(tpl, method)()
            if value is not None:
                entry[field] = dsh_node_access._val(value)
        except (AttributeError, hou.Error):
            pass
    try:
        tokens, labels = tpl.menuItems(), tpl.menuLabels()
        if tokens:
            entry["menu"] = _menu_entries(tpl, tokens, labels)
            kind = _menu_kind(tpl)
            if kind:
                entry['menu_kind'] = kind
            entry['menu_setting'] = ('integer_bitmask; 0 clears all; combine set_value bits; a token selects only that bit, not a toggle'
                                     if kind == 'toggle_strip' else
                                     'token_or_set_value; explicit expression object for numeric menu expressions')
        elif tpl.itemGeneratorScript():
            entry["menu_dynamic"] = True
    except (AttributeError, hou.Error):
        pass
    conditions = {_enum_name(k): v for k, v in tpl.conditionals().items()}
    if conditions:
        entry['conditionals'] = conditions
    return entry


_HDA_MANAGED_TAG = "dsh_houdini::managed"


_PARM_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _enum_name(value) -> str:
    try:
        return value.name()
    except Exception:
        return str(value).split(".")[-1]


def _template_info(template, depth: int, max_depth: int) -> dict:
    entry = {
        "name": template.name(),
        "label": template.label(),
        "type": _enum_name(template.type()),
    }
    for key, getter in (
        ("hidden", "isHidden"),
        ("join_next", "joinsWithNext"),
        ("hide_label", "isLabelHidden"),
        ("help", "help"),
        ("default", "defaultValue"),
        ("menu_items", "menuItems"),
        ("menu_labels", "menuLabels"),
        ("column_labels", "columnLabels"),
        ("components", "numComponents"),
        ("min", "minValue"),
        ("max", "maxValue"),
        ("min_strict", "minIsStrict"),
        ("max_strict", "maxIsStrict"),
        ("callback", "scriptCallback"),
        ("menu_generator", "itemGeneratorScript"),
        ("default_expression", "defaultExpression"),
    ):
        try:
            value = getattr(template, getter)()
        except Exception:
            continue
        if value not in (None, "", (), [], {}):
            entry[key] = dsh_node_access._val(value)
    try:
        conditions = {
            _enum_name(k): v for k, v in template.conditionals().items()
        }
        if conditions:
            entry["conditionals"] = conditions
    except Exception:
        pass
    try:
        tags = template.tags()
        if tags:
            entry["tags"] = dict(tags)
    except Exception:
        pass
    for key, getter in (("callback_language", "scriptCallbackLanguage"),
                        ("menu_generator_language", "itemGeneratorScriptLanguage"),
                        ("menu_type", "menuType"), ("string_type", "stringType"),
                        ("file_type", "fileType"), ("look", "look"), ("naming_scheme", "namingScheme")):
        try:
            entry[key] = _enum_name(getattr(template, getter)())
        except (AttributeError, hou.Error):
            pass
    if isinstance(template, hou.FolderParmTemplate):
        entry["folder_type"] = _enum_name(template.folderType())
        entry['tab_conditionals'] = {_enum_name(k): v for k, v in template.tabConditionals().items()}
        entry['ends_tab_group'] = template.endsTabGroup()
        children = list(template.parmTemplates())
        if depth < max_depth:
            entry["parms"] = [
                _template_info(child, depth + 1, max_depth) for child in children
            ]
        elif children:
            entry["parms_omitted"] = len(children)
    if isinstance(template, hou.RampParmTemplate):
        entry['ramp_type'] = _enum_name(template.parmType())
        entry['show_controls'] = template.showsControls()
        entry['basis'] = _enum_name(template.defaultBasis())
    return entry


def _spec_name(item: dict, path: str, multiparm_depth: int = 0) -> str:
    name = item.get("name")
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_#]*', name) or name.count('#') != multiparm_depth:
        raise ValueError(
            f"{path}.name requires a stable identifier and {multiparm_depth} multiparm # placeholders, received {name!r}"
        )
    return name


def _menu_data(item: dict, path: str) -> tuple[list[str], list[str]]:
    menu = item.get("menu")
    if not isinstance(menu, dict):
        raise ValueError(f"{path}.menu 必须是 {{items:[...], labels:[...]}}")
    items = menu.get("items")
    labels = menu.get("labels", items)
    if not isinstance(items, (list, tuple)) or not items:
        raise ValueError(f"{path}.menu.items 必须是非空 list")
    if not isinstance(labels, (list, tuple)) or len(labels) != len(items):
        raise ValueError(f"{path}.menu.labels 必须与 items 等长")
    return [str(x) for x in items], [str(x) for x in labels]


def _normalize_hide_when(value, path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}.hide_when 必须是非空字符串")
    value = value.strip()
    if not (value.startswith("{") and value.endswith("}")):
        value = "{ " + value + " }"
    return value


def _apply_template_common(template, item: dict, path: str, conditions: dict) -> None:
    help_text = item.get("help")
    if help_text is not None:
        template.setHelp(str(help_text))
    if item.get("join_next"):
        template.setJoinWithNext(True)
    hide_when = _normalize_hide_when(item.get("hide_when"), path)
    if hide_when is not None:
        template.setConditional(hou.parmCondType.HideWhen, hide_when)
        conditions[template.name()] = hide_when
    disable_when = _normalize_hide_when(item.get('disable_when'), path)
    if disable_when:
        template.setConditional(hou.parmCondType.DisableWhen, disable_when)
    if 'hidden' in item:
        template.hide(bool(item['hidden']))
    if 'hide_label' in item:
        template.setLabelHidden(bool(item['hide_label']))
    tags = dict(template.tags())
    user_tags = item.get("tags", {})
    if not isinstance(user_tags, dict):
        raise ValueError(f"{path}.tags 必须是 dict")
    tags.update({str(k): str(v) for k, v in user_tags.items()})
    tags[_HDA_MANAGED_TAG] = "1"
    template.setTags(tags)


def _build_interface_template(
    item: dict,
    path: str,
    names: set,
    conditions: dict,
    multiparm_depth: int = 0,
):
    if not isinstance(item, dict):
        raise ValueError(f"{path} 必须是 dict")
    kind = str(item.get("type", "")).strip().lower()
    if kind not in {
        "folder", "separator", "toggle", "int", "float", "string", "button", "menu", "ramp", "label"
    }:
        raise ValueError(
            f"{path}.type 不支持 {kind!r}；可用 folder/separator/toggle/int/float/"
            "string/button/menu"
        )
    name = _spec_name(item, path, multiparm_depth)
    if name in names:
        raise ValueError(f"参数/文件夹名 {name!r} 重复（Houdini 参数名全局唯一）")
    names.add(name)
    label = str(item.get("label", name))

    if kind == "folder":
        folder_type = str(item.get("folder_type", "simple")).strip().lower()
        folder_types = {
            "simple": hou.folderType.Simple,
            "tabs": hou.folderType.Tabs,
            "collapsible": hou.folderType.Collapsible,
            "multiparm_list": hou.folderType.MultiparmBlock,
            "multiparm_tabs": hou.folderType.TabbedMultiparmBlock,
            "multiparm_scroll": hou.folderType.ScrollingMultiparmBlock,
        }
        if folder_type not in folder_types:
            raise ValueError(f"{path}.folder_type 只能是 {sorted(folder_types)}")
        children = item.get("parms", [])
        if not isinstance(children, (list, tuple)):
            raise ValueError(f"{path}.parms 必须是 list")
        template = hou.FolderParmTemplate(
            name, label, folder_type=folder_types[folder_type], ends_tab_group=bool(item.get('ends_tab_group', False))
        )
        is_multi = folder_type.startswith('multiparm_')
        if is_multi:
            count = item.get('default', 0)
            if type(count) is not int or not 0 <= count <= 64:
                raise ValueError('multiparm default count must be 0..64')
            template.setDefaultValue(count)
        for field, condition in [('tab_hide_when', hou.parmCondType.HideWhen), ('tab_disable_when', hou.parmCondType.DisableWhen)]:
            if item.get(field):
                if is_multi:
                    raise ValueError('tab conditionals are unsupported on multiparm folders')
                template.setTabConditional(condition, _normalize_hide_when(item[field], path))
        for index, child in enumerate(children):
            template.addParmTemplate(
                _build_interface_template(
                    child, f"{path}.parms[{index}]", names, conditions, multiparm_depth + int(is_multi)
                )
            )
    elif kind == "separator":
        template = hou.SeparatorParmTemplate(name, label)
    elif kind == 'label':
        template = hou.LabelParmTemplate(name, label, column_labels=(label,))
    elif kind == 'ramp':
        ramp_type = item.get('ramp_type', 'float')
        if ramp_type not in ('float', 'color'):
            raise ValueError('ramp_type must be float/color')
        basis = item.get('basis', 'linear')
        bases = {'linear': hou.rampBasis.Linear, 'constant': hou.rampBasis.Constant,
                 'catmullrom': hou.rampBasis.CatmullRom, 'bspline': hou.rampBasis.BSpline}
        if basis not in bases:
            raise ValueError('unsupported ramp basis')
        points = item.get('points', 2)
        if type(points) is not int or not 2 <= points <= 16:
            raise ValueError('ramp points must be 2..16')
        template = hou.RampParmTemplate(name, label,
            hou.rampParmType.Float if ramp_type == 'float' else hou.rampParmType.Color,
            default_value=points, default_basis=bases[basis], show_controls=bool(item.get('show_controls', False)))
    elif kind == "toggle":
        template = hou.ToggleParmTemplate(
            name, label, default_value=bool(item.get("default", False))
        )
    elif kind in ("int", "float"):
        components = item.get('components', 1)
        if type(components) is not int or not 1 <= components <= 4:
            raise ValueError('numeric components must be 1..4')
        default = item.get("default", 0 if components == 1 else [0]*components)
        if components > 1 and (not isinstance(default, (list, tuple)) or len(default) != components):
            raise ValueError('tuple default must match components')
        values = [default] if components == 1 else default
        if any(type(v) not in (int, float) or not math.isfinite(v) or kind == 'int' and type(v) is not int for v in values):
            raise ValueError('numeric defaults must be finite and match numeric type')
        minimum = item.get("min", 0)
        maximum = item.get("max", 10)
        if kind == "float" and "menu" in item:
            raise ValueError(
                f"{path}: Houdini FloatParmTemplate 不支持菜单；"
                "需要菜单请用 int+menu（值为索引）或 type=menu；string只存文本，不创建菜单"
            )
        kwargs = {
            "default_value": tuple(float(v) for v in values) if kind == "float" else tuple(values),
            "min": float(minimum) if kind == "float" else int(minimum),
            "max": float(maximum) if kind == "float" else int(maximum),
            "min_is_strict": bool(item.get("min_strict", False)),
            "max_is_strict": bool(item.get("max_strict", False)),
        }
        if kind == "int" and "menu" in item:
            if components != 1:
                raise ValueError('menus require scalar components')
            items, labels = _menu_data(item, path)
            index = int(default)
            if not 0 <= index < len(items):
                raise ValueError(
                    f"{path}.default={index} 超出菜单索引 0..{len(items) - 1}；"
                    "Houdini 的 Int 菜单存索引，不存 item token"
                )
            kwargs.update(menu_items=items, menu_labels=labels)
        cls = hou.FloatParmTemplate if kind == "float" else hou.IntParmTemplate
        template = cls(name, label, components, **kwargs)
        look = item.get('look', 'regular')
        if look not in ('regular', 'vector', 'color') or look == 'color' and components not in (3, 4):
            raise ValueError('numeric look must be regular/vector/color (color needs 3/4 components)')
        template.setLook({'regular': hou.parmLook.Regular, 'vector': hou.parmLook.Vector, 'color': hou.parmLook.ColorSquare}[look])
        if look == 'color':
            template.setNamingScheme(hou.parmNamingScheme.RGBA)
    elif kind == "string":
        default = str(item.get("default", ""))
        file_kind = item.get("file")
        string_kind = item.get('string_type', 'regular')
        if string_kind not in ('regular', 'node'):
            raise ValueError(f'{path}.string_type must be regular/node')
        if string_kind == 'node' and file_kind is not None:
            raise ValueError(f'{path}: node reference and file selector are mutually exclusive')
        kwargs = {"default_value": (default,)}
        if string_kind == 'node':
            kwargs['string_type'] = hou.stringParmType.NodeReference
        if file_kind is not None:
            file_key = str(file_kind).strip().lower()
            file_types = {
                "dir": hou.fileType.Directory,
                "geo": hou.fileType.Geometry,
                "alembic": hou.fileType.Geometry,
                "image": hou.fileType.Image,
                "any": hou.fileType.Any,
            }
            if file_key not in file_types:
                raise ValueError(f"{path}.file 只能是 {sorted(file_types)}")
            kwargs.update(
                string_type=hou.stringParmType.FileReference,
                file_type=file_types[file_key],
            )
        template = hou.StringParmTemplate(name, label, 1, **kwargs)
    elif kind == "button":
        callback = item.get("callback")
        if not isinstance(callback, str) or not callback.strip():
            raise ValueError(f"{path}.callback 必须是非空 Python 回调字符串")
        template = hou.ButtonParmTemplate(name, label)
        template.setScriptCallback(callback)
        template.setScriptCallbackLanguage(hou.scriptLanguage.Python)
    else:  # menu
        items, labels = _menu_data(item, path)
        default = int(item.get("default", 0))
        if not 0 <= default < len(items):
            raise ValueError(f"{path}.default 必须是菜单索引 0..{len(items) - 1}")
        template = hou.MenuParmTemplate(
            name, label, items, menu_labels=labels, default_value=default
        )

    _apply_template_common(template, item, path, conditions)
    return template


def _template_has_managed(template) -> bool:
    try:
        if template.tags().get(_HDA_MANAGED_TAG) == "1":
            return True
    except Exception:
        pass
    if isinstance(template, hou.FolderParmTemplate):
        return any(_template_has_managed(c) for c in template.parmTemplates())
    return False


def _standard_interface_entries(node: hou.Node) -> list:
    """取 HDA 源 subnet 的标准界面；找不到基型时保留未受本动词管理的旧条目。"""
    source_name = _enum_name(node.type().source()).lower()
    if source_name == "subnet":
        base_type = node.type().category().nodeTypes().get("subnet")
        if base_type is not None and base_type is not node.type():
            return [entry.clone() for entry in base_type.parmTemplateGroup().entries()]
    return [
        entry.clone() for entry in node.parmTemplateGroup().entries()
        if not _template_has_managed(entry)
    ]


def _all_template_names(templates) -> set:
    names = set()
    for template in templates:
        names.add(template.name())
        if isinstance(template, hou.FolderParmTemplate):
            names.update(_all_template_names(template.parmTemplates()))
    return names


def _balanced_block_end(text: str, start: int) -> int:
    brace = text.find("{", start)
    if brace < 0:
        raise ValueError("DialogScript parm 块缺少 '{'")
    depth = 0
    quote = None
    escaped = False
    for index in range(brace, len(text)):
        ch = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    raise ValueError("DialogScript parm 块大括号不平衡")


def _patch_dialog_hide_when(dialog: str, name: str, condition: str) -> str:
    block_re = re.compile(r"(?m)^[ \t]*parm[ \t]*\{[ \t]*$")
    name_re = re.compile(r"(?m)^[ \t]*name[ \t]+\"" + re.escape(name) + r"\"[ \t]*$")
    for match in block_re.finditer(dialog):
        end = _balanced_block_end(dialog, match.start())
        block = dialog[match.start():end]
        name_match = name_re.search(block)
        if name_match is None:
            continue
        escaped = condition.replace("\\", "\\\\").replace('"', '\\"')
        hide_re = re.compile(r"(?m)^(?P<indent>[ \t]*)hidewhen[ \t]+\".*\"[ \t]*$")
        existing = hide_re.search(block)
        if existing is not None:
            replacement = existing.group("indent") + f'hidewhen "{escaped}"'
            block = block[:existing.start()] + replacement + block[existing.end():]
        else:
            indent = re.match(r"[ \t]*", block[name_match.start():]).group(0)
            close_line = block.rfind("\n", 0, len(block) - 1) + 1
            newline = "\r\n" if "\r\n" in block else "\n"
            insertion = indent + f'hidewhen "{escaped}"' + newline
            block = block[:close_line] + insertion + block[close_line:]
        return dialog[:match.start()] + block + dialog[end:]
    raise ValueError(f"DialogScript 中找不到参数 {name!r} 的 parm 块")


def _validate_section_code(section: str, code: str) -> None:
    if not isinstance(code, str):
        raise ValueError("code 必须是字符串")
    if section.lower().endswith("pythonmodule"):
        try:
            compile(code, f"<HDA:{section}>", "exec")
        except SyntaxError as e:
            source = (e.text or "").strip()
            where = f"line {e.lineno}" + (f", column {e.offset}" if e.offset else "")
            raise ValueError(
                f"{section} Python 语法错误（{where}）：{e.msg}"
                + (f"；{source}" if source else "")
            ) from e
