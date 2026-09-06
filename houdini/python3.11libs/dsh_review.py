"""Short-lived review testing permission. No contract registration or evidence cache.

Only Bridge calls this service on Houdini's owning thread. Lease tokens stay in
Host transport, never model arguments. Ordinary mutation provenance is unchanged.
"""
import contextlib
import hashlib
import json
import re
import threading
import time
import uuid

import hou
import dsh_hou_helpers as h
import dsh_quality_contracts as q

# Only the temporary mutation experiment is bounded, not asset discovery or
# normal authoring. Tube is deliberately admitted; no delivery authoring gate.
_TEST_TYPES = {'box','null','xform','merge','normal','attribdelete','groupcreate','groupcombine',
               'groupdelete','group','copytopoints','blast','fuse','subdivide','polybevel',
               'polyextrude','grid','line','resample','sweep','polywire','matchsize','reverse','convert','boolean','tube','sphere'}


def _exact(value,required,optional=()):
    if not isinstance(value,dict) or set(required)-set(value) or set(value)-set(required)-set(optional):
        raise ValueError(f'expected fields {sorted(required)}, optional {sorted(optional)}')


def _graph(parent):
    data=[]
    for n in sorted([parent,*parent.children()],key=lambda n:n.path()):
        data.append([n.sessionId(),n.path(),n.type().name(),
                     [[c.inputIndex(),c.inputNode().sessionId(),c.outputIndex()] for c in n.inputConnections()],
                     [[p.name(),p.rawValue(),[k.asCode() for k in p.keyframes()]] for p in n.parms()],
                     n.parmTemplateGroup().asCode()])
    return hashlib.sha256(json.dumps(data,sort_keys=True,allow_nan=False).encode()).hexdigest()


def _safe_test_scope(parent):
    children=parent.children()
    if len(children)>128:raise ValueError('review perturbation budget: at most 128 direct SOP nodes')
    for n in children:
        if n.type().category()!=hou.sopNodeTypeCategory() or n.type().name().split('::')[0] not in _TEST_TYPES:
            raise ValueError(f'controlled perturbation unsupported for {n.path()} ({n.type().name()}); review read-only, do not replace the asset to satisfy a whitelist')
        for p in n.parms():
            if p.parmTemplate().scriptCallback():raise ValueError('review tests do not run user callbacks')
            try:
                if p.keyframes() and p.expressionLanguage()==hou.exprLanguage.Python:raise ValueError('Python expressions are not reversible review tests')
            except hou.OperationFailed:pass
            if re.search(r'(?i)\b(python\w*|system|execute|run|unix)\s*\(|`',str(p.rawValue())):
                raise ValueError('external command expression outside reversible review scope')
        for ref in n.references():
            if ref!=parent and ref!=n and ref.parent()!=parent and not ref.path().startswith(n.path()+'/'):
                raise ValueError(f'external dependency outside reversible review scope: {n.path()} -> {ref.path()}')


def _compact(result):
    """One batch only; never resend past batches or all pairwise measurements."""
    rows=[]
    for row in result.get('results',[]):
        rows.append({k:row[k] for k in ('id','values','actual_values','status','reason','response_status','geometry_changed',
            'measurements','restored','restore_errors','captures','warnings') if k in row})
        for key in ('interfaces','topology','domain'):
            checked=row.get(key)
            if checked is not None:
                entries=checked if isinstance(checked,list) else checked.get('results',[])
                rows[-1][key]=[{k:r[k] for k in ('id','status','reason','max_distance','failure_count','surface_components') if k in r} for r in entries]
    return {k:result[k] for k in ('ok','status','restored','reason','parameter_writes','semantic_status') if k in result} | {
        'cases':rows,'scope':'this batch only; response-only evidence is not design correctness',
        'baseline_checks':{key:([{k:r[k] for k in ('id','status','reason','max_distance','failure_count') if k in r}
            for r in (value if isinstance(value,list) else value.get('results',[]))])
            for key in ('baseline_interfaces','baseline_topology','baseline_domain') if (value:=result.get(key)) is not None},
        'next_action':'Inspect measurements/captured images against the user goal; no register/check/retest ledger.'}


