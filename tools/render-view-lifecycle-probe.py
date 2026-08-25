"""Sacrificial GUI probe exercising the real render_view lifecycle.

Launch only in a separate Houdini process.  The log is fsynced at every
Python/ROP boundary so a fatal OpenGL dialog leaves an exact last-known step.
"""
from __future__ import annotations

import os
import sys
import time
import traceback

import hdefereval
import hou


REPO_LIB = "Z:/EEE_Project/dsh-houdini/houdini/python3.11libs"
PROBE_DIR = "Z:/tmp/dsh-render-view-lifecycle-probe"
LOG_PATH = PROBE_DIR + "/lifecycle.log"


def mark(event: str) -> None:
    os.makedirs(PROBE_DIR, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as stream:
        stream.write(f"{time.time_ns()} {event}\n")
        stream.flush()
        os.fsync(stream.fileno())


def callback_code(event: str) -> str:
    return (
        "import os,time\n"
        f"p={LOG_PATH!r}\n"
        "with open(p,'a',encoding='utf-8') as s:\n"
        f"    s.write(str(time.time_ns())+' rop_{event} frame='+str(hou.frame())+'\\n')\n"
        "    s.flush()\n"
        "    os.fsync(s.fileno())\n"
    )


def attach_callbacks(rop: hou.RopNode) -> None:
    for event in ("prerender", "preframe", "postframe", "postrender"):
        toggle = rop.parm("t" + event)
        language = rop.parm("l" + event)
        script = rop.parm(event)
        if toggle is not None:
            toggle.set(1)
        if language is not None:
            language.set("python")
        if script is not None:
            script.set(callback_code(event))


def run() -> None:
    try:
        mark("exact_probe_start")
        if REPO_LIB not in sys.path:
            sys.path.insert(0, REPO_LIB)
        import dsh_hou_helpers as helpers

        obj = hou.node("/obj")
        out = hou.node("/out")
        geo = obj.createNode("geo", "render_view_probe_geo")
        for child in list(geo.children()):
            child.destroy()
        box = geo.createNode("box", "ANIMATED_OUT")
        box.parmTuple("size").set((2.0, 2.0, 2.0))
        # Frame-varying geometry and transform exercise the same recook boundary
        # as an animation without importing the user's scene.
        box.parm("sizex").setExpression("2 + 0.35*sin($F*0.11)")
        box.parm("sizey").setExpression("2 + 0.25*cos($F*0.07)")
        box.setDisplayFlag(True)
        box.setRenderFlag(True)

        rop = out.createNode("opengl", "__dsh_houdini_opengl")
        rop.setUserData("dsh_houdini_owner", "render_view_v2")
        attach_callbacks(rop)
        mark("scene_ready")

        frames = (1.0, 46.0, 240.0)
        for index in range(1, 31):
            frame = frames[(index - 1) % len(frames)]
            picture = f"{PROBE_DIR}/render_{index:02d}_f{int(frame)}.png"
            mark(f"helper_{index:02d}_before frame={frame}")
            result = helpers.render_view(
                box.path(), frame=frame, framing_frame=1.0,
                width=1280, height=720, picture=picture)
            mark(
                f"helper_{index:02d}_after frame={frame} "
                f"bytes={result.get('file_bytes')} stale={result.get('stale')}"
            )

        mark("exact_probe_complete")
        hou.exit(exit_code=0, suppress_save_prompt=True)
    except Exception:
        mark("python_exception " + traceback.format_exc().replace("\n", " | "))
        raise


hdefereval.executeDeferred(run)
