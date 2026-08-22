"""H21 regression for the verb layer fixes.

Run:  /d/houdini/bin/hython.exe houdini/tests/regress_verbs.py
（等价：任意 H21 hython；脚本自行把 python3.11libs 加进 sys.path）
退出码非零即有失败项。场景内的 probe 节点在结尾统一清理。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIBS = os.path.abspath(os.path.join(HERE, "..", "python3.11libs"))
sys.path.insert(0, LIBS)

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


# 9b) render_view service nodes are persistent and cannot enter the fatal
# OpenGL teardown path through the generic delete verb.
def t9b():
    owned = geo.createNode("null", "owned_render_service")
    owned.setUserData(H._RENDER_OWNER_KEY, H._RENDER_OWNER_VALUE)
    try:
        H.delete_node(owned)
    except ValueError as e:
        assert "persistent dsh-houdini render service" in str(e), e
        assert hou.node(owned.path()) is not None
    else:
        raise AssertionError("delete_node accepted persistent render service node")
    finally:
        if owned is not None:
            owned.destroy()
check("9b delete_node guards persistent render service", t9b)


# 9c) the service Network Box is named, labelled, and contains every item.
def t9c():
    first = geo.createNode("null", "service_box_first")
    second = geo.createNode("null", "service_box_second")
    box = None
    try:
        box = H._render_service_box(geo, "__dsh_render_service_test", [first, second])
        assert box.comment() == H._RENDER_BOX_COMMENT, box.comment()
        members = set(box.items(recurse=False))
        assert first in members and second in members, members
        # Reuse must return the same box rather than making numbered copies.
        again = H._render_service_box(geo, "__dsh_render_service_test", [first, second])
        assert again == box
    finally:
        if box is not None:
            box.destroy(destroy_contents=False)
        for node in (first, second):
            if node is not None:
                node.destroy()
check("9c persistent render service Network Box", t9c)


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


# 12) display_node reports a mid-chain flag with note
def t12():
    tail = geo.createNode("null", "OUT")
    tail.setInput(0, box)          # box 在链中，tail 是链尾
    box.setDisplayFlag(True)       # 事故形态：旗标停在链中间
    box.setRenderFlag(True)
    tail.setDisplayFlag(False)
    info = H.display_node(geo)
    assert info["display"] == box.path(), info
    assert info["is_leaf"] is False and "note" in info, info
check("12 display_node mid-chain flag + note", t12)


# 13) set_display moves the flag to the requested node
def t13():
    tail = hou.node("/obj/regr_geo/OUT")
    r = H.set_display(tail)
    assert r["context"] == "sop" and r["node"] == tail.path(), r
    assert r["display"] is True and r["render"] is True, r
    info = H.display_node(geo)
    assert info["display"] == tail.path() and info["is_leaf"] is True, info
    assert "note" not in info, info
check("13 set_display moves flag to leaf", t13)


# 14) set_display(render=False) leaves the render flag untouched
def t14():
    box2 = geo.createNode("box", "b2")
    box2.setDisplayFlag(False)
    tail = hou.node("/obj/regr_geo/OUT")  # 当前持 display+render 旗标
    H.set_display(box2, render=False)
    assert box2.isDisplayFlagSet() and not box2.isRenderFlagSet()
    assert tail.isRenderFlagSet()  # render 旗标没被动过
    H.set_display(tail)            # 还原，别影响后续用例
check("14 set_display render=False untouched render flag", t14)


# 15) geo_attrib_stats: vector P stats + bad name suggestions + string attrib error
def t15():
    fresh = geo.createNode("box", "b15")  # 前面的用例改过 b 的尺寸/位移，用新 box
    s = H.geo_attrib_stats(fresh, "P")
    assert s["size"] == 3 and s["count"] == 8, s  # box 8 个点
    assert abs(s["min"][0] + 0.5) < 1e-6 and abs(s["max"][0] - 0.5) < 1e-6, s
    try:
        H.geo_attrib_stats(fresh, "nope")
    except ValueError as e:
        assert "相似属性" in str(e), e
    else:
        raise AssertionError("no error for unknown attrib")
    wr = geo.createNode("attribwrangle", "w15")
    wr.setInput(0, fresh)
    H.set_parm(wr, "snippet", 's@name = "hello";')
    H.cook_node(wr)
    try:
        H.geo_attrib_stats(wr, "name")
    except ValueError as e:
        assert "字符串属性" in str(e), e
    else:
        raise AssertionError("no error for string attrib")
    # detail 类（attribValue 特判路径）
    H.set_parm(wr, "class", "detail")
    H.set_parm(wr, "snippet", "f@total = 3.5;")
    H.cook_node(wr)
    d = H.geo_attrib_stats(wr, "total", attrib_class="detail")
    assert d["count"] == 1 and d["min"] == 3.5 and d["max"] == 3.5, d
check("15 geo_attrib_stats vector/suggest/string", t15)


# 16) render_frame: geometry ROP writes output; missing input = error not silent success
def t16():
    import os
    rop = hou.node("/out").createNode("geometry", "regr_rop")
    rop.parm("soppath").set(box.path())
    out = "/tmp/regr_render.$F4.bgeo.sc"
    if os.path.exists("/tmp/regr_render.0001.bgeo.sc"):
        os.remove("/tmp/regr_render.0001.bgeo.sc")
    r = H.render_frame(rop, picture=out, frame=1)
    assert r["file_bytes"] and r["file_bytes"] > 0, r
    assert r["errors"] == [] and r["output"].endswith("regr_render.0001.bgeo.sc"), r
    # 静默失败形态：soppath 指向不存在节点 → errors 非空，而不是假成功
    rop.parm("soppath").set("/obj/regr_geo/nonexistent")
    os.remove("/tmp/regr_render.0001.bgeo.sc")
    r2 = H.render_frame(rop, picture=out, frame=1, timeout=3)
    assert r2["file_bytes"] is None and r2["errors"], r2
    rop.destroy()
check("16 render_frame verifies output / catches silent failure", t16)


# 17) render_check: stats + two-image diff (pure-python PNG fixtures)
def t17():
    import struct, zlib

    def write_png(path, w, h, fill, rect=None):
        rows = []
        for y in range(h):
            row = bytearray(b"\x00")
            for x in range(w):
                px = fill
                if rect and rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                    px = (255, 128, 0)
                row += bytes(px)
            rows.append(bytes(row))
        raw = b"".join(rows)
        def chunk(typ, data):
            c = struct.pack(">I", len(data)) + typ + data
            return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        png = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(raw))
               + chunk(b"IEND", b""))
        open(path, "wb").write(png)

    p1, p2, p3 = "/tmp/regr_img1.png", "/tmp/regr_img2.png", "/tmp/regr_img3.png"
    write_png(p1, 64, 64, (0, 0, 0), rect=(16, 16, 48, 48))  # 黑底橙块
    write_png(p2, 64, 64, (0, 0, 0), rect=(16, 16, 48, 48))  # 与 p1 相同
    write_png(p3, 64, 64, (0, 0, 0), rect=(8, 8, 24, 24))    # 块位置不同
    s = H.render_check(p1)
    assert (s["width"], s["height"]) == (64, 64), s
    assert 20 < s["nonblack_pct"] < 30, s           # 32x32 / 64x64 = 25%
    assert s["dominant"][0] == 255 and s["content_bbox"] == [16, 16, 47, 47], s
    d_same = H.render_check(p1, ref=p2)["diff_vs_ref"]
    assert d_same["identical"] is True, d_same
    d_diff = H.render_check(p1, ref=p3)["diff_vs_ref"]
    assert d_diff["identical"] is False and d_diff["max_abs_diff"] > 100, d_diff
check("17 render_check stats + diff", t17)


# 18) viewport_screenshot: headless raises a clear error pointing at render_frame
def t18():
    assert not hou.isUIAvailable()  # 回归在 hython 跑，必为 headless
    try:
        H.viewport_screenshot()
    except ValueError as e:
        assert "render_frame" in str(e), e
        return
    raise AssertionError("no error for headless viewport_screenshot")
check("18 viewport_screenshot headless clear error", t18)


# 19-22) raw-hou gate：拦动词已覆盖的裸 hou、放只读、豁免通道、拦疑似场景修改
import dsh_bridge

def t19():
    dsh_bridge.set_raw_gate(True)
    r = dsh_bridge.run_code("hou.node('/obj').createNode('geo', '__gate_t19')")
    assert not r["ok"], r
    assert "raw-hou gate" in r["error"] and "tab_create" in r["error"], r["error"]
    assert hou.node("/obj/__gate_t19") is None  # 执行前拦截，无副作用
check("19 gate blocks verb-covered raw hou", t19)

def t20():
    r = dsh_bridge.run_code("n = hou.node('/obj')\nprint(n.path())")
    assert r["ok"], r
check("20 gate allows read-only hou", t20)

def t21():
    r = dsh_bridge.run_code(
        "hou.node('/obj').createNode('geo', '__gate_t21')",
        allow_raw="regress: exemption channel",
    )
    assert r["ok"], r
    assert "[gate] raw-hou exemption" in r["stdout"], r["stdout"]
    n = hou.node("/obj/__gate_t21")
    assert n is not None
    n.destroy()
check("21 gate allow_raw exemption passes + traced", t21)

def t22():
    r = dsh_bridge.run_code("hou.node('/obj/regr_geo').setComment('x')")
    assert not r["ok"] and "setComment" in r["error"], r
check("22 gate blocks mutating-but-uncovered call", t22)

dsh_bridge.set_raw_gate(False)


# 23) tab_create parent 接受 path 字符串（铁律 1 的实现漏洞修复，2026-08-19
# 草地 trace：agent 传 '/obj' 收到 'str' object has no attribute 报错）
def t23():
    n = H.tab_create("/obj/regr_geo", "null", name="n23")
    assert n is not None and n.path() == "/obj/regr_geo/n23", n
check("23 tab_create parent as path string", t23)


# 24) describe attrib_delta：color SOP 加 @Cd → added.point 含 Cd；
# 无输入节点不出 attrib_delta 字段（用 color SOP 而非 attribwrangle：
# 本机 hython 编译 VEX 栈溢出（0xC00000FD，HEAD 原生问题，见 t15））
def t24():
    src = geo.createNode("box", "b24")
    col = geo.createNode("color", "c24")
    col.setInput(0, src)
    H.cook_node(col)
    d = H.describe(col)
    delta = d.get("attrib_delta") or {}
    assert "Cd" in (delta.get("added", {}).get("point", [])), d
    d2 = H.describe(src)
    assert "attrib_delta" not in d2, d2  # 无 input 0，无字段
check("24 describe attrib_delta added/removed", t24)


# 25) media 登记：非图片产物（.bgeo）不登记（不污染 media relay）
def t25():
    import os
    rop = hou.node("/out").createNode("geometry", "regr_rop25")
    rop.parm("soppath").set(box.path())
    out = "/tmp/regr25.$F4.bgeo.sc"
    if os.path.exists("/tmp/regr25.0001.bgeo.sc"):
        os.remove("/tmp/regr25.0001.bgeo.sc")
    code = (
        "r = render_frame(hou.node('/out/regr_rop25'), "
        f"picture={out!r}, frame=1)\n"
        "__result__ = r['file_bytes']"
    )
    r = dsh_bridge.run_code(code)
    assert r["ok"] and r["result"], r
    assert "images" not in r, r.get("images")  # .bgeo.sc 不是图片，不登记
    rop.destroy()
check("25 render_frame bgeo not registered as image", t25)


# 26) render_view: headless 抛明确错误（GL 上下文），指向 render_frame
def t26():
    assert not hou.isUIAvailable()
    try:
        H.render_view(box)
    except ValueError as e:
        assert "render_frame" in str(e), e
        return
    raise AssertionError("no error for headless render_view")
check("26 render_view headless clear error", t26)


# 27) describe 对 SOP 必须返回 geometry（2026-08-19 修的大小写 bug：
# category().name() == 'Sop'，旧的 == 'sop' 比较让几何摘要长期静默缺失）
def t27():
    d = H.describe(box)
    g = d.get("geometry")
    assert g and g["points"] == 8 and g["bbox_min"] and g["bbox_max"], d
check("27 describe returns geometry for SOP", t27)


geo.destroy()
print()
print("FAILED:" if failures else "ALL PASS", failures if failures else "")
sys.exit(1 if failures else 0)
