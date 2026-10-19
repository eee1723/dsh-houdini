"""Cross-process recovery and hostile scene changes in isolated real Houdini."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def worker(mode, folder):
    sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
    import hou
    if mode == 'late-install':
        hou.hipFile.load((folder / 'project.hip').as_posix(), suppress_save_prompt=True, ignore_load_warnings=True)
    import dsh_bridge as bridge
    import dsh_scene_recovery as recovery
    import dsh_ownership as ownership
    owner = 'recovery-fixture-task'
    hip = folder / 'project.hip'
    if mode == 'save':
        built = bridge.run_code("p=tab_create('/obj','geo',name='asset')\n"
                                "n=tab_create(p,'box',name='source')\n__result__=n.path()",
                                owner_session=owner, owner_call='build')
        assert built['ok'], built
        other = bridge.run_code("p=tab_create('/obj','geo',name='second_task')\n"
                                "tab_create(p,'box',name='source')", owner_session='second-task', owner_call='build-second')
        assert other['ok'], other
        definition = bridge.run_code("p=tab_create('/obj','geo',name='definition_asset')\n"
                                     "tab_create(p,'attribwrangle',name='wrangle')",
                                     owner_session='definition-task', owner_call='build-definition')
        assert definition['ok'], definition
        wrangle = hou.node('/obj/definition_asset/wrangle')
        core = wrangle.node('attribvop1')
        assert core is not None and core.isInsideLockedHDA() and not core.isEditableInsideLockedHDA()
        core_path = core.path()
        assert int(core.sessionId()) in ownership.records(), 'fixture must exercise an originally owned definition member'
        hou.node('/obj/asset').createNode('null', 'user_node')
        # Exercise the actual native success script, not scene_save's fallback.
        hou.hipFile.save(hip.as_posix())
        for _ in range(200):
            if recovery.facts()['checkpoint']['status'] == 'checkpoint_saved':
                break
            time.sleep(.025)
        else:
            raise AssertionError(recovery.facts())
        saved_record = recovery.store.read(recovery.facts()['checkpoint_id'])
        assert any(row['path'] == wrangle.path() for row in saved_record['nodes'])
        assert not any(row['path'].startswith(wrangle.path() + '/') for row in saved_record['nodes'])
        (folder / 'ready.json').write_text(json.dumps({'executor': bridge._EXECUTOR_ID,
            'checkpoint': recovery.facts()['checkpoint_id'], 'scene': recovery.facts()['scene_id'],
            'definition_core': core_path, 'definition_core_type': core.type().name(),
            'definition_core_category': core.type().category().name()}), encoding='utf-8')
        sys.stdin.readline()  # Own process remains alive for the lease counterexample.
        return
    original = json.loads((folder / 'ready.json').read_text())
    base = {'session_id': owner, 'previous_executor': original['executor'],
            'source_executors': [original['executor']],
            'expected_contract': {'version': bridge._EXECUTION_CONTRACT_VERSION, 'hash': bridge._VERB_CATALOG_HASH}}
    bridge._pump_active = True
    def call(action, **fields):
        result = {}
        def run():
            try:
                handler = object.__new__(bridge._Handler)
                handler.path = '/recovery/' + action
                handler._send = lambda value, status=200: result.update(value=value, status=status)
                handler._route({**base, **fields})
            except Exception as error:
                result['error'] = str(error)
        thread = threading.Thread(target=run)
        thread.start()
        deadline = time.monotonic() + 40
        while thread.is_alive() and time.monotonic() < deadline:
            bridge._pump()
            time.sleep(.005)
        thread.join(.1)
        assert not thread.is_alive(), 'recovery worker hung'
        if result.get('value', {}).get('ok') is False:
            result['error'] = result['value']['error']
        return result
    def load():
        hou.hipFile.load(hip.as_posix(), suppress_save_prompt=True, ignore_load_warnings=True)
        assert recovery.facts()['loaded_checkpoint'] == original['checkpoint'], recovery.facts()
    if mode == 'late-install':
        initial = recovery.facts()
        assert initial['scene_id'] == original['scene'], initial
        assert initial['checkpoint_id'] == original['checkpoint'], initial
        assert initial['loaded_checkpoint'] is None and recovery._PROVEN is None
        assert not ownership.records(), 'a saved identity is not proof of live node ownership'
        assessment = call('assess', expected={'scene_id': original['scene']})['value']
        assert assessment['status'] == 'ready' and assessment['requires_reload'], assessment
        assert 'error' in call('prepare', operation_id=uuid.uuid4().hex, expected=assessment)
        hou.node('/obj/asset').createNode('null', 'unsaved_user_edit')
        assert 'error' in call('prepare', operation_id=uuid.uuid4().hex, expected=assessment, reload_saved=True)
        assert hou.node('/obj/asset/unsaved_user_edit') is not None and not ownership.records()
        recovery.task_target(owner)
        hou.node('/').setUserData(recovery.SCENE_KEY, uuid.uuid4().hex)
        recovery.install()
        assert recovery.facts()['scene_id'] == initial['scene_id'] and recovery.connected(owner)
        hou.hipFile.clear(suppress_save_prompt=True)
        assert recovery.facts()['scene_id'] != initial['scene_id'] and not recovery.connected(owner)
        assert not ownership.records()
        print('PASS late plugin install preserves saved scene identity without inventing load evidence or discarding edits', flush=True)
        return
    def wait_saved():
        for _ in range(400):
            if recovery.facts()['checkpoint']['status'] == 'checkpoint_saved':
                return
            time.sleep(.01)
        raise AssertionError(recovery.facts())
    def wait_verified():
        for _ in range(400):
            if recovery._PROVEN:
                return
            time.sleep(.01)
        raise AssertionError('load verification did not complete')
    load()
    if mode == 'alive':
        assert 'error' in call('assess'), 'a still-live original author must not be stolen'
        located = call('locate', expected={'scene_id': original['scene']})['value']
        assert not located['candidates'] and located['unavailable'], 'do not offer a still-live author as a resumable target'
        return
    assert not ownership.records()
    # An explicit recovery is still pinned to the selected live target, both
    # before queueing and at actor dispatch. It grants no ownership on mismatch.
    selected_epoch = recovery.scene_epoch()
    stale_epoch = '0' * 32 if selected_epoch != '0' * 32 else '1' * 32
    assert 'error' in call('assess', scene_epoch=stale_epoch, runtime_id=bridge._RUNTIME_ID)
    assert 'error' in call('assess', scene_epoch=selected_epoch, runtime_id='0' * 32 if bridge._RUNTIME_ID != '0' * 32 else '1' * 32)
    with patch.object(recovery, 'scene_epoch', side_effect=[selected_epoch, stale_epoch]):
        queued = call('assess', scene_epoch=selected_epoch, runtime_id=bridge._RUNTIME_ID)
    assert 'scene_epoch changed' in queued['error'], queued
    assert not ownership.records()
    located = call('locate', expected={'scene_id': original['scene']})['value']
    assert [item['checkpoint_id'] for item in located['candidates']] == [original['checkpoint']], located
    expected = {**recovery.facts(), 'scene_id': original['scene'], 'open_original': True}
    opened_args = {'checkpoint_id': original['checkpoint'], 'expected': expected}
    before_epoch = recovery.scene_epoch()
    assert 'error' in call('open', **{**opened_args, 'expected': {**expected, 'scene_epoch': uuid.uuid4().hex}})
    assert 'error' in call('open', **{**opened_args, 'expected': {**expected, 'open_original': 'yes'}})
    assert 'error' in call('open', **opened_args), 'hython cannot certify the dirty flag for a destructive load'
    assert 'error' in call('open', **opened_args, hip_path=str(hip)), 'there is no caller-selected arbitrary path opener'
    assert recovery.scene_epoch() == before_epoch and not ownership.records()
    assert 'error' in call('open', **{**opened_args, 'expected': {**expected, 'open_original': False, 'replace_empty': True}}), 'a nonempty scene cannot use the empty-scene continuation'
    saved_bytes = hip.read_bytes()
    try:
        hip.write_bytes(b'changed after the conversation question')
        assert 'error' in call('open', **opened_args)
        assert recovery.scene_epoch() == before_epoch, 'changed disk bytes must fail before HOM load'
    finally:
        hip.write_bytes(saved_bytes)
    load()  # The fixture restored bytes; observe the new file stamp normally.
    original_load, original_facts = hou.hipFile.load, recovery.facts
    def load_with_warning(*args, **kwargs):
        original_load(*args, **kwargs)
        raise hou.LoadWarning('fixture: native compatibility warning after a successful load')
    try:
        hou.hipFile.load = load_with_warning
        recovery.facts = lambda: {**original_facts(), 'dirty': False, 'dirty_reliable': True}
        recovery._LOADED, recovery._PROVEN = None, None
        assessment = call('assess')['value']
        warning_operation = uuid.uuid4().hex
        prepared_warning = call('prepare', operation_id=warning_operation, expected=assessment, reload_saved=True)['value']
        assert prepared_warning['load_warnings'] and 'compatibility warning' in prepared_warning['load_warnings'][0]
        assert not ownership.records(), 'a loaded warning does not bypass explicit activation'
        assert 'load_warnings' not in recovery.facts(), 'later scene receipts contain references, not repeated preview text'
        detail = prepared_warning['load_warning_details']
        assert detail['stored'] and recovery.facts()['load_warning_details'] == detail
        assert json.loads(Path(detail['path']).read_text())['result']['load_warnings'] == prepared_warning['load_warnings']
        hou.hipFile.load = lambda *a, **k: (_ for _ in ()).throw(hou.OperationFailed('fixture: fatal load'))
        recovery._LOADED, recovery._PROVEN = None, None
        fatal_operation = uuid.uuid4().hex
        assessment = call('assess')['value']
        assert 'error' in call('prepare', operation_id=fatal_operation, expected=assessment, reload_saved=True)
        assert fatal_operation not in recovery._OPERATIONS
    finally:
        hou.hipFile.load, recovery.facts = original_load, original_facts
    load()
    assert recovery.facts()['load_warning_details'] is None
    # Old records may include regenerated locked-definition members. Classify
    # only through an exact surviving HDA ancestor; never materialize the child.
    legacy = recovery.store.read(original['checkpoint'])
    legacy = {**legacy, 'nodes': [*legacy['nodes'], {
        'node_id': uuid.uuid4().hex, 'path': original['definition_core'],
        'type': original['definition_core_type'], 'category': original['definition_core_category'],
        'owner': {'session': 'definition-task', 'call': 'build-definition'},
        'source_executor': original['executor']}]}
    before_nodes = {int(node.sessionId()) for node in recovery._nodes()}
    mapped, missing = recovery._live_mapping(legacy, recovery._LOADED_NODES, 'definition-task')
    assert len(mapped) == 2 and missing == [{'path': original['definition_core'],
                                           'reason': 'native_definition_member_unverified'}], (mapped, missing)
    assert {int(node.sessionId()) for node in recovery._nodes()} == before_nodes
    unanchored = dict(recovery._LOADED_NODES)
    unanchored.pop(int(hou.node('/obj/definition_asset/wrangle').sessionId()))
    _, unanchored_missing = recovery._live_mapping(legacy, unanchored, 'definition-task')
    assert any(item['path'] == original['definition_core'] and item['reason'] == 'original_node_missing_or_changed'
               for item in unanchored_missing), unanchored_missing
    # A save which outruns background verification stays explicitly unavailable;
    # it cannot promote copied tags, block the actor, or delete original material.
    wait_verified()
    digest = recovery.store.file_digest
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    def blocked_digest(*args, **kwargs):
        if threading.current_thread().name == 'dsh-load-checkpoint':
            entered.set()
            assert release.wait(5)
            try:
                return digest(*args, **kwargs)
            finally:
                finished.set()
        return digest(*args, **kwargs)
    recovery.store.file_digest = blocked_digest
    try:
        load()
        assert entered.wait(2)
        hou.hipFile.save((folder / 'save-before-verification.hip').as_posix())
        assert recovery.facts()['checkpoint']['status'] == 'checkpoint_unavailable'
        assert not ownership.records()
        assert recovery.store.read(original['checkpoint'])['checkpoint_id'] == original['checkpoint']
    finally:
        release.set()
        assert finished.wait(5)
        recovery.store.file_digest = digest
    load()
    # Saving before any task is activated must preserve both creators, without
    # assigning either one live mutation authority.
    wait_verified()
    hou.hipFile.save((folder / 'resaved.hip').as_posix())
    wait_saved()
    record = recovery.store.read(recovery.facts()['checkpoint_id'])
    assert {row['owner']['session'] for row in record['nodes']} == {owner, 'second-task', 'definition-task'}
    assert not ownership.records()
    load()
    assessed = call('assess')['value']
    assert assessed['status'] == 'ready' and assessed['owned_nodes'] >= 2, assessed
    # Inherited creator E1 does not let stale E1 history steal a checkpoint
    # produced by another still-live E2 author into a third process.
    wait_verified()
    read_record = recovery.store.read
    later_executor = 'f' * 32
    recovery.store.retain_executor(later_executor)
    later_record = {**read_record(original['checkpoint']), 'executor_id': later_executor,
                    'source_executors': [original['executor'], later_executor]}
    try:
        recovery.store.read = lambda checkpoint: later_record if checkpoint == original['checkpoint'] else read_record(checkpoint)
        assert 'error' in call('assess'), 'a live checkpoint producer cannot be bypassed by older creator lineage'
    finally:
        recovery.store.read = read_record
    # Lazy startup with dirty content is never discarded merely because an
    # automatic caller requested reload; the dialogue decision is explicit.
    get_facts, loaded, proven = recovery.facts, recovery._LOADED, recovery._PROVEN
    dirty_facts = {**get_facts(), 'dirty': True, 'dirty_reliable': True}
    try:
        recovery.facts = lambda: dirty_facts
        recovery._LOADED, recovery._PROVEN = None, None
        rejected = call('prepare', operation_id=uuid.uuid4().hex, expected=assessed, reload_saved=True)
        assert 'error' in rejected and '未保存' in rejected['error'], rejected
    finally:
        recovery.facts, recovery._LOADED, recovery._PROVEN = get_facts, loaded, proven
    assert 'error' in call('assess', session_id='different-task')
    saved = hip.read_bytes()
    hip.write_bytes(saved + b'changed')
    assert 'error' in call('assess'), 'same path must not accept different saved bytes'
    hip.write_bytes(saved)
    assert 'error' in call('assess'), 'restoring disk bytes does not prove the already loaded scene came from those bytes'
    load()
    assessed = call('assess')['value']
    # Copy tags, then delete the original: uniqueness alone does not prove identity.
    source = hou.node('/obj/asset/source')
    clone = hou.copyNodesTo([source], source.parent())[0]
    source.destroy()
    clone.setName('source')
    partial = call('prepare', operation_id=uuid.uuid4().hex, expected=assessed)['value']
    assert partial['restored_nodes'] == 1 and partial['unrestored_nodes'], partial
    call('activate', operation_id=partial['operation_id'])
    assert int(clone.sessionId()) not in ownership.records(), 'a replacement cannot inherit its source identity'
    load()
    assert not ownership.records()
    assessed = call('assess')['value']
    source = hou.node('/obj/asset/source')
    clone = hou.copyNodesTo([source], source.parent())[0]
    duplicate = call('prepare', operation_id=uuid.uuid4().hex, expected=assessed)['value']
    assert duplicate['restored_nodes'] == 2 and not duplicate['unrestored_nodes'], duplicate
    assert int(clone.sessionId()) not in ownership.records()
    clone.destroy()
    # Preparation which fails the post-load disk check cannot be activated or
    # silently reused on retry, even though it has already mapped live nodes.
    digest, checks = recovery.store.file_digest, [0]
    failed_operation = uuid.uuid4().hex
    def fail_final_digest(*args, **kwargs):
        if threading.current_thread().name != 'dsh-load-checkpoint':
            checks[0] += 1
            if checks[0] == 2:
                raise RuntimeError('injected final file verification failure')
        return digest(*args, **kwargs)
    recovery.store.file_digest = fail_final_digest
    try:
        assert 'error' in call('prepare', operation_id=failed_operation, expected=assessed)
        assert failed_operation not in recovery._OPERATIONS
        assert 'error' in call('activate', operation_id=failed_operation)
    finally:
        recovery.store.file_digest = digest
    operation = uuid.uuid4().hex
    prepared = call('prepare', operation_id=operation, expected=assessed)['value']
    assert prepared['status'] == 'prepared' and not ownership.records()
    repeated = call('prepare', operation_id=operation, expected=assessed)['value']
    assert repeated == prepared
    assert 'error' in call('activate', operation_id=operation, session_id='different-task')
    assert not ownership.records()
    activated = call('activate', operation_id=operation)['value']
    assert activated['status'] == 'active', activated
    assert call('activate', operation_id=operation)['value'] == activated
    digest = recovery.store.file_digest
    try:
        recovery.store.file_digest = lambda *a, **k: (_ for _ in ()).throw(AssertionError('connected assessment must not hash'))
        current = call('assess', previous_executor=bridge._EXECUTOR_ID)['value']
        assert current['connected'] and current['task_bound'] and current['binding_id'] == operation, current
    finally:
        recovery.store.file_digest = digest
    edited = bridge.run_code("set_parms('/obj/asset/source',{'sizex':2.5})\n__result__=hou.node('/obj/asset/source').parm('sizex').eval()",
                             owner_session=owner, owner_call='continued-edit')
    assert edited['ok'], edited
    assert hou.node('/obj/asset/source').parm('sizex').eval() == 2.5
    denied = bridge.run_code("delete_node('/obj/asset/user_node')", owner_session=owner, owner_call='foreign')
    assert not denied['ok'] and hou.node('/obj/asset/user_node') is not None
    other = bridge.run_code("set_parms('/obj/asset/source',{'sizex':3})", owner_session='other-task', owner_call='foreign')
    assert not other['ok']
    # Saving after restoring only A carries B's original author across E1→E2.
    wait_verified()
    source = hou.node('/obj/asset/source')
    second_source = hou.node('/obj/second_task/source')
    foreign_copy = hou.copyNodesTo([source], source.parent())[0]
    foreign_copy.setName('user_copy')
    inactive_copy = hou.copyNodesTo([second_source], second_source.parent())[0]
    inactive_copy.setName('user_copy')
    copy_markers = (foreign_copy.userData(recovery.NODE_KEY), inactive_copy.userData(recovery.NODE_KEY))
    assert copy_markers == (source.userData(recovery.NODE_KEY), second_source.userData(recovery.NODE_KEY))
    # A failed save rotates only trusted sources, and the following successful
    # save must still retain B's inactive provenance after that marker change.
    saved_parent = recovery.facts()['checkpoint_id']
    recovery.before_save()
    recovery.after_save(hou.hipFile.path(), False)
    assert recovery.facts()['checkpoint']['status'] == 'save_failed'
    assert copy_markers == (foreign_copy.userData(recovery.NODE_KEY), inactive_copy.userData(recovery.NODE_KEY))
    assert copy_markers[0] != source.userData(recovery.NODE_KEY)
    assert copy_markers[1] != second_source.userData(recovery.NODE_KEY)
    continued_hip = (folder / 'continued.hip').as_posix()
    hou.hipFile.save(continued_hip)
    wait_saved()
    record = recovery.store.read(recovery.facts()['checkpoint_id'])
    assert record['parent_checkpoint'] == saved_parent, 'a failed save must not split the trusted saved lineage'
    candidates = recovery.store.locate(original['scene'], owner, [original['executor'], bridge._EXECUTOR_ID])['candidates']
    candidate_ids = {item['checkpoint_id'] for item in candidates}
    assert record['checkpoint_id'] in candidate_ids and saved_parent not in candidate_ids, candidates
    second = [row for row in record['nodes'] if row['owner']['session'] == 'second-task']
    assert len(second) == 2 and all(row['source_executor'] == original['executor'] for row in second)
    assert all(entry['session'] != 'second-task' for entry in ownership.records().values())
    # A fresh load still knows each exact original, even though the foreign
    # copies persisted the old tags. Neither copy is granted mutation rights.
    hou.hipFile.load(continued_hip, suppress_save_prompt=True)
    continued = call('assess')['value']
    continued_operation = uuid.uuid4().hex
    continued_prepared = call('prepare', operation_id=continued_operation, expected=continued)['value']
    assert continued_prepared['restored_nodes'] == 2 and not continued_prepared['unrestored_nodes']
    call('activate', operation_id=continued_operation)
    assert int(hou.node('/obj/asset/source').sessionId()) in ownership.records()
    assert int(hou.node('/obj/asset/user_copy').sessionId()) not in ownership.records()
    assessed_second = call('assess', session_id='second-task')['value']
    assert not assessed_second['requires_reload'], assessed_second
    second_operation = uuid.uuid4().hex
    prepared_second = call('prepare', session_id='second-task', operation_id=second_operation,
                           expected=assessed_second)['value']
    assert prepared_second['restored_nodes'] == 2
    call('activate', session_id='second-task', operation_id=second_operation)
    assert int(hou.node('/obj/second_task/source').sessionId()) in ownership.records()
    assert int(hou.node('/obj/second_task/user_copy').sessionId()) not in ownership.records()
    edited_second = bridge.run_code("set_parms('/obj/second_task/source',{'sizex':4})",
                                    owner_session='second-task', owner_call='continue-second')
    assert edited_second['ok'], edited_second
    # Read-only tasks can reconnect on recorded scene identity, with no node claims.
    assert 'error' in call('assess', session_id='read-only-task')
    assert 'error' in call('assess', session_id='read-only-task', expected={'scene_id': uuid.uuid4().hex})
    zero = call('assess', session_id='read-only-task', expected={'scene_id': original['scene']})['value']
    zero_operation = uuid.uuid4().hex
    prepared_zero = call('prepare', session_id='read-only-task', operation_id=zero_operation, expected=zero)['value']
    assert prepared_zero['restored_nodes'] == 0
    call('activate', session_id='read-only-task', operation_id=zero_operation)
    assert all(entry['session'] != 'read-only-task' for entry in ownership.records().values())
    definition_assessment = call('assess', session_id='definition-task')['value']
    definition_operation = uuid.uuid4().hex
    definition_prepared = call('prepare', session_id='definition-task', operation_id=definition_operation,
                               expected=definition_assessment)['value']
    assert definition_prepared['restored_nodes'] == 2 and not definition_prepared['unrestored_nodes']
    call('activate', session_id='definition-task', operation_id=definition_operation)
    edited_definition = bridge.run_code("set_parms('/obj/definition_asset/wrangle',{'snippet':'@P *= 2.0;'})",
                                        owner_session='definition-task', owner_call='continue-definition')
    assert edited_definition['ok'], edited_definition
    loaded_core = hou.node(original['definition_core'])
    assert loaded_core is not None and int(loaded_core.sessionId()) not in ownership.records()
    # A prepared request must not reach a different HIP, even in the same process.
    epoch = recovery.task_target(owner)
    ref = bridge._request_registry.issue(owner, scene_epoch=epoch)
    bridge._request_registry.reserve(ref, owner, {'owner_call': 'stale'})
    hou.hipFile.clear(suppress_save_prompt=True)
    assert not bridge._begin_request(ref, owner)
    assert bridge._request_registry.status(ref, owner)['status'] == 'not_executed'
    assert 'error' in call('activate', operation_id=operation)
    assert not ownership.records()
    # A task which only observed a newly saved scene also has continuity;
    # connection identity does not depend on having created at least one node.
    empty_owner = 'read-only-empty-scene'
    recovery.task_target(empty_owner)
    empty_scene = recovery.facts()['scene_id']
    empty_hip = (folder / 'empty.hip').as_posix()
    hou.hipFile.save(empty_hip)
    wait_saved()
    assert recovery.store.read(recovery.facts()['checkpoint_id'])['nodes'] == []
    hou.hipFile.load(empty_hip, suppress_save_prompt=True)
    empty_args = {'session_id': empty_owner, 'previous_executor': bridge._EXECUTOR_ID,
                  'source_executors': [bridge._EXECUTOR_ID]}
    empty = call('assess', **empty_args, expected={'scene_id': empty_scene})['value']
    empty_operation = uuid.uuid4().hex
    assert call('prepare', **empty_args, operation_id=empty_operation, expected=empty)['value']['restored_nodes'] == 0
    call('activate', session_id=empty_owner, operation_id=empty_operation)
    assert not ownership.records()
    print('PASS saved bytes, live-author lease, partial exact survivors, inactive authors across save, zero-node identity, cheap connected check, foreign and stale scene', flush=True)


def main():
    sys.path.insert(0, str(ROOT / 'tools'))
    from houdini_test_environment import isolated_environment, reexec_unpacked_test_cli
    reexec_unpacked_test_cli()
    for executable in sys.argv[1:]:
        hython = Path(executable).resolve(strict=True)
        folder = Path(tempfile.mkdtemp(prefix='dsh-scene-recovery-'))
        def env(name):
            value = isolated_environment(folder / name, executable=hython)
            value.update(DSH_HOUDINI_RECOVERY_ROOT=str(folder / 'recovery'),
                         HOUDINI_PATH=(ROOT / 'houdini').as_posix() + ';&')
            return value
        writer = subprocess.Popen([str(hython), __file__, '--worker', 'save', str(folder)],
            cwd=hython.parent, env=env('save-env'), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for _ in range(300):
                if (folder / 'ready.json').exists():
                    break
                if writer.poll() is not None:
                    raise RuntimeError(writer.communicate()[0])
                time.sleep(.1)
            else:
                raise RuntimeError('save checkpoint did not commit: ' + str(folder))
            def run(mode):
                result = subprocess.run([str(hython), __file__, '--worker', mode, str(folder)],
                    cwd=hython.parent, env=env(mode + '-env'), capture_output=True, text=True,
                    timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
                assert result.returncode == 0, (str(folder), result.stdout, result.stderr)
                print(hython, mode, result.stdout.strip(), flush=True)
            run('alive')
            output = writer.communicate('\n', timeout=20)[0]
            assert writer.returncode == 0, output
            run('late-install')
            run('restore')
        finally:
            if writer.poll() is None:
                writer.kill()
                writer.communicate(timeout=15)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        worker(sys.argv[2], Path(sys.argv[3]))
    else:
        main()
