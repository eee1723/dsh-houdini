import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {createHash} from 'node:crypto'
import {executeIsolated,registerIsolatedTool,isolatedInstallationRuntime} from '../../lib/isolated-execution.js'
import {HOUDINI_SCENE_TOOLS} from '../../lib/tool-catalog.js'

// DSH resolves local paths to their real spelling, including Windows TEMP aliases.
const root=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'dsh-isolated-tool-')))
async function canonical(filename){
  try{return await fs.realpath(filename)}catch(error){if(error.code!=='ENOENT')throw error;return path.join(await canonical(path.dirname(filename)),path.basename(filename))}
}
let mode='workspace-write',runtimeReads=0,savedImages=0,deniedInput,unreadableReport
const inputStats=[],jsonReads=[]
const ctx={fs:{resolve:async(filename,options={})=>({targetKey:await canonical(path.resolve(options.cwd??root,filename))}),
  processPath:ref=>ref.targetKey,processPathFromHostPath:value=>value,
  contains:(base,target)=>{const value=path.relative(base.targetKey,target.targetKey);return value===''||(!value.startsWith('..')&&!path.isAbsolute(value))},
  stat:ref=>{inputStats.push(ref.targetKey);if(ref.targetKey===deniedInput)throw Error('DSH input read policy denied');return fs.stat(ref.targetKey)},
  readBytes:async(ref,_signal,limit)=>{jsonReads.push({path:ref.targetKey,limit});if(ref.targetKey===unreadableReport)throw Error('report read failed');const value=await fs.readFile(ref.targetKey);assert(value.length<=limit);return value}},
  sandboxPolicy:{resolve:()=>({mode,workspaceRoot:root})},
  llm:{resolveModelInfo:async()=>({inputModalities:['text','image']})},
  attachments:{imageLimits:{maxImagesPerMessage:4,maxImageBytes:100000,maxMessageImageBytes:200000},
    saveImage:async({data,mediaType})=>{savedImages++;return {attachmentId:'unit-image',mediaType,bytes:data.length}}},
}
ctx.get=name=>ctx[name]
const exec={agent:{id:'isolated-tool-owner',options:{provider:'test',model:'image'},session:{header:{cwd:root}}},callId:'run-1',rootCallId:'run-1',signal:new AbortController().signal}
const runtimeResolver=async()=>{runtimeReads++;return {python:process.execPath,hython:process.execPath,hfs:path.dirname(process.execPath)}}
const pixel=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a+p8AAAAASUVORK5CYII=','base64')
let processRequests=[]
async function runner(request){
  processRequests.push(request)
  await fs.mkdir(path.join(request.output,'artifacts','image'),{recursive:true})
  await fs.writeFile(path.join(request.output,'artifacts','image','test.png'),pixel)
  const report={ok:true,finished:true,run_id:'unit-run',phase:'completed',inputs_unchanged:true,
    worker:{status:'completed',returncode:0,output:'verbose process log'},
    result:{ok:true,phase:'completed',runtime:{runtime_id:'independent-unit-runtime'},
      builder:{ok:true,result:{width:5},outcome:{batch:'completed'},verbs:[{verb:'set_parms'}],
        stdout:'[verb] set_parms echo\nMeasured width: 5 m',stderr:'Authored diagnostic'},
      checks:[{id:'image',kind:'render',status:'passed',artifact:{file:'artifacts/image/test.png',bytes:pixel.length,sha256:createHash('sha256').update(pixel).digest('hex')},execution:{ok:true,result:{fresh:true}}}]}}
  await fs.writeFile(path.join(request.output,'report.json'),JSON.stringify(report))
  return {exit_code:0,cancel_requested:false,stderr:''}
}
try {
  const manifest=path.join(root,'manifest.json')
  await fs.writeFile(path.join(root,'build.py'),'__result__={"width":5}')
  await fs.writeFile(manifest,JSON.stringify({script:'build.py',checks:[{id:'geometry',kind:'cook',node:'/obj/a/OUT',frame:1}]}))
  await assert.rejects(isolatedInstallationRuntime('relative-hfs'),/absolute Houdini installation/)
  const ambiguousHfs=path.join(root,'ambiguous-HFS')
  await fs.mkdir(ambiguousHfs)
  if(process.platform==='win32'){
    for(const folder of ['python311','python313']){
      await fs.mkdir(path.join(ambiguousHfs,folder));await fs.writeFile(path.join(ambiguousHfs,folder,'python.exe'),'not executed')
    }
    await assert.rejects(isolatedInstallationRuntime(ambiguousHfs),/exactly one bundled Python.*found 2/,
      'an explicit installation cannot silently choose a Python version when its layout is ambiguous')
  }
  const output=path.join(root,'run')
  const result=await executeIsolated(ctx,exec,{manifest,output_dir:output},runtimeResolver,runner)
  assert.equal(result.kind,'isolated-houdini');assert.equal(result.report.result.builder.result.width,5)
  assert.equal(result.report.result.builder.stdout,'Measured width: 5 m')
  assert.equal(result.report.result.builder.stderr,'Authored diagnostic')
  assert.equal(result.report.worker.output,undefined,'verbose process output remains in the retained report')
  assert.equal(result.execution,undefined,'independent execution never projects a live observation')
  assert.equal(result.process.exit_code,0);assert.equal(savedImages,1)
  assert(!HOUDINI_SCENE_TOOLS.has('houdini_isolated'))
  const definitions=new Map()
  registerIsolatedTool({...ctx,tools:{register:def=>definitions.set(def.name,def)}},{},{runtimeResolver,runner})
  const tool=definitions.get('houdini_isolated')
  const read=await tool.execute({operation:'read',output_dir:output},exec)
  assert.equal(runtimeReads,1,'reading a completed run never resolves the current Houdini')
  assert.equal(tool.output.render({},read).filter(item=>item.type==='image').length,1)
  assert.deepEqual(JSON.parse(JSON.stringify(read)),read,'public canonical values are lossless JSON')
  await fs.writeFile(path.join(output,'artifacts/image/test.png'),'changed after check')
  const changed=await executeIsolated(ctx,exec,{operation:'read',output_dir:output},runtimeResolver,runner)
  assert.equal(changed.imageAttachments[0].attachment,undefined)
  assert.match(changed.imageAttachments[0].error,/differs/)
  await assert.rejects(()=>executeIsolated(ctx,exec,{manifest,output_dir:output},runtimeResolver,runner),/already exists/)
  mode='read-only'
  await assert.rejects(()=>executeIsolated(ctx,exec,{manifest,output_dir:path.join(root,'denied')},runtimeResolver,runner),/read-only/)
  mode='workspace-write'
  await assert.rejects(()=>executeIsolated(ctx,exec,{manifest,output_dir:path.join(os.tmpdir(),'outside-workspace')},runtimeResolver,runner),/writable workspace/)
  let spec
  ctx.jobs={start:value=>{spec=value;return 'houdini-test-owned'}}
  const background=await executeIsolated(ctx,exec,{manifest,output_dir:path.join(root,'background'),background:true},runtimeResolver,runner)
  assert.equal(background.job_id,'houdini-test-owned');assert.equal(spec.owner,exec.agent.id)
  assert.deepEqual(spec.toolCall,{callId:'run-1',rootCallId:'run-1'})
  const before=processRequests.length
  assert.equal(before,1,'job registration does not start work before DSH admission')
  const hooks=spec.run({updateProgress(){}})
  const terminal=await hooks.done
  assert.equal(terminal.status,'completed');assert.equal(processRequests.length,before+1)
  assert.match(terminal.result,/operation=.?read|operation=\\?"read/)
  const failureRunner=async request=>({...await runner(request),exit_code:1})
  await executeIsolated(ctx,exec,{manifest,output_dir:path.join(root,'late-process-failure'),background:true},runtimeResolver,failureRunner)
  const failed=await spec.run({updateProgress(){}}).done
  assert.equal(failed.status,'failed','a successful worker report does not cover a failed checker process')
  assert.equal(JSON.parse(failed.result).ok,false)
  const rejected=await executeIsolated(ctx,exec,{manifest,output_dir:path.join(root,'preflight')},runtimeResolver,
    async()=>({exit_code:1,cancel_requested:false,stderr:'',stdout:'{"ok":false,"phase":"preflight","error":"declared dependency is missing"}\n'}))
  assert.equal(rejected.ok,false);assert.equal(rejected.error,'declared dependency is missing')
  assert.match(rejected.report_error,/report.json|ENOENT/,'a missing report remains secondary diagnostic evidence')
  const layout=JSON.parse(await fs.readFile(new URL('../../houdini/project-layout.json',import.meta.url),'utf8'))
  const policy=JSON.parse(await fs.readFile(new URL('../../houdini/result-detail-policy.json',import.meta.url),'utf8'))
  const defaults=await Promise.all([executeIsolated(ctx,exec,{manifest},runtimeResolver,runner),executeIsolated(ctx,exec,{manifest},runtimeResolver,runner)])
  assert.notEqual(defaults[0].run_directory,defaults[1].run_directory,'concurrent default runs have independent exclusive destinations')
  assert(defaults.every(value=>path.dirname(value.run_directory)===path.join(root,layout.directories.execution_run.path)),
    'default execution evidence follows the shared role under the DSH workspace without a scene query')
  assert.equal(layout.directories.execution_run.lifecycle,'execution-evidence')
  assert.equal(layout.directories.visual_check.path,'dsh-artifacts/checks/previews')
  assert(tool.parameters.properties.output_dir)
  assert(!tool.parameters.required?.includes('output_dir'),'registered DSH schema keeps run output_dir optional')
  const readsBeforeMissing=runtimeReads
  await assert.rejects(()=>executeIsolated(ctx,exec,{operation:'read'},runtimeResolver,runner),/original absolute output_dir/)
  assert.equal(runtimeReads,readsBeforeMissing,'read cannot silently allocate a replacement run')

  const freshWorkspace=path.join(root,'admission'),freshExec={...exec,agent:{...exec.agent,session:{header:{cwd:freshWorkspace}}}}
  await fs.mkdir(freshWorkspace)
  ctx.jobs={start:()=>{throw Error('DSH admission rejected')}}
  await assert.rejects(()=>executeIsolated(ctx,freshExec,{manifest,background:true},runtimeResolver,runner),/admission rejected/)
  assert.equal(await fs.stat(path.join(freshWorkspace,'dsh-artifacts')).catch(()=>null),null,'rejected job admission creates no fake run or artifact directories')
  ctx.jobs={start:value=>{spec=value;return 'admitted-default'}}
  const admitted=await executeIsolated(ctx,freshExec,{manifest,background:true},runtimeResolver,runner)
  assert.equal(await fs.stat(admitted.run_directory).catch(()=>null),null,'the checker creates the run only after admission calls run')
  assert.equal((await spec.run({updateProgress(){}}).done).status,'completed')

  const sourceRoot=path.join(root,'source'),manifestDir=path.join(root,'manifests'),combined=path.join(manifestDir,'hip-and-setup.json')
  await fs.mkdir(path.join(sourceRoot,'assets'),{recursive:true});await fs.mkdir(manifestDir)
  await fs.writeFile(path.join(sourceRoot,'saved.hip'),'saved-input')
  await fs.writeFile(path.join(sourceRoot,'setup.py'),'set_parms("/stage/settings", {"samplesperpixel": 4})')
  await fs.writeFile(path.join(sourceRoot,'assets/helper.txt'),'declared dependency')
  const combinedManifest={input_root:'../source',hip:'saved.hip',script:'setup.py',files:['assets/helper.txt'],checks:[]}
  await fs.writeFile(combined,JSON.stringify(combinedManifest))
  inputStats.length=0
  await executeIsolated(ctx,exec,{manifest:combined,output_dir:path.join(root,'combined')},runtimeResolver,runner)
  for(const file of ['saved.hip','setup.py','assets/helper.txt'])assert(inputStats.includes(path.join(sourceRoot,file)),
    'HIP, post-load setup and every dependency must pass DSH read policy: '+file)
  deniedInput=path.join(sourceRoot,'setup.py')
  const beforeDenied=runtimeReads
  await assert.rejects(()=>executeIsolated(ctx,exec,{manifest:combined,output_dir:path.join(root,'denied-setup')},runtimeResolver,runner),/DSH input read policy denied/)
  assert.equal(runtimeReads,beforeDenied,'a denied setup input fails before resolving Houdini or creating a run')
  assert.equal(await fs.stat(path.join(root,'denied-setup')).catch(()=>null),null)
  deniedInput=undefined
  await fs.writeFile(combined,JSON.stringify({...combinedManifest,input_root:sourceRoot}))
  await executeIsolated(ctx,exec,{manifest:combined,output_dir:path.join(root,'absolute-root')},runtimeResolver,runner)
  await fs.writeFile(combined,JSON.stringify({...combinedManifest,files:['../outside.py']}))
  await assert.rejects(()=>executeIsolated(ctx,exec,{manifest:combined,output_dir:path.join(root,'escaped-input')},runtimeResolver,runner),/safe relative files/)

  const legacyDir=path.join(root,'legacy-large');await fs.mkdir(legacyDir)
  const legacy={ok:false,finished:true,phase:'worker_result',run_id:'large-legacy',error:'original geometry check failure',
    worker:{status:'failed',returncode:1},result:{ok:false,phase:'check:geometry',builder:{ok:true,stdout:'',stderr:'',result:{large:'x'.repeat(5*1024*1024)}},
      checks:[{id:'geometry',status:'failed',execution:{ok:false,error:'original geometry check failure',stdout:'',stderr:'',
        execution:{runtime_id:'legacy-runtime'},outcome:{batch:'failed'},transaction:{status:'rolled_back'},evidence:[{reason:'author assertion'}]}}]}}
  await fs.writeFile(path.join(legacyDir,'report.json'),JSON.stringify(legacy))
  const legacyRead=await executeIsolated(ctx,exec,{operation:'read',output_dir:legacyDir},runtimeResolver,runner)
  assert.equal(legacyRead.report.error,legacy.error,'a legacy report above the manifest limit retains its original error')
  assert.equal(legacyRead.report.result.builder.result.large.length,5*1024*1024)
  assert.deepEqual(legacyRead.report.result.checks[0].execution.transaction,{status:'rolled_back'})
  assert.deepEqual(legacyRead.report.result.checks[0].execution.evidence,[{reason:'author assertion'}])
  assert.equal(jsonReads.findLast(value=>value.path===path.join(legacyDir,'report.json')).limit,policy.maxArchiveBytes)
  assert(jsonReads.filter(value=>value.path===manifest).every(value=>value.limit===4*1024*1024),'manifest keeps its separate small-document limit')

  const compactDir=path.join(root,'compact');await fs.mkdir(compactDir)
  const details={stored:true,path:path.join(compactDir,'executions/builder.json'),sha256:'a'.repeat(64),bytes:99999,format:'returned_bridge_envelope_json'}
  const compactEnvelope={ok:false,error:'original low-level error',stdout:'authored observation',stderr:'',result:{detail_pointer:'/result'},
    details,evidence:[{status:'failed',reason:'author check'}],outcome:{batch:'failed'},transaction:{status:'rolled_back'},execution:{runtime_id:'compact-runtime',owner_session:'independent-author'}}
  await fs.writeFile(path.join(compactDir,'report.json'),JSON.stringify({ok:false,finished:true,error:compactEnvelope.error,
    worker:{status:'failed'},result:{builder:compactEnvelope,checks:[{id:'check',status:'failed',execution:compactEnvelope}]}}))
  const compactRead=await executeIsolated(ctx,exec,{operation:'read',output_dir:compactDir},runtimeResolver,runner)
  for(const envelope of [compactRead.report.result.builder,compactRead.report.result.checks[0].execution]){
    assert.deepEqual(envelope,compactEnvelope,'Host preserves the checker projection and details without a second status interpretation')
    assert.equal(envelope.details_pointer,undefined,'original execution archives remain the detail address')
  }
  const brokenOutput=path.join(root,'unreadable-report')
  unreadableReport=path.join(brokenOutput,'report.json')
  const recorded={run_id:'recorded-failure',finished:true,ok:false,phase:'worker_result',error:'actual renderer failure',report:unreadableReport}
  const unreadable=await executeIsolated(ctx,exec,{manifest,output_dir:brokenOutput},runtimeResolver,async request=>{
    await runner(request)
    return {exit_code:1,cancel_requested:false,stderr:'',stdout:JSON.stringify(recorded)+'\n'}
  })
  assert.equal(unreadable.error,recorded.error,'a report retrieval problem cannot replace the original recorded execution error')
  assert.deepEqual(unreadable.reported_status,recorded)
  assert.match(unreadable.report_error,/report read failed/)
  unreadableReport=undefined
  console.log('PASS isolated Host: shared/default run roles, admission timing, HIP+setup input policy, legacy report budget, compact original facts, exact images and native jobs')
}finally {
  const resolved=path.resolve(root)
  assert.equal(path.dirname(resolved),await fs.realpath(os.tmpdir()));assert(path.basename(resolved).startsWith('dsh-isolated-tool-'))
  await fs.rm(resolved,{recursive:true,force:true})
}
