import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {videoModels,transcribeVideo,registerVideoTools,runVideoProcess} from '../../lib/video-transcription.js'

const root=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'dsh-video-host-')))
const work=path.join(root,'教程 audio');await fs.mkdir(work)
const secret='asr-test-private-value'
const profile={api:'openai-completions',baseURL:'https://speech.example/v1',apiKeyEnv:'ASR_TEST'}
let selected={provider:'speech',model:'exact-asr-model',python:process.execPath},mode='workspace-write',configured=true,resolves=0,calls=0
const context={
  houdiniFrontend:{videoSelection:()=>selected},
  settings:{describe:()=>[{ns:'llm-test',value:{providers:{speech:profile}}}]},
  llm:{listProviders:()=>[{id:'speech',name:'Speech API'}],
    listConfigurableProviders:()=>[{provider:'speech',displayName:'Speech API',settingsNs:'llm-test',settingsPath:['providers','speech']}],
    listModels:async()=>[{id:'a-chat-model',name:'Chat catalog entry'}]},
  credentials:{describe:async ref=>{assert.equal(ref,'ASR_TEST');return {configured,source:'test'}},
    resolve:async ref=>{assert.equal(ref,'ASR_TEST');resolves++;return configured?{value:secret}:undefined}},
  fs:{resolve:async(filename,opts={})=>{const target=await fs.realpath(path.resolve(opts.cwd??root,filename));return {targetKey:target}},
    processPath:target=>target.targetKey,processPathFromHostPath:local=>local,
    contains:(parent,target)=>{const relative=path.relative(parent.targetKey,target.targetKey);return !relative.startsWith('..')&&!path.isAbsolute(relative)}},
  sandboxPolicy:{resolve:()=>({mode,workspaceRoot:root})},
}
context.get=name=>context[name]
const exec={agent:{id:'video-session',session:{header:{cwd:root}}},signal:new AbortController().signal}
let lastRequest
const runner=async request=>{calls++;lastRequest=request;return {code:0,stdout:'{"chunk":"00000","status":"saved","characters":10}\n{"submitted":1,"remaining":2,"deferred":[]}\n',stderr:'',cancelled:false}}
const args={work,allow_upload:true}
let result=await videoModels(context)
assert.equal(result.selected.model,'exact-asr-model')
assert.equal(result.routes[0].endpoint,'https://speech.example/v1/audio/transcriptions')
assert.equal(result.routes[0].protocol,'openai-transcriptions')
assert.equal(result.routes[0].credential.configured,true)
assert.equal(resolves,0,'configuration inspection must never resolve the secret')
assert.equal(JSON.stringify(result).includes(secret),false)

selected.model='qwen3-asr-flash-2026-02-10'
result=await transcribeVideo(context,exec,args,runner)
assert.equal(result.protocol,'qwen-chat-asr')
assert.equal(result.endpoint,'https://speech.example/v1/chat/completions')
assert.equal(lastRequest.args[lastRequest.args.indexOf('--protocol')+1],'qwen-chat-asr')
assert.equal((await videoModels(context)).routes[0].protocol,'qwen-chat-asr')
const beforeUnsupported=calls
selected.model='qwen3-asr-flash-filetrans'
assert.equal((await videoModels(context)).routes[0].support,'unsupported')
await assert.rejects(()=>transcribeVideo(context,exec,args,runner),/DashScope/)
assert.equal(calls,beforeUnsupported,'unsupported file transcription must not dispatch an audio upload')
selected.model='exact-asr-model'

profile.baseURL='https://speech.example/compatible-mode/v1'
selected.model='qwen-audio-3.0-asr-flash'
result=await transcribeVideo(context,exec,args,runner)
assert.equal(result.protocol,'dashscope-asr')
assert.equal(result.endpoint,'https://speech.example/api/v1/services/aigc/multimodal-generation/generation')
assert.equal(lastRequest.args[lastRequest.args.indexOf('--protocol')+1],'dashscope-asr')
assert.equal((await videoModels(context)).routes[0].support,'unverified')
profile.baseURL='https://speech.example/v1'
await assert.rejects(()=>transcribeVideo(context,exec,args,runner),/基址/,'do not infer native paths from an unrelated gateway base')
profile.baseURL='https://speech.example/api/v1'
assert.equal((await videoModels(context)).routes[0].endpoint,result.endpoint)
profile.baseURL='https://speech.example/v1';selected.model='exact-asr-model'

