"""One-use admission tickets and bounded same-runtime receipts; no HOM/replay."""
from collections import OrderedDict
import hashlib
import json
import threading
import time
import uuid


class RequestRegistry:
    def __init__(self, runtime_id, limit=4096, result_bytes=64 * 1024 * 1024,
                 retention=600, ticket_retention=120):
        if limit < 1:
            raise ValueError('request capacity must be positive')
        self.runtime_id = runtime_id
        self.limit = limit
        self.result_bytes = result_bytes
        self.retention = retention
        self.ticket_retention = ticket_retention
        self.lock = threading.Lock()
        self.records = {}
        self.bytes = 0
        # These are indexes, not independent copies of execution state.
        self._tickets = OrderedDict()
        self._finished = OrderedDict()
        self._payloads = OrderedDict()

    def active_count(self):
        """In-flight requests and pinned job links, without scanning result bodies."""
        with self.lock:
            return len(self.records) - len(self._finished)

    def issue(self, owner):
        """Prepare one request without submitting code or occupying the HOM queue."""
        if not isinstance(owner, str) or not owner:
            raise ValueError('request tracking requires owner_session')
        with self.lock:
            now = time.monotonic()
            self._expire_tickets(now)
            while len(self._tickets) >= self.limit:
                self._tickets.popitem(last=False)
            ref = self.runtime_id + '.' + uuid.uuid4().hex
            self._tickets[ref] = (now, owner)
            return ref

    def _expire_tickets(self, now):
        while self._tickets:
            issued, _owner = next(iter(self._tickets.values()))
            if now - issued <= self.ticket_retention:
                break
            self._tickets.popitem(last=False)

    def _drop_payload(self, ref, status):
        record = self.records[ref]
        self.bytes -= record['bytes']
        record.update(payload=None, bytes=0, status=status)
        self._payloads.pop(ref, None)

    def _expire_payloads(self):
        now = time.monotonic()
        while self._payloads:
            ref = next(iter(self._payloads))
            if now - self.records[ref]['finished'] <= self.retention:
                break
            self._drop_payload(ref, 'result_expired')

    def reserve(self, ref, owner, payload):
        if not isinstance(ref, str) or not ref.startswith(self.runtime_id + '.'):
            raise ValueError('request_ref runtime mismatch; do not resubmit under a new runtime')
        suffix = ref[len(self.runtime_id) + 1:]
        if len(suffix) != 32 or any(c not in '0123456789abcdef' for c in suffix):
            raise ValueError('invalid request_ref')
        if not isinstance(owner, str) or not owner:
            raise ValueError('request tracking requires owner_session')
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.lock:
            self._expire_payloads()
            if ref in self.records:
                record = self.records[ref]
                if record['owner'] != owner or record['digest'] != digest:
                    raise ValueError('request_ref payload/owner conflict; original operation not repeated')
                return False
            self._expire_tickets(time.monotonic())
            ticket = self._tickets.get(ref)
            if ticket is None:
                # Consumed tickets never become admissible again, even after
                # their receipt is evicted. No lifetime tombstone set is needed.
                raise ValueError('request ticket expired, consumed or unknown; inspect the original receipt, do not resubmit')
            if ticket[1] != owner:
                raise ValueError('request ticket owner conflict')
            del self._tickets[ref]
            while len(self.records) >= self.limit:
                if not self._finished:
                    raise ValueError('too many active requests; no execution admitted')
                old, _ = self._finished.popitem(last=False)
                if self.records[old]['payload'] is not None:
                    self._drop_payload(old, 'result_expired')
                del self.records[old]
            self.records[ref] = {
                'owner': owner, 'digest': digest, 'status': 'queued', 'payload': None,
                'finished': None, 'bytes': 0, 'owner_call': payload.get('owner_call'),
                'kind': payload.get('request_kind', 'exec'), 'admitted_at': time.time(),
            }
            return True

    def running(self, ref):
        with self.lock:
            record = self.records.get(ref)
            if record is None or record['status'] != 'queued':
                return False
            record['status'] = 'running'
            return True

    def complete(self, ref, payload):
        encoded = json.dumps(payload, ensure_ascii=False)
        size = len(encoded.encode('utf-8'))
        with self.lock:
            self._expire_payloads()
            record = self.records[ref]
            if record['finished'] is not None:
                return  # A repeated completion cannot overwrite the original receipt.
            record['finished'] = time.monotonic()
            if isinstance(payload.get('jobId'), str):
                record['job_id'] = payload['jobId']
            if 'job_id' not in record or record.get('job_finished'):
                self._finished[ref] = None
            if size > self.result_bytes:
                record['status'] = 'result_unavailable'
                return
            while self.bytes + size > self.result_bytes:
                self._drop_payload(next(iter(self._payloads)), 'result_expired')
            record.update(status='done', payload=encoded, bytes=size)
            self._payloads[ref] = None
            self.bytes += size

    def fail_before_dispatch(self, ref, reason):
        with self.lock:
            record = self.records[ref]
            if record['status'] != 'queued':
                return
            record.update(status='not_executed', reason=str(reason), finished=time.monotonic())
            self._finished[ref] = None

    def finish_job(self, ref):
        """Release a job link only when its Bridge worker has reached a terminal state."""
        with self.lock:
            record = self.records.get(ref)
            if record is None:
                return  # An older runtime may finish after the Bridge was replaced.
            record['job_finished'] = True
            # A tiny job may finish before the HTTP handler records admission.
            if record['finished'] is not None:
                self._finished[ref] = None

    def status(self, ref, owner):
        with self.lock:
            self._expire_payloads()
            base = {'request_ref': ref, 'runtime_id': self.runtime_id}
            if not isinstance(ref, str) or not ref.startswith(self.runtime_id + '.'):
                return {**base, 'status': 'unknown_runtime',
                        'note': 'Runtime changed; prior execution cannot be inferred. Do not resubmit automatically.'}
            record = self.records.get(ref)
            if record is None or record['owner'] != owner:
                return {**base, 'status': 'unknown',
                        'note': 'Receipt unavailable or outside the retained window; missing does not prove not executed.'}
            return {**base, 'status': record['status'],
                    'owner_call': record['owner_call'], 'kind': record['kind'],
                    **({'jobId': record['job_id']} if record.get('job_id') else {}),
                    **({'result': json.loads(record['payload'])} if record['payload'] is not None else {}),
                    **({'reason': record['reason']} if 'reason' in record else {}),
                    'note': 'Same-runtime receipt only. Read status/results; never repeat a mutation to retrieve its result.'}

    def recent(self, owner):
        """Recover references lost with a Host result, within the bounded window."""
        with self.lock:
            self._expire_payloads()
            rows = [{'request_ref': ref, 'owner_call': record['owner_call'], 'kind': record['kind'],
                     'status': record['status'], 'admitted_at': record['admitted_at'],
                     'active': record['finished'] is None or ('job_id' in record and not record.get('job_finished'))}
                    for ref, record in self.records.items() if record['owner'] == owner]
            active = [row for row in rows if row['active']][-32:]
            recent = [row for row in rows if not row['active']]
            selected = active + (recent[-(32 - len(active)):] if len(active) < 32 else [])
            return {'status': 'index', 'runtime_id': self.runtime_id, 'requests': selected,
                    'omitted': max(0, len(rows) - 32), 'retained_limit': self.limit,
                    'note': 'Active requests/job links first, then recent completions for this Host session. Older completed receipts may be evicted; missing does not prove no execution. Match owner_call before selecting.'}
