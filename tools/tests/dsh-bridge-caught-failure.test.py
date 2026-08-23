"""Regression: caught verb exceptions must not commit an exec as successful."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))

import dsh_bridge


result = dsh_bridge.run_code(
    "try:\n"
    "    set_parm('/obj/__dsh_node_that_does_not_exist__', 'tx', 1)\n"
    "except Exception as exc:\n"
    "    print('caught:', exc)\n"
    "__result__ = {'incorrect_success': True}\n"
)
assert result["ok"] is False, result
assert "caught and suppressed a verb exception" in result["error"], result["error"]
assert result["verbs"][-1]["verb"] == "set_parm"
assert result["verbs"][-1]["ok"] is False
assert "result" not in result

print("caught verb failure regression passed")
