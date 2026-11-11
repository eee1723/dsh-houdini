"""Real H21/H22 saved editor-item provenance, copies and late replacement.

Uses owned temporary preferences and HIPs. It never attaches to a running UI.
"""
from pathlib import Path
import argparse
import json
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]


def worker(mode, folder):
    sys.path.insert(0, str(ROOT / 'houdini/python3.11libs'))
    import hou
    import dsh_bridge as bridge
    import dsh_network_notes as notes
    import dsh_network_boxes as boxes
    import dsh_ownership as ownership
    import dsh_scene_recovery as recovery
    owner, other, only, box_only = 'note-author', 'inactive-note-author', 'note-only-author', 'box-only-author'
    hip = folder / 'notes.hip'

    def run(code, author=owner):
        value = bridge.run_code(code, owner_session=author, owner_call=uuid.uuid4().hex)
        assert value['ok'], value
        return value

    def saved(path):
        hou.hipFile.save(path.as_posix())
        for _ in range(500):
            if recovery.facts()['checkpoint']['status'] == 'checkpoint_saved':
                return recovery.store.read(recovery.facts()['checkpoint_id'])
            time.sleep(.01)
        raise AssertionError(recovery.facts())

    if mode == 'save':
        run("p=tab_create('/obj','geo',name='asset')\nnetwork_notes(p,[{'name':'README','text':'original','text_size':.3}, {'name':'RENAME','text':'rename this','text_size':.6}])")
        run("network_notes('/obj/asset',[{'name':'OTHER','text':'another author'}])", other)
        run("n=tab_create('/obj/asset','null',name='source')\nnetwork_boxes('/obj/asset',[{'name':'INNER','members':[n.path()]},{'name':'OUTER','boxes':['INNER']}])")
        run("n=tab_create('/obj/asset','null',name='editable_source')\nnetwork_boxes('/obj/asset',[{'name':'SIMPLE','members':[n.path()]}])")
        parent = hou.node('/obj/asset')
        parent.findNetworkBox('INNER').addItem(parent.findStickyNote('RENAME'))
        artist = parent.createStickyNote('ARTIST'); artist.setText('original')
        parent.findNetworkBox('INNER').addItem(artist)
        other_source = parent.createNode('null', 'other_source')
        run("network_boxes('/obj/asset',[{'name':'OTHER_BOX','members':['/obj/asset/other_source']}],allow_foreign='Fixture user permits grouping this existing source')", other)
        foreign_parent = hou.node('/obj').createNode('geo', 'artist_network')
        run("network_notes('/obj/artist_network',[{'name':'ONLY','text':'note without owned parent'}])", only)
        foreign_parent.createNode('null', 'artist_source')
        run("network_boxes('/obj/artist_network',[{'name':'ONLY_BOX','members':['/obj/artist_network/artist_source']}],allow_foreign='Fixture user permits grouping this existing source')", box_only)
        run("tab_create('/mat','principledshader::2.0',name='definition_notes')")
        assert hou.node('/mat/definition_notes').isLockedHDA() and hou.node('/mat/definition_notes').stickyNotes()
        original = saved(hip)
        parent = hou.node('/obj/asset')
        parent.copyItems((parent.findStickyNote('README'),))
        copied_parent = hou.node('/obj').copyItems((parent,))[0]
        copied_parent.setName('copied_asset')
        old_tokens = notes._checkpoint_tokens(copied_parent)
        parent.findStickyNote('RENAME').setName('RENAMED')
        record = saved(hip)
        assert len(record['notes']) == 4 and all(row['parent_path'] != copied_parent.path() for row in record['notes'])
        assert old_tokens['README'] != notes._checkpoint_tokens(parent)['README']
        assert not any(row['name'] in ('ARTIST', 'README1') for row in record['notes'])
        assert any(row['name'] == 'RENAMED' for row in record['notes'])
        assert len(record['boxes']) == 5 and all(row['parent_path'] != copied_parent.path() for row in record['boxes'])
        assert not any(row['parent_path'].startswith('/mat/definition_notes') for row in [*record['notes'], *record['boxes']]), 'definition-owned editor items are not fresh-load instance evidence'
        assert ownership.records().get(int(foreign_parent.sessionId())) is None
        (folder / 'ready.json').write_text(json.dumps({'executor': bridge._EXECUTOR_ID,
            'checkpoint': record['checkpoint_id'], 'scene': record['scene_id'], 'version': hou.applicationVersionString()}), encoding='utf-8')
        print(json.dumps({'version': hou.applicationVersionString(), 'saved_notes': len(record['notes']), 'saved_boxes': len(record['boxes']),
                          'copied_parent_tokens_rotated': True, 'renamed_original_saved': True}), flush=True)
        return

    prior = json.loads((folder / 'ready.json').read_text())

    def load(path=hip):
        hou.hipFile.load(path.as_posix(), suppress_save_prompt=True, ignore_load_warnings=True)
        for _ in range(500):
            if recovery._PROVEN:
                return recovery.store.read(recovery.facts()['checkpoint_id'])
            time.sleep(.01)
        raise AssertionError('No trusted load')

    def prepare(record, author=owner, sources=None):
        sources = sources or [prior['executor']]
        recovery.store.require_task_source(record, author, sources)
        digest, _ = recovery.store.file_digest(hou.hipFile.path())
        assert digest == record['file_sha256']
        assessment = recovery.preview(record, author, sources[-1], record['scene_id'])
        operation = uuid.uuid4().hex
        result = recovery.prepare(record, author, sources[-1], operation, assessment, expected_scene=record['scene_id'])
        return operation, result

    def status(path, name, author=owner):
        return notes.note_provenance(hou.node(path).findStickyNote(name), author)['status']

    def box_status(path, name, author=owner):
        return boxes.box_provenance(hou.node(path).findNetworkBox(name), author)['status']

    if mode == 'verify-combinations':
        combinations = json.loads((folder / 'combinations.json').read_text())
        sources = [prior['executor'], combinations['executor']]
        for filename in ('failed-save-continued.hip', 'undo-continued.hip'):
            record = load(folder / filename)
            assert not notes.ownership_snapshot() and not boxes.ownership_snapshot() and not ownership.records()
            operation, prepared = prepare(record, sources=sources)
            assert prepared['restored_notes'] == 2 and prepared['restored_boxes'] == 3, prepared
            assert not prepared['unrestored_notes'] and not prepared['unrestored_boxes'], prepared
            recovery.activate(operation, owner)
            assert status('/obj/asset', 'README') == box_status('/obj/asset', 'SIMPLE') == 'owned_current_session'
            assert status('/obj/asset', 'README1') == box_status('/obj/copied_asset', 'SIMPLE') == 'foreign'
            assert status('/obj/asset', 'ARTIST') == 'foreign'
            parent = hou.node('/obj/asset')
            assert parent.findStickyNote('README').text() == 'original'
            assert abs(parent.findStickyNote('README').textSize() - .3) < 1e-6
            assert abs(parent.findStickyNote('RENAMED').textSize() - .6) < 1e-6
            assert parent.findNetworkBox('SIMPLE').comment() == 'SIMPLE'
            assert parent.findStickyNote('TRANSIENT') is None and parent.findNetworkBox('TRANSIENT_BOX') is None
            assert parent.node('editable_source').parentNetworkBox() == parent.findNetworkBox('SIMPLE')
            assert parent.findStickyNote('RENAMED').parentNetworkBox() == parent.findNetworkBox('INNER')
            assert parent.findNetworkBox('INNER').parentNetworkBox() == parent.findNetworkBox('OUTER')
            run("network_notes('/obj/asset',[{'name':'README','text':'new process can edit'}])\nnetwork_boxes('/obj/asset',[{'name':'SIMPLE','label':'New process can edit','members':['/obj/asset/editable_source']}])")
            other_operation, other_prepared = prepare(record, other, sources)
            assert other_prepared['restored_notes'] == other_prepared['restored_boxes'] == 1
            recovery.activate(other_operation, other)
            assert status('/obj/asset', 'OTHER', other) == box_status('/obj/asset', 'OTHER_BOX', other) == 'owned_current_session'
        print(json.dumps({'version': hou.applicationVersionString(), 'fresh_process_after_failed_save': True,
            'fresh_process_after_restored_edit_undo': True, 'inactive_author_and_foreign_boundaries_preserved': True}), flush=True)
        return

    record = load()
    assert not notes.ownership_snapshot() and not boxes.ownership_snapshot() and not ownership.records()
    operation, prepared = prepare(record)
    assert prepared['restored_notes'] == 2 and not prepared['unrestored_notes'], prepared
    assert prepared['restored_boxes'] == 3 and not prepared['unrestored_boxes'], prepared
    assert status('/obj/asset', 'README') == 'foreign', 'preparation never grants authority'
    recovery.activate(operation, owner)
    assert status('/obj/asset', 'README') == 'owned_current_session'
    assert status('/obj/asset', 'RENAMED') == 'owned_current_session'
    assert abs(hou.node('/obj/asset').findStickyNote('README').textSize() - .3) < 1e-6
    assert abs(hou.node('/obj/asset').findStickyNote('RENAMED').textSize() - .6) < 1e-6
    assert box_status('/obj/asset', 'INNER') == box_status('/obj/asset', 'OUTER') == 'owned_current_session'
    assert box_status('/obj/copied_asset', 'INNER') == box_status('/obj/asset', 'OTHER_BOX') == 'foreign'
    parent = hou.node('/obj/asset')
    assert parent.findStickyNote('RENAMED').parentNetworkBox() == parent.findNetworkBox('INNER')
    assert parent.findNetworkBox('INNER').parentNetworkBox() == parent.findNetworkBox('OUTER')
    run("__result__=network_boxes('/obj/asset',[{'name':'SIMPLE','label':'Restored group','members':['/obj/asset/editable_source']}])")
    for parent, name in [('/obj/asset', 'README1'), ('/obj/asset', 'ARTIST'), ('/obj/copied_asset', 'README'), ('/obj/asset', 'OTHER')]:
        assert status(parent, name) == 'foreign', (parent, name)
    run("network_notes('/obj/asset',[{'name':'README','text':'restored edit'}])")
    run("network_notes('/obj/asset',[{'name':'README','text_size':.45}])")
    assert abs(hou.node('/obj/asset').findStickyNote('README').textSize() - .45) < 1e-6
    only_op, only_prepared = prepare(record, only)
    assert only_prepared['restored_nodes'] == 0 and only_prepared['restored_notes'] == 1
    recovery.activate(only_op, only)
    run("network_notes('/obj/artist_network',[{'name':'ONLY','text':'restored independently'}])", only)
    assert ownership.records().get(int(hou.node('/obj/artist_network').sessionId())) is None
    box_operation, box_prepared = prepare(record, box_only)
    assert box_prepared['restored_nodes'] == box_prepared['restored_notes'] == 0 and box_prepared['restored_boxes'] == 1
    recovery.activate(box_operation, box_only)
    assert box_status('/obj/artist_network', 'ONLY_BOX', box_only) == 'owned_current_session'
    assert ownership.records().get(int(hou.node('/obj/artist_network/artist_source').sessionId())) is None

    # Save without activating the other author: its trusted independent source survives.
    continued = saved(folder / 'continued.hip')
    other_row = next(row for row in continued['notes'] if row['owner']['session'] == other)
    assert other_row['source_executor'] == prior['executor']
    assert next(row for row in continued['boxes'] if row['owner']['session'] == other)['source_executor'] == prior['executor']
    continued = load(folder / 'continued.hip')
    other_op, _ = prepare(continued, other)
    recovery.activate(other_op, other)
    assert status('/obj/asset', 'OTHER', other) == 'owned_current_session'
    assert box_status('/obj/asset', 'OTHER_BOX', other) == 'owned_current_session'

    # A same-name replacement before preparation cannot inherit a saved token.
    record = load()
    parent = hou.node('/obj/asset')
    parent.findStickyNote('README').destroy()
    parent.createStickyNote('README').setText('original')
    operation, prepared = prepare(record)
    assert prepared['restored_notes'] == 1 and prepared['unrestored_notes'], prepared
    recovery.activate(operation, owner)
    assert status('/obj/asset', 'README') == 'foreign'

    # Replacement after preparation fails activation and rolls back node grants too.
    record = load()
    operation, prepared = prepare(record)
    parent = hou.node('/obj/asset')
    parent.findStickyNote('README').destroy()
    parent.createStickyNote('README').setText('original')
    try:
        recovery.activate(operation, owner)
        raise AssertionError('late replacement was accepted')
    except RuntimeError as error:
        assert 'sticky_note changed' in str(error), error
    assert not ownership.records() and not notes.ownership_snapshot() and not boxes.ownership_snapshot()

    # A late Network Box replacement also rolls back grants of nodes and notes.
    record = load()
    operation, prepared = prepare(record)
    parent = hou.node('/obj/asset')
    parent.findNetworkBox('OUTER').destroy()
    parent.createNetworkBox('OUTER')
    try:
        recovery.activate(operation, owner)
        raise AssertionError('late box replacement was accepted')
    except RuntimeError as error:
        assert 'network_box changed' in str(error), error
    assert not ownership.records() and not notes.ownership_snapshot() and not boxes.ownership_snapshot()

    # Whole-network copies with copied metadata cannot replace the observed parent.
    record = load()
    parent = hou.node('/obj/asset')
    replacement = hou.node('/obj').copyItems((parent,))[0]
    parent.destroy()
    replacement.setName('asset')
    operation, prepared = prepare(record)
    assert prepared['restored_nodes'] == 1 and prepared['restored_notes'] == prepared['restored_boxes'] == 0
    recovery.activate(operation, owner)
    assert status('/obj/asset', 'README') == 'foreign'
    assert box_status('/obj/asset', 'INNER') == 'foreign'

    # Rename keeps the exact fresh-load item; copying its token onto a new item does not.
    record = load()
    parent = hou.node('/obj/asset')
    parent.findStickyNote('README').setName('USER_RENAMED')
    parent.findNetworkBox('OUTER').setName('BOX_RENAMED')
    forged = parent.createStickyNote('FORGED')
    tokens = notes._checkpoint_tokens(parent)
    tokens['FORGED'] = tokens['README']
    parent.setUserData(notes.CHECKPOINT_KEY, json.dumps(tokens))
    forged_box = parent.createNetworkBox('FORGED_BOX')
    box_tokens = boxes._CHECKPOINTS.tokens(parent)
    box_tokens['FORGED_BOX'] = box_tokens['OUTER']
    parent.setUserData(boxes.CHECKPOINT_KEY, json.dumps(box_tokens))
    operation, prepared = prepare(record)
    recovery.activate(operation, owner)
    assert status('/obj/asset', 'USER_RENAMED') == 'owned_current_session'
    assert notes.note_provenance(forged, owner)['status'] == 'foreign'
    assert box_status('/obj/asset', 'BOX_RENAMED') == 'owned_current_session'
    assert boxes.box_provenance(forged_box, owner)['status'] == 'foreign'
    renamed = saved(folder / 'renamed.hip')
    assert any(row['name'] == 'USER_RENAMED' for row in renamed['notes'])
    assert not any(row['name'] == 'FORGED' for row in renamed['notes'])
    assert any(row['name'] == 'BOX_RENAMED' for row in renamed['boxes'])
    assert not any(row['name'] == 'FORGED_BOX' for row in renamed['boxes'])

    # A legacy checkpoint with no independent note records cannot acquire them.
    record = load()
    legacy = {key: value for key, value in record.items() if key not in ('notes', 'boxes')}
    operation, prepared = prepare(legacy)
    assert prepared['restored_notes'] == prepared['restored_boxes'] == 0
    recovery.activate(operation, owner)
    assert status('/obj/asset', 'README') == 'foreign'
    assert box_status('/obj/asset', 'OUTER') == 'foreign'
    bad = {**record, 'notes': [{**row, 'source_executor': 'a' * 32} for row in record['notes']]}
    try:
        recovery.store.require_task_source(bad, only, [prior['executor']])
        raise AssertionError('note-only foreign source was accepted')
    except RuntimeError:
        pass

    # A real native save failure rotates tokens; the following successful save
    # must retain both active and inactive item provenance without a false tip.
    record = load()
    operation, _ = prepare(record)
    recovery.activate(operation, owner)
    saved_parent = record['checkpoint_id']
    blocked = folder / 'cannot-save.hip'
    blocked.mkdir()
    try:
        hou.hipFile.save(blocked.as_posix())
        raise AssertionError('saving a HIP over a directory unexpectedly succeeded')
    except hou.OperationFailed:
        pass
    assert recovery.facts()['checkpoint']['status'] == 'save_failed', recovery.facts()
    after_failed_save = saved(folder / 'failed-save-continued.hip')
    assert after_failed_save['parent_checkpoint'] == saved_parent
    assert len(after_failed_save['notes']) == 4 and len(after_failed_save['boxes']) == 5

    # Restore -> multiple note/box edits -> native Undo -> save. The next worker
    # proves that restored/recreated identities remain recoverable across a PID.
    record = load()
    operation, _ = prepare(record)
    recovery.activate(operation, owner)
    assert hou.undos.areEnabled(), 'this combination must exercise native Undo, not only compensation'
    failed = bridge.run_code("network_notes('/obj/asset',[{'name':'README','text':'transient','text_size':.9}, {'name':'TRANSIENT','text':'temporary','text_size':.5}])\n"
        "network_boxes('/obj/asset',[{'name':'SIMPLE','label':'Transient label','members':['/obj/asset/editable_source']}])\n"
        "network_boxes('/obj/asset',[{'name':'TRANSIENT_BOX','members':['/obj/asset/editable_source']}])\n"
        "network_notes('/obj/asset',remove=['README'])\nraise RuntimeError('after recovered editor changes')",
        owner_session=owner, owner_call='restored-edit-undo')
    assert not failed['ok'] and failed['rollback']['applied'], failed
    assert failed['rollback']['network_notes']['ok'] and failed['rollback']['network_boxes']['ok'], failed
    parent = hou.node('/obj/asset')
    assert parent.findStickyNote('README').text() == 'original'
    assert abs(parent.findStickyNote('README').textSize() - .3) < 1e-6
    assert parent.findNetworkBox('SIMPLE').comment() == 'SIMPLE'
    assert parent.findStickyNote('TRANSIENT') is None and parent.findNetworkBox('TRANSIENT_BOX') is None
    assert status('/obj/asset', 'README') == box_status('/obj/asset', 'SIMPLE') == 'owned_current_session'
    after_undo = saved(folder / 'undo-continued.hip')
    assert len(after_undo['notes']) == 4 and len(after_undo['boxes']) == 5
    (folder / 'combinations.json').write_text(json.dumps({'executor': bridge._EXECUTOR_ID}), encoding='utf-8')
    print(json.dumps({'version': hou.applicationVersionString(), 'restored_notes': True, 'restored_boxes': True,
        'foreign_parent_not_owned': True, 'copied_notes_and_networks_foreign': True,
        'late_replacement_atomic': True, 'inactive_author_preserved': True,
        'rename_survives': True, 'forged_tokens_foreign': True, 'legacy_unclaimed': True}), flush=True)


