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
contracts=dsh_bridge.run_code("__result__=verb_help(['scene_info','set_parms','render_frame'])",read_only=True)
assert contracts['ok'],contracts
assert [(item['call_mode'],item['content_invalidation']) for item in contracts['result']['items']]==[
    ('query_or_exec','none'),('exec','node'),('exec','none')],contracts

namespace_read = dsh_bridge.run_code("__result__ = len(globals().copy())", read_only=True)
assert namespace_read['ok'] and namespace_read['result'] > 0, namespace_read

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

# Python guarantees the container types of variadic parameters, including in
# nested authorization helpers. Their methods do not require raw exemptions.
for query in (False, True):
    variadic = dsh_bridge.run_code(
        "def dispatch(*args, **kwargs):\n"
        "    kwargs.setdefault('mode', 'edit'); return [args.count(2), kwargs['mode']]\n"
        "__result__=dispatch(2, 2)", read_only=query)
    assert variadic['ok'] and variadic['result'] == [2, 'edit'], variadic

# A proven ordinary callable stays Python when its argument expansion is not
# statically unpacked. The source body still supplies any actual HOM writes.
for source in (
    "def copy(value): return value + 1\nargs=(3,)\n__result__=copy(*args)",
    "class Module:\n    def copy(self, value): return value + 1\n"
    "args=(3,)\n__result__=Module().copy(*args)",
):
    for query in (False, True):
        expanded = dsh_bridge.run_code(source, read_only=query)
        assert expanded['ok'] and expanded['result'] == 4, expanded
        assert 'rawUsage' not in expanded, expanded

# A source-defined ordinary method is analyzed through its body. Calling the
# verb wrapper is legal; renaming the wrapper is not a prerequisite for work.
local_builder = dsh_bridge.run_code(
    "class Module:\n"
    "    def copy_complete(self): return tab_create('/obj', 'geo', name='__gate_local_wrapper')\n"
    "m=Module(); duplicate=m.copy_complete; __result__=duplicate().path()")
assert local_builder['ok'], local_builder
local_node = hou.node(local_builder['result'])
assert local_node is not None
local_node.destroy()

local_fixture = hou.node('/obj').createNode('geo', '__gate_local_source')
try:
    for source, operation in (
        ("class Module:\n    def copy(self): return hou.node('/obj').createNode('geo','__gate_bad_local')\nModule().copy()", 'createNode'),
        ("class Module:\n    def __init__(self): self.node=hou.node('/obj/__gate_local_source')\n    def copy(self): self.node.setName('__changed')\nModule().copy()", 'setName'),
        ("class Module:\n    def copy(self): return 1\nm=Module(); m.copy=hou.node('/obj/__gate_local_source').setName; m.copy('__changed')", 'setName'),
        ("class Module:\n    def copy(self): return 1\nAlias=Module; setattr(Alias,'copy',hou.node('/obj/__gate_local_source').setName); Module().copy('__changed')", 'setName'),
        ("class Module:\n    def copy(self): return 1\nm=Module(); d=vars(m); d['copy']=hou.node('/obj/__gate_local_source').setName; m.copy('__changed')", 'setName'),
    ):
        for query in (False, True):
            rejected = dsh_bridge.run_code(source, read_only=query, allow_raw='cannot exempt source-wrapped HOM')
            assert not rejected['ok'] and ('read-only' if query else 'allow_raw cannot exempt') in rejected['error'], rejected
            assert operation in {row['name'] for row in rejected['rawUsage']['coveredMutations']}, rejected
            assert local_fixture.name() == '__gate_local_source'
            assert hou.node('/obj/__gate_bad_local') is None
finally:
    local_fixture.destroy()

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

