"""Isolated H21/H22 UV continuity before/after Boolean, using a simple panel.

No user asset or product dimensions. Compare independent analytic coordinates
on planar faces, including new cut faces and changed source/cutter dimensions.
This is not an arbitrary curved-surface unwrap or visual-quality certification.
"""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import hou
import dsh_bridge as bridge

def run(code):
    reply=bridge.run_code(code,owner_session='uv-construction',owner_call='fixture')
    assert reply['ok'],reply.get('error',reply)
    return reply.get('result')

mapping='''vector p=@P; vector n=abs(prim_normal(0,@primnum,.5,.5));
vector q=n.x>.9?set(p.z,p.y,0):(n.y>.9?set(p.x,p.z,0):set(p.x,p.y,0));
v@uv=q*3.0;'''
run(f'''
g=tab_create('/obj','geo','uv_construction')
a=tab_create(g,'box','panel',parms={{'size':(1.4,.9,.16)}})
at=tab_create(g,'attribwrangle','panel_role',inputs=[a],parms={{'class':'primitive','snippet':'s@source_role="panel";'}})
b=tab_create(g,'box','cutter',parms={{'size':(.45,.32,.4),'tx':.17}})
bt=tab_create(g,'attribwrangle','cutter_role',inputs=[b],parms={{'class':'primitive','snippet':'s@source_role="cutter";'}})
au=tab_create(g,'attribwrangle','panel_uv',inputs=[at],parms={{'class':'vertex','snippet':{mapping!r}}})
bu=tab_create(g,'attribwrangle','cutter_uv',inputs=[bt],parms={{'class':'vertex','snippet':{mapping!r}}})
opts={{'booleanop':'subtract','subtractchoices':'aminusb','detriangulate':'unchanged'}}
raw=tab_create(g,'boolean','raw_cut',inputs=[at,bt],parms=opts)
pre=tab_create(g,'boolean','uv_before',inputs=[au,bu],parms=opts)
post=tab_create(g,'attribwrangle','uv_after',inputs=[raw],parms={{'class':'vertex','snippet':{mapping!r}}})
bad=tab_create(g,'attribwrangle','vertex_axis_switch',inputs=[raw],parms={{'class':'vertex','snippet':'vector q=@P.x>0?set(@P.y,@P.x,0):set(@P.x,@P.y,0); v@uv=q*3;'}})
missing=tab_create(g,'boolean','missing_cutter_uv',inputs=[au,bt],parms=opts)
''')
root=hou.node('/obj/uv_construction')

def mapping_error(node,role=None,front_only=False):
    geo=node.geometry()
    assert not node.errors(),node.errors()
    assert geo.findVertexAttrib('uv')
    errors=[];roles=set();mixed_faces=0
    for prim in geo.prims():
        if prim.type()!=hou.primType.Polygon:continue
        source=prim.stringAttribValue('source_role');roles.add(source)
        n=prim.normal()
        if role and source!=role:continue
        if front_only and abs(n[2])<.99:continue
        values=[v.point().position() for v in prim.vertices()]
        mixed_faces+=bool(any(p[0]>0 for p in values) and any(p[0]<=0 for p in values))
        axis=max(range(3),key=lambda i:abs(n[i]))
        for v in prim.vertices():
            p=v.point().position();uv=v.attribValue('uv')
            expected=((p[2],p[1]) if axis==0 else (p[0],p[2]) if axis==1 else (p[0],p[1]))
            errors.append(max(abs(uv[i]-3*expected[i]) for i in range(2)))
    assert errors,'measurement must cover actual target faces'
    return {'samples':len(errors),'max_error':max(errors),'roles':sorted(roles),'mixed_faces':mixed_faces}

results=[]
for width,offset in ((1.4,.17),(1.8,-.12)):
    run(f"set_parms('/obj/uv_construction/panel',{{'sizex':{width}}});set_parms('/obj/uv_construction/cutter',{{'tx':{offset}}})")
    pre=mapping_error(root.node('uv_before'))
    post=mapping_error(root.node('uv_after'))
    bad=mapping_error(root.node('vertex_axis_switch'),front_only=True)
    missing=mapping_error(root.node('missing_cutter_uv'),role='cutter')
    assert pre['max_error']<1e-5 and post['max_error']<1e-5,(pre,post)
    assert pre['roles']==post['roles']==['cutter','panel']
    assert bad['mixed_faces']>0 and bad['max_error']>.1,bad
    assert missing['max_error']>.1,missing
    # The UV-only routes also retain the original bounding extent.
    bounds=[list(root.node(name).geometry().boundingBox().sizevec()) for name in ('raw_cut','uv_before','uv_after')]
    assert all(max(abs(a-b) for a,b in zip(bounds[0],v))<1e-6 for v in bounds[1:]),bounds
    results.append({'width':width,'cutter_offset':offset,'before':pre,'after':post,
                    'bad_vertex_switch':bad,'missing_cutter_uv':missing})
print(json.dumps({'version':hou.applicationVersionString(),'scope':'axis-aligned planar UVs, input source roles, cut faces and two dimension states','results':results}))
