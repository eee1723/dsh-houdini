// Regression: the scene observation must stay bounded in real DSH history.
//
// DSH materializes registered prompt contexts as durable runtime-context
// snapshots and skips a snapshot whose text equals the retained one. A summary
// containing a live-computed field (for example an elapsed age) therefore makes
// every model step append another snapshot (see review evidence: 8 steps ->
// 8 snapshots / 4,921 chars). The provider must emit at most one full
// observation and then one byte-stable historical summary per user message.
//
// This exercises the real AgentLoop/SystemPrompt/RuntimeContextProjection from
// installed DSH packages with a fixture LLM and a fixture Bridge; it wires the
// same section/hook shape as src/context.ts so only provider text is measured.
import {SessionStore} from '@deepseek-ai/dsh-session'
import {Context} from '@deepseek-ai/cordis'
import {SystemPrompt} from '@deepseek-ai/dsh-system-prompt'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import {AgentRegistry} from '@deepseek-ai/dsh-agent'
import ToolsService from '@deepseek-ai/dsh-tools'
import {NativeToolExecutor} from '@deepseek-ai/dsh-tool-executor-native'
import {LlmRuntime,LlmAdapter} from '@deepseek-ai/dsh-llm'
import assert from 'node:assert/strict'
import {SceneContextProvider} from '../../lib/scene-context.js'
import {projectedExecutorState} from '../../lib/executor-identity-projection.js'
import {fixtureProjectionContext} from './fixture-session.mjs'

const SCENE='dsh-houdini:scene-context'
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))
const user=(id,text)=>({id,role:'user',content:[{type:'text',text}],source:{kind:'user'}})
const steer=(id)=>({id,role:'user',content:[{type:'text',text:'continue'}],source:{kind:'dsh-houdini'}})
const sceneSnapshots=(events)=>{
  const rows=[]
  for(const event of events){
    if(event.type!=='user/message')continue
    const message=event.data?.message??event.data
    const section=(message?.source?.sections??[]).find(item=>item.name===SCENE)
    if(!section)continue
    let parsed=null
    try{parsed=JSON.parse(section.text.slice(section.text.indexOf('\n')+1))}catch{}
    rows.push({text:section.text,historical:parsed?.historical,userMessageId:parsed?.user_message_id,
      age:parsed?.age_seconds,hip:parsed?.observation?.result?.hip_path})
  }
  return rows
}

async function run(){
  const ctx=new Context()
  new SessionStore(ctx)
  await fixtureProjectionContext(ctx)
  new SystemPrompt(ctx,{})
  const tools=new ToolsService(ctx,{})
  tools.setExecutor(new NativeToolExecutor(ctx))
  const llm=new LlmRuntime(ctx)
  let captures=0
  const bridge={async sceneContext(){captures++;return {ok:true,result:{frame:1,version:'22.0.368',
    hip_path:'E:/fixture/a.hip',hip_is_new:false,hip_dir:'E:/fixture',has_named_path:true,
    has_unsaved_changes:false,update_mode:'auto',selection:[{path:'/obj/A',type:'geo',needs_cook:false}],
    selection_count:1,selected_editor_items:[{type:'sticky_note',parent:'/obj',name:'NOTES'}],
    selected_editor_items_count:1}}}}
  const provider=new SceneContextProvider(bridge,agent=>projectedExecutorState(ctx,agent.session).sceneObservation)
  ctx.on('agent/inbox/inserted',({agent,message})=>provider.receive(agent,message))
  ctx.on('agent/inbox/claimed',({agent,message})=>provider.claim(agent,message))
  ctx.on('agent/inbox/discarded',({agent,message})=>provider.discard(agent,message))
  const prepared=new WeakMap()
  ctx.systemPrompt.context({name:SCENE,order:150,text:context=>{
    const agent=context.agent
    return agent?prepared.get(agent)??'':''
  }})
  ctx.on('system-prompt/assemble',async(_assembly,context,next)=>{
    const result=await next()
    const agent=context.agent
    if(!agent||!context.scope)return result
    const previous=prepared.get(agent)??''
    const section=result.contexts.find(item=>item.name===SCENE&&item.text===previous)
    if(!section)return result
    section.text=await provider.observe(agent,context.signal)
    prepared.set(agent,section.text)
    return result
  },{prepend:true})
  let steps=0
  let handle
  class Adapter extends LlmAdapter {
    async listModels(){return [{provider:'fixture',id:'fixture-model',name:'fixture'}]}
    async resolveModel(route,id){return {provider:route,id,name:'fixture',inputModalities:['text'],
      context:{contextWindow:500000}}}
    async *stream(options){
      steps++
      const current=steps
      // One steer per step keeps the same user turn alive without a new claim.
      if(current<6)handle.agent.steer(steer('steer-'+current))
      await sleep(120)
      yield {type:'block-start',index:0,blockType:'text'}
      yield {type:'block-end',index:0,block:{type:'text',text:'step '+current}}
      yield {type:'finish',reason:{kind:'stop'}}
    }
  }
  llm.registerAdapter(['fixture'],new Adapter())
  await ctx.plugin(AgentRegistry).await()
  await ctx.plugin(AgentLoop,{agents:[]}).await()
  try{
    handle=await ctx.agents.create({sessionId:'scene-snapshot-budget',
      agentOptions:{provider:'fixture',model:'fixture-model'}})
    handle.agent.followup(user('u1','do the task'))
    await handle.agent.whenIdle()
    await sleep(150)
    const first=sceneSnapshots(handle.agent.session.snapshotEvents())
    assert.equal(captures,1,'one observation is captured per received user message')
    assert(first.length>=1&&first.length<=2,`one user turn must keep at most one full + one summary, got ${first.length}`)
    assert.equal(first[0].historical,undefined,'the first materialized snapshot carries the full observation')
    assert.match(first[0].text,/Houdini metadata observation\./u)
    if(first.length>1){
      assert.equal(first[1].historical,true,'later snapshots carry the historical summary')
      assert.match(first[1].text,/NOT current scene state/u)
      assert.equal(first[1].age,undefined,'the summary must not carry a live-computed age (snapshot stability)')
      assert.equal(first[1].text,first[first.length-1].text,
        'every later snapshot for the same observation must be byte-identical')
      assert(first[1].text.length<1200,`historical summary stays bounded, got ${first[1].text.length}`)
    }
    const total=first.reduce((sum,row)=>sum+row.text.length,0)
    assert(total<6000,`per-turn scene context stays bounded, got ${total}`)

    // A second human message must receive its own full observation even though
    // the first one was already persisted and summarized.
    handle.agent.followup(user('u2','second request'))
    await handle.agent.whenIdle()
    await sleep(150)
    const second=sceneSnapshots(handle.agent.session.snapshotEvents())
    assert.equal(captures,2,'the second user message captures its own observation')
    const forSecond=second.filter(row=>row.userMessageId==='u2')
    assert(forSecond.length>=1&&forSecond.length<=2,`second turn snapshot budget, got ${forSecond.length}`)
    assert.equal(forSecond[0].historical,undefined,'the new user message starts with a full observation')
    assert.equal(second.length,first.length+forSecond.length,
      'no scene snapshot appears outside the two user-message phases')
    console.log('scene snapshot budget: 1 full + <=1 stable summary per user turn in real DSH history')
  } finally {
    await handle?.dispose()
    await ctx.fiber.dispose()
  }
}

await run()
