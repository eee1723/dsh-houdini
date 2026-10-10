import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {createHash} from 'node:crypto'
import {Session} from '@deepseek-ai/dsh-session'
import {ExecutorBinding} from '../../lib/executor-binding.js'
import {generateImage,imageModels,registerImageTools} from '../../lib/image-generation.js'

const root=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-image-unit-'))
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z8S8AAAAASUVORK5CYII=','base64')
const secret='test-secret-never-present-in-result'
const digest=bytes=>createHash('sha256').update(bytes).digest('hex')
const profile={api:'openai-completions',baseURL:'https://configured.example/v1',apiKeyEnv:'IMAGE_TEST_KEY',models:[]}
const exec={agent:{id:'image-unit-session',session:{header:{cwd:root}}},callId:'image-unit-call',route:{provider:'chat',model:'vision'},signal:new AbortController().signal}
async function canonical(filename) {
  try {return await fs.realpath(filename)}
  catch(e){if(e.code!=='ENOENT')throw e;return path.join(await canonical(path.dirname(filename)),path.basename(filename))}
}
const filesystem={
  resolve:async(filename,opts={})=>{const p=await canonical(path.resolve(opts.cwd??root,filename));return {targetKey:p,displayPath:p}},
  processPath:t=>t.targetKey,processPathFromHostPath:p=>p,
  contains:(a,b)=>{const r=path.relative(a.targetKey,b.targetKey);return !r.startsWith('..')&&!path.isAbsolute(r)},
  stat:async t=>{try{return await fs.stat(t.targetKey)}catch(e){if(e.code!=='ENOENT')throw e}},
  readBytes:(t,_signal,limit)=>fs.readFile(t.targetKey).then(bytes=>{assert(bytes.length<=limit);return bytes}),
}
let mode='workspace-write',previewError=false,recoveryError=false,resolveCount=0,recordReads=0
const context={fs:filesystem,sandboxPolicy:{resolve:()=>({mode,workspaceRoot:root})},
  settings:{describe:()=>[{ns:'model-test',value:{providers:{chosen:profile}}}]},
  llm:{listProviders:()=>[{id:'chosen',name:'Chosen'}],listConfigurableProviders:()=>[{provider:'chosen',settingsNs:'model-test',settingsPath:['providers','chosen']}],
    listModels:async()=>[{id:'gpt-image-2.5-sunburst',name:'Requested image model'},{id:'chat',name:'Chat'}],
    resolveModelInfo:async()=>({inputModalities:['text','image']})},
  credentials:{resolve:async ref=>{assert.equal(ref,'IMAGE_TEST_KEY');resolveCount++;return {value:secret}},readRecord:()=>{recordReads++;throw Error('must not guess private adapter records')}},
  attachments:{imageLimits:{maxImageBytes:20*1024*1024},validateImage:async ({data})=>assert.deepEqual(Buffer.from(data),png),
    saveFile:async({data,name})=>{if(recoveryError)throw Error('attachment disk full');const id=digest(data);await fs.writeFile(path.join(root,id),data);return {id,name}},
    fileHostPath:ref=>path.join(root,ref.id),
    saveImage:async({data,name})=>{if(previewError)throw Error('image message dimensions too large');return {id:digest(data),name,width:1,height:1}},
  },
}
context.get=name=>context[name]
const args=(name='output.png')=>({provider:'chosen',model:'gpt-image-2.5-sunburst',prompt:'a calibrated reference',output_policy:'explicit',output:path.join('dsh-texture',name)})
let requests=[]
const success=async(url,options)=>{requests.push({url:String(url),options});assert.equal(options.headers.get('Authorization'),`Bearer ${secret}`);assert.equal(options.redirect,'error');return Response.json({data:[{b64_json:png.toString('base64')}],usage:{output_tokens:10}},{headers:{'x-request-id':'image-1'}})}
assert.deepEqual((await imageModels(context)).routes[0].models.map(m=>m.id),['gpt-image-2.5-sunburst'])
assert.equal(JSON.stringify(await imageModels(context)).includes(secret),false)
let result=await generateImage(context,exec,args(),success)
assert.equal(result.status,'saved');assert.equal(result.request_id,'image-1');assert.equal(result.sha256,digest(png))
assert.deepEqual(await fs.readFile(result.output),png)
assert.equal(JSON.parse(requests[0].options.body).model,'gpt-image-2.5-sunburst')
assert.equal(requests[0].url,'https://configured.example/v1/images/generations')
assert.equal(result.recovery_file.attachment.id,digest(png));assert(result.attachment)
await assert.rejects(()=>generateImage(context,exec,args(),success),/already exists/)
mode='read-only';await assert.rejects(()=>generateImage(context,exec,args('read-only.png'),success),/read-only/);mode='workspace-write'
await assert.rejects(()=>generateImage(context,exec,{...args(),output:path.join(root,'..','outside.png')},success),/outside/)
await assert.rejects(()=>generateImage(context,exec,{...args(),output:'$HIP/dsh-texture/no.png'},success),/actual HIP/)
await assert.rejects(()=>generateImage(context,exec,{...args(),output:'transparent.jpg',background:'transparent'},success),/Transparent/)
assert.equal(requests.length,1)

