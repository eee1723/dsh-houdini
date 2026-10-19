"""Exercise real PowerShell installation into isolated preferences; no live Houdini."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import shutil
import stat
import sys
import tempfile
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini/python3.11libs"))
import dsh_deployment as d
import dsh_bootstrap as bootstrap
CLEAN_BOOT_ENV = dict(os.environ)
CLEAN_BOOT_ENV["PATH"] = str(Path(os.environ["WINDIR"]) / "System32") + os.pathsep + str(Path(os.environ["WINDIR"]) / "System32/WindowsPowerShell/v1.0")

def execute(args, *, env=CLEAN_BOOT_ENV):
    result = subprocess.run(args, capture_output=True, env=env)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    return result

with tempfile.TemporaryDirectory(prefix="dsh-bootstrap-中文 العربية 空格-") as temporary:
    # Windows PowerShell expands 8.3 TEMP aliases when normalizing paths.
    temp = Path(temporary).resolve()
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
    assert (hosted / "python/dsh_ui_style.py").is_file()
    assert (hosted / "python/dsh_support_ui.py").is_file()
    assert (hosted / "python/dsh_support_report.py").is_file()
    assert (hosted / "python/dsh_workbench.py").is_file()
    assert (hosted / "python/dsh_workbench_start.py").is_file()
    assert (hosted / "python/dsh_houdini_installations.py").is_file()
    assert (hosted / "open-workbench.ps1").is_file()
    assert (hosted / "dsh-houdini.ico").read_bytes() == (ROOT / "assets/dsh-houdini.ico").read_bytes()
    assert (install / "DSH-Houdini.lnk").is_file()
    # Read the persisted fields through native IShellLinkW, which preserves
    # Unicode independently of the machine's ANSI code page. WScript.Shell's
    # ANSI getters would corrupt the readback even when the link is correct.
    quote_ps = lambda value: "'" + str(value).replace("'", "''") + "'"
    readback = "$ErrorActionPreference = 'Stop'; [Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)\n"
    readback += "& " + quote_ps(ROOT / "installer/install.ps1") + " -Root " + quote_ps(install) + " -PackagesDir " + quote_ps(packages) + "\n"
    readback += """
