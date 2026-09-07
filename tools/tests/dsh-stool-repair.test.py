"""Production creation lifecycle, aggregate preflight and actual-output relations.

Shelf replay uses the real shipped script, with UI node creation stubbed. It is
not a substitute for live GUI acceptance. No user HIP is loaded or saved.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'houdini/python3.11libs'))
import hou, soptoolutils
import dsh_hou_helpers as h
import dsh_bridge as bridge
import dsh_quality_contracts as q

root=hou.node('/obj').createNode('geo','stool_repair_fixture')
old_editor=h._network_editor;old_test=h.toolutils.testTool;old_generic=soptoolutils.genericTool
class Pane:
    parent=root
    def pwd(self):return self.parent
    def setPwd(self,n):self.parent=n
pane=Pane()
seen=[]
def test_tool(tool, kwargs):
    node=pane.parent.createNode(kwargs['toolname'])
    soptoolutils.genericTool=lambda *a,**kw:node
    exec(tool.script(),{'kwargs':kwargs})
    seen.append(node.parm('surfaceshape').evalAsString())

try:
    line=root.createNode('line');line.parmTuple('dir').set((0,0,1))
    profile=root.createNode('circle');profile.parm('type').set('poly');profile.parm('orient').set('xy');profile.parmTuple('rad').set((.025,.025))
    h._network_editor=lambda:pane;h.toolutils.testTool=test_tool
    n=h.tab_create(root,'sweep','custom',inputs=[line,profile])
    assert seen[-1]=='tube','shipped initializer must exercise the original failure'
    assert n.parm('surfaceshape').evalAsString()=='input'
    assert abs(n.geometry().boundingBox().sizevec()[0]-.05)<1e-6
    internal=h.tab_create(root,'sweep','internal',inputs=[line])
    assert internal.parm('surfaceshape').evalAsString()=='tube'
    h.build_module(root,[{'name':'override','type':'sweep','inputs':[line.name(),profile.name()],
                        'parms':{'surfaceshape':'tube','radius':.04}}],output='override')
    assert root.node('override').parm('surfaceshape').evalAsString()=='tube','explicit build parms win after initialization'
    assert abs(root.node('override').geometry().boundingBox().sizevec()[0]-.08)<1e-6
    h._network_editor=old_editor;h.toolutils.testTool=old_test;soptoolutils.genericTool=old_generic

    before=set(root.children())
    spec=[{'name':'bad_circle','type':'circle','parms':{'rad':['ch("x")',1]}},
          {'name':'bad_transform','type':'xform','inputs':[line.name()],'parms':{'scalex':1,'scaley':1}},
          {'name':'bad_tube','type':'tube','parms':{'radx':.1,'orient':'nonsense'}}]
    try:h.build_module(root,spec,output='bad_tube')
    except h.PreflightError as e:
        assert e.evidence['scene_writes']==0
        assert e.evidence['error_count']==5,e.evidence
        assert {r['node'] for r in e.evidence['errors']}=={'bad_circle','bad_transform','bad_tube'}
    else:raise AssertionError('preflight did not reject all bad fields')
    assert set(root.children())==before
    envelope=bridge.run_code(f'build_module({root.path()!r},{spec!r},output="bad_tube")')
    assert envelope['evidence'][0]['phase']=='static_preflight' and envelope['evidence'][0]['error_count']==5
    assert envelope['transaction']['status']=='no_scene_change',envelope
    card=bridge.run_code(f'r=node_info({root.path()!r},"circle"); __result__={{"type":r["type"]}}',read_only=True)
    assert any(c['components']==['radx','rady'] for c in card['evidence'][0]['tuple_components'])

    parts=[{'name':'good','type':'box'},{'name':'empty','type':'null'},
           {'name':'merged','type':'merge','inputs':['good','empty']}]
    try:h.build_module(root,parts,output='merged',required_outputs=['empty'])
    except h.CheckpointError as e:assert e.evidence['failure_reasons']==['required_output']
    else:raise AssertionError('empty required branch passed aggregate output gate')
    assert root.node('good') is None and root.node('empty') is None
    h.build_module(root,parts,output='merged',required_outputs=['good'])
    assert root.node('empty') is not None,'optional empty helpers remain legal'

    h.create_spare_parms(root,spec=[{'name':'height','type':'float','default':.5},
                                  {'name':'gap','type':'float','default':0.0}])
    relation={'id':'stack','method':'axis_gap','source_group':'upper','target_group':'lower',
              'axis':1,'gap_range':[-1e-5,1e-5],'min_overlap':.5}
    network=[{'name':'lower','type':'box','parms':{'sizey':.2,'ty':'ch("../height")'}},
             {'name':'lower_tag','type':'attribwrangle','inputs':['lower'],'parms':{'class':'primitive','snippet':'setprimgroup(0,"lower",@primnum,1);'}},
             {'name':'upper','type':'box','parms':{'sizey':.2,'ty':'ch("../height")+.2+ch("../gap")'}},
             {'name':'upper_tag','type':'attribwrangle','inputs':['upper'],'parms':{'class':'primitive','snippet':'setprimgroup(0,"upper",@primnum,1);'}},
             {'name':'assembly','type':'merge','inputs':['upper_tag','lower_tag']}]
    h.build_module(root,network,output='assembly',interfaces=[relation],required_outputs=['upper_tag','lower_tag'])
    output=root.node('assembly')
    assert h.geo_check_interfaces(output,[relation])['ok']
    root.parm('gap').set(.018)
    measured=h.geo_check_interfaces(output,[relation])
    assert not measured['ok'] and abs(measured['results'][0]['gap']-.018)<1e-6,measured
    root.parm('gap').set(0)
    test=[{'id':'translate_stack','values':{'height':.8},'expectations':[{'group':'upper','metric':'bounds_center','axis':1,'delta':[.2999,.3001]}]}]
    assert h.test_controls(root,output,test,interfaces=[relation])['ok']
    detached=[{'id':'detach','values':{'gap':.018},'expectations':[{'group':'upper','metric':'bounds_center','axis':1,'delta':[.0179,.0181]}]}]
    result=h.test_controls(root,output,detached,interfaces=[relation])
    assert not result['ok'] and result['restored'] and root.evalParm('gap')==0,result
    root.node('upper').parm('tx').set(2)
    assert not h.geo_check_interfaces(output,[relation])['ok'],'transverse separation must fail'
    root.node('upper').parm('tx').set(0)
    root.parm('gap').set(-.05)
    assert not h.geo_check_interfaces(output,[relation])['ok'],'negative overlap outside interval must fail'
    assert h.geo_check_interfaces(output,[{**relation,'target_group':'upper'}])['results'][0]['reason']=='source_and_target_overlap_cannot_self_validate'
    assert h.geo_check_interfaces(output,[{**relation,'source_group':'missing'}])['status']=='fail'
    # Unsupported source is rejected, not silently interpreted as a surface bbox.
    wire=root.createNode('line','wire')
    wg=wire.geometry().freeze();wgroup=wg.createPrimGroup('wire');wgroup.add(wg.prims())
    lower=wg.createPrimGroup('lower');point=wg.createPoint();point.setPosition((0,0,0))
    polygon=wg.createPolygon();polygon.addVertex(point);lower.add(polygon)
    assert q._check_interfaces(wg,[{**relation,'source_group':'wire'}],50000)['status']=='unverified'
    try:q.validate_interfaces([{**relation,'axis':True}])
    except ValueError:pass
    else:raise AssertionError('boolean axis accepted')
finally:
    h._network_editor=old_editor;h.toolutils.testTool=old_test;soptoolutils.genericTool=old_generic
    root.destroy()
print('stool repair lifecycle/preflight/required branches/axis gap/restoration passed: '+hou.applicationVersionString())
