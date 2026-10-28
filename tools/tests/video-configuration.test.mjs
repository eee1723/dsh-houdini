import assert from 'node:assert/strict'
import {videoConfiguration,configureVideo,resolveVideoRoute,customVideoCredential,VIDEO_DEFAULTS} from '../../lib/video-configuration.js'
const secret='never-expose-configuration-secret',writes=[]
let revision=1,mutable=true,selection={provider:'',model:'',python:'',protocol:'',endpoint:'',authentication:'bearer',credentialRef:'',...VIDEO_DEFAULTS}
const mapping={videoProvider:'provider',videoModel:'model',videoPython:'python',videoProtocol:'protocol',videoEndpoint:'endpoint',
 videoAuthentication:'authentication',videoCredentialRef:'credentialRef',videoConcurrency:'concurrency',videoRequestsPerSecond:'requestsPerSecond'}
let resolves=0,describes=0,catalogReads=0,providerRevision=4
const nativeProfile={api:'openai-responses',baseURL:'https://speech.example/v1',apiKeyEnv:'SPEECH_KEY'}
const ctx={houdiniFrontend:{videoSelection:()=>selection},credentials:{describe:async ref=>{describes++;return{configured:ref==='SPEECH_KEY',writable:true,source:'file'}},resolve(){resolves++;throw Error('status must not resolve secrets')}},
 llm:{listProviders:()=>[{id:'main-chat'}],listConfigurableProviders:()=>[{provider:'main-chat',displayName:'Main chat',settingsNs:'llm-native',settingsPath:['providers','main-chat']}],
 listModels(){catalogReads++;throw Error('ASR is not a chat catalog')}},
 settings:{get writable(){return mutable},describe:()=>[{ns:'houdini-frontend',revision,value:{}},{ns:'llm-native',revision:providerRevision,value:{providers:{'main-chat':nativeProfile}}}],
 async update(ns,patch,expected){assert.equal(ns,'houdini-frontend');assert.equal(expected,revision);writes.push(patch);for(const [key,value]of Object.entries(patch))selection[mapping[key]]=value;revision++}}}
ctx.get=name=>ctx[name]
let status=await videoConfiguration(ctx)
assert.equal(status.service,null);assert.equal(resolves,0);assert.equal(catalogReads,0)
assert.deepEqual(status.defaults,{concurrency:2,requestsPerSecond:1})
status=await configureVideo(ctx,{endpoint:'http://127.0.0.1:8000/custom-asr',model:'local-model',protocol:'openai-transcriptions',authentication:'none',concurrency:1})
assert.equal(status.service.endpoint,'http://127.0.0.1:8000/custom-asr');assert.equal(status.service.authentication,'none')
assert.equal(status.service.credential.required,false);assert.equal(status.service.dataLocation,'loopback')
assert.deepEqual(status,JSON.parse(JSON.stringify(status)),'native tools require lossless JSON, unlike RPC which silently drops undefined fields')
assert.equal(status.service.provider,null);assert.equal(catalogReads,0,'a speech-only service needs no chat model entry')
const before=writes.length
for(const input of [{apiKey:secret},{python:'C:/arbitrary.exe'},{protocol:'realtime'},{endpoint:'wss://audio.example/socket'},
 {provider:'main-chat',endpoint:'https://other.example/asr'},{endpoint:'https://user:'+secret+'@speech.example/asr'},
 {endpoint:'https://speech.example/asr?api_key='+secret},{concurrency:0},{requests_per_second:101}])await assert.rejects(configureVideo(ctx,input))
