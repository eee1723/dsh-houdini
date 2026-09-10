"""Actual offscreen Qt widget construction; does not inspect/control a live desktop."""
from __future__ import annotations
import os
from pathlib import Path
import sys
import tempfile
import time
import types
from unittest.mock import patch
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini/python3.11libs"))
from hutil.Qt import QtWidgets, QtGui, QtCore
import dsh_deployment as d
import dsh_install_ui as ui

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def wait_until(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        assert time.monotonic() < deadline, "Qt worker did not finish"
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(25, loop.quit)
        loop.exec()


# The offscreen QPA plugin does not enumerate Windows fonts like the real
# Windows QPA plugin. Load the same installed fonts for representative QA.
for font in ("segoeui.ttf", "consola.ttf", "bahnschrift.ttf"):
    QtGui.QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / font))
with tempfile.TemporaryDirectory(prefix="dsh-install-ui-") as temporary:
    root = Path(temporary)
    parent = QtWidgets.QWidget()
    running = {"loaded": None}
    window = ui.show(d.Store(root, {"schemaVersion": 1, "keys": []}), parent=parent, context_provider=lambda: (None, running["loaded"]))
    app.processEvents()
    controls = {button.text(): button for button in window.findChildren(QtWidgets.QPushButton)}
    assert controls["Install local package…"].isEnabled()
    assert controls["Check for a release"].isEnabled()
    assert not controls["Repair current version"].isEnabled()
    assert not controls["Prepare rollback"].isEnabled()
    assert not controls["Advanced runtime diagnostics"].isEnabled()
    assert ui.show(d.Store(root, {"schemaVersion": 1, "keys": []}), parent=parent) is window
    output = ROOT / "tools/out"
    output.mkdir(exist_ok=True)
    screenshot = output / f"deployment-ui-python{sys.version_info.major}{sys.version_info.minor}.png"
    assert window.grab().save(str(screenshot))
    running["loaded"] = {"installId": "1.0.0-aaaaaaaaaaaa-bbbbbbbb"}
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(180, loop.quit)
    loop.exec()
    assert controls["Advanced runtime diagnostics"].isEnabled(), "an already-open manager must notice a newly loaded runtime"
    window.close()
    app.processEvents()
    assert ui._WINDOW is None

    # Source mode uses the same window with no managed state, installation or
    # runtime startup. A completed worker must not enable managed mutations.
    source = root / "source checkout"
    source.mkdir()
    (source / "package.json").write_text('{"version":"7.8.9"}', encoding="utf-8")
    with patch.object(d, "Store", side_effect=AssertionError("source must not create a store")):
        window = ui.show(source_root=source, parent=parent)
        controls = {button.text(): button for button in window.findChildren(QtWidgets.QPushButton)}
        refresh = controls["Refresh source version"]
        wait_until(refresh.isEnabled)
        labels = [label.text() for label in window.findChildren(QtWidgets.QLabel)]
        assert "7.8.9 · source" in labels and "Source mode · runtime unchecked" in labels
        assert str(source.resolve()) in labels
        assert window.windowTitle() == "DSH-Houdini · Version & Diagnostics"
        assert controls["Advanced runtime diagnostics"].isEnabled()
        controls["Source update instructions"].click()
        assert "npm run build" in window.findChild(QtWidgets.QPlainTextEdit).toPlainText()

        release = ui.releases.validate_published_release({
            "id": 1, "draft": False, "prerelease": False,
            "published_at": "2026-09-09T00:00:00Z", "tag_name": "v1.2.3",
            "html_url": "https://untrusted.invalid/",
        })
        check = controls["Check for a release"]
        with patch.object(ui.releases, "latest_stable_release", return_value=release), \
             patch.object(QtGui.QDesktopServices, "openUrl", return_value=True) as opened:
            check.click()
            wait_until(check.isEnabled)
            assert check.text() == "View release 1.2.3"
            check.click()
            assert opened.call_args.args[0].toString() == release["url"]
        for name in ("Repair current version", "Prepare rollback", "Cancel pending change"):
            assert not controls[name].isEnabled(), name
        called = []
        diagnostics = types.ModuleType("dsh_manager")
        diagnostics.show_version_manager = lambda: called.append(True)
        with patch.dict(sys.modules, {"dsh_manager": diagnostics}):
            controls["Advanced runtime diagnostics"].click()
        assert called == [True]
        assert not (root / "state.json").exists()
        assert window.grab().save(str(output / f"source-ui-python{sys.version_info.major}{sys.version_info.minor}.png"))

        (source / "package.json").write_text("broken", encoding="utf-8")
        refresh.click()
        wait_until(refresh.isEnabled)
        assert "Unavailable" in [label.text() for label in window.findChildren(QtWidgets.QLabel)]
        assert not controls["Prepare rollback"].isEnabled()
        window.close()
        app.processEvents()
        assert ui._WINDOW is None

    # Exercise the actual source menu script: it must enter the shared shell.
    menu = ET.parse(ROOT / "houdini/MainMenuCommon.xml")
    script = menu.find(".//scriptItem[@id='dsh.version_manager']/scriptCode").text
    with patch.object(ui, "show_source") as entry:
        exec(script, {})
        entry.assert_called_once_with()
print("shared source/managed Qt panel, release boundaries and missing-runtime actions passed")
