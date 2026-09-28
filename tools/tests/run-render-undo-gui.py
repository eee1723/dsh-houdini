"""Run isolated GUI control/failure probes and retain process evidence."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
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
    parser.add_argument("--timeout", default=120, type=float)
    parser.add_argument("--mode", choices=("all", "both", "control", "post_render_failure",
                                           "post_render_authored_failure"), default="all")
    args = parser.parse_args()
    executable = args.houdini.resolve(strict=True)
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("--output must be an empty or new directory")
    output.mkdir(parents=True, exist_ok=True)
    fixture = ROOT / "tools/tests/dsh-render-undo-gui-fixture.py"
    reports = []
    hython = executable.with_name("hython.exe")
    if not hython.is_file():
        parser.error("--houdini must have a sibling hython.exe")
    with tempfile.TemporaryDirectory(prefix="dsh-render-undo-version-") as version_temp:
        version_probe = subprocess.run(
            [str(hython), "-c", "import hou; print('DSH_HOUDINI_VERSION=' + '.'.join(map(str, hou.applicationVersion()[:2])))"],
            cwd=launch_directory(hython),
            env=isolated_environment(version_temp, executable=hython),
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    version_match = re.search(r"DSH_HOUDINI_VERSION=(21\.0|22\.0)\b", version_probe.stdout)
    if version_probe.returncode or not version_match:
        parser.error("--houdini must be a working H21.0 or H22.0 installation: "
                     + (version_probe.stderr or version_probe.stdout)[-500:])
    major = version_match.group(1)
    python_version = "3.11" if major == "21.0" else "3.13"

    modes = ("control", "post_render_failure", "post_render_authored_failure") if args.mode == "all" else (
        ("control", "post_render_failure") if args.mode == "both" else (args.mode,))
    for mode in modes:
        target = output / mode
        target.mkdir()
        with tempfile.TemporaryDirectory(prefix=f"dsh-render-undo-{mode}-") as temp:
            env = isolated_environment(temp, executable=executable, gui=True)
            prefs_pattern = env["HOUDINI_USER_PREF_DIR"]
            hook = Path(prefs_pattern.replace("__HVER__", major)) / f"python{python_version}libs/uiready.py"
            hook.parent.mkdir(parents=True, exist_ok=True)
            hook.write_text(f"import runpy\nrunpy.run_path({str(fixture)!r})\n", encoding="utf-8")
            env.update(DSH_RENDER_UNDO_GUI_DIR=str(target), DSH_RENDER_UNDO_GUI_REPO=str(ROOT),
                       DSH_RENDER_UNDO_GUI_MODE=mode, HOUDINI_TEMP_DIR=str(target / "houdini-temp"))
            (target / "houdini-temp").mkdir()
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            with (target / "gui-process.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    [str(executable), "-foreground", "-geometry=900x700+12000+12000"],
                    cwd=launch_directory(executable), env=env, stdout=log, stderr=log,
                    startupinfo=startup)
                try:
                    process.wait(timeout=args.timeout)
                    timed_out = False
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=20)
                    timed_out = True
            result_path = target / "results.json"
            report = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
            marker_path = target / "render-returned.json"
            marker = json.loads(marker_path.read_text(encoding="utf-8")) if marker_path.exists() else None
            checks = {
                "normal_exit": process.returncode == 0 and not timed_out,
                "render_returned": marker is not None and marker.get("ok") is True,
                "image_written": bool(marker and isinstance(marker.get("output"), str)
                                      and Path(marker["output"]).is_file()
                                      and Path(marker["output"]).stat().st_size > 0),
                "service_retained": report.get("service_exists") is True,
            }
            if mode == "control":
                checks["bridge_success"] = report.get("ok") is True
            else:
                checks["named_failure_returned"] = (report.get("ok") is False
                                                     and "NameError" in report.get("error", ""))
            if mode == "post_render_authored_failure":
                checks["author_edit_rolled_back"] = (bool(marker and marker.get("authored_node_exists") is True)
                                                       and report.get("authored_node_exists") is False
                                                       and (report.get("rollback") or {}).get("applied") is True)
            reports.append({"mode": mode, "exit_code": process.returncode,
                            "timed_out": timed_out, "result": report, "render_returned": marker,
                            "checks": checks, "passed": all(checks.values()),
                            "process_log": str(target / "gui-process.log"),
                            "error_file": str(target / "error.txt") if (target / "error.txt").exists() else None})
    summary = {"houdini": str(executable), "version": major,
               "passed": all(report["passed"] for report in reports), "reports": reports}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    if not all(report["passed"] for report in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
