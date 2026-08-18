"""诊断：reference plane 网格为什么关不掉。粘贴到 Houdini Python Shell 全量执行。"""
import hou

viewer = hou.ui.curDesktop().paneTabOfType(hou.paneTabType.SceneViewer)
vp = viewer.curViewport()

# 1) settings() 返回的是活对象还是副本？
st1 = vp.settings()
st2 = vp.settings()
print("1) settings() same object:", st1 is st2)

# 2) 视口上有没有把设置写回去的方法？
print("2) apply-ish methods on viewport:",
      [m for m in dir(vp) if any(k in m.lower() for k in ("setting", "apply"))])

# 3) 当前所有 guide 的开关状态（找出网格到底是哪个）
names = [n for n in dir(hou.viewportGuide) if not n.startswith("_") and n != "thisown"]
on, err = [], []
for n in names:
    g = getattr(hou.viewportGuide, n)
    try:
        if st1.guideEnabled(g):
            on.append(n)
    except Exception:
        err.append(n)
print("3) guides ON:", on)
print("   guides ERR:", err)

# 4) enableGuide 写进去之后，用新的 settings() 再读还在吗？（副本 vs 活对象判定）
g = hou.viewportGuide.XZPlane
before = st1.guideEnabled(g)
st1.enableGuide(g, False)
st3 = vp.settings()
after = st3.guideEnabled(g)
print(f"4) XZPlane: before={before} -> enableGuide(False) -> fresh settings() reads {after}")
if before and not after:
    st3.enableGuide(g, True)   # 还原
    print("   (restored)")

# 5) displayOrthoGrid 是不是真凶？
try:
    print("5) displayOrthoGrid:", st1.displayOrthoGrid())
except Exception as e:
    print("5) displayOrthoGrid ERR:", e)

print("DONE — 把全部输出贴回来")
