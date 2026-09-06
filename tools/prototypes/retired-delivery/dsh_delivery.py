"""RETIRED v8 reference (not packaged). Bounded SOP delivery observer.

Contracts are frozen per audit; the Host retains session evidence, not Python exec.
Only the observer writes evidence; callers cannot submit a `passed=True` claim.
Every receipt rereads the actual output and graph. Unknown dependencies invalidate
the entire cache conservatively. No file writes, repairs, scene saves or UI calls.
Supported fingerprint: polygon SOP output only; no simulation/packed oracle.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time

import hou
import dsh_hou_helpers as h
import dsh_quality_contracts as q


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _keys(value, required, optional=()):
    if not isinstance(value, dict) or set(required) - value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError(f'expected fields {sorted(required)}, optional {sorted(optional)}')


def _name(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('names must be nonempty strings')


def _thread():
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('HOM observation requires the main thread')


_LIVE_TYPES = {'box','null','xform','merge','normal','attribdelete','groupcreate','groupcombine',
               'groupdelete','group','copytopoints','blast','fuse','subdivide','polybevel',
               'polyextrude','grid','line','resample','sweep','polywire','matchsize','reverse','convert','boolean'}


def type_admission(category, type_name):
    """Same static policy used by node cards, module preflight and live admission.

    Eligible type is NOT a healthy/callback-free/budget-safe node or asset proof.
    """
    eligible=category=='Sop' and type_name.split('::')[0] in _LIVE_TYPES
    return {'eligible_type':eligible,'status':'eligible_type' if eligible else 'unsupported_type',
            'type':type_name,'scope':'type-level delivery admission only; actual parameters/dependencies/output still checked',
            'reason':('Native SOP type admitted; inspect the actual output before registration.' if eligible else
                      'Not in restricted delivery type set; keep normal draft workflow and report unsupported delivery.'),
            'limits':{'direct_nodes':128,'points':15000,'primitives':10000},
            'semantic_status':'unverified'}


def resolve_scope(parent_path, output_path, controller_path, restricted=True):
    _thread()
    parent=h._resolve(parent_path); out=h._resolve(output_path); ctrl=h._resolve(controller_path)
    if (parent.childTypeCategory()!=hou.sopNodeTypeCategory() or out.parent()!=parent or ctrl.parent()!=parent
            or out.type().category()!=hou.sopNodeTypeCategory() or ctrl.type().category()!=hou.sopNodeTypeCategory()):
        raise ValueError('output/controller must be direct SOP children of one network')
    children=parent.children()
    if len(children)>(128 if restricted else 256):raise ValueError('delivery scope exceeds direct-node budget')
    if restricted:
        for n in children:
            if not type_admission(n.type().category().name(),n.type().name())['eligible_type']:
                raise ValueError(f'unsupported delivery node {n.path()} ({n.type().name()}); initial scope is native, stateless SOPs, no VEX/Python/file/solver/subnet')
            for p in n.parms():
                if p.parmTemplate().scriptCallback():
                    raise ValueError(f'callbacks are outside delivery scope: {p.path()}')
                try:
                    if p.keyframes() and p.expressionLanguage()==hou.exprLanguage.Python:
                        raise ValueError(f'Python expressions are outside delivery scope: {p.path()}')
                except hou.OperationFailed:pass
                raw=p.rawValue()
                if re.search(r'(?i)\b(python\w*|system|execute|run|unix)\s*\(|`',str(raw)):
                    raise ValueError(f'external command expression outside delivery scope: {p.path()}')
            # Include expression dependencies, not just wires. Unsupported external
            # state is rejected BEFORE cooking/perturbing, rather than cached as safe.
            for ref in n.references():
                if ref!=parent and ref!=n and ref.parent()!=parent and not ref.path().startswith(n.path()+'/'):
                    raise ValueError(f'external dependency outside delivery scope: {n.path()} -> {ref.path()}')
    return parent,out,ctrl


def inspect_scope(parent, output, controller):
    p,out,ctrl=resolve_scope(parent,output,controller)
    _,g=q._geometry(out)
    controls=[]
    for parm in ctrl.spareParms():
        if parm.parmTemplate().type() in (hou.parmTemplateType.Float,hou.parmTemplateType.Int):
            controls.append({'parm':parm.name(),'value':parm.eval(),'label':parm.parmTemplate().label()})
    groups=[pg.name() for pg in g.primGroups() if pg.prims()]
    suggestions=[]
    if 2<=len(groups)<=16 and g.intrinsicValue('primitivecount')<=10000:
        candidate={'id':'joined_parts','groups':groups,'require_closed':True}
        observed=q._check_topology(g,[candidate])
        if observed['ok'] and observed['results'][0]['selected_prims']==g.intrinsicValue('primitivecount'):
            suggestions.append({'method':'topology','candidate':candidate,
                                'reason':'These groups cover one closed shared-edge polygon surface.',
                                'boundary':'Confirm these are the required parts; observation is not a registered obligation or shape acceptance.'})
    return {'output':out.path(),'controller':ctrl.path(),'node_count':len(p.children()),
            'verification_suggestions':suggestions,
            'verification_methods':{
                'interfaces':'Independent, non-shared surface vertices -> another primitive surface; not fused shared seams.',
                'topology':'Fused polygon parts: {id,groups:[part_group,...],require_closed:true}; checks shared-edge connectivity/closure, not shape or strength.',
            },
            'control_metrics':['bounds_size','bounds_center','bounds_min','bounds_max','point_count','primitive_count','area'],
            'domain_ops':['lt','le','gt','ge','eq','ne'],
            'domain_format':{'id':'condition_id','left':'numeric_spare_name','op':'lt','right':'another_spare_name or finite number'},
            'parts':[{'group':pg.name(),'prims':len(pg.prims())} for pg in g.primGroups()],
            'surface_point_groups':[{'group':pg.name(),'points':len(pg.points())} for pg in g.pointGroups()],
            'controls':controls,'semantic_status':'unverified',
            'next_action':'Select required final groups, intended control responses and any coupled parameter-domain conditions from the user goal, then register. Observed values are NOT acceptance thresholds. Tests prove individual cases, not all parameter combinations.'}


def _polygon_digest(g):
    """Semantic polygon content, not recook-varying bgeo serialization metadata.

    Not an oracle for native/packed intrinsics. Refuse them, never P-only fallback.
    The production control checker retains its own restoration oracle separately.
    """
    if any(p.type().name() != 'Polygon' for p in g.prims()):
        raise ValueError('prototype fingerprint supports Polygon only; other representations are unverified')
    if len(g.points()) > 100000 or len(g.prims()) > 40000 or g.intrinsicValue('memoryusage') > 32*1024*1024:
        raise ValueError('prototype geometry budget exceeded')
    points = g.points(); prims = g.prims()
    vertices = [v for p in prims for v in p.vertices()]
    if len(vertices) > 200000:
        raise ValueError('prototype vertex budget exceeded')
    payload = {'topology': [[p.isClosed(), [v.point().number() for v in p.vertices()]] for p in prims]}
    for label, attrs, elements in [('point', g.pointAttribs(), points), ('prim', g.primAttribs(), prims),
                                    ('vertex', g.vertexAttribs(), vertices)]:
        payload[label] = {a.name(): [str(a.dataType()), a.size(), [e.attribValue(a) for e in elements]] for a in attrs}
    payload['detail'] = {a.name(): [str(a.dataType()), a.size(), g.attribValue(a)] for a in g.globalAttribs()}
    payload['point_groups'] = {a.name(): [p.number() for p in a.points()] for a in g.pointGroups()}
    payload['prim_groups'] = {a.name(): [p.number() for p in a.prims()] for a in g.primGroups()}
    return _hash(payload)


class DeliveryAudit:
    """Frozen obligations + fresh observation + invalidated cached control tests.

    All numeric spare controls of the named controller require an individual
    declared case. Case deltas are design inputs, NOT fitted from observations.
    Part groups must survive into final OUT. Tags do not themselves prove shape,
    provenance or physical meaning; independent design/visual review stays open.
    """
    def __init__(self, contract, *, restricted=True):
        _thread()
        self._restricted=restricted
        _keys(contract, {'parent', 'output', 'controller', 'parts', 'controls', 'interfaces'}, {'domain','topology'})
        for key in ('parent', 'output', 'controller'):
            _name(contract[key])
            if not contract[key].startswith('/'):
                raise ValueError('explicit absolute node paths required')
        for key, limit in [('parts',32), ('controls',64), ('interfaces',16)]:
            if not isinstance(contract[key],list) or len(contract[key]) > limit:
                raise ValueError(f'{key}: expected bounded list <= {limit}')
        if not contract['parts']:
            raise ValueError('at least one final-output part obligation required')
        ids = set(); groups = set(); parms = set()
        for part in contract['parts']:
            _keys(part, {'id','group','min_prims'})
            _name(part['group'])
            if part['group'] in groups: raise ValueError('duplicate part group')
            groups.add(part['group'])
            if type(part['min_prims']) is not int or part['min_prims'] < 1:
                raise ValueError('min_prims must be positive integer')
        for case in contract['controls']:
            _keys(case, {'id','parm','value','expectations'})
            _name(case['parm']); q._finite(case['value'],'value')
            if case['parm'] in parms: raise ValueError('one independent case per control in prototype')
            parms.add(case['parm'])
            if not isinstance(case['expectations'],list) or not 1 <= len(case['expectations']) <= 16:
                raise ValueError('each control needs 1..16 expectations')
            for e in case['expectations']: q._validate_expectation(e)
            if not any(e['delta'][0] > 0 or e['delta'][1] < 0 for e in case['expectations']):
                raise ValueError('control must declare a non-zero expected response')
        if contract['interfaces']: q.validate_interfaces(contract['interfaces'])
        domain=contract.get('domain',[])
        q.validate_domain(domain)
        topology=contract.get('topology',[])
        if topology:q.validate_topology(topology)
        elif not isinstance(topology,list):raise ValueError('topology must be a list')
        if any(name not in groups for c in topology for name in c['groups']):
            raise ValueError('topology groups must refer to declared delivery parts')
        for item in contract['parts'] + contract['controls'] + contract['interfaces'] + domain + topology:
            _name(item['id'])
            if item['id']=='network' or item['id'].startswith('uncovered:'):
                raise ValueError('obligation id is reserved for system evidence')
            if item['id'] in ids: raise ValueError('obligation ids must be unique')
            ids.add(item['id'])
        self._contract = copy.deepcopy(contract)
        self._contract_hash = _hash(contract)
        self._revision = None
        self._epoch = 0
        self._control_evidence = {}
        self._invalidated = []
        self._resolve()

    @property
    def contract(self):
        return copy.deepcopy(self._contract)

    def _resolve(self):
        _thread()
        c = self._contract
        return resolve_scope(c['parent'],c['output'],c['controller'],self._restricted)

    def _snapshot(self):
        parent, out, ctrl = self._resolve()
        g = out.geometry()
        if g is None or out.errors(): raise ValueError('final output has no healthy geometry')
        if self._restricted and (g.intrinsicValue('pointcount')>15000 or g.intrinsicValue('primitivecount')>10000):
            raise ValueError('initial live delivery budget exceeded: <=15000 points / 10000 primitives')
        # Include raw expressions/keys as well as actual output. Even a currently
        # invisible code change can affect later controls and must invalidate them.
        graph = []
        for n in sorted(parent.children(), key=lambda n:n.path()):
            parms = [[p.name(), p.rawValue(), [k.asCode() for k in p.keyframes()]] for p in n.parms()]
            graph.append([n.path(), n.sessionId(), n.type().name(),
                          [[con.inputIndex(), con.inputNode().path() if con.inputNode() else None, con.outputIndex()] for con in n.inputConnections()],
                          parms, list(n.errors()), list(n.warnings())])
        return _hash({'hip':hou.hipFile.path(),'parent_id':parent.sessionId(),'frame':float(hou.frame()),
                      'graph':graph,'controller_schema':ctrl.parmTemplateGroup().asCode(),
                      'output':_polygon_digest(g),'contract':self._contract_hash})

    def _sync(self):
        revision = self._snapshot()
        if revision != self._revision:
            self._invalidated = sorted(self._control_evidence)
            self._control_evidence.clear()
            self._epoch += 1
            self._revision = revision

    def _spares(self, ctrl):
        return {p.name() for p in ctrl.spareParms()
                if p.parmTemplate().type() in (hou.parmTemplateType.Float,hou.parmTemplateType.Int)}

    def _domain_rows(self, overrides=None):
        """Check current/proposed scalar values; never eval, solve or clamp."""
        _,_,ctrl=self._resolve()
        return q.domain_checks(ctrl,self._contract.get('domain',[]),overrides)

    def test_control(self, case_id):
        """One registered case; delegates mutation/restoration to existing helper.

        There is no guessed repair and no foreign override in the prototype API.
        Use only a disposable process containing an explicitly authorized asset.
        """
        self._sync()
        case = next((c for c in self._contract['controls'] if c['id'] == case_id), None)
        if case is None: raise ValueError('unknown registered control case')
        _, out, ctrl = self._resolve()
        if case['parm'] not in self._spares(ctrl):
            raise ValueError('declared control must be a numeric spare parameter on controller')
        test = {'id':case['id'],'values':{case['parm']:case['value']},'expectations':case['expectations']}
        try:
            result = h.test_controls(ctrl, out, [test], interfaces=self._contract['interfaces'] or None,
                                     domain=self._contract.get('domain'),topology=self._contract.get('topology') or None)
            after = self._snapshot()
        except Exception:
            # Never retain earlier pass rows after an uncertain/failed restoration.
            self._control_evidence.clear(); self._revision = None
            raise
        if after != self._revision:
            self._control_evidence.clear(); self._revision = None
            raise RuntimeError('control observation changed baseline state; stop and inspect, no cached pass retained')
        row = {'id':case_id,'kind':'control','status':result['status'],'parm':case['parm'], 'evidence':result,
               'next_action':'Fix the declared control dependency or response, then rerun this same case; do not fit delta to the measured result.'}
        self._control_evidence[case_id] = row
        return copy.deepcopy(row)

    def receipt(self):
        """Fresh final-output observations plus only current control evidence."""
        _thread()
        try:
            parent, out, ctrl = self._resolve()
            network = h.verify_network(parent,output=out,require_valid=False)
            self._sync()
            g = out.geometry()
            rows = [{'id':'network','kind':'network','status':'pass' if network['healthy'] else 'fail',
                     'evidence':network,'next_action':'Resolve cook errors/warnings on the explicit final network.'}]
            rows.extend(self._domain_rows())
            if self._contract.get('topology'):
                checked=q._check_topology(g,self._contract['topology'])
                rows.extend({'id':r['id'],'kind':'topology','status':r['status'],'evidence':r} for r in checked['results'])
            for part in self._contract['parts']:
                group = g.findPrimGroup(part['group'])
                count = len(group.prims()) if group is not None else 0
                rows.append({'id':part['id'],'kind':'part','status':'pass' if count >= part['min_prims'] else 'fail',
                             'group':part['group'],'actual_prims':count,'minimum_prims':part['min_prims'],
                             'next_action':'Restore this required part in the final output and recheck; a node or earlier module image is not delivery evidence.'})
            if self._contract['interfaces']:
                checked = h.geo_check_interfaces(out,self._contract['interfaces'])
                rows.extend({'id':r['id'],'kind':'interface','status':r['status'],'evidence':r,
                             'next_action':'Correct the geometry from the shared interface; keep the declared tolerance and rerun.'} for r in checked['results'])
            cases = {c['parm']:c for c in self._contract['controls']}
            spares = self._spares(ctrl)
            for name in sorted(spares - cases.keys()):
                rows.append({'id':'uncovered:'+name,'kind':'coverage','status':'unverified','parm':name,
                             'next_action':'Declare an independent intended response for this exposed control; a new contract clears old evidence.'})
            for case in self._contract['controls']:
                if case['parm'] not in spares:
                    rows.append({'id':case['id'],'kind':'control','status':'fail','reason':'missing_declared_control'})
                else:
                    rows.append(copy.deepcopy(self._control_evidence.get(case['id'],
                                {'id':case['id'],'kind':'control','status':'unverified','reason':'no_current_control_evidence',
                                 'next_action':'Run this registered control case on the current output.'})))
            status = 'fail' if any(r['status']=='fail' for r in rows) else 'unverified' if any(r['status']=='unverified' for r in rows) else 'pass'
            return {'status':status,'scope':'declared numerical obligations only','ready_for_independent_review':status=='pass',
                    'delivery_status':'partial_pending_independent_review','semantic_status':'unverified',
                    'contract_sha256':self._contract_hash,'revision':self._revision,'epoch':self._epoch,
                    'checked_at':time.time(),'output':out.path(),'invalidated_control_cases':list(self._invalidated),
                    'checks':rows,'limitations':['Group labels do not prove the promised identity or shape.',
                    'Only declared scalar-domain comparisons and individual cases are checked; not the entire parameter space.',
                    'Undeclared relationships and aesthetic quality are not certified.',
                    'All cached control evidence is conservatively invalidated on observed state changes.']}
        except (ValueError, hou.Error) as error:
            self._control_evidence.clear(); self._revision = None
            return {'status':'unverified','ready_for_independent_review':False,'delivery_status':'partial_pending_independent_review',
                    'semantic_status':'unverified','reason':str(error),'checks':[], 'contract_sha256':self._contract_hash}
