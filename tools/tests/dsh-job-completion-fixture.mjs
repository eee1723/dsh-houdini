// Exercise plugin-owned compatibility over unmodified official jobs and tools.
// node tools/tests/dsh-job-completion-fixture.mjs [official-runtime-root]
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';

const root=path.resolve(import.meta.dirname,'../..'),runtime=path.resolve(process.argv[2]??root);
const require=createRequire(path.join(runtime,'package.json'));
const load=name=>import(pathToFileURL(require.resolve('@deepseek-ai/'+name)).href);
const target=JSON.parse(fs.readFileSync(path.join(runtime,'node_modules/@deepseek-ai/dsh/package.json'),'utf8')).version;
assert(JSON.parse(fs.readFileSync(path.join(root,'dsh-runtime-compatibility.json'),'utf8')).releases.some(row=>row.dshVersion===target),'test an explicitly supported official runtime');
const [{Context},{default:SystemPrompt},{default:ToolRuntime},{default:AgentRegistry},{default:LocalJobs},ToolJobs,
  {Session},SpillPolicy,{createScope},NativeExecution,PtcExecution,{SessionProjectionRegistry}]=await Promise.all([
  load('cordis'),load('dsh-system-prompt'),load('dsh-tools'),load('dsh-agent'),load('dsh-jobs-local'),load('dsh-tool-jobs'),
  load('dsh-session'),load('dsh-spill-policy'),load('dsh-scope'),load('dsh-tool-executor-native'),load('dsh-tool-executor-ptc'),load('dsh-session-projection')]);
const {LiveJobs}=await import(pathToFileURL(path.join(root,'lib/live-jobs.js')).href);
const {renderJobHandle,renderExec,jobHandleMeta}=await import(pathToFileURL(path.join(root,'lib/tool-output.js')).href);
const {retainResult,readResultDetail}=await import(pathToFileURL(path.join(root,'lib/result-details.js')).href);
const {installHoudiniExecutionLog,LIVE_JOB_KIND,LIVE_JOB_RESULT,JOB_EXECUTION_RECORD,executionResult}=await import(pathToFileURL(path.join(root,'lib/dsh-adapter.js')).href);
const ctx=new Context();
await ctx.plugin(SystemPrompt);await ctx.plugin(ToolRuntime);await ctx.plugin(SessionProjectionRegistry);await ctx.plugin(AgentRegistry);
ctx.tools.setExecutor(new NativeExecution.NativeToolExecutor(ctx));
await ctx.plugin(LocalJobs);let controls=await ctx.plugin(ToolJobs,{inlineOutputBytes:0});
const native=ctx.tools.get('job_output'),presetKey={},preset=createScope(ctx,presetKey);
installHoudiniExecutionLog(preset.ctx);
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const deferred=()=>{let resolve;const promise=new Promise(yes=>{resolve=yes});return {promise,resolve}};
async function settled(id,owner){const end=Date.now()+1500;while(['running','stopping'].includes(ctx.jobs.get(id,owner).status)&&Date.now()<end)await tick();
  assert(!['running','stopping'].includes(ctx.jobs.get(id,owner).status),'owned fixture did not settle');await tick()}
