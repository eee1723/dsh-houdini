import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {ChatGptAccountController,chatGptRouteConflicts} from '../../lib/chatgpt-account.js'

const key='llm-pi-ai/openai'
const tick=()=>new Promise(resolve=>setTimeout(resolve,0))
function fixture({profile,kind,configured=Boolean(kind),timeout=10000}={}){
  let stored=configured,recordKind=kind,registered=Boolean(profile),active=false,resolveLogin,request
  const writes=[],defaults=[],probes=[],preparations=[],disconnects=[]
  const descriptor={ns:'llm-pi-ai',revision:7,value:{providers:{...(profile?{openai:structuredClone(profile)}:{})}}}
  const ctx={
    credentials:{
      async describeRecord(actual){assert.equal(actual,key);return {configured:stored,kind:recordKind,writable:true}},
      readRecord(){throw Error('UI must never read a grant')},resolve(){throw Error('UI must never resolve a secret')},
      deleteRecord(){throw Error('UI must delegate logout to the native owner')},
    },
    authorization:{describe(actual){assert.equal(actual,key);return {methods:[{id:'oauth'}],inFlight:active}},
      begin(value){assert.equal(value.key,key);assert.equal(value.method,'oauth');assert.equal(active,false);active=true;request=value
        return new Promise(resolve=>{resolveLogin=outcome=>{active=false;if(outcome.status==='authorized'){stored=true;recordKind='grant'}resolve(outcome)}
          value.signal.addEventListener('abort',()=>resolveLogin({status:'cancelled'}),{once:true})})},
      cancel(actual){assert.equal(actual,key);resolveLogin?.({status:'cancelled'})},
    },
    settings:{writable:true,describe(options){assert.equal(options.redactSecrets,true);return [descriptor]},
      async mutate(ns,ops,revision){assert.equal(ns,descriptor.ns);assert.equal(revision,descriptor.revision);writes.push(structuredClone(ops));
        assert.deepEqual(ops[0].path,['providers','openai']);descriptor.value.providers.openai=structuredClone(ops[0].value);registered=true;descriptor.revision++}},
    llm:{listConfigurableProviders:()=>[{provider:'openai',settingsNs:descriptor.ns,settingsPath:['providers','openai'],nativeAuth:{oauth:true}}],
      listProviders:()=>registered?[{id:'openai'}]:[],
      listModels:async()=>[{id:'model-a',name:'Model A',inputModalities:['text','image']}],
      discoverModels:async(ns,input)=>{assert.equal(ns,descriptor.ns);assert.deepEqual(input,{provider:'openai'});return [{id:'model-a',name:'Model A'}]},
      resolveModelInfo:async()=>({id:'model-a',name:'Model A',inputModalities:['text','image'],context:{contextWindow:200000},reasoning:{efforts:[{id:'low',name:'Low'},{id:'high',name:'High'}],defaultEffort:'low'}}),
      resolveCallConfig:async value=>{if(value.reasoningEffort&&!['low','high'].includes(value.reasoningEffort))throw {code:'UNSUPPORTED_REASONING_EFFORT'};return {...value,reasoningEffort:value.reasoningEffort??'low'}},
      async *stream(value){probes.push(value);yield {type:'text-delta',text:'OK'};yield {type:'finish',reason:{kind:'stop'}}},
    },
    agentDefaultModel:{currentSelection:()=>defaults.at(-1)??{provider:'another',model:'unchanged'},saveSelection:async value=>defaults.push(value)},
  }
  ctx.get=name=>ctx[name]
  ctx.piAiAccounts={
    async ensureInstallationId(provider){assert.equal(provider,'openai');return '11111111-2222-3333-4444-555555555555'},
    async describe(provider){assert.equal(provider,'openai');return {...await ctx.credentials.describeRecord(key),registrationAvailable:true,disconnecting:false,
      ...(stored&&recordKind==='grant'?{account:{issuer:'https://auth.openai.com',subject:'verified-subject',email:'user@example.com',name:'User',token:'must-not-escape'}}:{})}},
    async disconnect(provider){assert.equal(provider,'openai');disconnects.push(true);stored=false;recordKind=undefined;return {revocation:'confirmed',localCleared:true}},
  }
  const controller=new ChatGptAccountController(ctx,{loginTimeoutMs:timeout,prepareLogin:async()=>{preparations.push(true)}})
  return {ctx,controller,descriptor,writes,defaults,probes,preparations,disconnects,request:()=>request,finish:()=>resolveLogin({status:'authorized'})}
}
async function rejectsCode(action,code){await assert.rejects(action,error=>error.code===code&&typeof error.message==='string')}

