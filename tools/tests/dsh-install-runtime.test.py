"""Source install/launch/repair must select the same exact DSH; no external writes."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))
sys.modules.setdefault("hou", types.SimpleNamespace())
import dsh_runtime_compat as compat
import dsh_launcher as launcher
import dsh_manager as manager

spec = importlib.util.spec_from_file_location("install_fixture", ROOT / "houdini" / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def write_cache(cache, key, version, *, name="@deepseek-ai/dsh", binary=True):
    root = cache / "_npx" / key / "node_modules" / "@deepseek-ai" / "dsh"
    (root / "lib").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"name": name, "version": version}), encoding="utf-8")
    bin_path = root / "lib" / "bin.js"
    if binary:
        bin_path.write_text("// fixture", encoding="utf-8")
    return bin_path


with tempfile.TemporaryDirectory(prefix="dsh-install-中文 空格-") as temporary:
    root = Path(temporary)
    node = root / "node.exe"
    node.touch()
    cache = root / "cache"
    target = compat.preferred_version()
    required = write_cache(cache, "required", target)
    newest = write_cache(cache, "newest", "99.9.9")
    os.utime(required, (1, 1))
    os.utime(newest, (9999, 9999))
    write_cache(cache, "wrong-name", target, name="other-package")
    write_cache(cache, "missing-bin", target, binary=False)
    malformed = cache / "_npx" / "bad" / "node_modules" / "@deepseek-ai" / "dsh"
    malformed.mkdir(parents=True)
    (malformed / "package.json").write_text("[]", encoding="utf-8")
    assert compat.preferred_cached_bin(cache) == required

    # Even another verified version does not replace preferred based on mtime.
    policy_file = root / "compat.json"
    policy_file.write_text(json.dumps({
        "schemaVersion": 1, "preferredVersion": target,
        "releases": [{"dshVersion": target}, {"dshVersion": "99.9.9"}],
    }), encoding="utf-8")
    assert compat.preferred_cached_bin(cache, policy_file) == required

    def which(name):
        return str(node) if name == "node" else str(root / "npx.cmd") if name == "npx" else None

    with patch.dict(os.environ, {}, clear=True), \
         patch.object(installer.shutil, "which", which), \
         patch.object(installer, "NPM_CACHE", cache), \
         patch.object(launcher, "NPM_CACHE", str(cache)), \
         patch.object(launcher, "NODE", str(node)), \
         patch.object(launcher, "DSH_BIN_ENV", ""), \
         patch.object(launcher, "SHELL", True), \
         patch.object(launcher, "DSH_SPEC", launcher.DEFAULT_DSH_SPEC), \
         patch.object(manager, "_NPM_CACHE", str(cache)):
        assert installer.dsh_command_prefix() == ([str(node), str(required)], False)
        assert launcher._resolve_cached_dsh_bin() == (str(required), "cached-cli")
        assert launcher._frontend_command()[0][:2] == [str(node), str(required)]
        assert manager._selected_cached_dsh_version() == target
        before = required.stat().st_mtime
        manager._require_cached_dsh(target)
        assert required.stat().st_mtime == before

        with patch.object(installer, "NPM_CACHE", root / "empty"), \
             patch.object(launcher, "NPM_CACHE", str(root / "empty")), \
             patch.object(manager, "_NPM_CACHE", str(root / "empty")):
            cold, shell = installer.dsh_command_prefix()
            assert compat.preferred_spec() in cold
            assert compat.preferred_spec() in launcher._frontend_command()[0]
            assert manager._selected_cached_dsh_version() is None

        # Explicit developer overrides are preserved, not silently substituted.
        with patch.dict(os.environ, {"DSH_HOUDINI_DSH_SPEC": "@deepseek-ai/dsh@9.8.7"}):
            assert "@deepseek-ai/dsh@9.8.7" in installer.dsh_command_prefix()[0]
        with patch.dict(os.environ, {"DSH_HOUDINI_DSH_BIN": str(newest)}):
            assert installer.dsh_command_prefix() == ([str(node), str(newest)], False)
        with patch.object(launcher, "DSH_SPEC", "@deepseek-ai/dsh@9.8.7"), \
             patch.object(launcher, "FRONTEND_RUNTIME_STATE", str(root / "runtime.json")), \
             patch.dict(launcher._PENDING, {"frontend_source": "npx-cold"}, clear=True):
            launcher._write_frontend_runtime_state(42)
            assert json.loads((root / "runtime.json").read_text())["version"] is None
        with patch.dict(os.environ, {"DSH_HOUDINI_DSH_SPEC": " "}):
            try:
                installer.dsh_command_prefix()
            except RuntimeError as exc:
                assert "empty" in str(exc)
            else:
                raise AssertionError("empty spec was accepted")

    with patch.dict(os.environ, {}, clear=True), patch.object(installer.shutil, "which", lambda name: None):
        try:
            installer.dsh_command_prefix()
        except RuntimeError as exc:
            assert "Node.js/npx" in str(exc)
        else:
            raise AssertionError("missing source-install dependency was hidden")

    # ZIP/source identity must work with no Git and never inspect parent repos.
    (root / "package.json").write_text('{"version":"0.1.0"}', encoding="utf-8")
    with patch.object(manager, "_PROJECT_ROOT", str(root)), \
         patch.object(manager, "_run", side_effect=AssertionError("no Git allowed")):
        version, identity, dirty = manager._plugin_identity()
        assert version == "0.1.0" and "no Git" in identity and not dirty

print("source installer exact runtime selection tests passed")