def main():
    sys.path.insert(0, str(ROOT / 'tools'))
    from houdini_test_environment import isolated_environment, reexec_unpacked_test_cli
    reexec_unpacked_test_cli()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hython', nargs='+', type=Path)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    output = args.output_dir.resolve() if args.output_dir else Path(tempfile.mkdtemp(prefix='dsh-note-recovery-'))
    output.mkdir(parents=True, exist_ok=True)
    for index, executable in enumerate(args.hython):
        hython = executable.resolve(strict=True)
        folder = output / str(index)
        folder.mkdir(exist_ok=False)
        for mode in ('save', 'restore', 'verify-combinations'):
            env = isolated_environment(folder / (mode + '-env'), executable=hython)
            env.update(DSH_HOUDINI_RECOVERY_ROOT=str(folder / 'recovery'), HOUDINI_PATH=(ROOT / 'houdini').as_posix() + ';&')
            result = subprocess.run([str(hython), __file__, '--worker', mode, str(folder)], cwd=hython.parent,
                env=env, capture_output=True, text=True, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
            (folder / (mode + '.log')).write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
            assert result.returncode == 0, (str(folder), result.stdout, result.stderr)
            print(str(hython), mode, result.stdout.strip(), flush=True)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        worker(sys.argv[2], Path(sys.argv[3]))
    else:
        main()
