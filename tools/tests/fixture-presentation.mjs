// DSH 0.2.1 has native and PTC presentations. Scripted integration tests switch
// only after a root tool receipt, before the next request is assembled.
export function fixturePresentation(ctx) {
  const disposers=new WeakMap(),next=new Map()
  const select=(agent,mode)=>{
    disposers.get(agent)?.()
    disposers.set(agent,agent.ctx.tools.presentAs(mode))
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
