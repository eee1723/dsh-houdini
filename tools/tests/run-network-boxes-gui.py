"""Run the Network Box/handoff fixture in a new isolated Houdini GUI."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from houdini_test_environment import isolated_environment, launch_directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--houdini", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    executable = args.houdini.resolve(strict=True)
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("--output must be an empty or new directory")
    output.mkdir(parents=True, exist_ok=True)
    fixture = ROOT / "tools/tests/dsh-network-boxes-gui.test.py"
    with tempfile.TemporaryDirectory(prefix="dsh-network-boxes-gui-") as temp:
        env = isolated_environment(temp, executable=executable, gui=True)
        prefs_pattern = env["HOUDINI_USER_PREF_DIR"]
        hook_source = f"import runpy\nrunpy.run_path({str(fixture)!r})\n"
        for major, python_version in (("21.0", "3.11"), ("22.0", "3.13")):
            prefs = Path(prefs_pattern.replace("__HVER__", major))
            hook = prefs / f"python{python_version}libs/uiready.py"
            hook.parent.mkdir(parents=True, exist_ok=True)
            hook.write_text(hook_source, encoding="utf-8")
        env["DSH_BOX_GUI_DIR"] = str(output)
        env["DSH_BOX_GUI_REPO"] = str(ROOT)
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        with (output / "gui-process.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [str(executable), "-foreground", "-geometry=900x700+12000+12000"],
                cwd=launch_directory(executable), env=env, stdout=log, stderr=log,
                startupinfo=startup)
            try:
                process.wait(timeout=120)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=20)
        report_path = output / "results.json"
        report = (json.loads(report_path.read_text(encoding="utf-8"))
                  if report_path.exists() else {"ok": False, "error": "no GUI report"})
        report["exit_code"] = process.returncode
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report.get("ok") or process.returncode != 0:
            error_path = output / "error.txt"
            if error_path.exists():
                print(error_path.read_text(encoding="utf-8"), file=sys.stderr)
            raise SystemExit(1)


if __name__ == "__main__":
    main()