# Method ownership, rather than a mutating spelling, distinguishes Python
# bookkeeping from HOM writes in both exec and inspect. Bound methods and HOM
# getter results use the same classification as direct literal receivers.
for read_only in (False, True):
    bookkeeping = dsh_bridge.run_code(
        "pieces=[hou.node('/obj'), 1]; remove=pieces.remove; remove(1)\n"
        "names=[n.name().removesuffix('_surface') for n in hou.node('/').children()]\n"
        "__result__=[len(pieces), hou.node('/obj').path().removeprefix('/'), len(names)>0]",
        read_only=read_only)
    assert bookkeeping['ok'] and bookkeeping['result'] == [1, 'obj', True], bookkeeping

# Stdlib API provenance is independent of spelling and direct/from/bound call
# syntax. Return values do not inherit that provenance. A known module export
# replaced with HOM must retain the covered write, including allow_raw.
for read_only in (False, True):
    ordinary = dsh_bridge.run_code(
        "import math, copy\nfrom math import copysign as sign\n"
        "bound=math.copysign\n__result__=[math.copysign(2,-1),sign(3,-1),bound(4,-1),copy.copy([5])]",
        read_only=read_only)
    assert ordinary['ok'] and ordinary['result'] == [-2, -3, -4, [5]], ordinary

import math
original_sign = math.copysign
module_fixture = hou.node('/obj').createNode('geo', '__gate_module_export')
try:
    math.copysign = module_fixture.setName
    for source in (
        "import math; math.copysign('__not_renamed')",
        "from math import copysign as rename; rename('__not_renamed')",
        "import math; getter=getattr; rename=getter(math,'copysign'); rename('__not_renamed')",
    ):
        for read_only in (False, True):
            rejected = dsh_bridge.run_code(source, read_only=read_only, allow_raw='cannot exempt re-exported HOM')
            assert not rejected['ok'], rejected
            assert rejected['rawUsage']['coveredMutations'] == [{'name':'setName','count':1,'verb':'rename_node'}], rejected
            assert module_fixture.name() == '__gate_module_export'
finally:
    math.copysign = original_sign
    module_fixture.destroy()

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

# A Python container may hold a HOM object; mutating that element is still a
# scene/geometry operation. Shadowed constructors cannot prove builtin values.
selection.add(mutable.point(0))
hou.session._dsh_adversarial_group = selection
try:
    for code in (
        "pieces=[hou.session._dsh_adversarial_group]; pieces[0].remove(hou.session._dsh_adversarial_group.geometry().point(0))",
        "list=lambda: hou.session._dsh_adversarial_group; list().remove(hou.session._dsh_adversarial_group.geometry().point(0))",
        "pieces=[]; pieces=hou.session._dsh_adversarial_group; remove=pieces.remove; remove(hou.session._dsh_adversarial_group.geometry().point(0))",
    ):
        denied = dsh_bridge.run_code(code, read_only=True)
        assert not denied['ok'] and 'remove' in denied['error'], denied
        assert len(selection.points()) == 1
    safe_container = dsh_bridge.run_code(
        "pieces=[hou.session._dsh_adversarial_group]; pieces.remove(hou.session._dsh_adversarial_group); __result__=len(pieces)",
        read_only=True)
    assert safe_container['ok'] and safe_container['result'] == 0, safe_container
    assert len(selection.points()) == 1
finally:
    del hou.session._dsh_adversarial_group

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

