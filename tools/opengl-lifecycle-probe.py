"""Disposable GUI probe for Houdini OpenGL ROP lifecycle failures.

Launch with:
    houdini -foreground waitforui tools/opengl-lifecycle-probe.py

The probe writes every lifecycle boundary with fsync so a process-fatal GL
dialog cannot erase the last completed step.  It deliberately keeps all nodes
alive and never clears object references, isolating ROP-internal render cleanup
from dsh-houdini's node/proxy cleanup.
"""
from __future__ import annotations

import os
import time
import traceback

import hdefereval
import hou


PROBE_DIR = r"Z:\tmp\dsh-opengl-lifecycle-probe"
LOG_PATH = os.path.join(PROBE_DIR, "lifecycle.log")
HIP_PATH = os.path.join(PROBE_DIR, "probe.hip")


def mark(event: str) -> None:
    os.makedirs(PROBE_DIR, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as stream:
        stream.write(f"{time.time_ns()} {event}\n")
        stream.flush()
        os.fsync(stream.fileno())


def set_if_present(node: hou.Node, name: str, value) -> bool:
    parm = node.parm(name)
    if parm is None:
        return False
    parm.set(value)
    return True


def callback_code(event: str) -> str:
    # ROP script parms parse backslashes once before Python sees the source.
    # Forward slashes avoid turning ``\\t`` in ``Z:\\tmp`` into a tab.
    callback_log_path = LOG_PATH.replace("\\", "/")
    return (
        "import os,time\n"
        f"p={callback_log_path!r}\n"
        "with open(p,'a',encoding='utf-8') as s:\n"
        f"    s.write(str(time.time_ns())+' rop_{event}\\n')\n"
        "    s.flush()\n"
        "    os.fsync(s.fileno())\n"
    )


def run() -> None:
    try:
        os.makedirs(PROBE_DIR, exist_ok=True)
        mark("probe_start")

        obj = hou.node("/obj")
        out = hou.node("/out")
        geo = obj.createNode("geo", "gl_lifecycle_geo")
        for child in list(geo.children()):
            child.destroy()
        box = geo.createNode("box", "box1")
        box.parmTuple("size").set((2.0, 2.0, 2.0))
        box.setDisplayFlag(True)
        box.setRenderFlag(True)

        cam = obj.createNode("cam", "gl_lifecycle_cam")
        aim = obj.createNode("null", "gl_lifecycle_aim")
        cam.parmTuple("t").set((4.0, 3.0, 4.0))
        aim.parmTuple("t").set((0.0, 0.0, 0.0))
        set_if_present(cam, "lookat", aim.path())

        rop = out.createNode("opengl", "gl_lifecycle_rop")
        settings = {
            "camera": cam.path(),
            "vobjects": geo.path(),
            "forceobjects": geo.path(),
            "excludeobjects": f"{cam.path()} {aim.path()}",
            "alights": "",
            "forcelights": "",
            "excludelights": "*",
            "shadingmode": "smooth",
            "usegeocolor": True,
            "colorcorrect": "none",
            "gamma": 1.0,
            "tres": True,
            "override_camerares": True,
            "res1": 720,
            "res2": 720,
        }
        for name, value in settings.items():
            mark(f"set_parm_begin {name}")
            applied = set_if_present(rop, name, value)
            mark(f"set_parm_end {name} applied={applied}")

        for event in ("prerender", "preframe", "postframe", "postrender"):
            set_if_present(rop, "t" + event, 1)
            language = rop.parm("l" + event)
            if language is not None:
                language.set("python")
            script = rop.parm(event)
            if script is not None:
                script.set(callback_code(event))

        hou.hipFile.save(file_name=HIP_PATH)
        mark("scene_saved")

        for index in range(1, 21):
            picture = os.path.join(PROBE_DIR, f"render_{index:02d}.png")
            rop.parm("picture").set(picture)
            mark(f"render_{index:02d}_before_call")
            rop.render(frame_range=(1.0, 1.0), verbose=True)
            mark(f"render_{index:02d}_after_call")
            size = os.path.getsize(picture) if os.path.exists(picture) else -1
            mark(f"render_{index:02d}_file_size {size}")

        mark("probe_complete")
        hou.hipFile.save(file_name=HIP_PATH)
        hou.exit(exit_code=0, suppress_save_prompt=True)
    except BaseException:
        mark("python_exception " + traceback.format_exc().replace("\n", " | "))
        raise


hdefereval.executeDeferred(run)
