"""Regression for the default-on, non-bypassable raw-hou gate."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))

import hou
import dsh_bridge


assert dsh_bridge._raw_gate is True
assert len(dsh_bridge._VERB_NAMES) == len(dsh_bridge._VERBS)
assert len(dsh_bridge._VERB_CATALOG_HASH) == 64

# A justification cannot turn the vocabulary into an optional API.
covered = dsh_bridge.run_code(
    "hou.node('/obj').createNode('geo', '__dsh_gate_covered__')",
    allow_raw="regression attempts to bypass tab_create",
)
assert covered["ok"] is False, covered
assert "createNode ->" in covered["error"], covered["error"]
assert "allow_raw cannot exempt verb-covered calls" in covered["error"], covered["error"]
assert hou.node("/obj/__dsh_gate_covered__") is None
assert covered["rawUsage"]["gateOutcome"] == "blocked", covered["rawUsage"]
assert covered["rawUsage"]["coveredMutations"] == [
    {"name": "createNode", "count": 1, "verb": "search_tab_entries + tab_create/tab_apply"}
], covered["rawUsage"]

# Parameter aliases and bound setters cannot turn a covered write into an exemption.
fixture = hou.node('/obj').createNode('geo', '__gate_parameter_alias')
before = fixture.parm('tx').eval()
for code in (
    f"n=hou.node({fixture.path()!r}); p=n.parm('tx'); p.set(9)",
    f"p=hou.node({fixture.path()!r}).parmTuple('t'); q=p; q.set((9,9,9))",
    f"p=hou.node({fixture.path()!r}).parm('tx'); write=p.set; write(9)",
    f"p, unused = hou.node({fixture.path()!r}).parm('tx'), 0; p.set(9)",
    f"p=hou.node({fixture.path()!r}).parm('tx'); p.set(hou.Ramp((hou.rampBasis.Linear,)*2,(0,1),(0,1)))",
):
    result = dsh_bridge.run_code(code, allow_raw='parameter format allegedly unsupported')
    assert not result['ok'] and 'allow_raw cannot exempt' in result['error'], result
    assert result['rawUsage']['coveredMutations'][0]['name'] == 'parm().set', result
    assert fixture.parm('tx').eval() == before
fixture.destroy()
assert dsh_bridge._raw_usage_analysis('class Box: pass\nx=Box(); x.set(3)')['coveredMutations'] == []
assert dsh_bridge._raw_usage_analysis("p=hou.parm('/obj/a/tx'); __result__=p.eval()")['coveredMutations'] == []

# Read-only HOM remains a language-level escape hatch without ceremony.
read_only = dsh_bridge.run_code(
    "n = hou.node('/obj')\n__result__ = n.path()",
)
assert read_only["ok"] is True, read_only
assert read_only["result"] == "/obj", read_only
assert read_only["rawUsage"]["gateOutcome"] == "read_only", read_only["rawUsage"]
assert read_only["rawUsage"]["directCalls"] == [
    {"name": "hou.node", "count": 1}
], read_only["rawUsage"]

# HOM getters whose names begin with a mutating prefix are still read-only.
# Old trace evidence incorrectly labeled renderNode() as a render side effect.
getter_analysis = dsh_bridge._raw_usage_analysis("hou.node('/obj').renderNode()")
assert getter_analysis["suspectedMutations"] == [], getter_analysis
assert dsh_bridge._gate_message("hou.node('/obj').renderNode()") is None

# The query tool is enforced at the bridge boundary, not only by its prompt.
query_read = dsh_bridge.run_code(
    "__result__ = scene_info()['frame']",
    read_only=True,
)
assert query_read["ok"] is True, query_read
original_frame = float(hou.frame())
query_mutation = dsh_bridge.run_code(
    f"__result__ = set_timeline(current_frame={original_frame + 1!r})",
    read_only=True,
)
assert query_mutation["ok"] is False, query_mutation
assert "houdini_query is read-only" in query_mutation["error"], query_mutation
assert float(hou.frame()) == original_frame, query_mutation

query_alias = dsh_bridge.run_code(
    f"mutate = set_timeline\n__result__ = mutate(current_frame={original_frame + 1!r})",
    read_only=True,
)
assert query_alias["ok"] is False, query_alias
assert "set_timeline" in query_alias["error"], query_alias
assert float(hou.frame()) == original_frame, query_alias

query_button = dsh_bridge.run_code(
    "hou.node('/obj').parm('does_not_matter').pressButton()",
    read_only=True,
)
assert query_button["ok"] is False, query_button
assert "pressButton" in query_button["error"], query_button

# Scene lifecycle resets cannot be made safe by allow_raw.
original_hip = hou.hipFile.path()
clear_blocked = dsh_bridge.run_code(
    "hou.hipFile.clear(suppress_save_prompt=True)",
    allow_raw="regression attempts to bypass the scene lifecycle guard",
)
assert clear_blocked["ok"] is False, clear_blocked
assert "hou.hipFile.clear() is forbidden" in clear_blocked["error"], clear_blocked
assert hou.hipFile.path() == original_hip, clear_blocked

# Python-only aggregation is read-only even though setdefault starts with
# "set". This exact shape occurred in a real geometry diagnostic trace.
container_query = dsh_bridge.run_code(
    "groups = {}\ngroups.setdefault('body', []).append(1)\n__result__ = groups"
)
assert container_query["ok"] is True, container_query
assert container_query["result"] == {"body": [1]}, container_query

# Python set.add caused a false Raw Gate block in the K3 bicycle trace.  Only
# receivers statically initialized as Python sets are exempted; HOM add* calls
# remain gated as low-level mutations.
set_query = dsh_bridge.run_code(
    "names = set()\nnames.add('Cd')\n__result__ = sorted(names)"
)
assert set_query["ok"] is True, set_query
assert set_query["result"] == ["Cd"], set_query
assert "rawUsage" not in set_query, set_query

# Uncovered low-level mutation is blocked first, then allowed as an isolated,
# trace-visible vocabulary-gap exemption.
low_level_code = (
    "g = hou.Geometry()\n"
    "p = g.createPoint()\n"
    "p.setPosition((0.0, 0.0, 0.0))\n"
    "__result__ = len(g.points())\n"
)
blocked = dsh_bridge.run_code(low_level_code)
assert blocked["ok"] is False, blocked
assert "possibly scene-mutating raw call" in blocked["error"], blocked["error"]
assert blocked["rawUsage"]["gateOutcome"] == "blocked", blocked["rawUsage"]
assert blocked["rawUsage"]["suspectedMutations"] == [
    {"name": "createPoint", "count": 1},
    {"name": "setPosition", "count": 1},
], blocked["rawUsage"]

exempt = dsh_bridge.run_code(
    low_level_code,
    allow_raw="scratch hou.Geometry point authoring has no scene verb",
)
assert exempt["ok"] is True, exempt
assert exempt["result"] == 1, exempt
assert "[gate] raw-hou exemption:" in exempt["stdout"], exempt["stdout"]
assert exempt["rawUsage"]["gateOutcome"] == "exempted", exempt["rawUsage"]
assert exempt["rawUsage"]["exemptionReason"] == (
    "scratch hou.Geometry point authoring has no scene verb"
), exempt["rawUsage"]

# Dotted HOM service calls must be visible to the UI; the old client regex
# highlighted hou.node() but missed the actual file write below.
save_analysis = dsh_bridge._raw_usage_analysis("hou.hipFile.save()")
assert save_analysis["directCalls"] == [
    {"name": "hou.hipFile.save", "count": 1}
], save_analysis
assert save_analysis["coveredMutations"] == [
    {"name": "hipFile.save", "count": 1, "verb": "scene_save"}
], save_analysis
assert save_analysis["suspectedMutations"] == [], save_analysis

# setPosition is receiver-ambiguous (NetworkMovableItem vs GeoPoint), so it is
# deliberately heuristic-only rather than falsely advertised as layout_nodes.
assert dsh_bridge._raw_hou_calls("p.setPosition((0.0, 0.0, 0.0))") == {}

print("raw-hou gate regression passed")
