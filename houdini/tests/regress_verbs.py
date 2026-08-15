"""H21 regression for the verb layer fixes.

Run:  /d/houdini/bin/hython.exe houdini/tests/regress_verbs.py
（等价：任意 H21 hython；脚本自行把 python3.11libs 加进 sys.path）
退出码非零即有失败项。场景内的 probe 节点在结尾统一清理。
"""
import sys

sys.path.insert(0, r"E:/dsh-houdini/houdini/python3.11libs")

import hou
import dsh_hou_helpers as H

failures = []


def check(label, fn):
    try:
        fn()
        print(f"PASS  {label}")
    except Exception as e:
        failures.append(label)
        print(f"FAIL  {label}: {type(e).__name__}: {str(e)[:200]}")


geo = hou.node("/obj").createNode("geo", "regr_geo")
box = geo.createNode("box", "b")


# 1) tab_create inputs: path string must actually connect
def t1():
    null = H.tab_create(geo, "null", name="n1", inputs=[box.path()])
    assert null.inputs() and null.inputs()[0] == box, f"inputs not connected: {null.inputs()}"
check("1 tab_create inputs=[path] connects", t1)


# 2) tab_create inputs: bad path must RAISE, not silently skip
def t2():
    try:
        H.tab_create(geo, "null", name="n2", inputs=["/obj/nonexistent"])
    except ValueError:
        return
    raise AssertionError("no error for bad input path")
check("2 tab_create bad input path raises", t2)


# 3) graph with sparse inputs (merge input 2 connected)
def t3():
    merge = geo.createNode("merge", "m")
    merge.setInput(2, box)
    g = H.graph(merge, direction="up")
    assert any("b" in p for p in g["inputs"]), g
check("3 graph sparse inputs no crash", t3)


# 4) connect honesty: unavailable index -> note + actual input
def t4():
    fresh = geo.createNode("null", "n4")  # 1 个空闲输入口
    r = H.connect(box, fresh, index=5)
    assert r["node"] == fresh.path() and r.get("note"), r
    assert r["input"] == 0, r
check("4 connect fallback reports actual input", t4)


# 4b) connect with no free input -> clear error, not raw InvalidInput
def t4b():
    null = hou.node("/obj/regr_geo/n1")  # 唯一输入已被 box 占用
    try:
        H.connect(box, null, index=5)
    except ValueError as e:
        assert "输入口" in str(e), e
        return
    raise AssertionError("no error when no input available")
check("4b connect no-free-input raises clear error", t4b)


# 5) connect normal path returns requested index
def t5():
    merge = hou.node("/obj/regr_geo/m")
    null2 = geo.createNode("null", "n3")
    r = H.connect(null2, merge, index=1)
    assert r == {"node": merge.path(), "input": 1}, r
check("5 connect exact index", t5)


# 6) set_parm expression routing on numeric parm
def t6():
    r = H.set_parm(box, "sizex", "2*3")
    assert r["value"] == 6.0 and r.get("expression") == "2*3", r
check("6 set_parm str -> expression", t6)


# 7) set_parm ch() reference + read_parms referenced_parm / referenced_by
def t7():
    H.set_parm(box, "sizey", 'ch("sizex")')
    rp = {e["name"]: e for e in H.read_parms(box)}
    assert rp["sizey"].get("referenced_parm", "").endswith("/sizex"), rp["sizey"]
    assert rp["sizex"].get("referenced_by") is True, rp["sizex"]
check("7 read_parms reference directions", t7)


# 8) set_parm plain value + tuple + similar names still work
def t8():
    r = H.set_parm(box, "sizez", 4)
    assert r["value"] == 4.0, r
    r2 = H.set_parm(box, "t", [1, 2, 3])  # 't' 分量无表达式，不受 t6/t7 影响
    assert list(r2["value"])[:3] == [1.0, 2.0, 3.0], r2
    try:
        H.set_parm(box, "numpoints", 5)
    except ValueError as e:
        assert "相似" in str(e) or "Similar" in str(e)
    else:
        raise AssertionError("no error for bad parm name")
check("8 set_parm scalar/tuple/suggestions", t8)


# 9) delete_node reports orphaned refs
def t9():
    victim = geo.createNode("box", "victim")
    watcher = geo.createNode("box", "watcher")
    H.set_parm(watcher, "sizex", f'ch("{victim.path()}/sizey")')
    r = H.delete_node(victim)
    assert any("watcher" in p for p in r.get("orphaned_parm_refs", [])), r
check("9 delete_node orphaned_parm_refs", t9)


# 10) describe/cook_node still sane
def t10():
    d = H.describe(box)
    assert d["type"].startswith("box") and "help" in d, d
    c = H.cook_node(box)
    assert c["errors"] == [], c
check("10 describe/cook_node", t10)


# 11) H21 embedded webview dependency
def t11():
    from PySide6 import QtWebEngineWidgets  # noqa: F401
check("11 PySide6.QtWebEngineWidgets present on H21", t11)


geo.destroy()
print()
print("FAILED:" if failures else "ALL PASS", failures if failures else "")
sys.exit(1 if failures else 0)
