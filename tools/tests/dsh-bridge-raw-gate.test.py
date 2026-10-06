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

# Network Box creation is unambiguous; generic color/comment methods are only
# verb-covered when the receiver is proven to be a Network Box.
box_create = dsh_bridge.run_code(
    "hou.node('/obj').createNetworkBox('__raw_box__')",
    allow_raw='attempted Network Box escape hatch',
)
assert not box_create['ok'] and 'createNetworkBox -> network_boxes' in box_create['error'], box_create
assert hou.node('/obj').findNetworkBox('__raw_box__') is None
box_usage = dsh_bridge._raw_usage_analysis(
    "b=hou.node('/obj').findNetworkBox('x')\nb.setColor(hou.Color((1,0,0)))\nb.setComment('x')\nb.addNode(hou.node('/obj/x'))\nb.removeNode(hou.node('/obj/x'))\nb.removeAllNodes()")
assert [row['name'] for row in box_usage['coveredMutations']] == [
    'networkBox.addNode', 'networkBox.removeAllNodes', 'networkBox.removeNode',
    'networkBox.setColor', 'networkBox.setComment'], box_usage
by_id=dsh_bridge._raw_usage_analysis("b=hou.networkBoxBySessionId(0)\nb.addItem(hou.node('/obj/x'))")
assert by_id['coveredMutations']==[{'name':'networkBox.addItem','count':1,'verb':'network_boxes'}],by_id
generic_color = dsh_bridge._raw_usage_analysis("widget.setColor('red')")
assert generic_color['coveredMutations'] == [] and generic_color['suspectedMutations'] == [
    {'name':'setColor','count':1}], generic_color

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
assert "houdini_inspect is read-only" in query_mutation["error"], query_mutation
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

# Ordinary Python aliases must retain the lifecycle prohibition in both exec
# and inspect. Previously the first form cleared the scene from a read-only
# request and still reported transaction=no_scene_change.
sentinel = hou.node('/obj').createNode('geo', '__lifecycle_alias_sentinel')
for code in (
    "hip = hou.hipFile\nhip.clear(suppress_save_prompt=True)",
    "import hou as H\nH.hipFile.clear(suppress_save_prompt=True)",
    "from hou import hipFile as scene\nscene.clear(suppress_save_prompt=True)",
    "H = hou\nscene = H.hipFile\nreset = scene.clear\nreset(suppress_save_prompt=True)",
    "scene, unused = hou.hipFile, 0\nreset = scene.clear\nagain = reset\nagain()",
    "scene = hou.hipFile\nload_scene = scene.load\nload_scene('/not-executed.hip')",
    "getattr(hou, 'hipFile').clear(suppress_save_prompt=True)",
    "scene = getattr(hou, 'hipFile')\nscene.clear(suppress_save_prompt=True)",
    "scene = hou.hipFile\ngetattr(scene, 'clear')(suppress_save_prompt=True)",
    "getattr(getattr(hou, 'hipFile'), 'clear')(suppress_save_prompt=True)",
):
    for query in (False, True):
        blocked = dsh_bridge.run_code(code, read_only=query, allow_raw='cannot exempt scene reset')
        assert not blocked['ok'] and 'is forbidden' in blocked['error'], blocked
        assert blocked['rawUsage']['gateOutcome'] == 'forbidden', blocked
        assert hou.node(sentinel.path()) == sentinel
        assert hou.hipFile.path() == original_hip
assert dsh_bridge.run_code("items = {1: 2}\nitems.clear()", read_only=True)['ok']
sentinel.destroy()

# A callable alias or literal reflection is still the same covered operation;
# neither inspect nor an exec allow_raw reason may authorize it. Save/Save As
# must retain their target/current-HIP/user-authorization verb contract.
import tempfile
with tempfile.TemporaryDirectory(prefix='dsh-raw-save-alias-') as raw_dir:
    target = str(Path(raw_dir) / 'unauthorized.hip')
    for code, operation in (
        ("create = hou.node('/obj').createNode\ncreate('geo','__bound_raw_creation')", 'createNode'),
        ("getattr(hou.node('/obj'), 'createNode')('geo','__bound_raw_creation')", 'createNode'),
        (f"write = hou.hipFile.save\nwrite({target!r})", 'hipFile.save'),
        (f"scene = hou.hipFile\nscene.save({target!r})", 'hipFile.save'),
        (f"scene = getattr(hou,'hipFile')\nwrite = getattr(scene,'save')\nwrite({target!r})", 'hipFile.save'),
        (f"rename = hou.hipFile.setName\nrename({target!r})", 'hipFile.setName'),
    ):
        for query in (False, True):
            rejected = dsh_bridge.run_code(code, read_only=query, allow_raw='cannot exempt covered writes')
            assert not rejected['ok'], rejected
            assert rejected['rawUsage']['coveredMutations'][0]['name'] == operation, rejected
            assert hou.node('/obj/__bound_raw_creation') is None
            assert not Path(target).exists()
            assert hou.hipFile.path() == original_hip
    reflected_parm = dsh_bridge._raw_usage_analysis("p = hou.node('/obj').parm('x'); write = getattr(p, 'set'); write(9)")
    assert reflected_parm['coveredMutations'] == [{'name': 'parm().set', 'count': 1, 'verb': 'set_parm'}], reflected_parm
    bound_box = dsh_bridge._raw_usage_analysis("box=hou.node('/obj').findNetworkBox('x'); paint=box.setColor; paint((1,0,0))")
    assert bound_box['coveredMutations'] == [{'name': 'networkBox.setColor', 'count': 1, 'verb': 'network_boxes'}], bound_box

