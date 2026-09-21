"""Pure rectangle core regression; no Houdini dependency."""
from pathlib import Path
import math,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import dsh_network_layout as layout


def reject(fn,needle):
    try:fn()
    except Exception as error:assert needle in str(error),error
    else:raise AssertionError('expected '+needle)


a=layout.Rect(0,0,2,1);b=layout.Rect(2,0,4,1);c=layout.Rect(1,.5,3,2)
assert not layout.overlaps(a,b) and layout.overlaps(a,b,touching=True)
assert layout.overlaps(a,c) and layout.contains(layout.union([a,c]),a)
assert layout.union([a,b]).as_list()==[0.0,0.0,4.0,1.0]
assert a.padded(1,2,3,4).as_list()==[-1.0,-3.0,4.0,5.0]
assert layout.axis_clearance(a,b,'x')==0 and layout.axis_clearance(a,layout.Rect(5,0,6,1),0)==3
assert layout.overlap_pairs([['a',a],['b',b],['c',c]])==[['a','c'],['b','c']]

preferred=layout.find_free_translation(a,[['far',layout.Rect(10,10,12,12)]],preferred=(3,4))
assert preferred['ok'] and preferred['translation']==[3.0,4.0]
obstacles=[['center',layout.Rect(-.5,-.5,2.5,1.5)]]
first=layout.find_free_translation(a,obstacles,step=(3,2),max_candidates=40)
second=layout.find_free_translation(a,list(reversed(obstacles)),step=(3,2),max_candidates=40)
assert first==second and first['ok'] and first['translation']!=[0,0]
blocked=layout.find_free_translation(a,[['huge',layout.Rect(-100,-100,100,100)]],max_candidates=3)
assert not blocked['ok'] and blocked['tested_candidates']==3 and blocked['blocked_by']==['huge']
contained=layout.find_free_translation(a,[['preferred',layout.Rect(0,0,2,1)]],
    container=layout.Rect(-4,-4,4,4),step=(3,2),max_candidates=40)
assert contained['ok'] and layout.contains(layout.Rect(-4,-4,4,4),contained['rect'])
container_blocked=layout.find_free_translation(a,[],container=layout.Rect(0,0,1,1),max_candidates=4)
assert not container_blocked['ok'] and 'container' in container_blocked['blocked_by']
assert a.as_list()==[0.0,0.0,2.0,1.0] and obstacles[0][1].as_list()==[-.5,-.5,2.5,1.5]

reject(lambda:layout.Rect(2,0,1,1),'ordered')
reject(lambda:layout.Rect(0,0,math.inf,1),'finite')
reject(lambda:a.padded(-1,0,0,0),'nonnegative')
reject(lambda:layout.find_free_translation(a,[],step=(0,1)),'positive')
reject(lambda:layout.find_free_translation(a,[['x',a]]*513),'512')
reject(lambda:layout.find_free_translation(a,[],max_candidates=4097),'4096')

nodes=[
 {'key':'a','group':'source','rect':[0,0,2,1]},
 {'key':'b','group':'source','rect':[3,0,5,1]},
 {'key':'c','group':'assembly','rect':[1,-2,3,-1]},
 {'key':'d','group':'output','rect':[1,-4,3,-3]},]
groups=[{'key':'source','members':['a','b'],'rect':[-1,-1,6,2]},
        {'key':'assembly','members':['c'],'rect':[0,-3,4,0]},
        {'key':'output','members':['d'],'rect':[0,-5,4,-2]}]
planned=layout.plan_handoff(nodes,groups,[['a','c'],['b','c'],['c','d']],[['fixed',[20,-2,24,2]]])
assert planned['ok'] and planned['layout_status']=='passed'
assert not planned['node_overlap_pairs'] and not planned['box_overlap_pairs']
assert not planned['obstacle_overlap_pairs'] and not planned['containment_failures']
assert not planned['clearance_failures']
assert planned['required_clearances']['box_vertical_clearance']==2.0
assert planned['achieved_clearances']['box_pairs']['minimum_vertical']==2.0
assert planned['achieved_clearances']['containment_margins']=={
    'minimum_side':1.0,'minimum_bottom':.5,'minimum_title':1.5}
reordered=layout.plan_handoff(list(reversed(nodes)),list(reversed(groups)),[['c','d'],['b','c'],['a','c']],[['fixed',[20,-2,24,2]]])
assert reordered==planned
reject(lambda:layout.plan_handoff(nodes,groups,[['a','c'],['c','a']],[]),'cycle')

# Declared planner boundary: 512 movable nodes across 64 boxes remains bounded.
boundary_nodes=[];boundary_groups=[]
for group_index in range(64):
    members=[]
    for member_index in range(8):
        key=f'n{group_index:02d}_{member_index:02d}';members.append(key)
        boundary_nodes.append({'key':key,'group':f'g{group_index:02d}','rect':[member_index*2,0,member_index*2+1,1]})
    boundary_groups.append({'key':f'g{group_index:02d}','members':members,'rect':[0,0,16,2]})
boundary=layout.plan_handoff(boundary_nodes,boundary_groups,[],[])
assert boundary['ok'] and len(boundary['node_positions'])==512 and len(boundary['box_bounds'])==64
reject(lambda:layout.plan_handoff(boundary_nodes,boundary_groups+[{'key':'too_many','members':[],'rect':[0,0,1,1]}],[],[]),'64')
reject(lambda:layout.plan_handoff(nodes,groups,[],[['fixed',[0,0,1,1]]]*510),'512 rectangle budget')
print('pure network layout rectangle core passed')
