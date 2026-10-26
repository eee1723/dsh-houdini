"""Pure admission counterexamples: Python ownership is not method spelling."""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import dsh_code_analysis as analysis


for source in (
    "pieces = [1, 2]; pieces.remove(1)",
    "pieces = list((1, 2)); alias = pieces; alias.remove(1)",
    "items, names = [], set(); items.copy(); names.add('body')",
    "groups = {}; groups.setdefault('body', []).append(1)",
    "value = 'node_surface'; value.removesuffix('_surface')",
    "value = str(12); value.removeprefix('1')",
    "value = f'node_{12}'; value.removesuffix('_12')",
    "pieces = [1, 2]; remove = pieces.remove; again = remove; again(1)",
    "pieces = [1, 2]; remove = getattr(pieces, 'remove'); remove(1)",
    "getattr([1, 2], 'remove')(1)",
    "from builtins import list as sequence; sequence((1, 2)).remove(1)",
    "import builtins as b; b.str('surface').removeprefix('sur')",
    "def build():\n    pieces = [1, 2]\n    pieces.remove(1)\nbuild()",
    "pieces=[]\ndef keep():\n    pieces.remove(1)",
    "values=[]\ndef unrelated(values):\n    pass\nvalues.remove(1)",
    "values=[]\n[None for values in ()]\nvalues.remove(1)",
    "def build():\n    values=[]\n    class Reader:\n        def call(self): values.remove(1)",
    "n=hou.node('/obj'); n.name().removesuffix('_surface')",
    "p=hou.node('/obj'); names=[n.name().removesuffix('_surface') for n in p.children()]",
    "import hou as H\nfor n in H.node('/obj').children():\n    n.path().removeprefix('/obj/')",
    "from hou import node as find\nname=find('/obj').name; name().removesuffix('_surface')",
    "import math; math.copysign(1, -1)",
    "import math as m; m.copysign(1, -1)",
    "from math import copysign as sign; again=sign; again(1, -1)",
    "import math; sign=getattr(math, 'copysign'); sign(1, -1)",
    "import math; attr=getattr; sign=attr(math, 'copysign'); sign(1, -1)",
    "import copy; copy.copy([1, 2])",
    "from copy import copy as duplicate; duplicate([1, 2])",
    "import shutil; duplicate=shutil.copyfile; duplicate(source, target)",
    "import math\ndef unrelated(math): pass\nmath.copysign(1, -1)",
    "import math\ndef sign():\n    return math.copysign(1, -1)",
    "from project_builder import create_part; create_part()",
    "from .math import copysign; copysign(1, -1)",
    "def dispatch(*args, **kwargs):\n    args.count(1); kwargs.setdefault('mode', 'edit')\ndispatch()",
    "class Module:\n    def copy(self, source): return tab_create(source, 'copytopoints')\nm=Module(); m.copy(source)",
    "class Module:\n    def copy_complete(self, source): return tab_create(source, 'copytopoints')\nAlias=Module; m=Alias(); duplicate=m.copy_complete; duplicate(source)",
    "class Module:\n    def create_part(self): return tab_create('/obj', 'geo')\n    def copy(self): return self.create_part()\nm=Module(); getattr(m, 'copy')()",
    "class Module:\n    def __init__(self): self.groups={}\n    def copy(self): self.groups.setdefault('body', [])\nm=Module(); m.copy()",
    "def build():\n    class Module:\n        def copy(self): return tab_create('/obj', 'geo')\n    m=Module(); m.copy(); m=Module(); m.copy()\nbuild()",
    "def copy(value): return value\ncopy(3)",
    "class Mod:\n    def copy(self, value): return value\nm=Mod(); m.copy(3)",
    "class Mod:\n    def set(self, value): return value\nm=Mod(); m.set(3)",
    "class Mod:\n    def setName(self, value): return value\nm=Mod(); m.setName('local')",
    "class Mod:\n    def copy(self, value): return value\nAlias=Mod; m=Alias(); fn=m.copy; again=fn; again(3)",
    "class Mod:\n    def copy(self, value): return value\ngetattr(Mod(),'copy')(3)",
    "def outer():\n    class Mod:\n        def copy(self, value): return value\n    m=Mod(); m.copy(3)\nouter()",
    "def duplicate(self, value): return value\nclass Mod:\n    copy=duplicate\nMod().copy(3)",
    "class Mod:\n    def copy(self,*args): return args\nMod().copy(*unknown)",
    "class Mod:\n    def copy(self,**kwargs): return kwargs\nMod().copy(**unknown)",
    "def copy(*args): return args\ncopy(*unknown)",
):
    result = analysis.CodeAnalysis(source)
    assert not result.raw_usage['coveredMutations'], (source, result.raw_usage)
    assert not result.raw_usage['suspectedMutations'], (source, result.raw_usage)
    for read_only in (False, True):
        error, _ = result.preflight(mutating_verbs=set(), read_only=read_only,
                                   raw_gate=True, allow_raw=None)
        assert error is None, (source, error)


