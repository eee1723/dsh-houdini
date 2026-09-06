"""Historical v8 reuse regression, excluded from the current test suite."""
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_bridge as b
from dsh_execution_effects import permits_numerical_reobserve as candidate

positive=[
    "print(verb_help('render_view'))",
    "r=render_view('/obj/g/OUT', direction='iso', coverage=0.62, picture='$HIP/render/a.png')\n__result__={'check':r['check']}",
    "lay=layout_nodes('/obj/g')\nout=sop_set_output('/obj/g/OUT')\nsave=scene_save()\n__result__={'layout_ok':bool(lay),'save':save}",
    "r=render_view('/obj/g/OUT')\n__result__={k:r.get(k) for k in ('ok','check','stale')}",
    "__result__={'scene':scene_info(),'nodes':find_nodes('/obj')}",
]
negative=[
    "set_parms('/obj/g/C',{'size':1})", "r=hou.node('/obj/g').geometry()",
    "import hou\nprint(scene_info())",
    "f=scene_save\nf()", "scene_save=lambda:None\nscene_save()", "getattr(hou,'node')('/obj')",
    "r=render_view('/obj/g/OUT')\nr.__class__", "for i in range(2):\n scene_info()",
    "__result__={scene_save:scene_save() for scene_save in (1,)}", "__result__=globals()",
    "render_view('/obj/g/OUT',**{})", "[set_parm('a','b',1) for i in (1,)]",
]
for code in positive:assert candidate(code),code
for code in negative:assert not candidate(code),code
assert candidate('__result__=1')

root=hou.node('/obj').createNode('geo','__evidence_reuse')
try:
    box=root.createNode('box','shape');out=root.createNode('null','OUT');out.setInput(0,box)
    with tempfile.TemporaryDirectory(prefix='dsh-evidence-reuse-') as tmp:
        hou.hipFile.save((Path(tmp)/'scene.hip').as_posix())
        owner={'owner_session':'reuse','owner_call':'test'}
        with b.dsh_hou_helpers._execution_owner('reuse','setup'):b.dsh_hou_helpers._register_owned_node(root)
        epoch=b._MUTATION_EPOCH
        r=b.run_code(f"layout_nodes({root.path()!r})\nsop_set_output({out.path()!r})\nscene_save()",**owner)
        assert r['ok'] and r['deliveryEffect']['numerical']=='reobserve' and b._MUTATION_EPOCH==epoch,r
        r=b.run_code("print(verb_help('render_view'))",**owner)
        assert r['ok'] and b._MUTATION_EPOCH==epoch,r
        # Headless can't perform OpenGL; substitute only the rendering service for
        # the policy test. Real source unchanged checking is separate from this stub.
        original=b._VERBS['render_view']
        try:
            b._VERBS['render_view']=lambda *a,**k:{'ok':True,'check':{'pixels':'fixture'}}
            r=b.run_code(f"r=render_view({out.path()!r})\n__result__={{k:r.get(k) for k in ('ok','check')}}",**owner)
            assert r['ok'] and b._MUTATION_EPOCH==epoch,r
            b._VERBS['render_view']=lambda *a,**k:{'ok':False,'errors':['render failed']}
            r=b.run_code(f"render_view({out.path()!r})",**owner)
            assert r['ok'] and r['deliveryEffect']['numerical']=='invalidate' and b._MUTATION_EPOCH>epoch,r
            epoch=b._MUTATION_EPOCH
            b._VERBS['render_view']=lambda *a,**k:{'ok':True,'user_state_restored':False}
            r=b.run_code(f"render_view({out.path()!r})",**owner)
            assert r['deliveryEffect']['numerical']=='invalidate' and b._MUTATION_EPOCH>epoch,r
        finally:b._VERBS['render_view']=original
        r=b.run_code("render_view('/missing',name='invalid')",**owner)
        assert not r['ok'] and r['deliveryEffect']['numerical']=='invalidate' and b._MUTATION_EPOCH>epoch,r
        epoch=b._MUTATION_EPOCH
        r=b.run_code(f"set_parm({box.path()!r},'sizex',1)",**owner)
        assert r['ok'] and b._MUTATION_EPOCH>epoch,r  # equal value setter is still a mutation
        epoch=b._MUTATION_EPOCH
        r=b.run_code("import math\n__result__=math.sqrt(1)",**owner)
        assert r['ok'] and b._MUTATION_EPOCH>epoch,r
        # Certificate cannot be assigned into the result by model code.
        r=b.run_code("__result__={'deliveryEffect':{'numerical':'reobserve'}}\nraise Exception('failure')",**owner)
        assert not r['ok'] and r['deliveryEffect']['numerical']=='invalidate'
finally:root.destroy()
print('evidence reobservation policy/unknown/failure/alias/shadowing regressions passed')
