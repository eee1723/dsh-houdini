"""Isolated H21/H22: filled-surface risk, delayed ownership, replace wiring, data preflight."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_bridge as b

def run(code, ok=True):
    r=b.run_code(code,owner_session='tutorial-contract')
    assert r['ok'] is ok,r
    return r

run('''
g=tab_create('/obj','geo',name='__tutorial_contract')
s=tab_create(g,'grid',name='surface')
set_parms(s,{'rows':2,'cols':2})
w=tab_create(g,'attribwrangle',name='deform',inputs=[s])
set_parms(w,{'snippet':'@P.y += 0.1;'})
consumer=tab_create(g,'null',name='OUT',inputs=[w])
cook_node(consumer)
''')
g=hou.node('/obj/__tutorial_contract')
try:
    result=run("__result__=delete_node('/obj/__tutorial_contract/deform')")['result']
    assert result['affected_connections'][0]['destination']==g.node('OUT').path(),result
    run("w=tab_create('/obj/__tutorial_contract','attribwrangle',name='deform')")
    assert g.node('OUT').input(0)!=g.node('deform'),'same-name creation must not pretend to reconnect'
    # A truly foreign user child remains foreign despite its owned parent.
    sub=run("s=tab_create('/obj/__tutorial_contract','subnet',name='holder')\n__result__=s.path()")['result']
    foreign=hou.node(sub).createNode('null','user_node')
    failed=run(f'delete_node({sub!r})',False)
    assert 'foreign' in failed['error'] and hou.node(foreign.path()) is not None,failed
    # Embedded geometry cannot enter scalar restoration; an earlier batch field stays unchanged.
    run("sk=tab_create('/obj/__tutorial_contract','kinefx::skeleton',name='skeleton')\ncreate_spare_parms(sk,spec=[{'type':'float','name':'probe','default':1}])")
    sk=g.node('skeleton'); p=sk.parm('stash')
    run("tab_create('/obj/__tutorial_contract','line',name='spine')")
    sk.setInput(0,g.node('spine'))
    # Native OnInputChanged initializes this new line; a second press may ask for overwrite confirmation.
    if p.eval() is None:
        sk.parm('stashinput').pressButton()  # H22 captures lazily; never overwrite an existing stash.
    before=p.eval().data()
    failed=run(f"set_parms({sk.path()!r},{{'probe':2,'stash':0}})",False)
    assert 'data parameters' in failed['error'] and sk.parm('probe').eval()==1,failed
    assert sk.parm('stash').eval().data()==before
    # Different domain/shape from the fern: a rectangular open sheet vs a capped duplicate.
    single=run("__result__=geo_piece_stats('/obj/__tutorial_contract/surface',inspect=True)")['result']
    assert single['boundary_edges']==4 and single['closed_planar_components']==0,single
    run("pf=tab_create('/obj/__tutorial_contract','polyfill',name='filled_again',inputs=[hou.node('/obj/__tutorial_contract/surface')])\nset_parms(pf,{'fillmode':'tris','smoothtoggle':0,'subdivtoggle':0})")
    doubled=run("__result__=geo_piece_stats('/obj/__tutorial_contract/filled_again',inspect=True)")['result']
    assert doubled['boundary_edges']==0 and doubled['closed_planar_components']==1,doubled
    assert abs(doubled['surface_area']-2*single['surface_area'])<1e-6,doubled
    # A genuine solid is not flagged as a coplanar double surface.
    run("box=tab_create('/obj/__tutorial_contract','box',name='solid')")
    solid=run("__result__=geo_piece_stats('/obj/__tutorial_contract/solid',inspect=True)")['result']
    assert solid['closed_planar_components']==0,solid
finally:
    if g is not None: g.destroy()
print('tutorial topology/ownership/data/rewiring contracts passed',hou.applicationVersionString())
