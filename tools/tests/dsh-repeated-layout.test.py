"""Cook the shipped repetition example through real Bridge verbs in isolated HOM.

Checks source identities/positions, downstream Sweep/string attributes, edits and
empty-output rollback. No user HIP, live connection or large-code admission gate.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
import hou
import dsh_bridge as bridge

source = (ROOT / 'skills/houdini-sop-workflow/references/modeling-methods.md').read_text(encoding='utf8')
section = source.split('### 重复规律与代码生成', 1)[1]
snippet = re.search(r'```vex\s*\n(.*?)\n```', section, re.S).group(1)
owner = 'repeated-layout-fixture'

def run(code, session=owner):
    return bridge.run_code(code, owner_session=session, owner_call='repeated-layout-check')

params = [{'type': 'int', 'name': 'count', 'label': 'Count', 'default': 240},
          {'type': 'int', 'name': 'samples', 'label': 'Samples', 'default': 32},
          {'type': 'float', 'name': 'spacing', 'label': 'Spacing', 'default': 1.7},
          {'type': 'float', 'name': 'length', 'label': 'Length', 'default': 9},
          {'type': 'float', 'name': 'amplitude', 'label': 'Amplitude', 'default': .35}]
built = run(f"""
g=tab_create('/obj','geo','repeated_layout_fixture')
w=tab_create(g,'attribwrangle','PATHS',parms={{'class':'detail','snippet':{snippet!r}}})
create_spare_parms(w,spec={params!r})
s=tab_create(g,'sweep','TUBES',inputs=[w],parms={{'surfaceshape':'tube','radius':.08,'cols':8,'endcaptype':'single'}})
a=tab_create(g,'attribwrangle','PARTS',inputs=[s],parms={{'class':'primitive','snippet':'s@part="ribs";v@Cd={{.2,.35,.5}};'}})
out=tab_create(g,'null','OUT',inputs=[a])
__result__={{'root':g.path(),'validation':verify_network(g,output=out)}}
""")
assert built['ok'], built
root = hou.node(built['result']['root'])
try:
    paths = root.node('PATHS')
    out = root.node('OUT')
    geo = paths.geometry()
    assert len(geo.points()) == 240 * 32 and len(geo.prims()) == 240
    ids = tuple(geo.pointIntAttribValues('id'))
    assert ids == tuple(range(240 * 32)), 'actual template order and identities'
    for piece in (0, 119, 239):
        prim = geo.prim(piece)
        assert not prim.isClosed() and len(prim.vertices()) == 32
        first, last = prim.vertices()[0].point(), prim.vertices()[-1].point()
        assert abs(first.position()[0] - piece * 1.7) < 1e-4
        assert abs(last.position()[2] - 9) < 1e-5
    surface = out.geometry()
    assert len(surface.prims()) > 240 and not out.errors()
    assert set(surface.primStringAttribValues('part')) == {'ribs'}
    assert tuple(round(v, 4) for v in surface.prim(0).attribValue('Cd')) == (.2, .35, .5)

    changed = run(f"set_parms({paths.path()!r},{{'count':241,'length':12}})\n"
                  f"__result__=verify_network({root.path()!r},output={out.path()!r})")
    assert changed['ok'], changed
    changed_geo = paths.geometry()
    assert len(changed_geo.points()) == 241 * 32
    assert tuple(changed_geo.pointIntAttribValues('id'))[:len(ids)] == ids
    assert abs(changed_geo.prim(240).vertices()[-1].point().position()[2] - 12) < 1e-5
    assert paths.parm('snippet').eval() == snippet, 'parameter edits do not regenerate source'

    failed = run(f"set_parms({paths.path()!r},{{'count':0}})\n"
                 f"__result__=verify_network({root.path()!r},output={out.path()!r})")
    assert not failed['ok'] and paths.parm('count').eval() == 241, failed
    assert len(out.geometry().prims()) > 0, 'empty output is rejected and edit rolled back'
    foreign = run(f"set_parms({paths.path()!r},{{'count':9}})", session='another-author')
    assert not foreign['ok'] and paths.parm('count').eval() == 241, foreign
    print('PASS repeated layout: shipped VEX, downstream attributes, parameter edits, IDs, empty rollback and foreign boundary')
finally:
    root.destroy()
