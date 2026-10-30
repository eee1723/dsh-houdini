// Exercise plugin-owned compatibility over unmodified official jobs and tools.
// node tools/tests/dsh-job-completion-fixture.mjs [official-runtime-root]
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';

const root=path.resolve(import.meta.dirname,'../..'),runtime=path.resolve(process.argv[2]??root);
const require=createRequire(path.join(runtime,'package.json'));
const load=name=>import(pathToFileURL(require.resolve('@deepseek-ai/'+name)).href);
const target=JSON.parse(fs.readFileSync(path.join(root,'dsh-runtime-compatibility.json'),'utf8')).preferredVersion;
assert.equal(JSON.parse(fs.readFileSync(path.join(runtime,'node_modules/@deepseek-ai/dsh/package.json'),'utf8')).version,target);
const [{Context},{default:SystemPrompt},{default:ToolRuntime},{default:AgentRegistry},{default:LocalJobs},ToolJobs,
  {Session},{createToolResultMessage},SpillPolicy,{createScope}]=await Promise.all([
  load('cordis'),load('dsh-system-prompt'),load('dsh-tools'),load('dsh-agent'),load('dsh-jobs-local'),load('dsh-tool-jobs'),
  load('dsh-session'),load('dsh-llm'),load('dsh-spill-policy'),load('dsh-scope')]);
const {LiveJobs}=await import(pathToFileURL(path.join(root,'lib/live-jobs.js')).href);
const {installHoudiniExecutionLog,LIVE_JOB_KIND,LIVE_JOB_RESULT,executionResult}=await import(pathToFileURL(path.join(root,'lib/dsh-adapter.js')).href);
const ctx=new Context();
await ctx.plugin(SystemPrompt);await ctx.plugin(ToolRuntime,{mode:'native'});await ctx.plugin(AgentRegistry);
await ctx.plugin(LocalJobs);let controls=await ctx.plugin(ToolJobs);
const native=ctx.tools.get('job_output'),presetKey={},preset=createScope(ctx,presetKey);
installHoudiniExecutionLog(preset.ctx);
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const deferred=()=>{let resolve;const promise=new Promise(yes=>{resolve=yes});return {promise,resolve}};
async function settled(id,owner){const end=Date.now()+1500;while(['running','stopping'].includes(ctx.jobs.get(id,owner).status)&&Date.now()<end)await tick();
  assert(!['running','stopping'].includes(ctx.jobs.get(id,owner).status),'owned fixture did not settle');await tick()}
async function ownerFor(id,houdini){
  const notices=[],session=Session.create(id),owner={id,session,status:'idle',ctx:undefined,
    followup:message=>notices.push(message),inject:message=>notices.push(message)};
  const scope=createScope(ctx,owner,houdini?{parent:presetKey}:{});owner.ctx=scope.ctx;
  await ctx.agents.register(owner);return {owner,scope,notices};
}
const selected=await ownerFor('houdini-job-owner',true),other=await ownerFor('standard-job-owner',false);
let ordinal=0,callId=0;
const call=(owner,name,args)=>ctx.tools.execute({name,arguments:args,callId:'fixture-'+(++callId),agent:owner,signal:new AbortController().signal});
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
const execution=()=>({agent:selected.owner,callId:'live-'+(++callId),signal:new AbortController().signal});
async function start(options){const controlled=bridgeFor(options),exec=execution();
  const admitted=await live.submit({code:'owned_fixture()'},exec,controlled.bridge,{sessionId:selected.owner.id,callId:exec.callId});
  return {...controlled,id:admitted.job_id}}
