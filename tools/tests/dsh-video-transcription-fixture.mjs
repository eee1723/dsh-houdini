// Only the ASR HTTP endpoint and planning adapter are fixtures. The DSH
// configuration tool, native credentials RPC, native/PTC and worker remain real.
import {fixturePresentation} from './fixture-presentation.mjs'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import {createHash,randomUUID} from 'node:crypto'
import {LlmAdapter} from '@deepseek-ai/dsh-llm'
import {setSandboxMode} from '@deepseek-ai/dsh-sandbox-policy'
export const inject=['loader','llm','settings','credentials','sessions','agents','sessionController','workspaceController','workspaceRegistry','sandboxPolicy','houdiniFrontend','sessionProjections']
const driver='video-fixture-driver',sha=value=>createHash('sha256').update(value).digest('hex')
export function apply(ctx){
 const workspace=process.env.DSH_VIDEO_FIXTURE_WORKSPACE,base=process.env.DSH_VIDEO_FIXTURE_BASE
 const output=process.env.DSH_VIDEO_FIXTURE_OUT,restart=process.env.DSH_VIDEO_FIXTURE_PHASE==='restart'
 const signalFile=process.env.DSH_VIDEO_FIXTURE_CREDENTIAL_SIGNAL
 const workA=path.join(workspace,'prepared-a'),workB=path.join(workspace,'prepared-b')
 const routeA={endpoint:base+'/custom-asr',protocol:'openai-transcriptions',model:'fixture-asr-a',authentication:'bearer'}
 const routeB={endpoint:base+'/custom-json-asr',protocol:'qwen-chat-asr',model:'fixture-asr-b',authentication:'none'}
 const requests=[],checks=[];let steps=0,failure,secret,firstRef,initialBHashes
 const read=(work,name)=>JSON.parse(fs.readFileSync(path.join(work,name),'utf8'))
 const ledger=work=>Object.fromEntries(fs.readdirSync(work).filter(name=>/^(asr-config|attempt-|outcome-).*\.json$/.test(name)).map(name=>[name,sha(fs.readFileSync(path.join(work,name)))]))
 const report=value=>{fs.writeFileSync(output+'.tmp',JSON.stringify(value,null,2));fs.renameSync(output+'.tmp',output)}
 const fail=error=>{failure??=String(error.stack||error).replaceAll(secret||'fixture-never-matches','[redacted]');report({ok:false,error:failure,requests,checks,steps})}
 const server=http.createServer(async(req,res)=>{
  try{
   assert(!restart,'Restart must reuse completed original task receipts')
   assert.equal(req.method,'POST')
   const buffers=[];for await(const bytes of req)buffers.push(bytes)
   const body=Buffer.concat(buffers);let model,audio,authentication
   if(req.url==='/custom-asr'){
    assert.equal(req.headers.authorization,'Bearer '+secret);authentication='bearer'
    const form=await new Request(base+req.url,{method:'POST',headers:{'content-type':req.headers['content-type']},body}).formData()
    model=form.get('model');const file=form.get('file');assert.equal(file.name,'audio.wav');assert.equal(file.type,'audio/wav');audio=Buffer.from(await file.arrayBuffer())
   }else{
    assert.equal(req.url,'/custom-json-asr');assert.equal(req.headers.authorization,undefined);authentication='none'
    const value=JSON.parse(body);model=value.model;assert.equal(value.stream,false);assert.deepEqual(value.asr_options,{enable_itn:false})
    const item=value.messages[0].content[0];assert.equal(item.type,'input_audio');audio=Buffer.from(item.input_audio.data.split(',')[1],'base64')
   }
   assert(['fixture-asr-a','fixture-asr-b'].includes(model));assert.equal(audio.toString('ascii',0,4),'RIFF')
   const work=model==='fixture-asr-a'?workA:workB,hash=sha(audio),chunk=read(work,'manifest.json').chunks.find(row=>row.sha256===hash)
   assert(chunk);assert(!requests.some(row=>row.model===model&&row.chunk===chunk.id),'successful audio was uploaded again')
   requests.push({model,chunk:chunk.id,audio_sha256:hash,bytes:audio.length,authentication,authorizationMatched:true})
   const text='Fixture transcript '+model+' '+chunk.id
   res.writeHead(200,{'content-type':'application/json','x-request-id':'owned-asr-'+requests.length})
   res.end(JSON.stringify(model==='fixture-asr-b'?{choices:[{finish_reason:'stop',message:{role:'assistant',content:text}}]}:{text}))
  }catch(error){fail(error);res.writeHead(500,{'content-type':'application/json'});res.end('{"error":"fixture assertion failed"}')}
 })
 const ready=new Promise((resolve,reject)=>{server.once('error',reject);server.listen(Number(new URL(base).port),'127.0.0.1',resolve)})
 const text=value=>[{type:'block-start',index:0,blockType:'text'},{type:'block-end',index:0,block:{type:'text',text:value}},{type:'finish',reason:{kind:'stop'}}]
 const presentation=fixturePresentation(ctx),prefix=restart?'asr-restart-':'asr-initial-'
 let chatBefore
 function validate(value,route,submitted,remaining){
  assert(value?.ok,value?.error);assert.equal(value.status,'processed');assert.equal(value.provider,null)
  assert.equal(value.endpoint,route.endpoint);assert.equal(value.model,route.model);assert.equal(value.protocol,route.protocol);assert.equal(value.authentication,route.authentication)
  assert.equal(value.concurrency,2);assert.equal(value.requests_per_second,1)
  assert.equal(value.summary.submitted,submitted);assert.equal(value.summary.remaining,remaining)
  const work=route.model==='fixture-asr-a'?workA:workB,config=read(work,'asr-config.json')
  assert.equal(config.model,route.model);assert.equal(config.authentication,route.authentication)
  assert.equal(config.protocol,route.protocol==='openai-transcriptions'?undefined:route.protocol)
  assert.equal(config.manifest_sha256,sha(fs.readFileSync(path.join(work,'manifest.json'))))
  for(const row of requests.filter(row=>row.model===route.model)){
   const outcome=read(work,`outcome-${row.chunk}-1.json`);assert.equal(outcome.status,'success');assert.equal(outcome.audio_sha256,row.audio_sha256)
   assert.equal(outcome.text,'Fixture transcript '+route.model+' '+row.chunk)
  }
 }
 async function waitForNativeCredential(config){
  firstRef=config.service.credentialRef;assert.match(firstRef,/^DSH_HOUDINI_ASR_[A-F0-9]{16}_API_KEY$/)
  assert.equal(config.service.credential.configured,false)
  fs.writeFileSync(signalFile,JSON.stringify({ref:firstRef,origin:config.service.origin,endpoint:config.service.endpoint}))
  const end=Date.now()+30000
  while(!(await ctx.credentials.describe(firstRef)).configured){assert(Date.now()<end,'Native credentials/set was not received');await new Promise(resolve=>setTimeout(resolve,100))}
  secret=(await ctx.credentials.resolve(firstRef)).value;assert(secret)
  checks.push('real video_configure committed purpose settings; native authenticated credentials/set supplied its reference without chat')
 }
 const initialCalls=[
  ['video_configure',routeA],['video_models',{}],['video_transcribe',{work:workA,allow_upload:false,max_chunks:1}],
  ['video_configure',routeB],
  ['run_code',{code:'return await tools.video_transcribe('+JSON.stringify({work:workB,allow_upload:false,max_chunks:1})+');',description:'Exercise explicit noauth ASR through actual PTC'}],
  ['video_transcribe',{work:workB,allow_upload:false,max_chunks:1}],['video_transcribe',{work:workB,allow_upload:false,max_chunks:100}],
  ['video_configure',{endpoint:routeA.endpoint,model:'changed-task-identity',protocol:'openai-transcriptions',authentication:'none'}],
  ['video_transcribe',{work:workB,allow_upload:false,max_chunks:1}],['video_configure',routeB],['video_models',{}],
 ]
 const restartCalls=[['video_models',{}],['video_transcribe',{work:workB,allow_upload:false,max_chunks:100}]]
 class Driver extends LlmAdapter{
  async listModels(){return[{provider:driver,id:'scripted',name:'ASR fixture planning',inputModalities:['text']}]}
  async resolveModel(provider,id){return{provider,id,name:'ASR fixture planning',inputModalities:['text'],context:{contextWindow:500000}}}
  async *stream(options){
   if(options.purpose){yield*text('ASR fixture');return}
   try{
    assert(!failure,failure);if(secret)assert(!JSON.stringify(options).includes(secret),'secret entered the final model request')
    const step=steps++,calls=restart?restartCalls:initialCalls;assert(step<=calls.length,'fixture converges')
    const events=ctx.sessions.get(options.sessionId).snapshotEvents()
    const native=n=>{
     const event=events.find(e=>e.type==='tool/result'&&e.data?.message?.source?.callId===prefix+n)
     assert(event,'missing native result '+prefix+n)
     assert(!event.data.message.isError,JSON.stringify(event.data.message.content))
     assert(event.data.meta&&Object.hasOwn(event.data.meta,'canonical'),'native result lost canonical '+prefix+n)
     return event.data.meta.canonical
    }
    if(restart){
     if(step===1){const status=native(0);assert.equal(status.service.model,routeB.model);assert.equal(status.service.authentication,'none');assert.equal(status.service.protocol,routeB.protocol)}
     if(step===2){validate(native(1),routeB,0,0);assert.equal(requests.length,0);checks.push('same native Session and original completed task resume after Host restart without another upload')}
    }else{
     if(step===1)await waitForNativeCredential(native(0))
     if(step===2){const status=native(1);assert.equal(status.service.credential.configured,true);assert.equal(status.service.support,'unverified');assert.equal(requests.length,0)}
     if(step===3){validate(native(2),routeA,1,2);assert.equal(requests.length,1);checks.push('real Python multipart sender uses ASR-only custom path and an actual one-chunk cost budget')}
     if(step===4){assert.equal(native(3).service.authentication,'none');assert.equal(native(3).service.credential.required,false)}
     if(step===5){
      const dispatch=events.find(e=>e.type==='tool/ptc-dispatch'&&e.data?.name==='video_transcribe');assert(dispatch&&!dispatch.data.isError)
      validate(JSON.parse(dispatch.data.content.find(block=>block.type==='text').text),routeB,1,2);assert.equal(requests.length,2)
      checks.push('same canonical ASR result crosses real native and PTC execution with explicit protocol and noauth')
     }
     if(step===6){validate(native(5),routeB,1,1);assert.equal(requests.length,3)}
     if(step===7){validate(native(6),routeB,1,0);assert.equal(requests.length,4);initialBHashes=ledger(workB)}
     if(step===9){const value=native(8);assert.equal(value.ok,false);assert.match(value.error,/configuration\/source changed/)
      assert.deepEqual(ledger(workB),initialBHashes);assert.equal(requests.length,4);checks.push('changed default route cannot rewrite or bill an existing task; original attempt/outcome bytes remain exact')}
    }
    if(step===calls.length){yield*text('ASR fixture completed.');return}
    const[name,args]=calls[step];assert(options.tools.some(tool=>tool.name===name),'mounted '+name)
    presentation.after(prefix+step,calls[step+1]?.[0])
    yield{type:'block-start',index:0,blockType:'tool-call'}
    yield{type:'block-end',index:0,block:{type:'tool-call',id:prefix+step,name,arguments:JSON.stringify(args)}}
    yield{type:'finish',reason:{kind:'tool-calls'}}
   }catch(error){fail(error);throw error}
  }
 }
 ctx.llm.registerAdapter([driver],new Driver())
 ctx.effect(()=>{queueMicrotask(async()=>{
  try{
   await ready;await ctx.loader.await()
   if(!restart){const config=ctx.settings.describe().find(row=>row.ns==='houdini-frontend');
    await ctx.settings.update(config.ns,{videoPython:process.env.DSH_VIDEO_FIXTURE_PYTHON},config.revision)}
   chatBefore=ctx.settings.describe().find(row=>row.ns==='llm-pi-ai')?.value
   let sessionId
   if(restart){
    sessionId=process.env.DSH_VIDEO_FIXTURE_SESSION;assert(sessionId)
    const resolved=await ctx.sessionController.resolveAgent(sessionId);assert(!('error'in resolved))
    assert.equal(ctx.sessionProjections.stateOf(resolved.agent.session,'agentPreset'),'houdini')
    assert.equal(ctx.houdiniFrontend.videoSelection().model,routeB.model)
   }else{
    const {workspace:record}=await ctx.workspaceController.create({path:workspace})
    ;({sessionId}=await ctx.sessionController.create({sessionId:randomUUID(),workspaceId:record.workspaceId,agentPreset:'houdini'}))
   }
   setSandboxMode(ctx.sessions.get(sessionId),'workspace-write')
   await ctx.sessionController.selectModel({sessionId,provider:driver,model:'scripted'})
   await ctx.sessionController.prompt({sessionId,requestId:randomUUID(),mode:'queue',content:[{type:'text',text:'Run the owned ASR '+(restart?'restart':'initial')+' transport fixture.'}]},AbortSignal.timeout(120000))
   const agent=ctx.agents.get(sessionId);await agent.whenIdle();assert(!failure,failure)
   assert.equal(steps,restart?3:12);assert.equal(requests.length,restart?0:4)
   assert.deepEqual(ctx.settings.describe().find(row=>row.ns==='llm-pi-ai')?.value,chatBefore,'ASR setup must not add a fake chat profile')
   const models=await ctx.llm.listModels(driver);assert(!models.some(model=>[routeA.model,routeB.model].includes(model.id)))
   await ctx.sessions.flush(agent.session)
   const events=agent.session.snapshotEvents();if(secret)assert(!JSON.stringify(events).includes(secret))
   checks.push('ASR IDs are absent from chat models; native canonical/session results contain no secret')
   report({ok:true,sessionId,workspace,checks,requests,steps,phase:restart?'restart':'initial',
    settingsPersisted:ctx.houdiniFrontend.videoSelection().model===routeB.model,credentialRef:firstRef,
    boundary:'Owned ASR HTTP and scripted planning only; exact official DSH tools/settings/credentials and actual Python/media. No paid provider, user profile, Houdini or GUI claim.'})
  }catch(error){fail(error)}
 });return()=>server.close()})
}