for source, method in (
    ("pieces=[]; pieces=hou.node('/obj'); pieces.remove(1)", 'remove'),
    ("pieces=[]\nif condition: pieces=unknown\npieces.remove(1)", 'remove'),
    ("pieces=[]\nfor pieces in [unknown]: pass\npieces.remove(1)", 'remove'),
    ("pieces=[]\nwith unknown as pieces: pass\npieces.remove(1)", 'remove'),
    ("pieces=[]\ntry: pass\nexcept Exception as pieces: pass\npieces.remove(1)", 'remove'),
    ("pieces=[]\nmatch unknown:\n    case pieces: pass\npieces.remove(1)", 'remove'),
    ("pieces=[]\ndef change():\n    global pieces\n    pieces=unknown\npieces.remove(1)", 'remove'),
    ("def outer():\n    pieces=[]\n    def change():\n        nonlocal pieces\n        pieces=unknown\n    pieces.remove(1)", 'remove'),
    ("def build(pieces):\n    pieces.remove(1)\npieces=[]", 'remove'),
    ("pieces=[]\ndef build(pieces):\n    pieces.remove(1).value = 0", 'remove'),
    ("pieces=[]\ndef build(pieces):\n    pieces.remove(1)[0] += 1", 'remove'),
    ("pieces=[]\ndef outer(pieces):\n    def build(value: pieces.remove(1)): pass", 'remove'),
    ("pieces=unknown\nclass C:\n    pieces=[]\n    values=[pieces.remove(1) for _ in (1,)]", 'remove'),
    ("pieces=unknown\nclass C:\n    pieces=[]\n    class D:\n        pieces.remove(1)", 'remove'),
    ("pieces=[]\n[pieces.remove(1) for pieces in [unknown]]", 'remove'),
    ("pieces=[]\n[(pieces:=unknown).remove(1) for _ in [0]]", 'remove'),
    ("def build(list):\n    list().remove(1)", 'remove'),
    ("list=custom_constructor; list().remove(1)", 'remove'),
    ("list=lambda: hou.node('/obj'); list().remove(1)", 'remove'),
    ("from custom import list\nlist().remove(1)", 'remove'),
    ("pieces=[]\nfrom custom import *\npieces.remove(1)", 'remove'),
    ("str=custom_constructor; str().removesuffix('_surface')", 'removesuffix'),
    ("def build(str):\n    str().removesuffix('_surface')", 'removesuffix'),
    ("n=unknown; n.name().removesuffix('_surface')", 'removesuffix'),
    ("hou=custom; hou.node('/obj').name().removesuffix('_surface')", 'removesuffix'),
    ("import hou as H\nH=custom\nH.node('/obj').name().removesuffix('_surface')", 'removesuffix'),
    ("pieces=[hou.node('/obj')]; pieces[0].remove(1)", 'remove'),
    ("pieces=[]; remove=pieces.remove; remove=unknown.remove; remove(1)", 'remove'),
    ("getattr=custom; getattr([], 'remove')(1)", 'remove'),
    ("unknown.setdefault('body', [])", 'setdefault'),
    ("n=hou.node('/obj'); n.removesuffix('_surface')", 'removesuffix'),
    ("n=hou.node('/obj'); n.setName('changed')", 'setName'),
    ("pieces=[hou.node('/obj')]; pieces[0].setName('changed')", 'setName'),
    ("pieces=[]; pieces=hou.node('/obj').parm('tx'); write=pieces.set; write(1)", 'parm().set'),
    ("import math; math=unknown; math.copysign(1, -1)", 'copysign'),
    ("import math\ndef sign(math):\n    return math.copysign(1, -1)", 'copysign'),
    ("import math\n[math.copysign(1, -1) for math in unknown]", 'copysign'),
    ("import math\nif condition: math=unknown\nmath.copysign(1, -1)", 'copysign'),
    ("from math import copysign; copysign=unknown.copysign; copysign(1, -1)", 'copysign'),
    ("import copy; copy.copy(value).setName('changed')", 'setName'),
    ("import math; math.frexp(value)[0].setName('changed')", 'setName'),
    ("import external; external.copysign(1, -1)", 'copysign'),
    ("import external; external.createNode('geo')", 'createNode'),
    ("import math; math.copysign=unknown; math.copysign(1, -1)", 'copysign'),
    ("import math; math.copysign=hou.node('/obj').setName; math.copysign('changed')", 'setName'),
    ("import math as m; alias=m; alias.copysign=hou.node('/obj').setName; m.copysign('changed')", 'setName'),
    ("import math; setattr(math, 'copysign', hou.node('/obj').setName); math.copysign('changed')", 'setName'),
    ("import math; setattr(math, field, hou.node('/obj').setName); math.copysign('changed')", 'setName'),
    ("import math; math.__dict__['copysign']=hou.node('/obj').setName; math.copysign('changed')", 'setName'),
    ("import math; math.copysign, other=hou.node('/obj').setName, None; math.copysign('changed')", 'setName'),
    ("import math; apply=setattr; apply(math, 'copysign', hou.node('/obj').setName); math.copysign('changed')", 'setName'),
    ("import math; d=math.__dict__; d['copysign']=hou.node('/obj').setName; math.copysign('changed')", 'setName'),
    ("import math; d=vars(math); d['copysign']=hou.node('/obj').setName; math.copysign('changed')", 'setName'),
    ("import math; d=math.__dict__; d.update(source); math.copysign(1, -1)", 'copysign'),
    ("import math; export(vars(math)); math.copysign(1, -1)", 'copysign'),
    ("import math; del math.copysign; math.copysign(1, -1)", 'copysign'),
    ("import math\nfor math.copysign in external: pass\nmath.copysign(1, -1)", 'copysign'),
    ("import math\nwith external as math.copysign: pass\nmath.copysign(1, -1)", 'copysign'),
    ("def dispatch(**kwargs):\n    kwargs=hou.node('/obj'); kwargs.setName('changed')", 'setName'),
    ("def dispatch(*args):\n    args=unknown; args.remove(1)", 'remove'),
    ("class Module:\n    def copy(self): return hou.node('/obj').createNode('geo')\nm=Module(); m.copy()", 'createNode'),
    ("class Module:\n    def __init__(self): self.node=hou.node('/obj')\n    def copy(self): self.node.setName('changed')\nm=Module(); m.copy()", 'setName'),
    ("class Module:\n    def copy(self): return 1\nm=Module(); m.copy=hou.node('/obj').setName; m.copy('changed')", 'setName'),
    ("class Module:\n    def copy(self): return 1\nAlias=Module; Alias.copy=hou.node('/obj').setName; Module().copy('changed')", 'setName'),
    ("class Module:\n    def __init__(self): self.copy=hou.node('/obj').setName\n    def copy(self): return 1\nm=Module(); m.copy('changed')", 'setName'),
    ("class Module:\n    def copy(self): return 1\nm=Module(); setattr(m, 'copy', hou.node('/obj').setName); getattr(m, 'copy')('changed')", 'setName'),
    ("class Module:\n    def copy(self): return 1\nm=Module(); setattr(Module, field, hou.node('/obj').setName); m.copy('changed')", 'setName'),
    ("class Module:\n    def copy(self): return 1\nm=Module(); m=unknown; m.copy()", 'copy'),
    ("class Module:\n    def copy(self): return 1\nm=Module(); Module=unknown; Module().copy()", 'copy'),
    ("class Module:\n    def copy(self): return 1\nm=Module(); d=vars(m); d['copy']=hou.node('/obj').setName; m.copy('changed')", 'setName'),
    ("class Module:\n    def copy(self): return 1\nm=Module(); del Module.copy; m.copy()", 'copy'),
    ("class Module(Base):\n    def copy(self): return 1\nm=Module(); m.copy()", 'copy'),
    ("@decorator\nclass Module:\n    def copy(self): return 1\nm=Module(); m.copy()", 'copy'),
    ("class Module(metaclass=Factory):\n    def copy(self): return 1\nm=Module(); m.copy()", 'copy'),
    ("class Module:\n    def __getattribute__(self, name): return external\n    def copy(self): return 1\nm=Module(); m.copy()", 'copy'),
    ("class Module:\n    __getattr__=external\n    def copy(self): return 1\nm=Module(); m.copy()", 'copy'),
    ("class Module:\n    def __new__(cls): return hou.node('/obj')\n    def copy(self): return 1\nm=Module(); m.copy()", 'copy'),
    ("class Module:\n    @decorator\n    def copy(self): return 1\nm=Module(); m.copy()", 'copy'),
    ("class Module:\n    def copy(self): return 1\nm=Module(); getattr(m, 'createNode')('geo')", 'createNode'),
    ("from external import duplicate\nclass Module:\n    copy=duplicate\nm=Module(); m.copy()", 'copy'),
    ("class Descriptor:\n    def __get__(self, instance, owner): return hou.node('/obj').setName\nclass Module:\n    copy=Descriptor()\nm=Module(); m.copy('changed')", 'copy'),
    ("class Module:\n    @staticmethod\n    def copy(): return external\nm=Module(); m.copy()", 'copy'),
    ("class Module:\n    @classmethod\n    def copy(cls): return external\nm=Module(); m.copy()", 'copy'),
    ("class Module:\n    @property\n    def copy(self): return hou.node('/obj').setName\nm=Module(); m.copy('changed')", 'copy'),
    ("class Module:\n    def copy(self): return 1\nm=Module(); m.__class__=external; m.copy()", 'copy'),
    ("class Module:\n    def copy(self): return 1\nModule.__getattribute__=external; Module().copy()", 'copy'),
    ("class Module:\n    def copy(self): return 1\nm=Module(); change(m); m.copy()", 'copy'),
    ("class Module:\n    def copy(self): return 1\nm=Module(); callback(m.copy); m.copy()", 'copy'),
    ("class Module:\n    def copy(self): return 1\nm=Module(); getattr(m,'copy').__func__.attr=external; m.copy()", 'copy'),
    ("class Mod:\n    def copy(self, value): return value\nm=Mod(); m=hou.node('/obj'); m.copyTo(hou.node('/obj'))", 'copyTo'),
    ("class Mod:\n    def copy(self, value): return value\ndef run(m): m.copy(3)\nrun(Mod())", 'copy'),
    ("class Mod:\n    def copy(self, value): return value\nm=Mod(); m=unknown; m.copy(3)", 'copy'),
    ("class Mod:\n    def copy(self, value): return value\nif condition: Mod=unknown\nMod().copy(3)", 'copy'),
    ("class Mod(Base):\n    def copy(self, value): return value\nMod().copy(3)", 'copy'),
    ("@decorate\nclass Mod:\n    def copy(self, value): return value\nMod().copy(3)", 'copy'),
    ("class Mod:\n    @decorate\n    def copy(self, value): return value\nMod().copy(3)", 'copy'),
    ("class Mod:\n    def __new__(cls): return unknown\n    def copy(self, value): return value\nMod().copy(3)", 'copy'),
    ("class Mod:\n    def __getattribute__(self, name): return unknown\n    def copy(self, value): return value\nMod().copy(3)", 'copy'),
    ("class Mod:\n    def copy(self, value): return value\nMod.__new__=unknown\nMod().copy(3)", 'copy'),
    ("class Mod:\n    def copy(self, value): return value\nMod.__dict__\nMod().copy(3)", 'copy'),
    ("class Mod:\n    def copy(self, value): return value\n    namespace=locals()\nMod().copy(3)", 'copy'),
    ("class Mod:\n    def copy(self, value): hou.node('/obj').setName(value)\nMod().copy('x')", 'setName'),
    ("class Mod:\n    copy=hou.node('/obj').setName\nMod().copy('x')", 'setName'),
    ("class Mod:\n    def copy(self, value): return value\nm=Mod(); m.copy=hou.node('/obj').setName; m.copy('x')", 'setName'),
    ("class Mod:\n    def copy(self, value): return value\nMod.copy=hou.node('/obj').setName; Mod().copy('x')", 'setName'),
    ("class Mod:\n    def copy(self, value): return value\n    def __init__(self): self.copy=hou.node('/obj').setName\nMod().copy('x')", 'setName'),
    ("class Mod:\n    def copy(self, value): return value\nm=Mod(); setattr(m,'copy',hou.node('/obj').setName); m.copy('x')", 'setName'),
    ("class Mod:\n    def copy(self, value): return value\nm=Mod(); m.__dict__['copy']=hou.node('/obj').setName; m.copy('x')", 'setName'),
    ("class Mod:\n    def copy(self, value): return value\nm=Mod(); d=vars(m); d['copy']=hou.node('/obj').setName; m.copy('x')", 'setName'),
    ("class Mod:\n    def copy(self, value): return value\nm=Mod(); change=m.__setattr__; change('copy',hou.node('/obj').setName); m.copy('x')", 'setName'),
    ("class Mod:\n    def copy(self, value): return value\nm=Mod(); object.__setattr__(m,'copy',hou.node('/obj').setName); m.copy('x')", 'setName'),
    ("class Mod:\n    def copy(self, value): return value\nm=Mod(); m.copy=hou.node('/obj').parm('tx').set; m.copy(9)", 'parm().set'),
    ("class Mod:\n    def copy(self): return hou.node('/obj').setName\nwrite=Mod().copy(); write('x')", 'setName'),
    ("class Mod:\n    def copy(self): return hou.node('/obj').parm('tx').set\nwrite=Mod().copy(); write(9)", 'parm().set'),
    ("class Mod:\n    def copy(self, value): return value\n    def __init__(self): self.__class__.copy=hou.node('/obj').setName\nMod().copy('x')", 'setName'),
    ("class Mod:\n    def copy(self, value): return value\n    def __init__(self): type(self).copy=hou.node('/obj').setName\nMod().copy('x')", 'setName'),
    ("class Mod:\n    def copy(self, value): return value\ndef replace(target,value): target.copy=value\nm=Mod();replace(m,hou.node('/obj').setName);m.copy('x')", 'copy'),
    ("class Mod:\n    def copy(self, fn): return fn('x')\nMod().copy(hou.node('/obj').setName)", 'setName'),
    ("class Mod:\n    def copy(self, fn): return fn('x')\nMod().copy(*[hou.node('/obj').setName])", 'setName'),
    ("class Mod:\n    def copy(self, fn): return fn('x')\nMod().copy(**{'fn':hou.node('/obj').setName})", 'setName'),
    ("class Mod:\n    def copy(self, fn=hou.node('/obj').setName): return fn('x')\nMod().copy()", 'setName'),
    ("class Mod:\n    def __init__(self, fn): self.fn=fn\n    def copy(self): return self.fn('x')\nMod(hou.node('/obj').setName).copy()", 'setName'),
    ("class Mod:\n    def copy(self,*args): return args[0]('x')\nMod().copy(hou.node('/obj').setName)", 'setName'),
    ("class Mod:\n    def copy(self,**kwargs): return kwargs['fn']('x')\nMod().copy(fn=hou.node('/obj').setName)", 'setName'),
    ("def copy(*args): return args[0]('x')\ncopy(hou.node('/obj').setName)", 'setName'),
    ("def copy(**kwargs): return kwargs['fn']('x')\ncopy(fn=hou.node('/obj').setName)", 'setName'),
):
    result = analysis.CodeAnalysis(source)
    mutations = result.raw_usage['coveredMutations'] + result.raw_usage['suspectedMutations']
    assert method in {item['name'] for item in mutations}, (source, mutations)
    for read_only in (False, True):
        error, _ = result.preflight(mutating_verbs=set(), read_only=read_only,
                                   raw_gate=True, allow_raw=None)
        assert error, (source, read_only)