try {
  assert.notEqual(ctx.tools.get('job_output',selected.owner),native,'Houdini receives a scoped thin output definition');
  assert.equal(ctx.tools.get('job_output',other.owner),native,'other modes retain the original definition object');
  const adapted=ctx.tools.get('job_output',selected.owner);
  for(const key of ['execute','projectContent','finalizeContent','presentCall','presentResult'])assert.equal(adapted[key],native[key]);
  assert.equal(adapted.output.schema,native.output.schema);assert.equal(adapted.output.render,native.output.render);
  for(const status of ['done','failed','cancelled']) {
    const running=await start(),before=selected.notices.length;
    const killed=await call(selected.owner,'job_kill',{job_id:running.id});assert.equal(killed.value.outcome,'cancellation-requested');
    running.finish(status);await settled(running.id,selected.owner.id);
    assert.equal(running.cancels(),1);
    assert.equal(ctx.jobs.get(running.id,selected.owner.id).status,status==='done'?'completed':status==='failed'?'failed':'killed');
    assert.equal(selected.notices.length-before,status==='cancelled'?0:1,'only cancellation-lost actual results need the missing notice');
  }
  const immediate=await start({cancelFinishes:true}),beforeImmediate=selected.notices.length;
  await call(selected.owner,'job_kill',{job_id:immediate.id});await settled(immediate.id,selected.owner.id);
  assert.equal(selected.notices.length-beforeImmediate,1,'settlement before the kill tool returns is still delivered once');
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
  assert.deepEqual(result.meta.canonical,result.value);assert.ok(Buffer.byteLength(result.value.text)>16000);
  assert.ok(result.content.every(block=>block.type!=='text'||Buffer.byteLength(block.text)<=16000));
  selected.owner.session.append('tool/result',{turn:1,step:1,message:createToolResultMessage({callId:'large-native',content:result.content,isError:false}),meta:result.meta},{surfaceOp:'append'});
  const cold=JSON.parse(JSON.stringify(selected.owner.session.snapshotEvents()));
  const stored=cold.find(event=>event.type==='tool/result'&&event.data.message.toolCallId==='large-native');
  assert.equal(JSON.parse(stored.data.meta.canonical.text).value.stdout,payload);
  assert.equal(executionResult(stored).value.stdout,payload,'shared history decoder reads the canonical producer envelope');
  assert.equal((await call(selected.owner,'job_output',{job_id:large.id})).value.text,'','preserving metadata never reconsumes a native job');
  const failed=await start(),failure='CheckpointError: failed final output /obj/fixture/OUT';
  failed.finish('failed',payload,{error:failure,outcome:{batch:'failed',operations:{total:100,failed:1}},
    transaction:{status:'rolled_back'},verbs:[{verb:'verify_network',ok:false,error:failure}],
    details:{stored:true,sha256:'c'.repeat(64),path:path.join(root,'fixture-original.json'),format:'returned_bridge_envelope_json'}});
  await settled(failed.id,selected.owner.id);
  const failureRead=await call(selected.owner,'job_output',{job_id:failed.id}),failureText=failureRead.content.map(b=>b.text??'').join('\n');
  assert(Buffer.byteLength(failureText)<=16000);
  for(const fact of [failure,'rolled_back','verify_network',failed.receipt.request_ref,'c'.repeat(64)])assert(failureText.includes(fact),fact);
  assert(!failureText.includes('[result truncated]'),'plugin summary fits the unchanged native finalizer');
  assert.equal(JSON.parse(failureRead.meta.canonical.text).value.stdout,payload);
  // Other job kinds preserve native value and rendering. The output projector
  // uses the legal null sentinel when the native definition has no metadata.
  for(const holder of [selected,other]) {
    const done=deferred(),id=ctx.jobs.start({kind:'bash',label:'Other producer',owner:holder.owner.id,run:()=>({done:done.promise,cancel(){}})});
    done.resolve({status:'completed',result:'plain-other-result'});await settled(id,holder.owner.id);
    const value=await call(holder.owner,'job_output',{job_id:id});assert.equal(value.value.text,'plain-other-result');
    assert.deepEqual(value.content,native.output.render({job_id:id},value.value));
    assert.equal(value.meta,holder===selected?null:undefined);
  }
  const otherDone=deferred(),otherBefore=other.notices.length,otherId=ctx.jobs.start({kind:LIVE_JOB_KIND,label:'Other mode',owner:other.owner.id,
    run:()=>({done:otherDone.promise,cancel(){}})});
  await call(other.owner,'job_kill',{job_id:otherId});otherDone.resolve({status:'completed',result:'other mode owned output'});await settled(otherId,other.owner.id);
  assert.equal(other.notices.length-otherBefore,0,'the plugin never changes another mode cancellation behavior');
  const spillCopies=[];ctx.provide('workingDirectory',{ensure:async()=>root});
  ctx.provide('spillStore',{async saveText(input){spillCopies.push(input.content);return {locator:'fixture:retained',retrievalHint:'Read retained fixture',bytes:Buffer.byteLength(input.content)}}});
  await ctx.plugin(SpillPolicy,{maxInlineTokens:100});
  const nested=await start();nested.finish('done',payload);await settled(nested.id,selected.owner.id);
  ctx.provide('ptcRuntime',{language:'typescript',resolve:request=>request,async run(request){return {value:await request.bindings[0].functions.job_output({job_id:nested.id}),logs:[]}}});
  const releaseMode=selected.owner.ctx.get('tools').presentAs('ptc');
  const nestedResult=await call(selected.owner,'run_code',{code:'return await tools.job_output({job_id:"fixture"})',description:'Read native Houdini job',workingDirectory:root});
  releaseMode();assert.equal(nestedResult.isError,false,JSON.stringify(nestedResult));
  const dispatch=selected.owner.session.snapshotEvents().findLast(event=>event.type==='tool/ptc-dispatch'&&event.data.name==='job_output');
  assert(dispatch,'official PTC records the actual nested dispatch');
  assert.equal(JSON.parse(dispatch.data.meta.canonical.text).value.stdout,payload,'nested durable metadata retains the full producer value');
  assert.ok(spillCopies.length>0,'real native spill policy ran without deleting canonical metadata');
  await preset.dispose();
  assert.equal(ctx.tools.get('job_output',selected.owner),native,'plugin unload removes the scoped definition while keeping the Agent');
  console.log(JSON.stringify({ok:true,runtime,dshVersion:target,checks:['real-native-jobs','cancellation-lost-completed-and-failed','actual-kill-suppressed','early-settlement','waiter-not-duplicated','UI-kill-not-duplicated','native-and-nested-full-metadata','display-retention','single-consumption','other-modes-unchanged','other-job-native-output','plugin-unload']}));
}finally{await ctx.fiber.dispose()}
