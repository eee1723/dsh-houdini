"""Copied saved HIP checks/rendering retain source and durable result identity."""
import importlib.util,json,sys,tempfile,threading,time
from pathlib import Path
import hou
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('isolated',ROOT/'tools/isolated-houdini-check.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
with tempfile.TemporaryDirectory(prefix='dsh-snapshot-') as raw:
    root=Path(raw);hython=Path(hou.text.expandString('$HFS'))/'bin/hython.exe'
    g=hou.node('/obj').createNode('geo','snapshot');box=g.createNode('box','OUT')
    rop=hou.node('/out').createNode('geometry','snapshot_export');rop.parm('soppath').set(box.path())
    camera=hou.node('/obj').createNode('cam','snapshot_camera');camera.parm('tz').set(4)
    camera.parmTuple('res').set((64,64))
    light=hou.node('/obj').createNode('hlight::2.0','snapshot_light');light.parmTuple('t').set((0,3,3))
    light.parm('light_type').set('point')
    image=hou.node('/out').createNode('ifd','snapshot_image');image.parm('camera').set(camera.path())
    image.parm('vm_renderengine').set('raytrace');image.parm('vm_samplesx').set(1);image.parm('vm_samplesy').set(1)
    hip=root/'saved.hip';hou.hipFile.save(str(hip));before=runner.digest(hip)
    manifest=root/'manifest.json'
    checks=[{'id':'geometry','kind':'cook','node':box.path(),'frame':1,'expect':{'points':8,'primitives':6}},
            {'id':'render','kind':'render','node':rop.path(),'frame':2,'file':'image.bgeo.sc'},
            {'id':'image','kind':'render','node':image.path(),'frame':1,'file':'image.png'}]
    manifest.write_text(json.dumps({'hip':'saved.hip','checks':checks}),encoding='utf-8')
    r=runner.check(manifest,hython,root/'run',trusted=True)
    assert r['ok'] and r['inputs_unchanged'],r
    assert runner.digest(hip)==before and r['result']['snapshot']['sha256']==before
    assert Path(r['result']['snapshot']['path']).is_relative_to(root/'run'/'inputs')
    s=runner.status(root/'run');assert s['finished'] and s['ok'] and len(s['checks'])==3,s
    assert tuple(hou.imageResolution(str(root/'run/artifacts/image/image.png')))==(64,64)
    assert not runner.status(root/'run',cancel=True)['cancel_requested'],'completed work is never restarted/cancelled'
    # A stale source edit is explicit and does not silently alter the saved copy.
    box.parm('sizex').set(3.)
    assert runner.digest(hip)==before
    # Stop an admitted expensive cook through the public status/cancel path.
    slow=g.createNode('python','slow');slow.parm('python').set('import time,hou\ntime.sleep(60)\nhou.pwd().geometry().createPoint()')
    slow.setDisplayFlag(False);box.setDisplayFlag(True)
    slowhip=root/'slow.hip';hou.hipFile.save(str(slowhip))
    manifest.write_text(json.dumps({'hip':'slow.hip','checks':[{'id':'slow','kind':'cook','node':slow.path(),'frame':1}]}),encoding='utf-8')
    seen=[]
    def cancel_running():
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            progress=root/'running'/'worker-result.json'
            if progress.exists() and runner.read_json(progress).get('phase')=='check:slow':
                seen.append(runner.status(root/'running',cancel=True));return
            time.sleep(.05)
    thread=threading.Thread(target=cancel_running);thread.start()
    try:r=runner.check(manifest,hython,root/'running',trusted=True,timeout=45)
    finally:thread.join()
    assert seen and seen[0]['cancel_requested'] and not seen[0]['finished'],seen
    assert not r['ok'] and r['worker']['status']=='cancelled',r
    assert runner.status(root/'running')['finished']
    saved=hou.node('/obj/snapshot/OUT').geometry().boundingBox().sizevec()[0]
    assert saved==3.
    # Missing output cannot be reported as a successful load/check.
    manifest.write_text(json.dumps({'hip':'saved.hip','checks':[dict(checks[0],node='/obj/missing')]}),encoding='utf-8')
    bad=runner.check(manifest,hython,root/'missing',trusted=True)
    assert not bad['ok'] and runner.status(root/'missing')['finished'],bad
    # Cancellation before start creates a terminal run without importing HIP.
    cancel=root/'cancel';cancel.write_text('cancel')
    r=runner.check(manifest,hython,root/'cancelled',trusted=True,cancel_file=cancel)
    assert r['worker']['status']=='cancelled_before_start' and not r['ok'],r
    assert runner.digest(hip)==before
print('PASS copied saved HIP: source identity, independent result/ROP, missing output, cancellation '+hou.applicationVersionString())
