import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {videoModels,transcribeVideo,registerVideoTools,runVideoProcess,tutorialRuntime} from '../../lib/video-transcription.js'
import {configureVideo,customVideoCredential,VIDEO_DEFAULTS} from '../../lib/video-configuration.js'
const root=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'dsh-video-host-')))
const work=path.join(root,'教程 audio');await fs.mkdir(work)
const secret='asr-test-private-value',vault=new Map([['ASR_TEST',secret]])
const profile={api:'openai-completions',baseURL:'https://speech.example/v1',apiKeyEnv:'ASR_TEST'}
let selected={provider:'speech',model:'exact-asr-model',python:process.execPath,protocol:'openai-transcriptions',endpoint:'',authentication:'bearer',credentialRef:''}
let mode='workspace-write',revision=0,resolves=0,calls=0,chatProfiles=true,lastRequest
const fields={videoProvider:'provider',videoModel:'model',videoPython:'python',videoProtocol:'protocol',videoEndpoint:'endpoint',videoAuthentication:'authentication',videoCredentialRef:'credentialRef',videoConcurrency:'concurrency',videoRequestsPerSecond:'requestsPerSecond'}
const context={houdiniFrontend:{videoSelection:()=>selected},settings:{writable:true,
 describe:()=>[{ns:'llm-test',value:{providers:chatProfiles?{speech:profile}:{}}},{ns:'houdini-frontend',value:{},revision}],
 update:async(ns,patch,expected)=>{assert.equal(ns,'houdini-frontend');assert.equal(expected,revision);for(const[name,value]of Object.entries(patch)){assert(fields[name],name);selected[fields[name]]=value}revision++}},
 llm:{listProviders:()=>chatProfiles?[{id:'speech',name:'Speech API'}]:[],listConfigurableProviders:()=>chatProfiles?[{provider:'speech',displayName:'Speech API',settingsNs:'llm-test',settingsPath:['providers','speech']}]:[],listModels:async()=>{throw Error('ASR must not use the chat model catalog')}},
 credentials:{describe:async ref=>({configured:vault.has(ref),source:vault.has(ref)?'test':undefined,writable:true}),resolve:async ref=>{resolves++;return vault.has(ref)?{value:vault.get(ref)}:undefined}},
 fs:{resolve:async(filename,opts={})=>({targetKey:await fs.realpath(path.resolve(opts.cwd??root,filename))}),processPath:target=>target.targetKey,processPathFromHostPath:local=>local,contains:(parent,target)=>{const relative=path.relative(parent.targetKey,target.targetKey);return !relative.startsWith('..')&&!path.isAbsolute(relative)}},sandboxPolicy:{resolve:()=>({mode,workspaceRoot:root})}}