# Executable source must enter this request's AST. Known builtin loaders and
# ordinary lexical aliases cannot hide it, including through a query or an
# allow_raw reason. Payloads are harmless even if this regression fails.
for code in (
    "exec('__result__=1')",
    "eval('1+1')",
    "run=exec\nrun('__result__=1')",
    "run, unused = exec, None\nrun('__result__=1')",
    "exec, run = (lambda source: None), exec\nrun('__result__=1')",
    "(run := exec)('__result__=1')",
    "run = (load := exec)\nrun('__result__=1')",
    "import builtins as b\nagain=b\nrun=getattr(again,'exec')\nrun('__result__=1')",
    "from builtins import eval as calculate\ncalculate('1+1')",
    "run=__builtins__['exec']\nrun('__result__=1')",
    "import builtins as b\nrun=b.__dict__['eval']\nrun('1+1')",
    "def call():\n    run=exec\n    run('__result__=1')\ncall()",
    "def call():\n    unused=[None for eval in ()]\n    return eval('1+1')\ncall()",
    "unused=[(run := exec) for item in [0]]\nrun('__result__=1')",
    "class Reader:\n    eval=lambda value: value\n    def call(self): return eval('1+1')\nReader().call()",
    "run = exec if True else None\nrun('__result__=1')",
    "run = [exec][0]\nrun('__result__=1')",
    "run = (lambda: exec)()\nrun('__result__=1')",
    "def invoke(run): return run('1+1')\ninvoke(eval)",
    "import builtins as b\nrun = [getattr(b,'exec')][0]\nrun('__result__=1')",
    "import builtins as b\nrun = (lambda: b.__dict__['eval'])()\nrun('1+1')",
):
    for read_only in (False, True):
        denied = dsh_bridge.run_code(code, read_only=read_only, allow_raw='cannot exempt hidden source')
        assert not denied['ok'] and 'Dynamic exec/eval' in denied['error'], denied
        assert denied['rawUsage']['gateOutcome'] == ('read_only_blocked' if read_only else 'blocked'), denied
        assert denied['transaction']['status'] == 'no_scene_change', denied

# These exact harmless aliases previously let a read-only request change the
# real Houdini frame while its receipt falsely claimed no_scene_change. The
# builtin reference must be rejected before its later invocation is obscured.
frame_before_hidden = float(hou.frame())
try:
    for reference in ('exec if True else None', '[exec][0]', '(lambda: exec)()'):
        source = f"run = {reference}\nrun('hou.setFrame({frame_before_hidden + 17!r})')"
        for read_only in (False, True):
            denied = dsh_bridge.run_code(source, read_only=read_only)
            assert not denied['ok'] and 'Dynamic exec/eval' in denied['error'], denied
            assert float(hou.frame()) == frame_before_hidden, denied
            assert denied['transaction']['status'] == 'no_scene_change', denied
finally:
    hou.setFrame(frame_before_hidden)

# Names are not builtin identity: explicit local functions, parameters and
# ordinary object methods named eval/exec retain normal Python behavior.
for code in (
    "def eval(value): return value+1\n__result__=eval(1)",
    "def call(eval): return eval(1)\n__result__=call(lambda value: value+1)",
    "def call(exec, /): return exec(1)\n__result__=call(lambda value: value+1)",
    "__result__=(lambda eval: eval(1))(lambda value: value+1)",
    "def outer(eval):\n    def inner(): return eval(1)\n    return inner()\n__result__=outer(lambda value: value+1)",
    "class Reader:\n    def call(self, eval): return eval(1)\n__result__=Reader().call(lambda value: value+1)",
    "class Reader:\n    def eval(self, value): return value+1\n__result__=Reader().eval(1)",
    "import types\nbuiltins=types.SimpleNamespace(eval=lambda value: value+1)\n__result__=builtins.eval(1)",
    "eval=lambda value: value+1\nrun=eval\n__result__=run(1)",
    "__result__=[eval(1) for eval in [lambda value: value+1]][0]",
):
    allowed = dsh_bridge.run_code(code, read_only=True)
    assert allowed['ok'] and allowed['result'] == 2, allowed

# Compiling authoring/callback text does not execute that text. A caught syntax
# error in this ordinary authoring operation is also not a failed scene edit.
compiled_only = dsh_bridge.run_code(
    "compile(\"hou.node('/obj').createNode('geo','never_executed')\", '<authored>', 'exec')\n"
    "try:\n    compile('invalid (', '<authored>', 'exec')\nexcept SyntaxError:\n    pass\n"
    "__result__=2", read_only=True)
assert compiled_only['ok'] and compiled_only['result'] == 2, compiled_only
assert hou.node('/obj/never_executed') is None

