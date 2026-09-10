"""Bounded risk rejection and Manual metadata behavior, no unsafe loops executed."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou
import dsh_bridge as b
import dsh_hou_helpers as h
from dsh_cook_control import validate_vex

for code in ['while(npoints(0)>0) removepoint(0,npoints(0)-1);',
             'while (nprimitives(0) > 0) { removeprim(0,0,1); }']:
    try:validate_vex(code)
    except (ValueError, RuntimeError) as error:
        assert 'unsafe VEX deletion loop' in str(error)
    else:raise AssertionError('unsafe deletion loop accepted')
validate_vex('for(int i=npoints(0)-1;i>=0;i--) removepoint(0,i);')
validate_vex('// while(npoints(0)>0) removepoint(0,0);\nfloat x=1;')
with h._execution_owner('cook-test','setup'):
    g=h.tab_create('/obj','geo',name='cook_test')
    n=h.tab_create(g,'box')
    w=h.tab_create(g,'attribwrangle')
    h.set_update_mode('manual','auto')
    assert h.scene_info()['update_mode']=='manual'
    assert h.describe(n)['geometry_status']=='not_evaluated_manual'
    assert h.cook_node(n)['status']=='not_cooked_manual'
    before=w.parm('snippet').unexpandedString()
    try:h.set_parms(w,{'snippet':'while(npoints(0)>0) removepoint(0,0);'})
    except (ValueError, RuntimeError) as error:
        assert 'unsafe VEX deletion loop' in str(error)
    else:raise AssertionError('unsafe source written')
    assert w.parm('snippet').unexpandedString()==before
    r=b.run_code("set_update_mode('auto','manual')",owner_session='cook-test',read_only=True)
    assert not r['ok'] and hou.updateModeSetting()==hou.updateMode.Manual
    h.set_update_mode('auto','manual')
    assert h.cook_node(n,timeout_ms=1000)['ok']
    g.destroy()
print('cook risk/Manual metadata/mode guard passed '+hou.applicationVersionString())
