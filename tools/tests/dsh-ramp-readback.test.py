"""Public read_parms result composes with json.dumps inside Bridge code."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_bridge as b
g=hou.node('/obj').createNode('geo','ramp_read_fixture')
n=g.createNode('null','control')
ptg=n.parmTemplateGroup()
ptg.append(hou.RampParmTemplate('curve','Curve',hou.rampParmType.Float))
ptg.append(hou.RampParmTemplate('colors','Colors',hou.rampParmType.Color))
n.setParmTemplateGroup(ptg)
try:
 n.parm('curve').set(hou.Ramp((hou.rampBasis.Linear,hou.rampBasis.Constant),(0.,1.),(.2,.9)))
 n.parm('colors').set(hou.Ramp((hou.rampBasis.Linear,hou.rampBasis.Linear),(0.,1.),((1.,0.,0.),(0.,.5,1.))))
 before=n.asCode()
 r=b.run_code(f"import json\nrows=read_parms({n.path()!r},names=['curve','colors'])\n__result__=json.loads(json.dumps(rows,allow_nan=False))",owner_session='ramp-reader',read_only=True)
 assert r['ok'],r
 scalar,color=[x['value'] for x in r['result']]
 assert scalar['type']=='ramp' and scalar['basis']==['Linear','Constant'],scalar
 assert scalar['keys']==[0.,1.] and abs(scalar['values'][0]-.2)<1e-6
 assert color['values']==[[1.,0.,0.],[0.,.5,1.]],color
 assert n.asCode()==before
 c=g.createNode('color')
 r=b.run_code(f"import json\n__result__=json.loads(json.dumps(read_parms({c.path()!r},changed_only=False)))",owner_session='ramp-reader',read_only=True)
 assert r['ok'],r
finally:g.destroy()
print('PASS JSON-safe float/color ramp readback '+hou.applicationVersionString())