const input=path.join(root,'source.png');await fs.writeFile(input,png)
result=await generateImage(context,exec,{...args('edit.png'),references:[input],size:'1024x1024'},success)
const edit=requests.at(-1)
assert.equal(edit.url,'https://configured.example/v1/images/edits')
assert(edit.options.body instanceof FormData)
assert.equal(edit.options.headers.has('Content-Type'),false)
assert.equal(edit.options.body.get('model'),'gpt-image-2.5-sunburst')
assert.deepEqual(Buffer.from(await edit.options.body.getAll('image[]')[0].arrayBuffer()),png)
assert.equal(result.sources[0].sha256,digest(png));assert.equal(result.sources[0].bytes,png.length)
assert.deepEqual(result.actual_dimensions,{width:1,height:1});assert.equal(result.warnings.length,1)
assert.equal(result.requested.size,'1024x1024');assert.equal(result.provider_model,null)

previewError=true;result=await generateImage(context,exec,args('no-preview.png'),success)
assert(result.ok);assert(result.attachment_error);assert(!result.attachment);assert.deepEqual(await fs.readFile(result.output),png)
previewError=false;recoveryError=true;result=await generateImage(context,exec,args('no-recovery.png'),success)
assert(result.ok);assert(result.recovery_error);assert(!result.recovery_file);assert.deepEqual(await fs.readFile(result.output),png);recoveryError=false

const originalOpen=fs.open
try {
  fs.open=async(...params)=>{const file=await originalOpen(...params);return {close:()=>file.close(),stat:()=>file.stat(),writeFile:async()=>{throw Error('destination disk full')}}}
  result=await generateImage(context,exec,args('disk-full.png'),success)
  assert.equal(result.status,'response_received');assert.equal(result.ok,false)
  assert.deepEqual(await fs.readFile(result.recovery_file.path),png)
  assert.equal(await fs.stat(result.output).catch(()=>null),null)
} finally {fs.open=originalOpen}

profile.headers={'X-Api-Secret':'separate-private-header'}
result=await generateImage(context,exec,args('rejected.png'),async()=>Response.json({error:{message:`refused ${secret} separate-private-header`}},{status:400}))
assert.equal(result.status,'provider_rejected');assert.equal(JSON.stringify(result).includes(secret),false)
assert.equal(JSON.stringify(result).includes('separate-private-header'),false);delete profile.headers
let attempts=0
result=await generateImage(context,exec,args('uncertain.png'),async()=>{attempts++;throw Error('connection lost')})
assert.equal(attempts,1);assert.equal(result.status,'outcome_unknown');assert.match(result.retry,/No automatic retry/)
assert.equal(await fs.stat(result.output).catch(()=>null),null)
result=await generateImage(context,exec,args('wrong-format.png'),async()=>Response.json({data:[{b64_json:Buffer.from('not an image').toString('base64')}]}))
assert.equal(result.ok,false);assert(result.recovery_file);assert(!result.attachment)
assert.equal(await fs.stat(result.output).catch(()=>null),null)
const cancelled=new AbortController();cancelled.abort()
result=await generateImage(context,{...exec,signal:cancelled.signal},args('cancelled.png'),success)
assert.equal(result.status,'not_sent')
// A remote response can arrive after someone replaces the reserved destination.
// Preserve their replacement and the billed original recovery attachment.
const replacement=path.join(root,'dsh-texture','replacement.png')
result=await generateImage(context,exec,args('replacement.png'),async(...request)=>{
  await fs.unlink(replacement);await fs.writeFile(replacement,'user replacement')
  return success(...request)
})
assert.equal(result.ok,false);assert.equal(result.status,'response_received')
assert.match(result.error,/reserved file changed/)
assert.equal(await fs.readFile(replacement,'utf8'),'user replacement')
assert.deepEqual(await fs.readFile(result.recovery_file.path),png)
delete profile.apiKeyEnv
await assert.rejects(()=>generateImage(context,exec,args('missing-key.png'),success),/explicit apiKeyEnv/)
assert.equal(recordReads,0);profile.apiKeyEnv='IMAGE_TEST_KEY'

