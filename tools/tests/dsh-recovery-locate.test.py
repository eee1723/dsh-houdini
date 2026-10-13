"""Saved-file discovery uses trusted checkpoint lineage, never directory contents."""
from pathlib import Path
import os,sys,tempfile,uuid
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import dsh_recovery_store as store
with tempfile.TemporaryDirectory(prefix='dsh-locate-') as directory:
    folder=Path(directory);os.environ['DSH_HOUDINI_RECOVERY_ROOT']=str(folder/'recovery')
    scene,executor=uuid.uuid4().hex,uuid.uuid4().hex
    def save(name,parent=None,scene_id=scene,source=executor):
        hip=folder/name;hip.write_bytes(name.encode())
        record={'checkpoint_id':uuid.uuid4().hex,'scene_id':scene_id,'executor_id':source,
                'source_executors':[source],'nodes':[],'saved_at':hip.stat().st_mtime_ns,
                'parent_checkpoint':parent,'hip_path':str(hip),'hou_version':'21.0'}
        return store.commit(record,store.file_stamp(hip))
    first=save('original.hip');latest=save('version2.hip',first['checkpoint_id'])
    save('unrelated.hip',scene_id=uuid.uuid4().hex)
    save('foreign.hip',source=uuid.uuid4().hex)
    found=store.locate(scene,'task',[executor]);assert [r['checkpoint_id'] for r in found['candidates']]==[latest['checkpoint_id']]
    copy=folder/'unrecorded-copy.hip';copy.write_bytes((folder/'version2.hip').read_bytes())
    assert len(store.locate(scene,'task',[executor])['candidates'])==1
    branch=save('branch.hip',first['checkpoint_id'])
    assert len(store.locate(scene,'task',[executor])['candidates'])==2,'parallel saved descendants require a content choice'
    (folder/'version2.hip').write_bytes(b'replaced')
    found=store.locate(scene,'task',[executor]);assert len(found['candidates'])==1 and len(found['unavailable'])==1
    (folder/'branch.hip').unlink()
    found=store.locate(scene,'task',[executor]);assert not found['candidates'] and len(found['unavailable'])==2
    assert all(r['checkpoint_id']!=first['checkpoint_id'] for r in found['unavailable']),'do not silently fall back to an ancestor'
    (folder/'recovery/checkpoints'/('f'*32+'.json')).write_text('{',encoding='utf-8')
    assert not store.locate(scene,'task',[executor])['candidates']
    for lease in store._LEASES.values():lease.close()
    store._LEASES.clear()
print('PASS locator: exact saved tips, alternate branches, unrelated sources, missing/replaced files and unrecorded copies')
