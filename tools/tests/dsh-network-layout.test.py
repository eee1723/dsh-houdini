"""Pure rectangle core regression; no Houdini dependency."""
from pathlib import Path
import math,random,sys,time,tracemalloc
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
large_obstacles = [[str(i), layout.Rect(i * 3, 10, i * 3 + 2, 11)] for i in range(600)]
large_obstacles.append(['late blocker', a])
large = layout.find_free_translation(a, large_obstacles, max_candidates=40)
assert large['ok'] and large['translation'] != [0, 0]
assert all(not layout.overlaps(large['rect'], r) for _, r in large_obstacles)
assert layout.find_free_translation(a, large_obstacles, preferred=(0, -3))['translation'] == [0, -3]
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

# Network size is not a layout admission rule. Hierarchical evidence covers
# complete large scopes while only descending into nearby rectangle clusters.
boundary_nodes=[];boundary_groups=[]
for group_index in range(70):
    members=[]
    for member_index in range(16):
        key=f'n{group_index:02d}_{member_index:02d}';members.append(key)
        boundary_nodes.append({'key':key,'group':f'g{group_index:02d}','rect':[member_index*2,0,member_index*2+1,1]})
    boundary_groups.append({'key':f'g{group_index:02d}','members':members,'rect':[0,0,16,2]})
boundary=layout.plan_handoff(boundary_nodes,boundary_groups,[],[])
assert boundary['ok'] and len(boundary['node_positions'])==1120 and len(boundary['box_bounds'])==70
late_obstacles=[[f'far{i}',[i*5,10000,i*5+2,10002]] for i in range(700)]
late_obstacles.append(['late blocker',boundary['box_bounds']['g00']])
blocked_boundary=layout.plan_handoff(boundary_nodes,boundary_groups,[],late_obstacles)
assert blocked_boundary['ok'] and not blocked_boundary['obstacle_overlap_pairs']
assert blocked_boundary['box_bounds']['g00']!=boundary['box_bounds']['g00']

# Readable layout follows connections, not the previous row or input list order.
def readable_fixture(names, edges, *, labels=None):
    rows=[{'key':name,'group':'model','rect':[index*3,index%2,index*3+2,index%2+1],
           'label':(labels or {}).get(name,name)} for index,name in enumerate(names)]
    boxes=[{'key':'model','members':list(names),'rect':[0,0,20,10]}]
    result=layout.plan_handoff(rows,boxes,edges,[],style='readable')
    assert result['ok'] and not result['clearance_failures'],result
    assert not result['node_overlap_pairs'] and not result['containment_failures'],result
    repeated=layout.plan_handoff(list(reversed(rows)),list(reversed(boxes)),
                                 list(reversed(edges)),[],style='readable')
    assert repeated==result
    return result

side=readable_fixture(['root','middle','out','side_root','side_end'],
    [['root','middle',0],['middle','out',0],['side_root','side_end',0],['side_end','out',1]])
p=side['node_positions']
assert p['root'][0]==p['middle'][0]==p['out'][0]
assert p['side_root'][0]==p['side_end'][0]>p['out'][0]
assert p['root'][1]>p['middle'][1]>p['out'][1]
assert p['side_end'][1]==p['middle'][1]
assert side['readability']['model']['families'][0]['chains']==[
    ['root','middle','out'],['side_root','side_end']]

short=readable_fixture(['a','b','c','d','cutter'],
    [['a','b',0],['b','c',0],['c','d',0],['cutter','d',1]])
assert short['node_positions']['cutter'][1]==short['node_positions']['c'][1]
assert short['node_positions']['cutter'][1]<short['node_positions']['a'][1]

fork=readable_fixture(['root','p','q','v','w','out'],
    [['root','p',0],['p','q',0],['root','v',0],['v','w',0],['q','out',0],['w','out',1]])
p=fork['node_positions']
assert p['root'][0]==p['p'][0]==p['q'][0]==p['out'][0]
assert p['v'][0]==p['w'][0]!=p['root'][0]
assert p['root'][1]>p['v'][1] and p['q'][1]>p['out'][1]
assert sum('root' in chain for family in fork['readability']['model']['families']
           for chain in family['chains'])==1

separate=readable_fixture(['a','b','c','d'],[['a','b'],['c','d']])
families=separate['readability']['model']['families']
assert len(families)==2
assert not layout.overlaps(
    [families[0][key] for key in ('left','bottom','right','top')],
    [families[1][key] for key in ('left','bottom','right','top')])
assert {tuple(family['members']) for family in families}=={('a','b'),('c','d')}
assert separate['node_positions']['a'][0]==separate['node_positions']['b'][0]
assert separate['node_positions']['c'][0]==separate['node_positions']['d'][0]

# Short pipelines should remain readable as pipelines, not become an unbounded
# horizontal catalogue. Connected fanout also wraps without reversing a wire.
pipeline_names=[];pipeline_edges=[]
for index in range(96):
    chain=[f'branch{index:03d}_{step}' for step in range(3)]
    pipeline_names.extend(chain);pipeline_edges.extend(zip(chain,chain[1:]))