// The exact field identity must change if a directory resolves elsewhere.
const realResolve=filesystem.resolve;let outputResolves=0
filesystem.resolve=async(...params)=>{const target=await realResolve(...params);if(String(params[0]).endsWith('moved.png')&&++outputResolves>1)target.targetKey+='-different';return target}
await assert.rejects(()=>generateImage(context,exec,args('moved.png'),success),/location changed/)
filesystem.resolve=realResolve

// A project's actual HIP and the DSH workspace may differ. The current
// observation, never the workspace or an old scene message, owns managed paths.
const project=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-image-project-'))
const secondProject=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-image-save-as-'))
const layout=JSON.parse(await fs.readFile(new URL('../../houdini/project-layout.json',import.meta.url),'utf8'))
let hip=path.join(project,'模型.hip'),newScene=false,observations=0,routes=0,failBridge=false,layoutMismatch=false
const connection={resolve:async actualExec=>{
  routes++;assert.equal(actualExec.agent.id,exec.agent.id)
  if(failBridge)throw Error('selected Houdini executor unavailable')
  return {targetExecutorId:undefined,sceneContext:async()=>{
    observations++;const directory=path.dirname(hip)
    return {ok:true,result:{hip_path:hip,hip_is_new:newScene,hip_dir:newScene?null:directory,
      runtime_id:'fixture-runtime',observed_at:1234,project_layout:{schema_version:1,available:!newScene,
        hip_path:hip,project_root:directory,directories:newScene?{}:Object.fromEntries(Object.entries(layout.directories)
          .map(([role,entry])=>[role,path.join(directory,entry.path)+(layoutMismatch?'wrong':'')]))}}}
  }}
}}
const managed=(overrides={})=>({provider:'chosen',model:'gpt-image-2.5-sunburst',prompt:'a calibrated reference',...overrides})
const beforeManaged=requests.length
await assert.rejects(()=>generateImage(context,exec,managed(),success,connection),/outside.*writable workspace/)
assert.equal(requests.length,beforeManaged,'workspace/HIP conflict must be rejected before billing')
assert.equal(await fs.stat(path.join(project,'dsh-reference')).catch(()=>null),null)
mode='danger-full-access'
result=await generateImage(context,exec,managed(),success,connection)
assert.equal(result.ok,true);assert.equal(result.artifact.role,'reference_generated')
assert.equal(result.artifact.lifecycle,layout.directories.reference_generated.lifecycle)
assert.equal(path.dirname(result.output),path.join(project,layout.directories.reference_generated.path))
assert.equal(result.artifact.hip_path,hip.replace(/\\/g,'/'))
assert.equal(result.artifact.hip_relative_path,path.relative(project,result.output).replace(/\\/g,'/'))
assert.deepEqual(result.artifact.observed_identity,{executor_id:null,runtime_id:'fixture-runtime',observed_at:1234})
assert.equal(await fs.stat(path.join(root,'dsh-reference')).catch(()=>null),null)
assert.equal(await fs.stat(path.join(project,'dsh-render')).catch(()=>null),null,'unused directories are not created')
const referenceOutput=result.output
const oneObservation=observations
result=await generateImage(context,exec,managed({purpose:'texture',output:'透明 标志.png'}),async(...request)=>{
  hip=path.join(secondProject,'later.hip')
  return success(...request)
},connection)
assert.equal(result.ok,true);assert.equal(result.artifact.role,'texture')
assert.equal(result.artifact.lifecycle,layout.directories.texture.lifecycle)
assert.equal(path.dirname(result.output),path.join(project,layout.directories.texture.path))
assert.match(path.basename(result.output),/^透明 标志_[0-9a-f]{16}\.png$/)
assert.equal(result.artifact.hip_path,path.join(project,'模型.hip').replace(/\\/g,'/'))
assert.equal(observations,oneObservation+1,'Save As during a paid request must not retarget its output')
assert.equal(await fs.stat(path.join(secondProject,layout.directories.texture.path)).catch(()=>null),null)
hip=path.join(project,'模型.hip')
const repeatedA=await generateImage(context,exec,managed({output:'same.png'}),success,connection)
const repeatedB=await generateImage(context,exec,managed({output:'same.png'}),success,connection)
assert.notEqual(repeatedA.output,repeatedB.output)
assert.deepEqual(await fs.readFile(referenceOutput),png)
const beforeInvalid=requests.length
for(const output of ['../escape.png','sub/picture.png','C:\\escape.png','CON.png','x`expr`.png','folder\\x.png'])
  await assert.rejects(()=>generateImage(context,exec,managed({output}),success,connection),/safe basename/)
