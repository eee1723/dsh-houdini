import assert from 'node:assert/strict';
import {Session} from '@deepseek-ai/dsh-session';
import {createUserMessage,createSystemMessage,createAssistantMessage,createToolResultMessage} from '@deepseek-ai/dsh-llm';
import {compactExecutionNotices,MAX_EXECUTION_NOTICES,installSceneContext} from '../../lib/context.js';
const STATE='dsh-houdini:execution-state';
const notice=(n,source={kind:'plugin',plugin:'dsh-houdini',form:'snapshot'})=>{
 const text='Historical execution attention\n'+JSON.stringify({status:'execution_attention',runtime_id:'r',checks:[{identity:n,validity:'stale_after_recorded_change',source_call:'c'+n}],unresolved_requests:[{request_ref:'r.'+n,status:'unknown'}]});
 return createUserMessage({source:{...source,sections:[{name:STATE,text}]},content:[{type:'text',text}]});
};
const isNotice=m=>m.source?.plugin==='dsh-houdini'&&m.source.sections?.length===1&&m.source.sections[0].name===STATE;
const user=text=>createUserMessage({source:{kind:'user'},content:[{type:'text',text}]});
const setup=id=>{const s=Session.create(id);s.append('system/message',{turn:1,step:1,message:createSystemMessage('system must survive','fixture')},{surfaceOp:'append'});s.append('user/message',user('original requirements and authorization'),{surfaceOp:'append'});return s;};
const a=setup('notice-a'),b=setup('notice-b');let maximum=0;
for(let n=1;n<=110;n++)for(const s of [a,b]){
 s.append('step/start',{turn:1,step:n});
 // Real paired call/result messages interleaved with human corrections.
 const id=`${s.id}-${n}`;
 s.append('assistant/message',{turn:1,step:n,stream:[],message:createAssistantMessage({source:{provider:'offline',model:'fixture'},content:[{type:'tool-call',name:'houdini_exec',id,arguments:'{}'}]})},{surfaceOp:'append'});
 s.append('tool/result',{turn:1,step:n,message:createToolResultMessage({callId:id,content:[{type:'text',text:'retained result '+n}],isError:false})},{surfaceOp:'append'});
 if(n%7===0)s.append('user/message',user('user correction '+n),{surfaceOp:'append'});
 const unchanged=JSON.stringify(s.deriveMessages().filter(m=>!isNotice(m)));
 const original=JSON.stringify(s.snapshotEvents());const length=s.snapshotEvents().length;
 compactExecutionNotices(s,true);
 s.append('user/message',notice(n),{surfaceOp:'append'});
 assert.equal(JSON.stringify(s.snapshotEvents().slice(0,length)),original,'original event log is immutable');
 const current=s.deriveMessages(),notices=current.filter(isNotice);
 maximum=Math.max(maximum,notices.length);assert(notices.length<=MAX_EXECUTION_NOTICES);
 assert.equal(JSON.stringify(current.filter(m=>!isNotice(m))),unchanged,'no user, system, call or result moved/deleted');
 assert(notices.at(-1).content[0].text.includes('r.'+n),'latest unresolved receipt preserved');
}
const restored=Session.create('notice-resume',JSON.parse(JSON.stringify(a.snapshotEvents())));
assert.deepEqual(restored.deriveMessages(),a.deriveMessages(),'resume reproduces the same bounded request');
// Mixed or foreign messages never qualify as independent snapshots.
const mixed=notice('mixed');const mixData=createUserMessage({content:[...mixed.content,{type:'text',text:'unrelated instruction'}],source:mixed.source});
a.append('user/message',mixData,{surfaceOp:'append'});a.append('user/message',notice('other',{kind:'plugin',plugin:'other-plugin',form:'snapshot'}),{surfaceOp:'append'});
for(let n=0;n<8;n++)a.append('user/message',notice(n+1000),{surfaceOp:'append'});
const originalOthers=JSON.stringify(a.deriveMessages().filter(m=>m===mixData||m.source?.plugin==='other-plugin'));
compactExecutionNotices(a,true);
assert.equal(JSON.stringify(a.deriveMessages().filter(m=>m===mixData||m.source?.plugin==='other-plugin')),originalOthers);
// Never remove a notice while any tool result is outstanding.
const pending=setup('pending');pending.append('step/start',{turn:1,step:1});for(let n=0;n<8;n++)pending.append('user/message',notice(n),{surfaceOp:'append'});
pending.append('assistant/message',{turn:1,step:1,stream:[],message:createAssistantMessage({source:{provider:'offline',model:'fixture'},content:[{type:'tool-call',name:'houdini_exec',id:'pending',arguments:'{}'}]})},{surfaceOp:'append'});
const pendingBefore=JSON.stringify(pending.snapshotEvents());assert.equal(compactExecutionNotices(pending,true),0);assert.equal(JSON.stringify(pending.snapshotEvents()),pendingBefore);
// Hook rejects/cancellation do not prune; self-compaction does not cause recovery injection.
const hooks={},contexts=[];
installSceneContext({systemPrompt:{context:c=>contexts.push(c)},get:()=>({flush:async()=>true}),on:(name,fn)=>hooks[name]=fn},{sceneContext:async()=>{throw Error('no passive scene read');}});
const view={session:restored};const signal=new AbortController().signal;
let assembly={contexts:contexts.map(c=>({...c})),tools:[{name:'houdini_query'}]};
await hooks['system-prompt/assemble'](assembly,{scope:{},agent:view,signal},async()=>assembly);
const beforeReject=JSON.stringify(restored.snapshotEvents());await hooks['agent/pre-step']({agent:view,signal},async()=>({kind:'reject'}));assert.equal(JSON.stringify(restored.snapshotEvents()),beforeReject);
const entered=await hooks['agent/pre-step']({agent:view,signal},async()=>({kind:'enter',messages:[]}));
assert(!entered.messages.some(m=>m.source.sections?.some(s=>s.name==='dsh-houdini:context-recovery')),'own tombstones must not trigger full recovery loops');
console.log(`native Session notices bounded at ${maximum}; 220 changes, immutable history, paired messages, two sessions, resume and exclusions passed`);