assert.equal(writes.length,before,'invalid/secret configuration is rejected before a native write')
status=await configureVideo(ctx,{endpoint:'https://speech.example/custom-asr',model:'exact-asr',protocol:'openai-transcriptions',authentication:'bearer'})
const firstRef=status.service.credentialRef
assert.match(firstRef,/^DSH_HOUDINI_ASR_[A-F0-9]{16}_API_KEY$/)
assert.equal(firstRef,customVideoCredential('https://speech.example/another-path','qwen-chat-asr'),'same origin can reuse its saved key across explicit models/protocols')
status=await configureVideo(ctx,{endpoint:'https://relay.example/custom-asr',model:'relay-asr',protocol:'openai-transcriptions'})
assert.notEqual(status.service.credentialRef,firstRef,'a new origin cannot inherit the previous saved credential')
assert.equal(status.service.credential.configured,false)
await configureVideo(ctx,{endpoint:'http://127.0.0.1:8000/custom-asr'})
status=await videoConfiguration(ctx);assert.equal(status.service,null,'changing service does not silently inherit the old wire/model/no-auth')
status=await configureVideo(ctx,{provider:'main-chat',model:'speech-only-id',protocol:'qwen-chat-asr'})
assert.equal(selection.endpoint,'');assert.equal(status.service.credentialRef,'SPEECH_KEY')
assert.equal(status.service.endpoint,'https://speech.example/v1/chat/completions')
assert.equal(status.service.credential.configured,true)
assert.deepEqual(status.service.settingsSource,{ns:'llm-native',revision:4})
assert.deepEqual(status.routes[0].settingsSource,{ns:'llm-native',revision:4})
assert.deepEqual(status,JSON.parse(JSON.stringify(status)),'provider-backed configuration must also be lossless JSON')
assert.equal(catalogReads,0);assert.equal(resolves,0);assert.ok(describes>0)
assert(!writes.some(patch=>Object.keys(patch).some(key=>/llm|chat|modelProvider/i.test(key))))
const providerGuardWrites=writes.length;providerRevision++
await assert.rejects(configureVideo(ctx,{model:'another-asr',expected_provider_revision:4}),/服务商设置已变化/)
assert.equal(writes.length,providerGuardWrites,'a stale provider revision cannot commit a new endpoint')
providerRevision--
selection={...selection,provider:'',endpoint:'https://user:'+secret+'@speech.example/asr?api_key='+secret,credentialRef:secret}
status=await videoConfiguration(ctx)
assert(!JSON.stringify(status).includes(secret),'invalid old/raw settings never echo URL credentials or a misfiled key reference')
assert.equal(status.service,null)
selection.endpoint='https://speech.example/custom-asr'
mutable=false;assert.equal((await videoConfiguration(ctx)).writable,false)
await assert.rejects(configureVideo(ctx,{model:'new-model'}),/不可写/)
mutable=true;await assert.rejects(configureVideo(ctx,{model:'new-model',expected_revision:revision-1}))
selection={...selection,provider:'',model:'speech-only-id',protocol:'openai-transcriptions',endpoint:'https://speech.example/custom-asr'}
const originalDescribe=ctx.credentials.describe,originalRevision=revision
let releasePresence
ctx.credentials.describe=()=>new Promise(resolve=>{releasePresence=()=>resolve({configured:false,writable:true})})
const pending=videoConfiguration(ctx)
assert.equal(typeof releasePresence,'function')
selection={...selection,endpoint:'https://new-service.example/asr'};revision++
releasePresence()
const captured=await pending
assert.equal(captured.service.endpoint,'https://speech.example/custom-asr')
assert.equal(captured.revision,originalRevision,'old route presence cannot be relabeled with a newer settings revision')
ctx.credentials.describe=originalDescribe
selection={...selection,provider:'main-chat',endpoint:'',protocol:'qwen-chat-asr'}
ctx.credentials.describe=()=>new Promise(resolve=>{releasePresence=()=>resolve({configured:true,writable:true})})
const pendingProvider=videoConfiguration(ctx)
nativeProfile.baseURL='https://provider-new.example/v1';providerRevision++
releasePresence()
const capturedProvider=await pendingProvider
assert.equal(capturedProvider.service.endpoint,'https://speech.example/v1/chat/completions')
assert.deepEqual(capturedProvider.service.settingsSource,{ns:'llm-native',revision:4},'reused provider endpoint and its native revision are captured together')
ctx.credentials.describe=originalDescribe
console.log('Tutorial configuration: ASR-only routes, explicit protocols, native settings/credentials, safe defaults, origin isolation, invalid legacy redaction and revision guards passed')
