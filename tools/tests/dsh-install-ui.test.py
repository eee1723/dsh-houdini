"""Actual offscreen Qt widget construction; does not inspect/control a live desktop."""
from __future__ import annotations
import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini/python3.11libs"))
from hutil.Qt import QtWidgets, QtGui, QtCore
import dsh_deployment as d
import dsh_install_ui as ui

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
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
print("install manager Qt widgets and missing-runtime actions passed")
