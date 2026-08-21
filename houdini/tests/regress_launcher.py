"""Non-scene regression for dsh_launcher startup command selection.

Run with Houdini's Python so importing ``hou`` matches the installed package:
    D:/houdini/bin/hython.exe houdini/tests/regress_launcher.py

This test never starts or stops either service and never edits the HIP scene.
"""

from __future__ import annotations

import io
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "houdini", "python3.11libs"))

import dsh_launcher as L


failures: list[str] = []


def check(label, fn):
    try:
        fn()
        print(f"PASS  {label}")
    except Exception as exc:
        failures.append(label)
        print(f"FAIL  {label}: {type(exc).__name__}: {exc}")


def runtime_probe():
    ok, output = L._plugin_runtime_probe()
    assert ok, output


check("compiled plugin resolves through Node ESM", runtime_probe)


def dependencies():
    assert L.ensure_dependencies() == "dependencies ok"


check("dependency check uses successful runtime import", dependencies)


def cached_cli():
    resolved = L._resolve_cached_dsh_bin()
    assert resolved is not None
    path, source = resolved
    assert source in {"cached-cli", "explicit-cli"}, source
    assert os.path.isfile(path), path


check("warm CLI resolves from local cache", cached_cli)


def warm_command():
    cmd, use_shell, source, timeout = L._frontend_command()
    assert isinstance(cmd, list), cmd
    assert not use_shell
    assert source in {"cached-cli", "explicit-cli"}, source
    assert timeout == L.FRONTEND_WARM_WAIT_TIMEOUT == 60
    assert cmd[-3:] == ["web", "--port", str(L.FRONTEND_PORT)], cmd


check("warm start bypasses npx and has short timeout", warm_command)


def explicit_version():
    old_spec = L.DSH_SPEC
    try:
        L.DSH_SPEC = "@deepseek-ai/dsh@0.0.0-test"
        cmd, use_shell, source, timeout = L._frontend_command()
        assert isinstance(cmd, str), cmd
        assert use_shell
        assert source == "npx-cold", source
        assert timeout == L.FRONTEND_COLD_WAIT_TIMEOUT == 600
        assert "@deepseek-ai/dsh@0.0.0-test" in cmd
    finally:
        L.DSH_SPEC = old_spec


check("explicit CLI version retains cold npx update path", explicit_version)


def invalid_explicit_bin():
    old_bin = L.DSH_BIN_ENV
    try:
        L.DSH_BIN_ENV = os.path.join(ROOT, "does-not-exist", "bin.js")
        try:
            L._frontend_command()
        except RuntimeError as exc:
            assert "DSH_HOUDINI_DSH_BIN" in str(exc)
            return
        raise AssertionError("invalid explicit CLI path was silently ignored")
    finally:
        L.DSH_BIN_ENV = old_bin


check("invalid explicit CLI path fails loudly", invalid_explicit_bin)


def session_selection():
    items = [
        {"sessionId": "wrong-preset", "agentPreset": "cordis", "cwd": ROOT, "updatedAt": 99},
        {"sessionId": "wrong-cwd", "agentPreset": "houdini", "cwd": os.path.dirname(ROOT), "updatedAt": 100},
        {"sessionId": "older", "agentPreset": "houdini", "cwd": ROOT, "updatedAt": 10},
        {"sessionId": "newer", "agentPreset": "houdini", "cwd": ROOT.replace("\\", "/"), "updatedAt": 20},
    ]
    selected = L._select_houdini_session(items, ROOT)
    assert selected is not None
    assert selected["sessionId"] == "newer", selected
    archived = L._select_houdini_session(items, ROOT, ["newer"])
    assert archived is not None
    assert archived["sessionId"] == "older", archived


check("session reuse requires exact cwd/preset and chooses newest", session_selection)


def workspace_selection():
    items = [
        {"workspaceId": "other", "path": os.path.dirname(ROOT)},
        {"workspaceId": "target", "path": ROOT.replace("\\", "/")},
    ]
    assert L._workspace_id_for_path(items, ROOT) == "target"
    assert L._workspace_id_for_path(items, os.path.join(ROOT, "missing")) is None


check("new session attaches only to exact workspace path", workspace_selection)


def session_create_uses_workspace_and_preset():
    calls = []
    old_rpc = L._dsh_rpc
    try:
        def fake_rpc(method, payload, timeout=L.DSH_RPC_TIMEOUT):
            calls.append((method, payload))
            if method == "session.list":
                return {"items": []}
            if method == "workspace.list":
                return {"items": [{"workspaceId": "hip-workspace", "path": ROOT}]}
            if method == "session.create":
                return {"sessionId": "created", "agentPreset": "houdini"}
            raise AssertionError(method)

        L._dsh_rpc = fake_rpc
        session_id, status = L.ensure_houdini_session(ROOT)
        assert session_id == "created"
        assert "workspace hip-workspace" in status
        assert calls[-1] == ("session.create", {
            "workspaceId": "hip-workspace", "agentPreset": "houdini",
        })
    finally:
        L._dsh_rpc = old_rpc


check("missing session creates exact preset inside existing workspace", session_create_uses_workspace_and_preset)


def session_create_falls_back_to_cwd():
    calls = []
    old_rpc = L._dsh_rpc
    try:
        def fake_rpc(method, payload, timeout=L.DSH_RPC_TIMEOUT):
            calls.append((method, payload))
            if method in {"session.list", "workspace.list"}:
                return {"items": []}
            if method == "session.create":
                return {"sessionId": "created-cwd", "agentPreset": "houdini"}
            raise AssertionError(method)

        L._dsh_rpc = fake_rpc
        session_id, status = L.ensure_houdini_session(ROOT)
        assert session_id == "created-cwd"
        assert f"cwd {ROOT}" in status
        assert calls[-1] == ("session.create", {
            "cwd": ROOT, "agentPreset": "houdini",
        })
    finally:
        L._dsh_rpc = old_rpc


check("missing workspace creates exact preset from cwd", session_create_falls_back_to_cwd)


def log_header():
    stream = io.BytesIO()
    L._write_frontend_attempt_header(
        stream,
        source="cached-cli",
        cwd=ROOT,
        cmd=[L.NODE, "example/bin.js", "web", "--port", "3081"],
        timeout=60,
    )
    rendered = stream.getvalue().decode("utf-8")
    assert "dsh-houdini frontend attempt" in rendered
    assert "source: cached-cli" in rendered
    assert "timeout: 60s" in rendered
    assert f"cwd: {ROOT}" in rendered


check("attempt log identifies source, cwd, command, and timeout", log_header)


if failures:
    raise SystemExit("launcher regression failures: " + ", ".join(failures))

print("ALL LAUNCHER REGRESSIONS PASSED")
