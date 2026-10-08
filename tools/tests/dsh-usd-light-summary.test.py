"""USD light schema classification, with no renderer, GUI or user scene."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
from pxr import Usd,UsdLux,UsdGeom
import dsh_hou_helpers as h

def check():
    # Keep all temporary USD handles in this function, released before Houdini
    # interpreter shutdown; the real LOP path is exercised by the material test.
    stage=Usd.Stage.CreateInMemory()
    UsdLux.DomeLight.Define(stage,'/Dome')
    mesh=UsdGeom.Mesh.Define(stage,'/EmissiveMesh')
    UsdLux.LightAPI.Apply(mesh.GetPrim())
    UsdLux.LightFilter.Define(stage,'/Filter')
    # This test supplies an in-memory USD stage; constructing a native LOP
    # would not contribute to the schema check. The material-delivery test
    # separately exercises the actual LOP, DomeLight_1 and consumer render.
    node=SimpleNamespace(path=lambda:'/in_memory/light_summary_fixture',errors=lambda:(),warnings=lambda:())
    with patch.object(h,'_lop_stage',return_value=(node,stage)):
        summary=h.usd_stage_summary(node)
    assert {p['path'] for p in summary['prims']['lights']}=={'/Dome','/EmissiveMesh'},summary
    assert {p['path'] for p in summary['prims']['geometry']}=={'/EmissiveMesh'},summary
    assert '/Filter' in {p['path'] for p in summary['prims']['other']},summary
    print('USD light schema summary passed',hou.applicationVersionString(),summary['prims']['lights'])

check()
