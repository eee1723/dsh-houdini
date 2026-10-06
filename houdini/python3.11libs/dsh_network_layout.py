"""Pure, deterministic rectangle primitives for network-editor planning.

No Houdini, filesystem, ownership, or mutation belongs in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


TOLERANCE = 1e-6
MAX_OBSTACLES = 512
MAX_CANDIDATES = 4096
MAX_BOXES = 64


def _finite(value, name):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f'{name} must be finite')
    return number


@dataclass(frozen=True, slots=True)
class Rect:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def __post_init__(self):
        values = tuple(_finite(value, name) for value, name in zip(
            (self.min_x, self.min_y, self.max_x, self.max_y),
            ('min_x', 'min_y', 'max_x', 'max_y')))
        if values[0] > values[2] or values[1] > values[3]:
            raise ValueError('rectangle bounds must be ordered')
        for field, value in zip(('min_x', 'min_y', 'max_x', 'max_y'), values):
            object.__setattr__(self, field, value)

    @property
    def width(self): return self.max_x - self.min_x

    @property
    def height(self): return self.max_y - self.min_y

    def as_list(self): return [self.min_x, self.min_y, self.max_x, self.max_y]

    def translated(self, dx, dy):
        dx, dy = _finite(dx, 'dx'), _finite(dy, 'dy')
        return Rect(self.min_x + dx, self.min_y + dy,
                    self.max_x + dx, self.max_y + dy)

    def padded(self, left=0, right=0, bottom=0, top=0):
        left, right = _finite(left, 'left'), _finite(right, 'right')
        bottom, top = _finite(bottom, 'bottom'), _finite(top, 'top')
        if min(left, right, bottom, top) < 0:
            raise ValueError('rectangle padding must be nonnegative')
        return Rect(self.min_x - left, self.min_y - bottom,
                    self.max_x + right, self.max_y + top)


def rect(value) -> Rect:
    if isinstance(value, Rect): return value
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError('rectangle must be Rect or [min_x,min_y,max_x,max_y]')
    return Rect(*value)


def union(rectangles) -> Rect:
    items = [rect(item) for item in rectangles]
    if not items:
        raise ValueError('rectangle union requires at least one item')
    return Rect(min(item.min_x for item in items), min(item.min_y for item in items),
                max(item.max_x for item in items), max(item.max_y for item in items))


def contains(container, item, tolerance=TOLERANCE) -> bool:
    outer, inner = rect(container), rect(item)
    tolerance = _finite(tolerance, 'tolerance')
    if tolerance < 0: raise ValueError('tolerance must be nonnegative')
    return (inner.min_x >= outer.min_x - tolerance and inner.max_x <= outer.max_x + tolerance
            and inner.min_y >= outer.min_y - tolerance and inner.max_y <= outer.max_y + tolerance)


def overlaps(left, right, *, touching=False, tolerance=TOLERANCE) -> bool:
    a, b = rect(left), rect(right)
    tolerance = _finite(tolerance, 'tolerance')
    if tolerance < 0: raise ValueError('tolerance must be nonnegative')
    if touching:
        return not (a.max_x < b.min_x - tolerance or b.max_x < a.min_x - tolerance
                    or a.max_y < b.min_y - tolerance or b.max_y < a.min_y - tolerance)
    return not (a.max_x <= b.min_x + tolerance or b.max_x <= a.min_x + tolerance
                or a.max_y <= b.min_y + tolerance or b.max_y <= a.min_y + tolerance)


def axis_clearance(left, right, axis) -> float:
    a, b = rect(left), rect(right)
    if axis not in ('x', 'y', 0, 1):
        raise ValueError("axis must be 'x'/'y' or 0/1")
    if axis in ('x', 0):
        return max(b.min_x - a.max_x, a.min_x - b.max_x)
    return max(b.min_y - a.max_y, a.min_y - b.max_y)


def overlap_pairs(items, *, touching=False, tolerance=TOLERANCE):
    if not isinstance(items, (list, tuple)) or len(items) > MAX_OBSTACLES:
        raise ValueError(f'items must contain at most {MAX_OBSTACLES} entries')
    prepared = []
    for row in items:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise ValueError('each item must be [stable_key, rectangle]')
        prepared.append((str(row[0]), rect(row[1])))
    result = []
    for index, (left_key, left) in enumerate(prepared):
        for right_key, right in prepared[index + 1:]:
            if overlaps(left, right, touching=touching, tolerance=tolerance):
                result.append([left_key, right_key])
    return result


def find_free_translation(subject, obstacles, *, preferred=(0, 0),
                          step=(1, 1), clearance=(0, 0), container=None,
                          max_candidates=MAX_CANDIDATES):
    """Propose one deterministic translation without mutating input data."""
    source = rect(subject)
    if not isinstance(obstacles, (list, tuple)) or len(obstacles) > MAX_OBSTACLES:
        raise ValueError(f'obstacles must contain at most {MAX_OBSTACLES} entries')
    fixed = []
    for row in obstacles:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise ValueError('each obstacle must be [stable_key, rectangle]')
        fixed.append((str(row[0]), rect(row[1])))
    fixed.sort(key=lambda row: row[0])
    if not isinstance(preferred, (list, tuple)) or len(preferred) != 2:
        raise ValueError('preferred must be [dx,dy]')
    if not isinstance(step, (list, tuple)) or len(step) != 2:
        raise ValueError('step must be [x,y]')
    if not isinstance(clearance, (list, tuple)) or len(clearance) != 2:
        raise ValueError('clearance must be [x,y]')
    px, py = _finite(preferred[0], 'preferred x'), _finite(preferred[1], 'preferred y')
    sx, sy = _finite(step[0], 'step x'), _finite(step[1], 'step y')
    cx, cy = _finite(clearance[0], 'clearance x'), _finite(clearance[1], 'clearance y')
    if sx <= 0 or sy <= 0 or cx < 0 or cy < 0:
        raise ValueError('step must be positive and clearance nonnegative')
    if type(max_candidates) is not int or not 1 <= max_candidates <= MAX_CANDIDATES:
        raise ValueError(f'max_candidates must be integer 1..{MAX_CANDIDATES}')
    expanded = [(key, obstacle.padded(cx, cx, cy, cy)) for key, obstacle in fixed]
    allowed = None if container is None else rect(container)

    def free(dx, dy):
        proposal = source.translated(dx, dy)
        blockers = [key for key, obstacle in expanded
                    if overlaps(proposal, obstacle, touching=False)]
        if allowed is not None and not contains(allowed, proposal):
            blockers.append('container')
        return proposal, blockers

    tested = 0
    proposal, blockers = free(px, py); tested += 1
    if not blockers:
        return {'ok': True, 'translation': [px, py], 'rect': proposal.as_list(),
                'tested_candidates': tested, 'blocked_by': []}
    radius = 1
    while tested < max_candidates:
        offsets = []
        for ix in range(-radius, radius + 1):
            iy = radius - abs(ix)
            offsets.append((ix, iy))
            if iy: offsets.append((ix, -iy))
        offsets.sort(key=lambda pair: (abs(pair[0]) + abs(pair[1]),
                                       abs(pair[1]), pair[1], pair[0]))
        for ix, iy in offsets:
            if tested >= max_candidates: break
            dx, dy = px + ix * sx, py + iy * sy
            proposal, blockers = free(dx, dy); tested += 1
            if not blockers:
                return {'ok': True, 'translation': [dx, dy], 'rect': proposal.as_list(),
                        'tested_candidates': tested, 'blocked_by': []}
        radius += 1
    return {'ok': False, 'translation': None, 'rect': None,
            'tested_candidates': tested,
            'blocked_by': [key for key, _item in expanded] + (['container'] if allowed is not None else []),
            'reason': 'candidate budget exhausted'}


def comfortable_profile(width, height):
    width,height=_finite(width,'width'),_finite(height,'height')
    if width<=0 or height<=0:raise ValueError('profile dimensions must be positive')
    return {'node_horizontal_clearance':.75*width,'node_vertical_clearance':1.5*height,
            'box_side_padding':.5*width,'box_bottom_padding':.5*height,
            'box_title_allowance':1.5*height,'box_horizontal_clearance':width,
            'box_vertical_clearance':2*height,'width_unit':width,'height_unit':height}


def _depths(keys,edges):
    incoming={key:set() for key in keys}
    for source,target in edges:
        if source in incoming and target in incoming and source!=target:incoming[target].add(source)
    result={};visiting=set()
    def visit(key):
        if key in result:return result[key]
        if key in visiting:raise ValueError('dependency cycle prevents deterministic handoff layout')
        visiting.add(key);value=0 if not incoming[key] else 1+max(visit(item) for item in incoming[key])
        visiting.remove(key);result[key]=value;return value
    for key in sorted(keys):visit(key)
    return result


def _separation_evidence(left_items, *, required_x, required_y, right_items=None):
    """Measure the axis that actually provides separation for every pair."""
    left=[(str(key),rect(value)) for key,value in left_items]
    right=left if right_items is None else [(str(key),rect(value)) for key,value in right_items]
    pairs=[]
    if right_items is None:
        pairs=[(left[index],other) for index in range(len(left)) for other in left[index+1:]]
    else:
        pairs=[(a,b) for a in left for b in right]
    horizontal=[];vertical=[];failures=[];overlap_rows=[]
    for (left_key,a),(right_key,b) in pairs:
        dx,dy=axis_clearance(a,b,'x'),axis_clearance(a,b,'y')
        if overlaps(a,b):overlap_rows.append([left_key,right_key])
        candidates=[]
        if dx>=required_x-TOLERANCE:candidates.append((dx/required_x,'horizontal',dx))
        if dy>=required_y-TOLERANCE:candidates.append((dy/required_y,'vertical',dy))
        if not candidates:
            failures.append({'left':left_key,'right':right_key,'horizontal':dx,'vertical':dy})
            continue
        _ratio,axis,value=sorted(candidates,key=lambda row:(row[0],row[1]))[0]
        (horizontal if axis=='horizontal' else vertical).append(value)
    return {'pair_count':len(pairs),'horizontal_pair_count':len(horizontal),
            'vertical_pair_count':len(vertical),
            'minimum_horizontal':min(horizontal) if horizontal else None,
            'minimum_vertical':min(vertical) if vertical else None,
            'failures':failures,'overlap_pairs':overlap_rows}


def evaluate_handoff(node_rects, box_rects, node_groups, obstacles, required):
    """Validate planned or read-back rectangles and report achieved minima."""
    nodes={str(key):rect(value) for key,value in node_rects.items()}
    boxes={str(key):rect(value) for key,value in box_rects.items()}
    groups={str(key):str(value) for key,value in node_groups.items()}
    fixed=[(str(key),rect(value)) for key,value in obstacles]
    node_sep=_separation_evidence(list(nodes.items()),
        required_x=required['node_horizontal_clearance'],required_y=required['node_vertical_clearance'])
    box_sep=_separation_evidence(list(boxes.items()),
        required_x=required['box_horizontal_clearance'],required_y=required['box_vertical_clearance'])
    obstacle_sep=_separation_evidence(list(boxes.items()),right_items=fixed,
        required_x=required['box_horizontal_clearance'],required_y=required['box_vertical_clearance'])
    containment=[];side=[];bottom=[];title=[];margin_failures=[]
    for key,node in nodes.items():
        group=groups[key];box=boxes[group]
        margins={'left':node.min_x-box.min_x,'right':box.max_x-node.max_x,
                 'bottom':node.min_y-box.min_y,'title':box.max_y-node.max_y}
        if not contains(box,node):containment.append(key)
        side.extend((margins['left'],margins['right']));bottom.append(margins['bottom']);title.append(margins['title'])
        if (margins['left']<required['box_side_padding']-TOLERANCE or
                margins['right']<required['box_side_padding']-TOLERANCE or
                margins['bottom']<required['box_bottom_padding']-TOLERANCE or
                margins['title']<required['box_title_allowance']-TOLERANCE):
            margin_failures.append({'node':key,'group':group,**margins})
    clearance_failures=[]
    for domain,evidence in (('nodes',node_sep),('boxes',box_sep),('box_obstacles',obstacle_sep)):
        clearance_failures.extend({'domain':domain,**row} for row in evidence['failures'])
    clearance_failures.extend({'domain':'containment_margins',**row} for row in margin_failures)
    achieved={'node_pairs':{key:value for key,value in node_sep.items() if key not in ('failures','overlap_pairs')},
              'box_pairs':{key:value for key,value in box_sep.items() if key not in ('failures','overlap_pairs')},
              'box_obstacles':{key:value for key,value in obstacle_sep.items() if key not in ('failures','overlap_pairs')},
              'containment_margins':{'minimum_side':min(side) if side else None,
                                     'minimum_bottom':min(bottom) if bottom else None,
                                     'minimum_title':min(title) if title else None}}
    status='passed' if not(node_sep['overlap_pairs'] or box_sep['overlap_pairs'] or obstacle_sep['overlap_pairs']
                           or containment or clearance_failures) else 'blocked'
    return {'ok':status=='passed','layout_status':status,
            'node_overlap_pairs':node_sep['overlap_pairs'],'box_overlap_pairs':box_sep['overlap_pairs'],
            'obstacle_overlap_pairs':obstacle_sep['overlap_pairs'],'containment_failures':containment,
            'clearance_failures':clearance_failures,'required_clearances':dict(required),
            'achieved_clearances':achieved}


def _wire_edges(edges):
    result=[]
    for edge in edges:
        if not isinstance(edge,(list,tuple)) or len(edge) not in (2,3):
            raise ValueError('edges require [source,target] or [source,target,input_index]')
        index=None if len(edge)==2 else edge[2]
        if index is not None and (type(index) is not int or index<0):
            raise ValueError('input_index must be a nonnegative integer')
        result.append((str(edge[0]),str(edge[1]),index))
    return sorted(set(result),key=lambda row:(row[0],row[1],-1 if row[2] is None else row[2]))


def _readable_members(node_map, members, edges, profile):
    """Keep primary wire chains vertical and pack separate families beside them."""
    def stable(key):return (node_map[key]['label'],key)
    members=set(members)
    incoming={key:[] for key in members};outgoing={key:[] for key in members}
    for source,target,index in edges:
        if source in members and target in members and source!=target:
            incoming[target].append((source,index));outgoing[source].append(target)
    def input_order(row):
        source,index=row
        return (index if index is not None else MAX_OBSTACLES,stable(source))
    for rows in incoming.values():rows.sort(key=input_order)
    pairs=[(source,target) for source,target,_index in edges if source in members and target in members]
    remaining=_depths(members,[(target,source) for source,target in pairs])
    primary_parent={key:rows[0][0] for key,rows in incoming.items() if rows}
    primary_children={key:[] for key in members}
    for child,parent in primary_parent.items():primary_children[parent].append(child)
    lengths={}
    def chain_length(key):
        if key not in lengths:
            lengths[key]=1+max((chain_length(child) for child in primary_children[key]),default=0)
        return lengths[key]
    retained_child={key:sorted(children,key=lambda child:(-chain_length(child),stable(child)))[0]
                    for key,children in primary_children.items() if children}
    retained_parent={child:parent for parent,child in retained_child.items()}
    chains=[];node_chain={}
    for start in sorted((key for key in members if key not in retained_parent),key=stable):
        chain=[];current=start
        while current is not None:
            node_chain[current]=len(chains);chain.append(current);current=retained_child.get(current)
        chains.append(chain)
    neighbors={key:set(outgoing[key])|{row[0] for row in incoming[key]} for key in members}
    families=[];unvisited=set(members)
    while unvisited:
        first=min(unvisited,key=stable);pending=[first];family=set()
        while pending:
            key=pending.pop()
            if key in family:continue
            family.add(key);pending.extend(neighbors[key]-family)
        unvisited-=family;families.append(family)
    positions={};footprints={};family_rows=[];cursor=0.0
    step_y=profile['height_unit']+profile['node_vertical_clearance']
    for family in families:
        ordered=[];seen=set()
        def visit_chain(identity):
            if identity in seen:return
            seen.add(identity);ordered.append(identity)
            for target in reversed(chains[identity]):
                for source,_index in incoming[target]:visit_chain(node_chain[source])
        sinks=sorted((key for key in family if not outgoing[key]),key=stable)
        for key in sinks:visit_chain(node_chain[key])
        for key in sorted(family,key=stable):visit_chain(node_chain[key])
        family_start=cursor
        for identity in ordered:
            lane_width=0.0
            for key in chains[identity]:
                source=node_map[key]['rect'];label=node_map[key]['label']
                # A font-independent allowance, not a measurement of the GUI label.
                characters=sum(2 if ord(character)>127 else 1 for character in label)
                # Native labels start beside the tile, not inside it. Reserve
                # the full name; GUI review of long SOP names exposed overlap
                # when an assumed first 12 characters were discounted.
                label_extra=characters*source.width*.13
                footprint=Rect(cursor,remaining[key]*step_y,
                    cursor+source.width+label_extra,remaining[key]*step_y+source.height)
                positions[key]=[footprint.min_x-source.min_x,footprint.min_y-source.min_y]
                footprints[key]=footprint;lane_width=max(lane_width,footprint.width)
            cursor+=lane_width+profile['node_horizontal_clearance']
        family_rows.append({'members':sorted(family,key=stable),
                            'chains':[list(chains[identity]) for identity in ordered],
                            'left':family_start,'right':cursor-profile['node_horizontal_clearance']})
        cursor+=profile['width_unit']
    return positions,footprints,{'families':family_rows,'label_clearance':'estimated',
        'primary_edges':sorted([[parent,child] for parent,child in retained_child.items()])}


def _group_depths_readable(keys, edges):
    """A valid node DAG may produce cycles when nodes are collected into boxes."""
    adjacency={key:set() for key in keys}
    for source,target in edges:adjacency[source].add(target)
    indices={};low={};stack=[];on_stack=set();components=[]
    def visit(key):
        indices[key]=low[key]=len(indices);stack.append(key);on_stack.add(key)
        for target in sorted(adjacency[key]):
            if target not in indices:visit(target);low[key]=min(low[key],low[target])
            elif target in on_stack:low[key]=min(low[key],indices[target])
        if low[key]==indices[key]:
            component=[]
            while True:
                member=stack.pop();on_stack.remove(member);component.append(member)
                if member==key:break
            components.append(sorted(component))
    for key in sorted(keys):
        if key not in indices:visit(key)
    membership={key:str(index) for index,component in enumerate(components) for key in component}
    condensed={(membership[a],membership[b]) for a,b in edges if membership[a]!=membership[b]}
    depths=_depths(set(membership.values()),condensed)
    return {key:depths[identity] for key,identity in membership.items()}


def _packing_width(rectangles, gap_x, gap_y):
    items=list(rectangles)
    return max(max(item.width for item in items),
               math.sqrt(sum((item.width+gap_x)*(item.height+gap_y) for item in items))*1.25)


def _shelf_rows(keys, rectangles, width, gap_x, gap_y, *, top=0.0):
    """Pack actual rectangle sizes in bounded rows, preserving the supplied order."""
    result={};cursor=0.0;row_bottom=top
    for key in keys:
        source=rectangles[key]
        if cursor and cursor+source.width>width+TOLERANCE:
            top=row_bottom-gap_y;cursor=0.0;row_bottom=top
        placed=Rect(cursor,top-source.height,cursor+source.width,top)
        result[key]=placed;row_bottom=min(row_bottom,placed.min_y)
        cursor=placed.max_x+gap_x
    return result


def _ranked_box_rows(keys, rectangles, edges, gap_x, gap_y, stable):
    depths=_group_depths_readable(keys,edges)
    width=_packing_width((rectangles[key] for key in keys),gap_x,gap_y)
    result={};top=0.0
    for depth in sorted(set(depths.values())):
        row=sorted((key for key in keys if depths[key]==depth),key=stable)
        packed=_shelf_rows(row,rectangles,width,gap_x,gap_y,top=top)
        result.update(packed);top=min(item.min_y for item in packed.values())-gap_y
    return result,width


def _readable_box_members(node_map, members, edges, profile):
    members=set(members);pairs={(source,target) for source,target,_index in edges
                               if source in members and target in members and source!=target}
    sources={key:node_map[key]['rect'] for key in members}
    packed,width=_ranked_box_rows(members,sources,pairs,
        profile['node_horizontal_clearance'],profile['node_vertical_clearance'],
        lambda key:(node_map[key]['label'],key))
    offsets={key:[item.min_x-sources[key].min_x,item.min_y-sources[key].min_y]
             for key,item in packed.items()}
    return offsets,packed,{'item_kind':'box','packing_width':width,
        'label_clearance':'included_in_box_bounds','families':[],'primary_edges':[]}


def _readable_box_groups(group_rows, local_boxes, group_edges, fixed, profile, max_candidates):
    gap_x=profile['box_horizontal_clearance'];gap_y=profile['box_vertical_clearance']
    regions={role:sorted(key for key,row in group_rows.items() if row.get('role')==role)
             for role in ('controls','output','checks')}
    special={key for rows in regions.values() for key in rows}
    normal=sorted(set(group_rows)-special);desired={}
    if normal:
        desired,_width=_ranked_box_rows(normal,local_boxes,
            {(a,b) for a,b in group_edges if a in normal and b in normal},gap_x,gap_y,lambda key:key)
        construction=union(desired.values())
    else:construction=Rect(0,0,0,0)
    for role in ('controls','output','checks'):
        keys=regions[role]
        if not keys:continue
        width=_packing_width((local_boxes[key] for key in keys),gap_x,gap_y)
        if role in ('controls','output'):width=max(width,construction.width)
        packed=_shelf_rows(keys,local_boxes,width,gap_x,gap_y);bounds=union(packed.values())
        if role=='controls':dx=construction.min_x;dy=construction.max_y+gap_y-bounds.min_y
        elif role=='output':dx=construction.min_x;dy=construction.min_y-gap_y-bounds.max_y
        else:dx=construction.max_x+gap_x;dy=construction.max_y-bounds.max_y
        desired.update({key:item.translated(dx,dy) for key,item in packed.items()})
    placed=[];offsets={};rectangles={}
    for key in regions['controls']+normal+regions['output']+regions['checks']:
        source=local_boxes[key];target=desired[key]
        proposal=find_free_translation(source,fixed+placed,
            preferred=(target.min_x-source.min_x,target.min_y-source.min_y),
            step=(profile['width_unit']+gap_x,profile['height_unit']+gap_y),
            clearance=(gap_x,gap_y),max_candidates=max_candidates)
        if not proposal['ok']:return proposal
        offsets[key]=proposal['translation'];rectangles[key]=source.translated(*offsets[key])
        placed.append((key,rectangles[key]))
    return {'ok':True,'offsets':offsets,'rectangles':rectangles}


def plan_handoff(nodes, groups, edges, obstacles, *, max_candidates=MAX_CANDIDATES,
                 style='comfortable', item_kind='node'):
    """Plan box contents and group placement without Houdini or scene mutation."""
    if not isinstance(nodes,(list,tuple)) or not 1<=len(nodes)<=MAX_OBSTACLES:raise ValueError('nodes must contain 1..512 entries')
    if not isinstance(groups,(list,tuple)) or not 1<=len(groups)<=MAX_BOXES:raise ValueError('groups must contain 1..64 entries')
    if not isinstance(obstacles,(list,tuple)) or len(obstacles)>MAX_OBSTACLES-len(groups):
        raise ValueError('fixed obstacles plus movable boxes must fit the 512 rectangle budget')
    if style not in ('comfortable','readable'):raise ValueError("style must be 'comfortable' or 'readable'")
    if item_kind not in ('node','box'):raise ValueError("item_kind must be 'node' or 'box'")
    node_map={};sizes=[]
    for item in nodes:
        if not {'key','group','rect'}<=set(item) or set(item)-{'key','group','rect','label'}:
            raise ValueError('node rows require key,group,rect and optional label')
        key=str(item['key']);rectangle=rect(item['rect'])
        if key in node_map or rectangle.width<=0 or rectangle.height<=0:raise ValueError('node keys unique and rectangles nonzero')
        node_map[key]={'key':key,'group':str(item['group']),'rect':rectangle,
                       'label':str(item.get('label',key))};sizes.append((rectangle.width,rectangle.height))
    group_rows={str(row['key']):row for row in groups}
    if len(group_rows)!=len(groups) or any(not {'key','members','rect'}<=set(row)
        or set(row)-{'key','members','rect','role'} for row in groups):
        raise ValueError('group rows require unique key,members,rect and optional role')
    if set(item['group'] for item in node_map.values())!=set(group_rows):raise ValueError('group membership mismatch')
    for key,row in group_rows.items():
        if set(map(str,row['members']))!={item['key'] for item in node_map.values() if item['group']==key}:raise ValueError('group members must be exact')
    if style=='readable' and item_kind=='box':
        height=min(v[1] for v in sizes);width=min(min(v[0] for v in sizes),4*height)
    else:width=max(v[0] for v in sizes);height=max(v[1] for v in sizes)
    profile=comfortable_profile(width,height)
    if style=='readable' and item_kind=='node':
        # Leave room for the native node type, name and lock badges between tiles.
        profile['node_vertical_clearance']=2.75*height
    wire_edges=_wire_edges(edges);edge_rows=[(a,b) for a,b,_index in wire_edges]
    positions={};local_boxes={};readability={}
    for group_key in sorted(group_rows):
        members=sorted(map(str,group_rows[group_key]['members']),key=lambda key:(node_map[key]['rect'].min_x,key))
        if style=='readable':
            operation=_readable_box_members if item_kind=='box' else _readable_members
            offsets,footprints,readability[group_key]=operation(node_map,members,wire_edges,profile)
            positions.update(offsets);local_rects=list(footprints.values())
        else:
            member_edges=[(a,b) for a,b in edge_rows if a in members and b in members]
            depths=_depths(members,member_edges);rows={}
            for key in members:rows.setdefault(depths[key],[]).append(key)
            local_rects=[]
            for depth,row in sorted(rows.items()):
                cursor=0.0
                for key in sorted(row,key=lambda name:(node_map[name]['rect'].min_x,name)):
                    source=node_map[key]['rect'];x=cursor;y=-depth*(height+profile['node_vertical_clearance'])
                    positions[key]=[x-source.min_x,y-source.min_y];placed=source.translated(*positions[key]);local_rects.append(placed)
                    cursor=placed.max_x+profile['node_horizontal_clearance']
        content=union(local_rects);local_boxes[group_key]=content.padded(
            profile['box_side_padding'],profile['box_side_padding'],profile['box_bottom_padding'],profile['box_title_allowance'])
    group_edges={(node_map[a]['group'],node_map[b]['group']) for a,b in edge_rows if a in node_map and b in node_map and node_map[a]['group']!=node_map[b]['group']}
    group_depth=(_group_depths_readable(group_rows,group_edges) if style=='readable'
                 else _depths(group_rows,group_edges));by_depth={}
    if style=='readable':
        normal_depth=max((depth for key,depth in group_depth.items()
            if group_rows[key].get('role') not in ('controls','output','checks')),default=0)
        for key in group_depth:
            role=group_rows[key].get('role')
            if role=='controls':group_depth[key]=-1
            elif role=='output':group_depth[key]=normal_depth+1
    for key,depth in group_depth.items():by_depth.setdefault(depth,[]).append(key)
    fixed=[(str(key),rect(value)) for key,value in obstacles];placed=[];box_offsets={};box_rects={}
    max_box_height=max(item.height for item in local_boxes.values())
    check_rows=[key for key in group_rows if style=='readable' and group_rows[key].get('role')=='checks']
    if style=='readable' and item_kind=='box':
        packed=_readable_box_groups(group_rows,local_boxes,group_edges,fixed,profile,max_candidates)
        if not packed['ok']:return {'ok':False,'layout_status':'blocked','reason':packed['reason'],'blocked_by':packed['blocked_by']}
        box_offsets=packed['offsets'];box_rects=packed['rectangles'];check_rows=[]
    for depth,row in ([] if style=='readable' and item_kind=='box' else sorted(by_depth.items())):
        cursor=0.0
        ordered=(sorted(row) if style=='readable' else sorted(row,key=lambda name:(rect(group_rows[name]['rect']).min_x,name)))
        for key in ordered:
            if key in check_rows:continue
            local=local_boxes[key];preferred=(cursor-local.min_x,-depth*(max_box_height+profile['box_vertical_clearance'])-local.min_y)
            proposal=find_free_translation(local,fixed+placed,preferred=preferred,
                step=(width+profile['box_horizontal_clearance'],height+profile['box_vertical_clearance']),
                clearance=(profile['box_horizontal_clearance'],profile['box_vertical_clearance']),max_candidates=max_candidates)
            if not proposal['ok']:return {'ok':False,'layout_status':'blocked','reason':proposal['reason'],'blocked_by':proposal['blocked_by']}
            offset=proposal['translation'];box_offsets[key]=offset;box_rects[key]=local.translated(*offset);placed.append((key,box_rects[key]));cursor=box_rects[key].max_x+profile['box_horizontal_clearance']
    check_x=max((item.max_x for item in box_rects.values()),default=0)+profile['box_horizontal_clearance']
    check_y=0.0
    for key in sorted(check_rows):
        local=local_boxes[key]
        proposal=find_free_translation(local,fixed+placed,preferred=(check_x-local.min_x,check_y-local.max_y),
            step=(width+profile['box_horizontal_clearance'],height+profile['box_vertical_clearance']),
            clearance=(profile['box_horizontal_clearance'],profile['box_vertical_clearance']),max_candidates=max_candidates)
        if not proposal['ok']:return {'ok':False,'layout_status':'blocked','reason':proposal['reason'],'blocked_by':proposal['blocked_by']}
        offset=proposal['translation'];box_offsets[key]=offset;box_rects[key]=local.translated(*offset)
        placed.append((key,box_rects[key]));check_y=box_rects[key].min_y-profile['box_vertical_clearance']
    final_positions={}
    for key,item in node_map.items():
        gx,gy=box_offsets[item['group']];dx,dy=positions[key];final_positions[key]=[item['rect'].min_x+dx+gx,item['rect'].min_y+dy+gy]
    node_rects={key:item['rect'].translated(final_positions[key][0]-item['rect'].min_x,final_positions[key][1]-item['rect'].min_y) for key,item in node_map.items()}
    evidence=evaluate_handoff(node_rects,box_rects,
        {key:item['group'] for key,item in node_map.items()},fixed,profile)
    return {**evidence,'profile':profile,'node_positions':final_positions,
            **({'style':style,'item_kind':item_kind,'readability':readability} if style=='readable' else {}),
            'box_bounds':{key:value.as_list() for key,value in box_rects.items()}}