# An unloaded stdlib module and an already imported one share the same API
# provenance. Analysis itself must not execute the submitted imports.
stdlib_source = 'import copy; copy.copy([])'
was_loaded = 'copy' in sys.modules
cold = analysis.CodeAnalysis(stdlib_source).raw_usage
assert ('copy' in sys.modules) == was_loaded
import copy
assert analysis.CodeAnalysis(stdlib_source).raw_usage == cold

# The module's name is insufficient: project files and loaded re-exports cannot
# inherit stdlib provenance. No probe is allowed to import the project module.
with tempfile.TemporaryDirectory(prefix='dsh-stdlib-origin-') as directory:
    Path(directory, 'copy.py').write_text("raise AssertionError('analysis imported author code')\n", encoding='utf-8')
    previous = sys.modules.pop('copy')
    sys.path.insert(0, directory)
    try:
        shadow = analysis.CodeAnalysis(stdlib_source).raw_usage
        assert shadow['suspectedMutations'] == [{'name': 'copy', 'count': 1}], shadow
        assert 'copy' not in sys.modules
    finally:
        sys.path.remove(directory)
        sys.modules['copy'] = previous

def fake_set_name(value): pass
fake_set_name.__name__ = 'setName'
fake_set_name.__module__ = 'hou'
original_copy = copy.copy
copy.copy = fake_set_name
try:
    for source in ('import copy; copy.copy(value)', 'from copy import copy as clone; clone(value)'):
        result = analysis.CodeAnalysis(source)
        assert result.raw_usage['coveredMutations'] == [{'name': 'setName', 'count': 1, 'verb': 'rename_node'}], result.raw_usage
        error, _ = result.preflight(mutating_verbs=set(), read_only=False, raw_gate=True, allow_raw='cannot exempt re-export')
        assert error and 'allow_raw cannot exempt' in error, error
finally:
    copy.copy = original_copy

# Evidence reads must not execute a forged spec or metaclass descriptor.
class UnexpectedDescriptor:
    def __getattribute__(self, key):
        raise AssertionError('analysis executed an authored descriptor')

class UnexpectedMeta(type):
    def __getattribute__(self, key):
        raise AssertionError('analysis executed an authored metaclass')

class UnexpectedCallable(metaclass=UnexpectedMeta): pass

original_spec = copy.__spec__
copy.__spec__ = UnexpectedDescriptor()
try:
    assert analysis.CodeAnalysis(stdlib_source).raw_usage['suspectedMutations'] == [{'name': 'copy', 'count': 1}]
finally:
    copy.__spec__ = original_spec
copy.copy = UnexpectedCallable
try:
    assert analysis.CodeAnalysis(stdlib_source).raw_usage['suspectedMutations'] == [{'name': 'copy', 'count': 1}]
finally:
    copy.copy = original_copy

print('pure Raw Gate ownership counterexamples passed')