// Read-only status never begins OAuth, reads opaque grants, probes a model, or changes settings.
const first=fixture()
try{
  const state=await first.controller.status()
  assert.equal(state.nativeFlowAvailable,true);assert.equal(state.credential.stored,false)
  assert.equal(state.route.configured,false);assert.equal(state.models[0].id,'model-a')
  assert.equal(first.request(),undefined);assert.deepEqual(first.preparations,[]);assert.deepEqual(first.writes,[]);assert.deepEqual(first.probes,[])
  const login=await first.controller.start();await tick()
  assert.equal(login.login.status,'pending');assert.equal(first.preparations.length,1)
  await rejectsCode(()=>first.controller.start(),'BUSY')
  const active=first.request()
  active.interaction.notify({message:'Continue in browser',url:'https://auth.openai.com/authorize?state=test',code:'human-code'})
  const pending=active.interaction.prompt({kind:'secret',message:'Paste the return URL',placeholder:'Return URL'})
  const prompt=(await first.controller.status()).login.prompt
  assert.equal(prompt.kind,'secret')
  await rejectsCode(()=>first.controller.submitPrompt({attemptId:login.login.attemptId,promptId:'old',value:'secret-return'}),'STALE_PROMPT')
  await first.controller.submitPrompt({attemptId:login.login.attemptId,promptId:prompt.id,value:'secret-return'})
  assert.equal(await pending,'secret-return');assert(!JSON.stringify(await first.controller.status()).includes('secret-return'))
  first.finish();await tick()
  assert.equal((await first.controller.status()).credential.kind,'grant')
  assert.deepEqual((await first.controller.status()).account,{issuer:'https://auth.openai.com',subject:'verified-subject',email:'user@example.com',name:'User'})
  assert(!JSON.stringify(await first.controller.status()).includes('must-not-escape'),'only the native verified account fields cross the UI boundary')
  assert.deepEqual(first.writes,[],'successful login does not activate a route')
  assert.deepEqual(first.defaults,[],'successful login does not silently change the model')
  const second=await first.controller.start();await tick()
  await rejectsCode(()=>first.controller.cancel({attemptId:login.login.attemptId}),'STALE_ATTEMPT')
  assert.equal((await first.controller.status()).login.attemptId,second.login.attemptId)
  await first.controller.cancel({attemptId:second.login.attemptId})
  const selected=await first.controller.select({model:'model-a'})
  assert.deepEqual(first.writes,[[{op:'set',path:['providers','openai'],value:{displayName:'ChatGPT'}}]])
  assert.deepEqual(first.defaults,[{provider:'openai',model:'model-a',reasoningEffort:'low'}])
  assert.equal(selected.models[0].reasoning.defaultEffort,'low')
  const verified=await first.controller.probe({model:'model-a',reasoningEffort:'high'})
  assert.equal(verified.ok,true);assert.equal(first.probes.length,1)
  assert.deepEqual(first.probes[0].messages,[{role:'user',content:[{type:'text',text:'Reply with only OK.'}]}])
  assert.deepEqual(first.probes[0].tools,[]);assert.equal(first.probes[0].sessionId,undefined)
  const signedOut=await first.controller.signout()
  assert.equal(signedOut.signout.localCleared,true);assert.equal(signedOut.credential.stored,false)
  assert.equal(first.writes.length,1);assert.equal(first.defaults.length,1,'logout preserves model configuration')
}finally{await first.controller.dispose()}

