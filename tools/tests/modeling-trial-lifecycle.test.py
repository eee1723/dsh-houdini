"""Trial policy and cleanup boundaries; no HOM, Host, or model requests."""
from pathlib import Path
import importlib.util
import json
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'houdini/python3.11libs'))


def load_driver(run):
    dummy = run/'dummy'
    dummy.write_text('fixture', encoding='utf-8')
    argv = ['run-modeling-trial.py', '--plugin', str(ROOT), '--run', str(run),
            '--node', str(dummy), '--dsh', str(dummy), '--houdini', str(dummy),
            '--credentials', str(dummy), '--settings', str(dummy), '--model', 'fixture',
            '--condition', 'lifecycle-fixture', '--smoke', '--no-feedback']
    spec = importlib.util.spec_from_file_location('modeling_trial_fixture', ROOT/'tools/run-modeling-trial.py')
    module = importlib.util.module_from_spec(spec)
    with patch.object(sys, 'argv', argv): spec.loader.exec_module(module)
    return module


class TrialLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='dsh-trial-lifecycle-')
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name)
        self.driver = load_driver(self.run)

    def event(self, kind, **data):
        return {'type': 'event', 'event': {'type': kind, 'data': data}}

    def test_never_is_pinned_in_both_native_config_seams_and_verified_from_session(self):
        overlay = self.driver.trial_permissions_overlay('never')
        self.assertIn('policy: never', overlay)
        self.assertIn('sandbox: workspace-write\n        approval: never', overlay)
        self.assertIn('defaultPreset: workspace-write', overlay)
        baseline = {'asOfSeq': 4, 'values': {'permissions': {'currentValue': 'workspace-write'}}}
        records = [self.event('sandbox/mode', mode='workspace-write'), self.event('approval/policy', policy='never')]
        self.assertEqual(self.driver.verify_trial_permissions(baseline, records, 'never')['approval'], 'never')
        for change in [self.event('approval/policy', policy='ask'), self.event('sandbox/mode', mode='danger-full-access')]:
            bad = [*records, change]
            with self.assertRaisesRegex(RuntimeError, 'Actual DSH session permission'):
                self.driver.verify_trial_permissions(baseline, bad, 'never')

    def test_native_pending_audit_is_observed_without_granting_or_resuming(self):
        asked = self.event('approval/asked', id='a', toolName='fixture')
        self.assertEqual(self.driver.pending_approvals([asked]), [{'id': 'a', 'toolName': 'fixture'}])
        self.assertEqual(self.driver.pending_approvals([asked, self.event('approval/decided', id='a', outcome='rejected')]), [])

    def test_interrupt_and_early_setup_error_preserve_inputs_write_outcome_and_clear_only_copy(self):
        source = self.run/'user-store.yaml'
        source.write_text('user-store-must-stay', encoding='utf-8')
        task = self.run/'task'
        task.mkdir()
        brief = task/'brief.md'
        brief.write_text('original public task', encoding='utf-8')
        for failure, expected in [(KeyboardInterrupt(), 'external_cancelled'), (RuntimeError('setup failed'), 'driver_error')]:
            def failed_run(result):
                self.driver.HOME.mkdir(parents=True)
                (self.driver.HOME/'.credentials.yaml').write_text('copied-secret', encoding='utf-8')
                raise failure
            with patch.object(self.driver, 'run_trial', side_effect=failed_run), \
                 patch.object(self.driver, 'reexec_unpacked_test_cli'):
                with self.assertRaises(type(failure)): self.driver.main()
            result = json.loads((self.run/'run-result.json').read_text(encoding='utf-8'))
            self.assertEqual(result['result'], expected)
            self.assertTrue(result['credentialCleanup']['copiedCredentialStoreCleared'])
            self.assertEqual((self.driver.HOME/'.credentials.yaml').read_text(encoding='utf-8'), 'version: 1\nrefs: {}\nrecords: {}\n')
            self.assertEqual(source.read_text(encoding='utf-8'), 'user-store-must-stay')
            self.assertEqual(brief.read_text(encoding='utf-8'), 'original public task')
            import shutil
            shutil.rmtree(self.driver.RUNTIME)

    def test_owned_stop_uses_stop_and_eof_then_records_process_outcome(self):
        supervisor = Mock()
        supervisor.poll.side_effect = [None, 0, 0]
        supervisor.wait.side_effect = [TimeoutError('first stop'), 0]
        host = Mock()
        host.poll.return_value = 0
        streams = [Mock(), Mock()]
        result = {}
        with patch.object(self.driver, 'stop_owned') as stop:
            self.driver.stop_trial_processes(supervisor, host, streams, result)
        supervisor.stdin.write.assert_called_once_with('STOP\n')
        supervisor.stdin.close.assert_called_once()
        stop.assert_called_once_with()
        self.assertTrue(result['supervisorStopped'])
        self.assertTrue(result['hostStopped'])
        for stream in streams: stream.close.assert_called_once()

    def test_external_cancel_before_startup_admits_no_worker_or_model(self):
        self.driver.CANCEL.touch()
        with patch.object(self.driver, 'reexec_unpacked_test_cli'), \
             patch.object(self.driver, 'spawn_frontend') as spawn:
            self.driver.main()
        spawn.assert_not_called()
        result = json.loads((self.run/'run-result.json').read_text(encoding='utf-8'))
        self.assertEqual(result['result'], 'external_cancelled')
        self.assertFalse(self.driver.RUNTIME.exists())
        self.assertEqual(self.driver.CREDENTIALS.read_text(encoding='utf-8'), 'fixture')

    def test_host_stop_failure_still_closes_logs_and_outer_finally_clears_credentials(self):
        streams = [Mock(), Mock()]
        host = Mock()
        host.poll.return_value = None
        def failed_stop(result):
            self.driver.HOME.mkdir(parents=True)
            (self.driver.HOME/'.credentials.yaml').write_text('copy', encoding='utf-8')
            self.driver.stop_trial_processes(None, host, streams, result)
        with patch.object(self.driver, 'stop_owned', side_effect=OSError('Job close failed')), \
             patch.object(self.driver, 'run_trial', side_effect=failed_stop), \
             patch.object(self.driver, 'reexec_unpacked_test_cli'):
            with self.assertRaises(OSError): self.driver.main()
        for stream in streams: stream.close.assert_called_once()
        self.assertNotIn('copy', (self.driver.HOME/'.credentials.yaml').read_text(encoding='utf-8'))
        result = json.loads((self.run/'run-result.json').read_text(encoding='utf-8'))
        self.assertEqual(result['result'], 'process_stop_uncertain')
        self.assertFalse(result['hostStopped'])


if __name__ == '__main__': unittest.main()