newScene=true
await assert.rejects(()=>generateImage(context,exec,managed(),success,connection),/named Houdini project/)
newScene=false;layoutMismatch=true
await assert.rejects(()=>generateImage(context,exec,managed(),success,connection),/disagrees/)
layoutMismatch=false
const savedHip=hip;hip=path.join(fileURLToPath(new URL('../../',import.meta.url)),'forbidden.hip')
await assert.rejects(()=>generateImage(context,exec,managed(),success,connection),/plugin repository/)
hip=savedHip
failBridge=true
await assert.rejects(()=>generateImage(context,exec,managed(),success,connection),/selected Houdini executor unavailable/)
assert.equal(requests.length,beforeInvalid,'invalid project/path must not send paid requests')
const beforeOffline=routes
result=await generateImage(context,exec,args('offline.png'),success,connection)
assert.equal(result.ok,true);assert.equal(routes,beforeOffline,'explicit offline generation must not access Houdini')
assert.equal(path.dirname(result.output),path.join(root,'dsh-texture'))
assert.equal(result.artifact.output_policy,'explicit');assert.equal(result.artifact.hip_path,null)
failBridge=false

// Managed image paths follow the same durable task target as scene tools.
// In single-instance mode the ambient bridge must not replace an old binding.
const firstExecutor='a'.repeat(32),otherExecutor='b'.repeat(32)
const bindingSession=Session.create('image-bound',[],{version:4,id:'image-bound',createdAt:1,isSeeded:false,agentPreset:'houdini',cwd:root})
await new ExecutorBinding().ensure(bindingSession,firstExecutor)
const boundEvents=structuredClone(bindingSession.snapshotEvents())
const bindingExec={...exec,agent:{id:bindingSession.id,session:bindingSession}}
let bindingReads=0
const boundBridge={targetExecutorId:otherExecutor,sceneContext:async()=>{
  bindingReads++;return {ok:true,result:{hip_path:savedHip,hip_is_new:false}}
}}
const beforeBinding=requests.length
await assert.rejects(()=>generateImage(context,bindingExec,managed(),success,boundBridge),/recorded executor differs/)
assert.equal(bindingReads,0);assert.equal(requests.length,beforeBinding)
assert.deepEqual(bindingSession.snapshotEvents(),boundEvents)
boundBridge.targetExecutorId=firstExecutor
result=await generateImage(context,bindingExec,managed(),success,boundBridge)
assert.equal(result.ok,true);assert.equal(bindingReads,1)
assert.equal(result.artifact.observed_identity.executor_id,firstExecutor)
assert.deepEqual(bindingSession.snapshotEvents(),boundEvents,'path resolution never appends another binding')
const unbound=Session.create('image-unbound',[],{version:4,id:'image-unbound',createdAt:1,isSeeded:false,agentPreset:'houdini',cwd:root})
const unboundEvents=structuredClone(unbound.snapshotEvents())
await assert.rejects(()=>generateImage(context,{...exec,agent:{id:unbound.id,session:unbound}},managed(),success,boundBridge),/selected before model tool/)
assert.deepEqual(unbound.snapshotEvents(),unboundEvents,'normal pre-step owns initial binding, not an image tool')
assert.equal(bindingReads,1)

// A managed folder must remain in the visible HIP tree, including an alias
// redirected inside that tree; following a symlink is not a managed allocation.
const redirectedProject=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-image-redirect-'))
const redirectTarget=path.join(redirectedProject,'elsewhere');await fs.mkdir(redirectTarget)
await fs.symlink(redirectTarget,path.join(redirectedProject,'dsh-reference'),process.platform==='win32'?'junction':'dir')
hip=path.join(redirectedProject,'redirect.hip')
const beforeRedirect=requests.length
await assert.rejects(()=>generateImage(context,exec,managed(),success,connection),/redirected/)
assert.equal(requests.length,beforeRedirect)
assert.deepEqual(await fs.readdir(redirectTarget),[])
await fs.unlink(path.join(redirectedProject,'dsh-reference'))
hip=savedHip;mode='workspace-write'

const registered=[];registerImageTools({...context,tools:{register:t=>registered.push(t)}})
assert.deepEqual(registered.map(t=>t.name),['image_models','image_generate'])
const tool=registered.find(t=>t.name==='image_generate')
const content=tool.output.render({}, {ok:false,recovery_file:{attachment:{id:'original'}},attachment:{id:'preview'}})
assert.deepEqual(content.map(b=>b.type),['text','file','image'])
assert(resolveCount>0)
console.log('Image generation: exact routes, pixels, HIP directory roles, explicit offline paths, policy, recovery and no-retry checks passed')
