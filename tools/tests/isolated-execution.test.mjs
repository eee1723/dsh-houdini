import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {createHash} from 'node:crypto'
import {executeIsolated,registerIsolatedTool} from '../../lib/isolated-execution.js'
import {HOUDINI_SCENE_TOOLS} from '../../lib/tool-catalog.js'

const root=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-isolated-tool-'))
async function canonical(filename){
  try{return await fs.realpath(filename)}catch(error){if(error.code!=='ENOENT')throw error;return path.join(await canonical(path.dirname(filename)),path.basename(filename))}
}
let mode='workspace-write',runtimeReads=0,savedImages=0
const ctx={fs:{resolve:async(filename,options={})=>({targetKey:await canonical(path.resolve(options.cwd??root,filename))}),
  processPath:ref=>ref.targetKey,processPathFromHostPath:value=>value,
  contains:(base,target)=>{const value=path.relative(base.targetKey,target.targetKey);return value===''||(!value.startsWith('..')&&!path.isAbsolute(value))},
  stat:ref=>fs.stat(ref.targetKey),readBytes:async(ref,_signal,limit)=>{const value=await fs.readFile(ref.targetKey);assert(value.length<=limit);return value}},
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
  console.log('PASS isolated Host: scoped files, retained errors/results, exact images, native background ownership, no live routing on read')
}finally {
  const resolved=path.resolve(root)
  assert.equal(path.dirname(resolved),path.resolve(os.tmpdir()));assert(path.basename(resolved).startsWith('dsh-isolated-tool-'))
  await fs.rm(resolved,{recursive:true,force:true})
}
