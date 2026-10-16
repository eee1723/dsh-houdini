import assert from 'node:assert/strict'
import {Session} from '@deepseek-ai/dsh-session'
import {createUserMessage,createToolResultMessage} from '@deepseek-ai/dsh-llm'
import {supportOptions,supportPayload,supportEvent} from '../../lib/support-report.js'
import {ExecutorBinding} from '../../lib/executor-binding.js'
import {houdiniSnapshot} from '../../lib/dsh-adapter.js'

const options={sessionId:'chosen-task',description:'restart then continue',includeContent:false,includeLogs:true,includePrevious:true}
for(const bad of [{...options,path:'C:/secret'}, {...options,includeContent:'true'}, {...options,sessionId:''},
  {...options,description:'x'.repeat(4001)},null,[]])assert.throws(()=>supportOptions(bad))
const selected=Session.create(options.sessionId),other=Session.create('unrelated-task')
selected.append('user/message',createUserMessage({content:[{type:'text',text:'PRIVATE_CHAT_SENTINEL'}]}),{surfaceOp:'append'})
await new ExecutorBinding().ensure(selected,'a'.repeat(32))
selected.append('user/message',houdiniSnapshot({name:'dsh-houdini:recovery-required',text:'diagnostic\n'+JSON.stringify({
  executor_id:'b'.repeat(32),reason:'checkpoint unavailable; token=TOP_SECRET_TOKEN'})}),{surfaceOp:'append'})
selected.append('tool/call',{callId:'readonly',name:'houdini_inspect',arguments:'PRIVATE_TOOL_CODE_SENTINEL'})
selected.append('tool/result',{message:createToolResultMessage({callId:'readonly',isError:true,content:[{type:'text',text:'recorded executor differs'}]})},{surfaceOp:'append'})
other.append('user/message',createUserMessage({content:[{type:'text',text:'WRONG_TASK_SENTINEL'}]}),{surfaceOp:'append'})
let closed=0,flushes=0,reads=0,corrupt=false,mismatch=false,countAvailable=true
const ctx={get(name){
  if(name==='sessions')return {get:id=>id===selected.id?selected:undefined,flush:async()=>{flushes++;return true}}
  if(name==='sessionPersistence')return {
    stat:async id=>({header:selected.header,...(countAvailable?{eventCount:selected.snapshotEvents().length}:{})}),
    open:async(id,access)=>{
      assert.equal(id,selected.id);assert.equal(access,'read')
      return {header:mismatch?other.header:selected.header,close:async()=>{closed++},read:async(offset,length)=>{
        reads++;if(corrupt)throw Error('corrupt fixture');return {events:selected.snapshotEvents().slice(offset,offset+length)}
      }}
    }
  }
  throw Error('No live, recovery, agent-start or model services allowed: '+name)
}}
const signal=new AbortController().signal
const payload=await supportPayload(ctx,options,signal)
const encoded=JSON.stringify(payload)
assert(!encoded.includes('PRIVATE_CHAT_SENTINEL'))
assert(!encoded.includes('PRIVATE_TOOL_CODE_SENTINEL'))
assert(!encoded.includes('WRONG_TASK_SENTINEL'))
assert(encoded.includes('checkpoint unavailable'))
assert(encoded.includes('recorded executor differs'))
assert.equal(payload.session.id,selected.id)
assert.equal(closed,1);assert.equal(flushes,1)
const full=await supportPayload(ctx,{...options,includeContent:true},signal)
assert(JSON.stringify(full).includes('PRIVATE_CHAT_SENTINEL'))
assert(!JSON.stringify(full).includes('WRONG_TASK_SENTINEL'))
corrupt=true
await assert.rejects(supportPayload(ctx,options,signal),/corrupt/)
assert.equal(closed,3)
corrupt=false;mismatch=true
await assert.rejects(supportPayload(ctx,options,signal),/身份不一致/)
assert.equal(closed,4)
mismatch=false
await assert.rejects(supportPayload(ctx,options,AbortSignal.abort()),/abort/i)
assert.equal(closed,4)
assert.equal(supportEvent({type:'user/message',data:{source:{kind:'user'},content:[{type:'text',text:'PRIVATE'}]}}),null)
assert.equal(supportEvent({type:'tool/ptc-dispatch',seq:99,data:{name:'houdini_exec',subCallId:'nested',isError:false,
  content:[{type:'text',text:JSON.stringify({kind:'dsh-houdini/execution-v1',callId:'nested',tool:'houdini_exec',
  value:{ok:false,error:'nested failed',result:{private:'PRIVATE_RESULT'},execution:{executor_id:'a'.repeat(32)}}})}]}}).outcome.error,'nested failed')
for(let index=0;index<2100;index++)selected.append('tool/call',{callId:'volume-'+index,name:'houdini_inspect',arguments:'private'})
selected.append('tool/result',{message:createToolResultMessage({callId:'volume-2099',isError:true,content:[{type:'text',text:'LATEST_FAILURE'}]})},{surfaceOp:'append'})
const large=await supportPayload(ctx,options,signal)
assert(large.missing.includes('history_middle_omitted'))
assert(JSON.stringify(large).includes('LATEST_FAILURE'))
assert(JSON.stringify(large).includes('executor_binding'))
countAvailable=false
const discovered=await supportPayload(ctx,options,signal)
assert.equal(discovered.session.total_events,selected.snapshotEvents().length)
assert(JSON.stringify(discovered).includes('LATEST_FAILURE'),'backends without eventCount must still export the latest failure')
assert.equal(new Set(discovered.timeline.map(event=>event.seq)).size,discovered.timeline.length)
console.log('support report: exact session, native messages, nested results, opt-in content, corruption, cancellation and bounded history passed')