result=await transcribeVideo(context,exec,args,runner)
assert.equal(result.status,'processed');assert.equal(result.summary.remaining,2)
assert.equal(result.model,'exact-asr-model','ASR model may be absent from the chat catalog')
assert.equal(lastRequest.executable,process.execPath)
assert.equal(lastRequest.env.DSH_VIDEO_TRANSCRIPTION_KEY,secret)
assert.equal(lastRequest.env.PYTHONUTF8,'1')
assert(!lastRequest.args.join(' ').includes(secret))
assert.equal(lastRequest.args[lastRequest.args.indexOf('--key-env')+1],'DSH_VIDEO_TRANSCRIPTION_KEY')
assert.equal(lastRequest.args[lastRequest.args.indexOf('--work')+1],work)
assert.equal(lastRequest.args[lastRequest.args.indexOf('--max-chunks')+1],'100')
assert.equal(lastRequest.args[lastRequest.args.indexOf('--concurrency')+1],'64')
assert.equal(lastRequest.args[lastRequest.args.indexOf('--requests-per-second')+1],'8')
assert.equal(JSON.stringify(result).includes(secret),false)
await assert.rejects(()=>transcribeVideo(context,exec,{...args,allow_upload:false},runner),/authorization/)
await assert.rejects(()=>transcribeVideo(context,exec,{...args,max_retries:1},runner),/Retries/)
await assert.rejects(()=>transcribeVideo(context,exec,{...args,chunks:['00000','00000']},runner),/unique/)
await assert.rejects(()=>transcribeVideo(context,exec,{...args,chunks:['--help']},runner),/unique/)
await assert.rejects(()=>transcribeVideo(context,exec,{...args,provider:'missing'},runner),/unambiguous/)
mode='read-only';await assert.rejects(()=>transcribeVideo(context,exec,args,runner),/read-only/);mode='workspace-write'
await assert.rejects(()=>transcribeVideo(context,exec,{...args,work:os.tmpdir()},runner),/outside/)
assert.equal(calls,3,'local validation rejects before dispatch')
configured=false
assert.equal((await videoModels(context)).routes[0].credential.configured,false)
await assert.rejects(()=>transcribeVideo(context,exec,args,runner),/No API key/)
configured=true
profile.headers={'X-Extra':'private'}
assert.match((await videoModels(context)).routes[0].diagnostics[0],/custom headers/)
await assert.rejects(()=>transcribeVideo(context,exec,args,runner),/custom headers/)
delete profile.headers
profile.baseURL='http://speech.example/v1'
await assert.rejects(()=>transcribeVideo(context,exec,args,runner),/HTTPS/)
profile.baseURL='https://speech.example/v1'
result=await transcribeVideo(context,exec,{...args,retry_failed:true,max_retries:2,chunks:['00002']},async request=>{
  assert(request.args.includes('--retry-failed'));assert.equal(request.args.at(-1),'00002')
  return {code:1,stdout:'{"chunk":"00001","status":"saved","characters":12}\n',stderr:`Failed on 00002 ${secret}`,cancelled:false}
})
assert.equal(result.ok,false);assert.equal(result.status,'worker_failed');assert.equal(result.progress.length,1)
assert.equal(JSON.stringify(result).includes(secret),false)
result=await transcribeVideo(context,exec,args,async()=>{throw Error(`spawn error ${secret}`)})
assert.equal(result.status,'worker_not_started');assert.equal(JSON.stringify(result).includes(secret),false)

profile.baseURL='https://speech.example/compatible-mode/v1';selected.model='qwen-audio-3.1-asr-flash'
let optionFile
result=await transcribeVideo(context,exec,{...args,concurrency:16,requests_per_second:8,
  speaker_diarization:true,vocabulary:[{word:'Houdini',weight:3},{word:'VEX',weight:2}]},async request=>{
  assert.equal(request.args[request.args.indexOf('--concurrency')+1],'16')
  assert.equal(request.args[request.args.indexOf('--requests-per-second')+1],'8')
  optionFile=request.args[request.args.indexOf('--asr-options-file')+1]
  const options=JSON.parse(await fs.readFile(optionFile,'utf8'))
  assert.deepEqual(options,{vocabulary:{Houdini:3,VEX:2},speaker_diarization_enabled:true})
  assert(!JSON.stringify(options).includes(secret))
  return {code:1,stdout:'{"submitted":4,"completed":4,"succeeded":3,"failed":1,"peak_inflight":4,"remaining":2}\n',stderr:'HTTP 429; in-flight results retained',cancelled:false}
})
assert.equal(result.ok,false);assert.equal(result.summary.succeeded,3);assert.equal(result.summary.peak_inflight,4)
assert.equal(await fs.stat(optionFile).catch(()=>null),null,'per-call options transport is removed; task config owns options identity')
await assert.rejects(()=>transcribeVideo(context,exec,{...args,concurrency:65},runner),/concurrency/)
await assert.rejects(()=>transcribeVideo(context,exec,{...args,requests_per_second:0},runner),/requests_per_second/)
await assert.rejects(()=>transcribeVideo(context,exec,{...args,vocabulary:[{word:'Houdini',weight:3},{word:'Houdini',weight:2}]},runner),/unique/)
selected.model='qwen-audio-3.0-asr-flash'
await assert.rejects(()=>transcribeVideo(context,exec,{...args,speaker_diarization:true},runner),/3.1/)

// Exercise the actual process transport, including cancellation and exact-child lock cleanup.
const childScript=path.join(root,'worker.mjs')
await fs.writeFile(childScript,`import fs from 'node:fs';fs.writeFileSync(process.argv[2]+'/.lock',String(process.pid));console.log('ready');setInterval(()=>{},1000);`)
const controller=new AbortController()
const pending=runVideoProcess({executable:process.execPath,args:[childScript,work],env:process.env,cwd:root,work,signal:controller.signal})
for (let i=0;i<100;i++) {if(await fs.stat(path.join(work,'.lock')).catch(()=>null))break;await new Promise(resolve=>setTimeout(resolve,10))}
assert(await fs.stat(path.join(work,'.lock')))
controller.abort();result=await pending
assert.equal(result.cancelled,true)
assert.equal(await fs.stat(path.join(work,'.lock')).catch(()=>null),null)
await fs.writeFile(path.join(work,'.lock'),'other-worker')
result=await runVideoProcess({executable:process.execPath,args:['-e','process.stdout.write("ok")'],env:process.env,cwd:root,work})
assert.equal(result.code,0);assert.equal(result.stdout,'ok')
assert.equal(await fs.readFile(path.join(work,'.lock'),'utf8'),'other-worker')
await assert.rejects(()=>runVideoProcess({executable:path.join(root,'missing-python'),args:[],env:process.env,cwd:root,work}),/Cannot start/)
const registered=[];registerVideoTools({tools:{register:tool=>registered.push(tool)}})
assert.deepEqual(registered.map(tool=>tool.name),['video_process','video_models','video_transcribe'])
console.log('video transcription Host routing, credential isolation, validation and child cancellation passed')
await fs.rm(root,{recursive:true,force:true})