disconnected=readable_fixture(pipeline_names,pipeline_edges)
disconnected_bounds=layout.rect(disconnected['box_bounds']['model'])
assert disconnected_bounds.width<200 and disconnected_bounds.height<200,disconnected_bounds
for index in range(96):
    xs={disconnected['node_positions'][f'branch{index:03d}_{step}'][0] for step in range(3)}
    assert max(xs)-min(xs)<layout.TOLERANCE
connected_edges=pipeline_edges+[[f'branch{index:03d}_2','out',index] for index in range(96)]
fanout=readable_fixture(pipeline_names+['out'],connected_edges)
fanout_bounds=layout.rect(fanout['box_bounds']['model'])
assert fanout_bounds.width<200 and fanout_bounds.height<200,fanout_bounds
for result,edges in ((disconnected,pipeline_edges),(fanout,connected_edges)):
    for source,target,*_ in edges:
        assert result['node_positions'][source][1]>result['node_positions'][target][1],(source,target)
# Contracting primary paths can introduce a grouping cycle in a valid DAG.
# Packing must still use actual ranks rather than inventing a path-block order.
cross=readable_fixture(['a','b','c','side','tail'],
    [['a','b',0],['b','c',0],['a','side',0],['side','c',1],['c','tail',0]])
for source,target in (('a','b'),('b','c'),('a','side'),('side','c'),('c','tail')):
    assert cross['node_positions'][source][1]>cross['node_positions'][target][1]

plain=readable_fixture(['a','b'],[])
long_label=readable_fixture(['a','b'],[],labels={'a':'a_very_long_human_readable_source_geometry_label'})
assert long_label['box_bounds']['model'][2]-long_label['box_bounds']['model'][0] > \
       plain['box_bounds']['model'][2]-plain['box_bounds']['model'][0]
assert long_label['readability']['model']['label_clearance']=='estimated'

role_nodes=[{'key':key,'group':key,'rect':[0,0,2,1],'label':'Ordinary node'}
            for key in ('begin','build','finish','inspect')]
role_groups=[{'key':key,'members':[key],'rect':[0,0,3,2],'role':role}
             for key,role in (('begin','controls'),('build','model'),('finish','output'),('inspect','checks'))]
role_plan=layout.plan_handoff(role_nodes,role_groups,[],[],style='readable')
assert role_plan['ok'],role_plan
boxes=role_plan['box_bounds']
assert boxes['begin'][1]>boxes['build'][3]
assert boxes['finish'][3]<boxes['build'][1]
assert boxes['inspect'][0]>max(boxes[key][2] for key in ('begin','build','finish'))
assert layout.plan_handoff(list(reversed(role_nodes)),list(reversed(role_groups)),[],[],
                           style='readable')==role_plan

# Cross-box feedback after grouping does not mean the SOP graph has a cycle.
grouped_nodes=[{'key':key,'group':group,'rect':[0,0,2,1]}
               for key,group in (('a','left'),('b','right'),('c','left'))]
grouped_boxes=[{'key':'left','members':['a','c'],'rect':[0,0,4,4]},
               {'key':'right','members':['b'],'rect':[0,0,4,4]}]
grouped_edges=[['a','b',0],['b','c',0]]
assert layout.plan_handoff(grouped_nodes,grouped_boxes,grouped_edges,[],style='readable')['ok']
assert layout.plan_handoff(grouped_nodes,grouped_boxes,grouped_edges,[])['ok']
reject(lambda:readable_fixture(['a','b'],[['a','b',0],['b','a',0]]),'cycle')
for style in ('comfortable','readable'):
    reject(lambda:layout.plan_handoff([{'key':'a','group':'g','rect':[0,0,2,1]}],
        [{'key':'g','members':['a'],'rect':[0,0,2,1]}],[['a','a']],[],style=style),'cycle')
reject(lambda:layout.plan_handoff(nodes,groups,[],[],style='invented'),'style')
reject(lambda:layout.plan_handoff(nodes,groups,[['a','c',-1]],[],style='readable'),'input_index')

# Component layout treats existing leaf boxes as rectangles, not large text glyphs.
box_sizes=[(100,5),(12,18),(9,4),(8,7),(5,3),(3,1)]
box_items=[{'key':f'leaf{index}','group':'component','rect':[0,0,width,height],
            'label':'A very long descriptive title for this existing leaf box'}
           for index,(width,height) in enumerate(box_sizes)]
box_groups=[{'key':'component','members':[row['key'] for row in box_items],'rect':[0,0,500,500]}]
packed=layout.plan_handoff(box_items,box_groups,[],[],style='readable',item_kind='box')
assert packed['ok'] and not packed['clearance_failures'],packed
bounds=layout.rect(packed['box_bounds']['component'])
assert bounds.width<=110 and bounds.height<50,bounds
assert packed['profile']['width_unit']==3 and packed['profile']['height_unit']==1
assert len({value[1] for value in packed['node_positions'].values()})>1
short_titles=[{**row,'label':'Leaf'} for row in box_items]
assert layout.plan_handoff(short_titles,box_groups,[],[],style='readable',item_kind='box')[
    'box_bounds']==packed['box_bounds']