// Existing profiles/catalogs remain byte-for-byte unchanged; native defaults own reasoning.
const preserved={displayName:'Personal route',models:[{id:'model-a',contextWindow:180000}],retryPolicy:{mode:'normal',maxRetries:1}}
const existing=fixture({profile:preserved,kind:'grant'})
try{
  await existing.controller.select({model:'model-a',reasoningEffort:'high'})
  assert.deepEqual(existing.descriptor.value.providers.openai,preserved);assert.deepEqual(existing.writes,[])
  await rejectsCode(()=>existing.controller.select({model:'missing'}),'MODEL_UNAVAILABLE')
  assert.equal(existing.defaults.length,1)
  existing.ctx.llm.stream=async function*(){yield {type:'text-delta',text:'partial'};yield {type:'finish',reason:{kind:'max-tokens'}}}
  assert.equal((await existing.controller.probe({model:'model-a'})).code,'INCOMPLETE')
  existing.ctx.llm.stream=async function*(){yield {type:'finish',reason:{kind:'error',failure:{code:'RATE_LIMIT',status:429,message:'provider secret token=must-not-escape'}}}}
  const quota=await existing.controller.probe({model:'model-a'})
  assert.equal(quota.code,'RATE_LIMIT');assert(!JSON.stringify(quota).includes('must-not-escape'))
  existing.ctx.credentials.describeRecord=async()=>{throw Error('filesystem secret must-not-escape')}
  const unknown=await existing.controller.status();assert.equal(unknown.credential.stored,null)
  assert.equal(unknown.credential.error.code,'CREDENTIAL_UNAVAILABLE');assert(!JSON.stringify(unknown).includes('must-not-escape'))
}finally{await existing.controller.dispose()}

for(const profile of [
  {apiKeyEnv:'PRIVATE_KEY'}, {headers:{Authorization:'secret'}}, {baseURL:'https://api.openai.com.evil.example/v1'},
  {baseURL:'http://api.openai.com/v1'}, {baseURL:'https://api.openai.com/v1?token=secret'}, {api:'openai-completions'},
  {models:[{id:'model-a',baseURL:'https://example.com/v1'}]},
  {models:[{id:'model-a',apiKeyEnv:'PRIVATE_KEY'}]},
  {modelOverrides:{'model-a':{headers:{Authorization:'secret'}}}},
]){
  assert(chatGptRouteConflicts(profile).length>0)
  const conflicting=fixture({profile,kind:'grant'})
  try{const status=await conflicting.controller.status();assert(status.route.conflicts.length);assert(!JSON.stringify(status.route).includes('PRIVATE_KEY'))
    await rejectsCode(()=>conflicting.controller.select({model:'model-a'}),'ROUTE_CONFLICT')
    assert.equal((await conflicting.controller.probe({model:'model-a'})).code,'ROUTE_CONFLICT')
    assert.deepEqual(conflicting.writes,[]);assert.deepEqual(conflicting.probes,[])
  }finally{await conflicting.controller.dispose()}
}
assert.deepEqual(chatGptRouteConflicts({baseURL:'https://api.openai.com/v1/',api:'openai-responses',headers:{}}),[])
const api=fixture({profile:{displayName:'API'},kind:'api-key'})
try{await rejectsCode(()=>api.controller.signout(),'API_KEY_CONFLICT');await rejectsCode(()=>api.controller.start(),'API_KEY_CONFLICT');assert.deepEqual(api.disconnects,[])}finally{await api.controller.dispose()}
const oldHost=fixture({profile:{displayName:'ChatGPT'},kind:'grant'})
delete oldHost.ctx.piAiAccounts
try{
  const state=await oldHost.controller.status();assert.equal(state.nativeFlowAvailable,false);assert.equal(state.credential.stored,true)
  await rejectsCode(()=>oldHost.controller.start(),'UNAVAILABLE')
  await rejectsCode(()=>oldHost.controller.select({model:'model-a'}),'UNAVAILABLE')
  assert.deepEqual(oldHost.preparations,[]);assert.deepEqual(oldHost.writes,[])
}finally{await oldHost.controller.dispose()}

