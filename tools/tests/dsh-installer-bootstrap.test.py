"""Exercise real PowerShell installation into isolated preferences; no live Houdini."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini/python3.11libs"))
import dsh_deployment as d
import dsh_bootstrap as bootstrap
CLEAN_BOOT_ENV = dict(os.environ)
CLEAN_BOOT_ENV["PATH"] = str(Path(os.environ["WINDIR"]) / "System32") + os.pathsep + str(Path(os.environ["WINDIR"]) / "System32/WindowsPowerShell/v1.0")

def execute(args):
    result = subprocess.run(args, capture_output=True, env=CLEAN_BOOT_ENV)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    return result

with tempfile.TemporaryDirectory(prefix="dsh-bootstrap-中文 空格-") as temporary:
    temp = Path(temporary)
    install, packages = temp / "managed", temp / "prefs/packages"
    args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "installer/install.ps1"), "-Root", str(install), "-PackagesDir", str(packages)]
    result = execute([*args, "-PrintOnly"])
    assert not install.exists() and not packages.exists()
    execute(args)
    target = packages / "dsh-houdini.json"
    package = d.read_json(target)
    hosted = Path(package["path"])
    assert hosted.resolve().is_relative_to(install.resolve())
    assert (hosted / "python/dsh_install_ui.py").is_file()
    assert (hosted / "python3.11libs/pythonrc.py").is_file()
    assert (hosted / "python3.13libs/pythonrc.py").is_file()
    # Repeated invocation preserves user-owned prior registration instead of deleting it.
    execute(args)
    assert d.read_json(target) == package
    assert list((install / "package-backups").glob("*.json"))
    # Repair a damaged bootstrap by making a new immutable copy, not overwriting a loaded module.
    (hosted / "python/dsh_install_ui.py").write_text("damaged", encoding="utf-8")
    execute(args)
    repaired = Path(d.read_json(target)["path"])
    assert repaired != hosted and (hosted / "python/dsh_install_ui.py").read_text() == "damaged"
    assert (repaired / "python/dsh_install_ui.py").read_bytes() == (ROOT / "houdini/python3.11libs/dsh_install_ui.py").read_bytes()
    # Exercise the actual double-click entry point, including spaces/Unicode,
    # without leaving a console open or requiring system Node/Git/Python.
    cmd_root, cmd_packages = temp / "cmd-managed", temp / "cmd-prefs/packages"
    command = ["cmd.exe", "/d", "/c", "call", str(ROOT / "Install.cmd"), "-Root", str(cmd_root), "-PackagesDir", str(cmd_packages)]
    result = subprocess.run(command, input=b"\n", capture_output=True, env=CLEAN_BOOT_ENV, timeout=60,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == 0, (result.stdout + result.stderr).decode("utf-8", errors="replace")
    assert (cmd_packages / "dsh-houdini.json").is_file()
    # A running Houdini process pins the state once; installing a release is not hot activation.
    with patch.dict(os.environ, {"DSH_HOUDINI_INSTALL_ROOT": str(install)}), \
         patch.object(subprocess, "run", side_effect=AssertionError("startup must not probe processes")):
        bootstrap.initialize()
        assert bootstrap._PINNED is None
        next_id = "1.0.0-" + "a" * 12 + "-" + "b" * 8
        d.atomic_json(install / "state.json", {**d.empty_state(), "pending": next_id})
        bootstrap.initialize()
        assert bootstrap._PINNED is None
    if Path(sys.executable).name.lower().startswith("hython"):
        import hou
        version = ".".join(str(x) for x in hou.applicationVersion()[:2])
        child_pattern = str(temp / "child-prefs/houdini__HVER__")
        child_packages = Path(child_pattern.replace("__HVER__", version)) / "packages"
        child_packages.mkdir(parents=True)
        shutil.copyfile(target, child_packages / target.name)
        child_env = dict(os.environ, HOUDINI_PATH="&", HOUDINI_NO_ENV_FILE="1", HOUDINI_USER_PREF_DIR=child_pattern)
        child_env.pop("DSH_HOUDINI_MANAGED_CONTEXT", None)
        script = "import sys; assert 'dsh_bootstrap' in sys.modules, 'startup hook was not run'; b=sys.modules['dsh_bootstrap']; assert b._INITIALIZED and b._PINNED == sys.argv[1], (b._PINNED, b._ERROR); print('Real Houdini startup hook pinned the installed state')"
        result = subprocess.run([sys.executable, "-c", script, next_id], env=child_env, capture_output=True)
        assert result.returncode == 0, (result.stdout + result.stderr).decode("utf-8", errors="replace")
        print(result.stdout.decode("utf-8", errors="replace").strip())
    # An explicit root cannot be the entire home/drive.
    rejected = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "installer/install.ps1"), "-Root", str(Path.home()), "-PackagesDir", str(packages)], capture_output=True)
    assert rejected.returncode != 0

print("PowerShell bootstrap: preview, no system runtimes, registration backup, repair and process pinning passed")