# A recursive source scan in the Bridge once held a component GUI queue for
# minutes. Reject the call before it can run, including common import aliases.
for code in (
    "import os\nlist(os.walk('C:/'))",
    "import os as files\nlist(files.walk('C:/'))",
    "from os import walk as scan\nlist(scan('C:/'))",
    "from pathlib import Path\nlist(Path('C:/').rglob('*.py'))",
    "from pathlib import Path\nlist(Path('C:/').walk())",
    "from pathlib import Path as Files\nroot=Files('C:/'); list(root.walk())",
    "import pathlib as files\nroot=files.Path('C:/'); list((root / 'Users').glob('**/*.py'))",
    "from pathlib import Path\nlist(Path.cwd().glob('**/scene.hip'))",
    "from pathlib import Path\npattern='**/*.hip'; list(Path('C:/').glob(pattern))",
    "import glob as files\nlist(files.iglob('C:/**/*.py', recursive=True))",
):
    for read_only in (False, True):
        blocked = dsh_bridge.run_code(code, read_only=read_only,
                                      allow_raw='attempted traversal exemption')
        assert not blocked['ok'] and 'filesystem traversal is forbidden' in blocked['error'], blocked
        assert blocked['rawUsage']['gateOutcome'] == 'forbidden', blocked
assert dsh_bridge._blocking_host_traversal_message(
    "import os\n__result__=os.path.basename('C:/bounded/file.txt')") is None
assert dsh_bridge._blocking_host_traversal_message(
    "from pathlib import Path\n__result__=list(Path('C:/bounded').glob('*.hip'))") is None

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

# The same aggregation used tuple unpacking in a real repair trace. Match each
# receiver to its initializer; a neighboring HOM receiver must stay gated.
unpacked_query = dsh_bridge.run_code(
    "slat_x, rails, slat_y = set(), [], set()\n"
    "slat_x.add(1); slat_y.add(2); rails.append(3)\n"
    "__result__ = [sorted(slat_x), rails, sorted(slat_y)]"
)
assert unpacked_query['ok'] and unpacked_query['result'] == [[1], [3], [2]], unpacked_query
mixed_usage = dsh_bridge._raw_usage_analysis(
    "names, geo = set(), hou.Geometry()\nnames.add('Cd')\ngeo.addAttrib(0, 'Cd', 0)"
)
assert mixed_usage['suspectedMutations'] == [{'name':'addAttrib', 'count':1}], mixed_usage

# A prior set initializer is not receiver identity after a rebinding. Exercise
# actual HOM PointGroup.add against a persistent, mutable geometry fixture.
mutable = hou.Geometry()
mutable.createPoint()
selection = mutable.createPointGroup('selected')
hou.session._dsh_adversarial_geometry = mutable
group_expr = "hou.session._dsh_adversarial_geometry.findPointGroup('selected')"
try:
    for prefix in (
        f"group, unused = set(), 0\ngroup = {group_expr}\n",
        f"group = set()\ngroup = {group_expr}\n",
        f"group = set()\nfor group in [{group_expr}]:\n    pass\n",
        f"set = lambda: {group_expr}\ngroup = set()\n",
    ):
        result = dsh_bridge.run_code(prefix + "group.add(hou.session._dsh_adversarial_geometry.point(0))",
                                     read_only=True)
        assert not result['ok'] and 'read-only' in result['error'], result
        assert result['rawUsage']['suspectedMutations'] == [{'name': 'add', 'count': 1}], result
        assert not selection.points(), result
finally:
    del hou.session._dsh_adversarial_geometry

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

# Removing archive delivery/reload from the vocabulary must not turn those
# native package mutations into read-only escape paths.
for operation in ('reloadPackage', 'loadPackageArchive'):
    denied = dsh_bridge.run_code(f"hou.ui.{operation}('never-dispatched')", read_only=True)
    assert denied['ok'] is False and operation in denied['error'], denied
    assert denied['rawUsage']['suspectedMutations'][0]['name'] == operation, denied

print("raw-hou gate regression passed")
