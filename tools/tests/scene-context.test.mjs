import assert from 'node:assert/strict';
import http from 'node:http';
import { SceneContextProvider, installSceneContext } from '../../lib/context.js';
import { HoudiniBridge } from '../../lib/bridge.js';

let calls = 0;
const bridge = { observationGeneration: 0, async sceneContext() {
  calls++;
  return {ok:true,result:{hip_path:'{{scene}}.hip', frame:1, observed_at:123}};
}};
function agent(text, seq=1) {
  const events=[{type:'user/message',seq,data:{source:{kind:'user'},content:[{type:'text',text}]}}];
  return {session:{header:{agentPreset:'houdini'},snapshotEvents:()=>events},events};
}
const p=new SceneContextProvider(bridge);
assert.equal(await p.observe(agent('你好！')), '');
assert.equal(calls,0);
const a=agent('改变选中节点');
const first=await p.observe(a);
assert.match(first,/houdini/);
assert.equal(first.includes('{{'),false,'scene data must not become prompt template variables');
assert.equal(JSON.parse(first.split('\n').slice(1).join('\n')).observation.result.hip_path,'{{scene}}.hip',
  'JSON string data roundtrips while nested structural braces stay valid');
assert.equal(await p.observe(a),first);
assert.equal(calls,1,'same assembly state is reused');
bridge.observationGeneration++;
await p.observe(a);
assert.equal(calls,1,'edits never refresh a user-message snapshot');
await p.observe(agent('改变选中节点'));
assert.equal(calls,2,'separate sessions cannot share cached selection');
a.events.push({type:'user/message',seq:2,data:{source:{kind:'user'},content:[{type:'text',text:'现在选中了另一个'}]}});
await p.observe(a);
assert.equal(calls,3);
const down=new SceneContextProvider({observationGeneration:0,async sceneContext(){throw Error('busy');}});
assert.match(await down.observe(agent('建模')),/unavailable/);
const abort=new AbortController();abort.abort();
await assert.rejects(down.observe(agent('建模'),abort.signal));
let hook, claimed, inserted;
installSceneContext({systemPrompt:{context(c){assert.equal(c.text,'');}},on(event,fn){
  if(event==='system-prompt/assemble')hook=fn;
  else if(event==='agent/inbox/claimed')claimed=fn;
  else if(event==='agent/inbox/inserted')inserted=fn;
  else assert.fail(event);
}},bridge);
const assembly={contexts:[{name:'dsh-houdini:scene-context',text:''}],tools:[{name:'houdini_query'}]};
await hook(assembly,{scope:{},agent:a},async()=>assembly);
assert.equal(assembly.contexts.length,1);
assert.match(assembly.contexts[0].text,/metadata observation/);
const countBeforeSuppression=calls;
const suppressed={contexts:[],tools:[{name:'houdini_query'}]};
await hook(suppressed,{scope:{},agent:agent('new suppressed task')},async()=>suppressed);
assert.equal(calls,countBeforeSuppression,'suppressed runtime contexts must not trigger HTTP');
const entering=agent('unused');entering.events.length=0;
claimed({agent:entering,message:{id:'first',source:{kind:'user'},content:[{type:'text',text:'Create geometry'}]}});
const firstAssembly={contexts:[{name:'dsh-houdini:scene-context',text:''}],tools:[{name:'houdini_query'}]};
await hook(firstAssembly,{scope:{},agent:entering},async()=>firstAssembly);
assert.match(firstAssembly.contexts[0].text,/metadata observation/,'first assembly sees claimed user before user/message is logged');
let sample=0, frame=1;
const changing={observationGeneration:0,async sceneContext(){return {ok:true,result:{observed_at:++sample,elapsed_ms:sample/10,frame,panes:[{current:{path:'/obj'}}]}};}};
const stableProvider=new SceneContextProvider(changing),stableAgent=agent('model');
const stableText=await stableProvider.observe(stableAgent);
changing.observationGeneration++;
assert.equal(await stableProvider.observe(stableAgent),stableText,'timestamp-only re-observation must not inject another snapshot');
frame=2;changing.observationGeneration++;
assert.equal(await stableProvider.observe(stableAgent),stableText,'later frame/selection changes must not rewrite the user referent');
const realNow=Date.now;
try {
  Date.now=()=>realNow()+3600000;
  assert.equal(await stableProvider.observe(stableAgent),stableText,'elapsed time never triggers capture');
  assert.equal(sample,1);
} finally { Date.now=realNow; }
stableProvider.claim(stableAgent,{id:'next-user',source:{kind:'user'},content:[{type:'text',text:'Inspect again'}]});
assert.equal(JSON.parse((await stableProvider.observe(stableAgent)).split('\n').slice(1).join('\n')).observation.result.observed_at,2,
  'new user message gets a fresh observation even if facts are unchanged');
