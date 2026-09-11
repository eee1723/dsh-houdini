import assert from 'node:assert/strict';
import http from 'node:http';
import {SceneContextProvider, installSceneContext, needsSceneReferent} from '../../lib/context.js';
import {HoudiniBridge} from '../../lib/bridge.js';
import {Session} from '@deepseek-ai/dsh-session';
const SCENE='dsh-houdini:scene-context',STATE='dsh-houdini:execution-state',TASK='dsh-houdini:task-sources',RECOVERY='dsh-houdini:context-recovery';
const user=(id,text)=>({id,role:'user',source:{kind:'user'},content:[{type:'text',text}]});
const data=s=>JSON.parse(s.text.slice(s.text.indexOf('\n')+1));
function agent(){
  const events=[],surface={nodes:[],replaceGeneration:0};
  const a={session:{header:{agentPreset:'houdini'},surface,snapshotEvents:()=>events},events};
  a.append=(type,d,visible=false)=>{const e={type,seq:events.length+1,data:d};events.push(e);if(visible)surface.nodes.push(e.seq);return e;};
  return a;
}
let calls=0,frame=1;
const bridge={async sceneContext(){calls++;return {ok:true,result:{runtime_id:'R',hip_path:'{{scene}}.hip',frame,observed_at:123,selection:[{path:'/obj/selected',type:'box'}]}};}};
const hooks={},registered=[];
installSceneContext({systemPrompt:{context(c){registered.push(c);}},on(name,fn){hooks[name]=fn;}},bridge);
const receive=(a,m)=>{hooks['agent/inbox/inserted']({agent:a,message:m});hooks['agent/inbox/claimed']({agent:a,message:m});};
async function step(a,{message,suppressed=false,reject=false,commit=true,contexts,tools=[{name:'houdini_query'}]}={}){
  if(message)receive(a,message);
  const assembly={contexts:contexts??(suppressed?[]:registered.map(c=>({...c}))),tools},signal=new AbortController().signal;
  await hooks['system-prompt/assemble'](assembly,{scope:{},agent:a,signal},async()=>assembly);
  const result=await hooks['agent/pre-step']({agent:a,signal},async()=>reject?{kind:'reject'}:{kind:'enter',messages:message?[message]:[]});
  if(commit&&result.kind==='enter')for(const m of result.messages)a.append('user/message',m,true);
  return {assembly,result,sections:result.messages?.flatMap(m=>m.source.sections||[])||[]};
}
function record(a,n,{name='houdini_query',ok=true,execution=true,receipt,nodes=[],checks=[],impact={},runtime='R',hip='scene.hip',observed=n}={}){
  const id='call-'+n;a.append('tool/call',{callId:id,name});
  a.append('tool/result',{message:{source:{callId:id},content:[]},meta:{canonical:{ok,transaction:{status:name==='houdini_exec'?'committed':'no_scene_change',nodes},evidence:checks,
    ...(receipt?{requestReceipt:receipt}:{}),...(execution?{execution:{runtime_id:runtime,hip_path:hip,sequence:n,observed_at:observed,frame,
    impact:{attempted:false,nodes:[],...impact},outputs:[]}}:{})}}},true);
}
for(const text of ['你好！','解释 build_module','创建一个程序化轮胎','检查 /obj/geo1/foo','What is a SOP?','继续']){
  assert.equal(needsSceneReferent(user('u',text)),false,text);const before=calls;
  assert.equal((await step(agent(),{message:user('u',text)})).sections.length,0,text);assert.equal(calls,before);
}
for(const text of ['改变选中节点','这个 HDA 为什么报错','inspect this node','当前场景有什么','edit selected'])assert(needsSceneReferent(user('u',text)),text);
const a=agent(),m=user('first','这个 HDA 为什么报错');
const first=await step(a,{message:m});
assert.deepEqual(first.assembly.contexts,[],'supplements are outside the combined Host snapshot');
assert.deepEqual(first.sections.map(s=>s.name),[SCENE]);
assert.equal(data(first.sections[0]).user_message_id,'first');
assert.equal(data(first.sections[0]).observation.result.hip_path,'{{scene}}.hip');
assert(!first.sections[0].text.includes('{{'));
const captured=calls;frame=500;
assert.equal((await step(a)).sections.length,0,'passive frame/selection changes add nothing');assert.equal(calls,captured);
// Failed read, corrected read, further read: no repeated runtime snapshot.
record(a,1,{ok:false});assert.equal((await step(a)).sections.length,0);
record(a,2);assert.equal((await step(a)).sections.length,0);
record(a,3);assert.equal((await step(a)).sections.length,0);assert.equal(calls,captured);
assert.equal((await step(a,{message:user('second','继续排查')})).sections.length,0);
assert.equal((await step(a,{message:user('third','检查 /obj/other')})).sections.length,0);
assert.equal((await step(a,{message:user('fourth','检查现在选中的节点')})).sections.length,1);
// Normal changes/results need no duplicate inventory; dependency invalidation does.
const edit=agent();await step(edit,{message:user('edit','创建一个盒子')});
record(edit,1,{name:'houdini_exec',nodes:[{identity:1,path:'/obj/a',exists:true}],checks:[{ledgerIndex:1,verb:'verify_network',output:'/obj/a',ok:true}],impact:{attempted:true}});
assert.equal((await step(edit)).sections.length,0);
record(edit,2,{name:'houdini_exec',impact:{attempted:true,global:true}});
let notice=await step(edit);assert.deepEqual(notice.sections.map(s=>s.name),[STATE]);
assert.equal(data(notice.sections[0]).checks[0].validity,'stale_after_recorded_change');
assert.equal((await step(edit)).sections.length,0);record(edit,3);assert.equal((await step(edit)).sections.length,0);
const uncertain=agent();await step(uncertain,{message:user('u','创建模块')});
record(uncertain,1,{name:'houdini_exec',execution:false,ok:false,receipt:{request_ref:'ref',status:'unknown',owner_call:'call-1'}});
notice=await step(uncertain);assert.deepEqual(notice.sections.map(s=>s.name),[STATE]);
assert.deepEqual(data(notice.sections[0]).unresolved_requests,[['ref','unknown']]);assert.equal((await step(uncertain)).sections.length,0);
record(uncertain,2,{receipt:{request_ref:'ref',status:'done',owner_call:'call-1'}});
notice=await step(uncertain);assert.equal(data(notice.sections[0]).status,'no_execution_attention');assert.equal((await step(uncertain)).sections.length,0);
record(uncertain,3,{receipt:{request_ref:'ref',status:'unknown',owner_call:'call-1'}});assert.equal((await step(uncertain)).sections.length,0);
const changed=agent();await step(changed,{message:user('u','继续')});record(changed,1);await step(changed);
record(changed,2,{runtime:'NEW',hip:'other.hip'});notice=await step(changed);assert.equal(data(notice.sections[0]).observed_scene_change.runtime_id,'NEW');
record(changed,3,{runtime:'NEW',hip:'other.hip'});assert.equal((await step(changed)).sections.length,0);
record(changed,4,{runtime:'R',observed:1});assert.equal((await step(changed)).sections.length,0,'late observation does not cause a new runtime change');
record(a,4,{name:'houdini_exec',execution:false,ok:false});notice=await step(a);assert.deepEqual(notice.sections.map(s=>s.name),[STATE]);
assert(!notice.sections[0].text.includes('metadata observation'),'attention never repeats the scene snapshot');
// Recovery is tied to a replaced model surface, not every step after compaction.
const recovery=agent();await step(recovery,{message:user('r','保留原要求 {{target}}')});record(recovery,1);await step(recovery);
recovery.session.surface.nodes=[];recovery.session.surface.replaceGeneration=1;
recovery.append('user/message',user('summary','历史摘要'),true).surfaceOp={op:'replace'};
notice=await step(recovery);assert.deepEqual(notice.sections.map(s=>s.name),[TASK,RECOVERY]);
assert.equal(data(notice.sections[0]).sources[0].excerpt,'保留原要求 {{target}}');assert(!notice.sections[0].text.includes('{{'));
assert.equal(data(notice.sections[1]).state.coverage.execution_records,1);assert.equal((await step(recovery)).sections.length,0);
record(recovery,2);assert.equal((await step(recovery)).sections.length,0);
recovery.session.surface.nodes=[];recovery.session.surface.replaceGeneration=2;
recovery.append('user/message',user('summary2','历史摘要'),true).surfaceOp={op:'replace'};
assert.equal((await step(recovery)).sections.length,2);
recovery.append('compaction/prune',{shadowedSeqs:[1]});
recovery.append('tool/result',{message:{source:{callId:'pruned'},content:[]}},true).surfaceOp={op:'replace'};
recovery.session.surface.replaceGeneration++;
assert.equal((await step(recovery)).sections.length,0,'tool-result pruning alone must not recreate the entire recovery context');
// Rejection/failed commit/suppression cannot consume an unlogged candidate.
const rejected=agent();assert.equal((await step(rejected,{message:user('j','这个节点'),reject:true})).result.kind,'reject');
assert.equal((await step(rejected)).sections.length,1);
const notCommitted=agent(),proposed=await step(notCommitted,{message:user('p','这个节点'),commit:false});
assert.equal((await step(notCommitted)).sections[0].text,proposed.sections[0].text);assert.equal((await step(notCommitted)).sections.length,0);
const suppressed=agent();receive(suppressed,user('s','这个节点'));
assert.equal((await step(suppressed,{suppressed:true})).sections.length,0);assert.equal((await step(suppressed,{tools:[]})).sections.length,0);
assert.equal((await step(suppressed)).sections.length,1);
const override=[{name:SCENE,text:'Scoped override'}];assert.deepEqual((await step(agent(),{contexts:override})).assembly.contexts,override);
// A restarted provider reads the original capture; it never samples today's selection for an old message.
const resumedProvider=new SceneContextProvider(bridge),beforeResume=calls;
assert.match(await resumedProvider.observe(a),/fourth/);assert.equal(calls,beforeResume);
const noCapture=agent();noCapture.append('user/message',user('old','这个节点'),true);
assert.equal(await resumedProvider.observe(noCapture),'');assert.equal(calls,beforeResume);
let release,count=0;
const concurrent=new SceneContextProvider({sceneContext(){count++;return new Promise(r=>release=r);}}),ca=agent(),cm=user('c','这个节点');
concurrent.receive(ca,cm);concurrent.claim(ca,cm);const p1=concurrent.observe(ca),p2=concurrent.observe(ca);
release({ok:true,result:{frame:10}});assert.equal(await p1,await p2);assert.equal(count,1);
let failures=0;const down=new SceneContextProvider({async sceneContext(){failures++;throw Error('busy');}});
down.receive(ca,cm);down.claim(ca,cm);assert.match(await down.observe(ca),/unavailable/);await down.observe(ca);assert.equal(failures,1);
const abort=new AbortController();abort.abort();await assert.rejects(down.observe(ca,abort.signal));
let queuedFrame=10;const queue=new SceneContextProvider({async sceneContext(){return {ok:true,result:{frame:queuedFrame}};}});
const qa=user('qa','选中节点'),qb=user('qb','选中节点');queue.receive(ca,qa);queuedFrame=20;queue.receive(ca,qb);queuedFrame=30;
queue.claim(ca,qa);assert.equal(data({text:await queue.observe(ca)}).observation.result.frame,10);
queue.claim(ca,qb);assert.equal(data({text:await queue.observe(ca)}).observation.result.frame,20);
const huge=new SceneContextProvider({async sceneContext(){return {ok:true,result:{selection:[{path:'x'.repeat(10000)}]}};}});
huge.receive(ca,cm);huge.claim(ca,cm);assert((await huge.observe(ca)).length<6700);
const braces=new SceneContextProvider({async sceneContext(){return {ok:true,result:{hip_path:'{'.repeat(3000)}};}});
braces.receive(ca,cm);braces.claim(ca,cm);assert((await braces.observe(ca)).length<6700,'budget includes template escaping');
// Exercise actual DSH surface validation and model-message derivation, not only the hook fixture.
const durable=Session.create('context-injection-regression');
const real={session:durable};
real.append=(type,d,visible=false)=>durable.append(type,d,visible?{surfaceOp:'append'}:undefined);
await step(real,{message:user('real','检查选中节点')});
assert.equal(durable.deriveMessages().length,2);
assert.equal(durable.deriveMessages()[1].source.sections[0].name,SCENE);
assert.equal((await step(real)).sections.length,0);
assert.equal(durable.deriveMessages().length,2,'model input does not accumulate repeated scene context');
durable.append('user/message',{...user('actual-summary','历史摘要'),source:{kind:'plugin',plugin:'compaction'}},
  {surfaceOp:{op:'replace',startSeq:durable.surface.nodes[0],endSeq:durable.surface.nodes.at(-1)},sourceEventSeqs:[...durable.surface.nodes]});
const restored=await step(real);
assert(restored.sections.some(s=>s.name===TASK),'replacement without a compaction marker still recovers a singleton original');
assert.equal((await step(real)).sections.length,0);
let posted;const server=http.createServer((req,res)=>{let body='';req.on('data',c=>body+=c);req.on('end',()=>{
  posted={url:req.url,body:JSON.parse(body)};res.setHeader('content-type','application/json');res.end(JSON.stringify({ok:true,result:{frame:1}}));
});});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
try{const b=new HoudiniBridge(`http://127.0.0.1:${server.address().port}`,120000);assert.equal((await b.sceneContext()).ok,true);assert.deepEqual(posted,{url:'/context',body:{schema_version:1}});}
finally{await new Promise(r=>server.close(r));}
console.log('context injection: referent capture, quiet reads, attention/resolution, recovery, resume, rejection, suppression and HTTP passed');