context.get=name=>context[name]
const exec={agent:{id:'video-session',session:{header:{cwd:root}}},signal:new AbortController().signal}
const runner=async request=>{calls++;lastRequest=request;return{code:0,stdout:'{"chunk":"00000","status":"saved","characters":10}\n{"submitted":1,"remaining":2,"deferred":[]}\n',stderr:'',cancelled:false}}
const args={work,allow_upload:true}
const policy=JSON.parse(await fs.readFile(new URL('../../skills/houdini-video-tutorial/scripts/transcription-policy.json',import.meta.url),'utf8'))
assert.deepEqual(VIDEO_DEFAULTS,{concurrency:policy.concurrency,requestsPerSecond:policy.requestsPerSecond})
let result=await videoModels(context)
assert.equal(result.service.endpoint,'https://speech.example/v1/audio/transcriptions');assert.equal(result.service.protocol,'openai-transcriptions');assert.equal(result.service.credential.configured,true);assert.equal(result.service.support,'unverified');assert.equal(resolves,0);assert(!JSON.stringify(result).includes(secret))
selected.model='qwen3-asr-flash-filetrans'
result=await transcribeVideo(context,exec,args,runner)
assert.equal(result.protocol,'openai-transcriptions','model names do not infer protocols');assert.equal(result.endpoint,'https://speech.example/v1/audio/transcriptions')
assert.equal(lastRequest.args[lastRequest.args.indexOf('--concurrency')+1],'2');assert.equal(lastRequest.args[lastRequest.args.indexOf('--requests-per-second')+1],'1')
selected.protocol='openai-realtime';await assert.rejects(()=>transcribeVideo(context,exec,args,runner),/实时|WebSocket|适配器/);assert.equal((await videoModels(context)).service,null)
selected.protocol='qwen-chat-asr';selected.model='relay-specific-asr-id';result=await transcribeVideo(context,exec,args,runner);assert.equal(result.endpoint,'https://speech.example/v1/chat/completions')
selected.protocol='dashscope-asr';profile.baseURL='https://speech.example/compatible-mode/v1';selected.model='qwen-audio-3.0-asr-flash'
result=await transcribeVideo(context,exec,args,runner);assert.equal(result.endpoint,'https://speech.example/api/v1/services/aigc/multimodal-generation/generation')
profile.baseURL='https://speech.example/unrelated-gateway';await assert.rejects(()=>transcribeVideo(context,exec,args,runner),/不能.*推断|明确/)
profile.baseURL='https://speech.example/v1';selected.protocol='openai-transcriptions'
// Purpose-specific endpoints do not need a fake chat provider/catalog.
chatProfiles=false
result=await configureVideo(context,{endpoint:'https://asr-only.example/custom-asr',protocol:'openai-transcriptions',model:'ASR-not-a-chat-model',authentication:'bearer'})
assert.equal(selected.provider,'');assert.equal(result.service.provider,null);assert.deepEqual(result.routes,[]);assert.equal(result.service.credential.configured,false)
const firstRef=result.service.credentialRef;assert.equal(firstRef,customVideoCredential(result.service.endpoint,result.service.protocol))
await assert.rejects(()=>transcribeVideo(context,exec,args,runner),/API key|密钥/);vault.set(firstRef,secret)
const ambientNames=['OPENAI_API_KEY','DEEPSEEK_API_KEY','DSH_API_TOKEN','dsh_test_identity','DSH_VIDEO_TRANSCRIPTION_KEY']
const beforeEnv=Object.fromEntries(ambientNames.map(name=>[name,process.env[name]]))
try{
 for(const name of ambientNames)process.env[name]='unrelated-parent-secret'
 result=await transcribeVideo(context,exec,{...args,max_chunks:1},runner)
 assert(result.ok);assert.equal(result.provider,null);assert.equal(lastRequest.env.DSH_VIDEO_TRANSCRIPTION_KEY,secret)
 for(const name of ambientNames.filter(name=>name!=='DSH_VIDEO_TRANSCRIPTION_KEY'))assert.equal(lastRequest.env[name],undefined)
 assert(!lastRequest.args.includes(secret));assert(!JSON.stringify(result).includes(secret));assert.equal(lastRequest.args[lastRequest.args.indexOf('--max-chunks')+1],'1')
 const beforeChange=calls
 result=await configureVideo(context,{endpoint:'https://another-origin.example/custom-asr',model:'ASR-not-a-chat-model',protocol:'openai-transcriptions',authentication:'bearer'})
 assert.notEqual(result.service.credentialRef,firstRef);assert.equal(result.service.credential.configured,false)
 await assert.rejects(()=>transcribeVideo(context,exec,args,runner),/API key|密钥/);assert.equal(calls,beforeChange)
 result=await configureVideo(context,{endpoint:'http://127.0.0.1:31337/custom-asr',model:'local-asr-id',protocol:'openai-transcriptions',authentication:'none'})
 assert.equal(result.service.credentialRef,'');assert.equal(result.service.credential.required,false)
 const beforeNone=resolves;result=await transcribeVideo(context,exec,{work,allow_upload:false},runner)
 assert.equal(result.authentication,'none');assert.equal(result.data_location,'loopback');assert.equal(resolves,beforeNone)
 for(const name of ambientNames)assert.equal(lastRequest.env[name],undefined)
 assert.equal(lastRequest.args[lastRequest.args.indexOf('--authentication')+1],'none')
}finally{for(const name of ambientNames)if(beforeEnv[name]===undefined)delete process.env[name];else process.env[name]=beforeEnv[name]}
selected.endpoint='https://fixture-user:fixture-url-secret@asr.example/custom-asr?key=fixture-query-secret';result=await videoModels(context)
assert.equal(result.service,null);assert(!JSON.stringify(result).includes('fixture-url-secret'));assert(!JSON.stringify(result).includes('fixture-query-secret'))
await assert.rejects(()=>configureVideo(context,{api_key:'not-a-tool-argument'}),/密钥|秘密/)
await assert.rejects(()=>configureVideo(context,{endpoint:'http://remote.example/custom-asr'}),/HTTPS/)
// Native provider credential reuse, request guards and redaction remain intact.
chatProfiles=true;selected={provider:'speech',model:'exact-asr-model',python:process.execPath,protocol:'openai-transcriptions',endpoint:'',authentication:'bearer'}
const savedProfile=structuredClone(profile)
await assert.rejects(()=>transcribeVideo(context,exec,{...args,allow_upload:false},runner),/authorization/)
await assert.rejects(()=>transcribeVideo(context,exec,{...args,max_retries:1},runner),/Retries/)
await assert.rejects(()=>transcribeVideo(context,exec,{...args,chunks:['00000','00000']},runner),/unique/)
await assert.rejects(()=>transcribeVideo(context,exec,{...args,provider:'missing'},runner),/不存在|不明确/)
mode='read-only';await assert.rejects(()=>transcribeVideo(context,exec,args,runner),/read-only/);mode='workspace-write';await assert.rejects(()=>transcribeVideo(context,exec,{...args,work:os.tmpdir()},runner),/outside/)
profile.headers={'X-Extra':'private'};await assert.rejects(()=>transcribeVideo(context,exec,args,runner),/请求头/);delete profile.headers
vault.delete('ASR_TEST');assert.equal((await videoModels(context)).service.credential.configured,false);await assert.rejects(()=>transcribeVideo(context,exec,args,runner),/API key|密钥/);vault.set('ASR_TEST',secret)
result=await transcribeVideo(context,exec,{...args,retry_failed:true,max_retries:2,chunks:['00002']},async request=>{assert(request.args.includes('--retry-failed'));assert.equal(request.args.at(-1),'00002');return{code:1,stdout:'{"chunk":"00001","status":"saved","characters":12}\n',stderr:`Failed ${secret}`,cancelled:false}})
assert(!result.ok);assert.equal(result.progress.length,1);assert(!JSON.stringify(result).includes(secret))
result=await transcribeVideo(context,exec,args,async()=>{throw Error(`spawn error ${secret}`)});assert.equal(result.status,'worker_not_started');assert(!JSON.stringify(result).includes(secret));assert.deepEqual(profile,savedProfile)
profile.baseURL='https://speech.example/compatible-mode/v1';selected.protocol='dashscope-asr';selected.model='qwen-audio-3.1-asr-flash'
let optionFile
result=await transcribeVideo(context,exec,{...args,concurrency:16,requests_per_second:8,speaker_diarization:true,vocabulary:[{word:'Houdini',weight:3},{word:'VEX',weight:2}]},async request=>{assert.equal(request.args[request.args.indexOf('--concurrency')+1],'16');optionFile=request.args[request.args.indexOf('--asr-options-file')+1];assert.deepEqual(JSON.parse(await fs.readFile(optionFile,'utf8')),{vocabulary:{Houdini:3,VEX:2},speaker_diarization_enabled:true});return{code:1,stdout:'{"submitted":4,"completed":4,"succeeded":3,"failed":1,"peak_inflight":4,"remaining":2}\n',stderr:'HTTP 429; retained',cancelled:false}})
assert.equal(result.summary.succeeded,3);assert.equal(await fs.stat(optionFile).catch(()=>null),null)
await assert.rejects(()=>transcribeVideo(context,exec,{...args,concurrency:65},runner),/concurrency/);await assert.rejects(()=>transcribeVideo(context,exec,{...args,requests_per_second:0},runner),/requests_per_second/)
await assert.rejects(()=>transcribeVideo(context,exec,{...args,vocabulary:[{word:'Houdini',weight:3},{word:'Houdini',weight:2}]},runner),/unique/)
selected.model='qwen-audio-3.0-asr-flash';await assert.rejects(()=>transcribeVideo(context,exec,{...args,speaker_diarization:true},runner),/3.1/)
const fakeHfs=path.join(root,'static-hfs'),fakePython=path.join(fakeHfs,'python313','python.exe');await fs.mkdir(path.dirname(fakePython),{recursive:true});await fs.writeFile(fakePython,'static runtime path fixture')
selected.python='';context.houdiniDesktop={listInstallations:async()=>[{hfs:fakeHfs}]};assert.equal((await tutorialRuntime(context,'')).python,fakePython)
context.sessionProjections={stateOf:()=>({selectedTarget:{executor_id:'a'.repeat(32)}})};let staticRuntimeCalls=0
const connection={resolveRuntime:async()=>{staticRuntimeCalls++;return{runtime:{python:fakePython,hfs:fakeHfs}}}}
assert.equal((await tutorialRuntime(context,'',exec,connection)).python,fakePython);assert.equal(staticRuntimeCalls,1)

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
assert.deepEqual(registered.map(tool=>tool.name),['video_process','video_models','video_configure','video_transcribe'])
console.log('video transcription Host routing, credential isolation, validation and child cancellation passed')
await fs.rm(root,{recursive:true,force:true})