# Ordinary local builder methods are Python helpers, independent of spelling.
# The exact class/function body is still analyzed for actual HOM writes.
for read_only in (False, True):
    local = dsh_bridge.run_code(
        "class Mod:\n"
        "    def copy(self,value): return value+1\n"
        "    def set(self,value): return value+2\n"
        "m=Mod(); copy=m.copy; __result__=[copy(1),getattr(m,'set')(1)]",
        read_only=read_only)
    assert local['ok'] and local['result']==[2,3],local
    assert 'rawUsage' not in local,local

builder = dsh_bridge.run_code(
    "def build(api):\n"
    "    C=api['tab_create']\n"
    "    root=C('/obj','geo',name='__gate_local_builder')\n"
    "    class Mod:\n"
    "        def __init__(self,name): self.p=C(root,'subnet',name=name)\n"
    "        def copy(self,name,source): return C(self.p,'xform',name=name,inputs=[source])\n"
    "    m=Mod('PARTS'); source=C(m.p,'box',name='source'); duplicate=m.copy('duplicate',source)\n"
    "    return {'root':root.path(),'output':duplicate.path()}\n"
    "__result__=build({'tab_create':tab_create})",owner_session='local-builder-gate')
assert builder['ok'],builder
root=hou.node(builder['result']['root'])
try:
    assert len(hou.node(builder['result']['output']).geometry().points())==8
finally:
    root.destroy()

target=hou.node('/obj').createNode('geo','__local_gate_target')
try:
    path=repr(target.path())
    unsafe_sources=[
        f"hou.node({path}).copyTo(hou.node('/obj'))",
        f"hou.node({path}).parm('tx').set(9)",
        "class Mod:\n    def copy(self,value): return value\n"
        f"m=Mod();m.copy=hou.node({path}).setName;m.copy('never_renamed')",
        "class Mod:\n    def copy(self): return hou.node("+path+").setName\n"
        "write=Mod().copy();write('never_renamed')",
        "class Mod:\n    def copy(self,fn): return fn('never_renamed')\n"
        f"Mod().copy(*[hou.node({path}).setName])",
        "class Mod:\n    def copy(self,fn): return fn('never_renamed')\n"
        "Mod().copy(**{'fn':hou.node("+path+").setName})",
        "class Mod:\n    def copy(self,*args): return args[0]('never_renamed')\n"
        f"Mod().copy(hou.node({path}).setName)",
        "class Mod:\n    def copy(self,**kwargs): return kwargs['fn']('never_renamed')\n"
        f"Mod().copy(fn=hou.node({path}).setName)",
        "def copy(*args): return args[0]('never_renamed')\n"
        f"copy(hou.node({path}).setName)",
        "class Mod:\n    def copy(self,value): return value\n"
        f"    def __init__(self): type(self).copy=hou.node({path}).setName\n"
        "Mod().copy('never_renamed')",
        "class Mod:\n    def copy(self,value): return value\n"
        "def replace(target,value): target.copy=value\n"
        f"m=Mod();replace(m,hou.node({path}).setName);m.copy('never_renamed')",
    ]
    for source in unsafe_sources:
        for read_only in (False,True):
            count=len(hou.node('/obj').children())
            rejected=dsh_bridge.run_code(source,read_only=read_only)
            assert not rejected['ok'] and rejected['transaction']['status']=='no_scene_change',rejected
            assert target.name()=='__local_gate_target' and target.parm('tx').eval()==0
            assert len(hou.node('/obj').children())==count
    # A known covered setter returned/passed through a helper remains covered
    # even when a caller supplies an allow_raw vocabulary-gap explanation.
    for source in unsafe_sources[1:-1]:
        rejected=dsh_bridge.run_code(source,allow_raw='local helper must not mask a covered HOM setter')
        assert not rejected['ok'] and 'allow_raw cannot exempt' in rejected['error'],rejected
finally:
    target.destroy()

print("raw-hou gate regression passed")