async function ownerFor(id,houdini){
  const notices=[],wakeups=[],pending=[],session=Session.create(id),owner={id,session,status:'idle',ctx:undefined,
    inbox:{nextStep:pending,remove(messageId){const index=pending.findIndex(message=>message.id===messageId);if(index>=0)pending.splice(index,1)}},
    followup:message=>{wakeups.push(message);notices.push(message);pending.push(message)},
    inject:message=>{notices.push(message);pending.push(message)}};
  const scope=createScope(ctx,owner,houdini?{parent:presetKey}:{});owner.ctx=scope.ctx;
  await ctx.agents.register(owner);return {owner,scope,notices,wakeups};
}
const selected=await ownerFor('houdini-job-owner',true),other=await ownerFor('standard-job-owner',false);
let ordinal=0,callId=0;
async function call(owner,name,args){
  const executor=await owner.ctx.plugin(name==='run_code'?PtcExecution:NativeExecution,{});
  try {
    const id='fixture-'+(++callId),batch=await ctx.tools.execute({calls:[{type:'tool-call',id,name,arguments:JSON.stringify(args)}],
      agent:owner,signal:new AbortController().signal,log:{turn:1,step:callId}});
    assert.equal(batch.results.length,1);return batch.results[0].result;
  }finally{await executor?.dispose()}
}
function bridgeFor({cancelFinishes=false}={}) {
  const serial=++ordinal,jobId=serial.toString(16).padStart(12,'0'),runtimeId='a'.repeat(32),terminal=deferred();
  let cancels=0,submissions=0;
  const receipt={request_ref:runtimeId+'.'+serial.toString(16).padStart(32,'0'),runtime_id:runtimeId,status:'job_submitted'};
  const bridge={forRuntime(){return this},async submitJob(){submissions++;return {jobId,requestReceipt:receipt}},
    async jobStatus(_id,_owner,_wait,signal){return new Promise((resolve,reject)=>{
      const abort=()=>reject(signal.reason);signal.addEventListener('abort',abort,{once:true});
      terminal.promise.then(value=>{signal.removeEventListener('abort',abort);resolve(value)},reject)})},
    async cancelJob(){cancels++;if(cancelFinishes)finish();return {jobId,status:'running',ok:false,stdout:'',stderr:''}}};
  const finish=(status='done',stdout='actual producer result',extra={})=>terminal.resolve({jobId,status,ok:status==='done',stdout,stderr:'',...extra});
  return {bridge,finish,receipt,jobId,cancels:()=>cancels,submissions:()=>submissions};
}
const live=new LiveJobs(preset.ctx,{retain:async value=>value});
const archiveDirectory=fs.mkdtempSync(path.join(os.tmpdir(),'dsh-job-archive-'));
const archivedLive=new LiveJobs(preset.ctx,{retain:value=>retainResult(value,archiveDirectory)});
const execution=()=>{const id='live-'+(++callId);return {agent:selected.owner,callId:id,rootCallId:'root-'+id,signal:new AbortController().signal}};
async function start(options,producer=live){const controlled=bridgeFor(options),exec=execution();
  const admitted=await producer.submit({code:'owned_fixture()'},exec,controlled.bridge,{sessionId:selected.owner.id,callId:exec.callId});
  return {...controlled,id:admitted.job_id,admitted,exec}}