// Durability acknowledgement must survive retries with zero new replacements.
function durabilityHarness(failures,seed,partial=false) {
 const base=seed?Session.create('durability-resume',seed):setup('durability');
 if(!seed){
  base.append('assistant/message',{turn:1,step:1,stream:[],message:createAssistantMessage({source:{provider:'offline',model:'fixture'},content:[{type:'tool-call',id:'lost',name:'houdini_exec',arguments:'{}'}]})},{surfaceOp:'append'});
  base.append('tool/call',{turn:1,step:1,callId:'lost',name:'houdini_exec',arguments:'{}'});
  base.append('tool/result',{turn:1,step:1,message:createToolResultMessage({callId:'lost',content:[{type:'text',text:'transport unknown'}],isError:true}),meta:{canonical:{ok:false,error:'transport unknown',requestReceipt:{request_ref:'a'.repeat(32)+'.'+'b'.repeat(32),status:'unknown'}}}},{surfaceOp:'append'});
  for(let i=0;i<5;i++)base.append('user/message',notice(i),{surfaceOp:'append'});
 }
 base.append('step/start',{turn:1,step:2});
 let interrupted=false;
 const session=partial?new Proxy(base,{get(target,name){
  if(name==='append')return (...args)=>{const e=target.append(...args);if(!interrupted&&args[0]==='system/message'){interrupted=true;throw Error('injected partial compaction')}return e};
  const value=Reflect.get(target,name);return typeof value==='function'?value.bind(target):value;
 }}):base;
 let calls=0,requests=0;const hooks={},contexts=[];
 installSceneContext({get:()=>({flush:async()=>{const outcome=failures[calls++]??true;if(outcome==='throw')throw Error('injected flush failure');return outcome}}),on:(n,f)=>hooks[n]=f,systemPrompt:{context:c=>contexts.push(c)}},{sceneContext:async()=>{throw Error('no passive observation')}});
 return {base,get calls(){return calls},get requests(){return requests},async enter({suppressed=false,aborted=false}={}){
  const agent={session};const controller=new AbortController();if(aborted)controller.abort();
  const signal=controller.signal,assembly={contexts:suppressed?[]:contexts.map(c=>({...c})),tools:[{name:'houdini_query'}]};
  await hooks['system-prompt/assemble'](assembly,{agent,scope:{},signal},async()=>assembly);
  const decision=await hooks['agent/pre-step']({agent,signal},async()=>({kind:'enter',messages:[]}));
  for(const m of decision.messages)base.append('user/message',m,{surfaceOp:'append'});
  requests++;return base.deriveMessages();
 }};
}
const failing=durabilityHarness([false,false,true]);
await assert.rejects(failing.enter(),/not durable/);
const firstTombstones=failing.base.snapshotEvents().filter(e=>e.type==='system/message'&&e.data.message.source.plugin==='dsh-houdini:attention-compaction').length;
await assert.rejects(failing.enter({suppressed:true}),/not durable/);
assert.equal(failing.requests,0);assert.equal(failing.calls,2);
assert.equal(failing.base.snapshotEvents().filter(e=>e.type==='system/message'&&e.data.message.source.plugin==='dsh-houdini:attention-compaction').length,firstTombstones);
const enteredAfterRecovery=await failing.enter();assert.equal(failing.requests,1);
assert(enteredAfterRecovery.some(m=>isNotice(m)&&m.content[0].text.includes('b'.repeat(32))),'uncertain request reference survives durability retry');
const thrown=durabilityHarness(['throw',true]);await assert.rejects(thrown.enter(),/injected flush/);assert.equal(thrown.requests,0);await thrown.enter();assert.equal(thrown.requests,1);
const interrupted=durabilityHarness([false,true],undefined,true);await assert.rejects(interrupted.enter(),/partial compaction/);await assert.rejects(interrupted.enter(),/not durable/);assert.equal(interrupted.requests,0);await interrupted.enter();assert.equal(interrupted.requests,1);
const paused=durabilityHarness([false,true]);await assert.rejects(paused.enter(),/not durable/);await assert.rejects(paused.enter({aborted:true}));assert.equal(paused.calls,1);await paused.enter();
const seedFailure=durabilityHarness([false]);await assert.rejects(seedFailure.enter(),/not durable/);
const resumed=durabilityHarness([false,true],JSON.parse(JSON.stringify(seedFailure.base.snapshotEvents())));await assert.rejects(resumed.enter({suppressed:true}),/not durable/);await resumed.enter();
assert.equal(resumed.requests,1);assert.equal(seedFailure.requests,0,'durability state does not cross sessions');
console.log('persistent false/throw barriers, suppression, partial replacement, cancellation, resume and session isolation passed');
