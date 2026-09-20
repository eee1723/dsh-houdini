import assert from 'node:assert/strict';
import {Session,foldSurface,deriveEventMessage} from '@deepseek-ai/dsh-session';
import {createSystemMessage,createUserMessage,createAssistantMessage,createToolResultMessage} from '@deepseek-ai/dsh-llm';
import {collectRequestContexts,collectRequestTelemetry} from '../trace-session-lib.mjs';
const s=Session.create('context-audit');
const sys=(text,intent={surfaceOp:'append'})=>s.append('system/message',{turn:1,step:1,message:createSystemMessage(text,'fixture')},intent);
const response=step=>s.append('assistant/message',{turn:1,step,usage:{inputTokens:2,cacheReadTokens:4,outputTokens:3,reasoningTokens:2,totalTokens:9},stream:[{ignored:'not model input'.repeat(100)}],message:createAssistantMessage({source:{provider:'fixture',model:'fixture'},content:[{type:'text',text:'response'},{type:'reasoning',text:'fixture reasoning'}]})},{surfaceOp:'append'});
const head=sys('You are a Houdini automation agent. render_view');
s.append('request/header',{header:{config:{model:'fixture'},tools:[{name:'houdini_exec'}]}});
response(1);
// No new header: replacement must still change the next request's effective system.
sys('New policy requires inspection.',{surfaceOp:{op:'replace',startSeq:head.seq,endSeq:head.seq},sourceEventSeqs:[head.seq]});
response(2);
const notice=s.append('user/message',createUserMessage({source:{kind:'plugin',plugin:'test'},content:[{type:'text',text:'obsolete notice'}]}),{surfaceOp:'append'});
sys('',{surfaceOp:{op:'replace',startSeq:notice.seq,endSeq:notice.seq},sourceEventSeqs:[notice.seq]});
response(3);
const all=s.snapshotEvents(),rows=collectRequestContexts(all,{includeSystemText:true});
assert.deepEqual(collectRequestContexts([{type:'session',data:{format:3}},...all],{includeSystemText:true}),rows,
  'JSONL file header has no event sequence and is not a missing-history signal');
assert.equal(rows.length,3);assert.equal(rows[0].systemText,'You are a Houdini automation agent. render_view');assert.equal(rows[1].systemText,'New policy requires inspection.');assert.equal(rows[2].systemText,rows[1].systemText);
for(const row of rows){
  const prefix=all.filter(e=>e.seq<row.seq);const nodes=foldSurface(prefix).nodes;
  const actual=nodes.map(n=>deriveEventMessage(prefix[n])).filter(Boolean);
  const system=actual.filter(m=>m.role==='system').flatMap(m=>m.content.filter(c=>c.type==='text').map(c=>c.text)).join('\n');
  assert.equal(row.systemChars,system.length);assert.equal(row.systemText,system);
  assert(!JSON.stringify(row).includes('not model input'));
}
assert.equal(rows[2].charactersByKind.plugin,0,'non-emitting tombstone removes obsolete text');
const usage=collectRequestTelemetry(all);assert.equal(usage.totals.totalTokens,27);assert.equal(usage.totals.reasoningTokens,6);assert.equal(usage.totals.outputTokens,9);
const legacy=collectRequestContexts([{seq:0,type:'request/header',data:{header:{system:'legacy',tools:[]}}},{seq:1,type:'assistant/message',data:{message:{role:'assistant',content:[]}}}],{includeSystemText:true});assert.equal(legacy[0].systemText,'legacy');
const incomplete=[...all.slice(0,3),{type:'system/message',seq:3,data:{message:createSystemMessage('bad','fixture')},surfaceOp:{op:'replace',startSeq:999,endSeq:999},sourceEventSeqs:[999]},{type:'assistant/message',seq:4,data:{turn:2,step:1,message:{content:[]}}}];
assert.equal(collectRequestContexts(incomplete).at(-1).projectionComplete,false);assert.equal(collectRequestContexts(incomplete).at(-1).systemChars,null);
for(const variant of ['missing-marker','missing-sources','wrong-sources']) {
 const bad=structuredClone(all);
 if(variant==='missing-marker')delete bad[0].surfaceOp;
 else {
  const replacement=bad.find(e=>typeof e.surfaceOp==='object');
  if(variant==='missing-sources')delete replacement.sourceEventSeqs;
  else replacement.sourceEventSeqs=[1];
 }
 assert.throws(()=>foldSurface(bad),undefined,variant+' must be rejected by the native oracle');
 const rejected=collectRequestContexts(bad).at(-1);
 assert.equal(rejected.projectionComplete,false,variant);
 assert.equal(rejected.systemChars,null,variant);
 assert(rejected.projectionError,variant+' needs an explicit unknown reason');
}
const crossing=Session.create('crossing-replacement');
crossing.append('system/message',{turn:1,step:1,message:createSystemMessage('system','fixture')},{surfaceOp:'append'});
const u=crossing.append('user/message',createUserMessage({source:{kind:'user'},content:[{type:'text',text:'preserve'}]}),{surfaceOp:'append'});
crossing.append('assistant/message',{turn:1,step:1,stream:[],message:createAssistantMessage({source:{provider:'fixture',model:'fixture'},content:[{type:'tool-call',id:'c',name:'houdini_query',arguments:'{}'}]})},{surfaceOp:'append'});
const tool=crossing.append('tool/result',{turn:1,step:1,message:createToolResultMessage({callId:'c',content:[{type:'text',text:'result'}],isError:false})},{surfaceOp:'append'});
const crossLog=[...crossing.snapshotEvents(),{...structuredClone(tool),seq:4,surfaceOp:{op:'replace',startSeq:u.seq,endSeq:tool.seq},sourceEventSeqs:[1,2,3]},
 {type:'assistant/message',seq:5,time:1,data:{turn:1,step:2,stream:[],message:createAssistantMessage({source:{provider:'fixture',model:'fixture'},content:[{type:'text',text:'next'}]})},surfaceOp:'append'}];
assert.throws(()=>foldSurface(crossLog),/exactly one/);
assert.equal(collectRequestContexts(crossLog).at(-1).projectionComplete,false);
const allMarkersMissing=structuredClone(all).map(e=>{delete e.surfaceOp;return e});
assert.equal(collectRequestContexts([{type:'session',version:3},...allMarkersMissing]).at(-1).projectionComplete,false,
  'declared V3 cannot fall back to legacy when every marker is missing');
const badHead=[...crossing.snapshotEvents(),{type:'user/message',seq:4,time:1,data:createUserMessage({source:{kind:'plugin',plugin:'fixture'},content:[{type:'text',text:'illegal replacement'}]}),surfaceOp:{op:'replace',startSeq:0,endSeq:0},sourceEventSeqs:[0]},crossLog.at(-1)];
assert.throws(()=>foldSurface(badHead),/system prompt/);assert.equal(collectRequestContexts(badHead).at(-1).projectionComplete,false);
const badMetadata=[...crossing.snapshotEvents(),{...structuredClone(tool),seq:4,data:{...structuredClone(tool.data),meta:{extra:'changed outside content'}},surfaceOp:{op:'replace',startSeq:3,endSeq:3},sourceEventSeqs:[3]},crossLog.at(-1)];
assert.throws(()=>foldSurface(badMetadata),/only content/);assert.equal(collectRequestContexts(badMetadata).at(-1).projectionComplete,false);
console.log('V3 request-prefix system replacements/tombstones, legacy compatibility and disjoint usage passed');
