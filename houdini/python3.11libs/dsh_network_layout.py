"""Pure, deterministic rectangle primitives for network-editor planning.

No Houdini, filesystem, ownership, or mutation belongs in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import math


TOLERANCE = 1e-6
MAX_CANDIDATES = 4096
MAX_RELATION_VISITS = 250_000


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
    if not isinstance(items, (list, tuple)):
        raise ValueError('items must be a list or tuple')
    prepared = []
    for row in items:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise ValueError('each item must be [stable_key, rectangle]')
        prepared.append((len(prepared), rect(row[1])))
    pairs=[];visits=0
    def consume():
        nonlocal visits
        visits+=1
        if visits>MAX_RELATION_VISITS:raise ValueError('layout spatial relation budget exhausted')
    def compare(a,b,same=False):
        consume()
        if not same and not overlaps(a.bounds,b.bounds,touching=touching,tolerance=tolerance):return
        if a.items is not None and b.items is not None:
            for index,(first,left) in enumerate(a.items):
                for second,right in (b.items[index+1:] if same else b.items):
                    consume()
                    if overlaps(left,right,touching=touching,tolerance=tolerance):pairs.append(tuple(sorted((first,second))))
        elif same:
            compare(a.left,a.left,True);compare(a.right,a.right,True);compare(a.left,a.right)
        elif a.items is None and (b.items is not None or a.count>=b.count):
            compare(a.left,b);compare(a.right,b)
        else:compare(a,b.left);compare(a,b.right)
    if prepared:
        tree=_RectTree(prepared);compare(tree,tree,True)
    return [[str(items[a][0]),str(items[b][0])] for a,b in sorted(pairs)]


class _RectTree:
    """Deterministic spatial hierarchy; complete rectangles, no obstacle truncation."""
    __slots__ = ('bounds', 'count', 'items', 'left', 'right')

    def __init__(self, items):
        self.count = len(items)
        self.bounds = union(row[1] for row in items)
        self.left = self.right = None
        self.items = items if len(items) <= 8 else None
        if self.items is None:
            axis = 0 if self.bounds.width >= self.bounds.height else 1
            ordered = sorted(items, key=lambda row: (
                (row[1].min_x + row[1].max_x) if axis == 0 else (row[1].min_y + row[1].max_y), row[0]))
            middle = len(ordered) // 2
            self.left, self.right = _RectTree(ordered[:middle]), _RectTree(ordered[middle:])

    def blocks(self, proposal):
        if not overlaps(proposal, self.bounds): return False
        if self.items is not None:
            return any(overlaps(proposal, item) for _key, item in self.items)
        return self.left.blocks(proposal) or self.right.blocks(proposal)


def find_free_translation(subject, obstacles, *, preferred=(0, 0),
                          step=(1, 1), clearance=(0, 0), container=None,
                          max_candidates=MAX_CANDIDATES):
    """Propose one deterministic translation without mutating input data."""
    source = rect(subject)
    # Candidate search is bounded; a spatial hierarchy tests the complete
    # existing network without imposing a node-count admission rule.
    if not isinstance(obstacles, (list, tuple)):
        raise ValueError('obstacles must be a list or tuple')
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
    spatial = _RectTree(expanded) if expanded else None
    allowed = None if container is None else rect(container)

    def free(dx, dy):
        proposal = source.translated(dx, dy)
        blockers = ['obstacles'] if spatial is not None and spatial.blocks(proposal) else []
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
    incoming={key:set() for key in keys};outgoing={key:set() for key in keys}
    for source,target in edges:
        if source in incoming and target in incoming:
            incoming[target].add(source);outgoing[source].add(target)
    pending=[key for key in incoming if not incoming[key]];heapq.heapify(pending)
    remaining={key:len(rows) for key,rows in incoming.items()};result={key:0 for key in pending}
    while pending:
        key=heapq.heappop(pending)
        for target in sorted(outgoing[key]):
            result[target]=max(result.get(target,0),result[key]+1)
            remaining[target]-=1
            if not remaining[target]:heapq.heappush(pending,target)
    if any(remaining.values()):raise ValueError('dependency cycle prevents deterministic handoff layout')
    return result


def _separation_evidence(left_items, *, required_x, required_y, right_items=None):
    """Prove all pairs, aggregating separated spatial clusters without expanding them."""
    left=[(str(key),rect(value)) for key,value in left_items]
    right=left if right_items is None else [(str(key),rect(value)) for key,value in right_items]
    counts={'horizontal':0,'vertical':0};minimum={'horizontal':None,'vertical':None}
    failures=[];overlap_rows=[];visits=0
    def consume():
        nonlocal visits
        visits+=1
        if visits>MAX_RELATION_VISITS:
            raise ValueError('layout spatial relation budget exhausted; reduce the overlapping layout scope')
    def record(axis,value,count):
        counts[axis]+=count
        minimum[axis]=value if minimum[axis] is None else min(value,minimum[axis])
    def check(a_row,b_row):
        consume()
        (left_key,a),(right_key,b)=a_row,b_row
        dx,dy=axis_clearance(a,b,'x'),axis_clearance(a,b,'y')
        if overlaps(a,b):overlap_rows.append([left_key,right_key])
        if dx>=required_x-TOLERANCE:record('horizontal',dx,1)
        elif dy>=required_y-TOLERANCE:record('vertical',dy,1)
        else:failures.append({'left':left_key,'right':right_key,'horizontal':dx,'vertical':dy})
    def compare(a,b,same=False):
        consume()
        if not same:
            dx,dy=axis_clearance(a.bounds,b.bounds,'x'),axis_clearance(a.bounds,b.bounds,'y')
            if dx>=required_x-TOLERANCE:record('horizontal',dx,a.count*b.count);return
            if dy>=required_y-TOLERANCE:record('vertical',dy,a.count*b.count);return
        if a.items is not None and b.items is not None:
            for index,first in enumerate(a.items):
                for second in (b.items[index+1:] if same else b.items):check(first,second)
        elif same:
            compare(a.left,a.left,True);compare(a.right,a.right,True);compare(a.left,a.right)
        elif a.items is None and (b.items is not None or a.count>=b.count):
            compare(a.left,b);compare(a.right,b)
        else:compare(a,b.left);compare(a,b.right)
    if left and right:
        first=_RectTree(left);compare(first,first if right_items is None else _RectTree(right),right_items is None)
    pair_count=len(left)*(len(left)-1)//2 if right_items is None else len(left)*len(right)
    return {'pair_count':pair_count,'horizontal_pair_count':counts['horizontal'],
            'vertical_pair_count':counts['vertical'],
            'minimum_horizontal':minimum['horizontal'],
            'minimum_vertical':minimum['vertical'],
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
    """Keep primary wire columns, wrap wide ranks, then pack independent DAGs.

    Width is a placement objective derived from actual footprints, never a
    graph admission rule. Every rank finishes before its downstream ranks, so
    wrapping cannot reverse a real wire or hide a dependency in a new subnet.
    """
    def stable(key):return (node_map[key]['label'],key)
    members=set(members)
    incoming={key:[] for key in members};outgoing={key:[] for key in members}
    for source,target,index in edges:
        if source in members and target in members and source!=target:
            incoming[target].append((source,index));outgoing[source].append(target)
    def input_order(row):
        source,index=row
        return (index if index is not None else math.inf,stable(source))
    for rows in incoming.values():rows.sort(key=input_order)
    pairs=[(source,target) for source,target,_index in edges if source in members and target in members]
    remaining=_depths(members,[(target,source) for source,target in pairs])
    primary_parent={key:rows[0][0] for key,rows in incoming.items() if rows}
    primary_children={key:[] for key in members}
    for child,parent in primary_parent.items():primary_children[parent].append(child)
    lengths={}
    for key in sorted(members,key=lambda key:(remaining[key],stable(key))):
        lengths[key]=1+max((lengths[child] for child in primary_children[key]),default=0)
    retained_child={key:sorted(children,key=lambda child:(-lengths[child],stable(child)))[0]
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
    sizes={}
    for key in members:
        source=node_map[key]['rect'];label=node_map[key]['label']
        # Native labels start beside the tile. This is an estimated allowance,
        # not a font measurement or a substitute for final GUI inspection.
        characters=sum(2 if ord(character)>127 else 1 for character in label)
        sizes[key]=Rect(0,0,source.width*(1+characters*.13),source.height)
    gap_x=profile['node_horizontal_clearance'];gap_y=profile['node_vertical_clearance']
    local_families=[];family_bounds={}
    for family in families:
        ordered=[];seen=set()
        def visit_chain(identity):
            pending=[identity]
            while pending:
                current=pending.pop()
                if current in seen:continue
                seen.add(current);ordered.append(current)
                following=[node_chain[source] for target in reversed(chains[current])
                           for source,_index in incoming[target]]
                pending.extend(reversed(following))
        sinks=sorted((key for key in family if not outgoing[key]),key=stable)
        for key in sinks:visit_chain(node_chain[key])
        for key in sorted(family,key=stable):visit_chain(node_chain[key])
        width=_packing_width((sizes[key] for key in family),gap_x,gap_y)
        lane_sizes={identity:Rect(0,0,max(sizes[key].width for key in chains[identity]),1)
                    for identity in ordered}
        lanes=_shelf_rows(ordered,lane_sizes,width,gap_x,0)
        ranks={}
        for key in family:
            ranks.setdefault(remaining[key],{}).setdefault(lanes[node_chain[key]].max_y,[]).append(key)
        local={};top=0.0
        for rank in sorted(ranks,reverse=True):
            for row in sorted(ranks[rank],reverse=True):
                keys=ranks[rank][row]
                for key in keys:
                    size=sizes[key];x=lanes[node_chain[key]].min_x
                    local[key]=Rect(x,top-size.height,x+size.width,top)
                top=min(local[key].min_y for key in keys)-gap_y
        identity=len(local_families)
        family_bounds[identity]=union(local.values())
        local_families.append((family,ordered,local,width))
    packed=_shelf_rows(list(range(len(local_families))),family_bounds,
        _packing_width(family_bounds.values(),gap_x+profile['width_unit'],gap_y),
        gap_x+profile['width_unit'],gap_y)
    positions={};footprints={};family_rows=[]
    for identity,(family,ordered,local,width) in enumerate(local_families):
        bounds=family_bounds[identity];target=packed[identity]
        dx=target.min_x-bounds.min_x;dy=target.min_y-bounds.min_y
        for chain_identity in ordered:
            for key in chains[chain_identity]:
                source=node_map[key]['rect'];footprint=local[key].translated(dx,dy)
                positions[key]=[footprint.min_x-source.min_x,footprint.min_y-source.min_y]
                footprints[key]=footprint
        family_rows.append({'members':sorted(family,key=stable),
                            'chains':[list(chains[identity]) for identity in ordered],
                            'left':target.min_x,'right':target.max_x,
                            'bottom':target.min_y,'top':target.max_y,'packing_width':width})
    return positions,footprints,{'families':family_rows,'label_clearance':'estimated',
        'primary_edges':sorted([[parent,child] for parent,child in retained_child.items()])}


def _group_depths_readable(keys, edges):
    """A valid node DAG may produce cycles when nodes are collected into boxes."""
    adjacency={key:set() for key in keys};reverse={key:set() for key in keys}
    for source,target in edges:
        adjacency[source].add(target);reverse[target].add(source)
    seen=set();order=[]
    for first in sorted(keys):
        if first in seen:continue
        pending=[(first,False)]
        while pending:
            key,finished=pending.pop()
            if finished:order.append(key);continue
            if key in seen:continue
            seen.add(key);pending.append((key,True))
            pending.extend((target,False) for target in sorted(adjacency[key],reverse=True) if target not in seen)
    seen=set();components=[]
    for first in reversed(order):
        if first in seen:continue
        pending=[first];component=[]
        while pending:
            key=pending.pop()
            if key in seen:continue
            seen.add(key);component.append(key);pending.extend(reverse[key]-seen)
        components.append(sorted(component))
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


def _readable_groups(group_rows, local_boxes, group_edges, fixed, profile, max_candidates):
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
    if not isinstance(nodes,(list,tuple)) or not nodes:raise ValueError('nodes must be a nonempty list or tuple')
    if not isinstance(groups,(list,tuple)) or not groups:raise ValueError('groups must be a nonempty list or tuple')
    if not isinstance(obstacles,(list,tuple)):raise ValueError('obstacles must be a list or tuple')
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
    actual_members={key:set() for key in group_rows}
    for item in node_map.values():
        if item['group'] not in actual_members:raise ValueError('group membership mismatch')
        actual_members[item['group']].add(item['key'])
    if any(not members for members in actual_members.values()):raise ValueError('group membership mismatch')
    for key,row in group_rows.items():
        if set(map(str,row['members']))!=actual_members[key]:raise ValueError('group members must be exact')
    if style=='readable' and item_kind=='box':
        height=min(v[1] for v in sizes);width=min(min(v[0] for v in sizes),4*height)
    else:width=max(v[0] for v in sizes);height=max(v[1] for v in sizes)
    profile=comfortable_profile(width,height)
    if style=='readable' and item_kind=='node':
        # Leave room for the native node type, name and lock badges between tiles.
        profile['node_vertical_clearance']=2.75*height
    wire_edges=_wire_edges(edges);edge_rows=[(a,b) for a,b,_index in wire_edges]
    # Validate the actual graph once. A later grouping is allowed to fold this
    # DAG into mutually dependent groups; those groups share a condensed rank.
    if item_kind=='node':_depths(node_map,edge_rows)
    group_wires={key:[] for key in group_rows}
    for source,target,index in wire_edges:
        if source in node_map and target in node_map and node_map[source]['group']==node_map[target]['group']:
            group_wires[node_map[source]['group']].append((source,target,index))
    positions={};local_boxes={};readability={}
    for group_key in sorted(group_rows):
        members=sorted(map(str,group_rows[group_key]['members']),key=lambda key:(node_map[key]['rect'].min_x,key))
        if style=='readable':
            operation=_readable_box_members if item_kind=='box' else _readable_members
            offsets,footprints,readability[group_key]=operation(node_map,members,group_wires[group_key],profile)
            positions.update(offsets);local_rects=list(footprints.values())
        else:
            member_edges=[(a,b) for a,b,_index in group_wires[group_key]]
            depths=(_group_depths_readable(members,member_edges) if item_kind=='box'
                    else _depths(members,member_edges));rows={}
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
    fixed=[(str(key),rect(value)) for key,value in obstacles];placed=[];box_offsets={};box_rects={}
    if style=='readable':
        packed=_readable_groups(group_rows,local_boxes,group_edges,fixed,profile,max_candidates)
        if not packed['ok']:return {'ok':False,'layout_status':'blocked','reason':packed['reason'],'blocked_by':packed['blocked_by']}
        box_offsets=packed['offsets'];box_rects=packed['rectangles']
    group_depth=(_group_depths_readable(group_rows,group_edges) if style=='comfortable' else {})
    by_depth={}
    for key,depth in group_depth.items():by_depth.setdefault(depth,[]).append(key)
    max_box_height=max(item.height for item in local_boxes.values())
    for depth,row in sorted(by_depth.items()):
        cursor=0.0
        for key in sorted(row,key=lambda name:(rect(group_rows[name]['rect']).min_x,name)):
            local=local_boxes[key];preferred=(cursor-local.min_x,-depth*(max_box_height+profile['box_vertical_clearance'])-local.min_y)
            proposal=find_free_translation(local,fixed+placed,preferred=preferred,
                step=(width+profile['box_horizontal_clearance'],height+profile['box_vertical_clearance']),
                clearance=(profile['box_horizontal_clearance'],profile['box_vertical_clearance']),max_candidates=max_candidates)
            if not proposal['ok']:return {'ok':False,'layout_status':'blocked','reason':proposal['reason'],'blocked_by':proposal['blocked_by']}
            offset=proposal['translation'];box_offsets[key]=offset;box_rects[key]=local.translated(*offset);placed.append((key,box_rects[key]));cursor=box_rects[key].max_x+profile['box_horizontal_clearance']
    final_positions={}
    for key,item in node_map.items():
        gx,gy=box_offsets[item['group']];dx,dy=positions[key];final_positions[key]=[item['rect'].min_x+dx+gx,item['rect'].min_y+dy+gy]
    node_rects={key:item['rect'].translated(final_positions[key][0]-item['rect'].min_x,final_positions[key][1]-item['rect'].min_y) for key,item in node_map.items()}
    evidence=evaluate_handoff(node_rects,box_rects,
        {key:item['group'] for key,item in node_map.items()},fixed,profile)
    return {**evidence,'profile':profile,'node_positions':final_positions,
            **({'style':style,'item_kind':item_kind,'readability':readability} if style=='readable' else {}),
            'box_bounds':{key:value.as_list() for key,value in box_rects.items()}}
