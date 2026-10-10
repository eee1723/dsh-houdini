import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {processLocalVideo,localVideoEnvironment,registerLocalVideoTool,runLocalVideoProcess} from '../../lib/video-process.js'
import {videoRuntime} from '../../lib/video-runtime.js'
const execute=promisify(execFile)
const root=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-video-process-'))
let mode='workspace-write',requests=[]
// Resolve the existing prefix like DSH's native filesystem, including symlinks.
async function canonical(filename){
  try{return await fs.realpath(filename)}catch(error){if(error.code!=='ENOENT')throw error;return path.join(await canonical(path.dirname(filename)),path.basename(filename))}
}
const context={fs:{resolve:async(filename,options={})=>({targetKey:await canonical(path.resolve(options.cwd??root,filename))}),
  processPath:ref=>ref.targetKey,processPathFromHostPath:value=>value,
  contains:(base,target)=>{const r=path.relative(base.targetKey,target.targetKey);return !r.startsWith('..')&&!path.isAbsolute(r)}},
  sandboxPolicy:{resolve:()=>({mode,workspaceRoot:root})},credentials:{resolve:()=>assert.fail('local operations never read credentials')}}
context.get=name=>context[name]
const exec={agent:{id:'local-video-session',session:{header:{cwd:root}}},signal:new AbortController().signal}
const runtime=videoRuntime(process.execPath)
const resolveRuntime=async()=>runtime
const runner=async request=>{requests.push(request);return{code:0,stdout:'{"frame":0,"total":1}\n{"frames":1,"status":"complete"}\n',stderr:'',cancelled:false}}
try{
  const output=path.join(root,'new-evidence')
  const input=path.join(root,'input video.mp4');await fs.writeFile(input,'not opened by fake runner')
  const result=await processLocalVideo(context,exec,{operation:'review',options:{video:input,output,start:1,duration:2,interval:1}},resolveRuntime,runner)
  assert(result.ok);assert.equal(result.cloud_request,false);assert.equal(result.exit_code,0);assert.equal(result.result.frames,1)
  assert.equal(requests[0].cwd,root);assert.equal(requests[0].executable,process.execPath)
  assert.deepEqual(requests[0].args.slice(-4),['--ffmpeg',runtime.ffmpeg,'--ffprobe',runtime.ffprobe])
  assert(!requests[0].args.some(value=>value.includes('Out-File')||value.includes('pwsh')))
  const environment=localVideoEnvironment({SystemRoot:'test-system',PATH:'test-path',ASR_API_KEY:'do-not-copy',OPENAI_API_KEY:'do-not-copy',HFS:'host-hfs',PYTHONPATH:'foreign-hook'})
  assert.deepEqual(environment,{SystemRoot:'test-system',PATH:'test-path',PYTHONUTF8:'1'})
  const count=requests.length
  for(const options of [{ffmpeg:input},{key_env:'SECRET'},{output:os.tmpdir()},{video:'relative.mp4'}, {question:'--help'}]){
    await assert.rejects(()=>processLocalVideo(context,exec,{operation:'review',options:{video:input,output,duration:2,...options}},resolveRuntime,runner))
  }
  await assert.rejects(()=>processLocalVideo(context,exec,{operation:'transcribe',options:{work:root}},resolveRuntime,runner),/Unsupported/)
  mode='read-only'
  await assert.rejects(()=>processLocalVideo(context,exec,{operation:'review',options:{video:input,output,duration:2}},resolveRuntime,runner),/read-only/)
  const read=await processLocalVideo(context,exec,{operation:'query-notes',options:{index:input,field:'code.rotation',view:'history'}},resolveRuntime,runner)
  assert(read.ok);assert.equal(read.readonly,true)
  assert(!requests.at(-1).args.includes('--ffmpeg'))
  await assert.rejects(()=>processLocalVideo(context,exec,{operation:'read-index',options:{index:input,output}},resolveRuntime,runner),/redirect/)
  mode='workspace-write'
  const outside=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-video-outside-'))
  try{
    await assert.rejects(()=>processLocalVideo(context,exec,{operation:'export',options:{work:outside,output:path.join(root,'exported')}},resolveRuntime,runner),/temporary input lock/)
    const junction=path.join(root,'linked');await fs.symlink(outside,junction,process.platform==='win32'?'junction':'dir')
    await assert.rejects(()=>processLocalVideo(context,exec,{operation:'review',options:{video:input,output:path.join(junction,'escape'),duration:2}},resolveRuntime,runner),/outside/)
  }finally{await fs.rm(outside,{recursive:true,force:true})}
  await fs.mkdir(output)
  await assert.rejects(()=>processLocalVideo(context,exec,{operation:'review',options:{video:input,output,duration:2}},resolveRuntime,runner),/already exists/)
  assert.equal(requests.length,count+1,'only the permitted read request was dispatched')
  const failed=await processLocalVideo(context,exec,{operation:'query-notes',options:{index:input}},resolveRuntime,async()=>({code:1,stdout:'{"plausible":"partial"}',stderr:'Source hash changed',cancelled:false}))
  assert.equal(failed.ok,false);assert.equal(failed.status,'worker_failed');assert.equal(failed.exit_code,1)
  const cancelled=await processLocalVideo(context,exec,{operation:'query-notes',options:{index:input}},resolveRuntime,async()=>({code:null,stdout:'',stderr:'',cancelled:true}))
  assert.equal(cancelled.status,'cancelled')
  const tools=[];registerLocalVideoTool({tools:{register:tool=>tools.push(tool)}},resolveRuntime)
  assert.equal(tools[0].name,'video_process');assert(!tools[0].parameters.properties.operation.enum.includes('transcribe'))

  // Native Python/FFmpeg path: local evidence outputs, then direct query without shell redirection.
  const python=process.env.DSH_VIDEO_PROCESS_TEST_PYTHON,ffmpeg=process.env.DSH_VIDEO_PROCESS_TEST_FFMPEG,ffprobe=process.env.DSH_VIDEO_PROCESS_TEST_FFPROBE
  if(python&&ffmpeg&&ffprobe){
    const actual={...videoRuntime(python),ffmpeg,ffprobe}
    const media=path.join(root,'real source.mp4')
    await execute(ffmpeg,['-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=size=96x64:rate=10:duration=2','-c:v','mpeg4',media])
    const before=await fs.readFile(media)
    const frames=path.join(root,'real-frames')
    const scanned=await processLocalVideo(context,exec,{operation:'review',options:{video:media,output:frames,start:0,duration:2,interval:1}},async()=>actual)
    assert.equal(scanned.ok,true,scanned.error);assert.equal(scanned.result.frames,2)
    const index=path.join(root,'real-index')
    const initialized=await processLocalVideo(context,exec,{operation:'index-init',options:{frames_dir:frames,output:index}},async()=>actual)
    assert.equal(initialized.ok,true,initialized.error)
    const indexFile=path.join(index,'index.json'),draft=JSON.parse(await fs.readFile(indexFile,'utf8'))
    draft.chapters=[{id:'chapter-source',title:'Local source',ranges:[[0,2]]}]
    draft.modules=[{id:'source-module',title:'Local source',ranges:[[0,2]],purpose:'Inspect local source frames',
      inputs:['source video'],outputs:['source observations'],depends_on:[],questions:[],unknowns:['No semantic review'],evidence:[]}]
    await fs.writeFile(indexFile,JSON.stringify(draft))
    const queried=await processLocalVideo(context,exec,{operation:'read-index',options:{index:path.join(index,'index.json')}},async()=>actual)
    assert.equal(queried.ok,true,queried.error);assert.equal(queried.result.structural_validation,'passed')
    assert.deepEqual(await fs.readFile(media),before)
    const rejected=await processLocalVideo(context,exec,{operation:'review',options:{video:media,output:path.join(root,'bad-flags'),unexpected_flag:'x',duration:2}},async()=>actual)
    assert.equal(rejected.ok,false);assert.equal(rejected.exit_code,2)
    await assert.rejects(()=>fs.stat(path.join(root,'bad-flags')),/ENOENT/)
    const outside=path.join(os.tmpdir(),'dsh-abbreviated-output-'+Date.now())
    const abbreviated=await processLocalVideo(context,exec,{operation:'review',options:{video:media,output:path.join(root,'alias-output'),outpu:outside,duration:2}},async()=>actual)
    assert.equal(abbreviated.ok,false);assert.equal(abbreviated.exit_code,2)
    assert.match(abbreviated.error,/unrecognized arguments/)
    await assert.rejects(()=>fs.stat(outside),/ENOENT/)
    await assert.rejects(()=>fs.stat(path.join(root,'alias-output')),/ENOENT/)
    const inputAlias=await processLocalVideo(context,exec,{operation:'read-index',options:{index:indexFile,inde:'unresolved-relative-index.json'}},async()=>actual)
    assert.equal(inputAlias.ok,false);assert.equal(inputAlias.exit_code,2)
    assert.match(inputAlias.error,/unrecognized arguments/)
    const worker=path.join(root,'tree-worker.py')
    await fs.writeFile(worker,`import os,sys,subprocess,time\nfrom pathlib import Path\nw=Path(sys.argv[1])\nc=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n(w/'descendant-pid').write_text(str(c.pid))\n(w/'.lock').write_text(str(os.getpid()))\nprint('ready',flush=True)\nif len(sys.argv)>2: print('x'*1100000,flush=True)\ntime.sleep(30)\n`)
    for(const overflow of [false,true]){
      const work=path.join(root,overflow?'overflow-tree':'cancel-tree');await fs.mkdir(work)
      const controller=new AbortController()
      const pending=runLocalVideoProcess({executable:python,args:[worker,work,...(overflow?['overflow']:[])],env:localVideoEnvironment(),cwd:root,work,signal:controller.signal})
      for(let i=0;i<200;i++){if(await fs.stat(path.join(work,'descendant-pid')).catch(()=>null))break;await new Promise(resolve=>setTimeout(resolve,10))}
      const childPid=Number(await fs.readFile(path.join(work,'descendant-pid'),'utf8'))
      if(!overflow)controller.abort()
      const ended=await pending
      assert.equal(ended.termination_error,undefined)
      if(overflow)assert.match(ended.stderr,/budget/);else assert.equal(ended.cancelled,true)
      assert.throws(()=>process.kill(childPid,0),/ESRCH|not found|No such process/,'worker and descendants are stopped before returning')
      await assert.rejects(()=>fs.stat(path.join(work,'.lock')),/ENOENT/,'only the terminated worker PID lock is removed')
    }
    await fs.writeFile(path.join(root,'.lock'),'another-worker')
    await runLocalVideoProcess({executable:python,args:['-c','print("ok")'],env:localVideoEnvironment(),cwd:root,work:root})
    assert.equal(await fs.readFile(path.join(root,'.lock'),'utf8'),'another-worker')
    console.log('Native local video review/index/query and failure-before-output passed')
  }else console.log('Native media probe not configured; fake-runner policy/serialization checks only')
}finally{await fs.rm(root,{recursive:true,force:true})}
console.log('Offline tutorial tool preserves DSH file policy, private executables, credential isolation, JSON facts and actual failure states')
