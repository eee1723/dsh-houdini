// Run against an exact prepared DSH runtime, without external models or Houdini.
// node tools/tests/dsh-job-completion-fixture.mjs <runtime-root>
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {runtimeFixInputs,runtimeFixKey} from '../runtime-fix-inputs.mjs';

const root=path.resolve(import.meta.dirname,'../..');
const manifest=JSON.parse(fs.readFileSync(path.join(root,'deployment/dsh-runtime-fixes/manifest.json')));
const runtime=path.resolve(process.argv[2]??path.join(root,'.npm-cache/_npx/dsh-houdini-'+runtimeFixKey(runtimeFixInputs(root,manifest))));
const proof=JSON.parse(fs.readFileSync(path.join(runtime,'.dsh-runtime-fixes.json')));
assert.equal(proof.sourceCommit,manifest.commit);
assert.equal(proof.patchSha256,manifest.patchSha256);
assert(proof.files['node_modules/@deepseek-ai/dsh-tool-jobs/lib/index.js'],'tool-jobs must come from the declared source build');
assert(proof.files['node_modules/@deepseek-ai/dsh-jobs-local/lib/index.js'],'jobs-local must come from the declared source build');
const require=createRequire(path.join(runtime,'package.json'));
const {LiveJobs}=await import(pathToFileURL(path.join(root,'lib/live-jobs.js')).href);
const load=name=>import(pathToFileURL(require.resolve('@deepseek-ai/'+name)).href);
const [{Context},{default:SystemPrompt},{default:ToolRuntime},{default:AgentRegistry},{default:LocalJobs},ToolJobs,{Session},{createToolResultMessage},SpillPolicy]=await Promise.all([
  load('cordis'),load('dsh-system-prompt'),load('dsh-tools'),load('dsh-agent'),load('dsh-jobs-local'),load('dsh-tool-jobs'),load('dsh-session'),load('dsh-llm'),load('dsh-spill-policy'),
]);
const ctx=new Context();
await ctx.plugin(SystemPrompt);
await ctx.plugin(ToolRuntime,{mode:'native'});
await ctx.plugin(AgentRegistry);
await ctx.plugin(LocalJobs);
let controls=await ctx.plugin(ToolJobs);
const scope=ctx.plugin(()=>{}),session=Session.create('job-completion-regression');
const notices=[];
const owner={id:session.id,session,ctx:scope.ctx,status:'idle',followup:message=>notices.push(message),inject:message=>notices.push(message)};
await ctx.agents.register(owner);
let callId=0;
const call=(name,args)=>ctx.tools.execute({name,arguments:args,callId:'job-regression-'+(++callId),agent:owner,signal:new AbortController().signal});
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
function producer(outputLimitBytes) {
  let settle,cancels=0;
  const done=new Promise(resolve=>{settle=resolve});
  const id=ctx.jobs.start({kind:'houdini',label:'Uninterruptible work fixture',owner:owner.id,outputLimitBytes,
    run:()=>({done,cancel:()=>{cancels++}})});
  return {id,settle,cancels:()=>cancels};
}
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject}};
async function within(promise,description) {
  let timer;
  try {return await Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(description+' did not quiesce')),1500)})])}
  finally {clearTimeout(timer)}
}
function untilAbort(promise,signal) {
  if(signal.aborted)return Promise.reject(signal.reason);
  let abort;
  const stopped=new Promise((_,reject)=>{abort=()=>reject(signal.reason);signal.addEventListener('abort',abort,{once:true})});
  return Promise.race([promise,stopped]).finally(()=>signal.removeEventListener('abort',abort));
}
let bridgeOrdinal=0;
function controlledBridge({holdCancellation=false}={}) {
  const index=++bridgeOrdinal,jobId=index.toString(16).padStart(12,'0'),runtimeId='a'.repeat(32);
  const handle={jobId,requestReceipt:{request_ref:runtimeId+'.'+index.toString(16).padStart(32,'0'),runtime_id:runtimeId,status:'job_submitted'}};
  const terminal=deferred(),entered=deferred(),cancelled=deferred();
  const facts={submissions:0,cancels:0,hardStops:0,polls:0,homState:'running',pollSignal:undefined,cancelSignal:undefined};
  const bridge={
    async submitJob(){facts.submissions++;return handle},
    forRuntime(id){assert.equal(id,runtimeId);return this},
    async jobStatus(_id,_owner,_wait,signal){facts.polls++;facts.pollSignal=signal;entered.resolve();return untilAbort(terminal.promise,signal)},
    async cancelJob(_id,_owner,signal){facts.cancels++;facts.cancelSignal=signal;return holdCancellation?cancelled.promise:{jobId,status:'running',ok:false,stdout:'',stderr:''}},
  };
  return {bridge,handle,facts,entered,terminal,cancelled,finish(){facts.homState='done';terminal.resolve({jobId,status:'done',ok:true,stdout:'actual result',stderr:''})}};
}
try {
  for(const status of ['completed','failed','killed']) {
    const p=producer();
    const before=notices.length;
    const result=await call('job_kill',{job_id:p.id});
    assert.equal(result.isError,false);
    assert.equal(result.value.outcome,'cancellation-requested');
    assert.equal(result.value.job.status,'stopping');
    assert.equal(p.cancels(),1);
    p.settle({status,result:'Actual producer result'});
    await tick();
    assert.equal(ctx.jobs.get(p.id,owner.id).status,status,'cancellation intent cannot replace the actual producer outcome');
    assert.equal(notices.length-before,status==='killed'?0:1,'a cancellation that loses the race must still deliver completion');
    if(status!=='killed')assert.match(notices.at(-1).content[0].text,new RegExp('status: '+status));
  }
  const payload=JSON.stringify({kind:'houdini-live-job',result:{stdout:'完整原回执'.repeat(12000),marker:'END-OF-ORIGINAL'}});
  const p=producer(128);
  p.settle({status:'completed',result:payload});
  await tick();
  const result=await call('job_output',{job_id:p.id});
  assert.equal(result.isError,false);
  assert.equal(result.value.text,payload);
  assert.deepEqual(result.meta.canonical,result.value,'durable metadata must preserve the exact canonical read');
  assert(Buffer.byteLength(result.content[0].text)<=128,'the model surface still honors the producer limit');
  assert(result.content[0].text.includes('[output truncated]'),'the fixture must actually truncate the displayed result');
  session.append('tool/result',{turn:1,step:1,message:createToolResultMessage({callId:'native-read',content:result.content,isError:false}),meta:result.meta},{surfaceOp:'append'});
  const cold=JSON.parse(JSON.stringify(session.snapshotEvents()));
  assert.equal(cold.find(event=>event.type==='tool/result').data.meta.canonical.text,payload,'cold native history keeps bytes discarded by display retention');
  const again=await call('job_output',{job_id:p.id});
  assert.equal(again.value.text,'','canonical preservation must not redeliver a consumed result');
  // Released PTC persists output metadata independently of display/log spill.
  const spillCopies=[];
  ctx.provide('workingDirectory',{ensure:async()=>root});
  ctx.provide('spillStore',{async saveText(input){spillCopies.push(input.content);return {
    locator:'fixture:retained',retrievalHint:'Read the retained fixture',bytes:Buffer.byteLength(input.content)}}});
  await ctx.plugin(SpillPolicy,{maxInlineTokens:1000});
  const nested=producer(20000);nested.settle({status:'completed',result:payload});await tick();
  ctx.provide('ptcRuntime',{language:'typescript',resolve:request=>request,async run(request){
    return {value:await request.bindings[0].functions.job_output({job_id:nested.id}),logs:[]};
  }});
  ctx.tools.defaultMode='ptc';
  const collected=await call('run_code',{code:'return await tools.job_output({job_id:"fixture"})',description:'Read original background output',workingDirectory:root});
  assert.equal(collected.isError,false,JSON.stringify(collected));
  const dispatch=session.snapshotEvents().find(event=>event.type==='tool/ptc-dispatch'&&event.data.name==='job_output');
  assert(dispatch,'the released PTC bridge must record its actual sub-dispatch');
  assert.equal(dispatch.data.meta.canonical.text,payload,'actual PTC metadata survives the official spill middleware intact');
  assert(spillCopies.length>0&&dispatch.data.content.some(block=>block.text?.includes('Full formatted result stored at:')),
    'the actual PTC display/log copy must have spilled');
  assert(!dispatch.data.content.some(block=>block.text?.includes('dsh-houdini/execution-v1')),'generic PTC durability needs no plugin JSON wrapper');

  // Inspect only this pinned provider's record to check retained references;
  // public lifecycle and ring reads must remain available after collection.
  const store=Reflect.get(ctx.jobs,'store'),memoryDone=deferred();
  let memoryCancels=0;
  const memoryHooks={done:memoryDone.promise,cancel(){memoryCancels++}};
  const memoryId=ctx.jobs.start({kind:'houdini',label:'Retained-result resource fixture',owner:owner.id,
    run(job){job.append('retained stream trace\n');return memoryHooks}});
  const memoryRecord=store.get(memoryId),boundCancel=memoryRecord.cancel;
  memoryDone.resolve({status:'completed',result:payload});await tick();
  assert.notEqual(memoryRecord.cancel,boundCancel,'settlement releases the producer hook receiver');
  assert.equal(memoryRecord.result,payload,'an uncollected terminal result remains available');
  const memoryRead=ctx.jobs.read(memoryId,owner.id);
  assert.equal(memoryRead.result,payload);
  assert.equal(memoryRecord.result,undefined,'the registry releases an already consumed terminal result');
  assert.equal(ctx.jobs.read(memoryId,owner.id).result,undefined);
  assert.equal(ctx.jobs.get(memoryId,owner.id).status,'completed');
  assert(ctx.jobs.list(owner.id).some(job=>job.id===memoryId),'collection does not delete the terminal record');
  assert.equal(ctx.jobs.readAt(memoryId,0,owner.id).chunks.map(chunk=>chunk.text).join(''),'retained stream trace\n');
  assert.equal(ctx.jobs.kill(memoryId,owner.id),'already-finished');assert.equal(memoryCancels,0);

  // A forced registry failure must release its hook without pretending that
  // the producer's independent asynchronous cleanup has already completed.
  const forcedScope=ctx.plugin(()=>{}),forcedSession=Session.create('forced-registry-resource-fixture');
  const forcedOwner={id:forcedSession.id,session:forcedSession,ctx:forcedScope.ctx,status:'idle',followup(){},inject(){}};
  await ctx.agents.register(forcedOwner);
  const forcedDone=deferred();let producerReleased=false,lateCancel;
  const forcedId=ctx.jobs.start({kind:'houdini',label:'Forced-record resource fixture',owner:forcedOwner.id,
    run:()=>({cancel(){throw Error('fixture teardown cancellation failed')},done:forcedDone.promise.finally(()=>{producerReleased=true})})});
  const forcedRecord=store.get(forcedId),forcedCancel=forcedRecord.cancel;
  const unsubscribe=ctx.jobs.events.subscribe({owner:forcedOwner.id},event=>{
    if(event.type==='settled')lateCancel=ctx.jobs.kill(forcedId,forcedOwner.id);
  });
  await within(forcedScope.dispose(),'forced owner teardown');unsubscribe();
  assert.equal(forcedRecord.status,'failed');assert.notEqual(forcedRecord.cancel,forcedCancel);
  assert.equal(lateCancel,'already-finished');assert.equal(producerReleased,false);
  forcedDone.resolve({status:'completed',result:'late producer result'});await tick();
  assert.equal(producerReleased,true,'producer cleanup remains independent of the forced terminal record');
  assert.equal(forcedRecord.status,'failed','late producer completion cannot overwrite a forced terminal record');

  // Keep native admission, owner cleanup and settlement real; only the Bridge
  // promises are controlled so these races require no HOM sleep or live scene.
  const producerScope=ctx.plugin(()=>{});
  const live=new LiveJobs(producerScope.ctx,{retain:async value=>value});
  const execution={agent:owner,callId:'live-boundary',signal:new AbortController().signal};
  const identity={sessionId:owner.id,callId:execution.callId};
  await controls.dispose();
  const refused=controlledBridge();
  await assert.rejects(live.submit({code:'must_not_execute()'},execution,refused.bridge,identity),/no job controller/);
  assert.equal(refused.facts.submissions,0,'native admission rejection must precede any Bridge submission');
  controls=await ctx.plugin(ToolJobs);

  const caller=new AbortController(),continuing=controlledBridge();
  const started=await live.submit({code:'long_work()'},{...execution,signal:caller.signal},continuing.bridge,identity);
  await continuing.entered.promise;caller.abort();await tick();
  assert.equal(ctx.jobs.get(started.job_id,owner.id).status,'running');
  assert.equal(continuing.facts.pollSignal.aborted,false,'ending the starting tool signal must not end its native observer');
  assert.equal(continuing.facts.cancels,0);
  continuing.finish();await ctx.jobs.wait(started.job_id,1500,owner.id);
  assert.equal(ctx.jobs.get(started.job_id,owner.id).status,'completed');

  const original=controlledBridge();
  const observers=await Promise.all([live.observe(original.handle,execution,original.bridge,identity),live.observe(original.handle,execution,original.bridge,identity)]);
  assert.equal(observers[0].job_id,observers[1].job_id,'same-reference concurrent recovery shares one observer');
  await original.entered.promise;assert.equal(original.facts.polls,1);assert.equal(original.facts.submissions,0);
  original.finish();await ctx.jobs.wait(observers[0].job_id,1500,owner.id);

  const stopping=controlledBridge({holdCancellation:true});
  const stoppingHandle=await live.submit({code:'long_work()'},execution,stopping.bridge,identity);
  await stopping.entered.promise;ctx.jobs.kill(stoppingHandle.job_id,owner.id);stopping.finish();await tick();
  assert.equal(stopping.facts.cancelSignal.aborted,true,'terminal work aborts any remaining cancellation HTTP resource');
  assert.equal(ctx.jobs.get(stoppingHandle.job_id,owner.id).status,'stopping','native done must await the pending cancellation resource');
  stopping.cancelled.resolve({jobId:stopping.handle.jobId,status:'done',ok:true,stdout:'',stderr:''});
  await ctx.jobs.wait(stoppingHandle.job_id,1500,owner.id);
  assert.equal(ctx.jobs.get(stoppingHandle.job_id,owner.id).status,'completed');

  const detached=controlledBridge();
  const detachedHandle=await live.submit({code:'long_work()'},execution,detached.bridge,identity);await detached.entered.promise;
  await within(producerScope.dispose(),'producer teardown');
  await ctx.jobs.wait(detachedHandle.job_id,1500,owner.id);
  assert.equal(detached.facts.homState,'running');assert.equal(detached.facts.cancels,0);assert.equal(detached.facts.hardStops,0);
  const detachedResult=JSON.parse(ctx.jobs.read(detachedHandle.job_id,owner.id).result);
  assert.equal(detachedResult.value.requestReceipt.status,'unknown_transport');
  assert.equal(detachedResult.value.requestReceipt.request_ref,detached.handle.requestReceipt.request_ref);

  const secondProducer=ctx.plugin(()=>{}),lastLive=new LiveJobs(secondProducer.ctx,{retain:async value=>value});
  const ownerStopped=controlledBridge();
  await lastLive.submit({code:'long_work()'},execution,ownerStopped.bridge,identity);await ownerStopped.entered.promise;
  await within(scope.dispose(),'owner teardown');
  assert.equal(ownerStopped.facts.homState,'running');assert.equal(ownerStopped.facts.hardStops,0);
  assert.equal(ctx.jobs.list(owner.id).length,0,'owner disposal releases native records without waiting for uninterruptible HOM');
  await secondProducer.dispose();
  console.log(JSON.stringify({ok:true,runtime,revision:proof.revision,checks:['cancel-race-completed-notice','cancel-race-failed-notice','actual-killed-notice-suppressed','bounded-display','lossless-native-history','single-result-delivery','lossless-native-ptc-metadata-after-real-spill','consumed-result-reference-released','settled-hook-reference-released','terminal-record-and-ring-preserved','forced-record-producer-cleanup-preserved','admission-before-bridge','caller-signal-independent','same-reference-one-observer','cancel-http-quiescence','producer-detach-keeps-hom','owner-detach-keeps-hom']}));
} finally {
  await ctx.fiber.dispose();
}
