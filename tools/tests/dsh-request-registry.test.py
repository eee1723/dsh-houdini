"""Bounded receipt lifetime and one-use admission; plain Python, no HOM/network."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
from dsh_requests import RequestRegistry


class Requests(unittest.TestCase):
    def setUp(self):
        self.registry = RequestRegistry('a' * 32, limit=8, result_bytes=256)
        self.owner = 'session'
        self.payload = {'code': 'x', 'owner_call': 'call'}

    def admit(self, registry=None, payload=None):
        registry = registry or self.registry
        ref = registry.issue(self.owner)
        self.assertTrue(registry.reserve(ref, self.owner, payload or self.payload))
        return ref

    def test_only_issued_owner_can_admit(self):
        ref = self.registry.issue(self.owner)
        with self.assertRaisesRegex(ValueError, 'owner conflict'):
            self.registry.reserve(ref, 'other', self.payload)
        self.assertTrue(self.registry.reserve(ref, self.owner, self.payload))
        self.assertFalse(self.registry.reserve(ref, self.owner, self.payload))
        with self.assertRaisesRegex(ValueError, 'payload/owner conflict'):
            self.registry.reserve(ref, self.owner, {'code': 'different'})
        self.assertEqual(self.registry.status(ref, 'other')['status'], 'unknown')
        with self.assertRaisesRegex(ValueError, 'consumed or unknown'):
            self.registry.reserve('a' * 32 + '.' + 'b' * 32, self.owner, self.payload)
        with self.assertRaisesRegex(ValueError, 'runtime mismatch'):
            self.registry.reserve('c' * 32 + '.' + 'b' * 32, self.owner, self.payload)
        self.assertEqual(self.registry.status('c' * 32 + '.' + 'b' * 32, self.owner)['status'], 'unknown_runtime')

    def test_concurrent_duplicate_has_one_admission(self):
        ref = self.registry.issue(self.owner)
        with ThreadPoolExecutor(max_workers=16) as pool:
            outcomes = list(pool.map(lambda _: self.registry.reserve(ref, self.owner, self.payload), range(64)))
        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(len(self.registry.records), 1)

    def test_twelve_thousand_completions_with_bounded_memory(self):
        active = self.admit()
        self.registry.running(active)
        first = None
        for index in range(12_000):
            ref = self.admit(payload={'code': 'x', 'owner_call': str(index)})
            first = first or ref
            self.registry.complete(ref, {'index': index})
            if index % 1000 == 0:
                self.assertLessEqual(len(self.registry.records), 8)
                self.assertLessEqual(len(self.registry._finished), 7)
                self.assertLessEqual(self.registry.bytes, 256)
        self.assertEqual(self.registry.status(active, self.owner)['status'], 'running')
        self.assertEqual(self.registry.status(ref, self.owner)['result'], {'index': 11_999})
        self.assertEqual(self.registry.status(first, self.owner)['status'], 'unknown')
        with self.assertRaisesRegex(ValueError, 'consumed or unknown'):
            self.registry.reserve(first, self.owner, {'code': 'x', 'owner_call': '0'})
        self.assertEqual(self.registry.bytes, sum(record['bytes'] for record in self.registry.records.values()))
        self.assertEqual(len(self.registry._tickets), 0)

    def test_active_capacity_recovers_without_restarting(self):
        registry = RequestRegistry('a' * 32, limit=1)
        first = self.admit(registry)
        refused = registry.issue(self.owner)
        with self.assertRaisesRegex(ValueError, 'too many active'):
            registry.reserve(refused, self.owner, self.payload)
        registry.complete(first, {'ok': True})
        second = self.admit(registry)
        self.assertEqual(registry.status(second, self.owner)['status'], 'queued')
        for old in (first, refused):
            with self.assertRaisesRegex(ValueError, 'consumed or unknown'):
                registry.reserve(old, self.owner, self.payload)

    def test_ticket_expiry_and_unused_capacity_never_reactivate(self):
        with patch('dsh_requests.time.monotonic', return_value=0) as clock:
            expired = self.registry.issue(self.owner)
            clock.return_value = 121
            with self.assertRaisesRegex(ValueError, 'expired'):
                self.registry.reserve(expired, self.owner, self.payload)
            oldest = self.registry.issue(self.owner)
            for _ in range(8):
                self.registry.issue(self.owner)
            with self.assertRaisesRegex(ValueError, 'expired'):
                self.registry.reserve(oldest, self.owner, self.payload)
            self.assertEqual(len(self.registry._tickets), 8)
            self.assertEqual(len(self.registry.records), 0)

    def test_result_ttl_and_budget_preserve_receipts_not_replay(self):
        registry = RequestRegistry('a' * 32, limit=8, result_bytes=20)
        with patch('dsh_requests.time.monotonic', return_value=0) as clock:
            old = self.admit(registry)
            registry.complete(old, {'value': 1})
            new = self.admit(registry)
            registry.complete(new, {'value': 2})
            self.assertEqual(registry.status(old, self.owner)['status'], 'result_expired')
            self.assertEqual(registry.status(new, self.owner)['result'], {'value': 2})
            self.assertFalse(registry.reserve(old, self.owner, self.payload))
            clock.return_value = 601
            self.assertEqual(registry.status(new, self.owner)['status'], 'result_expired')
            self.assertEqual(registry.bytes, 0)
        job = self.admit(registry)
        registry.complete(job, {'jobId': 'long-background-job'})
        self.assertEqual(registry.status(job, self.owner)['jobId'], 'long-background-job')
        self.assertEqual(registry.status(job, self.owner)['status'], 'result_unavailable')

    def test_original_terminal_outcome_is_stable(self):
        ref = self.admit()
        self.registry.running(ref)
        self.registry.complete(ref, {'ok': True})
        size = self.registry.bytes
        self.registry.complete(ref, {'ok': False})
        self.registry.running(ref)
        self.registry.fail_before_dispatch(ref, 'late error')
        self.assertEqual(self.registry.status(ref, self.owner)['result'], {'ok': True})
        self.assertEqual(self.registry.bytes, size)
        refused = self.admit()
        self.registry.fail_before_dispatch(refused, 'worker not started')
        self.assertFalse(self.registry.running(refused), 'a late worker cannot claim a cancelled request')
        self.registry.complete(refused, {'must_not_replace': True})
        self.assertEqual(self.registry.status(refused, self.owner)['status'], 'not_executed')

    def test_running_request_cannot_be_declared_not_executed(self):
        ref = self.admit()
        self.assertTrue(self.registry.running(ref))
        self.assertFalse(self.registry.running(ref), 'one execution claim per admission')
        self.registry.fail_before_dispatch(ref, 'too late')
        self.assertEqual(self.registry.status(ref, self.owner)['status'], 'running')

    def test_active_job_link_survives_pressure_until_worker_finishes(self):
        registry = RequestRegistry('a' * 32, limit=2, result_bytes=0)
        job = self.admit(registry, {'request_kind': 'job_submit', 'owner_call': 'lost-job'})
        registry.complete(job, {'jobId': 'long-job'})
        for _ in range(100):
            ref = self.admit(registry)
            registry.complete(ref, {'ok': True})
        self.assertEqual(registry.status(job, self.owner)['jobId'], 'long-job')
        self.assertEqual(registry.recent(self.owner)['requests'][0]['owner_call'], 'lost-job')
        registry.finish_job(job)
        # The oldest completed routine receipt can be retired first; both slots
        # eventually rotate now that the job worker is terminal.
        for _ in range(2):
            registry.complete(self.admit(registry), {'ok': True})
        self.assertEqual(registry.status(job, self.owner)['status'], 'unknown')
        with self.assertRaisesRegex(ValueError, 'consumed or unknown'):
            registry.reserve(job, self.owner, {'request_kind': 'job_submit', 'owner_call': 'lost-job'})

    def test_job_may_finish_before_admission_is_recorded(self):
        registry = RequestRegistry('a' * 32, limit=1)
        ref = self.admit(registry, {'request_kind': 'job_submit'})
        registry.finish_job(ref)
        registry.complete(ref, {'jobId': 'already-finished'})
        registry.complete(self.admit(registry), {'ok': True})
        self.assertEqual(registry.status(ref, self.owner)['status'], 'unknown')

    def test_active_job_is_not_buried_by_recent_index(self):
        registry = RequestRegistry('a' * 32, limit=64)
        job = self.admit(registry, {'request_kind': 'job_submit'})
        registry.complete(job, {'jobId': 'long-job'})
        for _ in range(50):
            registry.complete(self.admit(registry), {'ok': True})
        listing = registry.recent(self.owner)
        self.assertEqual(len(listing['requests']), 32)
        self.assertEqual(listing['requests'][0]['request_ref'], job)
        self.assertTrue(listing['requests'][0]['active'])

    def test_status_and_admission_do_not_rescan_history(self):
        class NoScan(dict):
            def values(self):
                raise AssertionError('history scan')
            def items(self):
                raise AssertionError('history scan')
        ref = self.admit()
        self.registry.complete(ref, {'ok': True})
        self.registry.records = NoScan(self.registry.records)
        self.assertEqual(self.registry.status(ref, self.owner)['status'], 'done')
        self.assertEqual(self.registry.active_count(), 0)
        self.admit()
        self.assertEqual(self.registry.active_count(), 1)

    def test_activity_excludes_tickets_and_includes_unfinished_jobs(self):
        self.registry.issue(self.owner)
        self.assertEqual(self.registry.active_count(), 0)
        ref = self.admit()
        self.assertEqual(self.registry.active_count(), 1)
        self.registry.running(ref)
        self.assertEqual(self.registry.active_count(), 1)
        self.registry.complete(ref, {'ok': True})
        self.assertEqual(self.registry.active_count(), 0)
        job = self.admit(payload={'request_kind': 'job_submit'})
        self.registry.complete(job, {'jobId': 'job'})
        self.assertEqual(self.registry.active_count(), 1)
        self.registry.finish_job(job)
        self.assertEqual(self.registry.active_count(), 0)
        refused = self.admit()
        self.registry.fail_before_dispatch(refused, 'not started')
        self.assertEqual(self.registry.active_count(), 0)

    def test_recent_index_is_owner_scoped_and_bounded(self):
        registry = RequestRegistry('a' * 32, limit=40)
        for index in range(60):
            ref = self.admit(registry, {'code': 'x', 'owner_call': str(index)})
            registry.complete(ref, {'ok': True})
        listing = registry.recent(self.owner)
        self.assertEqual(len(listing['requests']), 32)
        self.assertEqual(listing['requests'][-1]['owner_call'], '59')
        self.assertEqual(listing['omitted'], 8)
        self.assertEqual(registry.recent('other')['requests'], [])
        self.assertNotIn('code', json.dumps(listing))


if __name__ == '__main__':
    unittest.main(verbosity=2)
