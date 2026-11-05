import {NativeToolExecutor} from '@deepseek-ai/dsh-tool-executor-native'
import {PtcExecutor} from '@deepseek-ai/dsh-tool-executor-ptc'

// Scripted integration tests choose the official scoped executor only after
// a root receipt, before the next model step captures its capability set.
export function fixturePresentation(ctx) {
  const disposers=new WeakMap(),next=new Map()
  const select=(agent,mode)=>{
    disposers.get(agent)?.()
    disposers.set(agent,agent.ctx.tools.setExecutor(mode==='ptc'?new PtcExecutor(agent.ctx):new NativeToolExecutor(agent.ctx)))
  }
  ctx.on('agent/created',({agent})=>select(agent,'native'))
  ctx.on('session/event',(session,event)=>{
    const id=event.type==='tool/result'&&event.data?.message?.source?.callId
    if(!next.has(id))return
    const mode=next.get(id);next.delete(id)
    select(ctx.agents.get(session.id),mode)
  })
  return {select,after(callId,nextTool){next.set(callId,nextTool==='run_code'?'ptc':'native')}}
}
