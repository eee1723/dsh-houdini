"""Bounded same-runtime request receipts; no HOM, replay or automatic resubmit."""
import hashlib
import json
import threading
import time


class RequestRegistry:
    def __init__(self, runtime_id, limit=4096, result_bytes=64*1024*1024, retention=600):
        self.runtime_id=runtime_id
        self.limit=limit
        self.result_bytes=result_bytes
        self.retention=retention
        self.lock=threading.Lock()
        self.records={}
        self.bytes=0

    def _expire(self):
        now=time.monotonic()
        for r in self.records.values():
            if r.get('payload') is not None and not r.get('job_id') and now-r['finished']>self.retention:
                self.bytes-=r['bytes'];r['payload']=None;r['status']='result_expired'

    def reserve(self, ref, owner, payload):
        if not isinstance(ref,str) or not ref.startswith(self.runtime_id+'.'):
            raise ValueError('request_ref runtime mismatch; do not resubmit under a new runtime')
        suffix=ref[len(self.runtime_id)+1:]
        if len(suffix)!=32 or any(c not in '0123456789abcdef' for c in suffix):
            raise ValueError('invalid request_ref')
        if not isinstance(owner,str) or not owner:
            raise ValueError('request tracking requires owner_session')
        digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        with self.lock:
            self._expire()
            if ref in self.records:
                r=self.records[ref]
                if r['owner']!=owner or r['digest']!=digest:
                    raise ValueError('request_ref payload/owner conflict; original operation not repeated')
                return False
            # Retain tombstones until this runtime ends; capacity fails closed.
            if len(self.records)>=self.limit:
                raise ValueError('request receipt capacity reached; no execution admitted')
            self.records[ref]={'owner':owner,'digest':digest,'status':'queued','payload':None,
                               'finished':None,'bytes':0,'owner_call':payload.get('owner_call'),
                               'kind':payload.get('request_kind','exec'),'admitted_at':time.time()}
            return True

    def running(self, ref):
        with self.lock:self.records[ref]['status']='running'

    def complete(self, ref, payload):
        encoded=json.dumps(payload,ensure_ascii=False)
        size=len(encoded.encode('utf-8'))
        with self.lock:
            self._expire()
            r=self.records[ref]
            r['finished']=time.monotonic()
            if isinstance(payload.get('jobId'),str):r['job_id']=payload['jobId']
            if self.bytes+size>self.result_bytes:
                r['status']='result_unavailable'
                return
            r.update(status='done',payload=encoded,bytes=size)
            self.bytes+=size

    def fail_before_dispatch(self, ref, reason):
        with self.lock:
            r=self.records[ref]
            r.update(status='not_executed',reason=str(reason),finished=time.monotonic())

    def status(self, ref, owner):
        with self.lock:
            self._expire()
            base={'request_ref':ref,'runtime_id':self.runtime_id}
            if not isinstance(ref,str) or not ref.startswith(self.runtime_id+'.'):
                return {**base,'status':'unknown_runtime','note':'Runtime changed; prior execution cannot be inferred. Do not resubmit automatically.'}
            r=self.records.get(ref)
            if r is None or r['owner']!=owner:
                return {**base,'status':'unknown','note':'Receipt unavailable; missing does not prove not executed.'}
            return {**base,'status':r['status'],
                    'owner_call':r['owner_call'],'kind':r['kind'],
                    **({'jobId':r['job_id']} if r.get('job_id') else {}),
                    **({'result':json.loads(r['payload'])} if r['payload'] is not None else {}),
                    **({'reason':r['reason']} if 'reason' in r else {}),
                    'note':'Same-runtime receipt only. Read status/results; never repeat a mutation to retrieve its result.'}

    def recent(self, owner):
        """Recover references lost with a Host tool result; no code/result bodies."""
        with self.lock:
            self._expire()
            rows=[{'request_ref':ref,'owner_call':r['owner_call'],'kind':r['kind'],
                   'status':r['status'],'admitted_at':r['admitted_at']}
                  for ref,r in self.records.items() if r['owner']==owner]
            return {'status':'index','runtime_id':self.runtime_id,'requests':rows[-32:],
                    'omitted':max(0,len(rows)-32),
                    'note':'Only receipts admitted by this runtime for the current Host session. Missing records do not prove no execution; match owner_call before selecting.'}
