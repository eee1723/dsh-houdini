"""Bounded load diagnostics retain exact originals off the actor, including failure cases."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,os,sys,tempfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'houdini/python3.11libs'))
import dsh_load_warnings as warnings

def publish(capture):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=[pool.submit(capture.persist) for _ in range(2)]
        for result in results:result.result()
    return capture.reference()

def fixture(folder):
    os.environ['DSH_HOUDINI_RECOVERY_ROOT']=str(folder)
    text='HEAD missing parameter\n'+('重复{节点}🚀\\"\n'*20000)+'MIDDLE precise dependency\n'+'z'*9000+'\nTAIL missing asset'
    capture=warnings.LoadWarning(text);detail=publish(capture)
    return {'detail':detail,'preview':capture.excerpt()}

def main():
    with tempfile.TemporaryDirectory(prefix='dsh-load-warning-') as directory:
        folder=Path(directory);os.environ['DSH_HOUDINI_RECOVERY_ROOT']=str(folder)
        for text in ['', 'short warning', '首端{对象}🚀\n'+'\x00"\\😀'*20000+'\n尾端缺少资源']:
            capture=warnings.LoadWarning(text)
            assert warnings._size(capture.excerpt()[0])<=warnings.PREVIEW_BYTES
            assert 'load_warnings' not in capture.reference()
            try:capture.persist()
            except RuntimeError as error:assert 'owning thread' in str(error)
            else:raise AssertionError('actor must not write diagnostic files')
            detail=publish(capture);assert detail['status']=='stored',detail
            data=Path(detail['path']).read_bytes()
            assert hashlib.sha256(data).hexdigest()==detail['sha256']
            assert json.loads(data)['result']['load_warnings']==[text]
            assert capture._raw is None
            stamp=Path(detail['path']).stat().st_mtime_ns
            repeated=publish(warnings.LoadWarning(text))
            assert repeated['path']==detail['path'] and Path(detail['path']).stat().st_mtime_ns==stamp
            if len(text)>warnings.PREVIEW_BYTES:
                assert '首端' in capture.excerpt()[0] and '尾端' in capture.excerpt()[0] and detail['omitted_chars']>0
        blocker=folder/'blocked';blocker.write_text('file')
        with patch.object(warnings.store,'root',lambda:blocker):
            failed=warnings.LoadWarning('head\n'+'x'*100000+'\ntail');detail=publish(failed)
        assert detail['status']=='unavailable' and not detail['stored'] and 'sha256' not in detail
        assert warnings._size(failed.excerpt()[0])<=warnings.PREVIEW_BYTES and failed._raw is None
        with patch.object(warnings,'MAX_BYTES',256):
            for text in ['x'*400,'中'*100]:
                assert publish(warnings.LoadWarning(text))['status']=='unavailable'
        assert not list(folder.rglob('*.tmp'))
        original=warnings.LoadWarning('immutable original');detail=publish(original)
        Path(detail['path']).write_bytes(b'corrupt')
        assert publish(warnings.LoadWarning('immutable original'))['status']=='unavailable'
        assert Path(detail['path']).read_bytes()==b'corrupt'
    print('PASS load warnings: whole-preview budget, Unicode/control escaping, head/tail, exact archive, deduplication, I/O/quota/tamper and actor isolation')

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--fixture':print(json.dumps(fixture(Path(sys.argv[2]))))
    else:main()
