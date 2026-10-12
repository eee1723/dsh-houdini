"""Houdini hda sections. Executed on the Bridge owning thread."""
from __future__ import annotations

import dsh_parameter_templates

import hashlib
import hou
import dsh_node_access
import dsh_ownership


def _section_contents(definition: hou.HDADefinition, section: str) -> str:
    if not isinstance(section, str) or not section.strip():
        raise ValueError("section 必须是非空字符串")
    section = section.strip()
    sections = definition.sections()
    if section not in sections:
        raise ValueError(
            f"HDA 没有 section {section!r}；现有：{sorted(sections)}"
        )
    return sections[section].contents()


def hda_get_section(node, section: str = "PythonModule") -> dict:
    """读取 HDA section 全文；不存在时列出现有 section 名。"""
    n, definition = dsh_node_access._hda_definition(node)
    code = _section_contents(definition, section)
    return {
        "node": n.path(),
        "section": section,
        "code": code,
        "chars": len(code),
        "sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
    }




def _write_hda_section(definition: hou.HDADefinition, section: str, code: str) -> dict:
    dsh_parameter_templates._validate_section_code(section, code)
    before = None
    existing = definition.sections().get(section)
    if existing is not None:
        before = existing.contents()
    definition.addSection(section, code)
    actual = _section_contents(definition, section)
    if actual != code:
        raise RuntimeError(
            f"HDA section {section!r} 写后读回不一致："
            f"expected {len(code)} chars, got {len(actual)}"
        )
    return {
        "section": section,
        "changed": before != code,
        "chars": len(code),
        "lines": code.count("\n") + (1 if code else 0),
        "sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
    }


def hda_set_section(node, section: str, code: str,
                    allow_foreign: str | None = None) -> dict:
    """Shared-definition/library authorization and recovery; PythonModule compiles first."""
    n, definition = dsh_node_access._hda_definition(node)
    dsh_ownership.require_owned(n, "hda_set_section", allow_foreign)
    if not isinstance(section, str) or not section.strip():
        raise ValueError("section 必须是非空字符串")
    section = section.strip()
    dsh_parameter_templates._validate_section_code(section, code)
    from dsh_hda_interfaces import definition_write_guard
    with definition_write_guard(n, 'hda_set_section', allow_foreign):
        out = _write_hda_section(definition, section, code)
    out["node"] = n.path()
    return out


def hda_patch_section(
    node,
    section: str,
    old: str,
    new: str,
    count: int = 1,
    allow_foreign: str | None = None,
) -> dict:
    """按唯一锚点局部替换 HDA section，拒绝缺失或歧义锚点。"""
    n, definition = dsh_node_access._hda_definition(node)
    dsh_ownership.require_owned(n, "hda_patch_section", allow_foreign)
    if not isinstance(old, str) or not old:
        raise ValueError("old 必须是非空字符串（空锚点会产生歧义）")
    if not isinstance(new, str):
        raise ValueError("new 必须是字符串")
    if not isinstance(count, int) or count <= 0:
        raise ValueError("count 必须是正整数")
    source = _section_contents(definition, section)
    actual_count = source.count(old)
    if actual_count != count:
        raise ValueError(
            f"section {section!r} 中锚点期望出现 {count} 次，实际 {actual_count} 次；"
            "0 次说明锚点过期，多于期望说明锚点不唯一，请扩大 old 上下文"
        )
    patched = source.replace(old, new, count)
    dsh_parameter_templates._validate_section_code(section, patched)
    from dsh_hda_interfaces import definition_write_guard
    with definition_write_guard(n, 'hda_patch_section', allow_foreign):
        out = _write_hda_section(definition, section, patched)
    out.update({"node": n.path(), "replacements": count})
    return out