const receivedAgent=agent('unused');receivedAgent.events.length=0;
const received={id:'received-before-claim',source:{kind:'user'},content:[{type:'text',text:'edit this'}]};
const beforeReceipt=calls;
inserted({agent:receivedAgent,message:received});
assert.equal(calls,beforeReceipt+1,'capture starts at inbox receipt, not after model reasoning');
claimed({agent:receivedAgent,message:received});
const receiptAssembly={contexts:[{name:'dsh-houdini:scene-context',text:''}],tools:[{name:'houdini_query'}]};
await hook(receiptAssembly,{scope:{},agent:receivedAgent},async()=>receiptAssembly);
assert.equal(calls,beforeReceipt+1,'claim and assembly reuse the receipt capture');
const binding=JSON.parse(receiptAssembly.contexts[0].text.split('\n').slice(1).join('\n'));
assert.equal(binding.user_message_id,received.id);
assert.equal(typeof binding.capture_requested_at,'number');
let failures=0;
const failed=new SceneContextProvider({async sceneContext(){failures++;throw Error('unavailable');}});
const failedAgent=agent('inspect');
await failed.observe(failedAgent);await failed.observe(failedAgent);
assert.equal(failures,1,'failed captures are not retried automatically within a message');
let release;
const concurrent=new SceneContextProvider({sceneContext:()=>new Promise(r=>{release=r;})});
const concurrentAgent=agent('inspect');
const pending1=concurrent.observe(concurrentAgent),pending2=concurrent.observe(concurrentAgent);
release({ok:true,result:{frame:1}});
assert.equal(await pending1,await pending2,'concurrent assemblies share one in-flight capture');
let queuedFrame=10;
const queuedProvider=new SceneContextProvider({async sceneContext(){return {ok:true,result:{frame:queuedFrame}};}});
const queuedAgent=agent('unused');queuedAgent.events.length=0;
const qa={id:'queued-a',source:{kind:'user'},content:[{type:'text',text:'edit selected'}]};
const qb={...qa,id:'queued-b'};
queuedProvider.receive(queuedAgent,qa);
queuedFrame=20;queuedProvider.receive(queuedAgent,qb);
queuedFrame=30;
queuedProvider.claim(queuedAgent,qa);
assert.equal(JSON.parse((await queuedProvider.observe(queuedAgent)).split('\n').slice(1).join('\n')).observation.result.frame,10);
queuedProvider.claim(queuedAgent,qb);
assert.equal(JSON.parse((await queuedProvider.observe(queuedAgent)).split('\n').slice(1).join('\n')).observation.result.frame,20,
  'queued messages retain separate receipt snapshots, not later claim-time selections');
const huge=new SceneContextProvider({observationGeneration:0,async sceneContext(){return {ok:true,result:{selection:[{path:'x'.repeat(10000),type:'box'}]}};}});
assert((await huge.observe(agent('inspect huge selection'))).length<6500);

let posted;
const server=http.createServer((req,res)=>{
  let body='';req.on('data',c=>body+=c);req.on('end',()=>{
    posted={url:req.url,body:JSON.parse(body)};
    res.setHeader('content-type','application/json');res.end(JSON.stringify({ok:true,result:{frame:1}}));
  });
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
try {
  const b=new HoudiniBridge(`http://127.0.0.1:${server.address().port}`,120000);
  assert.equal((await b.sceneContext()).ok,true);
  assert.deepEqual(posted,{url:'/context',body:{schema_version:1}});
} finally { await new Promise(r=>server.close(r)); }
console.log('scene context: user-turn refresh, per-agent isolation, failure, assembly and HTTP passed');
// Per-request execution facts do not refresh the message-bound user referent.
const observedAgent=agent('edit selected');
observedAgent.events.push({type:'tool/call',seq:2,data:{callId:'observed',name:'houdini_exec'}},
  {type:'tool/result',seq:3,data:{message:{source:{callId:'observed'},content:[]},meta:{canonical:{
    ok:true,transaction:{status:'committed',nodes:[{identity:1,path:'/obj/{{not_instructions}}',exists:true}]},
    execution:{runtime_id:'runtime',sequence:1,observed_at:1,impact:{attempted:false,nodes:[]}}}}}});
const stateOnly={contexts:[{name:'dsh-houdini:execution-state',text:''}],tools:[{name:'houdini_query'}]};
const beforeState=calls;
await hook(stateOnly,{scope:{},agent:observedAgent},async()=>stateOnly);
assert.equal(calls,beforeState,'execution-state projection does not issue HTTP or update the user-message snapshot');
assert.ok(!stateOnly.contexts[0].text.includes('{{'));
assert.equal(JSON.parse(stateOnly.contexts[0].text.split('\n').slice(1).join('\n')).nodes[0].path,'/obj/{{not_instructions}}');
