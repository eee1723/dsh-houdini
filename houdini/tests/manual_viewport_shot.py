"""临时脚本：在 Houdini GUI 的 Python Shell 里直接跑，抓当前视口截图。

用法（二选一）：
  1. Python Shell 里执行：exec(open(r"E:/dsh-houdini/houdini/tests/manual_viewport_shot.py").read())
  2. 或直接粘贴本文件全部内容到 Python Shell

产物：$HIP/screenshots/viewport_f<帧>_<时间>.png（hip 未保存则落在当前目录 screenshots/）

注意：同一 Python Shell 里重复跑必须 importlib.reload——否则 sys.modules
缓存的是旧版模块（行号对不上文件内容就是缓存的指纹）。
"""
import importlib
import sys

if r"E:/dsh-houdini/houdini/python3.11libs" not in sys.path:
    sys.path.insert(0, r"E:/dsh-houdini/houdini/python3.11libs")

import dsh_hou_helpers
importlib.reload(dsh_hou_helpers)

r = dsh_hou_helpers.viewport_screenshot()
print("=" * 60)
print("viewer:  ", r["viewer"])
print("viewport:", r["viewport"])
print("frame:   ", r["frame"])
print("bytes:   ", r["bytes"])
print("saved:   ", r["path"])
print("=" * 60)