assert layout.plan_handoff(list(reversed(box_items)),box_groups,[],[],style='readable',
                           item_kind='box')==packed
for index,item in enumerate(box_items):
    x,y=packed['node_positions'][item['key']];width,height=box_sizes[index]
    placed=layout.Rect(x,y,x+width,y+height)
    assert layout.contains(bounds,placed)

parallel_items=[{'key':f'leaf{index:02d}','group':f'component{index:02d}',
                 'label':'Existing leaf','rect':[0,0,10+index%3,4+index%2]} for index in range(20)]
parallel_groups=[{'key':row['group'],'members':[row['key']],'rect':[0,0,100,100]}
                 for row in parallel_items]
parallel=layout.plan_handoff(parallel_items,parallel_groups,[],[],style='readable',item_kind='box')
assert parallel['ok'] and not parallel['clearance_failures'],parallel
canvas=layout.union(parallel['box_bounds'].values())
assert canvas.width<150 and .5<canvas.width/canvas.height<2.5,canvas
assert len({bounds[3] for bounds in parallel['box_bounds'].values()})>1
node_groups=layout.plan_handoff(parallel_items,parallel_groups,[],[],style='readable')
assert node_groups['ok'] and not node_groups['clearance_failures'],node_groups
node_canvas=layout.union(node_groups['box_bounds'].values())
assert node_canvas.width<400 and len({bounds[3] for bounds in node_groups['box_bounds'].values()})>1,node_canvas

box_roles=layout.plan_handoff(role_nodes,role_groups,[],[],style='readable',item_kind='box')
assert box_roles['ok'],box_roles
boxes=box_roles['box_bounds']
assert boxes['begin'][1]>boxes['build'][3]
assert boxes['finish'][3]<boxes['build'][1]
assert boxes['inspect'][0]>boxes['build'][2]
reject(lambda:layout.plan_handoff(nodes,groups,[],[],item_kind='text'),'item_kind')

# The spatial proof must match brute force, including contained, coincident,
# broad and late rectangles. Every pair is accounted for, never sampled.
rng=random.Random(31)
for count in (1,9,65):
    values=[]
    for index in range(count):
        x,y=rng.uniform(-30,30),rng.uniform(-30,30)
        values.append((str(index),layout.Rect(x,y,x+rng.uniform(.1,20),y+rng.uniform(.1,20))))
    for other in (None,list(reversed(values))):
        evidence=layout._separation_evidence(values,required_x=.75,required_y=1.5,right_items=other)
        pairs=[(a,b) for i,a in enumerate(values) for b in (values[i+1:] if other is None else other)]
        expected={tuple(sorted((a[0],b[0]))) for a,b in pairs
                  if layout.axis_clearance(a[1],b[1],'x')<.75-layout.TOLERANCE
                  and layout.axis_clearance(a[1],b[1],'y')<1.5-layout.TOLERANCE}
        actual={tuple(sorted((row['left'],row['right']))) for row in evidence['failures']}
        assert actual==expected
        assert evidence['pair_count']==len(pairs)
        assert evidence['horizontal_pair_count']+evidence['vertical_pair_count']+len(evidence['failures'])==len(pairs)
budget=layout.MAX_RELATION_VISITS
layout.MAX_RELATION_VISITS=32
try:
    reject(lambda:layout._separation_evidence([(str(i),[0,0,2,1]) for i in range(100)],
        required_x=.75,required_y=1.5),'relation budget')
finally:layout.MAX_RELATION_VISITS=budget

# Long valid wires exceed Python's recursion depth. Sparse verification should
# not allocate or visit all 4.5 million node pairs in this chain.
count=3000
chain_nodes=[{'key':f'n{i:04d}','group':'chain','rect':[0,0,2,1]} for i in range(count)]
chain_groups=[{'key':'chain','members':[row['key'] for row in chain_nodes],'rect':[0,0,2,1]}]
chain_edges=[[chain_nodes[i]['key'],chain_nodes[i+1]['key'],0] for i in range(count-1)]
tracemalloc.start();started=time.monotonic()
for style in ('comfortable','readable'):
    large_chain=layout.plan_handoff(chain_nodes,chain_groups,chain_edges,[],style=style)
    assert large_chain['ok'] and len(large_chain['node_positions'])==count
    assert large_chain['achieved_clearances']['node_pairs']['pair_count']==count*(count-1)//2
_current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
assert peak<64*1024*1024,peak
print(f'3000-node layouts: {time.monotonic()-started:.3f}s, peak {peak/1024/1024:.1f} MiB')
print('pure network layout rectangle core passed')