function fact(controlled,holder=selected){
  const rows=holder.owner.session.snapshotEvents().filter(event=>event.type===JOB_EXECUTION_RECORD
    &&event.data.callId==='bridge-job:'+controlled.receipt.request_ref);
  assert.equal(rows.length,1,'one actual terminal execution is recorded before any generic job read');
  const event=rows[0],data=event.data;
  assert.equal(event.ignorable,true);assert.equal(data.schema,1);assert.equal(data.tool,'houdini_job_submit');
  if(controlled.exec){assert.equal(data.sourceCallId,controlled.exec.callId);assert.equal(data.rootCallId,controlled.exec.rootCallId??controlled.exec.callId)}
  const decoded=executionResult(event);assert.equal(decoded.recorded,true);assert.equal(decoded.producer,'live-job');
  assert.deepEqual(decoded.value,data.canonical);return data.canonical;
}
try {
  assert.equal(ctx.tools.get('job_output',selected.owner),native,'Houdini consumes the original native tool without cloning its definition');
  assert.equal(ctx.tools.get('job_output',other.owner),native,'other modes retain the original definition object');
  const readable=await start();
  const exposed=renderJobHandle(readable.admitted)[0].text;
  const waitArguments=JSON.parse(exposed.match(/job_output\((\{[^\n]*?\})\)/)[1]);
  assert.equal(waitArguments.job_id,readable.id,'model-visible wait action uses the actual native job');
  assert.notEqual(waitArguments.job_id,readable.jobId,'Bridge id is a separate namespace');
  assert.equal(jobHandleMeta(readable.admitted).job_id,readable.id,'UI and model share the same native identifier');
  readable.finish();await settled(readable.id,selected.owner.id);
  assert.equal(fact(readable).status,'done','completion fact does not depend on job_output consumption');
  const readableResult=await call(selected.owner,'job_output',waitArguments);
  assert.equal(readableResult.isError,false,'the exact presented action is accepted by the real DSH tool: '+JSON.stringify(readableResult));
  const resumable=bridgeFor(),resumed=await live.observe({jobId:resumable.jobId,requestReceipt:resumable.receipt},execution(),resumable.bridge,{sessionId:selected.owner.id,callId:'recover'});
  const resumedText=renderExec({ok:true,stdout:'',stderr:'',...resumed})[0].text;
  const resumedArguments=JSON.parse(resumedText.match(/job_output\((\{[^\n]*?\})\)/)[1]);
  assert.equal(resumedArguments.job_id,resumed.job_id,'recovery reports the new local observer id');
  resumable.finish();await settled(resumed.job_id,selected.owner.id);
  assert.equal((await call(selected.owner,'job_output',resumedArguments)).isError,false);
  assert.equal(resumable.submissions(),0,'resuming observation never submits scene code');
  for(const status of ['done','failed','cancelled']) {
    const running=await start(),before=selected.notices.length;
    const killed=await call(selected.owner,'job_kill',{job_id:running.id});assert.equal(killed.value.outcome,'cancellation-requested');
    running.finish(status);await settled(running.id,selected.owner.id);
    assert.equal(running.cancels(),1);
    assert.equal(ctx.jobs.get(running.id,selected.owner.id).status,status==='done'?'completed':status==='failed'?'failed':'killed');
    assert.equal(selected.notices.length-before,0,'DSH owns suppression after a model-requested kill, independently of the actual outcome');
    const collected=await call(selected.owner,'job_output',{job_id:running.id});
    assert.equal(collected.meta,undefined,'generic job reads retain their native metadata contract');
    assert.equal(fact(running).status,status,'all actual terminal outcomes are recorded by the producer');
  }
  const immediate=await start({cancelFinishes:true}),beforeImmediate=selected.notices.length;
  await call(selected.owner,'job_kill',{job_id:immediate.id});await settled(immediate.id,selected.owner.id);
  assert.equal(selected.notices.length-beforeImmediate,0,'early settlement follows the same native model-kill suppression');
  for(const modelKill of [false,true]) {
    const running=await start(),before=selected.notices.length;
    if(modelKill)await call(selected.owner,'job_kill',{job_id:running.id});else ctx.jobs.kill(running.id,selected.owner.id);
    const waiting=call(selected.owner,'job_output',{job_id:running.id,wait:true});await tick();running.finish();
    await waiting;await settled(running.id,selected.owner.id);
    assert.equal(selected.notices.length-before,0,'an explicit native waiter already owns completion delivery');
  }
  const normal=await start(),beforeNormal=selected.notices.length;normal.finish();await settled(normal.id,selected.owner.id);
  assert.equal(selected.notices.length-beforeNormal,1,'ordinary native notification is never duplicated');
  const uiKill=await start(),beforeUiKill=selected.notices.length;ctx.jobs.kill(uiKill.id,selected.owner.id);uiKill.finish();await settled(uiKill.id,selected.owner.id);
  assert.equal(selected.notices.length-beforeUiKill,1,'a UI kill keeps the ordinary native completion path');
  const payload='完整原回执'.repeat(12000)+'END-OF-ORIGINAL',large=await start();large.finish('done',payload);await settled(large.id,selected.owner.id);
  const result=await call(selected.owner,'job_output',{job_id:large.id});assert.equal(result.isError,false);
  assert.equal(result.meta,undefined);assert(Buffer.byteLength(result.value.text)<=65536,'unarchived observer results remain bounded');
  assert.ok(result.content.every(block=>block.type!=='text'||Buffer.byteLength(block.text)<=16000));
  const cold=JSON.parse(JSON.stringify(selected.owner.session.snapshotEvents()));
  const stored=cold.find(event=>event.type===JOB_EXECUTION_RECORD&&event.data.callId==='bridge-job:'+large.receipt.request_ref);
  assert(Buffer.byteLength(JSON.stringify(stored.data.canonical))<=65536,'cold session facts are bounded even when archival is unavailable');
  assert.equal(executionResult(stored).value.status,'done','history decodes the exact producer fact');
  assert.equal((await call(selected.owner,'job_output',{job_id:large.id})).value.text,'','preserving metadata never reconsumes a native job');
  const archived=await start(undefined,archivedLive);archived.finish('done',payload,{result:{payload}});await settled(archived.id,selected.owner.id);
  const archivedRead=await call(selected.owner,'job_output',{job_id:archived.id});
  assert.equal(archivedRead.meta,undefined);const archivedFacts=fact(archived);
  assert.equal(archivedFacts.result,undefined);assert.equal(archivedFacts.stdout,undefined);
  assert.equal(archivedFacts.details.projection,'dsh-houdini/execution-facts-v1');
  assert(Buffer.byteLength(archivedRead.value.text)<16000,'DSH registry and client receive the existing lightweight execution facts');
  let recoveredPayload='',offset=0;
  do {
    const page=await readResultDetail(archiveDirectory,archivedFacts.details.sha256,'/result/payload',offset,16000);
    recoveredPayload+=page.result.text;offset=page.result.next_offset;
  }while(offset!==null);
  assert.equal(JSON.parse(recoveredPayload),payload,'the complete archived value remains recoverable through the public detail reader');
  const archivedBytes=fs.readFileSync(archivedFacts.details.path,'utf8');
  assert.equal(JSON.parse(archivedBytes).stdout,payload);assert.equal(JSON.parse(archivedBytes).result.payload,payload);
  const failed=await start(),failure='CheckpointError: failed final output /obj/fixture/OUT';
  failed.finish('failed',payload,{error:failure,outcome:{batch:'failed',operations:{total:100,failed:1}},
    transaction:{status:'rolled_back'},verbs:[{verb:'verify_network',ok:false,error:failure}],
    details:{stored:true,sha256:'c'.repeat(64),path:path.join(root,'fixture-original.json'),format:'returned_bridge_envelope_json'}});
  await settled(failed.id,selected.owner.id);
  const failureRead=await call(selected.owner,'job_output',{job_id:failed.id}),failureText=failureRead.content.map(b=>b.text??'').join('\n');
  assert(Buffer.byteLength(failureText)<=16000);
  for(const fact of [failure,'rolled_back','verify_network',failed.receipt.request_ref,'c'.repeat(64)])assert(failureText.includes(fact),fact);
  assert(!failureText.includes('[result truncated]'),'plugin summary fits the unchanged native finalizer');
  assert.equal(failureRead.meta,undefined);assert.equal(fact(failed).stdout,undefined,'archived failures also share the lightweight execution projection');
  // Generic jobs keep their exact native value, renderer, and metadata in
  // Houdini and other scopes; no native definition or metadata is shadowed.
  for(const holder of [selected,other]) {
    const done=deferred(),id=ctx.jobs.start({kind:'bash',label:'Other producer',owner:holder.owner.id,run:()=>({done:done.promise,cancel(){}})});
    done.resolve({status:'completed',result:'plain-other-result'});await settled(id,holder.owner.id);
    const value=await call(holder.owner,'job_output',{job_id:id});assert.equal(value.value.text,'plain-other-result');
    assert.deepEqual(value.content,native.output.render({job_id:id},value.value));
    assert.equal(value.meta,undefined);
  }
  const otherDone=deferred(),otherBefore=other.notices.length,otherId=ctx.jobs.start({kind:LIVE_JOB_KIND,label:'Other mode',owner:other.owner.id,
    run:()=>({done:otherDone.promise,cancel(){}})});
  await call(other.owner,'job_kill',{job_id:otherId});otherDone.resolve({status:'completed',result:'other mode owned output'});await settled(otherId,other.owner.id);
  assert.equal(other.notices.length-otherBefore,0,'the plugin never changes another mode cancellation behavior');
  const spillCopies=[];ctx.provide('workingDirectory',{ensure:async()=>root});
  ctx.provide('spillStore',{async saveText(input){spillCopies.push(input.content);return {locator:'fixture:retained',retrievalHint:'Read retained fixture',bytes:Buffer.byteLength(input.content)}}});
  await ctx.plugin(SpillPolicy,{maxInlineTokens:100});
  const nested=await start();nested.finish('done',payload);await settled(nested.id,selected.owner.id);
  let nestedJobId=nested.id;
  ctx.provide('ptcRuntime',{language:'typescript',resolve:request=>request,release(){},async run(request){return {value:await request.bindings[0].functions.job_output({job_id:nestedJobId}),logs:[]}}});
  const nestedResult=await call(selected.owner,'run_code',{code:'return await tools.job_output({job_id:"fixture"})',description:'Read native Houdini job',workingDirectory:root});
  assert.equal(nestedResult.isError,false,JSON.stringify(nestedResult));
  const dispatch=selected.owner.session.snapshotEvents().findLast(event=>event.type==='tool/ptc-dispatch'&&event.data.name==='job_output');
  assert(dispatch,'official PTC records the actual nested dispatch');
  assert.equal(dispatch.data.meta,undefined,'nested generic tool metadata is not replaced by Houdini');
  assert.equal(fact(nested).status,'done','nested reads do not create or replace completion facts');
  assert.ok(spillCopies.length>0,'real native display spilling leaves the independent producer fact intact');
  const nestedArchived=await start(undefined,archivedLive);nestedArchived.finish('done',payload,{result:{payload}});await settled(nestedArchived.id,selected.owner.id);
  nestedJobId=nestedArchived.id;
  const nestedArchivedRead=await call(selected.owner,'run_code',{code:'return await tools.job_output({job_id:"fixture"})',description:'Read archived native Houdini job',workingDirectory:root});
  assert.equal(nestedArchivedRead.isError,false);
  const archivedDispatch=selected.owner.session.snapshotEvents().findLast(event=>event.type==='tool/ptc-dispatch'&&event.data.name==='job_output');
  assert.equal(archivedDispatch.data.meta,undefined);const nestedArchivedFacts=fact(nestedArchived);
  assert.equal(nestedArchivedFacts.result,undefined);assert.equal(nestedArchivedFacts.stdout,undefined);
  assert.equal(nestedArchivedFacts.details.projection,'dsh-houdini/execution-facts-v1');
  assert.equal(JSON.parse(fs.readFileSync(nestedArchivedFacts.details.path,'utf8')).result.payload,payload);
  await controls.dispose();
  assert.equal(ctx.tools.get('job_output'),undefined,'unload removes the native definition');
  assert.equal(ctx.tools.get('job_output',selected.owner),undefined,'a surviving Houdini agent cannot retain a stale copy');
  controls=await ctx.plugin(ToolJobs,{completionDelivery:'quiet',maxConsecutiveWakes:1,inlineOutputBytes:0});
  const reloaded=ctx.tools.get('job_output');assert.notEqual(reloaded,native);assert.notEqual(reloaded.execute,native.execute);
  assert.equal(ctx.tools.get('job_output',selected.owner),reloaded,'surviving agents resolve the new native execute function');
  const afterReloadDone=deferred(),afterReloadId=ctx.jobs.start({kind:'bash',label:'After reload',owner:selected.owner.id,
    run:()=>({done:afterReloadDone.promise,cancel(){}})});
  afterReloadDone.resolve({status:'completed',result:'new native controller'});await settled(afterReloadId,selected.owner.id);
  assert.equal((await call(selected.owner,'job_output',{job_id:afterReloadId})).value.text,'new native controller',
    'the same surviving agent executes the replacement native controller');
  const quietOwner=await ownerFor('quiet-job-owner',true),quiet=bridgeFor(),quietExec={agent:quietOwner.owner,callId:'quiet-submit',signal:new AbortController().signal};
  const quietAdmission=await live.submit({code:'owned_fixture()'},quietExec,quiet.bridge,{sessionId:quietOwner.owner.id,callId:quietExec.callId});
  await call(quietOwner.owner,'job_kill',{job_id:quietAdmission.job_id});quiet.finish();await settled(quietAdmission.job_id,quietOwner.owner.id);
  assert.equal(quietOwner.wakeups.length,0,'Houdini may not bypass native quiet delivery or wake budgets after cancellation');
  const quietResult=await call(quietOwner.owner,'job_output',{job_id:quietAdmission.job_id});
  assert.equal(quietResult.meta,undefined);
  assert.equal(fact({...quiet,exec:quietExec},quietOwner).status,'done','suppressed notification never discards the actual execution');
  await controls.dispose();controls=await ctx.plugin(ToolJobs);
  const inlineOwner=await ownerFor('native-inline-owner',false),inlineDone=deferred();
  const inlineId=ctx.jobs.start({kind:'bash',label:'Native small output',owner:inlineOwner.owner.id,
    run:()=>({done:inlineDone.promise,cancel(){}})});
  inlineDone.resolve({status:'completed',result:'small native completion'});await settled(inlineId,inlineOwner.owner.id);
  assert.equal(inlineOwner.notices.length,1);
  assert(inlineOwner.notices[0].content.some(block=>block.type==='text'&&block.text.includes('small native completion')),
    'the new official small-output completion notice stays native and is not suppressed by Houdini');
  assert.equal(inlineOwner.owner.session.snapshotEvents().filter(event=>event.type===JOB_EXECUTION_RECORD).length,0,
    'a generic completion does not fabricate a Houdini execution fact');
  await preset.dispose();
  assert.equal(ctx.tools.get('job_output',selected.owner),ctx.tools.get('job_output'),'plugin unload removes the scoped definition while keeping the Agent');
  console.log(JSON.stringify({ok:true,runtime,dshVersion:target,checks:['real-native-jobs','cancellation-lost-completed-and-failed','native-model-kill-suppression','quiet-delivery-preserved','early-settlement','waiter-not-duplicated','UI-kill-not-duplicated','producer-facts-before-native-read','native-and-nested-original-metadata','bounded-durable-facts','exact-archived-recovery','display-retention','single-consumption','other-modes-unchanged','native-inline-notice','controller-unload-reload-with-surviving-agent','plugin-unload']}));
}finally{await ctx.fiber.dispose();fs.rmSync(archiveDirectory,{recursive:true,force:true})}
