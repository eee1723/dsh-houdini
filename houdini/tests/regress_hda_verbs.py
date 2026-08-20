"""H21/H22 regression for HDA-authoring verbs.

Run with the target Houdini's hython, for example:

    C:/Program Files/Side Effects Software/Houdini 21.0.440/bin/hython.exe \
        houdini/tests/regress_hda_verbs.py

The test creates one disposable Object subnet asset in the system temp directory.
Instances, installed definitions, and temp files are removed in ``finally``.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile


HERE = os.path.dirname(os.path.abspath(__file__))
LIBS = os.path.abspath(os.path.join(HERE, "..", "python3.11libs"))
sys.path.insert(0, LIBS)

import hou
import dsh_hou_helpers as H


failures = []
temp_dir = tempfile.mkdtemp(prefix="dsh-hda-regress-")
type_name = f"dsh_hda_regress_{os.getpid()}"
hda_file = os.path.join(temp_dir, type_name + ".hda")
probe_names = {"dsh_hda_regress_src", "dsh_hda_replace_src", "dsh_hda_builtin_guard"}


def check(label, fn):
    try:
        fn()
        print(f"PASS  {label}")
    except Exception as e:
        failures.append(label)
        print(f"FAIL  {label}: {type(e).__name__}: {str(e)[:500]}")


def cleanup():
    obj = hou.node("/obj")
    node_type = hou.objNodeTypeCategory().nodeTypes().get(type_name)
    if node_type is not None:
        try:
            instances = list(node_type.instances())
        except Exception:
            instances = []
        for instance in sorted(instances, key=lambda n: n.path().count("/"), reverse=True):
            try:
                instance.destroy()
            except Exception:
                pass
        try:
            definitions = list(node_type.allInstalledDefinitions())
        except Exception:
            definition = node_type.definition()
            definitions = [definition] if definition is not None else []
        for definition in definitions:
            try:
                definition.destroy()
            except Exception:
                pass
    for name in probe_names:
        node = obj.node(name)
        if node is not None:
            try:
                node.destroy()
            except Exception:
                pass
    # Exact mkdtemp result only; never derive this destructive target from $HOME/$HIP.
    if os.path.isdir(temp_dir) and os.path.basename(temp_dir).startswith("dsh-hda-regress-"):
        shutil.rmtree(temp_dir)


try:
    obj = hou.node("/obj")
    source = obj.createNode("subnet", "dsh_hda_regress_src")
    created = H.hda_create(
        source,
        type_name,
        description="DSH HDA Regression",
        hda_file=hda_file,
    )
    asset = hou.node(created["node"])

    def t1():
        assert created["type"] == type_name, created
        assert os.path.isfile(hda_file), hda_file
        assert H.resolve_latest_type("Object", "subnet") == "subnet"
        try:
            H.resolve_latest_type("not-a-category", "subnet")
        except ValueError as e:
            assert "合法类别" in str(e) and "object→obj" in str(e), e
        else:
            raise AssertionError("invalid category did not raise")
    check("1 hda_create + category aliases/actionable error", t1)

    def t2():
        tx = asset.parm("tx")
        tx.setExpression("$FEND", language=hou.exprLanguage.Hscript)
        result = H.set_parm(asset, "tx", 7)
        assert result["value"] == 7.0 and "cleared" in result.get("note", ""), result
        batch = H.set_parms(asset, {"ty": 2, "definitely_missing": 3})
        assert batch["set"]["ty"] == 2.0, batch
        assert "definitely_missing" in batch["failed"], batch
    check("2 set_parm clears animation + set_parms isolates failures", t2)

    spec = [
        {
            "type": "button",
            "name": "run_probe",
            "label": "Run Probe",
            "callback": "hou.phm().run(kwargs)",
            "join_next": True,
        },
        {"type": "separator", "name": "sep_top", "label": ""},
        {
            "type": "folder",
            "name": "main",
            "label": "Main",
            "folder_type": "simple",
            "parms": [
                {"type": "toggle", "name": "manual", "label": "Manual"},
                {
                    "type": "int",
                    "name": "quality",
                    "label": "Quality",
                    "default": 1,
                    "menu": {
                        "items": ["low", "high"],
                        "labels": ["Low", "High"],
                    },
                },
                {
                    "type": "float",
                    "name": "gain",
                    "label": "Gain",
                    "default": 1.5,
                    "min": 0.0,
                    "max": 10.0,
                    "hide_when": "manual == 0",
                },
                {
                    "type": "string",
                    "name": "abc_path",
                    "label": "Alembic",
                    "file": "alembic",
                },
                {
                    "type": "menu",
                    "name": "mode",
                    "label": "Mode",
                    "menu": {"items": ["a", "b"], "labels": ["A", "B"]},
                },
            ],
        },
    ]

    interface = None

    def t3():
        global interface
        interface = H.hda_set_interface(
            asset, spec, keep_std=True, hide_builtin_tabs=True
        )
        assert asset.parm("quality").eval() == 1, interface
        cond = asset.parmTemplateGroup().find("gain").conditionals()
        assert cond[hou.parmCondType.HideWhen] == "{ manual == 0 }", cond
        assert set(interface["hidden_standard_tabs"]) == {"Transform", "Subnet"}, interface
        assert asset.parmTemplateGroup().find("run_probe").joinsWithNext(), interface
    check("3 hda_set_interface full spec + hide_when + invisibletab", t3)

    def t3b():
        definition = asset.type().definition()
        dialog = definition.sections()["DialogScript"].contents()
        without = dialog.replace('hidewhen "{ manual == 0 }"', "", 1)
        assert without != dialog, "test setup could not remove hidewhen"
        definition.addSection("DialogScript", without)
        conds = asset.parmTemplateGroup().find("gain").conditionals()
        assert hou.parmCondType.HideWhen not in conds, conds
        repaired = H._patch_dialog_hide_when(without, "gain", "{ manual == 0 }")
        definition.addSection("DialogScript", repaired)
        conds = asset.parmTemplateGroup().find("gain").conditionals()
        assert conds[hou.parmCondType.HideWhen] == "{ manual == 0 }", conds
    check("3b DialogScript hidewhen fallback repairs a real HDA definition", t3b)

    def t4():
        try:
            H.hda_set_interface(
                asset,
                [{"type": "float", "name": "bad", "menu": {"items": ["a"]}}],
            )
        except ValueError as e:
            assert "FloatParmTemplate" in str(e), e
        else:
            raise AssertionError("float menu was accepted")
        try:
            H.hda_set_interface(
                asset,
                [{"type": "int", "name": "bad_index", "default": 24,
                  "menu": {"items": ["24", "25"]}}],
            )
        except ValueError as e:
            assert "索引" in str(e), e
        else:
            raise AssertionError("out-of-range int menu index was accepted")
    check("4 interface rejects HOM-invalid float menu / token-as-index", t4)

    def t5():
        result = H.hda_set_interface(
            asset,
            [{"type": "toggle", "name": "enabled", "label": "Enabled"}],
            keep_std=True,
        )
        assert asset.parm("enabled") is not None, result
        assert asset.parm("quality") is None, "old managed spec leaked into rebuild"
    check("5 interface uses whole-custom-group rebuild semantics", t5)

    module_v1 = "def run(kwargs):\n    return 'v1'\n"

    def t6():
        set_result = H.hda_set_section(asset, "PythonModule", module_v1)
        assert set_result["chars"] == len(module_v1), set_result
        patch_result = H.hda_patch_section(
            asset, "PythonModule", "return 'v1'", "return 'v2'"
        )
        assert patch_result["replacements"] == 1, patch_result
        assert "return 'v2'" in H.hda_get_section(asset)["code"]
        try:
            H.hda_patch_section(asset, "PythonModule", "missing anchor", "x")
        except ValueError as e:
            assert "实际 0 次" in str(e), e
        else:
            raise AssertionError("missing patch anchor was accepted")
    check("6 HDA section set/get/unique-anchor patch", t6)

    def t7():
        before = H.hda_get_section(asset)["code"]
        try:
            H.hda_set_section(asset, "PythonModule", "def broken(:\n    pass\n")
        except ValueError as e:
            assert "line 1" in str(e), e
        else:
            raise AssertionError("invalid PythonModule was accepted")
        assert H.hda_get_section(asset)["code"] == before, "syntax failure dirtied section"
        info = H.hda_info(asset, max_depth=3)
        assert info["definition"]["library_file"].replace("\\", "/").endswith(
            "/" + type_name + ".hda"
        ), info["definition"]
        assert any(s["name"] == "PythonModule" for s in info["definition"]["sections"])
    check("7 Python syntax preflight is non-mutating + hda_info", t7)

    def t8():
        guard = obj.createNode("subnet", "dsh_hda_builtin_guard")
        guard_path = guard.path()
        try:
            H.hda_create(guard, "subnet", hda_file=os.path.join(temp_dir, "bad.hda"), replace=True)
        except ValueError as e:
            assert "原生" in str(e) and hou.node(guard_path) is not None, e
        else:
            raise AssertionError("built-in node type replacement was accepted")
    check("8 hda_create never replaces/destroys a built-in type", t8)

    def t9():
        replacement = obj.createNode("subnet", "dsh_hda_replace_src")
        old_path = asset.path()
        result = H.hda_create(
            replacement,
            type_name,
            description="DSH HDA Replacement",
            hda_file=hda_file,
            replace=True,
        )
        assert old_path in result["destroyed_instances"], result
        assert hou.node(result["node"]) is not None, result
        assert hou.node(result["node"]).type().description() == "DSH HDA Replacement"
    check("9 explicit same-name replace reports destroyed instances", t9)

    def t10():
        import dsh_bridge

        expected = {
            "set_parms", "hda_create", "hda_info", "hda_get_section",
            "hda_set_section", "hda_patch_section", "hda_set_interface",
        }
        assert expected <= set(dsh_bridge._VERBS), sorted(dsh_bridge._VERBS)
        counts = dsh_bridge._raw_hou_calls(
            "n.createDigitalAsset(); d.setParmTemplateGroup(g); "
            "d.addSection('PythonModule', code); t.setConditional(c, x)"
        )
        assert set(counts) == {
            "createDigitalAsset", "setParmTemplateGroup", "addSection", "setConditional"
        }, counts
    check("10 bridge registers HDA verbs + raw-hou mappings", t10)

finally:
    cleanup()


print()
print("FAILED:" if failures else "ALL PASS", failures if failures else "")
sys.exit(1 if failures else 0)
