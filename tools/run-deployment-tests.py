"""Run deployment regressions, optionally with both licensed isolated H21/H22 hythons."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import re

ROOT = Path(__file__).resolve().parents[1]
PURE = ["dsh-release-policy", "dsh-install-runtime", "dsh-runtime-compat", "dsh-deployment", "dsh-installer-bootstrap"]
HOUDINI = ["dsh-manager-update", "dsh-launcher-preflight", "dsh-profile-sync", "dsh-install-ui",
           "dsh-bridge-raw-gate", "dsh-node-ownership", "dsh-bridge-caught-failure", "dsh-tab-create-failure",
           "dsh-object-parenting", "dsh-scene-network-render-contract"]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--hython", action="append", type=Path, default=[])
args = parser.parse_args()
targets = [(sys.executable, PURE)] if not args.hython else [(str(binary), PURE + HOUDINI) for binary in args.hython]
observed_versions = set()
for binary, suites in targets:
    if not Path(binary).is_file():
        raise RuntimeError("Hython/interpreter not found: " + binary)
    # Explicitly isolated user preferences; never inherit installed user packages.
    prefs = tempfile.mkdtemp(prefix="dsh-deployment-regression-")
    env = dict(os.environ, HOUDINI_PATH="&", HOUDINI_NO_ENV_FILE="1", HOUDINI_USER_PREF_DIR=prefs + "/houdini__HVER__",
               QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    env.pop("DSH_HOUDINI_MANAGED_CONTEXT", None)
    env.pop("DSH_HOUDINI_INSTALL_ROOT", None)
    if args.hython:
        probe = subprocess.run([binary, "-c", "import hou; print('DSH_TEST_HOUDINI=' + '.'.join(map(str,hou.applicationVersion()[:2])))"],
                               env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
        match = re.search(r"DSH_TEST_HOUDINI=(\d+\.\d+)", probe.stdout)
        if match is None or match[1] not in ("21.0", "22.0") or match[1] in observed_versions:
            raise RuntimeError("Expected distinct supported H21/H22 interpreters, not duplicate or mislabeled paths")
        observed_versions.add(match[1])
    for suite in suites:
        print(f"[{Path(binary).parent.parent.name}] {suite}", flush=True)
        subprocess.run([binary, str(ROOT / "tools/tests" / (suite + ".test.py"))], cwd=ROOT, env=env, check=True)
print("Deployment regression suites passed", flush=True)