$instance = New-Object DshHoudini.ShellLink
try {
    [void][Runtime.InteropServices.ComTypes.IPersistFile].GetMethod('Load').Invoke($instance, [object[]]@('LINK_PATH', [int]0))
    $native = [DshHoudini.IShellLinkW]
    $target = New-Object Text.StringBuilder 32768
    $arguments = New-Object Text.StringBuilder 32768
    $directory = New-Object Text.StringBuilder 32768
    $icon = New-Object Text.StringBuilder 32768
    [void]$native.GetMethod('GetPath').Invoke($instance, [object[]]@($target.PSObject.BaseObject, [int]32768, [IntPtr]::Zero, [uint32]0))
    [void]$native.GetMethod('GetArguments').Invoke($instance, [object[]]@($arguments.PSObject.BaseObject, [int]32768))
    [void]$native.GetMethod('GetWorkingDirectory').Invoke($instance, [object[]]@($directory.PSObject.BaseObject, [int]32768))
    $iconArguments = [object[]]@($icon.PSObject.BaseObject, [int]32768, [int]0)
    [void]$native.GetMethod('GetIconLocation').Invoke($instance, $iconArguments)
    $showArguments = [object[]]@([int]0)
    [void]$native.GetMethod('GetShowCmd').Invoke($instance, $showArguments)
    'DSH_SHORTCUT_JSON=' + (@{target=$target.ToString(); arguments=$arguments.ToString(); directory=$directory.ToString(); icon=$icon.ToString(); iconIndex=$iconArguments[2]; show=$showArguments[0]; powershell=(Join-Path $PSHOME 'powershell.exe')} | ConvertTo-Json -Compress)
} finally { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($instance) }
""".replace("'LINK_PATH'", quote_ps(install / "DSH-Houdini.lnk"))
    result = execute(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", base64.b64encode(readback.encode("utf-16le")).decode("ascii")])
    facts = json.loads(next(line.removeprefix("DSH_SHORTCUT_JSON=") for line in result.stdout.decode("utf-8").splitlines() if line.startswith("DSH_SHORTCUT_JSON=")))
    assert Path(facts["target"]) == Path(facts["powershell"])
    expected_arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + str(hosted / "open-workbench.ps1") + '" -Root "' + str(install) + '"'
    assert facts["arguments"] == expected_arguments, json.dumps({"actual": facts["arguments"], "expected": expected_arguments}, ensure_ascii=True)
    assert Path(facts["directory"]) == install
    assert Path(facts["icon"]) == hosted / "dsh-houdini.ico"
    assert facts["iconIndex"] == 0 and facts["show"] == 7
    assert (install / "Uninstall.cmd").is_file()
    assert (hosted / "uninstall.ps1").is_file()
    assert d.read_json(install / "registrations.json")["packages"] == [str(target)]
    assert (hosted / "python3.11libs/pythonrc.py").is_file()
    assert (hosted / "python3.13libs/pythonrc.py").is_file()
    assert (hosted / 'scripts/afterscenesave.py').read_bytes() == (ROOT / 'houdini/scripts/afterscenesave.py').read_bytes()
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
    # Bootstrap owns its manager before an older runtime's Python directory
    # takes precedence. Upgrading the installer alone must not import the old
    # manager or lose its new uninstall argument after Open Workspace.
    old_runtime = temp / "old-runtime-python"
    old_runtime.mkdir()
    (old_runtime / "dsh_install_ui.py").write_text("raise AssertionError('old runtime manager imported')", encoding="utf-8")
    manager_check = (
        "import pathlib,sys; from unittest.mock import patch; import dsh_bootstrap as b; "
        "manager=b.dsh_install_ui; sys.path.insert(0,sys.argv[1]); "
        "assert pathlib.Path(manager.__file__).resolve().parent == pathlib.Path(sys.argv[2]).resolve(); "
        "capture=patch.object(manager,'show',return_value='bootstrap-manager'); observed=capture.start(); "
        "assert b.show_manager() == 'bootstrap-manager'; "
        "assert pathlib.Path(observed.call_args.kwargs['uninstall_script']).resolve() == pathlib.Path(sys.argv[2]).parent / 'uninstall.ps1'; "
        "capture.stop(); print('Bootstrap retained its own manager with older runtime first on sys.path')"
    )
    manager_result = execute([sys.executable, "-c", manager_check, str(old_runtime), str(repaired / "python")],
                             env=dict(CLEAN_BOOT_ENV, PYTHONPATH=str(repaired / "python"), DSH_HOUDINI_INSTALL_ROOT=str(install)))
    assert b"Bootstrap retained its own manager" in manager_result.stdout
    # Exercise the actual double-click entry point, including spaces/Unicode,
    # without leaving a console open or requiring system Node/Git/Python.
    cmd_root, cmd_packages = temp / "cmd-managed", temp / "cmd-prefs/packages"
    command = ["cmd.exe", "/d", "/c", "call", str(ROOT / "Install.cmd"), "-Root", str(cmd_root), "-PackagesDir", str(cmd_packages)]
    result = subprocess.run(command, input=b"\n", capture_output=True, env=CLEAN_BOOT_ENV, timeout=60,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == 0, (result.stdout + result.stderr).decode("utf-8", errors="replace")
    assert (cmd_packages / "dsh-houdini.json").is_file()
    # Uninstall through the installed Unicode/space-safe double-click entry.
    # It removes this root's registrations and shortcut while retaining every
    # version, credential/session file and external project/standalone DSH file.
    second_packages = temp / "custom-preferences/packages"
    execute([*args[:-1], str(second_packages)])
    second_target = second_packages / target.name
    preserved = {
        install / "data/profile/settings.json": b'{"credential":"fixture"}',
        install / "data/profile/sessions/task.json": b'{"session":"fixture"}',
        install / "releases/version/program.js": b'// version fixture',
        temp / "projects/user.hip": b'project fixture',
        temp / "standalone-dsh/settings.json": b'{"standalone":true}',
        temp / "unrelated.json": b'{"env":[{"DSH_HOUDINI_INSTALL_ROOT":"fixture"}]}',
    }
    for filename, content in preserved.items():
        filename.parent.mkdir(parents=True, exist_ok=True)
        filename.write_bytes(content)
    records = d.read_json(install / "registrations.json")
    records["packages"].append(str(temp / "unrelated.json"))
    d.atomic_json(install / "registrations.json", records)
    uninstall = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "installer/uninstall.ps1"), "-Root", str(install)]
    execute([*uninstall, "-PrintOnly"])
    assert target.exists() and second_target.exists()
    result = subprocess.run(["cmd.exe", "/d", "/c", "call", str(install / "Uninstall.cmd")], input=b"\n", capture_output=True, env=CLEAN_BOOT_ENV, timeout=60,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == 0, (result.stdout + result.stderr).decode("utf-8", errors="replace")
    assert not target.exists() and not second_target.exists()
    assert not (install / "DSH-Houdini.lnk").exists()
    for filename, content in preserved.items():
        assert filename.read_bytes() == content
    execute(uninstall)  # Repeated uninstall is harmless.
    execute(args)  # Reinstall after uninstall preserves retained data.
    for filename, content in preserved.items():
        assert filename.read_bytes() == content
    # An unreadable registration must remain on disk and report partial
    # completion, so the version UI cannot present a successful uninstall.
    registered_content = target.read_bytes()
    target.write_text("{invalid", encoding="utf-8")
    incomplete = subprocess.run(uninstall, capture_output=True, env=CLEAN_BOOT_ENV)
    assert incomplete.returncode != 0 and b"Uninstall incomplete" in incomplete.stderr
    assert b"Preserved unreadable package" in incomplete.stderr
    assert target.read_text(encoding="utf-8") == "{invalid"
    target.write_bytes(registered_content)
    # A preference record that now points to another install is not ours.
    foreign = d.read_json(target)
    foreign["env"][0]["DSH_HOUDINI_INSTALL_ROOT"] = str(temp / "another-install")
    d.atomic_json(target, foreign)
    execute(uninstall)
    assert d.read_json(target) == foreign
    execute(args)
    # Read-only registration fails with an actionable explanation and leaves the
    # previous registration intact; retry works after the real lock is removed.
    before = target.read_bytes()
    target.chmod(stat.S_IREAD)
    try:
        failed = subprocess.run(args, capture_output=True, env=CLEAN_BOOT_ENV)
        assert failed.returncode != 0
        assert b"Could not update Houdini registration" in failed.stderr
        assert target.read_bytes() == before
        assert not list(packages.glob("*.tmp"))
    finally:
        target.chmod(stat.S_IWRITE | stat.S_IREAD)
    execute(args)
    # Old bootstrap installations have no target record. Check their standard
    # Houdini preference pattern, including dangling registration after deletion.
    legacy_root = temp / "deleted-legacy-install"
    legacy_pattern = str(temp / "legacy-prefs/houdini__HVER__")
    legacy_target = Path(legacy_pattern.replace("__HVER__", "21.0")) / "packages/dsh-houdini.json"
    legacy_target.parent.mkdir(parents=True)
    legacy_target.write_text(json.dumps({"env": [{"DSH_HOUDINI_INSTALL_ROOT": str(legacy_root)}]}), encoding="utf-8")
    legacy_env = dict(CLEAN_BOOT_ENV, HOUDINI_USER_PREF_DIR=legacy_pattern)
    execute([*uninstall[:-1], str(legacy_root)], env=legacy_env)
    assert not legacy_target.exists() and not legacy_root.exists()
    # Full offline installation must stage automatically from SideFX's actual
    # registered location, even when no Houdini exists under ProgramFiles.
    # Copy a small installer fixture and replace only stage with an inert script;
    # the real registered Houdini Python executes it without starting Houdini.
    registry_probe = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
        "@(Get-ChildItem -LiteralPath 'HKLM:\\SOFTWARE\\Side Effects Software' -ErrorAction SilentlyContinue | "
        "Where-Object PSChildName -Match '^Houdini (21|22)\\.0\\.' | "
        "ForEach-Object { (Get-ItemProperty -LiteralPath $_.PSPath).InstallPath } | "
        "Where-Object { Test-Path -LiteralPath (Join-Path $_ 'bin/houdini.exe') }) | ConvertTo-Json"],
        capture_output=True, env=CLEAN_BOOT_ENV, text=True)
    if registry_probe.stdout.strip():
        offline = temp / "offline-fixture"
        shutil.copytree(ROOT / "installer", offline / "installer")
        shutil.copytree(ROOT / "assets", offline / "assets")
        shutil.copytree(ROOT / "houdini/scripts", offline / "houdini/scripts")
        for module in ("dsh_bootstrap", "dsh_install_ui", "dsh_ui_style", "dsh_deployment", "dsh_release_policy", "dsh_support_ui", "dsh_support_report", "dsh_workbench", "dsh_houdini_installations", "dsh_workbench_start"):
            source = ROOT / "houdini/python3.11libs" / (module + ".py")
            destination = offline / "houdini/python3.11libs" / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        (offline / "release.json").write_text("{}", encoding="utf-8")
        (offline / "houdini/python3.11libs/dsh_deployment.py").write_text(
            "import json, pathlib, sys\n"
            "root = pathlib.Path(sys.argv[sys.argv.index('--root') + 1])\n"
            "(root / 'stage-invocation.json').write_text(json.dumps({'python': sys.executable, 'argv': sys.argv[1:]}), encoding='utf-8')\n", encoding="utf-8")
        staged_root = temp / "offline-managed"
        stage_env = dict(CLEAN_BOOT_ENV, ProgramFiles=str(temp / "no-standard-houdini"))
        stage_env.pop("HFS", None)
        poison = temp / "unrelated-python-modules"
        poison.mkdir()
        (poison / "json.py").write_text("raise AssertionError('inherited Python modules must not reach installation stage')", encoding="utf-8")
        stage_env["PYTHONPATH"] = str(poison)
        execute(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(offline / "installer/install.ps1"),
                 "-Root", str(staged_root), "-PackagesDir", str(temp / "offline-prefs/packages")], env=stage_env)
        invocation = d.read_json(staged_root / "stage-invocation.json")
        registered_roots = json.loads(registry_probe.stdout)
        if isinstance(registered_roots, str):
            registered_roots = [registered_roots]
        assert any(Path(invocation["python"]).resolve().is_relative_to(Path(location).resolve()) for location in registered_roots)
        assert invocation["argv"][0] == "stage" and "--directory" in invocation["argv"]
    else:
        print("Registered-Houdini offline stage not exercised: no H21/H22 installation is registered")
    # A running Houdini process pins the state once; installing a release is not hot activation.
    with patch.dict(os.environ, {"DSH_HOUDINI_INSTALL_ROOT": str(install)}), \
         patch.object(subprocess, "run", side_effect=AssertionError("startup must not probe processes")):
        bootstrap.initialize()
        assert bootstrap._PINNED is None
        next_id = "1.0.0-" + "a" * 12 + "-" + "b" * 8
        d.atomic_json(install / "state.json", {**d.empty_state(), "pending": next_id})
        bootstrap.initialize()
        assert bootstrap._PINNED is None
    # Merely opening source runtime diagnostics caches source-side paths and
    # compatibility modules. It must not allow a later managed activation.
    messages = []
    fake_hou = types.SimpleNamespace(ui=types.SimpleNamespace(displayMessage=messages.append))
    for runtime_module in ("dsh_manager", "dsh_runtime_compat", "dsh_context", "dsh_webview"):
        with patch.dict(sys.modules, {"hou": fake_hou, runtime_module: types.ModuleType(runtime_module)}), \
             patch.object(bootstrap, "_PINNED", next_id), \
             patch.object(bootstrap, "_CONTEXT", None), \
             patch.object(bootstrap, "_ERROR", None), \
             patch.object(d.Store, "activate", side_effect=AssertionError("mixed runtime activated")):
            bootstrap.open_workspace()
            assert "完整重开" in messages[-1]
            assert bootstrap._BUSY is False
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

# Reproduce the reported ReplaceFile failure using actual different volumes.
# A Documents/preferences drive can differ from LOCALAPPDATA (e.g. OneDrive or
# redirected Documents). Both the first installation and damaged-root repair
# must work without passing a cross-volume backup to ReplaceFile.
scratch = ROOT / "tools/out"
scratch.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="dsh-cross-volume-", dir=scratch) as managed_temp, \
     tempfile.TemporaryDirectory(prefix="dsh-cross-volume-prefs-") as preferences_temp:
    managed = Path(managed_temp).resolve()
    preferences = Path(preferences_temp)
    if managed.drive.lower() != preferences.drive.lower():
        cross_args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "installer/install.ps1"), "-Root", str(managed), "-PackagesDir", str(preferences)]
        target = preferences / "dsh-houdini.json"
        target.write_text('{"previous":"user registration"}', encoding="utf-8")
        execute(cross_args)
        assert any(path.read_text(encoding="utf-8") == '{"previous":"user registration"}' for path in (managed / "package-backups").glob("*.json"))
        execute(cross_args)
        # Deleting only the installation leaves the package in Houdini prefs.
        assert managed.is_relative_to(scratch.resolve())
        shutil.rmtree(managed)
        execute(cross_args)
        assert Path(d.read_json(target)["path"]).is_dir()
        print("Cross-volume registration and manually deleted installation repair passed")
    else:
        print("Cross-volume registration not exercised: preferences and repository are on the same volume")

print("PowerShell bootstrap: preview, registration backup, repair, preserved-data uninstall, old registrations and process pinning passed")