class ReviewService:
    def __init__(self):
        self.lease=None

    def active(self):
        # Called only on the owning thread. Expiry never interrupts the middle
        # of a HOM transaction; it is observed at the next request boundary.
        if self.lease and time.monotonic()>self.lease['expires']:self.lease=None
        return self.lease is not None

    def guard_code(self,session,read_only):
        if self.active() and not read_only:
            raise ValueError('review is active on this shared scene; only queries and authorized review_test are allowed')

    def _bound(self,lease):
        if (lease['hip']!=hou.hipFile.path() or lease['parent'].sessionId()!=lease['parent_id']
                or h._resolve(lease['output_path']).sessionId()!=lease['output_id']):
            raise ValueError('review runtime/HIP/node binding changed; start a new review')
        if _graph(lease['parent'])!=lease['graph'] or float(hou.frame())!=lease['frame']:
            raise ValueError('asset parameters/network/frame changed outside this review; do not overwrite user changes or reuse earlier conclusions')

    def execute(self,request,session,call):
        if threading.current_thread() is not threading.main_thread():raise RuntimeError('review HOM requires owning thread')
        if not isinstance(session,str) or not session or not isinstance(call,str) or not call:raise ValueError('review requires Host provenance')
        action=request.get('action') if isinstance(request,dict) else None
        if action=='begin':
            _exact(request,{'action','scope'})
            if self.active():raise ValueError('another review is active')
            scope=request['scope'];_exact(scope,{'parent','output'},{'controller'})
            parent=h._resolve(scope['parent']);out=h._resolve(scope['output'])
            if parent.childTypeCategory()!=hou.sopNodeTypeCategory() or out.parent()!=parent:raise ValueError('review output must be a direct SOP child of parent')
            h._require_owned(parent,'review asset');h._require_owned(out,'review output')
            ctrl=h._resolve(scope['controller']) if scope.get('controller') else None
            if ctrl:
                if ctrl.parent()!=parent:raise ValueError('review controller must be a direct child of parent')
                h._require_owned(ctrl,'review controller')
            token=uuid.uuid4().hex
            self.lease={'token':token,'owner':session,'child':None,'parent':parent,'parent_id':parent.sessionId(),
                        'output_path':out.path(),'output_id':out.sessionId(),'controller':ctrl,
                        'controller_id':ctrl.sessionId() if ctrl else None,'hip':hou.hipFile.path(),
                        'frame':float(hou.frame()),'graph':_graph(parent),'expires':time.monotonic()+600,'failed_restore':False}
            return {'token':token,'scope':dict(scope),'test_permission':'temporary numeric controls only; no edits/saves/jobs'}
        if action=='end':
            _exact(request,{'action','token'})
            # Idempotent cleanup after expiry; never releases somebody else's lease.
            if not self.active():return {'released':True}
        if not self.active() or request.get('token')!=self.lease['token']:raise ValueError('review permission absent or expired')
        lease=self.lease
        if action in ('bind','end'):
            if session!=lease['owner']:raise ValueError('only the original Host owner can bind/release review')
            if action=='end':
                try:
                    self._bound(lease)
                    if lease['failed_restore']:raise ValueError('review had a restoration failure; inspect the scene before continuing')
                    return {'released':True}
                finally:self.lease=None
            _exact(request,{'action','token','child'})
            if not isinstance(request['child'],str) or not request['child'] or request['child']==session or lease['child']:
                raise ValueError('review must bind exactly one independent child')
            lease['child']=request['child'];return {'bound':True}
        if action!='test':raise ValueError('unknown review action')
        _exact(request,{'action','token','request'})
        if session!=lease['child']:raise ValueError('review test belongs to a different child')
        if lease['failed_restore']:raise ValueError('previous restoration failed; stop review')
        self._bound(lease)
        spec=request['request'];_exact(spec,set(),{'tests','views','interfaces','topology','domain'})
        for key,validate in (('interfaces',q.validate_interfaces),('topology',q.validate_topology),('domain',q.validate_domain)):
            if key in spec:validate(spec[key])
        if spec.get('domain') and lease['controller'] is None:raise ValueError('domain needs the bound controller')
        tests=spec.get('tests',[]);views=spec.get('views',[])
        q.validate_capture_views(views)
        if not isinstance(tests,list) or len(tests)>16:raise ValueError('review_test.tests requires 0..16 cases')
        if len(views)*(len(tests)+1)>8:raise ValueError('at most 8 review images per batch, including baseline')
        out=h._resolve(lease['output_path']);ctrl=lease['controller']
        if tests:
            if ctrl is None or ctrl.sessionId()!=lease['controller_id']:raise ValueError('this review has no bound controller')
            try:
                _safe_test_scope(lease['parent'])
            except ValueError as error:
                return {'status':'unverified','reason':str(error),'parameter_writes':0,'restored':True,
                        'semantic_status':'unverified','cases':[],'next_action':'Use read-only evidence; this test method does not support the asset.'}
            numeric={p.name() for p in ctrl.spareParms() if p.parmTemplate().type() in (hou.parmTemplateType.Float,hou.parmTemplateType.Int)}
            for case in tests:
                if not isinstance(case,dict) or not isinstance(case.get('values'),dict) or not set(case['values'])<=numeric:
                    raise ValueError('review tests may change only numeric spare controls of the bound controller')
        try:
            baseline=q.capture_views(out,views)
            if not tests:
                network=h.verify_network(lease['parent'],output=out,require_valid=False)
                _,g=q._geometry(out)
                interfaces=q._check_interfaces(g,spec['interfaces'],50000) if spec.get('interfaces') else None
                topology=q._check_topology(g,spec['topology']) if spec.get('topology') else None
                domain=q.domain_checks(ctrl,spec['domain']) if spec.get('domain') and ctrl else []
                return {'status':'unverified','captures':baseline,'semantic_status':'unverified','restored':True,
                        'network':{k:network[k] for k in ('healthy','nonempty','warning_free','failure_reasons','error_nodes','warning_nodes') if k in network},
                        'groups':[{'group':p.name(),'prims':len(p.prims())} for p in g.primGroups()],
                        'point_groups':[{'group':p.name(),'points':len(p.points())} for p in g.pointGroups()],
                        'controls':[{'parm':p.name(),'value':p.eval()} for p in ctrl.spareParms() if p.parmTemplate().type() in (hou.parmTemplateType.Float,hou.parmTemplateType.Int)] if ctrl else [],
                        'interfaces':interfaces,'topology':topology,'domain':domain}
            # Narrow internal capability, not an allow_foreign string supplied by
            # the model and not a change to the node's durable/runtime owner.
            with h._review_parameter_access(session,ctrl):
                result=q.test_controls(ctrl,out,tests,interfaces=spec.get('interfaces'),domain=spec.get('domain'),
                                       topology=spec.get('topology'),views=views,response_only=True)
            self._bound(lease)
            return _compact(result) | {'baseline_captures':baseline}
        except BaseException as error:
            if isinstance(error,h.CheckpointError):lease['failed_restore']=True
            raise