// Native withdrawn prompts cannot be answered later, and controller disposal cancels its own attempt.
const abandoned=fixture()
try{
  const view=await abandoned.controller.start();await tick()
  const withdrawal=new AbortController()
  const answer=abandoned.request().interaction.prompt({kind:'text',message:'Callback',signal:withdrawal.signal}).catch(error=>error)
  const prompt=(await abandoned.controller.status()).login.prompt
  withdrawal.abort();assert.equal((await answer).code,'CANCELLED')
  await rejectsCode(()=>abandoned.controller.submitPrompt({attemptId:view.login.attemptId,promptId:prompt.id,value:'stale'}),'STALE_PROMPT')
  await abandoned.controller.dispose();assert.equal((await abandoned.controller.status()).login,null)
}finally{await abandoned.controller.dispose()}
// Disposal while storage lookup is pending cannot start a late authorization.
const slow=fixture()
let releaseStorage
slow.ctx.credentials.describeRecord=()=>new Promise(resolve=>{releaseStorage=()=>resolve({configured:false,writable:true})})
const late=slow.controller.start()
await tick();await rejectsCode(()=>slow.controller.start(),'BUSY');await slow.controller.dispose();releaseStorage()
await rejectsCode(()=>late,'UNAVAILABLE');assert.equal(slow.request(),undefined)
// A UI-owned connection probe is also cancelled when the controller is disposed.
const runningProbe=fixture({profile:{displayName:'ChatGPT'},kind:'grant'})
let entered
const enteredProbe=new Promise(resolve=>{entered=resolve})
runningProbe.ctx.llm.stream=async function*(request){entered();await new Promise((resolve,reject)=>{
  request.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true})
});yield {type:'finish',reason:{kind:'stop'}}}
const probing=runningProbe.controller.probe({model:'model-a'})
await enteredProbe;await runningProbe.controller.dispose();assert.equal((await probing).code,'CANCELLED')

// The one-time old device id is read only from the native home and only on login.
const home=await fs.mkdtemp(path.join(os.tmpdir(),'dsh-chatgpt-account-'))
const legacyFile=path.join(home,'dsh-houdini-chatgpt-host-id.json'),deviceId='11111111-2222-3333-4444-555555555555'
try{
  const migration=fixture({kind:'grant'}),nativeCalls=[]
  let installed=false,pathReads=0
  migration.ctx.dshHomePath=name=>{pathReads++;assert.equal(name,path.basename(legacyFile));return path.join(home,name)}
  migration.ctx.credentials.describeRecord=async actual=>actual===key?{configured:true,kind:'grant',writable:true}
    :actual==='llm-pi-ai-installation/openai'?{configured:installed,kind:installed?'grant':undefined,writable:true}:assert.fail('unexpected credential address')
  migration.ctx.piAiAccounts.ensureInstallationId=async(provider,options)=>{
    assert.equal(provider,'openai');nativeCalls.push(options);installed=true;return deviceId
  }
  const controller=new ChatGptAccountController(migration.ctx)
  await fs.writeFile(legacyFile,JSON.stringify({schemaVersion:1,app:'DSH-Houdini',deviceId}))
  try{
    await controller.status();assert.equal(pathReads,0);assert.deepEqual(nativeCalls,[])
    const initial=await controller.start();await tick();await tick()
    assert.deepEqual(nativeCalls,[{previousId:deviceId}]);assert.equal(JSON.parse(await fs.readFile(legacyFile,'utf8')).deviceId,deviceId)
    await controller.cancel({attemptId:initial.login.attemptId})
    await fs.writeFile(legacyFile,'invalid old record')
    const next=await controller.start();await tick();await tick()
    assert.equal(nativeCalls.length,2);assert.equal(nativeCalls[1],undefined,'a native installation record wins over obsolete old files')
    assert.equal(pathReads,1)
    await controller.cancel({attemptId:next.login.attemptId})
    installed=false
    await controller.start();await tick();await tick()
    const failed=await controller.status();assert.equal(failed.login.status,'failed');assert.equal(failed.login.error.code,'MIGRATION_INVALID')
    assert.equal(nativeCalls.length,2,'a broken old device identity is not silently replaced')
  }finally{await controller.dispose();await migration.controller.dispose()}
}finally{
  const target=path.resolve(home);assert.equal(path.dirname(target),path.resolve(os.tmpdir()));assert(path.basename(target).startsWith('dsh-chatgpt-account-'))
  await fs.rm(target,{recursive:true,force:true})
}
console.log('PASS ChatGPT UI controller: native-only authorization, safe facts, stale prompt/cancel fencing, untouched profiles, default selection, isolated probe and delegated logout')
